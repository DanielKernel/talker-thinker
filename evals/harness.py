"""
评测执行引擎 (Evaluation Harness)

负责加载用例、执行评测、收集指标
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from context.types import AgentRole, TaskComplexity, Message, Task
from config import settings

from .core.types import (
    Assertion,
    AssertionResult,
    CaseResult,
    EvalCase,
    EvalCategory,
    EvalResult,
    FailureReason,
    Priority,
)
from .metrics.collector import MetricsCollector
from .cases import get_all_cases, get_cases_by_category

logger = logging.getLogger(__name__)


@dataclass
class MockLLMResponse:
    """Mock LLM 响应"""
    content: str
    latency_ms: float = 100.0
    tokens_used: int = 50


@dataclass
class EvalConfig:
    """评测配置"""
    # 是否使用 Mock LLM
    use_mock_llm: bool = True

    # Mock 响应配置
    mock_response_latency_ms: float = 100.0
    mock_talker_latency_ms: float = 150.0
    mock_thinker_latency_ms: float = 2000.0

    # 超时配置
    case_timeout_seconds: float = 60.0

    # 是否启用进度输出
    show_progress: bool = True

    # 用例过滤器
    category_filter: Optional[EvalCategory] = None
    priority_filter: Optional[Priority] = None
    case_id_filter: Optional[List[str]] = None  # 指定运行某些用例 ID


class MockTalkerAgent:
    """Mock Talker Agent 用于评测"""

    def __init__(self, latency_ms: float = 150.0):
        self.latency_ms = latency_ms
        self.call_count = 0

    async def process(
        self,
        user_input: str,
        context_messages: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> Tuple[str, float, int]:
        """
        模拟 Talker 处理

        Returns:
            Tuple[content, latency_ms, tokens_used]
        """
        self.call_count += 1
        await asyncio.sleep(self.latency_ms / 1000)

        # 根据输入生成简单的模拟响应
        content = self._generate_response(user_input)
        return content, self.latency_ms, 50

    def _generate_response(self, user_input: str) -> str:
        """生成模拟响应"""
        input_lower = user_input.lower()

        if "你好" in user_input or "hello" in input_lower:
            return "你好！有什么我可以帮助你的吗？"
        elif "1+1" in user_input:
            return "1+1 等于 2"
        elif "时间" in user_input or "几点" in user_input:
            import datetime
            now = datetime.datetime.now()
            return f"现在是 {now.hour}点{now.minute}分"
        elif "谢谢" in user_input:
            return "不客气！有其他问题吗？"
        elif "谁" in user_input:
            return "我是 Talker 助手，可以快速回答你的问题。"
        elif "天气" in user_input:
            return "北京明天天气晴朗，气温 15-25 度。"
        elif "公里" in user_input or "英里" in user_input:
            return "100 公里约等于 62.14 英里。"
        elif "翻译" in user_input:
            return "Hello, World"
        else:
            return f"我收到了你的问题：'{user_input}'，这是一个简单的问题。"


class MockThinkerAgent:
    """Mock Thinker Agent 用于评测"""

    def __init__(self, latency_ms: float = 2000.0):
        self.latency_ms = latency_ms
        self.call_count = 0

    async def process(
        self,
        user_input: str,
        context_messages: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> Tuple[str, float, int]:
        """
        模拟 Thinker 处理

        Returns:
            Tuple[content, latency_ms, tokens_used]
        """
        self.call_count += 1
        await asyncio.sleep(self.latency_ms / 1000)

        content = self._generate_response(user_input)
        return content, self.latency_ms, 500

    def _generate_response(self, user_input: str) -> str:
        """生成模拟响应 (更长，更有结构)"""
        input_lower = user_input.lower()

        if "分析" in user_input or "趋势" in user_input:
            return """## AI 技术发展趋势分析

### 当前现状
人工智能技术正在快速发展，主要体现在以下几个方面：

1. **大语言模型**: 模型规模持续增长，能力不断增强
2. **多模态融合**: 文本、图像、音频的深度融合
3. **Agent 系统**: 自主智能体成为新热点

### 未来展望
考虑到以上因素，我们认为：
- 首先，通用人工智能 (AGI) 仍是长期目标
- 其次，垂直领域的深度应用将加速落地
- 最后，人机协作模式将重新定义工作方式

综上所述，AI 技术将在未来 5-10 年持续保持高速发展。"""

        elif "对比" in user_input or "比较" in user_input:
            return """## 产品对比分析

### iPhone 15
- 优点：A17 芯片性能强劲，iOS 生态完善，拍照优秀
- 缺点：价格较高，充电速度慢

### Samsung Galaxy S24
- 优点：屏幕素质一流，Android 系统灵活，快充支持
- 缺点：系统更新支持相对较短

### Google Pixel 8
- 优点：原生 Android 体验，AI 功能丰富，拍照算法优秀
- 缺点：国内使用受限，品牌认知度较低

