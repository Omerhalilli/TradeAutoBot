"""
Comprehensive Automated Tests for Background Screenshot Capture and
Account-Specific Accessible Symbols Selection.
"""
import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from zmq_client import zmq_client
from account_manager import account_manager, AccountProfile
import handlers


class TestScreenshotAndAccessibleSymbols(unittest.TestCase):
    def setUp(self):
        # Save original state of active account
        self.original_active_id = account_manager.active_id

    def tearDown(self):
        account_manager.set_active_account(self.original_active_id)

    def test_01_zmq_client_get_symbols_signature(self):
        """Verify zmq_client has get_symbols method and sends correct payload structure."""
        with patch.object(zmq_client, "send_command") as mock_send:
            mock_send.return_value = {"status": "ok", "action": "GET_SYMBOLS", "symbols": ["EURUSD", "GBPUSD"]}
            res = zmq_client.get_symbols(timeout_ms=3000)
            mock_send.assert_called_once_with("GET_SYMBOLS", timeout_ms=3000)
            self.assertEqual(res.get("status"), "ok")
            self.assertIn("symbols", res)
            self.assertEqual(len(res["symbols"]), 2)

    def test_02_account_manager_symbols_cache(self):
        """Verify account_manager stores and returns symbols per account profile."""
        account_manager.set_active_account("1")
        test_symbols = ["EURUSD.az", "GBPUSD.az", "USDJPY.az", "XAUUSD.az"]
        account_manager.set_account_symbols(test_symbols, account_id="1")
        cached = account_manager.get_account_symbols("1")
        self.assertEqual(cached, test_symbols)

        # Account 2 should have its own distinct list or empty
        cached_acc2 = account_manager.get_account_symbols("2")
        self.assertNotEqual(cached_acc2, test_symbols)

    def test_03_symbol_display_name_formatting(self):
        """Verify flags and commodity emojis are accurately mapped."""
        self.assertIn("🇬🇧", handlers.get_symbol_display_name("GBPUSD"))
        self.assertIn("🇪🇺", handlers.get_symbol_display_name("EURUSD"))
        self.assertIn("🪙", handlers.get_symbol_display_name("XAUUSD"))
        self.assertIn("🪙", handlers.get_symbol_display_name("GOLD"))
        self.assertIn("🥈", handlers.get_symbol_display_name("XAGUSD"))
        self.assertIn("🇯🇵", handlers.get_symbol_display_name("USDJPY"))
        self.assertIn("🇨🇭", handlers.get_symbol_display_name("USDCHF"))
        self.assertIn("🇦🇺", handlers.get_symbol_display_name("AUDUSD"))
        self.assertIn("🇳🇿", handlers.get_symbol_display_name("NZDUSD"))
        self.assertIn("🇨🇦", handlers.get_symbol_display_name("USDCAD"))
        self.assertIn("₿", handlers.get_symbol_display_name("BTCUSD"))
        self.assertIn("🛢️", handlers.get_symbol_display_name("USOIL"))
        self.assertIn("🛢️", handlers.get_symbol_display_name("UKOIL"))
        self.assertIn("📈", handlers.get_symbol_display_name("US30"))

    def test_04_symbol_keyboard_pagination(self):
        """Verify pagination creates correct page slices and navigation buttons."""
        symbols = [f"SYM{i}" for i in range(18)]
        # Page 0 (8 items)
        kb_p0 = handlers.get_symbol_keyboard(symbols, page=0, per_page=8)
        self.assertIsNotNone(kb_p0)
        # Check that page 0 has 4 rows of 2 symbols + 1 nav row + 1 action row = 6 rows
        self.assertEqual(len(kb_p0.inline_keyboard), 6)
        # Check first symbol
        self.assertEqual(kb_p0.inline_keyboard[0][0].callback_data, "shotsym:SYM0")
        # Check nav row buttons: Prev (disabled/noop), Page indicator, Next
        nav_row = kb_p0.inline_keyboard[4]
        self.assertEqual(nav_row[0].callback_data, "shotsym:noop")  # No prev on page 0
        self.assertIn("1/3", nav_row[1].text)
        self.assertEqual(nav_row[2].callback_data, "shotsym:page:1")

        # Page 1 (8 items)
        kb_p1 = handlers.get_symbol_keyboard(symbols, page=1, per_page=8)
        nav_row_p1 = kb_p1.inline_keyboard[4]
        self.assertEqual(nav_row_p1[0].callback_data, "shotsym:page:0")
        self.assertIn("2/3", nav_row_p1[1].text)
        self.assertEqual(nav_row_p1[2].callback_data, "shotsym:page:2")

        # Page 2 (2 items remaining)
        kb_p2 = handlers.get_symbol_keyboard(symbols, page=2, per_page=8)
        # 1 row of 2 symbols + 1 nav row + 1 action row = 3 rows
        self.assertEqual(len(kb_p2.inline_keyboard), 3)
        nav_row_p2 = kb_p2.inline_keyboard[1]
        self.assertEqual(nav_row_p2[0].callback_data, "shotsym:page:1")
        self.assertIn("3/3", nav_row_p2[1].text)
        self.assertEqual(nav_row_p2[2].callback_data, "shotsym:noop")  # No next on page 2

        # Check bottom action row has Active Chart and Refresh
        action_row = kb_p0.inline_keyboard[5]
        self.assertEqual(action_row[0].callback_data, "shotsym:CURRENT")
        self.assertEqual(action_row[1].callback_data, "shotsym:refresh")

    def test_05_get_accessible_symbols_fallback_and_cache(self):
        """Verify get_accessible_symbols caches MT4 results and falls back gracefully."""
        account_manager.set_active_account("1")
        account_manager.set_account_symbols([], "1")

        # 1. MT4 Offline -> returns fallback
        with patch.object(zmq_client, "send_command") as mock_send:
            mock_send.return_value = {"status": "error", "message": "MT4 not connected"}
            syms = asyncio.run(handlers.get_accessible_symbols(force_refresh=True))
            self.assertEqual(syms, handlers.DEFAULT_FALLBACK_SYMBOLS)

        # 2. MT4 Online -> returns live account symbols and caches them
        live_symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "USOIL"]
        with patch.object(zmq_client, "send_command") as mock_send:
            mock_send.return_value = {"status": "ok", "action": "GET_SYMBOLS", "symbols": live_symbols}
            syms = asyncio.run(handlers.get_accessible_symbols(force_refresh=True))
            self.assertEqual(syms, live_symbols)
            # Verify cached in account manager
            self.assertEqual(account_manager.get_account_symbols("1"), live_symbols)

    def test_06_cb_screenshot_symbol_navigation_and_pagination(self):
        """Verify callback queries for BACK, pagination, and refresh."""
        mock_update = MagicMock()
        mock_query = AsyncMock()
        mock_update.callback_query = mock_query

        # Test pagination callback
        mock_query.data = "shotsym:page:1"
        with patch("handlers.get_accessible_symbols", new_callable=AsyncMock) as mock_syms:
            mock_syms.return_value = [f"PAIR{i}" for i in range(12)]
            asyncio.run(handlers.cb_screenshot_symbol(mock_update, MagicMock()))
            mock_query.edit_message_text.assert_called_once()
            call_args = mock_query.edit_message_text.call_args
            self.assertIn("INSTITUTIONAL CHART SNAPSHOT WIZARD", call_args[0][0])
            self.assertIn("reply_markup", call_args[1])

        # Test refresh callback
        mock_query.reset_mock()
        mock_query.data = "shotsym:refresh"
        with patch("handlers.get_accessible_symbols", new_callable=AsyncMock) as mock_syms:
            mock_syms.return_value = ["EURUSD", "GBPUSD"]
            asyncio.run(handlers.cb_screenshot_symbol(mock_update, MagicMock()))
            mock_syms.assert_called_with(force_refresh=True)

        # Test selecting a symbol -> proceeds to timeframe menu
        mock_query.reset_mock()
        mock_query.data = "shotsym:EURUSD"
        asyncio.run(handlers.cb_screenshot_symbol(mock_update, MagicMock()))
        call_args = mock_query.edit_message_text.call_args
        self.assertIn("Target Instrument:</b> <code>EURUSD</code>", call_args[0][0])

    def test_07_mql4_source_integrity_checks(self):
        """Verify MQL4 source files do NOT modify chart 0, check targetChartId <= 0, and implement background capture."""
        mql4_files = [
            os.path.join(os.path.dirname(__file__), "..", "ZeroMQBridge.mqh"),
            os.path.join(os.path.dirname(__file__), "..", "MQL4", "Include", "ZeroMQBridge.mqh"),
            os.path.join(os.path.dirname(__file__), "..", "MT4_ZeroMQ_Bridge.mq4"),
            os.path.join(os.path.dirname(__file__), "..", "MQL4", "Experts", "MT4_ZeroMQ_Bridge.mq4"),
            os.path.join(os.path.dirname(__file__), "..", "SmartAutoTradeEA_Pro.mq4"),
            os.path.join(os.path.dirname(__file__), "..", "MQL4", "Experts", "SmartAutoTradeEA_Pro.mq4"),
        ]

        for path in mql4_files:
            self.assertTrue(os.path.exists(path), f"Missing MQL4 file: {path}")
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            # Verify GET_SYMBOLS is present in ZeroMQ bridge files
            if "ZeroMQ" in path:
                self.assertIn("GET_SYMBOLS", content, f"GET_SYMBOLS missing in {path}")
                self.assertIn("SymbolsTotal", content, f"SymbolsTotal missing in {path}")

            # Verify CHART_BRING_TO_TOP is present to restore active chart
            if "ZeroMQBridge" in path or "MT4_ZeroMQ_Bridge" in path or "SmartAutoTradeEA" in path:
                self.assertIn("CHART_BRING_TO_TOP", content, f"CHART_BRING_TO_TOP missing in {path}")

            # Verify targetChartId <= 0 is checked (not just < 0, to avoid ChartOpen failing to 0)
            self.assertIn("targetChartId <= 0", content, f"targetChartId <= 0 check missing in {path}")

            # Verify no harmful ChartSetSymbolPeriod(0, ...) in screenshot handlers
            lines = content.splitlines()
            in_screenshot = False
            for line in lines:
                if "Zmq_HandleScreenshot" in line or "HandleScreenshot" in line or "Telegram_CmdSendChartScreenshot" in line:
                    in_screenshot = True
                if in_screenshot and "ChartSetSymbolPeriod" in line:
                    self.fail(f"Dangerous ChartSetSymbolPeriod found in screenshot handler in {path}: {line}")
                if in_screenshot and line.strip().startswith("}"):
                    in_screenshot = False

    def test_08_clean_symbol_broker_suffixes(self):
        """Verify broker suffixes like .az are preserved correctly."""
        self.assertEqual(handlers.clean_symbol("EURUSD.az"), "EURUSD.az")
        self.assertEqual(handlers.clean_symbol("gbpusd.az"), "GBPUSD.az")
        self.assertEqual(handlers.clean_symbol("GOLD.az"), "XAUUSD.az")
        self.assertEqual(handlers.clean_symbol("SILVER.az"), "XAGUSD.az")
        self.assertEqual(handlers.clean_symbol("EUR-USD"), "EURUSD")
        self.assertEqual(handlers.clean_symbol("GBP/USD"), "GBPUSD")
        self.assertEqual(handlers.clean_symbol(" crude "), "USOIL")

    def test_09_account_manager_add_or_update_preserves_symbols(self):
        """Verify add_or_update_account does not wipe cached symbols."""
        account_manager.set_account_symbols(["EURUSD.az", "GBPUSD.az"], "1")
        acc = account_manager.get_account_by_id("1")
        self.assertIsNotNone(acc)
        # Update name or profile without passing symbols
        updated = account_manager.add_or_update_account(
            "1", acc.account_number, "Broker Updated", acc.profile_name, acc.server, acc.zmq_url
        )
        self.assertEqual(updated.symbols, ["EURUSD.az", "GBPUSD.az"])
        self.assertEqual(account_manager.get_account_symbols("1"), ["EURUSD.az", "GBPUSD.az"])

    def test_10_cb_screenshot_tf_photo_caption_support(self):
        """Verify cb_screenshot_tf edits photo caption instead of crashing when executed on a photo message."""
        mock_update = MagicMock()
        mock_query = AsyncMock()
        mock_update.callback_query = mock_query
        mock_query.data = "shottf:EURUSD:H1"
        # Simulate photo message
        mock_query.message.photo = [MagicMock()]
        mock_update.effective_chat.id = 123456789

        with patch("handlers.execute_screenshot_delivery", new_callable=AsyncMock) as mock_delivery:
            mock_delivery.return_value = True
            asyncio.run(handlers.cb_screenshot_tf(mock_update, MagicMock()))
            # Verify edit_message_caption was called
            mock_query.edit_message_caption.assert_called_once()
            call_kwargs = mock_query.edit_message_caption.call_args
            self.assertIn("Capturing EURUSD (H1)", call_kwargs[1]["caption"])
            mock_query.delete_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
