"""
Institutional 5-Tier Quantitative Confluence Scoring & Screener Engine.
Evaluates multi-timeframe quantitative confluence across five rigorous institutional tiers:
Tier 1: Market Regime Identification (Kaufman Efficiency Ratio & Hurst Exponent H)
Tier 2: Higher-Timeframe (HTF) Macro Bias (D1 & H4 200 EMA and SuperTrend 10, 3.0)
Tier 3: Momentum, Volume & Oscillator Corridors (ADX >= 22, RSI Corridors, CMF, VWAP, Volume Surge)
Tier 4: Market Structure & Candlestick Confirmation (ZigZag pivots, Liquidity Sweeps, Hammer/Star/Engulfing)
Tier 5: Normalized Cross-Asset Ranking (0 - 100 Points, Scale-Invariant Spread-to-ATR ratio)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from autotrade.analytics.indicators import indicators
from autotrade.risk.covariance import canonical_symbol

logger = logging.getLogger("autotrade.core.pipeline")


@dataclass
class CandidateEvaluation:
    symbol: str
    canonical_symbol: str
    signal: str  # BUY, SELL, HOLD
    score_100: float  # 0.0 to 100.0
    tier1_regime: str  # TRENDING, MEAN_REVERTING, CHOPPY_NOISE
    hurst_exponent: float
    ker_ratio: float
    htf_aligned: bool
    adx_value: float
    rsi_value: float
    cmf_value: float
    vwap_aligned: bool
    volume_surge: bool
    pattern: str  # BULLISH_ENGULFING, BEARISH_ENGULFING, HAMMER, SHOOTING_STAR, NONE
    spread_points: float
    atr_value: float
    spread_to_atr: float
    sl_pips: float
    tp_pips: float
    rr_ratio: float
    bid: float = 0.0
    ask: float = 0.0
    bar_time: int = 0
    is_qualified: bool = False
    disqualification_reason: str = ""

    def rank_sort_key(self) -> Tuple[float, float, float]:
        """
        Scale-invariant multi-factor sort key:
        1. Confluence Score (Descending: -score_100)
        2. Spread-to-ATR ratio (Ascending: spread_to_atr)
        3. Reward-to-Risk ratio (Descending: -rr_ratio)
        """
        return (-self.score_100, self.spread_to_atr, -self.rr_ratio)


class QuantitativeConfluenceEngine:
    """
    Institutional 5-Tier Market Surveillance & Confluence Scoring Engine.
    """
    def __init__(self, min_confluence_score: float = 65.0):
        self.min_confluence_score = min_confluence_score

    def evaluate_symbol(
        self,
        symbol: str,
        ohlcv: Dict[str, np.ndarray],
        htf_ohlcv: Optional[Dict[str, np.ndarray]] = None,
        spread_points: float = 15.0,
        bid: float = 0.0,
        ask: float = 0.0,
        server_time_str: Optional[str] = None,
        bar_time: int = 0
    ) -> CandidateEvaluation:
        """
        Evaluates an individual instrument across all 5 quantitative tiers.
        """
        canon = canonical_symbol(symbol)
        closes = ohlcv.get("close", np.array([], dtype=np.float64))
        highs = ohlcv.get("high", np.array([], dtype=np.float64))
        lows = ohlcv.get("low", np.array([], dtype=np.float64))
        opens = ohlcv.get("open", np.array([], dtype=np.float64))
        volumes = ohlcv.get("volume", np.ones_like(closes))

        n_bars = len(closes)
        pip_unit = 0.01 if ("JPY" in canon or "XAU" in canon or "OIL" in canon) else 0.0001

        # Base evaluation placeholder
        res = CandidateEvaluation(
            symbol=symbol,
            canonical_symbol=canon,
            signal="HOLD",
            score_100=0.0,
            tier1_regime="CHOPPY_NOISE",
            hurst_exponent=0.50,
            ker_ratio=0.0,
            htf_aligned=False,
            adx_value=0.0,
            rsi_value=50.0,
            cmf_value=0.0,
            vwap_aligned=False,
            volume_surge=False,
            pattern="NONE",
            spread_points=spread_points,
            atr_value=0.0020,
            spread_to_atr=1.0,
            sl_pips=30.0,
            tp_pips=60.0,
            rr_ratio=2.0,
            bid=bid,
            ask=ask,
            bar_time=bar_time,
            is_qualified=False,
            disqualification_reason=""
        )

        if n_bars < 35:
            res.disqualification_reason = f"Insufficient bars ({n_bars} < 35)"
            return res

        # ----------------------------------------------------------------------
        # Tier 1: Market Regime Identification (KER & Hurst Exponent H)
        # ----------------------------------------------------------------------
        H = indicators.hurst_exponent(closes, max_lags=20)
        res.hurst_exponent = round(H, 3)

        ker_series = indicators.kaufman_efficiency_ratio(closes, period=14)
        ker = float(ker_series[-1]) if not np.isnan(ker_series[-1]) else 0.30
        res.ker_ratio = round(ker, 3)

        if H > 0.55:
            res.tier1_regime = "TRENDING"
        elif H < 0.45:
            res.tier1_regime = "MEAN_REVERTING"
        else:
            res.tier1_regime = "CHOPPY_NOISE"

        # Veto if random noise
        if res.tier1_regime == "CHOPPY_NOISE" and ker < 0.40:
            res.disqualification_reason = f"Tier 1 Veto: Choppy Noise Regime (H={H:.2f}, KER={ker:.2f})"
            return res

        # ----------------------------------------------------------------------
        # Tier 2: Higher-Timeframe (HTF) Macro Bias
        # ----------------------------------------------------------------------
        # Evaluate H4 / D1 if available, otherwise 200 EMA + SuperTrend on current TF
        htf_bullish = False
        htf_bearish = False

        if htf_ohlcv and len(htf_ohlcv.get("close", [])) >= 50:
            htf_c = htf_ohlcv["close"]
            htf_h = htf_ohlcv["high"]
            htf_l = htf_ohlcv["low"]
            htf_ema200 = indicators.ema(htf_c, min(200, len(htf_c) - 1))
            htf_st = indicators.supertrend(htf_h, htf_l, htf_c, 10, 3.0)
            st_dir = htf_st["direction"][-1]
            c_last = htf_c[-1]
            e_last = htf_ema200[-1] if not np.isnan(htf_ema200[-1]) else c_last
            htf_bullish = (c_last >= e_last) and (st_dir == 1)
            htf_bearish = (c_last <= e_last) and (st_dir == -1)
        else:
            ema200 = indicators.ema(closes, min(200, n_bars - 1))
            st = indicators.supertrend(highs, lows, closes, 10, 3.0)
            st_dir = st["direction"][-1]
            c_last = closes[-1]
            e_last = ema200[-1] if not np.isnan(ema200[-1]) else c_last
            htf_bullish = (c_last >= e_last) and (st_dir == 1)
            htf_bearish = (c_last <= e_last) and (st_dir == -1)

        # ----------------------------------------------------------------------
        # Tier 3: Momentum, Volume & Oscillator Corridors
        # ----------------------------------------------------------------------
        adx_res = indicators.adx(highs, lows, closes, 14)
        adx_val = float(adx_res["adx"][-1]) if not np.isnan(adx_res["adx"][-1]) else 20.0
        res.adx_value = round(adx_val, 1)

        rsi_arr = indicators.rsi(closes, 14)
        rsi_val = float(rsi_arr[-1]) if not np.isnan(rsi_arr[-1]) else 50.0
        res.rsi_value = round(rsi_val, 1)

        cmf_arr = indicators.cmf(highs, lows, closes, volumes, 20)
        cmf_val = float(cmf_arr[-1]) if not np.isnan(cmf_arr[-1]) else 0.0
        res.cmf_value = round(cmf_val, 3)

        vwap_arr = indicators.vwap(highs, lows, closes, volumes)
        vwap_val = float(vwap_arr[-1]) if not np.isnan(vwap_arr[-1]) else closes[-1]

        # Volume Surge: Trigger bar volume >= 1.25x 20-period Volume SMA
        vol_sma20 = float(np.mean(volumes[-21:-1])) if len(volumes) >= 21 else float(volumes[-1])
        vol_surge = (volumes[-1] >= 1.25 * vol_sma20) if vol_sma20 > 0 else True
        res.volume_surge = vol_surge

        # ----------------------------------------------------------------------
        # Tier 4: Market Structure & Candlestick Confirmation
        # ----------------------------------------------------------------------
        pattern = "NONE"
        c_curr = closes[-1]
        o_curr = opens[-1]
        h_curr = highs[-1]
        l_curr = lows[-1]
        c_prev = closes[-2]
        o_prev = opens[-2]

        body = abs(c_curr - o_curr)
        total_range = h_curr - l_curr if (h_curr - l_curr) > 0 else 1e-6
        lower_wick = (min(c_curr, o_curr) - l_curr)
        upper_wick = (h_curr - max(c_curr, o_curr))

        # Bullish / Bearish Engulfing
        if c_curr > o_curr and c_prev < o_prev and c_curr >= o_prev and o_curr <= c_prev:
            pattern = "BULLISH_ENGULFING"
        elif c_curr < o_curr and c_prev > o_prev and c_curr <= o_prev and o_curr >= c_prev:
            pattern = "BEARISH_ENGULFING"
        # Hammer (lower wick >= 2.0x body, small upper wick)
        elif lower_wick >= 2.0 * max(body, 1e-6) and upper_wick <= 0.3 * total_range:
            pattern = "HAMMER"
        # Shooting Star (upper wick >= 2.0x body, small lower wick)
        elif upper_wick >= 2.0 * max(body, 1e-6) and lower_wick <= 0.3 * total_range:
            pattern = "SHOOTING_STAR"

        res.pattern = pattern

        # ----------------------------------------------------------------------
        # Directional Synthesis & Scored Confluence
        # ----------------------------------------------------------------------
        score = 0.0

        # Check candidate BUY vs SELL
        buy_points = 0.0
        sell_points = 0.0

        # Tier 1 scoring (max 20 pts)
        if res.tier1_regime == "TRENDING":
            buy_points += 15.0
            sell_points += 15.0
            if ker > 0.50:
                buy_points += 5.0
                sell_points += 5.0
        elif res.tier1_regime == "MEAN_REVERTING":
            buy_points += 10.0
            sell_points += 10.0

        # Tier 2 scoring (max 25 pts)
        if htf_bullish:
            buy_points += 25.0
        elif htf_bearish:
            sell_points += 25.0

        # Tier 3 scoring (max 30 pts)
        # ADX trend strength (10 pts)
        if adx_val >= 25.0:
            buy_points += 10.0
            sell_points += 10.0
        elif adx_val >= 22.0:
            buy_points += 7.0
            sell_points += 7.0

        # RSI Momentum Corridors (10 pts)
        if 45.0 <= rsi_val <= 65.0:
            buy_points += 10.0
        if 35.0 <= rsi_val <= 55.0:
            sell_points += 10.0

        # CMF Flow & VWAP (10 pts)
        if cmf_val > 0.03 and c_curr > vwap_val:
            buy_points += 10.0
        elif cmf_val < -0.03 and c_curr < vwap_val:
            sell_points += 10.0

        # Tier 4 Candlestick & Volume Surge (max 25 pts)
        if vol_surge:
            buy_points += 5.0
            sell_points += 5.0

        if pattern in ("BULLISH_ENGULFING", "HAMMER"):
            buy_points += 20.0
        elif pattern in ("BEARISH_ENGULFING", "SHOOTING_STAR"):
            sell_points += 20.0

        # Final Signal Verdict
        chosen_signal = "HOLD"
        final_score = 0.0

        if buy_points > sell_points and buy_points >= self.min_confluence_score and htf_bullish:
            chosen_signal = "BUY"
            final_score = buy_points
            res.htf_aligned = True
            res.vwap_aligned = (c_curr > vwap_val)
        elif sell_points > buy_points and sell_points >= self.min_confluence_score and htf_bearish:
            chosen_signal = "SELL"
            final_score = sell_points
            res.htf_aligned = True
            res.vwap_aligned = (c_curr < vwap_val)
        else:
            final_score = max(buy_points, sell_points)
            res.disqualification_reason = (
                f"Confluence below threshold ({final_score:.1f}/{self.min_confluence_score}) or HTF misaligned."
            )

        res.signal = chosen_signal
        res.score_100 = round(min(100.0, final_score), 1)

        # ----------------------------------------------------------------------
        # Tier 5: Normalized ATR & Spread Penalty Calculation
        # ----------------------------------------------------------------------
        atr_arr = indicators.atr(highs, lows, closes, 14)
        atr_val = float(atr_arr[-1]) if not np.isnan(atr_arr[-1]) else (0.0020 if "JPY" not in canon else 0.20)
        res.atr_value = atr_val

        atr_pips = (atr_val / pip_unit) if pip_unit > 0 else 20.0
        spread_pips = spread_points / 10.0 if "JPY" not in canon else spread_points

        # Normalized Spread-to-ATR ratio
        res.spread_to_atr = round((spread_pips / max(atr_pips, 1.0)), 4)

        # Stop loss & take profit calculation
        sl_pips = max(15.0, round(atr_pips * 1.5, 1))
        tp_pips = max(30.0, round(sl_pips * 2.0, 1))
        res.sl_pips = sl_pips
        res.tp_pips = tp_pips
        res.rr_ratio = round((tp_pips / sl_pips) if sl_pips > 0 else 1.5, 2)

        # Qualification check
        if chosen_signal in ("BUY", "SELL") and res.score_100 >= self.min_confluence_score:
            res.is_qualified = True
            res.disqualification_reason = "Qualified institutional setup"

        return res

    def rank_candidates(self, candidates: List[CandidateEvaluation]) -> List[CandidateEvaluation]:
        """
        Sorts qualified candidate setups by scale-invariant ranking:
        1. Confluence Score (descending)
        2. Spread-to-ATR ratio (ascending)
        3. Reward-to-Risk ratio (descending)
        """
        qualified = [c for c in candidates if c.is_qualified]
        qualified.sort(key=lambda c: c.rank_sort_key())
        return qualified

    def select_best_opportunity(self, candidates: List[CandidateEvaluation]) -> Optional[CandidateEvaluation]:
        """Selects the single highest-probability setup across the portfolio per cycle."""
        ranked = self.rank_candidates(candidates)
        return ranked[0] if ranked else None


# Singleton instance
confluence_engine = QuantitativeConfluenceEngine()
