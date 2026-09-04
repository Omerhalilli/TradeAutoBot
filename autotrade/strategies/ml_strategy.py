"""
Machine Learning & Quantitative Predictive Strategy.
Leverages ensemble decision stumps, ARIMA trend forecasting, and GARCH conditional volatility
to estimate directional price probabilities and execute statistical edge trades.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
import numpy as np

from autotrade.analytics.math_models import PredictiveModels
from autotrade.analytics.precision import PrecisionMath
from autotrade.strategies.base_strategy import BaseStrategy, StrategySignal

logger = logging.getLogger("autotrade.strategies.ml_strategy")


class MLPredictorStrategy(BaseStrategy):
    """
    Quantitative ML predictive strategy.
    Generates signals when forward directional probability exceeds confidence threshold.
    """
    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
        min_probability: float = 0.58,
        atr_multiplier_sl: float = 1.6,
        atr_multiplier_tp: float = 2.4
    ):
        params = {
            "min_probability": min_probability,
            "atr_multiplier_sl": atr_multiplier_sl,
            "atr_multiplier_tp": atr_multiplier_tp
        }
        super().__init__(
            name="MLPredictorStrategy",
            symbols=symbols,
            timeframes=timeframes,
            params=params
        )

    def evaluate(self, symbol: str, timeframe: str, ohlcv: Dict[str, Any]) -> Optional[StrategySignal]:
        closes = ohlcv.get("close", np.array([]))
        if len(closes) < 35:
            return None

        # 1. Run Machine Learning Model Inference
        pred = PredictiveModels.predict_price_direction(ohlcv)
        action = pred["action"]
        confidence = pred["confidence"]
        min_p = self.params["min_probability"]

        if action not in ("BUY", "SELL") or confidence < min_p:
            return None

        # 2. Volatility Estimate via GARCH
        log_ret = np.diff(np.log(closes[-30:]))
        garch_res = PredictiveModels.garch_volatility(log_ret)
        vol_forecast = garch_res.forecast_volatility
        
        curr_price = closes[-1]
        sl_dist = curr_price * vol_forecast * self.params["atr_multiplier_sl"]
        tp_dist = curr_price * vol_forecast * self.params["atr_multiplier_tp"]

        if action == "BUY":
            sl = PrecisionMath.round_price(symbol, curr_price - sl_dist)
            tp = PrecisionMath.round_price(symbol, curr_price + tp_dist)
        else:
            sl = PrecisionMath.round_price(symbol, curr_price + sl_dist)
            tp = PrecisionMath.round_price(symbol, curr_price - tp_dist)

        return StrategySignal(
            strategy_name=self.name,
            symbol=symbol,
            timeframe=timeframe,
            action=action,
            confidence=confidence,
            entry_price=curr_price,
            sl=sl,
            tp=tp,
            sizing_method="kelly_criterion",
            metadata={
                "p_buy": pred.get("p_buy"),
                "p_sell": pred.get("p_sell"),
                "garch_vol": round(vol_forecast, 4)
            }
        )
