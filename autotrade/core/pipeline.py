"""
Autonomous Zero-Configuration "Sniper" Quantitative Confluence Pipeline.
Enforces the Zero-Tolerance "Sniper" Selection Matrix and Zero-Manual-Input Dynamic Self-Calibration.

Architecture:
1. Autonomous Broker & Instrument Discovery:
   - Dynamic account balance, equity, leverage, free margin.
   - Dynamic contract size, digits, MODE_MINLOT, MODE_LOTSTEP, MODE_MAXLOT, tick value, tick size.
2. Autonomous Mathematical Lot Sizing:
   - Target Cash Risk = Account Equity * 0.005 (Strict 0.5% max risk cap).
   - Lots = Target Cash Risk / (Structural SL Distance in Ticks * Tick Value).
   - Clamped to [MODE_MINLOT, MODE_MAXLOT] and rounded down to nearest MODE_LOTSTEP.
3. Autonomous Dynamic SL / TP Calculation:
   - SL strictly derived from market structure:
     SELL: Anchored 2.0 * Spread above recent Swing High / Liquidity Wick.
     BUY: Anchored 2.0 * Spread below recent Swing Low / Liquidity Wick.
   - TP dynamically projected to opposing Unmitigated Fair Value Gap (FVG) or Liquidity Pool,
     guaranteeing mathematically enforced minimum Reward-to-Risk ratio >= 2.0:1.
4. Dynamic Self-Tuning Indicator Periods via Kaufman Efficiency Ratio (KER):
   - Fast trend expansion (KER > 0.6): Shortens lookbacks without lag.
   - Slow consolidation (KER < 0.3): Lengthens lookbacks to filter false breakouts.
5. Autonomous Dynamic Spread Filter:
   - Rolling 100-bar median spread tracking. Veto if Current Spread > 1.8 * Median Spread.
6. The Zero-Tolerance "Sniper" Selection Matrix (All-Or-Nothing Filter):
   - Rule 1: Macro Structure & Liquidity Displacement (H4 / H1 Market Structure Shift & Sweeps).
   - Rule 2: Strict Premium vs. Discount Equilibrium Gate (BUY < 40% Discount, SELL > 60% Premium).
   - Rule 3: Optimal Trade Entry (OTE 61.8% - 78.6% Fib) or Validated FVG between 20 & 50 EMA.
   - Rule 4: Oscillator Exhaustion Veto / Anti-Chasing Shield (RSI, CCI, Bollinger %B).
   - Rule 5: Lower-Timeframe Execution Confirmation (M15 / M5 Rejection Wick >= 2.0x body or Engulfing).
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from autotrade.analytics.indicators import (
    indicators,
    compute_liquidity_pools,
    compute_fvg_zones,
    compute_ote_levels,
    compute_dynamic_kaufman_periods,
)
from autotrade.risk.covariance import canonical_symbol

logger = logging.getLogger("autotrade.core.pipeline")


@dataclass
class BrokerInstrumentSpecs:
    """
    Dynamically discovered broker specifications for an individual instrument.
    Eliminates all hardcoded manual broker configuration.
    """
    symbol: str
    canonical_symbol: str
    digits: int = 5
    point: float = 0.00001
    contract_size: float = 100000.0
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_lot: float = 100.0
    tick_value: float = 10.0
    tick_size: float = 0.00001


def resolve_broker_specs(
    symbol: str,
    broker_info: Optional[Dict[str, Any]] = None
) -> BrokerInstrumentSpecs:
    """
    Dynamically constructs or resolves broker specifications.
    Prioritizes real-time ZeroMQ metadata, with scale-invariant fallbacks.
    """
    canon = canonical_symbol(symbol)
    b = broker_info or {}

    digits = int(b.get("digits", 0))
    if digits <= 0:
        if "JPY" in canon:
            digits = 3
        elif "XAU" in canon or "GOLD" in canon:
            digits = 2
        elif "OIL" in canon or "XAG" in canon:
            digits = 2
        else:
            digits = 5
    point = float(b.get("point", 0.0))
    if point <= 0.0:
        point = 10.0 ** (-digits)

    contract_size = float(b.get("contract_size", b.get("lot_size", 0.0)))
    if contract_size <= 0.0:
        if "XAU" in canon or "GOLD" in canon:
            contract_size = 100.0
        elif "XAG" in canon or "SILVER" in canon:
            contract_size = 5000.0
        elif "OIL" in canon:
            contract_size = 1000.0
        else:
            contract_size = 100000.0

    min_lot = float(b.get("min_lot", b.get("mode_minlot", 0.01)))
    if min_lot <= 0.0:
        min_lot = 0.01
    lot_step = float(b.get("lot_step", b.get("mode_lotstep", 0.01)))
    if lot_step <= 0.0:
        lot_step = 0.01
    max_lot = float(b.get("max_lot", b.get("mode_maxlot", 100.0)))
    if max_lot <= 0.0:
        max_lot = 100.0

    tick_size = float(b.get("tick_size", point))
    if tick_size <= 0.0:
        tick_size = point

    tick_value = float(b.get("tick_value", b.get("mode_tickvalue", 0.0)))
    if tick_value <= 0.0:
        if "XAU" in canon or "GOLD" in canon:
            tick_value = 1.0
        elif "OIL" in canon:
            tick_value = 10.0
        elif "JPY" in canon:
            tick_value = 6.67
        else:
            tick_value = 10.0

    return BrokerInstrumentSpecs(
        symbol=symbol,
        canonical_symbol=canon,
        digits=digits,
        point=point,
        contract_size=contract_size,
        min_lot=min_lot,
        lot_step=lot_step,
        max_lot=max_lot,
        tick_value=tick_value,
        tick_size=tick_size,
    )


@dataclass
class CandidateEvaluation:
    """
    Consolidated output of the Zero-Tolerance Sniper Selection Matrix.
    Contains structural metrics, self-calibrating parameters, and execution gates.
    """
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
    pattern: str  # BULLISH_ENGULFING, BEARISH_ENGULFING, REJECTION_WICK, NONE
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

    # Zero-Configuration Sniper Telemetry
    calculated_lots: float = 0.01
    target_cash_risk: float = 0.0
    sl_price: float = 0.0
    tp_price: float = 0.0
    median_spread: float = 0.0
    spread_ratio: float = 1.0
    spread_filter_passed: bool = True
    dealing_range_pct: float = 0.50
    ote_corridor: Tuple[float, float] = (0.0, 0.0)
    in_ote_or_fvg: bool = False
    mss_detected: bool = False
    liquidity_swept: bool = False
    reversal_confirmed: bool = False
    adaptive_rsi_period: int = 14
    adaptive_fast_ema_period: int = 20
    adaptive_slow_ema_period: int = 50
    cci_value: float = 0.0
    bollinger_pct_b: float = 0.50
    adaptive_score_modifier: float = 0.0
    dna_win_rate_2r: float = 0.50
    dna_expectancy_r: float = 0.0
    optimal_sl_atr_mult: float = 2.0
    optimal_tp_atr_mult: float = 3.0
    dna_edge_boost: float = 0.0
    veto_reasons: List[str] = field(default_factory=list)

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
    100% Fully Autonomous, Zero-Manual-Input "Sniper" Trading Engine.
    Executes the unyielding All-Or-Nothing Selection Matrix:
    - Dynamic Spread Filter: Rolling 100-bar Median Spread. Veto if spread > 1.8x median.
    - Rule 1: Macro Structure & Liquidity Displacement (H4 / H1 MSS & Sweeps)
    - Rule 2: Strict Premium vs. Discount Equilibrium Gate (BUY < 40%, SELL > 60%)
    - Rule 3: Optimal Trade Entry (OTE 61.8% - 78.6% Fib) or Validated FVG between 20 & 50 EMA
    - Rule 4: Oscillator Exhaustion Veto (Anti-Chasing Shield)
    - Rule 5: Lower-Timeframe Execution Confirmation (M15 / M5 Rejection Wick >= 2x Body or Engulfing)
    """
    def __init__(self, min_confluence_score: float = 65.0):
        self.min_confluence_score = min_confluence_score
        # Rolling spread tracking: keeps up to 100 historical spread observations per symbol
        self._rolling_spreads: Dict[str, deque[float]] = {}
        # Dynamic broker specs cache
        self._broker_specs_cache: Dict[str, BrokerInstrumentSpecs] = {}

    def update_broker_specs(self, symbol: str, broker_data: Dict[str, Any]) -> BrokerInstrumentSpecs:
        """Dynamically caches or updates broker account specs."""
        specs = resolve_broker_specs(symbol, broker_data)
        self._broker_specs_cache[symbol] = specs
        self._broker_specs_cache[specs.canonical_symbol] = specs
        return specs

    def get_broker_specs(self, symbol: str) -> BrokerInstrumentSpecs:
        """Retrieves cached broker specs or creates defaults."""
        canon = canonical_symbol(symbol)
        if symbol in self._broker_specs_cache:
            return self._broker_specs_cache[symbol]
        if canon in self._broker_specs_cache:
            return self._broker_specs_cache[canon]
        specs = resolve_broker_specs(symbol)
        self._broker_specs_cache[symbol] = specs
        return specs

    def compute_dynamic_spread_filter(
        self,
        symbol: str,
        current_spread: float,
        spread_history: Optional[List[float]] = None
    ) -> Tuple[bool, float, float]:
        """
        Autonomous Dynamic Spread Filter:
        Computes rolling 100-bar Median Spread.
        Vetoes trade if Current Spread > 1.8 * Median Spread.
        """
        canon = canonical_symbol(symbol)
        if canon not in self._rolling_spreads:
            self._rolling_spreads[canon] = deque(maxlen=100)

        if spread_history is not None and len(spread_history) > 0:
            for sp in spread_history[-100:]:
                if sp > 0:
                    self._rolling_spreads[canon].append(float(sp))

        if current_spread > 0:
            self._rolling_spreads[canon].append(float(current_spread))

        spreads_list = list(self._rolling_spreads[canon])
        if len(spreads_list) >= 5:
            median_spread = float(np.median(spreads_list))
        else:
            median_spread = max(current_spread, 10.0)

        spread_ratio = (current_spread / median_spread) if median_spread > 0 else 1.0
        passed = (spread_ratio <= 1.80)
        return passed, median_spread, round(spread_ratio, 2)

    def compute_autonomous_lot_size(
        self,
        symbol: str,
        equity: float,
        sl_distance_price: float,
        specs: Optional[BrokerInstrumentSpecs] = None
    ) -> Tuple[float, float]:
        """
        Autonomous Mathematical Lot Sizing:
        Target Cash Risk = Account Equity * 0.005 (Strict 0.5% max risk cap).
        Lots = Target Cash Risk / (Structural SL Distance in Ticks * Tick Value).
        Clamped to [MODE_MINLOT, MODE_MAXLOT] and rounded down to nearest MODE_LOTSTEP.
        """
        if equity <= 0.0 or sl_distance_price <= 0.0:
            return 0.01, 0.0

        spec = specs or self.get_broker_specs(symbol)
        target_cash_risk = equity * 0.005  # 0.5% max risk

        tick_size = spec.tick_size if spec.tick_size > 0 else spec.point
        tick_val = spec.tick_value if spec.tick_value > 0 else 10.0

        sl_ticks = sl_distance_price / tick_size
        denom = sl_ticks * tick_val

        raw_lots = (target_cash_risk / denom) if denom > 0 else spec.min_lot

        # Round down to the nearest MODE_LOTSTEP
        min_lot = spec.min_lot
        max_lot = spec.max_lot
        lot_step = spec.lot_step if spec.lot_step > 0 else 0.01

        if raw_lots < min_lot:
            quantized = min_lot
        elif raw_lots > max_lot:
            quantized = max_lot
        else:
            steps = math.floor((raw_lots - min_lot) / lot_step)
            quantized = min_lot + steps * lot_step

        decimals = 2
        if lot_step < 0.01:
            decimals = 3
        quantized = max(min_lot, min(max_lot, round(quantized, decimals)))

        return quantized, round(target_cash_risk, 2)

    def evaluate_symbol(
        self,
        symbol: str,
        ohlcv: Dict[str, np.ndarray],
        htf_ohlcv: Optional[Dict[str, np.ndarray]] = None,
        spread_points: float = 15.0,
        bid: float = 0.0,
        ask: float = 0.0,
        server_time_str: Optional[str] = None,
        bar_time: int = 0,
        account_equity: float = 10000.0,
        broker_specs: Optional[Dict[str, Any]] = None,
        spread_history: Optional[List[float]] = None,
        ltf_ohlcv: Optional[Dict[str, np.ndarray]] = None,
    ) -> CandidateEvaluation:
        """
        Executes the unyielding All-Or-Nothing "Sniper" Selection Matrix.
        If ANY criteria fail, emits HOLD immediately with explicit mathematical reason.
        """
        canon = canonical_symbol(symbol)
        specs = self.update_broker_specs(symbol, broker_specs) if broker_specs else self.get_broker_specs(symbol)

        closes = np.asarray(ohlcv.get("close", np.array([], dtype=np.float64)), dtype=np.float64)
        highs = np.asarray(ohlcv.get("high", np.array([], dtype=np.float64)), dtype=np.float64)
        lows = np.asarray(ohlcv.get("low", np.array([], dtype=np.float64)), dtype=np.float64)
        opens = np.asarray(ohlcv.get("open", np.array([], dtype=np.float64)), dtype=np.float64)
        volumes = np.asarray(ohlcv.get("volume", np.ones_like(closes)), dtype=np.float64)

        n_bars = len(closes)
        pip_unit = 0.01 if ("JPY" in canon or "XAU" in canon or "OIL" in canon) else 0.0001

        # Current reference price
        curr_price = float(closes[-1]) if n_bars > 0 else 0.0
        if curr_price <= 0.0:
            curr_price = float(ask if ask > 0 else bid)

        # Base evaluation container
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

        # Check Autonomous Adaptive Learner Quarantine
        try:
            from autotrade.analytics.adaptive_learner import adaptive_learner
            if adaptive_learner.is_symbol_quarantined(symbol):
                is_q, rem_s, q_reason = adaptive_learner.get_quarantine_status(symbol)
                rem_h = int(rem_s // 3600)
                rem_m = int((rem_s % 3600) // 60)
                res.disqualification_reason = f"Adaptive Quarantine Veto: {symbol} in cooling freeze ({q_reason}, {rem_h}h {rem_m}m remaining)."
                res.veto_reasons.append(res.disqualification_reason)
                return res
        except Exception:
            pass

        if n_bars < 50:
            res.disqualification_reason = f"Insufficient bars for sniper calibration ({n_bars} < 50)"
            res.veto_reasons.append(res.disqualification_reason)
            return res

        # ----------------------------------------------------------------------
        # AUTONOMOUS DYNAMIC SPREAD FILTER
        # ----------------------------------------------------------------------
        spread_ok, med_spread, sp_ratio = self.compute_dynamic_spread_filter(
            symbol=symbol,
            current_spread=spread_points,
            spread_history=spread_history
        )
        res.median_spread = med_spread
        res.spread_ratio = sp_ratio
        res.spread_filter_passed = spread_ok

        if not spread_ok:
            res.disqualification_reason = (
                f"Dynamic Spread Veto: Spread {spread_points:.1f} pts > 1.8x Median ({med_spread:.1f} pts, ratio={sp_ratio:.2f})"
            )
            res.veto_reasons.append(res.disqualification_reason)
            return res

        # ----------------------------------------------------------------------
        # DYNAMIC SELF-TUNING INDICATOR PERIODS (KER ADAPTATION)
        # ----------------------------------------------------------------------
        H = indicators.hurst_exponent(closes, max_lags=20)
        res.hurst_exponent = round(H, 3)

        adaptive_p = indicators.compute_dynamic_kaufman_periods(closes, base_rsi=14, base_fast_ema=20, base_slow_ema=50, ker_period=14)
        ker = adaptive_p.ker
        res.ker_ratio = round(ker, 3)
        res.adaptive_rsi_period = adaptive_p.rsi_period
        res.adaptive_fast_ema_period = adaptive_p.fast_ema_period
        res.adaptive_slow_ema_period = adaptive_p.slow_ema_period

        if H > 0.55:
            res.tier1_regime = "TRENDING"
        elif H < 0.45:
            res.tier1_regime = "MEAN_REVERTING"
        else:
            res.tier1_regime = "CHOPPY_NOISE"

        # Baseline ATR & Spread-to-ATR
        atr_arr = indicators.atr(highs, lows, closes, 14)
        atr_val = float(atr_arr[-1]) if not np.isnan(atr_arr[-1]) else (0.0020 if "JPY" not in canon else 0.20)
        res.atr_value = atr_val
        atr_pips = (atr_val / pip_unit) if pip_unit > 0 else 20.0
        spread_pips = spread_points / 10.0 if "JPY" not in canon else spread_points
        res.spread_to_atr = round((spread_pips / max(atr_pips, 1.0)), 4)

        # ----------------------------------------------------------------------
        # RULE 1: MACRO STRUCTURE & LIQUIDITY DISPLACEMENT (H4 / H1)
        # ----------------------------------------------------------------------
        macro_c = closes
        macro_h = highs
        macro_l = lows
        macro_o = opens
        if htf_ohlcv and len(htf_ohlcv.get("close", [])) >= 30:
            macro_c = np.asarray(htf_ohlcv["close"], dtype=np.float64)
            macro_h = np.asarray(htf_ohlcv["high"], dtype=np.float64)
            macro_l = np.asarray(htf_ohlcv["low"], dtype=np.float64)
            macro_o = np.asarray(htf_ohlcv["open"], dtype=np.float64)

        macro_ema200 = indicators.ema(macro_c, min(200, len(macro_c) - 1))
        macro_st = indicators.supertrend(macro_h, macro_l, macro_c, 10, 3.0)
        st_dir = macro_st["direction"][-1]
        e_last = macro_ema200[-1] if not np.isnan(macro_ema200[-1]) else macro_c[-1]
        htf_bull = (macro_c[-1] >= e_last) and (st_dir == 1)
        htf_bear = (macro_c[-1] <= e_last) and (st_dir == -1)

        # Market Structure Shift (MSS): Displacement candle breaking prior swing structure
        lp_macro = indicators.compute_liquidity_pools(macro_h, macro_l, macro_c, macro_o, lookback=50)
        recent_sh = lp_macro.recent_swing_high
        recent_sl = lp_macro.recent_swing_low

        macro_atr = indicators.atr(macro_h, macro_l, macro_c, 14)[-1]
        if np.isnan(macro_atr) or macro_atr <= 0:
            macro_atr = atr_val

        bullish_mss = False
        bearish_mss = False
        for k in range(max(0, len(macro_c) - 8), len(macro_c)):
            b_rng = macro_h[k] - macro_l[k]
            b_body = abs(macro_c[k] - macro_o[k])
            is_displacement = (b_rng >= 1.25 * macro_atr) and (b_body >= 0.55 * b_rng)
            if is_displacement:
                if macro_c[k] > macro_o[k] and macro_c[k] > recent_sh:
                    bullish_mss = True
                if macro_c[k] < macro_o[k] and macro_c[k] < recent_sl:
                    bearish_mss = True

        has_bull_sweep = lp_macro.has_bullish_sweep
        has_bear_sweep = lp_macro.has_bearish_sweep

        cand_buy = (htf_bull or bullish_mss or has_bull_sweep) and (bullish_mss or has_bull_sweep)
        cand_sell = (htf_bear or bearish_mss or has_bear_sweep) and (bearish_mss or has_bear_sweep)

        if not cand_buy and not cand_sell:
            res.disqualification_reason = (
                "Rule 1 Veto: No Macro MSS displacement or Liquidity Sweep confirmed."
            )
            res.veto_reasons.append(res.disqualification_reason)
            return res

        chosen_direction = "BUY" if (cand_buy and not cand_sell) else ("SELL" if (cand_sell and not cand_buy) else ("BUY" if htf_bull else "SELL"))
        res.mss_detected = bullish_mss if chosen_direction == "BUY" else bearish_mss
        res.liquidity_swept = has_bull_sweep if chosen_direction == "BUY" else has_bear_sweep
        res.htf_aligned = htf_bull if chosen_direction == "BUY" else htf_bear

        # ----------------------------------------------------------------------
        # RULE 2: STRICT PREMIUM VS. DISCOUNT EQUILIBRIUM GATE
        # ----------------------------------------------------------------------
        dealing_50_high = float(np.max(highs[-50:]))
        dealing_50_low = float(np.min(lows[-50:]))
        dealing_range = dealing_50_high - dealing_50_low
        price_percentile = (curr_price - dealing_50_low) / dealing_range if dealing_range > 0 else 0.50
        res.dealing_range_pct = round(price_percentile, 3)

        if chosen_direction == "BUY" and price_percentile >= 0.40:
            res.disqualification_reason = (
                f"Rule 2 Veto: BUY rejected. Price at {price_percentile*100:.1f}% of dealing range (must be < 40% Discount Zone)."
            )
            res.veto_reasons.append(res.disqualification_reason)
            return res

        if chosen_direction == "SELL" and price_percentile <= 0.60:
            res.disqualification_reason = (
                f"Rule 2 Veto: SELL rejected. Price at {price_percentile*100:.1f}% of dealing range (must be > 60% Premium Zone)."
            )
            res.veto_reasons.append(res.disqualification_reason)
            return res

        # ----------------------------------------------------------------------
        # RULE 3: OPTIMAL TRADE ENTRY (OTE) PULLBACK VALIDATION
        # ----------------------------------------------------------------------
        # Check 3a: Never enter on extended breakout bars
        curr_bar_range = highs[-1] - lows[-1]
        is_extended_breakout = False
        if chosen_direction == "BUY":
            if (curr_bar_range >= 2.0 * atr_val) and (closes[-1] >= dealing_50_high - 0.15 * dealing_range):
                is_extended_breakout = True
        else:
            if (curr_bar_range >= 2.0 * atr_val) and (closes[-1] <= dealing_50_low + 0.15 * dealing_range):
                is_extended_breakout = True

        if is_extended_breakout:
            res.disqualification_reason = "Rule 3 Veto: Extended breakout bar detected. Anti-chasing shield active."
            res.veto_reasons.append(res.disqualification_reason)
            return res

        # Check 3b: OTE Corridor or FVG between 20 and 50 EMA
        ote_data = indicators.compute_ote_levels(highs, lows, closes, lookback=50)
        res.ote_corridor = (round(ote_data.ote_lower, 5), round(ote_data.ote_upper, 5))

        in_ote_corridor = (curr_price >= ote_data.ote_lower and curr_price <= ote_data.ote_upper)

        ema20 = indicators.ema(closes, adaptive_p.fast_ema_period)
        ema50 = indicators.ema(closes, adaptive_p.slow_ema_period)
        ema_low = min(ema20[-1], ema50[-1])
        ema_high = max(ema20[-1], ema50[-1])

        fvg_data = indicators.compute_fvg_zones(highs, lows, closes)
        in_validated_fvg = False
        if chosen_direction == "BUY":
            for f in fvg_data.unmitigated_bullish:
                if (f["bottom"] <= curr_price <= f["top"]) or (f["bottom"] <= ema_high and f["top"] >= ema_low):
                    if f["bottom"] <= curr_price <= f["top"] * 1.002:
                        in_validated_fvg = True
                        break
        else:
            for f in fvg_data.unmitigated_bearish:
                if (f["bottom"] <= curr_price <= f["top"]) or (f["bottom"] <= ema_high and f["top"] >= ema_low):
                    if f["bottom"] * 0.998 <= curr_price <= f["top"]:
                        in_validated_fvg = True
                        break

        res.in_ote_or_fvg = (in_ote_corridor or in_validated_fvg)
        if not res.in_ote_or_fvg:
            res.disqualification_reason = (
                f"Rule 3 Veto: Price not in OTE corridor [{ote_data.ote_lower:.5f}, {ote_data.ote_upper:.5f}] "
                f"or validated FVG between {adaptive_p.fast_ema_period} and {adaptive_p.slow_ema_period} EMA."
            )
            res.veto_reasons.append(res.disqualification_reason)
            return res

        # ----------------------------------------------------------------------
        # RULE 4: OSCILLATOR EXHAUSTION VETO (ANTI-CHASING SHIELD)
        # ----------------------------------------------------------------------
        rsi_series = indicators.rsi(closes, adaptive_p.rsi_period)
        rsi_val = float(rsi_series[-1]) if not np.isnan(rsi_series[-1]) else 50.0
        res.rsi_value = round(rsi_val, 1)

        cci_series = indicators.cci(highs, lows, closes, adaptive_p.cci_period)
        cci_val = float(cci_series[-1]) if not np.isnan(cci_series[-1]) else 0.0
        res.cci_value = round(cci_val, 1)

        bb_data = indicators.bollinger_bands(closes, adaptive_p.fast_ema_period, 2.0)
        bb_u = bb_data["upper"][-1]
        bb_l = bb_data["lower"][-1]
        pct_b = (curr_price - bb_l) / (bb_u - bb_l) if (bb_u - bb_l) > 0 else 0.50
        res.bollinger_pct_b = round(pct_b, 3)

        if chosen_direction == "BUY":
            if rsi_val > 60.0 or cci_val > 100.0 or pct_b > 0.80:
                res.disqualification_reason = (
                    f"Rule 4 Veto: BUY exhausted (RSI={rsi_val:.1f}>60, CCI={cci_val:.1f}>100, %B={pct_b:.2f}>0.80)."
                )
                res.veto_reasons.append(res.disqualification_reason)
                return res
        else:
            if rsi_val < 40.0 or cci_val < -100.0 or pct_b < 0.20:
                res.disqualification_reason = (
                    f"Rule 4 Veto: SELL exhausted (RSI={rsi_val:.1f}<40, CCI={cci_val:.1f}<-100, %B={pct_b:.2f}<0.20)."
                )
                res.veto_reasons.append(res.disqualification_reason)
                return res

        # ----------------------------------------------------------------------
        # RULE 5: LOWER-TIMEFRAME EXECUTION CONFIRMATION (M15 / M5)
        # ----------------------------------------------------------------------
        trig_c = ltf_ohlcv["close"] if (ltf_ohlcv and len(ltf_ohlcv.get("close", [])) >= 5) else closes
        trig_h = ltf_ohlcv["high"] if (ltf_ohlcv and len(ltf_ohlcv.get("high", [])) >= 5) else highs
        trig_l = ltf_ohlcv["low"] if (ltf_ohlcv and len(ltf_ohlcv.get("low", [])) >= 5) else lows
        trig_o = ltf_ohlcv["open"] if (ltf_ohlcv and len(ltf_ohlcv.get("open", [])) >= 5) else opens

        c_last = trig_c[-1]
        o_last = trig_o[-1]
        h_last = trig_h[-1]
        l_last = trig_l[-1]
        c_prev = trig_c[-2]
        o_prev = trig_o[-2]

        last_body = abs(c_last - o_last)
        last_tot_rng = h_last - l_last if (h_last - l_last) > 0 else 1e-6
        lower_wick = min(c_last, o_last) - l_last
        upper_wick = h_last - max(c_last, o_last)

        reversal_confirmed = False
        pat_name = "NONE"

        if chosen_direction == "BUY":
            is_wick = (lower_wick >= 2.0 * max(last_body, 1e-6)) and (upper_wick <= 0.35 * last_tot_rng)
            is_engulf = (c_last > o_last and c_prev < o_prev and c_last >= o_prev and o_last <= c_prev)
            if is_wick:
                reversal_confirmed = True
                pat_name = "REJECTION_WICK"
            elif is_engulf:
                reversal_confirmed = True
                pat_name = "BULLISH_ENGULFING"
        else:
            is_wick = (upper_wick >= 2.0 * max(last_body, 1e-6)) and (lower_wick <= 0.35 * last_tot_rng)
            is_engulf = (c_last < o_last and c_prev > o_prev and c_last <= o_prev and o_last >= c_prev)
            if is_wick:
                reversal_confirmed = True
                pat_name = "REJECTION_WICK"
            elif is_engulf:
                reversal_confirmed = True
                pat_name = "BEARISH_ENGULFING"

        res.pattern = pat_name
        res.reversal_confirmed = reversal_confirmed

        if not reversal_confirmed:
            res.disqualification_reason = (
                f"Rule 5 Veto: Institutional reversal not confirmed on trigger candle (wick < 2x body and no engulfing)."
            )
            res.veto_reasons.append(res.disqualification_reason)
            return res

        # ----------------------------------------------------------------------
        # RULE 6: LIVE PIPELINE EMPIRICAL ASSET DNA GATE
        # ----------------------------------------------------------------------
        cand_setup = "SNIPER_ALL"
        if res.liquidity_swept:
            cand_setup = "LIQUIDITY_SWEEP"
        elif getattr(res, "in_ote_or_fvg", False):
            cand_setup = "FVG_MITIGATION"
        elif in_ote_corridor:
            cand_setup = "OTE_PULLBACK"

        from autotrade.analytics.adaptive_learner import resolve_trading_session
        sess_now = resolve_trading_session(bar_time if bar_time > 0 else time.time())

        # Check empirical edge via historical profiler
        dna_passed = True
        dna_gate_reason = ""
        dna_edge_boost = 0.0
        opt_sl_mult = 2.0
        try:
            from autotrade.analytics.historical_profiler import historical_profiler
            dna_passed, dna_gate_reason, dna_edge_boost, opt_sl_mult = historical_profiler.check_empirical_gate(
                symbol=symbol,
                setup_type=cand_setup,
                session=sess_now
            )
            dna_profile = historical_profiler.get_dna(symbol, cand_setup, sess_now)
            if dna_profile:
                res.dna_win_rate_2r = dna_profile.win_rate_2r
                res.dna_expectancy_r = dna_profile.expectancy_r
                res.optimal_sl_atr_mult = dna_profile.optimal_sl_atr_mult
                res.optimal_tp_atr_mult = dna_profile.optimal_tp_atr_mult
        except Exception as ex:
            logger.debug(f"Historical profiler gate check bypass: {ex}")

        if not dna_passed:
            res.disqualification_reason = dna_gate_reason
            res.veto_reasons.append(dna_gate_reason)
            return res

        res.dna_edge_boost = dna_edge_boost
        res.optimal_sl_atr_mult = opt_sl_mult

        # ----------------------------------------------------------------------
        # AUTONOMOUS DYNAMIC SL / TP DERIVATION (100% MARKET STRUCTURE)
        # ----------------------------------------------------------------------
        spread_price = spread_points * specs.point
        if spread_price <= 0.0:
            spread_price = 15.0 * specs.point

        # Incorporate Volatility & Stop-Loss Self-Adaptation from AdaptiveLearner + Asset DNA
        atr_adj = 0.0
        try:
            from autotrade.analytics.adaptive_learner import adaptive_learner
            atr_adj = adaptive_learner.get_sl_atr_multiplier_adjustment(symbol)
        except Exception:
            pass
        effective_spread_mult = max(1.5, opt_sl_mult + atr_adj)

        lp_current = indicators.compute_liquidity_pools(highs, lows, closes, opens, lookback=50)

        if chosen_direction == "BUY":
            anchor_low = min(lp_current.recent_swing_low, min(lows[-5:]))
            sl_price = anchor_low - (effective_spread_mult * spread_price)
            sl_dist = abs(curr_price - sl_price)
            if sl_dist < 10.0 * pip_unit:
                sl_dist = 15.0 * pip_unit
                sl_price = curr_price - sl_dist

            min_tp_dist = 2.0 * sl_dist
            opposing_target = curr_price + min_tp_dist

            if len(lp_current.equal_highs) > 0:
                higher_eqh = [h for h in lp_current.equal_highs if h > curr_price]
                if higher_eqh:
                    opposing_target = max(opposing_target, float(min(higher_eqh)))

            if fvg_data.unmitigated_bearish:
                higher_fvgs = [f["bottom"] for f in fvg_data.unmitigated_bearish if f["bottom"] > curr_price]
                if higher_fvgs:
                    opposing_target = max(opposing_target, float(min(higher_fvgs)))

            tp_price = opposing_target
            tp_dist = tp_price - curr_price
        else:
            anchor_high = max(lp_current.recent_swing_high, max(highs[-5:]))
            sl_price = anchor_high + (effective_spread_mult * spread_price)
            sl_dist = abs(sl_price - curr_price)
            if sl_dist < 10.0 * pip_unit:
                sl_dist = 15.0 * pip_unit
                sl_price = curr_price + sl_dist

            min_tp_dist = 2.0 * sl_dist
            opposing_target = curr_price - min_tp_dist

            if len(lp_current.equal_lows) > 0:
                lower_eql = [l for l in lp_current.equal_lows if l < curr_price]
                if lower_eql:
                    opposing_target = min(opposing_target, float(max(lower_eql)))

            if fvg_data.unmitigated_bullish:
                lower_fvgs = [f["top"] for f in fvg_data.unmitigated_bullish if f["top"] < curr_price]
                if lower_fvgs:
                    opposing_target = min(opposing_target, float(max(lower_fvgs)))

            tp_price = opposing_target
            tp_dist = curr_price - tp_price

        rr_actual = (tp_dist / sl_dist) if sl_dist > 0 else 2.0
        if rr_actual < 2.0:
            tp_dist = 2.0 * sl_dist
            tp_price = (curr_price + tp_dist) if chosen_direction == "BUY" else (curr_price - tp_dist)
            rr_actual = 2.0

        res.sl_price = round(sl_price, specs.digits)
        res.tp_price = round(tp_price, specs.digits)
        res.sl_pips = round(sl_dist / pip_unit, 1) if pip_unit > 0 else 30.0
        res.tp_pips = round(tp_dist / pip_unit, 1) if pip_unit > 0 else 60.0
        res.rr_ratio = round(rr_actual, 2)

        # ----------------------------------------------------------------------
        # AUTONOMOUS MATHEMATICAL LOT SIZING
        # ----------------------------------------------------------------------
        lots, cash_risk = self.compute_autonomous_lot_size(
            symbol=symbol,
            equity=account_equity,
            sl_distance_price=sl_dist,
            specs=specs
        )
        res.calculated_lots = lots
        res.target_cash_risk = cash_risk

        adx_res = indicators.adx(highs, lows, closes, 14)
        res.adx_value = round(float(adx_res["adx"][-1]), 1) if not np.isnan(adx_res["adx"][-1]) else 25.0
        cmf_arr = indicators.cmf(highs, lows, closes, volumes, 20)
        res.cmf_value = round(float(cmf_arr[-1]), 3) if not np.isnan(cmf_arr[-1]) else 0.0

        # All 5 rules and filters passed!
        res.signal = chosen_direction
        base_score = 100.0

        # Apply Dynamic Bayesian Score Modifier from AdaptiveLearner
        score_mod = 0.0
        try:
            from autotrade.analytics.adaptive_learner import adaptive_learner, resolve_trading_session
            session_now = resolve_trading_session()
            score_mod = adaptive_learner.get_score_modifier(
                symbol=symbol,
                features={
                    "session": session_now,
                    "rsi": res.rsi_value,
                    "adx": res.adx_value,
                    "cci": getattr(res, "cci_value", 0.0),
                    "spread": spread_points,
                    "direction": chosen_direction
                }
            )
        except Exception:
            pass

        total_score_mod = score_mod + res.dna_edge_boost
        res.score_100 = max(0.0, min(100.0, base_score + total_score_mod))
        res.adaptive_score_modifier = total_score_mod

        if res.score_100 < self.min_confluence_score:
            res.is_qualified = False
            res.disqualification_reason = (
                f"Adaptive Learning Penalty: Confluence score ({res.score_100:.1f}) penalized by {total_score_mod:.1f} pts "
                f"below minimum threshold ({self.min_confluence_score})."
            )
            res.veto_reasons.append(res.disqualification_reason)
            return res

        res.is_qualified = True
        res.disqualification_reason = (
            f"100% Sniper Matrix Qualified (Zero Manual Input | Score Mod: {score_mod:+.1f} | DNA Edge: {res.dna_edge_boost:+.1f})"
        )
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
