"""
Talker-Thinker 双Agent系统主入口
"""
import argparse
import asyncio
import json
import sys
import time
from enum import Enum
from typing import Optional

from config import settings
from orchestrator.coordinator import Orchestrator
from monitoring.logging import get_logger
from monitoring.metrics import get_metrics_collector

logger = get_logger("main")


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
        """结束当前任务"""
        self._current_task = None
        self._current_input = None
        self._is_processing = False
        self._paused = False
        self._task_context = None
        self._current_topic = None

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
            self.end_task()
            return True
        return False

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
        cancel_keywords = [
            "取消", "停止", "停", "算了", "不用了", "不要了",
            "不看了", "不做了", "换个", "重新", "不定", "不买了",
            "不买", "不需要了", "先不用", "先不", "不用买",
            "stop", "cancel", "never mind", "forget it",
        ]
        if any(kw in text for kw in cancel_keywords):
            return UserIntent.REPLACE

        # === 0.05 明确补充信息（优先于新任务）===
        # 避免“帮我补充...”被误判为新任务替换
        modify_keywords = [
            "另外", "还有", "加上", "补充", "再加", "也要",
            "或者", "改为", "换成", "最好是", "注意", "顺便",
            "并且", "同时", "补充下", "补充一下",
        ]
        if any(kw in text for kw in modify_keywords):
            return UserIntent.MODIFY

        # === 0.1 显式新任务（高优先级）===
        explicit_new_task_phrases = [
            "我要", "我想", "帮我", "给我", "麻烦", "请你", "请帮", "重新帮我",
        ]
        if any(phrase in text for phrase in explicit_new_task_phrases):
            if self._is_likely_new_task(text):
                return UserIntent.REPLACE

        # === 1. 检测用户在等待中的疑问/抱怨 ===
        waiting_questions = [
            "有人在", "在吗", "在不在", "人呢", "还在吗",
            "太慢", "好慢", "怎么这么慢", "等好久了",
            "好了吗", "怎么样了", "完成没", "进度",
            "没回应", "没反应", "不回应", "不反应",
            "你在干啥", "你在干嘛", "分析啥", "在做什么",
        ]
        if any(q in text for q in waiting_questions):
            if any(q in text for q in ["吗", "？", "?", "在", "没"]):
                return UserIntent.QUERY_STATUS
            return UserIntent.COMMENT

        # === 2. 检测附和/应答（不打断，但需要明确是附和）===
        backchannel_patterns = [
            "嗯", "嗯嗯", "好的", "好", "行", "可以", "对", "是",
            "ok", "okay", "yes", "right", "明白", "了解", "收到",
        ]
        # 注意：只有明确是附和词才返回BACKCHANNEL
        # 不再用len(text)<=2来判断，因为"取消"也是2个字
        if text in backchannel_patterns:
            return UserIntent.BACKCHANNEL

        # === 2.1 短文本新任务检测（避免“吃饭”被误判）===
        if len(text) <= 4 and self._is_likely_new_task(text):
            return UserIntent.REPLACE

        # === 3. 检测评论/感叹（不打断任务） ===
        comment_patterns = [
            "不错", "很好", "太好了", "厉害", "赞", "可以啊",
            "挺好", "还行", "好的呀", "是吗", "真的吗",
            "interesting", "cool", "nice", "good", "great",
        ]
        if any(pattern in text for pattern in comment_patterns):
            question_patterns = ["吗", "？", "?", "呢", "什么", "怎么", "如何", "为什么"]
            if not any(q in text for q in question_patterns):
                return UserIntent.COMMENT

        # === 4. 查询状态 ===
        status_keywords = [
            "进度", "怎么样", "好了吗", "完成没", "状态", "多久",
            "还在吗", "到哪了", "在不在",
        ]
        if any(kw in text for kw in status_keywords):
            return UserIntent.QUERY_STATUS

        # === 5. 暂停/恢复关键词 ===
        pause_keywords = ["暂停", "等一下", "稍等", "等会", "先停", "pause"]
        if any(kw in text for kw in pause_keywords):
            return UserIntent.PAUSE

        resume_keywords = ["继续", "恢复", "接着", "resume", "continue", "go on"]
        if any(kw in text for kw in resume_keywords):
            return UserIntent.RESUME

        # === 6. 检查是否是全新的任务请求（需要打断） ===
        new_task_indicators = [
            "我要", "帮我", "给我", "推荐", "分析", "比较", "查一下",
            "选", "买", "找", "看", "订", "定", "吃", "点餐",
        ]
        if any(q in text for q in new_task_indicators):
            # 检查是否与当前任务相关
            current_topic = self._current_topic or self._extract_topic(self._current_input)
            new_topic = self._extract_topic(new_input)

            # 如果话题不同，认为是新任务
            if current_topic and new_topic and current_topic != new_topic:
                return UserIntent.REPLACE

            # 如果包含明确的任务词
            if len(text) > 5:
                return UserIntent.REPLACE

        # === 7. 补充/修改信息的关键词 ===
        if any(kw in text for kw in modify_keywords):
            return UserIntent.MODIFY

        # === 8. 回答澄清问题 ===
        clarify_keywords = [
            "是", "对", "好", "可以", "要", "大概", "左右",
            "万", "块", "元", "预算", "北京", "上海", "广州", "深圳",
        ]
        if any(kw in text for kw in clarify_keywords) and len(text) < 20:
            return UserIntent.CONTINUE

        # === 9. 默认：不打断任务 ===
        return UserIntent.COMMENT

    def _is_likely_new_task(self, text: str) -> bool:
        """判断输入是否更像新任务而不是附和/评论。"""
        current_topic = self._current_topic or self._extract_topic(self._current_input or "")
        new_topic = self._extract_topic(text)

        action_keywords = [
            "买", "选", "推荐", "分析", "比较", "查", "找", "看", "订", "定",
            "吃", "安排", "规划", "预订", "打车", "叫车", "叫个",
        ]

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
        使用LLM进行更智能的意图分类

        关键改进：
        - 区分评论/感叹（不打断）和取消请求（打断）
        - 考虑当前任务上下文

        Args:
            new_input: 用户新输入
            llm_client: LLM客户端
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
5. REPLACE - 取消当前任务开始新任务（如"算了"、"不用了"、"帮我查xxx"）
6. CONTINUE - 回答系统的澄清问题

