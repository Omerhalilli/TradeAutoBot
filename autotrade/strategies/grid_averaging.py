"""
Smart Adaptive Grid & Volatility Cost-Averaging Strategy.
Deploys dynamic ATR-spaced grid levels with hard stop-loss risk capping,
preventing the unbounded drawdowns common in naive martingales.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
import numpy as np

from autotrade.analytics.indicators import indicators
from autotrade.analytics.precision import PrecisionMath
from autotrade.strategies.base_strategy import BaseStrategy, StrategySignal

logger = logging.getLogger("autotrade.strategies.grid_averaging")


class SmartGridStrategy(BaseStrategy):
    """
    Adaptive Grid & Dollar-Cost Averaging Strategy.
    Enforces maximum grid depth (max 3 levels) and dynamic volatility-based spacing.
    """
    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
        max_grid_levels: int = 3,
        grid_atr_multiplier: float = 1.8,
        basket_tp_pips: int = 25
    ):
        params = {
            "max_grid_levels": max_grid_levels,
            "grid_atr_multiplier": grid_atr_multiplier,
            "basket_tp_pips": basket_tp_pips
        }
        super().__init__(
            name="SmartGridStrategy",
            symbols=symbols,
            timeframes=timeframes,
            params=params
        )

    def evaluate(self, symbol: str, timeframe: str, ohlcv: Dict[str, Any]) -> Optional[StrategySignal]:
        closes = ohlcv.get("close", np.array([]))
        highs = ohlcv.get("high", np.array([]))
        lows = ohlcv.get("low", np.array([]))
        
        if len(closes) < 30:
            return None

        # Evaluates initial grid anchor entry
        rsi_val = indicators.rsi(closes, 14)[-1]
        atr_val = indicators.atr(highs, lows, closes, 14)[-1]
        curr_price = closes[-1]

        # Initial anchor on mild range extremes
        if rsi_val <= 38.0:
            sl_dist = atr_val * (self.params["grid_atr_multiplier"] * self.params["max_grid_levels"] + 1.0)
            tp_dist = atr_val * 1.2
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                timeframe=timeframe,
                action="BUY",
                confidence=0.72,
                entry_price=curr_price,
                sl=PrecisionMath.round_price(symbol, curr_price - sl_dist),
                tp=PrecisionMath.round_price(symbol, curr_price + tp_dist),
                sizing_method="fixed_lot",
                metadata={"grid_level": 1, "atr_spacing": round(atr_val * self.params["grid_atr_multiplier"], 5)}
            )

        if rsi_val >= 62.0:
            sl_dist = atr_val * (self.params["grid_atr_multiplier"] * self.params["max_grid_levels"] + 1.0)
            tp_dist = atr_val * 1.2
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                timeframe=timeframe,
                action="SELL",
                confidence=0.72,
                entry_price=curr_price,
                sl=PrecisionMath.round_price(symbol, curr_price + sl_dist),
                tp=PrecisionMath.round_price(symbol, curr_price - tp_dist),
                sizing_method="fixed_lot",
                metadata={"grid_level": 1, "atr_spacing": round(atr_val * self.params["grid_atr_multiplier"], 5)}
            )

        return None
