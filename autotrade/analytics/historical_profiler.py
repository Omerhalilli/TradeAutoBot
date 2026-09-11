"""
Background Historical Deep-Replay & Asset Behavioral DNA Profiler.
Executes heavy historical simulations in a dedicated ProcessPoolExecutor on secondary CPU cores,
mines empirical order-flow patterns without lookahead bias across up to 50,000 bars,
persists Asset DNA into SQLite, and provides an O(1) zero-latency empirical gate for live execution.
"""

from __future__ import annotations
import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
import logging
import math
import os
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import numpy as np

from autotrade.analytics.indicators import (
    run_fast_historical_replay,
    indicators,
    ReplayResult,
)
from autotrade.analytics.adaptive_learner import resolve_trading_session
from autotrade.data_layer.database import db_engine
from autotrade.risk.covariance import canonical_symbol

logger = logging.getLogger("autotrade.analytics.historical_profiler")


# ==============================================================================
# 1. ASSET BEHAVIORAL DNA DOMAIN SCHEMA
# ==============================================================================

@dataclass
class AssetDNA:
    """Statistical DNA fingerprint for an asset, setup, and trading session."""
    symbol: str
    setup_type: str = "SNIPER_ALL"       # LIQUIDITY_SWEEP, FVG_MITIGATION, OTE_PULLBACK, SNIPER_ALL
    session: str = "ALL"                 # ASIAN, LONDON, OVERLAP, NY, ALL
    sample_count: int = 0
    win_rate_1r: float = 0.50
    win_rate_2r: float = 0.50
    win_rate_3r: float = 0.30
    median_mfe_pips: float = 0.0
    median_mae_pct: float = 0.0
    optimal_sl_atr_mult: float = 2.0
    optimal_tp_atr_mult: float = 3.0
    expectancy_r: float = 0.0
    profit_factor: float = 1.0
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ==============================================================================
# 2. STANDALONE WORKER FUNCTION (FOR MULTIPROCESSING PROCESSPOOLEXECUTOR)
# ==============================================================================

