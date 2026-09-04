"""
Unit tests for Mathematical, Statistical and Machine Learning Models.
"""

import unittest
import numpy as np
from autotrade.analytics.math_models import PredictiveModels


class TestMathModels(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        n = 80
        returns = np.random.normal(0.0005, 0.008, n)
        self.prices = np.cumprod(1.0 + returns) * 100.0

    def test_polynomial_regression(self):
        res = PredictiveModels.polynomial_regression(self.prices, degree=2, forecast_steps=5)
        self.assertIn("fitted", res)
        self.assertIn("forecast", res)
        self.assertEqual(len(res["forecast"]), 5)

    def test_arima_forecast(self):
        arima = PredictiveModels.arima_forecast(self.prices, p=2, d=1, q=1, steps=5)
        self.assertEqual(len(arima.forecast_prices), 5)
        self.assertEqual(len(arima.upper_bound), 5)
        self.assertEqual(len(arima.lower_bound), 5)
        self.assertTrue(arima.upper_bound[0] >= arima.lower_bound[0])

    def test_garch_volatility(self):
        rets = np.diff(np.log(self.prices))
        garch = PredictiveModels.garch_volatility(rets)
        self.assertGreater(garch.forecast_volatility, 0.0)
        self.assertTrue(garch.is_stable)

    def test_fft_cycle_analysis(self):
        # Generate synthetic sine wave with 20-period cycle
        t = np.arange(100)
        synthetic_price = 100.0 + 5.0 * np.sin(2 * np.pi * t / 20.0)
        cycles = PredictiveModels.fft_cycle_analysis(synthetic_price, max_cycles=2)
        self.assertGreater(len(cycles), 0)
        # Dominant cycle should be near 20 bars
        self.assertAlmostEqual(cycles[0].dominant_period_bars, 20.0, delta=3.0)

    def test_monte_carlo_simulation(self):
        rets = list(np.random.normal(0.002, 0.01, 50))
        mc = PredictiveModels.monte_carlo_simulation(
            initial_balance=100000.0,
            trade_returns=rets,
            num_simulations=500,
            horizon_trades=30
        )
        self.assertGreater(mc.mean_final_equity, 0.0)
        self.assertGreaterEqual(mc.var_95, 0.0)
        self.assertTrue(0.0 <= mc.probability_of_ruin_pct <= 100.0)

    def test_ml_prediction(self):
        highs = self.prices + 0.5
        lows = self.prices - 0.5
        vols = np.full_like(self.prices, 500)
        ohlcv = {
            "open": self.prices,
            "high": highs,
            "low": lows,
            "close": self.prices,
            "volume": vols
        }
        pred = PredictiveModels.predict_price_direction(ohlcv)
        self.assertIn(pred["action"], ["BUY", "SELL", "HOLD"])
        self.assertTrue(0.0 <= pred["confidence"] <= 1.0)


if __name__ == "__main__":
    unittest.main()