重要规则：
- 如果只是评论或感叹，返回COMMENT，不要误判为REPLACE
- 如果是简短的应答，返回BACKCHANNEL
- 只有明确表示取消或提出全新问题才返回REPLACE

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
        topic_keywords = {
            "选车": ["车", "汽车", "买车", "选车", "suv", "轿车", "新能源车"],
            "打车": ["打车", "滴滴", "高德", " taxi", "专车", "快车"],
            "咖啡": ["咖啡", "拿铁", "星巴克", "瑞幸"],
            "美食": ["餐厅", "美食", "吃的", "推荐菜", "吃饭", "吃"],
            "购物": ["买", "购物", "价格", "便宜"],
            "旅游": ["旅游", "景点", "酒店", "机票"],
        }
        text_lower = text.lower()
        for topic, keywords in topic_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return topic
        return None


class TalkerThinkerApp:
    """
    Talker-Thinker应用

    提供命令行和API两种使用方式
    支持全双工交互：用户可在处理过程中发送新消息
    """

    def __init__(self):
        self.orchestrator: Optional[Orchestrator] = None
        self.metrics = get_metrics_collector()
        self.task_manager = TaskManager()

    async def initialize(self) -> None:
        """初始化应用"""
        logger.info("Initializing Talker-Thinker system...")

        # 创建Orchestrator
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
        """Handoff回调"""
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
            session_id: 会话ID（可选）
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
                # 实时输出（用于CLI模式）
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

    async def _handle_new_input_during_processing(
        self,
        new_input: str,
        session_id: str,
    ) -> tuple[bool, Optional[str]]:
        """
        处理任务进行中的新输入

        关键改进：
        - COMMENT和BACKCHANNEL不打断任务，但Talker应该回应
        - 只有REPLACE才真正取消任务
        - 用户的问题应该得到实时反馈

        Returns:
            tuple: (是否已处理, 响应内容)
        """
        intent = self.task_manager.classify_intent(new_input)
        current = self.task_manager.current_input or "您的请求"

        if intent == UserIntent.COMMENT:
            # 评论/感叹，不打断任务，但Talker应该简短回应
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
            # 查询状态，给详细反馈
            elapsed = time.time() - self.task_manager.task_start_time
            return True, f"\n[Talker] 正在处理「{current[:30]}...」，已用时{elapsed:.0f}秒，请稍候"

        elif intent == UserIntent.REPLACE:
            # 取消当前任务，处理新任务
            print("\n" + "━" * 50)
            print("⚠️ 上一任务已被用户打断")
            print("━" * 50)

            await self.task_manager.cancel_current_task()
            return False, None  # 返回False表示需要处理新任务

        elif intent == UserIntent.MODIFY:
            # 补充信息，确认收到
            return True, f"\n[Talker] 收到补充信息「{new_input[:20]}」，已更新处理中..."

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
        """
        await self.initialize()

        print("=" * 60)
        print("Talker-Thinker 双Agent系统 (全双工模式)")
        print("=" * 60)
        print("输入 'quit' 或 'exit' 退出")
        print("输入 'stats' 查看统计信息")
        print("提示: 处理过程中可随时输入新消息打断当前任务")
        print("=" * 60)
        print()

        session_id = None
        input_queue = asyncio.Queue()

        async def read_input():
            """异步读取用户输入"""
            loop = asyncio.get_event_loop()
            while True:
                try:
                    # 使用线程池执行阻塞的input
                    line = await loop.run_in_executor(None, input)
                    await input_queue.put(line)
                except EOFError:
                    break
                except Exception:
                    break

        # 启动输入读取任务
        input_task = asyncio.create_task(read_input())

        try:
            while True:
                try:
                    # 显示输入提示（如果没有正在处理的任务）
                    if not self.task_manager.is_processing:
                        now = time.time()
                        timestamp = time.strftime("%H:%M:%S", time.localtime(now))
                        ms = int((now % 1) * 1000)
                        print(f"\n[{timestamp}.{ms:03d}] 你: ", end="", flush=True)

                    # 等待用户输入
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
                    self.task_manager._cancelled = False
                    process_task = await self._process_as_task(
                        user_input, session_id, input_time
                    )

                    # 等待任务完成，同时监听新输入
                    while not process_task.done():
                        try:
                            new_input = await asyncio.wait_for(
                                input_queue.get(),
                                timeout=0.2
                            )
                            # 有新输入，处理打断逻辑
                            if new_input.strip():
                                # 显示用户输入
                                print(f"\n\n[{time.strftime('%H:%M:%S')}.{int((time.time() % 1) * 1000):03d}] 你: {new_input}")

                                handled, response = await self._handle_new_input_during_processing(
                                    new_input, session_id
                                )

                                if handled:
                                    if response:
                                        print(response)
                                else:
                                    # 需要处理新任务
                                    user_input = new_input.strip()
                                    input_time = time.time()
                                    break  # 退出等待循环，开始处理新任务

                        except asyncio.TimeoutError:
                            continue

                    # 如果任务完成，清理状态
                    if process_task.done():
                        self.task_manager.end_task()
                        print()  # 换行
                    else:
                        # 被打断，处理新任务
                        self.task_manager._cancelled = False
                        process_task = await self._process_as_task(
                            user_input, session_id, input_time
                        )
                        # 继续等待新任务完成
                        try:
                            await process_task
                        except asyncio.CancelledError:
                            pass
                        self.task_manager.end_task()
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
                    print(f"\n错误: {e}")
                    self.task_manager.end_task()

        finally:
            # 清理
            input_task.cancel()
            try:
                await input_task
            except asyncio.CancelledError:
                pass

    def get_stats(self) -> dict:
        """获取系统统计"""
        if self.orchestrator:
            return self.orchestrator.get_stats()
        return {}


async def main_async():
    """异步主函数"""
    parser = argparse.ArgumentParser(
        description="Talker-Thinker 双Agent系统"
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
        help="会话ID",
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
        print("\n助手: ", end="")
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
