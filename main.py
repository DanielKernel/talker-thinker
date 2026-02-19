"""
Talker-Thinker 双Agent系统主入口
"""
import argparse
import asyncio
import json
import sys
from typing import Optional

from config import settings
from orchestrator.coordinator import Orchestrator
from monitoring.logging import get_logger
from monitoring.metrics import get_metrics_collector

logger = get_logger("main")


class TalkerThinkerApp:
    """
    Talker-Thinker应用

    提供命令行和API两种使用方式
    """

    def __init__(self):
        self.orchestrator: Optional[Orchestrator] = None
        self.metrics = get_metrics_collector()

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

    async def process(self, user_input: str, session_id: Optional[str] = None) -> str:
        """
        处理用户输入

        Args:
            user_input: 用户输入
            session_id: 会话ID（可选）

        Returns:
            str: 系统响应
        """
        if not self.orchestrator:
            await self.initialize()

        start_time = asyncio.get_event_loop().time()

        # 收集流式响应
        result_chunks = []
        async for chunk in self.orchestrator.process(user_input, session_id):
            result_chunks.append(chunk)
            # 实时输出（用于CLI模式）
            print(chunk, end="", flush=True)

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

    async def run_interactive(self) -> None:
        """运行交互模式"""
        await self.initialize()

        print("=" * 50)
        print("Talker-Thinker 双Agent系统")
        print("=" * 50)
        print("输入 'quit' 或 'exit' 退出")
        print("输入 'stats' 查看统计信息")
        print("=" * 50)
        print()

        session_id = None
        turn = 0

        while True:
            try:
                # 读取用户输入
                user_input = input("\n你: ").strip()

                if not user_input:
                    continue

                # 处理特殊命令
                if user_input.lower() in ("quit", "exit"):
                    print("\n再见!")
                    break

                if user_input.lower() == "stats":
                    stats = self.orchestrator.get_stats()
                    print("\n系统统计:")
                    print(json.dumps(stats, indent=2, ensure_ascii=False))
                    continue

                # 处理用户输入
                print("\n助手: ", end="")
                turn += 1
                if session_id is None:
                    import uuid
                    session_id = str(uuid.uuid4())

                await self.process(user_input, session_id)
                print()  # 换行

            except KeyboardInterrupt:
                print("\n\n已中断")
                break
            except Exception as e:
                logger.error(f"Error in interactive mode: {e}")
                print(f"\n错误: {e}")

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
