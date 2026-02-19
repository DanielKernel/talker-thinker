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


class TaskManager:
    """任务管理器 - 管理任务状态和中断"""

    def __init__(self):
        self._current_task: Optional[asyncio.Task] = None
        self._current_input: Optional[str] = None
        self._is_processing = False
        self._cancelled = False

    @property
    def is_processing(self) -> bool:
        return self._is_processing

    @property
    def current_input(self) -> Optional[str]:
        return self._current_input

    def start_task(self, task: asyncio.Task, user_input: str):
        """开始新任务"""
        self._current_task = task
        self._current_input = user_input
        self._is_processing = True
        self._cancelled = False

    def end_task(self):
        """结束当前任务"""
        self._current_task = None
        self._current_input = None
        self._is_processing = False

    async def cancel_current_task(self) -> bool:
        """取消当前任务"""
        if self._current_task and not self._current_task.done():
            self._cancelled = True
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
        分类用户意图：继续、替换、修改当前任务

        基于自然语言理解用户意图
        """
        if not self._current_input or not self._is_processing:
            return UserIntent.REPLACE

        text = new_input.lower().strip()

        # 明确的取消/替换关键词
        cancel_keywords = [
            "不用", "算了", "取消", "停止", "停", "不要了", "不用了",
            "换个", "改", "重新", "直接", "先", "算了",
            "stop", "cancel", "never mind", "forget it",
        ]
        if any(kw in text for kw in cancel_keywords):
            return UserIntent.REPLACE

        # 查询状态
        status_keywords = [
            "进度", "怎么样", "好了吗", "完成", "状态", "多久",
            "在吗", "还在吗", "继续", "等等",
        ]
        if any(kw in text for kw in status_keywords):
            return UserIntent.QUERY_STATUS

        # 补充/修改信息的关键词
        modify_keywords = [
            "另外", "还有", "加上", "补充", "再加", "也要",
            "或者", "改为", "换成", "最好是",
        ]
        if any(kw in text for kw in modify_keywords):
            return UserIntent.MODIFY

        # 检查是否是全新的话题
        # 如果新问题和当前任务差异很大，认为是替换
        current_topic = self._extract_topic(self._current_input)
        new_topic = self._extract_topic(new_input)

        # 如果话题完全不同，认为是替换意图
        if current_topic and new_topic and current_topic != new_topic:
            # 但如果新输入很短（如"快点"），可能是催促而非替换
            if len(text) > 5:
                return UserIntent.REPLACE

        # 默认：如果当前有任务在运行，新输入视为替换
        # 因为用户不太会在等待时提供补充信息
        return UserIntent.REPLACE

    def _extract_topic(self, text: str) -> Optional[str]:
        """提取话题关键词"""
        topic_keywords = {
            "打车": ["打车", "滴滴", "高德", " taxi", "专车", "快车"],
            "咖啡": ["咖啡", "拿铁", "星巴克", "瑞幸"],
            "美食": ["餐厅", "美食", "吃的", "推荐菜"],
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

        Returns:
            tuple: (是否已处理, 响应内容)
        """
        intent = self.task_manager.classify_intent(new_input)

        if intent == UserIntent.QUERY_STATUS:
            # 查询状态，不取消任务
            current = self.task_manager.current_input
            return True, f"\n[系统] 正在处理: {current[:50]}... 请稍候或发送新问题"

        elif intent == UserIntent.REPLACE:
            # 取消当前任务，处理新任务
            print("\n" + "━" * 50)
            print("⚠️ 上一任务已被用户打断")
            print("━" * 50)

            await self.task_manager.cancel_current_task()
            return False, None  # 返回False表示需要处理新任务

        elif intent == UserIntent.MODIFY:
            # 修改当前任务（这里简化为替换）
            print("\n" + "━" * 50)
            print("🔄 正在调整任务...")
            print("━" * 50)

            await self.task_manager.cancel_current_task()
            return False, None

        else:  # CONTINUE
            # 继续当前任务，忽略新输入或记录为补充信息
            return True, "\n[系统] 收到补充信息，正在处理中..."

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
