"""
Real-Time Multi-Timeframe Market Data Aggregator & Tick Processor.
Constructs live OHLCV bars across M1, M5, M15, M30, H1, H4, and D1 from raw streaming ticks.
Maintains in-memory circular buffers and yields zero-copy vectorized NumPy arrays for sub-millisecond indicator calculations.
"""

from __future__ import annotations
import asyncio
from collections import deque
from dataclasses import dataclass, field
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from autotrade.core.event_bus import event_bus, EventType, EventPriority
from autotrade.data_layer.database import DatabaseEngine, db_engine

logger = logging.getLogger("autotrade.data_layer.market_data")

TIMEFRAME_SECONDS: Dict[str, int] = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400
}


@dataclass
class Tick:
    """Individual real-time market quote."""
    symbol: str
    timestamp: float
    bid: float
    ask: float
    spread: float
    volume: float = 1.0


@dataclass
class Bar:
    """Consolidated OHLCV Candlestick bar."""
    symbol: str
    timeframe: str
    timestamp: int  # Start of candle epoch
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "is_closed": self.is_closed
        }


class MarketDataManager:
    """
    High-frequency market data aggregator.
    Processes incoming quotes, maintains multi-timeframe candles,
    and supplies vectorized arrays for quant models.
    """
    def __init__(self, database: Optional[DatabaseEngine] = None, max_bars: int = 1000, max_ticks: int = 5000):
        self.db = database or db_engine
        self.max_bars = max_bars
        self.max_ticks = max_ticks
        
        # In-memory fast storage: {symbol: deque[Tick]}
        self._ticks: Dict[str, deque[Tick]] = {}
        # Multi-timeframe bar buffers: {(symbol, timeframe): deque[Bar]}
        self._bars: Dict[Tuple[str, str], deque[Bar]] = {}
        # Currently building candles: {(symbol, timeframe): Bar}
        self._current_bar: Dict[Tuple[str, str], Bar] = {}
        self._lock = asyncio.Lock()

    async def on_tick(self, tick_dict: Dict[str, Any]) -> None:
        """
        Ingests a raw tick dictionary (from MT4 ZeroMQ bridge or synthetic feed)
        and distributes updates across all tracked timeframes.
        """
        symbol = str(tick_dict.get("symbol", "")).upper()
        if not symbol:
            return

        ts = float(tick_dict.get("timestamp", time.time()))
        bid = float(tick_dict.get("bid", 0.0))
        ask = float(tick_dict.get("ask", 0.0))
        spread = float(tick_dict.get("spread", (ask - bid) * 10000 if bid > 0 else 0.0))
        vol = float(tick_dict.get("volume", 1.0))

        tick = Tick(symbol=symbol, timestamp=ts, bid=bid, ask=ask, spread=spread, volume=vol)

        # Store in tick circular buffer
        if symbol not in self._ticks:
            self._ticks[symbol] = deque(maxlen=self.max_ticks)
        self._ticks[symbol].append(tick)

        # Aggregate across timeframes
        mid_price = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else (bid or ask)
        if mid_price <= 0:
            return

        for tf, period_sec in TIMEFRAME_SECONDS.items():
            await self._update_timeframe_bar(symbol, tf, period_sec, ts, mid_price, vol)

    async def _update_timeframe_bar(
        self,
        symbol: str,
        timeframe: str,
        period_sec: int,
        ts: float,
        price: float,
        volume: float
    ) -> None:
        """Updates or completes a candle for a given timeframe."""
        key = (symbol, timeframe)
        bar_start = int(ts // period_sec) * period_sec
        
        cur = self._current_bar.get(key)
        if cur is None:
            # First bar initialization
            cur = Bar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=bar_start,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=volume,
                is_closed=False
            )
            self._current_bar[key] = cur
        elif cur.timestamp == bar_start:
            # Update existing bar
            cur.high = max(cur.high, price)
            cur.low = min(cur.low, price)
            cur.close = price
            cur.volume += volume
        else:
            # Existing bar closed!
            cur.is_closed = True
            if key not in self._bars:
                self._bars[key] = deque(maxlen=self.max_bars)
            self._bars[key].append(cur)

            # Persist closed bar to database asynchronously
            await self.db.execute_async(
                """
                INSERT INTO market_bars (symbol, timeframe, timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timeframe, timestamp) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume;
                """,
                (symbol, timeframe, cur.timestamp, cur.open, cur.high, cur.low, cur.close, cur.volume)
            )

            # Publish bar completed event onto the event bus
            event_bus.publish(
                EventType.BAR_COMPLETED,
                payload=cur.to_dict(),
                priority=EventPriority.NORMAL,
                source="MarketDataManager"
            )

            # Start new candle
            self._current_bar[key] = Bar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=bar_start,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=volume,
                is_closed=False
            )

    def get_bars(self, symbol: str, timeframe: str, count: int = 300) -> List[Bar]:
        """Returns the most recent completed and in-progress bars."""
        key = (symbol.upper(), timeframe.upper())
        out: List[Bar] = []
        if key in self._bars:
            out.extend(list(self._bars[key])[-count:])
        cur = self._current_bar.get(key)
        if cur:
            out.append(cur)

        # If cache is low, hydrate from database
        if len(out) < 20:
            db_rows = self.db.get_recent_bars(symbol, timeframe, limit=count)
            if db_rows:
                db_bars = [
                    Bar(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=r["timestamp"],
                        open=r["open"],
                        high=r["high"],
                        low=r["low"],
                        close=r["close"],
                        volume=r["volume"],
                        is_closed=True
                    )
                    for r in db_rows
                ]
                # Merge deduplicated
                existing_times = {b.timestamp for b in out}
                merged = [b for b in db_bars if b.timestamp not in existing_times] + out
                merged.sort(key=lambda x: x.timestamp)
                return merged[-count:]
        return out[-count:]

    def get_numpy_ohlcv(self, symbol: str, timeframe: str, count: int = 300) -> Dict[str, np.ndarray]:
        """
        Returns structured dictionary of 1D NumPy arrays (open, high, low, close, volume, timestamps)
        optimized for vectorized technical indicators and ML models.
        """
        bars = self.get_bars(symbol, timeframe, count=count)
        if not bars:
            return {
                "open": np.array([], dtype=np.float64),
                "high": np.array([], dtype=np.float64),
                "low": np.array([], dtype=np.float64),
                "close": np.array([], dtype=np.float64),
                "volume": np.array([], dtype=np.float64),
                "timestamp": np.array([], dtype=np.int64)
            }
        
        opens = np.fromiter((b.open for b in bars), dtype=np.float64, count=len(bars))
        highs = np.fromiter((b.high for b in bars), dtype=np.float64, count=len(bars))
        lows = np.fromiter((b.low for b in bars), dtype=np.float64, count=len(bars))
        closes = np.fromiter((b.close for b in bars), dtype=np.float64, count=len(bars))
        vols = np.fromiter((b.volume for b in bars), dtype=np.float64, count=len(bars))
        times = np.fromiter((b.timestamp for b in bars), dtype=np.int64, count=len(bars))

        return {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": vols,
            "timestamp": times
        }

    def get_latest_tick(self, symbol: str) -> Optional[Tick]:
        """Returns the most recent quote for a symbol."""
        sym = symbol.upper()
        if sym in self._ticks and self._ticks[sym]:
            return self._ticks[sym][-1]
        return None

    def seed_synthetic_bars_if_empty(self, symbol: str, timeframe: str, count: int = 150, base_price: float = 1.3000) -> None:
        """Seeds synthetic realistic geometric brownian motion candles if empty, ensuring indicators function immediately."""
        key = (symbol.upper(), timeframe.upper())
        if self.get_bars(symbol, timeframe, count=10):
            return  # Already has bars
            
        now = int(time.time())
        period = TIMEFRAME_SECONDS.get(timeframe.upper(), 3600)
        bars = []
        price = base_price
        
        np.random.seed(42)
        returns = np.random.normal(0.0001, 0.0015, count)
        
        for i in range(count):
            t = now - (count - i) * period
            o = price
            ret = returns[i]
            c = o * (1.0 + ret)
            h = max(o, c) + abs(np.random.normal(0, 0.0008)) * price
            l = min(o, c) - abs(np.random.normal(0, 0.0008)) * price
            vol = float(np.random.randint(50, 500))
            price = c
            bars.append({
                "timestamp": t,
                "open": round(o, 5),
                "high": round(h, 5),
                "low": round(l, 5),
                "close": round(c, 5),
                "volume": vol
            })
            
        self.db.save_bars_batch(symbol.upper(), timeframe.upper(), bars)
        logger.info(f"Seeded {count} synthetic bars for {symbol} {timeframe}")
