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


from unittest.mock import patch


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
        self.acc_patcher = patch(
            "zmq_client.zmq_client.get_account",
            return_value={"status": "ok", "balance": 100000.0, "equity": 100000.0, "margin_free": 100000.0}
        )
        self.acc_patcher.start()
        self.addCleanup(self.acc_patcher.stop)
        self.pos_patcher = patch(
            "zmq_client.zmq_client.get_positions",
            return_value={"status": "ok", "positions": []}
        )
        self.pos_patcher.start()
        self.addCleanup(self.pos_patcher.stop)

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

    def test_low_balance_margin_capacity_and_position_sizing(self):
        # Test low balance account safeguards ($90.49 balance & free margin)
        low_balance_account = {
            "balance": 90.49,
            "equity": 90.49,
            "margin_free": 90.49
        }

        # 1. Verify that an oversized lot (5.02 lots) is strictly rejected by risk limits
        res_oversized = self.risk.evaluate_order_risk(
            symbol="USDCHF",
            cmd="BUY",
            lots=5.02,
            price=0.8850,
            sl=0.8820,
            tp=0.8910,
            account_info=low_balance_account,
            open_positions=[]
        )
        self.assertFalse(res_oversized.passed)
        self.assertIn("exceeds maximum per-trade limit", res_oversized.reason)

        # 2. Verify that order is rejected when margin requirement exceeds allowable free margin buffer
        constrained_margin_account = {
            "balance": 10000.0,
            "equity": 10000.0,
            "margin_free": 10.0  # Only $10 free margin available
        }
        res_margin_breach = self.risk.evaluate_order_risk(
            symbol="EURUSD",
            cmd="BUY",
            lots=0.05,  # Requires ~$50 margin at 1:100 leverage
            price=1.0850,
            sl=1.0835,  # 15 pips -> $7.50 risk (0.075% of $10,000 equity, within 0.5% limit)
            tp=1.0880,
            account_info=constrained_margin_account,
            open_positions=[]
        )
        self.assertFalse(res_margin_breach.passed)
        self.assertIn("margin requirement exceeds allowable free margin buffer", res_margin_breach.reason)

        # 3. Verify that PositionSizer calculates an affordable 0.01 lot for low balance account ($90.49)
        lots_calculated = self.sizer.calculate_lot_size(
            symbol="USDCHF",
            method=SizingMethod.PERCENTAGE_RISK,
            balance=90.49,
            entry_price=0.8850,
            stop_loss=0.8820
        )
        self.assertEqual(lots_calculated, 0.01)

    def test_rollover_spread_freeze_and_dynamic_pips(self):
        # 1. Midnight rollover freeze test: 23:58 server time
        res_rollover_2358 = self.risk.evaluate_order_risk(
            symbol="EURUSD",
            cmd="BUY",
            lots=0.01,
            price=1.0850,
            sl=1.0820,
            tp=1.0910,
            account_info={"balance": 100000.0, "equity": 100000.0, "margin_free": 90000.0},
            open_positions=[],
            server_time_str="2026.09.10 23:58:12"
        )
        self.assertFalse(res_rollover_2358.passed)
        self.assertIn("rollover window", res_rollover_2358.reason)

        # 2. Midnight rollover freeze test: 00:05 server time
        res_rollover_0005 = self.risk.evaluate_order_risk(
            symbol="EURUSD",
            cmd="BUY",
            lots=0.01,
            price=1.0850,
            sl=1.0820,
            tp=1.0910,
            account_info={"balance": 100000.0, "equity": 100000.0, "margin_free": 90000.0},
            open_positions=[],
            server_time_str="2026.09.11 00:05:00"
        )
        self.assertFalse(res_rollover_0005.passed)
        self.assertIn("rollover window", res_rollover_0005.reason)

        # 3. Dynamic pip calculation tests across assets
        pv_eurusd = self.sizer.get_dynamic_pip_value("EURUSD")
        self.assertEqual(pv_eurusd, 10.0)

        pv_xauusd = self.sizer.get_dynamic_pip_value("XAUUSD")
        self.assertEqual(pv_xauusd, 100.0)

        pv_eurjpy = self.sizer.get_dynamic_pip_value("EURJPY", exchange_rates={"USDJPY": 150.0})
        self.assertAlmostEqual(pv_eurjpy, 6.67, places=1)


