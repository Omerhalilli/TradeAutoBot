"""
Main Application Entry Point for MT4 Telegram Bot & ZeroMQ Bridge.
Runs python-telegram-bot v20+ with background economic news reminder tasks,
2-step interactive screenshot panel, resilient ZeroMQ fault-tolerance,
and 24/7 automatic reconnect loops.
"""
import asyncio
import json
import logging
import os
import socket
import sys
import time
from telegram import BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.request import HTTPXRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

from config import TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_IDS, NEWS_REMINDER_LEAD_MINUTES, MT4_FILES_DIR, setup_logging
from news_service import news_service, CURRENCY_FLAGS
import handlers

# Configure root logger to output to both console and rotating logs/bot.log
logger = logging.getLogger("MT4BridgeBot")
logging.getLogger("apscheduler").setLevel(logging.WARNING)

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
            BotCommand("buy", "🟢 Quick BUY Market Order (e.g. /buy GBPUSD 0.01)"),
            BotCommand("sell", "🔴 Quick SELL Market Order (e.g. /sell GBPUSD 0.01)"),
            BotCommand("trade", "⚡ Remote Order Execution Wizard"),
            BotCommand("boost", "⚡ Institutional Turbo Boost & Diagnostics"),
            BotCommand("accounts", "👥 Switch Accounts & Inspect BUY/SELL"),
            BotCommand("status", "📊 Account Balance, Equity & Health"),
            BotCommand("positions", "💼 View & Manage Active Trades"),
            BotCommand("be", "🛡️ Move SL to Break-Even (+1 Pip Locked)"),
            BotCommand("trailing", "⚡ Dynamic Trailing Stop Management"),
            BotCommand("history", "📜 Closed Trades History & Net P/L"),
            BotCommand("screenshot", "📸 Interactive Chart Screenshot"),
            BotCommand("prop", "🛡️ Prop-Firm Risk Guardian Scorecard"),
            BotCommand("reset_risk", "🔄 Recalibrate Prop Anchors & DD"),
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

    # Synchronize active account profile with live MT4 terminal on startup
    try:
        from zmq_client import zmq_client
        from account_manager import account_manager
        acc_data = await asyncio.to_thread(zmq_client.get_account)
        if acc_data and acc_data.get("status") == "ok":
            synced_acc = account_manager.sync_with_live_terminal(acc_data)
            logger.info(f"Synchronized with live MT4 terminal: Account #{synced_acc.account_number} ({synced_acc.name})")
    except Exception as e:
        logger.debug(f"Could not synchronize active account with live terminal on startup: {e}")

