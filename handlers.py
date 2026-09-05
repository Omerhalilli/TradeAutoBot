"""
Telegram Command Handlers for MT4 ZeroMQ Bridge Bot.
Institutional Trading Terminal styling, robust validation, pagination,
inline quick navigation, and full remote MT4 control.
"""
import asyncio
import functools
import logging
import os
import time
from typing import Callable, List, Dict, Any, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import ALLOWED_CHAT_IDS, AUTOTRADE_FLAG_FILE, MT4_FILES_DIR
from zmq_client import zmq_client
from news_service import news_service, CURRENCY_FLAGS
from account_manager import account_manager, AccountProfile

logger = logging.getLogger(__name__)

async def zmq_async(func: Callable, *args, **kwargs) -> Any:
    """Dispatches blocking ZeroMQ socket I/O to a worker thread so the asyncio event loop never stalls."""
    return await asyncio.to_thread(func, *args, **kwargs)

async def safe_answer(query: Any, text: str = "", show_alert: bool = False) -> None:
    """Safely answers a Telegram callback query without crashing if already answered."""
    if not query:
        return
    try:
        if text:
            await query.answer(text, show_alert=show_alert)
        else:
            await query.answer()
    except Exception:
        pass

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
    """Normalizes financial instrument aliases and removes separators/whitespace."""
    s = symbol.strip().upper().replace("/", "").replace("\\", "").replace("-", "").replace(".", "").replace(" ", "")
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

async def send_or_edit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: InlineKeyboardMarkup = None,
    parse_mode: str = ParseMode.HTML
) -> None:
    """Helper to cleanly edit inline callback query messages or reply to messages without crashing."""
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return
        except Exception as e:
            if "Message is not modified" in str(e):
                return
            logger.debug(f"send_or_edit edit_message_text error: {e}")
    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    elif update.effective_chat and context and context.bot:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )

def get_offline_card(section_name: str = "status") -> Tuple[str, InlineKeyboardMarkup]:
    """Builds a consistent, elegant institutional offline bridge card."""
    active_acc = account_manager.get_active_account()
    msg = (
        "╔══════════════════════════════════╗\n"
        "   ⚠️ <b>MT4 ZERO-MQ BRIDGE OFFLINE</b>\n"
        "╚══════════════════════════════════╝\n"
        f"<b>Target Account:</b> <code>#{active_acc.id} • {active_acc.name}</code>\n"
        f"<b>Server Endpoint:</b> <code>{active_acc.zmq_url}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔴 <b>DIAGNOSTIC STATUS:</b>\n"
        "• MetaTrader 4 terminal unreachable or EA unattached.\n"
        "• ZeroMQ REP socket did not respond within 3000ms.\n\n"
        "👉 <b>Resolution Checklist:</b>\n"
        "1. Verify MetaTrader 4 is launched and logged in.\n"
        "2. Ensure <code>SmartAutoTradeEA_Pro</code> is attached to an active chart.\n"
        "3. Enable <i>'Allow DLL imports'</i> and <i>'Allow WebRequest'</i>.\n"
        "4. Click <b>🔄 Retry Connection</b> below once verified."
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Retry Connection", callback_data=f"nav_refresh:{section_name}"),
            InlineKeyboardButton("👥 Switch Account", callback_data="switch_acc:panel")
        ],
        [
            InlineKeyboardButton("⚡ Turbo Boost", callback_data="nav_boost"),
            InlineKeyboardButton("📅 Economic News", callback_data="news_filter:today")
        ]
    ])
    return msg, kb

def get_history_keyboard(active_filter: str = "all") -> InlineKeyboardMarkup:
    """Interactive filter keyboard for /history."""
    b_all = "🔟 Last 10" if active_filter != "10" else "🔟 • 10 •"
    b_today = "📅 Today" if active_filter != "today" else "📅 • Today •"
    b_week = "📆 This Week" if active_filter not in ["week", "lastweek"] else "📆 • Week •"
    
    keyboard = [
        [
            InlineKeyboardButton(b_all, callback_data="hist_filter:10"),
            InlineKeyboardButton(b_today, callback_data="hist_filter:today"),
            InlineKeyboardButton(b_week, callback_data="hist_filter:week"),
        ],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data=f"hist_filter:{active_filter}"),
            InlineKeyboardButton("📊 Account Status", callback_data="nav_status")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_news_keyboard(active_scope: str = "today") -> InlineKeyboardMarkup:
    """Interactive filter keyboard for /news."""
    b_today = "📅 Today" if active_scope != "today" else "📅 • Today •"
    b_week = "📆 This Week" if active_scope not in ["week", "thisweek"] else "📆 • Week •"
    keyboard = [
        [
            InlineKeyboardButton(b_today, callback_data="news_filter:today"),
            InlineKeyboardButton(b_week, callback_data="news_filter:week")
        ],
        [
            InlineKeyboardButton("🔄 Refresh News", callback_data=f"news_filter:{active_scope}"),
            InlineKeyboardButton("📊 Status", callback_data="nav_status")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

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
            InlineKeyboardButton("📜 History", callback_data="hist_filter:10"),
            InlineKeyboardButton("📅 News", callback_data="news_filter:today"),
            InlineKeyboardButton("🔄 Refresh", callback_data=f"nav_refresh:{active_section}")
        ],
        [
            InlineKeyboardButton("👥 Switch Account", callback_data="switch_acc:panel"),
            InlineKeyboardButton("🚨 Emergency Panic", callback_data="nav_panic")
        ]
    ]
    if active_section == "prop":
        keyboard.insert(2, [
            InlineKeyboardButton("🔄 Recalibrate Prop Anchors", callback_data="recalibrate_safeguards")
        ])
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
        mt4_files_dir = MT4_FILES_DIR
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
    try:
        acc_data = await zmq_async(zmq_client.get_account)
        if acc_data and acc_data.get("status") == "ok":
            account_manager.sync_with_live_terminal(acc_data)
    except Exception:
        pass
    active_acc = account_manager.get_active_account()
    mode_badge = "🔴 REAL (LIVE)" if "REAL" in active_acc.name.upper() else "🟡 DEMO"
    
    help_text = (
        "🏛️ <b>INVEST-AZ INSTITUTIONAL COMMAND CENTER</b>\n"
        f"👤 <b>Active Account:</b> <code>#{active_acc.id} • {active_acc.name}</code> ({mode_badge})\n"
        f"🌐 <b>Server:</b> <code>{active_acc.server}</code> | <b>Endpoint:</b> <code>{active_acc.zmq_url}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>TURBO & ORDER EXECUTION</b>\n"
        "• /buy <code>[SYM] [LOTS] [SL] [TP]</code> — Execute live market BUY order on MT4\n"
        "• /sell <code>[SYM] [LOTS] [SL] [TP]</code> — Execute live market SELL order on MT4\n"
        "• /trade or /order — Interactive 1-click Quick Trade panel\n"
        "• /boost — Instant latency diagnostics, live spreads & engine health\n"
        "• /status or /account — Account overview, equity, margin health & telemetry\n"
        "• /accounts or /switch — Multi-account switcher & BUY/SELL diagnostics\n\n"
        "💼 <b>PORTFOLIO & ORDER MANAGEMENT</b>\n"
        "• /positions — Active open orders with live P/L & tickets\n"
        "• /be <code>[SYM|TICKET] [PIPS]</code> — Move Stop Loss to Break-Even (+pips locked)\n"
        "• /trailing <code>[SYM|TICKET] [PIPS]</code> — Dynamic trailing stop management\n"
        "• /history — Closed trade deals, statistics & cumulative net P/L\n"
        "  └ <code>/history today</code> | <code>/history week</code> | <code>/history 20</code>\n"
        "• /close <code>[SYMBOL|TICKET]</code> — Liquidate positions for symbol or ticket\n"
        "• /modify_sl <code>[SYM|TICKET] [PRICE]</code> — Modify Stop Loss (0 to remove)\n"
        "• /modify_tp <code>[SYM|TICKET] [PRICE]</code> — Modify Take Profit (0 to remove)\n"
        "• /panic or /closeall — Emergency kill-switch (liquidate entire book)\n\n"
        "🛡️ <b>RISK GUARDIAN & PERFORMANCE</b>\n"
        "• /prop or /risk — Prop-firm risk scorecard, drawdown limits & target progress\n"
        "• /reset_risk — Recalibrate prop firm daily anchors & clear lockouts\n"
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
    await send_or_edit(update, context, help_text, reply_markup=get_nav_keyboard("help"))

@restricted
async def cmd_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = await zmq_async(zmq_client.get_account)
    if data.get("status") != "ok":
        card, kb = get_offline_card("status")
        await send_or_edit(update, context, card, reply_markup=kb)
        return

    active_acc = account_manager.sync_with_live_terminal(data)
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

    trade_allowed = data.get("is_trade_allowed", True)
    expert_enabled = data.get("is_expert_enabled", True)

    lock_warning = ""
    if not expert_enabled:
        lock_warning = (
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🚨 <b>AUTOTRADING IS LOCKED (OFF):</b>\n"
            "• MT4 AutoTrading toolbar button is currently OFF (Red).\n"
            "👉 <i>Fix: Click the 'AutoTrading' button in MT4 top toolbar to turn it green.</i>\n"
        )
    elif not trade_allowed:
        lock_warning = (
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🚨 <b>LIVE TRADING IS NOT PERMITTED:</b>\n"
            "• EA does not have live trading permission on this chart.\n"
            "👉 <i>Fix: Press F7 on chart ➜ 'Common' tab ➜ Check 'Allow live trading'.</i>\n"
        )

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
        f"{lock_warning}"
    )
    keyboard = get_nav_keyboard("status")
    await send_or_edit(update, context, msg, reply_markup=keyboard)

