"""
Order Management & Trade Execution Layer.
Supports Market, Limit, Stop, Stop-Limit, Trailing Stop, OCO, and Bracket orders,
with dynamic partial take-profits, break-even locking, and scale-in averaging.
"""

from autotrade.orders.order_types import (
    OrderType,
    OrderSide,
    OrderStatus,
    TradeOrder,
    BracketOrder,
    OCOOrderGroup
)
from autotrade.orders.execution_router import ExecutionRouter
from autotrade.orders.position_tracker import PositionTracker
from autotrade.orders.order_manager import OrderManager

__all__ = [
    "OrderType",
    "OrderSide",
    "OrderStatus",
    "TradeOrder",
    "BracketOrder",
    "OCOOrderGroup",
    "ExecutionRouter",
    "PositionTracker",
    "OrderManager",
]
