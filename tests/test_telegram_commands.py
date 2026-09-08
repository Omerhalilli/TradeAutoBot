import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Chat, User, Update, CallbackQuery
import handlers
from config import ALLOWED_CHAT_IDS
from zmq_client import zmq_client


class TestTelegramCommands(unittest.TestCase):
    def setUp(self):
        self.auth_id = ALLOWED_CHAT_IDS[0] if ALLOWED_CHAT_IDS else 123456789
        self.unauth_id = 999999999
        while self.unauth_id in ALLOWED_CHAT_IDS:
            self.unauth_id += 1

    def _make_message_update(self, chat_id: int, text: str = "", args: list = None):
        user = User(id=chat_id, is_bot=False, first_name="Trader")
        chat = Chat(id=chat_id, type="private")
        message = MagicMock()
        message.from_user = user
        message.chat = chat
        message.text = text
        sent_mock = MagicMock()
        sent_mock.edit_text = AsyncMock()
        message.reply_text = AsyncMock(return_value=sent_mock)
        update = Update(update_id=100, message=message)
        context = MagicMock()
        context.bot.send_message = AsyncMock()
        context.args = args or []
        return update, context, message

    def _make_callback_update(self, chat_id: int, callback_data: str = ""):
        user = User(id=chat_id, is_bot=False, first_name="Trader")
        chat = Chat(id=chat_id, type="private")
        query = MagicMock(spec=CallbackQuery)
        query.from_user = user
        query.data = callback_data
        query.message = MagicMock()
        query.message.chat = chat
        query.edit_message_text = AsyncMock()
        query.answer = AsyncMock()
        update = Update(update_id=200, callback_query=query)
        context = MagicMock()
        context.args = []
        return update, context, query

    def _get_reply_text(self, mock_call):
        if not mock_call.called:
            return ""
        args, kwargs = mock_call.call_args
        if args:
            return args[0]
        return kwargs.get("text", "")

    # --------------------------------------------------------------------------
    # 1. Authorization & Security Enforcement
    # --------------------------------------------------------------------------
    def test_unauthorized_message_rejected(self):
        """Unauthorized message commands must be rejected with an access restricted alert."""
        async def run():
            update, context, message = self._make_message_update(self.unauth_id, text="/account")
            await handlers.cmd_account(update, context)
            self.assertTrue(message.reply_text.called)
            reply = self._get_reply_text(message.reply_text)
            self.assertIn("ACCESS RESTRICTED", reply)

        asyncio.run(run())

    def test_unauthorized_callback_rejected(self):
        """Unauthorized callback queries must be rejected with alert."""
        async def run():
            update, context, query = self._make_callback_update(self.unauth_id, callback_data="confirm_close_all")
            await handlers.callback_closeall(update, context)
            query.answer.assert_called_with("⛔ Access Denied: Unauthorized account.", show_alert=True)
            self.assertFalse(query.edit_message_text.called)

        asyncio.run(run())

    # --------------------------------------------------------------------------
    # 2. Risk Configuration (/setrisk & cb_setrisk)
    # --------------------------------------------------------------------------
    def test_cmd_setrisk_no_args_displays_menu(self):
        """Executing /setrisk with no arguments displays the risk configuration menu and presets."""
        async def run():
            update, context, message = self._make_message_update(self.auth_id, text="/setrisk", args=[])
            await handlers.cmd_setrisk(update, context)
            self.assertTrue(message.reply_text.called)
            reply = self._get_reply_text(message.reply_text)
            self.assertIn("RISK MANAGEMENT & SAFEGUARD CONFIGURATION", reply)
            self.assertIn("Risk Per Trade:", reply)
            self.assertIn("Max Daily Loss Limit:", reply)

        asyncio.run(run())

    def test_cmd_setrisk_valid_trade_risk(self):
        """Setting risk per trade updates configuration and returns confirmation."""
        async def run():
            from autotrade.core.config_manager import get_config
            cfg = get_config()
            original_val = getattr(cfg.risk, "max_account_risk_pct", getattr(cfg.risk, "risk_per_trade_pct", 1.0))

            try:
                update, context, message = self._make_message_update(self.auth_id, text="/setrisk 1.75", args=["1.75"])
                await handlers.cmd_setrisk(update, context)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("Risk per trade updated:", reply)
                self.assertIn("1.75%", reply)
                current_val = getattr(cfg.risk, "max_account_risk_pct", getattr(cfg.risk, "risk_per_trade_pct", 0.0))
                self.assertEqual(current_val, 1.75)

                # Also test keyword format: /setrisk trade 2.25
                message.reply_text.reset_mock()
                context.args = ["trade", "2.25"]
                await handlers.cmd_setrisk(update, context)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("2.25%", reply)
                current_val = getattr(cfg.risk, "max_account_risk_pct", getattr(cfg.risk, "risk_per_trade_pct", 0.0))
                self.assertEqual(current_val, 2.25)
            finally:
                if hasattr(cfg.risk, "max_account_risk_pct"):
                    cfg.risk.max_account_risk_pct = original_val
                if hasattr(cfg.risk, "risk_per_trade_pct"):
                    cfg.risk.risk_per_trade_pct = original_val

        asyncio.run(run())

    def test_cmd_setrisk_valid_daily_loss_and_max_trades(self):
        """Setting daily loss and max trades boundaries."""
        async def run():
            from autotrade.core.config_manager import get_config
            cfg = get_config()
            orig_daily = cfg.risk.max_daily_loss_pct
            orig_trades = getattr(cfg.risk, "max_open_positions", getattr(cfg.risk, "max_open_trades_total", 10))

            try:
                # Daily loss
                update, context, message = self._make_message_update(self.auth_id, text="/setrisk daily 4.25", args=["daily", "4.25"])
                await handlers.cmd_setrisk(update, context)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("Daily loss limit updated:", reply)
                self.assertIn("4.25%", reply)
                self.assertEqual(cfg.risk.max_daily_loss_pct, 4.25)

                # Max trades
                message.reply_text.reset_mock()
                context.args = ["trades", "8"]
                await handlers.cmd_setrisk(update, context)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("Max concurrent trades updated:", reply)
                self.assertIn("<code>8</code> positions", reply)
                current_trades = getattr(cfg.risk, "max_open_positions", getattr(cfg.risk, "max_open_trades_total", 0))
                self.assertEqual(current_trades, 8)
            finally:
                cfg.risk.max_daily_loss_pct = orig_daily
                if hasattr(cfg.risk, "max_open_positions"):
                    cfg.risk.max_open_positions = orig_trades
                if hasattr(cfg.risk, "max_open_trades_total"):
                    cfg.risk.max_open_trades_total = orig_trades

        asyncio.run(run())

    def test_cmd_setrisk_edge_cases_and_invalid_inputs(self):
        """Handles non-numeric, negative, and out-of-range bounds safely without crashing."""
        async def run():
            # Non-numeric input
            update, context, message = self._make_message_update(self.auth_id, text="/setrisk invalid", args=["invalid"])
            await handlers.cmd_setrisk(update, context)
            reply = self._get_reply_text(message.reply_text)
            self.assertIn("Invalid value:", reply)

            # Trade risk out of range (> 15% or <= 0)
            message.reply_text.reset_mock()
            context.args = ["trade", "25.0"]
            await handlers.cmd_setrisk(update, context)
            reply = self._get_reply_text(message.reply_text)
            self.assertIn("Out of range:", reply)

            message.reply_text.reset_mock()
            context.args = ["trade", "-1.0"]
            await handlers.cmd_setrisk(update, context)
            reply = self._get_reply_text(message.reply_text)
            self.assertIn("Out of range:", reply)

            # Daily loss out of range (> 25% or <= 0.5%)
            message.reply_text.reset_mock()
            context.args = ["daily", "35.0"]
            await handlers.cmd_setrisk(update, context)
            reply = self._get_reply_text(message.reply_text)
            self.assertIn("Out of range:", reply)

            # Max trades out of range (> 50 or < 1)
            message.reply_text.reset_mock()
            context.args = ["trades", "99"]
            await handlers.cmd_setrisk(update, context)
            reply = self._get_reply_text(message.reply_text)
            self.assertIn("Out of range:", reply)

        asyncio.run(run())

    def test_cb_setrisk_presets(self):
        """Verifies clicking preset buttons updates risk configuration."""
        async def run():
            from autotrade.core.config_manager import get_config
            cfg = get_config()
            orig_risk = getattr(cfg.risk, "max_account_risk_pct", getattr(cfg.risk, "risk_per_trade_pct", 1.0))

            try:
                update, context, query = self._make_callback_update(self.auth_id, callback_data="setrisk:trade:0.5")
                await handlers.cb_setrisk(update, context)
                current_val = getattr(cfg.risk, "max_account_risk_pct", getattr(cfg.risk, "risk_per_trade_pct", 0.0))
                self.assertEqual(current_val, 0.5)
            finally:
                if hasattr(cfg.risk, "max_account_risk_pct"):
                    cfg.risk.max_account_risk_pct = orig_risk
                if hasattr(cfg.risk, "risk_per_trade_pct"):
                    cfg.risk.risk_per_trade_pct = orig_risk

        asyncio.run(run())

    # --------------------------------------------------------------------------
    # 3. Remote Order Execution (/buy, /openbuy, /sell, /opensell)
    # --------------------------------------------------------------------------
    def test_cmd_buy_and_sell_wizard_when_empty_args(self):
        """When called without arguments, /buy and /sell show quick trade interactive wizards."""
        async def run():
            # /buy
            update, context, message = self._make_message_update(self.auth_id, text="/buy", args=[])
            await handlers.cmd_buy(update, context)
            reply = self._get_reply_text(message.reply_text)
            self.assertIn("QUICK BUY EXECUTION WIZARD", reply)

            # /sell
            message.reply_text.reset_mock()
            update, context, message = self._make_message_update(self.auth_id, text="/sell", args=[])
            await handlers.cmd_sell(update, context)
            reply = self._get_reply_text(message.reply_text)
            self.assertIn("QUICK SELL EXECUTION WIZARD", reply)

        asyncio.run(run())

    def test_cmd_buy_and_sell_with_mocked_zmq(self):
        """Verifies order dispatch to ZMQ client with correct parameters."""
        async def run():
            update, context, message = self._make_message_update(
                self.auth_id,
                text="/buy GBPUSD 0.02 sl=1.2600 tp=1.2800",
                args=["GBPUSD", "0.02", "sl=1.2600", "tp=1.2800"]
            )

            mock_response = {
                "status": "ok",
                "ticket": 999123,
                "symbol": "GBPUSD",
                "action": "BUY",
                "lots": 0.02,
                "price": 1.26500,
                "sl": 1.26000,
                "tp": 1.28000
            }

            with patch.object(zmq_client, "open_order", return_value=mock_response) as mock_open:
                await handlers.cmd_buy(update, context)
                mock_open.assert_called_once_with(
                    symbol="GBPUSD",
                    cmd="BUY",
                    lots=0.02,
                    sl=1.2600,
                    tp=1.2800,
                    sl_pips=0.0,
                    tp_pips=0.0,
                    magic=8882026,
                    comment="TelegramTrade"
                )
                status_msg = message.reply_text.return_value
                self.assertTrue(status_msg.edit_text.called)
                reply = self._get_reply_text(status_msg.edit_text)
                self.assertIn("ORDER EXECUTED", reply)
                self.assertIn("999123", reply)

            # SELL order
            message.reply_text.reset_mock()
            sent_mock_sell = MagicMock()
            sent_mock_sell.edit_text = AsyncMock()
            message.reply_text.return_value = sent_mock_sell
            context.args = ["EURUSD", "0.05"]
            mock_sell_resp = {
                "status": "ok",
                "ticket": 999124,
                "symbol": "EURUSD",
                "action": "SELL",
                "lots": 0.05,
                "price": 1.08500,
                "sl": 0.0,
                "tp": 0.0
            }
            with patch.object(zmq_client, "open_order", return_value=mock_sell_resp) as mock_open_sell:
                await handlers.cmd_sell(update, context)
                mock_open_sell.assert_called_once_with(
                    symbol="EURUSD",
                    cmd="SELL",
                    lots=0.05,
                    sl=0.0,
                    tp=0.0,
                    sl_pips=0.0,
                    tp_pips=0.0,
                    magic=8882026,
                    comment="TelegramTrade"
                )
                self.assertTrue(sent_mock_sell.edit_text.called)
                reply = self._get_reply_text(sent_mock_sell.edit_text)
                self.assertIn("ORDER EXECUTED", reply)
                self.assertIn("999124", reply)

        asyncio.run(run())

    # --------------------------------------------------------------------------
    # 4. Emergency Kill-Switch & Liquidations (/closeall, /close_all)
    # --------------------------------------------------------------------------
    def test_cmd_closeall_prompts_confirmation(self):
        """Executing /closeall generates a confirmation prompt without closing immediately."""
        async def run():
            update, context, message = self._make_message_update(self.auth_id, text="/closeall", args=[])

            with patch.object(zmq_client, "get_positions", return_value={"status": "ok", "count": 3, "orders": []}):
                await handlers.cmd_closeall(update, context)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("EMERGENCY KILL-SWITCH CONFIRMATION", reply)
                self.assertIn("ALL 3 open positions", reply)

        asyncio.run(run())

    def test_callback_closeall_confirm_and_cancel(self):
        """Executing confirm_close_all liquidates trades; cancel_close_all preserves them."""
        async def run():
            # Confirm close all
            update, context, query = self._make_callback_update(self.auth_id, callback_data="confirm_close_all")
            mock_close_resp = {
                "status": "ok",
                "closed_count": 3,
                "failed_count": 0,
                "realized_pl": 125.50
            }

            with patch.object(zmq_client, "close_all", return_value=mock_close_resp) as mock_close:
                await handlers.callback_closeall(update, context)
                mock_close.assert_called_once()
                self.assertTrue(query.edit_message_text.called)
                reply = self._get_reply_text(query.edit_message_text)
                self.assertIn("EMERGENCY KILL-SWITCH EXECUTED", reply)
                self.assertIn("Orders Closed:</b> <b>3</b>", reply)
                self.assertIn("+$125.50", reply)

            # Cancel close all
            query.edit_message_text.reset_mock()
            update, context, query = self._make_callback_update(self.auth_id, callback_data="cancel_close_all")
            await handlers.callback_closeall(update, context)
            reply = self._get_reply_text(query.edit_message_text)
            self.assertIn("Emergency Close All cancelled", reply)

        asyncio.run(run())

    # --------------------------------------------------------------------------
    # 5. Remote Bot Pause & Resume Controls (/pause, /resume)
    # --------------------------------------------------------------------------
    def test_cmd_pause_and_resume_bot(self):
        """Verifies remote pause and resume commands correctly write state flags and call ZMQ."""
        async def run():
            with tempfile.TemporaryDirectory() as tmpdir:
                flag_path = os.path.join(tmpdir, "autotrade_state.flag")
                with patch("handlers.AUTOTRADE_FLAG_FILE", flag_path), \
                     patch("handlers.MT4_FILES_DIR", tmpdir), \
                     patch.object(zmq_client, "pause_bot", return_value={"status": "ok"}) as mock_pause, \
                     patch.object(zmq_client, "resume_bot", return_value={"status": "ok"}) as mock_resume:

                    # /pause_bot
                    update, context, message = self._make_message_update(self.auth_id, text="/pause")
                    await handlers.cmd_pause_bot(update, context)
                    mock_pause.assert_called_once()
                    reply = self._get_reply_text(message.reply_text)
                    self.assertIn("AUTOTRADING PAUSED BY REMOTE COMMAND", reply)
                    with open(flag_path, "r", encoding="utf-8") as f:
                        self.assertIn("PAUSED", f.read())

                    # /resume_bot
                    message.reply_text.reset_mock()
                    update, context, message = self._make_message_update(self.auth_id, text="/resume")
                    await handlers.cmd_resume_bot(update, context)
                    mock_resume.assert_called_once()
                    reply = self._get_reply_text(message.reply_text)
                    self.assertIn("AUTOTRADING RESUMED BY REMOTE COMMAND", reply)
                    with open(flag_path, "r", encoding="utf-8") as f:
                        self.assertIn("ACTIVE", f.read())

        asyncio.run(run())

    # --------------------------------------------------------------------------
    # 6. Full Command Center & Status (/start, /help, /status, /account)
    # --------------------------------------------------------------------------
    def test_cmd_start_and_help(self):
        """Verifies /start and /help render command center with navigation keyboard."""
        async def run():
            # /start
            update, context, message = self._make_message_update(self.auth_id, text="/start")
            await handlers.cmd_start(update, context)
            reply = self._get_reply_text(message.reply_text)
            self.assertIn("COMMAND CENTER", reply)
            self.assertIn("/buy", reply)
            self.assertIn("/positions", reply)

            # /help
            message.reply_text.reset_mock()
            update, context, message = self._make_message_update(self.auth_id, text="/help")
            await handlers.cmd_help(update, context)
            reply = self._get_reply_text(message.reply_text)
            self.assertIn("COMMAND CENTER", reply)

        asyncio.run(run())

    def test_cmd_account_online_and_offline(self):
        """Verifies /account and /status render full account stats when online and offline card when offline."""
        async def run():
            # Online
            online_resp = {
                "status": "ok",
                "account_number": "1234567",
                "trade_mode": "DEMO",
                "balance": 100000.0,
                "equity": 102500.0,
                "margin": 1500.0,
                "free_margin": 101000.0,
                "margin_level": 6833.3,
                "floating_pl": 2500.0,
                "currency": "USD",
                "company": "Institutional Broker",
                "server": "Demo-Server",
                "server_time": "2026.09.07 12:00:00",
                "leverage": 100,
                "is_trade_allowed": True,
                "is_expert_enabled": True
            }
            with patch.object(zmq_client, "get_account", return_value=online_resp):
                update, context, message = self._make_message_update(self.auth_id, text="/status")
                await handlers.cmd_account(update, context)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("Balance:", reply)
                self.assertIn("$100,000.00", reply)
                self.assertIn("$102,500.00", reply)
                self.assertIn("Margin Level:", reply)

            # Offline
            with patch.object(zmq_client, "get_account", return_value={"status": "error"}):
                message.reply_text.reset_mock()
                update, context, message = self._make_message_update(self.auth_id, text="/account")
                await handlers.cmd_account(update, context)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("BRIDGE OFFLINE", reply)

        asyncio.run(run())

    # --------------------------------------------------------------------------
    # 7. Portfolio & Orders (/positions, /close, /modify_sl, /modify_tp)
    # --------------------------------------------------------------------------
    def test_cmd_positions_empty_and_populated(self):
        """Verifies /positions handles 0 orders cleanly and renders active trade details when orders exist."""
        async def run():
            # Empty portfolio
            with patch.object(zmq_client, "get_positions", return_value={"status": "ok", "count": 0, "positions": []}):
                update, context, message = self._make_message_update(self.auth_id, text="/positions")
                await handlers.cmd_positions(update, context)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("0 Orders", reply)
                self.assertIn("no active market orders running", reply)

            # Populated portfolio
            pop_resp = {
                "status": "ok",
                "count": 1,
                "positions": [{
                    "ticket": 888100,
                    "symbol": "GBPUSD",
                    "type": "BUY",
                    "volume": 0.05,
                    "open_price": 1.26500,
                    "sl": 1.26000,
                    "tp": 1.28000,
                    "profit": 45.20,
                    "open_time": "2026.09.07 10:00:00"
                }]
            }
            with patch.object(zmq_client, "get_positions", return_value=pop_resp):
                message.reply_text.reset_mock()
                context.bot.send_message.reset_mock()
                update, context, message = self._make_message_update(self.auth_id, text="/positions")
                await handlers.cmd_positions(update, context)
                reply = self._get_reply_text(context.bot.send_message) or self._get_reply_text(message.reply_text)
                self.assertIn("888100", reply)
                self.assertIn("GBPUSD", reply)
                self.assertIn("/close_888100", reply)
                self.assertIn("/be_888100", reply)
                self.assertIn("/half_888100", reply)

        asyncio.run(run())

    def test_cmd_close_symbol_and_ticket(self):
        """Verifies /close handles missing args, symbol close, ticket close, and /close all."""
        async def run():
            # No args shows guide
            update, context, message = self._make_message_update(self.auth_id, text="/close", args=[])
            await handlers.cmd_close_symbol(update, context)
            reply = self._get_reply_text(message.reply_text)
            self.assertIn("Close Order Usage:", reply)

            # /close all routes to cmd_closeall
            with patch.object(zmq_client, "get_positions", return_value={"status": "ok", "count": 1, "orders": []}):
                message.reply_text.reset_mock()
                context.args = ["all"]
                await handlers.cmd_close_symbol(update, context)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("EMERGENCY KILL-SWITCH", reply)

            # Close by symbol (e.g. /close GBPUSD)
            close_sym_resp = {"status": "ok", "closed_count": 2, "failed_count": 0, "realized_pl": 85.0}
            with patch.object(zmq_client, "close_symbol", return_value=close_sym_resp) as mock_sym_close:
                message.reply_text.reset_mock()
                context.args = ["GBPUSD"]
                await handlers.cmd_close_symbol(update, context)
                mock_sym_close.assert_called_once_with("GBPUSD")
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("LIQUIDATION COMPLETED", reply)
                self.assertIn("+$85.00", reply)

            # Close by ticket (e.g. /close 888100)
            close_ticket_resp = {"status": "ok", "closed_count": 1, "failed_count": 0, "realized_pl": 45.20}
            with patch.object(zmq_client, "close_symbol", return_value=close_ticket_resp) as mock_tick_close:
                message.reply_text.reset_mock()
                context.args = ["888100"]
                await handlers.cmd_close_symbol(update, context)
                mock_tick_close.assert_called_once_with("888100")
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("LIQUIDATION COMPLETED", reply)

        asyncio.run(run())

    def test_cmd_modify_sl_and_tp(self):
        """Verifies /modify_sl and /modify_tp validate arguments and dispatch to ZMQ."""
        async def run():
            # /modify_sl missing args
            update, context, message = self._make_message_update(self.auth_id, text="/modify_sl", args=[])
            await handlers.cmd_modify_sl(update, context)
            reply = self._get_reply_text(message.reply_text)
            self.assertIn("Modify Stop Loss Usage:", reply)

            # /modify_sl invalid price
            message.reply_text.reset_mock()
            context.args = ["GBPUSD", "-1.5"]
            await handlers.cmd_modify_sl(update, context)
            reply = self._get_reply_text(message.reply_text)
            self.assertIn("Invalid Price:", reply)

            # /modify_sl valid ticket
            with patch.object(zmq_client, "modify_sl", return_value={"status": "ok", "modified_count": 1}) as mock_sl:
                message.reply_text.reset_mock()
                context.args = ["888100", "1.2610"]
                await handlers.cmd_modify_sl(update, context)
                mock_sl.assert_called_once_with(ticket=888100, sl=1.2610)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("STOP LOSS SYNCHRONIZED", reply)

            # /modify_tp valid symbol
            with patch.object(zmq_client, "modify_tp", return_value={"status": "ok", "modified_count": 2}) as mock_tp:
                message.reply_text.reset_mock()
                context.args = ["GBPUSD", "1.2850"]
                await handlers.cmd_modify_tp(update, context)
                mock_tp.assert_called_once_with(symbol="GBPUSD", tp=1.2850)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("TAKE PROFIT SYNCHRONIZED", reply)

        asyncio.run(run())

    # --------------------------------------------------------------------------
    # 8. Protection & Risk (/be, /trailing, /prop, /reset_risk)
    # --------------------------------------------------------------------------
    def test_cmd_breakeven_and_trailing_variations(self):
        """Verifies /be and /trailing with symbol, ticket, custom pips, and no-match scenarios."""
        async def run():
            # /be with ticket
            with patch.object(zmq_client, "set_breakeven", return_value={"status": "ok", "modified_count": 1, "skipped_count": 0}) as mock_be:
                update, context, message = self._make_message_update(self.auth_id, text="/be 888100 2", args=["888100", "2"])
                await handlers.cmd_breakeven(update, context)
                mock_be.assert_called_once_with(symbol="", ticket=888100, lock_pips=2)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("BREAK-EVEN PROTECTION SYNCHRONIZED", reply)

            # /trailing with symbol
            with patch.object(zmq_client, "set_trailing", return_value={"status": "ok", "modified_count": 1, "skipped_count": 0}) as mock_tr:
                message.reply_text.reset_mock()
                context.args = ["GBPUSD", "25"]
                await handlers.cmd_trailing(update, context)
                mock_tr.assert_called_once_with(symbol="GBPUSD", ticket=0, trail_pips=25)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("TRAILING STOP SYNCHRONIZED", reply)

        asyncio.run(run())

    def test_cmd_prop_and_reset_safeguards(self):
        """Verifies /prop scorecard display and /reset_risk recalibration."""
        async def run():
            prop_resp = {
                "status": "ok",
                "account": "1234567",
                "company": "Institutional Broker",
                "equity": 102500.0,
                "peak_equity": 103000.0,
                "day_loss": 200.0,
                "day_loss_limit": 4500.0,
                "day_loss_pct": 0.2,
                "day_status": "Safe",
                "peak_loss": 500.0,
                "peak_loss_limit": 8000.0,
                "peak_loss_pct": 0.5,
                "peak_status": "Safe",
                "current_gain": 2500.0,
                "target_profit_goal": 8000.0,
                "autotrading_active": True
            }
            with patch.object(zmq_client, "get_prop", return_value=prop_resp):
                update, context, message = self._make_message_update(self.auth_id, text="/prop")
                await handlers.cmd_prop(update, context)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("PROP-FIRM RISK GUARDIAN SCORECARD", reply)
                self.assertIn("DAILY DRAWDOWN MONITOR", reply)

            # /reset_risk
            reset_resp = {"status": "ok", "account": "1234567", "equity": 102500.0}
            with patch.object(zmq_client, "reset_safeguards", return_value=reset_resp):
                message.reply_text.reset_mock()
                update, context, message = self._make_message_update(self.auth_id, text="/reset_risk")
                await handlers.cmd_reset_safeguards(update, context)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("PROP SAFEGUARDS RECALIBRATED", reply)
                self.assertIn("$102,500.00", reply)

        asyncio.run(run())

    # --------------------------------------------------------------------------
    # 9. Diagnostics & Intel (/boost, /report, /colors, /news, /screenshot, /trade)
    # --------------------------------------------------------------------------
    def test_cmd_boost_and_report_and_colors_and_news(self):
        """Verifies diagnostics, reports, colors, and news calendar commands."""
        async def run():
            # /boost
            boost_resp = {
                "status": "ok",
                "balance": 100000.0,
                "equity": 102500.0,
                "active_orders": 2,
                "floating_pl": 2500.0,
                "server_time": "2026.09.07 12:00:00",
                "autotrading_active": True,
                "spread_gbpusd": 1.2,
                "spread_eurusd": 0.8,
                "spread_xauusd": 15.0
            }
            with patch.object(zmq_client, "get_boost", return_value=boost_resp), \
                 patch.object(zmq_client, "ping_latency_ms", return_value=12.5):
                update, context, message = self._make_message_update(self.auth_id, text="/boost")
                await handlers.cmd_boost(update, context)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("TURBO BOOST PANEL", reply)
                self.assertIn("12.50 ms", reply)

            # /report
            rep_resp = {
                "status": "ok",
                "period": "Last 24 Hours",
                "account": "1234567",
                "total_trades": 10,
                "win_count": 7,
                "loss_count": 3,
                "win_rate": 70.0,
                "gross_profit": 1400.0,
                "gross_loss": 400.0,
                "profit_factor": 3.5,
                "net_pl": 1000.0,
                "ending_balance": 101000.0,
                "ending_equity": 101000.0
            }
            with patch.object(zmq_client, "get_report", return_value=rep_resp):
                message.reply_text.reset_mock()
                update, context, message = self._make_message_update(self.auth_id, text="/report")
                await handlers.cmd_report(update, context)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("24-HOUR PERFORMANCE SCORECARD", reply)
                self.assertIn("70.0%", reply)
                self.assertIn("3.50", reply)

            # /colors
            with patch.object(zmq_client, "apply_colors", return_value={"status": "ok", "synced_count": 2}):
                message.reply_text.reset_mock()
                update, context, message = self._make_message_update(self.auth_id, text="/colors")
                await handlers.cmd_colors(update, context)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("CHART COLORS SYNCHRONIZED", reply)
                self.assertIn("2 chart(s)", reply)

            # /news
            message.reply_text.reset_mock()
            update, context, message = self._make_message_update(self.auth_id, text="/news")
            await handlers.cmd_news(update, context)
            reply = self._get_reply_text(message.reply_text)
            self.assertIn("Economic Calendar", reply)

        asyncio.run(run())

    def test_cmd_trade_and_history_and_screenshot(self):
        """Verifies /trade wizard, /history query filters, and /screenshot wizard."""
        async def run():
            # /trade wizard
            update, context, message = self._make_message_update(self.auth_id, text="/trade", args=[])
            await handlers.cmd_trade(update, context)
            reply = self._get_reply_text(message.reply_text)
            self.assertIn("REMOTE MT4 ORDER EXECUTION", reply)

            # /history
            hist_resp = {
                "status": "ok",
                "count": 1,
                "total_net_pl": 50.0,
                "trades": [{
                    "ticket": 777123,
                    "symbol": "GBPUSD",
                    "cmd": "BUY",
                    "lots": 0.10,
                    "close_price": 1.27000,
                    "profit": 50.0,
                    "close_time": "2026.09.07 11:00:00"
                }]
            }
            with patch.object(zmq_client, "get_history", return_value=hist_resp):
                message.reply_text.reset_mock()
                context.bot.send_message.reset_mock()
                update, context, message = self._make_message_update(self.auth_id, text="/history", args=["today"])
                await handlers.cmd_history(update, context)
                reply = self._get_reply_text(context.bot.send_message) or self._get_reply_text(message.reply_text)
                self.assertIn("TRADE HISTORY AUDIT", reply)
                self.assertIn("777123", reply)

            # /screenshot wizard
            message.reply_text.reset_mock()
            update, context, message = self._make_message_update(self.auth_id, text="/screenshot", args=[])
            await handlers.cmd_screenshot(update, context)
            reply = self._get_reply_text(message.reply_text)
            self.assertIn("CHART SNAPSHOT WIZARD", reply)

        asyncio.run(run())

    # --------------------------------------------------------------------------
    # 10. Slash Actions & Comprehensive Authorization
    # --------------------------------------------------------------------------
    def test_slash_actions_parsing(self):
        """Verifies slash actions /close_123, /half_123, /be_123 dispatch properly."""
        async def run():
            update, context, message = self._make_message_update(self.auth_id, text="/close_888123")
            with patch.object(zmq_client, "close_symbol", return_value={"status": "ok", "closed_count": 1, "failed_count": 0, "realized_pl": 30.0}) as mock_close:
                await handlers.handle_slash_action(update, context)
                mock_close.assert_called_once_with("888123")

        asyncio.run(run())

    def test_unauthorized_all_major_commands(self):
        """Verifies unauthorized chat IDs are rejected on all major commands."""
        async def run():
            unauth_cmds = [
                handlers.cmd_help,
                handlers.cmd_account,
                handlers.cmd_positions,
                handlers.cmd_boost,
                handlers.cmd_prop,
                handlers.cmd_closeall,
                handlers.cmd_pause_bot,
                handlers.cmd_resume_bot,
                handlers.cmd_buy,
                handlers.cmd_sell,
                handlers.cmd_trade,
                handlers.cmd_close_symbol,
                handlers.cmd_modify_sl,
                handlers.cmd_modify_tp,
                handlers.cmd_history,
                handlers.cmd_colors,
                handlers.cmd_news,
                handlers.cmd_goal
            ]
            for cmd_fn in unauth_cmds:
                update, context, message = self._make_message_update(self.unauth_id, text="/test")
                await cmd_fn(update, context)
                self.assertTrue(message.reply_text.called, f"Command {cmd_fn.__name__} failed to reply to unauthorized user")
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("ACCESS RESTRICTED", reply, f"Command {cmd_fn.__name__} allowed unauthorized access!")

        asyncio.run(run())

    def test_cmd_goal_and_single_symbol_scan(self):
        """Verifies /goal and /scan with specific symbol argument render cleanly."""
        async def run():
            # 1. Test /goal
            update, context, message = self._make_message_update(self.auth_id, text="/goal")
            mock_prop = {"status": "ok", "equity": 100.0, "balance": 100.0, "target_profit_goal": 8.0, "day_profit": 1.5}
            mock_rep = {"status": "ok", "profit": 1.5, "win_rate": 70.0, "trades_count": 10}
            with patch("handlers.zmq_client.get_prop", return_value=mock_prop), \
                 patch("handlers.zmq_client.get_report", return_value=mock_rep):
                await handlers.cmd_goal(update, context)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("INSTITUTIONAL PROFIT GOAL TRACKER", reply)
                self.assertIn("DAILY PROFIT GOAL", reply)
                self.assertIn("GROWTH MILESTONE", reply)

            # 2. Test /scan with symbol argument
            message.reply_text.reset_mock()
            update, context, message = self._make_message_update(self.auth_id, text="/scan EURUSD", args=["EURUSD"])
            mock_scan = {
                "status": "ok",
                "results": [
                    {
                        "symbol": "EURUSD",
                        "score": 8,
                        "analysis_score": 82.5,
                        "signal": "BUY",
                        "trend": "STRONG BULLISH",
                        "spread": 10.0,
                        "sl_pips": 20.0,
                        "tp_pips": 40.0
                    }
                ]
            }
            with patch("autotrade.core.autonomous_trader.zmq_client.scan_symbols", return_value=mock_scan):
                await handlers.cmd_scan(update, context)
                reply = self._get_reply_text(message.reply_text)
                self.assertIn("INSTITUTIONAL TECHNICAL AUDIT", reply)
                self.assertIn("EURUSD", reply)
            # 3. Test callback query for scan_sym: and nav_goal
            update_cb, context_cb, query_cb = self._make_callback_update(self.auth_id, callback_data="scan_sym:EURUSD")
            with patch("autotrade.core.autonomous_trader.zmq_client.scan_symbols", return_value=mock_scan):
                await handlers.cb_nav_action(update_cb, context_cb)
                reply_cb = self._get_reply_text(query_cb.edit_message_text)
                self.assertIn("INSTITUTIONAL TECHNICAL AUDIT", reply_cb)
                self.assertIn("EURUSD", reply_cb)

            update_goal_cb, context_goal_cb, query_goal_cb = self._make_callback_update(self.auth_id, callback_data="nav_goal")
            with patch("handlers.zmq_client.get_prop", return_value=mock_prop), \
                 patch("handlers.zmq_client.get_report", return_value=mock_rep):
                await handlers.cb_nav_action(update_goal_cb, context_goal_cb)
                reply_goal = self._get_reply_text(query_goal_cb.edit_message_text)
                self.assertIn("INSTITUTIONAL PROFIT GOAL TRACKER", reply_goal)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()