async def outbox_alert_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatches any trade events written to telegram_outbox.json or tg_out_*.json by MT4 EA."""
    if not os.path.exists(MT4_FILES_DIR):
        return

    targets = []
    try:
        main_out = os.path.join(MT4_FILES_DIR, "telegram_outbox.json")
        if os.path.exists(main_out):
            targets.append(main_out)

        for entry in sorted(os.listdir(MT4_FILES_DIR)):
            if entry.startswith("tg_out_") and entry.endswith(".json"):
                targets.append(os.path.join(MT4_FILES_DIR, entry))
    except Exception as e:
        logger.debug(f"Error scanning outbox files: {e}")
        return

    for target_file in targets:
        try:
            with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
            if not content:
                try:
                    os.remove(target_file)
                except Exception:
                    pass
                continue

            data = json.loads(content)
            chat_id = data.get("chat_id")
            text = data.get("text", "")
            parse_mode = data.get("parse_mode", "HTML")
            reply_markup = None
            if "reply_markup" in data:
                kb_rows = []
                for row in data["reply_markup"].get("inline_keyboard", []):
                    kb_rows.append([InlineKeyboardButton(btn.get("text", ""), callback_data=btn.get("callback_data")) for btn in row])
                if kb_rows:
                    reply_markup = InlineKeyboardMarkup(kb_rows)

            target_chats = [chat_id] if chat_id else ALLOWED_CHAT_IDS
            for cid in target_chats:
                try:
                    await context.bot.send_message(
                        chat_id=cid,
                        text=text,
                        parse_mode=ParseMode.HTML if parse_mode == "HTML" else None,
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    logger.error(f"Error sending outbox alert to chat {cid}: {e}")

            try:
                os.remove(target_file)
            except Exception:
                pass
        except Exception as ex:
            logger.error(f"Error processing outbox file {target_file}: {ex}")
            try:
                os.remove(target_file)
            except Exception:
                pass

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
    app.add_handler(CommandHandler(["buy"], handlers.cmd_buy))
    app.add_handler(CommandHandler(["sell"], handlers.cmd_sell))
    app.add_handler(CommandHandler(["trade", "order"], handlers.cmd_trade))
    app.add_handler(CommandHandler(["boost", "turbo"], handlers.cmd_boost))
    app.add_handler(CommandHandler(["accounts", "switch"], handlers.cmd_accounts))
    app.add_handler(CommandHandler(["status", "account"], handlers.cmd_account))
    app.add_handler(CommandHandler("positions", handlers.cmd_positions))
    app.add_handler(CommandHandler(["be", "breakeven"], handlers.cmd_breakeven))
    app.add_handler(CommandHandler(["trailing", "trail"], handlers.cmd_trailing))
    app.add_handler(CommandHandler(["prop", "risk"], handlers.cmd_prop))
    app.add_handler(CommandHandler(["reset_risk", "reset_prop", "reset_safeguards"], handlers.cmd_reset_safeguards))
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

    # Slash text commands from EA messages: /close_12345, /half_12345, /be_12345, /shot_SYM_TF
    app.add_handler(MessageHandler(filters.Regex(r"^/(close|half|be|shot)_\w+"), handlers.handle_slash_action))

    # Callback Query Handlers
    app.add_handler(CallbackQueryHandler(handlers.cb_quick_trade, pattern=r"^trade:(buy|sell):"))
    app.add_handler(CallbackQueryHandler(handlers.cb_switch_account, pattern=r"^switch_acc:"))
    app.add_handler(CallbackQueryHandler(handlers.cb_nav_action, pattern=r"^(nav_|boost_colors)"))
    app.add_handler(CallbackQueryHandler(handlers.cb_reset_safeguards, pattern=r"^recalibrate_safeguards$"))
    app.add_handler(CallbackQueryHandler(handlers.cb_history_filter, pattern=r"^hist_filter:"))
    app.add_handler(CallbackQueryHandler(handlers.cb_news_filter, pattern=r"^news_filter:"))
    app.add_handler(CallbackQueryHandler(handlers.callback_closeall, pattern=r"^(confirm_close_all|cancel_close_all)$"))
    app.add_handler(CallbackQueryHandler(handlers.cb_screenshot_symbol, pattern=r"^shotsym:"))
    app.add_handler(CallbackQueryHandler(handlers.cb_screenshot_tf, pattern=r"^shottf:"))
    app.add_handler(CallbackQueryHandler(handlers.cb_ea_close, pattern=r"^/?close_\d+$"))
    app.add_handler(CallbackQueryHandler(handlers.cb_ea_half, pattern=r"^/?half_\d+$"))
    app.add_handler(CallbackQueryHandler(handlers.cb_ea_be, pattern=r"^/?be_\d+$"))
    app.add_handler(CallbackQueryHandler(handlers.cb_ea_shot, pattern=r"^/?shot_[A-Za-z0-9]+_[A-Za-z0-9]+$"))

    # Modern Institutional Handlers
    try:
        from autotrade.telegram_interface.command_router import command_router
        app.add_handler(CommandHandler(["menu"], command_router.cmd_start))
        app.add_handler(CommandHandler(["strategies", "strat"], command_router.cmd_strategies))
        app.add_handler(CallbackQueryHandler(command_router.handle_callback_query, pattern=r"^(strat_|set_risk_|set_dd_|set_pt_|act_panic)"))
    except Exception as ex:
        logger.warning(f"Could not register modern command router handlers: {ex}")

    # Error Handler
    app.add_error_handler(error_handler)

    # Schedule background news alerts and MT4 outbox poller
    if app.job_queue:
        app.job_queue.run_repeating(news_alert_job, interval=60, first=10)
        app.job_queue.run_repeating(outbox_alert_job, interval=2, first=3)
        logger.info(f"News alert (60s) and MT4 outbox (2s) background schedulers registered")

    return app

def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("No Telegram bot token found! Check .env or TELEGRAM_BOT_TOKEN environment variable.")
        sys.exit(1)

    logger.info(f"Starting 24/7 Telegram bot... Authorized Chat IDs: {ALLOWED_CHAT_IDS}")

    # Startup Self-Compilation and Integrity Check
    try:
        from autotrade.self_healing.compiler import SourceCompiler
        from autotrade.self_healing.healing_engine import HealingEngine
        compiler = SourceCompiler()
        res = compiler.compile_all_sync()
        if not res.success:
            logger.warning(f"Startup compilation detected {len(res.error_details)} errors. Engaging self-healing...")
            healer = HealingEngine(compiler=compiler)
            heal_res = healer.heal_compilation_errors_sync(res.error_details)
            if not heal_res.resolved:
                logger.critical("Unresolvable compilation errors remain! Starting bot in SAFEGUARD MODE.")
        else:
            logger.info(f"✅ Startup Self-Compilation Verified ({res.total_files_compiled}/{res.total_files_checked} files compiled in {res.duration_ms}ms).")
    except Exception as ex:
        logger.warning(f"Startup self-compilation check exception: {ex}")
    
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
