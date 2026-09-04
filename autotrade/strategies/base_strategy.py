"""
Abstract Base Strategy Architecture.
Provides uniform lifecycle hooks, event dispatching, parameter hot-reloading,
and performance tracking across all algorithmic trading strategies.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from autotrade.core.event_bus import event_bus, EventType, EventPriority
from autotrade.data_layer.market_data import Bar, Tick

logger = logging.getLogger("autotrade.strategies.base_strategy")


@dataclass
class StrategySignal:
    """Standardized trading signal emitted by a strategy."""
    strategy_name: str
    symbol: str
    timeframe: str
    action: str  # BUY, SELL, or HOLD
    confidence: float  # 0.0 to 1.0
    entry_price: float
    sl: float = 0.0
    tp: float = 0.0
    sizing_method: str = "volatility_atr"
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "action": self.action,
            "confidence": round(self.confidence, 3),
            "entry_price": self.entry_price,
            "sl": self.sl,
            "tp": self.tp,
            "sizing_method": self.sizing_method,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }


class BaseStrategy(ABC):
    """
    Abstract Strategy Interface.
    Every autonomous strategy subclasses BaseStrategy to integrate with the multi-layer core.
    """
    def __init__(
        self,
        name: str,
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
        params: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.symbols = symbols or ["GBPUSD", "EURUSD", "XAUUSD", "USOIL"]
        self.timeframes = timeframes or ["M15", "H1"]
        self.params = params or {}
        self.is_enabled = True
        
        # Telemetry
        self.total_signals_generated: int = 0
        self.last_signal_time: Optional[float] = None

    def enable(self) -> None:
        """Enables strategy execution."""
        self.is_enabled = True
        event_bus.publish(
            EventType.STRATEGY_ENABLED,
            payload={"strategy": self.name},
            priority=EventPriority.NORMAL,
            source="BaseStrategy"
        )
        logger.info(f"Strategy '{self.name}' enabled.")

    def disable(self) -> None:
        """Disables strategy execution."""
        self.is_enabled = False
        event_bus.publish(
            EventType.STRATEGY_DISABLED,
            payload={"strategy": self.name},
            priority=EventPriority.NORMAL,
            source="BaseStrategy"
        )
        logger.info(f"Strategy '{self.name}' disabled.")

    def update_parameter(self, param_name: str, value: Any) -> bool:
        """Dynamically updates a parameter at runtime without restarting."""
        if param_name in self.params:
            old_val = self.params[param_name]
            self.params[param_name] = type(old_val)(value) if old_val is not None else value
            logger.info(f"Strategy '{self.name}' param '{param_name}' updated: {old_val} -> {value}")
            return True
        self.params[param_name] = value
        return True

    @abstractmethod
    def evaluate(self, symbol: str, timeframe: str, ohlcv: Dict[str, Any]) -> Optional[StrategySignal]:
        """
        Core algorithmic decision routine.
        Analyzes multi-timeframe OHLCV bars and technical indicators to emit StrategySignal.
        """
        pass

    async def on_bar(self, bar: Bar, ohlcv: Dict[str, Any]) -> Optional[StrategySignal]:
        """Called automatically when a candle closes."""
        if not self.is_enabled:
            return None
        if bar.symbol not in self.symbols or bar.timeframe not in self.timeframes:
            return None

        signal = self.evaluate(bar.symbol, bar.timeframe, ohlcv)
        if signal and signal.action in ("BUY", "SELL"):
            self.total_signals_generated += 1
            self.last_signal_time = time.time()
            
            event_bus.publish(
                EventType.SIGNAL_GENERATED,
                payload=signal.to_dict(),
                priority=EventPriority.NORMAL,
                source=self.name
            )
        return signal

    async def on_tick(self, tick: Tick) -> Optional[StrategySignal]:
        """Optional tick-level evaluation hook for high-frequency scalping."""
        return None
