"""
Unit tests for Institutional Multi-Format Chart Rendering Engine.
"""

import os
import unittest
import numpy as np
from autotrade.analytics.charts import ChartGenerator, ChartType


class TestCharts(unittest.TestCase):
    def setUp(self):
        self.generator = ChartGenerator()
        np.random.seed(42)
        n = 50
        returns = np.random.normal(0.0002, 0.004, n)
        self.closes = np.cumprod(1.0 + returns) * 1.3000
        self.highs = self.closes + 0.0015
        self.lows = self.closes - 0.0015
        self.opens = np.roll(self.closes, 1)
        self.opens[0] = self.closes[0]
        self.vols = np.random.uniform(100, 500, n)
        self.ohlcv = {
            "open": self.opens,
            "high": self.highs,
            "low": self.lows,
            "close": self.closes,
            "volume": self.vols,
            "timestamp": np.arange(n) * 3600
        }

    def test_candlestick_chart_generation(self):
        filepath = self.generator.generate_chart(
            symbol="GBPUSD",
            timeframe="H1",
            ohlcv=self.ohlcv,
            chart_type=ChartType.CANDLESTICK
        )
        self.assertTrue(os.path.exists(filepath))
        self.assertGreater(os.path.getsize(filepath), 1000)

    def test_heikin_ashi_chart_generation(self):
        filepath = self.generator.generate_chart(
            symbol="EURUSD",
            timeframe="M15",
            ohlcv=self.ohlcv,
            chart_type=ChartType.HEIKIN_ASHI
        )
        self.assertTrue(os.path.exists(filepath))
        self.assertGreater(os.path.getsize(filepath), 1000)

    def test_renko_chart_generation(self):
        filepath = self.generator.generate_chart(
            symbol="XAUUSD",
            timeframe="H4",
            ohlcv=self.ohlcv,
            chart_type=ChartType.RENKO
        )
        self.assertTrue(os.path.exists(filepath))
        self.assertGreater(os.path.getsize(filepath), 1000)


if __name__ == "__main__":
    unittest.main()
