"""
HTML 报告生成器

生成可视化的 HTML 评测报告
"""
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

from ..core.types import EvalResult, CaseResult, FailureReason


class HTMLReporter:
    """
    HTML 报告生成器

    生成带有样式和图表的 HTML 评测报告
    """

    def __init__(self):
        self.styles = self._get_styles()

    def generate(self, eval_result: EvalResult) -> str:
        """
        生成 HTML 报告

        Args:
            eval_result: 评测结果

        Returns:
            str: HTML 格式的报告
        """
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Talker-Thinker 评测报告</title>
    {self.styles}
</head>
<body>
    <div class="container">
        <header>
            <h1>📊 Talker-Thinker 评测报告</h1>
            <p class="subtitle">Generated at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(eval_result.start_time))}</p>
        </header>

        {self._generate_summary_card(eval_result)}

        {self._generate_category_stats(eval_result)}

        {self._generate_failure_breakdown(eval_result)}

        {self._generate_targets_section(eval_result)}

        {self._generate_detailed_results(eval_result)}

        {self._generate_recommendations(eval_result)}

        <footer>
            <p>Talker-Thinker Evaluation System v1.0</p>
        </footer>
    </div>
</body>
</html>"""
        return html

    def _get_styles(self) -> str:
        """获取 CSS 样式"""
        return """<style>
    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }

    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        min-height: 100vh;
        padding: 20px;
    }

    .container {
        max-width: 1200px;
        margin: 0 auto;
    }

    header {
        text-align: center;
        color: white;
        margin-bottom: 30px;
    }

    header h1 {
        font-size: 2.5em;
        margin-bottom: 10px;
    }

    .subtitle {
        opacity: 0.9;
    }

    .card {
        background: white;
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }

    .card h2 {
        color: #333;
        margin-bottom: 20px;
        padding-bottom: 10px;
        border-bottom: 2px solid #eee;
    }

    .summary-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 20px;
    }

    .stat-box {
        text-align: center;
        padding: 20px;
        background: #f8f9fa;
        border-radius: 8px;
    }

    .stat-value {
        font-size: 2.5em;
        font-weight: bold;
        color: #667eea;
    }

    .stat-label {
        color: #666;
        margin-top: 5px;
    }

    .stat-value.success { color: #28a745; }
    .stat-value.warning { color: #ffc107; }
    .stat-value.danger { color: #dc3545; }

    .progress-bar {
        background: #e9ecef;
        border-radius: 10px;
        height: 20px;
        overflow: hidden;
        margin: 10px 0;
    }

    .progress-fill {
        height: 100%;
        background: linear-gradient(90deg, #667eea, #764ba2);
        transition: width 0.3s;
    }

    table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 15px;
    }

    th, td {
        padding: 12px;
        text-align: left;
        border-bottom: 1px solid #eee;
    }

    th {
        background: #f8f9fa;
        font-weight: 600;
        color: #333;
    }

    tr:hover {
        background: #f8f9fa;
    }

    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85em;
        font-weight: 500;
    }

    .status-pass {
        background: #d4edda;
        color: #155724;
    }

    .status-fail {
        background: #f8d7da;
        color: #721c24;
    }

    .category-stats {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 20px;
    }

    .category-card {
        background: #f8f9fa;
        padding: 20px;
        border-radius: 8px;
        border-left: 4px solid #667eea;
    }

    .category-card h3 {
        color: #333;
        margin-bottom: 10px;
    }

    .target-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 15px;
        background: #f8f9fa;
        border-radius: 8px;
        margin-bottom: 10px;
    }

    .target-status {
        font-size: 1.5em;
    }

    .target-info {
        flex: 1;
        margin-left: 15px;
    }

    .target-name {
        font-weight: 600;
        color: #333;
    }

    .target-values {
        color: #666;
        font-size: 0.9em;
    }

    .recommendation-item {
        display: flex;
        align-items: flex-start;
        padding: 15px;
        background: #fff3cd;
        border-radius: 8px;
        margin-bottom: 10px;
        border-left: 4px solid #ffc107;
    }

    .recommendation-item::before {
        content: "💡";
        margin-right: 10px;
    }

    footer {
        text-align: center;
        color: white;
        margin-top: 30px;
        padding: 20px;
        opacity: 0.9;
    }

    .failure-tag {
        display: inline-block;
        padding: 4px 8px;
        background: #e9ecef;
        border-radius: 4px;
        margin: 2px;
        font-size: 0.85em;
    }

    @media (max-width: 768px) {
        .summary-grid {
            grid-template-columns: repeat(2, 1fr);
        }
    }
</style>"""

    def _generate_summary_card(self, eval_result: EvalResult) -> str:
        """生成摘要卡片"""
        pass_rate = eval_result.pass_rate
        avg_score = eval_result.average_score
        avg_time = eval_result.average_response_time

        pass_rate_class = "success" if pass_rate >= 85 else "warning" if pass_rate >= 70 else "danger"
        score_class = "success" if avg_score >= 80 else "warning" if avg_score >= 60 else "danger"
        time_class = "success" if avg_time < 500 else "warning" if avg_time < 1000 else "danger"

        return f"""
        <div class="card">
            <h2>📈 总体概览</h2>
            <div class="summary-grid">
                <div class="stat-box">
                    <div class="stat-value {pass_rate_class}">{pass_rate:.1f}%</div>
                    <div class="stat-label">通过率</div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {pass_rate}%"></div>
                    </div>
                </div>
                <div class="stat-box">
                    <div class="stat-value {score_class}">{avg_score:.1f}</div>
                    <div class="stat-label">平均得分</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value {time_class}">{avg_time:.0f}ms</div>
                    <div class="stat-label">平均响应时间</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">{eval_result.total_cases}</div>
                    <div class="stat-label">总用例数</div>
                </div>
            </div>
            <div style="margin-top: 20px; display: flex; gap: 20px;">
                <div class="stat-box" style="flex: 1;">
                    <div class="stat-value success">{eval_result.passed_cases}</div>
                    <div class="stat-label">通过用例</div>
                </div>
                <div class="stat-box" style="flex: 1;">
                    <div class="stat-value danger">{eval_result.failed_cases}</div>
                    <div class="stat-label">失败用例</div>
                </div>
            </div>
        </div>"""

    def _generate_category_stats(self, eval_result: EvalResult) -> str:
        """生成分类统计"""
        category_stats = self._compute_category_stats(eval_result.case_results)

        category_names = {
            "simple": "🟢 简单任务",
            "medium": "🟡 中等任务",
            "complex": "🔴 复杂任务",
            "edge": "🔵 边界/异常",
        }

        cards = []
        for cat_id, stats in category_stats.items():
            name = category_names.get(cat_id, cat_id)
            pass_rate = stats.get("pass_rate", 0)
            pass_class = "success" if pass_rate >= 85 else "warning" if pass_rate >= 70 else "danger"

            cards.append(f"""
            <div class="category-card">
                <h3>{name}</h3>
                <p>用例数：<strong>{stats.get('total', 0)}</strong></p>
                <p>通过率：<span class="stat-value {pass_class}" style="font-size: 1.2em;">{pass_rate:.1f}%</span></p>
                <p>平均响应时间：<strong>{stats.get('avg_time', 0):.1f}ms</strong></p>
            </div>""")

        return f"""
        <div class="card">
            <h2>📋 分类统计</h2>
            <div class="category-stats">
                {''.join(cards)}
            </div>
        </div>"""

    def _generate_failure_breakdown(self, eval_result: EvalResult) -> str:
        """生成失败原因分布"""
        if not eval_result.failure_breakdown:
            return ""

        failure_names = {
            FailureReason.WRONG_AGENT: "路由错误",
            FailureReason.TIMEOUT: "超时",
            FailureReason.WRONG_OUTPUT: "输出错误",
            FailureReason.SKILL_FAILED: "技能失败",
            FailureReason.ASSERTION_FAILED: "断言失败",
            FailureReason.EXCEPTION: "异常",
            FailureReason.HANDOFF_FAILED: "Handoff 失败",
            FailureReason.CONTEXT_LOST: "上下文丢失",
        }

        tags = []
        for reason, count in eval_result.failure_breakdown.items():
            name = failure_names.get(reason, str(reason))
            tags.append(f'<span class="failure-tag">{name}: {count}</span>')

        return f"""
        <div class="card">
            <h2>❌ 失败原因分布</h2>
            <div>{''.join(tags)}</div>
        </div>"""

    def _generate_targets_section(self, eval_result: EvalResult) -> str:
        """生成目标达成情况"""
        targets = self._compute_targets(eval_result)

        items = []
        for name, info in targets.items():
            status = "✅" if info["achieved"] else "❌"
            items.append(f"""
            <div class="target-item">
                <span class="target-status">{status}</span>
                <div class="target-info">
                    <div class="target-name">{name}</div>
                    <div class="target-values">目标：{info['target']} | 实际：{info['actual']}</div>
                </div>
            </div>""")

        return f"""
        <div class="card">
            <h2>🎯 目标达成情况</h2>
            {''.join(items)}
        </div>"""

    def _generate_detailed_results(self, eval_result: EvalResult) -> str:
        """生成详细结果表格"""
        rows = []
        for result in eval_result.case_results:
            status_class = "pass" if result.passed else "fail"
            status_text = "通过" if result.passed else "失败"

            failure_info = ""
            if not result.passed:
                failure_info = f'<span style="color: #dc3545;">{result.failure_details or result.failure_reason or ""}</span>'

            rows.append(f"""
            <tr>
                <td><strong>{result.case_id}</strong></td>
                <td>{result.case_name}</td>
                <td><span class="status-badge status-{status_class}">{status_text}</span></td>
                <td>{result.response_time_ms:.1f}ms</td>
                <td>{result.score:.1f}</td>
                <td>{failure_info}</td>
            </tr>""")

        return f"""
        <div class="card">
            <h2>📝 详细结果</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>名称</th>
                        <th>状态</th>
                        <th>响应时间</th>
                        <th>得分</th>
                        <th>失败原因</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>
        </div>"""

    def _generate_recommendations(self, eval_result: EvalResult) -> str:
        """生成改进建议"""
        recommendations = self._generate_recommendation_list(eval_result)

        if not recommendations:
            recommendations = ["表现优秀，继续保持！"]

        items = [f'<div class="recommendation-item">{rec}</div>' for rec in recommendations]

        return f"""
        <div class="card">
            <h2>💡 改进建议</h2>
            {''.join(items)}
        </div>"""

    def _compute_category_stats(self, case_results: List[CaseResult]) -> Dict[str, Dict[str, Any]]:
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

        for category, data in stats.items():
            data["pass_rate"] = data["passed"] / data["total"] * 100 if data["total"] > 0 else 0
            data["avg_time"] = data["total_time"] / data["total"] if data["total"] > 0 else 0

        return stats

    def _compute_targets(self, eval_result: EvalResult) -> Dict[str, Dict[str, Any]]:
        """计算目标达成情况"""
        return {
            "响应速度": {
                "target": "<500ms",
                "actual": f"{eval_result.average_response_time:.1f}ms",
                "achieved": eval_result.average_response_time < 500,
            },
            "通过率": {
                "target": ">85%",
                "actual": f"{eval_result.pass_rate:.1f}%",
                "achieved": eval_result.pass_rate >= 85,
            },
            "平均得分": {
                "target": ">80",
                "actual": f"{eval_result.average_score:.1f}",
                "achieved": eval_result.average_score >= 80,
            },
        }

    def _generate_recommendation_list(self, eval_result: EvalResult) -> List[str]:
        """生成建议列表"""
        recommendations = []

        failure_breakdown = eval_result.failure_breakdown

        if FailureReason.WRONG_AGENT in failure_breakdown:
            recommendations.append("优化 Agent 路由策略，提高意图分类准确性")

        if FailureReason.TIMEOUT in failure_breakdown:
            recommendations.append("优化响应速度，考虑使用更快的模型或优化 prompt")

        if FailureReason.WRONG_OUTPUT in failure_breakdown:
            recommendations.append("改进模型输出质量，优化 prompt 和 Few-shot 示例")

        if eval_result.pass_rate < 70:
            recommendations.append("整体通过率较低，建议全面检查系统配置和模型设置")
        elif eval_result.pass_rate < 85:
            recommendations.append("通过率有待提升，重点关注失败用例较多的类别")

        if eval_result.average_response_time > 500:
            recommendations.append("平均响应时间超过目标值，建议优化 Talker 响应速度")

        return recommendations

    def export(
        self,
        eval_result: EvalResult,
        file_path: Optional[str] = None,
    ) -> str:
        """
        导出 HTML 报告到文件

        Args:
            eval_result: 评测结果
            file_path: 输出文件路径

        Returns:
            str: 输出文件路径
        """
        if file_path is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            file_path = f"evals/results/eval_report_{timestamp}.html"

        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(self.generate(eval_result))

        return str(file_path)
