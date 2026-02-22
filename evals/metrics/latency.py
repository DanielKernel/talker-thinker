"""
延迟指标 (Latency Metrics)

收集和统计响应时间相关指标:
- TTFT (Time To First Token): 首 token 时间
- TPS (Tokens Per Second): 每秒 token 数
- Response Time: 总响应时间
"""
import statistics
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class LatencyType(str, Enum):
    """延迟类型"""
    TTFT = "ttft"           # Time To First Token
    TPS = "tps"             # Tokens Per Second
    RESPONSE_TIME = "response_time"  # 总响应时间


@dataclass
class LatencyMetrics:
    """
    延迟指标收集器

    用于收集和统计延迟相关指标
    """
    response_times: List[float] = field(default_factory=list)
    ttft_values: List[float] = field(default_factory=list)
    tps_values: List[float] = field(default_factory=list)
    tokens_used: List[int] = field(default_factory=list)

    # 按类别分组统计
    by_category: Dict[str, List[float]] = field(default_factory=dict)
    by_agent: Dict[str, List[float]] = field(default_factory=dict)

    def record_response_time(
        self,
        response_time_ms: float,
        category: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> None:
        """记录响应时间"""
        self.response_times.append(response_time_ms)

        if category:
            if category not in self.by_category:
                self.by_category[category] = []
            self.by_category[category].append(response_time_ms)

        if agent:
            if agent not in self.by_agent:
                self.by_agent[agent] = []
            self.by_agent[agent].append(response_time_ms)

    def record_ttft(self, ttft_ms: float) -> None:
        """记录首 token 时间"""
        self.ttft_values.append(ttft_ms)

    def record_tps(self, tps: float) -> None:
        """记录每秒 token 数"""
        self.tps_values.append(tps)

    def record_tokens(self, tokens: int) -> None:
        """记录 token 使用量"""
        self.tokens_used.append(tokens)

    # ========= 统计方法 =========

    @property
    def avg_response_time(self) -> float:
        """平均响应时间 (ms)"""
        if not self.response_times:
            return 0.0
        return statistics.mean(self.response_times)

    @property
    def median_response_time(self) -> float:
        """中位数响应时间 (ms)"""
        if not self.response_times:
            return 0.0
        return statistics.median(self.response_times)

    @property
    def p95_response_time(self) -> float:
        """P95 响应时间 (ms)"""
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        p95_idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(p95_idx, len(sorted_times) - 1)]

    @property
    def p99_response_time(self) -> float:
        """P99 响应时间 (ms)"""
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        p99_idx = int(len(sorted_times) * 0.99)
        return sorted_times[min(p99_idx, len(sorted_times) - 1)]

    @property
    def min_response_time(self) -> float:
        """最小响应时间 (ms)"""
        if not self.response_times:
            return 0.0
        return min(self.response_times)

    @property
    def max_response_time(self) -> float:
        """最大响应时间 (ms)"""
        if not self.response_times:
            return 0.0
        return max(self.response_times)

    @property
    def std_response_time(self) -> float:
        """响应时间标准差"""
        if len(self.response_times) < 2:
            return 0.0
        return statistics.stdev(self.response_times)

    @property
    def avg_ttft(self) -> float:
        """平均首 token 时间 (ms)"""
        if not self.ttft_values:
            return 0.0
        return statistics.mean(self.ttft_values)

    @property
    def avg_tps(self) -> float:
        """平均每秒 token 数"""
        if not self.tps_values:
            return 0.0
        return statistics.mean(self.tps_values)

    @property
    def total_tokens(self) -> int:
        """总 token 使用量"""
        return sum(self.tokens_used)

    # ========= 按类别统计 =========

    def get_category_stats(self, category: str) -> Dict[str, float]:
        """获取指定类别的统计信息"""
        times = self.by_category.get(category, [])
        if not times:
            return {
                "count": 0,
                "avg": 0.0,
                "median": 0.0,
                "p95": 0.0,
                "min": 0.0,
                "max": 0.0,
            }

        return {
            "count": len(times),
            "avg": statistics.mean(times),
            "median": statistics.median(times),
            "p95": sorted(times)[int(len(times) * 0.95)] if len(times) > 1 else times[0],
            "min": min(times),
            "max": max(times),
        }

    def get_agent_stats(self, agent: str) -> Dict[str, float]:
        """获取指定 Agent 的统计信息"""
        times = self.by_agent.get(agent, [])
        if not times:
            return {
                "count": 0,
                "avg": 0.0,
                "median": 0.0,
                "p95": 0.0,
            }

        return {
            "count": len(times),
            "avg": statistics.mean(times),
            "median": statistics.median(times),
            "p95": sorted(times)[int(len(times) * 0.95)] if len(times) > 1 else times[0],
        }

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "summary": {
                "total_samples": len(self.response_times),
                "avg_response_time_ms": round(self.avg_response_time, 2),
                "median_response_time_ms": round(self.median_response_time, 2),
                "p95_response_time_ms": round(self.p95_response_time, 2),
                "p99_response_time_ms": round(self.p99_response_time, 2),
                "min_response_time_ms": round(self.min_response_time, 2),
                "max_response_time_ms": round(self.max_response_time, 2),
                "std_response_time_ms": round(self.std_response_time, 2),
            },
            "streaming": {
                "avg_ttft_ms": round(self.avg_ttft, 2),
                "avg_tps": round(self.avg_tps, 2),
            },
            "tokens": {
                "total": self.total_tokens,
                "avg_per_request": round(self.total_tokens / len(self.tokens_used), 1) if self.tokens_used else 0,
            },
            "by_category": {k: self.get_category_stats(k) for k in self.by_category},
            "by_agent": {k: self.get_agent_stats(k) for k in self.by_agent},
        }
