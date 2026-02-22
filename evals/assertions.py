"""
断言检查器模块

提供通用的断言检查函数
"""
import re
from typing import Any, Callable, Dict, List, Optional

from context.types import AgentRole, TaskComplexity
from .core.types import Assertion, AssertionResult, FailureReason


# =============================================================================
# 响应时间检查
# =============================================================================

def check_response_time(
    actual: float,
    threshold: float = 500.0,
    **kwargs,
) -> bool:
    """
    检查响应时间是否在阈值内

    Args:
        actual: 实际响应时间 (ms)
        threshold: 阈值 (ms)

    Returns:
        bool: 是否在阈值内
    """
    return actual <= threshold


def check_ttft(
    ttft: float,
    threshold: float = 200.0,
    **kwargs,
) -> bool:
    """
    检查首 token 时间

    Args:
        ttft: 首 token 时间 (ms)
        threshold: 阈值 (ms)

    Returns:
        bool: 是否在阈值内
    """
    return ttft <= threshold


# =============================================================================
# Agent 路由检查
# =============================================================================

def check_agent_routing(
    actual: AgentRole,
    expected: AgentRole,
    **kwargs,
) -> bool:
    """
    检查 Agent 路由是否正确

    Args:
        actual: 实际分配的 Agent
        expected: 期望分配的 Agent

    Returns:
        bool: 是否匹配
    """
    return actual == expected


def check_complexity_classification(
    actual: TaskComplexity,
    expected: TaskComplexity,
    **kwargs,
) -> bool:
    """
    检查复杂度分类是否正确

    Args:
        actual: 实际复杂度
        expected: 期望复杂度

    Returns:
        bool: 是否匹配
    """
    return actual == expected


# =============================================================================
# 输出内容检查
# =============================================================================

def check_contains_keyword(
    actual_output: str,
    keyword: str,
    case_insensitive: bool = True,
    **kwargs,
) -> bool:
    """
    检查输出是否包含关键词

    Args:
        actual_output: 实际输出
        keyword: 关键词
        case_insensitive: 是否忽略大小写

    Returns:
        bool: 是否包含
    """
    if case_insensitive:
        return keyword.lower() in actual_output.lower()
    return keyword in actual_output


def check_contains_all_keywords(
    actual_output: str,
    keywords: List[str],
    case_insensitive: bool = True,
    **kwargs,
) -> bool:
    """
    检查输出是否包含所有关键词

    Args:
        actual_output: 实际输出
        keywords: 关键词列表
        case_insensitive: 是否忽略大小写

    Returns:
        bool: 是否包含所有关键词
    """
    for keyword in keywords:
        if not check_contains_keyword(actual_output, keyword, case_insensitive):
            return False
    return True


def check_contains_any_keyword(
    actual_output: str,
    keywords: List[str],
    case_insensitive: bool = True,
    **kwargs,
) -> bool:
    """
    检查输出是否包含任一关键词

    Args:
        actual_output: 实际输出
        keywords: 关键词列表
        case_insensitive: 是否忽略大小写

    Returns:
        bool: 是否包含任一关键词
    """
    for keyword in keywords:
        if check_contains_keyword(actual_output, keyword, case_insensitive):
            return True
    return False


def check_regex_match(
    actual_output: str,
    pattern: str,
    **kwargs,
) -> bool:
    """
    检查输出是否匹配正则表达式

    Args:
        actual_output: 实际输出
        pattern: 正则表达式

    Returns:
        bool: 是否匹配
    """
    return bool(re.search(pattern, actual_output))


def check_output_length(
    actual_output: str,
    min_length: int = 0,
    max_length: int = float('inf'),
    **kwargs,
) -> bool:
    """
    检查输出长度

    Args:
        actual_output: 实际输出
        min_length: 最小长度
        max_length: 最大长度

    Returns:
        bool: 是否在长度范围内
    """
    return min_length <= len(actual_output) <= max_length


def check_not_contains(
    actual_output: str,
    forbidden_words: List[str],
    case_insensitive: bool = True,
    **kwargs,
) -> bool:
    """
    检查输出不包含禁用词

    Args:
        actual_output: 实际输出
        forbidden_words: 禁用词列表
        case_insensitive: 是否忽略大小写

    Returns:
        bool: 是否不包含禁用词
    """
    for word in forbidden_words:
        if check_contains_keyword(actual_output, word, case_insensitive):
            return False
    return True


# =============================================================================
# 特殊检查
# =============================================================================

def check_is_greeting(
    actual_output: str,
    **kwargs,
) -> bool:
    """
    检查是否为问候语

    Args:
        actual_output: 实际输出

    Returns:
        bool: 是否为问候语
    """
    greetings = ["你好", "您好", "hello", "hi", "hey", "早上好", "晚上好", "早安", "晚安"]
    return any(g in actual_output.lower() for g in greetings)


