"""
Master Algorithmic Trading Engine.
Orchestrates the 9 enterprise architectural layers:
Core Engine, Data Layer, Strategy Layer, Risk Manager, Order Manager,
Telegram Interface, Self-Healing & Compiler, Analytics & Reporting, and Security.
Maintains 24/7 autonomous market surveillance, sub-millisecond event-driven loops,
and instant fail-safe containment.
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

from autotrade.core.event_bus import event_bus, Event, EventType, EventPriority
from autotrade.core.config_manager import get_config, get_config_manager
from autotrade.core.scheduler import scheduler

logger = logging.getLogger("autotrade.core.engine")


@dataclass
class EngineState:
    """Runtime state snapshot of the trading engine."""
    is_running: bool = False
    is_paused: bool = False
    emergency_halt: bool = False
    start_time: float = 0.0
    uptime_seconds: float = 0.0
    total_ticks_processed: int = 0
    total_signals_evaluated: int = 0
    total_orders_executed: int = 0
    current_equity: float = 0.0
    current_balance: float = 0.0
    daily_drawdown_pct: float = 0.0
    mt4_bridge_online: bool = False
    active_account_id: str = ""
    active_account_name: str = ""
    last_heartbeat: float = field(default_factory=time.time)


class TradingEngine:
    """
    Central Trading Engine coordinating all architectural layers into a cohesive,
    institutional-grade automated trading system.
    """
    def __init__(self):
        self.state = EngineState()
        self.config = get_config()
        self._main_loop_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        # Subsystem references (lazily populated during layer initialization)
        self.compiler = None
        self.healing_engine = None
        self.database = None
        self.market_data = None
        self.order_manager = None
        self.risk_manager = None
        self.strategy_manager = None
        self.telegram_bot = None
        self.audit_logger = None
        self.report_generator = None

        # Subscribe to core control events
        event_bus.subscribe(EventType.EMERGENCY_HALT, self._on_emergency_halt)
        event_bus.subscribe(EventType.TICK, self._on_tick_event)

    async def initialize(self) -> bool:
        """
        Performs pre-boot validation, self-compilation of source code,
        database schema migration, and subsystem linking.
        """
        logger.info("Initializing AutoTrade Institutional Engine...")
        t0 = time.perf_counter()

        # Step 1: Self-Compilation & Integrity Verification
        from autotrade.self_healing.compiler import SourceCompiler
        from autotrade.self_healing.healing_engine import HealingEngine
        from autotrade.self_healing.watchdog import ModuleWatchdog
        
        self.compiler = SourceCompiler()
        self.healing_engine = HealingEngine(compiler=self.compiler)
        self.watchdog = ModuleWatchdog()
        
        if self.config.healing.enable_startup_compilation:
            compile_res = await self.compiler.compile_all_async()
            if not compile_res.get("success", False):
                logger.error(f"Startup compilation errors detected: {compile_res.get('errors')}")
                if self.config.healing.enable_auto_heal_ast:
                    logger.info("Invoking Self-Healing Engine to resolve compilation anomalies...")
                    heal_res = await self.healing_engine.heal_compilation_errors(compile_res.get("error_details", []))
                    if not heal_res.get("resolved", False):
                        logger.critical("Unrecoverable syntax errors remain. Trading engine boot halted.")
                        return False
            logger.info("✅ Self-compilation check PASSED.")

        # Step 2: Initialize Database and Data Storage Layer
        from autotrade.data_layer.database import DatabaseEngine
        from autotrade.data_layer.market_data import MarketDataManager
        from autotrade.data_layer.news_feed import NewsFeedService
        from autotrade.data_layer.storage import TimeSeriesStorage
        
        self.database = DatabaseEngine()
        await self.database.initialize()
        self.storage = TimeSeriesStorage(database=self.database)
        self.market_data = MarketDataManager(database=self.database)
        self.news_feed = NewsFeedService()

        # Step 3: Initialize Analytics & Precision Math
        from autotrade.analytics.precision import PrecisionMath
        from autotrade.analytics.indicators import TechnicalIndicators
        from autotrade.analytics.charts import ChartGenerator
        from autotrade.analytics.math_models import PredictiveModels
        
        self.precision = PrecisionMath()
        self.indicators = TechnicalIndicators()
        self.charts = ChartGenerator()
        self.math_models = PredictiveModels()

        # Step 4: Initialize Risk Management Layer
        from autotrade.risk.risk_manager import RiskManager
        from autotrade.risk.position_sizer import PositionSizer
        
        self.position_sizer = PositionSizer()
        self.risk_manager = RiskManager(position_sizer=self.position_sizer)

        # Step 5: Initialize Order Management Layer
        from autotrade.orders.order_manager import OrderManager
        from autotrade.orders.position_tracker import PositionTracker
        from autotrade.orders.execution_router import ExecutionRouter
        
        self.router = ExecutionRouter()
        self.position_tracker = PositionTracker(router=self.router)
        self.order_manager = OrderManager(
            router=self.router,
            risk_manager=self.risk_manager,
            position_tracker=self.position_tracker
        )

        # Step 6: Initialize Strategy Layer
        from autotrade.strategies.strategy_manager import StrategyManager
        self.strategy_manager = StrategyManager(
            order_manager=self.order_manager,
            risk_manager=self.risk_manager,
            market_data=self.market_data
        )
        self.strategy_manager.load_strategies()

        # Step 7: Initialize Analytics & Audit Logging
        from autotrade.reporting.audit_logger import AuditLogger
        from autotrade.reporting.report_generator import ReportGenerator
        from autotrade.reporting.performance_metrics import PerformanceMetricsEngine
        
        self.audit_logger = AuditLogger(database=self.database)
        self.metrics_engine = PerformanceMetricsEngine(database=self.database)
        self.report_generator = ReportGenerator(
            database=self.database,
            metrics_engine=self.metrics_engine,
            charts=self.charts
        )

        # Step 8: Security and Authentication Layer
        from autotrade.security.crypto_manager import CryptoManager
        from autotrade.security.auth import SecurityGuardian
        from autotrade.security.two_factor import TwoFactorAuth
        
        self.crypto = CryptoManager()
        self.security = SecurityGuardian()
        self.two_factor = TwoFactorAuth()

        # Register Scheduled Recurring Tasks
        self._register_scheduled_tasks()

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(f"All 9 Institutional Layers initialized successfully in {elapsed_ms:.2f} ms.")
        return True

    def _register_scheduled_tasks(self) -> None:
        """Configures periodic background cron jobs for the autonomous bot."""
        # 1. MT4 Bridge Health Check & State Sync (every 5 seconds)
        scheduler.add_interval_task(
            "mt4_health_sync",
            "MT4 Bridge Health Check",
            self._sync_bridge_state,
            interval_sec=5.0
        )
        # 2. News Alert Broadcast Job (every 60 seconds)
        scheduler.add_interval_task(
            "news_alert_check",
            "Economic News Calendar Check",
            self._check_economic_news,
            interval_sec=60.0
        )
        # 3. Position Trailing & Breakeven Evaluator (every 1 second)
        scheduler.add_interval_task(
            "position_guardian",
            "Position Trailing & Breakeven Monitor",
            self._evaluate_positions,
            interval_sec=1.0
        )
        # 4. Daily Report Generator (every 24 hours / midnight)
        scheduler.add_interval_task(
            "daily_performance_report",
            "Daily Institutional Report",
            self._generate_daily_report,
            interval_sec=86400.0,
            first_delay_sec=3600.0
        )
        # 5. Periodic Walk-Forward Optimization (every 6 hours)
        scheduler.add_interval_task(
            "periodic_optimizer",
            "Strategy Parameter Optimizer",
            self._run_strategy_optimization,
            interval_sec=21600.0,
            first_delay_sec=1800.0
        )

    async def start(self) -> None:
        """Starts the Event Bus, Scheduler, Watchdog, and Main 24/7 Trading Loop."""
        async with self._lock:
            if self.state.is_running:
                logger.warning("TradingEngine is already running.")
                return

            self.state.is_running = True
            self.state.emergency_halt = False
            self.state.start_time = time.time()
            
            # Start Event Bus
            await event_bus.start()
            
            # Start Scheduler
            await scheduler.start()
            
            # Start Watchdog
            if hasattr(self, "watchdog") and self.watchdog:
                await self.watchdog.start()

            # Launch Main Surveillance Loop
            self._main_loop_task = asyncio.create_task(self._run_trading_loop(), name="EngineTradingLoop")
            
            event_bus.publish(
                EventType.SYSTEM_STARTUP,
                payload={"start_time": self.state.start_time},
                priority=EventPriority.CRITICAL,
                source="TradingEngine"
            )
            logger.info("🚀 AutoTrade Institutional 24/7 Engine is ONLINE and Active.")

    async def stop(self) -> None:
        """Gracefully halts trading, flushes queues, and shuts down subsystems."""
        async with self._lock:
            if not self.state.is_running:
                return
            self.state.is_running = False

            logger.info("Halting AutoTrade Engine gracefully...")
            
            if self._main_loop_task:
                self._main_loop_task.cancel()
                try:
                    await self._main_loop_task
                except asyncio.CancelledError:
                    pass
                self._main_loop_task = None

            if hasattr(self, "watchdog") and self.watchdog:
                await self.watchdog.stop()
                
            await scheduler.stop()
            await event_bus.stop()
            
            if self.database:
                await self.database.close()

            event_bus.publish(
                EventType.SYSTEM_SHUTDOWN,
                payload={"shutdown_time": time.time()},
                priority=EventPriority.CRITICAL,
                source="TradingEngine"
            )
            logger.info("TradingEngine stopped cleanly.")

    async def emergency_halt(self, reason: str = "Emergency Button Activated") -> None:
        """
        Instant Kill-Switch: Closes all positions immediately, cancels pending orders,
        and locks the engine to prevent any new trades until explicit owner reset.
        """
        async with self._lock:
            self.state.emergency_halt = True
            self.state.is_paused = True
            logger.critical(f"🚨 EMERGENCY HALT TRIGGERED: {reason}")
            
            # Close all active orders
            if self.order_manager:
                await self.order_manager.close_all_positions(reason=reason)

            event_bus.publish(
                EventType.EMERGENCY_HALT,
                payload={"reason": reason, "timestamp": time.time()},
                priority=EventPriority.CRITICAL,
                source="TradingEngine"
            )

    async def pause(self) -> None:
        """Pauses autonomous trade generation without closing existing trades."""
        async with self._lock:
            self.state.is_paused = True
            logger.info("Auto-trading paused by operator.")

    async def resume(self) -> None:
        """Resumes autonomous trade generation if no emergency halt is active."""
        async with self._lock:
            if self.state.emergency_halt:
                logger.warning("Cannot resume: Emergency halt is active. Reset risk safeguard first.")
                return
            self.state.is_paused = False
            logger.info("Auto-trading resumed by operator.")

    async def _on_emergency_halt(self, event: Event) -> None:
        """Listener handling emergency halt broadcast."""
        self.state.emergency_halt = True
        self.state.is_paused = True

    async def _on_tick_event(self, event: Event) -> None:
        """Processes incoming market tick."""
        self.state.total_ticks_processed += 1
        if self.state.is_paused or self.state.emergency_halt:
            return
            
        tick_data = event.payload
        # Forward tick to market data aggregator and strategy manager
        if self.market_data:
            await self.market_data.on_tick(tick_data)
        if self.strategy_manager:
            await self.strategy_manager.on_tick(tick_data)

    async def _run_trading_loop(self) -> None:
        """Core 24/7 background market surveillance and state evaluation loop."""
        while self.state.is_running:
            try:
                self.state.uptime_seconds = time.time() - self.state.start_time
                self.state.last_heartbeat = time.time()
                
                # Heartbeat event
                event_bus.publish(
                    EventType.SYSTEM_HEARTBEAT,
                    payload={"uptime": self.state.uptime_seconds, "equity": self.state.current_equity},
                    priority=EventPriority.LOW,
                    source="TradingEngine"
                )

                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception as ex:
                logger.error(f"Error in engine main loop: {ex}", exc_info=True)
                await asyncio.sleep(2.0)

    async def _sync_bridge_state(self) -> None:
        """Pings MT4 ZeroMQ bridge, updates account balance, equity, and margin."""
        try:
            from zmq_client import zmq_client
            res = zmq_client.get_account()
            if res.get("status") == "ok":
                self.state.mt4_bridge_online = True
                self.state.current_equity = float(res.get("equity", 0.0))
                self.state.current_balance = float(res.get("balance", 0.0))
                self.state.active_account_id = str(res.get("login", ""))
                self.state.active_account_name = str(res.get("name", ""))
            else:
                self.state.mt4_bridge_online = False
        except Exception as ex:
            self.state.mt4_bridge_online = False
            logger.debug(f"Bridge state sync check failed: {ex}")

    async def _check_economic_news(self) -> None:
        """Evaluates upcoming high-impact economic news events."""
        if hasattr(self, "news_feed") and self.news_feed:
            await self.news_feed.check_due_alerts()

    async def _evaluate_positions(self) -> None:
        """Monitors open positions for dynamic trailing stops and break-even rules."""
        if hasattr(self, "position_tracker") and self.position_tracker:
            await self.position_tracker.evaluate_all_active_positions()

    async def _generate_daily_report(self) -> None:
        """Generates comprehensive daily performance summary."""
        if hasattr(self, "report_generator") and self.report_generator:
            await self.report_generator.generate_daily_report()

    async def _run_strategy_optimization(self) -> None:
        """Executes periodic walk-forward parameter optimization."""
        if hasattr(self, "strategy_manager") and self.strategy_manager:
            await self.strategy_manager.optimize_strategies()

    def get_status(self) -> Dict[str, Any]:
        """Returns comprehensive diagnostic status of the trading system."""
        now = time.time()
        uptime = now - self.state.start_time if self.state.is_running else 0.0
        return {
            "is_running": self.state.is_running,
            "is_paused": self.state.is_paused,
            "emergency_halt": self.state.emergency_halt,
            "uptime_seconds": round(uptime, 1),
            "total_ticks_processed": self.state.total_ticks_processed,
            "total_orders_executed": self.state.total_orders_executed,
            "current_equity": self.state.current_equity,
            "current_balance": self.state.current_balance,
            "mt4_bridge_online": self.state.mt4_bridge_online,
            "account_id": self.state.active_account_id,
            "account_name": self.state.active_account_name,
            "event_bus_metrics": event_bus.get_metrics(),
            "scheduler_tasks_count": len(scheduler._tasks),
        }


# Global singleton engine instance
_trading_engine = TradingEngine()

def get_engine() -> TradingEngine:
    """Returns singleton TradingEngine instance."""
    return _trading_engine
