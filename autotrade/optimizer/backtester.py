"""
High-Speed Event-Driven Backtesting Engine.
Simulates realistic order execution with spread friction, slippage modeling,
commissions, and multi-tier TP/SL dynamics. Calculates institutional performance statistics.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import logging
import math
from typing import Any, Callable, Dict, List, Optional
import numpy as np

from autotrade.analytics.precision import PrecisionMath

logger = logging.getLogger("autotrade.optimizer.backtester")


@dataclass
class BacktestTrade:
    """Individual simulated trade record."""
    symbol: str
    side: str
    entry_index: int
    exit_index: int
    entry_price: float
    exit_price: float
    lots: float
    pnl: float
    return_pct: float
    exit_reason: str


@dataclass
class BacktestResult:
    """Comprehensive performance scorecard from a backtesting simulation run."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    net_profit: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    avg_trade_pnl: float = 0.0
    trades: List[BacktestTrade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 3),
            "net_profit": round(self.net_profit, 2),
            "profit_factor": round(self.profit_factor, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "sortino_ratio": round(self.sortino_ratio, 2),
            "calmar_ratio": round(self.calmar_ratio, 2),
            "avg_trade_pnl": round(self.avg_trade_pnl, 2)
        }


class Backtester:
    """
    Quantitative backtesting engine.
    """
    def __init__(
        self,
        initial_balance: float = 100000.0,
        spread_pips: float = 1.0,
        commission_per_lot: float = 3.50,
        slippage_pips: float = 0.2
    ):
        self.initial_balance = initial_balance
        self.spread_pips = spread_pips
        self.commission_per_lot = commission_per_lot
        self.slippage_pips = slippage_pips

    def run(
        self,
        symbol: str,
        ohlcv: Dict[str, np.ndarray],
        strategy_eval_fn: Callable[[int, Dict[str, np.ndarray]], Optional[Dict[str, Any]]],
        default_lots: float = 0.10
    ) -> BacktestResult:
        """
        Executes chronological candle-by-candle simulation.
        `strategy_eval_fn(index, sliced_ohlcv)` is called at each bar to generate signals.
        """
        closes = ohlcv["close"]
        highs = ohlcv["high"]
        lows = ohlcv["low"]
        opens = ohlcv["open"]
        n_bars = len(closes)

        pip_size = float(PrecisionMath.get_pip_size(symbol))
        spread_cost = self.spread_pips * pip_size
        slippage_cost = self.slippage_pips * pip_size

        balance = self.initial_balance
        peak_balance = balance
        equity_curve = [balance]
        trades: List[BacktestTrade] = []

        active_trade: Optional[Dict[str, Any]] = None

        # Minimum warm-up period
        warmup = 35

        for i in range(warmup, n_bars):
            cur_high = highs[i]
            cur_low = lows[i]
            cur_open = opens[i]
            cur_close = closes[i]

            # 1. Manage Active Trade
            if active_trade is not None:
                side = active_trade["side"]
                entry_p = active_trade["entry_price"]
                sl = active_trade["sl"]
                tp = active_trade["tp"]
                lots = active_trade["lots"]
                hit_exit = False
                exit_price = cur_close
                exit_reason = "BAR_CLOSE"

                if side == "BUY":
                    if sl > 0 and cur_low <= sl:
                        exit_price = sl
                        exit_reason = "STOP_LOSS"
                        hit_exit = True
                    elif tp > 0 and cur_high >= tp:
                        exit_price = tp
                        exit_reason = "TAKE_PROFIT"
                        hit_exit = True
                else: # SELL
                    if sl > 0 and cur_high >= sl:
                        exit_price = sl
                        exit_reason = "STOP_LOSS"
                        hit_exit = True
                    elif tp > 0 and cur_low <= tp:
                        exit_price = tp
                        exit_reason = "TAKE_PROFIT"
                        hit_exit = True

                if hit_exit:
                    # Calculate PnL
                    pip_diff = (exit_price - entry_p) / pip_size if side == "BUY" else (entry_p - exit_price) / pip_size
                    pip_val = 10.0 # Approximate for standard FX
                    gross_pnl = pip_diff * pip_val * lots
                    comm = self.commission_per_lot * lots * 2.0
                    net_pnl = gross_pnl - comm

                    balance += net_pnl
                    ret_pct = net_pnl / balance

                    trades.append(BacktestTrade(
                        symbol=symbol,
                        side=side,
                        entry_index=active_trade["entry_index"],
                        exit_index=i,
                        entry_price=entry_p,
                        exit_price=exit_price,
                        lots=lots,
                        pnl=net_pnl,
                        return_pct=ret_pct,
                        exit_reason=exit_reason
                    ))
                    active_trade = None

            # 2. Evaluate Strategy for New Entry if flat
            if active_trade is None:
                # Provide slice up to current bar to prevent lookahead
                sliced = {
                    "open": opens[:i + 1],
                    "high": highs[:i + 1],
                    "low": lows[:i + 1],
                    "close": closes[:i + 1],
                    "volume": ohlcv.get("volume", np.ones_like(closes))[:i + 1],
                    "timestamp": ohlcv.get("timestamp", np.arange(len(closes)))[:i + 1]
                }
                sig = strategy_eval_fn(i, sliced)
                if sig and sig.get("action") in ("BUY", "SELL"):
                    side = sig["action"]
                    entry_p = cur_close + (spread_cost + slippage_cost if side == "BUY" else -(spread_cost + slippage_cost))
                    active_trade = {
                        "side": side,
                        "entry_price": entry_p,
                        "sl": sig.get("sl", 0.0),
                        "tp": sig.get("tp", 0.0),
                        "lots": sig.get("lots", default_lots),
                        "entry_index": i
                    }

            equity_curve.append(balance)
            if balance > peak_balance:
                peak_balance = balance

        # Calculate Institutional Performance Metrics
        return self._calculate_metrics(trades, equity_curve)

    def _calculate_metrics(self, trades: List[BacktestTrade], equity_curve: List[float]) -> BacktestResult:
        """Computes statistical risk and return metrics."""
        result = BacktestResult(trades=trades, equity_curve=equity_curve)
        result.total_trades = len(trades)
        if result.total_trades == 0:
            return result

        pnls = np.array([t.pnl for t in trades])
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]

        result.winning_trades = len(wins)
        result.losing_trades = len(losses)
        result.win_rate = len(wins) / float(result.total_trades)
        result.net_profit = float(np.sum(pnls))
        result.avg_trade_pnl = float(np.mean(pnls))

        sum_wins = float(np.sum(wins)) if len(wins) else 0.0
        sum_losses = abs(float(np.sum(losses))) if len(losses) else 0.0
        result.profit_factor = sum_wins / sum_losses if sum_losses > 0 else (99.0 if sum_wins > 0 else 0.0)

        # Drawdown calculation
        eq = np.array(equity_curve)
        peak = np.maximum.accumulate(eq)
        drawdowns = (peak - eq) / peak * 100.0
        result.max_drawdown_pct = float(np.max(drawdowns)) if len(drawdowns) else 0.0

        # Sharpe & Sortino ratios (annualized assumption)
        rets = np.diff(eq) / eq[:-1]
        mean_r = np.mean(rets)
        std_r = np.std(rets)
        downside_std = np.std(rets[rets < 0]) if len(rets[rets < 0]) else std_r

        result.sharpe_ratio = float((mean_r / std_r) * math.sqrt(252 * 24)) if std_r > 0 else 0.0
        result.sortino_ratio = float((mean_r / downside_std) * math.sqrt(252 * 24)) if downside_std > 0 else 0.0
        result.calmar_ratio = (result.net_profit / self.initial_balance * 100.0) / result.max_drawdown_pct if result.max_drawdown_pct > 0 else 0.0

        return result
