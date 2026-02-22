"""
复杂任务评测用例集 (Complex)

测试 Thinker Agent 深度推理和任务规划能力
"""
from context.types import AgentRole, TaskComplexity
from ..core.types import Assertion, EvalCase, EvalCategory, Priority


def _check_response_time(actual: float, threshold: float = 5000.0) -> bool:
    """检查响应时间 (复杂任务允许更长时间)"""
    return actual <= threshold


def _check_agent_routing(actual: AgentRole, expected: AgentRole) -> bool:
    """检查 Agent 路由"""
    return actual == expected


def _check_output_length(actual_output: str, min_length: int = 200) -> bool:
    """检查输出长度 (复杂任务应有较长输出)"""
    return len(actual_output) >= min_length


def _check_has_structure(actual_output: str) -> bool:
    """检查输出是否有结构 (如编号、列表等)"""
    import re
    # 检查是否有编号列表或项目符号
    has_numbering = bool(re.search(r'\d+[\.、)]', actual_output))
    has_bullets = bool(re.search(r'[-•*]\s', actual_output))
    has_sections = bool(re.search(r'##|###|\*\*|\n\n', actual_output))
    return has_numbering or has_bullets or has_sections


def _check_has_reasoning(actual_output: str) -> bool:
    """检查是否包含推理过程"""
    reasoning_markers = ["因为", "所以", "因此", "由于", "考虑到", "分析", "首先", "其次", "最后"]
    return any(marker in actual_output for marker in reasoning_markers)


# =============================================================================
# 复杂任务用例集
# =============================================================================

