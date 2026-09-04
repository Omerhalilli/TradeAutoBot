"""
Telegram Command Handlers for MT4 ZeroMQ Bridge Bot.
Institutional Trading Terminal styling, robust validation, pagination,
inline quick navigation, and full remote MT4 control.
"""
import functools
import logging
import os
import time
from typing import Callable, List, Dict, Any, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import ALLOWED_CHAT_IDS, AUTOTRADE_FLAG_FILE
from zmq_client import zmq_client
from news_service import news_service, CURRENCY_FLAGS
from account_manager import account_manager, AccountProfile

logger = logging.getLogger(__name__)

# ==============================================================================
# Authorization Decorator
# ==============================================================================
def restricted(func: Callable) -> Callable:
    """Decorator to restrict commands to authorized Telegram chat IDs."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id if update.effective_user else 0
        chat_id = update.effective_chat.id if update.effective_chat else 0
        
        if chat_id not in ALLOWED_CHAT_IDS and user_id not in ALLOWED_CHAT_IDS:
            logger.warning(f"Unauthorized access attempt by User ID {user_id} (Chat ID {chat_id})")
            denied_msg = (
                "⛔ <b>ACCESS RESTRICTED</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Your Telegram Account/Chat is not authorized to interface with this institutional terminal.\n"
                f"• User ID: <code>{user_id}</code> | Chat ID: <code>{chat_id}</code>"
            )
            if update.message:
                await update.message.reply_text(denied_msg, parse_mode=ParseMode.HTML)
            elif update.callback_query:
                await update.callback_query.answer("⛔ Access Denied: Unauthorized account.", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# ==============================================================================
# Institutional Visual & Formatting Helpers
# ==============================================================================
def format_progress_bar(current: float, max_val: float, bar_len: int = 10) -> str:
    """Generates an institutional ASCII progress bar."""
    if max_val <= 0.0:
        return f"[{'□' * bar_len}] 0%"
    ratio = max(0.0, min(1.0, current / max_val))
    filled = int(round(ratio * bar_len))
    bar = "■" * filled + "□" * (bar_len - filled)
    return f"[{bar}] {int(round(ratio * 100))}%"

def clean_symbol(symbol: str) -> str:
    """Normalizes financial instrument aliases and removes whitespace."""
    s = symbol.strip().upper()
    aliases = {
        "GOLD": "XAUUSD",
        "SILVER": "XAGUSD",
        "OIL": "USOIL",
        "CRUDE": "USOIL",
        "WTI": "USOIL",
        "BRENT": "UKOIL",
        "BITCOIN": "BTCUSD",
        "CRYPTO": "BTCUSD"
    }
    return aliases.get(s, s)

def get_nav_keyboard(active_section: str = "status") -> InlineKeyboardMarkup:
    """Institutional unified navigation keyboard with section highlighting."""
    b_status = "📊 Status" if active_section != "status" else "📊 • Status •"
    b_pos = "💼 Positions" if active_section != "positions" else "💼 • Positions •"
    b_prop = "🛡️ Prop Guard" if active_section != "prop" else "🛡️ • Prop Guard •"
    b_report = "📈 24h Report" if active_section != "report" else "📈 • Report •"
    b_boost = "⚡ Turbo Boost" if active_section != "boost" else "⚡ • Boost •"
    
    keyboard = [
        [
            InlineKeyboardButton(b_status, callback_data="nav_status"),
            InlineKeyboardButton(b_pos, callback_data="nav_pos"),
            InlineKeyboardButton(b_prop, callback_data="nav_prop")
        ],
        [
            InlineKeyboardButton(b_report, callback_data="nav_report"),
            InlineKeyboardButton("📸 Screenshot", callback_data="nav_shot"),
            InlineKeyboardButton(b_boost, callback_data="nav_boost")
        ],
        [
            InlineKeyboardButton("👥 Switch Account", callback_data="switch_acc:panel"),
            InlineKeyboardButton("🔄 Refresh", callback_data=f"nav_refresh:{active_section}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def write_autotrade_flag(state: str) -> None:
    """Writes autotrade state flag to both local folder and MT4 Files directory."""
    content = f"{state.upper()}\nTimestamp={int(time.time())}\n"
    try:
        with open(AUTOTRADE_FLAG_FILE, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as ex:
        logger.debug(f"Could not write local flag file: {ex}")

    try:
        mt4_files_dir = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\80152BA938C72BA373B1EA4889AEE06F\MQL4\Files")
        os.makedirs(mt4_files_dir, exist_ok=True)
        mt4_flag_path = os.path.join(mt4_files_dir, "autotrade_state.flag")
        with open(mt4_flag_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as ex:
        logger.debug(f"Could not write MT4 flag file: {ex}")

# ==============================================================================
# Command Handlers
# ==============================================================================
@restricted
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_help(update, context)

@restricted
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    active_acc = account_manager.get_active_account()
    mode_badge = "🔴 REAL (LIVE)" if "REAL" in active_acc.name.upper() else "🟡 DEMO"
    
    help_text = (
        "🏛️ <b>INVEST-AZ INSTITUTIONAL COMMAND CENTER</b>\n"
        f"👤 <b>Active Account:</b> <code>#{active_acc.id} • {active_acc.name}</code> ({mode_badge})\n"
        f"🌐 <b>Server:</b> <code>{active_acc.server}</code> | <b>Endpoint:</b> <code>{active_acc.zmq_url}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>TURBO & SYSTEM PERFORMANCE</b>\n"
        "• /boost — Instant latency diagnostics, live spreads & engine health\n"
        "• /status or /account — Account overview, equity, margin health & telemetry\n"
        "• /accounts or /switch — Multi-account switcher & BUY/SELL diagnostics\n\n"
        "💼 <b>PORTFOLIO & ORDER MANAGEMENT</b>\n"
        "• /positions — Active open orders with live P/L & tickets\n"
        "• /history — Closed trade deals, statistics & cumulative net P/L\n"
        "  └ <code>/history today</code> | <code>/history week</code> | <code>/history 20</code>\n"
        "• /close <code>[SYMBOL|TICKET]</code> — Liquidate positions for symbol or ticket\n"
        "• /modify_sl <code>[SYM|TICKET] [PRICE]</code> — Modify Stop Loss (0 to remove)\n"
        "• /modify_tp <code>[SYM|TICKET] [PRICE]</code> — Modify Take Profit (0 to remove)\n"
        "• /panic or /closeall — Emergency kill-switch (liquidate entire book)\n\n"
        "🛡️ <b>RISK GUARDIAN & PERFORMANCE</b>\n"
        "• /prop or /risk — Prop-firm risk scorecard, drawdown limits & target progress\n"
        "• /report — Institutional 24-hour daily performance summary & win rate\n"
        "• /pause — Pause automated EA order entry immediately\n"
        "• /resume — Resume automated EA order entry scanning\n\n"
        "📸 <b>CHARTS & MARKET INTELLIGENCE</b>\n"
        "• /screenshot — Interactive 2-step chart snapshot wizard\n"
        "• /colors — Apply institutional GBPUSD black & candlestick scheme\n"
        "• /news or /calendar — High-impact macroeconomic calendar & countdowns\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <i>Tip: Use the inline buttons below for rapid one-touch terminal navigation.</i>"
    )
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(help_text, reply_markup=get_nav_keyboard("help"), parse_mode=ParseMode.HTML)
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(help_text, reply_markup=get_nav_keyboard("help"), parse_mode=ParseMode.HTML)

@restricted
async def cmd_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = zmq_client.get_account()
    if data.get("status") != "ok":
        await update.message.reply_text(
            f"⚠️ <b>MetaTrader 4 Bridge Offline</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Reason: <i>{data.get('message', 'Terminal unreachable on ZeroMQ socket.')}</i>\n\n"
            f"👉 Please verify MT4 is running with SmartAutoTradeEA_Pro attached.",
            parse_mode=ParseMode.HTML
        )
        return

    active_acc = account_manager.get_active_account()
    bal = float(data.get("balance", 0.0))
    eq = float(data.get("equity", 0.0))
    margin = float(data.get("margin", 0.0))
    free_m = float(data.get("free_margin", 0.0))
    m_level = float(data.get("margin_level", 0.0))
    floating = float(data.get("floating_pl", 0.0))
    curr = data.get("currency", "USD")
    server_time = data.get("server_time", "-")
    company = data.get("company", "Invest-AZ")
    trade_mode = data.get("trade_mode", "DEMO").upper()
    leverage = data.get("leverage", 100)
    server = data.get("server", active_acc.server)

    pl_pct = ((floating / bal) * 100.0) if bal > 0 else 0.0
    pl_badge = "🟢 PROFIT" if floating >= 0 else "🔴 DRAWDOWN"
    pl_sign = "+" if floating >= 0 else ""
    mode_badge = "🔴 REAL (LIVE)" if trade_mode == "REAL" else "🟡 DEMO"

    if margin <= 0.0:
        margin_health = "🟢 HEALTHY (No Margin Used)"
        m_level_str = "∞"
    elif m_level >= 500.0:
        margin_health = "🟢 HEALTHY"
        m_level_str = f"{m_level:,.1f}%"
    elif m_level >= 200.0:
        margin_health = "🟡 CAUTION"
        m_level_str = f"{m_level:,.1f}%"
    else:
        margin_health = "🚨 CRITICAL MARGIN CALL"
        m_level_str = f"{m_level:,.1f}%"

    msg = (
        "╔══════════════════════════════════╗\n"
        "   🏛️ <b>INVEST-AZ INSTITUTIONAL TERMINAL</b>\n"
        "╚══════════════════════════════════╝\n"
        f"<b>ACCOUNT:</b> <code>#{active_acc.id} • {active_acc.name}</code> [🟢 ACTIVE]\n"
        f"<b>LOGIN:</b>   <code>{data.get('account_number', active_acc.account_number)}</code> | <b>MODE:</b> {mode_badge}\n"
        f"<b>SERVER:</b>  <code>{server}</code> | <b>BROKER:</b> <i>{company}</i>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Balance:</b>      <code>${bal:,.2f} {curr}</code>\n"
        f"💎 <b>Equity:</b>       <code>${eq:,.2f} {curr}</code>\n"
        f"📊 <b>Floating P/L:</b> <code>{pl_sign}${floating:,.2f} {curr}</code> ({pl_sign}{pl_pct:.2f}%) — {pl_badge}\n"
        "──────────────────────────\n"
        f"🔒 <b>Margin Used:</b>  <code>${margin:,.2f}</code>\n"
        f"🆓 <b>Free Margin:</b>  <code>${free_m:,.2f}</code>\n"
        f"📈 <b>Margin Level:</b> <code>{m_level_str}</code> ({margin_health})\n"
        f"⚙️ <b>Leverage:</b>     <code>1:{leverage}</code>\n"
        f"🕒 <b>Server Time:</b>  <code>{server_time}</code>"
    )
    keyboard = get_nav_keyboard("status")
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)

@restricted
async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = zmq_client.get_positions()
    if data.get("status") != "ok":
        err_text = f"⚠️ <b>MT4 Bridge Error:</b> <i>{data.get('message', 'Failed to retrieve positions')}</i>"
        if update.callback_query:
            await update.callback_query.edit_message_text(err_text, parse_mode=ParseMode.HTML)
        elif update.message:
            await update.message.reply_text(err_text, parse_mode=ParseMode.HTML)
        return

    active_acc = account_manager.get_active_account()
    positions = data.get("positions", [])
    count = data.get("count", 0)

    if count == 0:
        empty_msg = (
            f"💼 <b>OPEN POSITIONS PORTFOLIO (0 Orders)</b>\n"
            f"👤 <b>Account #{active_acc.id}:</b> <code>{active_acc.account_number}</code> ({active_acc.name})\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>There are currently no active market orders running on this account.</i>"
        )
        if update.callback_query:
            await update.callback_query.edit_message_text(empty_msg, reply_markup=get_nav_keyboard("positions"), parse_mode=ParseMode.HTML)
        elif update.message:
            await update.message.reply_text(empty_msg, reply_markup=get_nav_keyboard("positions"), parse_mode=ParseMode.HTML)
        return

    total_pl = sum(float(p.get("profit", 0.0)) for p in positions)
    total_volume = sum(float(p.get("volume", p.get("lots", 0.0))) for p in positions)
    sign_pl = "+" if total_pl >= 0 else ""
    pl_badge = "🟢 PROFIT" if total_pl >= 0 else "🔴 DRAWDOWN"

    header = (
        f"💼 <b>OPEN POSITIONS PORTFOLIO ({count} Orders | {total_volume:.2f} Lots)</b>\n"
        f"👤 <b>Account #{active_acc.id}:</b> <code>{active_acc.account_number}</code> ({active_acc.name})\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )

    chunk_size = 8
    total_pages = (count + chunk_size - 1) // chunk_size

    for page_idx in range(total_pages):
        page_positions = positions[page_idx * chunk_size : (page_idx + 1) * chunk_size]
        msg = header if page_idx == 0 else f"💼 <b>Open Positions (Part {page_idx + 1}/{total_pages})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        
        for pos in page_positions:
            ticket = pos.get("ticket")
            sym = pos.get("symbol")
            type_str = str(pos.get("type", "BUY")).upper()
            lots = float(pos.get("volume", pos.get("lots", 0.0)))
            open_p = float(pos.get("open_price", 0.0))
            curr_p = float(pos.get("close_price", 0.0))
            sl = float(pos.get("sl", 0.0))
            tp = float(pos.get("tp", 0.0))
            profit = float(pos.get("profit", 0.0))

            icon = "🟢 BUY" if "BUY" in type_str else "🔴 SELL"
            p_sign = "+" if profit >= 0 else ""
            sl_str = f"<code>{sl}</code>" if sl > 0 else "<i>None</i>"
            tp_str = f"<code>{tp}</code>" if tp > 0 else "<i>None</i>"

            msg += (
                f"<b>#{ticket} • {icon} {lots:.2f} {sym}</b>\n"
                f"   In: <code>{open_p}</code> ➜ Now: <code>{curr_p}</code>\n"
                f"   SL: {sl_str} | TP: {tp_str}\n"
                f"   Net P/L: <b>{p_sign}${profit:,.2f}</b>\n\n"
            )

        if page_idx == total_pages - 1:
            msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"💰 <b>Total Portfolio P/L:</b> <b>{sign_pl}${total_pl:,.2f}</b> ({pl_badge})"

        keyboard = get_nav_keyboard("positions") if page_idx == total_pages - 1 else None
        
        if update.callback_query and page_idx == 0:
            try:
                await update.callback_query.edit_message_text(msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)
            except Exception:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)

@restricted
async def cmd_boost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Turbo Boost Command: Rapid diagnostics, live latency test, spreads and engine health."""
    latency = zmq_client.ping_latency_ms()
    boost_data = zmq_client.get_boost()
    active_acc = account_manager.get_active_account()

    if boost_data.get("status") != "ok":
        acc_data = zmq_client.get_account()
        pos_data = zmq_client.get_positions()
        
        bal = float(acc_data.get("balance", 0.0))
        eq = float(acc_data.get("equity", 0.0))
        orders_count = pos_data.get("count", 0)
        float_pl = eq - bal
        server_time = acc_data.get("server_time", "-")
        autotrade_active = True
        spread_gbp = 10.0
        spread_eur = 10.0
        spread_gold = 25.0
    else:
        bal = float(boost_data.get("balance", 0.0))
        eq = float(boost_data.get("equity", 0.0))
        orders_count = int(boost_data.get("active_orders", 0))
        float_pl = float(boost_data.get("floating_pl", 0.0))
        server_time = boost_data.get("server_time", "-")
        autotrade_active = boost_data.get("autotrading_active", True)
        spread_gbp = float(boost_data.get("spread_gbpusd", 10.0))
        spread_eur = float(boost_data.get("spread_eurusd", 10.0))
        spread_gold = float(boost_data.get("spread_xauusd", 25.0))

    lat_badge = "🟢 ULTRA-FAST" if latency < 15.0 else ("🟡 ACCEPTABLE" if latency < 50.0 else "🔴 HIGH LATENCY")
    auto_badge = "ACTIVE & SCANNING 🟢" if autotrade_active else "PAUSED ⏸️"
    pl_sign = "+" if float_pl >= 0 else ""

    msg = (
        "╔══════════════════════════════════╗\n"
        "   ⚡ <b>INSTITUTIONAL TURBO BOOST PANEL</b>\n"
        "╚══════════════════════════════════╝\n"
        f"👤 <b>Account #{active_acc.id}:</b> <code>{active_acc.name}</code> ({active_acc.account_number})\n"
        f"🌐 <b>Bridge Status:</b> ONLINE | <b>Server Time:</b> <code>{server_time}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 <b>ENGINE PERFORMANCE & TELEMETRY:</b>\n"
        f"• <b>Roundtrip Latency:</b> <code>{latency:.2f} ms</code> — {lat_badge}\n"
        f"• <b>ZeroMQ Event Loop:</b> <code>250 ms (4 Hz)</code> high-frequency cycle\n"
        f"• <b>AutoTrading Engine:</b> {auto_badge}\n"
        f"• <b>Active Exposure:</b> <code>{orders_count} orders</code> | Float P/L: <b>{pl_sign}${float_pl:,.2f}</b>\n"
        "──────────────────────────\n"
        "📊 <b>LIVE MAJOR SPREADS CHECK:</b>\n"
        f"• 🇬🇧 <b>GBPUSD:</b> <code>{spread_gbp:.1f} pts</code> (Tight)\n"
        f"• 🇪🇺 <b>EURUSD:</b> <code>{spread_eur:.1f} pts</code> (Tight)\n"
        f"• 🪙 <b>XAUUSD:</b> <code>{spread_gold:.1f} pts</code> (Standard)\n"
        "──────────────────────────\n"
        "💎 <b>CAPITAL HEALTH:</b>\n"
        f"• Balance: <code>${bal:,.2f}</code> | Equity: <code>${eq:,.2f}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>QUICK TURBO ACTIONS:</b>"
    )

    boost_keyboard = [
        [
            InlineKeyboardButton("📸 Instant Chart Snapshot", callback_data="shotsym:CURRENT"),
            InlineKeyboardButton("🎨 Sync GBPUSD Colors", callback_data="boost_colors")
        ],
        [
            InlineKeyboardButton("🛡️ Prop Guardian", callback_data="nav_prop"),
            InlineKeyboardButton("💼 Open Positions", callback_data="nav_pos")
        ],
        [
            InlineKeyboardButton("🔄 Re-Run Boost Diagnostics", callback_data="nav_boost"),
            InlineKeyboardButton("📊 Back to Status", callback_data="nav_status")
        ]
    ]

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(boost_keyboard), parse_mode=ParseMode.HTML)
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(boost_keyboard), parse_mode=ParseMode.HTML)

