"""
Metrics Collector - 指标收集器
用于收集和暴露系统指标
"""
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MetricPoint:
    """指标数据点"""
    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    labels: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """
    指标收集器

    收集和聚合系统指标
    """

    def __init__(self):
        # 计数器
        self._counters: Dict[str, float] = defaultdict(float)
        # 直方图
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        # 仪表盘
        self._gauges: Dict[str, float] = {}
        # 标签
        self._labels: Dict[str, Dict[str, str]] = defaultdict(dict)

        # 指标历史
        self._history: List[MetricPoint] = []
        self._max_history = 10000

    def counter(self, name: str, value: float = 1, labels: Optional[Dict[str, str]] = None) -> None:
        """
        增加计数器

        Args:
            name: 指标名称
            value: 增加的值
            labels: 标签
        """
        key = self._make_key(name, labels)
        self._counters[key] += value
        if labels:
            self._labels[key] = labels

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """
        设置仪表盘值

        Args:
            name: 指标名称
            value: 值
            labels: 标签
        """
        key = self._make_key(name, labels)
        self._gauges[key] = value
        if labels:
            self._labels[key] = labels

    def histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """
        记录直方图值

        Args:
            name: 指标名称
            value: 值
            labels: 标签
        """
        key = self._make_key(name, labels)
        self._histograms[key].append(value)
        # 只保留最近的1000个值
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-1000:]
        if labels:
            self._labels[key] = labels

    def record_latency(
        self,
        agent: str,
        operation: str,
        latency_ms: float,
        success: bool = True,
    ) -> None:
        """记录延迟"""
        labels = {"agent": agent, "operation": operation, "success": str(success)}
        self.histogram("latency_ms", latency_ms, labels)
        self.counter("requests_total", 1, labels)

    def record_handoff(self, from_agent: str, to_agent: str, reason: str) -> None:
        """记录Handoff"""
        labels = {"from": from_agent, "to": to_agent, "reason": reason}
        self.counter("handoffs_total", 1, labels)

    def record_skill_invocation(
        self,
        skill_name: str,
        success: bool,
        latency_ms: float,
    ) -> None:
        """记录技能调用"""
        labels = {"skill": skill_name, "success": str(success)}
        self.counter("skill_invocations_total", 1, labels)
        self.histogram("skill_latency_ms", latency_ms, labels)

    def _make_key(self, name: str, labels: Optional[Dict[str, str]] = None) -> str:
        """生成指标键"""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """获取计数器值"""
        key = self._make_key(name, labels)
        return self._counters.get(key, 0)

    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[float]:
        """获取仪表盘值"""
        key = self._make_key(name, labels)
        return self._gauges.get(key)

    def get_histogram_stats(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> Dict[str, float]:
        """获取直方图统计"""
        key = self._make_key(name, labels)
        values = self._histograms.get(key, [])

        if not values:
            return {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0}

        sorted_values = sorted(values)
        count = len(sorted_values)

        return {
            "count": count,
            "sum": sum(sorted_values),
            "avg": sum(sorted_values) / count,
            "min": sorted_values[0],
            "max": sorted_values[-1],
            "p50": sorted_values[int(count * 0.5)],
            "p90": sorted_values[int(count * 0.9)],
            "p95": sorted_values[int(count * 0.95)],
            "p99": sorted_values[int(count * 0.99)] if count > 10 else sorted_values[-1],
        }

    def get_all_metrics(self) -> Dict[str, Any]:
        """获取所有指标"""
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                key: self.get_histogram_stats(key.split("{")[0], None)
                for key in self._histograms
            },
        }

    def export_prometheus(self) -> str:
        """导出Prometheus格式"""
        lines = []

        # 导出计数器
        for key, value in self._counters.items():
            name = key.split("{")[0]
            labels = self._labels.get(key, {})
            labels_str = "".join(f'{k}="{v}"' for k, v in labels.items())
            if labels_str:
                lines.append(f"{name}{{{labels_str}}} {value}")
            else:
                lines.append(f"{name} {value}")

        # 导出仪表盘
        for key, value in self._gauges.items():
            name = key.split("{")[0]
            labels = self._labels.get(key, {})
            labels_str = "".join(f'{k}="{v}"' for k, v in labels.items())
            if labels_str:
                lines.append(f"{name}{{{labels_str}}} {value}")
            else:
                lines.append(f"{name} {value}")

        return "\n".join(lines)

    def clear(self) -> None:
        """清空所有指标"""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._history.clear()


# 全局指标收集器
_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """获取全局指标收集器"""
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector
