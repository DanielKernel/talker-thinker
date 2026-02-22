"""
准确率指标 (Accuracy Metrics)

收集和统计准确率相关指标:
- 意图分类准确率
- Agent 路由准确率
- 断言通过率
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict


@dataclass
class AccuracyMetrics:
    """
    准确率指标收集器

    用于收集和统计准确率相关指标
    """
    # 意图分类结果 (predicted, expected)
    intent_predictions: List[Tuple[str, str]] = field(default_factory=list)

    # Agent 路由结果 (predicted, expected)
    agent_routing: List[Tuple[str, str]] = field(default_factory=list)

    # 断言结果 (assertion_name, passed)
    assertion_results: List[Tuple[str, bool]] = field(default_factory=list)

    # 按类别分组
    by_category: Dict[str, Dict[str, Any]] = field(default_factory=lambda: defaultdict(lambda: {
        "total": 0,
        "correct": 0,
        "predictions": [],
        "routing": [],
    }))

    def record_intent_classification(
        self,
        predicted: str,
        expected: str,
        category: Optional[str] = None,
    ) -> bool:
        """
        记录意图分类结果

        Args:
            predicted: 预测的意图
            expected: 期望的意图
            category: 用例类别

        Returns:
            bool: 是否分类正确
        """
        self.intent_predictions.append((predicted, expected))
        correct = predicted == expected

        if category:
            self.by_category[category]["total"] += 1
            if correct:
                self.by_category[category]["correct"] += 1
            self.by_category[category]["predictions"].append((predicted, expected))

        return correct

    def record_agent_routing(
        self,
        actual: str,
        expected: str,
        category: Optional[str] = None,
    ) -> bool:
        """
        记录 Agent 路由结果

        Args:
            actual: 实际分配的 Agent
            expected: 期望分配的 Agent
            category: 用例类别

        Returns:
            bool: 是否路由正确
        """
        self.agent_routing.append((actual, expected))
        correct = actual == expected

        if category:
            if category not in self.by_category:
                self.by_category[category] = {"total": 0, "correct": 0, "predictions": [], "routing": []}
            self.by_category[category]["routing"].append((actual, expected))

        return correct

    def record_assertion(
        self,
        assertion_name: str,
        passed: bool,
        category: Optional[str] = None,
    ) -> None:
        """
        记录断言结果

        Args:
            assertion_name: 断言名称
            passed: 是否通过
            category: 用例类别
        """
        self.assertion_results.append((assertion_name, passed))

    # ========= 统计方法 =========

    @property
    def intent_classification_accuracy(self) -> float:
        """意图分类准确率"""
        if not self.intent_predictions:
            return 0.0
        correct = sum(1 for p, e in self.intent_predictions if p == e)
        return correct / len(self.intent_predictions) * 100

    @property
    def agent_routing_accuracy(self) -> float:
        """Agent 路由准确率"""
        if not self.agent_routing:
            return 0.0
        correct = sum(1 for a, e in self.agent_routing if a == e)
        return correct / len(self.agent_routing) * 100

    @property
    def overall_assertion_pass_rate(self) -> float:
        """整体断言通过率"""
        if not self.assertion_results:
            return 0.0
        passed = sum(1 for _, p in self.assertion_results if p)
        return passed / len(self.assertion_results) * 100

    def get_assertion_pass_rate(self, assertion_name: str) -> float:
        """获取指定断言的通过率"""
        results = [p for name, p in self.assertion_results if name == assertion_name]
        if not results:
            return 0.0
        passed = sum(1 for p in results if p)
        return passed / len(results) * 100

    def get_confusion_matrix(self) -> Dict[str, Dict[str, int]]:
        """
        获取 Agent 路由混淆矩阵

        Returns:
            Dict[expected, Dict[actual, count]]
        """
        matrix: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for actual, expected in self.agent_routing:
            matrix[expected][actual] += 1
        return {k: dict(v) for k, v in matrix.items()}

    def get_category_breakdown(self) -> Dict[str, Dict[str, Any]]:
        """获取按类别分解的准确率"""
        breakdown = {}
        for category, data in self.by_category.items():
            total = data.get("total", 0)
            correct = data.get("correct", 0)

            # 计算路由准确率
            routing_data = data.get("routing", [])
            routing_correct = sum(1 for a, e in routing_data if a == e) if routing_data else 0
            routing_accuracy = routing_correct / len(routing_data) * 100 if routing_data else 0.0

            breakdown[category] = {
                "total_cases": total,
                "intent_accuracy": correct / total * 100 if total > 0 else 0.0,
                "routing_accuracy": routing_accuracy,
                "routing_predictions": routing_data,
            }

        return breakdown

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "summary": {
                "intent_classification_accuracy": round(self.intent_classification_accuracy, 2),
                "agent_routing_accuracy": round(self.agent_routing_accuracy, 2),
                "overall_assertion_pass_rate": round(self.overall_assertion_pass_rate, 2),
            },
            "details": {
                "intent_predictions": {
                    "total": len(self.intent_predictions),
                    "correct": sum(1 for p, e in self.intent_predictions if p == e),
                },
                "agent_routing": {
                    "total": len(self.agent_routing),
                    "correct": sum(1 for a, e in self.agent_routing if a == e),
                },
                "assertions": {
                    "total": len(self.assertion_results),
                    "passed": sum(1 for _, p in self.assertion_results if p),
                },
            },
            "confusion_matrix": self.get_confusion_matrix(),
            "category_breakdown": self.get_category_breakdown(),
        }
