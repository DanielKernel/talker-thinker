"""
Talker-Thinker 双 Agent 系统主入口
"""
import argparse
import asyncio
import json
import re
import sys
import time
from enum import Enum
from typing import Optional

from typing import Any, Dict, Optional

from config import settings
from config.keywords_manager import get_keywords_manager
from orchestrator.coordinator import Orchestrator
from context.shared_context import TaskQueue, TaskInfo
from monitoring.logging import get_logger
from monitoring.metrics import get_metrics_collector

logger = get_logger("main")

# Initialize keywords manager
_keywords_manager = get_keywords_manager()



# === 用户情绪检测工具函数 ===
def detect_user_emotion(text: str) -> str:
    """
    检测用户情绪状态

    Args:
        text: 用户输入文本

    Returns:
        情绪标签：'complaint'（抱怨）、'neutral'（中性）、'positive'（正面）、'negative'（负面）
    """
    return _keywords_manager.detect_emotion(text)


class UserIntent(Enum):
    """用户意图类型"""
    CONTINUE = "continue"      # 继续当前任务（补充信息）
    REPLACE = "replace"        # 取消当前任务，开始新任务
    MODIFY = "modify"          # 修改当前任务
    QUERY_STATUS = "status"    # 查询状态
    PAUSE = "pause"            # 暂停当前任务
    RESUME = "resume"          # 恢复当前任务
    COMMENT = "comment"        # 评论/感叹（不打断任务）
    BACKCHANNEL = "backchannel"  # 附和/应答（不打断任务）


class InterruptAction(Enum):
    """任务中断后的执行动作"""
    CONTINUE = "continue"
    MODIFY_CURRENT = "modify_current"
    CANCEL_ONLY = "cancel_only"
    REPLACE_WITH_NEW_TASK = "replace_with_new_task"