@restricted
async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = await zmq_async(zmq_client.get_positions)
    if data.get("status") != "ok":
        card, kb = get_offline_card("positions")
        await send_or_edit(update, context, card, reply_markup=kb)
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
        await send_or_edit(update, context, empty_msg, reply_markup=get_nav_keyboard("positions"))
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

    pos_action_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 Quick BUY 0.01", callback_data="trade:buy:GBPUSD:0.01"),
            InlineKeyboardButton("🔴 Quick SELL 0.01", callback_data="trade:sell:GBPUSD:0.01")
        ],
        [
            InlineKeyboardButton("📸 Active Screenshot", callback_data="shotsym:CURRENT"),
            InlineKeyboardButton("📅 Economic News", callback_data="news_filter:today")
        ],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="nav_refresh:positions"),
            InlineKeyboardButton("📊 Account Status", callback_data="nav_status")
        ]
    ])

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

        cur_kb = pos_action_kb if page_idx == total_pages - 1 else None
        
        if page_idx == 0 and update.callback_query:
            await send_or_edit(update, context, msg, reply_markup=cur_kb)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, reply_markup=cur_kb, parse_mode=ParseMode.HTML)

@restricted
async def cmd_boost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Turbo Boost Command: Rapid diagnostics, live latency test, spreads and engine health."""
    latency = await zmq_async(zmq_client.ping_latency_ms)
    boost_data = await zmq_async(zmq_client.get_boost)
    active_acc = account_manager.get_active_account()

    is_online = (boost_data.get("status") == "ok") or (latency > 0)

    if not is_online:
        msg = (
            "╔══════════════════════════════════╗\n"
            "   ⚡ <b>INSTITUTIONAL TURBO BOOST PANEL</b>\n"
            "╚══════════════════════════════════╝\n"
            f"👤 <b>Account #{active_acc.id}:</b> <code>{active_acc.name}</code> ({active_acc.account_number})\n"
            f"🌐 <b>Bridge Status:</b> 🔴 <b>OFFLINE / UNREACHABLE</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🚀 <b>ENGINE PERFORMANCE & TELEMETRY:</b>\n"
            "• <b>Roundtrip Latency:</b> <code>TIMEOUT (>3000 ms)</code> — 🔴 OFFLINE\n"
            "• <b>ZeroMQ Event Loop:</b> <code>Standby / Reconnecting</code>\n"
            "• <b>AutoTrading Engine:</b> 🔴 DISCONNECTED\n"
            "• <b>Active Exposure:</b> <i>Unavailable while offline</i>\n"
            "──────────────────────────\n"
            "📊 <b>MAJOR SPREADS TELEMETRY:</b>\n"
            "• 🇬🇧 <b>GBPUSD:</b> <i>Offline</i>\n"
            "• 🇪🇺 <b>EURUSD:</b> <i>Offline</i>\n"
            "• 🪙 <b>XAUUSD:</b> <i>Offline</i>\n"
            "──────────────────────────\n"
            "💡 <i>Verify MT4 is running with SmartAutoTradeEA_Pro attached to an active chart.</i>"
        )
        boost_keyboard = [
            [
                InlineKeyboardButton("🔄 Re-Run Boost Diagnostics", callback_data="nav_boost"),
                InlineKeyboardButton("👥 Switch Account", callback_data="switch_acc:panel")
            ],
            [
                InlineKeyboardButton("📊 Account Status", callback_data="nav_status"),
                InlineKeyboardButton("📅 Economic News", callback_data="news_filter:today")
            ]
        ]
        await send_or_edit(update, context, msg, reply_markup=InlineKeyboardMarkup(boost_keyboard))
        return

    # Online path
    bal = float(boost_data.get("balance", 0.0))
    eq = float(boost_data.get("equity", 0.0))
    orders_count = int(boost_data.get("active_orders", 0))
    float_pl = float(boost_data.get("floating_pl", 0.0))
    server_time = boost_data.get("server_time", "-")
    autotrade_active = boost_data.get("autotrading_active", True)
    spread_gbp = float(boost_data.get("spread_gbpusd", 10.0))
    spread_eur = float(boost_data.get("spread_eurusd", 10.0))
    spread_gold = float(boost_data.get("spread_xauusd", 25.0))

    if latency < 15.0:
        lat_badge = "🟢 ULTRA-FAST (Direct Fiber)"
    elif latency < 50.0:
        lat_badge = "🟡 ACCEPTABLE (VPS)"
    else:
        lat_badge = "🔴 HIGH LATENCY (Sub-optimal)"

    auto_badge = "ACTIVE & SCANNING 🟢" if autotrade_active else "PAUSED ⏸️"
    pl_sign = "+" if float_pl >= 0 else ""
    gbp_status = "🟢 Tight" if spread_gbp <= 12.0 else ("🟡 Normal" if spread_gbp <= 20.0 else "🔴 Wide")
    eur_status = "🟢 Tight" if spread_eur <= 12.0 else ("🟡 Normal" if spread_eur <= 20.0 else "🔴 Wide")
    gold_status = "🟢 Tight" if spread_gold <= 30.0 else ("🟡 Normal" if spread_gold <= 50.0 else "🔴 Wide")

    msg = (
        "╔══════════════════════════════════╗\n"
        "   ⚡ <b>INSTITUTIONAL TURBO BOOST PANEL</b>\n"
        "╚══════════════════════════════════╝\n"
        f"👤 <b>Account #{active_acc.id}:</b> <code>{active_acc.name}</code> ({active_acc.account_number})\n"
        f"🌐 <b>Bridge Status:</b> 🟢 <b>ACTIVE & STREAMING</b> | <b>Time:</b> <code>{server_time}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 <b>ENGINE PERFORMANCE & TELEMETRY:</b>\n"
        f"• <b>Roundtrip Latency:</b> <code>{latency:.2f} ms</code> — {lat_badge}\n"
        f"• <b>ZeroMQ Event Loop:</b> <code>250 ms (4 Hz)</code> High-Frequency\n"
        f"• <b>AutoTrading Engine:</b> {auto_badge}\n"
        f"• <b>Open Exposure:</b>     <code>{orders_count} orders</code> | Float: <b>{pl_sign}${float_pl:,.2f}</b>\n"
        "──────────────────────────\n"
        "📊 <b>LIVE MAJOR SPREADS TELEMETRY:</b>\n"
        f"• 🇬🇧 <b>GBPUSD:</b> <code>{spread_gbp:.1f} pts</code> ({gbp_status})\n"
        f"• 🇪🇺 <b>EURUSD:</b> <code>{spread_eur:.1f} pts</code> ({eur_status})\n"
        f"• 🪙 <b>XAUUSD:</b> <code>{spread_gold:.1f} pts</code> ({gold_status})\n"
        "──────────────────────────\n"
        "💎 <b>CAPITAL HEALTH:</b>\n"
        f"• <b>Balance:</b> <code>${bal:,.2f}</code> | <b>Equity:</b> <code>${eq:,.2f}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>RAPID TURBO CONTROLS:</b>"
    )

    boost_keyboard = [
        [
            InlineKeyboardButton("📸 Instant Snapshot", callback_data="shotsym:CURRENT"),
            InlineKeyboardButton("🎨 Sync GBPUSD Colors", callback_data="boost_colors")
        ],
        [
            InlineKeyboardButton("🛡️ Prop Guardian", callback_data="nav_prop"),
            InlineKeyboardButton("💼 Open Positions", callback_data="nav_pos")
        ],
        [
            InlineKeyboardButton("📅 Economic News", callback_data="news_filter:today"),
            InlineKeyboardButton("📜 Closed History", callback_data="hist_filter:10")
        ],
        [
            InlineKeyboardButton("🔄 Re-Run Boost Diagnostics", callback_data="nav_boost"),
            InlineKeyboardButton("📊 Back to Status", callback_data="nav_status")
        ]
    ]
    await send_or_edit(update, context, msg, reply_markup=InlineKeyboardMarkup(boost_keyboard))

@restricted
async def cmd_prop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = await zmq_async(zmq_client.get_prop)
    if data.get("status") != "ok":
        card, kb = get_offline_card("prop")
        await send_or_edit(update, context, card, reply_markup=kb)
        return

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
    await send_or_edit(update, context, msg, reply_markup=keyboard)

@restricted
async def cmd_reset_safeguards(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Recalibrates prop firm daily anchors, peak equity, and trips to live account equity."""
    data = await zmq_async(zmq_client.reset_safeguards)
    if data.get("status") != "ok":
        err_msg = (
            f"❌ <b>Recalibration Failed:</b>\n"
            f"<i>{data.get('message', 'ZeroMQ bridge unreachable.')}</i>"
        )
        await send_or_edit(update, context, err_msg)
        return

    acc_num = data.get("account", "-")
    eq = float(data.get("equity", 0.0))
    msg = (
        "╔══════════════════════════════════╗\n"
        "   🔄 <b>PROP SAFEGUARDS RECALIBRATED</b>\n"
        "╚══════════════════════════════════╝\n"
        f"• <b>Account:</b> <code>#{acc_num}</code>\n"
        f"• <b>Base Equity Anchor:</b> <code>${eq:,.2f}</code>\n"
        f"• <b>Daily Drawdown Circuit:</b> <b>RESET 🟢</b>\n"
        f"• <b>Lockout State:</b> <b>CLEARED 🔓</b>\n"
        f"• <b>Trading Engine:</b> <b>ACTIVE ▶️</b>\n\n"
        "✅ <i>All starting equity anchors have been successfully synchronized to live account equity.</i>"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛡️ View Prop Guard", callback_data="nav_prop"),
            InlineKeyboardButton("📊 Account Status", callback_data="nav_status")
        ]
    ])
    await send_or_edit(update, context, msg, reply_markup=kb)

