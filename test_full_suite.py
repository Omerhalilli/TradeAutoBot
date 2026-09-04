"""
Comprehensive Automated Test Suite for MT4 Telegram Bridge.
Tests ZMQ endpoints, live MT4 telemetry, news service, account manager,
and handlers text formatting.
"""
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

from config import TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_IDS, ZMQ_SERVER_URL
from zmq_client import zmq_client
from news_service import news_service
from account_manager import account_manager
import handlers

class TestMT4BridgeFullSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("\n" + "=" * 60)
        print("  STARTING FULL END-TO-END VERIFICATION TEST SUITE")
        print("=" * 60)

    def test_01_config(self):
        self.assertTrue(bool(TELEGRAM_BOT_TOKEN), "Bot token must not be empty")
        self.assertGreater(len(ALLOWED_CHAT_IDS), 0, "Must have allowed chat IDs")
        self.assertTrue(ZMQ_SERVER_URL.startswith("tcp://"), "ZMQ URL must start with tcp://")
        print("  [PASS] Configuration validation verified.")

    def test_02_zmq_ping_and_latency(self):
        res = zmq_client.ping()
        self.assertEqual(res.get("status"), "ok", f"Ping failed: {res}")
        latency = zmq_client.ping_latency_ms()
        self.assertGreater(latency, 0.0, f"Latency must be positive, got {latency}")
        print(f"  [PASS] Live MT4 Ping OK (Roundtrip Latency: {latency:.2f} ms)")

    def test_03_zmq_get_account(self):
        res = zmq_client.get_account()
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("balance", res)
        self.assertIn("equity", res)
        print(f"  [PASS] Live MT4 Get Account OK (Login: {res.get('account_number')}, Equity: ${res.get('equity'):,.2f})")

    def test_04_zmq_get_positions(self):
        res = zmq_client.get_positions()
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("positions", res)
        print(f"  [PASS] Live MT4 Get Positions OK (Open Orders: {res.get('count')})")

    def test_05_zmq_get_history(self):
        res = zmq_client.get_history(limit=5)
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("trades", res)
        print(f"  [PASS] Live MT4 Get History OK (History Deals Count: {res.get('count')})")

    def test_06_zmq_get_boost(self):
        res = zmq_client.get_boost()
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("engine_hz"), 4)
        self.assertIn("spread_gbpusd", res)
        self.assertIn("spread_eurusd", res)
        self.assertIn("spread_xauusd", res)
        print(f"  [PASS] Live MT4 /boost OK (Spreads: GBP={res.get('spread_gbpusd')}, EUR={res.get('spread_eurusd')}, Gold={res.get('spread_xauusd')})")

    def test_07_zmq_get_prop(self):
        res = zmq_client.get_prop()
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("peak_equity", res)
        self.assertIn("day_loss_pct", res)
        self.assertIn("day_status", res)
        self.assertIn("target_profit_goal", res)
        print(f"  [PASS] Live MT4 /prop OK (Day Status: {res.get('day_status')}, Peak DD: {res.get('peak_loss_pct')}%)")

    def test_08_zmq_get_report(self):
        res = zmq_client.get_report()
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("win_rate", res)
        self.assertIn("profit_factor", res)
        self.assertIn("gross_profit", res)
        print(f"  [PASS] Live MT4 /report OK (Trades: {res.get('total_trades')}, Win Rate: {res.get('win_rate')}%, Net: ${res.get('net_pl'):,.2f})")

    def test_09_zmq_apply_colors(self):
        res = zmq_client.apply_colors()
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("synced_count", res)
        print(f"  [PASS] Live MT4 /colors OK (Synced charts: {res.get('synced_count')})")

    def test_10_zmq_screenshot(self):
        res = zmq_client.get_screenshot(symbol="GBPUSD", timeframe="H1")
        self.assertEqual(res.get("status"), "ok")
        fn = res.get("filename")
        files_dir = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\80152BA938C72BA373B1EA4889AEE06F\MQL4\Files")
        shot_path = os.path.join(files_dir, fn)
        self.assertTrue(os.path.exists(shot_path), f"Screenshot file does not exist at {shot_path}")
        size = os.path.getsize(shot_path)
        self.assertGreater(size, 1000, f"Screenshot file too small ({size} bytes)")
        print(f"  [PASS] Live MT4 Chart Screenshot OK (Saved {fn}, {size:,} bytes)")

    def test_11_format_helpers(self):
        bar0 = handlers.format_progress_bar(0, 100)
        self.assertIn("0%", bar0)
        bar50 = handlers.format_progress_bar(50, 100)
        self.assertIn("50%", bar50)
        bar100 = handlers.format_progress_bar(100, 100)
        self.assertIn("100%", bar100)

        self.assertEqual(handlers.clean_symbol("gold"), "XAUUSD")
        self.assertEqual(handlers.clean_symbol(" crude "), "USOIL")
        self.assertEqual(handlers.clean_symbol("gbpusd"), "GBPUSD")
        print("  [PASS] Formatting helpers verified.")

    def test_12_account_manager(self):
        accs = account_manager.get_all_accounts()
        self.assertGreaterEqual(len(accs), 2)
        active = account_manager.get_active_account()
        self.assertIsNotNone(active)
        # Test switching
        account_manager.set_active_account("2")
        self.assertEqual(account_manager.get_active_account().id, "2")
        account_manager.set_active_account("1")
        self.assertEqual(account_manager.get_active_account().id, "1")
        print("  [PASS] Account Manager switcher and persistence verified.")

    def test_13_news_service(self):
        events = news_service.fetch_events()
        self.assertIsInstance(events, list)
        today = news_service.get_today_events()
        self.assertIsInstance(today, list)
        digest = news_service.format_news_digest(today[:3] if today else events[:3], "Test Digest")
        self.assertIn("Test Digest", digest)
        print(f"  [PASS] Economic News Service OK ({len(events)} events loaded)")

    def test_14_handler_rendering(self):
        import asyncio
        from telegram import Chat, User, Message, Update

        async def run_handlers():
            user = User(id=123456789, is_bot=False, first_name="Owner")
            chat = Chat(id=123456789, type="private")
            message = MagicMock()
            message.from_user = user
            message.chat = chat
            message.reply_text = AsyncMock()
            update = Update(update_id=1, message=message)
            context = MagicMock()
            context.bot.send_message = AsyncMock()

            # 1. Test cmd_help
            await handlers.cmd_help(update, context)
            message.reply_text.assert_called()
            help_call_args = message.reply_text.call_args[0][0]
            self.assertIn("INSTITUTIONAL COMMAND CENTER", help_call_args)
            self.assertIn("/boost", help_call_args)

            # 2. Test cmd_boost
            message.reply_text.reset_mock()
            await handlers.cmd_boost(update, context)
            message.reply_text.assert_called()
            boost_call_args = message.reply_text.call_args[0][0]
            self.assertIn("INSTITUTIONAL TURBO BOOST PANEL", boost_call_args)

            # 3. Test cmd_prop
            message.reply_text.reset_mock()
            await handlers.cmd_prop(update, context)
            message.reply_text.assert_called()
            prop_call_args = message.reply_text.call_args[0][0]
            self.assertIn("PROP-FIRM RISK GUARDIAN SCORECARD", prop_call_args)

            # 4. Test cmd_report
            message.reply_text.reset_mock()
            await handlers.cmd_report(update, context)
            message.reply_text.assert_called()
            report_call_args = message.reply_text.call_args[0][0]
            self.assertIn("24-HOUR PERFORMANCE SCORECARD", report_call_args)

            # 5. Test cmd_account
            message.reply_text.reset_mock()
            await handlers.cmd_account(update, context)
            message.reply_text.assert_called()
            acc_call_args = message.reply_text.call_args[0][0]
            self.assertIn("INVEST-AZ INSTITUTIONAL TERMINAL", acc_call_args)

        asyncio.run(run_handlers())
        print("  [PASS] Telegram Handler rendering verified (all panels rendered cleanly).")

if __name__ == "__main__":
    unittest.main(verbosity=2)