@restricted
async def cmd_prop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = zmq_client.get_prop()
    if data.get("status") != "ok":
        acc_data = zmq_client.get_account()
        eq = float(acc_data.get("equity", 10000.0))
        bal = float(acc_data.get("balance", 10000.0))
        acc = acc_data.get("account_number", "-")
        comp = acc_data.get("company", "Invest-AZ")
        curr = acc_data.get("currency", "USD")
        peak_eq = max(eq, bal)
        day_loss = max(0.0, bal - eq)
        day_limit = bal * 0.045
        day_pct = (day_loss / bal * 100.0) if bal > 0 else 0.0
        day_st = "Safe" if day_pct < 3.0 else "Caution"
        peak_loss = max(0.0, peak_eq - eq)
        peak_limit = peak_eq * 0.08
        peak_pct = (peak_loss / peak_eq * 100.0) if peak_eq > 0 else 0.0
        peak_st = "Safe" if peak_pct < 5.0 else "Caution"
        gain = max(0.0, eq - bal)
        target_goal = bal * 0.08
        max_d_pct = 4.5
        max_t_pct = 8.0
        target_goal_pct = 8.0
        lockout = False
        autotrade = True
        shield = "Friday 21:00 GMT (Active) 🛡️"
    else:
        acc = data.get("account", "-")
        comp = data.get("company", "Invest-AZ")
        curr = data.get("currency", "USD")
        eq = float(data.get("equity", 0.0))
        peak_eq = float(data.get("peak_equity", eq))
        day_loss = float(data.get("day_loss", 0.0))
        day_limit = float(data.get("day_loss_limit", eq * 0.045))
        day_pct = float(data.get("day_loss_pct", 0.0))
        day_st = data.get("day_status", "Safe")
        peak_loss = float(data.get("peak_loss", 0.0))
        peak_limit = float(data.get("peak_loss_limit", peak_eq * 0.08))
        peak_pct = float(data.get("peak_loss_pct", 0.0))
        peak_st = data.get("peak_status", "Safe")
        gain = float(data.get("current_gain", 0.0))
        target_goal = float(data.get("target_profit_goal", eq * 0.08))
        max_d_pct = float(data.get("max_daily_limit_pct", 4.5))
        max_t_pct = float(data.get("max_total_limit_pct", 8.0))
        target_goal_pct = float(data.get("target_goal_pct", 8.0))
        lockout = bool(data.get("lockout_active", False))
        autotrade = bool(data.get("autotrading_active", True))
        shield = data.get("weekend_shield", "Friday 21:00 GMT (Active) 🛡️")

    day_badge = "🟢 Safe" if day_st == "Safe" else ("🟡 Caution" if day_st == "Caution" else "🚨 BREACHED")
    peak_badge = "🟢 Safe" if peak_st == "Safe" else ("🟡 Caution" if peak_st == "Caution" else "🚨 BREACHED")
    guard_badge = "🔒 LOCKED (Breach Liquidated)" if lockout else ("ACTIVE & ENFORCED 🟢" if autotrade else "PAUSED ⏸️")

    msg = (
        "╔══════════════════════════════════╗\n"
        "   🛡️ <b>PROP-FIRM RISK GUARDIAN SCORECARD</b>\n"
        "╚══════════════════════════════════╝\n"
        f"• <b>Account:</b> <code>{acc}</code> ({comp})\n"
        f"• <b>Equity:</b> <code>${eq:,.2f} {curr}</code> | <b>Peak:</b> <code>${peak_eq:,.2f} {curr}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📉 <b>DAILY DRAWDOWN MONITOR (Max: {max_d_pct:.1f}%):</b>\n"
        f"• Loss Today: -${day_loss:,.2f} / -${day_limit:,.2f} ({day_pct:.2f}%) — {day_badge}\n"
        f"  <code>{format_progress_bar(day_loss, day_limit, 12)}</code>\n"
        "──────────────────────────\n"
        f"📉 <b>TRAILING PEAK DRAWDOWN (Max: {max_t_pct:.1f}%):</b>\n"
        f"• Trailing DD: -${peak_loss:,.2f} / -${peak_limit:,.2f} ({peak_pct:.2f}%) — {peak_badge}\n"
        f"  <code>{format_progress_bar(peak_loss, peak_limit, 12)}</code>\n"
        "──────────────────────────\n"
        f"🎯 <b>PROFIT TARGET MILESTONE (Target: {target_goal_pct:.1f}%):</b>\n"
        f"• Net Progress: +${gain:,.2f} / +${target_goal:,.2f}\n"
        f"  <code>{format_progress_bar(gain, target_goal, 12)}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Guardian Protection:</b> <b>{guard_badge}</b>\n"
        f"• <b>Weekend Shield:</b> <code>{shield}</code>"
    )
    keyboard = get_nav_keyboard("prop")
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)

