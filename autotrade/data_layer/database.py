"""
High-Performance SQLite Database Engine with WAL Mode & Async Execution.
Manages relational storage for trades, ticks, candles, backtest results, and audit trails.
Optimized for high-throughput institutional workloads with memory-mapped I/O and indexed tables.
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("autotrade.data_layer.database")

DEFAULT_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "autotrade.db"))


class DatabaseEngine:
    """
    Thread-safe SQLite relational database engine with Write-Ahead Logging (WAL)
    and asynchronous thread-pool query dispatch.
    """
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._local = threading.local()
        self._lock = threading.RLock()
        self._is_initialized = False

    def get_connection(self) -> sqlite3.Connection:
        """Returns a thread-local SQLite connection with optimized PRAGMAs."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                check_same_thread=False,
                isolation_level=None # Autocommit mode for granular transaction control
            )
            conn.row_factory = sqlite3.Row
            # Institutional Performance PRAGMAs
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA cache_size = -64000;")     # 64 MB cache
            conn.execute("PRAGMA mmap_size = 268435456;")   # 256 MB memory-mapped I/O
            conn.execute("PRAGMA temp_store = MEMORY;")
            conn.execute("PRAGMA busy_timeout = 10000;")
            self._local.conn = conn
        return self._local.conn

    async def initialize(self) -> None:
        """Asynchronously creates required tables and performance indices."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._create_tables_and_indices)
        self._is_initialized = True
        logger.info(f"Database initialized at {self.db_path} with WAL mode.")

    def _create_tables_and_indices(self) -> None:
        """Executes table creation DDL statements."""
        conn = self.get_connection()
        with self._lock:
            # 1. Trades Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    ticket INTEGER PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    cmd TEXT NOT NULL,
                    open_time TEXT NOT NULL,
                    open_price REAL NOT NULL,
                    close_time TEXT,
                    close_price REAL,
                    lots REAL NOT NULL,
                    sl REAL DEFAULT 0.0,
                    tp REAL DEFAULT 0.0,
                    pnl REAL DEFAULT 0.0,
                    commission REAL DEFAULT 0.0,
                    swap REAL DEFAULT 0.0,
                    magic INTEGER DEFAULT 0,
                    strategy_name TEXT,
                    exit_reason TEXT,
                    created_at REAL NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_open_time ON trades(open_time);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy_name);")

            # 2. Historical Bars (Candles) Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_bars (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    PRIMARY KEY (symbol, timeframe, timestamp)
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bars_symbol_tf_time ON market_bars(symbol, timeframe, timestamp DESC);")

            # 3. Market Ticks Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    bid REAL NOT NULL,
                    ask REAL NOT NULL,
                    spread REAL NOT NULL,
                    volume REAL DEFAULT 1.0
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ticks_symbol_time ON market_ticks(symbol, timestamp DESC);")

            # 4. Strategy Signals Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS strategy_signals (
                    id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    strategy_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    sl REAL,
                    tp REAL,
                    sizing_method TEXT,
                    status TEXT NOT NULL,
                    meta_json TEXT
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_sym_time ON strategy_signals(symbol, timestamp DESC);")

            # 5. Audit Logs Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    category TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details_json TEXT
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(timestamp DESC);")

            # 6. Optimization History Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS optimization_runs (
                    id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    strategy_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    sharpe_ratio REAL NOT NULL,
                    profit_factor REAL NOT NULL,
                    win_rate REAL NOT NULL,
                    max_drawdown_pct REAL NOT NULL,
                    total_trades INTEGER NOT NULL
                );
            """)

    def execute(self, query: str, params: Union[tuple, dict] = ()) -> sqlite3.Cursor:
        """Synchronously executes a parameterized query."""
        conn = self.get_connection()
        return conn.execute(query, params)

    def executemany(self, query: str, param_list: List[Union[tuple, dict]]) -> sqlite3.Cursor:
        """Synchronously executes a batch of queries inside a transaction."""
        conn = self.get_connection()
        return conn.executemany(query, param_list)

    def fetch_all(self, query: str, params: Union[tuple, dict] = ()) -> List[Dict[str, Any]]:
        """Synchronously executes a query and returns all matching rows as dictionaries."""
        cursor = self.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def fetch_one(self, query: str, params: Union[tuple, dict] = ()) -> Optional[Dict[str, Any]]:
        """Synchronously executes a query and returns the first row as a dictionary."""
        cursor = self.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    # Asynchronous query helpers
    async def execute_async(self, query: str, params: Union[tuple, dict] = ()) -> None:
        """Asynchronously executes a parameterized statement."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.execute, query, params)

    async def fetch_all_async(self, query: str, params: Union[tuple, dict] = ()) -> List[Dict[str, Any]]:
        """Asynchronously executes a query and returns all rows."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.fetch_all, query, params)

    async def fetch_one_async(self, query: str, params: Union[tuple, dict] = ()) -> Optional[Dict[str, Any]]:
        """Asynchronously executes a query and returns a single row."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.fetch_one, query, params)

    # High-level domain persistence methods
    def save_trade(self, trade_data: Dict[str, Any]) -> None:
        """Inserts or updates a trade record."""
        query = """
            INSERT INTO trades (
                ticket, symbol, cmd, open_time, open_price, close_time, close_price,
                lots, sl, tp, pnl, commission, swap, magic, strategy_name, exit_reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticket) DO UPDATE SET
                close_time=excluded.close_time,
                close_price=excluded.close_price,
                sl=excluded.sl,
                tp=excluded.tp,
                pnl=excluded.pnl,
                swap=excluded.swap,
                exit_reason=excluded.exit_reason;
        """
        params = (
            trade_data.get("ticket"),
            trade_data.get("symbol"),
            trade_data.get("cmd"),
            trade_data.get("open_time"),
            float(trade_data.get("open_price", 0.0)),
            trade_data.get("close_time"),
            float(trade_data.get("close_price", 0.0)) if trade_data.get("close_price") is not None else None,
            float(trade_data.get("lots", 0.0)),
            float(trade_data.get("sl", 0.0)),
            float(trade_data.get("tp", 0.0)),
            float(trade_data.get("pnl", 0.0)),
            float(trade_data.get("commission", 0.0)),
            float(trade_data.get("swap", 0.0)),
            int(trade_data.get("magic", 0)),
            trade_data.get("strategy_name", "manual"),
            trade_data.get("exit_reason", ""),
            time.time()
        )
        self.execute(query, params)

    def save_bars_batch(self, symbol: str, timeframe: str, bars: List[Dict[str, Any]]) -> None:
        """Batch inserts or updates OHLCV bars."""
        query = """
            INSERT INTO market_bars (symbol, timeframe, timestamp, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, timeframe, timestamp) DO UPDATE SET
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                volume=excluded.volume;
        """
        param_list = [
            (
                symbol,
                timeframe,
                int(b["timestamp"]),
                float(b["open"]),
                float(b["high"]),
                float(b["low"]),
                float(b["close"]),
                float(b.get("volume", 1.0))
            )
            for b in bars
        ]
        self.executemany(query, param_list)

    def get_recent_bars(self, symbol: str, timeframe: str, limit: int = 500) -> List[Dict[str, Any]]:
        """Retrieves recent bars sorted ascending by timestamp for technical calculation."""
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM market_bars
            WHERE symbol = ? AND timeframe = ?
            ORDER BY timestamp DESC
            LIMIT ?;
        """
        rows = self.fetch_all(query, (symbol, timeframe, limit))
        rows.reverse()
        return rows

    def record_audit(self, category: str, level: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Records an audit log entry."""
        query = "INSERT INTO audit_logs (timestamp, category, level, message, details_json) VALUES (?, ?, ?, ?, ?);"
        det_str = json.dumps(details) if details else None
        self.execute(query, (time.time(), category, level, message, det_str))

    async def close(self) -> None:
        """Closes thread-local connection cleanly."""
        if hasattr(self._local, "conn") and self._local.conn:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None


# Global singleton instance
db_engine = DatabaseEngine()
