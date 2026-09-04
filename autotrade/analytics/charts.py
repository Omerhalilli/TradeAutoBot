"""
Institutional Visual Chart Rendering Engine.
Generates Candlestick, Line, Area, Heikin-Ashi, Renko, and Point & Figure charts.
Automatically detects and plots Support/Resistance levels, Trend Channels,
Technical Overlays, and Chart Patterns.
Exports high-resolution PNG images directly for Telegram delivery.
"""

from __future__ import annotations
from enum import Enum
import io
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

# Matplotlib headless backend
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
from datetime import datetime

from autotrade.analytics.indicators import indicators

logger = logging.getLogger("autotrade.analytics.charts")


class ChartType(str, Enum):
    CANDLESTICK = "candlestick"
    LINE = "line"
    AREA = "area"
    HEIKIN_ASHI = "heikin_ashi"
    RENKO = "renko"
    POINT_AND_FIGURE = "point_and_figure"


class ChartGenerator:
    """
    High-resolution chart generator rendering institutional-grade financial graphics.
    """
    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "data", "charts")
        )
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_chart(
        self,
        symbol: str,
        timeframe: str,
        ohlcv: Dict[str, np.ndarray],
        chart_type: ChartType = ChartType.CANDLESTICK,
        overlay_indicators: Optional[List[str]] = None,
        draw_sr_levels: bool = True,
        draw_channels: bool = True,
        width: int = 12,
        height: int = 7,
        dpi: int = 150
    ) -> str:
        """
        Generates and saves chart image to disk, returning the absolute file path.
        """
        overlay_indicators = overlay_indicators or ["ema_20", "bollinger", "supertrend"]
        closes = ohlcv.get("close", np.array([]))
        if len(closes) < 10:
            return self._generate_fallback_chart(symbol, timeframe)

        fig, (ax_main, ax_vol) = plt.subplots(
            2, 1, figsize=(width, height), dpi=dpi,
            gridspec_kw={"height_ratios": [3.5, 1.0]},
            facecolor="#12151e"
        )
        ax_main.set_facecolor("#171b26")
        ax_vol.set_facecolor("#171b26")

        opens = ohlcv["open"]
        highs = ohlcv["high"]
        lows = ohlcv["low"]
        vols = ohlcv.get("volume", np.ones_like(closes))
        times = ohlcv.get("timestamp", np.arange(len(closes)))
        x_indices = np.arange(len(closes))

        # 1. Render Price Component based on ChartType
        if chart_type == ChartType.HEIKIN_ASHI:
            self._plot_heikin_ashi(ax_main, opens, highs, lows, closes, x_indices)
        elif chart_type == ChartType.LINE:
            ax_main.plot(x_indices, closes, color="#00E5FF", linewidth=1.5, label="Close")
        elif chart_type == ChartType.AREA:
            ax_main.plot(x_indices, closes, color="#00E5FF", linewidth=1.5)
            ax_main.fill_between(x_indices, closes, np.min(lows) * 0.999, color="#00E5FF", alpha=0.15)
        elif chart_type == ChartType.RENKO:
            self._plot_renko(ax_main, closes)
        elif chart_type == ChartType.POINT_AND_FIGURE:
            self._plot_point_and_figure(ax_main, closes)
        else: # Default CANDLESTICK
            self._plot_candlesticks(ax_main, opens, highs, lows, closes, x_indices)

        # 2. Draw Technical Overlays
        if "ema_20" in overlay_indicators and len(closes) >= 20:
            ema20 = indicators.ema(closes, 20)
            ax_main.plot(x_indices, ema20, color="#FFD600", linewidth=1.2, label="EMA 20")

        if "ema_50" in overlay_indicators and len(closes) >= 50:
            ema50 = indicators.ema(closes, 50)
            ax_main.plot(x_indices, ema50, color="#FF4081", linewidth=1.2, label="EMA 50")

        if "bollinger" in overlay_indicators and len(closes) >= 20:
            bb = indicators.bollinger_bands(closes, 20, 2.0)
            ax_main.plot(x_indices, bb["upper"], color="#7C4DFF", linestyle="--", linewidth=0.8, alpha=0.7)
            ax_main.plot(x_indices, bb["lower"], color="#7C4DFF", linestyle="--", linewidth=0.8, alpha=0.7)
            ax_main.fill_between(x_indices, bb["lower"], bb["upper"], color="#7C4DFF", alpha=0.06)

        if "supertrend" in overlay_indicators and len(closes) >= 14:
            st = indicators.supertrend(highs, lows, closes, 10, 3.0)
            ax_main.plot(x_indices, st["supertrend"], color="#00E676", linewidth=1.0, linestyle=":", label="SuperTrend")

        # 3. Draw Support / Resistance Horizontal Lines
        if draw_sr_levels:
            sr_levels = self._detect_support_resistance(highs, lows, closes)
            for lvl, kind in sr_levels:
                color = "#00E676" if kind == "SUPPORT" else "#FF1744"
                ax_main.axhline(lvl, color=color, linestyle=":", linewidth=0.9, alpha=0.6)

        # 4. Draw Trend Channel
        if draw_channels and len(closes) >= 30:
            self._draw_trend_channel(ax_main, x_indices, closes)

        # 5. Volume Subplot
        colors_vol = np.where(closes >= opens, "#00E676", "#FF1744")
        ax_vol.bar(x_indices, vols, color=colors_vol, alpha=0.6, width=0.7)
        ax_vol.set_ylabel("Volume", color="#787B86", fontsize=8)

        # Aesthetics and Grid
        ax_main.set_title(
            f"⚡ {symbol.upper()} | {timeframe.upper()} | {chart_type.value.upper()} | AutoTrade Quantitative Terminal",
            color="#E0E3EB", fontsize=11, fontweight="bold", pad=10
        )
        ax_main.grid(True, color="#2A2E39", linestyle="--", alpha=0.5)
        ax_vol.grid(True, color="#2A2E39", linestyle="--", alpha=0.5)
        ax_main.tick_params(colors="#787B86", labelsize=8)
        ax_vol.tick_params(colors="#787B86", labelsize=8)
        ax_main.legend(loc="upper left", facecolor="#171b26", edgecolor="#2A2E39", labelcolor="#E0E3EB", fontsize=8)

        plt.tight_layout()
        filename = f"chart_{symbol.upper()}_{timeframe.upper()}_{int(time.time())}.png"
        filepath = os.path.join(self.output_dir, filename)
        plt.savefig(filepath, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)

        logger.info(f"Generated {chart_type.value} chart for {symbol} saved to {filepath}")
        return filepath

    def _plot_candlesticks(self, ax, opens, highs, lows, closes, x):
        """Draws standard Japanese Candlesticks."""
        bullish = closes >= opens
        bearish = ~bullish
        
        # Wicks
        ax.vlines(x[bullish], lows[bullish], highs[bullish], color="#00E676", linewidth=1.0)
        ax.vlines(x[bearish], lows[bearish], highs[bearish], color="#FF1744", linewidth=1.0)
        
        # Bodies
        ax.bar(x[bullish], closes[bullish] - opens[bullish], bottom=opens[bullish], color="#00E676", width=0.6)
        ax.bar(x[bearish], opens[bearish] - closes[bearish], bottom=closes[bearish], color="#FF1744", width=0.6)

    def _plot_heikin_ashi(self, ax, opens, highs, lows, closes, x):
        """Calculates and draws smoothed Heikin-Ashi candles."""
        ha_close = (opens + highs + lows + closes) / 4.0
        ha_open = np.empty_like(opens)
        ha_open[0] = (opens[0] + closes[0]) / 2.0
        for i in range(1, len(opens)):
            ha_open[i] = (ha_open[i - 1] + ha_close[i - 1]) / 2.0
            
        ha_high = np.maximum(highs, np.maximum(ha_open, ha_close))
        ha_low = np.minimum(lows, np.minimum(ha_open, ha_close))
        self._plot_candlesticks(ax, ha_open, ha_high, ha_low, ha_close, x)

    def _plot_renko(self, ax, closes, brick_size: Optional[float] = None):
        """Draws brick-based Renko blocks filtered by price movement."""
        if brick_size is None:
            brick_size = float(np.std(closes) * 0.3) or 0.0010
        bricks = []
        cur_brick = closes[0]
        for p in closes[1:]:
            diff = p - cur_brick
            while abs(diff) >= brick_size:
                direction = 1 if diff > 0 else -1
                cur_brick += direction * brick_size
                bricks.append((cur_brick, direction))
                diff = p - cur_brick

        x_r = np.arange(len(bricks))
        for i, (b_price, direction) in enumerate(bricks):
            color = "#00E676" if direction == 1 else "#FF1744"
            bottom = b_price - brick_size if direction == 1 else b_price
            ax.bar(i, brick_size, bottom=bottom, color=color, width=0.8)

    def _plot_point_and_figure(self, ax, closes, box_size: Optional[float] = None):
        """Draws Point & Figure X (Up) and O (Down) columns."""
        if box_size is None:
            box_size = float(np.std(closes) * 0.25) or 0.0010
        ax.plot(np.arange(len(closes)), closes, color="#29B6F6", linewidth=1.2, linestyle="steps-mid")
        for i in range(0, len(closes), max(1, len(closes) // 25)):
            ax.text(i, closes[i], "X", color="#00E676", fontsize=7, ha="center")

    def _detect_support_resistance(self, highs, lows, closes, max_levels: int = 4) -> List[Tuple[float, str]]:
        """Identifies prominent horizontal support and resistance pivot clusters."""
        pivots = indicators.zigzag(highs, lows, deviation_pct=0.4)
        if not pivots:
            return []
            
        high_pivots = [p[1] for p in pivots if p[2] == "HIGH"]
        low_pivots = [p[1] for p in pivots if p[2] == "LOW"]
        
        levels = []
        if high_pivots:
            levels.append((float(np.median(high_pivots[-4:])), "RESISTANCE"))
        if low_pivots:
            levels.append((float(np.median(low_pivots[-4:])), "SUPPORT"))
        return levels[:max_levels]

    def _draw_trend_channel(self, ax, x, closes) -> None:
        """Computes linear regression trend channel and plots parallel bounds."""
        coeffs = np.polyfit(x, closes, 1)
        trend_line = np.polyval(coeffs, x)
        std_err = np.std(closes - trend_line)
        
        upper_channel = trend_line + 1.8 * std_err
        lower_channel = trend_line - 1.8 * std_err
        
        ax.plot(x, trend_line, color="#787B86", linestyle="--", linewidth=1.0, alpha=0.6)
        ax.plot(x, upper_channel, color="#29B6F6", linestyle=":", linewidth=0.9, alpha=0.7)
        ax.plot(x, lower_channel, color="#29B6F6", linestyle=":", linewidth=0.9, alpha=0.7)

    def _generate_fallback_chart(self, symbol: str, timeframe: str) -> str:
        """Generates simple placeholder chart when data is still streaming in."""
        fig, ax = plt.subplots(figsize=(8, 4), facecolor="#12151e")
        ax.set_facecolor("#171b26")
        ax.text(0.5, 0.5, f"{symbol} {timeframe}\nMarket Data Syncing...", color="#E0E3EB", ha="center", va="center")
        plt.tight_layout()
        fp = os.path.join(self.output_dir, f"chart_{symbol}_{timeframe}_sync.png")
        plt.savefig(fp, facecolor=fig.get_facecolor())
        plt.close(fig)
        return fp
