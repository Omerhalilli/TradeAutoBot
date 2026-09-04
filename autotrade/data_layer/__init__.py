"""
Data Layer package for AutoTrade Institutional Trading System.
Provides high-performance WAL SQLite database engine, multi-timeframe candle aggregators,
compressed time-series storage, and economic news sentiment feeds.
"""

from autotrade.data_layer.database import DatabaseEngine, db_engine
from autotrade.data_layer.market_data import MarketDataManager, Bar, Tick
from autotrade.data_layer.storage import TimeSeriesStorage
from autotrade.data_layer.news_feed import NewsFeedService, EconomicEvent

__all__ = [
    "DatabaseEngine",
    "db_engine",
    "MarketDataManager",
    "Bar",
    "Tick",
    "TimeSeriesStorage",
    "NewsFeedService",
    "EconomicEvent",
]