COMPLEX_CASES = [
    # C001: 深度分析
    EvalCase(
        case_id="C001",
        name="deep_analysis",
        description="测试 AI 发展趋势的深度分析能力",
        category=EvalCategory.COMPLEX,
        user_input="请分析 AI 技术的发展趋势和未来展望",
        expected_complexity=TaskComplexity.COMPLEX,
        expected_agent=AgentRole.THINKER,
        assertions=[
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.5,
                failure_reason_template="路由错误：复杂分析任务应由 Thinker 处理",
                description="应由 Thinker 处理",
            ),
            Assertion(
                name="output_length_check",
                checker=lambda actual_output, **_: _check_output_length(actual_output, min_length=300),
                weight=1.0,
                failure_reason_template="输出过短，无法构成深度分析",
                description="输出长度应至少 300 字",
            ),
            Assertion(
                name="structure_check",
                checker=lambda actual_output, **_: _check_has_structure(actual_output),
                weight=1.0,
                failure_reason_template="输出缺乏结构化组织",
                description="输出应有清晰的结构",
            ),
            Assertion(
                name="reasoning_check",
                checker=lambda actual_output, **_: _check_has_reasoning(actual_output),
                weight=1.0,
                failure_reason_template="输出缺乏推理过程",
                description="输出应包含推理过程",
            ),
        ],
        golden_output=None,
        priority=Priority.CRITICAL,
        tags=["analysis", "ai", "trends"],
    ),

    # C002: 多步任务 - 产品对比
    EvalCase(
        case_id="C002",
        name="product_comparison",
        description="测试多步对比和推荐能力",
        category=EvalCategory.COMPLEX,
        user_input="请对比 iPhone 15、Samsung Galaxy S24 和 Google Pixel 8，并给出购买建议",
        expected_complexity=TaskComplexity.COMPLEX,
        expected_agent=AgentRole.THINKER,
        assertions=[
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.5,
                failure_reason_template="路由错误：复杂对比任务应由 Thinker 处理",
                description="应由 Thinker 处理",
            ),
            Assertion(
                name="output_length_check",
                checker=lambda actual_output, **_: _check_output_length(actual_output, min_length=400),
                weight=1.0,
                failure_reason_template="输出过短，无法构成完整对比",
                description="输出长度应至少 400 字",
            ),
            Assertion(
                name="mentions_all_products",
                checker=lambda actual_output, **_: all(p in actual_output.lower() for p in ["iphone", "samsung", "pixel"]),
                weight=1.0,
                failure_reason_template="未对比所有三款产品",
                description="应对比所有三款产品",
            ),
            Assertion(
                name="has_recommendation",
                checker=lambda actual_output, **_: any(k in actual_output for k in ["推荐", "建议", "值得", "选择"]),
                weight=1.0,
                failure_reason_template="缺少购买建议",
                description="应给出购买建议",
            ),
        ],
        golden_output=None,
        priority=Priority.CRITICAL,
        tags=["comparison", "product", "recommendation"],
    ),

    # C003: 方案规划 - 旅行计划
    EvalCase(
        case_id="C003",
        name="travel_planning",
        description="测试旅行计划规划能力",
        category=EvalCategory.COMPLEX,
        user_input="帮我规划一个 5 天的日本东京旅行计划，包括景点、美食和住宿建议",
        expected_complexity=TaskComplexity.COMPLEX,
        expected_agent=AgentRole.THINKER,
        assertions=[
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.5,
                failure_reason_template="路由错误：复杂规划任务应由 Thinker 处理",
                description="应由 Thinker 处理",
            ),
            Assertion(
                name="output_length_check",
                checker=lambda actual_output, **_: _check_output_length(actual_output, min_length=500),
                weight=1.0,
                failure_reason_template="输出过短，无法构成完整计划",
                description="输出长度应至少 500 字",
            ),
            Assertion(
                name="covers_all_aspects",
                checker=lambda actual_output, **_: all(k in actual_output for k in ["景点", "美食", "住宿"]),
                weight=1.0,
                failure_reason_template="计划未覆盖所有要求的方面",
                description="计划应覆盖景点、美食、住宿",
            ),
            Assertion(
                name="has_daily_plan",
                checker=lambda actual_output, **_: any(f"第{n}天" in actual_output or f"day {n}" in actual_output.lower() for n in range(1, 6)),
                weight=1.0,
                failure_reason_template="缺少每日计划安排",
                description="应有每日计划安排",
            ),
        ],
        golden_output=None,
        priority=Priority.HIGH,
        tags=["planning", "travel", "multi-step"],
    ),

    # C004: 问题排查
    EvalCase(
        case_id="C004",
        name="debugging_analysis",
        description="测试代码问题分析和排查能力",
        category=EvalCategory.COMPLEX,
        user_input="我的 Python 程序运行时报错'TypeError: 'int' object is not iterable'，可能是什么原因？如何修复？",
        expected_complexity=TaskComplexity.COMPLEX,
        expected_agent=AgentRole.THINKER,
        assertions=[
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.5,
                failure_reason_template="路由错误：复杂分析问题应由 Thinker 处理",
                description="应由 Thinker 处理",
            ),
            Assertion(
                name="output_length_check",
                checker=lambda actual_output, **_: _check_output_length(actual_output, min_length=200),
                weight=1.0,
                failure_reason_template="输出过短，无法构成完整分析",
                description="输出长度应至少 200 字",
            ),
            Assertion(
                name="explains_error_cause",
                checker=lambda actual_output, **_: any(k in actual_output for k in ["原因", "因为", "导致", "可能"]),
                weight=1.0,
                failure_reason_template="未解释错误原因",
                description="应解释错误原因",
            ),
            Assertion(
                name="provides_solution",
                checker=lambda actual_output, **_: any(k in actual_output for k in ["修复", "解决", "方法", "尝试", "代码"]),
                weight=1.0,
                failure_reason_template="未提供解决方案",
                description="应提供解决方案",
            ),
        ],
        golden_output=None,
        priority=Priority.HIGH,
        tags=["debugging", "programming", "analysis"],
    ),

    # C005: 方案设计
    EvalCase(
        case_id="C005",
        name="system_design",
        description="测试系统方案设计能力",
        category=EvalCategory.COMPLEX,
        user_input="设计一个支持高并发的短 URL 生成系统，需要考虑哪些关键点？",
        expected_complexity=TaskComplexity.COMPLEX,
        expected_agent=AgentRole.THINKER,
        assertions=[
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.5,
                failure_reason_template="路由错误：系统设计任务应由 Thinker 处理",
                description="应由 Thinker 处理",
            ),
            Assertion(
                name="output_length_check",
                checker=lambda actual_output, **_: _check_output_length(actual_output, min_length=400),
                weight=1.0,
                failure_reason_template="输出过短，无法构成完整设计",
                description="输出长度应至少 400 字",
            ),
            Assertion(
                name="mentions_key_concepts",
                checker=lambda actual_output, **_: any(k in actual_output for k in ["并发", "数据库", "缓存", "分布式", "ID", "hash"]),
                weight=1.0,
                failure_reason_template="未涉及关键技术概念",
                description="应涉及关键技术概念",
            ),
            Assertion(
                name="has_structure",
                checker=lambda actual_output, **_: _check_has_structure(actual_output),
                weight=1.0,
                failure_reason_template="输出缺乏结构化组织",
                description="输出应有清晰的结构",
            ),
        ],
        golden_output=None,
        priority=Priority.HIGH,
        tags=["design", "system", "architecture"],
    ),

    # C006: 学术写作
    EvalCase(
        case_id="C006",
        name="academic_writing",
        description="测试学术写作能力",
        category=EvalCategory.COMPLEX,
        user_input="请写一篇关于机器学习在医疗诊断中应用的简短综述，包括摘要、方法和结论",
        expected_complexity=TaskComplexity.COMPLEX,
        expected_agent=AgentRole.THINKER,
        assertions=[
            Assertion(
                name="agent_routing_check",
                checker=lambda actual_agent, expected_agent, **_: actual_agent == expected_agent,
                weight=1.5,
                failure_reason_template="路由错误：学术写作任务应由 Thinker 处理",
                description="应由 Thinker 处理",
            ),
            Assertion(
                name="output_length_check",
                checker=lambda actual_output, **_: _check_output_length(actual_output, min_length=500),
                weight=1.0,
                failure_reason_template="输出过短，无法构成完整综述",
                description="输出长度应至少 500 字",
            ),
            Assertion(
                name="has_required_sections",
                checker=lambda actual_output, **_: all(k in actual_output for k in ["摘要", "方法", "结论"]),
                weight=1.0,
                failure_reason_template="缺少必要的章节",
                description="应包含摘要、方法、结论",
            ),
        ],
        golden_output=None,
        priority=Priority.NORMAL,
        tags=["writing", "academic", "healthcare"],
    ),
]


def get_cases() -> list:
    """获取复杂任务评测用例"""
    return COMPLEX_CASES
