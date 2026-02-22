"""
简单任务评测用例集 (Simple)

测试 Talker Agent 快速响应简单任务的能力
"""
from context.types import AgentRole, TaskComplexity
from ..core.types import Assertion, EvalCase, EvalCategory, Priority


def _check_response_time(actual: float, threshold: float = 500.0) -> bool:
    """检查响应时间"""
    return actual <= threshold


def _check_agent_routing(actual: AgentRole, expected: AgentRole) -> bool:
    """检查 Agent 路由"""
    return actual == expected


def _check_contains_keyword(actual_output: str, keyword: str) -> bool:
    """检查输出是否包含关键词"""
    return keyword.lower() in actual_output.lower()


def _check_is_greeting(actual_output: str) -> bool:
    """检查是否为问候语"""
    greetings = ["你好", "您好", "hello", "hi", "hey", "早上好", "晚上好"]
    return any(g in actual_output.lower() for g in greetings)


def _check_math_result(actual_output: str, expected_answer: str) -> bool:
    """检查数学计算结果"""
    return expected_answer in actual_output


# =============================================================================
# 简单任务用例集
# =============================================================================

SIMPLE_CASES = [
    # S001: 问候
    EvalCase(
        case_id="S001",
        name="greeting",
        description="测试基本问候响应",
        category=EvalCategory.SIMPLE,
        user_input="你好",
        expected_complexity=TaskComplexity.SIMPLE,
        expected_agent=AgentRole.TALKER,
        assertions=[
            Assertion(
                name="response_time_check",
                checker=lambda response_time_ms, **_: _check_response_time(response_time_ms, threshold=300),
                weight=1.0,
                failure_reason_template="响应时间超过 300ms",
                description="响应时间应小于 300ms",
            ),
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.0,
                failure_reason_template="路由错误：期望 {expected_agent}，实际 {actual_agent}",
                description="应由 Talker 处理",
            ),
            Assertion(
                name="is_greeting_check",
                checker=lambda actual_output, **_: _check_is_greeting(actual_output),
                weight=1.0,
                failure_reason_template="输出不是有效的问候语",
                description="输出应为问候语",
            ),
        ],
        golden_output=None,
        priority=Priority.CRITICAL,
        tags=["greeting", "basic"],
    ),

    # S002: 简单计算
    EvalCase(
        case_id="S002",
        name="simple_calculation",
        description="测试简单数学计算",
        category=EvalCategory.SIMPLE,
        user_input="1+1 等于几？",
        expected_complexity=TaskComplexity.SIMPLE,
        expected_agent=AgentRole.TALKER,
        assertions=[
            Assertion(
                name="response_time_check",
                checker=lambda response_time_ms, **_: _check_response_time(response_time_ms, threshold=500),
                weight=1.0,
                failure_reason_template="响应时间超过 500ms",
                description="响应时间应小于 500ms",
            ),
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.0,
                failure_reason_template="路由错误",
                description="应由 Talker 处理",
            ),
            Assertion(
                name="math_result_check",
                checker=lambda actual_output, **_: _check_math_result(actual_output, "2"),
                weight=1.0,
                failure_reason_template="计算结果错误，应包含 2",
                description="计算结果应为 2",
            ),
        ],
        golden_output="1+1 等于 2",
        priority=Priority.CRITICAL,
        tags=["math", "calculation"],
    ),

    # S003: 时间查询
    EvalCase(
        case_id="S003",
        name="time_query",
        description="测试时间查询",
        category=EvalCategory.SIMPLE,
        user_input="现在几点了？",
        expected_complexity=TaskComplexity.SIMPLE,
        expected_agent=AgentRole.TALKER,
        assertions=[
            Assertion(
                name="response_time_check",
                checker=lambda response_time_ms, **_: _check_response_time(response_time_ms, threshold=500),
                weight=1.0,
                failure_reason_template="响应时间超过 500ms",
                description="响应时间应小于 500ms",
            ),
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.0,
                failure_reason_template="路由错误",
                description="应由 Talker 处理",
            ),
            Assertion(
                name="contains_time_info",
                checker=lambda actual_output, **_: any(k in actual_output for k in ["点", "时", ":", "当前", "现在"]),
                weight=1.0,
                failure_reason_template="输出不包含时间信息",
                description="输出应包含时间信息",
            ),
        ],
        golden_output=None,
        priority=Priority.HIGH,
        tags=["time", "query"],
    ),

    # S004: 记忆 recall
    EvalCase(
        case_id="S004",
        name="memory_recall",
        description="测试历史记忆召回",
        category=EvalCategory.SIMPLE,
        user_input="我之前说过什么？",
        expected_complexity=TaskComplexity.SIMPLE,
        expected_agent=AgentRole.TALKER,
        assertions=[
            Assertion(
                name="response_time_check",
                checker=lambda response_time_ms, **_: _check_response_time(response_time_ms, threshold=500),
                weight=1.0,
                failure_reason_template="响应时间超过 500ms",
                description="响应时间应小于 500ms",
            ),
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.0,
                failure_reason_template="路由错误",
                description="应由 Talker 处理",
            ),
        ],
        golden_output=None,
        priority=Priority.NORMAL,
        tags=["memory", "recall"],
        context_messages=[
            {"role": "user", "content": "我喜欢吃苹果"},
            {"role": "assistant", "content": "好的，我记住了你喜欢吃苹果"},
        ],
    ),

    # S005: 自我介绍
    EvalCase(
        case_id="S005",
        name="self_introduction",
        description="测试自我介绍响应",
        category=EvalCategory.SIMPLE,
        user_input="你是谁？",
        expected_complexity=TaskComplexity.SIMPLE,
        expected_agent=AgentRole.TALKER,
        assertions=[
            Assertion(
                name="response_time_check",
                checker=lambda response_time_ms, **_: _check_response_time(response_time_ms, threshold=500),
                weight=1.0,
                failure_reason_template="响应时间超过 500ms",
                description="响应时间应小于 500ms",
            ),
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.0,
                failure_reason_template="路由错误",
                description="应由 Talker 处理",
            ),
        ],
        golden_output=None,
        priority=Priority.NORMAL,
        tags=["identity", "basic"],
    ),

    # S006: 感谢
    EvalCase(
        case_id="S006",
        name="gratitude",
        description="测试感谢回应",
        category=EvalCategory.SIMPLE,
        user_input="谢谢",
        expected_complexity=TaskComplexity.SIMPLE,
        expected_agent=AgentRole.TALKER,
        assertions=[
            Assertion(
                name="response_time_check",
                checker=lambda response_time_ms, **_: _check_response_time(response_time_ms, threshold=300),
                weight=1.0,
                failure_reason_template="响应时间超过 300ms",
                description="响应时间应小于 300ms",
            ),
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.0,
                failure_reason_template="路由错误",
                description="应由 Talker 处理",
            ),
        ],
        golden_output=None,
        priority=Priority.NORMAL,
        tags=["social", "basic"],
    ),
]


def get_cases() -> list:
    """获取简单任务评测用例"""
    return SIMPLE_CASES
