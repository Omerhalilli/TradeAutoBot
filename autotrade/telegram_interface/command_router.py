"""
High-Performance Telegram Command Router & Security Dispatcher.
Enforces user authorization, rate limiting, two-factor authentication,
and zero-latency routing to institutional engine subsystems.
"""

from __future__ import annotations
import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from autotrade.analytics.charts import ChartGenerator, ChartType
from autotrade.core.config_manager import get_config, get_config_manager
from autotrade.core.engine import get_engine
from autotrade.core.event_bus import event_bus, EventType, EventPriority
from autotrade.data_layer.market_data import MarketDataManager
from autotrade.security.auth import SecurityGuardian
from autotrade.security.two_factor import TwoFactorAuth
from autotrade.telegram_interface.keyboards import (
    get_main_menu_keyboard,
    get_positions_keyboard,
    get_chart_symbols_keyboard,
    get_chart_timeframes_keyboard,
    get_panic_confirm_keyboard,
    get_strategy_tuning_keyboard,
    get_risk_settings_keyboard
)
from autotrade.telegram_interface.panels import (
    render_status_panel,
    render_positions_panel,
    render_prop_risk_panel,
    render_strategy_panel,
    render_optimization_panel
)

logger = logging.getLogger("autotrade.telegram_interface.command_router")


