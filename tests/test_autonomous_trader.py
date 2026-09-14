"""
Unit tests for AutonomousMultiSymbolTrader and its integration with Telegram commands & ZeroMQ.
Verifies multi-symbol scanning, confluence scoring thresholding, cooldown, spread filtering,
direct order dispatch, and alert broadcasting with zero user advisory prompting.
All live market executions are fully mocked to safeguard user account capital.
"""

import asyncio
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

from autotrade.core.autonomous_trader import AutonomousMultiSymbolTrader, autonomous_trader
import handlers


class TestAutonomousMultiSymbolTrader(unittest.TestCase):
    def setUp(self):
        self.temp_flag_dir = tempfile.TemporaryDirectory()
        self.flag_path = os.path.join(self.temp_flag_dir.name, "autotrade_state.flag")
        self.flag_patch = patch("autotrade.core.autonomous_trader.AUTOTRADE_FLAG_FILE", self.flag_path)
        self.flag_patch.start()
        self.trader = AutonomousMultiSymbolTrader(
            symbols=["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
            min_score=6,
            cooldown_sec=300,
            max_spread=40.0
        )

    def tearDown(self):
        self.flag_patch.stop()
        self.temp_flag_dir.cleanup()

    def test_initialization_and_watchlist(self):
        """Verifies symbol watchlist initialization, additions, and removals."""
        self.assertEqual(len(self.trader.symbols), 4)
        self.assertIn("EURUSD", self.trader.symbols)
        self.assertIn("XAUUSD", self.trader.symbols)

        # Add symbol
        added = self.trader.add_symbol("AUDUSD")
        self.assertTrue(added)
        self.assertIn("AUDUSD", self.trader.symbols)

        # Duplicate add
        self.assertFalse(self.trader.add_symbol("AUDUSD"))

        # Remove symbol
        removed = self.trader.remove_symbol("AUDUSD")
        self.assertTrue(removed)
        self.assertNotIn("AUDUSD", self.trader.symbols)

        # Cannot remove if only 1 symbol left
        solo_trader = AutonomousMultiSymbolTrader(symbols=["EURUSD"])
        self.assertFalse(solo_trader.remove_symbol("EURUSD"))

    def test_enable_disable_and_flag_file(self):
        """Verifies internal state and external flag file interaction."""
        self.assertTrue(self.trader.is_autotrade_active())

        self.trader.set_enabled(False)
        self.assertFalse(self.trader.is_autotrade_active())
        self.trader.set_enabled(True)
        self.assertTrue(self.trader.is_autotrade_active())

        # Test multi-line PAUSED flag file
        with open(self.flag_path, "w", encoding="utf-8") as f:
            f.write("PAUSED\nTimestamp=1788853039\n")
        self.assertFalse(self.trader.is_autotrade_active())

        # Test multi-line ACTIVE flag file
        with open(self.flag_path, "w", encoding="utf-8") as f:
            f.write("ACTIVE\nTimestamp=1788853039\n")
        self.assertTrue(self.trader.is_autotrade_active())

    def test_scan_portfolio_mock(self):
        """Verifies portfolio scan parses bridge responses and falls back cleanly."""
        mock_scan_data = {
            "status": "ok",
            "action": "SCAN_SYMBOLS",
            "results": [
                {
                    "symbol": "EURUSD",
                    "score": 8,
                    "signal": "BUY",
                    "trend": "STRONG_BULLISH",
                    "spread": 12.0,
                    "sl_pips": 25.0,
                    "tp_pips": 50.0
                },
                {
                    "symbol": "GBPUSD",
                    "score": 3,
                    "signal": "HOLD",
                    "trend": "NEUTRAL",
                    "spread": 15.0,
                    "sl_pips": 30.0,
                    "tp_pips": 60.0
                }
            ]
        }

        with patch("autotrade.core.autonomous_trader.zmq_client.scan_symbols", return_value=mock_scan_data):
            res = self.trader.scan_portfolio()
            self.assertEqual(res.get("status"), "ok")
            self.assertEqual(len(res.get("results")), 2)
            self.assertEqual(self.trader.last_scan_data["results"][0]["symbol"], "EURUSD")

    def test_scan_portfolio_fallback(self):
        """Verifies fallback data structure when bridge returns error or offline."""
        mock_error = {"status": "error", "message": "Bridge connection timed out"}
        with patch("autotrade.core.autonomous_trader.zmq_client.scan_symbols", return_value=mock_error):
            res = self.trader.scan_portfolio()
            self.assertEqual(res.get("status"), "ok")
            self.assertTrue(res.get("fallback"))
            self.assertEqual(len(res.get("results")), len(self.trader.symbols))

    def test_execute_autonomous_cycle_high_confluence(self):
        """
        Verifies that high-confluence setup (Score >= min_score) autonomously executes
        a direct market order without asking the user.
        """
        mock_scan = {
            "status": "ok",
            "results": [
                {
                    "symbol": "GBPUSD",
                    "score": 9,
                    "analysis_score": 90.0,
                    "signal": "BUY",
                    "trend": "BULLISH_BREAKOUT",
                    "spread": 14.0,
                    "sl_pips": 30.0,
                    "tp_pips": 60.0
                }
            ]
        }
        mock_positions = {"status": "ok", "positions": []}
        mock_order_res = {
            "status": "ok",
            "action": "OPEN_ORDER",
            "ticket": 123456,
            "price": 1.26500,
            "lots": 0.01,
            "symbol": "GBPUSD"
        }

        mock_bot = AsyncMock()

        async def run_test():
            with patch.object(self.trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order", return_value=mock_order_res) as mock_open:
                trades = await self.trader.execute_autonomous_cycle(bot=mock_bot)
                self.assertEqual(len(trades), 1)
                self.assertEqual(trades[0]["symbol"], "GBPUSD")
                self.assertEqual(trades[0]["cmd"], "BUY")
                self.assertEqual(trades[0]["ticket"], 123456)
                self.assertEqual(self.trader.total_trades_executed, 1)
                mock_open.assert_called_once()
                # Bot notification dispatched to operator
                mock_bot.send_message.assert_called()

        asyncio.run(run_test())

    def test_execute_autonomous_cycle_low_confluence_ignored(self):
        """Verifies low-conviction signals (Score < min_score) are completely ignored."""
        mock_scan = {
            "status": "ok",
            "results": [
                {
                    "symbol": "EURUSD",
                    "score": 4,  # Below threshold 6
                    "signal": "BUY",
                    "trend": "WEAK_BULLISH",
                    "spread": 12.0
                }
            ]
        }
        mock_positions = {"status": "ok", "positions": []}

        async def run_test():
            with patch.object(self.trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                trades = await self.trader.execute_autonomous_cycle()
                self.assertEqual(len(trades), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_execute_autonomous_cycle_symbol_already_open(self):
        """Verifies trader does not double-open positions on the same symbol."""
        mock_scan = {
            "status": "ok",
            "results": [
                {
                    "symbol": "EURUSD",
                    "score": 9,
                    "signal": "BUY",
                    "trend": "STRONG_BULLISH",
                    "spread": 10.0
                }
            ]
        }
        # EURUSD is already open
        mock_positions = {
            "status": "ok",
            "positions": [{"ticket": 999, "symbol": "EURUSD", "type": "BUY"}]
        }

        async def run_test():
            with patch.object(self.trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                trades = await self.trader.execute_autonomous_cycle()
                self.assertEqual(len(trades), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_execute_autonomous_cycle_spread_filter(self):
        """Verifies instruments with spreads exceeding max_spread are filtered out."""
        mock_scan = {
            "status": "ok",
            "results": [
                {
                    "symbol": "XAUUSD",
                    "score": 9,
                    "signal": "BUY",
                    "spread": 85.0  # Exceeds max_spread 40.0
                }
            ]
        }
        mock_positions = {"status": "ok", "positions": []}

        async def run_test():
            with patch.object(self.trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                trades = await self.trader.execute_autonomous_cycle()
                self.assertEqual(len(trades), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_execute_autonomous_cycle_cooldown(self):
        """Verifies symbol cooldown prevents rapid-fire sequential order entries."""
        mock_scan = {
            "status": "ok",
            "results": [
                {
                    "symbol": "USDJPY",
                    "score": 7,
                    "signal": "SELL",
                    "spread": 12.0
                }
            ]
        }
        mock_positions = {"status": "ok", "positions": []}
        import time
        self.trader.last_trade_times["USDJPY"] = time.time() - 50.0  # only 50s ago, cooldown is 300s

        async def run_test():
            with patch.object(self.trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                trades = await self.trader.execute_autonomous_cycle()
                self.assertEqual(len(trades), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_formatting_panels(self):
        """Verifies HTML output formatting of panels."""
        status_html = self.trader.format_status_panel()
        self.assertIn("AUTONOMOUS MULTI-SYMBOL TRADING ENGINE", status_html)
        self.assertIn("Confluence Threshold", status_html)

        scan_html = self.trader.format_scan_matrix({
            "status": "ok",
            "results": [
                {"symbol": "EURUSD", "trend": "BULLISH", "score": 8, "signal": "BUY", "spread": 12.0}
            ]
        })
        self.assertIn("AUTONOMOUS MULTI-SYMBOL SCANNER", scan_html)
        self.assertIn("EURUSD", scan_html)
        self.assertIn("Score: <b>8/10</b>", scan_html)

        symbols_html = self.trader.format_symbols_panel()
        self.assertIn("AUTONOMOUS PORTFOLIO WATCHLIST", symbols_html)
        self.assertIn("EURUSD", symbols_html)

    def test_canonical_symbol_normalization(self):
        """Verifies canonical_symbol correctly normalizes symbols with various broker suffixes."""
        from autotrade.core.autonomous_trader import canonical_symbol
        self.assertEqual(canonical_symbol("EURUSD"), "EURUSD")
        self.assertEqual(canonical_symbol("EURUSD_min"), "EURUSD")
        self.assertEqual(canonical_symbol("EURUSD.pro"), "EURUSD")
        self.assertEqual(canonical_symbol("GBPUSD_min"), "GBPUSD")
        self.assertEqual(canonical_symbol("XAUUSD_min"), "XAUUSD")
        self.assertEqual(canonical_symbol("USDJPY.raw"), "USDJPY")
        self.assertEqual(canonical_symbol("EUR/USD"), "EURUSD")
        self.assertEqual(canonical_symbol("USDCADm"), "USDCAD")
        self.assertEqual(canonical_symbol("BTCUSD"), "BTCUSD")
        self.assertEqual(canonical_symbol("EURUSD+"), "EURUSD")
        self.assertEqual(canonical_symbol("GBPUSD+"), "GBPUSD")
        self.assertEqual(canonical_symbol("rEURUSD"), "EURUSD")
        self.assertEqual(canonical_symbol("mGBPUSD"), "GBPUSD")
        self.assertEqual(canonical_symbol("mEURGBP"), "EURGBP")
        self.assertEqual(canonical_symbol("rGBPJPY"), "GBPJPY")
        self.assertEqual(canonical_symbol("USDTRY.pro"), "USDTRY")
        self.assertEqual(canonical_symbol("mUSDTRY"), "USDTRY")
        self.assertEqual(canonical_symbol("GOLD"), "XAUUSD")
        self.assertEqual(canonical_symbol("SILVER"), "XAGUSD")

        from autotrade.core.autonomous_trader import split_currency_pair
        self.assertEqual(split_currency_pair("EURUSD"), ("EUR", "USD"))
        self.assertEqual(split_currency_pair("GBPUSD_min"), ("GBP", "USD"))
        self.assertEqual(split_currency_pair("mEURGBP"), ("EUR", "GBP"))
        self.assertEqual(split_currency_pair("GOLD"), ("XAU", "USD"))

    def test_currency_exposure_clamping(self):
        """Verifies that an autonomous trade is rejected if open currency exposure ceiling is reached."""
        async def run_test():
            trader = AutonomousMultiSymbolTrader(symbols=["GBPUSD"], min_score=6)
            mock_scan = {
                "status": "ok",
                "results": [
                    {
                        "symbol": "GBPUSD",
                        "score": 8,
                        "signal": "BUY",
                        "spread": 10.0,
                        "sl_pips": 30.0,
                        "tp_pips": 60.0
                    }
                ]
            }
            # Open position already exists on EURUSD (involving USD)
            open_pos = [{"ticket": 1001, "symbol": "EURUSD", "cmd": "BUY", "lots": 0.05}]
            with patch.object(trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value={"status": "ok", "positions": open_pos}), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                executed = await trader.execute_autonomous_cycle()
                # Should be clamped because USD already has 1 open position
                self.assertEqual(len(executed), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_order_failure_backoff_cooldown(self):
        """Verifies that an order placement failure sets failure backoff and skips retries."""
        async def run_test():
            trader = AutonomousMultiSymbolTrader(symbols=["GBPUSD"], min_score=6)
            mock_scan = {
                "status": "ok",
                "results": [
                    {
                        "symbol": "GBPUSD",
                        "score": 9,
                        "analysis_score": 90.0,
                        "signal": "BUY",
                        "spread": 10.0,
                        "sl_pips": 30.0,
                        "tp_pips": 60.0
                    }
                ]
            }
            with patch.object(trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value={"status": "ok", "positions": []}), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order", return_value={"status": "error", "message": "OrderSend failed: Longs not allowed"}) as mock_open:
                # First run fails
                executed = await trader.execute_autonomous_cycle()
                self.assertEqual(len(executed), 0)
                mock_open.assert_called_once()
                self.assertIn("GBPUSD", trader.last_failure_times)

                # Immediate second run is throttled by failure backoff
                mock_open.reset_mock()
                executed_2 = await trader.execute_autonomous_cycle()
                self.assertEqual(len(executed_2), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_get_positions_failure_aborts_cycle(self):
        """Verifies that failure to fetch open positions aborts the cycle for safety."""
        async def run_test():
            trader = AutonomousMultiSymbolTrader(symbols=["EURUSD"], min_score=6)
            mock_scan = {
                "status": "ok",
                "results": [{"symbol": "EURUSD", "score": 8, "signal": "BUY", "spread": 10.0}]
            }
            with patch.object(trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value={"status": "error", "message": "Timeout"}), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                executed = await trader.execute_autonomous_cycle()
                self.assertEqual(len(executed), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_execute_autonomous_cycle_symbol_already_open_with_broker_suffix(self):
        """
        Verifies that an open position with a broker suffix (e.g. EURUSD_min)
        correctly prevents duplicate autonomous execution for EURUSD.
        """
        mock_scan = {
            "status": "ok",
            "results": [
                {
                    "symbol": "EURUSD",
                    "score": 9,
                    "signal": "BUY",
                    "trend": "STRONG_BULLISH",
                    "spread": 10.0
                }
            ]
        }
        # Broker position has suffix EURUSD_min
        mock_positions = {
            "status": "ok",
            "positions": [{"ticket": 77701, "symbol": "EURUSD_min", "type": "BUY"}]
        }

        async def run_test():
            with patch.object(self.trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                trades = await self.trader.execute_autonomous_cycle()
                self.assertEqual(len(trades), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_execute_autonomous_cycle_reverse_suffix_already_open(self):
        """
        Verifies that when a generic symbol EURUSD is open, an incoming scan
        with broker suffix EURUSD.pro is recognized as open and ignored.
        """
        mock_scan = {
            "status": "ok",
            "results": [
                {
                    "symbol": "EURUSD.pro",
                    "score": 9,
                    "signal": "BUY",
                    "trend": "STRONG_BULLISH",
                    "spread": 10.0
                }
            ]
        }
        mock_positions = {
            "status": "ok",
            "positions": [{"ticket": 77702, "symbol": "EURUSD", "type": "BUY"}]
        }

        async def run_test():
            with patch.object(self.trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                trades = await self.trader.execute_autonomous_cycle()
                self.assertEqual(len(trades), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_interactive_buttons_in_execution_alert(self):
        """Verifies that _dispatch_execution_alert attaches interactive buttons with ticket actions."""
        mock_bot = AsyncMock()
        trade_record = {
            "symbol": "GBPUSD",
            "cmd": "BUY",
            "ticket": 888123,
            "price": 1.27500,
            "lots": 0.02,
            "score": 8,
            "sl_pips": 25.0,
            "tp_pips": 50.0,
            "trend": "BULLISH_BREAKOUT",
            "timestamp": 1788800000.0
        }

        async def run_test():
            await self.trader._dispatch_execution_alert(mock_bot, trade_record)
            mock_bot.send_message.assert_called_once()
            call_kwargs = mock_bot.send_message.call_args[1]
            self.assertIn("reply_markup", call_kwargs)
            kb = call_kwargs["reply_markup"]
            self.assertIsNotNone(kb)
            # Find callback data in keyboard buttons
            callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
            self.assertIn("/close_888123", callbacks)
            self.assertIn("/half_888123", callbacks)
            self.assertIn("nav_pos", callbacks)

        asyncio.run(run_test())

    def test_max_concurrent_positions_guard_respects_limit(self):
        """Verifies execute_autonomous_cycle blocks new trades when max_positions is reached."""
        mock_scan = {
            "status": "ok",
            "results": [
                {"symbol": "EURUSD", "score": 9, "signal": "BUY", "spread": 10.0}
            ]
        }
        mock_pos = {
            "status": "ok",
            "positions": [
                {"ticket": 101, "symbol": "GBPUSD", "type": "BUY"},
                {"ticket": 102, "symbol": "USDJPY", "type": "BUY"},
                {"ticket": 103, "symbol": "AUDUSD", "type": "BUY"}
            ]
        }
        self.trader.max_positions = 3

        async def run_test():
            with patch.object(self.trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_pos), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                trades = await self.trader.execute_autonomous_cycle()
                self.assertEqual(len(trades), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_per_symbol_cooldown_guard_skips_recent_traded_symbol(self):
        """Verifies execute_autonomous_cycle enforces cooldown on recently traded symbols."""
        mock_scan = {
            "status": "ok",
            "results": [
                {"symbol": "GBPUSD", "score": 9, "signal": "BUY", "spread": 10.0}
            ]
        }
        mock_pos = {"status": "ok", "positions": []}
        self.trader.cooldown_sec = 3600
        # Register a recent trade 5 minutes ago
        self.trader.last_trade_times["GBPUSD"] = time.time() - 300

        async def run_test():
            with patch.object(self.trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_pos), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                trades = await self.trader.execute_autonomous_cycle()
                self.assertEqual(len(trades), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_score_5_and_below_strictly_ignored(self):
        """Verifies score 5 (and below 6) is strictly ignored, resolving user bug."""
        # Ensure min_score clamping
        lenient_trader = AutonomousMultiSymbolTrader(symbols=["EURCAD"], min_score=4)
        self.assertGreaterEqual(lenient_trader.min_score, 6)

        mock_scan = {
            "status": "ok",
            "results": [
                {
                    "symbol": "EURCAD",
                    "score": 5,  # Score 5 reported by user
                    "signal": "SELL",
                    "trend": "STRONG_BEARISH",
                    "spread": 15.0
                }
            ]
        }
        mock_positions = {"status": "ok", "positions": []}

        async def run_test():
            with patch.object(self.trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                trades = await self.trader.execute_autonomous_cycle()
                self.assertEqual(len(trades), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_directional_trend_mismatch_ignored(self):
        """Verifies buy signals in bearish trends or sell signals in bullish trends are rejected."""
        mock_scan = {
            "status": "ok",
            "results": [
                {
                    "symbol": "EURUSD",
                    "score": 8,
                    "signal": "BUY",
                    "trend": "STRONG_BEARISH",  # Mismatch!
                    "spread": 10.0
                },
                {
                    "symbol": "GBPUSD",
                    "score": 8,
                    "signal": "SELL",
                    "trend": "STRONG_BULLISH",  # Mismatch!
                    "spread": 10.0
                }
            ]
        }
        mock_positions = {"status": "ok", "positions": []}

        async def run_test():
            with patch.object(self.trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                trades = await self.trader.execute_autonomous_cycle()
                self.assertEqual(len(trades), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_closed_bar_confirmation_dedup(self):
        """Verifies closed bar timestamp confirmation prevents duplicate entries on the same bar."""
        mock_scan = {
            "status": "ok",
            "results": [
                {
                    "symbol": "EURUSD",
                    "score": 9,
                    "analysis_score": 90.0,
                    "signal": "BUY",
                    "trend": "STRONG_BULLISH",
                    "spread": 10.0,
                    "sl_pips": 30.0,
                    "tp_pips": 60.0,
                    "bar_time": 1788890000
                }
            ]
        }
        mock_positions = {"status": "ok", "positions": []}
        mock_order_res = {"status": "ok", "ticket": 777001, "price": 1.0850}

        async def run_test():
            with patch.object(self.trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order", return_value=mock_order_res) as mock_open:
                # First execution succeeds
                trades = await self.trader.execute_autonomous_cycle()
                self.assertEqual(len(trades), 1)
                self.assertEqual(mock_open.call_count, 1)
                self.assertEqual(self.trader.last_traded_bar_times.get("EURUSD"), 1788890000)

                # Second cycle with same bar_time is skipped even if cooldown was cleared
                self.trader.last_trade_times.clear()
                mock_positions_empty = {"status": "ok", "positions": []}
                with patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions_empty):
                    trades2 = await self.trader.execute_autonomous_cycle()
                    self.assertEqual(len(trades2), 0)
                    self.assertEqual(mock_open.call_count, 1)  # Not called again!

        asyncio.run(run_test())

    def test_score_5_strictly_prohibited(self):
        """Verifies that evaluation score 5 is strictly prohibited from opening a trade."""
        mock_scan = {
            "status": "ok",
            "results": [
                {
                    "symbol": "EURUSD",
                    "score": 5,  # Score 5 MUST NEVER trade!
                    "signal": "BUY",
                    "trend": "STRONG_BULLISH",
                    "spread": 10.0,
                    "sl_pips": 30.0,
                    "tp_pips": 60.0
                },
                {
                    "symbol": "GBPUSD",
                    "score": 5,
                    "signal": "SELL",
                    "trend": "STRONG_BEARISH",
                    "spread": 12.0,
                    "sl_pips": 30.0,
                    "tp_pips": 60.0
                }
            ]
        }
        mock_positions = {"status": "ok", "positions": []}

        async def run_test():
            with patch.object(self.trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                trades = await self.trader.execute_autonomous_cycle()
                self.assertEqual(len(trades), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_deep_analysis_gates_reject_invalid_setups(self):
        """Verifies deep analysis rejects ADX <= 20, RSI outside corridor, trend contradiction, and HTF contradiction."""
        # 1. ADX <= 20 rejected
        item_flat_adx = {
            "symbol": "EURUSD", "score": 8, "signal": "BUY", "trend": "BULLISH",
            "adx": 18.0, "rsi": 52.0, "htf_trend": "BULLISH", "spread": 10.0
        }
        # 2. Overbought RSI (> 65) on BUY rejected
        item_overbought_rsi = {
            "symbol": "GBPUSD", "score": 8, "signal": "BUY", "trend": "BULLISH",
            "adx": 28.0, "rsi": 72.0, "htf_trend": "BULLISH", "spread": 10.0
        }
        # 3. Oversold RSI (< 45) on BUY rejected
        item_oversold_buy_rsi = {
            "symbol": "USDJPY", "score": 8, "signal": "BUY", "trend": "BULLISH",
            "adx": 28.0, "rsi": 40.0, "htf_trend": "BULLISH", "spread": 10.0
        }
        # 4. Trend contradiction rejected
        item_trend_contradiction = {
            "symbol": "AUDUSD", "score": 8, "signal": "BUY", "trend": "BEARISH",
            "adx": 28.0, "rsi": 52.0, "htf_trend": "BULLISH", "spread": 10.0
        }
        # 5. HTF contradiction rejected
        item_htf_contradiction = {
            "symbol": "USDCAD", "score": 8, "signal": "BUY", "trend": "BULLISH",
            "adx": 28.0, "rsi": 52.0, "htf_trend": "BEARISH", "spread": 10.0
        }

        mock_scan = {
            "status": "ok",
            "results": [item_flat_adx, item_overbought_rsi, item_oversold_buy_rsi,
                        item_trend_contradiction, item_htf_contradiction]
        }
        mock_positions = {"status": "ok", "positions": []}

        async def run_test():
            with patch.object(self.trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                trades = await self.trader.execute_autonomous_cycle()
                self.assertEqual(len(trades), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_require_bar_transition_startup_protection(self):
        """Verifies that require_bar_transition seeds initial forming bar on startup and waits for a new bar."""
        trader = AutonomousMultiSymbolTrader(
            symbols=["EURUSD"],
            min_score=6,
            require_bar_transition=True
        )

        mock_scan_bar1 = {
            "status": "ok",
            "results": [
                {
                    "symbol": "EURUSD", "score": 9, "analysis_score": 90.0, "signal": "BUY", "trend": "STRONG_BULLISH",
                    "adx": 28.0, "rsi": 52.0, "htf_trend": "BULLISH", "spread": 10.0,
                    "sl_pips": 30.0, "tp_pips": 60.0, "bar_time": 1788890000
                }
            ]
        }
        mock_scan_bar2 = {
            "status": "ok",
            "results": [
                {
                    "symbol": "EURUSD", "score": 9, "analysis_score": 90.0, "signal": "BUY", "trend": "STRONG_BULLISH",
                    "adx": 28.0, "rsi": 52.0, "htf_trend": "BULLISH", "spread": 10.0,
                    "sl_pips": 30.0, "tp_pips": 60.0, "bar_time": 1788893600  # New Bar!
                }
            ]
        }
        mock_positions = {"status": "ok", "positions": []}
        mock_order_res = {"status": "ok", "ticket": 888001, "price": 1.0850}

        async def run_test():
            with patch.object(trader, "scan_portfolio_async", return_value=mock_scan_bar1), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order", return_value=mock_order_res) as mock_open:
                # Cycle 1 on startup: initial bar is seeded into seen_bar_times; NO trade executed!
                trades1 = await trader.execute_autonomous_cycle()
                self.assertEqual(len(trades1), 0)
                mock_open.assert_not_called()
                self.assertEqual(trader.seen_bar_times.get("EURUSD"), 1788890000)

                # Cycle 2 during same forming bar: NO trade executed!
                trades2 = await trader.execute_autonomous_cycle()
                self.assertEqual(len(trades2), 0)
                mock_open.assert_not_called()

            # Cycle 3 with NEW bar: trade is executed!
            with patch.object(trader, "scan_portfolio_async", return_value=mock_scan_bar2), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order", return_value=mock_order_res) as mock_open:
                trades3 = await trader.execute_autonomous_cycle()
                self.assertEqual(len(trades3), 1)
                self.assertEqual(trades3[0]["ticket"], 888001)
                self.assertEqual(mock_open.call_count, 1)
                self.assertEqual(trader.last_traded_bar_times.get("EURUSD"), 1788893600)

        asyncio.run(run_test())

    def test_counter_trend_strictly_prohibited(self):
        """Verifies that COUNTER-TREND setups are strictly rejected even with high score and valid oscillators."""
        mock_scan = {
            "status": "ok",
            "results": [
                {
                    "symbol": "EURUSD", "score": 8, "signal": "BUY", "trend": "COUNTER-TREND BULLISH",
                    "adx": 28.0, "rsi": 52.0, "htf_trend": "BULLISH", "spread": 10.0,
                    "sl_pips": 30.0, "tp_pips": 60.0
                },
                {
                    "symbol": "GBPUSD", "score": 8, "signal": "SELL", "trend": "COUNTER-TREND BEARISH",
                    "adx": 28.0, "rsi": 48.0, "htf_trend": "BEARISH", "spread": 10.0,
                    "sl_pips": 30.0, "tp_pips": 60.0
                }
            ]
        }
        mock_positions = {"status": "ok", "positions": []}

        async def run_test():
            with patch.object(self.trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                trades = await self.trader.execute_autonomous_cycle()
                self.assertEqual(len(trades), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_mid_bar_signal_rejected_after_untraded_bars(self):
        """Verifies that if a new bar had no trades at bar open, mid-bar ticks later in that bar are rejected."""
        trader = AutonomousMultiSymbolTrader(
            symbols=["EURUSD"],
            min_score=6,
            require_bar_transition=True
        )

        # Bar 1 on startup (10:00)
        mock_bar1 = {
            "status": "ok",
            "results": [{"symbol": "EURUSD", "score": 4, "signal": "HOLD", "bar_time": 1788890000}]
        }
        # Bar 2 open (11:00) - No signal (score 4)
        mock_bar2_open = {
            "status": "ok",
            "results": [{"symbol": "EURUSD", "score": 4, "signal": "HOLD", "bar_time": 1788893600}]
        }
        # Bar 2 mid-bar (11:35) - Sudden indicator repaint to score 8
        mock_bar2_midbar = {
            "status": "ok",
            "results": [
                {
                    "symbol": "EURUSD", "score": 8, "signal": "BUY", "trend": "STRONG_BULLISH",
                    "adx": 28.0, "rsi": 52.0, "htf_trend": "BULLISH", "spread": 10.0,
                    "sl_pips": 30.0, "tp_pips": 60.0, "bar_time": 1788893600
                }
            ]
        }
        mock_positions = {"status": "ok", "positions": []}

        async def run_test():
            # Cycle 1: Startup seeds bar 1 (10:00)
            with patch.object(trader, "scan_portfolio_async", return_value=mock_bar1), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                trades1 = await trader.execute_autonomous_cycle()
                self.assertEqual(len(trades1), 0)
                mock_open.assert_not_called()

            # Cycle 2: Bar 2 open (11:00) - score 4, no trade, but bar transition registered
            with patch.object(trader, "scan_portfolio_async", return_value=mock_bar2_open), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                trades2 = await trader.execute_autonomous_cycle()
                self.assertEqual(len(trades2), 0)
                mock_open.assert_not_called()
                self.assertEqual(trader.seen_bar_times.get("EURUSD"), 1788893600)

            # Cycle 3: Mid-bar 11:35 - score 8, but MUST BE REJECTED because bar transition already occurred
            with patch.object(trader, "scan_portfolio_async", return_value=mock_bar2_midbar), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value=mock_positions), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                trades3 = await trader.execute_autonomous_cycle()
                self.assertEqual(len(trades3), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_is_qualified_candidate_filters(self):
        """Verifies is_qualified_candidate comprehensively enforces all institutional gates."""
        valid_buy = {
            "symbol": "EURUSD", "signal": "BUY", "score": 9, "analysis_score": 90.0, "trend": "STRONG BULLISH",
            "htf_trend": "BULLISH", "adx": 25.0, "rsi": 50.0
        }
        self.assertTrue(self.trader.is_qualified_candidate(valid_buy))

        # 1. Score < 8.5 rejected
        self.assertFalse(self.trader.is_qualified_candidate({**valid_buy, "score": 8, "analysis_score": 80.0}))
        self.assertFalse(self.trader.is_qualified_candidate({**valid_buy, "score": 6, "analysis_score": 60.0}))
        self.assertFalse(self.trader.is_qualified_candidate({**valid_buy, "score": 5, "analysis_score": 50.0}))

        # 2. Counter-trend rejected
        self.assertFalse(self.trader.is_qualified_candidate({**valid_buy, "trend": "COUNTER-TREND BULLISH"}))

        # 3. Opposite trend rejected
        self.assertFalse(self.trader.is_qualified_candidate({**valid_buy, "trend": "BEARISH"}))

        # 4. Flat / Sideways rejected
        self.assertFalse(self.trader.is_qualified_candidate({**valid_buy, "trend": "FLAT"}))

        # 5. HTF contradiction rejected
        self.assertFalse(self.trader.is_qualified_candidate({**valid_buy, "htf_trend": "BEARISH"}))

        # 6. ADX <= 20 rejected
        self.assertFalse(self.trader.is_qualified_candidate({**valid_buy, "adx": 19.5}))

        # 7. RSI outside corridor rejected (corridor for BUY is [40.0, 55.0])
        self.assertFalse(self.trader.is_qualified_candidate({**valid_buy, "rsi": 68.0}))
        self.assertFalse(self.trader.is_qualified_candidate({**valid_buy, "rsi": 38.0}))

        # 8. Unparseable ADX/RSI rejected
        self.assertFalse(self.trader.is_qualified_candidate({**valid_buy, "adx": "invalid"}))
        self.assertFalse(self.trader.is_qualified_candidate({**valid_buy, "rsi": "invalid"}))

        # 9. ATR < 10.0 pips rejected
        self.assertFalse(self.trader.is_qualified_candidate({**valid_buy, "atr": 0.0005, "server_time": "2026.09.08 14:00:00"}))
        self.assertTrue(self.trader.is_qualified_candidate({**valid_buy, "atr": 0.0025, "server_time": "2026.09.08 14:00:00"}))

        # 10. session_active = False rejected
        self.assertFalse(self.trader.is_qualified_candidate({**valid_buy, "session_active": False}))

        # 11. Asian session off-hours for EURUSD with score < 8.5 rejected
        self.assertFalse(self.trader.is_qualified_candidate({**valid_buy, "score": 7, "analysis_score": 70.0, "server_time": "2026.09.08 02:00:00"}))
        self.assertTrue(self.trader.is_qualified_candidate({**valid_buy, "score": 9, "analysis_score": 90.0, "server_time": "2026.09.08 02:00:00"}))

        # 12. Valid SELL setup accepted and edge cases verified
        valid_sell = {
            "symbol": "GBPUSD", "signal": "SELL", "score": 9, "analysis_score": 90.0, "trend": "STRONG BEARISH",
            "htf_trend": "BEARISH", "adx": 28.0, "rsi": 50.0, "atr": 0.0025, "server_time": "2026.09.08 14:00:00",
            "session_active": True
        }
        self.assertTrue(self.trader.is_qualified_candidate(valid_sell))
        self.assertFalse(self.trader.is_qualified_candidate({**valid_sell, "trend": "BULLISH"}))
        self.assertFalse(self.trader.is_qualified_candidate({**valid_sell, "trend": "COUNTER-TREND BEARISH"}))
        self.assertFalse(self.trader.is_qualified_candidate({**valid_sell, "htf_trend": "BULLISH"}))
        self.assertFalse(self.trader.is_qualified_candidate({**valid_sell, "rsi": 25.0}))  # oversold exhaustion
        self.assertFalse(self.trader.is_qualified_candidate({**valid_sell, "rsi": 65.0}))  # outside corridor [45, 60]

    def test_format_scan_matrix_excludes_unqualified_from_spotlight(self):
        """Verifies format_scan_matrix will NOT highlight unqualified setups as top opportunity."""
        scan_data = {
            "status": "ok",
            "server_time": "2026.09.08 22:00:00",
            "results": [
                {
                    "symbol": "EURUSD", "signal": "BUY", "score": 8, "trend": "COUNTER-TREND BULLISH",
                    "analysis_score": 80.0, "spread": 10.0, "sl_pips": 30.0, "tp_pips": 60.0
                }
            ]
        }
        matrix_text = self.trader.format_scan_matrix(scan_data)
        self.assertNotIn("TOP RANKED OPPORTUNITY", matrix_text)


class TestTelegramAutonomousHandlers(unittest.TestCase):
    def setUp(self):
        self.patcher = patch("handlers.ALLOWED_CHAT_IDS", [123456789])
        self.patcher.start()
        self.temp_flag_dir = tempfile.TemporaryDirectory()
        self.flag_path = os.path.join(self.temp_flag_dir.name, "autotrade_state.flag")
        self.flag_patch = patch("autotrade.core.autonomous_trader.AUTOTRADE_FLAG_FILE", self.flag_path)
        self.flag_patch.start()

    def tearDown(self):
        self.flag_patch.stop()
        self.temp_flag_dir.cleanup()
        self.patcher.stop()

    def _make_mock_update(self, chat_id=123456789, args=None, query_data=None):
        update = MagicMock()
        update.effective_chat.id = chat_id
        update.effective_user.id = chat_id
        if query_data:
            update.callback_query = MagicMock()
            update.callback_query.data = query_data
            update.callback_query.edit_message_text = AsyncMock()
            update.callback_query.answer = AsyncMock()
            update.message = None
        else:
            update.callback_query = None
            update.message = MagicMock()
            update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.args = args or []
        context.bot = AsyncMock()
        return update, context

    def test_cmd_autotrade(self):
        """Verifies /autotrade status command and argument handling."""
        async def run_test():
            update, context = self._make_mock_update(args=["on"])
            with patch("handlers.write_autotrade_flag"), \
                 patch("handlers.zmq_client.resume_bot", return_value={"status": "ok"}):
                await handlers.cmd_autotrade(update, context)
                self.assertTrue(autonomous_trader.is_enabled)
                update.message.reply_text.assert_called_once()
                sent_msg = update.message.reply_text.call_args[0][0]
                self.assertIn("AUTONOMOUS MULTI-SYMBOL TRADING ENGINE", sent_msg)

        asyncio.run(run_test())

    def test_cmd_scan(self):
        """Verifies /scan displays multi-symbol matrix."""
        async def run_test():
            update, context = self._make_mock_update()
            mock_scan = {
                "status": "ok",
                "results": [
                    {"symbol": "GBPUSD", "trend": "BULL", "score": 7, "signal": "BUY", "spread": 15.0}
                ]
            }
            with patch.object(autonomous_trader, "scan_portfolio_async", return_value=mock_scan):
                await handlers.cmd_scan(update, context)
                update.message.reply_text.assert_called_once()
                sent_msg = update.message.reply_text.call_args[0][0]
                self.assertIn("AUTONOMOUS MULTI-SYMBOL SCANNER", sent_msg)
                self.assertIn("GBPUSD", sent_msg)

        asyncio.run(run_test())

    def test_cmd_symbols(self):
        """Verifies /symbols displays portfolio watchlist."""
        async def run_test():
            update, context = self._make_mock_update()
            await handlers.cmd_symbols(update, context)
            update.message.reply_text.assert_called_once()
            sent_msg = update.message.reply_text.call_args[0][0]
            self.assertIn("AUTONOMOUS PORTFOLIO WATCHLIST", sent_msg)

        asyncio.run(run_test())

    def test_cb_autotrade_toggle(self):
        """Verifies callback query 1-tap pause/resume toggle."""
        async def run_test():
            update, context = self._make_mock_update(query_data="autotrade_toggle:pause")
            with patch("handlers.write_autotrade_flag"), \
                 patch("handlers.zmq_client.pause_bot", return_value={"status": "ok"}):
                await handlers.cb_autotrade_toggle(update, context)
                self.assertFalse(autonomous_trader.is_enabled)
                update.callback_query.answer.assert_called()

        asyncio.run(run_test())

    def test_cb_nav_action_autotrade(self):
        """Verifies navigation keyboard routes nav_autotrade and nav_scan correctly."""
        async def run_test():
            update, context = self._make_mock_update(query_data="nav_autotrade")
            with patch("handlers.cmd_autotrade", new_callable=AsyncMock) as mock_cmd:
                await handlers.cb_nav_action(update, context)
                mock_cmd.assert_called_once()

            update_scan, context_scan = self._make_mock_update(query_data="nav_scan")
            with patch("handlers.cmd_scan", new_callable=AsyncMock) as mock_cmd_scan:
                await handlers.cb_nav_action(update_scan, context_scan)
                mock_cmd_scan.assert_called_once()

        asyncio.run(run_test())


    def test_cmd_autotrade_status(self):
        """Verifies /autotrade status displays status panel without changing active state."""
        async def run_test():
            update, context = self._make_mock_update(args=["status"])
            autonomous_trader.set_enabled(True)
            await handlers.cmd_autotrade(update, context)
            self.assertTrue(autonomous_trader.is_enabled)
            update.message.reply_text.assert_called_once()
            sent_msg = update.message.reply_text.call_args[0][0]
            self.assertIn("AUTONOMOUS MULTI-SYMBOL TRADING ENGINE", sent_msg)
            self.assertIn("ACTIVE & SCANNING", sent_msg)

        asyncio.run(run_test())

    def test_cmd_status_reflects_autonomous_state(self):
        """Verifies /status (cmd_account) dynamically reflects autonomous trading mode."""
        async def run_test():
            mock_acc = {
                "status": "ok",
                "account_number": 213173,
                "balance": 90.49,
                "equity": 90.49,
                "margin": 0.0,
                "free_margin": 90.49,
                "margin_level": 0.0,
                "floating_pl": 0.0,
                "currency": "USD",
                "trade_mode": "REAL",
                "leverage": 100
            }
            # Active state
            autonomous_trader.set_enabled(True)
            update_active, context_active = self._make_mock_update()
            with patch("handlers.zmq_async", return_value=mock_acc):
                await handlers.cmd_account(update_active, context_active)
                update_active.message.reply_text.assert_called_once()
                sent_active = update_active.message.reply_text.call_args[0][0]
                self.assertIn("Autonomous Bot:", sent_active)
                self.assertIn("ACTIVE", sent_active)

            # Paused state
            autonomous_trader.set_enabled(False)
            update_paused, context_paused = self._make_mock_update()
            with patch("handlers.zmq_async", return_value=mock_acc):
                await handlers.cmd_account(update_paused, context_paused)
                update_paused.message.reply_text.assert_called_once()
                sent_paused = update_paused.message.reply_text.call_args[0][0]
                self.assertIn("Autonomous Bot:", sent_paused)
                self.assertIn("PAUSED", sent_paused)

        asyncio.run(run_test())


    def test_timeframe_durations_and_boundary_calculations(self):
        """Verifies timeframe second mappings, seconds-until-next-bar, and startup seeding."""
        trader = AutonomousMultiSymbolTrader(timeframe="H1", scan_on_bar_close_only=True)
        self.assertEqual(trader.get_timeframe_seconds("H1"), 3600)
        self.assertEqual(trader.get_timeframe_seconds("M30"), 1800)
        self.assertEqual(trader.get_timeframe_seconds("M15"), 900)
        self.assertEqual(trader.get_timeframe_seconds("M5"), 300)
        self.assertEqual(trader.get_timeframe_seconds("M1"), 60)
        self.assertEqual(trader.get_timeframe_seconds("H4"), 14400)
        self.assertEqual(trader.get_timeframe_seconds("D1"), 86400)

        # Test countdown to next boundary on H1
        # E.g. at 09:15:00 (3600 * 10 + 900 = 36900)
        ts_mid_bar = 36900.0
        secs_left = trader.get_seconds_until_next_bar(now=ts_mid_bar)
        self.assertEqual(secs_left, 2700.0)  # 45 minutes left

        # Startup seeding: first call registers boundary and returns False (no trade on startup)
        self.assertEqual(trader.last_scanned_bar_boundary, 0)
        self.assertFalse(trader.is_new_bar_boundary(now=ts_mid_bar))
        self.assertEqual(trader.last_scanned_bar_boundary, 36000)

        # Mid-bar call within same hour (e.g. 09:45:00 = 38700) -> returns False
        self.assertFalse(trader.is_new_bar_boundary(now=38700.0))
        self.assertEqual(trader.last_scanned_bar_boundary, 36000)

        # Candle boundary crossing (10:00:00 = 39600) -> returns True!
        self.assertTrue(trader.is_new_bar_boundary(now=39600.0))
        self.assertEqual(trader.last_scanned_bar_boundary, 39600)

        # Still inside hour 10 (10:15:00 = 40500) -> returns False
        self.assertFalse(trader.is_new_bar_boundary(now=40500.0))

        # Next candle boundary (11:00:00 = 43200) -> returns True!
        self.assertTrue(trader.is_new_bar_boundary(now=43200.0))
        self.assertEqual(trader.last_scanned_bar_boundary, 43200)

    def test_m30_timeframe_boundary_synchronization(self):
        """Verifies 30-minute boundary synchronization (e.g. 1:30, 2:00)."""
        trader = AutonomousMultiSymbolTrader(timeframe="M30", scan_on_bar_close_only=True)
        # Start at 01:10 (ts = 4200)
        self.assertFalse(trader.is_new_bar_boundary(now=4200.0))
        self.assertEqual(trader.last_scanned_bar_boundary, 3600)  # Seeded to 01:00

        # At 01:25 (ts = 5100) -> mid-bar, returns False
        self.assertFalse(trader.is_new_bar_boundary(now=5100.0))

        # At 01:30 (ts = 5400) -> exactly 30 min mark, returns True!
        self.assertTrue(trader.is_new_bar_boundary(now=5400.0))
        self.assertEqual(trader.last_scanned_bar_boundary, 5400)

        # At 01:45 (ts = 6300) -> mid-bar, returns False
        self.assertFalse(trader.is_new_bar_boundary(now=6300.0))

        # At 02:00 (ts = 7200) -> top of the hour, returns True!
        self.assertTrue(trader.is_new_bar_boundary(now=7200.0))
        self.assertEqual(trader.last_scanned_bar_boundary, 7200)

    def test_set_timeframe_and_toggle_scan_on_bar_close_only(self):
        """Verifies setting timeframe resets boundary and toggling scan_on_bar_close_only."""
        trader = AutonomousMultiSymbolTrader(timeframe="H1")
        trader.last_scanned_bar_boundary = 36000

        # Valid timeframe change resets anchor
        self.assertTrue(trader.set_timeframe("M30"))
        self.assertEqual(trader.timeframe, "M30")
        self.assertEqual(trader.last_scanned_bar_boundary, 0)

        # Invalid timeframe rejected
        self.assertFalse(trader.set_timeframe("INVALID_TF"))
        self.assertEqual(trader.timeframe, "M30")

        # Toggle scan_on_bar_close_only
        trader.set_scan_on_bar_close_only(False)
        self.assertFalse(trader.scan_on_bar_close_only)
        # When disabled, is_new_bar_boundary always returns True
        self.assertTrue(trader.is_new_bar_boundary(now=12345.0))

        trader.set_scan_on_bar_close_only(True)
        self.assertTrue(trader.scan_on_bar_close_only)

    def test_run_cycle_async_bar_boundary_gate(self):
        """Verifies run_cycle_async executes only at candle boundary unless forced."""
        trader = AutonomousMultiSymbolTrader(timeframe="H1", scan_on_bar_close_only=True)
        # Startup seeding
        trader.is_new_bar_boundary(now=36000.0)

        async def run_test():
            with patch.object(trader, "execute_autonomous_cycle", new_callable=AsyncMock) as mock_exec:
                # Mid-bar timestamp (no boundary): should NOT execute
                with patch("time.time", return_value=37000.0):
                    await trader.run_cycle_async()
                    mock_exec.assert_not_called()

                # Forced execution: bypasses boundary check
                with patch("time.time", return_value=37000.0):
                    await trader.run_cycle_async(force=True)
                    mock_exec.assert_called_once()

                mock_exec.reset_mock()

                # Boundary crossed (10:00:00 = 39600): should execute!
                with patch("time.time", return_value=39600.0):
                    await trader.run_cycle_async()
                    mock_exec.assert_called_once()

        asyncio.run(run_test())

    def test_cmd_timeframe_handler(self):
        """Verifies /timeframe command view and update behavior."""
        async def run_test():
            # View status (no args)
            update, context = self._make_mock_update(args=[])
            await handlers.cmd_timeframe(update, context)
            update.message.reply_text.assert_called_once()
            status_text = update.message.reply_text.call_args[0][0]
            self.assertIn("AUTONOMOUS TIMEFRAME STATUS", status_text)
            self.assertIn(autonomous_trader.timeframe, status_text)

            # Set valid timeframe
            update_set, context_set = self._make_mock_update(args=["M30"])
            await handlers.cmd_timeframe(update_set, context_set)
            update_set.message.reply_text.assert_called_once()
            set_text = update_set.message.reply_text.call_args[0][0]
            self.assertIn("AUTONOMOUS TIMEFRAME UPDATED", set_text)
            self.assertIn("M30", set_text)
            self.assertEqual(autonomous_trader.timeframe, "M30")

            # Restore H1
            update_h1, context_h1 = self._make_mock_update(args=["H1"])
            await handlers.cmd_timeframe(update_h1, context_h1)
            self.assertEqual(autonomous_trader.timeframe, "H1")

            # Invalid timeframe
            update_inv, context_inv = self._make_mock_update(args=["INVALID"])
            await handlers.cmd_timeframe(update_inv, context_inv)
            inv_text = update_inv.message.reply_text.call_args[0][0]
            self.assertIn("Invalid timeframe", inv_text)

        asyncio.run(run_test())

    def test_cmd_autotrade_tf_and_barclose_subcommands(self):
        """Verifies /autotrade tf <TF> and /autotrade barclose <on|off> subcommands."""
        async def run_test():
            # /autotrade tf M30
            update, context = self._make_mock_update(args=["tf", "M30"])
            await handlers.cmd_autotrade(update, context)
            sent_text = update.message.reply_text.call_args[0][0]
            self.assertIn("Autonomous Scan Timeframe set to:", sent_text)
            self.assertIn("M30", sent_text)
            self.assertEqual(autonomous_trader.timeframe, "M30")

            # /autotrade barclose off
            update_bc_off, context_bc_off = self._make_mock_update(args=["barclose", "off"])
            await handlers.cmd_autotrade(update_bc_off, context_bc_off)
            self.assertFalse(autonomous_trader.scan_on_bar_close_only)

            # /autotrade barclose on
            update_bc_on, context_bc_on = self._make_mock_update(args=["barclose", "on"])
            await handlers.cmd_autotrade(update_bc_on, context_bc_on)
            self.assertTrue(autonomous_trader.scan_on_bar_close_only)

            # Restore H1
            autonomous_trader.set_timeframe("H1")

        asyncio.run(run_test())

    def test_manual_scan_runs_on_demand_mid_bar(self):
        """Verifies /scan runs on-demand at any time without waiting for candle boundary."""
        async def run_test():
            mock_scan = {
                "status": "ok",
                "server_time": "2026.09.08 14:23:45",
                "results": [
                    {
                        "symbol": "EURUSD", "score": 7, "signal": "BUY", "trend": "STRONG_BULLISH",
                        "spread": 12.0, "sl_pips": 25.0, "tp_pips": 50.0, "adx": 25.0, "rsi": 50.0
                    }
                ]
            }
            update, context = self._make_mock_update(args=[])
            with patch.object(autonomous_trader, "scan_portfolio_async", return_value=mock_scan):
                await handlers.cmd_scan(update, context)
                update.message.reply_text.assert_called_once()
                scan_text = update.message.reply_text.call_args[0][0]
                self.assertIn("AUTONOMOUS MULTI-SYMBOL SCANNER", scan_text)
                self.assertIn("EURUSD", scan_text)
                self.assertIn("Score: <b>7/10</b>", scan_text)

        asyncio.run(run_test())

    def test_format_countdown_string(self):
        """Verifies countdown string formats correctly for minutes and hours."""
        trader = AutonomousMultiSymbolTrader()
        self.assertEqual(trader.format_countdown_string(45.0), "0m 45s")
        self.assertEqual(trader.format_countdown_string(125.0), "2m 05s")
        self.assertEqual(trader.format_countdown_string(3600.0), "1h 00m 00s")
        self.assertEqual(trader.format_countdown_string(7345.0), "2h 02m 25s")

    def test_scan_portfolio_custom_symbols_and_timeframe(self):
        """Verifies scan_portfolio accepts custom symbols list and custom timeframe."""
        trader = AutonomousMultiSymbolTrader()
        with patch("autotrade.core.autonomous_trader.zmq_client.scan_symbols") as mock_scan:
            mock_scan.return_value = {
                "status": "ok",
                "server_time": "2026.09.08 14:15:30",
                "results": [{"symbol": "GBPJPY", "score": 7}]
            }
            res = trader.scan_portfolio(timeframe="M15", symbols=["GBPJPY", "EURJPY"])
            mock_scan.assert_called_once_with(symbols="GBPJPY,EURJPY", timeframe="M15", timeout_ms=6000)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["results"][0]["symbol"], "GBPJPY")

    def test_multi_timeframe_def_bar_time_derivation(self):
        """Verifies def_bar_time accurately snaps to candle boundary for any timeframe (e.g. M5, M30, H4)."""
        trader = AutonomousMultiSymbolTrader()
        with patch("autotrade.core.autonomous_trader.zmq_client.scan_symbols") as mock_scan:
            # Server time is 14:27:15; return fresh dict on each call to avoid in-place mutation
            mock_scan.side_effect = lambda **kwargs: {
                "status": "ok",
                "server_time": "2026.09.08 14:27:15",
                "results": [{"symbol": "EURUSD", "score": 6}]
            }
            # For M5: should snap to 14:25:00
            res_m5 = trader.scan_portfolio(timeframe="M5", symbols=["EURUSD"])
            bt_m5 = res_m5["results"][0]["bar_time"]
            self.assertEqual(bt_m5 % 300, 0)

            # For M30: should snap to 14:00:00
            res_m30 = trader.scan_portfolio(timeframe="M30", symbols=["EURUSD"])
            bt_m30 = res_m30["results"][0]["bar_time"]
            self.assertEqual(bt_m30 % 1800, 0)

            # For H4: should snap to 12:00:00
            res_h4 = trader.scan_portfolio(timeframe="H4", symbols=["EURUSD"])
            bt_h4 = res_h4["results"][0]["bar_time"]
            self.assertEqual(bt_h4 % 14400, 0)

    def test_cmd_scan_with_custom_symbol_and_timeframe(self):
        """Verifies /scan <SYM> [TF] scans custom symbol with custom timeframe."""
        async def run_test():
            mock_scan = {
                "status": "ok",
                "server_time": "2026.09.08 14:23:45",
                "results": [
                    {
                        "symbol": "GBPJPY", "score": 8, "signal": "BUY", "trend": "STRONG_BULLISH",
                        "spread": 14.0, "sl_pips": 25.0, "tp_pips": 50.0, "adx": 26.0, "rsi": 55.0
                    }
                ]
            }
            update, context = self._make_mock_update(args=["GBPJPY", "M30"])
            with patch.object(autonomous_trader, "scan_portfolio_async", return_value=mock_scan) as mock_async:
                await handlers.cmd_scan(update, context)
                mock_async.assert_called_once()
                call_kw = mock_async.call_args[1]
                self.assertEqual(call_kw.get("timeframe"), "M30")
                self.assertIn("GBPJPY", call_kw.get("symbols", []))
                update.message.reply_text.assert_called_once()
                scan_text = update.message.reply_text.call_args[0][0]
                self.assertIn("GBPJPY", scan_text)

        asyncio.run(run_test())

    def test_cmd_scan_with_only_timeframe(self):
        """Verifies /scan M30 triggers full portfolio scan with M30 timeframe."""
        async def run_test():
            mock_scan = {
                "status": "ok",
                "server_time": "2026.09.08 14:23:45",
                "results": [
                    {
                        "symbol": "EURUSD", "score": 6, "signal": "HOLD", "trend": "NEUTRAL",
                        "spread": 12.0, "sl_pips": 25.0, "tp_pips": 50.0
                    }
                ]
            }
            update, context = self._make_mock_update(args=["M30"])
            with patch.object(autonomous_trader, "scan_portfolio_async", return_value=mock_scan) as mock_async:
                await handlers.cmd_scan(update, context)
                mock_async.assert_called_once_with(timeframe="M30")
                update.message.reply_text.assert_called_once()
                scan_text = update.message.reply_text.call_args[0][0]
                self.assertIn("AUTONOMOUS MULTI-SYMBOL SCANNER", scan_text)

    def test_spread_to_atr_normalized_sorting(self):
        """
        Verifies that candidates are ranked by normalized spread-to-ATR rather than raw points.
        Gold (30 pts spread / $15 ATR = 2% ATR cost) should outrank EURUSD (20 pts spread / 20 pip ATR = 10% ATR cost)
        at equal scores.
        """
        async def run_test():
            trader = AutonomousMultiSymbolTrader(symbols=["EURUSD", "XAUUSD"], min_score=6)
            mock_scan = {
                "status": "ok",
                "results": [
                    {
                        "symbol": "EURUSD", "score": 9, "analysis_score": 90.0, "signal": "BUY", "trend": "BULLISH",
                        "spread": 20.0, "atr": 0.0020, "sl_pips": 30.0, "tp_pips": 60.0,
                        "adx": 25.0, "rsi": 50.0, "htf_trend": "BULLISH"
                    },
                    {
                        "symbol": "XAUUSD", "score": 9, "analysis_score": 90.0, "signal": "BUY", "trend": "BULLISH",
                        "spread": 30.0, "atr": 15.0, "sl_pips": 150.0, "tp_pips": 300.0,
                        "adx": 25.0, "rsi": 50.0, "htf_trend": "BULLISH"
                    }
                ]
            }
            with patch.object(trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value={"status": "ok", "positions": []}), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order", return_value={"status": "ok", "ticket": 999123}) as mock_open:
                trades = await trader.execute_autonomous_cycle()
                self.assertEqual(len(trades), 1)
                # XAUUSD has lower spread-to-ATR (0.02 vs 0.10) so it must execute first!
                self.assertEqual(trades[0]["symbol"], "XAUUSD")

        asyncio.run(run_test())

    def test_disk_state_persistence(self):
        """Verifies state serialization to and restoration from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "test_trader_state.json")
            trader1 = AutonomousMultiSymbolTrader(symbols=["EURUSD"], state_file_path=state_file)
            trader1.total_trades_executed = 42
            trader1.last_trade_times["EURUSD"] = 1788899999.0
            trader1.seen_bar_times["EURUSD"] = 1788890000
            trader1._save_state_to_disk()
            self.assertTrue(os.path.exists(state_file))

            # New instance loading from same path
            trader2 = AutonomousMultiSymbolTrader(symbols=["EURUSD"], state_file_path=state_file)
            self.assertEqual(trader2.total_trades_executed, 42)
            self.assertEqual(trader2.last_trade_times.get("EURUSD"), 1788899999.0)
            self.assertEqual(trader2.seen_bar_times.get("EURUSD"), 1788890000)

    def test_quote_rejection_in_production(self):
        """Verifies that missing market quote in production mode strictly halts trade dispatch."""
        async def run_test():
            trader = AutonomousMultiSymbolTrader(symbols=["EURUSD"], min_score=6)
            mock_scan = {
                "status": "ok",
                "results": [
                    {
                        "symbol": "EURUSD", "score": 8, "signal": "BUY", "trend": "BULLISH",
                        "spread": 10.0, "sl_pips": 30.0, "tp_pips": 60.0,
                        "adx": 25.0, "rsi": 50.0, "htf_trend": "BULLISH",
                        "ask": 0.0, "bid": 0.0, "price": 0.0
                    }
                ]
            }
            with patch.object(trader, "scan_portfolio_async", return_value=mock_scan), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_positions", return_value={"status": "ok", "positions": []}), \
                 patch("autotrade.core.autonomous_trader.zmq_client.get_quote", return_value={"status": "error"}), \
                 patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}), \
                 patch("autotrade.core.autonomous_trader.zmq_client.open_order") as mock_open:
                trades = await trader.execute_autonomous_cycle()
                self.assertEqual(len(trades), 0)
                mock_open.assert_not_called()

        asyncio.run(run_test())

    def test_dynamic_market_watch_discovery_startup(self):
        """Verifies trader dynamically discovers symbols from Market Watch on startup when symbols is None."""
        mock_mw_symbols = {
            "status": "ok",
            "action": "GET_MARKET_WATCH_SYMBOLS",
            "count": 4,
            "symbols": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
        }
        with patch("autotrade.core.autonomous_trader.zmq_client.get_market_watch_symbols", return_value=mock_mw_symbols):
            trader = AutonomousMultiSymbolTrader(symbols=None)
            self.assertTrue(trader.dynamic_market_watch)
            self.assertEqual(trader.symbols, ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])

    def test_dynamic_market_watch_exotic_filtering(self):
        """Verifies exotic symbols (AZN, TRY, RUB, ZAR) are filtered out during dynamic discovery."""
        mock_mw_symbols = {
            "status": "ok",
            "action": "GET_MARKET_WATCH_SYMBOLS",
            "count": 6,
            "symbols": ["EURUSD_min", "EURAZN_min", "USDTRY", "USDRUB", "USDZAR", "CADJPY_min"]
        }
        with patch("autotrade.core.autonomous_trader.zmq_client.get_market_watch_symbols", return_value=mock_mw_symbols):
            trader = AutonomousMultiSymbolTrader(symbols=None)
            self.assertIn("EURUSD_MIN", trader.symbols)
            self.assertIn("CADJPY_MIN", trader.symbols)
            self.assertNotIn("EURAZN_MIN", trader.symbols)
            self.assertNotIn("USDTRY", trader.symbols)
            self.assertNotIn("USDRUB", trader.symbols)
            self.assertNotIn("USDZAR", trader.symbols)

    def test_dynamic_market_watch_sync_async(self):
        """Verifies async dynamic Market Watch synchronization updates trader symbols."""
        trader = AutonomousMultiSymbolTrader(symbols=["EURUSD"], dynamic_market_watch=True)
        self.assertEqual(trader.symbols, ["EURUSD"])

        mock_update = {
            "status": "ok",
            "symbols": ["GBPUSD", "USDCHF", "AUDUSD"]
        }
        async def run_test():
            with patch("autotrade.core.autonomous_trader.zmq_client.get_market_watch_symbols_async", return_value=mock_update):
                updated = await trader.sync_market_watch_symbols_async()
                self.assertEqual(updated, ["GBPUSD", "USDCHF", "AUDUSD"])
                self.assertEqual(trader.symbols, ["GBPUSD", "USDCHF", "AUDUSD"])

        asyncio.run(run_test())

    def test_zmq_client_get_market_watch_symbols_fallback(self):
        """Verifies zmq_client queries GET_MARKET_WATCH_SYMBOLS and falls back to GET_SYMBOLS if needed."""
        from zmq_client import zmq_client

        # 1. Successful GET_MARKET_WATCH_SYMBOLS
        with patch.object(zmq_client, "send_command", return_value={"status": "ok", "symbols": ["EURUSD"]}) as mock_send:
            res = zmq_client.get_market_watch_symbols()
            self.assertEqual(res["status"], "ok")
            mock_send.assert_called_once_with("GET_MARKET_WATCH_SYMBOLS", timeout_ms=5000)

        # 2. Fallback when GET_MARKET_WATCH_SYMBOLS returns error/unsupported
        with patch.object(zmq_client, "send_command", side_effect=[
            {"status": "error", "message": "Unknown action"},
            {"status": "ok", "symbols": ["EURUSD", "GBPUSD"]}
        ]) as mock_send_fallback:
            res = zmq_client.get_market_watch_symbols()
            self.assertEqual(res["status"], "ok")
            self.assertEqual(mock_send_fallback.call_count, 2)

    def test_format_symbols_panel_dynamic_badge(self):
        """Verifies format_symbols_panel reflects Market Watch Dynamic badge."""
        trader = AutonomousMultiSymbolTrader(symbols=["EURUSD", "GBPUSD"], dynamic_market_watch=True)
        with patch.object(trader, "sync_market_watch_symbols", return_value=["EURUSD", "GBPUSD"]):
            panel = trader.format_symbols_panel()
            self.assertIn("Market Watch Dynamic", panel)
            self.assertIn("EURUSD", panel)


if __name__ == "__main__":
    unittest.main()



