"""
Unit tests for the Autonomous Self-Learning Performance Feedback Engine (AdaptiveLearner),
TradeMemory SQLite persistence, Bayesian Cluster Scoring, 48h Quarantine, MAE SL adaptation,
and PositionTracker integration.
"""

import asyncio
import os
import time
import unittest
from unittest.mock import MagicMock, patch

from autotrade.analytics.adaptive_learner import (
    AdaptiveLearner,
    TradeMemory,
    TradeLearningRecord,
    ClusterPerformance,
    SymbolQuarantineStatus,
    MAEAdaptationStatus,
    resolve_trading_session,
    resolve_rsi_zone,
    build_cluster_key,
    adaptive_learner,
)
from autotrade.data_layer.database import db_engine
from autotrade.orders.execution_router import ExecutionRouter
from autotrade.orders.order_types import TradeOrder, OrderSide, OrderType, OrderStatus
from autotrade.orders.position_tracker import PositionTracker
from autotrade.risk.risk_manager import RiskManager
from autotrade.risk.position_sizer import PositionSizer


class TestAdaptiveLearner(unittest.TestCase):
    def setUp(self):
        # Create an isolated AdaptiveLearner instance with in-memory buffer
        self.learner = AdaptiveLearner(memory_capacity=100, in_memory_only=True)
        self.sizer = PositionSizer()
        self.risk = RiskManager(position_sizer=self.sizer)

    def tearDown(self):
        # Clean up any active quarantines on the global singleton
        adaptive_learner.clear_all_quarantines()

    def test_session_and_rsi_classifier(self):
        """Validates trading session resolution and RSI momentum zone classification."""
        # 1. Trading Sessions based on UTC hours
        # Asian: 00:00 - 08:00 UTC
        self.assertEqual(resolve_trading_session(1710126000), "ASIAN") # 03:00 UTC
        # London: 08:00 - 13:00 UTC
        self.assertEqual(resolve_trading_session(1710151200), "LONDON") # 10:00 UTC
        # London / NY Overlap: 13:00 - 17:00 UTC
        self.assertEqual(resolve_trading_session(1710165600), "OVERLAP") # 14:00 UTC
        # New York: 17:00 - 22:00 UTC
        self.assertEqual(resolve_trading_session(1710183600), "NY") # 19:00 UTC

        # 2. RSI Momentum Corridor Zones
        self.assertEqual(resolve_rsi_zone(25.0), "OVERSOLD")
        self.assertEqual(resolve_rsi_zone(40.0), "BEAR_MOMENTUM")
        self.assertEqual(resolve_rsi_zone(50.0), "NEUTRAL")
        self.assertEqual(resolve_rsi_zone(60.0), "BULL_MOMENTUM")
        self.assertEqual(resolve_rsi_zone(75.0), "OVERBOUGHT")

        # 3. Cluster key assembly
        key = build_cluster_key("EURUSD", "LONDON", "BULL_MOMENTUM")
        self.assertEqual(key, "EURUSD_LONDON_BULL_MOMENTUM")

    def test_trade_memory_persistence(self):
        """Validates TradeMemory SQLite insertion and retrieval round-trip."""
        memory = TradeMemory(capacity=50)
        rec = TradeLearningRecord(
            ticket=999901,
            symbol="GBPUSD",
            direction="BUY",
            session="LONDON",
            regime="TRENDING",
            entry_rsi=58.5,
            entry_adx=28.0,
            entry_cci=110.0,
            distance_to_ema20_pips=4.2,
            spread_at_entry=0.8,
            confluence_score=82.0,
            realized_pnl=150.0,
            return_r=1.5,
            max_favorable_excursion_pips=22.0,
            max_adverse_excursion_pips=3.5,
            close_reason="TP",
            open_price=1.26500,
            close_price=1.26800,
            initial_sl=1.26300,
            initial_tp=1.26800,
            lots=0.50,
            open_time=time.time() - 3600,
            close_time=time.time()
        )

        memory.record_trade(rec)
        recent = memory.get_recent_trades(limit=10, symbol="GBPUSD")
        self.assertGreaterEqual(len(recent), 1)
        retrieved = next(t for t in recent if t.ticket == 999901)
        self.assertEqual(retrieved.symbol, "GBPUSD")
        self.assertEqual(retrieved.direction, "BUY")
        self.assertEqual(retrieved.return_r, 1.5)
        self.assertEqual(retrieved.max_favorable_excursion_pips, 22.0)
        self.assertEqual(retrieved.max_adverse_excursion_pips, 3.5)
        self.assertEqual(retrieved.close_reason, "TP")

    def test_bayesian_cluster_penalty_on_consecutive_losses(self):
        """
        Validates Bayesian weight calibrator penalizes setups (-25 pts)
        when encountering consecutive losses or negative expectancy.
        """
        learner = self.learner
        cluster_key = "USDCHF_NY_BEAR_MOMENTUM"
        features = {"session": "NY", "entry_rsi": 42.0}

        # Initial score modifier should be 0.0
        self.assertEqual(learner.get_score_modifier("USDCHF", features), 0.0)

        # Feed 2 consecutive losses into this cluster
        for i in range(1, 3):
            rec = TradeLearningRecord(
                ticket=1000 + i,
                symbol="USDCHF",
                direction="SELL",
                session="NY",
                regime="TRENDING",
                entry_rsi=42.0,
                return_r=-1.0,
                realized_pnl=-50.0,
                close_reason="SL",
                open_price=0.9000,
                close_price=0.8980,
                initial_sl=0.9020
            )
            learner.on_trade_closed(rec)

        # Modifier should now apply -25 pts penalty due to 2 consecutive losses
        mod = learner.get_score_modifier("USDCHF", features)
        self.assertEqual(mod, -25.0)

    def test_bayesian_cluster_boost_on_high_expectancy(self):
        """
        Validates Bayesian weight calibrator boosts setups (+10 pts)
        when Expectancy > 1.2R and Profit Factor > 1.8.
        """
        learner = self.learner
        features = {"session": "LONDON", "entry_rsi": 60.0}

        # Feed 4 winning trades (+2.0R each) and 1 small loss (-0.5R)
        # Total profit = 8.0R, total loss = 0.5R -> PF = 16.0, Expectancy = 7.5 / 5 = +1.5R
        for i in range(4):
            learner.on_trade_closed(TradeLearningRecord(
                ticket=2000 + i,
                symbol="EURJPY",
                direction="BUY",
                session="LONDON",
                regime="TRENDING",
                entry_rsi=60.0,
                return_r=2.0,
                realized_pnl=200.0,
                close_reason="TP",
                open_price=160.00,
                close_price=160.60,
                initial_sl=159.70
            ))
        learner.on_trade_closed(TradeLearningRecord(
            ticket=2005,
            symbol="EURJPY",
            direction="BUY",
            session="LONDON",
            regime="TRENDING",
            entry_rsi=60.0,
            return_r=-0.5,
            realized_pnl=-50.0,
            close_reason="SL",
            open_price=160.00,
            close_price=159.85,
            initial_sl=159.70
        ))

        mod = learner.get_score_modifier("EURJPY", features)
        self.assertEqual(mod, 10.0)

    def test_autonomous_symbol_quarantine_consecutive_sl(self):
        """
        Validates Asset Circuit Breaker: 48-hour quarantine is triggered
        upon 2 consecutive full stop-loss hits.
        """
        learner = self.learner
        sym = "AUDCAD"
        self.assertFalse(learner.is_symbol_quarantined(sym))

        # 1st SL hit
        learner.on_trade_closed(TradeLearningRecord(
            ticket=3001,
            symbol=sym,
            direction="BUY",
            session="ASIAN",
            regime="RANGING",
            return_r=-1.0,
            close_reason="SL",
            open_price=0.8800,
            close_price=0.8780,
            initial_sl=0.8780
        ))
        self.assertFalse(learner.is_symbol_quarantined(sym))

        # 2nd SL hit -> triggers 48h quarantine
        learner.on_trade_closed(TradeLearningRecord(
            ticket=3002,
            symbol=sym,
            direction="BUY",
            session="ASIAN",
            regime="RANGING",
            return_r=-1.0,
            close_reason="SL",
            open_price=0.8800,
            close_price=0.8780,
            initial_sl=0.8780
        ))
        self.assertTrue(learner.is_symbol_quarantined(sym))
        q_status = learner.get_quarantine_status(sym)
        self.assertTrue(q_status.is_quarantined)
        self.assertGreater(q_status.quarantined_until, time.time() + 47 * 3600)
        self.assertIn("2 consecutive full Stop-Loss hits", q_status.reason)

    def test_autonomous_symbol_quarantine_negative_expectancy(self):
        """
        Validates Asset Circuit Breaker: 48-hour quarantine is triggered
        when rolling 5-trade expectancy drops below -0.5R.
        """
        learner = self.learner
        sym = "NZDUSD"
        self.assertFalse(learner.is_symbol_quarantined(sym))

        # Feed 5 trades with returns: -1.0R, +0.1R, -1.0R, -0.8R, -0.7R -> avg = -0.68R (< -0.5R)
        returns = [-1.0, 0.1, -1.0, -0.8, -0.7]
        for i, r in enumerate(returns):
            learner.on_trade_closed(TradeLearningRecord(
                ticket=4000 + i,
                symbol=sym,
                direction="SELL",
                session="NY",
                regime="TRENDING",
                return_r=r,
                close_reason="BREAKEVEN" if r > 0 else "SL",
                open_price=0.6000,
                close_price=0.6000 + (r * 0.0020),
                initial_sl=0.6020
            ))

        self.assertTrue(learner.is_symbol_quarantined(sym))
        q_status = learner.get_quarantine_status(sym)
        self.assertIn("Expectancy", q_status.reason)
        q_rec = learner.get_quarantine_record(sym)
        self.assertIsNotNone(q_rec)
        self.assertLess(q_rec.rolling_expectancy_r, -0.5)

    def test_risk_manager_vetoes_quarantined_symbol(self):
        """
        Validates Check -1b in RiskManager rejects orders for quarantined symbols.
        """
        sym = "XAUUSD"
        # Quarantine symbol globally
        adaptive_learner.quarantine_symbol(sym, duration_sec=172800.0, reason="Test Circuit Breaker")
        self.assertTrue(adaptive_learner.is_symbol_quarantined(sym))

        risk_res = self.risk.evaluate_order_risk(
            symbol=sym,
            cmd="BUY",
            lots=0.1,
            price=2000.0,
            sl=1990.0,
            tp=2020.0,
            account_info={"balance": 10000.0, "equity": 10000.0, "margin_free": 10000.0},
            open_positions=[],
            is_news_imminent=False
        )
        self.assertFalse(risk_res.passed)
        self.assertIn("adaptive learning quarantine", risk_res.reason.lower())

    def test_mae_volatility_self_adaptation(self):
        """
        Validates MAE Volatility & Stop-Loss Self-Adaptation:
        - Median MAE >= 80% SL -> widens ATR multiplier +0.2x.
        - Median MAE < 30% SL -> tightens ATR multiplier -0.2x.
        """
        learner = self.learner
        sym = "USDCAD"
        base_mult = 2.0

        # Initial adjustment should be 0.0
        self.assertEqual(learner.get_sl_atr_multiplier_adjustment(sym), 0.0)
        self.assertEqual(learner.get_adapted_sl_multiplier(sym, base_mult), 2.0)

        # 1. High MAE (MAE >= 80% of SL): SL = 20 pips, MAE = 18 pips (90%)
        # Feed 3 winning trades
        for i in range(3):
            learner.on_trade_closed(TradeLearningRecord(
                ticket=5000 + i,
                symbol=sym,
                direction="BUY",
                session="LONDON",
                regime="TRENDING",
                return_r=1.5,
                realized_pnl=100.0,
                max_adverse_excursion_pips=18.0,
                close_reason="TP",
                open_price=1.3500,
                close_price=1.3530,
                initial_sl=1.3480 # 20 pips SL
            ))

        self.assertEqual(learner.get_sl_atr_multiplier_adjustment(sym), 0.20)
        self.assertEqual(learner.get_adapted_sl_multiplier(sym, base_mult), 2.20)

        # 2. Low MAE (MAE < 30% of SL): SL = 20 pips, MAE = 4 pips (20%)
        # Feed 4 clean breakout winning trades to shift median
        for i in range(4):
            learner.on_trade_closed(TradeLearningRecord(
                ticket=6000 + i,
                symbol=sym,
                direction="BUY",
                session="LONDON",
                regime="TRENDING",
                return_r=2.0,
                realized_pnl=150.0,
                max_adverse_excursion_pips=4.0,
                close_reason="TP",
                open_price=1.3500,
                close_price=1.3540,
                initial_sl=1.3480 # 20 pips SL
            ))

        self.assertEqual(learner.get_sl_atr_multiplier_adjustment(sym), -0.20)
        self.assertEqual(learner.get_adapted_sl_multiplier(sym, base_mult), 1.80)

    def test_position_tracker_mfe_mae_and_dispatch(self):
        """
        Validates PositionTracker excursion tracking (MFE/MAE) and dispatch
        to AdaptiveLearner on trade closure.
        """
        router = ExecutionRouter(simulation_mode=True)
        tracker = PositionTracker(router=router)

        order = TradeOrder(
            ticket=777888,
            symbol="EURUSD",
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            lots=0.10,
            price=1.1000,
            sl=1.0980, # 20 pips SL
            tp=1.1040,
            features={"session": "LONDON", "entry_rsi": 55.0, "confluence_score": 85.0}
        )
        tracker.register_order(order)
        self.assertIn(777888, tracker._active_orders)

        # Simulate tick 1: Price goes up +15 pips to 1.1015
        asyncio.run(tracker._evaluate_single_position(
            ticket=777888,
            symbol="EURUSD",
            cmd="BUY",
            open_price=1.1000,
            current_price=1.1015,
            current_sl=1.0980,
            lots=0.10
        ))
        self.assertAlmostEqual(tracker._mfe[777888], 15.0, delta=0.5)
        self.assertEqual(tracker._mae.get(777888, 0.0), 0.0)

        # Simulate tick 2: Price pulls back to 1.0990 (-10 pips adverse)
        asyncio.run(tracker._evaluate_single_position(
            ticket=777888,
            symbol="EURUSD",
            cmd="BUY",
            open_price=1.1000,
            current_price=1.0990,
            current_sl=1.0980,
            lots=0.10
        ))
        self.assertAlmostEqual(tracker._mfe[777888], 15.0, delta=0.5)
        self.assertAlmostEqual(tracker._mae[777888], 10.0, delta=0.5)

        # Simulate tick 3: Price hits Take Profit at 1.1040 (+40 pips favorable)
        asyncio.run(tracker._evaluate_single_position(
            ticket=777888,
            symbol="EURUSD",
            cmd="BUY",
            open_price=1.1000,
            current_price=1.1040,
            current_sl=1.0980,
            lots=0.10
        ))
        self.assertAlmostEqual(tracker._mfe[777888], 40.0, delta=0.5)
        self.assertAlmostEqual(tracker._mae[777888], 10.0, delta=0.5)

        # Dispatch closure via notify_trade_closed
        rec = tracker.notify_trade_closed(
            ticket=777888,
            close_reason="TP",
            close_price=1.1040,
            pnl=40.0,
            return_r=2.0
        )
        self.assertIsNotNone(rec)
        self.assertEqual(rec.ticket, 777888)
        self.assertEqual(rec.symbol, "EURUSD")
        self.assertAlmostEqual(rec.max_favorable_excursion_pips, 40.0, delta=0.5)
        self.assertAlmostEqual(rec.max_adverse_excursion_pips, 10.0, delta=0.5)
        self.assertEqual(rec.return_r, 2.0)
        self.assertEqual(rec.close_reason, "TP")

        # Unregister
        tracker.unregister_order(777888)
        self.assertNotIn(777888, tracker._active_orders)

    def test_pipeline_adaptive_quarantine_preflight_veto(self):
        """
        Validates that QuantitativeConfluenceEngine immediately vetoes quarantined symbols
        at pre-flight check before performing costly computations.
        """
        from autotrade.core.pipeline import QuantitativeConfluenceEngine
        engine = QuantitativeConfluenceEngine()

        sym = "EURGBP"
        adaptive_learner.quarantine_symbol(sym, duration_sec=172800.0, reason="Drawdown Circuit Breaker")
        self.assertTrue(adaptive_learner.is_symbol_quarantined(sym))

        import numpy as np
        ohlcv = {
            "close": np.array([0.8500] * 60, dtype=np.float64),
            "high": np.array([0.8510] * 60, dtype=np.float64),
            "low": np.array([0.8490] * 60, dtype=np.float64),
            "open": np.array([0.8500] * 60, dtype=np.float64)
        }
        res = engine.evaluate_symbol(symbol=sym, ohlcv=ohlcv, spread_points=10.0)

        self.assertFalse(res.is_qualified)
        self.assertIn("Adaptive Quarantine Veto", res.disqualification_reason)
        self.assertIn("Drawdown Circuit Breaker", res.disqualification_reason)

        # Release quarantine
        adaptive_learner.clear_quarantine(sym)
        self.assertFalse(adaptive_learner.is_symbol_quarantined(sym))

    def test_pipeline_candidate_adaptive_score_attribute(self):
        """Validates that CandidateEvaluation includes adaptive_score_modifier."""
        from autotrade.core.pipeline import CandidateEvaluation
        candidate = CandidateEvaluation(
            symbol="EURUSD",
            canonical_symbol="EURUSD",
            signal="BUY",
            score_100=80.0,
            tier1_regime="TRENDING",
            hurst_exponent=0.65,
            ker_ratio=0.5,
            htf_aligned=True,
            adx_value=30.0,
            rsi_value=55.0,
            cmf_value=0.1,
            vwap_aligned=True,
            volume_surge=True,
            pattern="BULLISH_ENGULFING",
            spread_points=12.0,
            atr_value=0.0020,
            spread_to_atr=0.6,
            sl_pips=20.0,
            tp_pips=40.0,
            rr_ratio=2.0
        )
        self.assertEqual(candidate.adaptive_score_modifier, 0.0)


if __name__ == "__main__":
    unittest.main()
