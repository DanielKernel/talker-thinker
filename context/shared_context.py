"""
Shared Context - Talker和Thinker共享的上下文
实现双向信息流，支持边交互边澄清
"""
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class ClarificationStatus(Enum):
    """澄清状态"""
    NONE = "none"                    # 无需澄清
    PENDING = "pending"              # 等待澄清
    ANSWERED = "answered"            # 已回答
    TIMEOUT = "timeout"              # 超时


@dataclass
class ClarificationRequest:
    """澄清请求"""
    question: str                           # 问题内容
    reason: str                             # 为什么需要澄清
    options: List[str] = field(default_factory=list)  # 可选答案
    created_at: float = field(default_factory=time.time)
    status: ClarificationStatus = ClarificationStatus.PENDING
    answer: Optional[str] = None            # 用户的回答
    answered_at: Optional[float] = None


@dataclass
class ThinkerProgress:
    """Thinker进度信息"""
    current_stage: str = "idle"             # 当前阶段
    current_step: int = 0                   # 当前步骤号
    total_steps: int = 0                    # 总步骤数
    partial_results: List[str] = field(default_factory=list)  # 中间结果
    started_at: float = field(default_factory=time.time)
    last_update: float = field(default_factory=time.time)

    def update(self, stage: str = None, step: int = None, total: int = None, result: str = None):
        """更新进度"""
        if stage:
            self.current_stage = stage
        if step is not None:
            self.current_step = step
        if total is not None:
            self.total_steps = total
        if result:
            self.partial_results.append(result)
        self.last_update = time.time()

    def get_progress_percent(self) -> float:
        """获取进度百分比"""
        if self.total_steps == 0:
            return 0.0
        return (self.current_step / self.total_steps) * 100


@dataclass
class TalkerInteraction:
    """Talker与用户的交互记录"""
    content: str                            # 交互内容
    interaction_type: str                   # 类型: broadcast/clarification/response
    created_at: float = field(default_factory=time.time)


@dataclass
class SharedContext:
    """
    Talker和Thinker共享的上下文

    实现双向信息流：
    - Talker → Thinker: 用户澄清、情绪反馈、新信息
    - Thinker → Talker: 处理进度、澄清请求、中间结果
    """

    # === 用户信息 ===
    user_input: str = ""                    # 原始问题
    user_id: Optional[str] = None           # 用户ID
    user_emotion: str = "neutral"           # 用户情绪：neutral/positive/negative/complaint

    # === 澄清相关 ===
    clarification_requests: List[ClarificationRequest] = field(default_factory=list)
    clarification_status: ClarificationStatus = ClarificationStatus.NONE

    # === Thinker进度 ===
    thinker_progress: ThinkerProgress = field(default_factory=ThinkerProgress)

    # === Talker交互 ===
    talker_interactions: List[TalkerInteraction] = field(default_factory=list)

    # === 融合信息 ===
    clarified_intent: str = ""              # 澄清后的意图
    extracted_entities: Dict[str, Any] = field(default_factory=dict)  # 提取的实体
    constraints: List[str] = field(default_factory=list)               # 约束条件
    user_preferences: Dict[str, Any] = field(default_factory=dict)     # 用户偏好

    # === 状态标记 ===
    is_processing: bool = False             # 是否正在处理
    is_paused: bool = False                 # 是否暂停
    is_cancelled: bool = False              # 是否取消

    # === 辅助方法 ===

    def needs_clarification(self) -> bool:
        """是否需要澄清"""
        return self.clarification_status == ClarificationStatus.PENDING

    def add_clarification_request(
        self,
        question: str,
        reason: str = "",
        options: List[str] = None
    ) -> ClarificationRequest:
        """添加澄清请求"""
        request = ClarificationRequest(
            question=question,
            reason=reason,
            options=options or [],
        )
        self.clarification_requests.append(request)
        self.clarification_status = ClarificationStatus.PENDING
        return request

    def answer_clarification(self, answer: str) -> bool:
        """回答澄清问题"""
        if not self.clarification_requests:
            return False

        # 找到最近的待回答问题
        for request in reversed(self.clarification_requests):
            if request.status == ClarificationStatus.PENDING:
                request.answer = answer
                request.status = ClarificationStatus.ANSWERED
                request.answered_at = time.time()
                self.clarification_status = ClarificationStatus.ANSWERED
                return True
        return False

    def get_pending_clarification(self) -> Optional[ClarificationRequest]:
        """获取待回答的澄清问题"""
        for request in self.clarification_requests:
            if request.status == ClarificationStatus.PENDING:
                return request
        return None

    def update_thinker_progress(
        self,
        stage: str = None,
        step: int = None,
        total: int = None,
        result: str = None
    ):
        """更新Thinker进度"""
        self.thinker_progress.update(stage, step, total, result)

    def add_talker_interaction(self, content: str, interaction_type: str = "broadcast"):
        """记录Talker交互"""
        self.talker_interactions.append(TalkerInteraction(
            content=content,
            interaction_type=interaction_type,
        ))

    def update_intent_with_clarification(self, new_info: str):
        """根据澄清信息更新意图"""
        if self.clarified_intent:
            self.clarified_intent = f"{self.clarified_intent}。补充信息：{new_info}"
        else:
            self.clarified_intent = f"{self.user_input}。补充信息：{new_info}"

    def add_entity(self, key: str, value: Any):
        """添加实体"""
        self.extracted_entities[key] = value

    def add_constraint(self, constraint: str):
        """添加约束"""
        if constraint not in self.constraints:
            self.constraints.append(constraint)


    def set_user_emotion(self, emotion: str):
        """设置用户情绪"""
        self.user_emotion = emotion

    def get_user_emotion(self) -> str:
        """获取用户情绪"""
        return self.user_emotion
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "user_input": self.user_input,
            "user_id": self.user_id,
            "clarified_intent": self.clarified_intent,
            "extracted_entities": self.extracted_entities,
            "constraints": self.constraints,
            "user_preferences": self.user_preferences,
            "clarification_status": self.clarification_status.value,
            "clarification_requests": [
                {
                    "question": r.question,
                    "answer": r.answer,
                    "status": r.status.value,
                }
                for r in self.clarification_requests
            ],
            "thinker_progress": {
                "stage": self.thinker_progress.current_stage,
                "step": self.thinker_progress.current_step,
                "total": self.thinker_progress.total_steps,
                "percent": self.thinker_progress.get_progress_percent(),
            },
            "is_processing": self.is_processing,
            "is_paused": self.is_paused,
            "is_cancelled": self.is_cancelled,
        }