### 购买建议
综合考虑，如果追求稳定体验推荐 iPhone 15；如果偏好 Android 推荐 Samsung Galaxy S24。"""

        elif "旅行" in user_input or "计划" in user_input:
            return """## 5 天东京旅行计划

### 第一天：抵达与适应
- 上午：抵达成田机场，办理入住
- 下午：游览涩谷、原宿
- 晚餐：涩谷美食街

### 第二天：传统文化体验
- 上午：浅草寺、雷门
- 下午：秋叶原电器街
- 晚餐：银座高级料理

### 第三天：现代东京
- 上午：东京塔、皇居
- 下午：台场海滨公园
- 晚餐：新宿歌舞伎町

### 第四天：周边游览
- 全天：镰仓一日游（鹤冈八幡宫、镰仓大佛）

### 第五天：购物与返程
- 上午：表参道购物
- 下午：前往机场

### 住宿建议
推荐选择新宿或涩谷区域，交通便利，餐饮选择丰富。"""

        elif "错误" in user_input or "bug" in user_input.lower():
            return """## 代码错误分析

### 错误原因
`TypeError: 'int' object is not iterable` 通常由以下原因导致：

1. **原因一**: 尝试遍历一个整数
   ```python
   for i in 5:  # 错误！5 是整数，不可迭代
       print(i)
   ```

2. **原因二**: 函数返回了整数而非可迭代对象
   ```python
   result = get_items()  # 期望返回 list，但返回了 int
   for item in result:
       print(item)
   ```

### 解决方案
1. 检查变量类型，使用 `isinstance()` 验证
2. 确保使用 `range()` 等函数生成可迭代对象
3. 检查函数返回值类型

建议添加类型注解和单元测试来预防此类错误。"""

        else:
            return f"""## 关于'{user_input[:50]}...'的分析

### 问题理解
这是一个需要深入思考的复杂问题。

### 分析过程
考虑到多方面因素，我们需要从以下几个角度分析：

1. **背景分析**: 理解问题的来龙去脉
2. **关键因素**: 识别影响结果的核心要素
3. **解决方案**: 基于分析提出可行方案