@restricted
async def cb_reset_safeguards(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer("Recalibrating prop safeguards...")
    await cmd_reset_safeguards(update, context)

@restricted
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = await zmq_async(zmq_client.get_report)
    if data.get("status") != "ok":
        card, kb = get_offline_card("report")
        await send_or_edit(update, context, card, reply_markup=kb)
        return

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
    await send_or_edit(update, context, msg, reply_markup=keyboard)

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
            await send_or_edit(
                update,
                context,
                "ℹ️ <b>History Filter Usage:</b>\n"
                "• <code>/history</code> — Last 10 closed deals\n"
                "• <code>/history today</code> — Deals closed today\n"
                "• <code>/history week</code> — Deals closed this week\n"
                "• <code>/history 25</code> — Last N closed deals",
                reply_markup=get_history_keyboard(filter_type)
            )
            return

    data = await zmq_async(zmq_client.get_history, limit=limit, filter_type=filter_type)
    if data.get("status") != "ok":
        card, kb = get_offline_card("history")
        await send_or_edit(update, context, card, reply_markup=kb)
        return

    trades = data.get("trades", [])
    total_net = float(data.get("total_net_pl", 0.0))
    count = data.get("count", 0)

    filter_label = "TODAY" if filter_type == "today" else ("THIS WEEK" if filter_type == "lastweek" else f"LAST {limit}")

    if count == 0:
        empty_msg = (
            f"📜 <b>TRADE HISTORY AUDIT ({filter_label}):</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>No closed trade transactions recorded for this period.</i>"
        )
        await send_or_edit(update, context, empty_msg, reply_markup=get_history_keyboard(filter_type))
        return

    tot_icon = "🟢" if total_net >= 0 else "🔴"
    tot_sign = "+" if total_net >= 0 else ""

    header = (
        f"📜 <b>CLOSED TRADE HISTORY AUDIT ({filter_label} • {count} Deals)</b>\n"
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
            if page_idx == 0 and update.callback_query:
                await send_or_edit(update, context, msg, reply_markup=get_history_keyboard(filter_type))
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, reply_markup=get_history_keyboard(filter_type), parse_mode=ParseMode.HTML)
        else:
            if page_idx == 0 and update.callback_query:
                await send_or_edit(update, context, msg)
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode=ParseMode.HTML)

