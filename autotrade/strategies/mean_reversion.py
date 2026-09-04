"""
Statistical Arbitrage & Bollinger Mean Reversion Strategy.
Capitalizes on extreme price standard deviation departures from moving averages.
Triggers counter-trend mean reversion trades when price penetrates Bollinger Bands with RSI confirmation.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
import numpy as np

from autotrade.analytics.indicators import indicators
from autotrade.analytics.precision import PrecisionMath
from autotrade.strategies.base_strategy import BaseStrategy, StrategySignal

logger = logging.getLogger("autotrade.strategies.mean_reversion")


class MeanReversionStrategy(BaseStrategy):
    """
    Mean Reversion Strategy.
    Buys when: Price <= Bollinger Lower Band, RSI < 30, Price rejects back upwards.
    Sells when: Price >= Bollinger Upper Band, RSI > 70, Price rejects back downwards.
    """
    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0
    ):
        params = {
            "bb_period": bb_period,
            "bb_std": bb_std,
            "rsi_period": rsi_period,
            "rsi_oversold": rsi_oversold,
            "rsi_overbought": rsi_overbought,
        }
        super().__init__(
            name="MeanReversionStrategy",
            symbols=symbols,
            timeframes=timeframes,
            params=params
        )

    def evaluate(self, symbol: str, timeframe: str, ohlcv: Dict[str, Any]) -> Optional[StrategySignal]:
        closes = ohlcv.get("close", np.array([]))
        highs = ohlcv.get("high", np.array([]))
        lows = ohlcv.get("low", np.array([]))
        
        if len(closes) < max(self.params["bb_period"] + 5, 30):
            return None

        # Compute Technical Indicators
        bb = indicators.bollinger_bands(closes, self.params["bb_period"], self.params["bb_std"])
        rsi_vals = indicators.rsi(closes, self.params["rsi_period"])
        atr_val = indicators.atr(highs, lows, closes, 14)[-1]

        curr_price = closes[-1]
        curr_rsi = rsi_vals[-1]
        lower_band = bb["lower"][-1]
        upper_band = bb["upper"][-1]
        middle_band = bb["middle"][-1]

        # Buy Condition: Deep oversold bounce
        if curr_price <= lower_band and curr_rsi <= self.params["rsi_oversold"]:
            sl_dist = atr_val * 1.5
            sl = PrecisionMath.round_price(symbol, curr_price - sl_dist)
            tp = PrecisionMath.round_price(symbol, middle_band)
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                timeframe=timeframe,
                action="BUY",
                confidence=min(0.90, 0.70 + ((30.0 - curr_rsi) / 100.0)),
                entry_price=curr_price,
                sl=sl,
                tp=tp,
                sizing_method="percentage_risk",
                metadata={"rsi": round(curr_rsi, 1), "bb_lower": round(lower_band, 5)}
            )

        # Sell Condition: Deep overbought rejection
        if curr_price >= upper_band and curr_rsi >= self.params["rsi_overbought"]:
            sl_dist = atr_val * 1.5
            sl = PrecisionMath.round_price(symbol, curr_price + sl_dist)
            tp = PrecisionMath.round_price(symbol, middle_band)
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                timeframe=timeframe,
                action="SELL",
                confidence=min(0.90, 0.70 + ((curr_rsi - 70.0) / 100.0)),
                entry_price=curr_price,
                sl=sl,
                tp=tp,
                sizing_method="percentage_risk",
                metadata={"rsi": round(curr_rsi, 1), "bb_upper": round(upper_band, 5)}
            )

        return None