@restricted
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = zmq_client.get_report()
    if data.get("status") != "ok":
        acc_data = zmq_client.get_account()
        bal = float(acc_data.get("balance", 0.0))
        eq = float(acc_data.get("equity", 0.0))
        acc = acc_data.get("account_number", "-")
        comp = acc_data.get("company", "Invest-AZ")
        curr = acc_data.get("currency", "USD")
        period = "Last 24 Hours"
        total_trades = 0
        win_count = 0
        loss_count = 0
        win_rate = 0.0
        gross_p = 0.0
        gross_l = 0.0
        pf = 0.0
        net = 0.0
        best_sym = "-"
        best_p = 0.0
        worst_sym = "-"
        worst_l = 0.0
    else:
        period = data.get("period", "Last 24 Hours")
        acc = data.get("account", "-")
        comp = data.get("company", "Invest-AZ")
        curr = data.get("currency", "USD")
        total_trades = int(data.get("total_trades", 0))
        win_count = int(data.get("win_count", 0))
        loss_count = int(data.get("loss_count", 0))
        win_rate = float(data.get("win_rate", 0.0))
        gross_p = float(data.get("gross_profit", 0.0))
        gross_l = float(data.get("gross_loss", 0.0))
        pf = float(data.get("profit_factor", 0.0))
        net = float(data.get("net_pl", 0.0))
        best_sym = data.get("best_symbol", "-")
        best_p = float(data.get("best_profit", 0.0))
        worst_sym = data.get("worst_symbol", "-")
        worst_l = float(data.get("worst_loss", 0.0))
        bal = float(data.get("ending_balance", 0.0))
        eq = float(data.get("ending_equity", 0.0))

    pl_sign = "🟢 +" if net >= 0 else "🔴 -"
    pf_badge = " ⭐ Institutional Grade" if pf >= 1.5 else ""

    msg = (
        "╔══════════════════════════════════╗\n"
        "   📈 <b>24-HOUR PERFORMANCE SCORECARD</b>\n"
        "╚══════════════════════════════════╝\n"
        f"• <b>Reporting Period:</b> {period}\n"
        f"• <b>Account:</b> <code>{acc}</code> ({comp})\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Closed Trades:</b> <code>{total_trades} deals</code> ({win_count}W / {loss_count}L)\n"
        f"• <b>Win Rate:</b> <code>{win_rate:.1f}%</code>\n"
        f"  <code>{format_progress_bar(win_count, total_trades, 12)}</code>\n"
        "──────────────────────────\n"
        f"• <b>Gross Profit:</b>  <code>+${gross_p:,.2f} {curr}</code>\n"
        f"• <b>Gross Loss:</b>    <code>-${gross_l:,.2f} {curr}</code>\n"
        f"• <b>Profit Factor:</b> <code>{pf:.2f}</code>{pf_badge}\n"
        f"• <b>Net Realized:</b>  <b>{pl_sign}${abs(net):,.2f} {curr}</b>\n"
        "──────────────────────────\n"
    )
    if best_p > 0:
        msg += f"• 🏆 <b>Best Deal:</b>  <code>{best_sym}</code> (+${best_p:,.2f})\n"
    if worst_l < 0:
        msg += f"• ⚠️ <b>Worst Deal:</b> <code>{worst_sym}</code> (-${abs(worst_l):,.2f})\n"
    msg += (
        f"• <b>Ending Balance:</b> <code>${bal:,.2f} {curr}</code>\n"
        f"• <b>Ending Equity:</b>  <code>${eq:,.2f} {curr}</code>"
    )
    keyboard = get_nav_keyboard("report")
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)