@restricted
async def cmd_breakeven(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Move Stop Loss to Break-Even for open profitable orders (+1 pip locked)."""
    args = context.args or []
    target_sym = ""
    ticket_num = 0
    lock_pips = 1

    if len(args) == 1:
        arg0 = args[0].strip()
        if arg0.isdigit():
            val = int(arg0)
            if val <= 100:  # User entered pips (e.g. /be 2 or /be 5)
                lock_pips = max(0, val)
                ticket_num = 0
            else:  # User entered ticket number (e.g. /be 1234567)
                ticket_num = val
        elif arg0.upper() not in ["ALL", "*"]:
            target_sym = clean_symbol(arg0)
    elif len(args) >= 2:
        arg0 = args[0].strip()
        if arg0.isdigit() and int(arg0) > 100:
            ticket_num = int(arg0)
        elif arg0.upper() not in ["ALL", "*"]:
            target_sym = clean_symbol(arg0)

        try:
            lock_pips = max(0, int(float(args[1])))
        except ValueError:
            lock_pips = 1

    data = await zmq_async(zmq_client.set_breakeven, symbol=target_sym, ticket=ticket_num, lock_pips=lock_pips)
    if data.get("status") != "ok":
        err_msg = (
            f"❌ <b>Break-Even Execution Failed:</b>\n"
            f"<i>{data.get('message', 'Terminal unreachable on ZeroMQ socket.')}</i>"
        )
        await send_or_edit(update, context, err_msg)
        return

    modified = data.get("modified_count", 0)
    skipped = data.get("skipped_count", 0)
    target_label = f"Ticket #{ticket_num}" if ticket_num > 0 else (target_sym if target_sym else "ALL OPEN POSITIONS")

    if modified == 0 and skipped == 0:
        msg = (
            "ℹ️ <b>NO ELIGIBLE ORDERS FOUND:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Target:</b> <code>{target_label}</code>\n"
            "• No open market orders matched the target query.\n"
            "• Open a position first or check active orders with /positions."
        )
    elif modified == 0 and skipped > 0:
        msg = (
            "⚠️ <b>BREAK-EVEN CRITERIA NOT MET:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Target:</b> <code>{target_label}</code>\n"
            f"• <b>Orders Evaluated:</b> <code>{skipped}</code>\n"
            f"• <b>Stop Losses Updated:</b> <code>0</code>\n\n"
            f"💡 <i>Break-Even protects profit and only triggers when a trade is in positive floating gain. Current trades have not exceeded entry + {lock_pips} pip buffer (or broker StopLevel distance) yet.</i>"
        )
    else:
        status_badge = "🟢 RISK ELIMINATED" if skipped == 0 else "🟡 PARTIALLY APPLIED"
        msg = (
            "🛡️ <b>BREAK-EVEN PROTECTION SYNCHRONIZED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Target:</b> <code>{target_label}</code>\n"
            f"• <b>Status:</b> <b>{status_badge}</b>\n"
            f"• <b>Orders Protected:</b> <b>{modified}</b>\n"
            f"• <b>Skipped (Not in Profit):</b> <code>{skipped}</code>\n"
            f"• <b>Profit Locked:</b> <b>+{lock_pips} pip(s)</b> above entry\n\n"
            "🔒 <i>Positions are now risk-free. If price reverses, capital is preserved.</i>"
        )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💼 View Positions", callback_data="nav_pos"),
            InlineKeyboardButton("📊 Account Status", callback_data="nav_status")
        ]
    ])
    await send_or_edit(update, context, msg, reply_markup=kb)

@restricted
async def cmd_trailing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Activate or adjust dynamic Trailing Stop on open profitable positions."""
    args = context.args or []
    target_sym = ""
    ticket_num = 0
    trail_pips = 20

    if len(args) == 1:
        arg0 = args[0].strip()
        if arg0.isdigit():
            val = int(arg0)
            if val <= 500:  # User entered pips (e.g. /trailing 25)
                trail_pips = max(5, val)
                ticket_num = 0
            else:  # User entered ticket number (e.g. /trailing 1234567)
                ticket_num = val
        elif arg0.upper() not in ["ALL", "*"]:
            target_sym = clean_symbol(arg0)
    elif len(args) >= 2:
        arg0 = args[0].strip()
        if arg0.isdigit() and int(arg0) > 500:
            ticket_num = int(arg0)
        elif arg0.upper() not in ["ALL", "*"]:
            target_sym = clean_symbol(arg0)

        try:
            trail_pips = max(5, int(float(args[1])))
        except ValueError:
            trail_pips = 20

    data = await zmq_async(zmq_client.set_trailing, symbol=target_sym, ticket=ticket_num, trail_pips=trail_pips)
    if data.get("status") != "ok":
        err_msg = (
            f"❌ <b>Trailing Stop Execution Failed:</b>\n"
            f"<i>{data.get('message', 'Terminal unreachable on ZeroMQ socket.')}</i>"
        )
        await send_or_edit(update, context, err_msg)
        return

    modified = data.get("modified_count", 0)
    skipped = data.get("skipped_count", 0)
    target_label = f"Ticket #{ticket_num}" if ticket_num > 0 else (target_sym if target_sym else "ALL OPEN POSITIONS")

    if modified == 0 and skipped == 0:
        msg = (
            "ℹ️ <b>NO ELIGIBLE ORDERS FOUND:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Target:</b> <code>{target_label}</code>\n"
            "• No open market orders matched the target query."
        )
    elif modified == 0 and skipped > 0:
        msg = (
            "⚠️ <b>TRAILING STOP CRITERIA NOT MET:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Target:</b> <code>{target_label}</code>\n"
            f"• <b>Orders Evaluated:</b> <code>{skipped}</code>\n"
            f"• <b>Stop Losses Stepped:</b> <code>0</code>\n\n"
            f"💡 <i>Trailing Stop steps SL forward only after profit exceeds the {trail_pips} pip threshold. Existing SL levels are already at optimal protection.</i>"
        )
    else:
        msg = (
            "⚡ <b>TRAILING STOP SYNCHRONIZED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Target:</b> <code>{target_label}</code>\n"
            f"• <b>Orders Updated:</b> <b>{modified}</b>\n"
            f"• <b>Trailing Distance:</b> <code>{trail_pips} pips</code>\n"
            f"• <b>Skipped:</b> <code>{skipped}</code>\n\n"
            "📈 <i>Stop Loss will step forward as market price advances in your favor.</i>"
        )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💼 View Positions", callback_data="nav_pos"),
            InlineKeyboardButton("📊 Account Status", callback_data="nav_status")
        ]
    ])
    await send_or_edit(update, context, msg, reply_markup=kb)

@restricted
async def cmd_close_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if not args:
        guide_msg = (
            "ℹ️ <b>Close Order Usage:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• <code>/close SYMBOL</code> — Close all trades for symbol (e.g. <code>/close GBPUSD</code>, <code>/close GOLD</code>)\n"
            "• <code>/close TICKET</code> — Close specific ticket (e.g. <code>/close 35183711</code>)\n"
            "• <code>/panic</code> or <code>/close all</code> — Liquidate entire book immediately"
        )
        await send_or_edit(update, context, guide_msg)
        return

    arg0 = args[0].strip().upper()
    if arg0 in ["ALL", "*"]:
        await cmd_closeall(update, context)
        return

    target = clean_symbol(args[0])
    data = await zmq_async(zmq_client.close_symbol, target)
    if data.get("status") != "ok":
        await send_or_edit(update, context, f"❌ <b>Execution Error:</b> {data.get('message')}")
        return

    closed = data.get("closed_count", 0)
    failed = data.get("failed_count", 0)
    realized = float(data.get("realized_pl", 0.0))
    r_sign = "+" if realized >= 0 else ""

    if closed == 0 and failed == 0:
        await send_or_edit(
            update,
            context,
            f"ℹ️ <b>No Open Trades Found:</b> No active market orders match target <code>{target}</code>."
        )
        return

    if closed > 0 and failed == 0:
        badge = "🎯 <b>LIQUIDATION COMPLETED</b>"
    elif closed > 0 and failed > 0:
        badge = "⚠️ <b>PARTIALLY LIQUIDATED</b>"
    else:
        badge = "❌ <b>LIQUIDATION FAILED</b>"

    msg = (
        f"{badge}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Target:</b> <code>{target}</code>\n"
        f"• <b>Orders Closed:</b> <b>{closed}</b>\n"
        f"• <b>Orders Failed:</b> <b>{failed}</b>\n"
        f"• <b>Realized P/L:</b>  <b>{r_sign}${realized:,.2f}</b>"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💼 View Positions", callback_data="nav_pos"),
            InlineKeyboardButton("📊 Status Panel", callback_data="nav_status")
        ]
    ])
    await send_or_edit(update, context, msg, reply_markup=kb)

@restricted
async def cmd_modify_sl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if len(args) < 2:
        guide_msg = (
            "ℹ️ <b>Modify Stop Loss Usage:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• <code>/modify_sl SYMBOL PRICE</code> — e.g. <code>/modify_sl GBPUSD 1.3520</code>\n"
            "• <code>/modify_sl TICKET PRICE</code> — e.g. <code>/modify_sl 35183711 1.3520</code>\n"
            "• <code>/modify_sl GBPUSD 0</code> — Remove Stop Loss"
        )
        await send_or_edit(update, context, guide_msg)
        return

    target = clean_symbol(args[0])
    try:
        sl_price = float(args[1])
        if sl_price < 0.0:
            raise ValueError("Negative price")
    except ValueError:
        await send_or_edit(update, context, "❌ <b>Invalid Price:</b> Stop Loss price must be a valid non-negative number.")
        return

    if target.isdigit():
        data = await zmq_async(zmq_client.modify_sl, ticket=int(target), sl=sl_price)
    else:
        data = await zmq_async(zmq_client.modify_sl, symbol=target, sl=sl_price)

    if data.get("status") != "ok":
        await send_or_edit(update, context, f"❌ <b>Error Modifying SL:</b> {data.get('message')}")
        return

    count = data.get("modified_count", 0)
    if count == 0:
        await send_or_edit(
            update,
            context,
            f"ℹ️ <b>No Orders Updated:</b> No open trades matching target <code>{target}</code> were found."
        )
        return

    sl_action = "Removed (0.0)" if sl_price == 0.0 else f"<code>{sl_price}</code>"
    msg = (
        "✅ <b>STOP LOSS SYNCHRONIZED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Target:</b> <code>{target}</code>\n"
        f"• <b>New SL Level:</b> {sl_action}\n"
        f"• <b>Orders Updated:</b> <b>{count}</b>"
    )
    await send_or_edit(update, context, msg)

