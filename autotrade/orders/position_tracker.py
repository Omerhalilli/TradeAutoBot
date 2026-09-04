"""
Active Position Tracker, Trailing Stop Guardian & Partial Profit Manager.
Monitors real-time open positions, automatically locks in Break-Even (+1 pip),
advances Dynamic Trailing Stops, and executes Multi-Tier Partial Take-Profits.
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
import logging
import time
from typing import Any, Dict, List, Optional

from autotrade.analytics.precision import PrecisionMath
from autotrade.core.config_manager import get_config
from autotrade.core.event_bus import event_bus, EventType, EventPriority
from autotrade.orders.execution_router import ExecutionRouter
from autotrade.orders.order_types import TradeOrder, PartialTarget

logger = logging.getLogger("autotrade.orders.position_tracker")


class PositionTracker:
    """
    Continuous position lifecycle supervisor.
    Automates break-even triggers, trailing stops, and tiered scaling.
    """
    def __init__(self, router: Optional[ExecutionRouter] = None):
        self.config = get_config()
        self.router = router or ExecutionRouter()
        self._active_orders: Dict[int, TradeOrder] = {}  # {ticket: TradeOrder}
        self._breakeven_activated_tickets: set[int] = set()

    def register_order(self, order: TradeOrder) -> None:
        """Adds filled order to active tracking registry."""
        if order.ticket > 0:
            self._active_orders[order.ticket] = order
            logger.debug(f"Registered ticket #{order.ticket} ({order.symbol}) in PositionTracker")

    def unregister_order(self, ticket: int) -> None:
        """Removes closed order from tracking registry."""
        self._active_orders.pop(ticket, None)
        self._breakeven_activated_tickets.discard(ticket)

    async def evaluate_all_active_positions(self) -> None:
        """
        Periodically polls MT4 open positions and evaluates Trailing Stop / Break-Even rules.
        """
        try:
            from zmq_client import zmq_client
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(None, zmq_client.get_positions)
            if res.get("status") != "ok":
                return

            positions = res.get("positions", [])
            for p in positions:
                ticket = int(p.get("ticket", 0))
                symbol = p.get("symbol", "")
                cmd = p.get("cmd", "BUY").upper()
                open_price = float(p.get("open_price", 0.0))
                current_price = float(p.get("current_price", open_price))
                current_sl = float(p.get("sl", 0.0))
                lots = float(p.get("lots", 0.0))

                await self._evaluate_single_position(
                    ticket=ticket,
                    symbol=symbol,
                    cmd=cmd,
                    open_price=open_price,
                    current_price=current_price,
                    current_sl=current_sl,
                    lots=lots
                )
        except Exception as ex:
            logger.debug(f"Position evaluation check failed: {ex}")

    async def _evaluate_single_position(
        self,
        ticket: int,
        symbol: str,
        cmd: str,
        open_price: float,
        current_price: float,
        current_sl: float,
        lots: float
    ) -> None:
        """Applies algorithmic break-even and trailing stop logic to an individual trade."""
        is_buy = "BUY" in cmd
        pip_size = float(PrecisionMath.get_pip_size(symbol))

        # 1. Break-Even Check
        if self.config.risk.enable_breakeven and ticket not in self._breakeven_activated_tickets:
            trigger_pips = self.config.risk.breakeven_trigger_pips
            lock_pips = self.config.risk.breakeven_lock_pips
            
            pips_in_profit = (current_price - open_price) / pip_size if is_buy else (open_price - current_price) / pip_size
            
            if pips_in_profit >= trigger_pips:
                # Calculate new break-even SL
                new_sl = open_price + (lock_pips * pip_size) if is_buy else open_price - (lock_pips * pip_size)
                new_sl = PrecisionMath.round_price(symbol, new_sl)

                # Send modification
                logger.info(f"🛡️ Activating Break-Even on #{ticket} ({symbol}) at {new_sl} (+{lock_pips} pip lock)")
                res = await self.router.modify_sl_tp(ticket=ticket, sl=new_sl)
                if res.get("status") == "ok":
                    self._breakeven_activated_tickets.add(ticket)
                    event_bus.publish(
                        EventType.BREAKEVEN_ACTIVATED,
                        payload={"ticket": ticket, "symbol": symbol, "sl": new_sl},
                        priority=EventPriority.HIGH,
                        source="PositionTracker"
                    )

        # 2. Dynamic Trailing Stop Check
        if self.config.risk.enable_trailing_stop:
            trail_pips = self.config.risk.default_trailing_pips
            trail_distance = trail_pips * pip_size

            if is_buy:
                proposed_sl = PrecisionMath.round_price(symbol, current_price - trail_distance)
                if proposed_sl > open_price and proposed_sl > (current_sl + 2 * pip_size):
                    await self.router.modify_sl_tp(ticket=ticket, sl=proposed_sl)
            else:
                proposed_sl = PrecisionMath.round_price(symbol, current_price + trail_distance)
                if (proposed_sl < open_price and (current_sl == 0.0 or proposed_sl < (current_sl - 2 * pip_size))):
                    await self.router.modify_sl_tp(ticket=ticket, sl=proposed_sl)

        # 3. Multi-Tier Partial Take-Profit Check
        tracked_order = self._active_orders.get(ticket)
        if tracked_order and tracked_order.partial_targets:
            for target in tracked_order.partial_targets:
                if target.is_executed:
                    continue
                hit_tp = (current_price >= target.target_price) if is_buy else (current_price <= target.target_price)
                if hit_tp:
                    close_fraction = max(0.05, min(1.0, target.close_fraction))
                    partial_lots = PrecisionMath.round_lot(lots * close_fraction)
                    if partial_lots > 0:
                        logger.info(
                            f"🎯 Tiered Take-Profit hit on #{ticket} ({symbol}) at {current_price}. "
                            f"Closing {partial_lots:.2f} lots ({close_fraction * 100:.0f}%)"
                        )
                        res = await self.router.close_position(ticket=ticket, lots=partial_lots)
                        if res.get("status") == "ok":
                            target.is_executed = True
                            target.executed_time = time.time()
                            tracked_order.lots = max(0.01, round(lots - partial_lots, 2))
                            event_bus.publish(
                                EventType.ORDER_PARTIAL_FILL,
                                payload={
                                    "ticket": ticket,
                                    "symbol": symbol,
                                    "closed_lots": partial_lots,
                                    "remaining_lots": tracked_order.lots,
                                    "price": current_price,
                                    "target_price": target.target_price
                                },
                                priority=EventPriority.HIGH,
                                source="PositionTracker"
                            )

        # 4. Partial Stop-Loss Check (protect capital if 75% adverse drift to SL)
        if tracked_order and tracked_order.sl > 0:
            sl_distance = abs(open_price - tracked_order.sl)
            current_adverse = (open_price - current_price) if is_buy else (current_price - open_price)
            if sl_distance > 0 and current_adverse >= 0.75 * sl_distance and not getattr(tracked_order, "partial_sl_executed", False):
                cut_lots = PrecisionMath.round_lot(lots * 0.50)
                if cut_lots > 0:
                    logger.warning(
                        f"⚠️ Partial Stop-Loss triggered on #{ticket} ({symbol}) at 75% adverse drift. Cutting {cut_lots:.2f} lots."
                    )
                    res = await self.router.close_position(ticket=ticket, lots=cut_lots)
                    if res.get("status") == "ok":
                        setattr(tracked_order, "partial_sl_executed", True)
                        tracked_order.lots = max(0.01, round(lots - cut_lots, 2))
                        event_bus.publish(
                            EventType.ORDER_PARTIAL_FILL,
                            payload={
                                "ticket": ticket,
                                "symbol": symbol,
                                "type": "PARTIAL_SL",
                                "closed_lots": cut_lots,
                                "remaining_lots": tracked_order.lots
                            },
                            priority=EventPriority.HIGH,
                            source="PositionTracker"
                        )
