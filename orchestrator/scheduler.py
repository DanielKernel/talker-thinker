"""
Task Scheduler - 任务调度器
基于复杂度和优先级的任务调度
"""
import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from context.types import Task, TaskComplexity, TaskStatus


class Priority(Enum):
    """任务优先级"""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass
class ScheduledTask:
    """调度任务"""
    task: Task
    priority: Priority
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


class TaskScheduler:
    """
    任务调度器

    支持：
    - 基于复杂度的调度
    - 基于优先级的调度
    - 并发控制
    """

    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent

        # 任务队列
        self._queues: Dict[Priority, asyncio.Queue] = {
            Priority.CRITICAL: asyncio.Queue(),
            Priority.HIGH: asyncio.Queue(),
            Priority.NORMAL: asyncio.Queue(),
            Priority.LOW: asyncio.Queue(),
        }

        # 活动任务
        self._active_tasks: Dict[str, ScheduledTask] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # 统计
        self._stats = {
            "total_scheduled": 0,
            "total_completed": 0,
            "total_failed": 0,
            "queue_wait_time_ms": 0,
        }

    async def schedule(
        self,
        task: Task,
        priority: Priority = Priority.NORMAL,
    ) -> str:
        """
        调度任务

        Args:
            task: 任务对象
            priority: 优先级

        Returns:
            str: 任务ID
        """
        scheduled = ScheduledTask(task=task, priority=priority)
        await self._queues[priority].put(scheduled)
        self._stats["total_scheduled"] += 1

        return task.task_id

    async def get_next_task(self) -> Optional[ScheduledTask]:
        """
        获取下一个待执行任务（按优先级）

        Returns:
            Optional[ScheduledTask]: 下一个任务或None
        """
        # 按优先级顺序检查队列
        for priority in Priority:
            queue = self._queues[priority]
            if not queue.empty():
                try:
                    scheduled = queue.get_nowait()
                    scheduled.started_at = time.time()
                    self._active_tasks[scheduled.task.task_id] = scheduled

                    # 记录等待时间
                    wait_time = (scheduled.started_at - scheduled.created_at) * 1000
                    self._stats["queue_wait_time_ms"] += wait_time

                    return scheduled
                except asyncio.QueueEmpty:
                    continue

        return None

    async def complete_task(self, task_id: str, success: bool = True) -> None:
        """
        标记任务完成

        Args:
            task_id: 任务ID
            success: 是否成功
        """
        if task_id in self._active_tasks:
            scheduled = self._active_tasks[task_id]
            scheduled.completed_at = time.time()
            del self._active_tasks[task_id]

            if success:
                self._stats["total_completed"] += 1
            else:
                self._stats["total_failed"] += 1

    def get_queue_sizes(self) -> Dict[str, int]:
        """获取各队列大小"""
        return {
            priority.name: self._queues[priority].qsize()
            for priority in Priority
        }

    def get_active_count(self) -> int:
        """获取活动任务数"""
        return len(self._active_tasks)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = self._stats["total_scheduled"]
        return {
            **self._stats,
            "active_tasks": self.get_active_count(),
            "queue_sizes": self.get_queue_sizes(),
            "avg_wait_time_ms": (
                self._stats["queue_wait_time_ms"] / max(total, 1)
            ),
        }


class ComplexityBasedScheduler:
    """
    基于复杂度的调度器

    根据任务复杂度自动选择处理策略
    """

    def __init__(self):
        self.rules = {
            TaskComplexity.SIMPLE: {
                "agent": "talker",
                "timeout_ms": 500,
                "max_tokens": 200,
            },
            TaskComplexity.MEDIUM: {
                "agent": "talker",
                "timeout_ms": 2000,
                "max_tokens": 500,
            },
            TaskComplexity.COMPLEX: {
                "agent": "thinker",
                "timeout_ms": 30000,
                "max_tokens": 2000,
                "requires_planning": True,
            },
        }

    def get_strategy(self, complexity: TaskComplexity) -> Dict[str, Any]:
        """获取处理策略"""
        return self.rules.get(complexity, self.rules[TaskComplexity.SIMPLE])

    def evaluate_complexity(self, task: Task) -> TaskComplexity:
        """
        评估任务复杂度

        Args:
            task: 任务对象

        Returns:
            TaskComplexity: 复杂度级别
        """
        text = task.user_input.lower()

        # 特征评分
        length_score = min(len(text) / 100, 1.0)

        # 复杂关键词
        complex_keywords = [
            "分析", "比较", "评估", "设计", "规划", "优化",
            "为什么", "怎么理解", "深入", "详细", "步骤",
        ]
        keyword_score = sum(0.2 for k in complex_keywords if k in text)
        keyword_score = min(keyword_score, 1.0)

        # 问题数量（根据问号数量）
        question_count = text.count("?") + text.count("？")
        question_score = min(question_count * 0.3, 1.0)

        # 综合评分
        total_score = length_score * 0.3 + keyword_score * 0.4 + question_score * 0.3

        if total_score < 0.3:
            return TaskComplexity.SIMPLE
        elif total_score < 0.7:
            return TaskComplexity.MEDIUM
        else:
            return TaskComplexity.COMPLEX
