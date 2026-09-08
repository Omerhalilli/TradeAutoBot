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
                    "score": 8,
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
                        "score": 7,
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
                    "score": 8,
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
                    "symbol": "EURUSD", "score": 8, "signal": "BUY", "trend": "STRONG_BULLISH",
                    "adx": 28.0, "rsi": 52.0, "htf_trend": "BULLISH", "spread": 10.0,
                    "sl_pips": 30.0, "tp_pips": 60.0, "bar_time": 1788890000
                }
            ]
        }
        mock_scan_bar2 = {
            "status": "ok",
            "results": [
                {
                    "symbol": "EURUSD", "score": 8, "signal": "BUY", "trend": "STRONG_BULLISH",
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


if __name__ == "__main__":
    unittest.main()


