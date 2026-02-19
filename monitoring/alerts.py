"""
Alert Manager - 告警管理器
"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

from config import settings


@dataclass
class Alert:
    """告警"""
    alert_type: str
    severity: str  # "info", "warning", "critical"
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    resolved: bool = False


class AlertManager:
    """
    告警管理器

    支持：
    - 基于阈值的告警
    - Webhook通知
    - 告警历史
    """

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or settings.ALERT_WEBHOOK_URL

        # 告警规则
        self.rules = {
            "high_latency": {
                "threshold": 5000.0,  # 5秒
                "condition": "latency_p95 > threshold",
                "severity": "warning",
            },
            "high_error_rate": {
                "threshold": 0.1,  # 10%
                "condition": "error_rate > threshold",
                "severity": "critical",
            },
            "skill_failure": {
                "threshold": 3,  # 3次失败
                "window_seconds": 300,  # 5分钟
                "condition": "failures > threshold in window",
                "severity": "warning",
            },
        }

        # 告警历史
        self._alerts: List[Alert] = []
        self._max_alerts = 1000

        # 通知回调
        self._callbacks: List[Callable] = []

    def add_callback(self, callback: Callable) -> None:
        """添加通知回调"""
        self._callbacks.append(callback)

    async def check_and_alert(self, metrics: Dict[str, Any]) -> List[Alert]:
        """
        检查指标并触发告警

        Args:
            metrics: 指标数据

        Returns:
            List[Alert]: 触发的告警列表
        """
        alerts = []

        # 检查延迟
        latency_alert = self._check_latency(metrics)
        if latency_alert:
            alerts.append(latency_alert)

        # 检查错误率
        error_alert = self._check_error_rate(metrics)
        if error_alert:
            alerts.append(error_alert)

        # 发送告警
        for alert in alerts:
            await self._send_alert(alert)

        return alerts

    def _check_latency(self, metrics: Dict[str, Any]) -> Optional[Alert]:
        """检查延迟"""
        rule = self.rules["high_latency"]
        threshold = rule["threshold"]

        # 获取P95延迟
        latency_stats = metrics.get("histograms", {}).get("latency_ms", {})
        p95 = latency_stats.get("p95", 0)

        if p95 > threshold:
            return Alert(
                alert_type="high_latency",
                severity=rule["severity"],
                message=f"P95延迟过高: {p95:.0f}ms (阈值: {threshold}ms)",
                details={"p95_latency_ms": p95, "threshold_ms": threshold},
            )

        return None

    def _check_error_rate(self, metrics: Dict[str, Any]) -> Optional[Alert]:
        """检查错误率"""
        rule = self.rules["high_error_rate"]
        threshold = rule["threshold"]

        # 计算错误率
        counters = metrics.get("counters", {})
        total = 0
        errors = 0

        for key, value in counters.items():
            if "requests_total" in key:
                total += value
                if "success=False" in key:
                    errors += value

        if total > 0:
            error_rate = errors / total
            if error_rate > threshold:
                return Alert(
                    alert_type="high_error_rate",
                    severity=rule["severity"],
                    message=f"错误率过高: {error_rate*100:.1f}% (阈值: {threshold*100:.1f}%)",
                    details={"error_rate": error_rate, "errors": errors, "total": total},
                )

        return None

    async def _send_alert(self, alert: Alert) -> None:
        """发送告警"""
        # 记录告警
        self._alerts.append(alert)
        if len(self._alerts) > self._max_alerts:
            self._alerts = self._alerts[-self._max_alerts:]

        # 调用回调
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(alert)
                else:
                    callback(alert)
            except Exception:
                pass

        # 发送Webhook
        if self.webhook_url:
            await self._send_webhook(alert)

    async def _send_webhook(self, alert: Alert) -> None:
        """发送Webhook通知"""
        if not HAS_AIOHTTP:
            return

        payload = {
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "message": alert.message,
            "details": alert.details,
            "timestamp": alert.timestamp,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        # 记录失败但不要抛出异常
                        pass
        except Exception:
            pass

    def get_alerts(
        self,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """获取告警历史"""
        alerts = self._alerts

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        return [
            {
                "alert_type": a.alert_type,
                "severity": a.severity,
                "message": a.message,
                "details": a.details,
                "timestamp": a.timestamp,
                "resolved": a.resolved,
            }
            for a in alerts[-limit:]
        ]

    def resolve_alert(self, index: int) -> bool:
        """解决告警"""
        if 0 <= index < len(self._alerts):
            self._alerts[index].resolved = True
            return True
        return False

    def clear_alerts(self) -> None:
        """清空告警"""
        self._alerts.clear()


# 全局告警管理器
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """获取全局告警管理器"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager
