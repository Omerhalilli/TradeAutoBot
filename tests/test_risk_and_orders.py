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

    def test_scale_out_and_cost_average(self):
        async def run_scale():
            order = TradeOrder(
                symbol="GBPUSD",
                side=OrderSide.BUY,
                lots=0.20,
                price=1.3000,
                sl=1.2950,
                tp=1.3100
            )
            res = await self.order_mgr.submit_order(order)
            self.assertTrue(res.get("success"))
            ticket = order.ticket

            # Test Scale Out
            scale_res = await self.order_mgr.scale_out(ticket, lots=0.10)
            self.assertTrue(scale_res["success"])
            self.assertAlmostEqual(scale_res["remaining_lots"], 0.10, places=2)

            # Test Cost Average
            ca_res = await self.order_mgr.cost_average(ticket, additional_lots=0.10, price_step_pips=15.0)
            self.assertTrue(ca_res.get("success"))

        asyncio.run(run_scale())

    def test_partial_take_profit_and_partial_sl(self):
        async def run_partial():
            from autotrade.orders.order_types import PartialTarget
            order = TradeOrder(
                ticket=99901,
                symbol="EURUSD",
                side=OrderSide.BUY,
                lots=0.10,
                price=1.0800,
                sl=1.0760,
                tp=1.0900,
                partial_targets=[
                    PartialTarget(target_price=1.0850, close_fraction=0.50)
                ]
            )
            self.order_mgr.position_tracker.register_order(order)

            # Price reaches TP target 1.0855
            await self.order_mgr.position_tracker._evaluate_single_position(
                ticket=99901,
                symbol="EURUSD",
                cmd="BUY",
                open_price=1.0800,
                current_price=1.0855,
                current_sl=1.0760,
                lots=0.10
            )
            self.assertTrue(order.partial_targets[0].is_executed)
            self.assertAlmostEqual(order.lots, 0.05, places=2)

            # Adverse drift 75% towards SL (1.0800 - 0.75 * 0.0040 = 1.0770)
            await self.order_mgr.position_tracker._evaluate_single_position(
                ticket=99901,
                symbol="EURUSD",
                cmd="BUY",
                open_price=1.0800,
                current_price=1.0768,
                current_sl=1.0760,
                lots=0.05
            )
            self.assertTrue(getattr(order, "partial_sl_executed", False))

        asyncio.run(run_partial())

    def test_correlation_limit_and_trade_count_halt(self):
        account = {"balance": 100000.0, "equity": 100000.0, "margin_free": 90000.0}
        
        # Test correlation limit rejection (max 2 positions)
        correlated_pos = [
            {"symbol": "GBPUSD", "cmd": "BUY", "lots": 0.1},
            {"symbol": "EURUSD", "cmd": "BUY", "lots": 0.1},
            {"symbol": "AUDUSD", "cmd": "BUY", "lots": 0.1},
        ]
        res = self.risk.evaluate_order_risk(
            symbol="NZDUSD", cmd="BUY", lots=0.1, price=0.6000,
            sl=0.5950, tp=0.6100, account_info=account, open_positions=correlated_pos
        )
        self.assertFalse(res.passed)
        self.assertIn("Correlation exposure limit exceeded", res.reason)

        # Test daily trade limit halt
        self.risk._daily_trades_count = self.risk.config.risk.daily_trade_limit
        res_halt = self.risk.evaluate_order_risk(
            symbol="EURUSD", cmd="BUY", lots=0.05, price=1.0800,
            sl=1.0750, tp=1.0900, account_info=account, open_positions=[]
        )
        self.assertFalse(res_halt.passed)
        self.assertTrue(self.risk._is_daily_halted)


if __name__ == "__main__":
    unittest.main()