def _worker_simulate_symbol_dna(
    symbol: str,
    ohlcv_dict: Dict[str, Any],
    pip_size: float = 0.0001,
    max_bars: int = 50000,
    max_holding_bars: int = 72
) -> List[Dict[str, Any]]:
    """
    Isolated worker function executing CPU-bound historical replay simulation.
    Processes chronological bars with strictly zero lookahead bias.
    """
    canon = str(symbol).upper().replace("/", "").replace("_", "").replace("-", "")
    closes = np.asarray(ohlcv_dict.get("close", []), dtype=np.float64)
    highs = np.asarray(ohlcv_dict.get("high", []), dtype=np.float64)
    lows = np.asarray(ohlcv_dict.get("low", []), dtype=np.float64)
    opens = np.asarray(ohlcv_dict.get("open", []), dtype=np.float64)
    times = np.asarray(ohlcv_dict.get("time", ohlcv_dict.get("timestamp", np.zeros_like(closes))), dtype=np.float64)

    n_bars = len(closes)
    if n_bars < 80:
        return []

    # Slice up to max_bars
    if n_bars > max_bars:
        closes = closes[-max_bars:]
        highs = highs[-max_bars:]
        lows = lows[-max_bars:]
        opens = opens[-max_bars:]
        times = times[-max_bars:]
        n_bars = len(closes)

    # Compute baseline ATR array
    atr_arr = indicators.atr(highs, lows, closes, 14)
    valid_atr = atr_arr[~np.isnan(atr_arr)]
    default_atr = float(np.mean(valid_atr)) if len(valid_atr) > 0 else (0.0020 if pip_size < 0.005 else 0.20)

    # Setup Collector: group occurrences by setup_type and session
    # { (setup_type, session): {"indices": [], "directions": [], "prices": [], "atrs": []} }
    setups_map: Dict[Tuple[str, str], Dict[str, List[Any]]] = {}

    def add_setup_occurrence(s_type: str, sess: str, idx: int, direction: int, price: float, atr_val: float):
        # Register specific setup and session
        for s_key in (s_type, "SNIPER_ALL"):
            for sess_key in (sess, "ALL"):
                k = (s_key, sess_key)
                if k not in setups_map:
                    setups_map[k] = {"indices": [], "directions": [], "prices": [], "atrs": []}
                setups_map[k]["indices"].append(idx)
                setups_map[k]["directions"].append(direction)
                setups_map[k]["prices"].append(price)
                setups_map[k]["atrs"].append(atr_val)

    # Walk chronologically from bar 50 to n_bars - max_holding_bars
    eval_limit = max(50, n_bars - max_holding_bars)
    for i in range(50, eval_limit):
        t_sec = float(times[i]) if times[i] > 0 else (time.time() - (n_bars - i) * 900.0)
        curr_session = resolve_trading_session(t_sec)
        c_i = closes[i]
        h_i = highs[i]
        l_i = lows[i]
        o_i = opens[i]

        curr_atr = atr_arr[i]
        if np.isnan(curr_atr) or curr_atr <= 0:
            curr_atr = default_atr

        # ----------------------------------------------------------------------
        # 1. LIQUIDITY SWEEP SETUP
        # ----------------------------------------------------------------------
        # Bearish Sweep: bar swept recent 20-bar high but closed below it
        prior_h20 = np.max(highs[i-20:i])
        if h_i > prior_h20 and c_i < prior_h20:
            add_setup_occurrence("LIQUIDITY_SWEEP", curr_session, i, -1, c_i, curr_atr)

        # Bullish Sweep: bar swept recent 20-bar low but closed above it
        prior_l20 = np.min(lows[i-20:i])
        if l_i < prior_l20 and c_i > prior_l20:
            add_setup_occurrence("LIQUIDITY_SWEEP", curr_session, i, 1, c_i, curr_atr)

        # ----------------------------------------------------------------------
        # 2. FAIR VALUE GAP (FVG) MITIGATION SETUP
        # ----------------------------------------------------------------------
        # Bullish FVG formed at i-2/i-1 (high[i-2] < low[i]): current bar dips into gap
        if i >= 3:
            if highs[i-2] < lows[i] and l_i <= lows[i] and c_i >= highs[i-2]:
                add_setup_occurrence("FVG_MITIGATION", curr_session, i, 1, c_i, curr_atr)
            # Bearish FVG (low[i-2] > high[i]): current bar rallies into gap
            if lows[i-2] > highs[i] and h_i >= highs[i] and c_i <= lows[i-2]:
                add_setup_occurrence("FVG_MITIGATION", curr_session, i, -1, c_i, curr_atr)

        # ----------------------------------------------------------------------
        # 3. OPTIMAL TRADE ENTRY (OTE) PULLBACK SETUP
        # ----------------------------------------------------------------------
        # 50-bar swing range
        range_high = float(np.max(highs[i-50:i+1]))
        range_low = float(np.min(lows[i-50:i+1]))
        r_span = range_high - range_low
        if r_span > 0:
            # Bullish displacement: range formed upward, price pulled back to 61.8% - 78.6%
            ote_l = range_low + 0.214 * r_span
            ote_u = range_low + 0.382 * r_span
            if c_i >= ote_l and c_i <= ote_u and c_i > o_i:
                add_setup_occurrence("OTE_PULLBACK", curr_session, i, 1, c_i, curr_atr)

            # Bearish displacement: price rallied to 61.8% - 78.6% from bottom
            ote_sell_l = range_low + 0.618 * r_span
            ote_sell_u = range_low + 0.786 * r_span
            if c_i >= ote_sell_l and c_i <= ote_sell_u and c_i < o_i:
                add_setup_occurrence("OTE_PULLBACK", curr_session, i, -1, c_i, curr_atr)

    results: List[Dict[str, Any]] = []

    # Run Numba replay simulation for each setup category
    for (setup_type, session), data in setups_map.items():
        n_occurrences = len(data["indices"])
        if n_occurrences == 0:
            continue

        e_idx = np.asarray(data["indices"], dtype=np.int64)
        e_dir = np.asarray(data["directions"], dtype=np.int64)
        e_prc = np.asarray(data["prices"], dtype=np.float64)
        atrs = np.asarray(data["atrs"], dtype=np.float64)

        replay_res: ReplayResult = run_fast_historical_replay(
            high=highs,
            low=lows,
            close=closes,
            open_=opens,
            entry_indices=e_idx,
            entry_directions=e_dir,
            entry_prices=e_prc,
            pip_size=pip_size,
            max_holding_bars=max_holding_bars,
            atr_values=atrs
        )

        dna = AssetDNA(
            symbol=canon,
            setup_type=setup_type,
            session=session,
            sample_count=n_occurrences,
            win_rate_1r=replay_res.win_rate_1r,
            win_rate_2r=replay_res.win_rate_2r,
            win_rate_3r=replay_res.win_rate_3r,
            median_mfe_pips=replay_res.median_mfe_pips,
            median_mae_pct=replay_res.median_mae_pct,
            optimal_sl_atr_mult=replay_res.optimal_sl_atr_mult,
            optimal_tp_atr_mult=replay_res.optimal_tp_atr_mult,
            expectancy_r=replay_res.expectancy_r,
            profit_factor=replay_res.profit_factor,
            last_updated=time.time()
        )
        results.append(dna.to_dict())

    return results