class TestSniperAutonomousEngine(unittest.TestCase):
    """
    Comprehensive verification for the 100% Autonomous Zero-Configuration Sniper Engine:
    - Dynamic 0.5% max risk lot sizing
    - 1.5% Hard Daily Loss Circuit Breaker
    - 24-hour single-loss asset quarantine
    - +1.0R Risk-Free Trade protocol (50% partial close + BE +1 pip lock)
    - 5-Rule All-Or-Nothing Sniper Selection Matrix & Dynamic Spread Filter
    """
    def setUp(self):
        from autotrade.risk.risk_manager import RiskManager
        from autotrade.risk.position_sizer import PositionSizer
        from autotrade.orders.order_manager import OrderManager
        from autotrade.core.pipeline import (
            QuantitativeConfluenceEngine,
            BrokerInstrumentSpecs,
            resolve_broker_specs
        )
        self.risk = RiskManager()
        self.sizer = PositionSizer()
        self.order_mgr = OrderManager()
        self.engine = QuantitativeConfluenceEngine(min_confluence_score=6.0)

    def test_autonomous_lot_sizing_strict_half_percent_cap(self):
        """Validates autonomous mathematical lot sizing with strict 0.5% max equity risk cap."""
        account = {"balance": 10000.0, "equity": 10000.0, "free_margin": 10000.0}
        specs = {
            "contract_size": 100000.0,
            "min_lot": 0.01,
            "lot_step": 0.01,
            "max_lot": 50.0,
            "tick_value": 1.0,
            "tick_size": 0.00001
        }
        # Equity = $10,000 -> 0.5% Risk Cap = $50.00
        # SL distance = 25 pips = 0.0025 = 250 ticks. Tick value = $1.00.
        # Lots = 50 / (250 * 1.0) = 0.20 lots
        lots, cash_risk = self.risk.calculate_autonomous_lots(
            symbol="EURUSD",
            equity=10000.0,
            sl_distance_price=0.0025,
            broker_specs=specs
        )
        self.assertEqual(lots, 0.20)
        self.assertEqual(cash_risk, 50.0)

        # Pre-flight risk check must pass for 0.20 lots (0.5% risk)
        res_pass = self.risk.evaluate_order_risk(
            symbol="EURUSD",
            cmd="BUY",
            lots=0.20,
            price=1.0800,
            sl=1.0775,
            tp=1.0850,
            account_info=account,
            open_positions=[]
        )
        self.assertTrue(res_pass.passed)

        # Risk check must strictly veto oversized lot (e.g. 1.0 lots = 2.5% risk > 0.5% cap)
        res_veto = self.risk.evaluate_order_risk(
            symbol="EURUSD",
            cmd="BUY",
            lots=1.0,
            price=1.0800,
            sl=1.0775,
            tp=1.0850,
            account_info=account,
            open_positions=[]
        )
        self.assertFalse(res_veto.passed)
        self.assertIn("exceeds maximum per-trade limit", res_veto.reason)

    def test_hard_daily_loss_circuit_breaker(self):
        """Validates that a 1.5% daily drawdown halts all trading operations."""
        self.risk.reset_daily_stats(current_balance=10000.0, current_equity=10000.0)
        # Current equity down to $9,840 = 1.6% loss (> 1.5% limit)
        account_breached = {"balance": 9840.0, "equity": 9840.0, "free_margin": 9840.0}

        res = self.risk.evaluate_order_risk(
            symbol="EURUSD",
            cmd="BUY",
            lots=0.01,
            price=1.0800,
            sl=1.0775,
            tp=1.0850,
            account_info=account_breached,
            open_positions=[]
        )
        self.assertFalse(res.passed)
        self.assertIn("Hard Daily Loss Circuit Breaker", res.reason)
        self.assertTrue(self.risk._is_daily_halted)

    def test_autonomous_single_loss_asset_quarantine(self):
        """Validates 24-hour quarantine freeze on any symbol hitting full SL."""
        symbol = "GBPUSD"
        self.assertFalse(self.risk.is_symbol_quarantined(symbol)[0])

        # Record a full stop-loss loss trade (-$50.00)
        self.risk.record_trade_result(
            profit=-50.0,
            symbol=symbol,
            is_full_sl=True
        )

        is_quar, remaining = self.risk.is_symbol_quarantined(symbol)
        self.assertTrue(is_quar)
        self.assertGreater(remaining, 86000)

        # Pre-flight check on quarantined symbol must be vetoed
        res_quar = self.risk.evaluate_order_risk(
            symbol=symbol,
            cmd="BUY",
            lots=0.01,
            price=1.2500,
            sl=1.2475,
            tp=1.2550,
            account_info={"balance": 10000.0, "equity": 10000.0, "free_margin": 10000.0},
            open_positions=[]
        )
        self.assertFalse(res_quar.passed)
        self.assertIn("quarantine freeze", res_quar.reason)

        # Unquarantined symbol (EURUSD) must pass without restriction
        res_other = self.risk.evaluate_order_risk(
            symbol="EURUSD",
            cmd="BUY",
            lots=0.01,
            price=1.0800,
            sl=1.0775,
            tp=1.0850,
            account_info={"balance": 10000.0, "equity": 10000.0, "free_margin": 10000.0},
            open_positions=[]
        )
        self.assertTrue(res_other.passed)

    def test_risk_free_trade_protocol_execution(self):
        """Validates Target 1 (+1.0R): 50% partial close + SL to BE +1 pip."""
        async def run_test():
            from unittest.mock import AsyncMock
            from autotrade.orders.order_types import TradeOrder, OrderSide
            tracker = self.order_mgr.position_tracker

            order = TradeOrder(
                ticket=77701,
                symbol="EURUSD",
                side=OrderSide.BUY,
                lots=0.10,
                price=1.0800,
                sl=1.0760,
                tp=1.0900
            )
            tracker.register_order(order)
            tracker._initial_sl_levels[77701] = 1.0760

            tracker.router.close_position = AsyncMock(return_value={"status": "ok"})
            tracker.router.modify_sl_tp = AsyncMock(return_value={"status": "ok"})

            # Price advances to 1.0845 (+1.125R > 1.0R)
            await tracker._evaluate_single_position(
                ticket=77701,
                symbol="EURUSD",
                cmd="BUY",
                open_price=1.0800,
                current_price=1.0845,
                current_sl=1.0760,
                lots=0.10
            )

            # Check that 1R risk-free protocol triggered:
            self.assertIn(77701, tracker._risk_free_activated_tickets)
            self.assertAlmostEqual(order.lots, 0.05, places=2)
            tracker.router.close_position.assert_called_once_with(ticket=77701, lots=0.05)
            tracker.router.modify_sl_tp.assert_any_call(ticket=77701, sl=1.0801)

        asyncio.run(run_test())

    def test_dynamic_spread_filter(self):
        """Validates rolling median spread filter (veto if current > 1.8 * median)."""
        import numpy as np
        # Rolling 100-bar spreads with median = 10.0 points
        spread_history = np.full(100, 10.0, dtype=np.float64)

        # Spread = 12 points (1.2 * median <= 1.8) -> allowed
        ok, median, ratio = self.engine.compute_dynamic_spread_filter("EURUSD", 12.0, spread_history)
        self.assertTrue(ok)
        self.assertEqual(median, 10.0)
        self.assertEqual(ratio, 1.2)

        # Spread = 20 points (> 1.8 * median = 18.0) -> vetoed
        bad, median, ratio = self.engine.compute_dynamic_spread_filter("EURUSD", 20.0, spread_history)
        self.assertFalse(bad)
        self.assertEqual(ratio, 2.0)

    def test_sniper_matrix_all_or_nothing_rules(self):
        """Validates that evaluate_symbol strictly enforces All-Or-Nothing sniper gates."""
        import numpy as np

        # Case 1: Insufficient bars (< 50 bars) -> immediate veto
        short_ohlcv = {
            "open": np.full(30, 1.0800),
            "high": np.full(30, 1.0820),
            "low": np.full(30, 1.0780),
            "close": np.full(30, 1.0810),
            "volume": np.full(30, 100.0)
        }
        res_short = self.engine.evaluate_symbol("EURUSD", short_ohlcv)
        self.assertEqual(res_short.signal, "HOLD")
        self.assertFalse(res_short.is_qualified)
        self.assertIn("Insufficient bars", res_short.disqualification_reason)

        # Case 2: Excessive spread exceeding 1.8 * rolling median -> immediate veto
        full_ohlcv = {
            "open": np.linspace(1.0700, 1.0800, 100),
            "high": np.linspace(1.0720, 1.0820, 100),
            "low": np.linspace(1.0690, 1.0790, 100),
            "close": np.linspace(1.0710, 1.0810, 100),
            "volume": np.full(100, 500.0)
        }
        spread_hist = [10.0] * 100
        res_wide_spread = self.engine.evaluate_symbol(
            "EURUSD",
            full_ohlcv,
            spread_points=25.0,  # 2.5x median (> 1.8x limit)
            spread_history=spread_hist
        )
        self.assertEqual(res_wide_spread.signal, "HOLD")
        self.assertFalse(res_wide_spread.is_qualified)
        self.assertIn("Dynamic Spread Veto", res_wide_spread.disqualification_reason)


if __name__ == "__main__":
    unittest.main()


