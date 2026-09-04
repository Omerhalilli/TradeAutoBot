"""
Core package for the AutoTrade Algorithmic Trading Framework.
Contains the event bus, asynchronous engine, task scheduler, and dynamic configuration manager.
"""

from autotrade.core.event_bus import (
    EventBus,
    Event,
    EventType,
    EventPriority,
    event_bus
)
from autotrade.core.config_manager import ConfigManager, get_config
from autotrade.core.scheduler import AsyncScheduler, scheduler
from autotrade.core.engine import TradingEngine, get_engine

__all__ = [
    "EventBus",
    "Event",
    "EventType",
    "EventPriority",
    "event_bus",
    "ConfigManager",
    "get_config",
    "AsyncScheduler",
    "scheduler",
    "TradingEngine",
    "get_engine",
]
