"""
Autonomous Multi-Symbol Market Surveillance & Execution Engine.
Monitors configured portfolio of symbols (EURUSD, GBPUSD, USDJPY, XAUUSD, etc.),
evaluates multi-factor confluence scoring across technical indicators, and
autonomously executes high-probability setups directly on MetaTrader without
sending optional or advisory messages to the operator.
"""

from __future__ import annotations
import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from config import (
    ALLOWED_CHAT_IDS,
    AUTOTRADE_FLAG_FILE,
    AUTOTRADE_MAX_OPEN_POSITIONS,
    AUTOTRADE_COOLDOWN_MINUTES,
    AUTOTRADE_MIN_SCORE,
    MAX_OPEN_POSITIONS,
    MAX_LOTS_PER_SYMBOL,
    TRADING_SYMBOLS,
    DEFAULT_FIXED_LOT,
    MT4_FILES_DIR
)
from zmq_client import zmq_client

logger = logging.getLogger("autotrade.core.autonomous_trader")

DEFAULT_PORTFOLIO_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD", "XAUUSD"
]


def canonical_symbol(sym: str) -> str:
    """Normalizes symbol string by removing whitespace, broker prefixes/suffixes, and delimiters."""
    s = str(sym).strip().upper()
    if s == "GOLD":
        return "XAUUSD"
    if s == "SILVER":
        return "XAGUSD"
    if s in ("OIL", "CRUDE", "WTI"):
        return "USOIL"
    if s == "BRENT":
        return "UKOIL"
    if s in ("BITCOIN", "CRYPTO"):
        return "BTCUSD"

    std_pairs = [
        "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD", "XAUUSD", "XAGUSD",
        "EURGBP", "EURJPY", "GBPJPY", "EURCHF", "EURAUD", "EURNZD", "EURCAD", "GBPAUD", "GBPCAD",
        "GBPCHF", "GBPNZD", "AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "CADCHF", "CADJPY", "CHFJPY",
        "NZDCAD", "NZDCHF", "NZDJPY", "USDTRY", "USDRUB", "USDZAR", "USDSEK", "USDNOK", "USDMXN"
    ]
    for pair in std_pairs:
        if pair in s:
            return pair

    for delimiter in ["/", "\\", ".", "-", "_", "#", "+"]:
        s = s.replace(delimiter, "")
    for suffix in ["MIN", "PRO", "RAW", "ECN", "MICRO", "STP", "I", "M"]:
        if s.endswith(suffix) and len(s) > len(suffix) + 3:
            s = s[:-len(suffix)]
            break
    if len(s) == 7 and s[0] in ("M", "R") and s[1:] in std_pairs:
        s = s[1:]
    return s


def split_currency_pair(sym: str) -> Tuple[str, str]:
    """Deconstructs instrument symbol into canonical base and quote currency components."""
    clean = canonical_symbol(sym)
    if len(clean) >= 6:
        return clean[:3], clean[3:6]
    return clean, "USD"


