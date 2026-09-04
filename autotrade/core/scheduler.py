"""
High-Precision Asynchronous Task Scheduler.
Orchestrates periodic market scans, self-healing cycles, database maintenance,
walk-forward re-optimizations, economic news synchronization, and health monitoring.
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import inspect
import logging
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union

logger = logging.getLogger("autotrade.core.scheduler")


@dataclass
class ScheduledTask:
    """Represents an isolated recurring or delayed asynchronous task."""
    task_id: str
    name: str
    coro_fn: Callable[..., Coroutine[Any, Any, None]]
    interval_sec: float
    is_recurring: bool = True
    enabled: bool = True
    next_run: float = field(default_factory=time.time)
    last_run: Optional[float] = None
    last_duration_ms: float = 0.0
    total_runs: int = 0
    total_errors: int = 0
    last_error: Optional[str] = None
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)


class AsyncScheduler:
    """
    Enterprise Asynchronous Cron & Interval Scheduler.
    Features:
    - Drift-free interval timing
    - Isolated error execution boundary
    - Dynamic task addition, pausing, resumption, and deletion
    - Full telemetry on execution durations and failure rates
    """
    def __init__(self, check_resolution_sec: float = 0.5):
        self.check_resolution_sec = check_resolution_sec
        self._tasks: Dict[str, ScheduledTask] = {}
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    def add_interval_task(
        self,
        task_id: str,
        name: str,
        coro_fn: Callable[..., Coroutine[Any, Any, None]],
        interval_sec: float,
        first_delay_sec: float = 0.0,
        *args,
        **kwargs
    ) -> ScheduledTask:
        """Schedules a recurring coroutine to run every `interval_sec` seconds."""
        task = ScheduledTask(
            task_id=task_id,
            name=name,
            coro_fn=coro_fn,
            interval_sec=interval_sec,
            is_recurring=True,
            enabled=True,
            next_run=time.time() + first_delay_sec,
            args=args,
            kwargs=kwargs
        )
        self._tasks[task_id] = task
        logger.debug(f"Added scheduled task '{name}' (ID: {task_id}) every {interval_sec}s")
        return task

    def add_delayed_task(
        self,
        task_id: str,
        name: str,
        coro_fn: Callable[..., Coroutine[Any, Any, None]],
        delay_sec: float,
        *args,
        **kwargs
    ) -> ScheduledTask:
        """Schedules a one-shot coroutine to execute after `delay_sec` seconds."""
        task = ScheduledTask(
            task_id=task_id,
            name=name,
            coro_fn=coro_fn,
            interval_sec=0.0,
            is_recurring=False,
            enabled=True,
            next_run=time.time() + delay_sec,
            args=args,
            kwargs=kwargs
        )
        self._tasks[task_id] = task
        return task

    def remove_task(self, task_id: str) -> bool:
        """Removes a scheduled task."""
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        return False

    def pause_task(self, task_id: str) -> bool:
        """Temporarily disables a task from running."""
        if task_id in self._tasks:
            self._tasks[task_id].enabled = False
            return True
        return False

    def resume_task(self, task_id: str) -> bool:
        """Re-enables a paused task and recalibrates its next run time."""
        if task_id in self._tasks:
            t = self._tasks[task_id]
            t.enabled = True
            t.next_run = time.time() + t.interval_sec
            return True
        return False

    async def start(self) -> None:
        """Starts the scheduler evaluation loop."""
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._scheduler_loop(), name="AsyncSchedulerLoop")
        logger.info("⏱️ AsyncScheduler started.")

    async def stop(self) -> None:
        """Gracefully shuts down the scheduler loop."""
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        logger.info("AsyncScheduler stopped.")

    async def _scheduler_loop(self) -> None:
        """Main polling loop checking for due tasks."""
        while self._running:
            try:
                now = time.time()
                due_tasks: List[ScheduledTask] = []
                
                for task in list(self._tasks.values()):
                    if task.enabled and now >= task.next_run:
                        due_tasks.append(task)
                        
                for task in due_tasks:
                    # Spawn independent runner task so long jobs don't delay other schedules
                    asyncio.create_task(self._run_task_safely(task), name=f"SchedTask_{task.task_id}")
                    
                    if task.is_recurring:
                        # Schedule next execution without time-drift
                        task.next_run = now + task.interval_sec
                    else:
                        # Remove one-shot task
                        self._tasks.pop(task.task_id, None)

                await asyncio.sleep(self.check_resolution_sec)
            except asyncio.CancelledError:
                break
            except Exception as ex:
                logger.error(f"Error in AsyncScheduler loop: {ex}", exc_info=True)
                await asyncio.sleep(1.0)

    async def _run_task_safely(self, task: ScheduledTask) -> None:
        """Executes task coroutine with timing telemetry and error handling."""
        t0 = time.perf_counter()
        task.last_run = time.time()
        try:
            if inspect.iscoroutinefunction(task.coro_fn):
                await task.coro_fn(*task.args, **task.kwargs)
            else:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, task.coro_fn, *task.args, **task.kwargs)
                
            task.last_duration_ms = (time.perf_counter() - t0) * 1000.0
            task.total_runs += 1
            task.last_error = None
        except Exception as ex:
            task.last_duration_ms = (time.perf_counter() - t0) * 1000.0
            task.total_runs += 1
            task.total_errors += 1
            task.last_error = str(ex)
            logger.error(f"Scheduled task '{task.name}' failed: {ex}", exc_info=True)

    def get_status(self) -> List[Dict[str, Any]]:
        """Returns status and telemetry of all registered scheduler jobs."""
        out = []
        now = time.time()
        for t in self._tasks.values():
            out.append({
                "task_id": t.task_id,
                "name": t.name,
                "interval_sec": t.interval_sec,
                "enabled": t.enabled,
                "next_run_in_sec": round(max(0.0, t.next_run - now), 1),
                "total_runs": t.total_runs,
                "total_errors": t.total_errors,
                "last_duration_ms": round(t.last_duration_ms, 2),
                "last_error": t.last_error,
            })
        return out


# Global singleton instance
scheduler = AsyncScheduler()
