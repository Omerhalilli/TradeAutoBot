"""
High-Precision Decimal Mathematics & Broker Pip Quantization Engine.
Eliminates floating-point rounding inaccuracies in lot sizing, pip distances,
profit-and-loss valuations, and margin requirements.
"""

from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR, ROUND_CEILING
from typing import Union

# Standard point sizes by symbol class
PIP_SIZES = {
    "EURUSD": Decimal("0.0001"),
    "GBPUSD": Decimal("0.0001"),
    "USDCHF": Decimal("0.0001"),
    "AUDUSD": Decimal("0.0001"),
    "NZDUSD": Decimal("0.0001"),
    "USDCAD": Decimal("0.0001"),
    "USDJPY": Decimal("0.01"),
    "GBPJPY": Decimal("0.01"),
    "EURJPY": Decimal("0.01"),
    "XAUUSD": Decimal("0.01"),   # Gold
    "XAGUSD": Decimal("0.001"),  # Silver
    "USOIL": Decimal("0.01"),   # WTI Crude
    "UKOIL": Decimal("0.01"),   # Brent Crude
    "BTCUSD": Decimal("1.00"),
    "ETHUSD": Decimal("0.10")
}


class PrecisionMath:
    """
    Arbitrary-precision arithmetic helpers for trading calculations.
    """
    @staticmethod
    def to_decimal(val: Union[float, int, str, Decimal]) -> Decimal:
        """Converts arbitrary input to high-precision Decimal safely."""
        if isinstance(val, Decimal):
            return val
        return Decimal(str(val))

    @classmethod
    def get_pip_size(cls, symbol: str) -> Decimal:
        """Returns standard pip increment for a symbol."""
        sym = symbol.upper().replace(".PRO", "").replace(".RAW", "").replace("+", "").replace("M", "")
        return PIP_SIZES.get(sym, Decimal("0.0001"))

    @classmethod
    def price_to_pips(cls, symbol: str, price_diff: Union[float, Decimal]) -> float:
        """Converts raw price difference to pip count."""
        diff = cls.to_decimal(price_diff)
        pip_size = cls.get_pip_size(symbol)
        return float((diff / pip_size).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))

    @classmethod
    def pips_to_price(cls, symbol: str, pips: Union[float, int, Decimal]) -> float:
        """Converts pip count to raw price delta."""
        p = cls.to_decimal(pips)
        pip_size = cls.get_pip_size(symbol)
        return float(p * pip_size)

    @classmethod
    def round_price(cls, symbol: str, price: Union[float, Decimal], digits: int = 5) -> float:
        """Rounds price to symbol decimal digits."""
        sym = symbol.upper()
        if "JPY" in sym or "XAU" in sym or "OIL" in sym:
            digits = 2 if "OIL" in sym or "XAU" in sym else 3
        d = cls.to_decimal(price)
        fmt = Decimal("10") ** -digits
        return float(d.quantize(fmt, rounding=ROUND_HALF_UP))

    @classmethod
    def round_lot(cls, lots: Union[float, Decimal], min_lot: float = 0.01, step_lot: float = 0.01, max_lot: float = 100.0) -> float:
        """Rounds volume down to valid broker lot step size."""
        d_lots = cls.to_decimal(lots)
        d_min = cls.to_decimal(min_lot)
        d_step = cls.to_decimal(step_lot)
        d_max = cls.to_decimal(max_lot)

        if d_lots < d_min:
            return float(d_min)
        if d_lots > d_max:
            return float(d_max)

        steps = (d_lots / d_step).quantize(Decimal("1"), rounding=ROUND_FLOOR)
        rounded = steps * d_step
        return float(rounded.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def round_to_pip(symbol: str, price: float) -> float:
    """Helper shortcut to round price based on symbol digits."""
    return PrecisionMath.round_price(symbol, price)

def round_to_lot(lots: float) -> float:
    """Helper shortcut to quantize lots to standard 0.01 steps."""
    return PrecisionMath.round_lot(lots)