class AutonomousMultiSymbolTrader:
    """
    Master Autonomous Multi-Symbol Trader.
    Performs background surveillance across multiple instruments, filters noise,
    evaluates quantitative scoring confluence, and autonomously dispatches market
    orders directly to MetaTrader.
    """
    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        min_score: int = AUTOTRADE_MIN_SCORE,
        cooldown_sec: int = AUTOTRADE_COOLDOWN_MINUTES * 60,
        max_spread: float = 50.0,
        max_positions: int = AUTOTRADE_MAX_OPEN_POSITIONS
    ):
        self.symbols: List[str] = symbols or list(TRADING_SYMBOLS) or list(DEFAULT_PORTFOLIO_SYMBOLS)
        # Clean symbol strings
        self.symbols = [s.strip().upper() for s in self.symbols if s.strip()]
        if not self.symbols:
            self.symbols = list(DEFAULT_PORTFOLIO_SYMBOLS)

        self.min_score: int = min_score
        self.cooldown_sec: int = cooldown_sec
        self.max_spread: float = max_spread
        self.max_positions: int = max_positions
        self.is_enabled: bool = True
        self.timeframe: str = "H1"
        self.total_trades_executed: int = 0
        self.last_trade_times: Dict[str, float] = {}
        self.last_failure_times: Dict[str, float] = {}
        self.last_scan_data: Dict[str, Any] = {}
        self.last_scan_timestamp: float = 0.0
        self._lock = asyncio.Lock()
        self._risk_manager = None
        self._position_sizer = None

    @property
    def risk_manager(self):
        if self._risk_manager is None:
            from autotrade.risk.risk_manager import RiskManager
            self._risk_manager = RiskManager()
        return self._risk_manager

    @property
    def position_sizer(self):
        if self._position_sizer is None:
            from autotrade.risk.position_sizer import PositionSizer
            self._position_sizer = PositionSizer()
        return self._position_sizer

    def is_autotrade_active(self) -> bool:
        """Reads external flag file and checks internal state."""
        if not self.is_enabled:
            return False
        if os.path.exists(AUTOTRADE_FLAG_FILE):
            try:
                with open(AUTOTRADE_FLAG_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip().upper()
                        if not line:
                            continue
                        if line == "PAUSED" or line.startswith("PAUSED"):
                            return False
                        elif line == "ACTIVE" or line.startswith("ACTIVE"):
                            return True
            except Exception:
                pass
        return self.is_enabled

    def set_enabled(self, active: bool) -> None:
        """Toggles the autonomous trader state."""
        self.is_enabled = active

    def add_symbol(self, symbol: str) -> bool:
        """Adds a symbol to the autonomous watchlist."""
        sym = symbol.strip().upper()
        if sym and sym not in self.symbols:
            self.symbols.append(sym)
            return True
        return False

    def remove_symbol(self, symbol: str) -> bool:
        """Removes a symbol from the autonomous watchlist."""
        sym = symbol.strip().upper()
        if sym in self.symbols and len(self.symbols) > 1:
            self.symbols.remove(sym)
            return True
        return False

    def scan_portfolio(self, timeframe: Optional[str] = None) -> Dict[str, Any]:
        """
        Synchronously queries MetaTrader 4 ZeroMQ Bridge for multi-symbol market data & scores.
        """
        tf = timeframe or self.timeframe
        sym_str = ",".join(self.symbols)
        res = zmq_client.scan_symbols(symbols=sym_str, timeframe=tf, timeout_ms=6000)

        if res.get("status") == "ok" and "results" in res:
            self.last_scan_data = res
            self.last_scan_timestamp = time.time()
            return res

        # If bridge does not support scan_symbols or returns error, check fallback
        is_unsupported = ("Unknown action" in str(res.get("message", "")))
        fallback_results: List[Dict[str, Any]] = []
        for s in self.symbols:
            fallback_results.append({
                "symbol": s,
                "bid": 0.0,
                "ask": 0.0,
                "spread": 0.0,
                "digits": 5,
                "trend": "MONITORING",
                "buy_score": 0,
                "sell_score": 0,
                "score": 0,
                "signal": "HOLD",
                "sl_pips": 30.0,
                "tp_pips": 60.0,
                "rsi": 50.0,
                "atr": 0.0020
            })
        fallback = {
            "status": "ok",
            "action": "SCAN_SYMBOLS",
            "server_time": time.strftime("%Y.%m.%d %H:%M:%S"),
            "results": fallback_results,
            "count": len(fallback_results),
            "fallback": True,
            "bridge_unsupported": is_unsupported
        }
        self.last_scan_data = fallback
        self.last_scan_timestamp = time.time()
        return fallback

    async def scan_portfolio_async(self, timeframe: Optional[str] = None) -> Dict[str, Any]:
        """Asynchronously triggers portfolio scan in a separate worker thread."""
        return await asyncio.to_thread(self.scan_portfolio, timeframe)

    async def execute_autonomous_cycle(self, bot=None) -> List[Dict[str, Any]]:
        """
        Evaluates scan results and autonomously executes valid confluence trade setups.
        Does NOT send advisory/asking messages to operator; executes directly.
        """
        async with self._lock:
            if not self.is_autotrade_active():
                return []

            # 1. Scan market portfolio
            scan_data = await self.scan_portfolio_async()
            results = scan_data.get("results", [])
            if not results:
                return []

            # 2. Check open positions & account safety
            pos_data = await asyncio.to_thread(zmq_client.get_positions)
            if pos_data.get("status") != "ok":
                logger.debug("AutonomousTrader: Unable to fetch open positions from MT4 ZeroMQ bridge; aborting cycle for safety.")
                return []
            open_positions = pos_data.get("positions", [])
            total_open = len(open_positions)

            effective_max = min(self.max_positions, MAX_OPEN_POSITIONS)
            if total_open >= effective_max:
                logger.debug(f"AutonomousTrader: Max open portfolio positions reached ({total_open}/{effective_max})")
                return []

            # Extract symbols currently holding open positions (raw and canonical normalized)
            open_symbols = set()
            canonical_open_symbols = set()
            currency_exposure: Dict[str, int] = {}
            for p in open_positions:
                sym = str(p.get("symbol", "")).strip().upper()
                if sym:
                    open_symbols.add(sym)
                    canon_p = canonical_symbol(sym)
                    canonical_open_symbols.add(canon_p)
                    b_curr, q_curr = split_currency_pair(canon_p)
                    currency_exposure[b_curr] = currency_exposure.get(b_curr, 0) + 1
                    currency_exposure[q_curr] = currency_exposure.get(q_curr, 0) + 1

            executed_trades: List[Dict[str, Any]] = []
            now = time.time()

            # Retrieve account balance/equity metrics for accurate risk sizing & checks
            try:
                acc_data = await asyncio.to_thread(zmq_client.get_account)
            except Exception:
                acc_data = {}
            if not isinstance(acc_data, dict) or acc_data.get("status") != "ok":
                acc_data = {"status": "ok", "balance": 10000.0, "equity": 10000.0, "margin_free": 10000.0}
            acc_equity = float(acc_data.get("equity", acc_data.get("balance", 10000.0)))

            # Symbol Priority with Safety:
            # Filter valid confluence signals (score >= min_score, stands on 6 or past 6)
            # and sort by score descending, spread ascending, and reward-to-risk ratio descending
            candidates = []
            for item in results:
                sig = str(item.get("signal", "HOLD")).strip().upper()
                sc = int(item.get("score", 0))
                if sig in ("BUY", "SELL") and sc >= self.min_score:
                    candidates.append(item)

            def _safety_sort_key(it):
                sc = int(it.get("score", 0))
                sp = float(it.get("spread", 999.0))
                sl_p = float(it.get("sl_pips", 30.0))
                tp_p = float(it.get("tp_pips", 60.0))
                rr = (tp_p / sl_p) if sl_p > 0 else 1.0
                return (-sc, sp, -rr)

            candidates.sort(key=_safety_sort_key)

            for item in candidates:
                raw_sym = str(item.get("symbol", "")).strip().upper()
                canon_sym = canonical_symbol(raw_sym)
                score = int(item.get("score", 0))
                signal = str(item.get("signal", "HOLD")).strip().upper()
                spread = float(item.get("spread", 0.0))

                if raw_sym in open_symbols or canon_sym in canonical_open_symbols:
                    continue  # Already in an active trade on this symbol
                
                # Currency exposure / correlation clamping (max 1 position per currency)
                cand_base, cand_quote = split_currency_pair(canon_sym)
                max_curr_exposure = 1
                if currency_exposure.get(cand_base, 0) >= max_curr_exposure or currency_exposure.get(cand_quote, 0) >= max_curr_exposure:
                    logger.debug(
                        f"AutonomousTrader: Skipping {raw_sym} due to currency exposure limit "
                        f"({cand_base}: {currency_exposure.get(cand_base, 0)}, {cand_quote}: {currency_exposure.get(cand_quote, 0)})"
                    )
                    continue

                if spread > self.max_spread and spread > 0.0:
                    logger.debug(f"AutonomousTrader: Skipping {raw_sym} due to wide spread ({spread} pts > {self.max_spread})")
                    continue

                # Failure retry backoff check (e.g. longs not allowed, market closed, broker error)
                last_fail = max(
                    self.last_failure_times.get(raw_sym, 0.0),
                    self.last_failure_times.get(canon_sym, 0.0)
                )
                if now - last_fail < 300.0:
                    continue

                # Cooldown check
                last_time = max(
                    self.last_trade_times.get(raw_sym, 0.0),
                    self.last_trade_times.get(canon_sym, 0.0)
                )
                if now - last_time < self.cooldown_sec:
                    continue

                # Calculate protective SL & TP (mandatory stops with min 1.5:1 reward-to-risk)
                sl_pips = float(item.get("sl_pips", 30.0))
                tp_pips = float(item.get("tp_pips", 60.0))
                if sl_pips < 15.0:
                    sl_pips = 25.0
                min_rr = 1.5
                if tp_pips < sl_pips * min_rr:
                    tp_pips = round(sl_pips * min_rr, 1)
                if tp_pips < 30.0:
                    tp_pips = 30.0
                if sl_pips <= 0.0 or tp_pips <= 0.0:
                    continue  # Refuse trade without valid stops

                entry_ref = float(item.get("ask" if signal == "BUY" else "bid", 0.0))
                if entry_ref <= 0.0:
                    entry_ref = 1.2500 if "GBP" in canon_sym else (1.0800 if "EUR" in canon_sym else (2350.0 if "XAU" in canon_sym else (150.0 if "JPY" in canon_sym else 1.0000)))

                pip_unit = 0.01 if ("JPY" in canon_sym or "XAU" in canon_sym or "OIL" in canon_sym) else 0.0001
                sl_dist = sl_pips * pip_unit
                tp_dist = tp_pips * pip_unit
                sl_price = round(entry_ref - sl_dist, 5) if signal == "BUY" else round(entry_ref + sl_dist, 5)
                tp_price = round(entry_ref + tp_dist, 5) if signal == "BUY" else round(entry_ref - tp_dist, 5)

                # Determine lot size safely via percentage-based risk sizing (0.5% default)
                lots = self.position_sizer.calculate_lot_size(
                    symbol=raw_sym,
                    method="percentage_risk",
                    balance=acc_equity,
                    entry_price=entry_ref,
                    stop_loss=sl_price
                )
                if lots <= 0.0:
                    lots = 0.01

                # News blackout filter
                is_news = False
                try:
                    from news_service import news_service
                    is_news = news_service.is_news_imminent_for_currency([cand_base, cand_quote])
                except Exception:
                    pass

                # Pre-flight institutional risk check (drawdown, margin, daily loss, consecutive cooldown, correlation)
                risk_res = self.risk_manager.evaluate_order_risk(
                    symbol=raw_sym,
                    cmd=signal,
                    lots=lots,
                    price=entry_ref,
                    sl=sl_price,
                    tp=tp_price,
                    account_info=acc_data,
                    open_positions=open_positions,
                    is_news_imminent=is_news
                )
                if not risk_res.passed:
                    logger.info(f"AutonomousTrader: Pre-flight risk veto for {raw_sym}: {risk_res.reason}")
                    continue
                lots = risk_res.adjusted_lots

                # Execute order directly on MetaTrader
                logger.info(
                    f"🎯 [AUTONOMOUS TRADE TRIGGERED] Symbol: {raw_sym} | Signal: {signal} | "
                    f"Confluence Score: {score}/10 | Lots: {lots:.2f} | Direct Execution..."
                )

                order_res = await asyncio.to_thread(
                    zmq_client.open_order,
                    symbol=raw_sym,
                    cmd=signal,
                    lots=lots,
                    sl_pips=sl_pips,
                    tp_pips=tp_pips,
                    comment=f"Auto_{raw_sym[:4]}"
                )

                if order_res.get("status") == "ok":
                    ticket = order_res.get("ticket", 0)
                    exec_price = order_res.get("price", 0.0)
                    self.total_trades_executed += 1
                    self.last_trade_times[raw_sym] = now
                    self.last_trade_times[canon_sym] = now
                    open_symbols.add(raw_sym)
                    canonical_open_symbols.add(canon_sym)
                    currency_exposure[cand_base] = currency_exposure.get(cand_base, 0) + 1
                    currency_exposure[cand_quote] = currency_exposure.get(cand_quote, 0) + 1

                    trade_record = {
                        "symbol": raw_sym,
                        "cmd": signal,
                        "ticket": ticket,
                        "price": exec_price,
                        "lots": lots,
                        "score": score,
                        "sl_pips": sl_pips,
                        "tp_pips": tp_pips,
                        "trend": item.get("trend", "ALIGNED"),
                        "timestamp": now
                    }
                    executed_trades.append(trade_record)

                    # Notify operator that the bot has executed the trade autonomously
                    if bot and ALLOWED_CHAT_IDS:
                        await self._dispatch_execution_alert(bot, trade_record)

                    # Maximum 1 order per autonomous cycle to prevent order burst
                    break
                else:
                    err_msg = order_res.get("message", "Unknown error")
                    logger.warning(f"Autonomous order dispatch failed for {raw_sym}: {err_msg}")
                    # Enforce 300s failure backoff to prevent spamming the MT4 terminal every cycle
                    self.last_failure_times[raw_sym] = now
                    self.last_failure_times[canon_sym] = now

            return executed_trades

    async def _dispatch_execution_alert(self, bot, trade: Dict[str, Any]) -> None:
        """Sends clean institutional execution alert to all authorized chats with interactive buttons."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        sym = trade["symbol"]
        cmd = trade["cmd"]
        arrow = "🟢 BUY ⬆️" if cmd == "BUY" else "🔴 SELL ⬇️"
        price_fmt = f"{trade['price']:.5f}" if trade['price'] > 0 else "Market"
        ticket = trade.get("ticket", 0)
        ticket_fmt = f"#{ticket}" if ticket else "Filled"

        msg = (
            "🤖 <b>[AUTONOMOUS MULTI-SYMBOL TRADE EXECUTED]</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Asset:</b> <code>{sym}</code> ({arrow})\n"
            f"• <b>Ticket:</b> <code>{ticket_fmt}</code> | <b>Volume:</b> <code>{trade['lots']:.2f} Lots</code>\n"
            f"• <b>Entry Price:</b> <code>{price_fmt}</code>\n"
            f"• <b>Confluence Score:</b> <b>{trade['score']}/10</b> ({trade['trend']})\n"
            f"• <b>Stop Loss:</b> <code>-{trade['sl_pips']:.1f} pips</code>\n"
            f"• <b>Take Profit:</b> <code>+{trade['tp_pips']:.1f} pips</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>⚡ 100% Autonomous Execution: Order placed directly via MT4 ZeroMQ Bridge.</i>"
        )

        kb = None
        if ticket:
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"Close #{ticket}", callback_data=f"/close_{ticket}"),
                    InlineKeyboardButton("Close 50%", callback_data=f"/half_{ticket}")
                ],
                [
                    InlineKeyboardButton("💼 Active Positions", callback_data="nav_pos"),
                    InlineKeyboardButton("📡 Scanner", callback_data="nav_scan")
                ]
            ])

        for chat_id in ALLOWED_CHAT_IDS:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            except Exception as ex:
                logger.error(f"Failed to dispatch autonomous execution alert to chat {chat_id}: {ex}")

    async def run_cycle_async(self, bot=None) -> None:
        """Asynchronous entry point for periodic background scheduler."""
        try:
            await self.execute_autonomous_cycle(bot=bot)
        except Exception as ex:
            logger.debug(f"Error running autonomous trading cycle: {ex}")

    def format_status_panel(self) -> str:
        """Formats comprehensive HTML status panel for /autotrade command."""
        active = self.is_autotrade_active()
        status_badge = "🟢 <b>ACTIVE & SCANNING</b>" if active else "⏸️ <b>PAUSED</b>"
        sym_list = ", ".join(self.symbols)

        msg = (
            "🤖 <b>AUTONOMOUS MULTI-SYMBOL TRADING ENGINE</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>System State:</b> {status_badge}\n"
            f"• <b>Timeframe:</b> <code>{self.timeframe}</code>\n"
            f"• <b>Confluence Threshold:</b> <b>Score ≥ {self.min_score}/10</b>\n"
            f"• <b>Execution Mode:</b> <b>Autonomous Direct Execution</b>\n"
            f"• <b>Max Spread Filter:</b> <code>{self.max_spread:.0f} points</code>\n"
            f"• <b>Max Concurrent Positions:</b> <code>{self.max_positions}</code>\n"
            f"• <b>Cooldown Per Symbol:</b> <code>{self.cooldown_sec // 60} minutes</code>\n"
            f"• <b>Autonomous Trades Executed:</b> <b>{self.total_trades_executed}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 <b>Portfolio Watchlist ({len(self.symbols)} Assets):</b>\n"
            f"<code>{sym_list}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>💡 When an actionable setup is detected on any symbol, the bot trades itself directly without prompting.</i>"
        )
        return msg

    def format_scan_matrix(self, scan_res: Optional[Dict[str, Any]] = None) -> str:
        """Formats clean tabular scorecard for /scan command."""
        data = scan_res or self.last_scan_data
        if not data or "results" not in data:
            data = self.scan_portfolio()

        results = data.get("results", [])
        server_time = data.get("server_time", time.strftime("%Y.%m.%d %H:%M:%S"))

        msg = (
            "⚡ <b>AUTONOMOUS MULTI-SYMBOL SCANNER</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <b>Scan Time:</b> <code>{server_time}</code> | <b>TF:</b> <code>{self.timeframe}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        if data.get("bridge_unsupported"):
            msg += (
                "⚠️ <i>Note: MT4 ZeroMQ bridge requires updated EA reload to stream live scores. "
                "Displaying portfolio watchlist.</i>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )

        for item in results:
            sym = item.get("symbol", "")
            trend = item.get("trend", "NEUTRAL")
            score = item.get("score", 0)
            sig = item.get("signal", "HOLD")
            spread = item.get("spread", 0.0)

            if sig == "BUY":
                sig_badge = "🟢 BUY"
            elif sig == "SELL":
                sig_badge = "🔴 SELL"
            else:
                sig_badge = "⚪ HOLD"

            trend_badge = "⬆️" if "BULL" in trend else ("⬇️" if "BEAR" in trend else "↔️")
            msg += (
                f"• <b>{sym:7s}</b> {sig_badge} (Score: <b>{score}/10</b>) "
                f"| {trend_badge} {trend} | Spd: <code>{spread:.1f}</code>\n"
            )

        msg += (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>💡 Autonomous Multi-Symbol Execution: High-conviction setups (Score ≥ 6) are executed automatically.</i>"
        )
        return msg

    def format_symbols_panel(self) -> str:
        """Formats the list of active monitored symbols for /symbols command."""
        msg = (
            "🌐 <b>AUTONOMOUS PORTFOLIO WATCHLIST</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Total Monitored Symbols:</b> <b>{len(self.symbols)}</b>\n"
            f"• <b>Current Symbols:</b>\n"
        )
        for s in self.symbols:
            msg += f"  • <code>{s}</code>\n"

        msg += (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Use /scan to check current market scores across all symbols.</i>"
        )
        return msg


# Global singleton instance
autonomous_trader = AutonomousMultiSymbolTrader()
