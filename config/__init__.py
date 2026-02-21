"""
配置模块
"""
from config.settings import Settings, get_settings, settings
from config.keywords_manager import KeywordsManager, get_keywords_manager

__all__ = [
    "Settings",
    "get_settings",
    "settings",
    "KeywordsManager",
    "get_keywords_manager",
]
