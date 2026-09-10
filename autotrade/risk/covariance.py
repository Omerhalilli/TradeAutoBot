"""
Real-Time Portfolio Covariance & Correlation Gatekeeper.
Computes live Pearson correlation across active portfolio positions using rolling log returns.
Rejects candidate trades that exceed directional correlation thresholds (e.g., > 0.75) to prevent
unhedged correlated concentration risk.
"""

from __future__ import annotations
import logging
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger("autotrade.risk.covariance")

# Fallback typical inter-asset 30-day baseline Pearson correlations
DEFAULT_BASE_CORRELATIONS: Dict[Tuple[str, str], float] = {
    ("EURUSD", "GBPUSD"): 0.82,
    ("EURUSD", "USDCHF"): -0.88,
    ("GBPUSD", "USDCHF"): -0.76,
    ("EURUSD", "USDJPY"): -0.25,
    ("AUDUSD", "NZDUSD"): 0.86,
    ("EURUSD", "AUDUSD"): 0.65,
    ("USDCAD", "USOIL"): -0.68,
    ("XAUUSD", "EURUSD"): 0.45,
    ("XAUUSD", "USDCHF"): -0.48,
}


def canonical_symbol(sym: str) -> str:
    """Normalizes symbol string to 6-character canonical format."""
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


class PortfolioCovarianceGatekeeper:
    """
    Institutional Portfolio Covariance & Correlation Manager.
    Evaluates joint directional risk to prevent correlated over-exposure across FX, Metals, and Commodities.
    """
    def __init__(self, max_correlation_threshold: float = 0.75, window_bars: int = 30):
        self.max_correlation_threshold = max_correlation_threshold
        self.window_bars = window_bars
        # Cache for historical price series: {symbol: np.ndarray}
        self._price_history: Dict[str, np.ndarray] = {}

    def update_price_history(self, symbol: str, closes: np.ndarray) -> None:
        """Updates rolling close price history for symbol."""
        sym = canonical_symbol(symbol)
        arr = np.asarray(closes, dtype=np.float64)
        if len(arr) >= 5:
            self._price_history[sym] = arr

    def compute_pearson_correlation(self, sym1: str, sym2: str) -> float:
        """
        Calculates Pearson correlation of rolling log returns:
        rho = Cov(r1, r2) / (Std(r1) * Std(r2))
        """
        s1 = canonical_symbol(sym1)
        s2 = canonical_symbol(sym2)
        if s1 == s2:
            return 1.0

        p1 = self._price_history.get(s1)
        p2 = self._price_history.get(s2)

        if p1 is not None and p2 is not None and len(p1) >= 10 and len(p2) >= 10:
            min_len = min(len(p1), len(p2), self.window_bars + 1)
            c1 = p1[-min_len:]
            c2 = p2[-min_len:]
            if len(c1) > 2 and np.all(c1 > 0) and np.all(c2 > 0):
                r1 = np.diff(np.log(c1))
                r2 = np.diff(np.log(c2))
                std1 = np.std(r1)
                std2 = np.std(r2)
                if std1 > 1e-9 and std2 > 1e-9:
                    cov = np.cov(r1, r2)[0, 1]
                    corr = float(cov / (std1 * std2))
                    return max(-1.0, min(1.0, corr))

        # Check default table
        pair_key = (s1, s2) if (s1, s2) in DEFAULT_BASE_CORRELATIONS else (s2, s1)
        if pair_key in DEFAULT_BASE_CORRELATIONS:
            return DEFAULT_BASE_CORRELATIONS[pair_key]

        # Shared base or quote currency heuristic
        b1, q1 = s1[:3], s1[3:6] if len(s1) >= 6 else (s1, "USD")
        b2, q2 = s2[:3], s2[3:6] if len(s2) >= 6 else (s2, "USD")

        if b1 == b2 and q1 == q2:
            return 1.0
        if b1 == q2 and q1 == b2:
            return -1.0
        if q1 == q2 and q1 == "USD":
            # e.g. EURUSD and GBPUSD
            return 0.70
        if b1 == b2 and b1 == "USD":
            # e.g. USDJPY and USDCHF
            return 0.65
        if b1 == q2 or q1 == b2:
            return -0.50

        return 0.0

    def evaluate_candidate_correlation(
        self,
        candidate_symbol: str,
        candidate_direction: str,  # BUY or SELL
        open_positions: List[Dict[str, Any]]
    ) -> Tuple[bool, str, float]:
        """
        Validates whether candidate order creates excessive directional correlation with open portfolio.
        Returns: (passed: bool, reason: str, max_net_correlation: float)
        """
        cand_sym = canonical_symbol(candidate_symbol)
        cand_dir = 1.0 if candidate_direction.upper() == "BUY" else -1.0
        max_net_corr = 0.0
        conflict_sym = ""

        for p in open_positions:
            pos_sym = canonical_symbol(str(p.get("symbol", "")))
            if not pos_sym:
                continue

            pos_cmd = str(p.get("cmd", "BUY")).upper()
            pos_dir = 1.0 if "BUY" in pos_cmd else -1.0

            raw_corr = self.compute_pearson_correlation(cand_sym, pos_sym)
            # Net directional correlation: positive if positions move in same dollar direction
            net_corr = cand_dir * pos_dir * raw_corr

            if net_corr > max_net_corr:
                max_net_corr = net_corr
                conflict_sym = pos_sym

            if net_corr > self.max_correlation_threshold:
                reason = (
                    f"Correlation exposure limit exceeded: Directional correlation with open position {pos_sym} ({pos_cmd}) is too high: "
                    f"{net_corr:.2f} > threshold {self.max_correlation_threshold:.2f}. Risk rejected."
                )
                logger.warning(f"PortfolioCovarianceGatekeeper: {reason}")
                return False, reason, max_net_corr

        return True, "Correlation checks passed", max_net_corr


# Singleton instance
covariance_gatekeeper = PortfolioCovarianceGatekeeper()
