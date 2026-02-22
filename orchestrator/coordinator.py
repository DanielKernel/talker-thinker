"""
Orchestrator - 协调器
管理Talker和Thinker的协同工作
"""
import asyncio
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from config import settings
from context.types import AgentRole, HandoffType, Message, ResponseLayer, Task, TaskComplexity
from context.session_context import SessionContext
from context.shared_context import SharedContext, ClarificationStatus
from context.summarizer import ConversationSummarizer
from agents.talker.agent import TalkerAgent
from agents.thinker.agent import ThinkerAgent
from orchestrator.scheduler import TaskScheduler, ComplexityBasedScheduler
from skills.engine import SkillsEngine
from skills.invoker import SkillInvoker
from skills.examples import (
    WeatherSkill,
    SearchSkill,
    KnowledgeSearchSkill,
    CalculatorSkill,
    UnitConverterSkill,
)


class ThinkerStage(Enum):
    """Thinker处理阶段"""
    IDLE = "idle"
    ANALYZING = "analyzing"      # 思考/分析
    PLANNING = "planning"        # 规划
    EXECUTING = "executing"      # 执行步骤
    SYNTHESIZING = "synthesizing"  # 整合/生成答案
    COMPLETED = "completed"


@dataclass
class ProgressState:
    """进度状态跟踪"""
    current_stage: ThinkerStage = ThinkerStage.IDLE
    last_stage_change: float = 0
    last_broadcast: float = 0
    last_broadcast_msg_template: str = ""  # 消息模板（不含时间）
    broadcast_count: int = 0
    current_step: int = 0
    total_steps: int = 0
    step_description: str = ""
    broadcast_history: set = field(default_factory=set)
    last_content_hash: str = ""
    used_message_templates: Dict[str, set] = field(default_factory=dict)  # 按阶段记录已使用的消息模板
    recent_message_fingerprints: List[str] = field(default_factory=list)  # 最近消息指纹（用于语义去重）


