"""
Orchestrator - 协调器
管理Talker和Thinker的协同工作
"""
import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from config import settings
from context.types import AgentRole, HandoffType, Message, ResponseLayer, Task, TaskComplexity
from agents.talker.agent import TalkerAgent
from agents.thinker.agent import ThinkerAgent
from orchestrator.scheduler import TaskScheduler, ComplexityBasedScheduler


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
    ):
        # Agent实例
        self.talker = talker or TalkerAgent()
        self.thinker = thinker or ThinkerAgent()

        # 调度器
        self.task_scheduler = task_scheduler or TaskScheduler()
        self.complexity_scheduler = ComplexityBasedScheduler()

        # 会话状态
        self._sessions: Dict[str, Dict[str, Any]] = {}
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

        session = self._get_or_create_session(session_id)
        session["messages"].append({
            "role": "user",
            "content": user_input,
            "timestamp": time.time(),
        })

        # 构建上下文
        full_context = {
            **(context or {}),
            "session_id": session_id,
            "messages": session["messages"],
            "received_time": received_time,
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
            import re
            # 移除类似 [接收: 00:09:01.123] [Talker | 简单任务] 的标记
            clean_response = re.sub(r'\[接收: [^\]]+\]\s*\[[^\]]+\]\s*', '', assistant_response)
            # 移除类似 [响应时延: XXXms] 的标记
            clean_response = re.sub(r'\n?\[[^\]]*时延[^\]]*\]$', '', clean_response)
            # 移除类似 [Talker -> Thinker | ...] 的标记
            clean_response = re.sub(r'\[[^\]]*Talker[^\]]*\]\s*', '', clean_response)
            # 移除类似 [Thinker开始: ...] 的标记
            clean_response = re.sub(r'\[[^\]]*Thinker[^\]]*\]\s*', '', clean_response)
            clean_response = clean_response.strip()

            if clean_response:
                session["messages"].append({
                    "role": "assistant",
                    "content": clean_response,
                    "timestamp": time.time(),
                })

            elapsed = (time.time() - start_time) * 1000
            session["last_latency_ms"] = elapsed

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
        """
        start_time = time.time()
        if received_time is None:
            received_time = start_time

        # 格式化时间戳（精确到毫秒）
        def format_timestamp(t):
            ts = time.strftime("%H:%M:%S", time.localtime(t))
            ms = int((t % 1) * 1000)
            return f"{ts}.{ms:03d}"

        # 显示Agent身份标识和接收时间
        if settings.SHOW_AGENT_IDENTITY:
            complexity_str = {
                TaskComplexity.SIMPLE: "简单",
                TaskComplexity.MEDIUM: "中等",
                TaskComplexity.COMPLEX: "复杂",
            }.get(classification.complexity, "未知")
            yield f"[接收: {format_timestamp(received_time)}] [Talker | {complexity_str}任务]\n"

        first_token_time = None
        async for chunk in self.talker.process(user_input, context):
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
                    user_input, context, start_time, received_time=received_time
                ):
                    yield thinker_chunk
                return

            if first_token_time is None and chunk.strip():
                first_token_time = time.time()
            yield chunk

        # 显示响应时延和首token时间
        end_time = time.time()
        elapsed_ms = (end_time - start_time) * 1000
        if settings.SHOW_AGENT_IDENTITY:
            timing_info = [f"响应时延: {elapsed_ms:.0f}ms"]
            if first_token_time:
                first_token_ms = (first_token_time - start_time) * 1000
                timing_info.append(f"首Token: {first_token_ms:.0f}ms")
                timing_info.append(f"首Token时间: {format_timestamp(first_token_time)}")
            yield f"\n[{' | '.join(timing_info)}]"

    async def _collaboration_handoff(
        self,
        user_input: str,
        context: Dict[str, Any],
        start_time: float = None,
        received_time: float = None,
    ) -> AsyncIterator[str]:
        """
        协作模式Handoff

        Talker收集信息，Thinker深度处理，Talker播报
        """
        if start_time is None:
            start_time = time.time()
        if received_time is None:
            received_time = start_time

        thinker_start = time.time()

        # 格式化时间戳（精确到毫秒）
        def format_timestamp(t):
            ts = time.strftime("%H:%M:%S", time.localtime(t))
            ms = int((t % 1) * 1000)
            return f"{ts}.{ms:03d}"

        # Talker首先给用户反馈
        if settings.SHOW_AGENT_IDENTITY:
            yield f"[接收: {format_timestamp(received_time)}] [Talker -> Thinker | 复杂任务转交]\n"
        yield "好的，这个问题需要我深度思考一下...\n\n"

        # 记录Handoff到Thinker
        self._record_handoff(
            HandoffType.COLLABORATION,
            "talker",
            "thinker",
            "启动协作模式",
        )

        # 显示Thinker身份标识
        if settings.SHOW_AGENT_IDENTITY:
            yield f"[Thinker开始: {format_timestamp(thinker_start)}]\n"

        # 收集Thinker的输出
        thinker_output = []
        first_token_time = None
        async for chunk in self.thinker.process(user_input, context):
            if first_token_time is None and chunk.strip():
                first_token_time = time.time()
            thinker_output.append(chunk)
            yield chunk

        # 完整的Thinker输出
        full_output = "".join(thinker_output)

        # 记录Handoff回Talker
        self._record_handoff(
            HandoffType.COLLABORATION,
            "thinker",
            "talker",
            "Thinker处理完成",
        )

        # 显示响应时延
        end_time = time.time()
        elapsed_ms = (end_time - start_time) * 1000
        thinker_ms = (end_time - thinker_start) * 1000
        if settings.SHOW_AGENT_IDENTITY:
            timing_parts = [f"总时延: {elapsed_ms:.0f}ms", f"Thinker时延: {thinker_ms:.0f}ms"]
            if first_token_time:
                first_token_ms = (first_token_time - thinker_start) * 1000
                timing_parts.append(f"首Token: {first_token_ms:.0f}ms")
            yield f"\n[{' | '.join(timing_parts)}]"

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

    def _get_or_create_session(self, session_id: str) -> Dict[str, Any]:
        """获取或创建会话"""
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "messages": [],
                "created_at": time.time(),
                "state": "active",
            }
        return self._sessions[session_id]

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

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话信息"""
        return self._sessions.get(session_id)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "active_sessions": len(self._sessions),
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

    def clear_session(self, session_id: str) -> None:
        """清除会话"""
        if session_id in self._sessions:
            del self._sessions[session_id]

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
