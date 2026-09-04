"""
Institutional Position Sizing & Capital Allocation Engine.
Calculates mathematically optimal order volumes using:
- Fixed Lot Sizing
- Percentage-Based Account Risk
- Fractional Kelly Criterion
- ATR-Based Volatility Sizing
- Optimal f Allocation
- Dynamic Auto-Regime Sizing
"""

from __future__ import annotations
from enum import Enum
import logging
import math
from typing import Any, Dict, Optional

from autotrade.analytics.precision import PrecisionMath
from autotrade.core.config_manager import get_config

logger = logging.getLogger("autotrade.risk.position_sizer")


class SizingMethod(str, Enum):
    FIXED_LOT = "fixed_lot"
    PERCENTAGE_RISK = "percentage_risk"
    KELLY_CRITERION = "kelly_criterion"
    VOLATILITY_ATR = "volatility_atr"
    OPTIMAL_F = "optimal_f"
    AUTO = "auto"


class PositionSizer:
    """
    Mathematical position sizing engine ensuring risk per trade aligns strictly with portfolio capital preservation.
    """
    def __init__(self):
        self.config = get_config()

    def calculate_lot_size(
        self,
        symbol: str,
        method: Union[SizingMethod, str],
        balance: float,
        entry_price: float,
        stop_loss: float,
        atr_value: Optional[float] = None,
        win_rate: float = 0.55,
        profit_factor: float = 1.6,
        market_regime: str = "TRENDING"
    ) -> float:
        """
        Computes quantized lot size for an order.
        """
        if isinstance(method, str):
            try:
                method = SizingMethod(method.lower())
            except ValueError:
                method = SizingMethod.PERCENTAGE_RISK

        # 1. AUTO Regime Selection
        if method == SizingMethod.AUTO:
            if market_regime == "VOLATILE_NEWS":
                method = SizingMethod.VOLATILITY_ATR
            elif market_regime == "TRENDING" and win_rate >= 0.52:
                method = SizingMethod.KELLY_CRITERION
            else:
                method = SizingMethod.PERCENTAGE_RISK

        # 2. Compute candidate lots
        if method == SizingMethod.FIXED_LOT:
            lots = self.config.strategy.default_fixed_lot
        elif method == SizingMethod.PERCENTAGE_RISK:
            lots = self._calculate_percent_risk_lots(symbol, balance, entry_price, stop_loss)
        elif method == SizingMethod.KELLY_CRITERION:
            lots = self._calculate_kelly_lots(symbol, balance, entry_price, stop_loss, win_rate, profit_factor)
        elif method == SizingMethod.VOLATILITY_ATR:
            lots = self._calculate_atr_volatility_lots(symbol, balance, atr_value or 0.0020)
        elif method == SizingMethod.OPTIMAL_F:
            lots = self._calculate_optimal_f_lots(symbol, balance, entry_price, stop_loss)
        else:
            lots = self.config.strategy.default_fixed_lot

        # 3. Quantize to broker lot boundaries
        quantized = PrecisionMath.round_lot(
            lots=lots,
            min_lot=0.01,
            step_lot=0.01,
            max_lot=self.config.risk.max_lots_per_symbol
        )

        logger.debug(f"Position sizing for {symbol} ({method.value}): raw={lots:.4f}, quantized={quantized:.2f}")
        return quantized

    def _calculate_percent_risk_lots(
        self,
        symbol: str,
        balance: float,
        entry_price: float,
        stop_loss: float
    ) -> float:
        """
        Lots = (Balance * Risk%) / (SL_Distance_In_Pips * Pip_Value)
        """
        if balance <= 0 or entry_price <= 0 or stop_loss <= 0:
            return self.config.strategy.default_fixed_lot

        risk_pct = self.config.risk.max_account_risk_pct / 100.0
        risk_cash = balance * risk_pct

        price_diff = abs(entry_price - stop_loss)
        pips = PrecisionMath.price_to_pips(symbol, price_diff)
        if pips < 5.0:
            pips = 15.0  # Minimum conservative SL distance assumption

        # Approximate 1 standard lot = $10 / pip on standard FX, adjust for cross/metals
        pip_val_per_lot = 10.0
        sym_upper = symbol.upper()
        if "JPY" in sym_upper:
            pip_val_per_lot = 9.0
        elif "XAU" in sym_upper: # Gold: 1 lot = 100 oz, $1 move = $100
            pip_val_per_lot = 100.0
        elif "OIL" in sym_upper: # Crude: 1 lot = 1000 bbl, $1 move = $1000
            pip_val_per_lot = 100.0

        lots = risk_cash / (pips * pip_val_per_lot)
        return max(0.01, lots)

    def _calculate_kelly_lots(
        self,
        symbol: str,
        balance: float,
        entry_price: float,
        stop_loss: float,
        win_rate: float,
        profit_factor: float
    ) -> float:
        """
        Fractional Kelly: f* = (p * b - q) / b * fraction
        """
        p = max(0.01, min(0.99, win_rate))
        q = 1.0 - p
        b = max(0.1, profit_factor)
        
        kelly_full = (p * b - q) / b
        if kelly_full <= 0:
            # Negative edge, fall back to minimum lot
            return 0.01

        # Apply conservative fractional Kelly multiplier (e.g. 0.5x Half-Kelly)
        frac_kelly = kelly_full * self.config.strategy.kelly_fraction
        # Cap max risk at 3% balance
        effective_risk_pct = min(frac_kelly * 100.0, 3.0)

        risk_cash = balance * (effective_risk_pct / 100.0)
        price_diff = abs(entry_price - stop_loss)
        pips = max(10.0, PrecisionMath.price_to_pips(symbol, price_diff))
        pip_val = 10.0
        return max(0.01, risk_cash / (pips * pip_val))

    def _calculate_atr_volatility_lots(
        self,
        symbol: str,
        balance: float,
        atr_value: float
    ) -> float:
        """
        Inverse ATR Sizing: Scales lot inversely with market volatility.
        """
        if atr_value <= 0 or balance <= 0:
            return self.config.strategy.default_fixed_lot

        pips_atr = max(5.0, PrecisionMath.price_to_pips(symbol, atr_value))
        target_risk_dollars = balance * 0.015  # Target 1.5% volatility budget
        lots = target_risk_dollars / (pips_atr * 10.0)
        return max(0.01, lots)

    def _calculate_optimal_f_lots(
        self,
        symbol: str,
        balance: float,
        entry_price: float,
        stop_loss: float
    ) -> float:
        """
        Optimal f position sizing bounded within safety limits.
        """
        base_lots = self._calculate_percent_risk_lots(symbol, balance, entry_price, stop_loss)
        optimal_f_factor = 0.85 # Scaled fraction
        return base_lots * optimal_f_factor