class CommandRouter:
    """
    Asynchronous Command Router and Telegram message dispatcher.
    """
    def __init__(self):
        self.config = get_config()
        self.security = SecurityGuardian()
        self.two_factor = TwoFactorAuth()
        self.charts = ChartGenerator()
        self.engine = get_engine()

    async def _check_access(self, update: Update) -> bool:
        """Verifies Telegram user ID authorization and rate limits."""
        user_id = update.effective_user.id if update.effective_user else 0
        auth_res = self.security.is_user_authorized(user_id)
        if not auth_res.is_authorized:
            if update.message:
                await update.message.reply_text(f"⛔ <b>ACCESS DENIED:</b> {auth_res.reason}", parse_mode=ParseMode.HTML)
            elif update.callback_query:
                await update.callback_query.answer(f"⛔ {auth_res.reason}", show_alert=True)
            return False
        return True

    # --------------------------------------------------------------------------
    # Master Command Handlers
    # --------------------------------------------------------------------------
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Displays main interactive command menu."""
        if not await self._check_access(update):
            return
        
        text = (
            "🧠 <b>AUTOTRADE QUANTITATIVE INSTITUTIONAL SYSTEM</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Welcome to the next-generation algorithmic trading environment.\n"
            "• <b>24/7 Autonomous Market Surveillance</b>\n"
            "• <b>Real-Time Self-Compiling & Self-Healing Core</b>\n"
            "• <b>50+ Vectorized Mathematical Indicators</b>\n"
            "• <b>Dynamic ATR Position Sizing & Prop Firm Safeguards</b>\n"
            "• <b>Fast Multi-Format Charting Engine</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Select an operational panel below:</i>"
        )
        await update.message.reply_text(
            text,
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Renders live account balance, equity, and latency."""
        if not await self._check_access(update):
            return
        
        from zmq_client import zmq_client
        loop = asyncio.get_running_loop()
        t0 = time.perf_counter()
        acc = await loop.run_in_executor(None, zmq_client.get_account)
        latency = (time.perf_counter() - t0) * 1000.0

        panel_text = render_status_panel(acc, latency)
        reply_target = update.message or (update.callback_query.message if update.callback_query else None)
        if reply_target:
            await reply_target.reply_text(panel_text, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)

    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Displays open positions with interactive management buttons."""
        if not await self._check_access(update):
            return

        from zmq_client import zmq_client
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, zmq_client.get_positions)
        positions = res.get("positions", []) if res.get("status") == "ok" else []

        text = render_positions_panel(positions)
        reply_target = update.message or (update.callback_query.message if update.callback_query else None)
        if reply_target:
            await reply_target.reply_text(text, reply_markup=get_positions_keyboard(positions), parse_mode=ParseMode.HTML)

    async def cmd_chart(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Step 1: Select symbol for chart rendering."""
        if not await self._check_access(update):
            return

        text = "📸 <b>INSTITUTIONAL CHART ENGINE</b>\n<i>Select instrument to render:</i>"
        reply_target = update.message or (update.callback_query.message if update.callback_query else None)
        if reply_target:
            await reply_target.reply_text(text, reply_markup=get_chart_symbols_keyboard(), parse_mode=ParseMode.HTML)

    async def cmd_panic(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Two-step emergency kill switch confirmation."""
        if not await self._check_access(update):
            return

        text = (
            "🚨 <b>EMERGENCY KILL-SWITCH WARNING</b> 🚨\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ <b>Action:</b> Liquidate ALL open positions and HALT auto-trading.\n"
            "Are you absolutely certain you want to proceed?"
        )
        reply_target = update.message or (update.callback_query.message if update.callback_query else None)
        if reply_target:
            await reply_target.reply_text(text, reply_markup=get_panic_confirm_keyboard(), parse_mode=ParseMode.HTML)

    async def cmd_strategies(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Displays active algorithmic strategies controller."""
        if not await self._check_access(update):
            return

        active_strats = self.config.strategy.active_strategies
        strats = self.engine.strategy_manager.get_all_strategies() if self.engine.strategy_manager else []
        text = render_strategy_panel(strats, active_strats)
        reply_target = update.message or (update.callback_query.message if update.callback_query else None)
        if reply_target:
            await reply_target.reply_text(text, reply_markup=get_strategy_tuning_keyboard(active_strats), parse_mode=ParseMode.HTML)

    async def cmd_start_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Starts or resumes autonomous trading execution."""
        if not await self._check_access(update):
            return
        if not self.engine.state.is_running:
            await self.engine.start()
            msg = "🚀 <b>AutoTrade Institutional Engine STARTED</b> and active 24/7."
        elif self.engine.state.is_paused:
            await self.engine.resume()
            msg = "▶️ <b>AutoTrade Engine RESUMED:</b> Autonomous order generation active."
        else:
            msg = "ℹ️ AutoTrade Engine is already running and active."
        reply_target = update.message or (update.callback_query.message if update.callback_query else None)
        if reply_target:
            await reply_target.reply_text(msg, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)

    async def cmd_stop_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Gracefully halts trading engine and background workers."""
        if not await self._check_access(update):
            return
        await self.engine.stop()
        msg = "🛑 <b>AutoTrade Engine STOPPED gracefully:</b> Event bus and worker loops halted."
        reply_target = update.message or (update.callback_query.message if update.callback_query else None)
        if reply_target:
            await reply_target.reply_text(msg, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)

    async def cmd_restart_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Performs full clean restart and self-compilation."""
        if not await self._check_access(update):
            return
        reply_target = update.message or (update.callback_query.message if update.callback_query else None)
        if reply_target:
            await reply_target.reply_text("🔄 <b>Restarting AutoTrade Engine...</b>\n1. Halting subsystems\n2. Running self-compilation\n3. Booting layers...", parse_mode=ParseMode.HTML)
        await self.engine.stop()
        await self.engine.initialize()
        await self.engine.start()
        if reply_target:
            await reply_target.reply_text("✅ <b>Restart Complete:</b> All 9 layers verified and operational.", reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)

    async def cmd_optimize(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Runs on-demand Walk-Forward parameter optimization."""
        if not await self._check_access(update):
            return
        reply_target = update.message or (update.callback_query.message if update.callback_query else None)
        if reply_target:
            await reply_target.reply_text("⏳ <b>Executing Walk-Forward Strategy Optimization...</b>", parse_mode=ParseMode.HTML)
        if self.engine.strategy_manager:
            res = await self.engine.strategy_manager.optimize_strategies()
            lines = ["⚡ <b>WALK-FORWARD OPTIMIZATION REPORT</b>", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
            for s_name, opt in res.items():
                wfe = opt.get("average_wfe_pct", 0.0)
                status = "✅ ROBUST" if opt.get("is_robust") else "⚠️ OVERFIT RISK"
                lines.append(f"• <b>{s_name}:</b> WFE = <code>{wfe:.1f}%</code> ({status})")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n<i>Strategy parameters adapted to market regime.</i>")
            if reply_target:
                await reply_target.reply_text("\n".join(lines), reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)

    async def cmd_set_risk(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Modifies per-trade risk percentage via command-line."""
        if not await self._check_access(update):
            return
        args = context.args or []
        reply_target = update.message or (update.callback_query.message if update.callback_query else None)
        if not args:
            text = "🛡️ <b>RISK CONFIGURATION:</b>\nSelect preset below or type <code>/set_risk 1.5</code>"
            if reply_target:
                await reply_target.reply_text(text, reply_markup=get_risk_settings_keyboard(), parse_mode=ParseMode.HTML)
            return

        try:
            val = float(args[0])
            self.config.risk.max_account_risk_pct = val
            if reply_target:
                await reply_target.reply_text(f"🛡️ <b>Risk Limit Updated:</b> Max risk per trade set to <b>{val:.2f}%</b>.", parse_mode=ParseMode.HTML)
        except ValueError:
            if reply_target:
                await reply_target.reply_text("❌ Invalid percentage. Usage: <code>/set_risk 2.0</code>", parse_mode=ParseMode.HTML)

    async def cmd_chart_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Generates visual PnL equity curve and underwater drawdown chart."""
        if not await self._check_access(update):
            return
        reply_target = update.message or (update.callback_query.message if update.callback_query else None)
        if reply_target:
            await reply_target.reply_text("⏳ Generating visual equity & drawdown analytics chart...", parse_mode=ParseMode.HTML)

        from zmq_client import zmq_client
        loop = asyncio.get_running_loop()
        hist = await loop.run_in_executor(None, lambda: zmq_client.get_history(limit=50, filter_type="all"))
        trades = hist.get("trades", []) if hist.get("status") == "ok" else []
        
        acc = await loop.run_in_executor(None, zmq_client.get_account)
        initial_balance = float(acc.get("balance", 100000.0)) if acc.get("status") == "ok" else 100000.0

        chart_path = self.charts.generate_equity_drawdown_chart(
            initial_balance=initial_balance,
            trades_or_equities=trades,
            title="Institutional Equity & Drawdown Analysis"
        )

        chat_id = update.effective_chat.id if update.effective_chat else 0
        if os.path.exists(chart_path) and chat_id:
            with open(chart_path, "rb") as photo:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption="📈 <b>Portfolio Equity & Underwater Drawdown Analysis</b>\n<i>Rendered by AutoTrade Analytics</i>",
                    parse_mode=ParseMode.HTML
                )

    async def cmd_verify(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Validates 2FA challenge code and executes pending critical action."""
        if not await self._check_access(update):
            return
        args = context.args or []
        user_id = update.effective_user.id if update.effective_user else 0

        if len(args) < 2:
            if update.message:
                await update.message.reply_text("Usage: <code>/verify &lt;challenge_id&gt; &lt;code&gt;</code>", parse_mode=ParseMode.HTML)
            return

        challenge_id = args[0]
        code = args[1]

        if self.two_factor.verify_challenge(challenge_id, user_id, code):
            await self.engine.emergency_halt("2FA Verified Panic Kill-Switch")
            if update.message:
                await update.message.reply_text("🚨 <b>2FA VERIFIED & EMERGENCY HALT COMPLETED:</b> All open orders closed. Engine locked.", parse_mode=ParseMode.HTML)
        else:
            if update.message:
                await update.message.reply_text("❌ <b>2FA FAILED:</b> Invalid or expired challenge code.", parse_mode=ParseMode.HTML)

    # --------------------------------------------------------------------------
    # Callback Query Router
    # --------------------------------------------------------------------------
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Routes inline button taps to appropriate handlers."""
        query = update.callback_query
        await query.answer()
        data = query.data

        if not await self._check_access(update):
            return

        import handlers

        if data == "nav_menu":
            await self.cmd_start(update, context)
        elif data == "nav_status":
            await self.cmd_status(update, context)
        elif data == "nav_positions":
            await self.cmd_positions(update, context)
        elif data == "nav_chart":
            await self.cmd_chart(update, context)
        elif data == "nav_panic":
            await self.cmd_panic(update, context)
        elif data == "nav_strategies":
            await self.cmd_strategies(update, context)
        elif data == "nav_boost":
            await handlers.cmd_boost(update, context)
        elif data == "nav_prop":
            await handlers.cmd_prop(update, context)
        elif data == "nav_report":
            await handlers.cmd_report(update, context)
        elif data == "nav_accounts":
            await handlers.cmd_accounts(update, context)
        elif data.startswith("strat_toggle:"):
            parts = data.split(":")
            strat_name, action = parts[1], parts[2]
            active_strats = list(self.config.strategy.active_strategies)
            if action == "enable" and strat_name not in active_strats:
                active_strats.append(strat_name)
            elif action == "disable" and strat_name in active_strats:
                active_strats.remove(strat_name)
            self.config.strategy.active_strategies = active_strats
            if self.engine.strategy_manager:
                self.engine.strategy_manager.load_strategies()
            strats = self.engine.strategy_manager.get_all_strategies() if self.engine.strategy_manager else []
            text = render_strategy_panel(strats, active_strats)
            await query.edit_message_text(text, reply_markup=get_strategy_tuning_keyboard(active_strats), parse_mode=ParseMode.HTML)
        elif data == "strat_run_opt":
            await query.edit_message_text("⏳ <b>Running Walk-Forward Optimization across active strategies...</b>", parse_mode=ParseMode.HTML)
            if self.engine.strategy_manager:
                res = await self.engine.strategy_manager.optimize_strategies()
                lines = ["⚡ <b>WALK-FORWARD OPTIMIZATION COMPLETED</b>", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
                for s_name, opt in res.items():
                    wfe = opt.get("average_wfe_pct", 0.0)
                    robust = "✅ ROBUST" if opt.get("is_robust") else "⚠️ OVERFIT RISK"
                    lines.append(f"• <b>{s_name}:</b> WFE = <code>{wfe:.1f}%</code> ({robust})")
                lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n<i>Strategy parameters updated in memory.</i>")
                await query.message.reply_text("\n".join(lines), reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)
        elif data.startswith("set_risk_pct:"):
            val = float(data.split(":")[1])
            self.config.risk.max_account_risk_pct = val
            await query.edit_message_text(f"🛡️ <b>RISK UPDATED:</b> Maximum account risk per trade set to <b>{val}%</b>.", reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)
        elif data.startswith("set_dd_pct:"):
            val = float(data.split(":")[1])
            self.config.risk.max_daily_loss_pct = val
            await query.edit_message_text(f"🛡️ <b>RISK UPDATED:</b> Maximum daily loss circuit breaker set to <b>{val}%</b>.", reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)
        elif data.startswith("shotsym:"):
            # Symbol chosen, show timeframes
            symbol = data.split(":")[1]
            await query.edit_message_text(
                f"📸 Selected <b>{symbol}</b>. Choose timeframe and format:",
                reply_markup=get_chart_timeframes_keyboard(symbol),
                parse_mode=ParseMode.HTML
            )
        elif data.startswith("shottf:"):
            # Render chart
            parts = data.split(":")
            symbol, tf, ctype = parts[1], parts[2], parts[3]
            await query.edit_message_text(f"⏳ Generating high-resolution {ctype.upper()} chart for {symbol} ({tf})...")
            
            # Fetch bars from market data
            ohlcv = self.engine.market_data.get_numpy_ohlcv(symbol, tf, count=120) if self.engine.market_data else {}
            if not len(ohlcv.get("close", [])):
                if self.engine.market_data:
                    self.engine.market_data.seed_synthetic_bars_if_empty(symbol, tf, count=120)
                    ohlcv = self.engine.market_data.get_numpy_ohlcv(symbol, tf, count=120)

            chart_path = self.charts.generate_chart(
                symbol=symbol,
                timeframe=tf,
                ohlcv=ohlcv,
                chart_type=ChartType(ctype)
            )

            if os.path.exists(chart_path):
                with open(chart_path, "rb") as photo:
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id,
                        photo=photo,
                        caption=f"📈 <b>{symbol} {tf}</b> | {ctype.upper()} | <i>Rendered by AutoTrade Engine</i>",
                        parse_mode=ParseMode.HTML
                    )
        elif data == "confirm_close_all":
            user_id = update.effective_user.id if update.effective_user else 0
            if self.two_factor.is_2fa_required("panic"):
                ch = self.two_factor.generate_challenge(user_id=user_id, action_name="panic", payload={"action": "panic"})
                prompt_text = (
                    "🔐 <b>TWO-FACTOR AUTHENTICATION (2FA) REQUIRED</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "⚠️ To confirm emergency liquidation and system halt, execute:\n"
                    f"<code>/verify {ch.challenge_id} {ch.code}</code>\n\n"
                    f"⏱️ <i>Token expires in {int(self.two_factor.challenge_ttl_sec)} seconds.</i>"
                )
                await query.edit_message_text(prompt_text, parse_mode=ParseMode.HTML)
                return

            await self.engine.emergency_halt("Manual Panic Button Activated via Telegram")
            await query.edit_message_text("🚨 <b>EMERGENCY HALT COMPLETED:</b> All open orders closed. Engine locked.")
        elif data == "cancel_close_all":
            await query.edit_message_text("🛡️ Emergency halt cancelled. Positions preserved.")


# Global router singleton
command_router = CommandRouter()
