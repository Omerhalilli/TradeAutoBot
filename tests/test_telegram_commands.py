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


if __name__ == "__main__":
    unittest.main()