@dataclass
class HandoffContext:
    """Handoff上下文"""
    handoff_type: HandoffType
    from_agent: str
    to_agent: str
    reason: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class Orchestrator:
    """
    Orchestrator - 协调器

    核心职责：
    1. 任务调度和路由
    2. Agent之间的Handoff管理
    3. 上下文同步
    4. 状态维护
    """

    def __init__(
        self,
        talker: Optional[TalkerAgent] = None,
        thinker: Optional[ThinkerAgent] = None,
        task_scheduler: Optional[TaskScheduler] = None,
        session_context: Optional[SessionContext] = None,
        skills_engine: Optional[SkillsEngine] = None,
        summarizer: Optional[ConversationSummarizer] = None,
    ):
        # Agent实例
        self.talker = talker or TalkerAgent()
        self.thinker = thinker or ThinkerAgent()

        # 调度器
        self.task_scheduler = task_scheduler or TaskScheduler()
        self.complexity_scheduler = ComplexityBasedScheduler()

        # 会话上下文（支持Redis持久化，不可用时降级到内存）
        self.session_context = session_context or SessionContext()

        # 共享上下文（Talker和Thinker之间共享）
        self._shared_contexts: Dict[str, SharedContext] = {}

        # Skills引擎和调用器
        self.skills_engine = skills_engine or SkillsEngine()
        self.skill_invoker = SkillInvoker(self.skills_engine)
        self._initialize_default_skills()

        # 将SkillInvoker注入到Thinker
        self.thinker.set_skill_invoker(self.skill_invoker)

        # 对话摘要器（用于长对话压缩）
        self.summarizer = summarizer or ConversationSummarizer(
            summary_threshold=settings.SUMMARY_THRESHOLD
        )

        # Handoff历史
        self._handoff_history: List[HandoffContext] = []

        # 回调函数
        self._on_response: Optional[Callable] = None
        self._on_handoff: Optional[Callable] = None
        self._on_progress: Optional[Callable] = None

        # 设置进度回调
        self.talker.set_progress_callback(self._handle_progress)
        self.thinker.set_progress_callback(self._handle_progress)

        # 统计
        self._stats = {
            "total_requests": 0,
            "talker_handled": 0,
            "thinker_handled": 0,
            "handoffs": 0,
            "errors": 0,
        }
        self._precheck_timeout_s = 15.0

        # 进度状态
        self._progress_state = ProgressState()

    def _initialize_default_skills(self) -> None:
        """初始化默认技能"""
        default_skills = [
            WeatherSkill(),
            SearchSkill(),
            KnowledgeSearchSkill(),
            CalculatorSkill(),
            UnitConverterSkill(),
        ]
        for skill in default_skills:
            self.skills_engine.register_skill(skill)

    def _parse_thinker_stage(self, output: str) -> tuple[ThinkerStage, int, int, str]:
        """
        解析Thinker输出，识别当前阶段

        Returns:
            tuple: (阶段, 当前步骤, 总步骤, 步骤描述)
        """
        stage = self._progress_state.current_stage
        current_step = self._progress_state.current_step
        total_steps = self._progress_state.total_steps
        step_desc = ""

        # 检测阶段变化
        if "[思考]" in output or "正在分析" in output:
            stage = ThinkerStage.ANALYZING
        elif "[规划]" in output:
            stage = ThinkerStage.PLANNING
            # 尝试解析总步骤数
            steps_match = re.search(r"共(\d+)个步骤", output)
            if steps_match:
                total_steps = int(steps_match.group(1))
        elif "[步骤" in output:
            stage = ThinkerStage.EXECUTING
            # 解析步骤信息
            step_match = re.search(r"\[步骤(\d+)\]", output)
            if step_match:
                current_step = int(step_match.group(1))
            # 解析步骤描述
            desc_match = re.search(r"\[步骤\d+\]\s*(.+?)(?:\n|$)", output)
            if desc_match:
                step_desc = desc_match.group(1).strip()
        elif "[思考] 整合" in output or "生成最终答案" in output:
            stage = ThinkerStage.SYNTHESIZING
        elif "[答案]" in output:
            stage = ThinkerStage.COMPLETED

        return stage, current_step, total_steps, step_desc

    def _stage_from_shared_progress(self, stage_name: str) -> ThinkerStage:
        """将SharedContext中的阶段名映射为ThinkerStage。"""
        mapping = {
            "idle": ThinkerStage.IDLE,
            "analyzing": ThinkerStage.ANALYZING,
            "planning": ThinkerStage.PLANNING,
            "executing": ThinkerStage.EXECUTING,
            "synthesizing": ThinkerStage.SYNTHESIZING,
            "completed": ThinkerStage.COMPLETED,
        }
        return mapping.get((stage_name or "").lower(), ThinkerStage.IDLE)

    def _latest_shared_step_desc(self, shared: Optional[SharedContext]) -> str:
        """从SharedContext提取最近的Thinker阶段说明。"""
        if not shared:
            return ""
        partials = shared.thinker_progress.partial_results
        if not partials:
            return ""
        desc = (partials[-1] or "").strip()
        return desc[:30]


    def _is_semantic_duplicate(self, message_text: str) -> bool:
        """检测消息是否为语义重复"""
        # 计算消息的语义指纹（基于关键词）
        keywords = self._extract_semantic_keywords(message_text)
        fingerprint = f"{self._progress_state.current_stage.value}:{keywords}"

        # 检查最近 N 条消息
        recent_fingerprints = self._progress_state.recent_message_fingerprints[-5:]
        if fingerprint in recent_fingerprints:
            return True

        # 添加新指纹
        self._progress_state.recent_message_fingerprints.append(fingerprint)
        # 限制列表长度
        if len(self._progress_state.recent_message_fingerprints) > 10:
            self._progress_state.recent_message_fingerprints = self._progress_state.recent_message_fingerprints[-10:]
        return False

    def _extract_semantic_keywords(self, text: str) -> str:
        """提取消息的语义关键词"""
        # 移除时间戳、进度条等变量
        text = re.sub(r'\d+s', '', text)
        text = re.sub(r'\[.+?\]', '', text)
        text = re.sub(r'[░█\d%]', '', text)

        # 保留核心动词和名词
        keywords = re.findall(r'[整合 | 分析 | 规划 | 执行 | 检查 | 优化 | 答案 | 结果 | 步骤]', text)
        return ''.join(sorted(set(keywords)))

    def _generate_stage_broadcast(
        self,
        stage: ThinkerStage,
        user_query: str,
        elapsed_time: float,
        current_step: int = 0,
        total_steps: int = 0,
        step_desc: str = "",
        partial_results: Optional[List[str]] = None,
    ) -> tuple[str, str]:
        """
        根据阶段生成播报消息

        Returns:
            tuple: (完整消息, 消息模板)
            消息模板用于去重，不含时间戳
        """
        # 提取主题
        topic = self._extract_topic(user_query)
        stage_key = stage.value

        # 获取该阶段已使用的消息模板集合
        if stage_key not in self._progress_state.used_message_templates:
            self._progress_state.used_message_templates[stage_key] = set()

        used_templates = self._progress_state.used_message_templates[stage_key]

        # 根据已耗时选择播报风格
        if elapsed_time < 10:
            style = "initial"
        elif elapsed_time < 30:
            style = "progress"
        else:
            style = "long_wait"

        def get_unused_template(templates: list, used_set: set) -> str:
            """从未使用的模板中选择一个"""
            for t in templates:
                if t not in used_set:
                    used_set.add(t)
                    return t
            # 所有模板都用过了，返回默认
            return templates[0]

        if stage == ThinkerStage.IDLE:
            if style == "initial":
                templates = [
                    f"深度思考模块已接手，正在加载关于「{topic}」的上下文",
                    "正在准备分析环境",
                    f"正在同步「{topic}」相关信息",
                ]
            elif style == "progress":
                templates = [
                    f"仍在准备「{topic}」分析，请稍候",
                    f"即将开始分析「{topic}」",
                ]
            else:
                templates = ["准备工作进行中"]

            template = get_unused_template(templates, used_templates)
            if template == "准备工作进行中":
                return f"{template} ({elapsed_time:.0f}s)...", template
            # 注入中间结果到播报
            if partial_results and partial_results[-1]:
                latest = partial_results[-1][:25]
                return f"{template}（{latest}）...", template
            return f"{template}...", template

        if stage == ThinkerStage.ANALYZING:
            if style == "initial":
                templates = [
                    f"正在理解您关于「{topic}」的需求",
                    f"正在分析「{topic}」问题关键点",
                    f"梳理「{topic}」相关信息",
                ]
            elif style == "progress":
                templates = [
                    f"深度分析「{topic}」中，请稍候",
                    f"正在提取「{topic}」关键要素",
                ]
            else:
                # 长时间等待，显示已用时间
                templates = [f"「{topic}」分析进行中"]  # 不含时间，时间单独显示

            template = get_unused_template(templates, used_templates)
            # 如果是"分析进行中"，加上时间
            if "分析进行中" in template:
                return f"{template} ({elapsed_time:.0f}s)...", template
            # 注入中间结果到播报
            if partial_results and partial_results[-1]:
                latest = partial_results[-1][:25]
                return f"{template}（{latest}）...", template
            return f"{template}...", template

        elif stage == ThinkerStage.PLANNING:
            if style == "initial":
                templates = [
                    f"已理解「{topic}」需求，正在制定方案",
                    f"规划「{topic}」最优解决路径",
                ]
            elif style == "progress":
                templates = [
                    f"「{topic}」方案设计中",
                    f"正在分解「{topic}」任务步骤",
                ]
            else:
                templates = [f"「{topic}」规划中"]

            template = get_unused_template(templates, used_templates)
            # 注入中间结果到播报
            if partial_results and partial_results[-1]:
                latest = partial_results[-1][:25]
                return f"{template}（{latest}）...", template
            return f"{template}...", template

        elif stage == ThinkerStage.EXECUTING:
            if total_steps > 0 and current_step > 0:
                progress_pct = int((current_step / total_steps) * 100)
                # 清理步骤描述中的冗余内容
                clean_step_desc = step_desc.strip()
                # 移除步骤描述中的"正在"、"搜索"等冗余前缀
                for prefix in ["正在", "开始", "进行", "搜索", "获取", "分析"]:
                    if clean_step_desc.startswith(prefix):
                        clean_step_desc = clean_step_desc[len(prefix):].strip()
                        break
                # 限制描述长度
                if len(clean_step_desc) > 20:
                    clean_step_desc = clean_step_desc[:17] + "..."
                # 生成进度条
                progress_bar = self._format_progress_bar(current_step, total_steps)
                msg = f"步骤{current_step}/{total_steps}: {clean_step_desc} {progress_bar}"
                template = f"step_{current_step}_{total_steps}"
                return msg, template
            # 没有具体步骤信息时的降级播报
            templates = [
                f"正在处理「{topic}」核心任务",
                f"执行「{topic}」关键步骤",
            ]
            template = get_unused_template(templates, used_templates)
            # 注入中间结果到播报
            if partial_results and partial_results[-1]:
                latest = partial_results[-1][:25]
                return f"{template}（{latest}）...", template
            return f"{template}...", template

        elif stage == ThinkerStage.SYNTHESIZING:
            # 按时间顺序使用不同模板，避免随机选择导致重复
            if elapsed_time < 10:
                templates = [f"正在整合「{topic}」分析结果，请稍候..."]
            elif elapsed_time < 20:
                templates = [f"正在整理「{topic}」最终答案..."]
            elif elapsed_time < 30:
                templates = [f"即将完成，正在进行「{topic}」质量检查..."]
            else:
                templates = [f"正在优化「{topic}」答案，感谢耐心等待..."]

            # 使用时间分段选择模板
            elapsed_bucket = int(elapsed_time // 10)
            template = templates[elapsed_bucket % len(templates)]
            return template, f"synthesize_bucket_{elapsed_bucket}"

        elif stage == ThinkerStage.COMPLETED:
            return f"「{topic}」处理完成！", "处理完成"

        # 默认消息
        return f"处理中 ({elapsed_time:.0f}s)...", "处理中"

    def _is_silent_marker(self, chunk: str) -> bool:
        """检测是否为应静默处理的标记"""
        silent_patterns = [
            r'✓\s*完成\s*\(\d+ms\)',
            r'✓\s*已验证',
            r'^[-=]{3,}',
            r'执行进度\s*:',
        ]
        return any(re.match(p, chunk.strip()) for p in silent_patterns)

    def _try_rewrite_step_marker(self, chunk: str, total_steps: int) -> Optional[str]:
        """统一处理步骤标记"""
        # 匹配步骤标记：[步骤 X] 描述... 或 [步骤 X] 描述
        match = re.match(r'\[步骤 (\d+)\] (.+?)\.\.\.', chunk.strip())
        if match and total_steps > 0:
            step_num = int(match.group(1))
            step_name = match.group(2).strip()
            progress_pct = int((step_num / total_steps) * 100)
            return f"步骤{step_num}/{total_steps}: {step_name} ({progress_pct}%)"

        # 无省略号的变体
        match = re.match(r'\[步骤 (\d+)\] (.+)', chunk.strip())
        if match and total_steps > 0:
            step_num = int(match.group(1))
            step_name = match.group(2).strip()
            progress_pct = int((step_num / total_steps) * 100)
            return f"步骤{step_num}/{total_steps}: {step_name} ({progress_pct}%)"

        return None

    def _try_rewrite_synthesize_marker(self, chunk: str) -> Optional[str]:
        """统一处理整合/答案相关标记 - 使用映射表避免重复"""
        synthesize_map = {
            # 精确匹配优先
            ("整合", "答案"): "即将完成，正在整合答案...",
            ("整合结果", "最终答案"): "即将完成，正在整理最终答案...",
            # 通用模式
            ("整合", None): "正在整合内容，请稍候...",
            ("检查", "质量"): "正在进行质量检查...",
            ("优化", "答案"): "正在优化答案，请稍候...",
        }

        for (k1, k2), rewrite in synthesize_map.items():
            if k1 in chunk and (k2 is None or k2 in chunk):
                return rewrite
        return None

    def _try_rewrite_thinking_marker(self, chunk, stage, current_step, total_steps) -> Optional[str]:
        """处理思考/规划/分析标记"""
        chunk_stripped = chunk.strip()

        # [思考] 正在 xxx...（支持中文括号）
        thinking_match = re.match(r'\[思考\]\s*(.+)\.\.\.', chunk_stripped)
        if thinking_match:
            action = thinking_match.group(1)
            # 根据阶段给出更友好的描述
            if stage == ThinkerStage.ANALYZING:
                return f"正在{action}，请稍候..."
            elif stage == ThinkerStage.PLANNING:
                return f"已理解需求，{action}..."
            elif stage == ThinkerStage.EXECUTING:
                return f"{action}，进度{current_step}/{total_steps}..."
            else:
                return f"正在{action}..."

        # [思考] 没有省略号的变体
        thinking_no_dots = re.match(r'\[思考\]\s*(.+)', chunk_stripped)
        if thinking_no_dots and '...' not in chunk_stripped:
            action = thinking_no_dots.group(1).strip()
            return f"正在{action}，请稍候..."

        # [规划] 任务目标：xxx
        plan_target_match = re.match(r'\[规划\]\s*任务目标:\s*(.+)', chunk_stripped)
        if plan_target_match:
            target = plan_target_match.group(1)
            return f"已理解任务目标：{target}"

        # [规划] 共 X 个步骤
        plan_steps_match = re.match(r'\[规划\]\s*共\s*(\d+)\s*个步骤', chunk_stripped)
        if plan_steps_match:
            num_steps = int(plan_steps_match.group(1))
            return f"任务已分解为{num_steps}个步骤，开始执行..."

        # [规划] 通用模式
        if chunk_stripped.startswith("[规划]") or chunk_stripped.startswith("［规划］"):
            return "正在规划任务执行方案..."

        # [分析] 通用模式
        if chunk_stripped.startswith("[分析]") or chunk_stripped.startswith("［分析］"):
            return "正在分析问题，请稍候..."

        return None

    def _try_rewrite_thinker_output(
        self,
        chunk: str,
        stage: ThinkerStage,
        current_step: int,
        total_steps: int,
        step_desc: str,
        elapsed: float,
    ) -> Optional[str]:
        """
        尝试将 Thinker 的阶段标记输出转换为 Talker 风格的播报

        检测 Thinker 输出的阶段标记（如"[步骤 1] xxx"、"[思考] xxx"、"[规划] xxx"），
        由 Talker 重新组织语言后显示，使用户感知更一致、更友好。

        优先级重写规则：
        1. 静默处理（无意义标记）
        2. 步骤标记（最具体，优先匹配）
        3. 整合/答案标记（使用统一映射表）
        4. 思考/规划/分析标记

        Returns:
            Optional[str]: 如果检测到阶段标记则返回重写后的播报，否则返回 None
        """
        chunk_stripped = chunk.strip()

        # 优先级 1: 静默处理（无意义标记）
        if self._is_silent_marker(chunk_stripped):
            return None

        # 优先级 2: 步骤标记（最具体，优先匹配）
        rewrite = self._try_rewrite_step_marker(chunk_stripped, total_steps)
        if rewrite:
            return rewrite

        # 优先级 3: 整合/答案标记（使用统一映射表）
        rewrite = self._try_rewrite_synthesize_marker(chunk_stripped)
        if rewrite:
            return rewrite

        # 空白字符容错：移除所有空白字符后再匹配
        normalized = re.sub(r'\s+', '', chunk_stripped)

        # === 检测 Thinker 阶段标记 ===

        # "开始处理..." → 已启动（支持多种变体）
        if chunk_stripped.startswith("开始处理") or re.search(r'开始\s*处理', chunk_stripped) or '开始处理' in normalized:
            return "已启动，正在分析您的问题..."

        # "开始 xxx..." 通用模式
        if chunk_stripped.startswith("开始") and "..." in chunk_stripped:
            action = chunk_stripped[2:].split('.')[0].strip()
            return f"开始{action}，请稍候..."

        # "正在 xxx..." → 正在 xxx，请稍候...（支持更宽松的检测）
        if chunk_stripped.startswith("正在") and "..." in chunk_stripped:
            return f"{chunk_stripped}请稍候..."

        # "正在 xxx" 没有省略号的变体
        if chunk_stripped.startswith("正在") and len(chunk_stripped) > 4:
            return f"{chunk_stripped}，请稍候..."

        # "整合结果，生成最终答案..." → 即将完成
        if "整合" in chunk_stripped and "答案" in chunk_stripped:
            return "即将完成，正在整合答案..."

        # "整合 xxx" 通用模式
        if chunk_stripped.startswith("整合"):
            return "正在整合内容，请稍候..."

        # "检查答案质量..." → 质量检查中
        if "检查" in chunk_stripped and "质量" in chunk_stripped:
            return "正在进行质量检查..."

        # "检查 xxx" 通用模式
        if chunk_stripped.startswith("检查") and "..." in chunk_stripped:
            return f"正在{chunk_stripped}，请稍候..."

        # "答案需要改进，正在优化..." → 优化中
        if "优化" in chunk_stripped and "答案" in chunk_stripped:
            return "正在优化答案，请稍候..."

        # "优化 xxx" 通用模式
        if chunk_stripped.startswith("优化") and "..." in chunk_stripped:
            return f"正在{chunk_stripped}，请稍候..."

        # [步骤 X] 步骤名称...（支持中文括号和空格变体）
        step_match = re.match(r'[\[［] 步骤\s*(\d+)[\]］]\s*([^\.\.]+)\.\.\.', chunk_stripped)
        if step_match and total_steps > 0:
            step_num = int(step_match.group(1))
            step_name = step_match.group(2).strip()
            progress_pct = int((step_num / total_steps) * 100)
            return f"步骤{step_num}/{total_steps}: {step_name}（{progress_pct}%）"

        # [步骤 X] 没有省略号的变体
        step_no_dots = re.match(r'[\[［] 步骤\s*(\d+)[\]］]\s*(.+)', chunk_stripped)
        if step_no_dots and total_steps > 0 and '...' not in chunk_stripped:
            step_num = int(step_no_dots.group(1))
            step_name = step_no_dots.group(2).strip()
            progress_pct = int((step_num / total_steps) * 100)
            return f"步骤{step_num}/{total_steps}: {step_name}（{progress_pct}%）"

        # [思考] 正在 xxx...（支持中文括号）
        thinking_match = re.match(r'[\[［] 思考[\]］]\s*(.+)\.\.\.', chunk_stripped)
        if thinking_match:
            action = thinking_match.group(1)
            # 根据阶段给出更友好的描述
            if stage == ThinkerStage.ANALYZING:
                return f"正在{action}，请稍候..."
            elif stage == ThinkerStage.PLANNING:
                return f"已理解需求，{action}..."
            elif stage == ThinkerStage.EXECUTING:
                return f"{action}，进度{current_step}/{total_steps}..."
            else:
                return f"正在{action}..."

        # [思考] 没有省略号的变体
        thinking_no_dots = re.match(r'[\[［] 思考[\]］]\s*(.+)', chunk_stripped)
        if thinking_no_dots and '...' not in chunk_stripped:
            action = thinking_no_dots.group(1).strip()
            return f"正在{action}，请稍候..."

        # [规划] 任务目标：xxx
        plan_target_match = re.match(r'[\[［] 规划[\]］]\s*任务目标:\s*(.+)', chunk_stripped)
        if plan_target_match:
            target = plan_target_match.group(1)
            return f"已理解任务目标：{target}"

        # [规划] 共 X 个步骤
        plan_steps_match = re.match(r'[\[［] 规划[\]］]\s*共\s*(\d+)\s*个步骤', chunk_stripped)
        if plan_steps_match:
            num_steps = int(plan_steps_match.group(1))
            return f"任务已分解为{num_steps}个步骤，开始执行..."

        # [规划] 通用模式
        if chunk_stripped.startswith("[规划]") or chunk_stripped.startswith("［规划］"):
            return "正在规划任务执行方案..."

        # [分析] 通用模式（新增支持）
        if chunk_stripped.startswith("[分析]") or chunk_stripped.startswith("［分析］"):
            return "正在分析问题，请稍候..."

        # [答案] xxx - 最终答案，静默处理，由后续逻辑处理
        answer_match = re.match(r'[\[［] 答案[\]］]\s*(.+)', chunk_stripped)
        if answer_match:
            # 最终答案内容，返回 None 让正常流程处理
            return None

        # 通用阶段标记处理 - fallback 机制
        # 检查是否是 Thinker 的阶段标记格式：[阶段名] 内容
        stage_marker_match = re.match(r'[\[［](步骤 | 思考 | 规划 | 分析 | 执行 | 整合 | 答案)[\]］]\s*(.+)', chunk_stripped)
        if stage_marker_match:
            stage_type = stage_marker_match.group(1)
            content = stage_marker_match.group(2)
            # 通用的阶段标记处理
            return "正在处理中，请稍候..."

        # 空白字符容错检测：对于短内容，使用 normalized 再次检测
        if len(normalized) < 20:
            if '开始处理' in normalized:
                return "已启动，正在分析您的问题..."
            if '正在分析' in normalized:
                return "正在分析问题，请稍候..."
            if '整合答案' in normalized:
                return "即将完成，正在整合答案..."

        # 未检测到阶段标记，返回 None 让原始输出显示
        return None

    def _format_progress_bar(self, current: int, total: int, width: int = 20) -> str:
        """
        生成进度条字符串

        Args:
            current: 当前步骤
            total: 总步骤数
            width: 进度条宽度（字符数）

        Returns:
            进度条字符串，如：[████████████░░░░░░░░] 60%
        """
        if total <= 0:
            return ""

        percent = current / total
        filled = int(width * percent)
        empty = width - filled

        # 使用 Unicode 块字符创建进度条
        bar = "█" * filled + "░" * empty
        return f"[{bar}] {int(percent * 100)}%"

    def _get_emotional_broadcast_suffix(self, elapsed: float, user_complaint: bool = False) -> str:
        """
        根据已耗时和用户情绪生成播报后缀（安抚性话语）

        Args:
            elapsed: 已用时间（秒）
            user_complaint: 用户是否表达了不满

        Returns:
            安抚性后缀字符串
        """
        if user_complaint:
            # 用户有抱怨，使用更安抚的语气
            if elapsed < 30:
                return "，马上就好~"
            elif elapsed < 60:
                return "，再给我一点时间~"
            else:
                return "，这个任务确实有点复杂，感谢您的耐心！"
        else:
            # 正常语气
            if elapsed < 30:
                return "，请稍候..."
            elif elapsed < 60:
                return "，还需一点时间..."
            else:
                return "，复杂任务需要更多时间，感谢等待~"

    def _extract_topic(self, query: str) -> str:
        """从用户问题中提取主题"""
        query_lower = query.lower()

        # 话题关键词配置：按优先级排序，具体话题在前，通用话题在后
        # 每个话题的关键词按特异性排序，具体词在前，通用词在后
        topic_keywords = [
            # 具体话题优先（避免被通用话题覆盖）
            ("奶茶", ["奶茶", "波霸", "珍珠奶茶", "鲜奶茶"]),
            ("咖啡", ["咖啡", "拿铁", "星巴克", "瑞幸", "美式", "卡布奇诺"]),
            ("打车", ["打车", "滴滴", "高德", "专车", "快车", "网约车"]),
            ("选车", ["车", "汽车", "车型", "品牌", "suv", "轿车", "买车", "选车", "新能源车"]),
            ("旅游", ["旅游", "旅行", "景点", "酒店", "机票", "去哪玩", "出去玩"]),
            ("美食", ["美食", "餐厅", "餐馆", "菜", "吃", "推荐菜", "小吃", "甜品"]),
            # 通用话题放最后（避免过度匹配）
            ("购物", ["购物", "价格", "便宜", "对比", "买东西"]),
        ]

        # 第一轮：精确匹配具体话题
        for topic, keywords in topic_keywords:
            if any(kw in query_lower for kw in keywords):
                return topic

        # 第二轮：检查是否包含"买"字但没有具体话题
        # 如果查询中有具体物品（如"买奶茶"），提取物品名作为话题
        if "买" in query_lower:
            # 尝试提取"买"后面的物品
            match = re.search(r'买 ([\u4e00-\u9fa5]{2,6})', query_lower)
            if match:
                return match.group(1)

        # 第三轮：提取问题中的关键词作为主题
        words = re.findall(r'[\u4e00-\u9fa5]{2,4}', query)
        if words:
            return words[0]
        return "您的问题"

    def _extract_user_preferences(self, text: str) -> Dict[str, Any]:
        """从输入中提取可持久化的用户偏好（通用建模，不强绑定具体场景）。"""
        text = (text or "").lower().strip()
        prefs: Dict[str, Any] = {}
        likes: List[str] = []
        dislikes: List[str] = []
        constraints: List[str] = []

        for pat in [r"我喜欢([^，。；,!?？]{1,20})", r"偏好([^，。；,!?？]{1,20})", r"更喜欢([^，。；,!?？]{1,20})"]:
            likes.extend([m.strip() for m in re.findall(pat, text) if m.strip()])
        for pat in [r"我不喜欢([^，。；,!?？]{1,20})", r"不要([^，。；,!?？]{1,20})", r"避免([^，。；,!?？]{1,20})"]:
            dislikes.extend([m.strip() for m in re.findall(pat, text) if m.strip()])
        for pat in [r"希望([^，。；,!?？]{1,20})", r"最好([^，。；,!?？]{1,20})", r"需要([^，。；,!?？]{1,20})"]:
            constraints.extend([m.strip() for m in re.findall(pat, text) if m.strip()])

        if likes:
            prefs["likes"] = list(dict.fromkeys(likes))
        if dislikes:
            prefs["dislikes"] = list(dict.fromkeys(dislikes))
        if constraints:
            prefs["constraints"] = list(dict.fromkeys(constraints))

        # 兼容既有高频偏好字段
        if any(k in text for k in ["喜欢吃辣", "爱吃辣", "能吃辣", "口味重"]):
            prefs["taste"] = "喜欢吃辣"
        elif any(k in text for k in ["不吃辣", "不能吃辣", "清淡"]):
            prefs["taste"] = "偏清淡/不吃辣"

        budget_match = re.search(r"(\d{1,3})\s*万", text)
        if budget_match:
            prefs["budget"] = f"{budget_match.group(1)}万"
        amount_match = re.search(r"(\d{2,6})\s*(元|块)", text)
        if amount_match and "budget" not in prefs:
            prefs["budget"] = f"{amount_match.group(1)}{amount_match.group(2)}"

        if "suv" in text or "越野" in text:
            prefs["car_type"] = "偏好SUV"
        elif "轿车" in text:
            prefs["car_type"] = "偏好轿车"
        return prefs

    def _merge_user_preferences(self, base: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
        """合并偏好：列表去重并保序，字典递归合并，标量覆盖。"""
        merged: Dict[str, Any] = dict(base or {})
        for k, v in (new or {}).items():
            if k not in merged:
                merged[k] = v
                continue
            old = merged[k]
            if isinstance(old, list) and isinstance(v, list):
                merged[k] = list(dict.fromkeys([*old, *v]))
            elif isinstance(old, dict) and isinstance(v, dict):
                merged[k] = {**old, **v}
            else:
                merged[k] = v
        return merged

    async def persist_user_preferences(self, text: str) -> Dict[str, Any]:
        """提取并持久化用户偏好，返回最新偏好。"""
        global_pref_sid = "__global_user__"
        persisted_prefs = await self.session_context.get_session_data(
            global_pref_sid, "user_preferences", {}
        ) or {}
        extracted_prefs = self._extract_user_preferences(text)
        if extracted_prefs:
            persisted_prefs = self._merge_user_preferences(persisted_prefs, extracted_prefs)
            await self.session_context.set_session_data(
                global_pref_sid, "user_preferences", persisted_prefs, ttl=86400 * 30
            )
        return persisted_prefs

    def _should_broadcast(
        self,
        new_stage: ThinkerStage,
        current_step: int,
        elapsed_time: float,
        content_hash: str,
        message_text: str = "",  # 新增：待播报的消息文本
        force_check: bool = False,
    ) -> tuple[bool, str]:
        """
        判断是否需要播报

        Args:
            new_stage: 当前阶段
            current_step: 当前步骤
            elapsed_time: 已耗时
            message_text: 待播报的消息文本（用于语义去重）
            force_check: 是否强制检查（忽略最小间隔）

        Returns:
            tuple: (是否播报, 原因)
        """
        state = self._progress_state
        current_time = time.time()

        # 阶段变化，立即播报
        if new_stage != state.current_stage:
            return True, "stage_changed"

        # 步骤变化（执行阶段）
        if new_stage == ThinkerStage.EXECUTING and current_step != state.current_step and current_step > 0:
            return True, "step_changed"

        # 无进度变化时，降低播报频率（仅保留心跳播报）
        if content_hash == state.last_content_hash:
            if current_time - state.last_broadcast < 15:
                return False, "no_progress"
            return True, "heartbeat"


        # 语义去重检查
        if message_text and self._is_semantic_duplicate(message_text):
            return False, "semantic_duplicate"

        # 检查该阶段已使用的模板数量
        stage_key = new_stage.value
        template_count = len(state.used_message_templates.get(stage_key, set()))
        max_templates_per_stage = 4  # 每阶段最多4条不同消息

        if template_count >= max_templates_per_stage:
            return False, "max_templates_reached"

        return True, "interval_elapsed"

    def _hash_broadcast_content(self, stage: ThinkerStage, step: int, elapsed: float) -> str:
        """生成播报内容的哈希值，用于去重"""
        # 使用阶段和步骤的整数部分作为哈希基础
        elapsed_bucket = int(elapsed // 5) * 5  # 每5秒一个桶
        return f"{stage.value}_{step}_{elapsed_bucket}"

    def set_callbacks(
        self,
        on_response: Optional[Callable] = None,
        on_handoff: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
    ) -> None:
        """设置回调函数"""
        self._on_response = on_response
        self._on_handoff = on_handoff
        self._on_progress = on_progress

    async def process(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        received_time: Optional[float] = None,
    ) -> AsyncIterator[str]:
        """
        处理用户输入

        Args:
            user_input: 用户输入
            session_id: 会话ID
            context: 额外上下文
            received_time: 消息接收时间

        Yields:
            str: 响应内容
        """
        self._stats["total_requests"] += 1
        start_time = time.time()
        if received_time is None:
            received_time = start_time

        # 初始化会话
        if session_id is None:
            import uuid
            session_id = str(uuid.uuid4())

        # 使用SessionContext获取会话（支持持久化）
        session = await self._get_or_create_session(session_id)

        # 添加用户消息到SessionContext
        user_message = Message(
            role="user",
            content=user_input,
            timestamp=time.time(),
        )
        await self.session_context.add_message(session_id, user_message)

        # 创建/获取共享上下文
        shared = self._get_or_create_shared_context(session_id)
        persisted_prefs = await self.persist_user_preferences(user_input)
        shared.user_preferences = persisted_prefs
        if not shared.needs_clarification():
            shared.user_input = user_input
            shared.clarified_intent = user_input
        shared.is_processing = True

        effective_input = user_input

        # === 检查是否是回答澄清问题 ===
        if shared.needs_clarification():
            # 用户可能是在回答澄清问题
            pending = shared.get_pending_clarification()
            if pending:
                # 记录回答
                shared.answer_clarification(user_input)
                # 更新意图
                shared.update_intent_with_clarification(user_input)
                effective_input = shared.clarified_intent or shared.user_input or user_input

                # 给用户确认反馈
                ts = time.strftime("%H:%M:%S", time.localtime())
                ms = int((time.time() % 1) * 1000)
                yield f"\n[{ts}.{ms:03d}] Talker: 收到，已更新您的需求信息"
                shared.add_talker_interaction("收到，已更新您的需求信息", "clarification")

                # 标记为继续处理，但使用更新后的意图
                # 如果澄清后的意图足够简单，可以让Talker处理
                # 否则继续交给Thinker

        # 构建完整上下文（包含共享上下文和摘要）
        # 获取会话摘要（如果有的话）
        session_summary = await self.session_context.get_summary(session_id)

        # 如果没有摘要且消息较多，生成摘要
        messages = await self.session_context.get_messages(session_id, limit=50)
        if not session_summary and len(messages) >= settings.SUMMARY_THRESHOLD:
            session_summary = await self.summarizer.summarize_recent_messages(messages)
            if session_summary:
                await self.session_context.set_summary(session_id, session_summary)

        full_context = {
            **(context or {}),
            "session_id": session_id,
            "messages": session["messages"],
            "received_time": received_time,
            "shared": shared,  # 添加共享上下文
            "session_summary": session_summary,  # 添加会话摘要
            "effective_input": effective_input,
            "user_preferences": persisted_prefs,
        }

        # 收集助手响应用于保存到会话
        assistant_response_chunks = []

        try:
            # 使用Talker进行意图分类
            classification = await self.talker.classify_intent(effective_input, full_context)

            # 根据复杂度选择处理策略
            if classification.complexity == TaskComplexity.COMPLEX:
                # 复杂任务：使用协作模式
                self._stats["thinker_handled"] += 1
                async for chunk in self._collaboration_handoff(
                    effective_input, full_context, received_time=received_time
                ):
                    assistant_response_chunks.append(chunk)
                    yield chunk
            else:
                # 简单/中等任务：Talker处理
                self._stats["talker_handled"] += 1
                async for chunk in self._delegation_handoff(
                    effective_input, full_context, classification, received_time=received_time
                ):
                    assistant_response_chunks.append(chunk)
                    yield chunk

        except Exception as e:
            self._stats["errors"] += 1
            error_msg = f"抱歉，处理时出现错误：{str(e)}"
            assistant_response_chunks.append(error_msg)
            yield error_msg

        finally:
            # 保存助手响应到会话（清理掉元数据标记）
            assistant_response = "".join(assistant_response_chunks)
            # 移除时间戳和Agent标识等元数据，只保留实际回复内容
            # 移除类似 [HH:MM:SS.mmm] Talker: 的标记
            clean_response = re.sub(r'\n?\[\d{2}:\d{2}:\d{2}\.\d{3}\]\s*(Talker|Thinker):\s*', '', assistant_response)
            # 移除类似 [Talker] ... 的标记
            clean_response = re.sub(r'\n?\[Talker\][^\n]*', '', clean_response)
            clean_response = re.sub(r'\n?\[Thinker\][^\n]*', '', clean_response)
            # 移除 [Talker -> Thinker | ...] 的标记
            clean_response = re.sub(r'\n?\[Talker[^\]]*\]\s*', '', clean_response)
            clean_response = re.sub(r'\n?\[Thinker[^\]]*\]\s*', '', clean_response)
            # 移除性能指标区块（包含📊符号的部分）
            clean_response = re.sub(r'\n-{10,}.*?-{10,}', '', clean_response, flags=re.DOTALL)
            # 移除剩余的指标行
            clean_response = re.sub(r'\n\s*📊[^\n]*', '', clean_response)
            clean_response = re.sub(r'\n\s*(Tokens|TTFT|TPOT|TPS|总生成时延|LLM请求时间)[^\n]*', '', clean_response)
            # 清理多余空行
            clean_response = re.sub(r'\n{3,}', '\n\n', clean_response)
            clean_response = clean_response.strip()

            if clean_response:
                # 使用SessionContext保存助手响应
                assistant_message = Message(
                    role="assistant",
                    content=clean_response,
                    timestamp=time.time(),
                )
                await self.session_context.add_message(session_id, assistant_message)

            # 更新共享上下文状态
            shared.is_processing = False

            elapsed = (time.time() - start_time) * 1000
            await self.session_context.set_session_data(session_id, "last_latency_ms", elapsed)

    async def _delegation_handoff(
        self,
        user_input: str,
        context: Dict[str, Any],
        classification,
        received_time: float = None,
    ) -> AsyncIterator[str]:
        """
        委托模式Handoff

        Talker处理简单/中等任务，复杂任务委托给Thinker
        改进：独立于Talker输出频率进行定时播报
        """
        # 格式化时间戳（精确到毫秒）
        def format_timestamp(t):
            ts = time.strftime("%H:%M:%S", time.localtime(t))
            ms = int((t % 1) * 1000)
            return f"{ts}.{ms:03d}"

        # 记录LLM请求发送时间
        llm_request_time = time.time()

        # 使用队列收集Talker输出
        talker_queue = asyncio.Queue()
        talker_complete = False

        async def run_talker():
            """运行Talker并收集输出"""
            nonlocal talker_complete
            try:
                async for chunk in self.talker.process(user_input, context):
                    await talker_queue.put(chunk)
            except Exception as e:
                logger.error(f"Talker task error: {e}")
            finally:
                talker_complete = True

        # 启动Talker任务
        talker_task = asyncio.create_task(run_talker())
        TALKER_TIMEOUT = 120.0  # 120 秒超时
        # 循环保护：防止无限循环
        loop_iteration_count = 0
        max_loop_iterations = 10000  # 最大循环次数


        # 处理Talker输出
        first_token_time = None
        first_timestamp_shown = False
        last_broadcast_time = llm_request_time
        broadcast_count = 0
        used_broadcast_templates = set()  # 追踪已使用的消息模板

        def get_talker_broadcast_interval(elapsed: float) -> float:
            """动态计算播报间隔 - 更保守"""
            if elapsed < 15:
                return 4.0  # 初始4秒
            elif elapsed < 30:
                return 6.0  # 中期6秒
            else:
                return 8.0  # 后期8秒

        while not talker_complete or not talker_queue.empty():
            loop_iteration_count += 1

            # 循环次数保护
            if loop_iteration_count > max_loop_iterations:
                logger.warning(f"Talker loop exceeded {max_loop_iterations} iterations, breaking")
                break

            current_time = time.time()
            elapsed = current_time - llm_request_time
            
            # 超时保护
            # 超时保护
            if elapsed > TALKER_TIMEOUT:
                logger.warning(f"Talker task timeout ({TALKER_TIMEOUT}s), cancelling...")
                talker_task.cancel()
                break

            # === 播报检查 ===
            broadcast_interval = get_talker_broadcast_interval(elapsed)
            if current_time - last_broadcast_time >= broadcast_interval:
                ts = format_timestamp(current_time)

                # 根据时间选择播报模板
                if elapsed < 15:
                    templates = ["正在处理", "思考中"]
                elif elapsed < 30:
                    templates = ["仍在处理中", "请稍候"]
                else:
                    templates = ["响应较慢"]  # 模板不含时间

                # 选择未使用的模板
                template = None
                for t in templates:
                    if t not in used_broadcast_templates:
                        template = t
                        used_broadcast_templates.add(t)
                        break

                if template is None:
                    # 所有模板都用过了，用默认
                    template = "处理中"

                # 生成完整消息
                if template == "响应较慢":
                    msg = f"{template} ({elapsed:.0f}s)..."
                else:
                    msg = f"{template}..."

                yield f"\n[{ts}] Talker: {msg}"
                last_broadcast_time = current_time
                broadcast_count += 1

                # 限制最大播报次数
                if broadcast_count >= 5:
                    break

            # 尝试获取输出
            try:
                chunk = await asyncio.wait_for(talker_queue.get(), timeout=0.1)

                # 检查是否需要转交给Thinker
                if "[NEEDS_THINKER]" in chunk:
                    # 记录Handoff
                    self._record_handoff(
                        HandoffType.DELEGATION,
                        "talker",
                        "thinker",
                        "任务复杂度超过Talker能力",
                    )

                    # 切换到协作模式
                    async for thinker_chunk in self._collaboration_handoff(
                        user_input, context, llm_request_time, received_time=received_time
                    ):
                        yield thinker_chunk
                    return

                # 记录第一个有效内容的时间
                if first_token_time is None and chunk.strip():
                    first_token_time = time.time()
                    # 在内容前显示Talker时间戳
                    if settings.SHOW_AGENT_IDENTITY and not first_timestamp_shown:
                        yield f"\n[{format_timestamp(first_token_time)}] Talker: "
                        first_timestamp_shown = True

                yield chunk

            except asyncio.TimeoutError:
                # 超时，继续循环检查播报
                continue

        # 显示详细指标
        if settings.SHOW_AGENT_IDENTITY:
            metrics = context.get("_llm_metrics", {}) if context else {}
            yield "\n" + self._format_metrics(metrics, llm_request_time, first_token_time)

    def _format_metrics(self, metrics: dict, llm_request_time: float, first_token_time: float = None) -> str:
        """格式化指标输出"""
        def format_timestamp(t):
            ts = time.strftime("%H:%M:%S", time.localtime(t))
            ms = int((t % 1) * 1000)
            return f"{ts}.{ms:03d}"

        lines = ["-" * 50]
        lines.append("📊 模型性能指标")

        # Token统计
        input_tokens = metrics.get("input_tokens", 0)
        output_tokens = metrics.get("output_tokens", 0)
        if input_tokens or output_tokens:
            lines.append(f"  Tokens: 输入={input_tokens} | 输出={output_tokens}")

        # 时延指标
        ttft = metrics.get("ttft_ms", 0)
        tpot = metrics.get("tpot_ms", 0)
        total_time = metrics.get("total_time_ms", 0)

        if ttft:
            lines.append(f"  TTFT(首Token响应时延): {ttft:.0f}ms")
        if total_time:
            lines.append(f"  响应时延(生成总耗时): {total_time:.0f}ms")
        if tpot:
            lines.append(f"  TPOT(平均每Token时延): {tpot:.1f}ms")

        # TPS吞吐
        tps = metrics.get("tps", 0)
        if tps:
            lines.append(f"  TPS(模型吞吐): {tps:.1f} tokens/s")

        # 时间戳
        lines.append(f"  LLM请求发送时间: {format_timestamp(llm_request_time)}")
        if first_token_time:
            lines.append(f"  LLM首Token时间: {format_timestamp(first_token_time)}")
        lines.append("-" * 50)

        return "\n".join(lines)

    async def _collaboration_handoff(
        self,
        user_input: str,
        context: Dict[str, Any],
        llm_request_time: float = None,
        received_time: float = None,
    ) -> AsyncIterator[str]:
        """
        协作模式Handoff

        Talker收集信息，Thinker深度处理，Talker播报
        关键改进：独立于Thinker输出频率进行定时播报
        """
        def format_timestamp(t):
            ts = time.strftime("%H:%M:%S", time.localtime(t))
            ms = int((t % 1) * 1000)
            return f"{ts}.{ms:03d}"

        thinker_start = time.time()
        if llm_request_time is None:
            llm_request_time = thinker_start

        # 重置进度状态
        self._progress_state = ProgressState()
        self._progress_state.last_stage_change = thinker_start
        self._progress_state.last_broadcast = thinker_start - 3  # 允许立即播报

        # 获取共享上下文
        shared = context.get("shared")

        # 确保Thinker有共享上下文的引用
        if shared:
            self.thinker.set_shared_context(shared)

        # Talker首先给用户反馈
        if settings.SHOW_AGENT_IDENTITY:
            timestamp = format_timestamp(thinker_start)
            yield f"\n[{timestamp}] Talker: 好的，这个问题需要深度思考，已转交给深度思考模块处理"

        # === 澄清机制：检测是否需要澄清（带主动播报） ===
        async def run_precheck():
            quick_plan = await self.thinker.plan_task(user_input, context)
            needs_clarification, reason, missing_info = await self.thinker.needs_clarification(
                user_input, quick_plan, context
            )
            question = None
            if needs_clarification and missing_info and shared:
                question = await self.thinker.generate_clarification_question(
                    user_input, missing_info, context
                )
            return quick_plan, needs_clarification, reason, missing_info, question

        precheck_task = asyncio.create_task(run_precheck())
        precheck_last_broadcast = thinker_start
        # 预检查阶段播报模板（有限集合，按顺序使用）
        precheck_templates = ["正在分析关键信息", "正在核对必要条件", "即将进入详细推理"]
        precheck_idx = 0
        last_precheck_template = ""
        precheck_timed_out = False
        precheck_first_feedback_shown = False  # 确保 2 秒内有首次反馈

        while not precheck_task.done():
            now = time.time()
            elapsed_since_start = now - thinker_start

            # 超时处理
            if now - thinker_start >= self._precheck_timeout_s:
                precheck_timed_out = True
                precheck_task.cancel()
                ts = format_timestamp(now)
                timeout_msg = "预分析耗时较长，先进入详细处理"
                yield f"\n[{ts}] Talker: {timeout_msg}..."
                if shared:
                    shared.add_talker_interaction(timeout_msg, "broadcast")
                break

            # 确保 2 秒内有首次反馈（SLA）
            if not precheck_first_feedback_shown and elapsed_since_start >= 2.0:
                ts = format_timestamp(now)
                yield f"\n[{ts}] Talker: 正在同步上下文并规划步骤，请稍候..."
                if shared:
                    shared.add_talker_interaction("正在同步上下文并规划步骤", "broadcast")
                precheck_first_feedback_shown = True
                precheck_last_broadcast = now
                continue

            # 常规播报（5 秒间隔）
            if now - precheck_last_broadcast >= 5.0:
                if precheck_idx < len(precheck_templates):
                    msg = precheck_templates[precheck_idx]
                    msg_template = f"precheck_{precheck_idx}"
                else:
                    elapsed = int(now - thinker_start)
                    msg = f"预分析进行中（{elapsed}s）"
                    msg_template = f"precheck_elapsed_{elapsed // 10}"
                if msg_template != last_precheck_template:
                    ts = format_timestamp(now)
                    yield f"\n[{ts}] Talker: {msg}..."
                    if shared:
                        shared.add_talker_interaction(msg, "broadcast")
                    last_precheck_template = msg_template
                precheck_last_broadcast = now
                precheck_idx += 1
            await asyncio.sleep(0.1)

        quick_plan = None
        try:
            if not precheck_timed_out:
                quick_plan, needs_clarification, reason, missing_info, question = await precheck_task
                if not needs_clarification and quick_plan and getattr(quick_plan, "steps", None):
                    ts = format_timestamp(time.time())
                    yield f"\n[{ts}] Talker: 深度思考模块已完成规划，预计{len(quick_plan.steps)}步执行"
                if needs_clarification and missing_info and shared and question:
                    ts = format_timestamp(time.time())
                    yield f"\n[{ts}] Talker: {question}"
                    shared.add_talker_interaction(question, "clarification")
                    shared.add_clarification_request(question, reason or "", [])
                    shared.clarification_status = ClarificationStatus.PENDING
                    return
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

        # 记录Handoff到Thinker
        self._record_handoff(
            HandoffType.COLLABORATION,
            "talker",
            "thinker",
            "启动协作模式",
        )

        # Thinker 开始工作的提示 - 由 Talker 播报，后续劫持机制会处理

        # 收集Thinker的输出
        thinker_output = []
        thinker_complete = False
        accumulated_output = ""
        thinker_first_token_shown = False
        # 标记：precheck 超时后已播报，避免与 Thinker 劫持输出重复
        precheck_timeout_broadcast = precheck_timed_out

        # 播报控制 - 使用独立的时间检查（动态间隔）
        last_broadcast_time = thinker_start

        def get_broadcast_interval(elapsed: float) -> float:
            """根据已耗时动态计算播报间隔 - 更保守"""
            if elapsed < 15:
                return 4.0  # 初始4秒
            elif elapsed < 30:
                return 6.0  # 中期6秒
            else:
                return 8.0  # 后期8秒
        output_index = 0

        async def run_thinker():
            """运行Thinker并收集输出"""
            nonlocal thinker_complete
            try:
                async for chunk in self.thinker.process(user_input, context):
                    thinker_output.append(chunk)
            except Exception as e:
                logger.error(f"Thinker task error: {e}")
            finally:
                thinker_complete = True

        # 启动Thinker任务
        thinker_task = asyncio.create_task(run_thinker())
        THINKER_TIMEOUT = 300.0  # 300 秒超时

        # 主循环：处理Thinker输出和播报
        # 添加超时保护变量
        last_output_time = thinker_start
        max_wait_time = 30.0  # 最大等待时间（秒）
        
        # 循环保护：防止无限循环
        loop_iteration_count = 0
        max_loop_iterations = 10000  # 最大循环次数

        while not thinker_complete or output_index < len(thinker_output):
            loop_iteration_count += 1

            # 循环次数保护
            if loop_iteration_count > max_loop_iterations:
                logger.warning(f"Loop exceeded {max_loop_iterations} iterations, breaking")
                break

            current_time = time.time()
            elapsed = current_time - thinker_start
            
            # 超时保护 1: 整体任务超时
            if elapsed > THINKER_TIMEOUT:
                logger.warning(f"Thinker task timeout ({THINKER_TIMEOUT}s), cancelling...")
                thinker_task.cancel()
                break
            
            # 超时保护 2: Thinker 已完成但输出处理卡住
            if thinker_complete and current_time - last_output_time > max_wait_time:
                logger.warning(f"Thinker output processing timeout ({max_wait_time}s), breaking loop...")
                break

            # === 播报检查 ===
            broadcast_interval = get_broadcast_interval(elapsed)
            if current_time - last_broadcast_time >= broadcast_interval:
                # 优先使用SharedContext中的实时进度，回退到输出解析
                if shared and shared.thinker_progress.current_stage != "idle":
                    new_stage = self._stage_from_shared_progress(shared.thinker_progress.current_stage)
                    current_step = shared.thinker_progress.current_step
                    total_steps = shared.thinker_progress.total_steps
                    step_desc = self._latest_shared_step_desc(shared)
                else:
                    new_stage, current_step, total_steps, step_desc = self._parse_thinker_stage(accumulated_output)

                # 检查是否需要播报
                content_hash = f"{new_stage.value}:{current_step}:{total_steps}:{step_desc[:20]}"
                should_broadcast, reason = self._should_broadcast(
                    new_stage,
                    current_step,
                    elapsed,
                    content_hash,
                )

                if should_broadcast:
                    # 生成播报消息和模板
                    if reason == "heartbeat":
                        # 基于真实进度生成播报，而不是机械的"仍在 xx 阶段"
                        stage_zh = {
                            ThinkerStage.ANALYZING: "分析",
                            ThinkerStage.PLANNING: "规划",
                            ThinkerStage.EXECUTING: "执行",
                            ThinkerStage.SYNTHESIZING: "整合",
                            ThinkerStage.IDLE: "准备",
                            ThinkerStage.COMPLETED: "收尾",
                        }.get(new_stage, "处理")

                        # 优先显示详细进度信息（带进度条）
                        if total_steps > 0 and current_step > 0:
                            progress_pct = int((current_step / total_steps) * 100)
                            progress_bar = self._format_progress_bar(current_step, total_steps)
                            if step_desc:
                                # 有步骤描述：显示具体步骤信息 + 进度条
                                broadcast_msg = f"步骤{current_step}/{total_steps}: {step_desc} {progress_bar}"
                                msg_template = f"step_{current_step}_{total_steps}"
                            else:
                                # 无步骤描述：显示进度条
                                broadcast_msg = f"执行中 {progress_bar}（{current_step}/{total_steps} 步）"
                                msg_template = f"progress_{current_step}_{total_steps}"
                        elif shared and shared.thinker_progress.partial_results:
                            # 有中间结果：显示最新结果
                            latest = shared.thinker_progress.partial_results[-1]
                            if latest and len(latest) < 50:
                                broadcast_msg = f"{stage_zh}中：{latest}"
                                msg_template = f"result_{hash(latest) % 1000}"
                            else:
                                # 有中间结果但太长，显示时间 + 安抚
                                user_complaint = shared and shared.get_user_emotion() == "complaint"
                                suffix = self._get_emotional_broadcast_suffix(elapsed, user_complaint=user_complaint)
                                broadcast_msg = f"仍在{stage_zh}阶段（{elapsed:.0f}s）{suffix}"
                                msg_template = f"heartbeat_{new_stage.value}_{int(elapsed // 15)}"
                        else:
                            # 降级：显示时间和阶段 + 安抚
                            user_complaint = shared and shared.get_user_emotion() == "complaint"
                            suffix = self._get_emotional_broadcast_suffix(elapsed, user_complaint=user_complaint)
                            broadcast_msg = f"仍在{stage_zh}阶段（{elapsed:.0f}s）{suffix}"
                            msg_template = f"heartbeat_{new_stage.value}_{int(elapsed // 15)}"
                    else:
                        # 从共享上下文获取中间结果
                        partials = shared.thinker_progress.partial_results if shared else []
                        broadcast_msg, msg_template = self._generate_stage_broadcast(
                            stage=new_stage,
                            user_query=user_input,
                            elapsed_time=elapsed,
                            current_step=current_step,
                            total_steps=total_steps,
                            step_desc=step_desc,
                            partial_results=partials,
                        )

                    # 基于模板去重（不是完整消息）
                    if msg_template != self._progress_state.last_broadcast_msg_template:
                        ts = format_timestamp(current_time)
                        yield f"\n[{ts}] Talker: {broadcast_msg}"
                        if shared:
                            shared.add_talker_interaction(broadcast_msg, "broadcast")
                        self._progress_state.last_broadcast = current_time
                        self._progress_state.last_broadcast_msg_template = msg_template
                        self._progress_state.broadcast_count += 1

                    # 更新状态
                    if new_stage != self._progress_state.current_stage:
                        self._progress_state.current_stage = new_stage
                        self._progress_state.last_stage_change = current_time
                        # 阶段变化时重置模板集合
                        self._progress_state.used_message_templates = {}
                    self._progress_state.current_step = current_step
                    self._progress_state.total_steps = total_steps
                    self._progress_state.last_content_hash = content_hash

                last_broadcast_time = current_time

            # === 处理Thinker输出 ===
            if output_index < len(thinker_output):
                chunk = thinker_output[output_index]
                output_index += 1
                accumulated_output += chunk
                last_output_time = current_time  # 更新最后输出时间

                # 解析阶段（用于状态更新）
                if shared and shared.thinker_progress.current_stage != "idle":
                    new_stage = self._stage_from_shared_progress(shared.thinker_progress.current_stage)
                    current_step = shared.thinker_progress.current_step
                    total_steps = shared.thinker_progress.total_steps
                    step_desc = self._latest_shared_step_desc(shared)
                else:
                    new_stage, current_step, total_steps, step_desc = self._parse_thinker_stage(accumulated_output)

                # 更新状态
                if new_stage != self._progress_state.current_stage:
                    self._progress_state.current_stage = new_stage
                    self._progress_state.last_stage_change = current_time
                self._progress_state.current_step = current_step
                self._progress_state.total_steps = total_steps
                self._progress_state.last_content_hash = f"{new_stage.value}:{current_step}:{total_steps}:{step_desc[:20]}"

                # === Thinker 输出劫持：Talker 重新组织语言 ===
                # 检测 Thinker 的阶段标记输出，由 Talker 重新组织后显示
                if chunk.strip():
                    talker_rewrite = self._try_rewrite_thinker_output(
                        chunk, new_stage, current_step, total_steps, step_desc, elapsed
                    )
                    if talker_rewrite:
                        # 避免重复播报：如果 precheck 超时已播报"先进入详细处理"，
                        # 且 Thinker 输出是"开始处理"，则跳过劫持（静默处理）
                        if precheck_timeout_broadcast and "Thinker 已启动" in talker_rewrite:
                            # 静默处理，不重复播报，但重置 heartbeat 计时器
                            last_broadcast_time = current_time
                            continue

                        # 语义去重检查：如果与最近播报重复，则跳过
                        if self._is_semantic_duplicate(talker_rewrite):
                            # 跳过播报，但重置计时器
                            last_broadcast_time = current_time
                            continue

                        # Talker 劫持输出，重新组织语言
                        # 重置 heartbeat 计时器，避免重复播报
                        last_broadcast_time = current_time

                        # 每个阶段标记都作为独立的消息显示，带有自己的时间戳和 Talker 前缀
                        ts = format_timestamp(current_time)
                        yield f"\n[{ts}] Talker: {talker_rewrite}"
                    else:
                        # 非阶段标记输出，使用 Talker 风格播报
                        # 根据内容判断是否需要特殊处理
                        if chunk.strip() and not chunk.startswith('[答案]'):
                            # 普通内容，使用通用的 Talker 播报
                            ts = format_timestamp(current_time)
                            yield f"\n[{ts}] Talker: "
                            # 短内容直接显示，长内容截断
                            if len(chunk.strip()) > 50:
                                yield f"{chunk.strip()[:50]}..."
                            else:
                                yield chunk.strip()
                        else:
                            # 答案内容或空内容，直接显示
                            if chunk.strip():
                                ts = format_timestamp(current_time)
                                yield f"\n[{ts}] Talker: "
                            yield chunk
            else:
                # 没有新输出时短暂等待
                await asyncio.sleep(0.05)

        # 确保所有输出都已处理
        while output_index < len(thinker_output):
            chunk = thinker_output[output_index]
            output_index += 1
            if chunk.strip():
                ts = format_timestamp(time.time())
                yield f"\n[{ts}] Talker: {chunk}"

        # 记录Handoff回Talker
        self._record_handoff(
            HandoffType.COLLABORATION,
            "thinker",
            "talker",
            "Thinker处理完成",
        )

        # 显示详细指标
        if settings.SHOW_AGENT_IDENTITY:
            metrics = context.get("_llm_metrics", {}) if context else {}
            yield "\n" + self._format_metrics(metrics, thinker_start, thinker_start)

    async def _parallel_handoff(
        self,
        user_input: str,
        context: Dict[str, Any],
    ) -> AsyncIterator[str]:
        """
        并行模式Handoff

        Talker和Thinker同时工作
        """
        # 并行启动
        talker_task = asyncio.create_task(
            self._collect_stream(self.talker.process(user_input, context))
        )
        thinker_task = asyncio.create_task(
            self._collect_stream(self.thinker.process(user_input, context))
        )

        # 先返回Talker的快速响应
        talker_result = await talker_task
        yield "".join(talker_result)

        # 等待Thinker完成
        thinker_result = await thinker_task

        # 如果Thinker的答案更好，补充说明
        if thinker_result:
            yield "\n\n【补充说明】\n"
            yield "".join(thinker_result)

    async def _iterative_handoff(
        self,
        user_input: str,
        context: Dict[str, Any],
    ) -> AsyncIterator[str]:
        """
        迭代模式Handoff

        Talker提供初步答案，Thinker根据用户反馈改进
        """
        # Talker先提供初步答案
        yield "【初步答案】\n"
        async for chunk in self.talker.process(user_input, context):
            yield chunk

        yield "\n\n如果您需要更详细的解释，请告诉我。"

    async def _collect_stream(self, stream: AsyncIterator[str]) -> List[str]:
        """收集流式输出"""
        result = []
        async for chunk in stream:
            result.append(chunk)
        return result

    async def _get_or_create_session(self, session_id: str) -> Dict[str, Any]:
        """获取或创建会话（使用SessionContext持久化）"""
        if not await self.session_context.exists(session_id):
            await self.session_context.set_session_data(session_id, "created_at", time.time())
            await self.session_context.set_session_data(session_id, "state", "active")

        # 返回兼容格式
        messages = await self.session_context.get_messages(session_id, limit=100)
        return {
            "messages": [m.to_dict() for m in messages],
            "created_at": await self.session_context.get_session_data(session_id, "created_at", time.time()),
            "state": await self.session_context.get_session_data(session_id, "state", "active"),
        }

    def _get_or_create_shared_context(self, session_id: str, user_input: str = "") -> SharedContext:
        """获取或创建共享上下文"""
        if session_id not in self._shared_contexts:
            self._shared_contexts[session_id] = SharedContext(user_input=user_input)
        elif user_input:
            self._shared_contexts[session_id].user_input = user_input
        return self._shared_contexts[session_id]

    def get_shared_context(self, session_id: str) -> Optional[SharedContext]:
        """获取会话共享上下文（只读访问）。"""
        return self._shared_contexts.get(session_id)

    def _record_handoff(
        self,
        handoff_type: HandoffType,
        from_agent: str,
        to_agent: str,
        reason: str,
    ) -> None:
        """记录Handoff"""
        self._stats["handoffs"] += 1
        handoff = HandoffContext(
            handoff_type=handoff_type,
            from_agent=from_agent,
            to_agent=to_agent,
            reason=reason,
        )
        self._handoff_history.append(handoff)

        # 触发回调
        if self._on_handoff:
            asyncio.create_task(self._on_handoff(handoff))

    async def _handle_progress(self, progress_info: Dict[str, Any]) -> None:
        """处理进度更新"""
        if self._on_progress:
            await self._on_progress(progress_info)

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话信息"""
        if await self.session_context.exists(session_id):
            return await self._get_or_create_session(session_id)
        return None

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "active_sessions": len(self._shared_contexts),
            "recent_handoffs": len(self._handoff_history[-10:]),
            "talker_stats": self.talker.get_stats(),
            "thinker_stats": self.thinker.get_stats(),
        }

    def get_handoff_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取Handoff历史"""
        return [
            {
                "type": h.handoff_type.value,
                "from": h.from_agent,
                "to": h.to_agent,
                "reason": h.reason,
                "timestamp": h.timestamp,
            }
            for h in self._handoff_history[-limit:]
        ]

    async def clear_session(self, session_id: str) -> None:
        """清除会话"""
        await self.session_context.delete_session(session_id)
        if session_id in self._shared_contexts:
            del self._shared_contexts[session_id]

    def reset_stats(self) -> None:
        """重置统计"""
        self._stats = {
            "total_requests": 0,
            "talker_handled": 0,
            "thinker_handled": 0,
            "handoffs": 0,
            "errors": 0,
        }
        self.talker.reset_stats()
        self.thinker.reset_stats()
