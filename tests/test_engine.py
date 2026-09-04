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


if __name__ == "__main__":
    unittest.main()
