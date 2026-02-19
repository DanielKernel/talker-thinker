"""
核心类型定义
"""
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentRole(str, Enum):
    """Agent角色"""
    TALKER = "talker"
    THINKER = "thinker"
    ORCHESTRATOR = "orchestrator"


class TaskComplexity(str, Enum):
    """任务复杂度"""
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class ResponseLayer(str, Enum):
    """响应层次"""
    L1_INSTANT = "L1"  # < 100ms
    L2_FAST = "L2"     # < 300ms
    L3_ASYNC = "L3"    # 异步
    L4_STREAM = "L4"   # 流式


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class HandoffType(str, Enum):
    """Handoff类型"""
    DELEGATION = "delegation"
    PARALLEL = "parallel"
    ITERATIVE = "iterative"
    COLLABORATION = "collaboration"


@dataclass
class Message:
    """消息类"""
    role: str  # "user", "assistant", "system", "talker", "thinker"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AgentState:
    """Agent状态"""
    agent_name: str
    status: str
    current_task: Optional[str] = None
    progress: float = 0.0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "status": self.status,
            "current_task": self.current_task,
            "progress": self.progress,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class Task:
    """任务类"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_input: str = ""
    complexity: TaskComplexity = TaskComplexity.SIMPLE
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: Optional[AgentRole] = None
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_input": self.user_input,
            "complexity": self.complexity.value,
            "status": self.status.value,
            "assigned_agent": self.assigned_agent.value if self.assigned_agent else None,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        return cls(
            task_id=data["task_id"],
            user_input=data["user_input"],
            complexity=TaskComplexity(data["complexity"]),
            status=TaskStatus(data["status"]),
            assigned_agent=AgentRole(data["assigned_agent"]) if data.get("assigned_agent") else None,
            result=data.get("result"),
            error=data.get("error"),
            created_at=data["created_at"],
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class StepResult:
    """步骤执行结果"""
    step_name: str
    status: str  # "success", "failed", "partial_success"
    result: str
    intermediate_results: List[Dict[str, Any]] = field(default_factory=list)
    skills_called: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    tokens_used: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_name": self.step_name,
            "status": self.status,
            "result": self.result,
            "intermediate_results": self.intermediate_results,
            "skills_called": self.skills_called,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "errors": self.errors,
        }


@dataclass
class QualityScore:
    """质量评分"""
    overall_score: float
    completeness: float
    accuracy: float
    relevance: float
    clarity: float
    usefulness: float
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    needs_revision: bool = False
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "dimensions": {
                "completeness": self.completeness,
                "accuracy": self.accuracy,
                "relevance": self.relevance,
                "clarity": self.clarity,
                "usefulness": self.usefulness,
            },
            "issues": self.issues,
            "suggestions": self.suggestions,
            "needs_revision": self.needs_revision,
            "reasoning": self.reasoning,
        }
