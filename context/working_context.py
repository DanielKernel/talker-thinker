"""
L1: Working Context（工作上下文）
存储在内存中，用于当前会话轮次的快速访问
"""
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from context.types import AgentState, Message


@dataclass
class WorkingContext:
    """
    工作上下文 - L1层
    存储当前轮次的消息、Agent状态和临时变量
    延迟要求: < 1ms
    """
    turn_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    messages: List[Message] = field(default_factory=list)
    agent_states: Dict[str, AgentState] = field(default_factory=dict)
    temp_vars: Dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    version: int = 0

    def add_message(self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Message:
        """添加消息"""
        message = Message(
            role=role,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self.messages.append(message)
        self.version += 1
        return message

    def set_agent_state(
        self,
        agent_name: str,
        status: str,
        current_task: Optional[str] = None,
        progress: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentState:
        """设置Agent状态"""
        state = AgentState(
            agent_name=agent_name,
            status=status,
            current_task=current_task,
            progress=progress,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self.agent_states[agent_name] = state
        self.version += 1
        return state

    def get_agent_state(self, agent_name: str) -> Optional[AgentState]:
        """获取Agent状态"""
        return self.agent_states.get(agent_name)

    def set_temp_var(self, key: str, value: Any) -> None:
        """设置临时变量"""
        self.temp_vars[key] = value
        self.version += 1

    def get_temp_var(self, key: str, default: Any = None) -> Any:
        """获取临时变量"""
        return self.temp_vars.get(key, default)

    def get_recent_messages(self, n: int = 10) -> List[Message]:
        """获取最近n条消息"""
        return self.messages[-n:]

    def get_recent_context(self, n: int = 10) -> Dict[str, Any]:
        """获取最近上下文"""
        return {
            "turn_id": self.turn_id,
            "messages": [m.to_dict() for m in self.get_recent_messages(n)],
            "agent_states": {k: v.to_dict() for k, v in self.agent_states.items()},
            "temp_vars": self.temp_vars,
            "start_time": self.start_time,
            "version": self.version,
        }

    def clear(self) -> None:
        """清空上下文"""
        self.messages.clear()
        self.agent_states.clear()
        self.temp_vars.clear()
        self.version += 1

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "turn_id": self.turn_id,
            "messages": [m.to_dict() for m in self.messages],
            "agent_states": {k: v.to_dict() for k, v in self.agent_states.items()},
            "temp_vars": self.temp_vars,
            "start_time": self.start_time,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkingContext":
        """从字典创建"""
        context = cls(
            turn_id=data.get("turn_id", str(uuid.uuid4())),
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            agent_states={
                k: AgentState(**v) for k, v in data.get("agent_states", {}).items()
            },
            temp_vars=data.get("temp_vars", {}),
            start_time=data.get("start_time", time.time()),
            version=data.get("version", 0),
        )
        return context

    @property
    def elapsed_time(self) -> float:
        """获取已经过的时间（秒）"""
        return time.time() - self.start_time

    @property
    def message_count(self) -> int:
        """获取消息数量"""
        return len(self.messages)

    def get_last_user_message(self) -> Optional[Message]:
        """获取最后一条用户消息"""
        for message in reversed(self.messages):
            if message.role == "user":
                return message
        return None

    def get_last_assistant_message(self) -> Optional[Message]:
        """获取最后一条助手消息"""
        for message in reversed(self.messages):
            if message.role in ("assistant", "talker", "thinker"):
                return message
        return None
