"""
Main Application Entry Point for MT4 Telegram Bot & ZeroMQ Bridge.
Runs python-telegram-bot v20+ with background economic news reminder tasks,
2-step interactive screenshot panel, resilient ZeroMQ fault-tolerance,
and 24/7 automatic reconnect loops.
"""
import asyncio
import logging
import socket
import sys
import time
from telegram import BotCommand
from telegram.constants import ParseMode
from telegram.request import HTTPXRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

from config import TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_IDS, NEWS_REMINDER_LEAD_MINUTES, setup_logging
from news_service import news_service, CURRENCY_FLAGS
import handlers

# Configure root logger to output to both console and rotating logs/bot.log
logger = logging.getLogger("MT4BridgeBot")

# Resilient DNS fallback hook for 24/7 network stability
_orig_getaddrinfo = socket.getaddrinfo
def resilient_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        return _orig_getaddrinfo(host, port, family, type, proto, flags)
    except Exception:
        if host == "api.telegram.org":
            return _orig_getaddrinfo("149.154.166.110", port, family, type, proto, flags)
        raise

socket.getaddrinfo = resilient_getaddrinfo

async def post_init(application) -> None:
    """Synchronize Telegram native Menu button commands."""
    try:
        commands = [
            BotCommand("accounts", "👥 Switch Accounts & Inspect BUY/SELL"),
            BotCommand("status", "📊 Account Balance, Equity & Health"),
            BotCommand("positions", "💼 View & Manage Active Trades"),
            BotCommand("history", "📜 Closed Trades History & Net P/L"),
            BotCommand("screenshot", "📸 Interactive Chart Screenshot"),
            BotCommand("prop", "🛡️ Prop-Firm Risk Guardian Scorecard"),
            BotCommand("report", "📈 24-Hour Performance & P/L Summary"),
            BotCommand("panic", "🚨 Emergency Kill-Switch (Close All)"),
            BotCommand("colors", "🎨 Apply GBPUSD Color Scheme to Charts"),
            BotCommand("news", "📅 High-Impact Economic Calendar"),
            BotCommand("pause", "⏸️ Pause Auto-Trading Entries"),
            BotCommand("resume", "▶️ Resume Auto-Trading Entries"),
            BotCommand("help", "🤖 Full Bot Command Guide"),
        ]
        await application.bot.set_my_commands(commands)
        logger.info("Successfully synchronized Telegram Menu commands via set_my_commands")
    except Exception as e:
        logger.error(f"Failed to set Telegram menu commands: {e}")

async def news_alert_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Background recurring task to check and broadcast high-impact news reminders."""
    try:
        due_alerts = news_service.check_for_due_alerts(lead_minutes=NEWS_REMINDER_LEAD_MINUTES)
        for ev in due_alerts:
            country = ev.get("country", "")
            flag = CURRENCY_FLAGS.get(country, "🌐")
            mins = ev.get("minutes_remaining", 15)
            
            alert_msg = (
                f"🚨 <b>HIGH-IMPACT NEWS REMINDER</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ <b>Event:</b> {flag} <b>{country}</b> | <b>{ev.get('title')}</b>\n"
                f"⏳ <b>Starts In:</b> <b>~{mins} minutes</b>\n"
                f"📊 <b>Forecast:</b> <code>{ev.get('forecast', '-')}</code> | <b>Prev:</b> <code>{ev.get('previous', '-')}</code>\n\n"
                f"<i>💡 Recommended: Check open exposure, widen stops, or use /pause to prevent high-spread slippage.</i>"
            )
            
            for chat_id in ALLOWED_CHAT_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=alert_msg,
                        parse_mode=ParseMode.HTML
                    )
                    logger.info(f"Broadcasted news alert for '{ev.get('title')}' to chat {chat_id}")
                except Exception as ex:
                    logger.error(f"Failed to send news alert to chat {chat_id}: {ex}")
    except Exception as e:
        logger.error(f"Error in news_alert_job: {e}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler."""
    logger.error(f"Exception while handling an update: {context.error}")

def create_application():
    request = HTTPXRequest(connect_timeout=25.0, read_timeout=25.0, write_timeout=25.0)
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .build()
    )

    # Command Handlers (Supporting exact Menu commands + aliases)
    app.add_handler(CommandHandler(["start", "help"], handlers.cmd_help))
    app.add_handler(CommandHandler(["accounts", "switch"], handlers.cmd_accounts))
    app.add_handler(CommandHandler(["status", "account"], handlers.cmd_account))
    app.add_handler(CommandHandler("positions", handlers.cmd_positions))
    app.add_handler(CommandHandler(["prop", "risk"], handlers.cmd_prop))
    app.add_handler(CommandHandler("report", handlers.cmd_report))
    app.add_handler(CommandHandler(["screenshot", "screenphoto", "chart"], handlers.cmd_screenshot))
    app.add_handler(CommandHandler(["colors", "synccharts", "sync"], handlers.cmd_colors))
    app.add_handler(CommandHandler(["panic", "closeall"], handlers.cmd_closeall))
    app.add_handler(CommandHandler("history", handlers.cmd_history))
    app.add_handler(CommandHandler("close", handlers.cmd_close_symbol))
    app.add_handler(CommandHandler("modify_sl", handlers.cmd_modify_sl))
    app.add_handler(CommandHandler("modify_tp", handlers.cmd_modify_tp))
    app.add_handler(CommandHandler(["pause", "pause_bot"], handlers.cmd_pause_bot))
    app.add_handler(CommandHandler(["resume", "resume_bot"], handlers.cmd_resume_bot))
    app.add_handler(CommandHandler(["news", "calendar"], handlers.cmd_news))

    # Callback Query Handlers
    app.add_handler(CallbackQueryHandler(handlers.cb_switch_account, pattern=r"^switch_acc:"))
    app.add_handler(CallbackQueryHandler(handlers.cb_nav_action, pattern=r"^nav_"))
    app.add_handler(CallbackQueryHandler(handlers.callback_closeall, pattern=r"^(confirm_close_all|cancel_close_all)$"))
    app.add_handler(CallbackQueryHandler(handlers.cb_screenshot_symbol, pattern=r"^shotsym:"))
    app.add_handler(CallbackQueryHandler(handlers.cb_screenshot_tf, pattern=r"^shottf:"))

    # Error Handler
    app.add_error_handler(error_handler)

    # Schedule background news alerts every 60 seconds
    if app.job_queue:
        app.job_queue.run_repeating(news_alert_job, interval=60, first=10)
        logger.info(f"News alert background scheduler registered (every 60s, lead: {NEWS_REMINDER_LEAD_MINUTES}m)")

    return app

def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("No Telegram bot token found! Check .env or TELEGRAM_BOT_TOKEN environment variable.")
        sys.exit(1)

    logger.info(f"Starting 24/7 Telegram bot... Authorized Chat IDs: {ALLOWED_CHAT_IDS}")
    
    # Resilient 24/7 run loop
    while True:
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
            app = create_application()
            logger.info("Bot application initialized. Starting polling...")
            app.run_polling(drop_pending_updates=True)
            break
        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
            break
        except Exception as e:
            logger.error(f"Connection or runtime error in bot polling loop: {e}. Auto-reconnecting in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    main()