@restricted
async def cmd_modify_tp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if len(args) < 2:
        guide_msg = (
            "ℹ️ <b>Modify Take Profit Usage:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• <code>/modify_tp SYMBOL PRICE</code> — e.g. <code>/modify_tp GBPUSD 1.3650</code>\n"
            "• <code>/modify_tp TICKET PRICE</code> — e.g. <code>/modify_tp 35183711 1.3650</code>\n"
            "• <code>/modify_tp GBPUSD 0</code> — Remove Take Profit"
        )
        await send_or_edit(update, context, guide_msg)
        return

    target = clean_symbol(args[0])
    try:
        tp_price = float(args[1])
        if tp_price < 0.0:
            raise ValueError("Negative price")
    except ValueError:
        await send_or_edit(update, context, "❌ <b>Invalid Price:</b> Take Profit price must be a valid non-negative number.")
        return

    if target.isdigit():
        data = await zmq_async(zmq_client.modify_tp, ticket=int(target), tp=tp_price)
    else:
        data = await zmq_async(zmq_client.modify_tp, symbol=target, tp=tp_price)

    if data.get("status") != "ok":
        await send_or_edit(update, context, f"❌ <b>Error Modifying TP:</b> {data.get('message')}")
        return

    count = data.get("modified_count", 0)
    if count == 0:
        await send_or_edit(
            update,
            context,
            f"ℹ️ <b>No Orders Updated:</b> No open trades matching target <code>{target}</code> were found."
        )
        return

    tp_action = "Removed (0.0)" if tp_price == 0.0 else f"<code>{tp_price}</code>"
    msg = (
        "✅ <b>TAKE PROFIT SYNCHRONIZED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Target:</b> <code>{target}</code>\n"
        f"• <b>New TP Level:</b> {tp_action}\n"
        f"• <b>Orders Updated:</b> <b>{count}</b>"
    )
    await send_or_edit(update, context, msg)

@restricted
async def cmd_closeall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompts for confirmation before closing all open trades."""
    pos_data = await zmq_async(zmq_client.get_positions)
    count = pos_data.get("count", 0)
    
    keyboard = [
        [
            InlineKeyboardButton(f"🚨 YES, CLOSE ALL ({count} POSITIONS)", callback_data="confirm_close_all"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_close_all")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_or_edit(
        update,
        context,
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
        data = await zmq_async(zmq_client.close_all)
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
    data = await zmq_async(zmq_client.pause_bot)
    conn_note = "" if data.get("status") == "ok" else " (Note: MT4 bridge offline; flag will apply upon restart)"

    msg = (
        "⏸️ <b>AUTOTRADING PAUSED BY REMOTE COMMAND</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "• State flag <code>autotrade_state.flag</code> set to <b>PAUSED</b>\n"
        "• Global Variable <code>AutoTrading_Paused</code> set to <b>1.0</b>\n"
        f"• AutoTrading EAs will immediately freeze all new order placement.{conn_note}"
    )
    await send_or_edit(update, context, msg, reply_markup=get_nav_keyboard("status"))

@restricted
async def cmd_resume_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    write_autotrade_flag("ACTIVE")
    data = await zmq_async(zmq_client.resume_bot)
    conn_note = "" if data.get("status") == "ok" else " (Note: MT4 bridge offline; flag will apply upon restart)"

    msg = (
        "▶️ <b>AUTOTRADING RESUMED BY REMOTE COMMAND</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "• State flag <code>autotrade_state.flag</code> set to <b>ACTIVE</b>\n"
        "• Global Variable <code>AutoTrading_Paused</code> set to <b>0.0</b>\n"
        f"• AutoTrading EAs have resumed full scanning and order execution.{conn_note}"
    )
    await send_or_edit(update, context, msg, reply_markup=get_nav_keyboard("status"))

@restricted
async def cmd_colors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = await zmq_async(zmq_client.apply_colors)
    if data.get("status") != "ok":
        await send_or_edit(update, context, f"⚠️ <b>MT4 Error:</b> {data.get('message', 'Failed to apply colors')}")
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
    await send_or_edit(update, context, msg, reply_markup=get_nav_keyboard("status"))

@restricted
async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    scope = "today"
    if args and args[0].lower() in ["week", "thisweek"]:
        events = news_service.get_week_events()
        title = "This Week's High-Impact Economic Calendar"
        scope = "week"
    else:
        events = news_service.get_today_events()
        title = "Today's High-Impact Economic Calendar"
        scope = "today"

    messages = news_service.format_news_messages(events, title)
    kb = get_news_keyboard(scope)
    for i, msg in enumerate(messages):
        cur_kb = kb if i == len(messages) - 1 else None
        if i == 0:
            await send_or_edit(update, context, msg, reply_markup=cur_kb)
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=msg,
                reply_markup=cur_kb,
                parse_mode=ParseMode.HTML
            )

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
        tf = args[1].upper() if len(args) > 1 else "H1"
        status_msg = await update.effective_message.reply_text(
            f"⏳ <i>Capturing chart for <b>{sym}</b> ({tf})...</i>",
            parse_mode=ParseMode.HTML
        )
        ok = await execute_screenshot_delivery(update.effective_chat.id, context, sym, tf)
        if ok:
            try:
                await status_msg.delete()
            except Exception:
                pass
        else:
            await status_msg.edit_text(
                f"⚠️ <b>Capture Failed:</b> MT4 bridge unreachable or chart window unavailable for <code>{sym}</code> ({tf}).",
                parse_mode=ParseMode.HTML
            )
        return

    msg = (
        "📸 <b>INSTITUTIONAL CHART SNAPSHOT WIZARD</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Select the currency pair or financial asset you wish to render:"
    )
    await send_or_edit(update, context, msg, reply_markup=get_symbol_keyboard())

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
    data = await zmq_async(zmq_client.get_screenshot, symbol=symbol, timeframe=timeframe)
    if data.get("status") != "ok":
        return False

    shot_filename = data.get("filename", "chart_screenshot.png")
    sym = data.get("symbol", symbol)
    tf = data.get("timeframe", timeframe).replace("PERIOD_", "")
    bid = data.get("bid", 0.0)
    ask = data.get("ask", 0.0)
    server_time = data.get("server_time", "")

    mt4_files_dir = MT4_FILES_DIR
    shot_path = os.path.join(mt4_files_dir, shot_filename)

    # Wait up to 2.5 seconds for MT4 graphics engine to flush image file to disk
    file_ready = False
    for _ in range(25):
        if os.path.exists(shot_path) and os.path.getsize(shot_path) > 500:
            file_ready = True
            break
        await asyncio.sleep(0.1)

    if not file_ready:
        logger.warning(f"Screenshot file {shot_path} not ready after wait.")
        return False

    caption = (
        f"📸 <b>INSTITUTIONAL CHART TELEMETRY</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Asset:</b> <code>{sym}</code>  •  <b>Timeframe:</b> <code>{tf}</code>\n"
        f"• <b>Market Quote:</b> <code>{bid} / {ask}</code>\n"
        f"• <b>Server Time:</b> <code>{server_time}</code>"
    )
    kb_shot = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💼 Active Positions", callback_data="nav_pos"),
            InlineKeyboardButton("📊 Account Status", callback_data="nav_status")
        ],
        [
            InlineKeyboardButton("🔄 Retake Screenshot", callback_data=f"shottf:{sym}:{tf}"),
            InlineKeyboardButton("📸 All Symbols", callback_data="shotsym:BACK")
        ]
    ])
    with open(shot_path, "rb") as photo_file:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo_file,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=kb_shot
        )
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
            InlineKeyboardButton("🟢 Quick BUY 0.01", callback_data="trade:buy:GBPUSD:0.01"),
            InlineKeyboardButton("🔴 Quick SELL 0.01", callback_data="trade:sell:GBPUSD:0.01")
        ],
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
    try:
        acc_data = await zmq_async(zmq_client.get_account)
        if acc_data and acc_data.get("status") == "ok":
            account_manager.sync_with_live_terminal(acc_data)
    except Exception:
        pass
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
    data = query.data or ""

    if data in ["switch_acc:refresh", "switch_acc:panel"]:
        await safe_answer(query)
        await cmd_accounts(update, context)
        return

    if data.startswith("switch_acc:"):
        target_id = data.split(":", 1)[1]
        acc = account_manager.set_active_account(target_id)
        if not acc:
            await safe_answer(query, "❌ Account ID not found", show_alert=True)
            return

        report_text, markup = await zmq_async(inspect_account_trades, acc)
        try:
            await query.edit_message_text(report_text, reply_markup=markup, parse_mode=ParseMode.HTML)
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error editing message in cb_switch_account: {e}")
        await safe_answer(query, f"✅ Switched to Account #{acc.id}: {acc.name}", show_alert=False)

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
        await send_or_edit(update, context, msg, reply_markup=get_symbol_keyboard())
    elif data == "boost_colors":
        res = await zmq_async(zmq_client.apply_colors)
        count = res.get("synced_count", 0)
        await query.answer(f"🎨 Synchronized {count} charts to GBPUSD scheme!", show_alert=True)
    elif data == "nav_panic":
        await cmd_closeall(update, context)
    elif data in ["recalibrate_safeguards", "nav_reset_risk"]:
        await cmd_reset_safeguards(update, context)
    elif data in ["nav_strategies", "nav_chart", "nav_menu"]:
        try:
            from autotrade.telegram_interface.command_router import command_router
            await command_router.handle_callback_query(update, context)
        except Exception as e:
            logger.error(f"Error delegating {data} to command_router: {e}")

@restricted
async def cb_history_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles 1-tap history filtering (Last 10, Today, Week)."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    filter_val = data.split(":", 1)[1] if ":" in data else "10"
    context.args = [filter_val]
    await cmd_history(update, context)

@restricted
async def cb_news_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles 1-tap economic calendar filtering (Today, Week)."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    scope_val = data.split(":", 1)[1] if ":" in data else "today"
    context.args = [scope_val]
    await cmd_news(update, context)

@restricted
async def cb_ea_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles 1-tap trade liquidation from EA notification buttons (e.g. /close_12345)."""
    query = update.callback_query
    data = query.data or ""
    raw_ticket = data.lstrip("/").split("_", 1)[1] if "_" in data else ""
    ticket_str = raw_ticket.split("@", 1)[0].strip()
    if not ticket_str.isdigit():
        await safe_answer(query, "❌ Invalid ticket parameter", show_alert=True)
        return

    res = await zmq_async(zmq_client.close_symbol, ticket_str)
    if res.get("status") == "ok" and res.get("closed_count", 0) > 0:
        r_pl = float(res.get("realized_pl", 0.0))
        sign = "+" if r_pl >= 0 else ""
        await safe_answer(query, f"✅ Order #{ticket_str} Liquidated ({sign}${r_pl:,.2f})", show_alert=True)
        msg = (
            "🏁 <b>POSITION LIQUIDATED BY REMOTE COMMAND</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Ticket:</b> <code>#{ticket_str}</code>\n"
            f"• <b>Realized P/L:</b> <b>{sign}${r_pl:,.2f}</b>\n"
            "• <i>Market exposure closed successfully.</i>"
        )
        await send_or_edit(update, context, msg, reply_markup=get_nav_keyboard("status"))
    else:
        err = res.get("message", "Order already closed or MT4 offline")
        await safe_answer(query, f"❌ Failed: {err}", show_alert=True)