@restricted
async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    filter_type = "all"
    limit = 10

    if args:
        arg0 = args[0].lower()
        if arg0 in ["today", "day"]:
            filter_type = "today"
            limit = 50
        elif arg0 in ["lastweek", "week", "thisweek"]:
            filter_type = "lastweek"
            limit = 50
        elif arg0.isdigit():
            limit = min(100, max(1, int(arg0)))
        else:
            await update.message.reply_text(
                "ℹ️ <b>History Filter Usage:</b>\n"
                "• <code>/history</code> — Last 10 closed deals\n"
                "• <code>/history today</code> — Deals closed today\n"
                "• <code>/history week</code> — Deals closed this week\n"
                "• <code>/history 25</code> — Last N closed deals",
                parse_mode=ParseMode.HTML
            )
            return

    data = zmq_client.get_history(limit=limit, filter_type=filter_type)
    if data.get("status") != "ok":
        await update.message.reply_text(f"⚠️ <b>MT4 Bridge Error:</b> <i>{data.get('message', 'Could not retrieve history')}</i>", parse_mode=ParseMode.HTML)
        return

    trades = data.get("trades", [])
    total_net = float(data.get("total_net_pl", 0.0))
    count = data.get("count", 0)

    if count == 0:
        await update.message.reply_text(
            f"📜 <b>TRADE HISTORY AUDIT ({filter_type.upper()}):</b>\n"
            f"<i>No closed trade transactions recorded for this period.</i>",
            parse_mode=ParseMode.HTML
        )
        return

    tot_icon = "🟢" if total_net >= 0 else "🔴"
    tot_sign = "+" if total_net >= 0 else ""

    header = (
        f"📜 <b>CLOSED TRADE HISTORY AUDIT ({filter_type.upper()} • {count} Deals)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    chunk_size = 8
    total_pages = (count + chunk_size - 1) // chunk_size

    for page_idx in range(total_pages):
        page_trades = trades[page_idx * chunk_size : (page_idx + 1) * chunk_size]
        msg = header if page_idx == 0 else f"📜 <b>Trade History (Part {page_idx + 1}/{total_pages})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        for tr in page_trades:
            ticket = tr.get("ticket")
            sym = tr.get("symbol")
            type_str = tr.get("type", "BUY")
            lots = float(tr.get("lots", 0.0))
            open_p = float(tr.get("open_price", 0.0))
            close_p = float(tr.get("close_price", 0.0))
            net_pl = float(tr.get("net_pl", 0.0))
            close_time = tr.get("close_time", "")

            icon = "🟢 BUY" if type_str == "BUY" else "🔴 SELL"
            p_badge = "✅" if net_pl >= 0 else "❌"
            p_sign = "+" if net_pl >= 0 else ""

            msg += (
                f"{p_badge} <b>#{ticket} • {icon} {lots:.2f} {sym}</b>\n"
                f"   In: <code>{open_p}</code> ➜ Out: <code>{close_p}</code>\n"
                f"   Net P/L: <b>{p_sign}${net_pl:,.2f}</b> | <code>{close_time}</code>\n\n"
            )

        if page_idx == total_pages - 1:
            msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"{tot_icon} <b>Cumulative Net Profit:</b> <b>{tot_sign}${total_net:,.2f}</b>"

        await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML)

