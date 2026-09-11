"""
Unit and integration tests for the Background Historical Deep-Replay & Asset DNA Profiler
(HistoricalProfiler), Numba JIT replay kernels, SQLite behavioral DNA persistence,
and QuantitativeConfluenceEngine Empirical Gate integration.
"""

import time
import unittest
import numpy as np
from unittest.mock import patch, MagicMock

from autotrade.analytics.indicators import run_fast_historical_replay, ReplayResult
from autotrade.analytics.historical_profiler import (
    HistoricalProfiler,
    AssetDNA,
    historical_profiler,
    _worker_simulate_symbol_dna,
)
from autotrade.data_layer.database import (
    db_engine,
    upsert_asset_dna,
    fetch_asset_dna,
    fetch_all_asset_dna,
    insert_market_bars,
    fetch_market_bars,
)
from autotrade.core.pipeline import QuantitativeConfluenceEngine, CandidateEvaluation


class TestFastHistoricalReplayKernel(unittest.TestCase):
    """Validates the Numba-accelerated forward trajectory replay and parameter optimizer."""

    def setUp(self):
        np.random.seed(42)

    def test_causal_buy_trajectory(self):
        """Validates causal forward replay on synthetic deterministic upward trajectory."""
        n = 100
        opens = np.ones(n, dtype=np.float64) * 1.1000
        highs = np.ones(n, dtype=np.float64) * 1.1020
        lows = np.ones(n, dtype=np.float64) * 1.0990
        closes = np.ones(n, dtype=np.float64) * 1.1010
        atr = np.ones(n, dtype=np.float64) * 0.0010

        # Create upward run starting after index 10: index 11 to 25 rises steadily
        for i in range(11, 25):
            highs[i] = 1.1000 + (i - 10) * 0.0010
            lows[i] = 1.0995 + (i - 10) * 0.0008
            closes[i] = highs[i] - 0.0002

        # Signal at index 10: BUY
        entry_indices = np.array([10], dtype=np.int64)
        entry_directions = np.array([1], dtype=np.int64)
        entry_prices = np.array([1.1010], dtype=np.float64)
        sl_prices = np.array([1.0995], dtype=np.float64)
        tp_prices = np.array([1.1040], dtype=np.float64)

        res = run_fast_historical_replay(
            high=highs,
            low=lows,
            close=closes,
            open_=opens,
            entry_indices=entry_indices,
            entry_directions=entry_directions,
            entry_prices=entry_prices,
            sl_prices=sl_prices,
            tp_prices=tp_prices,
            pip_size=0.0001,
            max_holding_bars=24,
            atr_values=atr,
        )

        self.assertIsInstance(res, ReplayResult)
        self.assertEqual(res.total_trades, 1)
        self.assertEqual(res.win_rate_1r, 1.0)
        self.assertEqual(res.win_rate_2r, 1.0)
        self.assertGreaterEqual(res.expectancy_r, 1.0)
        self.assertGreater(res.median_mfe_pips, 10.0)

    def test_causal_sell_trajectory(self):
        """Validates causal forward replay on synthetic deterministic downward trajectory."""
        n = 100
        opens = np.ones(n, dtype=np.float64) * 1.1000
        highs = np.ones(n, dtype=np.float64) * 1.1010
        lows = np.ones(n, dtype=np.float64) * 1.0990
        closes = np.ones(n, dtype=np.float64) * 1.1000
        atr = np.ones(n, dtype=np.float64) * 0.0010

        # Create downward drop starting after index 10
        for i in range(11, 25):
            lows[i] = 1.1000 - (i - 10) * 0.0010
            highs[i] = 1.1002 - (i - 10) * 0.0008
            closes[i] = lows[i] + 0.0002

        # Signal at index 10: SELL
        entry_indices = np.array([10], dtype=np.int64)
        entry_directions = np.array([-1], dtype=np.int64)
        entry_prices = np.array([1.1000], dtype=np.float64)
        sl_prices = np.array([1.1015], dtype=np.float64)
        tp_prices = np.array([1.0970], dtype=np.float64)

        res = run_fast_historical_replay(
            high=highs,
            low=lows,
            close=closes,
            open_=opens,
            entry_indices=entry_indices,
            entry_directions=entry_directions,
            entry_prices=entry_prices,
            sl_prices=sl_prices,
            tp_prices=tp_prices,
            pip_size=0.0001,
            max_holding_bars=24,
            atr_values=atr,
        )

        self.assertEqual(res.total_trades, 1)
        self.assertEqual(res.win_rate_1r, 1.0)
        self.assertEqual(res.win_rate_2r, 1.0)
        self.assertGreater(res.median_mfe_pips, 10.0)

    def test_zero_lookahead_and_empty_signals(self):
        """Verifies replay handles zero signals gracefully."""
        n = 50
        opens = np.ones(n, dtype=np.float64) * 1.1000
        highs = opens + 0.0010
        lows = opens - 0.0010
        closes = opens
        atr = np.ones(n, dtype=np.float64) * 0.0010

        empty_indices = np.array([], dtype=np.int64)
        empty_directions = np.array([], dtype=np.int64)
        empty_prices = np.array([], dtype=np.float64)

        res = run_fast_historical_replay(
            high=highs,
            low=lows,
            close=closes,
            open_=opens,
            entry_indices=empty_indices,
            entry_directions=empty_directions,
            entry_prices=empty_prices,
        )
        self.assertEqual(res.total_trades, 0)
        self.assertEqual(res.win_rate_2r, 0.0)
        self.assertEqual(res.expectancy_r, 0.0)
        self.assertEqual(res.profit_factor, 1.0)


