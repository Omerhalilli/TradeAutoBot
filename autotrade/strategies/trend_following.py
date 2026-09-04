"""
Multi-Timeframe Trend Following & Momentum Strategy.
Combines Fast/Slow Exponential Moving Average (EMA) crossovers,
Average Directional Index (ADX) trend-strength filtering,
SuperTrend confirmation, and dynamic ATR-based profit brackets.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
import numpy as np

from autotrade.analytics.indicators import indicators
from autotrade.analytics.precision import PrecisionMath
from autotrade.strategies.base_strategy import BaseStrategy, StrategySignal

logger = logging.getLogger("autotrade.strategies.trend_following")


class TrendFollowingStrategy(BaseStrategy):
    """
    Institutional Trend Following Strategy.
    Buys when: Fast EMA > Slow EMA, Price > Trend EMA 200, ADX > 25, SuperTrend is Bullish.
    Sells when: Fast EMA < Slow EMA, Price < Trend EMA 200, ADX > 25, SuperTrend is Bearish.
    """
    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
        fast_ema: int = 9,
        slow_ema: int = 21,
        trend_ema: int = 200,
        adx_threshold: float = 22.0,
        atr_sl_multiplier: float = 1.5,
        risk_reward_ratio: float = 2.0
    ):
        params = {
            "fast_ema": fast_ema,
            "slow_ema": slow_ema,
            "trend_ema": trend_ema,
            "adx_threshold": adx_threshold,
            "atr_sl_multiplier": atr_sl_multiplier,
            "risk_reward_ratio": risk_reward_ratio,
        }
        super().__init__(
            name="TrendFollowingStrategy",
            symbols=symbols,
            timeframes=timeframes,
            params=params
        )

    def evaluate(self, symbol: str, timeframe: str, ohlcv: Dict[str, Any]) -> Optional[StrategySignal]:
        closes = ohlcv.get("close", np.array([]))
        highs = ohlcv.get("high", np.array([]))
        lows = ohlcv.get("low", np.array([]))
        
        req_len = max(self.params["trend_ema"] + 5, 50)
        if len(closes) < req_len:
            return None

        # Compute Technical Indicators
        fast_ema = indicators.ema(closes, self.params["fast_ema"])
        slow_ema = indicators.ema(closes, self.params["slow_ema"])
        trend_ema = indicators.ema(closes, self.params["trend_ema"])
        adx_res = indicators.adx(highs, lows, closes, 14)
        adx_val = adx_res["adx"][-1]
        st_res = indicators.supertrend(highs, lows, closes, 10, 3.0)
        st_dir = st_res["direction"][-1]  # 1 for Bull, -1 for Bear
        atr_val = indicators.atr(highs, lows, closes, 14)[-1]

        curr_price = closes[-1]
        prev_price = closes[-2]
        sl_mult = self.params["atr_sl_multiplier"]
        rr = self.params["risk_reward_ratio"]

        # Signal Logic: Bullish Condition
        is_bullish = (
            fast_ema[-1] > slow_ema[-1] and
            curr_price > trend_ema[-1] and
            st_dir == 1 and
            adx_val >= self.params["adx_threshold"]
        )

        # Signal Logic: Bearish Condition
        is_bearish = (
            fast_ema[-1] < slow_ema[-1] and
            curr_price < trend_ema[-1] and
            st_dir == -1 and
            adx_val >= self.params["adx_threshold"]
        )

        if is_bullish:
            sl_dist = atr_val * sl_mult
            sl = PrecisionMath.round_price(symbol, curr_price - sl_dist)
            tp = PrecisionMath.round_price(symbol, curr_price + (sl_dist * rr))
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                timeframe=timeframe,
                action="BUY",
                confidence=min(0.95, 0.65 + (adx_val / 100.0)),
                entry_price=curr_price,
                sl=sl,
                tp=tp,
                sizing_method="volatility_atr",
                metadata={"adx": round(adx_val, 1), "atr": round(atr_val, 5)}
            )

        if is_bearish:
            sl_dist = atr_val * sl_mult
            sl = PrecisionMath.round_price(symbol, curr_price + sl_dist)
            tp = PrecisionMath.round_price(symbol, curr_price - (sl_dist * rr))
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                timeframe=timeframe,
                action="SELL",
                confidence=min(0.95, 0.65 + (adx_val / 100.0)),
                entry_price=curr_price,
                sl=sl,
                tp=tp,
                sizing_method="volatility_atr",
                metadata={"adx": round(adx_val, 1), "atr": round(atr_val, 5)}
            )

        return None
