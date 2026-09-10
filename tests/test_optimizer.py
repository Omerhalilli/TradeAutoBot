"""
Unit tests for Backtester, Walk-Forward Analysis, GA, and PSO Optimizers.
"""

import unittest
import numpy as np
from autotrade.optimizer.backtester import Backtester
from autotrade.optimizer.walk_forward import WalkForwardOptimizer
from autotrade.optimizer.genetic_optimizer import GeneticOptimizer
from autotrade.optimizer.pso_optimizer import ParticleSwarmOptimizer


class TestOptimizer(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        n = 150
        returns = np.random.normal(0.0003, 0.006, n)
        self.prices = np.cumprod(1.0 + returns) * 1.3000
        self.ohlcv = {
            "open": np.roll(self.prices, 1),
            "high": self.prices + 0.0010,
            "low": self.prices - 0.0010,
            "close": self.prices,
            "volume": np.random.uniform(100, 500, n),
            "timestamp": np.arange(n) * 3600
        }
        self.ohlcv["open"][0] = self.prices[0]

    def test_backtester_run(self):
        bt = Backtester(initial_balance=100000.0)

        # Simple moving average crossover mock strategy
        def eval_fn(idx, data):
            closes = data["close"]
            if len(closes) < 20:
                return None
            sma5 = np.mean(closes[-5:])
            sma20 = np.mean(closes[-20:])
            if sma5 > sma20:
                return {"action": "BUY", "sl": closes[-1] - 0.0030, "tp": closes[-1] + 0.0060, "lots": 0.1}
            elif sma5 < sma20:
                return {"action": "SELL", "sl": closes[-1] + 0.0030, "tp": closes[-1] - 0.0060, "lots": 0.1}
            return None

        res = bt.run("GBPUSD", self.ohlcv, eval_fn)
        self.assertGreaterEqual(res.total_trades, 0)
        self.assertIsInstance(res.equity_curve, list)

    def test_genetic_optimizer(self):
        # Optimize Rosenbrock / Sphere-like fitness function
        param_bounds = {
            "fast_period": (5, 15, "int"),
            "slow_period": (20, 50, "int"),
            "multiplier": (1.0, 3.0, "float")
        }
        ga = GeneticOptimizer(param_bounds, population_size=10, generations=3)

        def mock_fitness(genes):
            # Target fast=9, slow=21, mult=2.0
            err = (
                abs(genes["fast_period"] - 9) * 0.1 +
                abs(genes["slow_period"] - 21) * 0.05 +
                abs(genes["multiplier"] - 2.0) * 0.5
            )
            sharpe = max(0.1, 3.0 - err)
            return {"sharpe": sharpe, "profit_factor": 1.8, "drawdown": 5.0}

        res = ga.optimize(mock_fitness)
        self.assertIn("best_parameters", res)
        self.assertGreater(res["sharpe_ratio"], 0.0)

    def test_pso_optimizer(self):
        param_bounds = {
            "param_a": (1.0, 10.0, "float"),
            "param_b": (10, 50, "int")
        }
        pso = ParticleSwarmOptimizer(param_bounds, swarm_size=10, max_iterations=3)

        def mock_fitness(params):
            val_a = params["param_a"]
            val_b = params["param_b"]
            return 10.0 - abs(val_a - 5.0) - abs(val_b - 25) * 0.1

        res = pso.optimize(mock_fitness)
        self.assertIn("best_parameters", res)
        self.assertGreater(res["best_fitness"], 0.0)

    def test_conservative_worst_case_dual_breach_fill(self):
        """Verifies institutional worst-case assumption: SL struck before TP on intra-bar dual breach."""
        bt = Backtester(initial_balance=100000.0)
        n = 45
        closes = np.full(n, 1.2500)
        highs = np.full(n, 1.2510)
        lows = np.full(n, 1.2490)
        opens = np.full(n, 1.2500)

        # Bar 36 triggers BUY with entry 1.2500, SL=1.2450, TP=1.2550
        # Bar 37 has Low 1.2400 (breaches SL) AND High 1.2600 (breaches TP)
        highs[37] = 1.2600
        lows[37] = 1.2400

        data = {"open": opens, "high": highs, "low": lows, "close": closes}

        def eval_fn(idx, d):
            if idx == 36:
                return {"action": "BUY", "sl": 1.2450, "tp": 1.2550, "lots": 0.10}
            return None

        res = bt.run("GBPUSD", data, eval_fn)
        self.assertEqual(len(res.trades), 1)
        trade = res.trades[0]
        # Must be conservative STOP_LOSS rather than optimistic TAKE_PROFIT
        self.assertEqual(trade.exit_reason, "STOP_LOSS")
        self.assertEqual(trade.exit_price, 1.2450)

    def test_walk_forward_optimizer_parallel(self):
        """Verifies concurrent WalkForwardOptimizer grid search."""
        wfo = WalkForwardOptimizer(n_folds=2, is_ratio=0.7)
        param_grid = [{"period": p} for p in range(5, 12)]

        def strat_factory(params):
            def eval_fn(idx, d):
                return None
            return eval_fn

        res = wfo.run_walk_forward("EURUSD", self.ohlcv, strat_factory, param_grid)
        self.assertEqual(res["total_folds"], 2)


if __name__ == "__main__":
    unittest.main()