@restricted
async def cb_ea_half(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles 50% partial close from EA notification buttons (e.g. /half_12345)."""
    query = update.callback_query
    data = query.data or ""
    raw_ticket = data.lstrip("/").split("_", 1)[1] if "_" in data else ""
    ticket_str = raw_ticket.split("@", 1)[0].strip()
    if not ticket_str.isdigit():
        await safe_answer(query, "❌ Invalid ticket parameter", show_alert=True)
        return

    res = await zmq_async(zmq_client.close_half, int(ticket_str))
    if res.get("status") == "ok":
        closed_lots = float(res.get("closed_lots", 0.0))
        rem_lots = float(res.get("remaining_lots", 0.0))
        r_pl = float(res.get("realized_pl", 0.0))
        sign = "+" if r_pl >= 0 else ""
        await safe_answer(query, f"✂️ Closed {closed_lots:.2f}L on #{ticket_str} ({sign}${r_pl:,.2f})", show_alert=True)
        msg = (
            "✂️ <b>50% PARTIAL CLOSE COMPLETED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Ticket:</b> <code>#{ticket_str}</code>\n"
            f"• <b>Closed Volume:</b> <code>{closed_lots:.2f} lots</code>\n"
            f"• <b>Remaining Volume:</b> <code>{rem_lots:.2f} lots</code>\n"
            f"• <b>Realized P/L:</b> <b>{sign}${r_pl:,.2f}</b>"
        )
        await send_or_edit(update, context, msg, reply_markup=get_nav_keyboard("positions"))
    else:
        err = res.get("message", "MT4 offline or position unavailable")
        await safe_answer(query, f"❌ Partial close failed: {err}", show_alert=True)

@restricted
async def cb_ea_be(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles 1-tap Break-Even from EA notification buttons (e.g. /be_12345)."""
    query = update.callback_query
    data = query.data or ""
    raw_ticket = data.lstrip("/").split("_", 1)[1] if "_" in data else ""
    ticket_str = raw_ticket.split("@", 1)[0].strip()
    if not ticket_str.isdigit():
        await safe_answer(query, "❌ Invalid ticket parameter", show_alert=True)
        return

    res = await zmq_async(zmq_client.set_breakeven, ticket=int(ticket_str), lock_pips=1)
    if res.get("status") == "ok" and res.get("modified_count", 0) > 0:
        await safe_answer(query, f"🛡️ Break-Even active for #{ticket_str} (+1 pip locked)!", show_alert=True)
        msg = (
            "🛡️ <b>BREAK-EVEN SYNCHRONIZED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Ticket:</b> <code>#{ticket_str}</code>\n"
            "• <b>Status:</b> <b>Risk-Free (Profit Protected)</b>\n"
            "• <b>Locked Buffer:</b> +1 pip above entry"
        )
        await send_or_edit(update, context, msg, reply_markup=get_nav_keyboard("positions"))
    elif res.get("skipped_count", 0) > 0:
        await safe_answer(query, f"⚠️ Position #{ticket_str} is not in profit yet (+1 pip threshold).", show_alert=True)
    else:
        err = res.get("message", "Order not found or already closed")
        await safe_answer(query, f"❌ Failed: {err}", show_alert=True)

@restricted
async def cb_ea_shot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles 1-tap chart snapshot from EA notification buttons (e.g. /shot_GBPUSD_H1)."""
    query = update.callback_query
    data = query.data or ""
    parts = data.lstrip("/").split("_")
    sym = parts[1] if len(parts) > 1 else "CURRENT"
    tf = parts[2] if len(parts) > 2 else "H1"
    await query.answer(f"Capturing {sym} ({tf})...", show_alert=False)
    chat_id = update.effective_chat.id
    success = await execute_screenshot_delivery(chat_id, context, sym, tf)
    if not success:
        await send_or_edit(update, context, f"⚠️ Failed to capture chart for {sym} ({tf}).")

def _parse_trade_args(args: list[str], default_action: str = "") -> dict:
    """
    Parses command arguments for trade execution:
    /buy 0.01
    /buy EURGBP 0.01
    /sell EURUSD 0.05 sl=20p tp=40p
    /trade buy GBPUSD 0.1
    /order sell XAUUSD 0.02
    """
    action = default_action.upper()
    symbol = ""
    lots = 0.01
    sl = 0.0
    tp = 0.0
    sl_pips = 0.0
    tp_pips = 0.0
    magic = 8882026
    comment = "TelegramTrade"

    for arg in args:
        arg_clean = arg.strip()
        if not arg_clean:
            continue

        if "=" in arg_clean:
            k, v = arg_clean.split("=", 1)
            k = k.lower().strip()
            v_low = v.strip().lower()
            try:
                if v_low.endswith("pips") or v_low.endswith("pip") or v_low.endswith("p"):
                    num_val = float(v_low.rstrip("pips").rstrip("pip").rstrip("p").strip())
                    if k in ["sl", "stoploss", "stop", "sl_pips"]:
                        sl_pips = num_val
                    elif k in ["tp", "takeprofit", "take", "tp_pips"]:
                        tp_pips = num_val
                elif k in ["sl", "stoploss", "stop"]:
                    sl = float(v)
                elif k in ["tp", "takeprofit", "take"]:
                    tp = float(v)
                elif k in ["sl_pips", "slpips"]:
                    sl_pips = float(v)
                elif k in ["tp_pips", "tppips"]:
                    tp_pips = float(v)
                elif k in ["lots", "lot", "vol", "volume"]:
                    lots = float(v)
                elif k in ["magic", "id"]:
                    magic = int(v)
                elif k in ["comment", "com"]:
                    comment = v
            except ValueError:
                pass
            continue

        upper_token = arg_clean.upper()
        if upper_token in ["BUY", "SELL"] and not action:
            action = upper_token
            continue

        try:
            val = float(arg_clean)
            lots = val
            continue
        except ValueError:
            pass

        if not symbol and len(arg_clean) >= 2:
            symbol = clean_symbol(arg_clean)

    if not symbol:
        symbol = "GBPUSD"

    if not action:
        action = "BUY"

    lots = max(0.01, min(100.0, round(lots, 2)))

    return {
        "action": action,
        "symbol": symbol,
        "lots": lots,
        "sl": sl,
        "tp": tp,
        "sl_pips": sl_pips,
        "tp_pips": tp_pips,
        "magic": magic,
        "comment": comment
    }

async def _execute_and_report_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    parsed: dict
) -> None:
    sym = parsed["symbol"]
    act = parsed["action"]
    lots = parsed["lots"]
    sl = parsed["sl"]
    tp = parsed["tp"]
    sl_p = parsed.get("sl_pips", 0.0)
    tp_p = parsed.get("tp_pips", 0.0)
    magic = parsed["magic"]
    comment = parsed["comment"]

    if not sym:
        try:
            acc = await zmq_async(zmq_client.get_account)
            sym = acc.get("chart_symbol", "")
        except Exception:
            sym = ""
        if not sym:
            sym = "EURGBP"

    reply_target = update.message or (update.callback_query.message if update.callback_query else None)
    status_msg = None
    if reply_target:
        try:
            status_msg = await reply_target.reply_text(
                f"⏳ <i>Dispatching {act} {lots:.2f} {sym} to MetaTrader 4 via ZeroMQ...</i>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

    res = await zmq_async(
        zmq_client.open_order,
        symbol=sym,
        cmd=act,
        lots=lots,
        sl=sl,
        tp=tp,
        sl_pips=sl_p,
        tp_pips=tp_p,
        magic=magic,
        comment=comment
    )

    if res.get("status") == "ok":
        ticket = res.get("ticket", 0)
        open_price = float(res.get("price", 0.0))
        exec_lots = float(res.get("lots", lots))
        res_sym = res.get("symbol", sym)
        res_sl = float(res.get("sl", sl))
        res_tp = float(res.get("tp", tp))
        retries = res.get("retries", 0)

        icon = "🟢 BUY" if act == "BUY" else "🔴 SELL"
        sl_text = f"<code>{res_sl}</code>" if res_sl > 0 else "<i>None</i>"
        tp_text = f"<code>{res_tp}</code>" if res_tp > 0 else "<i>None</i>"

        msg = (
            f"✅ <b>ORDER EXECUTED ON MT4 TERMINAL</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Ticket:</b> <code>#{ticket}</code>\n"
            f"• <b>Order:</b> <b>{icon} {exec_lots:.2f} {res_sym}</b>\n"
            f"• <b>Fill Price:</b> <code>{open_price:.5f}</code>\n"
            f"• <b>Stop Loss:</b> {sl_text} | <b>Take Profit:</b> {tp_text}\n"
            f"• <b>Execution:</b> ZeroMQ Bridge (retries: {retries})\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Quick Actions for this position:</i>"
        )
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🛡️ Set Break-Even", callback_data=f"/be_{ticket}"),
                InlineKeyboardButton("✂️ Close 50%", callback_data=f"/half_{ticket}")
            ],
            [
                InlineKeyboardButton("📸 Chart Snapshot", callback_data=f"shotsym:{res_sym}"),
                InlineKeyboardButton("🏁 Close Order", callback_data=f"/close_{ticket}")
            ],
            [
                InlineKeyboardButton("💼 Open Positions", callback_data="nav_pos"),
                InlineKeyboardButton("📊 Account Status", callback_data="nav_status")
            ]
        ])
        if status_msg:
            try:
                await status_msg.edit_text(msg, reply_markup=kb, parse_mode=ParseMode.HTML)
                return
            except Exception:
                pass
        if reply_target:
            await reply_target.reply_text(msg, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        err_msg = res.get("message", "Unknown execution error")
        code = res.get("error_code", "")
        code_str = f" [Code: {code}]" if code else ""
        icon = "🟢 BUY" if act == "BUY" else "🔴 SELL"

        msg = (
            f"❌ <b>MT4 ORDER REJECTED{code_str}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Attempted:</b> {icon} {lots:.2f} {sym}\n"
            f"• <b>Reason:</b> <i>{err_msg}</i>\n\n"
            "💡 <b>Troubleshooting:</b>\n"
            "1. Make sure MT4 'AutoTrading' toolbar button is green.\n"
            "2. Make sure EA has 'Allow live trading' checked (F7 -> Common).\n"
            "3. If error 132: Market is closed (FX pairs trade Mon-Fri)."
        )
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Re-Check Account", callback_data="nav_status"),
                InlineKeyboardButton("💼 Positions", callback_data="nav_pos")
            ]
        ])
        if status_msg:
            try:
                await status_msg.edit_text(msg, reply_markup=kb, parse_mode=ParseMode.HTML)
                return
            except Exception:
                pass
        if reply_target:
            await reply_target.reply_text(msg, reply_markup=kb, parse_mode=ParseMode.HTML)

@restricted
async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Executes a BUY market order on MT4."""
    args = context.args or []
    if not args:
        guide_msg = (
            "🟢 <b>QUICK BUY EXECUTION WIZARD</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• <code>/buy GBPUSD 0.01</code>\n"
            "• <code>/buy EURUSD 0.05 sl=1.0800 tp=1.0950</code>\n"
            "• <code>/buy GOLD 0.02</code>\n\n"
            "👇 <i>Or tap a quick 1-tap trade button below:</i>"
        )
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🟢 BUY GBPUSD 0.01", callback_data="trade:buy:GBPUSD:0.01"),
                InlineKeyboardButton("🟢 BUY EURUSD 0.01", callback_data="trade:buy:EURUSD:0.01")
            ],
            [
                InlineKeyboardButton("🟢 BUY XAUUSD 0.01", callback_data="trade:buy:XAUUSD:0.01"),
                InlineKeyboardButton("🟢 BUY BTCUSD 0.01", callback_data="trade:buy:BTCUSD:0.01")
            ],
            [
                InlineKeyboardButton("💼 View Positions", callback_data="nav_pos"),
                InlineKeyboardButton("📊 Account Status", callback_data="nav_status")
            ]
        ])
        await send_or_edit(update, context, guide_msg, reply_markup=kb)
        return

    parsed = _parse_trade_args(args, default_action="BUY")
    await _execute_and_report_order(update, context, parsed)

