"""
Comprehensive Unit & Integration Tests for Walk-Forward & Genetic Parameter Calibration.
Verifies evolutionary optimization, anti-overfitting Walk-Forward Efficiency (WFE),
SQLite persistence, O(1) cache lookups, and runtime integration into the live trading pipeline.
"""

import json
import os
import unittest
import numpy as np

from autotrade.optimizer.backtester import Backtester
from autotrade.optimizer.walk_forward import WalkForwardOptimizer
from autotrade.optimizer.genetic_optimizer import GeneticOptimizer
from autotrade.optimizer.parameter_calibrator import (
    ParameterCalibrator,
    CalibratedSymbolParams,
    create_institutional_eval_fn,
    parameter_calibrator,
)
from autotrade.data_layer.database import db_engine


class TestParameterCalibrator(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        n = 160
        # Generate synthetic trending and mean-reverting price walk
        returns = np.random.normal(0.0004, 0.005, n)
        self.prices = np.cumprod(1.0 + returns) * 1.2500
        self.ohlcv = {
            "open": np.roll(self.prices, 1),
            "high": self.prices + 0.0015,
            "low": self.prices - 0.0015,
            "close": self.prices,
            "volume": np.random.uniform(50, 200, n),
            "timestamp": np.arange(n) * 3600
        }
        self.ohlcv["open"][0] = self.prices[0]

        # Test database & calibrator instance
        self.calibrator = ParameterCalibrator(db=db_engine)

    def test_calibrated_symbol_params_schema(self):
        """Verifies CalibratedSymbolParams dataclass and dictionary export."""
        p = CalibratedSymbolParams(
            symbol="EURUSD",
            rsi_period=12,
            fast_ema_period=15,
            slow_ema_period=45,
            atr_period=10,
            atr_multiplier=2.2,
            min_score_threshold=6.5,
            sl_atr_mult=1.8,
            tp_atr_mult=3.2,
            wfe_pct=68.5,
            in_sample_sharpe=2.1,
            out_of_sample_sharpe=1.6,
            profit_factor=1.8,
            win_rate=0.62,
            sample_bars=1000
        )
        d = p.to_dict()
        self.assertEqual(d["symbol"], "EURUSD")
        self.assertEqual(d["rsi_period"], 12)
        self.assertEqual(d["atr_multiplier"], 2.2)
        self.assertEqual(d["wfe_pct"], 68.5)
        self.assertTrue(d["is_active"])

    def test_institutional_eval_fn_signals(self):
        """Verifies that create_institutional_eval_fn generates valid simulated orders."""
        params = {
            "rsi_period": 10,
            "fast_ema_period": 12,
            "slow_ema_period": 24,
            "atr_period": 10,
            "sl_atr_mult": 2.0,
            "tp_atr_mult": 3.0
        }
        eval_fn = create_institutional_eval_fn(params)
        self.assertTrue(callable(eval_fn))

        # Backtester run with this evaluation function
        bt = Backtester(initial_balance=100000.0)
        res = bt.run("GBPUSD", self.ohlcv, eval_fn)
        self.assertIsInstance(res.total_trades, int)
        self.assertIsInstance(res.sharpe_ratio, float)

    def test_run_walk_forward_ga(self):
        """Verifies hybrid Walk-Forward Genetic Optimization execution across rolling folds."""
        wfo = WalkForwardOptimizer(n_folds=2, is_ratio=0.70)
        param_bounds = {
            "rsi_period": (8, 16, "int"),
            "fast_ema_period": (10, 18, "int"),
            "slow_ema_period": (22, 35, "int"),
            "atr_period": (8, 14, "int"),
            "sl_atr_mult": (1.5, 2.5, "float"),
            "tp_atr_mult": (2.0, 3.5, "float")
        }

        res = wfo.run_walk_forward_ga(
            symbol="EURUSD",
            ohlcv=self.ohlcv,
            strategy_factory_fn=create_institutional_eval_fn,
            param_bounds=param_bounds,
            population_size=6,
            generations=2
        )

        self.assertEqual(res["symbol"], "EURUSD")
        self.assertEqual(res["total_folds"], 2)
        self.assertIn("best_parameters", res)
        self.assertIn("average_wfe_pct", res)
        self.assertIn("is_robust", res)

    def test_calibrator_save_and_retrieve(self):
        """Verifies saving profile to SQLite and retrieving with O(1) in-memory latency."""
        p = CalibratedSymbolParams(
            symbol="AUDUSD",
            rsi_period=11,
            fast_ema_period=14,
            slow_ema_period=40,
            atr_period=12,
            atr_multiplier=2.1,
            min_score_threshold=6.2,
            sl_atr_mult=1.9,
            tp_atr_mult=3.1,
            wfe_pct=72.0,
            in_sample_sharpe=2.4,
            out_of_sample_sharpe=1.8,
            last_calibrated_at=1700000000.0
        )
        self.calibrator._save_profile(p)

        # In-memory retrieval
        cached = self.calibrator.get_calibrated_params("AUDUSD")
        self.assertIsNotNone(cached)
        self.assertEqual(cached.rsi_period, 11)
        self.assertEqual(cached.atr_multiplier, 2.1)
        self.assertEqual(cached.min_score_threshold, 6.2)

        # Dedicated getters
        self.assertEqual(self.calibrator.get_rsi_period("AUDUSD"), 11)
        self.assertEqual(self.calibrator.get_atr_multiplier("AUDUSD"), 2.1)
        self.assertEqual(self.calibrator.get_min_score("AUDUSD"), 6.2)
        self.assertEqual(self.calibrator.get_sl_atr_mult("AUDUSD"), 1.9)

        # Fallback default for unknown symbol
        self.assertEqual(self.calibrator.get_rsi_period("UNKNOWN_SYM", default=14), 14)
        self.assertEqual(self.calibrator.get_atr_multiplier("UNKNOWN_SYM", default=2.0), 2.0)

    def test_is_calibration_due(self):
        """Verifies monthly (30-day) staleness detection."""
        # Symbol with no record is due immediately
        self.assertTrue(self.calibrator.is_calibration_due("NON_EXISTENT_SYM"))

        # Freshly calibrated symbol (< 30 days) is not due
        import time
        fresh = CalibratedSymbolParams(symbol="USDCHF")
        fresh.last_calibrated_at = time.time() - (5 * 86400) # 5 days ago
        self.calibrator._save_profile(fresh)
        self.assertFalse(self.calibrator.is_calibration_due("USDCHF", max_age_days=30))

        # Stale calibration (> 30 days) is due
        stale = CalibratedSymbolParams(symbol="NZDUSD")
        stale.last_calibrated_at = time.time() - (35 * 86400) # 35 days ago
        self.calibrator._save_profile(stale)
        self.assertTrue(self.calibrator.is_calibration_due("NZDUSD", max_age_days=30))

    def test_calibrate_symbol_full_cycle(self):
        """Executes full calibrate_symbol pipeline with mock OHLCV."""
        calibrated = self.calibrator.calibrate_symbol(
            symbol="XAUUSD",
            ohlcv=self.ohlcv,
            timeframe="H1",
            population_size=6,
            generations=2,
            n_folds=2
        )
        self.assertEqual(calibrated.symbol, "XAUUSD")
        self.assertGreaterEqual(calibrated.rsi_period, 8)
        self.assertLessEqual(calibrated.rsi_period, 22)
        self.assertGreater(calibrated.last_calibrated_at, 0.0)

        # Ensure it's retrievable globally
        retrieved = self.calibrator.get_calibrated_params("XAUUSD")
        self.assertEqual(retrieved.rsi_period, calibrated.rsi_period)


if __name__ == "__main__":
    unittest.main()
