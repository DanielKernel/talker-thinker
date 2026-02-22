"""
控制台报告生成器
"""
import time
from typing import Dict, Any, Optional

from ..core.types import EvalResult, CaseResult, FailureReason, EvalCategory


class ConsoleReporter:
    """
    控制台报告生成器

    在终端输出评测报告
    """

    def __init__(self, verbose: bool = True):
        """
        初始化报告生成器

        Args:
            verbose: 是否输出详细信息
        """
        self.verbose = verbose

    def generate(self, eval_result: EvalResult) -> str:
        """
        生成报告

        Args:
            eval_result: 评测结果

        Returns:
            str: 格式化的报告文本
        """
        lines = []

        # 标题
        lines.append(self._separator("="))
        lines.append(self._center("Talker-Thinker 评测报告"))
        lines.append(self._separator("="))
        lines.append("")

        # 基本信息
        lines.append("📊 基本信息")
        lines.append(self._separator("-", length=60))
        lines.append(f"  评测 ID:        {eval_result.run_id[:8]}...")
        lines.append(f"  评测时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(eval_result.start_time))}")
        lines.append(f"  耗时：{eval_result.end_time - eval_result.start_time:.2f} 秒")
        lines.append("")

        # 总体概览
        lines.append("📈 总体概览")
        lines.append(self._separator("-", length=60))
        lines.append(f"  总用例数：{eval_result.total_cases}")
        lines.append(f"  通过用例：{eval_result.passed_cases} ({eval_result.pass_rate:.1f}%)")
        lines.append(f"  失败用例：{eval_result.failed_cases} ({100 - eval_result.pass_rate:.1f}%)")
        lines.append(f"  平均得分：{eval_result.average_score:.1f}/100")
        lines.append(f"  平均响应时间：{eval_result.average_response_time:.1f}ms")
        lines.append("")

        # 分类统计
        category_stats = self._compute_category_stats(eval_result.case_results)
        lines.append("📋 分类统计")
        lines.append(self._separator("-", length=60))
        for category, stats in category_stats.items():
            category_name = self._get_category_name(category)
            lines.append(f"  {category_name}:")
            lines.append(f"    用例数：{stats['total']}")
            lines.append(f"    通过率：{stats['pass_rate']:.1f}%")
            lines.append(f"    平均响应时间：{stats['avg_time']:.1f}ms")
        lines.append("")

        # 失败原因分布
        if eval_result.failure_breakdown:
            lines.append("❌ 失败原因分布")
            lines.append(self._separator("-", length=60))
            for reason, count in eval_result.failure_breakdown.items():
                reason_name = self._get_failure_reason_name(reason)
                lines.append(f"  {reason_name}: {count}")
            lines.append("")

        # 详细结果
        if self.verbose and eval_result.case_results:
            lines.append("📝 详细结果")
            lines.append(self._separator("-", length=60))

            # 按类别分组输出
            for category in ["simple", "medium", "complex", "edge"]:
                category_results = [
                    r for r in eval_result.case_results
                    if r.case_id.lower().startswith(category[0])
                ]

                if category_results:
                    category_name = self._get_category_name(category)
                    lines.append(f"\n  【{category_name}】")
                    lines.append("")

                    for result in category_results:
                        status = "✅" if result.passed else "❌"
                        lines.append(f"    {status} {result.case_id}: {result.case_name}")

                        if not result.passed:
                            lines.append(f"        失败原因：{result.failure_details or result.failure_reason}")

                        if self.verbose:
                            lines.append(f"        响应时间：{result.response_time_ms:.1f}ms")
                            lines.append(f"        得分：{result.score:.1f}")

            lines.append("")

        # 目标达成情况
        lines.append("🎯 目标达成情况")
        lines.append(self._separator("-", length=60))
        targets = self._compute_targets(eval_result)
        for name, target_info in targets.items():
            status = "✅" if target_info["achieved"] else "❌"
            lines.append(f"  {status} {name}:")
            lines.append(f"      目标：{target_info['target']}")
            lines.append(f"      实际：{target_info['actual']}")
        lines.append("")

        # 建议
        lines.append("💡 改进建议")
        lines.append(self._separator("-", length=60))
        recommendations = self._generate_recommendations(eval_result)
        for i, rec in enumerate(recommendations, 1):
            lines.append(f"  {i}. {rec}")
        lines.append("")

        lines.append(self._separator("="))
        lines.append(self._center("评测完成"))
        lines.append(self._separator("="))

        return "\n".join(lines)

    def print(self, eval_result: EvalResult) -> None:
        """打印报告到控制台"""
        print(self.generate(eval_result))

    def _separator(self, char: str = "=", length: int = 80) -> str:
        """生成分隔线"""
        return char * length

    def _center(self, text: str, width: int = 80) -> str:
        """生成居中文本"""
        padding = (width - len(text)) // 2
        return " " * padding + text

    def _get_category_name(self, category: str) -> str:
        """获取类别中文名"""
        names = {
            "simple": "简单任务",
            "medium": "中等任务",
            "complex": "复杂任务",
            "edge": "边界/异常",
        }
        return names.get(category, category)

    def _get_failure_reason_name(self, reason: FailureReason) -> str:
        """获取失败原因中文名"""
        names = {
            FailureReason.WRONG_AGENT: "路由错误 (Wrong Agent)",
            FailureReason.TIMEOUT: "超时 (Timeout)",
            FailureReason.WRONG_OUTPUT: "输出错误 (Wrong Output)",
            FailureReason.SKILL_FAILED: "技能失败 (Skill Failed)",
            FailureReason.ASSERTION_FAILED: "断言失败 (Assertion Failed)",
            FailureReason.EXCEPTION: "异常 (Exception)",
            FailureReason.HANDOFF_FAILED: "Handoff 失败 (Handoff Failed)",
            FailureReason.CONTEXT_LOST: "上下文丢失 (Context Lost)",
        }
        return names.get(reason, str(reason))

    def _compute_category_stats(self, case_results: list) -> Dict[str, Dict[str, Any]]:
        """计算分类统计信息"""
        stats = {}

        for result in case_results:
            category = result.case_id[0].lower()
            category_map = {
                "s": "simple",
                "m": "medium",
                "c": "complex",
                "e": "edge",
            }
            category = category_map.get(category, "unknown")

            if category not in stats:
                stats[category] = {"total": 0, "passed": 0, "total_time": 0}

            stats[category]["total"] += 1
            if result.passed:
                stats[category]["passed"] += 1
            stats[category]["total_time"] += result.response_time_ms

        # 计算通过率和平局响应时间
        for category, data in stats.items():
            data["pass_rate"] = data["passed"] / data["total"] * 100 if data["total"] > 0 else 0
            data["avg_time"] = data["total_time"] / data["total"] if data["total"] > 0 else 0

        return stats

    def _compute_targets(self, eval_result: EvalResult) -> Dict[str, Dict[str, Any]]:
        """计算目标达成情况"""
        targets = {
            "响应速度 (<500ms)": {
                "target": "<500ms",
                "actual": f"{eval_result.average_response_time:.1f}ms",
                "achieved": eval_result.average_response_time < 500,
            },
            "通过率 (>85%)": {
                "target": ">85%",
                "actual": f"{eval_result.pass_rate:.1f}%",
                "achieved": eval_result.pass_rate >= 85,
            },
            "平均得分 (>80)": {
                "target": ">80",
                "actual": f"{eval_result.average_score:.1f}",
                "achieved": eval_result.average_score >= 80,
            },
        }
        return targets

    def _generate_recommendations(self, eval_result: EvalResult) -> list:
        """生成改进建议"""
        recommendations = []

        # 基于失败原因的建议
        failure_breakdown = eval_result.failure_breakdown

        if FailureReason.WRONG_AGENT in failure_breakdown:
            recommendations.append(
                "优化 Agent 路由策略，提高意图分类准确性"
            )

        if FailureReason.TIMEOUT in failure_breakdown:
            recommendations.append(
                "优化响应速度，考虑使用更快的模型或优化 prompt"
            )

        if FailureReason.WRONG_OUTPUT in failure_breakdown:
            recommendations.append(
                "改进模型输出质量，优化 prompt 和Few-shot 示例"
            )

        # 基于通过率的整体建议
        if eval_result.pass_rate < 70:
            recommendations.append(
                "整体通过率较低，建议全面检查系统配置和模型设置"
            )
        elif eval_result.pass_rate < 85:
            recommendations.append(
                "通过率有待提升，重点关注失败用例较多的类别"
            )

        # 基于响应时间的建议
        if eval_result.average_response_time > 500:
            recommendations.append(
                "平均响应时间超过目标值，建议优化 Talker 响应速度"
            )

        if not recommendations:
            recommendations.append("表现优秀，继续保持！")

        return recommendations
