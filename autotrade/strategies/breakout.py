"""
Volatility Expansion & Donchian Channel Breakout Strategy.
Detects range compression breakouts confirmed by institutional volume surges and money flow expansion.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
import numpy as np

from autotrade.analytics.indicators import indicators
from autotrade.analytics.precision import PrecisionMath
from autotrade.strategies.base_strategy import BaseStrategy, StrategySignal

logger = logging.getLogger("autotrade.strategies.breakout")


class BreakoutStrategy(BaseStrategy):
    """
    Breakout Strategy.
    Buys when: Price breaks above N-bar Donchian high with Volume surge > 1.3x average and positive CMF.
    Sells when: Price breaks below N-bar Donchian low with Volume surge > 1.3x average and negative CMF.
    """
    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
        channel_period: int = 20,
        volume_multiplier: float = 1.3,
        risk_reward_ratio: float = 2.5
    ):
        params = {
            "channel_period": channel_period,
            "volume_multiplier": volume_multiplier,
            "risk_reward_ratio": risk_reward_ratio
        }
        super().__init__(
            name="BreakoutStrategy",
            symbols=symbols,
            timeframes=timeframes,
            params=params
        )

    def evaluate(self, symbol: str, timeframe: str, ohlcv: Dict[str, Any]) -> Optional[StrategySignal]:
        closes = ohlcv.get("close", np.array([]))
        highs = ohlcv.get("high", np.array([]))
        lows = ohlcv.get("low", np.array([]))
        vols = ohlcv.get("volume", np.ones_like(closes))
        
        p = self.params["channel_period"]
        if len(closes) < p + 5:
            return None

        # Donchian Channels computed up to prior bar to avoid lookahead bias
        donchian = indicators.donchian_channels(highs[:-1], lows[:-1], p)
        upper_ch = donchian["upper"][-1]
        lower_ch = donchian["lower"][-1]

        vol_sma = indicators.sma(vols, p)[-1]
        cmf_val = indicators.cmf(highs, lows, closes, vols, p)[-1]
        atr_val = indicators.atr(highs, lows, closes, 14)[-1]

        curr_price = closes[-1]
        curr_vol = vols[-1]
        is_vol_surge = curr_vol >= (vol_sma * self.params["volume_multiplier"]) if vol_sma > 0 else True

        # Bullish Breakout
        if curr_price > upper_ch and is_vol_surge and cmf_val > 0.02:
            sl_dist = atr_val * 1.5
            sl = PrecisionMath.round_price(symbol, curr_price - sl_dist)
            tp = PrecisionMath.round_price(symbol, curr_price + (sl_dist * self.params["risk_reward_ratio"]))
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                timeframe=timeframe,
                action="BUY",
                confidence=0.82,
                entry_price=curr_price,
                sl=sl,
                tp=tp,
                sizing_method="volatility_atr",
                metadata={"breakout_level": round(upper_ch, 5), "cmf": round(cmf_val, 3)}
            )

        # Bearish Breakdown
        if curr_price < lower_ch and is_vol_surge and cmf_val < -0.02:
            sl_dist = atr_val * 1.5
            sl = PrecisionMath.round_price(symbol, curr_price + sl_dist)
            tp = PrecisionMath.round_price(symbol, curr_price - (sl_dist * self.params["risk_reward_ratio"]))
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                timeframe=timeframe,
                action="SELL",
                confidence=0.82,
                entry_price=curr_price,
                sl=sl,
                tp=tp,
                sizing_method="volatility_atr",
                metadata={"breakout_level": round(lower_ch, 5), "cmf": round(cmf_val, 3)}
            )

        return None
