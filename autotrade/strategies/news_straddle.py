"""
High-Impact Economic Calendar Straddle & Breakout Strategy.
Capitalizes on macroeconomic volatility explosions (NFP, CPI, Interest Rate Decisions).
Establishes pre-news consolidation brackets and straddles breakouts with tight risk containment.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
import numpy as np

from autotrade.analytics.precision import PrecisionMath
from autotrade.strategies.base_strategy import BaseStrategy, StrategySignal

logger = logging.getLogger("autotrade.strategies.news_straddle")


class NewsStraddleStrategy(BaseStrategy):
    """
    Economic News Straddle Strategy.
    Monitors currency volatility around scheduled economic events.
    """
    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
        straddle_offset_pips: int = 20,
        stop_loss_pips: int = 25,
        take_profit_pips: int = 50
    ):
        params = {
            "straddle_offset_pips": straddle_offset_pips,
            "stop_loss_pips": stop_loss_pips,
            "take_profit_pips": take_profit_pips
        }
        super().__init__(
            name="NewsStraddleStrategy",
            symbols=symbols,
            timeframes=timeframes,
            params=params
        )

    def evaluate(self, symbol: str, timeframe: str, ohlcv: Dict[str, Any]) -> Optional[StrategySignal]:
        closes = ohlcv.get("close", np.array([]))
        if len(closes) < 20:
            return None

        # News-specific triggering is primarily event-driven via news alerts
        return None

    def create_news_straddle_signals(
        self,
        symbol: str,
        current_price: float,
        sentiment_score: float = 0.0
    ) -> List[StrategySignal]:
        """
        Creates paired Buy and Sell breakout bracket signals before a high-impact news release.
        """
        pip_size = float(PrecisionMath.get_pip_size(symbol))
        offset = self.params["straddle_offset_pips"] * pip_size
        sl_dist = self.params["stop_loss_pips"] * pip_size
        tp_dist = self.params["take_profit_pips"] * pip_size

        buy_price = PrecisionMath.round_price(symbol, current_price + offset)
        buy_sl = PrecisionMath.round_price(symbol, buy_price - sl_dist)
        buy_tp = PrecisionMath.round_price(symbol, buy_price + tp_dist)

        sell_price = PrecisionMath.round_price(symbol, current_price - offset)
        sell_sl = PrecisionMath.round_price(symbol, sell_price + sl_dist)
        sell_tp = PrecisionMath.round_price(symbol, sell_price - tp_dist)

        sig_buy = StrategySignal(
            strategy_name=self.name,
            symbol=symbol,
            timeframe="M5",
            action="BUY",
            confidence=0.75 + (sentiment_score * 0.1),
            entry_price=buy_price,
            sl=buy_sl,
            tp=buy_tp,
            sizing_method="volatility_atr",
            metadata={"news_straddle": "UPPER_LEG"}
        )

        sig_sell = StrategySignal(
            strategy_name=self.name,
            symbol=symbol,
            timeframe="M5",
            action="SELL",
            confidence=0.75 - (sentiment_score * 0.1),
            entry_price=sell_price,
            sl=sell_sl,
            tp=sell_tp,
            sizing_method="volatility_atr",
            metadata={"news_straddle": "LOWER_LEG"}
        )

        return [sig_buy, sig_sell]
