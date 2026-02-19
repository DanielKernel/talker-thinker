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
    last_broadcast_msg: str = ""
    broadcast_count: int = 0
    current_step: int = 0
    total_steps: int = 0
    step_description: str = ""
    broadcast_history: set = field(default_factory=set)  # 用于去重
    last_content_hash: str = ""  # 用于内容去重
    used_messages: Dict[str, set] = field(default_factory=dict)  # 按阶段记录已使用的消息


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

    def _generate_stage_broadcast(
        self,
        stage: ThinkerStage,
        user_query: str,
        elapsed_time: float,
        current_step: int = 0,
        total_steps: int = 0,
        step_desc: str = "",
    ) -> str:
        """
        根据阶段生成播报消息（基于上下文的动态消息）
        关键改进：根据时间进度生成不同风格的播报，避免重复
        使用已使用消息追踪来避免重复
        """
        # 提取主题
        topic = self._extract_topic(user_query)
        stage_key = stage.value

        # 获取该阶段已使用的消息集合
        if stage_key not in self._progress_state.used_messages:
            self._progress_state.used_messages[stage_key] = set()

        used = self._progress_state.used_messages[stage_key]

        # 根据已耗时选择播报风格
        if elapsed_time < 8:
            style = "initial"
        elif elapsed_time < 15:
            style = "progress"
        elif elapsed_time < 25:
            style = "reassure"
        else:
            style = "urgent"

        def get_unused_message(msgs: list, used_set: set) -> str:
            """从未使用的消息中选择一个，如果都用过则重置"""
            for msg in msgs:
                if msg not in used_set:
                    used_set.add(msg)
                    return msg
            # 所有消息都用过了，清空并重新开始
            used_set.clear()
            used_set.add(msgs[0])
            return msgs[0]

        if stage == ThinkerStage.ANALYZING:
            if style == "initial":
                msgs = [
                    f"正在理解您关于「{topic}」的需求...",
                    "正在分析问题关键点...",
                    f"梳理「{topic}」相关信息...",
                ]
            elif style == "progress":
                msgs = [
                    "深度分析中，请稍候...",
                    "正在提取关键要素...",
                ]
            else:
                # 每次生成带时间的唯一消息，自然不会重复
                msgs = [
                    f"分析进行中 ({elapsed_time:.0f}s)...",
                ]
            return get_unused_message(msgs, used)

        elif stage == ThinkerStage.PLANNING:
            if style == "initial":
                msgs = [
                    f"已理解需求，正在制定{topic}方案...",
                    "规划最优解决路径...",
                ]
            elif style == "progress":
                msgs = [
                    "方案设计中...",
                    "正在分解任务步骤...",
                ]
            else:
                msgs = [
                    f"规划中 ({elapsed_time:.0f}s)...",
                ]
            return get_unused_message(msgs, used)

        elif stage == ThinkerStage.EXECUTING:
            if total_steps > 0 and current_step > 0:
                progress_pct = int((current_step / total_steps) * 100)
                if step_desc:
                    short_desc = step_desc[:15] + "..." if len(step_desc) > 15 else step_desc
                    return f"第{current_step}/{total_steps}步: {short_desc} ({progress_pct}%)"
                return f"执行中: {current_step}/{total_steps} 步 ({progress_pct}%)"
            # 没有步骤信息时使用通用消息
            msgs = [
                "正在处理核心任务...",
                "执行关键步骤...",
            ]
            return get_unused_message(msgs, used)

        elif stage == ThinkerStage.SYNTHESIZING:
            msgs = [
                "正在整合分析结果...",
                "生成最终答案中...",
                "即将完成，请稍候...",
                "整理输出内容...",
            ]
            return get_unused_message(msgs, used)

        elif stage == ThinkerStage.COMPLETED:
            return "处理完成！"

        # 默认消息
        return f"处理中 ({elapsed_time:.0f}s)..."

    def _extract_topic(self, query: str) -> str:
        """从用户问题中提取主题"""
        query_lower = query.lower()

        topic_keywords = {
            "选车": ["车", "汽车", "车型", "品牌", "suv", "轿车", "买车", "选车"],
            "旅游": ["旅游", "旅行", "景点", "酒店", "机票", "去哪"],
            "美食": ["美食", "餐厅", "菜", "吃", "推荐菜"],
            "购物": ["买", "购物", "价格", "便宜", "对比"],
            "咖啡": ["咖啡", "拿铁", "星巴克", "瑞幸"],
            "打车": ["打车", "滴滴", "高德", "专车", "快车"],
        }

        for topic, keywords in topic_keywords.items():
            if any(kw in query_lower for kw in keywords):
                return topic

        # 提取问题中的关键词作为主题
        words = re.findall(r'[\u4e00-\u9fa5]{2,4}', query)
        if words:
            return words[0]
        return "您的问题"

    def _should_broadcast(
        self,
        new_stage: ThinkerStage,
        current_step: int,
        elapsed_time: float,
        force_check: bool = False,
    ) -> tuple[bool, str]:
        """
        判断是否需要播报

        Args:
            new_stage: 当前阶段
            current_step: 当前步骤
            elapsed_time: 已耗时
            force_check: 是否强制检查（忽略最小间隔）

        Returns:
            tuple: (是否播报, 原因)
        """
        state = self._progress_state
        current_time = time.time()

        # 动态计算播报间隔：初始适中，后期延长
        def get_min_interval(elapsed: float, stage: ThinkerStage) -> float:
            """根据耗时和阶段动态计算最小间隔"""
            # 更保守的间隔策略
            if elapsed < 10:
                base_interval = 4.0  # 初始4秒
            elif elapsed < 20:
                base_interval = 5.0  # 中期5秒
            elif elapsed < 40:
                base_interval = 6.0  # 后期6秒
            else:
                base_interval = 8.0  # 长时间任务8秒

            # 规划阶段可能需要更长时间，稍微延长间隔
            if stage == ThinkerStage.PLANNING:
                base_interval = min(base_interval + 1.0, 10.0)
            return base_interval

        min_interval = get_min_interval(elapsed_time, new_stage)

        # 阶段变化，立即播报
        if new_stage != state.current_stage:
            return True, "stage_changed"

        # 步骤变化（执行阶段）
        if new_stage == ThinkerStage.EXECUTING and current_step != state.current_step and current_step > 0:
            return True, "step_changed"

        # 同阶段内，检查时间间隔
        time_since_last = current_time - state.last_broadcast
        if time_since_last >= min_interval:
            # 限制每阶段的播报次数
            stage_key = new_stage.value
            stage_broadcast_count = len(state.used_messages.get(stage_key, set()))
            max_broadcasts_per_stage = 5  # 每阶段最多5条不同消息

            if stage_broadcast_count < max_broadcasts_per_stage:
                return True, "interval_elapsed"

        return False, "skip"

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
        shared = self._get_or_create_shared_context(session_id, user_input)
        shared.is_processing = True

        # === 检查是否是回答澄清问题 ===
        if shared.needs_clarification():
            # 用户可能是在回答澄清问题
            pending = shared.get_pending_clarification()
            if pending:
                # 记录回答
                shared.answer_clarification(user_input)
                # 更新意图
                shared.update_intent_with_clarification(user_input)

                # 给用户确认反馈
                ts = time.strftime("%H:%M:%S", time.localtime())
                ms = int((time.time() % 1) * 1000)
                yield f"\n[{ts}.{ms:03d}] Talker: 收到，已更新您的需求信息"

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
        }

        # 收集助手响应用于保存到会话
        assistant_response_chunks = []

        try:
            # 使用Talker进行意图分类
            classification = await self.talker.classify_intent(user_input, full_context)

            # 根据复杂度选择处理策略
            if classification.complexity == TaskComplexity.COMPLEX:
                # 复杂任务：使用协作模式
                self._stats["thinker_handled"] += 1
                async for chunk in self._collaboration_handoff(
                    user_input, full_context, received_time=received_time
                ):
                    assistant_response_chunks.append(chunk)
                    yield chunk
            else:
                # 简单/中等任务：Talker处理
                self._stats["talker_handled"] += 1
                async for chunk in self._delegation_handoff(
                    user_input, full_context, classification, received_time=received_time
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
            async for chunk in self.talker.process(user_input, context):
                await talker_queue.put(chunk)
            talker_complete = True

        # 启动Talker任务
        talker_task = asyncio.create_task(run_talker())

        # 处理Talker输出
        first_token_time = None
        first_timestamp_shown = False
        last_broadcast_time = llm_request_time
        broadcast_count = 0
        used_broadcast_msgs = set()  # 追踪已使用的消息

        def get_talker_broadcast_interval(elapsed: float) -> float:
            """动态计算播报间隔"""
            if elapsed < 10:
                return 4.0  # 初始4秒
            elif elapsed < 20:
                return 5.0  # 中期5秒
            else:
                return 6.0  # 后期6秒

        while not talker_complete or not talker_queue.empty():
            current_time = time.time()
            elapsed = current_time - llm_request_time

            # === 关键改进：每次循环都检查是否需要播报 ===
            broadcast_interval = get_talker_broadcast_interval(elapsed)
            if current_time - last_broadcast_time >= broadcast_interval:
                ts = format_timestamp(current_time)

                # 根据时间动态选择播报内容，避免重复
                if elapsed < 10:
                    all_msgs = ["正在处理...", "思考中..."]
                elif elapsed < 20:
                    all_msgs = ["仍在处理中...", "请稍候..."]
                else:
                    # 长时间任务，带时间提示
                    all_msgs = [f"响应较慢 ({elapsed:.0f}s)..."]

                # 选择一个未使用的消息
                msg = None
                for m in all_msgs:
                    if m not in used_broadcast_msgs:
                        msg = m
                        used_broadcast_msgs.add(m)
                        break

                if msg is None:
                    # 所有消息都用过了，清空重来（但这不应该频繁发生）
                    used_broadcast_msgs.clear()
                    msg = all_msgs[0]

                yield f"\n[{ts}] Talker: {msg}"
                last_broadcast_time = current_time
                broadcast_count += 1

                # 限制最大播报次数
                if broadcast_count >= 8:
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
            yield f"\n[{timestamp}] Talker: 好的，这个问题需要深度思考，已转交给Thinker处理"

        # === 澄清机制：检测是否需要澄清 ===
        try:
            # 快速规划以检测是否需要澄清
            quick_plan = await self.thinker.plan_task(user_input, context)
            needs_clarification, reason, missing_info = await self.thinker.needs_clarification(
                user_input, quick_plan, context
            )

            if needs_clarification and missing_info and shared:
                # 生成澄清问题
                question = await self.thinker.generate_clarification_question(
                    user_input, missing_info, context
                )

                # 通过Talker向用户提问
                ts = format_timestamp(time.time())
                yield f"\n[{ts}] Talker: {question}"

                # 记录澄清请求
                shared.add_clarification_request(question, reason or "", [])

                # 等待用户回答（通过队列机制）
                # 注意：这里使用简化的方式，实际回答会在下一次process中处理
                # 将澄清状态保存到共享上下文供下次使用
                shared.clarification_status = ClarificationStatus.PENDING

        except Exception:
            # 澄清检测失败，继续正常处理
            pass

        # 记录Handoff到Thinker
        self._record_handoff(
            HandoffType.COLLABORATION,
            "talker",
            "thinker",
            "启动协作模式",
        )

        # Thinker开始工作的提示
        ts = format_timestamp(time.time())
        yield f"\n[{ts}] Thinker: 开始处理..."

        # 收集Thinker的输出
        thinker_output = []
        thinker_complete = False
        accumulated_output = ""
        thinker_first_token_shown = False

        # 播报控制 - 使用独立的时间检查（动态间隔）
        last_broadcast_time = thinker_start

        def get_broadcast_interval(elapsed: float) -> float:
            """根据已耗时动态计算播报间隔"""
            # 初始阶段更频繁（2-3秒），后期稳定在3-4秒
            if elapsed < 10:
                return 2.5  # 初始2.5秒
            elif elapsed < 20:
                return 3.0  # 中期3秒
            else:
                return 4.0  # 后期4秒（上限）
        output_index = 0

        async def run_thinker():
            """运行Thinker并收集输出"""
            nonlocal thinker_complete
            async for chunk in self.thinker.process(user_input, context):
                thinker_output.append(chunk)
            thinker_complete = True

        # 启动Thinker任务
        thinker_task = asyncio.create_task(run_thinker())

        # 主循环：处理Thinker输出和播报
        while not thinker_complete or output_index < len(thinker_output):
            current_time = time.time()
            elapsed = current_time - thinker_start

            # === 关键改进：每次循环都检查是否需要播报 ===
            # 使用动态间隔：初始频繁，后期稳定
            broadcast_interval = get_broadcast_interval(elapsed)
            if current_time - last_broadcast_time >= broadcast_interval:
                # 解析当前阶段（基于已有输出）
                new_stage, current_step, total_steps, step_desc = self._parse_thinker_stage(accumulated_output)

                # 检查是否需要播报
                should_broadcast, reason = self._should_broadcast(new_stage, current_step, elapsed)

                if should_broadcast:
                    # 使用内容哈希去重
                    content_hash = self._hash_broadcast_content(new_stage, current_step, elapsed)
                    if content_hash not in self._progress_state.broadcast_history:
                        broadcast_msg = self._generate_stage_broadcast(
                            stage=new_stage,
                            user_query=user_input,
                            elapsed_time=elapsed,
                            current_step=current_step,
                            total_steps=total_steps,
                            step_desc=step_desc,
                        )

                        # 额外检查：确保消息不重复
                        if broadcast_msg != self._progress_state.last_broadcast_msg:
                            ts = format_timestamp(current_time)
                            yield f"\n[{ts}] Talker: {broadcast_msg}"
                            self._progress_state.last_broadcast = current_time
                            self._progress_state.last_broadcast_msg = broadcast_msg
                            self._progress_state.broadcast_count += 1
                            self._progress_state.broadcast_history.add(content_hash)

                        # 更新状态
                        if new_stage != self._progress_state.current_stage:
                            self._progress_state.current_stage = new_stage
                            self._progress_state.last_stage_change = current_time
                        self._progress_state.current_step = current_step
                        self._progress_state.total_steps = total_steps

                last_broadcast_time = current_time

            # === 处理Thinker输出 ===
            if output_index < len(thinker_output):
                chunk = thinker_output[output_index]
                output_index += 1
                accumulated_output += chunk

                # 解析阶段（用于状态更新）
                new_stage, current_step, total_steps, step_desc = self._parse_thinker_stage(accumulated_output)

                # 更新状态
                if new_stage != self._progress_state.current_stage:
                    self._progress_state.current_stage = new_stage
                    self._progress_state.last_stage_change = current_time
                self._progress_state.current_step = current_step
                self._progress_state.total_steps = total_steps

                # Thinker输出加时间戳
                if chunk.strip():
                    if not thinker_first_token_shown:
                        ts = format_timestamp(current_time)
                        yield f"\n[{ts}] Thinker: "
                        thinker_first_token_shown = True
                    yield chunk
            else:
                # 没有新输出时短暂等待
                await asyncio.sleep(0.05)

        # 确保所有输出都已处理
        while output_index < len(thinker_output):
            chunk = thinker_output[output_index]
            output_index += 1
            if chunk.strip():
                if not thinker_first_token_shown:
                    ts = format_timestamp(time.time())
                    yield f"\n[{ts}] Thinker: "
                    thinker_first_token_shown = True
            yield chunk

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
