"""
Unit tests for Institutional Chart Compositor (autotrade.analytics.chart_composer).
"""

import os
import tempfile
import unittest
from PIL import Image

from autotrade.analytics.chart_composer import compose_chart_screenshot, BG_CARD, BG_CANVAS


class TestChartComposer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        # Create a mock base chart image (1280x720)
        self.mock_chart_path = os.path.join(self.temp_dir.name, "test_chart.png")
        base_img = Image.new("RGB", (1280, 720), color=(10, 10, 10))
        base_img.save(self.mock_chart_path, "PNG")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_file_handling(self):
        """Verify non-existent file returns path gracefully without exception."""
        non_existent = os.path.join(self.temp_dir.name, "non_existent.png")
        res = compose_chart_screenshot(non_existent, {})
        self.assertEqual(res, non_existent)

    def test_successful_composition_and_dimensions(self):
        """Verify composition adds header and expands height from 720 to 968."""
        sample_data = {
            "symbol": "EURUSD",
            "timeframe": "H1",
            "bid": 1.0850,
            "ask": 1.0852,
            "server_time": "2026.09.07 14:00:00",
            "telemetry": {
                "trend": "STRONG BULLISH",
                "signal": "BUY (Score: 8/10)",
                "points": "Pts: Trend(3/0) Mom(2/0) SR(1/0) Cndl(2/0)",
                "osc": "RSI: 64.2 | MACD: +0.00035 | ADX: 30.1",
                "session": "London/NY Overlap",
                "spread": "12 pts (Max: 50) | ATR: 0.0011",
                "balance": "50000.00",
                "equity": "50450.00",
                "daily_pnl": "+$450.00 (+0.90%)",
                "positions": "1/1",
                "bot_status": "ACTIVE [RUNNING]",
                "quant": "KER: 0.42 | Squeeze: None",
                "pattern": "Bullish Engulfing",
                "ext_ind": "CCI: 110.5 | %B: 0.85 | VSA: Normal",
                "mtf": {
                    "M5": "UP",
                    "M15": "UP",
                    "M30": "UP",
                    "H1": "UP",
                    "H4": "UP",
                    "D1": "DN"
                },
                "bull_power": "83.3% (5/6 TFs)",
                "power_pct": 83.3,
                "mtf_advice": "Action: Strong Long Alignment Active"
            }
        }
        res_path = compose_chart_screenshot(self.mock_chart_path, sample_data)
        self.assertEqual(res_path, self.mock_chart_path)

        with Image.open(self.mock_chart_path) as img:
            w, h = img.size
            self.assertEqual(w, 1280)
            self.assertEqual(h, 968)  # 720 + 248 header
            self.assertEqual(img.info.get("composed"), "true")

    def test_idempotency_guard(self):
        """Verify calling compose twice does not add a second header."""
        sample_data = {
            "symbol": "GBPUSD",
            "timeframe": "M15",
            "telemetry": {"trend": "SIDEWAYS", "signal": "NEUTRAL 0/10"}
        }
        compose_chart_screenshot(self.mock_chart_path, sample_data)
        with Image.open(self.mock_chart_path) as img1:
            h1 = img1.size[1]
            self.assertEqual(h1, 968)

        # Call again on already-composited image
        compose_chart_screenshot(self.mock_chart_path, sample_data)
        with Image.open(self.mock_chart_path) as img2:
            h2 = img2.size[1]
            self.assertEqual(h2, 968)  # Must remain 968, NOT 968+248

    def test_atr_deduplication(self):
        """Verify spread containing ATR is not appended with a duplicate ATR."""
        sample_data = {
            "symbol": "USDJPY",
            "timeframe": "H4",
            "telemetry": {
                "spread": "18 pts | ATR: 0.0015",
                "atr": "0.0006",  # Stale fallback should be ignored
                "session": "Asian"
            }
        }
        # Should compose cleanly without crash
        compose_chart_screenshot(self.mock_chart_path, sample_data)
        with Image.open(self.mock_chart_path) as img:
            self.assertEqual(img.size, (1280, 968))

    def test_long_signal_and_empty_telemetry_graceful(self):
        """Verify empty telemetry dictionary or very long text doesn't crash composer."""
        empty_data = {}
        compose_chart_screenshot(self.mock_chart_path, empty_data)
        with Image.open(self.mock_chart_path) as img:
            self.assertEqual(img.size, (1280, 968))

    def test_mtf_power_color_and_percent_thresholds(self):
        """Verify dynamic power calculation when power_pct key is absent."""
        data_low = {
            "telemetry": {
                "mtf": {"M5": "DN", "M15": "DN", "M30": "DN", "H1": "DN", "H4": "DN", "D1": "DN"}
            }
        }
        compose_chart_screenshot(self.mock_chart_path, data_low)
        with Image.open(self.mock_chart_path) as img:
            self.assertEqual(img.size, (1280, 968))


    def test_card1_header_account_badge_real_and_demo(self):
        """Verify Card 1 renders account badge accurately for REAL and DEMO trade modes."""
        real_data = {
            "symbol": "GBPUSD_min",
            "timeframe": "M15",
            "account_number": "213173",
            "account_name": "Elnare Xelilzade FX#1 (Real)",
            "trade_mode": "REAL",
            "telemetry": {
                "trend": "STRONG BULLISH",
                "signal": "BUY 8/10",
                "account_number": "213173",
                "account_name": "Elnare Xelilzade FX#1 (Real)",
                "trade_mode": "REAL"
            }
        }
        compose_chart_screenshot(self.mock_chart_path, real_data)
        with Image.open(self.mock_chart_path) as img:
            self.assertEqual(img.size, (1280, 968))

        # Reset image
        base_img = Image.new("RGB", (1280, 720), color=(10, 10, 10))
        base_img.save(self.mock_chart_path, "PNG")

        demo_data = {
            "symbol": "EURUSD",
            "timeframe": "H1",
            "account_number": "1234567",
            "account_name": "Demo Account",
            "trade_mode": "DEMO",
            "telemetry": {
                "trend": "SIDEWAYS",
                "signal": "FLAT 0/10",
                "account_number": "1234567",
                "account_name": "Demo Account",
                "trade_mode": "DEMO"
            }
        }
        compose_chart_screenshot(self.mock_chart_path, demo_data)
        with Image.open(self.mock_chart_path) as img:
            self.assertEqual(img.size, (1280, 968))


if __name__ == "__main__":
    unittest.main()
