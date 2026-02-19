"""
L2: Session Context（会话上下文）
存储在Redis中，用于跨轮次的状态保持
支持Redis不可用时降级到内存存储
"""
import json
import time
from typing import Any, Dict, List, Optional

from config import settings
from context.types import Message, Task

# 尝试导入redis，如果不可用则使用内存存储
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class InMemorySessionStorage:
    """内存会话存储（Redis不可用时的降级方案）"""

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._messages: Dict[str, List[Dict]] = {}
        self._summaries: Dict[str, str] = {}
        self._data: Dict[str, Dict[str, Any]] = {}

    def _get_or_create_session(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "created_at": time.time(),
                "messages": [],
            }
        return self._sessions[session_id]

    def add_message(self, session_id: str, message: Dict) -> None:
        if session_id not in self._messages:
            self._messages[session_id] = []
        self._messages[session_id].insert(0, message)
        # 保留最近100条
        self._messages[session_id] = self._messages[session_id][:100]

    def get_messages(self, session_id: str, limit: int = 50) -> List[Dict]:
        messages = self._messages.get(session_id, [])
        return list(reversed(messages[:limit]))

    def set_data(self, session_id: str, key: str, value: Any) -> None:
        if session_id not in self._data:
            self._data[session_id] = {}
        self._data[session_id][key] = value

    def get_data(self, session_id: str, key: str, default: Any = None) -> Any:
        return self._data.get(session_id, {}).get(key, default)

    def set_summary(self, session_id: str, summary: str) -> None:
        self._summaries[session_id] = summary

    def get_summary(self, session_id: str) -> Optional[str]:
        return self._summaries.get(session_id)

    def exists(self, session_id: str) -> bool:
        return session_id in self._messages or session_id in self._sessions

    def delete_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._messages.pop(session_id, None)
        self._summaries.pop(session_id, None)
        self._data.pop(session_id, None)


