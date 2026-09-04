"""
Institutional Portfolio & Trade Performance Metrics Engine.
Computes Sharpe Ratio, Sortino Ratio, Calmar Ratio, Profit Factor,
Win Rate, Expected Payoff, Maximum Drawdown, and Recovery Factors.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
import logging
import math
from typing import Any, Dict, List, Optional
import numpy as np

from autotrade.data_layer.database import DatabaseEngine, db_engine

logger = logging.getLogger("autotrade.reporting.performance_metrics")


@dataclass
class PortfolioMetrics:
    """Consolidated performance scorecard."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    net_profit: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    expected_payoff: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    win_loss_ratio: float = 0.0
    max_drawdown_dollars: float = 0.0
    max_drawdown_pct: float = 0.0
    recovery_factor: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate * 100.0, 1),
            "net_profit": round(self.net_profit, 2),
            "gross_profit": round(self.gross_profit, 2),
            "gross_loss": round(self.gross_loss, 2),
            "profit_factor": round(self.profit_factor, 2),
            "expected_payoff": round(self.expected_payoff, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "sortino_ratio": round(self.sortino_ratio, 2),
            "calmar_ratio": round(self.calmar_ratio, 2),
            "recovery_factor": round(self.recovery_factor, 2)
        }


class PerformanceMetricsEngine:
    """
    Evaluates quantitative risk and return statistics across trade history.
    """
    def __init__(self, database: Optional[DatabaseEngine] = None):
        self.db = database or db_engine

    def calculate_metrics_from_trades(
        self,
        trades: List[Dict[str, Any]],
        initial_balance: float = 100000.0
    ) -> PortfolioMetrics:
        """
        Computes portfolio statistics from a list of closed trade dictionaries.
        """
        metrics = PortfolioMetrics()
        if not trades:
            return metrics

        pnls = np.array([float(t.get("pnl", 0.0)) for t in trades])
        metrics.total_trades = len(pnls)
        
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        
        metrics.winning_trades = len(wins)
        metrics.losing_trades = len(losses)
        metrics.win_rate = len(wins) / float(len(pnls)) if len(pnls) else 0.0

        metrics.gross_profit = float(np.sum(wins)) if len(wins) else 0.0
        metrics.gross_loss = abs(float(np.sum(losses))) if len(losses) else 0.0
        metrics.net_profit = float(np.sum(pnls))
        metrics.profit_factor = metrics.gross_profit / metrics.gross_loss if metrics.gross_loss > 0 else (99.0 if metrics.gross_profit > 0 else 0.0)

        metrics.avg_win = float(np.mean(wins)) if len(wins) else 0.0
        metrics.avg_loss = abs(float(np.mean(losses))) if len(losses) else 0.0
        metrics.win_loss_ratio = metrics.avg_win / metrics.avg_loss if metrics.avg_loss > 0 else 0.0
        metrics.expected_payoff = float(np.mean(pnls)) if len(pnls) else 0.0

        # Drawdown computation
        cum_pnl = np.cumsum(pnls)
        equity_series = initial_balance + cum_pnl
        peak_series = np.maximum.accumulate(equity_series)
        dd_dollars = peak_series - equity_series
        dd_pct = (dd_dollars / peak_series) * 100.0

        metrics.max_drawdown_dollars = float(np.max(dd_dollars)) if len(dd_dollars) else 0.0
        metrics.max_drawdown_pct = float(np.max(dd_pct)) if len(dd_pct) else 0.0
        metrics.recovery_factor = metrics.net_profit / metrics.max_drawdown_dollars if metrics.max_drawdown_dollars > 0 else 0.0

        # Ratios
        if len(pnls) > 1:
            mean_ret = float(np.mean(pnls))
            std_ret = float(np.std(pnls))
            downside_std = float(np.std(losses)) if len(losses) > 1 else std_ret

            metrics.sharpe_ratio = (mean_ret / std_ret) * math.sqrt(252) if std_ret > 0 else 0.0
            metrics.sortino_ratio = (mean_ret / downside_std) * math.sqrt(252) if downside_std > 0 else 0.0
            metrics.calmar_ratio = (metrics.net_profit / initial_balance * 100.0) / metrics.max_drawdown_pct if metrics.max_drawdown_pct > 0 else 0.0

        return metrics

    def calculate_database_metrics(self, days_back: int = 30) -> PortfolioMetrics:
        """Queries SQLite database for closed trades and computes metrics."""
        query = "SELECT * FROM trades WHERE close_time IS NOT NULL ORDER BY close_time ASC;"
        trades = self.db.fetch_all(query)
        return self.calculate_metrics_from_trades(trades)
