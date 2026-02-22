"""
指标收集器

统一收集和管理所有评测指标
"""
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from .latency import LatencyMetrics
from .accuracy import AccuracyMetrics
from .quality import QualityMetrics
from ..core.types import CaseResult, EvalResult, EvalCategory, FailureReason


@dataclass
class MetricsCollector:
    """
    指标收集器

    统一收集和管理所有评测指标
    """
    latency: LatencyMetrics = field(default_factory=LatencyMetrics)
    accuracy: AccuracyMetrics = field(default_factory=AccuracyMetrics)
    quality: QualityMetrics = field(default_factory=QualityMetrics)

    # 执行信息
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    total_cases: int = 0
    completed_cases: int = 0

    def record_case_result(
        self,
        result: CaseResult,
        category: str,
    ) -> None:
        """
        记录用例执行结果

        Args:
            result: 用例执行结果
            category: 用例类别
        """
        self.completed_cases += 1

        # 记录延迟指标
        self.latency.record_response_time(
            result.response_time_ms,
            category=category,
            agent=result.actual_agent.value,
        )

        # 记录准确率指标
        self.accuracy.record_assertion("response_time", result.response_time_ms < 1000, category)

        for assertion_result in result.assertion_results:
            self.accuracy.record_assertion(
                assertion_result.assertion_name,
                assertion_result.passed,
                category,
            )

        # 记录质量评分 (如果有 golden output)
        if result.golden_output if hasattr(result, 'golden_output') else None:
            quality_score = QualityMetrics.heuristic_evaluate(
                result.actual_output,
                getattr(result, 'golden_output', None),
            )
            self.quality.record_quality_score(quality_score, category)

    def compute_targets(self) -> Dict[str, Any]:
        """
        计算目标达成情况

        Returns:
            Dict: 各目标的达成情况
        """
        targets = {
            "talker_response_target_ms": 500,
            "intent_classification_target": 90.0,
            "handoff_accuracy_target": 95.0,
            "task_success_rate_target": 85.0,
            "quality_score_target": 80.0,
        }

        achievements = {}

        # 响应速度目标
        avg_response = self.latency.avg_response_time
        achievements["response_speed"] = {
            "target": targets["talker_response_target_ms"],
            "actual": round(avg_response, 2),
            "achieved": avg_response <= targets["talker_response_target_ms"],
        }

        # 意图分类准确率目标
        # 这里简化处理，使用 agent routing accuracy 代替
        routing_accuracy = self.accuracy.agent_routing_accuracy
        achievements["intent_classification"] = {
            "target": targets["intent_classification_target"],
            "actual": round(routing_accuracy, 2),
            "achieved": routing_accuracy >= targets["intent_classification_target"],
        }

        # Handoff 准确率目标
        achievements["handoff_accuracy"] = {
            "target": targets["handoff_accuracy_target"],
            "actual": round(routing_accuracy, 2),
            "achieved": routing_accuracy >= targets["handoff_accuracy_target"],
        }

        # 任务完成率目标 (使用断言通过率近似)
        task_success = self.accuracy.overall_assertion_pass_rate
        achievements["task_completion"] = {
            "target": targets["task_success_rate_target"],
            "actual": round(task_success, 2),
            "achieved": task_success >= targets["task_success_rate_target"],
        }

        # 质量评分目标
        avg_quality = self.quality.avg_overall_score
        achievements["quality_score"] = {
            "target": targets["quality_score_target"],
            "actual": round(avg_quality, 2),
            "achieved": avg_quality >= targets["quality_score_target"],
        }

        return achievements

    def generate_summary(self) -> Dict[str, Any]:
        """
        生成指标摘要

        Returns:
            Dict: 指标摘要
        """
        return {
            "execution": {
                "start_time": self.start_time,
                "end_time": self.end_time,
                "duration_seconds": round(self.end_time - self.start_time, 2),
                "total_cases": self.total_cases,
                "completed_cases": self.completed_cases,
                "completion_rate": round(
                    self.completed_cases / self.total_cases * 100, 2
                ) if self.total_cases > 0 else 0.0,
            },
            "latency": self.latency.to_dict(),
            "accuracy": self.accuracy.to_dict(),
            "quality": self.quality.to_dict(),
            "targets": self.compute_targets(),
        }

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.generate_summary()

    @classmethod
    def from_eval_result(
        cls,
        eval_result: EvalResult,
    ) -> "MetricsCollector":
        """
        从评测结果构建指标收集器

        Args:
            eval_result: 评测结果

        Returns:
            MetricsCollector: 指标收集器实例
        """
        collector = cls()
        collector.start_time = eval_result.start_time
        collector.end_time = eval_result.end_time
        collector.total_cases = eval_result.total_cases
        collector.completed_cases = len(eval_result.case_results)

        for result in eval_result.case_results:
            # 确定类别
            category = "unknown"
            if result.case_id.startswith("S"):
                category = EvalCategory.SIMPLE.value
            elif result.case_id.startswith("M"):
                category = EvalCategory.MEDIUM.value
            elif result.case_id.startswith("C"):
                category = EvalCategory.COMPLEX.value
            elif result.case_id.startswith("E"):
                category = EvalCategory.EDGE.value

            collector.record_case_result(result, category)

        return collector
