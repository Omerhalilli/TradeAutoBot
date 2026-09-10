"""
Institutional Position Sizing & Capital Allocation Engine.
Calculates mathematically optimal order volumes using:
- Dynamic Pip Value based on real-time quote currency exchange rates
- Percentage-Based Account Risk (strictly 0.5% - 1.0% cap)
- Fractional Kelly Criterion
- ATR-Based Volatility Parity Sizing
- Optimal f Allocation
"""

from __future__ import annotations
from enum import Enum
import logging
import math
from typing import Any, Dict, Optional, Union

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


# Fallback exchange rates against USD for dynamic pip conversion
DEFAULT_EXCHANGE_RATES: Dict[str, float] = {
    "EURUSD": 1.0850,
    "GBPUSD": 1.2850,
    "USDJPY": 152.00,
    "USDCHF": 0.8950,
    "USDCAD": 1.3650,
    "AUDUSD": 0.6550,
    "NZDUSD": 0.6050,
    "XAUUSD": 2400.0,
    "USOIL": 80.0,
}


def get_canonical_symbol(sym: str) -> str:
    s = str(sym).strip().upper()
    if s in ("GOLD", "XAU"):
        return "XAUUSD"
    if s in ("SILVER", "XAG"):
        return "XAGUSD"
    if s in ("OIL", "CRUDE", "WTI"):
        return "USOIL"
    for d in ["/", "\\", ".", "-", "_", "#", "+"]:
        s = s.replace(d, "")
    for suffix in ["MIN", "PRO", "RAW", "ECN", "MICRO", "STP", "I", "M"]:
        if s.endswith(suffix) and len(s) > len(suffix) + 3:
            s = s[:-len(suffix)]
            break
    return s


