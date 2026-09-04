"""
Unit tests for Institutional Performance Metrics and Report Generator.
"""

import asyncio
import os
import time
import unittest
from autotrade.reporting.performance_metrics import PerformanceMetricsEngine
from autotrade.reporting.report_generator import ReportGenerator


class TestReporting(unittest.TestCase):
    def setUp(self):
        self.metrics_engine = PerformanceMetricsEngine()
        self.report_gen = ReportGenerator(metrics_engine=self.metrics_engine)

    def test_performance_metrics_calculation(self):
        trades = [
            {"pnl": 100.0, "lots": 0.1, "close_time": time.time() - 300},
            {"pnl": -50.0, "lots": 0.1, "close_time": time.time() - 200},
            {"pnl": 200.0, "lots": 0.1, "close_time": time.time() - 100},
            {"pnl": -30.0, "lots": 0.1, "close_time": time.time() - 50},
        ]
        metrics = self.metrics_engine.calculate_metrics_from_trades(trades)
        self.assertEqual(metrics.total_trades, 4)
        self.assertEqual(metrics.winning_trades, 2)
        self.assertEqual(metrics.losing_trades, 2)
        self.assertEqual(metrics.win_rate, 0.5)
        self.assertEqual(metrics.net_profit, 220.0)
        self.assertGreater(metrics.profit_factor, 1.0)

    def test_report_generator_with_chart(self):
        async def _run():
            res = await self.report_gen.generate_period_report(period_name="DAILY", hours_back=24)
            self.assertIn("period", res)
            self.assertIn("metrics", res)
            self.assertIn("telegram_message", res)
            self.assertIn("chart_path", res)
            if res["chart_path"]:
                self.assertTrue(os.path.exists(res["chart_path"]))
        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
