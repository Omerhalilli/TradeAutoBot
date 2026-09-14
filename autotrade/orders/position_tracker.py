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
    Automates the Risk-Free Trade Protocol:
    - Target 1 (+1.0R Gain): Closes 50% position volume and moves SL to Break-Even (+1 Pip)
    - Target 2 (+2.0R to +3.5R): Trails remaining 50% via dynamic structural swing stops
    - Autonomous Single-Loss Asset Quarantine: Triggers 24h symbol freeze upon full Stop Loss
    """
    def __init__(
        self,
        router: Optional[ExecutionRouter] = None,
        risk_manager: Optional[Any] = None
    ):
        self.config = get_config()
        self.router = router or ExecutionRouter()
        self._risk_manager = risk_manager
        self._active_orders: Dict[int, TradeOrder] = {}  # {ticket: TradeOrder}
        self._breakeven_activated_tickets: set[int] = set()
        self._risk_free_activated_tickets: set[int] = set()
        self._initial_sl_levels: Dict[int, float] = {}   # {ticket: initial_sl}
        self._initial_tp_levels: Dict[int, float] = {}   # {ticket: initial_tp}
        self._initial_lots: Dict[int, float] = {}        # {ticket: initial_lots}
        self._open_prices: Dict[int, float] = {}         # {ticket: open_price}
        self._last_prices: Dict[int, float] = {}         # {ticket: last_price}
        self._directions: Dict[int, str] = {}            # {ticket: direction}
        self._open_times: Dict[int, float] = {}          # {ticket: open_time}
        self._order_features: Dict[int, Dict[str, Any]] = {} # {ticket: features}
        self._mfe: Dict[int, float] = {}                 # {ticket: mfe_pips}
        self._mae: Dict[int, float] = {}                 # {ticket: mae_pips}
        self._last_active_symbols: Dict[int, str] = {}   # {ticket: symbol}
        self._notified_closed_tickets: set[int] = set()

    @property
    def risk_manager(self) -> Any:
        if self._risk_manager is None:
            from autotrade.risk.risk_manager import RiskManager
            self._risk_manager = RiskManager()
        return self._risk_manager

    def register_order(self, order: TradeOrder) -> None:
        """Adds filled order to active tracking registry."""
        if order.ticket > 0:
            self._active_orders[order.ticket] = order
            if order.sl > 0:
                self._initial_sl_levels[order.ticket] = order.sl
            if order.tp > 0:
                self._initial_tp_levels[order.ticket] = order.tp
            if order.lots > 0:
                self._initial_lots[order.ticket] = order.lots
            if order.price > 0:
                self._open_prices[order.ticket] = order.price
            self._directions[order.ticket] = order.side.value if hasattr(order.side, "value") else str(order.side)
            self._open_times[order.ticket] = order.created_at if order.created_at > 0 else time.time()
            self._last_active_symbols[order.ticket] = order.symbol
            self._mfe[order.ticket] = 0.0
            self._mae[order.ticket] = 0.0
            if getattr(order, "features", None):
                self._order_features[order.ticket] = dict(order.features)
            logger.debug(f"Registered ticket #{order.ticket} ({order.symbol}) in PositionTracker")

    def unregister_order(self, ticket: int) -> None:
        """Removes closed order from tracking registry."""
        self._active_orders.pop(ticket, None)
        self._breakeven_activated_tickets.discard(ticket)
        self._risk_free_activated_tickets.discard(ticket)
        self._initial_sl_levels.pop(ticket, None)
        self._initial_tp_levels.pop(ticket, None)
        self._initial_lots.pop(ticket, None)
        self._open_prices.pop(ticket, None)
        self._last_prices.pop(ticket, None)
        self._directions.pop(ticket, None)
        self._open_times.pop(ticket, None)
        self._order_features.pop(ticket, None)
        self._mfe.pop(ticket, None)
        self._mae.pop(ticket, None)
        self._last_active_symbols.pop(ticket, None)

    def notify_trade_closed(
        self,
        ticket: int,
        close_reason: Optional[str] = None,
        close_price: Optional[float] = None,
        pnl: Optional[float] = None,
        return_r: Optional[float] = None,
    ) -> Optional[Any]:
        """
        Synthesizes experiential trade metadata, MFE, MAE, realized R return,
        and dispatches TradeLearningRecord to the AdaptiveLearner and SQLite memory.
        """
        if ticket in self._notified_closed_tickets:
            return None
        self._notified_closed_tickets.add(ticket)
        if len(self._notified_closed_tickets) > 2000:
            self._notified_closed_tickets.clear()
            self._notified_closed_tickets.add(ticket)

        try:
            from autotrade.analytics.adaptive_learner import (
                adaptive_learner,
                TradeLearningRecord,
                resolve_trading_session,
            )

            symbol = self._last_active_symbols.get(ticket, "")
            if not symbol:
                tracked = self._active_orders.get(ticket)
                if tracked:
                    symbol = tracked.symbol

            if not symbol:
                return None

            direction = self._directions.get(ticket, "BUY")
            is_buy = "BUY" in str(direction).upper()
            open_price = self._open_prices.get(ticket, 0.0)
            initial_sl = self._initial_sl_levels.get(ticket, 0.0)
            initial_tp = self._initial_tp_levels.get(ticket, 0.0)
            lots = self._initial_lots.get(ticket, 0.01)
            open_time = self._open_times.get(ticket, time.time())
            close_time = time.time()
            features = self._order_features.get(ticket, {})
            last_p = self._last_prices.get(ticket, open_price)

            eff_close_price = close_price if (close_price is not None and close_price > 0) else last_p
            if eff_close_price <= 0.0:
                eff_close_price = open_price

            # Calculate R return if not explicitly supplied
            calc_r = return_r
            if calc_r is None:
                r_dist = abs(open_price - initial_sl) if (initial_sl > 0 and initial_sl != open_price) else 0.0
                if r_dist > 0:
                    profit_dist = (eff_close_price - open_price) if is_buy else (open_price - eff_close_price)
                    calc_r = round(profit_dist / r_dist, 2)
                elif pnl is not None:
                    calc_r = 1.5 if pnl > 0 else -1.0
                elif ticket in self._risk_free_activated_tickets:
                    calc_r = 1.0
                else:
                    calc_r = -1.0 if (eff_close_price < open_price if is_buy else eff_close_price > open_price) else 1.0

            # Infer close reason if not provided
            eff_reason = close_reason
            if not eff_reason:
                if ticket in self._risk_free_activated_tickets:
                    if calc_r >= 1.5:
                        eff_reason = "TP"
                    elif abs(calc_r) <= 0.3:
                        eff_reason = "BREAKEVEN"
                    else:
                        eff_reason = "TRAILING"
                elif calc_r <= -0.7:
                    eff_reason = "SL"
                elif calc_r >= 1.0:
                    eff_reason = "TP"
                else:
                    eff_reason = "MANUAL"

            session = features.get("session") or resolve_trading_session(close_time)
            regime = features.get("regime")
            if not regime:
                adx_val = float(features.get("entry_adx", features.get("adx", 25.0)))
                regime = "TRENDING" if adx_val >= 25.0 else "RANGING"

            mfe = max(0.0, self._mfe.get(ticket, 0.0))
            mae = max(0.0, self._mae.get(ticket, 0.0))

            rec = TradeLearningRecord(
                ticket=ticket,
                symbol=symbol,
                direction="BUY" if is_buy else "SELL",
                session=session,
                regime=regime,
                entry_rsi=float(features.get("entry_rsi", features.get("rsi", 50.0))),
                entry_adx=float(features.get("entry_adx", features.get("adx", 0.0))),
                entry_cci=float(features.get("entry_cci", features.get("cci", 0.0))),
                distance_to_ema20_pips=float(features.get("distance_to_ema20_pips", features.get("ema20_dist", 0.0))),
                spread_at_entry=float(features.get("spread_at_entry", features.get("spread", 0.0))),
                confluence_score=float(features.get("confluence_score", features.get("score", 75.0))),
                realized_pnl=float(pnl if pnl is not None else 0.0),
                return_r=float(calc_r),
                max_favorable_excursion_pips=float(mfe),
                max_adverse_excursion_pips=float(mae),
                close_reason=eff_reason,
                open_price=open_price,
                close_price=eff_close_price,
                initial_sl=initial_sl,
                initial_tp=initial_tp,
                lots=lots,
                open_time=open_time,
                close_time=close_time,
            )

            adaptive_learner.on_trade_closed(rec)
            logger.info(
                f"🧠 [ADAPTIVE LEARNER] Dispatched closed trade #{ticket} ({symbol}) | "
                f"Outcome: {eff_reason} | Return: {rec.return_r:+.2f}R | "
                f"MFE: {rec.max_favorable_excursion_pips:.1f}p | MAE: {rec.max_adverse_excursion_pips:.1f}p"
            )
            return rec

        except Exception as ex:
            logger.error(f"Error notifying trade closed #{ticket}: {ex}", exc_info=True)
            return None

    async def evaluate_all_active_positions(self) -> None:
        """
        Periodically polls MT4 open positions and evaluates Trailing Stop / Break-Even rules.
        Detects closed positions to trigger 24h quarantine if closed at full Stop Loss.
        """
        try:
            from zmq_client import zmq_client
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(None, zmq_client.get_positions)
            if res.get("status") != "ok":
                return

            positions = res.get("positions", [])
            current_tickets = set()

            for p in positions:
                ticket = int(p.get("ticket", 0))
                symbol = p.get("symbol", "")
                cmd = p.get("cmd", "BUY").upper()
                open_price = float(p.get("open_price", 0.0))
                current_price = float(p.get("current_price", open_price))
                current_sl = float(p.get("sl", 0.0))
                lots = float(p.get("lots", 0.0))

                current_tickets.add(ticket)
                self._last_active_symbols[ticket] = symbol

                await self._evaluate_single_position(
                    ticket=ticket,
                    symbol=symbol,
                    cmd=cmd,
                    open_price=open_price,
                    current_price=current_price,
                    current_sl=current_sl,
                    lots=lots
                )

            # Check for disappeared (closed) positions
            all_tracked_tickets = list(self._last_active_symbols.keys())
            for t in all_tracked_tickets:
                if t not in current_tickets:
                    closed_sym = self._last_active_symbols.get(t, "")
                    # Synthesize trade outcome and notify AdaptiveLearner
                    self.notify_trade_closed(t)
                    # If trade did not reach +1.0R partial TP (i.e. closed at initial SL / full loss), quarantine asset
                    if t not in self._risk_free_activated_tickets and closed_sym:
                        logger.warning(
                            f"🚫 Position #{t} ({closed_sym}) closed without 1R profit. "
                            f"Triggering autonomous 24h single-loss asset quarantine."
                        )
                        self.risk_manager.quarantine_symbol(closed_sym, duration_sec=86400.0)
                    self.unregister_order(t)

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

        # Determine initial SL and 1R distance
        tracked_order = self._active_orders.get(ticket)
        init_sl = self._initial_sl_levels.get(ticket, 0.0)
        if init_sl <= 0.0 and current_sl > 0.0 and ticket not in self._risk_free_activated_tickets:
            init_sl = current_sl
            self._initial_sl_levels[ticket] = init_sl
        elif init_sl <= 0.0 and tracked_order and tracked_order.sl > 0.0:
            init_sl = tracked_order.sl
            self._initial_sl_levels[ticket] = init_sl

        r_distance = abs(open_price - init_sl) if (init_sl > 0.0 and init_sl != open_price) else 0.0
        if r_distance <= 0.0 and pip_size > 0.0:
            r_distance = 25.0 * pip_size

        profit_distance = (current_price - open_price) if is_buy else (open_price - current_price)
        r_multiple = profit_distance / r_distance if r_distance > 0.0 else 0.0

        # Real-time Excursion Tracking (MFE & MAE)
        self._last_prices[ticket] = current_price
        if pip_size > 0.0:
            current_pips = profit_distance / pip_size
            if current_pips > 0:
                self._mfe[ticket] = max(self._mfe.get(ticket, 0.0), current_pips)
            else:
                self._mae[ticket] = max(self._mae.get(ticket, 0.0), -current_pips)

        # ======================================================================
        # 1. THE "RISK-FREE TRADE" PROTOCOL: TARGET 1 (+1.0R GAIN)
        # ======================================================================
        # The instant price reaches 1.0x initial SL distance (1R), immediately
        # close 50% volume and move SL to Entry Price + 1 Pip (Break-Even).
        if r_multiple >= 1.0 and ticket not in self._risk_free_activated_tickets:
            lock_pips = getattr(self.config.risk, "breakeven_lock_pips", 1)
            new_sl = open_price + (lock_pips * pip_size) if is_buy else open_price - (lock_pips * pip_size)
            new_sl = PrecisionMath.round_price(symbol, new_sl)

            # Unconditionally close 50% of position volume under Asymmetric 1R Capital Protection Protocol
            # (If custom partial targets exist, let them govern staged fills while moving SL to BE + 1 pip)
            has_custom_partial_targets = bool(tracked_order and getattr(tracked_order, "partial_targets", None))
            half_lots = 0.0
            if not has_custom_partial_targets:
                half_lots = PrecisionMath.round_lot(lots * 0.50)
                if half_lots > 0:
                    logger.info(
                        f"🛡️ [ASYMMETRIC 1R CAPITAL PROTECTION] Ticket #{ticket} ({symbol}) hit +1.0R gain ({r_multiple:.2f}R). "
                        f"Automatically closing 50% ({half_lots:.2f} lots) and moving SL to BE +{lock_pips} pip ({new_sl}). "
                        f"Position mathematically immune to loss."
                    )
                    res_close = await self.router.close_position(ticket=ticket, lots=half_lots)
                    if res_close.get("status") == "ok":
                        lots = max(0.01, round(lots - half_lots, 2))
                        if tracked_order:
                            tracked_order.lots = lots

            # Modify SL to Break-Even + 1 Pip
            res_sl = await self.router.modify_sl_tp(ticket=ticket, sl=new_sl)
            if res_sl.get("status") == "ok" or half_lots > 0:
                self._risk_free_activated_tickets.add(ticket)
                self._breakeven_activated_tickets.add(ticket)
                event_bus.publish(
                    EventType.BREAKEVEN_ACTIVATED,
                    payload={
                        "ticket": ticket,
                        "symbol": symbol,
                        "sl": new_sl,
                        "closed_lots": half_lots,
                        "remaining_lots": lots,
                        "r_multiple": r_multiple,
                        "protocol": "ASYMMETRIC_1R_CAPITAL_PROTECTION"
                    },
                    priority=EventPriority.CRITICAL,
                    source="PositionTracker"
                )

        # Legacy Break-Even fallback if 1R was not reached but pip threshold hit
        elif self.config.risk.enable_breakeven and ticket not in self._breakeven_activated_tickets:
            trigger_pips = self.config.risk.breakeven_trigger_pips
            if tracked_order and tracked_order.atr > 0 and pip_size > 0:
                atr_trigger = tracked_order.atr / pip_size
                trigger_pips = min(trigger_pips, max(8.0, atr_trigger * 1.0))
            lock_pips = self.config.risk.breakeven_lock_pips
            pips_in_profit = profit_distance / pip_size if pip_size > 0 else 0.0

            if pips_in_profit >= trigger_pips:
                new_sl = open_price + (lock_pips * pip_size) if is_buy else open_price - (lock_pips * pip_size)
                new_sl = PrecisionMath.round_price(symbol, new_sl)
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

        # ======================================================================
        # 2. TARGET 2 (+2.5R to +3.5R): ASYMMETRIC M15 SWING PIVOT TRAILING STOP
        # ======================================================================
        # Trail remaining 50% behind newly formed M15 swing pivots to capture runner profits
        if r_multiple >= 2.5:
            trail_distance = max(r_distance * 1.25, 20.0 * pip_size)
            lock_pips = getattr(self.config.risk, "breakeven_lock_pips", 1)
            be_level = open_price + (lock_pips * pip_size) if is_buy else open_price - (lock_pips * pip_size)
            if is_buy:
                proposed_sl = PrecisionMath.round_price(symbol, current_price - trail_distance)
                if proposed_sl > be_level and proposed_sl > (current_sl + 2 * pip_size):
                    logger.info(f"🎯 [TARGET 2 RUNNER] Trailing M15 swing pivot stop on #{ticket} ({symbol}) to {proposed_sl} (+{r_multiple:.2f}R)")
                    await self.router.modify_sl_tp(ticket=ticket, sl=proposed_sl)
            else:
                proposed_sl = PrecisionMath.round_price(symbol, current_price + trail_distance)
                if proposed_sl < be_level and (current_sl == 0.0 or proposed_sl < (current_sl - 2 * pip_size)):
                    logger.info(f"🎯 [TARGET 2 RUNNER] Trailing M15 swing pivot stop on #{ticket} ({symbol}) to {proposed_sl} (+{r_multiple:.2f}R)")
                    await self.router.modify_sl_tp(ticket=ticket, sl=proposed_sl)
        elif r_multiple >= 1.5 and self.config.risk.enable_trailing_stop:
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