### 结论
综上所述，这个问题需要综合考虑多个维度的信息，建议进一步收集相关信息后做出决策。"""


class EvalRunner:
    """
    评测执行引擎

    负责加载用例、执行评测、收集指标
    """

    def __init__(self, config: Optional[EvalConfig] = None):
        self.config = config or EvalConfig()
        self.collector = MetricsCollector()
        self.talker_mock = MockTalkerAgent(self.config.mock_talker_latency_ms)
        self.thinker_mock = MockThinkerAgent(self.config.mock_thinker_latency_ms)

    async def run(self, cases: Optional[List[EvalCase]] = None) -> EvalResult:
        """
        执行评测

        Args:
            cases: 要执行的用例列表，如果为 None 则根据配置加载

        Returns:
            EvalResult: 评测结果
        """
        # 加载用例
        if cases is None:
            cases = self._load_cases()

        if not cases:
            logger.warning("没有要执行的评测用例")
            return EvalResult()

        self.collector.total_cases = len(cases)
        self.collector.start_time = time.time()

        # 执行所有用例
        case_results = []
        for i, case in enumerate(cases):
            if self.config.show_progress:
                print(f"\r正在执行评测 [{i+1}/{len(cases)}] {case.case_id}: {case.name}", end="")

            try:
                result = await self._execute_case(case)
                case_results.append(result)
            except Exception as e:
                logger.exception(f"用例 {case.case_id} 执行失败")
                case_results.append(CaseResult(
                    case_id=case.case_id,
                    case_name=case.name,
                    passed=False,
                    actual_agent=AgentRole.TALKER,
                    actual_complexity=TaskComplexity.SIMPLE,
                    actual_output=f"执行异常：{str(e)}",
                    response_time_ms=0,
                    assertion_results=[],
                    failure_reason=FailureReason.EXCEPTION,
                    failure_details=str(e),
                ))

        if self.config.show_progress:
            print("\n")

        # 构建评测结果
        self.collector.end_time = time.time()

        passed_cases = sum(1 for r in case_results if r.passed)
        failed_cases = len(case_results) - passed_cases

        eval_result = EvalResult(
            case_results=case_results,
            start_time=self.collector.start_time,
            end_time=self.collector.end_time,
            total_cases=len(case_results),
            passed_cases=passed_cases,
            failed_cases=failed_cases,
        )

        # 更新指标收集器
        for result in case_results:
            category = self._get_category_from_case_id(result.case_id)
            self.collector.record_case_result(result, category)

        return eval_result

    def _load_cases(self) -> List[EvalCase]:
        """加载用例"""
        if self.config.category_filter:
            cases = get_cases_by_category(self.config.category_filter)
        else:
            cases = get_all_cases()

        # 应用优先级过滤
        if self.config.priority_filter:
            cases = [c for c in cases if c.priority == self.config.priority_filter]

        # 应用用例 ID 过滤
        if self.config.case_id_filter:
            cases = [c for c in cases if c.case_id in self.config.case_id_filter]

        return cases

    async def _execute_case(self, case: EvalCase) -> CaseResult:
        """
        执行单个用例

        Args:
            case: 评测用例

        Returns:
            CaseResult: 用例执行结果
        """
        start_time = time.time()

        # 确定使用哪个 Mock Agent
        # 在真实场景中，这里会调用 Orchestrator
        # 为了评测，我们根据期望的 Agent 来模拟路由
        expected_agent = case.expected_agent

        # 模拟 Agent 路由
        actual_agent = self._route_agent(case.user_input)
        actual_complexity = self._classify_complexity(case.user_input)

        # 执行 Agent 处理
        if actual_agent == AgentRole.THINKER:
            content, latency, tokens = await self.thinker_mock.process(
                case.user_input,
                case.context_messages,
            )
        else:
            content, latency, tokens = await self.talker_mock.process(
                case.user_input,
                case.context_messages,
            )

        response_time_ms = latency

        # 执行断言检查
        assertion_results = self._run_assertions(
            case,
            actual_agent=actual_agent,
            actual_complexity=actual_complexity,
            actual_output=content,
            response_time_ms=response_time_ms,
        )

        # 判断是否通过
        passed = all(ar.passed for ar in assertion_results)

        # 确定失败原因
        failure_reason = None
        failure_details = ""
        if not passed:
            failed_assertions = [ar for ar in assertion_results if not ar.passed]
            if failed_assertions:
                # 根据失败的断言判断失败原因
                for fa in failed_assertions:
                    if "routing" in fa.assertion_name.lower():
                        failure_reason = FailureReason.WRONG_AGENT
                    elif "time" in fa.assertion_name.lower():
                        failure_reason = FailureReason.TIMEOUT
                    elif "output" in fa.assertion_name.lower():
                        failure_reason = FailureReason.WRONG_OUTPUT
                    else:
                        failure_reason = FailureReason.ASSERTION_FAILED

                    failure_details = fa.failure_reason
                    break

        return CaseResult(
            case_id=case.case_id,
            case_name=case.name,
            passed=passed,
            actual_agent=actual_agent,
            actual_complexity=actual_complexity,
            actual_output=content,
            response_time_ms=response_time_ms,
            assertion_results=assertion_results,
            failure_reason=failure_reason,
            failure_details=failure_details,
            tokens_used=tokens,
        )

    def _route_agent(self, user_input: str) -> AgentRole:
        """
        模拟 Agent 路由

        在真实场景中，这里会调用 Orchestrator 的路由逻辑
        """
        # 简单规则：长输入或包含复杂关键词 -> Thinker
        complex_keywords = ["分析", "对比", "规划", "设计", "方案", "深度", "复杂", "多步"]

        if len(user_input) > 50 or any(k in user_input for k in complex_keywords):
            return AgentRole.THINKER
        return AgentRole.TALKER

    def _classify_complexity(self, user_input: str) -> TaskComplexity:
        """
        模拟复杂度分类

        在真实场景中，这里会调用意图分类逻辑
        """
        complex_keywords = ["分析", "对比", "规划", "设计", "方案"]

        if len(user_input) > 100 or any(k in user_input for k in complex_keywords):
            return TaskComplexity.COMPLEX
        elif len(user_input) > 30:
            return TaskComplexity.MEDIUM
        return TaskComplexity.SIMPLE

    def _run_assertions(
        self,
        case: EvalCase,
        actual_agent: AgentRole,
        actual_complexity: TaskComplexity,
        actual_output: str,
        response_time_ms: float,
    ) -> List[AssertionResult]:
        """执行所有断言检查"""
        results = []

        for assertion in case.assertions:
            try:
                result = assertion.check(
                    # Agent 路由相关参数
                    actual_agent=actual_agent,
                    expected_agent=case.expected_agent,
                    # 复杂度相关参数
                    actual_complexity=actual_complexity,
                    expected_complexity=case.expected_complexity,
                    # 输出相关参数
                    actual_output=actual_output,
                    golden_output=case.golden_output,
                    # 时间相关参数
                    response_time_ms=response_time_ms,
                    threshold=500 if case.expected_agent == AgentRole.TALKER else 3000,
                    # 兼容性参数 (旧版断言可能使用)
                    actual=actual_agent,
                    expected=case.expected_agent,
                )
                results.append(result)
            except Exception as e:
                results.append(AssertionResult(
                    assertion_name=assertion.name,
                    passed=False,
                    weight=assertion.weight,
                    failure_reason=f"断言执行异常：{str(e)}",
                ))

        return results

    def _get_category_from_case_id(self, case_id: str) -> str:
        """从用例 ID 获取类别"""
        if case_id.startswith("S"):
            return EvalCategory.SIMPLE.value
        elif case_id.startswith("M"):
            return EvalCategory.MEDIUM.value
        elif case_id.startswith("C"):
            return EvalCategory.COMPLEX.value
        elif case_id.startswith("E"):
            return EvalCategory.EDGE.value
        return "unknown"

    def get_collector(self) -> MetricsCollector:
        """获取指标收集器"""
        return self.collector