class TaskManager:
    """任务管理器 - 管理任务状态和中断"""

    def __init__(self):
        self._current_task: Optional[asyncio.Task] = None
        self._current_input: Optional[str] = None
        self._is_processing = False
        self._cancelled = False
        self._paused = False
        self._pause_event: Optional[asyncio.Event] = None
        self._task_context: Optional[dict] = None  # 保存暂停时的上下文
        self._task_start_time: float = 0  # 任务开始时间
        self._current_topic: Optional[str] = None
        self._pending_replacement_input: Optional[str] = None
        # 多任务队列支持
        self.task_queue = TaskQueue()
        # 使用 KeywordsManager 获取话题库，不再 hardcode

    @property
    def is_processing(self) -> bool:
        return self._is_processing

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def current_input(self) -> Optional[str]:
        return self._current_input

    @property
    def task_start_time(self) -> float:
        return self._task_start_time

    @property
    def pending_replacement_input(self) -> Optional[str]:
        return self._pending_replacement_input

    def start_task(self, task: asyncio.Task, user_input: str):
        """开始新任务"""
        self._current_task = task
        self._current_input = user_input
        self._is_processing = True
        self._cancelled = False
        self._paused = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # 初始状态：不暂停
        self._task_start_time = time.time()  # 记录开始时间
        self._current_topic = self._extract_topic(user_input)

    def end_task(self):
        """结束当前任务并启动队列中的下一个任务"""
        # 将当前任务标记为完成
        if self._current_topic and hasattr(self, '_completed_tasks'):
            pass  # 可以在这里添加完成记录

        self._current_task = None
        self._current_input = None
        self._is_processing = False
        self._paused = False
        self._task_context = None
        self._current_topic = None
        self._pending_replacement_input = None

    def set_pending_replacement_input(self, text: Optional[str]) -> None:
        """设置用户替换任务的新输入。"""
        self._pending_replacement_input = text

    def augment_current_input(self, extra: str) -> None:
        """将用户补充信息并入当前任务描述。"""
        extra = (extra or "").strip()
        if not extra:
            return
        if self._current_input:
            self._current_input = f"{self._current_input}；补充：{extra}"
        else:
            self._current_input = extra

    async def pause_current_task(self) -> bool:
        """暂停当前任务"""
        if self._current_task and not self._current_task.done() and not self._paused:
            self._paused = True
            if self._pause_event:
                self._pause_event.clear()  # 设置暂停标志
            return True
        return False

    async def resume_current_task(self) -> bool:
        """恢复当前任务"""
        if self._paused:
            self._paused = False
            if self._pause_event:
                self._pause_event.set()  # 清除暂停标志
            return True
        return False

    async def wait_if_paused(self):
        """如果任务被暂停，等待恢复"""
        if self._paused and self._pause_event:
            await self._pause_event.wait()

    async def cancel_current_task(self) -> bool:
        """取消当前任务"""
        if self._current_task and not self._current_task.done():
            self._cancelled = True
            # 如果暂停了，先恢复才能取消
            if self._paused:
                await self.resume_current_task()
            self._current_task.cancel()
            try:
                await self._current_task
            except asyncio.CancelledError:
                pass
            # 不立即调用 end_task()，保留 current_input 用于状态查询
            # 只设置_is_processing 为 False，但保留其他状态
            self._is_processing = False
            # 等待一小段时间让共享上下文同步
            await asyncio.sleep(0.5)
            # 然后清理剩余状态，但保留 current_input
            self._current_task = None
            self._task_context = None
            return True
        return False


    def get_running_tasks_count(self) -> int:
        """获取正在运行的任务数量"""
        count = 1 if self._current_task else 0
        return count

    def get_task_queue_status(self) -> str:
        """获取任务队列状态"""
        return self.task_queue.get_status_summary()

    def get_pending_tasks_count(self) -> int:
        """获取待处理任务数量"""
        return len(self.task_queue.pending)
    def classify_intent(self, new_input: str) -> UserIntent:
        """
        分类用户意图：基于语义理解，不是所有输入都应该打断任务

        关键改进：
        1. 优先检测取消意图（最高优先级）
        2. 默认不打断（COMMENT），只有明确的取消意图才打断
        3. 识别评论/感叹类输入，这类不应该打断任务
        4. 识别附和/应答类输入，保持任务继续
        5. 识别用户等待中的疑问，给与回应

        基于关键词的快速分类（同步方法，用于快速判断）
        """
        if not self._current_input or not self._is_processing:
            return UserIntent.REPLACE

        text = new_input.lower().strip()

        if not text:
            return UserIntent.BACKCHANNEL

        # === 0. 最高优先级：明确的取消/替换关键词 ===
        # 必须在最前面，否则会被其他规则捕获
        if _keywords_manager.has_intent_keyword(text, "cancel"):
            return UserIntent.REPLACE

        # === 0.05 明确补充信息（优先于新任务）===
        # 避免"帮我补充..."被误判为新任务替换
        modify_keywords = _keywords_manager.get_intent_keywords("modify")
        # 但"还有任务吗"、"还有多少任务"是查询状态，不是补充信息
        status_exceptions = ["还有任务", "还有多少", "还有几个"]
        if any(se in text for se in status_exceptions):
            pass  # 不返回 MODIFY，让后面的 QUERY_STATUS 处理
        elif any(kw in text for kw in modify_keywords):
            return UserIntent.MODIFY

        # === 0.06 上下文补充短句（优先于新任务）===
        contextual_markers = _keywords_manager.get_intent_keywords("contextual")
        explicit_new_task_markers = _keywords_manager.get_intent_keywords("new_task")
        if len(text) <= 14 and any(m in text for m in contextual_markers):
            if not any(m in text for m in explicit_new_task_markers):
                return UserIntent.MODIFY

        # === 0.1 显式新任务（高优先级）===
        # 已合并到 new_task 意图检测中

        # === 0.2 话题切换检测 ===
        if self._is_topic_switch(new_input):
            return UserIntent.REPLACE

        # === 1. 检测用户在等待中的疑问/抱怨 ===
        if _keywords_manager.has_intent_keyword(text, "query_status"):
            return UserIntent.QUERY_STATUS

        # === 2. 检测附和/应答（不打断任务）===
        if _keywords_manager.has_intent_keyword(text, "backchannel"):
            return UserIntent.BACKCHANNEL

        # === 2.1 短文本新任务检测（避免"吃饭"被误判）===
        if len(text) <= 4 and self._is_likely_new_task(text):
            return UserIntent.REPLACE

        # === 3. 检测评论/感叹（不打断任务） ===
        if _keywords_manager.has_intent_keyword(text, "comment"):
            question_patterns = ["吗", "？", "?", "呢", "什么", "怎么", "如何", "为什么"]
            if not any(q in text for q in question_patterns):
                return UserIntent.COMMENT

        # === 4. 查询状态 ===
        # 已合并到 query_status 检测中

        # === 5. 暂停/恢复关键词 ===
        if _keywords_manager.has_intent_keyword(text, "pause"):
            return UserIntent.PAUSE

        if _keywords_manager.has_intent_keyword(text, "resume"):
            return UserIntent.RESUME

        # === 6. 检查是否是全新的任务请求（需要打断）===
        # 已合并到 new_task 检测中

        # === 7. 补充/修改信息的关键词 ===
        # 已合并到 modify 检测中

        # === 8. 回答澄清问题 ===
        # 注意：先检测评论/感叹，避免"挺好的"被误判为澄清回答
        clarify_keywords = _keywords_manager.get_intent_keywords("clarify")
        # 澄清回答通常是单个确认词，且不包含评论词
        comment_words = ["好", "不错", "行", "可以", "挺", "真", "太"]
        is_comment = any(cw in text for cw in comment_words)
        if not is_comment and any(kw in text for kw in clarify_keywords) and len(text) < 20:
            return UserIntent.CONTINUE

        # === 9. 默认：不打断任务 ===
        return UserIntent.COMMENT

    def extract_replacement_input(self, text: str) -> str:
        """从"取消 + 新任务"的复合输入中提取新任务意图。"""
        chunks = [c.strip() for c in re.split(r"[，,。；;！!？?]", text) if c.strip()]
        if not chunks:
            return text
        # 使用 KeywordsManager 获取新任务关键词
        new_task_markers = _keywords_manager.get_intent_keywords("new_task")
        cancel_keywords = _keywords_manager.get_intent_keywords("cancel")
        for chunk in chunks:
            if any(m in chunk for m in new_task_markers):
                if not any(k in chunk for k in cancel_keywords):
                    return chunk
        return text

    def decide_interrupt_action(self, new_input: str) -> tuple[InterruptAction, Optional[str]]:
        """判断新输入应触发的任务中断动作。"""
        intent = self.classify_intent(new_input)
        text = (new_input or "").strip()
        if not text:
            return InterruptAction.CONTINUE, None

        if intent == UserIntent.MODIFY:
            return InterruptAction.MODIFY_CURRENT, None
        if intent != UserIntent.REPLACE:
            return InterruptAction.CONTINUE, None

        replacement = self.extract_replacement_input(text)
        cancel_keywords = _keywords_manager.get_intent_keywords("cancel")
        has_cancel = any(k in text.lower() for k in cancel_keywords)
        has_new_task_phrase = _keywords_manager.has_intent_keyword(text, "new_task")

        if replacement != text or has_new_task_phrase:
            return InterruptAction.REPLACE_WITH_NEW_TASK, replacement
        if has_cancel:
            return InterruptAction.CANCEL_ONLY, None
        return InterruptAction.REPLACE_WITH_NEW_TASK, replacement

    def _is_likely_new_task(self, text: str) -> bool:
        """判断输入是否更像新任务而不是附和/评论。"""
        current_topic = self._current_topic or self._extract_topic(self._current_input or "")
        new_topic = self._extract_topic(text)

        # 使用 KeywordsManager 获取动作词
        all_intent_keywords = []
        for intent_type in ["new_task", "modify", "cancel"]:
            all_intent_keywords.extend(_keywords_manager.get_intent_keywords(intent_type))
        action_keywords = list(set(all_intent_keywords))

        has_action = any(kw in text for kw in action_keywords)

        if current_topic and new_topic and current_topic != new_topic and (has_action or len(text) <= 6):
            return True

        if current_topic and not new_topic and has_action and len(text) <= 4:
            return True

        if not current_topic and has_action:
            return True

        return False

    async def classify_intent_with_llm(
        self,
        new_input: str,
        llm_client,
        timeout: float = 1.0
    ) -> UserIntent:
        """
        使用 LLM 进行更智能的意图分类

        关键改进：
        - 区分评论/感叹（不打断）和取消请求（打断）
        - 考虑当前任务上下文

        Args:
            new_input: 用户输入
            llm_client: LLM 客户端
            timeout: 超时时间（秒）

        Returns:
            UserIntent: 分类结果
        """
        if not self._current_input or not self._is_processing:
            return UserIntent.REPLACE

        prompt = f"""系统正在处理用户的任务：{self._current_input[:100]}

用户在等待过程中说：{new_input}

请判断用户这句话的意图（注意：不要过度解读，用户可能只是随口评论）：

1. COMMENT - 评论/感叹（如"不错"、"挺好的"、"这个好"）
2. BACKCHANNEL - 简单附和（如"嗯"、"好的"、"明白"）
3. MODIFY - 补充当前任务的信息（如"再加上..."、"还有..."）
4. QUERY_STATUS - 查询进度（如"好了吗"、"怎么样"）
5. REPLACE - 取消当前任务开始新任务（如"算了"、"不用了"、"帮我查 xxx"）
6. CONTINUE - 回答系统的澄清问题

重要规则：
- 如果只是评论或感叹，返回 COMMENT，不要误判为 REPLACE
- 如果是简短的应答，返回 BACKCHANNEL
- 只有明确表示取消或提出全新问题才返回 REPLACE

只返回一个意图类型，不要解释。"""

        try:
            import asyncio
            response = await asyncio.wait_for(
                llm_client.generate(prompt, max_tokens=20, temperature=0.3),
                timeout=timeout
            )
            response = response.strip().upper()

            if "REPLACE" in response:
                return UserIntent.REPLACE
            elif "MODIFY" in response:
                return UserIntent.MODIFY
            elif "QUERY_STATUS" in response or "STATUS" in response:
                return UserIntent.QUERY_STATUS
            elif "COMMENT" in response:
                return UserIntent.COMMENT
            elif "BACKCHANNEL" in response:
                return UserIntent.BACKCHANNEL
            elif "CONTINUE" in response:
                return UserIntent.CONTINUE

        except asyncio.TimeoutError:
            pass  # 超时，使用关键词分类
        except Exception:
            pass

        # 降级到关键词分类
        return self.classify_intent(new_input)

    def _extract_topic(self, text: str) -> Optional[str]:
        """提取话题关键词"""
        # 首先使用 KeywordsManager 提取话题
        topic = _keywords_manager.extract_topic(text)
        if topic:
            return topic

        text_lower = text.lower()

        # 过滤掉纯评论/附和的短语
        filters = _keywords_manager.get_filter_phrases
        comment_phrases = filters("comment_phrases")
        backchannel_phrases = filters("backchannel_phrases")
        complaint_phrases = filters("complaint_phrases")
        status_query_phrases = filters("status_query_phrases")

        # 过滤掉预算/数字类澄清回答（如"20 万左右"、"15 万"、"5000 块"）
        if re.search(r'\d+\s*万', text) or re.search(r'\d+\s*(块 | 元)', text):
            return None
        if text_lower in comment_phrases or text_lower in backchannel_phrases or text_lower in complaint_phrases or text_lower in status_query_phrases:
            return None
        # 提取问题中的关键词作为主题
        words = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
        if words:
            return words[0]
        return None

    def _is_topic_switch(self, new_input: str) -> bool:
        """
        检测是否是话题切换

        规则：
        1. 当前有明确话题，新输入指向不同话题 → 话题切换
        2. 当前有话题，新输入是短动作词（如"吃饭"）→ 话题切换
        3. 话题相同 → 不是切换
        4. 附和/评论类短语 → 不是切换
        5. 状态查询类短语 → 不是切换
        """
        if not self._current_topic:
            return False

        text = new_input.lower().strip()

        # 先排除附和/评论类短语
        filters = _keywords_manager.get_filter_phrases
        backchannel_phrases = filters("backchannel_phrases")
        comment_phrases = filters("comment_phrases")
        complaint_phrases = filters("complaint_phrases")
        status_query_phrases = filters("status_query_phrases")
        status_queries = filters("status_queries")

        # 排除预算/数字类澄清回答
        if re.search(r'\d+\s*万', text) or re.search(r'\d+\s*(块 | 元)', text):
            return False
        if text in backchannel_phrases or text in comment_phrases or text in complaint_phrases or text in status_query_phrases or text in status_queries:
            return False

        new_topic = self._extract_topic(new_input)

        # 新输入有明确话题且与当前话题不同 → 话题切换
        if new_topic and new_topic != self._current_topic:
            return True

        # 短文本（<=4 字）+ 动作词 → 可能是新话题
        # 例如：当前任务是选车，用户说"吃饭" → 切换
        if len(text) <= 4:
            action_words = filters("action_words")
            has_action = any(kw in text for kw in action_words)
            # 有新动作且没有当前话题的关键词 → 话题切换
            if has_action and not new_topic:
                current_keywords = _keywords_manager.get_topic_keywords(self._current_topic)
                has_current_topic_kw = any(kw in text for kw in current_keywords)
                if not has_current_topic_kw:
                    return True

        return False


