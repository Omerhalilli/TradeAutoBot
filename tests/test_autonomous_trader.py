"""
Unit tests for AutonomousMultiSymbolTrader and its integration with Telegram commands & ZeroMQ.
Verifies multi-symbol scanning, confluence scoring thresholding, cooldown, spread filtering,
direct order dispatch, and alert broadcasting with zero user advisory prompting.
All live market executions are fully mocked to safeguard user account capital.
"""

import asyncio
import os
import tempfile
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

from autotrade.core.autonomous_trader import AutonomousMultiSymbolTrader, autonomous_trader
import handlers


class TestAutonomousMultiSymbolTrader(unittest.TestCase):
    def setUp(self):
        self.trader = AutonomousMultiSymbolTrader(
            symbols=["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
            min_score=6,
            cooldown_sec=300,
            max_spread=40.0
        )

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

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("PAUSED\n")
            temp_flag = f.name

        try:
            with patch("autotrade.core.autonomous_trader.AUTOTRADE_FLAG_FILE", temp_flag):
                self.assertFalse(self.trader.is_autotrade_active())
        finally:
            if os.path.exists(temp_flag):
                os.unlink(temp_flag)

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


class TestTelegramAutonomousHandlers(unittest.TestCase):
    def setUp(self):
        self.patcher = patch("handlers.ALLOWED_CHAT_IDS", [123456789])
        self.patcher.start()

    def tearDown(self):
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
            with patch("handlers.zmq_client.resume_bot", return_value={"status": "ok"}):
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
            with patch("handlers.zmq_client.pause_bot", return_value={"status": "ok"}):
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


if __name__ == "__main__":
    unittest.main()