class TestDatabaseAssetDNA(unittest.TestCase):
    """Validates SQLite persistence and querying for asset_behavioral_dna and market bars."""

    def test_dna_upsert_and_fetch(self):
        record = {
            "symbol": "EURUSD",
            "setup_type": "SNIPER_ALL",
            "session": "LONDON",
            "sample_count": 45,
            "win_rate_1r": 0.82,
            "win_rate_2r": 0.71,
            "win_rate_3r": 0.58,
            "median_mfe_pips": 24.5,
            "median_mae_pct": 0.15,
            "optimal_sl_atr_mult": 1.75,
            "optimal_tp_atr_mult": 3.25,
            "expectancy_r": 1.42,
            "profit_factor": 2.30,
            "last_updated": 1710150000.0,
        }
        upsert_asset_dna(record)

        fetched = fetch_asset_dna("EURUSD", "SNIPER_ALL", "LONDON")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["symbol"], "EURUSD")
        self.assertEqual(fetched["setup_type"], "SNIPER_ALL")
        self.assertEqual(fetched["session"], "LONDON")
        self.assertEqual(fetched["sample_count"], 45)
        self.assertAlmostEqual(fetched["win_rate_2r"], 0.71, places=2)
        self.assertAlmostEqual(fetched["expectancy_r"], 1.42, places=2)
        self.assertAlmostEqual(fetched["optimal_sl_atr_mult"], 1.75, places=2)

        # Update the same unique key
        record["sample_count"] = 50
        record["win_rate_2r"] = 0.75
        upsert_asset_dna(record)

        updated = fetch_asset_dna("EURUSD", "SNIPER_ALL", "LONDON")
        self.assertEqual(updated["sample_count"], 50)
        self.assertAlmostEqual(updated["win_rate_2r"], 0.75, places=2)

    def test_fetch_all_asset_dna(self):
        upsert_asset_dna({
            "symbol": "GBPUSD",
            "setup_type": "LIQUIDITY_SWEEP",
            "session": "NY",
            "sample_count": 25,
            "win_rate_1r": 0.70,
            "win_rate_2r": 0.60,
            "win_rate_3r": 0.40,
            "median_mfe_pips": 21.0,
            "median_mae_pct": 0.20,
            "optimal_sl_atr_mult": 2.0,
            "optimal_tp_atr_mult": 3.0,
            "expectancy_r": 0.8,
            "profit_factor": 1.8,
            "last_updated": 1710180000.0,
        })
        all_dna = fetch_all_asset_dna("GBPUSD")
        self.assertGreaterEqual(len(all_dna), 1)
        self.assertTrue(any(d["setup_type"] == "LIQUIDITY_SWEEP" for d in all_dna))

    def test_insert_and_fetch_market_bars(self):
        t0 = int(time.time()) - 1000
        bars = [
            (t0 + i * 60, 1.1000 + i * 0.0001, 1.1005 + i * 0.0001, 1.0995 + i * 0.0001, 1.1002 + i * 0.0001, 100.0)
            for i in range(10)
        ]
        insert_market_bars("USDJPY", "M15", bars)

        fetched = fetch_market_bars("USDJPY", "M15", limit=5)
        self.assertEqual(len(fetched), 5)
        self.assertTrue(fetched[0]["timestamp"] < fetched[-1]["timestamp"])


