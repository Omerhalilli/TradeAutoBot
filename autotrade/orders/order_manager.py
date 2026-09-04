"""
Central Order Management System (OMS).
Coordinates order lifecycles, risk validation, complex bracket orders,
OCO interlocks, scaling in/out, and emergency liquidation.
"""

from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, List, Optional

from autotrade.core.event_bus import event_bus, EventType, EventPriority
from autotrade.orders.order_types import (
    TradeOrder,
    BracketOrder,
    OCOOrderGroup,
    OrderStatus,
    OrderSide,
    OrderType
)
from autotrade.orders.execution_router import ExecutionRouter
from autotrade.orders.position_tracker import PositionTracker
from autotrade.risk.risk_manager import RiskManager

logger = logging.getLogger("autotrade.orders.order_manager")


class OrderManager:
    """
    Master Order Manager coordinating pre-trade risk gating, bracket workflows, and router execution.
    """
    def __init__(
        self,
        router: Optional[ExecutionRouter] = None,
        risk_manager: Optional[RiskManager] = None,
        position_tracker: Optional[PositionTracker] = None
    ):
        self.router = router or ExecutionRouter()
        self.risk_manager = risk_manager or RiskManager()
        self.position_tracker = position_tracker or PositionTracker(router=self.router)
        self._oco_groups: Dict[str, OCOOrderGroup] = {}
        self._lock = asyncio.Lock()

    async def submit_order(
        self,
        order: TradeOrder,
        is_news_imminent: bool = False
    ) -> Dict[str, Any]:
        """
        Validates risk constraints and executes trade order.
        """
        async with self._lock:
            # Step 1: Query account state and open positions from MT4
            from zmq_client import zmq_client
            loop = asyncio.get_running_loop()
            acc_res = await loop.run_in_executor(None, zmq_client.get_account)
            pos_res = await loop.run_in_executor(None, zmq_client.get_positions)
            
            account_info = acc_res if acc_res.get("status") == "ok" else {"balance": 100000.0, "equity": 100000.0}
            open_positions = pos_res.get("positions", []) if pos_res.get("status") == "ok" else []

            # Step 2: Evaluate Risk Safeguards
            risk_res = self.risk_manager.evaluate_order_risk(
                symbol=order.symbol,
                cmd="BUY" if order.side == OrderSide.BUY else "SELL",
                lots=order.lots,
                price=order.price,
                sl=order.sl,
                tp=order.tp,
                account_info=account_info,
                open_positions=open_positions,
                is_news_imminent=is_news_imminent
            )

            if not risk_res.passed:
                logger.warning(f"Order rejected by RiskManager: {risk_res.reason}")
                order.status = OrderStatus.REJECTED
                return {"success": False, "reason": risk_res.reason}

            # Adjust lot size if risk manager modified it (e.g. news filter)
            order.lots = risk_res.adjusted_lots

            # Step 3: Route execution
            exec_res = await self.router.execute_order(order)
            if exec_res.get("success", False):
                self.position_tracker.register_order(order)
                
                # Check if this belongs to an OCO group
                if order.oco_linked_id and order.oco_linked_id in self._oco_groups:
                    await self._handle_oco_trigger(order.oco_linked_id, order.order_id)
                    
            return exec_res

    async def submit_bracket_order(self, bracket: BracketOrder) -> Dict[str, Any]:
        """
        Submits bracket parent order with attached Profit Target and Stop Loss.
        """
        order = bracket.primary_order
        order.sl = bracket.stop_loss_price
        order.tp = bracket.profit_target_price
        order.trailing_stop_pips = bracket.trailing_pips
        order.partial_targets = bracket.partial_targets
        return await self.submit_order(order)

    async def submit_oco_pair(self, group: OCOOrderGroup) -> None:
        """
        Registers an OCO order group and monitors fills.
        """
        group.order_a.oco_linked_id = group.group_id
        group.order_b.oco_linked_id = group.group_id
        self._oco_groups[group.group_id] = group
        logger.info(f"Registered OCO Order Group {group.group_id}")

    async def _handle_oco_trigger(self, group_id: str, filled_order_id: str) -> None:
        """Cancels sibling leg when one leg of an OCO group fills."""
        group = self._oco_groups.get(group_id)
        if not group or not group.is_active:
            return
        group.is_active = False

        sibling = group.order_b if group.order_a.order_id == filled_order_id else group.order_a
        if sibling.ticket > 0:
            logger.info(f"Cancelling OCO sibling ticket #{sibling.ticket}")
            await self.router.close_position(sibling.ticket)
        sibling.status = OrderStatus.CANCELLED

    async def close_position(self, ticket: int, lots: Optional[float] = None) -> Dict[str, Any]:
        """Closes position in whole or in part."""
        res = await self.router.close_position(ticket=ticket, lots=lots)
        if res.get("status") == "ok":
            self.position_tracker.unregister_order(ticket)
        return res

    async def close_all_positions(self, reason: str = "Emergency Button") -> Dict[str, Any]:
        """Closes all active positions across the account."""
        logger.critical(f"Liquidating all positions. Reason: {reason}")
        res = await self.router.close_all_positions()
        self.position_tracker._active_orders.clear()
        return res

    async def scale_in(self, ticket: int, additional_lots: float) -> Dict[str, Any]:
        """
        Adds volume to an active position (pyramiding winning trades or cost averaging).
        """
        order = self.position_tracker._active_orders.get(ticket)
        if not order:
            return {"success": False, "reason": "Ticket not found in tracker"}

        scale_order = TradeOrder(
            symbol=order.symbol,
            side=order.side,
            lots=additional_lots,
            sl=order.sl,
            tp=order.tp,
            magic=order.magic,
            strategy_name=f"{order.strategy_name}-ScaleIn"
        )
        return await self.submit_order(scale_order)