class SessionContext:
    """
    会话上下文 - L2层
    支持Redis存储和内存存储两种模式
    TTL: 24小时
    """

    def __init__(self, redis_client=None, use_memory_fallback: bool = True):
        self.redis = redis_client
        self._use_redis = REDIS_AVAILABLE and redis_client is not None
        self._memory_storage = InMemorySessionStorage() if use_memory_fallback else None
        self._redis_checked = False

    async def _check_redis_available(self) -> bool:
        """检查Redis是否可用"""
        if self._redis_checked:
            return self._use_redis

        if not REDIS_AVAILABLE:
            self._use_redis = False
            self._redis_checked = True
            return False

        try:
            if self.redis is None:
                self.redis = redis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                )
            # 测试连接
            await self.redis.ping()
            self._use_redis = True
        except Exception:
            self._use_redis = False
            if self._memory_storage is None:
                self._memory_storage = InMemorySessionStorage()

        self._redis_checked = True
        return self._use_redis

    def _make_key(self, session_id: str, *parts: str) -> str:
        """生成Redis键"""
        return f"session:{session_id}:{':'.join(parts)}"

    async def add_message(self, session_id: str, message: Message) -> None:
        """添加消息到会话历史"""
        if await self._check_redis_available():
            try:
                key = self._make_key(session_id, "messages")
                await self.redis.lpush(key, json.dumps(message.to_dict()))
                await self.redis.ltrim(key, 0, settings.MAX_CONTEXT_MESSAGES - 1)
                await self.redis.expire(key, 86400)
                return
            except Exception:
                pass  # 降级到内存存储

        # 内存存储
        self._memory_storage.add_message(session_id, message.to_dict())

    async def get_messages(
        self, session_id: str, limit: int = 50
    ) -> List[Message]:
        """获取会话消息历史"""
        if await self._check_redis_available():
            try:
                key = self._make_key(session_id, "messages")
                messages_data = await self.redis.lrange(key, 0, limit - 1)
                return [Message.from_dict(json.loads(m)) for m in reversed(messages_data)]
            except Exception:
                pass  # 降级到内存存储

        # 内存存储
        messages_data = self._memory_storage.get_messages(session_id, limit)
        return [Message.from_dict(m) for m in messages_data]

    async def set_task_state(
        self, session_id: str, task_id: str, state: Dict[str, Any]
    ) -> None:
        """设置任务状态"""
        if await self._check_redis_available():
            try:
                key = self._make_key(session_id, "task", task_id)
                await self.redis.hset(key, mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                                                for k, v in state.items()})
                await self.redis.expire(key, 3600)
                return
            except Exception:
                pass

        self._memory_storage.set_data(session_id, f"task_{task_id}", state)

    async def get_task_state(
        self, session_id: str, task_id: str
    ) -> Dict[str, Any]:
        """获取任务状态"""
        if await self._check_redis_available():
            try:
                key = self._make_key(session_id, "task", task_id)
                data = await self.redis.hgetall(key)
                if not data:
                    return {}
                return {k: json.loads(v) if v.startswith(("{", "[")) else v
                        for k, v in data.items()}
            except Exception:
                pass

        return self._memory_storage.get_data(session_id, f"task_{task_id}", {})

    async def set_session_data(
        self, session_id: str, key: str, value: Any, ttl: int = 86400
    ) -> None:
        """设置会话数据"""
        if await self._check_redis_available():
            try:
                redis_key = self._make_key(session_id, "data", key)
                await self.redis.set(redis_key, json.dumps(value), ex=ttl)
                return
            except Exception:
                pass

        self._memory_storage.set_data(session_id, key, value)

    async def get_session_data(
        self, session_id: str, key: str, default: Any = None
    ) -> Any:
        """获取会话数据"""
        if await self._check_redis_available():
            try:
                redis_key = self._make_key(session_id, "data", key)
                data = await self.redis.get(redis_key)
                if data is None:
                    return default
                return json.loads(data)
            except Exception:
                pass

        return self._memory_storage.get_data(session_id, key, default)

    async def set_summary(self, session_id: str, summary: str) -> None:
        """保存会话摘要"""
        if await self._check_redis_available():
            try:
                key = self._make_key(session_id, "summary")
                await self.redis.set(key, summary, ex=86400)
                return
            except Exception:
                pass

        self._memory_storage.set_summary(session_id, summary)

    async def get_summary(self, session_id: str) -> Optional[str]:
        """获取会话摘要"""
        if await self._check_redis_available():
            try:
                key = self._make_key(session_id, "summary")
                return await self.redis.get(key)
            except Exception:
                pass

        return self._memory_storage.get_summary(session_id)

    async def increment_counter(self, session_id: str, counter_name: str) -> int:
        """增加计数器"""
        if await self._check_redis_available():
            try:
                key = self._make_key(session_id, "counter", counter_name)
                return await self.redis.incr(key)
            except Exception:
                pass

        # 内存计数器
        current = self._memory_storage.get_data(session_id, f"counter_{counter_name}", 0)
        self._memory_storage.set_data(session_id, f"counter_{counter_name}", current + 1)
        return current + 1

    async def get_context_for_agent(
        self,
        session_id: str,
        agent_role: str,
        max_messages: int = 20,
    ) -> Dict[str, Any]:
        """获取Agent所需的上下文"""
        messages = await self.get_messages(session_id, limit=max_messages)
        summary = await self.get_summary(session_id)

        return {
            "session_id": session_id,
            "messages": [m.to_dict() for m in messages],
            "summary": summary,
            "agent_role": agent_role,
        }

    async def delete_session(self, session_id: str) -> None:
        """删除会话"""
        if await self._check_redis_available():
            try:
                pattern = self._make_key(session_id, "*")
                keys = await self.redis.keys(pattern)
                if keys:
                    await self.redis.delete(*keys)
                return
            except Exception:
                pass

        self._memory_storage.delete_session(session_id)

    async def exists(self, session_id: str) -> bool:
        """检查会话是否存在"""
        if await self._check_redis_available():
            try:
                key = self._make_key(session_id, "messages")
                return await self.redis.exists(key) > 0
            except Exception:
                pass

        return self._memory_storage.exists(session_id)

    async def set_user_preference(
        self, session_id: str, key: str, value: Any
    ) -> None:
        """设置用户偏好"""
        await self.set_session_data(session_id, f"pref:{key}", value, ttl=86400 * 7)

    async def get_user_preference(
        self, session_id: str, key: str, default: Any = None
    ) -> Any:
        """获取用户偏好"""
        return await self.get_session_data(session_id, f"pref:{key}", default)