def check_is_question(
    actual_output: str,
    **kwargs,
) -> bool:
    """
    检查是否为问句

    Args:
        actual_output: 实际输出

    Returns:
        bool: 是否为问句
    """
    question_markers = ["？", "?", "吗", "什么", "如何", "怎样", "哪里", "何时", "为什么"]
    return any(m in actual_output for m in question_markers)


def check_requests_clarification(
    actual_output: str,
    **kwargs,
) -> bool:
    """
    检查是否请求澄清

    Args:
        actual_output: 实际输出

    Returns:
        bool: 是否请求澄清
    """
    clarification_markers = ["请问", "能否", "具体", "哪", "什么", "可以", "请", "意思"]
    question_markers = ["？", "?", "吗"]

    has_question = any(m in actual_output for m in question_markers)
    has_clarification = any(m in actual_output for m in clarification_markers)

    return has_question or has_clarification


def check_graceful_handling(
    actual_output: str,
    **kwargs,
) -> bool:
    """
    检查是否优雅处理 (有响应而非报错)

    Args:
        actual_output: 实际输出

    Returns:
        bool: 是否优雅处理
    """
    if not actual_output or len(actual_output.strip()) == 0:
        return False

    # 检查是否包含错误信息
    error_markers = ["错误", "Error", "异常", "Exception", "失败", "Failed"]
    # 但允许"出错了"这样的温和表达
    if actual_output.startswith("抱歉") or "抱歉" in actual_output[:20]:
        return True

    return not any(m in actual_output[:50] for m in error_markers)


def check_has_structure(
    actual_output: str,
    **kwargs,
) -> bool:
    """
    检查输出是否有结构

    Args:
        actual_output: 实际输出

    Returns:
        bool: 是否有结构
    """
    # 检查是否有编号列表或项目符号
    has_numbering = bool(re.search(r'\d+[\.、)]', actual_output))
    has_bullets = bool(re.search(r'[-•*]\s', actual_output))
    has_sections = bool(re.search(r'##|###|\*\*|\n\n', actual_output))
    return has_numbering or has_bullets or has_sections


def check_has_reasoning(
    actual_output: str,
    **kwargs,
) -> bool:
    """
    检查是否包含推理过程

    Args:
        actual_output: 实际输出

    Returns:
        bool: 是否包含推理过程
    """
    reasoning_markers = [
        "因为", "所以", "因此", "由于", "考虑到", "分析",
        "首先", "其次", "再次", "最后", "综上所述",
        "原因", "导致", "结果", "推断", "推测",
    ]
    return any(marker in actual_output for marker in reasoning_markers)


def check_math_result(
    actual_output: str,
    expected_answer: str,
    **kwargs,
) -> bool:
    """
    检查数学计算结果

    Args:
        actual_output: 实际输出
        expected_answer: 期望答案

    Returns:
        bool: 是否包含期望答案
    """
    return expected_answer in actual_output


def check_translation_accuracy(
    actual_output: str,
    expected_keywords: List[str],
    **kwargs,
) -> bool:
    """
    检查翻译准确性

    Args:
        actual_output: 实际输出
        expected_keywords: 期望包含的关键词

    Returns:
        bool: 是否包含所有关键词
    """
    return check_contains_all_keywords(actual_output, expected_keywords)


# =============================================================================
# 技能调用检查
# =============================================================================

def check_skill_invoked(
    skills_called: List[str],
    expected_skill: str,
    **kwargs,
) -> bool:
    """
    检查是否调用了指定技能

    Args:
        skills_called: 已调用的技能列表
        expected_skill: 期望调用的技能

    Returns:
        bool: 是否调用了指定技能
    """
    return expected_skill in skills_called


def check_skills_called(
    skills_called: List[str],
    expected_skills: List[str],
    **kwargs,
) -> bool:
    """
    检查是否调用了所有期望的技能

    Args:
        skills_called: 已调用的技能列表
        expected_skills: 期望调用的技能列表

    Returns:
        bool: 是否调用了所有期望的技能
    """
    return all(skill in skills_called for skill in expected_skills)


# =============================================================================
# 断言工厂函数
# =============================================================================

def create_assertion(
    name: str,
    checker_func: Callable,
    weight: float = 1.0,
    failure_reason: str = "",
    description: str = "",
    **checker_kwargs,
) -> Assertion:
    """
    创建断言

    Args:
        name: 断言名称
        checker_func: 检查函数
        weight: 权重
        failure_reason: 失败原因模板
        description: 断言描述
        **checker_kwargs: 检查函数的参数

    Returns:
        Assertion: 断言实例
    """
    # 创建闭包包装器
    def wrapper(**kwargs):
        merged_kwargs = {**kwargs, **checker_kwargs}
        return checker_func(**merged_kwargs)

    return Assertion(
        name=name,
        checker=wrapper,
        weight=weight,
        failure_reason_template=failure_reason,
        description=description,
    )
