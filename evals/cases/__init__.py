"""
评测用例集模块
"""
from typing import List

from ..core.types import EvalCase, EvalCategory


def get_all_cases() -> List[EvalCase]:
    """获取所有评测用例"""
    from . import simple, medium, complex, edge

    cases = []
    cases.extend(simple.get_cases())
    cases.extend(medium.get_cases())
    cases.extend(complex.get_cases())
    cases.extend(edge.get_cases())

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

    return []


__all__ = ["get_all_cases", "get_cases_by_category"]
