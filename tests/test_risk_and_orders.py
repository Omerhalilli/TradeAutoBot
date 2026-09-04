"""
Unit tests for Risk Management, Position Sizing, and Order Lifecycle.
"""

import asyncio
import unittest
from autotrade.orders.order_types import TradeOrder, OrderSide, OrderType, OrderStatus, OCOOrderGroup
from autotrade.orders.execution_router import ExecutionRouter
from autotrade.orders.position_tracker import PositionTracker
from autotrade.orders.order_manager import OrderManager
from autotrade.risk.position_sizer import PositionSizer, SizingMethod
from autotrade.risk.risk_manager import RiskManager


class TestRiskAndOrders(unittest.TestCase):
    def setUp(self):
        self.sizer = PositionSizer()
        self.risk = RiskManager(position_sizer=self.sizer)
        self.router = ExecutionRouter(simulation_mode=True)
        self.tracker = PositionTracker(router=self.router)
        self.order_mgr = OrderManager(
            router=self.router,
            risk_manager=self.risk,
            position_tracker=self.tracker
        )

    def test_position_sizer_methods(self):
        # 1. Percent risk
        lots_pct = self.sizer.calculate_lot_size(
            symbol="GBPUSD",
            method=SizingMethod.PERCENTAGE_RISK,
            balance=100000.0,
            entry_price=1.3500,
            stop_loss=1.3480
        )
        self.assertGreater(lots_pct, 0.0)
        self.assertLessEqual(lots_pct, 5.0)

        # 2. Kelly Criterion
        lots_kelly = self.sizer.calculate_lot_size(
            symbol="GBPUSD",
            method=SizingMethod.KELLY_CRITERION,
            balance=100000.0,
            entry_price=1.3500,
            stop_loss=1.3480,
            win_rate=0.60,
            profit_factor=2.0
        )
        self.assertGreater(lots_kelly, 0.0)

        # 3. Volatility ATR
        lots_atr = self.sizer.calculate_lot_size(
            symbol="GBPUSD",
            method=SizingMethod.VOLATILITY_ATR,
            balance=100000.0,
            entry_price=1.3500,
            stop_loss=1.3480,
            atr_value=0.0030
        )
        self.assertGreater(lots_atr, 0.0)

    def test_risk_manager_pre_order_checks(self):
        account = {"balance": 100000.0, "equity": 100000.0, "margin_free": 90000.0}
        open_pos = []

        # Valid trade check
        res = self.risk.evaluate_order_risk(
            symbol="GBPUSD",
            cmd="BUY",
            lots=0.10,
            price=1.3500,
            sl=1.3480,
            tp=1.3540,
            account_info=account,
            open_positions=open_pos
        )
        self.assertTrue(res.passed)

        # News volatility lot reduction
        res_news = self.risk.evaluate_order_risk(
            symbol="GBPUSD",
            cmd="BUY",
            lots=1.00,
            price=1.3500,
            sl=1.3480,
            tp=1.3540,
            account_info=account,
            open_positions=open_pos,
            is_news_imminent=True
        )
        self.assertTrue(res_news.passed)
        self.assertLess(res_news.adjusted_lots, 1.00)

        # Max open positions breach
        many_pos = [{"symbol": "EURUSD", "lots": 0.1, "cmd": "BUY"} for _ in range(15)]
        res_max = self.risk.evaluate_order_risk(
            symbol="GBPUSD",
            cmd="BUY",
            lots=0.10,
            price=1.3500,
            sl=1.3480,
            tp=1.3540,
            account_info=account,
            open_positions=many_pos
        )
        self.assertFalse(res_max.passed)
        self.assertIn("Maximum open positions", res_max.reason)

    def test_simulated_order_execution(self):
        async def run_order():
            order = TradeOrder(
                symbol="EURUSD",
                side=OrderSide.BUY,
                lots=0.05,
                price=1.0850,
                sl=1.0820,
                tp=1.0910
            )
            res = await self.order_mgr.submit_order(order)
            self.assertTrue(res.get("success"))
            self.assertGreater(order.ticket, 0)
            self.assertEqual(order.status, OrderStatus.FILLED)

        asyncio.run(run_order())


if __name__ == "__main__":
    unittest.main()
