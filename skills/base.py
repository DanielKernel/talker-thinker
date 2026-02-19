"""
Skill基类定义
"""
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SkillMetadata:
    """Skill元数据"""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = "unknown"
    latency_target_ms: int = 1000
    max_retries: int = 3
    timeout_ms: int = 30000
    requires_api_key: bool = False
    required_params: List[str] = field(default_factory=list)
    group: str = "general"
    tags: List[str] = field(default_factory=list)


@dataclass
class SkillResult:
    """Skill执行结果"""
    success: bool
    data: Any = None
    formatted: str = ""
    error: Optional[str] = None
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "formatted": self.formatted,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "metadata": self.metadata,
        }


class Skill(ABC):
    """
    Skill基类
    所有技能都应该继承此类
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.metadata = self._build_metadata()
        self._start_time: float = 0

    @property
    @abstractmethod
    def name(self) -> str:
        """Skill名称"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Skill描述"""
        pass

    def _build_metadata(self) -> SkillMetadata:
        """构建元数据"""
        return SkillMetadata(
            name=self.name,
            description=self.description,
            version=self.config.get("version", "1.0.0"),
            author=self.config.get("author", "unknown"),
            latency_target_ms=self.config.get("latency_target_ms", 1000),
            max_retries=self.config.get("max_retries", 3),
            timeout_ms=self.config.get("timeout_ms", 30000),
            requires_api_key=self.config.get("requires_api_key", False),
            required_params=self.config.get("required_params", []),
            group=self.config.get("group", "general"),
            tags=self.config.get("tags", []),
        )

    @abstractmethod
    async def execute(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        """
        执行Skill

        Args:
            params: 执行参数
            context: 执行上下文

        Returns:
            SkillResult: 执行结果
        """
        pass

    async def validate_params(self, params: Dict[str, Any]) -> bool:
        """
        验证参数

        Args:
            params: 要验证的参数

        Returns:
            bool: 参数是否有效

        Raises:
            ValueError: 参数无效时抛出
        """
        required = self.metadata.required_params
        missing = [p for p in required if p not in params]
        if missing:
            raise ValueError(f"Missing required parameters: {missing}")
        return True

    def get_schema(self) -> Dict[str, Any]:
        """
        获取参数schema

        Returns:
            Dict: JSON Schema格式的参数定义
        """
        param_descriptions = self._get_param_descriptions()
        return {
            "type": "object",
            "properties": {
                param: {
                    "type": param_type,
                    "description": description,
                }
                for param, param_type, description in param_descriptions
            },
            "required": self.metadata.required_params,
        }

    def _get_param_descriptions(self) -> List[tuple]:
        """
        获取参数描述
        子类应该重写此方法

        Returns:
            List[tuple]: [(param_name, param_type, description), ...]
        """
        return []

    def _start_timer(self) -> None:
        """开始计时"""
        self._start_time = time.time()

    def _get_elapsed_time(self) -> float:
        """获取已经过的时间（毫秒）"""
        return (time.time() - self._start_time) * 1000

    def _create_success_result(
        self,
        data: Any,
        formatted: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        """创建成功结果"""
        return SkillResult(
            success=True,
            data=data,
            formatted=formatted or str(data),
            latency_ms=self._get_elapsed_time(),
            metadata=metadata or {},
        )

    def _create_error_result(
        self,
        error: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        """创建错误结果"""
        return SkillResult(
            success=False,
            error=error,
            latency_ms=self._get_elapsed_time(),
            metadata=metadata or {},
        )

    def __repr__(self) -> str:
        return f"Skill(name={self.name}, description={self.description})"
