"""
Unit tests for TradingEngine Lifecycle and Subsystem Orchestration.
"""

import asyncio
import unittest
from autotrade.core.engine import TradingEngine


class TestTradingEngine(unittest.TestCase):
    def setUp(self):
        self.engine = TradingEngine()

    def test_engine_initialization_and_lifecycle(self):
        async def run_lifecycle():
            init_ok = await self.engine.initialize()
            self.assertTrue(init_ok)

            # Start Engine
            await self.engine.start()
            self.assertTrue(self.engine.state.is_running)

            # Pause & Resume
            await self.engine.pause()
            self.assertTrue(self.engine.state.is_paused)

            await self.engine.resume()
            self.assertFalse(self.engine.state.is_paused)

            # Status query
            status = self.engine.get_status()
            self.assertIn("is_running", status)
            self.assertIn("event_bus_metrics", status)

            # Emergency halt
            await self.engine.emergency_halt("Unit test halt")
            self.assertTrue(self.engine.state.emergency_halt)

            # Stop engine
            await self.engine.stop()
            self.assertFalse(self.engine.state.is_running)

        asyncio.run(run_lifecycle())



class TestScalperMicroEngine(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np = np
        from autotrade.core.pipeline import confluence_engine
        self.engine = confluence_engine
        self.engine._rolling_spreads.clear()

    def _generate_scalper_bullish_ohlcv(self, n=50):
        np = self.np
        base = 1.0800
        t = np.linspace(0, 3 * np.pi, n)
        closes = base + 0.0005 * np.sin(t) + np.linspace(0, 0.0003, n)
        opens = closes - 0.00005
        highs = np.maximum(opens, closes) + 0.00015
        lows = np.minimum(opens, closes) - 0.00015

        # Recent bars: pullback to lower band and bounce up with fast EMA8 > EMA21
        closes[-6:] = [base + 0.00010, base + 0.00015, base + 0.00022, base + 0.00030, base + 0.00040, base + 0.00052]
        opens[-6:]  = [base + 0.00008, base + 0.00012, base + 0.00018, base + 0.00026, base + 0.00035, base + 0.00045]
        highs[-6:]  = [c + 0.00015 for c in closes[-6:]]
        lows[-6:]   = [o - 0.00010 for o in opens[-6:]]

        # Bullish rejection wick on last bar: lower wick >= 2.0x body
        lows[-1] = opens[-1] - 0.00030

        # Bullish 3-bar micro-FVG (lows[-2] > highs[-4])
        highs[-4] = base + 0.00020
        lows[-2] = highs[-4] + 0.00008

        volumes = np.full(n, 100.0)
        return {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes}

    def test_scalper_bullish_qualification(self):
        ohlcv = self._generate_scalper_bullish_ohlcv()
        eval_res = self.engine.evaluate_symbol_scalper(
            symbol="EURUSD",
            ohlcv=ohlcv,
            spread_points=12.0,  # 1.2 pips
            account_equity=10000.0
        )
        self.assertTrue(eval_res.is_qualified, f"Expected qualified but got: {eval_res.disqualification_reason}")
        self.assertEqual(eval_res.signal, "BUY")
        self.assertGreaterEqual(eval_res.score_100, 75.0)
        self.assertGreaterEqual(eval_res.sl_pips, 6.0)
        self.assertLessEqual(eval_res.sl_pips, 10.0)
        self.assertGreaterEqual(eval_res.tp_pips, 10.0)
        self.assertLessEqual(eval_res.tp_pips, 20.0)
        self.assertGreaterEqual(eval_res.rr_ratio, 1.5)

    def test_scalper_spread_sanity_gate_veto(self):
        ohlcv = self._generate_scalper_bullish_ohlcv()
        # Spread of 40 points = 4.0 pips. On a 15-pip TP, max allowed is 0.15 * 15 = 2.25 pips.
        eval_res = self.engine.evaluate_symbol_scalper(
            symbol="EURUSD",
            ohlcv=ohlcv,
            spread_points=40.0,
            account_equity=10000.0
        )
        self.assertFalse(eval_res.is_qualified)
        self.assertIn("Spread-to-Target Sanity Gate Veto", eval_res.disqualification_reason)

    def test_evaluate_symbol_scalper_mode_dispatch(self):
        ohlcv = self._generate_scalper_bullish_ohlcv()
        eval_res = self.engine.evaluate_symbol(
            symbol="EURUSD",
            ohlcv=ohlcv,
            spread_points=12.0,
            account_equity=10000.0,
            execution_mode="SCALPER"
        )
        self.assertTrue(eval_res.is_qualified)
        self.assertEqual(eval_res.signal, "BUY")


if __name__ == "__main__":
    unittest.main()

