"""
L3: Long-term Memory（长期记忆）
存储在PostgreSQL中，用于持久化用户数据和重要事件
"""
import json
import time
from typing import Any, Dict, List, Optional

from config import settings


class LongTermMemory:
    """
    长期记忆 - L3层
    存储在PostgreSQL中，永久保存
    """

    def __init__(self, db_connection=None):
        self.db = db_connection
        self._connected = False

    async def _ensure_connection(self) -> None:
        """确保数据库连接"""
        if self.db is None and settings.DATABASE_URL:
            # 延迟导入以避免未安装asyncpg时报错
            import asyncpg
            self.db = await asyncpg.connect(settings.DATABASE_URL)
            self._connected = True
            await self._create_tables()

    async def _create_tables(self) -> None:
        """创建数据表"""
        if not self._connected:
            return

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id VARCHAR(255) PRIMARY KEY,
                profile_data JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS user_events (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                event_type VARCHAR(100) NOT NULL,
                event_data JSONB NOT NULL DEFAULT '{}',
                timestamp BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_events_user_id (user_id),
                INDEX idx_user_events_timestamp (timestamp)
            )
        """)

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255),
                summary TEXT NOT NULL,
                message_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_conversation_summaries_session_id (session_id),
                INDEX idx_conversation_summaries_user_id (user_id)
            )
        """)

    async def save_event(
        self,
        user_id: str,
        event_type: str,
        event_data: Dict[str, Any],
    ) -> None:
        """保存用户事件"""
        await self._ensure_connection()
        if not self._connected:
            return

        await self.db.execute(
            """
            INSERT INTO user_events (user_id, event_type, event_data, timestamp)
            VALUES ($1, $2, $3, $4)
            """,
            user_id,
            event_type,
            json.dumps(event_data),
            int(time.time() * 1000),
        )

    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户档案"""
        await self._ensure_connection()
        if not self._connected:
            return None

        row = await self.db.fetchrow(
            """
            SELECT profile_data FROM user_profiles WHERE user_id = $1
            """,
            user_id,
        )
        if row:
            return dict(row["profile_data"])
        return None

    async def update_user_profile(
        self, user_id: str, updates: Dict[str, Any]
    ) -> None:
        """更新用户档案"""
        await self._ensure_connection()
        if not self._connected:
            return

        await self.db.execute(
            """
            INSERT INTO user_profiles (user_id, profile_data, updated_at)
            VALUES ($1, $2, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) DO UPDATE SET
                profile_data = user_profiles.profile_data || $2,
                updated_at = CURRENT_TIMESTAMP
            """,
            user_id,
            json.dumps(updates),
        )

    async def get_user_events(
        self,
        user_id: str,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """获取用户事件"""
        await self._ensure_connection()
        if not self._connected:
            return []

        if event_type:
            rows = await self.db.fetch(
                """
                SELECT event_type, event_data, timestamp
                FROM user_events
                WHERE user_id = $1 AND event_type = $2
                ORDER BY timestamp DESC
                LIMIT $3
                """,
                user_id,
                event_type,
                limit,
            )
        else:
            rows = await self.db.fetch(
                """
                SELECT event_type, event_data, timestamp
                FROM user_events
                WHERE user_id = $1
                ORDER BY timestamp DESC
                LIMIT $2
                """,
                user_id,
                limit,
            )

        return [
            {
                "event_type": row["event_type"],
                "event_data": dict(row["event_data"]),
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]

    async def save_conversation_summary(
        self,
        session_id: str,
        user_id: Optional[str],
        summary: str,
        message_count: int,
    ) -> None:
        """保存会话摘要"""
        await self._ensure_connection()
        if not self._connected:
            return

        await self.db.execute(
            """
            INSERT INTO conversation_summaries
            (session_id, user_id, summary, message_count)
            VALUES ($1, $2, $3, $4)
            """,
            session_id,
            user_id,
            summary,
            message_count,
        )

    async def get_conversation_summaries(
        self,
        user_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """获取用户的会话摘要"""
        await self._ensure_connection()
        if not self._connected:
            return []

        rows = await self.db.fetch(
            """
            SELECT session_id, summary, message_count, created_at
            FROM conversation_summaries
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )

        return [dict(row) for row in rows]

    async def learn_user_preference(
        self,
        user_id: str,
        category: str,
        preference: str,
        strength: float = 1.0,
    ) -> None:
        """学习用户偏好"""
        profile = await self.get_user_profile(user_id) or {}
        preferences = profile.get("preferences", {})

        if category not in preferences:
            preferences[category] = {}

        # 更新偏好强度
        current_strength = preferences[category].get(preference, 0)
        preferences[category][preference] = current_strength + strength

        profile["preferences"] = preferences
        await self.update_user_profile(user_id, {"preferences": preferences})

    async def get_user_preferences(
        self, user_id: str, category: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取用户偏好"""
        profile = await self.get_user_profile(user_id)
        if not profile:
            return {}

        preferences = profile.get("preferences", {})
        if category:
            return preferences.get(category, {})
        return preferences

    async def close(self) -> None:
        """关闭数据库连接"""
        if self.db and self._connected:
            await self.db.close()
            self._connected = False
