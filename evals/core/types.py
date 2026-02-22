"""
评测系统核心类型定义
"""
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from context.types import TaskComplexity, AgentRole


class EvalCategory(str, Enum):
    """评测用例类别"""
    SIMPLE = "simple"       # 简单任务
    MEDIUM = "medium"       # 中等任务
    COMPLEX = "complex"     # 复杂任务
    EDGE = "edge"           # 边界/异常用例


class Priority(str, Enum):
    """用例优先级"""
    CRITICAL = "critical"   # 关键用例
    HIGH = "high"           # 高优先级
    NORMAL = "normal"       # 普通优先级
    LOW = "low"             # 低优先级


class FailureReason(str, Enum):
    """失败原因分类"""
    WRONG_AGENT = "wrong_agent"         # 路由错误 - Agent 分配不正确
    TIMEOUT = "timeout"                 # 超时 - 响应时间超过阈值
    WRONG_OUTPUT = "wrong_output"       # 输出错误 - 答案不符合预期
    SKILL_FAILED = "skill_failed"       # 技能调用失败
    ASSERTION_FAILED = "assertion_failed"  # 断言失败
    EXCEPTION = "exception"             # 异常 - 执行过程中抛出异常
    HANDOFF_FAILED = "handoff_failed"   # Handoff 失败
    CONTEXT_LOST = "context_lost"       # 上下文丢失


@dataclass
class Assertion:
    """
    评测断言

    用于定义单个检查项，包括检查函数、权重和失败原因模板
    """
    name: str                           # 断言名称
    checker: Callable                   # 检查函数
    weight: float = 1.0                 # 权重 (用于计算加权得分)
    failure_reason_template: str = ""   # 失败原因模板
    description: str = ""               # 断言描述

    def check(self, **kwargs) -> "AssertionResult":
        """
        执行断言检查

        Returns:
            AssertionResult: 断言结果
        """
        try:
            passed = self.checker(**kwargs)
            return AssertionResult(
                assertion_name=self.name,
                passed=passed,
                weight=self.weight,
                failure_reason=self.failure_reason_template if not passed else "",
            )
        except Exception as e:
            return AssertionResult(
                assertion_name=self.name,
                passed=False,
                weight=self.weight,
                failure_reason=f"检查异常：{str(e)}",
            )


@dataclass
class AssertionResult:
    """断言执行结果"""
    assertion_name: str
    passed: bool
    weight: float
    failure_reason: str = ""
    details: Optional[str] = None


@dataclass
class EvalCase:
    """
    评测用例

    每个用例包含完整的测试场景定义
    """
    case_id: str                        # 唯一标识 (如 S001, M001, C001)
    name: str                           # 用例名称
    description: str                    # 描述
    category: EvalCategory              # 类别
    user_input: str                     # 用户输入
    expected_complexity: 'TaskComplexity' # 期望复杂度
    expected_agent: 'AgentRole'           # 期望处理 Agent
    assertions: List[Assertion]         # 断言列表
    golden_output: Optional[str] = None # 期望输出 (可选)
    priority: Priority = Priority.NORMAL  # 优先级
    tags: List[str] = field(default_factory=list)  # 标签
    context_messages: List[Dict[str, str]] = field(default_factory=list)  # 前置上下文

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "case_id": self.case_id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "user_input": self.user_input,
            "expected_complexity": self.expected_complexity.value,
            "expected_agent": self.expected_agent.value,
            "golden_output": self.golden_output,
            "priority": self.priority.value,
            "tags": self.tags,
        }


@dataclass
class CaseResult:
    """
    用例执行结果
    """
    case_id: str
    case_name: str
    passed: bool
    actual_agent: 'AgentRole'
    actual_complexity: 'TaskComplexity'
    actual_output: str
    response_time_ms: float
    assertion_results: List[AssertionResult]
    failure_reason: Optional[FailureReason] = None
    failure_details: str = ""
    tokens_used: int = 0
    timestamp: float = field(default_factory=time.time)

    @property
    def score(self) -> float:
        """计算得分 (0-100)"""
        if not self.assertion_results:
            return 100.0 if self.passed else 0.0

        total_weight = sum(a.weight for a in self.assertion_results)
        passed_weight = sum(a.weight for a in self.assertion_results if a.passed)

        if total_weight == 0:
            return 100.0 if self.passed else 0.0

        return (passed_weight / total_weight) * 100

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "case_id": self.case_id,
            "case_name": self.case_name,
            "passed": self.passed,
            "actual_agent": self.actual_agent.value,
            "actual_complexity": self.actual_complexity.value,
            "actual_output": self.actual_output[:500] + "..." if len(self.actual_output) > 500 else self.actual_output,
            "response_time_ms": self.response_time_ms,
            "score": self.score,
            "failure_reason": self.failure_reason.value if self.failure_reason else None,
            "failure_details": self.failure_details,
            "tokens_used": self.tokens_used,
            "timestamp": self.timestamp,
        }


@dataclass
class EvalResult:
    """
    评测结果

    包含单次评测运行的完整结果
    """
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    case_results: List[CaseResult] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0

    @property
    def pass_rate(self) -> float:
        """通过率"""
        if self.total_cases == 0:
            return 0.0
        return self.passed_cases / self.total_cases * 100

    @property
    def average_score(self) -> float:
        """平均得分"""
        if not self.case_results:
            return 0.0
        return sum(r.score for r in self.case_results) / len(self.case_results)

    @property
    def average_response_time(self) -> float:
        """平均响应时间"""
        if not self.case_results:
            return 0.0
        return sum(r.response_time_ms for r in self.case_results) / len(self.case_results)

    @property
    def failure_breakdown(self) -> Dict[FailureReason, int]:
        """失败原因分布"""
        breakdown = {}
        for result in self.case_results:
            if result.failure_reason:
                breakdown[result.failure_reason] = breakdown.get(result.failure_reason, 0) + 1
        return breakdown

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "run_id": self.run_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.end_time - self.start_time,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "pass_rate": self.pass_rate,
            "average_score": self.average_score,
            "average_response_time_ms": self.average_response_time,
            "failure_breakdown": {k.value: v for k, v in self.failure_breakdown.items()},
            "case_results": [r.to_dict() for r in self.case_results],
        }


@dataclass
class EvalReport:
    """
    评测报告

    用于生成最终的评测报告
    """
    eval_result: EvalResult
    category_breakdown: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    historical_comparison: Optional[Dict[str, Any]] = None
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "eval_result": self.eval_result.to_dict(),
            "category_breakdown": self.category_breakdown,
            "historical_comparison": self.historical_comparison,
            "recommendations": self.recommendations,
        }