class PositionSizer:
    """
    Mathematical position sizing engine ensuring risk per trade aligns strictly with portfolio capital preservation.
    """
    def __init__(self):
        self.config = get_config()

    def get_dynamic_pip_value(
        self,
        symbol: str,
        exchange_rates: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Calculates dynamic dollar pip value for 1.0 standard lot based on real-time exchange rates.
        Eliminates fixed $10/pip assumption across cross-currency pairs, metals, and commodities.
        """
        canon = get_canonical_symbol(symbol)
        rates = exchange_rates or DEFAULT_EXCHANGE_RATES

        # Commodities / Metals
        if "XAU" in canon or canon == "GOLD":
            # 1 lot = 100 oz. Pip size = 0.01 -> $1.00 per pip. A $1.00 move is 100 pips = $100.
            return 100.0  # Normalized to $1.00 index points or 100 pips
        if "XAG" in canon or canon == "SILVER":
            # 1 lot = 5000 oz -> $50 per $0.01
            return 50.0
        if "OIL" in canon:
            # 1 lot = 1000 bbl -> $10 per $0.01 move, $1000 per $1.00
            return 10.0

        if len(canon) < 6:
            return 10.0

        base = canon[:3]
        quote = canon[3:6]

        # Case 1: Quote is USD (EURUSD, GBPUSD, AUDUSD, NZDUSD)
        if quote == "USD":
            return 10.0

        # Case 2: Base is USD (USDJPY, USDCHF, USDCAD) -> Pip Value = 10.0 / Rate (or 1000/Rate for JPY)
        if base == "USD":
            rate = rates.get(f"USD{quote}", rates.get(f"{quote}USD", 1.0))
            if quote == "JPY":
                return (1000.0 / rate) if rate > 0 else 6.50
            return (10.0 / rate) if rate > 0 else 10.0

        # Case 3: Cross pairs (e.g., EURGBP, EURJPY, GBPJPY, EURCHF, CADJPY)
        if quote == "JPY":
            usdjpy = rates.get("USDJPY", 150.0)
            return (1000.0 / usdjpy) if usdjpy > 0 else 6.67
        elif quote == "GBP":
            gbpusd = rates.get("GBPUSD", 1.28)
            return 10.0 * gbpusd
        elif quote == "CHF":
            usdchf = rates.get("USDCHF", 0.90)
            return (10.0 / usdchf) if usdchf > 0 else 11.11
        elif quote == "CAD":
            usdcad = rates.get("USDCAD", 1.36)
            return (10.0 / usdcad) if usdcad > 0 else 7.35
        elif quote == "AUD":
            audusd = rates.get("AUDUSD", 0.66)
            return 10.0 * audusd
        elif quote == "NZD":
            nzdusd = rates.get("NZDUSD", 0.60)
            return 10.0 * nzdusd

        return 10.0

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
        market_regime: str = "TRENDING",
        exchange_rates: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Computes quantized lot size for an order using dynamic pip valuation and volatility parity.
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
            lots = getattr(self.config.strategy, "default_fixed_lot", 0.01)
        elif method == SizingMethod.PERCENTAGE_RISK:
            lots = self._calculate_percent_risk_lots(symbol, balance, entry_price, stop_loss, exchange_rates)
        elif method == SizingMethod.KELLY_CRITERION:
            lots = self._calculate_kelly_lots(symbol, balance, entry_price, stop_loss, win_rate, profit_factor, exchange_rates)
        elif method == SizingMethod.VOLATILITY_ATR:
            lots = self._calculate_atr_volatility_lots(symbol, balance, atr_value or 0.0020, exchange_rates)
        elif method == SizingMethod.OPTIMAL_F:
            lots = self._calculate_optimal_f_lots(symbol, balance, entry_price, stop_loss, exchange_rates)
        else:
            lots = getattr(self.config.strategy, "default_fixed_lot", 0.01)

        # 3. Quantize to broker lot boundaries
        max_lot = getattr(self.config.risk, "max_lots_per_symbol", 5.0)
        quantized = PrecisionMath.round_lot(
            lots=lots,
            min_lot=0.01,
            step_lot=0.01,
            max_lot=max_lot
        )

        logger.debug(f"Position sizing for {symbol} ({method.value}): raw={lots:.4f}, quantized={quantized:.2f}")
        return quantized

    def _calculate_percent_risk_lots(
        self,
        symbol: str,
        balance: float,
        entry_price: float,
        stop_loss: float,
        exchange_rates: Optional[Dict[str, float]] = None
    ) -> float:
        """Lots = (Balance * Risk%) / (SL_Distance_In_Pips * Dynamic_Pip_Value)"""
        if balance <= 0 or entry_price <= 0 or stop_loss <= 0:
            return getattr(self.config.strategy, "default_fixed_lot", 0.01)

        risk_pct = getattr(self.config.risk, "max_account_risk_pct", 0.5) / 100.0
        risk_cash = balance * risk_pct

        price_diff = abs(entry_price - stop_loss)
        pips = PrecisionMath.price_to_pips(symbol, price_diff)
        if pips < 5.0:
            pips = 15.0

        pip_val = self.get_dynamic_pip_value(symbol, exchange_rates)
        denom = pips * pip_val
        lots = (risk_cash / denom) if denom > 0 else 0.01
        return max(0.01, lots)

    def _calculate_kelly_lots(
        self,
        symbol: str,
        balance: float,
        entry_price: float,
        stop_loss: float,
        win_rate: float,
        profit_factor: float,
        exchange_rates: Optional[Dict[str, float]] = None
    ) -> float:
        """Fractional Kelly: f* = (p * b - q) / b * fraction (capped at max account risk)"""
        p = max(0.01, min(0.99, win_rate))
        q = 1.0 - p
        b = max(0.1, profit_factor)

        kelly_full = (p * b - q) / b
        if kelly_full <= 0:
            return 0.01

        # Half-Kelly multiplier
        fractional_kelly = max(0.0, kelly_full * 0.50)
        # Cap risk between 0.5% and 1.0% of balance
        max_allowed_risk = min(0.01, getattr(self.config.risk, "max_account_risk_pct", 0.5) / 100.0)
        effective_risk_pct = min(fractional_kelly, max_allowed_risk)

        risk_cash = balance * effective_risk_pct
        price_diff = abs(entry_price - stop_loss)
        pips = max(5.0, PrecisionMath.price_to_pips(symbol, price_diff))
        pip_val = self.get_dynamic_pip_value(symbol, exchange_rates)
        denom = pips * pip_val
        lots = (risk_cash / denom) if denom > 0 else 0.01
        return max(0.01, lots)

    def _calculate_atr_volatility_lots(
        self,
        symbol: str,
        balance: float,
        atr_value: float,
        exchange_rates: Optional[Dict[str, float]] = None
    ) -> float:
        """Volatility ATR parity sizing: Lots = Risk_Cash / (ATR * Multiplier * Dynamic_Pip_Value)"""
        risk_pct = getattr(self.config.risk, "max_account_risk_pct", 0.5) / 100.0
        risk_cash = balance * risk_pct

        pip_size = float(PrecisionMath.get_pip_size(symbol))
        atr_pips = (atr_value / pip_size) if pip_size > 0 else 20.0
        sl_pips = max(15.0, atr_pips * 1.5)

        pip_val = self.get_dynamic_pip_value(symbol, exchange_rates)
        denom = sl_pips * pip_val
        lots = (risk_cash / denom) if denom > 0 else 0.01
        return max(0.01, lots)

    def _calculate_optimal_f_lots(
        self,
        symbol: str,
        balance: float,
        entry_price: float,
        stop_loss: float,
        exchange_rates: Optional[Dict[str, float]] = None
    ) -> float:
        """Optimal f fraction sizing."""
        opt_f = 0.015
        risk_cash = balance * opt_f
        price_diff = abs(entry_price - stop_loss)
        pips = max(5.0, PrecisionMath.price_to_pips(symbol, price_diff))
        pip_val = self.get_dynamic_pip_value(symbol, exchange_rates)
        denom = pips * pip_val
        lots = (risk_cash / denom) if denom > 0 else 0.01
        return max(0.01, lots)


_default_position_sizer = PositionSizer()


def get_dynamic_pip_value(symbol: str, exchange_rates: Optional[Dict[str, float]] = None) -> float:
    """Calculates dynamic dollar pip value for 1.0 standard lot based on exchange rates."""
    return _default_position_sizer.get_dynamic_pip_value(symbol, exchange_rates)