# ==============================================================================
# 3. HISTORICAL PROFILER & EMPIRICAL GATE SUPERVISOR
# ==============================================================================

class HistoricalProfiler:
    """
    Asynchronous historical replay supervisor and empirical Asset DNA manager.
    Maintains persistent SQLite statistical memory and zero-latency in-memory cache.
    """
    def __init__(
        self,
        max_workers: int = 2,
        in_memory_only: bool = False,
        use_threads: bool = False
    ):
        self.max_workers = max_workers
        self.in_memory_only = in_memory_only
        self.use_threads = use_threads
        self._lock = threading.RLock()
        self._dna_cache: Dict[Tuple[str, str, str], AssetDNA] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers) if use_threads else ProcessPoolExecutor(max_workers=max_workers)

        if not in_memory_only:
            self._load_dna_from_db()

    def _load_dna_from_db(self) -> None:
        """Hydrates internal cache with all persisted Asset DNA profiles from SQLite."""
        try:
            rows = db_engine.fetch_all_asset_dna()
            with self._lock:
                for r in rows:
                    dna = AssetDNA(
                        symbol=str(r.get("symbol", "")).upper(),
                        setup_type=str(r.get("setup_type", "SNIPER_ALL")).upper(),
                        session=str(r.get("session", "ALL")).upper(),
                        sample_count=int(r.get("sample_count", 0)),
                        win_rate_1r=float(r.get("win_rate_1r", 0.5)),
                        win_rate_2r=float(r.get("win_rate_2r", 0.5)),
                        win_rate_3r=float(r.get("win_rate_3r", 0.3)),
                        median_mfe_pips=float(r.get("median_mfe_pips", 0.0)),
                        median_mae_pct=float(r.get("median_mae_pct", 0.0)),
                        optimal_sl_atr_mult=float(r.get("optimal_sl_atr_mult", 2.0)),
                        optimal_tp_atr_mult=float(r.get("optimal_tp_atr_mult", 3.0)),
                        expectancy_r=float(r.get("expectancy_r", 0.0)),
                        profit_factor=float(r.get("profit_factor", 1.0)),
                        last_updated=float(r.get("last_updated", time.time()))
                    )
                    self._dna_cache[(dna.symbol, dna.setup_type, dna.session)] = dna
            if rows:
                logger.info(f"HistoricalProfiler: Warmed cache with {len(rows)} Asset DNA profiles from SQLite.")
        except Exception as ex:
            logger.warning(f"HistoricalProfiler: Cache warming notice: {ex}")

    # --------------------------------------------------------------------------
    # Live Pipeline Empirical Gate
    # --------------------------------------------------------------------------
    def get_dna(
        self,
        symbol: str,
        setup_type: str = "SNIPER_ALL",
        session: str = "ALL"
    ) -> Optional[AssetDNA]:
        """
        Fast O(1) in-memory lookup with hierarchical fallback.
        1. Exact (Symbol, Setup, Session)
        2. Session (Symbol, SNIPER_ALL, Session)
        3. Setup (Symbol, Setup, ALL)
        4. Generic (Symbol, SNIPER_ALL, ALL)
        """
        canon = canonical_symbol(symbol).upper()
        s_type = setup_type.upper()
        sess = session.upper()

        with self._lock:
            # 1. Exact match
            dna = self._dna_cache.get((canon, s_type, sess))
            if dna:
                return dna
            # 2. Session match on aggregate sniper setup
            dna = self._dna_cache.get((canon, "SNIPER_ALL", sess))
            if dna:
                return dna
            # 3. Setup match across all sessions
            dna = self._dna_cache.get((canon, s_type, "ALL"))
            if dna:
                return dna
            # 4. Master symbol profile
            dna = self._dna_cache.get((canon, "SNIPER_ALL", "ALL"))
            if dna:
                return dna
        return None

    def check_empirical_gate(
        self,
        symbol: str,
        setup_type: str = "SNIPER_ALL",
        session: str = "ALL"
    ) -> Tuple[bool, str, float, float]:
        """
        Live Pipeline Empirical Gate:
        Evaluates historical performance for the given asset setup:
        - Veto (passed=False) if Win Rate < 50% or Expectancy < 0.0R (sample_count >= 10)
        - Edge Boost (+15 pts) if Win Rate >= 65% and Expectancy > 1.2R (sample_count >= 40)
        - Returns (passed, reason, score_modifier, optimal_sl_atr_mult)
        """
        dna = self.get_dna(symbol, setup_type, session)
        canon = canonical_symbol(symbol)

        if not dna or dna.sample_count < 10:
            # Insufficient historical samples to statistically disqualify
            return True, "Empirical Gate: Neutral (Insufficient historical samples)", 0.0, 2.0

        # Empirical Veto: negative historical expectancy or sub-50% win rate
        if dna.win_rate_2r < 0.50 or dna.expectancy_r < 0.0:
            reason = (
                f"Empirical Asset DNA Veto: {canon} {dna.setup_type} ({dna.session}) "
                f"historically unprofitable (WinRate={dna.win_rate_2r*100:.1f}% < 50%, "
                f"Expectancy={dna.expectancy_r:.2f}R < 0.0R over {dna.sample_count} occurrences)."
            )
            return False, reason, 0.0, dna.optimal_sl_atr_mult

        # Empirical Confluence Boost: proven statistical edge
        if dna.win_rate_2r >= 0.65 and dna.expectancy_r > 1.20 and dna.sample_count >= 40:
            reason = (
                f"Empirical Edge Boost: {canon} {dna.setup_type} ({dna.session}) "
                f"proven high expectancy (+15 pts, WinRate={dna.win_rate_2r*100:.1f}%, "
                f"Expectancy={dna.expectancy_r:.2f}R over {dna.sample_count} occurrences)."
            )
            return True, reason, 15.0, dna.optimal_sl_atr_mult

        reason = (
            f"Empirical Edge Verified: {canon} {dna.setup_type} ({dna.session}) "
            f"WinRate={dna.win_rate_2r*100:.1f}%, Expectancy={dna.expectancy_r:.2f}R "
            f"over {dna.sample_count} occurrences."
        )
        return True, reason, 0.0, dna.optimal_sl_atr_mult

    # --------------------------------------------------------------------------
    # Background Deep-Replay Profiling
    # --------------------------------------------------------------------------
    async def run_symbol_profiling(
        self,
        symbol: str,
        ohlcv: Dict[str, np.ndarray],
        pip_size: float = 0.0001,
        max_bars: int = 50000
    ) -> List[AssetDNA]:
        """
        Executes historical profiling in background ProcessPoolExecutor without blocking live bot.
        Caches and persists learned Asset DNA profiles upon completion.
        """
        loop = asyncio.get_running_loop()
        # Convert numpy arrays into serializable dict for process boundary
        data_payload = {
            "close": np.asarray(ohlcv.get("close", []), dtype=np.float64),
            "high": np.asarray(ohlcv.get("high", []), dtype=np.float64),
            "low": np.asarray(ohlcv.get("low", []), dtype=np.float64),
            "open": np.asarray(ohlcv.get("open", []), dtype=np.float64),
            "time": np.asarray(ohlcv.get("time", ohlcv.get("timestamp", [])), dtype=np.float64),
        }

        try:
            records: List[Dict[str, Any]] = await loop.run_in_executor(
                self._executor,
                _worker_simulate_symbol_dna,
                symbol,
                data_payload,
                pip_size,
                max_bars,
                72
            )
        except Exception as ex:
            logger.error(f"Historical profiling failed for {symbol}: {ex}")
            return []

        dna_list: List[AssetDNA] = []
        with self._lock:
            for rec in records:
                dna = AssetDNA(**rec)
                self._dna_cache[(dna.symbol, dna.setup_type, dna.session)] = dna
                dna_list.append(dna)
                if not self.in_memory_only:
                    try:
                        db_engine.upsert_asset_dna(dna.to_dict())
                    except Exception as db_err:
                        logger.error(f"Failed to persist Asset DNA {dna.symbol} to SQLite: {db_err}")

        logger.info(f"🧬 [ASSET DNA PROFILED] {symbol}: Generated {len(dna_list)} empirical profiles.")
        return dna_list

    def save_dna(self, dna: AssetDNA) -> None:
        """Stores Asset DNA into memory cache and persists to SQLite."""
        with self._lock:
            self._dna_cache[(dna.symbol, dna.setup_type, dna.session)] = dna
        if not self.in_memory_only:
            try:
                db_engine.upsert_asset_dna(dna.to_dict())
            except Exception as ex:
                logger.error(f"Failed to persist Asset DNA for {dna.symbol}: {ex}")

    def clear_all_dna(self) -> None:
        """Clears in-memory DNA profiles."""
        with self._lock:
            self._dna_cache.clear()

    def shutdown(self) -> None:
        """Gracefully shuts down executor workers."""
        self._executor.shutdown(wait=False)


# Global singleton instance
historical_profiler = HistoricalProfiler()