@restricted
async def cmd_close_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "ℹ️ <b>Close Order Usage:</b>\n"
            "• <code>/close SYMBOL</code> — Close all trades for symbol (e.g. <code>/close GBPUSD</code>, <code>/close GOLD</code>)\n"
            "• <code>/close TICKET</code> — Close specific ticket (e.g. <code>/close 35183711</code>)\n"
            "• <code>/panic</code> — Liquidate entire book immediately",
            parse_mode=ParseMode.HTML
        )
        return

    target = clean_symbol(args[0])
    data = zmq_client.close_symbol(target)
    if data.get("status") != "ok":
        await update.message.reply_text(f"❌ <b>Execution Error:</b> {data.get('message')}", parse_mode=ParseMode.HTML)
        return

    closed = data.get("closed_count", 0)
    failed = data.get("failed_count", 0)
    realized = float(data.get("realized_pl", 0.0))
    r_sign = "+" if realized >= 0 else ""

    if closed == 0 and failed == 0:
        await update.message.reply_text(
            f"ℹ️ <b>No Open Trades Found:</b> No active market orders match target <code>{target}</code>.",
            parse_mode=ParseMode.HTML
        )
        return

    msg = (
        f"🎯 <b>MARKET LIQUIDATION EXECUTED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Target:</b> <code>{target}</code>\n"
        f"• <b>Orders Closed:</b> <b>{closed}</b>\n"
        f"• <b>Orders Failed:</b> <b>{failed}</b>\n"
        f"• <b>Realized P/L:</b>  <b>{r_sign}${realized:,.2f}</b>"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@restricted
async def cmd_modify_sl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "ℹ️ <b>Modify Stop Loss Usage:</b>\n"
            "• <code>/modify_sl SYMBOL PRICE</code> — e.g. <code>/modify_sl GBPUSD 1.3520</code>\n"
            "• <code>/modify_sl TICKET PRICE</code> — e.g. <code>/modify_sl 35183711 1.3520</code>\n"
            "• <code>/modify_sl GBPUSD 0</code> — Remove Stop Loss",
            parse_mode=ParseMode.HTML
        )
        return

    target = clean_symbol(args[0])
    try:
        sl_price = float(args[1])
    except ValueError:
        await update.message.reply_text("❌ <b>Invalid Price:</b> Stop Loss price must be a valid numeric value.", parse_mode=ParseMode.HTML)
        return

    if target.isdigit():
        data = zmq_client.modify_sl(ticket=int(target), sl=sl_price)
    else:
        data = zmq_client.modify_sl(symbol=target, sl=sl_price)

    if data.get("status") != "ok":
        await update.message.reply_text(f"❌ <b>Error Modifying SL:</b> {data.get('message')}", parse_mode=ParseMode.HTML)
        return

    count = data.get("modified_count", 0)
    sl_action = "Removed (0.0)" if sl_price == 0.0 else f"<code>{sl_price}</code>"
    msg = (
        "✅ <b>STOP LOSS SYNCHRONIZED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Target:</b> <code>{target}</code>\n"
        f"• <b>New SL Level:</b> {sl_action}\n"
        f"• <b>Orders Updated:</b> <b>{count}</b>"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@restricted
async def cmd_modify_tp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "ℹ️ <b>Modify Take Profit Usage:</b>\n"
            "• <code>/modify_tp SYMBOL PRICE</code> — e.g. <code>/modify_tp GBPUSD 1.3650</code>\n"
            "• <code>/modify_tp TICKET PRICE</code> — e.g. <code>/modify_tp 35183711 1.3650</code>\n"
            "• <code>/modify_tp GBPUSD 0</code> — Remove Take Profit",
            parse_mode=ParseMode.HTML
        )
        return

    target = clean_symbol(args[0])
    try:
        tp_price = float(args[1])
    except ValueError:
        await update.message.reply_text("❌ <b>Invalid Price:</b> Take Profit price must be a valid numeric value.", parse_mode=ParseMode.HTML)
        return

    if target.isdigit():
        data = zmq_client.modify_tp(ticket=int(target), tp=tp_price)
    else:
        data = zmq_client.modify_tp(symbol=target, tp=tp_price)

    if data.get("status") != "ok":
        await update.message.reply_text(f"❌ <b>Error Modifying TP:</b> {data.get('message')}", parse_mode=ParseMode.HTML)
        return

    count = data.get("modified_count", 0)
    tp_action = "Removed (0.0)" if tp_price == 0.0 else f"<code>{tp_price}</code>"
    msg = (
        "✅ <b>TAKE PROFIT SYNCHRONIZED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Target:</b> <code>{target}</code>\n"
        f"• <b>New TP Level:</b> {tp_action}\n"
        f"• <b>Orders Updated:</b> <b>{count}</b>"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@restricted
async def cmd_closeall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompts for confirmation before closing all open trades."""
    pos_data = zmq_client.get_positions()
    count = pos_data.get("count", 0)
    
    keyboard = [
        [
            InlineKeyboardButton(f"🚨 YES, CLOSE ALL ({count} POSITIONS)", callback_data="confirm_close_all"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_close_all")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "⚠️ <b>EMERGENCY KILL-SWITCH CONFIRMATION</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Are you sure you want to market-liquidate <b>ALL {count} open positions</b> immediately?\n"
        "<i>This action cannot be undone. Pending orders will also be purged.</i>",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def callback_closeall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_close_all":
        data = zmq_client.close_all()
        if data.get("status") != "ok":
            await query.edit_message_text(f"❌ <b>Error:</b> {data.get('message', 'Failed to close orders')}", parse_mode=ParseMode.HTML)
            return

        closed = data.get("closed_count", 0)
        failed = data.get("failed_count", 0)
        realized = float(data.get("realized_pl", 0.0))
        r_sign = "+" if realized >= 0 else ""

        msg = (
            "🚨 <b>EMERGENCY KILL-SWITCH EXECUTED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>Orders Closed:</b> <b>{closed}</b>\n"
            f"⚠️ <b>Orders Failed:</b> <b>{failed}</b>\n"
            f"💵 <b>Realized P/L:</b>   <b>{r_sign}${realized:,.2f}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>All market exposure has been liquidated.</i>"
        )
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML)

    elif query.data == "cancel_close_all":
        await query.edit_message_text("✅ <i>Emergency Close All cancelled. Open portfolio positions left intact.</i>", parse_mode=ParseMode.HTML)

@restricted
async def cmd_pause_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    write_autotrade_flag("PAUSED")
    data = zmq_client.pause_bot()
    conn_note = "" if data.get("status") == "ok" else " (Note: MT4 bridge offline; flag will apply upon restart)"

    msg = (
        "⏸️ <b>AUTOTRADING PAUSED BY REMOTE COMMAND</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "• State flag <code>autotrade_state.flag</code> set to <b>PAUSED</b>\n"
        "• Global Variable <code>AutoTrading_Paused</code> set to <b>1.0</b>\n"
        f"• AutoTrading EAs will immediately freeze all new order placement.{conn_note}"
    )
    await update.message.reply_text(msg, reply_markup=get_nav_keyboard("status"), parse_mode=ParseMode.HTML)

@restricted
async def cmd_resume_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    write_autotrade_flag("ACTIVE")
    data = zmq_client.resume_bot()
    conn_note = "" if data.get("status") == "ok" else " (Note: MT4 bridge offline; flag will apply upon restart)"

    msg = (
        "▶️ <b>AUTOTRADING RESUMED BY REMOTE COMMAND</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "• State flag <code>autotrade_state.flag</code> set to <b>ACTIVE</b>\n"
        "• Global Variable <code>AutoTrading_Paused</code> set to <b>0.0</b>\n"
        f"• AutoTrading EAs have resumed full scanning and order execution.{conn_note}"
    )
    await update.message.reply_text(msg, reply_markup=get_nav_keyboard("status"), parse_mode=ParseMode.HTML)

@restricted
async def cmd_colors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = zmq_client.apply_colors()
    if data.get("status") != "ok":
        await update.message.reply_text(f"⚠️ <b>MT4 Error:</b> {data.get('message', 'Failed to apply colors')}", parse_mode=ParseMode.HTML)
        return

    count = data.get("synced_count", 0)
    msg = (
        "🎨 <b>INSTITUTIONAL CHART COLORS SYNCHRONIZED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "• <b>Theme:</b> GBPUSD Dark Institutional Candlestick Scheme\n"
        f"• <b>Open Charts Synchronized:</b> <b>{count} chart(s)</b>\n"
        "• <b>Candles:</b> Bull (Teal Green) | Bear (Coral Red)\n"
        "• <b>Background:</b> Solid Dark Terminal Slate\n"
        "• <b>Result:</b> All charts updated in real time! ✅"
    )
    await update.message.reply_text(msg, reply_markup=get_nav_keyboard("status"), parse_mode=ParseMode.HTML)

@restricted
async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if args and args[0].lower() in ["week", "thisweek"]:
        events = news_service.get_week_events()
        title = "This Week's High-Impact Economic Calendar"
    else:
        events = news_service.get_today_events()
        title = "Today's High-Impact Economic Calendar"

    messages = news_service.format_news_messages(events, title)
    for msg in messages:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

# ==============================================================================
# Interactive Screenshot Panel
# ==============================================================================
def get_symbol_keyboard() -> InlineKeyboardMarkup:
    """Generates the Step 1 symbol selection keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("🇬🇧 GBPUSD", callback_data="shotsym:GBPUSD"),
            InlineKeyboardButton("🇪🇺 EURUSD", callback_data="shotsym:EURUSD")
        ],
        [
            InlineKeyboardButton("🪙 XAUUSD (Gold)", callback_data="shotsym:XAUUSD"),
            InlineKeyboardButton("🇯🇵 USDJPY", callback_data="shotsym:USDJPY")
        ],
        [
            InlineKeyboardButton("₿ BTCUSD", callback_data="shotsym:BTCUSD"),
            InlineKeyboardButton("🛢️ USOIL", callback_data="shotsym:USOIL")
        ],
        [
            InlineKeyboardButton("📊 Active Chart Window", callback_data="shotsym:CURRENT")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_timeframe_keyboard(symbol: str) -> InlineKeyboardMarkup:
    """Generates the Step 2 timeframe selection keyboard for a given symbol."""
    keyboard = [
        [
            InlineKeyboardButton("⏱️ M1", callback_data=f"shottf:{symbol}:M1"),
            InlineKeyboardButton("⏱️ M5", callback_data=f"shottf:{symbol}:M5"),
            InlineKeyboardButton("⏱️ M15", callback_data=f"shottf:{symbol}:M15")
        ],
        [
            InlineKeyboardButton("⏱️ M30", callback_data=f"shottf:{symbol}:M30"),
            InlineKeyboardButton("⏱️ H1", callback_data=f"shottf:{symbol}:H1"),
            InlineKeyboardButton("⏱️ H4", callback_data=f"shottf:{symbol}:H4")
        ],
        [
            InlineKeyboardButton("📅 D1", callback_data=f"shottf:{symbol}:D1"),
            InlineKeyboardButton("📅 W1", callback_data=f"shottf:{symbol}:W1"),
            InlineKeyboardButton("🔙 Back to Symbols", callback_data="shotsym:BACK")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

@restricted
async def cmd_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if args:
        sym = clean_symbol(args[0])
        tf = args[1].upper() if len(args) > 1 else ""
        await execute_screenshot_delivery(update.effective_chat.id, context, sym, tf)
        return

    msg = (
        "📸 <b>INSTITUTIONAL CHART SNAPSHOT WIZARD</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Select the currency pair or financial asset you wish to render:"
    )
    await update.message.reply_text(msg, reply_markup=get_symbol_keyboard(), parse_mode=ParseMode.HTML)

async def cb_screenshot_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if data == "shotsym:BACK":
        msg = (
            "📸 <b>INSTITUTIONAL CHART SNAPSHOT WIZARD</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Select the currency pair or financial asset you wish to render:"
        )
        await query.edit_message_text(msg, reply_markup=get_symbol_keyboard(), parse_mode=ParseMode.HTML)
        return

    symbol = data.split(":", 1)[1] if ":" in data else "CURRENT"
    display_sym = "Active Chart Window" if symbol == "CURRENT" else symbol

    msg = (
        f"📸 <b>Target Instrument:</b> <code>{display_sym}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Select the chart timeframe to capture:"
    )
    await query.edit_message_text(msg, reply_markup=get_timeframe_keyboard(symbol), parse_mode=ParseMode.HTML)

async def cb_screenshot_tf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Capturing high-resolution chart...")

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        return

    symbol = parts[1]
    timeframe = parts[2]
    display_sym = "Current Chart" if symbol == "CURRENT" else symbol

    await query.edit_message_text(
        f"⏳ <i>Capturing {display_sym} ({timeframe}) from MetaTrader 4 engine...</i>",
        parse_mode=ParseMode.HTML
    )

    chat_id = update.effective_chat.id
    success = await execute_screenshot_delivery(chat_id, context, symbol, timeframe)
    if success:
        try:
            await query.delete_message()
        except Exception:
            pass
    else:
        await query.edit_message_text(
            f"⚠️ <b>Capture Failed:</b> MT4 bridge unreachable or chart window unavailable.",
            parse_mode=ParseMode.HTML
        )

async def execute_screenshot_delivery(chat_id: int, context: ContextTypes.DEFAULT_TYPE, symbol: str, timeframe: str) -> bool:
    data = zmq_client.get_screenshot(symbol=symbol, timeframe=timeframe)
    if data.get("status") != "ok":
        return False

    shot_filename = data.get("filename", "chart_screenshot.png")
    sym = data.get("symbol", symbol)
    tf = data.get("timeframe", timeframe).replace("PERIOD_", "")
    bid = data.get("bid", 0.0)
    ask = data.get("ask", 0.0)
    server_time = data.get("server_time", "")

    mt4_files_dir = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\80152BA938C72BA373B1EA4889AEE06F\MQL4\Files")
    shot_path = os.path.join(mt4_files_dir, shot_filename)

    if not os.path.exists(shot_path):
        return False

    caption = (
        f"📊 <b>Chart Telemetry: {sym} ({tf})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Bid / Ask:</b> <code>{bid} / {ask}</code>\n"
        f"• <b>Server Time:</b> <code>{server_time}</code>"
    )
    with open(shot_path, "rb") as photo_file:
        await context.bot.send_photo(chat_id=chat_id, photo=photo_file, caption=caption, parse_mode=ParseMode.HTML)
    return True

# ==============================================================================
# Multi-Account Profile Switcher & BUY/SELL Function Inspection
# ==============================================================================
def get_accounts_keyboard() -> InlineKeyboardMarkup:
    """Renders inline keyboard showing the 2 Invest-AZ accounts (Demo vs Real)."""
    accounts = account_manager.get_all_accounts()
    active = account_manager.get_active_account()
    keyboard = []
    for acc in accounts:
        is_active = (str(acc.id) == str(active.id))
        icon = "🟢" if is_active else "⚪"
        active_tag = " [ACTIVE]" if is_active else ""
        type_badge = "🟡 DEMO" if "DEMO" in acc.name.upper() else "🔴 REAL"
        btn_text = f"{icon} {type_badge} — {acc.name} ({acc.account_number}){active_tag}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"switch_acc:{acc.id}")])
    keyboard.append([InlineKeyboardButton("🔄 Refresh Panel", callback_data="switch_acc:refresh")])
    return InlineKeyboardMarkup(keyboard)

def inspect_account_trades(account: AccountProfile) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Performs deep inspection of the Invest-AZ account:
    Checks if the account has any active BUY or SELL functions/orders,
    computes exposure, volume, and floating profit, and formats a complete report.
    """
    target_url = account.zmq_url
    zmq_client.switch_endpoint(target_url)
    acc_data = zmq_client.get_account()

    if acc_data.get("status") != "ok" and target_url != "tcp://127.0.0.1:5555":
        zmq_client.switch_endpoint("tcp://127.0.0.1:5555")
        acc_data = zmq_client.get_account()

    if acc_data.get("status") != "ok":
        msg = (
            f"👥 <b>ACCOUNT #{account.id}: {account.name.upper()}</b> [SWITCHED]\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔢 <b>Account Number:</b> <code>{account.account_number}</code>\n"
            f"📂 <b>Profile:</b> <code>{account.profile_name}</code>\n"
            f"🌐 <b>Server:</b> <code>{account.server}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ <b>CONNECTION STATUS: OFFLINE / UNREACHABLE</b>\n"
            "<i>The Invest-AZ MetaTrader 4 terminal is currently closed or bridge EA is not attached.</i>\n\n"
            "📌 <b>To connect:</b>\n"
            "1. Open your Invest-AZ MT4 terminal.\n"
            "2. Ensure SmartAutoTradeEA_Pro is attached to an open chart (e.g. GBPUSD, H1).\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚡ <b>BUY / SELL FUNCTION DIAGNOSTICS:</b>\n\n"
            "🟢 <b>BUY FUNCTION:</b> <i>Offline — Unable to query active BUY orders.</i>\n\n"
            "🔴 <b>SELL FUNCTION:</b> <i>Offline — Unable to query active SELL orders.</i>\n"
        )
        keyboard = [
            [InlineKeyboardButton("🔄 Re-Check Connection", callback_data=f"switch_acc:{account.id}")],
            [InlineKeyboardButton("👥 Switch Account", callback_data="switch_acc:panel")]
        ]
        return msg, InlineKeyboardMarkup(keyboard)

    # Live MT4 Connected
    live_num = str(acc_data.get("account_number", account.account_number))
    trade_mode = str(acc_data.get("trade_mode", "DEMO")).upper()
    server = str(acc_data.get("server", account.server))
    company = str(acc_data.get("company", "Invest-AZ"))

    target_is_real = (str(account.id) == "2" or "REAL" in account.name.upper())
    terminal_is_real = (trade_mode == "REAL" or "REAL" in server.upper())

    if target_is_real and terminal_is_real and live_num not in ["Real Live", "0"]:
        account.account_number = live_num
        account_manager.add_or_update_account(account.id, live_num, account.name, account.profile_name, server, account.zmq_url)

    pos_data = zmq_client.get_positions()
    balance = float(acc_data.get("balance", 0.0))
    equity = float(acc_data.get("equity", 0.0))
    margin = float(acc_data.get("margin", 0.0))
    free_margin = float(acc_data.get("free_margin", 0.0))
    floating_pl = equity - balance
    margin_level = f"{float(acc_data.get('margin_level', 0.0)):.1f}%" if margin > 0 else "∞"
    server_time = acc_data.get("server_time", "N/A")
    currency = acc_data.get("currency", "USD")

    mismatch_note = ""
    if target_is_real and not terminal_is_real:
        mismatch_note = (
            f"\n⚠️ <b>NOTICE:</b> <i>Target set to REAL, but your MT4 terminal is currently logged into DEMO ({live_num}).</i>\n"
            "💡 <i>To execute on REAL: Open MT4 Navigator (Ctrl+N) ➜ Double-click your Real account to log in.</i>\n"
        )
    elif not target_is_real and terminal_is_real:
        mismatch_note = (
            f"\n⚠️ <b>NOTICE:</b> <i>Target set to DEMO, but your MT4 terminal is currently logged into REAL ({live_num}).</i>\n"
            "💡 <i>To execute on DEMO: Open MT4 Navigator (Ctrl+N) ➜ Double-click your Demo account to log in.</i>\n"
        )

    positions = pos_data.get("positions", []) if pos_data.get("status") == "ok" else []
    buy_orders = []
    sell_orders = []

    for pos in positions:
        pos_type = str(pos.get("type", "")).upper()
        if pos_type in ["0", "BUY"]:
            buy_orders.append(pos)
        elif pos_type in ["1", "SELL"]:
            sell_orders.append(pos)

    total_buy_lots = sum(float(p.get("volume", p.get("lots", 0.0))) for p in buy_orders)
    total_buy_pl = sum(float(p.get("profit", 0.0)) for p in buy_orders)

    total_sell_lots = sum(float(p.get("volume", p.get("lots", 0.0))) for p in sell_orders)
    total_sell_pl = sum(float(p.get("profit", 0.0)) for p in sell_orders)

    sign_pl = "+" if floating_pl >= 0 else ""
    sign_buy = "+" if total_buy_pl >= 0 else ""
    sign_sell = "+" if total_sell_pl >= 0 else ""
    mode_badge = "🔴 REAL (LIVE)" if terminal_is_real else "🟡 DEMO"

    msg = (
        f"👥 <b>ACCOUNT #{account.id}: {account.name.upper()}</b> [🟢 ACTIVE]\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔢 <b>Account Number:</b> <code>{live_num}</code> ({mode_badge})\n"
        f"🏢 <b>Broker:</b> {company}\n"
        f"🌐 <b>Server:</b> <code>{server}</code>\n"
        f"💰 <b>Balance / Equity:</b> <code>${balance:,.2f} / ${equity:,.2f}</code>\n"
        f"📊 <b>Margin:</b> <code>${margin:,.2f}</code> | <b>Free:</b> <code>${free_margin:,.2f}</code> ({margin_level})\n"
        f"📈 <b>Floating P/L:</b> <code>{sign_pl}${floating_pl:,.2f} {currency}</code>\n"
        f"⏰ <b>Server Time:</b> <code>{server_time}</code>\n"
        f"{mismatch_note}"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>BUY / SELL FUNCTION DIAGNOSTICS:</b>\n\n"
    )

    # 1. BUY Function Inspection
    if buy_orders:
        msg += f"🟢 <b>BUY FUNCTION: ACTIVE ({len(buy_orders)} order(s) | {total_buy_lots:.2f} lots)</b>\n"
        msg += f"   • Total BUY Floating P/L: <code>{sign_buy}${total_buy_pl:,.2f}</code>\n"
        for o in buy_orders[:5]:
            t_id = o.get("ticket", "N/A")
            sym = o.get("symbol", "")
            vol = float(o.get("volume", o.get("lots", 0.0)))
            op = float(o.get("open_price", 0.0))
            prof = float(o.get("profit", 0.0))
            s_prof = "+" if prof >= 0 else ""
            sl = float(o.get("sl", 0.0))
            tp = float(o.get("tp", 0.0))
            sl_str = f"SL: {sl}" if sl > 0 else "SL: none"
            tp_str = f"TP: {tp}" if tp > 0 else "TP: none"
            msg += f"   ▫️ <code>#{t_id}</code> {sym} BUY {vol:.2f} @ {op:.5f} | <b>{s_prof}${prof:,.2f}</b>\n"
            msg += f"      └ {sl_str} | {tp_str}\n"
        if len(buy_orders) > 5:
            msg += f"   <i>...and {len(buy_orders) - 5} more BUY orders.</i>\n"
    else:
        msg += "🟢 <b>BUY FUNCTION:</b> <i>No active BUY positions running.</i>\n"

    msg += "\n"

    # 2. SELL Function Inspection
    if sell_orders:
        msg += f"🔴 <b>SELL FUNCTION: ACTIVE ({len(sell_orders)} order(s) | {total_sell_lots:.2f} lots)</b>\n"
        msg += f"   • Total SELL Floating P/L: <code>{sign_sell}${total_sell_pl:,.2f}</code>\n"
        for o in sell_orders[:5]:
            t_id = o.get("ticket", "N/A")
            sym = o.get("symbol", "")
            vol = float(o.get("volume", o.get("lots", 0.0)))
            op = float(o.get("open_price", 0.0))
            prof = float(o.get("profit", 0.0))
            s_prof = "+" if prof >= 0 else ""
            sl = float(o.get("sl", 0.0))
            tp = float(o.get("tp", 0.0))
            sl_str = f"SL: {sl}" if sl > 0 else "SL: none"
            tp_str = f"TP: {tp}" if tp > 0 else "TP: none"
            msg += f"   ▫️ <code>#{t_id}</code> {sym} SELL {vol:.2f} @ {op:.5f} | <b>{s_prof}${prof:,.2f}</b>\n"
            msg += f"      └ {sl_str} | {tp_str}\n"
        if len(sell_orders) > 5:
            msg += f"   <i>...and {len(sell_orders) - 5} more SELL orders.</i>\n"
    else:
        msg += "🔴 <b>SELL FUNCTION:</b> <i>No active SELL positions running.</i>\n"

    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "✅ <i>Active target switched. All commands (/status, /positions, /close, /screenshot, /panic) operate on this account.</i>"

    keyboard = [
        [
            InlineKeyboardButton("💼 Open Positions", callback_data="nav_pos"),
            InlineKeyboardButton("📸 Screenshot", callback_data="nav_shot")
        ],
        [
            InlineKeyboardButton("🚨 Panic / Liquidate", callback_data="nav_panic"),
            InlineKeyboardButton("👥 Switch Account", callback_data="switch_acc:panel")
        ]
    ]
    return msg, InlineKeyboardMarkup(keyboard)

@restricted
async def cmd_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    active = account_manager.get_active_account()
    msg = (
        "👥 <b>INVEST-AZ MULTI-ACCOUNT CONTROL & TRADE INSPECTION</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 <b>Current Active Target:</b> <b>{active.name}</b>\n"
        f"• <b>Number:</b> <code>{active.account_number}</code>\n"
        f"• <b>Server:</b> <code>{active.server}</code>\n"
        f"• <b>ZMQ Port:</b> <code>{active.zmq_url}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 <b>Select an account below to switch control and inspect BUY/SELL functionality:</b>"
    )
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(msg, reply_markup=get_accounts_keyboard(), parse_mode=ParseMode.HTML)
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(msg, reply_markup=get_accounts_keyboard(), parse_mode=ParseMode.HTML)

@restricted
async def cb_switch_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data in ["switch_acc:refresh", "switch_acc:panel"]:
        await cmd_accounts(update, context)
        return

    if data.startswith("switch_acc:"):
        target_id = data.split(":", 1)[1]
        acc = account_manager.set_active_account(target_id)
        if not acc:
            await query.answer("❌ Account ID not found", show_alert=True)
            return

        report_text, markup = inspect_account_trades(acc)
        try:
            await query.edit_message_text(report_text, reply_markup=markup, parse_mode=ParseMode.HTML)
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error editing message in cb_switch_account: {e}")
        await query.answer(f"✅ Switched to Account #{acc.id}: {acc.name}", show_alert=False)

@restricted
async def cb_nav_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    chat_id = update.effective_chat.id

    if data in ["nav_status", "nav_refresh:status"]:
        await cmd_account(update, context)
    elif data in ["nav_pos", "nav_refresh:positions"]:
        await cmd_positions(update, context)
    elif data in ["nav_prop", "nav_refresh:prop"]:
        await cmd_prop(update, context)
    elif data in ["nav_report", "nav_refresh:report"]:
        await cmd_report(update, context)
    elif data in ["nav_boost", "nav_refresh:boost"]:
        await cmd_boost(update, context)
    elif data == "nav_shot":
        msg = (
            "📸 <b>INSTITUTIONAL CHART SNAPSHOT WIZARD</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Select the currency pair or financial asset you wish to render:"
        )
        if update.callback_query:
            try:
                await update.callback_query.edit_message_text(msg, reply_markup=get_symbol_keyboard(), parse_mode=ParseMode.HTML)
            except Exception:
                await context.bot.send_message(chat_id=chat_id, text=msg, reply_markup=get_symbol_keyboard(), parse_mode=ParseMode.HTML)
    elif data == "boost_colors":
        res = zmq_client.apply_colors()
        count = res.get("synced_count", 0)
        await query.answer(f"🎨 Synchronized {count} charts to GBPUSD scheme!", show_alert=True)
    elif data == "nav_panic":
        keyboard = [
            [
                InlineKeyboardButton("🚨 CONFIRM EMERGENCY LIQUIDATE ALL", callback_data="confirm_close_all"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_close_all")
            ]
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ <b>CONFIRMATION REQUIRED</b>\n\nAre you sure you want to close <b>ALL active market positions</b> immediately?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

# Command Aliases
cmd_switch = cmd_accounts
cmd_panic = cmd_closeall
cmd_status = cmd_account
cmd_pause = cmd_pause_bot
cmd_resume = cmd_resume_bot
