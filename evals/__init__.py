"""
Talker-Thinker 评测系统

分层评测架构:
- L1 单元测试：组件级别 (Agent、Skills、Context)
- L2 集成测试：Agent 协同、Handoff 机制
- L3 端到端评测：完整用户场景
- L4 质量评估：答案质量、相关性、准确性
"""

from context.types import TaskComplexity, AgentRole

from .core.types import (
    EvalCase,
    Assertion,
    EvalCategory,
    Priority,
    FailureReason,
    EvalResult,
    CaseResult,
    EvalReport,
    AssertionResult,
)
from .harness import EvalRunner
from .metrics.collector import MetricsCollector

__version__ = "1.0.0"
__all__ = [
    "EvalCase",
    "Assertion",
    "EvalCategory",
    "TaskComplexity",
    "AgentRole",
    "Priority",
    "FailureReason",
    "EvalResult",
    "CaseResult",
    "EvalReport",
    "AssertionResult",
    "EvalRunner",
    "MetricsCollector",
]
