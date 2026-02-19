"""
L2: Session Context（会话上下文）
存储在Redis中，用于跨轮次的状态保持
"""
import json
import time
from typing import Any, Dict, List, Optional

import redis.asyncio as redis

from config import settings
from context.types import Message, Task


class SessionContext:
    """
    会话上下文 - L2层
    存储在Redis中，支持跨轮次访问
    TTL: 24小时
    """

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client
        self._local_cache: Dict[str, Any] = {}

    async def _get_redis(self) -> redis.Redis:
        """获取Redis客户端"""
        if self.redis is None:
            self.redis = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        return self.redis

    def _make_key(self, session_id: str, *parts: str) -> str:
        """生成Redis键"""
        return f"session:{session_id}:{':'.join(parts)}"

    async def add_message(self, session_id: str, message: Message) -> None:
        """添加消息到会话历史"""
        client = await self._get_redis()
        key = self._make_key(session_id, "messages")
        await client.lpush(key, json.dumps(message.to_dict()))
        # 只保留最近100条
        await client.ltrim(key, 0, settings.MAX_CONTEXT_MESSAGES - 1)
        await client.expire(key, 86400)  # 24小时过期

    async def get_messages(
        self, session_id: str, limit: int = 50
    ) -> List[Message]:
        """获取会话消息历史"""
        client = await self._get_redis()
        key = self._make_key(session_id, "messages")
        messages_data = await client.lrange(key, 0, limit - 1)
        return [Message.from_dict(json.loads(m)) for m in reversed(messages_data)]

    async def set_task_state(
        self, session_id: str, task_id: str, state: Dict[str, Any]
    ) -> None:
        """设置任务状态"""
        client = await self._get_redis()
        key = self._make_key(session_id, "task", task_id)
        await client.hset(key, mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                                        for k, v in state.items()})
        await client.expire(key, 3600)  # 1小时过期

    async def get_task_state(
        self, session_id: str, task_id: str
    ) -> Dict[str, Any]:
        """获取任务状态"""
        client = await self._get_redis()
        key = self._make_key(session_id, "task", task_id)
        data = await client.hgetall(key)
        if not data:
            return {}
        return {k: json.loads(v) if v.startswith(("{", "[")) else v
                for k, v in data.items()}

    async def set_session_data(
        self, session_id: str, key: str, value: Any, ttl: int = 86400
    ) -> None:
        """设置会话数据"""
        client = await self._get_redis()
        redis_key = self._make_key(session_id, "data", key)
        await client.set(redis_key, json.dumps(value), ex=ttl)

    async def get_session_data(
        self, session_id: str, key: str, default: Any = None
    ) -> Any:
        """获取会话数据"""
        client = await self._get_redis()
        redis_key = self._make_key(session_id, "data", key)
        data = await client.get(redis_key)
        if data is None:
            return default
        return json.loads(data)

    async def set_summary(self, session_id: str, summary: str) -> None:
        """保存会话摘要"""
        client = await self._get_redis()
        key = self._make_key(session_id, "summary")
        await client.set(key, summary, ex=86400)

    async def get_summary(self, session_id: str) -> Optional[str]:
        """获取会话摘要"""
        client = await self._get_redis()
        key = self._make_key(session_id, "summary")
        return await client.get(key)

    async def increment_counter(self, session_id: str, counter_name: str) -> int:
        """增加计数器"""
        client = await self._get_redis()
        key = self._make_key(session_id, "counter", counter_name)
        return await client.incr(key)

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
        client = await self._get_redis()
        pattern = self._make_key(session_id, "*")
        keys = await client.keys(pattern)
        if keys:
            await client.delete(*keys)

    async def exists(self, session_id: str) -> bool:
        """检查会话是否存在"""
        client = await self._get_redis()
        key = self._make_key(session_id, "messages")
        return await client.exists(key) > 0

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
