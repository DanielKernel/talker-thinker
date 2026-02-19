"""
Talker-Thinker系统配置模块
"""
import os
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """系统配置类"""

    # 应用配置
    APP_NAME: str = "talker-thinker"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Agent模型配置
    TALKER_MODEL: str = "gpt-4o-mini"
    THINKER_MODEL: str = "gpt-4o"
    TALKER_TEMPERATURE: float = 0.7
    THINKER_TEMPERATURE: float = 0.3

    # 超时配置（毫秒）
    TALKER_TIMEOUT_MS: int = 500
    THINKER_TIMEOUT_MS: int = 30000
    SKILL_TIMEOUT_MS: int = 10000

    # 缓存配置
    CACHE_TTL_SECONDS: int = 3600
    REDIS_URL: str = "redis://localhost:6379"
    CACHE_ENABLED: bool = True

    # 并发配置
    MAX_CONCURRENT_TASKS: int = 10
    MAX_CONCURRENT_SKILLS: int = 5

    # 上下文配置
    MAX_CONTEXT_MESSAGES: int = 100
    MAX_SESSION_HISTORY: int = 1000
    WORKING_CONTEXT_MESSAGES: int = 10
    SUMMARY_THRESHOLD: int = 10

    # 响应层次延迟阈值（毫秒）
    L1_THRESHOLD_MS: int = 100
    L2_THRESHOLD_MS: int = 300
    L3_THRESHOLD_MS: int = 500

    # 监控配置
    ENABLE_METRICS: bool = True
    LOG_LEVEL: str = "INFO"
    ALERT_WEBHOOK_URL: Optional[str] = None

    # 特性开关
    ENABLE_STREAMING: bool = True
    ENABLE_PROGRESS_NOTIFICATION: bool = True
    ENABLE_PROACTIVE_CONVERSATION: bool = True
    ENABLE_SELF_REFLECTION: bool = True

    # 数据库配置
    DATABASE_URL: Optional[str] = None

    # API Keys
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # 向量数据库配置
    VECTOR_DB_URL: Optional[str] = None
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# 全局配置实例
settings = Settings()


def get_settings() -> Settings:
    """获取配置实例"""
    return settings