@restricted
async def cmd_sell(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Executes a SELL market order on MT4."""
    args = context.args or []
    if not args:
        guide_msg = (
            "🔴 <b>QUICK SELL EXECUTION WIZARD</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• <code>/sell GBPUSD 0.01</code>\n"
            "• <code>/sell EURUSD 0.05 sl=1.0950 tp=1.0800</code>\n"
            "• <code>/sell GOLD 0.02</code>\n\n"
            "👇 <i>Or tap a quick 1-tap trade button below:</i>"
        )
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔴 SELL GBPUSD 0.01", callback_data="trade:sell:GBPUSD:0.01"),
                InlineKeyboardButton("🔴 SELL EURUSD 0.01", callback_data="trade:sell:EURUSD:0.01")
            ],
            [
                InlineKeyboardButton("🔴 SELL XAUUSD 0.01", callback_data="trade:sell:XAUUSD:0.01"),
                InlineKeyboardButton("🔴 SELL BTCUSD 0.01", callback_data="trade:sell:BTCUSD:0.01")
            ],
            [
                InlineKeyboardButton("💼 View Positions", callback_data="nav_pos"),
                InlineKeyboardButton("📊 Account Status", callback_data="nav_status")
            ]
        ])
        await send_or_edit(update, context, guide_msg, reply_markup=kb)
        return

    parsed = _parse_trade_args(args, default_action="SELL")
    await _execute_and_report_order(update, context, parsed)

@restricted
async def cmd_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Universal trade command: /trade buy/sell SYMBOL LOTS [sl=X tp=Y]."""
    args = context.args or []
    if not args:
        guide_msg = (
            "⚡ <b>REMOTE MT4 ORDER EXECUTION</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>Usage:</b>\n"
            "• <code>/trade buy GBPUSD 0.01</code>\n"
            "• <code>/trade sell EURUSD 0.05 sl=1.0950 tp=1.0820</code>\n"
            "• <code>/order buy GOLD 0.02</code>"
        )
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🟢 Quick BUY 0.01", callback_data="trade:buy:GBPUSD:0.01"),
                InlineKeyboardButton("🔴 Quick SELL 0.01", callback_data="trade:sell:GBPUSD:0.01")
            ],
            [
                InlineKeyboardButton("💼 View Positions", callback_data="nav_pos"),
                InlineKeyboardButton("📊 Account Status", callback_data="nav_status")
            ]
        ])
        await send_or_edit(update, context, guide_msg, reply_markup=kb)
        return

    parsed = _parse_trade_args(args)
    await _execute_and_report_order(update, context, parsed)

