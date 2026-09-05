"""
Comprehensive Automated Test Suite for MT4 Telegram Bridge.
Tests ZMQ endpoints, live MT4 telemetry, news service, account manager,
and handlers text formatting.
"""
import os
import sys

# Provide test fixture defaults if environment is unconfigured
if not os.environ.get("TELEGRAM_BOT_TOKEN"):
    os.environ["TELEGRAM_BOT_TOKEN"] = "123456789:dummy_token_for_ci_testing"
if not os.environ.get("ALLOWED_CHAT_IDS"):
    os.environ["ALLOWED_CHAT_IDS"] = "123456789"

import unittest
from unittest.mock import AsyncMock, MagicMock

from config import TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_IDS, ZMQ_SERVER_URL, MT4_FILES_DIR
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
        cls.mt4_online = (zmq_client.ping().get("status") == "ok")
        if cls.mt4_online:
            print("  [LIVE] MT4 ZeroMQ Bridge detected ONLINE. Running live socket tests.")
        else:
            print("  [OFFLINE] MT4 ZeroMQ Bridge is OFFLINE. Live socket tests will be skipped.")

    @classmethod
    def tearDownClass(cls):
        # Restore active account to live terminal account (ID 2 for real)
        try:
            res = zmq_client.get_account()
            if res and res.get("status") == "ok":
                account_manager.sync_with_live_terminal(res)
            else:
                account_manager.set_active_account("2")
        except Exception:
            account_manager.set_active_account("2")

    def test_01_config(self):
        self.assertTrue(bool(TELEGRAM_BOT_TOKEN), "Bot token must not be empty")
        self.assertGreater(len(ALLOWED_CHAT_IDS), 0, "Must have allowed chat IDs")
        self.assertTrue(ZMQ_SERVER_URL.startswith("tcp://"), "ZMQ URL must start with tcp://")
        print("  [PASS] Configuration validation verified.")

    def test_02_zmq_ping_and_latency(self):
        if not self.mt4_online:
            self.skipTest("MT4 offline")
        res = zmq_client.ping()
        self.assertEqual(res.get("status"), "ok", f"Ping failed: {res}")
        latency = zmq_client.ping_latency_ms()
        self.assertGreater(latency, 0.0, f"Latency must be positive, got {latency}")
        print(f"  [PASS] Live MT4 Ping OK (Roundtrip Latency: {latency:.2f} ms)")

    def test_03_zmq_get_account(self):
        if not self.mt4_online:
            self.skipTest("MT4 offline")
        res = zmq_client.get_account()
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("balance", res)
        self.assertIn("equity", res)
        print(f"  [PASS] Live MT4 Get Account OK (Login: {res.get('account_number')}, Equity: ${res.get('equity'):,.2f})")

    def test_04_zmq_get_positions(self):
        if not self.mt4_online:
            self.skipTest("MT4 offline")
        res = zmq_client.get_positions()
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("positions", res)
        print(f"  [PASS] Live MT4 Get Positions OK (Open Orders: {res.get('count')})")

    def test_05_zmq_get_history(self):
        if not self.mt4_online:
            self.skipTest("MT4 offline")
        res = zmq_client.get_history(limit=5)
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("trades", res)
        print(f"  [PASS] Live MT4 Get History OK (History Deals Count: {res.get('count')})")

    def test_06_zmq_get_boost(self):
        if not self.mt4_online:
            self.skipTest("MT4 offline")
        res = zmq_client.get_boost()
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("engine_hz"), 4)
        self.assertIn("spread_gbpusd", res)
        self.assertIn("spread_eurusd", res)
        self.assertIn("spread_xauusd", res)
        print(f"  [PASS] Live MT4 /boost OK (Spreads: GBP={res.get('spread_gbpusd')}, EUR={res.get('spread_eurusd')}, Gold={res.get('spread_xauusd')})")

    def test_07_zmq_get_prop(self):
        if not self.mt4_online:
            self.skipTest("MT4 offline")
        res = zmq_client.get_prop()
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("peak_equity", res)
        self.assertIn("day_loss_pct", res)
        self.assertIn("day_status", res)
        self.assertIn("target_profit_goal", res)
        print(f"  [PASS] Live MT4 /prop OK (Day Status: {res.get('day_status')}, Peak DD: {res.get('peak_loss_pct')}%)")

    def test_08_zmq_get_report(self):
        if not self.mt4_online:
            self.skipTest("MT4 offline")
        res = zmq_client.get_report()
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("win_rate", res)
        self.assertIn("profit_factor", res)
        self.assertIn("gross_profit", res)
        print(f"  [PASS] Live MT4 /report OK (Trades: {res.get('total_trades')}, Win Rate: {res.get('win_rate')}%, Net: ${res.get('net_pl'):,.2f})")

    def test_09_zmq_apply_colors(self):
        if not self.mt4_online:
            self.skipTest("MT4 offline")
        res = zmq_client.apply_colors()
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("synced_count", res)
        print(f"  [PASS] Live MT4 /colors OK (Synced charts: {res.get('synced_count')})")

    def test_10_zmq_screenshot(self):
        if not self.mt4_online:
            self.skipTest("MT4 offline")
        res = zmq_client.get_screenshot(symbol="GBPUSD", timeframe="H1")
        self.assertEqual(res.get("status"), "ok")
        fn = res.get("filename")
        files_dir = MT4_FILES_DIR
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
        account_manager.set_active_account("1")
        self.assertEqual(account_manager.get_active_account().id, "1")
        account_manager.set_active_account("2")
        self.assertEqual(account_manager.get_active_account().id, "2")
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
        from unittest.mock import patch

        async def run_handlers():
            test_chat_id = ALLOWED_CHAT_IDS[0] if ALLOWED_CHAT_IDS else 123456789
            user = User(id=test_chat_id, is_bot=False, first_name="Owner")
            chat = Chat(id=test_chat_id, type="private")
            message = MagicMock()
            message.from_user = user
            message.chat = chat
            message.reply_text = AsyncMock()
            update = Update(update_id=1, message=message)
            context = MagicMock()
            context.bot.send_message = AsyncMock()

            # Helper to extract text from mock call
            def get_text(mock_call):
                if mock_call.call_args[0]:
                    return mock_call.call_args[0][0]
                return mock_call.call_args.kwargs.get("text", "")

            # 1. Test cmd_help
            await handlers.cmd_help(update, context)
            message.reply_text.assert_called()
            help_call_args = get_text(message.reply_text)
            self.assertIn("INSTITUTIONAL COMMAND CENTER", help_call_args)
            self.assertIn("/boost", help_call_args)

            # 2. Test cmd_boost
            message.reply_text.reset_mock()
            with patch.object(zmq_client, "ping_latency_ms", return_value=1.5), \
                 patch.object(zmq_client, "get_boost", return_value={"status": "ok", "balance": 10000.0, "equity": 10150.0, "ping_ms": 1.2, "autotrade_enabled": True, "open_positions": 1, "daily_pnl": 50.0, "spreads": {"GBPUSD": 1.2, "EURUSD": 0.8, "XAUUSD": 15.0}}):
                await handlers.cmd_boost(update, context)
                message.reply_text.assert_called()
                boost_call_args = get_text(message.reply_text)
                self.assertIn("INSTITUTIONAL TURBO BOOST PANEL", boost_call_args)

            # 3. Test cmd_prop
            message.reply_text.reset_mock()
            with patch.object(zmq_client, "get_prop", return_value={"status": "ok", "balance": 10000.0, "equity": 10250.0, "starting_balance": 10000.0, "daily_loss": -50.0, "max_daily_loss": 500.0, "max_total_drawdown": 1000.0, "profit_target": 1000.0, "trading_days": 3, "min_trading_days": 5, "is_passed": False, "is_failed": False, "currency": "USD"}):
                await handlers.cmd_prop(update, context)
                message.reply_text.assert_called()
                prop_call_args = get_text(message.reply_text)
                self.assertIn("PROP-FIRM RISK GUARDIAN SCORECARD", prop_call_args)

            # 4. Test cmd_report
            message.reply_text.reset_mock()
            with patch.object(zmq_client, "get_report", return_value={"status": "ok", "trades": [], "total_trades": 0, "profit_trades": 0, "loss_trades": 0, "total_profit": 0.0, "total_loss": 0.0, "net_profit": 0.0, "win_rate": 0.0, "profit_factor": 0.0, "best_trade": 0.0, "worst_trade": 0.0, "best_symbol": "N/A", "worst_symbol": "N/A", "balance": 10000.0, "equity": 10000.0, "currency": "USD"}):
                await handlers.cmd_report(update, context)
                message.reply_text.assert_called()
                report_call_args = get_text(message.reply_text)
                self.assertIn("24-HOUR PERFORMANCE SCORECARD", report_call_args)

            # 5. Test cmd_account
            message.reply_text.reset_mock()
            with patch.object(zmq_client, "get_account", return_value={"status": "ok", "account_number": 1234567, "name": "Invest-AZ Demo", "server": "InvestAZ-Demo", "company": "InvestAZ", "currency": "USD", "balance": 10000.0, "equity": 10150.0, "margin": 200.0, "free_margin": 9950.0, "margin_level": 5075.0, "leverage": 100, "positions_count": 1, "total_floating_pl": 150.0}):
                await handlers.cmd_account(update, context)
                message.reply_text.assert_called()
                acc_call_args = get_text(message.reply_text)
                self.assertIn("INVEST-AZ INSTITUTIONAL TERMINAL", acc_call_args)

            # 6. Test cmd_positions
            message.reply_text.reset_mock()
            with patch.object(zmq_client, "get_positions", return_value={"status": "ok", "positions": [], "total_floating_pl": 0.0, "count": 0}):
                await handlers.cmd_positions(update, context)
                message.reply_text.assert_called()

            # 7. Test cmd_closeall
            message.reply_text.reset_mock()
            await handlers.cmd_closeall(update, context)
            message.reply_text.assert_called()
            self.assertIn("EMERGENCY KILL-SWITCH CONFIRMATION", get_text(message.reply_text))

        asyncio.run(run_handlers())
        print("  [PASS] Telegram Handler rendering verified (all panels rendered cleanly).")

    def test_15_cmd_breakeven_and_trailing(self):
        import asyncio
        from telegram import Chat, User, Update
        from unittest.mock import patch

        async def run():
            test_chat_id = ALLOWED_CHAT_IDS[0] if ALLOWED_CHAT_IDS else 123456789
            user = User(id=test_chat_id, is_bot=False, first_name="Owner")
            chat = Chat(id=test_chat_id, type="private")
            message = MagicMock()
            message.from_user = user
            message.chat = chat
            message.reply_text = AsyncMock()
            update = Update(update_id=10, message=message)
            context = MagicMock()
            context.args = ["GBPUSD", "1"]

            def get_text(mock_call):
                if mock_call.call_args[0]:
                    return mock_call.call_args[0][0]
                return mock_call.call_args.kwargs.get("text", "")

            # Mock zmq_client.set_breakeven
            with patch.object(zmq_client, "set_breakeven", return_value={"status": "ok", "modified_count": 1, "skipped_count": 0, "lock_pips": 1}):
                await handlers.cmd_breakeven(update, context)
                message.reply_text.assert_called()
                self.assertIn("BREAK-EVEN PROTECTION SYNCHRONIZED", get_text(message.reply_text))

            # Mock zmq_client.set_trailing
            message.reply_text.reset_mock()
            context.args = ["GBPUSD", "20"]
            with patch.object(zmq_client, "set_trailing", return_value={"status": "ok", "modified_count": 1, "skipped_count": 0, "trail_pips": 20}):
                await handlers.cmd_trailing(update, context)
                message.reply_text.assert_called()
                self.assertIn("TRAILING STOP SYNCHRONIZED", get_text(message.reply_text))

        asyncio.run(run())
        print("  [PASS] /be and /trailing command logic and formatting verified.")

    def test_16_callback_query_safety(self):
        """Verifies that none of the handlers crash when invoked via CallbackQuery where update.message is None."""
        import asyncio
        from telegram import Chat, User, Update, CallbackQuery
        from unittest.mock import patch

        async def run_callbacks():
            test_chat_id = ALLOWED_CHAT_IDS[0] if ALLOWED_CHAT_IDS else 123456789
            user = User(id=test_chat_id, is_bot=False, first_name="Owner")
            chat = Chat(id=test_chat_id, type="private")
            query = MagicMock(spec=CallbackQuery)
            query.from_user = user
            query.message = MagicMock()
            query.message.chat = chat
            query.edit_message_text = AsyncMock()
            query.answer = AsyncMock()

            # update has callback_query, but update.message is None!
            update = Update(update_id=20, callback_query=query)
            self.assertIsNone(update.message)
            context = MagicMock()
            context.bot.send_message = AsyncMock()

            def get_query_text(mock_call):
                if mock_call.call_args and mock_call.call_args[0]:
                    return mock_call.call_args[0][0]
                if mock_call.call_args:
                    return mock_call.call_args.kwargs.get("text", "")
                return ""

            mock_acc = {"status": "ok", "balance": 10000.0, "equity": 10000.0, "currency": "USD", "positions_count": 0, "total_floating_pl": 0.0}
            mock_pos = {"status": "ok", "positions": [], "total_floating_pl": 0.0, "count": 0}
            mock_prop = {"status": "ok", "balance": 10000.0, "equity": 10000.0, "starting_balance": 10000.0, "daily_loss": 0.0, "max_daily_loss": 500.0, "max_total_drawdown": 1000.0, "profit_target": 1000.0, "trading_days": 1, "min_trading_days": 5, "currency": "USD"}
            mock_rep = {"status": "ok", "trades": [], "total_trades": 0, "profit_trades": 0, "loss_trades": 0, "total_profit": 0.0, "total_loss": 0.0, "net_profit": 0.0, "balance": 10000.0, "equity": 10000.0, "currency": "USD"}
            mock_boost = {"status": "ok", "balance": 10000.0, "equity": 10000.0, "ping_ms": 1.5, "autotrade_enabled": True, "open_positions": 0, "daily_pnl": 0.0, "spreads": {"GBPUSD": 1.0}}

            with patch.object(zmq_client, "get_account", return_value=mock_acc), \
                 patch.object(zmq_client, "get_positions", return_value=mock_pos), \
                 patch.object(zmq_client, "get_prop", return_value=mock_prop), \
                 patch.object(zmq_client, "get_report", return_value=mock_rep), \
                 patch.object(zmq_client, "get_boost", return_value=mock_boost), \
                 patch.object(zmq_client, "ping_latency_ms", return_value=1.0), \
                 patch.object(zmq_client, "set_breakeven", return_value={"status": "ok", "modified_count": 0, "skipped_count": 0, "lock_pips": 1.0}), \
                 patch.object(zmq_client, "set_trailing", return_value={"status": "ok", "modified_count": 0, "skipped_count": 0, "trail_pips": 20.0}), \
                 patch.object(zmq_client, "get_history", return_value={"status": "ok", "trades": [], "total_net_pl": 0.0, "count": 0}):

                # 1. Navigation callbacks
                nav_targets = ["nav_status", "nav_pos", "nav_prop", "nav_report", "nav_boost", "nav_shot", "nav_panic"]
                for target in nav_targets:
                    query.data = target
                    query.edit_message_text.reset_mock()
                    await handlers.cb_nav_action(update, context)
                    # Ensure no exception occurred and edit_message_text was called
                    self.assertTrue(query.edit_message_text.called or query.answer.called)

                # 2. History filter callbacks
                query.data = "hist_filter:today"
                await handlers.cb_history_filter(update, context)

                # 3. News filter callbacks
                query.data = "news_filter:week"
                await handlers.cb_news_filter(update, context)

                # 4. Emergency Kill-Switch Cancel
                query.data = "cancel_close_all"
                await handlers.callback_closeall(update, context)
                self.assertIn("cancelled", get_query_text(query.edit_message_text))

        asyncio.run(run_callbacks())
        print("  [PASS] CallbackQuery safety verified (Zero NoneType reply_text crashes).")

    def test_17_ea_trade_callbacks(self):
        """Verifies that EA trade notification callbacks (/close_123, /half_123, /be_123) execute correctly."""
        import asyncio
        from telegram import Chat, User, Update, CallbackQuery
        from unittest.mock import patch

        async def run_ea_callbacks():
            test_chat_id = ALLOWED_CHAT_IDS[0] if ALLOWED_CHAT_IDS else 123456789
            user = User(id=test_chat_id, is_bot=False, first_name="Owner")
            chat = Chat(id=test_chat_id, type="private")
            query = MagicMock(spec=CallbackQuery)
            query.from_user = user
            query.message = MagicMock()
            query.message.chat = chat
            query.edit_message_text = AsyncMock()
            query.answer = AsyncMock()
            update = Update(update_id=30, callback_query=query)
            context = MagicMock()

            # 1. /close_12345
            query.data = "/close_12345"
            with patch.object(zmq_client, "close_symbol", return_value={"status": "ok", "closed_count": 1, "realized_pl": 25.50}):
                await handlers.cb_ea_close(update, context)
                self.assertIn("POSITION LIQUIDATED", query.edit_message_text.call_args[0][0])

            # 2. /half_12345
            query.data = "/half_12345"
            with patch.object(zmq_client, "close_half", return_value={"status": "ok", "closed_lots": 0.05, "remaining_lots": 0.05, "realized_pl": 12.00}):
                await handlers.cb_ea_half(update, context)
                self.assertIn("50% PARTIAL CLOSE", query.edit_message_text.call_args[0][0])

            # 3. /be_12345
            query.data = "/be_12345"
            with patch.object(zmq_client, "set_breakeven", return_value={"status": "ok", "modified_count": 1, "lock_pips": 1}):
                await handlers.cb_ea_be(update, context)
                self.assertIn("BREAK-EVEN SYNCHRONIZED", query.edit_message_text.call_args[0][0])

        asyncio.run(run_ea_callbacks())
        print("  [PASS] EA trade notification interactive button callbacks verified.")

    def test_18_bot_app_initialization(self):
        """Verifies that bot.create_application builds cleanly with all registered handlers."""
        from bot import create_application
        from telegram.ext import CommandHandler, CallbackQueryHandler
        app = create_application()
        self.assertIsNotNone(app)
        handlers_list = app.handlers.get(0, [])
        handler_count = len(handlers_list)
        self.assertGreaterEqual(handler_count, 22, f"Expected >= 22 handlers, got {handler_count}")
        
        # Verify essential commands are registered
        command_names = set()
        for h in handlers_list:
            if isinstance(h, CommandHandler):
                for cmd in h.commands:
                    command_names.add(cmd)
        
        for required_cmd in ["be", "breakeven", "trailing", "trail", "reset_risk", "panic", "boost", "prop"]:
            self.assertIn(required_cmd, command_names, f"Required command /{required_cmd} not found in registered bot handlers")

        print(f"  [PASS] Bot ApplicationBuilder validated ({handler_count} handlers registered, {len(command_names)} commands).")

    def test_19_reset_safeguards(self):
        """Verifies zmq_client.reset_safeguards and cmd_reset_safeguards logic."""
        import asyncio
        from telegram import Chat, User, Update, CallbackQuery
        from unittest.mock import patch

        if self.mt4_online:
            res = zmq_client.reset_safeguards()
            self.assertEqual(res.get("status"), "ok")
            self.assertIn("equity", res)
            print(f"  [PASS] Live MT4 Reset Safeguards OK (Account: #{res.get('account')}, Calibrated Equity: ${res.get('equity'):,.2f})")

        async def run_reset_cmd():
            test_chat_id = ALLOWED_CHAT_IDS[0] if ALLOWED_CHAT_IDS else 123456789
            user = User(id=test_chat_id, is_bot=False, first_name="Owner")
            chat = Chat(id=test_chat_id, type="private")
            query = MagicMock(spec=CallbackQuery)
            query.from_user = user
            query.message = MagicMock()
            query.message.chat = chat
            query.edit_message_text = AsyncMock()
            query.answer = AsyncMock()
            update = Update(update_id=40, callback_query=query)
            context = MagicMock()

            mock_res = {"status": "ok", "action": "RESET_SAFEGUARDS", "account": "213173", "equity": 91.91}
            with patch.object(zmq_client, "reset_safeguards", return_value=mock_res):
                await handlers.cb_reset_safeguards(update, context)
                self.assertIn("PROP SAFEGUARDS RECALIBRATED", query.edit_message_text.call_args[0][0])
                self.assertIn("213173", query.edit_message_text.call_args[0][0])

        asyncio.run(run_reset_cmd())
        print("  [PASS] /reset_risk command & callback verification completed.")

    def test_20_parse_trade_args(self):
        """Tests parsing of various user formats for buy/sell/trade commands."""
        p1 = handlers._parse_trade_args(["GBPUSD", "0.01"], default_action="BUY")
        self.assertEqual(p1["action"], "BUY")
        self.assertEqual(p1["symbol"], "GBPUSD")
        self.assertEqual(p1["lots"], 0.01)

        p2 = handlers._parse_trade_args(["0.05", "EURUSD", "sl=1.0800", "tp=1.0950"], default_action="SELL")
        self.assertEqual(p2["action"], "SELL")
        self.assertEqual(p2["symbol"], "EURUSD")
        self.assertEqual(p2["lots"], 0.05)
        self.assertEqual(p2["sl"], 1.0800)
        self.assertEqual(p2["tp"], 1.0950)

        p3 = handlers._parse_trade_args(["buy", "GOLD", "0.02"])
        self.assertEqual(p3["action"], "BUY")
        self.assertEqual(p3["symbol"], "XAUUSD")
        self.assertEqual(p3["lots"], 0.02)

        p4 = handlers._parse_trade_args([])
        self.assertEqual(p4["action"], "BUY")
        self.assertEqual(p4["symbol"], "GBPUSD")
        self.assertEqual(p4["lots"], 0.01)
        print("  [PASS] Trade argument parsing (_parse_trade_args) verified.")

    def test_21_cmd_buy_sell_trade_handlers(self):
        """Verifies cmd_buy, cmd_sell, and cmd_trade execution with mocks."""
        import asyncio
        from telegram import Chat, User, Update, Message
        from unittest.mock import patch

        async def run_cmds():
            test_chat_id = ALLOWED_CHAT_IDS[0] if ALLOWED_CHAT_IDS else 123456789
            user = User(id=test_chat_id, is_bot=False, first_name="Trader")
            chat = Chat(id=test_chat_id, type="private")

            msg = MagicMock(spec=Message)
            msg.from_user = user
            msg.chat = chat
            msg.reply_text = AsyncMock()
            update = Update(update_id=50, message=msg)
            context = MagicMock()
            context.args = []

            await handlers.cmd_buy(update, context)
            self.assertIn("QUICK BUY EXECUTION WIZARD", msg.reply_text.call_args[0][0])

            await handlers.cmd_sell(update, context)
            self.assertIn("QUICK SELL EXECUTION WIZARD", msg.reply_text.call_args[0][0])

            context.args = ["GBPUSD", "0.02"]
            status_msg = MagicMock(spec=Message)
            status_msg.edit_text = AsyncMock()
            msg.reply_text = AsyncMock(return_value=status_msg)

            mock_res = {"status": "ok", "action": "OPEN_ORDER", "ticket": 987654, "price": 1.25000, "lots": 0.02}
            with patch.object(zmq_client, "open_order", return_value=mock_res):
                await handlers.cmd_buy(update, context)
                self.assertIn("ORDER EXECUTED ON MT4 TERMINAL", status_msg.edit_text.call_args[0][0])
                self.assertIn("#987654", status_msg.edit_text.call_args[0][0])

        asyncio.run(run_cmds())
        print("  [PASS] /buy, /sell, /trade command handlers verified.")

    def test_22_quick_trade_callback(self):
        """Verifies 1-tap trade button callback handler (cb_quick_trade)."""
        import asyncio
        from telegram import Chat, User, Update, CallbackQuery, Message
        from unittest.mock import patch

        async def run_cb():
            test_chat_id = ALLOWED_CHAT_IDS[0] if ALLOWED_CHAT_IDS else 123456789
            user = User(id=test_chat_id, is_bot=False, first_name="Trader")
            chat = Chat(id=test_chat_id, type="private")
            query = MagicMock(spec=CallbackQuery)
            query.from_user = user
            query.data = "trade:buy:EURUSD:0.01"
            msg = MagicMock(spec=Message)
            msg.from_user = user
            msg.chat = chat
            msg.reply_text = AsyncMock()
            query.message = msg
            query.answer = AsyncMock()
            update = Update(update_id=51, callback_query=query)
            context = MagicMock()

            mock_res = {"status": "ok", "action": "OPEN_ORDER", "ticket": 123456, "price": 1.08500, "lots": 0.01}
            with patch.object(zmq_client, "open_order", return_value=mock_res):
                await handlers.cb_quick_trade(update, context)
                query.answer.assert_called()

        asyncio.run(run_cb())
        print("  [PASS] Quick trade callback query verified.")

    def test_23_slash_actions(self):
        """Verifies text messages for slash commands /close_123, /half_123, /be_123."""
        import asyncio
        from telegram import Chat, User, Update, Message
        from unittest.mock import patch

        async def run_slash():
            test_chat_id = ALLOWED_CHAT_IDS[0] if ALLOWED_CHAT_IDS else 123456789
            user = User(id=test_chat_id, is_bot=False, first_name="Trader")
            chat = Chat(id=test_chat_id, type="private")
            context = MagicMock()

            # Test /close_12345
            msg = MagicMock(spec=Message)
            msg.from_user = user
            msg.chat = chat
            msg.text = "/close_12345"
            msg.reply_text = AsyncMock()
            update = Update(update_id=52, message=msg)
            mock_res = {"status": "ok", "closed_count": 1, "realized_pl": 25.50}
            with patch.object(zmq_client, "close_symbol", return_value=mock_res):
                await handlers.handle_slash_action(update, context)
                self.assertIn("POSITION LIQUIDATED", msg.reply_text.call_args[0][0])
                self.assertIn("#12345", msg.reply_text.call_args[0][0])

            # Test /half_12345
            msg.text = "/half_12345"
            mock_half = {"status": "ok", "closed_lots": 0.05, "remaining_lots": 0.05, "realized_pl": 12.0}
            with patch.object(zmq_client, "close_half", return_value=mock_half):
                await handlers.handle_slash_action(update, context)
                self.assertIn("PARTIAL CLOSE COMPLETED", msg.reply_text.call_args[0][0])

            # Test /be_12345
            msg.text = "/be_12345"
            mock_be = {"status": "ok", "modified_count": 1}
            with patch.object(zmq_client, "set_breakeven", return_value=mock_be):
                await handlers.handle_slash_action(update, context)
                self.assertIn("BREAK-EVEN SYNCHRONIZED", msg.reply_text.call_args[0][0])

        asyncio.run(run_slash())
        print("  [PASS] Slash command text action handler verified.")

    def test_24_live_open_order_zmq(self):
        """Verifies live ZeroMQ OPEN_ORDER dispatch to running MT4 terminal."""
        if not self.mt4_online:
            self.skipTest("MT4 offline")

        res = zmq_client.open_order(symbol="GBPUSD", cmd="BUY", lots=0.01)
        self.assertIn("status", res)
        # On weekends, error 132 is returned with human-readable description
        if res.get("status") == "error":
            self.assertEqual(res.get("error_code"), 132)
            self.assertIn("Market is closed", res.get("message"))
            print(f"  [PASS] Live MT4 OPEN_ORDER verified (Returned Error 132 with clear text: '{res.get('message')}')")
        else:
            self.assertEqual(res.get("status"), "ok")
            print(f"  [PASS] Live MT4 OPEN_ORDER executed successfully (Ticket: #{res.get('ticket')})")

if __name__ == "__main__":
    unittest.main(verbosity=2)

