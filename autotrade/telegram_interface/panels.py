"""
Visual View Panels & HTML Renderers for Telegram Messages.
Formats high-density financial metrics, status cards, and risk scorecards with institutional aesthetics.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional


def render_status_panel(acc_data: Dict[str, Any], latency_ms: float = 0.0) -> str:
    """Renders comprehensive Account Status & Bridge Telemetry card."""
    balance = float(acc_data.get("balance", 0.0))
    equity = float(acc_data.get("equity", balance))
    margin = float(acc_data.get("margin", 0.0))
    margin_free = float(acc_data.get("margin_free", equity - margin))
    floating_pnl = equity - balance
    margin_level = (equity / margin * 100.0) if margin > 0 else 0.0

    pnl_sign = "+" if floating_pnl >= 0 else ""
    pnl_emoji = "🟢" if floating_pnl >= 0 else "🔴"

    lines = [
        "📊 <b>INSTITUTIONAL ACCOUNT STATUS</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"👤 <b>Account:</b> <code>#{acc_data.get('login', 'N/A')}</code> ({acc_data.get('name', 'Trader')})",
        f"🏢 <b>Broker / Server:</b> <code>{acc_data.get('company', 'MetaQuotes')}</code>",
        f"💵 <b>Balance:</b> <code>${balance:,.2f}</code>",
        f"💎 <b>Equity:</b> <code>${equity:,.2f}</code>",
        f"{pnl_emoji} <b>Floating P/L:</b> <code>{pnl_sign}${floating_pnl:,.2f}</code>",
        f"🛡️ <b>Free Margin:</b> <code>${margin_free:,.2f}</code>",
        f"📈 <b>Margin Level:</b> <code>{margin_level:,.1f}%</code>" if margin > 0 else "📈 <b>Margin Level:</b> <code>0% (Flat)</code>",
        f"⚡ <b>Bridge Latency:</b> <code>{latency_ms:.1f} ms</code>",
        f"⏰ <b>Server Time:</b> <code>{acc_data.get('server_time', 'Live')}</code>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "<i>🟢 24/7 Autonomous Market Surveillance Active</i>"
    ]
    return "\n".join(lines)


def render_positions_panel(positions: List[Dict[str, Any]]) -> str:
    """Renders active trade positions with live profit and stop metrics."""
    if not positions:
        return (
            "💼 <b>ACTIVE POSITIONS MONITOR</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>No open market orders at this time. Portfolio is 100% in cash.</i>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>💡 Use /boost to inspect live institutional spreads.</i>"
        )

    lines = [
        f"💼 <b>ACTIVE POSITIONS ({len(positions)})</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ]

    total_pnl = 0.0
    for p in positions:
        ticket = p.get("ticket", 0)
        symbol = p.get("symbol", "")
        cmd = p.get("cmd", "BUY").upper()
        lots = float(p.get("lots", 0.0))
        open_p = float(p.get("open_price", 0.0))
        curr_p = float(p.get("current_price", open_p))
        pnl = float(p.get("pnl", 0.0))
        sl = float(p.get("sl", 0.0))
        tp = float(p.get("tp", 0.0))
        total_pnl += pnl

        dir_emoji = "🟢 BUY" if "BUY" in cmd else "🔴 SELL"
        pnl_str = f"+${pnl:,.2f}" if pnl >= 0 else f"-${abs(pnl):,.2f}"

        lines.append(
            f"<b>#{ticket}</b> | {dir_emoji} <b>{lots}</b> <code>{symbol}</code>\n"
            f"   Entry: <code>{open_p}</code> ➜ Now: <code>{curr_p}</code> | P/L: <b>{pnl_str}</b>\n"
            f"   SL: <code>{sl or 'None'}</code> | TP: <code>{tp or 'None'}</code>"
        )

    net_sign = "+" if total_pnl >= 0 else ""
    net_emoji = "🟢" if total_pnl >= 0 else "🔴"
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"{net_emoji} <b>Net Floating Exposure:</b> <b>{net_sign}${total_pnl:,.2f}</b>")
    return "\n".join(lines)


def render_prop_risk_panel(prop_data: Dict[str, Any]) -> str:
    """Renders Prop Firm Guardian scorecard with progress bars."""
    peak_dd = float(prop_data.get("peak_dd_pct", 0.0))
    daily_dd = float(prop_data.get("daily_dd_pct", 0.0))
    calibrated_eq = float(prop_data.get("calibrated_equity", 100000.0))
    status = prop_data.get("day_status", "Safe")

    # Progress bar (out of 10)
    bar_len = 10
    filled = min(bar_len, int(round((daily_dd / 4.0) * bar_len)))
    bar = "█" * filled + "░" * (bar_len - filled)

    lines = [
        "🛡️ <b>PROP-FIRM RISK GUARDIAN SCORECARD</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🛡️ <b>Safety Status:</b> <b>{status.upper()}</b>",
        f"🎯 <b>Anchor Baseline:</b> <code>${calibrated_eq:,.2f}</code>",
        f"📉 <b>Daily Drawdown:</b> <b>{daily_dd:.2f}%</b> / 4.0% [<code>{bar}</code>]",
        f"📊 <b>Peak Drawdown:</b> <b>{peak_dd:.2f}%</b> / 8.0%",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "<i>💡 Limits recalibrate automatically at 00:00 server time. Use /reset_risk to recalibrate baseline.</i>"
    ]
    return "\n".join(lines)


def render_strategy_panel(strategies: List[Any], active_names: List[str]) -> str:
    """Renders active strategy registry and telemetry."""
    lines = [
        "⚙️ <b>QUANTITATIVE STRATEGY CONTROLLER</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ]
    for s in strategies:
        is_on = s.name in active_names
        status_ico = "🟢 ACTIVE" if is_on else "⚪ PAUSED"
        lines.append(
            f"<b>{s.name}</b> [{status_ico}]\n"
            f"   Symbols: <code>{', '.join(s.symbols)}</code>\n"
            f"   Timeframes: <code>{', '.join(s.timeframes)}</code>\n"
            f"   Signals Emitted: <b>{s.total_signals_generated}</b>"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("<i>💡 Tap buttons below to toggle strategies or trigger parameter optimization.</i>")
    return "\n".join(lines)


def render_optimization_panel(opt_result: Dict[str, Any]) -> str:
    """Renders walk-forward and genetic algorithm optimization summary."""
    lines = [
        "🧬 <b>WALK-FORWARD & GA OPTIMIZATION SCORECARD</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📈 <b>Symbol:</b> <code>{opt_result.get('symbol', 'Portfolio')}</code>",
        f"🎯 <b>Average Walk-Forward Efficiency:</b> <b>{opt_result.get('average_wfe_pct', 0.0)}%</b>",
        f"🛡️ <b>Anti-Overfitting Status:</b> <b>{'PASSED' if opt_result.get('is_robust') else 'MARGINAL'}</b>",
        f"💼 <b>Evaluated Folds:</b> <b>{opt_result.get('total_folds', 0)}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "<i>Optimal hyperparameters applied to active trading engine.</i>"
    ]
    return "\n".join(lines)