@restricted
async def cb_quick_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles 1-tap quick trade execution buttons (pattern: ^trade:(buy|sell):)."""
    query = update.callback_query
    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 4:
        await safe_answer(query, "❌ Invalid trade callback format", show_alert=True)
        return

    act = parts[1].upper()
    sym = parts[2].upper()
    try:
        lots = float(parts[3])
    except ValueError:
        lots = 0.01

    await safe_answer(query, f"Submitting {act} {lots:.2f} on {sym} to MT4...", show_alert=False)

    parsed = {
        "action": act,
        "symbol": sym,
        "lots": lots,
        "sl": 0.0,
        "tp": 0.0,
        "magic": 8882026,
        "comment": "QuickTelegram"
    }
    await _execute_and_report_order(update, context, parsed)

@restricted
async def handle_slash_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles slash commands sent as text messages: /close_12345, /half_12345, /be_12345, /shot_SYM_TF."""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    if text.startswith("/close_"):
        raw_ticket = text.split("_", 1)[1] if "_" in text else ""
        ticket_str = raw_ticket.split("@", 1)[0].strip()
        if not ticket_str.isdigit():
            await update.message.reply_text("❌ Invalid ticket parameter.")
            return

        res = await zmq_async(zmq_client.close_symbol, ticket_str)
        if res.get("status") == "ok" and res.get("closed_count", 0) > 0:
            r_pl = float(res.get("realized_pl", 0.0))
            sign = "+" if r_pl >= 0 else ""
            msg = (
                "🏁 <b>POSITION LIQUIDATED BY REMOTE COMMAND</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Ticket:</b> <code>#{ticket_str}</code>\n"
                f"• <b>Realized P/L:</b> <b>{sign}${r_pl:,.2f}</b>\n"
                "• <i>Closed successfully on MT4 terminal.</i>"
            )
            await update.message.reply_text(msg, reply_markup=get_nav_keyboard("positions"), parse_mode=ParseMode.HTML)
        else:
            err = res.get("message", "Order already closed or MT4 offline")
            await update.message.reply_text(f"❌ Failed to close #{ticket_str}: {err}")

    elif text.startswith("/half_"):
        raw_ticket = text.split("_", 1)[1] if "_" in text else ""
        ticket_str = raw_ticket.split("@", 1)[0].strip()
        if not ticket_str.isdigit():
            await update.message.reply_text("❌ Invalid ticket parameter.")
            return

        res = await zmq_async(zmq_client.close_half, int(ticket_str))
        if res.get("status") == "ok":
            closed_lots = float(res.get("closed_lots", 0.0))
            rem_lots = float(res.get("remaining_lots", 0.0))
            r_pl = float(res.get("realized_pl", 0.0))
            sign = "+" if r_pl >= 0 else ""
            msg = (
                "✂️ <b>50% PARTIAL CLOSE COMPLETED</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Ticket:</b> <code>#{ticket_str}</code>\n"
                f"• <b>Closed Volume:</b> <code>{closed_lots:.2f} lots</code>\n"
                f"• <b>Remaining Volume:</b> <code>{rem_lots:.2f} lots</code>\n"
                f"• <b>Realized P/L:</b> <b>{sign}${r_pl:,.2f}</b>"
            )
            await update.message.reply_text(msg, reply_markup=get_nav_keyboard("positions"), parse_mode=ParseMode.HTML)
        else:
            err = res.get("message", "MT4 offline or position unavailable")
            await update.message.reply_text(f"❌ Partial close failed: {err}")

    elif text.startswith("/be_"):
        raw_ticket = text.split("_", 1)[1] if "_" in text else ""
        ticket_str = raw_ticket.split("@", 1)[0].strip()
        if not ticket_str.isdigit():
            await update.message.reply_text("❌ Invalid ticket parameter.")
            return

        res = await zmq_async(zmq_client.set_breakeven, ticket=int(ticket_str), lock_pips=1)
        if res.get("status") == "ok" and res.get("modified_count", 0) > 0:
            msg = (
                "🛡️ <b>BREAK-EVEN SYNCHRONIZED</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Ticket:</b> <code>#{ticket_str}</code>\n"
                "• <b>Status:</b> <b>Risk-Free (Profit Protected)</b>\n"
                "• <b>Locked Buffer:</b> +1 pip above entry"
            )
            await update.message.reply_text(msg, reply_markup=get_nav_keyboard("positions"), parse_mode=ParseMode.HTML)
        elif res.get("skipped_count", 0) > 0:
            await update.message.reply_text(f"⚠️ Position #{ticket_str} is not in profit yet (+1 pip threshold).")
        else:
            err = res.get("message", "Order not found or already closed")
            await update.message.reply_text(f"❌ Failed: {err}")

    elif text.startswith("/shot_"):
        parts = text.lstrip("/").split("_")
        sym = parts[1] if len(parts) > 1 else "CURRENT"
        tf = parts[2] if len(parts) > 2 else "H1"
        await update.message.reply_text(f"📸 Capturing chart for {sym} ({tf})...")
        success = await execute_screenshot_delivery(chat_id, context, sym, tf)
        if not success:
            await update.message.reply_text(f"⚠️ Failed to capture chart for {sym} ({tf}).")

# Command Aliases
cmd_switch = cmd_accounts
cmd_panic = cmd_closeall
cmd_status = cmd_account
cmd_pause = cmd_pause_bot
cmd_resume = cmd_resume_bot
cmd_be = cmd_breakeven
cmd_trail = cmd_trailing
cmd_calendar = cmd_news
cmd_reset_risk = cmd_reset_safeguards
cmd_reset_prop = cmd_reset_safeguards
cmd_order = cmd_trade

