"""
评测用例集模块

支持的用例类别:
- simple: 简单任务
- medium: 中等任务
- complex: 复杂任务
- edge: 边界/异常
- conversation: 对话场景
- ux_quality: 用户体验质量
"""
from typing import List

from ..core.types import EvalCase, EvalCategory


def get_all_cases() -> List[EvalCase]:
    """获取所有评测用例"""
    from . import simple, medium, complex, edge, conversation, ux_quality

    cases = []
    cases.extend(simple.get_cases())
    cases.extend(medium.get_cases())
    cases.extend(complex.get_cases())
    cases.extend(edge.get_cases())
    cases.extend(conversation.get_cases())
    cases.extend(ux_quality.get_cases())

    return cases


def get_cases_by_category(category: EvalCategory) -> List[EvalCase]:
    """按类别获取评测用例"""
    if category == EvalCategory.SIMPLE:
        from . import simple
        return simple.get_cases()
    elif category == EvalCategory.MEDIUM:
        from . import medium
        return medium.get_cases()
    elif category == EvalCategory.COMPLEX:
        from . import complex
        return complex.get_cases()
    elif category == EvalCategory.EDGE:
        from . import edge
        return edge.get_cases()
    elif category == "conversation":
        from . import conversation
        return conversation.get_cases()
    elif category == "ux_quality":
        from . import ux_quality
        return ux_quality.get_cases()

    return []


__all__ = ["get_all_cases", "get_cases_by_category"]
