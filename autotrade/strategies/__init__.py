"""
Strategy Layer package.
Modular quantitative trading strategies with event-driven execution,
multi-timeframe technical models, machine learning predictors, and dynamic parameter optimization.
"""

from autotrade.strategies.base_strategy import BaseStrategy, StrategySignal
from autotrade.strategies.trend_following import TrendFollowingStrategy
from autotrade.strategies.mean_reversion import MeanReversionStrategy
from autotrade.strategies.breakout import BreakoutStrategy
from autotrade.strategies.ml_strategy import MLPredictorStrategy
from autotrade.strategies.news_straddle import NewsStraddleStrategy
from autotrade.strategies.grid_averaging import SmartGridStrategy
from autotrade.strategies.strategy_manager import StrategyManager

__all__ = [
    "BaseStrategy",
    "StrategySignal",
    "TrendFollowingStrategy",
    "MeanReversionStrategy",
    "BreakoutStrategy",
    "MLPredictorStrategy",
    "NewsStraddleStrategy",
    "SmartGridStrategy",
    "StrategyManager",
]
