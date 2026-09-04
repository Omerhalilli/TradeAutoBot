"""
Order Domain Schemas, Enums & Complex Execution Structures.
Defines specifications for Market, Limit, Stop, Stop-Limit, Trailing Stop, OCO, and Bracket orders.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional
import uuid


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TRAILING_STOP = "TRAILING_STOP"
    OCO = "OCO"
    BRACKET = "BRACKET"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class PartialTarget:
    """Specification for tiered profit taking (TP1, TP2, TP3)."""
    target_price: float
    close_fraction: float  # e.g., 0.33 for 33% partial close
    is_executed: bool = False
    executed_time: Optional[float] = None


@dataclass
class TradeOrder:
    """Master representation of an execution order across MT4 and internal state."""
    order_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    ticket: int = 0
    symbol: str = "GBPUSD"
    order_type: OrderType = OrderType.MARKET
    side: OrderSide = OrderSide.BUY
    lots: float = 0.01
    price: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    trailing_stop_pips: int = 0
    breakeven_pips: int = 0
    breakeven_lock_pips: int = 1
    is_breakeven_active: bool = False
    partial_targets: List[PartialTarget] = field(default_factory=list)
    magic: int = 100100
    strategy_name: str = "QuantitativeCore"
    status: OrderStatus = OrderStatus.PENDING
    created_at: float = field(default_factory=time.time)
    filled_at: Optional[float] = None
    filled_price: float = 0.0
    close_price: float = 0.0
    pnl: float = 0.0
    oco_linked_id: Optional[str] = None
    comment: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "ticket": self.ticket,
            "symbol": self.symbol,
            "order_type": self.order_type.value,
            "side": self.side.value,
            "lots": self.lots,
            "price": self.price,
            "sl": self.sl,
            "tp": self.tp,
            "trailing_stop_pips": self.trailing_stop_pips,
            "breakeven_pips": self.breakeven_pips,
            "status": self.status.value,
            "magic": self.magic,
            "strategy_name": self.strategy_name,
            "created_at": self.created_at,
            "pnl": self.pnl
        }


@dataclass
class BracketOrder:
    """
    Composite Bracket Order: Combines primary entry with attached Stop-Loss,
    Take-Profit, and trailing parameters.
    """
    primary_order: TradeOrder
    profit_target_price: float
    stop_loss_price: float
    trailing_pips: int = 20
    partial_targets: List[PartialTarget] = field(default_factory=list)


@dataclass
class OCOOrderGroup:
    """
    One-Cancels-Other (OCO) order pair. If either leg triggers or fills,
    the counter-leg is immediately cancelled.
    """
    group_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    order_a: TradeOrder = field(default_factory=TradeOrder)
    order_b: TradeOrder = field(default_factory=TradeOrder)
    is_active: bool = True