class TestHistoricalProfilerEngine(unittest.TestCase):
    """Validates HistoricalProfiler caching, empirical gate logic, and replay worker."""

    def setUp(self):
        self.profiler = HistoricalProfiler(in_memory_only=True)

    def test_empirical_gate_default_neutral(self):
        """When insufficient data (< 10 samples), gate should allow passage with 0 boost."""
        passed, reason, boost, sl_mult = self.profiler.check_empirical_gate("AUDUSD", "SNIPER_ALL", "LONDON")
        self.assertTrue(passed)
        self.assertEqual(boost, 0.0)
        self.assertEqual(sl_mult, 2.0)

    def test_empirical_gate_veto_low_win_rate(self):
        """When sample_count >= 10 and Win Rate < 50%, gate vetoes setup."""
        dna = AssetDNA(
            symbol="EURUSD",
            setup_type="SNIPER_ALL",
            session="ASIAN",
            sample_count=20,
            win_rate_1r=0.45,
            win_rate_2r=0.40,  # < 50%
            win_rate_3r=0.30,
            median_mfe_pips=12.0,
            median_mae_pct=0.45,
            optimal_sl_atr_mult=2.0,
            optimal_tp_atr_mult=3.0,
            expectancy_r=0.10,
            profit_factor=0.85,
            last_updated=1710120000.0,
        )
        self.profiler.save_dna(dna)

        passed, reason, boost, sl_mult = self.profiler.check_empirical_gate("EURUSD", "SNIPER_ALL", "ASIAN")
        self.assertFalse(passed)
        self.assertIn("Empirical Asset DNA Veto", reason)
        self.assertIn("WinRate=40.0%", reason)

    def test_empirical_gate_veto_negative_expectancy(self):
        """When sample_count >= 10 and Expectancy < 0.0R, gate vetoes setup."""
        dna = AssetDNA(
            symbol="GBPUSD",
            setup_type="FVG_MITIGATION",
            session="NY",
            sample_count=15,
            win_rate_1r=0.55,
            win_rate_2r=0.51,  # >= 50%
            win_rate_3r=0.20,
            median_mfe_pips=10.0,
            median_mae_pct=0.40,
            optimal_sl_atr_mult=2.0,
            optimal_tp_atr_mult=3.0,
            expectancy_r=-0.15,  # Negative expectancy
            profit_factor=0.90,
            last_updated=1710180000.0,
        )
        self.profiler.save_dna(dna)

        passed, reason, boost, sl_mult = self.profiler.check_empirical_gate("GBPUSD", "FVG_MITIGATION", "NY")
        self.assertFalse(passed)
        self.assertIn("Empirical Asset DNA Veto", reason)
        self.assertIn("Expectancy=-0.15R", reason)

    def test_empirical_gate_proven_edge_boost(self):
        """When sample_count >= 40, Win Rate >= 65%, and Expectancy > 1.20R, grant +15 pt boost."""
        dna = AssetDNA(
            symbol="XAUUSD",
            setup_type="LIQUIDITY_SWEEP",
            session="LONDON",
            sample_count=48,
            win_rate_1r=0.85,
            win_rate_2r=0.72,  # >= 65%
            win_rate_3r=0.60,
            median_mfe_pips=28.0,
            median_mae_pct=0.15,
            optimal_sl_atr_mult=1.75,
            optimal_tp_atr_mult=3.5,
            expectancy_r=1.45,  # > 1.20R
            profit_factor=2.40,
            last_updated=1710150000.0,
        )
        self.profiler.save_dna(dna)

        passed, reason, boost, sl_mult = self.profiler.check_empirical_gate("XAUUSD", "LIQUIDITY_SWEEP", "LONDON")
        self.assertTrue(passed)
        self.assertEqual(boost, 15.0)
        self.assertEqual(sl_mult, 1.75)
        self.assertIn("Empirical Edge Boost", reason)
        self.assertIn("+15 pts", reason)

    def test_worker_simulation_synthetic_ohlcv(self):
        """Validates standalone picklable worker simulation across setups and sessions."""
        n = 500
        np.random.seed(123)
        returns = np.random.normal(0.0001, 0.002, n)
        c = np.cumprod(1.0 + returns) * 1.1000
        h = c + np.abs(np.random.normal(0, 0.001, n))
        l = c - np.abs(np.random.normal(0, 0.001, n))
        o = np.roll(c, 1)
        o[0] = c[0]
        v = np.random.uniform(500, 2000, n)
        timestamps = np.arange(1710000000, 1710000000 + n * 900, 900, dtype=np.int64)

        bars_dict = {
            "time": timestamps,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
        }

        results = _worker_simulate_symbol_dna(
            symbol="EURUSD",
            ohlcv_dict=bars_dict,
            pip_size=0.0001,
            max_bars=500,
            max_holding_bars=48,
        )
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

        for d in results:
            self.assertEqual(d["symbol"], "EURUSD")
            self.assertIn(d["setup_type"], ("LIQUIDITY_SWEEP", "FVG_MITIGATION", "OTE_PULLBACK", "SNIPER_ALL"))
            self.assertIn(d["session"], ("ASIAN", "LONDON", "OVERLAP", "NY", "ALL"))
            self.assertGreaterEqual(d["optimal_sl_atr_mult"], 1.0)
            self.assertGreaterEqual(d["optimal_tp_atr_mult"], 1.5)


