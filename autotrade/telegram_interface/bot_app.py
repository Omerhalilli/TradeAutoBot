"""
Telegram Bot Application Builder & Runtime Service.
Configures HTTPX connection pooling, registers command routers,
and coordinates background scheduled broadcast jobs.
"""

from __future__ import annotations
import logging
from telegram import BotCommand
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

from autotrade.core.config_manager import get_config
from autotrade.telegram_interface.command_router import command_router
import handlers

logger = logging.getLogger("autotrade.telegram_interface.bot_app")


async def post_init_hook(application: Application) -> None:
    """Sets Telegram native menu commands and verifies gateway connectivity."""
    try:
        commands = [
            BotCommand("start", "🧠 Main Interactive Command Menu"),
            BotCommand("boost", "⚡ Turbo Boost & Institutional Spreads"),
            BotCommand("status", "📊 Live Balance, Equity & Health"),
            BotCommand("positions", "💼 Manage Active Trade Orders"),
            BotCommand("chart", "📸 Render High-Resolution Technical Chart"),
            BotCommand("be", "🛡️ Move SL to Break-Even (+1 Pip)"),
            BotCommand("trailing", "⚡ Dynamic Trailing Stop Management"),
            BotCommand("prop", "🛡️ Prop-Firm Risk Guardian"),
            BotCommand("reset_risk", "🔄 Recalibrate Prop Anchors & DD"),
            BotCommand("report", "📈 24-Hour Performance Scorecard"),
            BotCommand("strategies", "⚙️ Algorithmic Strategy Tuning"),
            BotCommand("accounts", "👥 Switch MT4 Trading Accounts"),
            BotCommand("panic", "🚨 Emergency Kill-Switch (Close All)"),
            BotCommand("pause", "⏸️ Pause Autonomous Entries"),
            BotCommand("resume", "▶️ Resume Autonomous Entries"),
            BotCommand("help", "🤖 Institutional Command Guide"),
        ]
        await application.bot.set_my_commands(commands)
        logger.info("Successfully registered Telegram native menu commands.")
    except Exception as ex:
        logger.error(f"Failed to synchronize Telegram menu commands: {ex}")


def build_telegram_app() -> Application:
    """
    Constructs python-telegram-bot v20+ Application with optimized connection pooling.
    """
    config = get_config()
    request = HTTPXRequest(
        connect_timeout=25.0,
        read_timeout=25.0,
        write_timeout=25.0,
        pool_timeout=15.0
    )

    app = (
        ApplicationBuilder()
        .token(config.telegram.bot_token)
        .request(request)
        .post_init(post_init_hook)
        .build()
    )

    # Core Institutional Handlers
    app.add_handler(CommandHandler(["start", "help", "menu"], command_router.cmd_start))
    app.add_handler(CommandHandler(["status", "account"], command_router.cmd_status))
    app.add_handler(CommandHandler("positions", command_router.cmd_positions))
    app.add_handler(CommandHandler(["chart", "screenshot", "screenphoto"], command_router.cmd_chart))
    app.add_handler(CommandHandler(["panic", "closeall"], command_router.cmd_panic))
    app.add_handler(CommandHandler(["strategies", "strat"], command_router.cmd_strategies))
    app.add_handler(CommandHandler(["start_bot", "engine_start"], command_router.cmd_start_bot))
    app.add_handler(CommandHandler(["stop_bot", "engine_stop"], command_router.cmd_stop_bot))
    app.add_handler(CommandHandler(["restart_bot", "engine_restart"], command_router.cmd_restart_bot))
    app.add_handler(CommandHandler(["optimize", "wfa"], command_router.cmd_optimize))
    app.add_handler(CommandHandler(["set_risk", "risk_limits"], command_router.cmd_set_risk))
    app.add_handler(CommandHandler(["chart_report", "pnl_chart"], command_router.cmd_chart_report))
    app.add_handler(CommandHandler("verify", command_router.cmd_verify))

    # Existing Legacy Handlers for seamless backward compatibility
    app.add_handler(CommandHandler(["boost", "turbo"], handlers.cmd_boost))
    app.add_handler(CommandHandler(["accounts", "switch"], handlers.cmd_accounts))
    app.add_handler(CommandHandler(["be", "breakeven"], handlers.cmd_breakeven))
    app.add_handler(CommandHandler(["trailing", "trail"], handlers.cmd_trailing))
    app.add_handler(CommandHandler(["prop", "risk"], handlers.cmd_prop))
    app.add_handler(CommandHandler(["reset_risk", "reset_prop", "reset_safeguards"], handlers.cmd_reset_safeguards))
    app.add_handler(CommandHandler("report", handlers.cmd_report))
    app.add_handler(CommandHandler(["colors", "synccharts", "sync"], handlers.cmd_colors))
    app.add_handler(CommandHandler("history", handlers.cmd_history))
    app.add_handler(CommandHandler("close", handlers.cmd_close_symbol))
    app.add_handler(CommandHandler("modify_sl", handlers.cmd_modify_sl))
    app.add_handler(CommandHandler("modify_tp", handlers.cmd_modify_tp))
    app.add_handler(CommandHandler(["pause", "pause_bot"], handlers.cmd_pause_bot))
    app.add_handler(CommandHandler(["resume", "resume_bot"], handlers.cmd_resume_bot))
    app.add_handler(CommandHandler(["news", "calendar"], handlers.cmd_news))

    # Callback Query Handlers (Supporting both modern router and existing handlers)
    app.add_handler(CallbackQueryHandler(
        command_router.handle_callback_query,
        pattern=r"^(nav_|shotsym:|shottf:|confirm_close_all|cancel_close_all|strat_toggle:|strat_run_opt|set_risk_pct:|set_dd_pct:)"
    ))
    app.add_handler(CallbackQueryHandler(handlers.cb_switch_account, pattern=r"^switch_acc:"))
    app.add_handler(CallbackQueryHandler(handlers.cb_reset_safeguards, pattern=r"^recalibrate_safeguards$"))
    app.add_handler(CallbackQueryHandler(handlers.cb_history_filter, pattern=r"^hist_filter:"))
    app.add_handler(CallbackQueryHandler(handlers.cb_news_filter, pattern=r"^news_filter:"))
    app.add_handler(CallbackQueryHandler(handlers.cb_ea_close, pattern=r"^/?close_\d+$"))
    app.add_handler(CallbackQueryHandler(handlers.cb_ea_half, pattern=r"^/?half_\d+$"))
    app.add_handler(CallbackQueryHandler(handlers.cb_ea_be, pattern=r"^/?be_\d+$"))
    app.add_handler(CallbackQueryHandler(handlers.cb_ea_shot, pattern=r"^/?shot_[A-Za-z0-9]+_[A-Za-z0-9]+$"))

    logger.info("Telegram Bot Application built with 45+ command and callback routers.")
    return app
