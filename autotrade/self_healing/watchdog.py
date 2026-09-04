"""
Runtime Module Supervisor & Crash Containment Watchdog.
Monitors critical trading tasks, catches unexpected exceptions,
maintains subsystem uptime, and restarts failed modules with exponential backoff.
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional

from autotrade.core.event_bus import event_bus, EventType, EventPriority

logger = logging.getLogger("autotrade.self_healing.watchdog")


@dataclass
class SupervisedModule:
    """Represents an active, supervised asynchronous runtime module."""
    name: str
    target_coro_fn: Callable[..., Coroutine[Any, Any, None]]
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    max_restarts: int = 10
    restart_count: int = 0
    backoff_sec: float = 1.0
    max_backoff_sec: float = 60.0
    is_running: bool = False
    last_error: Optional[str] = None
    last_crash_time: Optional[float] = None
    task: Optional[asyncio.Task] = None


class ModuleWatchdog:
    """
    Supervises background worker loops and services across the 9 layers.
    Ensures 24/7 continuous operation without system crash if an individual coroutine fails.
    """
    def __init__(self, check_interval_sec: float = 5.0):
        self.check_interval_sec = check_interval_sec
        self._modules: Dict[str, SupervisedModule] = {}
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    def register(
        self,
        name: str,
        target_coro_fn: Callable[..., Coroutine[Any, Any, None]],
        max_restarts: int = 10,
        backoff_sec: float = 2.0,
        *args,
        **kwargs
    ) -> SupervisedModule:
        """Registers a coroutine worker under watchdog supervision."""
        mod = SupervisedModule(
            name=name,
            target_coro_fn=target_coro_fn,
            args=args,
            kwargs=kwargs,
            max_restarts=max_restarts,
            backoff_sec=backoff_sec
        )
        self._modules[name] = mod
        logger.info(f"Registered module '{name}' with Watchdog (max restarts: {max_restarts})")
        return mod

    async def start(self) -> None:
        """Starts all registered supervised modules and launches watchdog monitoring loop."""
        if self._running:
            return
        self._running = True
        
        # Start each module
        for mod in self._modules.values():
            self._spawn_module_task(mod)
            
        self._monitor_task = asyncio.create_task(self._supervision_loop(), name="WatchdogMonitorLoop")
        logger.info(f"🛡️ Module Watchdog active. Supervising {len(self._modules)} modules.")

    async def stop(self) -> None:
        """Gracefully halts all supervised modules and watchdog loop."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        for mod in self._modules.values():
            if mod.task and not mod.task.done():
                mod.task.cancel()
                try:
                    await mod.task
                except asyncio.CancelledError:
                    pass
            mod.is_running = False

        logger.info("Module Watchdog stopped.")

    def _spawn_module_task(self, mod: SupervisedModule) -> None:
        """Spawns an isolated asyncio Task with crash recovery wrapper."""
        mod.is_running = True
        mod.task = asyncio.create_task(self._module_wrapper(mod), name=f"Supervised_{mod.name}")

    async def _module_wrapper(self, mod: SupervisedModule) -> None:
        """Wraps module execution, catching unhandled exceptions and initiating recovery."""
        try:
            await mod.target_coro_fn(*mod.args, **mod.kwargs)
        except asyncio.CancelledError:
            mod.is_running = False
            return
        except Exception as ex:
            mod.is_running = False
            mod.last_crash_time = time.time()
            mod.last_error = str(ex)
            mod.restart_count += 1
            
            logger.critical(
                f"🚨 CRASH in supervised module '{mod.name}' (Crash #{mod.restart_count}/{mod.max_restarts}): {ex}",
                exc_info=True
            )
            
            event_bus.publish(
                EventType.WATCHDOG_RESTART,
                payload={
                    "module": mod.name,
                    "restart_count": mod.restart_count,
                    "error": str(ex)
                },
                priority=EventPriority.CRITICAL,
                source="ModuleWatchdog"
            )

            # Check if restart limit exceeded
            if mod.restart_count > mod.max_restarts:
                logger.critical(f"❌ Module '{mod.name}' exceeded maximum restart threshold. Halting module.")
                event_bus.publish(
                    EventType.TELEGRAM_NOTIFICATION,
                    payload={
                        "message": f"🚨 <b>CRITICAL:</b> Module <code>{mod.name}</code> halted after {mod.max_restarts} crashes!\nError: {ex}",
                        "priority": "CRITICAL"
                    },
                    priority=EventPriority.CRITICAL,
                    source="ModuleWatchdog"
                )
                return

            # Apply exponential backoff delay before restart
            delay = min(mod.backoff_sec * (1.5 ** (mod.restart_count - 1)), mod.max_backoff_sec)
            logger.warning(f"Restarting module '{mod.name}' in {delay:.1f}s...")
            await asyncio.sleep(delay)
            
            if self._running:
                self._spawn_module_task(mod)

    async def _supervision_loop(self) -> None:
        """Periodic loop verifying health of supervised workers."""
        while self._running:
            try:
                for mod in list(self._modules.values()):
                    if mod.is_running and (mod.task is None or mod.task.done()):
                        # Check if it ended unexpectedly
                        if mod.task and mod.task.exception():
                            # Exception handled in wrapper
                            pass
                        elif mod.restart_count <= mod.max_restarts:
                            logger.info(f"Reviving inactive module '{mod.name}'...")
                            self._spawn_module_task(mod)

                await asyncio.sleep(self.check_interval_sec)
            except asyncio.CancelledError:
                break
            except Exception as ex:
                logger.error(f"Error in watchdog supervision loop: {ex}")
                await asyncio.sleep(2.0)

    def get_status(self) -> List[Dict[str, Any]]:
        """Returns diagnostic status of all monitored modules."""
        out = []
        for mod in self._modules.values():
            out.append({
                "name": mod.name,
                "is_running": mod.is_running,
                "restart_count": mod.restart_count,
                "max_restarts": mod.max_restarts,
                "last_error": mod.last_error,
                "last_crash_time": datetime.fromtimestamp(mod.last_crash_time, tz=timezone.utc).isoformat() if mod.last_crash_time else None
            })
        return out
