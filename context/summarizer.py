"""
上下文摘要器
用于压缩对话历史，减少token使用
"""
import time
from typing import Any, Dict, List, Optional

from context.types import Message


class ConversationSummarizer:
    """
    对话摘要器
    用于压缩对话历史
    """

    def __init__(self, llm_client=None, summary_threshold: int = 10):
        self.llm = llm_client
        self.summary_threshold = summary_threshold
        self._summaries: Dict[str, List[Dict[str, Any]]] = {}

    def _format_messages(self, messages: List[Message]) -> str:
        """格式化消息列表"""
        formatted = []
        for msg in messages:
            role = msg.role
            content = msg.content[:200]  # 截断长消息
            formatted.append(f"[{role}]: {content}")
        return "\n".join(formatted)

    async def summarize_recent_messages(
        self,
        messages: List[Message],
        max_tokens: int = 500,
    ) -> Optional[str]:
        """摘要最近的消息"""
        if len(messages) < self.summary_threshold:
            return None

        formatted = self._format_messages(messages)

        if self.llm:
            prompt = f"""请将以下对话摘要成一段简短文字（不超过{max_tokens} tokens）：

{formatted}

摘要要求：
1. 保留关键信息和决策
2. 省略无关的闲聊
3. 按时间顺序组织
4. 突出重要事件和结论

只输出摘要内容："""

            try:
                summary = await self.llm.generate(prompt, max_tokens=max_tokens)
                return summary
            except Exception:
                pass

        # 简单的fallback摘要
        return self._simple_summarize(messages)

    def _simple_summarize(self, messages: List[Message]) -> str:
        """简单的摘要方法（不使用LLM）"""
        user_messages = [m for m in messages if m.role == "user"]
        assistant_messages = [m for m in messages if m.role in ("assistant", "talker", "thinker")]

        summary_parts = [
            f"对话共{len(messages)}条消息",
            f"用户提问{len(user_messages)}次",
        ]

        # 提取关键话题
        topics = set()
        for msg in user_messages:
            words = msg.content.split()
            for word in words:
                if len(word) > 2 and word not in ("的", "是", "了", "在", "有"):
                    topics.add(word)

        if topics:
            summary_parts.append(f"涉及话题: {', '.join(list(topics)[:5])}")

        return "。".join(summary_parts)

    async def incremental_summarize(
        self,
        session_id: str,
        messages: List[Message],
    ) -> Optional[str]:
        """增量摘要"""
        # 获取之前的摘要
        previous_summaries = self._summaries.get(session_id, [])

        if len(messages) < self.summary_threshold:
            return None

        # 只摘要新消息
        last_summary_count = previous_summaries[-1].get("message_count", 0) if previous_summaries else 0
        new_messages = messages[last_summary_count:]

        if len(new_messages) < self.summary_threshold // 2:
            return None

        # 生成新摘要
        summary = await self.summarize_recent_messages(new_messages)
        if summary:
            self._summaries.setdefault(session_id, []).append({
                "summary": summary,
                "message_count": len(messages),
                "timestamp": time.time(),
            })

        return summary

    async def get_full_context(
        self,
        session_id: str,
        recent_messages: List[Message],
    ) -> str:
        """获取完整上下文（摘要 + 最近消息）"""
        context_parts = []

        # 添加历史摘要
        summaries = self._summaries.get(session_id, [])
        for i, summary_data in enumerate(summaries):
            context_parts.append(f"[历史摘要{i+1}] {summary_data['summary']}")

        # 添加最近原始消息
        if recent_messages:
            context_parts.append("\n【最近对话】")
            context_parts.append(self._format_messages(recent_messages))

        return "\n\n".join(context_parts)

    def clear_session(self, session_id: str) -> None:
        """清除会话摘要"""
        if session_id in self._summaries:
            del self._summaries[session_id]


class ProgressiveSummarizer:
    """
    渐进式摘要器
    分层摘要，保留不同粒度的历史
    """

    def __init__(self, chunk_size: int = 10):
        self.chunk_size = chunk_size
        self._summaries: List[str] = []
        self._message_indices: List[int] = []
        self._messages: List[Message] = []

    async def add_messages(self, messages: List[Message]) -> None:
        """添加消息"""
        self._messages.extend(messages)

        # 检查是否需要生成摘要
        last_index = self._message_indices[-1] if self._message_indices else 0
        if len(self._messages) - last_index >= self.chunk_size:
            # 这里可以调用LLM生成摘要
            summary = self._simple_chunk_summary(
                self._messages[last_index:last_index + self.chunk_size]
            )
            self._summaries.append(summary)
            self._message_indices.append(len(self._messages))

    def _simple_chunk_summary(self, messages: List[Message]) -> str:
        """简单的块摘要"""
        user_contents = [m.content[:50] for m in messages if m.role == "user"]
        if user_contents:
            return f"用户询问: {'; '.join(user_contents[:3])}"
        return "对话片段"

    async def get_full_context(self) -> str:
        """获取完整上下文"""
        context_parts = []

        # 添加摘要
        for i, summary in enumerate(self._summaries):
            context_parts.append(f"[摘要{i+1}] {summary}")

        # 添加最近的原始消息
        if self._message_indices:
            recent_start = self._message_indices[-1]
        else:
            recent_start = 0
        recent_messages = self._messages[recent_start:]

        if recent_messages:
            context_parts.append("\n【最近对话】")
            for msg in recent_messages[-5:]:
                context_parts.append(f"[{msg.role}]: {msg.content[:100]}")

        return "\n".join(context_parts)

    def clear(self) -> None:
        """清空"""
        self._summaries.clear()
        self._message_indices.clear()
        self._messages.clear()
