"""
质量评分指标 (Quality Metrics)

收集和统计答案质量相关指标:
- 完整性 (Completeness)
- 准确性 (Accuracy)
- 相关性 (Relevance)
- 清晰度 (Clarity)
- 有用性 (Usefulness)
"""
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from context.types import QualityScore


@dataclass
class QualityMetrics:
    """
    质量评分指标收集器

    用于收集和统计答案质量相关指标
    """
    quality_scores: List[QualityScore] = field(default_factory=list)
    raw_scores: List[Dict[str, float]] = field(default_factory=list)

    # 按类别分组
    by_category: Dict[str, List[QualityScore]] = field(default_factory=dict)

    def record_quality_score(
        self,
        quality_score: QualityScore,
        category: Optional[str] = None,
    ) -> None:
        """记录质量评分"""
        self.quality_scores.append(quality_score)
        self.raw_scores.append(quality_score.to_dict())

        if category:
            if category not in self.by_category:
                self.by_category[category] = []
            self.by_category[category].append(quality_score)

    def record_raw_score(
        self,
        overall: float,
        completeness: float,
        accuracy: float,
        relevance: float,
        clarity: float,
        usefulness: float,
        category: Optional[str] = None,
    ) -> QualityScore:
        """记录原始质量评分"""
        score = QualityScore(
            overall_score=overall,
            completeness=completeness,
            accuracy=accuracy,
            relevance=relevance,
            clarity=clarity,
            usefulness=usefulness,
        )
        self.raw_scores.append(score.to_dict())

        if category:
            if category not in self.by_category:
                self.by_category[category] = []
            self.by_category[category].append(score)

        return score

    # ========= 启发式质量评估 =========

    @staticmethod
    def heuristic_evaluate(
        actual_output: str,
        golden_output: Optional[str] = None,
        expected_length: int = 100,
    ) -> QualityScore:
        """
        启发式质量评估

        基于规则和启发式方法评估答案质量

        Args:
            actual_output: 实际输出
            golden_output: 期望输出 (可选)
            expected_length: 期望长度

        Returns:
            QualityScore: 质量评分
        """
        # 1. 完整性评分 (基于长度和内容覆盖)
        completeness = min(1.0, len(actual_output) / expected_length)

        # 2. 准确性评分 (基于与 golden output 的重叠)
        accuracy = 1.0
        if golden_output:
            # 计算词汇重叠率
            actual_words = set(re.findall(r'\w+', actual_output.lower()))
            golden_words = set(re.findall(r'\w+', golden_output.lower()))

            if golden_words:
                overlap = len(actual_words & golden_words) / len(golden_words)
                accuracy = min(1.0, overlap * 2)  # 放大重叠率影响

        # 3. 相关性评分 (基于是否包含问题关键词)
        # 简化处理：假设输出长度合理即相关
        relevance = 0.5 + 0.5 * min(1.0, len(actual_output) / 50)

        # 4. 清晰度评分 (基于结构化程度)
        has_structure = bool(re.search(r'\d+[\.、)]|[-•*]\s|##|###', actual_output))
        has_paragraphs = actual_output.count('\n\n') > 0
        clarity = 0.6
        if has_structure:
            clarity += 0.2
        if has_paragraphs:
            clarity += 0.1
        clarity = min(1.0, clarity)

        # 5. 有用性评分 (综合评分)
        usefulness = (completeness + accuracy + relevance) / 3

        # 计算总体评分
        overall = (
            completeness * 0.2 +
            accuracy * 0.25 +
            relevance * 0.2 +
            clarity * 0.15 +
            usefulness * 0.2
        )

        # 生成问题和建议
        issues = []
        suggestions = []

        if len(actual_output) < expected_length * 0.5:
            issues.append("输出过短，可能不够完整")
            suggestions.append("尝试提供更详细的回答")

        if accuracy < 0.5 and golden_output:
            issues.append("与期望输出的匹配度较低")
            suggestions.append("检查是否正确理解了问题")

        if not has_structure:
            suggestions.append("可以考虑使用列表或小标题组织内容")

        return QualityScore(
            overall_score=overall * 100,
            completeness=completeness * 100,
            accuracy=accuracy * 100,
            relevance=relevance * 100,
            clarity=clarity * 100,
            usefulness=usefulness * 100,
            issues=issues,
            suggestions=suggestions,
            reasoning=f"启发式评估：完整性={completeness:.2f}, 准确性={accuracy:.2f}, 相关性={relevance:.2f}",
        )

    # ========= 统计方法 =========

    @property
    def avg_overall_score(self) -> float:
        """平均总体评分"""
        if not self.quality_scores:
            return 0.0
        return sum(s.overall_score for s in self.quality_scores) / len(self.quality_scores)

    @property
    def avg_dimension_scores(self) -> Dict[str, float]:
        """各维度平均评分"""
        if not self.quality_scores:
            return {
                "completeness": 0.0,
                "accuracy": 0.0,
                "relevance": 0.0,
                "clarity": 0.0,
                "usefulness": 0.0,
            }

        n = len(self.quality_scores)
        return {
            "completeness": sum(s.completeness for s in self.quality_scores) / n,
            "accuracy": sum(s.accuracy for s in self.quality_scores) / n,
            "relevance": sum(s.relevance for s in self.quality_scores) / n,
            "clarity": sum(s.clarity for s in self.quality_scores) / n,
            "usefulness": sum(s.usefulness for s in self.quality_scores) / n,
        }

    def get_category_scores(self, category: str) -> Dict[str, float]:
        """获取指定类别的质量评分"""
        scores = self.by_category.get(category, [])
        if not scores:
            return {"overall": 0.0}

        avg_overall = sum(s.overall_score for s in scores) / len(scores)
        return {
            "overall": avg_overall,
            "avg_dimensions": {
                "completeness": sum(s.completeness for s in scores) / len(scores),
                "accuracy": sum(s.accuracy for s in scores) / len(scores),
                "relevance": sum(s.relevance for s in scores) / len(scores),
                "clarity": sum(s.clarity for s in scores) / len(scores),
                "usefulness": sum(s.usefulness for s in scores) / len(scores),
            },
        }

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        avg_dims = self.avg_dimension_scores

        return {
            "summary": {
                "total_evaluated": len(self.quality_scores),
                "avg_overall_score": round(self.avg_overall_score, 2),
            },
            "dimensions": {
                "completeness": round(avg_dims["completeness"], 2),
                "accuracy": round(avg_dims["accuracy"], 2),
                "relevance": round(avg_dims["relevance"], 2),
                "clarity": round(avg_dims["clarity"], 2),
                "usefulness": round(avg_dims["usefulness"], 2),
            },
            "by_category": {
                k: {
                    "count": len(v),
                    "avg_overall": round(sum(s.overall_score for s in v) / len(v), 2),
                }
                for k, v in self.by_category.items()
            },
        }