class TestPipelineEmpiricalGateIntegration(unittest.TestCase):
    """Validates QuantitativeConfluenceEngine integration with Rule 6 Asset DNA Gate."""

    def setUp(self):
        historical_profiler.clear_all_dna()
        self.engine = QuantitativeConfluenceEngine(min_confluence_score=70.0)

    def tearDown(self):
        historical_profiler.clear_all_dna()

    def test_pipeline_empirical_gate_veto(self):
        """Validates empirical gate check directly and via pipeline telemetry."""
        sym = "GBPUSD"
        # Seed unprofitable DNA
        dna = AssetDNA(
            symbol=sym,
            setup_type="SNIPER_ALL",
            session="LONDON",
            sample_count=30,
            win_rate_1r=0.40,
            win_rate_2r=0.35,  # Veto: < 50%
            win_rate_3r=0.20,
            median_mfe_pips=10.0,
            median_mae_pct=0.55,
            optimal_sl_atr_mult=2.0,
            optimal_tp_atr_mult=3.0,
            expectancy_r=-0.30,
            profit_factor=0.65,
            last_updated=1710150000.0,
        )
        historical_profiler.save_dna(dna)

        passed, reason, boost, sl_mult = historical_profiler.check_empirical_gate(sym, "SNIPER_ALL", "LONDON")
        self.assertFalse(passed)
        self.assertIn("Empirical Asset DNA Veto", reason)

    def test_pipeline_empirical_gate_boost(self):
        """Candidate receives +15.0 pt boost and optimal SL multiplier when DNA has proven edge."""
        sym = "USDCHF"
        dna = AssetDNA(
            symbol=sym,
            setup_type="SNIPER_ALL",
            session="LONDON",
            sample_count=45,
            win_rate_1r=0.85,
            win_rate_2r=0.75,  # >= 65%
            win_rate_3r=0.60,
            median_mfe_pips=29.0,
            median_mae_pct=0.14,
            optimal_sl_atr_mult=1.65,
            optimal_tp_atr_mult=3.30,
            expectancy_r=1.50,  # > 1.20R
            profit_factor=2.60,
            last_updated=1710150000.0,
        )
        historical_profiler.save_dna(dna)

        passed, reason, boost, sl_mult = historical_profiler.check_empirical_gate(sym, "SNIPER_ALL", "LONDON")
        self.assertTrue(passed)
        self.assertEqual(boost, 15.0)
        self.assertEqual(sl_mult, 1.65)
        self.assertIn("Empirical Edge Boost", reason)
        self.assertIn("+15 pts", reason)

    def test_pipeline_candidate_dna_attributes(self):
        """Validates CandidateEvaluation schema includes all required Asset DNA telemetry."""
        candidate = CandidateEvaluation(
            symbol="EURUSD",
            canonical_symbol="EURUSD",
            signal="BUY",
            score_100=80.0,
            tier1_regime="TRENDING",
            hurst_exponent=0.65,
            ker_ratio=0.5,
            htf_aligned=True,
            adx_value=30.0,
            rsi_value=55.0,
            cmf_value=0.1,
            vwap_aligned=True,
            volume_surge=True,
            pattern="BULLISH_ENGULFING",
            spread_points=12.0,
            atr_value=0.0020,
            spread_to_atr=0.6,
            sl_pips=20.0,
            tp_pips=40.0,
            rr_ratio=2.0,
            dna_win_rate_2r=0.68,
            dna_expectancy_r=1.35,
            optimal_sl_atr_mult=1.8,
            optimal_tp_atr_mult=3.2,
            dna_edge_boost=15.0
        )
        self.assertEqual(candidate.dna_win_rate_2r, 0.68)
        self.assertEqual(candidate.dna_expectancy_r, 1.35)
        self.assertEqual(candidate.optimal_sl_atr_mult, 1.8)
        self.assertEqual(candidate.optimal_tp_atr_mult, 3.2)
        self.assertEqual(candidate.dna_edge_boost, 15.0)

    def test_profiler_persistent_sqlite_mode(self):
        """Validates HistoricalProfiler with SQLite persistence and recovery."""
        profiler = HistoricalProfiler(in_memory_only=False)
        dna = AssetDNA(
            symbol="EURJPY",
            setup_type="OTE_PULLBACK",
            session="OVERLAP",
            sample_count=42,
            win_rate_1r=0.80,
            win_rate_2r=0.70,
            win_rate_3r=0.55,
            median_mfe_pips=35.0,
            median_mae_pct=0.12,
            optimal_sl_atr_mult=1.85,
            optimal_tp_atr_mult=3.15,
            expectancy_r=1.30,
            profit_factor=2.20,
            last_updated=time.time(),
        )
        profiler.save_dna(dna)

        # Create another instance pointing to same DB, verify it fetches from SQLite
        fresh_profiler = HistoricalProfiler(in_memory_only=False)
        recovered = fresh_profiler.get_dna("EURJPY", "OTE_PULLBACK", "OVERLAP")
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.symbol, "EURJPY")
        self.assertEqual(recovered.setup_type, "OTE_PULLBACK")
        self.assertEqual(recovered.session, "OVERLAP")
        self.assertEqual(recovered.sample_count, 42)
        self.assertAlmostEqual(recovered.win_rate_2r, 0.70, places=2)
        self.assertAlmostEqual(recovered.expectancy_r, 1.30, places=2)


if __name__ == "__main__":
    unittest.main()

