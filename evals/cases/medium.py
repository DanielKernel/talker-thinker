"""
中等任务评测用例集 (Medium)

测试 Talker Agent 处理中等复杂度任务的能力
"""
from context.types import AgentRole, TaskComplexity
from ..core.types import Assertion, EvalCase, EvalCategory, Priority


def _check_response_time(actual: float, threshold: float = 1000.0) -> bool:
    """检查响应时间"""
    return actual <= threshold


def _check_agent_routing(actual: AgentRole, expected: AgentRole) -> bool:
    """检查 Agent 路由"""
    return actual == expected


def _check_contains_keyword(actual_output: str, keyword: str) -> bool:
    """检查输出是否包含关键词"""
    return keyword.lower() in actual_output.lower()


# =============================================================================
# 中等任务用例集
# =============================================================================

MEDIUM_CASES = [
    # M001: 天气查询
    EvalCase(
        case_id="M001",
        name="weather_query",
        description="测试天气查询能力",
        category=EvalCategory.MEDIUM,
        user_input="北京明天天气怎么样？",
        expected_complexity=TaskComplexity.MEDIUM,
        expected_agent=AgentRole.TALKER,
        assertions=[
            Assertion(
                name="response_time_check",
                checker=lambda response_time_ms, **_: _check_response_time(response_time_ms, threshold=1000),
                weight=1.0,
                failure_reason_template="响应时间超过 1000ms",
                description="响应时间应小于 1000ms",
            ),
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.0,
                failure_reason_template="路由错误",
                description="应由 Talker 处理",
            ),
            Assertion(
                name="contains_weather_info",
                checker=lambda actual_output, **_: any(k in actual_output for k in ["天气", "晴", "雨", "温度", "度", "阴"]),
                weight=1.0,
                failure_reason_template="输出不包含天气信息",
                description="输出应包含天气信息",
            ),
        ],
        golden_output=None,
        priority=Priority.HIGH,
        tags=["weather", "query"],
    ),

    # M002: 单位转换
    EvalCase(
        case_id="M002",
        name="unit_conversion",
        description="测试单位转换能力",
        category=EvalCategory.MEDIUM,
        user_input="100 公里等于多少英里？",
        expected_complexity=TaskComplexity.MEDIUM,
        expected_agent=AgentRole.TALKER,
        assertions=[
            Assertion(
                name="response_time_check",
                checker=lambda response_time_ms, **_: _check_response_time(response_time_ms, threshold=1000),
                weight=1.0,
                failure_reason_template="响应时间超过 1000ms",
                description="响应时间应小于 1000ms",
            ),
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.0,
                failure_reason_template="路由错误",
                description="应由 Talker 处理",
            ),
            Assertion(
                name="conversion_accuracy",
                checker=lambda actual_output, **_: "62" in actual_output or "62.1" in actual_output,
                weight=1.0,
                failure_reason_template="转换结果错误 (期望约 62 英里)",
                description="转换结果应约为 62 英里",
            ),
        ],
        golden_output="100 公里约等于 62.14 英里",
        priority=Priority.HIGH,
        tags=["conversion", "math"],
    ),

    # M003: 电影推荐
    EvalCase(
        case_id="M003",
        name="movie_recommendation",
        description="测试简单推荐能力",
        category=EvalCategory.MEDIUM,
        user_input="推荐一部电影",
        expected_complexity=TaskComplexity.MEDIUM,
        expected_agent=AgentRole.TALKER,
        assertions=[
            Assertion(
                name="response_time_check",
                checker=lambda response_time_ms, **_: _check_response_time(response_time_ms, threshold=1000),
                weight=1.0,
                failure_reason_template="响应时间超过 1000ms",
                description="响应时间应小于 1000ms",
            ),
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.0,
                failure_reason_template="路由错误",
                description="应由 Talker 处理",
            ),
            Assertion(
                name="has_recommendation",
                checker=lambda actual_output, **_: len(actual_output) > 20,
                weight=1.0,
                failure_reason_template="输出过短，无法构成有效推荐",
                description="输出应包含具体的电影推荐",
            ),
        ],
        golden_output=None,
        priority=Priority.NORMAL,
        tags=["recommendation", "entertainment"],
    ),

    # M004: 翻译请求
    EvalCase(
        case_id="M004",
        name="translation",
        description="测试简单翻译能力",
        category=EvalCategory.MEDIUM,
        user_input="把'你好，世界'翻译成英文",
        expected_complexity=TaskComplexity.MEDIUM,
        expected_agent=AgentRole.TALKER,
        assertions=[
            Assertion(
                name="response_time_check",
                checker=lambda response_time_ms, **_: _check_response_time(response_time_ms, threshold=1000),
                weight=1.0,
                failure_reason_template="响应时间超过 1000ms",
                description="响应时间应小于 1000ms",
            ),
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.0,
                failure_reason_template="路由错误",
                description="应由 Talker 处理",
            ),
            Assertion(
                name="translation_accuracy",
                checker=lambda actual_output, **_: "hello" in actual_output.lower() and "world" in actual_output.lower(),
                weight=1.0,
                failure_reason_template="翻译错误 (期望包含'Hello, World')",
                description="翻译应包含'Hello, World'",
            ),
        ],
        golden_output="Hello, World",
        priority=Priority.HIGH,
        tags=["translation", "language"],
    ),

    # M005: 定义解释
    EvalCase(
        case_id="M005",
        name="definition_explanation",
        description="测试概念解释能力",
        category=EvalCategory.MEDIUM,
        user_input="什么是人工智能？",
        expected_complexity=TaskComplexity.MEDIUM,
        expected_agent=AgentRole.TALKER,
        assertions=[
            Assertion(
                name="response_time_check",
                checker=lambda response_time_ms, **_: _check_response_time(response_time_ms, threshold=1500),
                weight=1.0,
                failure_reason_template="响应时间超过 1500ms",
                description="响应时间应小于 1500ms",
            ),
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.0,
                failure_reason_template="路由错误",
                description="应由 Talker 处理",
            ),
            Assertion(
                name="contains_ai_concepts",
                checker=lambda actual_output, **_: any(k in actual_output for k in ["智能", "机器", "学习", "计算机", "AI"]),
                weight=1.0,
                failure_reason_template="输出不包含 AI 相关概念",
                description="输出应包含 AI 相关概念",
            ),
        ],
        golden_output=None,
        priority=Priority.NORMAL,
        tags=["explanation", "knowledge"],
    ),

    # M006: 简单比较
    EvalCase(
        case_id="M006",
        name="simple_comparison",
        description="测试简单比较能力",
        category=EvalCategory.MEDIUM,
        user_input="Python 和 Java 有什么区别？",
        expected_complexity=TaskComplexity.MEDIUM,
        expected_agent=AgentRole.TALKER,
        assertions=[
            Assertion(
                name="response_time_check",
                checker=lambda response_time_ms, **_: _check_response_time(response_time_ms, threshold=1500),
                weight=1.0,
                failure_reason_template="响应时间超过 1500ms",
                description="响应时间应小于 1500ms",
            ),
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.0,
                failure_reason_template="路由错误",
                description="应由 Talker 处理",
            ),
            Assertion(
                name="mentions_both_languages",
                checker=lambda actual_output, **_: "python" in actual_output.lower() and "java" in actual_output.lower(),
                weight=1.0,
                failure_reason_template="输出未同时提及两种语言",
                description="输出应同时提及 Python 和 Java",
            ),
        ],
        golden_output=None,
        priority=Priority.NORMAL,
        tags=["comparison", "programming"],
    ),
]


def get_cases() -> list:
    """获取中等任务评测用例"""
    return MEDIUM_CASES
