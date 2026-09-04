"""
Interactive Telegram Inline Keyboards & Menu Navigators.
Provides fast tap-to-execute navigation for trading operations,
risk management, chart generation, and strategy parameters.
"""

from __future__ import annotations
from typing import List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Returns institutional master command keyboard."""
    buttons = [
        [
            InlineKeyboardButton("⚡ Turbo Boost", callback_data="nav_boost"),
            InlineKeyboardButton("📊 Status", callback_data="nav_status")
        ],
        [
            InlineKeyboardButton("💼 Positions", callback_data="nav_positions"),
            InlineKeyboardButton("🛡️ Prop Risk", callback_data="nav_prop")
        ],
        [
            InlineKeyboardButton("📸 Chart", callback_data="nav_chart"),
            InlineKeyboardButton("📈 Report", callback_data="nav_report")
        ],
        [
            InlineKeyboardButton("👥 Switch Acc", callback_data="nav_accounts"),
            InlineKeyboardButton("⚙️ Strategies", callback_data="nav_strategies")
        ],
        [
            InlineKeyboardButton("🚨 EMERGENCY KILL-SWITCH", callback_data="nav_panic")
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def get_positions_keyboard(positions: List[dict]) -> InlineKeyboardMarkup:
    """Generates per-trade interactive action buttons (Close, Half, Break-Even)."""
    buttons = []
    for p in positions[:8]:  # Limit inline rows to 8
        ticket = p.get("ticket", 0)
        symbol = p.get("symbol", "")
        buttons.append([
            InlineKeyboardButton(f"❌ Close #{ticket}", callback_data=f"/close_{ticket}"),
            InlineKeyboardButton(f"✂️ Half #{ticket}", callback_data=f"/half_{ticket}"),
            InlineKeyboardButton(f"🛡️ BE #{ticket}", callback_data=f"/be_{ticket}")
        ])
    
    buttons.append([
        InlineKeyboardButton("🔄 Refresh", callback_data="nav_positions"),
        InlineKeyboardButton("🏠 Main Menu", callback_data="nav_menu")
    ])
    return InlineKeyboardMarkup(buttons)


def get_chart_symbols_keyboard() -> InlineKeyboardMarkup:
    """Step 1: Select symbol for visual chart generation."""
    symbols = ["GBPUSD", "EURUSD", "XAUUSD", "USOIL", "USDJPY", "BTCUSD"]
    buttons = []
    row = []
    for s in symbols:
        row.append(InlineKeyboardButton(f"📈 {s}", callback_data=f"shotsym:{s}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔙 Cancel", callback_data="nav_menu")])
    return InlineKeyboardMarkup(buttons)


def get_chart_timeframes_keyboard(symbol: str) -> InlineKeyboardMarkup:
    """Step 2: Select timeframe and chart type."""
    buttons = [
        [
            InlineKeyboardButton("M5 (5m)", callback_data=f"shottf:{symbol}:M5:candlestick"),
            InlineKeyboardButton("M15 (15m)", callback_data=f"shottf:{symbol}:M15:candlestick"),
            InlineKeyboardButton("H1 (1h)", callback_data=f"shottf:{symbol}:H1:candlestick")
        ],
        [
            InlineKeyboardButton("H4 (4h)", callback_data=f"shottf:{symbol}:H4:candlestick"),
            InlineKeyboardButton("D1 (Daily)", callback_data=f"shottf:{symbol}:D1:candlestick"),
            InlineKeyboardButton("🧱 Renko", callback_data=f"shottf:{symbol}:H1:renko")
        ],
        [
            InlineKeyboardButton("🕯️ Heikin-Ashi", callback_data=f"shottf:{symbol}:H1:heikin_ashi"),
            InlineKeyboardButton("🔙 Back", callback_data="nav_chart")
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def get_panic_confirm_keyboard() -> InlineKeyboardMarkup:
    """Two-step confirmation for catastrophic emergency kill-switch."""
    buttons = [
        [
            InlineKeyboardButton("⚠️ YES - CLOSE ALL & STOP ⚠️", callback_data="confirm_close_all"),
        ],
        [
            InlineKeyboardButton("🛡️ CANCEL - KEEP POSITIONS", callback_data="cancel_close_all")
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def get_strategy_tuning_keyboard(active_strategies: List[str]) -> InlineKeyboardMarkup:
    """Interactive toggle for algorithmic strategies."""
    buttons = []
    known = [
        "TrendFollowingStrategy",
        "MeanReversionStrategy",
        "BreakoutStrategy",
        "MLPredictorStrategy",
        "SmartGridStrategy"
    ]
    for name in known:
        is_on = name in active_strategies
        label = f"✅ {name}" if is_on else f"❌ {name}"
        action = "disable" if is_on else "enable"
        buttons.append([InlineKeyboardButton(label, callback_data=f"strat_toggle:{name}:{action}")])

    buttons.append([
        InlineKeyboardButton("⚡ Run Walk-Forward Optimizer", callback_data="strat_run_opt"),
        InlineKeyboardButton("🏠 Main Menu", callback_data="nav_menu")
    ])
    return InlineKeyboardMarkup(buttons)


def get_risk_settings_keyboard() -> InlineKeyboardMarkup:
    """Interactive risk limit updates."""
    buttons = [
        [
            InlineKeyboardButton("Risk: 1.0%", callback_data="set_risk_pct:1.0"),
            InlineKeyboardButton("Risk: 2.0%", callback_data="set_risk_pct:2.0"),
            InlineKeyboardButton("Risk: 3.0%", callback_data="set_risk_pct:3.0")
        ],
        [
            InlineKeyboardButton("Max DD: 4%", callback_data="set_dd_pct:4.0"),
            InlineKeyboardButton("Max DD: 6%", callback_data="set_dd_pct:6.0"),
            InlineKeyboardButton("Max DD: 8%", callback_data="set_dd_pct:8.0")
        ],
        [
            InlineKeyboardButton("🔄 Recalibrate Safeguards", callback_data="recalibrate_safeguards"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="nav_menu")
        ]
    ]
    return InlineKeyboardMarkup(buttons)
