"""
Automated Institutional Performance Report Generator.
Generates Daily, Weekly, and Monthly executive trading summaries,
drawdown analytics, and visual equity curve charts for Telegram broadcast.
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta
import logging
import os
import time
from typing import Any, Dict, List, Optional

from autotrade.analytics.charts import ChartGenerator
from autotrade.core.config_manager import get_config
from autotrade.core.event_bus import event_bus, EventType, EventPriority
from autotrade.data_layer.database import DatabaseEngine, db_engine
from autotrade.reporting.performance_metrics import PerformanceMetricsEngine, PortfolioMetrics

logger = logging.getLogger("autotrade.reporting.report_generator")


class ReportGenerator:
    """
    Automated multi-period performance report generator.
    """
    def __init__(
        self,
        database: Optional[DatabaseEngine] = None,
        metrics_engine: Optional[PerformanceMetricsEngine] = None,
        charts: Optional[ChartGenerator] = None
    ):
        self.config = get_config()
        self.db = database or db_engine
        self.metrics_engine = metrics_engine or PerformanceMetricsEngine(database=self.db)
        self.charts = charts or ChartGenerator()

    async def generate_daily_report(self) -> Dict[str, Any]:
        """Generates 24-hour performance report and broadcasts via Telegram."""
        return await self.generate_period_report(period_name="DAILY", hours_back=24)

    async def generate_weekly_report(self) -> Dict[str, Any]:
        """Generates 7-day performance report."""
        return await self.generate_period_report(period_name="WEEKLY", hours_back=168)

    async def generate_monthly_report(self) -> Dict[str, Any]:
        """Generates 30-day performance report."""
        return await self.generate_period_report(period_name="MONTHLY", hours_back=720)

    async def generate_period_report(self, period_name: str = "DAILY", hours_back: int = 24) -> Dict[str, Any]:
        """
        Compiles trade performance over given lookback window and creates Telegram message + chart.
        """
        now = time.time()
        cutoff = now - (hours_back * 3600)
        
        # Query closed trades
        query = "SELECT * FROM trades WHERE close_time IS NOT NULL AND created_at >= ? ORDER BY close_time ASC;"
        trades = self.db.fetch_all(query, (cutoff,))
        
        metrics = self.metrics_engine.calculate_metrics_from_trades(trades)
        formatted_text = self._format_telegram_report(period_name, metrics, hours_back)

        event_bus.publish(
            EventType.REPORT_GENERATED,
            payload={"period": period_name, "metrics": metrics.to_dict(), "message": formatted_text},
            priority=EventPriority.NORMAL,
            source="ReportGenerator"
        )

        return {
            "period": period_name,
            "metrics": metrics.to_dict(),
            "telegram_message": formatted_text,
            "trades_count": len(trades)
        }

    def _format_telegram_report(self, period: str, m: PortfolioMetrics, hours: int) -> str:
        """Formats an executive summary card with HTML tags for Telegram."""
        pnl_sign = "+" if m.net_profit >= 0 else ""
        pnl_emoji = "🟢" if m.net_profit >= 0 else "🔴"
        win_rate_pct = m.win_rate * 100.0

        bar_len = 10
        filled = int(round((win_rate_pct / 100.0) * bar_len)) if m.total_trades > 0 else 0
        progress_bar = "█" * filled + "░" * (bar_len - filled)

        lines = [
            f"📊 <b>AUTOTRADE {period} PERFORMANCE SCORECARD</b>",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"⏱️ <b>Lookback Window:</b> Last {hours} hours",
            f"{pnl_emoji} <b>Net Profit / Loss:</b> <code>{pnl_sign}${m.net_profit:,.2f}</code>\n",
            f"🎯 <b>Win Rate:</b> <b>{win_rate_pct:.1f}%</b> [<code>{progress_bar}</code>]",
            f"💼 <b>Total Deals:</b> <b>{m.total_trades}</b> (✅ {m.winning_trades} | ❌ {m.losing_trades})",
            f"⚖️ <b>Profit Factor:</b> <b>{m.profit_factor:.2f}</b>",
            f"📈 <b>Sharpe Ratio:</b> <b>{m.sharpe_ratio:.2f}</b>",
            f"🛡️ <b>Max Drawdown:</b> <b>{m.max_drawdown_pct:.2f}%</b> (${m.max_drawdown_dollars:,.2f})",
            f"💵 <b>Avg Trade Payoff:</b> <code>${m.expected_payoff:.2f}</code>",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"<i>💡 Institutional algorithmic execution running 24/7.</i>"
        ]
        return "\n".join(lines)
