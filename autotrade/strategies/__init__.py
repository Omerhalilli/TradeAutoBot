"""
Strategy Layer package.
Modular quantitative trading strategies powered by the Institutional Sniper Architecture.
"""

from autotrade.strategies.base_strategy import BaseStrategy, StrategySignal
from autotrade.strategies.sniper_strategy import SniperConfluenceStrategy, TrendFollowingStrategy
from autotrade.strategies.strategy_manager import StrategyManager

__all__ = [
    "BaseStrategy",
    "StrategySignal",
    "SniperConfluenceStrategy",
    "TrendFollowingStrategy",
    "StrategyManager",
]