class TalkerThinkerApp:
    """
    Talker-Thinker 应用

    提供命令行和 API 两种使用方式
    支持全双工交互：用户可在处理过程中发送新消息
    """

    def __init__(self):
        self.orchestrator: Optional[Orchestrator] = None
        self.metrics = get_metrics_collector()
        self.task_manager = TaskManager()
        # 确认机制相关属性
        self._pending_new_task: Optional[str] = None  # 待确认的新任务
        self._awaiting_confirmation: bool = False     # 是否等待确认

    async def initialize(self) -> None:
        """初始化应用"""
        logger.info("Initializing Talker-Thinker system...")

        # 创建 Orchestrator
        self.orchestrator = Orchestrator()

        # 设置回调
        self.orchestrator.set_callbacks(
            on_response=self._on_response,
            on_handoff=self._on_handoff,
            on_progress=self._on_progress,
        )

        logger.info(
            "System initialized",
            talker_model=settings.TALKER_MODEL,
            thinker_model=settings.THINKER_MODEL,
        )

    async def _on_response(self, response: str) -> None:
        """响应回调"""
        self.metrics.counter("responses_total")

    async def _on_handoff(self, handoff) -> None:
        """Handoff 回调"""
        logger.log_handoff(
            handoff.from_agent,
            handoff.to_agent,
            handoff.reason,
        )
        self.metrics.record_handoff(
            handoff.from_agent,
            handoff.to_agent,
            handoff.reason,
        )

    async def _on_progress(self, progress: dict) -> None:
        """进度回调"""
        self.metrics.gauge(
            "progress",
            progress.get("progress", 0),
            {"agent": progress.get("agent", "unknown")},
        )

    async def process(self, user_input: str, session_id: Optional[str] = None, received_time: Optional[float] = None) -> str:
        """
        处理用户输入

        Args:
            user_input: 用户输入
            session_id: 会话 ID（可选）
            received_time: 消息接收时间（可选）

        Returns:
            str: 系统响应
        """
        if not self.orchestrator:
            await self.initialize()

        start_time = asyncio.get_event_loop().time()

        # 收集流式响应
        result_chunks = []
        first_token_time = None
        try:
            async for chunk in self.orchestrator.process(user_input, session_id, received_time=received_time):
                # 检查是否被取消
                if self.task_manager._cancelled:
                    break
                if first_token_time is None and chunk.strip():
                    first_token_time = time.time()
                result_chunks.append(chunk)
                # 实时输出（用于 CLI 模式）
                print(chunk, end="", flush=True)
        except asyncio.CancelledError:
            # 任务被取消
            result_chunks.append("\n\n⚠️ 任务已取消")
            print("\n\n⚠️ 任务已取消", end="", flush=True)

        result = "".join(result_chunks)

        # 记录指标
        elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
        self.metrics.record_latency(
            agent="orchestrator",
            operation="process",
            latency_ms=elapsed,
            success=True,
        )

        return result

    async def _process_as_task(self, user_input: str, session_id: str, received_time: float) -> asyncio.Task:
        """创建处理任务"""
        task = asyncio.create_task(
            self.process(user_input, session_id, received_time)
        )
        self.task_manager.start_task(task, user_input)
        return task

    def _get_shared_context(self, session_id: str):
        """获取当前会话共享上下文。"""
        if self.orchestrator and session_id:
            return self.orchestrator.get_shared_context(session_id)
        return None

    async def _persist_preferences_from_input(self, text: str) -> None:
        """从用户输入提取并持久化偏好。"""
        if not self.orchestrator:
            return
        try:
            await self.orchestrator.persist_user_preferences(text)
        except Exception:
            pass

    def _build_status_reply(self, session_id: str, current: str, elapsed: float) -> str:
        """基于 SharedContext 构建状态反馈。"""
        shared = self._get_shared_context(session_id)

        # 优先检查共享上下文中的 Thinker 状态（更可靠）
        if shared and shared.thinker_progress.current_stage != "idle":
            # Thinker 仍在执行，显示进度
            progress = shared.thinker_progress
            stage_map = {
                "idle": "准备中",
                "analyzing": "分析需求中",
                "planning": "规划方案中",
                "executing": "执行步骤中",
                "synthesizing": "整合答案中",
                "completed": "已完成",
            }
            stage_text = stage_map.get(progress.current_stage, "处理中")
            latest = progress.partial_results[-1] if progress.partial_results else ""
            if progress.total_steps > 0 and progress.current_step > 0:
                step_text = f"（第{progress.current_step}/{progress.total_steps}步）"
            else:
                step_text = ""
            detail = f"，当前：{latest}" if latest else ""
            return f"\n[Talker] 正在处理「{current[:26] if current else '任务'}...」{step_text}，{stage_text}，已用时{elapsed:.0f}秒{detail}"

        # 即使 stage 为 idle，但如果有中间结果，说明 Thinker 可能刚完成或正在取消中
        if shared and shared.thinker_progress.partial_results:
            progress = shared.thinker_progress
            latest = progress.partial_results[-1] if progress.partial_results else ""
            if progress.total_steps > 0 and progress.current_step > 0:
                step_text = f"（第{progress.current_step}/{progress.total_steps}步）"
            else:
                step_text = ""
            detail = f"，当前：{latest}" if latest else ""
            # 检查是否在取消窗口期
            if self.task_manager._cancelled:
                return f"\n[Talker] 任务正在取消中{step_text}，请稍候...{detail}"
            # Thinker 可能刚完成但仍保留进度信息
            return f"\n[Talker] 正在处理「{current[:26] if current else '任务'}...」{step_text}，已完成，已用时{elapsed:.0f}秒{detail}"

        # 检查是否在取消窗口期
        if self.task_manager._cancelled:
            return "\n[Talker] 任务正在取消中，请稍候..."

        # 如果 task_manager 显示正在处理，但 shared context 还没更新，也显示处理中
        if self.task_manager.is_processing:
            return f"\n[Talker] 正在处理「{current[:26] if current else '任务'}...」，已用时{elapsed:.0f}秒，请稍候..."

        # 共享上下文也显示空闲，才认为真的没有任务
        return "\n[Talker] 目前没有需要处理的任务。如果您有其他需求，请随时告诉我！"

    async def _handle_new_input_during_processing(
        self,
        new_input: str,
        session_id: str,
    ) -> tuple[bool, Optional[str]]:
        """
        处理任务进行中的新输入

        关键改进：
        - COMMENT 和 BACKCHANNEL 不打断任务，但 Talker 应该回应
        - 只有 REPLACE 才真正取消任务
        - 用户的问题应该得到实时反馈

        Returns:
            tuple: (是否已处理，响应内容)
        """
        interrupt_action, replacement_input = self.task_manager.decide_interrupt_action(new_input)
        intent = self.task_manager.classify_intent(new_input)
        current = self.task_manager.current_input or "您的请求"

        # 检测用户情绪并存储到 SharedContext
        emotion = detect_user_emotion(new_input)
        shared = self._get_shared_context(session_id)
        if shared:
            shared.set_user_emotion(emotion)

        if intent == UserIntent.COMMENT:
            # 评论/感叹，不打断任务，但 Talker 应该简短回应
            text = new_input.lower()
            if "慢" in text or "久" in text:
                return True, "\n[Talker] 抱歉让您久等了，正在加速处理..."
            elif "在" in text and ("吗" in text or "?" in text or "？" in text):
                return True, "\n[Talker] 在的！正在为您处理，请稍候..."
            elif "回应" in text or "反应" in text:
                return True, "\n[Talker] 抱歉！我在的，正在处理中..."
            elif "干啥" in text or "干嘛" in text or "分析啥" in text or "做什么" in text:
                return True, f"\n[Talker] 正在分析「{current[:24]}...」，马上给您结果"
            elif "乱" in text:
                return True, "\n[Talker] 抱歉让您困惑了，如需取消请说'取消'"
            elif any(w in text for w in ["好", "不错", "行", "可以"]):
                return True, "\n[Talker] 好的，继续处理中..."
            elif "?" in text or "？" in text or "吗" in text or "呢" in text:
                # 问题类评论，简短回应
                return True, f"\n[Talker] 好问题！正在处理「{current[:20]}...」，稍后给您详细回答"
            else:
                # 其他评论，简短确认或静默
                return True, None

        elif intent == UserIntent.BACKCHANNEL:
            # 附和/应答，简短回应
            return True, "\n[Talker] 嗯，继续..."

        elif intent == UserIntent.QUERY_STATUS:
            # 查询状态，给详细反馈（包括任务数量）
            shared = self._get_shared_context(session_id)
            elapsed = time.time() - self.task_manager.task_start_time if self.task_manager.task_start_time else 0

            # 检查 task_manager 是否正在处理任务
            if self.task_manager.is_processing:
                # 任务正在处理中，显示进度
                return True, self._build_status_reply(session_id, current or "任务", elapsed)

            # 检查共享上下文中的 Thinker 状态（优先）
            if shared and shared.thinker_progress.current_stage != "idle":
                # Thinker 仍在执行，使用共享上下文的进度信息
                return True, self._build_status_reply(session_id, current or "任务", elapsed)

            # 检查是否在取消窗口期
            if self.task_manager._cancelled:
                return True, "\n[Talker] 任务正在取消中，请稍候..."

            # 检查用户是否询问特定话题的任务（如"你还在处理打车比？"）
            # 即使 task_manager.is_processing 为 False，但 shared context 可能仍有信息
            if shared and shared.thinker_progress.partial_results:
                # 有中间结果，说明 Thinker 可能刚完成或正在取消
                return True, self._build_status_reply(session_id, current or "任务", elapsed)

            # 检查用户是否询问任务数量
            if "几个任务" in new_input or "多少任务" in new_input:
                running_count = self.task_manager.get_running_tasks_count()
                pending_count = self.task_manager.get_pending_tasks_count()
                queue_status = self.task_manager.get_task_queue_status()
                return True, f"\n[Talker] 当前有{running_count}个任务正在执行，{pending_count}个任务在等待。{queue_status}"

            # 真的没有任务
            return True, "\n[Talker] 目前没有需要处理的任务。如果您有其他需求，请随时告诉我！"

        elif intent == UserIntent.REPLACE:
            # 新任务请求：先确认，不直接取消
            elapsed = time.time() - self.task_manager.task_start_time
            progress_info = self._get_current_task_progress(session_id)

            # 保存待处理的新任务
            self._pending_new_task = replacement_input or new_input.strip()

            # 判断是否需要确认（短任务或执行时间<10 秒可直接取消）
            if elapsed < 10 and progress_info.get("percent", 0) < 20:
                # 任务刚开始，直接取消
                await self.task_manager.cancel_current_task()
                self._pending_new_task = None
                self._awaiting_confirmation = False
                return False, None
            else:
                # 需要确认
                self._awaiting_confirmation = True
                return True, self._generate_task_confirmation_request(new_input, progress_info, elapsed)

        # 处理确认回复
        if self._is_confirmation_reply(new_input):
            self._awaiting_confirmation = False
            choice = self._parse_confirmation_choice(new_input)
            if choice == "cancel":
                await self.task_manager.cancel_current_task()
                pending_task = self._pending_new_task
                self._pending_new_task = None
                return True, "\n[Talker] 好的，已取消当前任务，开始处理新任务..."
            elif choice == "queue":
                # 加入队列逻辑
                pending_task = self._pending_new_task
                self._pending_new_task = None
                # 将新任务加入队列
                task_info = TaskInfo(
                    task_id=f"task_{time.time()}",
                    name=pending_task[:30],
                    user_input=pending_task,
                )
                self.task_manager.task_queue.add_pending(task_info)
                return True, f"\n[Talker] 新任务已加入队列（当前等待：{self.task_manager.task_queue.get_status_summary()}），当前任务继续处理..."
            elif choice == "after":
                # 完成后处理逻辑 - 插入队列最前面
                pending_task = self._pending_new_task
                self._pending_new_task = None
                self._awaiting_confirmation = False
                task_info = TaskInfo(
                    task_id=f"task_{time.time()}",
                    name=pending_task[:30],
                    user_input=pending_task,
                )
                # 插入到队列最前面
                self.task_manager.task_queue.pending.insert(0, task_info)
                return True, f"\n[Talker] 好的，新任务将在当前任务完成后立即处理（队列状态：{self.task_manager.task_queue.get_status_summary()}）"

        elif intent == UserIntent.MODIFY:
            # 补充信息，确认收到
            shared = self._get_shared_context(session_id)
            self.task_manager.augment_current_input(new_input)
            await self._persist_preferences_from_input(new_input)
            if shared:
                shared.update_intent_with_clarification(new_input)
                shared.add_constraint(new_input)
                shared.add_talker_interaction(f"补充信息：{new_input}", "response")
            return True, f"\n[Talker] 收到补充信息「{new_input[:20]}」，已并入当前任务继续处理..."

        elif intent == UserIntent.PAUSE:
            # 暂停当前任务
            await self.task_manager.pause_current_task()
            return True, "\n[Talker] 好的，已暂停。说'继续'可以恢复"

        elif intent == UserIntent.RESUME:
            # 恢复当前任务
            if self.task_manager.is_paused:
                await self.task_manager.resume_current_task()
                return True, "\n[Talker] 好的，继续处理..."
            else:
                return True, "\n[Talker] 当前没有暂停的任务哦"

        else:  # CONTINUE
            # 继续当前任务
            return True, f"\n[Talker] 收到，继续处理「{current[:30]}...」"

    async def run_interactive(self) -> None:
        """
        运行交互模式（支持全双工）

        用户可以在任务处理过程中发送新消息来打断当前任务

        使用 prompt_toolkit 提供中文友好的 TUI 体验：
        - 支持中文输入的正常删除（一次退格删除一个汉字）
        - 支持方向键左右移动光标
        - 支持上下键浏览历史命令
        - 支持 Tab 自动补全
        """
        from tui.input import get_input_handler

        await self.initialize()

        # 获取输入处理器（优先使用 prompt_toolkit，失败时降级为原生 input）
        input_handler = get_input_handler(use_prompt_toolkit=True)

        print("=" * 60)
        print("Talker-Thinker 双 Agent 系统 (全双工模式)")
        print("=" * 60)
        print("输入 'quit' 或 'exit' 退出")
        print("输入 'stats' 查看统计信息")
        print("提示：处理过程中可随时输入新消息打断当前任务")
        print("=" * 60)
        print()

        session_id = None
        input_queue = asyncio.Queue()

        # 输出完成事件：用于控制输入提示的显示时机
        # 事件 set 时表示输出完成，可以显示输入提示
        output_complete_event = asyncio.Event()
        output_complete_event.set()  # 初始状态为已设置，允许显示输入提示

        # 将输出事件传递给输入处理器
        if hasattr(input_handler, 'set_output_event'):
            input_handler.set_output_event(output_complete_event)

        async def read_input():
            """异步读取用户输入 - 使用 prompt_toolkit"""
            loop = asyncio.get_event_loop()
            while True:
                try:
                    # 等待输出完成后再显示输入提示
                    # 这确保了输入提示不会在 Talker 输出过程中显示
                    while not output_complete_event.is_set():
                        await asyncio.sleep(0.1)

                    # 使用 prompt_toolkit 获取输入（支持中文编辑）
                    line = await loop.run_in_executor(None, input_handler.get_input, session_id)
                    await input_queue.put(line)
                except EOFError:
                    logger.info("Input EOF, exiting read_input loop")
                    break
                except KeyboardInterrupt:
                    logger.info("Input interrupted by user")
                    break
                except Exception as e:
                    logger.error(f"Error reading input: {e}", exc_info=True)
                    break

        # 启动输入读取任务
        input_task = asyncio.create_task(read_input())

        try:
            while True:
                try:
                    # 等待用户输入
                    # 注意：使用 prompt_toolkit 时，输入提示由 prompt_toolkit 自己显示
                    try:
                        user_input = await asyncio.wait_for(
                            input_queue.get(),
                            timeout=0.5 if self.task_manager.is_processing else None
                        )
                    except asyncio.TimeoutError:
                        # 超时，继续等待（处理中的任务会继续执行）
                        continue

                    user_input = user_input.strip()

                    if not user_input:
                        continue

                    # 记录输入时间
                    input_time = time.time()

                    # 处理特殊命令
                    if user_input.lower() in ("quit", "exit"):
                        print("\n再见!")
                        break

                    if user_input.lower() == "stats":
                        stats = self.orchestrator.get_stats()
                        print("\n系统统计:")
                        print(json.dumps(stats, indent=2, ensure_ascii=False))
                        continue

                    # 如果当前有任务在处理
                    if self.task_manager.is_processing:
                        # 分类用户意图
                        handled, response = await self._handle_new_input_during_processing(
                            user_input, session_id or ""
                        )

                        if handled:
                            # 任务已处理（如查询状态），显示响应
                            if response:
                                print(response)
                            continue
                        # 否则，继续处理新输入

                    # 初始化会话
                    if session_id is None:
                        import uuid
                        session_id = str(uuid.uuid4())

                    # 创建并运行处理任务
                    # 在开始处理前，清除输出完成事件，防止输入提示显示
                    output_complete_event.clear()

                    self.task_manager._cancelled = False
                    process_task = await self._process_as_task(
                        user_input, session_id, input_time
                    )
                    pending_new_input: Optional[str] = None

                    # 等待任务完成，同时监听新输入
                    while not process_task.done():
                        try:
                            new_input = await asyncio.wait_for(
                                input_queue.get(),
                                timeout=0.2
                            )
                            # 有新输入，处理打断逻辑
                            if new_input.strip():
                                # 1. 先处理获取响应，不立即显示用户输入
                                #    prompt_toolkit 已经显示了输入提示，这里只需要处理逻辑
                                handled, response = await self._handle_new_input_during_processing(
                                    new_input, session_id
                                )

                                # 2. 先显示 Talker 响应（如果有）
                                if handled:
                                    if response:
                                        print(response)
                                else:
                                    # 需要处理新任务
                                    pending_new_input = (
                                        self.task_manager.pending_replacement_input
                                        or new_input.strip()
                                    )
                                    self.task_manager.set_pending_replacement_input(None)
                                    input_time = time.time()
                                    break  # 退出等待循环，开始处理新任务

                        except asyncio.TimeoutError:
                            continue

                    # 如果任务完成，清理状态
                    if process_task.done():
                        self.task_manager.end_task()
                        print()  # 换行

                        # 任务完成，设置输出完成事件，允许显示输入提示
                        output_complete_event.set()

                        if pending_new_input:
                            user_input = pending_new_input
                            self.task_manager._cancelled = False
                            process_task = await self._process_as_task(
                                user_input, session_id, input_time
                            )
                            try:
                                await process_task
                            except asyncio.CancelledError:
                                pass
                            self.task_manager.end_task()
                            print()
                    else:
                        # 被打断，处理新任务
                        self.task_manager._cancelled = False
                        user_input = pending_new_input or user_input
                        process_task = await self._process_as_task(
                            user_input, session_id, input_time
                        )
                        # 继续等待新任务完成
                        try:
                            await process_task
                        except asyncio.CancelledError:
                            pass
                        self.task_manager.end_task()

                        # 检查是否有队列中的任务需要处理
                        next_task = self.task_manager.task_queue.start_next()
                        if next_task:
                            print(f"\n[Talker] 开始处理队列任务：{next_task.name}...")
                            # 异步启动新任务（不等待完成）
                            task = asyncio.create_task(self._process_as_task(
                                next_task.user_input, session_id, time.time()
                            ))
                            # Add error handling for the background task
                            task.add_done_callback(lambda t: self._handle_background_task_error(t))
                        print()

                except KeyboardInterrupt:
                    # Ctrl+C 处理
                    if self.task_manager.is_processing:
                        print("\n\n⚠️ 正在取消当前任务...")
                        await self.task_manager.cancel_current_task()
                        print("✓ 任务已取消，可以继续对话\n")
                    else:
                        print("\n\n再见!")
                        break

                except Exception as e:
                    logger.error(f"Error in interactive mode: {e}")
                    print(f"\n错误：{e}")
                    self.task_manager.end_task()

        finally:
            # 清理
            input_task.cancel()
            try:
                await input_task
            except asyncio.CancelledError:
                pass

    def _handle_background_task_error(self, task: asyncio.Task) -> None:
        """
        Handle errors from background tasks

        Args:
            task: The completed task
        """
        try:
            task.result()  # This will raise any exception that occurred
        except asyncio.CancelledError:
            pass  # Task was cancelled, this is expected
        except Exception as e:
            logger.error(f"Background task error: {e}", exc_info=True)

    def get_stats(self) -> dict:
        """获取系统统计"""
        if self.orchestrator:
            return self.orchestrator.get_stats()
        return {}

    def _get_current_task_progress(self, session_id: str) -> Dict[str, Any]:
        """获取当前任务进度信息"""
        shared = self._get_shared_context(session_id)
        if not shared:
            return {"name": "当前任务", "percent": 0, "step": 0, "total": 0}

        progress = shared.thinker_progress
        percent = progress.get_progress_percent()

        # 提取任务名称（从用户输入）
        task_name = self.task_manager.current_input or "当前任务"
        if len(task_name) > 20:
            task_name = task_name[:20] + "..."

        return {
            "name": task_name,
            "percent": percent,
            "step": progress.current_step,
            "total": progress.total_steps,
            "stage": progress.current_stage,
        }

    def _generate_task_confirmation_request(
        self,
        new_input: str,
        progress_info: Dict[str, Any],
        elapsed: float
    ) -> str:
        """生成任务确认请求"""
        task_name = progress_info.get("name", "当前任务")
        percent = progress_info.get("percent", 0)
        step = progress_info.get("step", 0)
        total = progress_info.get("total", 0)

        # 构建进度描述
        if total > 0:
            progress_desc = f"已执行 {step}/{total} 步 ({percent:.0f}%)"
        else:
            progress_desc = f"已执行 {elapsed:.0f}秒 ({percent:.0f}%)"

        # 截断新任务输入
        new_task = new_input[:30] + "..." if len(new_input) > 30 else new_input

        return f"""
[Talker] 检测到您想开始新任务「{new_task}」，当前任务「{task_name}」{progress_desc}。

请选择如何处理：
  1️⃣  取消当前任务，立即开始新任务（回复"1"或"取消"）
  2️⃣  新任务加入队列，当前任务继续（回复"2"或"排队"）
  3️⃣  完成后处理新任务（回复"3"或"稍后"）
"""

    def _is_confirmation_reply(self, text: str) -> bool:
        """检测是否是确认回复"""
        if not getattr(self, '_awaiting_confirmation', False):
            return False
        text = text.lower().strip()
        # 检测确认选项关键词
        return any(k in text for k in ["1", "取消", "2", "排队", "3", "稍后"])

    def _parse_confirmation_choice(self, text: str) -> Optional[str]:
        """解析确认选择"""
        text = text.lower().strip()
        if "1" in text or "取消" in text:
            return "cancel"
        elif "2" in text or "排队" in text:
            return "queue"
        elif "3" in text or "稍后" in text:
            return "after"
        return None


async def main_async():
    """异步主函数"""
    parser = argparse.ArgumentParser(
        description="Talker-Thinker 双 Agent 系统"
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="运行交互模式",
    )
    parser.add_argument(
        "-q", "--query",
        type=str,
        help="单次查询",
    )
    parser.add_argument(
        "-s", "--session",
        type=str,
        help="会话 ID",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="显示系统统计",
    )

    args = parser.parse_args()

    app = TalkerThinkerApp()

    if args.interactive:
        await app.run_interactive()

    elif args.query:
        await app.initialize()
        print("\n助手：", end="")
        await app.process(args.query, args.session)
        print()

    elif args.stats:
        await app.initialize()
        stats = app.get_stats()
        print(json.dumps(stats, indent=2, ensure_ascii=False))

    else:
        # 默认运行交互模式
        await app.run_interactive()


def main():
    """主函数入口"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n程序已退出")


if __name__ == "__main__":
    main()
