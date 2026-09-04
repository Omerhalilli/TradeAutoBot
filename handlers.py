"""
Telegram Command Handlers for MT4 ZeroMQ Bridge Bot.
Implements remote control, position management, trade history, and economic news.
"""
import functools
import logging
import os
from typing import Callable
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import ALLOWED_CHAT_IDS
from zmq_client import zmq_client
from news_service import news_service
from account_manager import account_manager, AccountProfile

logger = logging.getLogger(__name__)

def restricted(func: Callable) -> Callable:
    """Decorator to restrict commands to authorized Telegram chat IDs."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id if update.effective_user else 0
        chat_id = update.effective_chat.id if update.effective_chat else 0
        
        if chat_id not in ALLOWED_CHAT_IDS and user_id not in ALLOWED_CHAT_IDS:
            logger.warning(f"Unauthorized access attempt by User ID {user_id} (Chat ID {chat_id})")
            if update.message:
                await update.message.reply_text("⛔ <b>Access Denied</b>: You are not authorized to control this terminal.", parse_mode=ParseMode.HTML)
            elif update.callback_query:
                await update.callback_query.answer("⛔ Access Denied: Unauthorized account.", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

@restricted
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_help(update, context)

@restricted
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    active_acc = account_manager.get_active_account()
    help_text = (
        "🤖 <b>MT4 Institutional Command Center & Bot Menu</b>\n"
        f"👤 <i>Target Account: #{active_acc.id} {active_acc.name} ({active_acc.profile_name})</i>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👥 <b>MULTI-ACCOUNT SWITCHING</b>\n"
        "• /accounts or /switch — Switch between accounts & inspect BUY/SELL functions\n\n"
        "📊 <b>ACCOUNT & STATUS</b>\n"
        "• /status or /account — Balance, Equity, Margin & Health\n"
        "• /positions — Active open market orders\n"
        "• /prop — Prop-Firm Risk Guardian Scorecard & Drawdown\n"
        "• /report — 24-Hour Daily Performance & P/L Summary\n\n"
        "📸 <b>CHARTS & VISUALS</b>\n"
        "• /screenshot — Capture high-res chart photo from MT4\n"
        "• /colors — Apply GBPUSD black & green/red scheme to all charts\n\n"
        "📜 <b>TRADE HISTORY</b>\n"
        "• /history — Last 10 closed trades with tickets & net P/L\n"
        "• /history today — Today's closed trades\n"
        "• /history lastweek — Last week's closed trades\n"
        "• /history <code>[N]</code> — Last N closed trades (e.g. <code>/history 20</code>)\n\n"
        "⚡ <b>REMOTE ORDER MANAGEMENT</b>\n"
        "• /panic or /closeall — Emergency kill-switch (Liquidate all trades)\n"
        "• /close <code>[SYMBOL]</code> — Close open trades for symbol (e.g. <code>/close XAUUSD</code>)\n"
        "• /modify_sl <code>[SYMBOL] [PRICE]</code> — Modify Stop Loss\n"
        "• /modify_tp <code>[SYMBOL] [PRICE]</code> — Modify Take Profit\n\n"
        "🛡️ <b>BOT CONTROLS</b>\n"
        "• /pause — Pause automated trade entries\n"
        "• /resume — Resume automated trade entries\n\n"
        "📅 <b>ECONOMIC CALENDAR & NEWS</b>\n"
        "• /news or /calendar — Today's high-impact economic news\n"
        "• /calendar week — Full weekly economic calendar\n"
        "• <i>Automated 15-min alerts active in background</i>"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

@restricted
async def cmd_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = zmq_client.get_account()
    if data.get("status") != "ok":
        await update.message.reply_text(data.get("message", "Error communicating with MT4."), parse_mode=ParseMode.HTML)
        return

    active_acc = account_manager.get_active_account()
    bal = data.get("balance", 0.0)
    eq = data.get("equity", 0.0)
    margin = data.get("margin", 0.0)
    free_m = data.get("free_margin", 0.0)
    m_level = data.get("margin_level", 0.0)
    floating = data.get("floating_pl", 0.0)
    curr = data.get("currency", "USD")
    server_time = data.get("server_time", "-")
    company = data.get("company", "-")

    pl_icon = "🟢" if floating >= 0 else "🔴"

    msg = (
        f"🏛️ <b>MT4 Account Overview</b>\n"
        f"👤 <b>Account #{active_acc.id}:</b> <code>{active_acc.account_number}</code> ({active_acc.name})\n"
        f"📂 <b>Profile:</b> <code>{active_acc.profile_name}</code> | <i>Broker: {company}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Balance:</b> <code>${bal:,.2f} {curr}</code>\n"
        f"💎 <b>Equity:</b> <code>${eq:,.2f} {curr}</code>\n"
        f"{pl_icon} <b>Floating P/L:</b> <code>${floating:+,.2f} {curr}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔒 <b>Margin Used:</b> <code>${margin:,.2f}</code>\n"
        f"🆓 <b>Free Margin:</b> <code>${free_m:,.2f}</code>\n"
        f"📈 <b>Margin Level:</b> <code>{m_level:,.1f}%</code>\n"
        f"⚙️ <b>Leverage:</b> <code>1:{data.get('leverage', 100)}</code>\n"
        f"🕒 <b>Server Time:</b> <code>{server_time}</code>\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@restricted
async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = zmq_client.get_positions()
    if data.get("status") != "ok":
        await update.message.reply_text(data.get("message", "Error communicating with MT4."), parse_mode=ParseMode.HTML)
        return

    active_acc = account_manager.get_active_account()
    positions = data.get("positions", [])
    count = data.get("count", 0)

    if count == 0:
        await update.message.reply_text(
            f"💼 <b>Open Positions:</b> None\n"
            f"👤 <b>Account #{active_acc.id}:</b> <code>{active_acc.account_number}</code> ({active_acc.name})\n"
            f"📂 <b>Profile:</b> <code>{active_acc.profile_name}</code>\n"
            f"<i>There are currently no active market orders.</i>",
            parse_mode=ParseMode.HTML
        )
        return

    msg = (
        f"💼 <b>Active Open Positions ({count})</b>\n"
        f"👤 <b>Account #{active_acc.id}:</b> <code>{active_acc.account_number}</code> ({active_acc.name} — <code>{active_acc.profile_name}</code>)\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    total_pl = 0.0

    for pos in positions:
        ticket = pos.get("ticket")
        sym = pos.get("symbol")
        type_str = pos.get("type")
        lots = pos.get("lots")
        open_p = pos.get("open_price")
        curr_p = pos.get("close_price")
        sl = pos.get("sl")
        tp = pos.get("tp")
        profit = pos.get("profit")
        total_pl += profit

        icon = "🟢 BUY" if "BUY" in type_str else "🔴 SELL"
        p_icon = "📈" if profit >= 0 else "📉"

        msg += (
            f"<b>#{ticket} {icon} {lots:.2f} {sym}</b>\n"
            f"   Open: <code>{open_p}</code> ➜ Now: <code>{curr_p}</code>\n"
            f"   SL: <code>{sl}</code> | TP: <code>{tp}</code>\n"
            f"   {p_icon} Profit: <b>${profit:+,.2f}</b>\n\n"
        )

    msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"<b>Total Floating P/L:</b> <b>${total_pl:+,.2f}</b>"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@restricted
async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    filter_type = "all"
    limit = 10

    if args:
        arg0 = args[0].lower()
        if arg0 == "today":
            filter_type = "today"
            limit = 50
        elif arg0 == "lastweek":
            filter_type = "lastweek"
            limit = 50
        elif arg0.isdigit():
            limit = int(arg0)

    data = zmq_client.get_history(limit=limit, filter_type=filter_type)
    if data.get("status") != "ok":
        await update.message.reply_text(data.get("message", "Error communicating with MT4."), parse_mode=ParseMode.HTML)
        return

    trades = data.get("trades", [])
    total_net = data.get("total_net_pl", 0.0)
    count = data.get("count", 0)

    if count == 0:
        await update.message.reply_text(f"📜 <b>Trade History ({filter_type.capitalize()}):</b> No closed trades found.", parse_mode=ParseMode.HTML)
        return

    msg = f"📜 <b>Closed Trade History ({filter_type.upper()} - {count} deals)</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for tr in trades:
        ticket = tr.get("ticket")
        sym = tr.get("symbol")
        type_str = tr.get("type")
        lots = tr.get("lots")
        open_p = tr.get("open_price")
        close_p = tr.get("close_price")
        net_pl = tr.get("net_pl")
        close_time = tr.get("close_time", "")

        icon = "🟢 BUY" if type_str == "BUY" else "🔴 SELL"
        p_badge = "✅" if net_pl >= 0 else "❌"

        msg += (
            f"{p_badge} <b>#{ticket} {icon} {lots:.2f} {sym}</b>\n"
            f"   In: <code>{open_p}</code> ➜ Out: <code>{close_p}</code>\n"
            f"   Net P/L: <b>${net_pl:+,.2f}</b> | Closed: <code>{close_time}</code>\n\n"
        )

    tot_icon = "🟢" if total_net >= 0 else "🔴"
    msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"{tot_icon} <b>Cumulative Net Profit:</b> <b>${total_net:+,.2f}</b>"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@restricted
async def cmd_closeall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompts for confirmation before closing all open trades."""
    keyboard = [
        [
            InlineKeyboardButton("⚠️ Yes, Close All Positions", callback_data="confirm_close_all"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_close_all")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "⚠️ <b>CONFIRMATION REQUIRED</b>\n\n"
        "Are you sure you want to close <b>ALL active market positions</b> immediately?",
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
        realized = data.get("realized_pl", 0.0)

        msg = (
            "🚨 <b>Emergency Close All Executed</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>Orders Closed:</b> {closed}\n"
            f"⚠️ <b>Orders Failed:</b> {failed}\n"
            f"💵 <b>Realized P/L:</b> <b>${realized:+,.2f}</b>\n"
        )
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML)

    elif query.data == "cancel_close_all":
        await query.edit_message_text("✅ <i>Close All operation cancelled. Open positions left intact.</i>", parse_mode=ParseMode.HTML)

@restricted
async def cmd_close_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if not args:
        await update.message.reply_text("ℹ️ <b>Usage:</b> <code>/close SYMBOL</code>\nExample: <code>/close EURUSD</code>", parse_mode=ParseMode.HTML)
        return

    symbol = args[0].upper().strip()
    data = zmq_client.close_symbol(symbol)
    if data.get("status") != "ok":
        await update.message.reply_text(f"❌ <b>Error:</b> {data.get('message')}", parse_mode=ParseMode.HTML)
        return

    closed = data.get("closed_count", 0)
    failed = data.get("failed_count", 0)
    realized = data.get("realized_pl", 0.0)

    msg = (
        f"🎯 <b>Close Executed for {symbol}</b>\n"
        f"• Closed: {closed}\n"
        f"• Failed: {failed}\n"
        f"• Realized P/L: <b>${realized:+,.2f}</b>"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@restricted
async def cmd_modify_sl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text("ℹ️ <b>Usage:</b> <code>/modify_sl SYMBOL PRICE</code>\nExample: <code>/modify_sl GBPUSD 1.3520</code>", parse_mode=ParseMode.HTML)
        return

    symbol = args[0].upper().strip()
    try:
        sl_price = float(args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid price format. Must be a numeric value.", parse_mode=ParseMode.HTML)
        return

    data = zmq_client.modify_sl(symbol=symbol, sl=sl_price)
    if data.get("status") != "ok":
        await update.message.reply_text(f"❌ <b>Error:</b> {data.get('message')}", parse_mode=ParseMode.HTML)
        return

    count = data.get("modified_count", 0)
    await update.message.reply_text(f"✅ <b>Stop Loss Modified</b>\nSymbol: <code>{symbol}</code>\nNew SL: <code>{sl_price}</code>\nOrders modified: {count}", parse_mode=ParseMode.HTML)

@restricted
async def cmd_modify_tp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text("ℹ️ <b>Usage:</b> <code>/modify_tp SYMBOL PRICE</code>\nExample: <code>/modify_tp GBPUSD 1.3650</code>", parse_mode=ParseMode.HTML)
        return

    symbol = args[0].upper().strip()
    try:
        tp_price = float(args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid price format. Must be a numeric value.", parse_mode=ParseMode.HTML)
        return

    data = zmq_client.modify_tp(symbol=symbol, tp=tp_price)
    if data.get("status") != "ok":
        await update.message.reply_text(f"❌ <b>Error:</b> {data.get('message')}", parse_mode=ParseMode.HTML)
        return

    count = data.get("modified_count", 0)
    await update.message.reply_text(f"✅ <b>Take Profit Modified</b>\nSymbol: <code>{symbol}</code>\nNew TP: <code>{tp_price}</code>\nOrders modified: {count}", parse_mode=ParseMode.HTML)

@restricted
async def cmd_pause_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = zmq_client.pause_bot()
    if data.get("status") != "ok":
        await update.message.reply_text(f"❌ <b>Error:</b> {data.get('message')}", parse_mode=ParseMode.HTML)
        return

    msg = (
        "⏸️ <b>AutoTrading PAUSED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "• Global Variable <code>AutoTrading_Paused</code> set to <b>1</b>\n"
        "• State flag <code>autotrade_state.flag</code> written\n"
        "• Auto-trading EAs will freeze new order entries immediately."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@restricted
async def cmd_resume_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = zmq_client.resume_bot()
    if data.get("status") != "ok":
        await update.message.reply_text(f"❌ <b>Error:</b> {data.get('message')}", parse_mode=ParseMode.HTML)
        return

    msg = (
        "▶️ <b>AutoTrading RESUMED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "• Global Variable <code>AutoTrading_Paused</code> set to <b>0</b>\n"
        "• State flag <code>autotrade_state.flag</code> set to ACTIVE\n"
        "• Auto-trading EAs resumed scanning and trade execution."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@restricted
async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if args and args[0].lower() in ["week", "thisweek"]:
        events = news_service.get_week_events()
        title = "This Week's Economic Calendar"
    else:
        events = news_service.get_today_events()
        title = "Today's Economic Calendar"

    messages = news_service.format_news_messages(events, title)
    for msg in messages:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

def format_progress_bar(current: float, max_val: float, bar_len: int = 10) -> str:
    if max_val <= 0.0:
        return "[□□□□□□□□□□] 0%"
    ratio = max(0.0, min(1.0, current / max_val))
    filled = int(round(ratio * bar_len))
    bar = "■" * filled + "□" * (bar_len - filled)
    return f"[{bar}] {int(round(ratio * 100))}%"

@restricted
async def cmd_prop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = zmq_client.get_prop()
    if data.get("status") != "ok":
        await update.message.reply_text(data.get("message", "Error communicating with MT4."), parse_mode=ParseMode.HTML)
        return

    acc = data.get("account", "-")
    comp = data.get("company", "-")
    curr = data.get("currency", "USD")
    eq = data.get("equity", 0.0)
    peak_eq = data.get("peak_equity", 0.0)
    day_loss = data.get("day_loss", 0.0)
    day_limit = data.get("day_loss_limit", 0.0)
    day_pct = data.get("day_loss_pct", 0.0)
    day_st = data.get("day_status", "Safe")
    peak_loss = data.get("peak_loss", 0.0)
    peak_limit = data.get("peak_loss_limit", 0.0)
    peak_pct = data.get("peak_loss_pct", 0.0)
    peak_st = data.get("peak_status", "Safe")
    gain = data.get("current_gain", 0.0)
    target_goal = data.get("target_profit_goal", 0.0)
    max_d_pct = data.get("max_daily_limit_pct", 4.5)
    max_t_pct = data.get("max_total_limit_pct", 8.0)
    target_goal_pct = data.get("target_goal_pct", 8.0)
    lockout = data.get("lockout_active", False)
    autotrade = data.get("autotrading_active", True)
    shield = data.get("weekend_shield", "Disabled")

    day_badge = "✅ Safe" if day_st == "Safe" else ("⚠️ Caution" if day_st == "Caution" else "🚨 BREACHED")
    peak_badge = "✅ Safe" if peak_st == "Safe" else ("⚠️ Caution" if peak_st == "Caution" else "🚨 BREACHED")
    guard_badge = "LOCKED (Breach) 🔒" if lockout else ("ACTIVE & ENFORCED 🟢" if autotrade else "PAUSED ⏸️")

    msg = (
        f"🛡️ <b>PROP-FIRM RISK GUARDIAN SCORECARD</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Account:</b> {acc} ({comp})\n"
        f"• <b>Equity:</b> ${eq:,.2f} {curr} | <b>Peak:</b> ${peak_eq:,.2f} {curr}\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"📉 <b>DAILY DRAWDOWN (Limit: {max_d_pct:.1f}%):</b>\n"
        f"• Loss Today: -${day_loss:.2f} / -${day_limit:.2f} ({day_pct:.2f}%) — {day_badge}\n"
        f"  {format_progress_bar(day_loss, day_limit, 10)}\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"📉 <b>TRAILING PEAK DRAWDOWN (Limit: {max_t_pct:.1f}%):</b>\n"
        f"• Trailing DD: -${peak_loss:.2f} / -${peak_limit:.2f} ({peak_pct:.2f}%) — {peak_badge}\n"
        f"  {format_progress_bar(peak_loss, peak_limit, 10)}\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"🎯 <b>PROFIT TARGET PROGRESS ({target_goal_pct:.1f}%):</b>\n"
        f"• Progress: +${gain:.2f} / +${target_goal:.2f}\n"
        f"  {format_progress_bar(gain, target_goal, 10)}\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"• <b>Guardian Status:</b> {guard_badge}\n"
        f"• <b>Weekend Shield:</b> {shield}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@restricted
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = zmq_client.get_report()
    if data.get("status") != "ok":
        await update.message.reply_text(data.get("message", "Error communicating with MT4."), parse_mode=ParseMode.HTML)
        return

    period = data.get("period", "Last 24 Hours")
    acc = data.get("account", "-")
    comp = data.get("company", "-")
    curr = data.get("currency", "USD")
    total_trades = data.get("total_trades", 0)
    win_count = data.get("win_count", 0)
    loss_count = data.get("loss_count", 0)
    win_rate = data.get("win_rate", 0.0)
    gross_p = data.get("gross_profit", 0.0)
    gross_l = data.get("gross_loss", 0.0)
    pf = data.get("profit_factor", 0.0)
    net = data.get("net_pl", 0.0)
    best_sym = data.get("best_symbol", "")
    best_p = data.get("best_profit", 0.0)
    worst_sym = data.get("worst_symbol", "")
    worst_l = data.get("worst_loss", 0.0)
    bal = data.get("ending_balance", 0.0)
    eq = data.get("ending_equity", 0.0)

    pl_sign = "🟢 +" if net >= 0 else "🔴 -"

    msg = (
        f"📈 <b>DAILY PERFORMANCE SUMMARY REPORT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Period:</b> {period}\n"
        f"• <b>Account:</b> {acc} ({comp})\n"
        f"• <b>Closed Trades:</b> {total_trades} ({win_count}W / {loss_count}L)\n"
        f"• <b>Win Rate:</b> {win_rate:.1f}%\n"
        f"• <b>Gross Profit:</b> +${gross_p:,.2f} {curr}\n"
        f"• <b>Gross Loss:</b> -${gross_l:,.2f} {curr}\n"
        f"• <b>Profit Factor:</b> {pf:.2f}\n"
        f"• <b>Net P/L:</b> <b>{pl_sign}${abs(net):,.2f} {curr}</b>\n"
    )
    if best_p > 0:
        msg += f"• <b>Best Trade:</b> {best_sym} (+${best_p:,.2f} {curr})\n"
    if worst_l < 0:
        msg += f"• <b>Worst Trade:</b> {worst_sym} (-${abs(worst_l):,.2f} {curr})\n"
    msg += (
        f"• <b>Ending Balance:</b> ${bal:,.2f} {curr}\n"
        f"• <b>Ending Equity:</b> ${eq:,.2f} {curr}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@restricted
async def cmd_colors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = zmq_client.apply_colors()
    if data.get("status") != "ok":
        await update.message.reply_text(data.get("message", "Error communicating with MT4."), parse_mode=ParseMode.HTML)
        return

    count = data.get("synced_count", 0)
    msg = (
        "🎨 <b>CHART COLOR SCHEME SYNCHRONIZED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "• <b>Style:</b> GBPUSD Black & Green/Red Candlestick Scheme\n"
        f"• <b>Open Charts Synchronized:</b> {count} chart(s)\n"
        "• <b>Default Template:</b> <code>templates/default.tpl</code> created!\n"
        "• <b>Result:</b> All current and future charts will now open in this exact style! ✅"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

import time
from config import AUTOTRADE_FLAG_FILE

def write_autotrade_flag(state: str) -> None:
    """Writes autotrade state flag to both local folder and MT4 Files directory."""
    content = f"{state.upper()}\nTimestamp={int(time.time())}\n"
    # 1. Local scratch directory
    try:
        with open(AUTOTRADE_FLAG_FILE, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as ex:
        logger.debug(f"Could not write local flag file: {ex}")

    # 2. MT4 Terminal Files directory
    try:
        mt4_files_dir = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\80152BA938C72BA373B1EA4889AEE06F\MQL4\Files")
        os.makedirs(mt4_files_dir, exist_ok=True)
        mt4_flag_path = os.path.join(mt4_files_dir, "autotrade_state.flag")
        with open(mt4_flag_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as ex:
        logger.debug(f"Could not write MT4 flag file: {ex}")

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
            InlineKeyboardButton("📊 Current Active Chart", callback_data="shotsym:CURRENT")
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
    """
    Step 1: Displays an interactive inline keyboard of instruments to choose from.
    If user provided arguments (e.g. /screenshot GBPUSD H1), executes directly.
    """
    args = context.args or []
    if args:
        sym = args[0].upper()
        tf = args[1].upper() if len(args) > 1 else ""
        await execute_screenshot_delivery(update.effective_chat.id, context, sym, tf)
        return

    msg = (
        "📸 <b>Interactive Chart Screenshot Panel</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Select the currency pair or market instrument you wish to capture:"
    )
    await update.message.reply_text(msg, reply_markup=get_symbol_keyboard(), parse_mode=ParseMode.HTML)

async def cb_screenshot_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Step 2: Receives chosen symbol and prompts user with timeframe buttons."""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if data == "shotsym:BACK":
        msg = (
            "📸 <b>Interactive Chart Screenshot Panel</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Select the currency pair or market instrument you wish to capture:"
        )
        await query.edit_message_text(msg, reply_markup=get_symbol_keyboard(), parse_mode=ParseMode.HTML)
        return

    symbol = data.split(":", 1)[1] if ":" in data else "CURRENT"
    display_sym = "Active Chart" if symbol == "CURRENT" else symbol

    msg = (
        f"📸 <b>Selected Instrument:</b> <code>{display_sym}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Now choose the timeframe to render and capture:"
    )
    await query.edit_message_text(msg, reply_markup=get_timeframe_keyboard(symbol), parse_mode=ParseMode.HTML)

async def cb_screenshot_tf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Step 3: Receives chosen timeframe, commands MT4 over ZeroMQ, and sends photo."""
    query = update.callback_query
    await query.answer("Capturing chart...")

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        return

    symbol = parts[1]
    timeframe = parts[2]
    display_sym = "Current Chart" if symbol == "CURRENT" else symbol

    await query.edit_message_text(
        f"⏳ <i>Capturing {display_sym} ({timeframe}) chart from MetaTrader 4...</i>",
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
            f"⚠️ <b>Capture Failed:</b> MT4 not connected or chart unavailable. Ensure MT4 is running.",
            parse_mode=ParseMode.HTML
        )

async def execute_screenshot_delivery(chat_id: int, context: ContextTypes.DEFAULT_TYPE, symbol: str, timeframe: str) -> bool:
    """Helper that queries ZeroMQ and dispatches the photo to Telegram."""
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

# Update pause/resume bot to ensure flag file is always written
@restricted
async def cmd_pause_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    write_autotrade_flag("PAUSED")
    data = zmq_client.pause_bot()
    conn_note = "" if data.get("status") == "ok" else " (Note: MT4 currently offline; flag will take effect upon launch)"

    msg = (
        "⏸️ <b>AutoTrading PAUSED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "• State flag <code>autotrade_state.flag</code> set to <b>PAUSED</b>\n"
        "• Global Variable <code>AutoTrading_Paused</code> set to <b>1</b>\n"
        f"• All auto-trading robots will freeze new entries immediately.{conn_note}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@restricted
async def cmd_resume_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    write_autotrade_flag("ACTIVE")
    data = zmq_client.resume_bot()
    conn_note = "" if data.get("status") == "ok" else " (Note: MT4 currently offline; flag will take effect upon launch)"

    msg = (
        "▶️ <b>AutoTrading RESUMED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "• State flag <code>autotrade_state.flag</code> set to <b>ACTIVE</b>\n"
        "• Global Variable <code>AutoTrading_Paused</code> set to <b>0</b>\n"
        f"• Auto-trading robots resumed scanning and trade execution.{conn_note}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

# ==============================================================================
# Multi-Account Profile Switcher & BUY/SELL Function Inspection
# ==============================================================================

# ==============================================================================
# Invest-AZ Multi-Account (Demo vs Real) Switcher & BUY/SELL Function Inspection
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

def inspect_account_trades(account: AccountProfile) -> tuple:
    """
    Performs deep inspection of the Invest-AZ account:
    Checks if the account has any active BUY or SELL functions/orders,
    computes exposure, volume, and floating profit, and formats a complete report.
    """
    # Try primary endpoint, with fallback to 5555 if port 5556 is unreachable
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
            "2. Ensure SmartAutoTradeEA_Pro is attached to an open chart (e.g. GBPUSD, H1)."
        )
        keyboard = [
            [InlineKeyboardButton("🔄 Re-Check Connection", callback_data=f"switch_acc:{account.id}")],
            [InlineKeyboardButton("👥 Switch Account", callback_data="switch_acc:panel")]
        ]
        return msg, InlineKeyboardMarkup(keyboard)

    # MT4 is online! Extract live data
    live_num = str(acc_data.get("account_number", account.account_number))
    trade_mode = str(acc_data.get("trade_mode", "DEMO")).upper()
    server = str(acc_data.get("server", account.server))
    company = str(acc_data.get("company", "Invest-AZ"))

    # Determine if target account matches terminal's current active login
    target_is_real = (str(account.id) == "2" or "REAL" in account.name.upper())
    terminal_is_real = (trade_mode == "REAL" or "REAL" in server.upper())

    # Auto-update the account number in registry if detected on live account
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

    # Mismatch warning if user selected Real but terminal is on Demo, or vice versa
    mismatch_note = ""
    if target_is_real and not terminal_is_real:
        mismatch_note = (
            "\n⚠️ <b>NOTICE:</b> <i>Target set to REAL, but your MT4 terminal is currently logged into DEMO (1234567).</i>\n"
            "💡 <i>To execute on REAL: Open MT4 Navigator (Ctrl+N) ➜ Double-click your Real account to log in.</i>\n"
        )
    elif not target_is_real and terminal_is_real:
        mismatch_note = (
            f"\n⚠️ <b>NOTICE:</b> <i>Target set to DEMO, but your MT4 terminal is currently logged into REAL ({live_num}).</i>\n"
            "💡 <i>To execute on DEMO: Open MT4 Navigator (Ctrl+N) ➜ Double-click your Demo account (1234567) to log in.</i>\n"
        )

    # Inspect positions for BUY vs SELL functions
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
        msg += f"🟢 <b>ACTIVE BUY FUNCTION ({len(buy_orders)} order(s) | {total_buy_lots:.2f} lots)</b>\n"
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
        msg += f"🔴 <b>ACTIVE SELL FUNCTION ({len(sell_orders)} order(s) | {total_sell_lots:.2f} lots)</b>\n"
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
    """Displays the Multi-Account & Profile Switching Panel."""
    active = account_manager.get_active_account()
    msg = (
        "👥 <b>INVEST-AZ ACCOUNT SWITCHER & TRADE INSPECTOR</b>\n"
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
    """Handles account switching button taps and trade inspection."""
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
    """Handles navigation action buttons from the trade inspection report."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    chat_id = update.effective_chat.id

    if data == "nav_pos":
        data_pos = zmq_client.get_positions()
        if data_pos.get("status") != "ok":
            await context.bot.send_message(chat_id=chat_id, text=data_pos.get("message", "⚠️ MT4 not connected."), parse_mode=ParseMode.HTML)
            return

        active_acc = account_manager.get_active_account()
        positions = data_pos.get("positions", [])
        count = data_pos.get("count", 0)

        if count == 0:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"💼 <b>Open Positions:</b> None\n"
                    f"👤 <b>Account #{active_acc.id}:</b> <code>{active_acc.account_number}</code> ({active_acc.name})\n"
                    f"📂 <b>Profile:</b> <code>{active_acc.profile_name}</code>\n"
                    f"<i>There are currently no active market orders.</i>"
                ),
                parse_mode=ParseMode.HTML
            )
            return

        msg = (
            f"💼 <b>Active Open Positions ({count})</b>\n"
            f"👤 <b>Account #{active_acc.id}:</b> <code>{active_acc.account_number}</code> ({active_acc.name})\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        total_pl = 0.0
        for pos in positions:
            ticket = pos.get("ticket")
            sym = pos.get("symbol")
            type_str = pos.get("type")
            lots = pos.get("lots")
            open_p = pos.get("open_price")
            curr_p = pos.get("close_price")
            sl = pos.get("sl")
            tp = pos.get("tp")
            profit = pos.get("profit")
            total_pl += profit

            icon = "🟢 BUY" if "BUY" in str(type_str) else "🔴 SELL"
            p_icon = "📈" if profit >= 0 else "📉"
            msg += (
                f"• <b>#{ticket} {icon} {lots} {sym}</b>\n"
                f"  In: <code>{open_p}</code> ➜ Now: <code>{curr_p}</code>\n"
                f"  {p_icon} Profit: <b>${profit:+,.2f}</b> (SL: {sl} | TP: {tp})\n\n"
            )
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"💰 <b>Total Floating P/L:</b> <b>${total_pl:+,.2f}</b>"
        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)

    elif data == "nav_shot":
        msg = (
            "📸 <b>Interactive Chart Screenshot Panel</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Select the currency pair or market instrument you wish to capture:"
        )
        await context.bot.send_message(chat_id=chat_id, text=msg, reply_markup=get_symbol_keyboard(), parse_mode=ParseMode.HTML)

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

# Aliases for Menu commands
cmd_switch = cmd_accounts
cmd_panic = cmd_closeall
cmd_status = cmd_account
cmd_pause = cmd_pause_bot
cmd_resume = cmd_resume_bot
