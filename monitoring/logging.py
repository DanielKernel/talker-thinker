"""
Structured Logger - 结构化日志记录
"""
import logging
import os
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

try:
    import structlog
    HAS_STRUCTLOG = True
except ImportError:
    HAS_STRUCTLOG = False

from config import settings


# 日志目录
LOG_DIR = "logs"


def setup_logging(log_dir: str = LOG_DIR) -> None:
    """
    配置全局日志系统

    Args:
        log_dir: 日志目录
    """
    # 创建日志目录
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 根日志配置
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL))

    # 清除现有处理器
    root_logger.handlers.clear()

    # 日志格式
    log_format = '%(asctime)s [%(levelname)s] %(name)s - %(message)s'
    formatter = logging.Formatter(log_format)

    # 控制台处理器 - 只显示错误及以上级别，避免干扰交互界面
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.ERROR)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件处理器 - 所有日志
    log_file = os.path.join(log_dir, "talker-thinker.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8',
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 文件处理器 - 错误日志
    error_log_file = os.path.join(log_dir, "error.log")
    error_handler = RotatingFileHandler(
        error_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8',
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)

    # 抑制第三方库的日志
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


class StructuredLogger:
    """
    结构化日志记录器

    支持JSON格式输出和上下文绑定
    """

    def __init__(self, name: str):
        self.name = name
        self._logger = logging.getLogger(name)
        self._logger.setLevel(getattr(logging, settings.LOG_LEVEL))

        # 上下文
        self._context: Dict[str, Any] = {}

    def bind(self, **kwargs) -> "StructuredLogger":
        """绑定上下文"""
        self._context.update(kwargs)
        return self

    def unbind(self, *keys) -> "StructuredLogger":
        """解除绑定上下文"""
        for key in keys:
            self._context.pop(key, None)
        return self

    def _log(self, level: int, message: str, **kwargs) -> None:
        """内部日志方法"""
        extra = {**self._context, **kwargs}
        extra_str = " | ".join(f"{k}={v}" for k, v in extra.items())
        full_message = f"{message} | {extra_str}" if extra_str else message
        self._logger.log(level, full_message)

    def debug(self, message: str, **kwargs) -> None:
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs) -> None:
        self._log(logging.CRITICAL, message, **kwargs)

    def exception(self, message: str, **kwargs) -> None:
        """记录异常（包含堆栈信息）"""
        extra = {**self._context, **kwargs}
        extra_str = " | ".join(f"{k}={v}" for k, v in extra.items())
        full_message = f"{message} | {extra_str}" if extra_str else message
        self._logger.exception(full_message)

    def log_request(
        self,
        request_id: str,
        agent: str,
        task: str,
        start_time: float,
        end_time: Optional[float] = None,
        status: str = "completed",
        error: Optional[str] = None,
    ) -> None:
        """记录请求"""
        end_time = end_time or time.time()
        duration_ms = (end_time - start_time) * 1000

        self.info(
            "request_processed",
            request_id=request_id,
            agent=agent,
            task=task[:100],
            duration_ms=round(duration_ms, 2),
            status=status,
            error=error,
        )

    def log_handoff(
        self,
        from_agent: str,
        to_agent: str,
        reason: str,
    ) -> None:
        """记录Handoff"""
        self.info(
            "agent_handoff",
            from_agent=from_agent,
            to_agent=to_agent,
            reason=reason,
        )

    def log_skill_invocation(
        self,
        skill_name: str,
        params: Dict[str, Any],
        success: bool,
        latency_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """记录技能调用"""
        self.info(
            "skill_invoked",
            skill=skill_name,
            success=success,
            latency_ms=round(latency_ms, 2),
            error=error,
        )


def get_logger(name: str) -> StructuredLogger:
    """获取日志记录器"""
    return StructuredLogger(name)


# 初始化日志系统
setup_logging()
