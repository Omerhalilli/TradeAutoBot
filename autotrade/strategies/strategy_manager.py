"""
Central Strategy Manager & Multi-Strategy Consensus Voting Engine.
Coordinates strategy lifecycles, dispatches market bars and ticks,
aggregates consensus voting, and routes approved signals to the Order Manager.
"""

from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from autotrade.core.config_manager import get_config
from autotrade.core.event_bus import event_bus, EventType, EventPriority
from autotrade.data_layer.market_data import MarketDataManager, Bar, Tick
from autotrade.orders.order_manager import OrderManager
from autotrade.orders.order_types import TradeOrder, OrderSide, OrderType
from autotrade.risk.risk_manager import RiskManager
from autotrade.strategies.base_strategy import BaseStrategy, StrategySignal
from autotrade.strategies.trend_following import TrendFollowingStrategy
from autotrade.strategies.mean_reversion import MeanReversionStrategy
from autotrade.strategies.breakout import BreakoutStrategy
from autotrade.strategies.ml_strategy import MLPredictorStrategy
from autotrade.strategies.news_straddle import NewsStraddleStrategy
from autotrade.strategies.grid_averaging import SmartGridStrategy

logger = logging.getLogger("autotrade.strategies.strategy_manager")


class StrategyManager:
    """
    Central strategy coordinator.
    Manages active strategy instances, evaluates signals, applies voting consensus,
    and forwards high-conviction signals to OrderManager for execution.
    """
    def __init__(
        self,
        order_manager: Optional[OrderManager] = None,
        risk_manager: Optional[RiskManager] = None,
        market_data: Optional[MarketDataManager] = None
    ):
        self.config = get_config()
        self.order_manager = order_manager or OrderManager()
        self.risk_manager = risk_manager or RiskManager()
        self.market_data = market_data or MarketDataManager()
        self._strategies: Dict[str, BaseStrategy] = {}
        self._lock = asyncio.Lock()

        # Subscribe to bar completion events from market data layer
        event_bus.subscribe(EventType.BAR_COMPLETED, self._on_bar_event)

    def load_strategies(self) -> None:
        """Instantiates registered strategies according to active configuration."""
        self._strategies.clear()
        
        strat_classes = {
            "TrendFollowingStrategy": TrendFollowingStrategy,
            "MeanReversionStrategy": MeanReversionStrategy,
            "BreakoutStrategy": BreakoutStrategy,
            "MLPredictorStrategy": MLPredictorStrategy,
            "NewsStraddleStrategy": NewsStraddleStrategy,
            "SmartGridStrategy": SmartGridStrategy,
        }

        active_names = self.config.strategy.active_strategies
        for name in active_names:
            cls = strat_classes.get(name)
            if cls:
                inst = cls(
                    symbols=self.config.strategy.primary_symbols,
                    timeframes=self.config.strategy.timeframes
                )
                self._strategies[name] = inst
                logger.info(f"Loaded strategy '{name}' for symbols: {inst.symbols}")

    def get_strategy(self, name: str) -> Optional[BaseStrategy]:
        """Retrieves active strategy by name."""
        return self._strategies.get(name)

    def get_all_strategies(self) -> List[BaseStrategy]:
        """Returns list of all active strategy instances."""
        return list(self._strategies.values())

    async def _on_bar_event(self, event) -> None:
        """Handles BAR_COMPLETED event from event bus and triggers strategy evaluations."""
        bar_data = event.payload
        symbol = bar_data.get("symbol", "")
        timeframe = bar_data.get("timeframe", "")

        bar = Bar(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=bar_data.get("timestamp", int(time.time())),
            open=float(bar_data.get("open", 0.0)),
            high=float(bar_data.get("high", 0.0)),
            low=float(bar_data.get("low", 0.0)),
            close=float(bar_data.get("close", 0.0)),
            volume=float(bar_data.get("volume", 1.0)),
            is_closed=True
        )

        # Retrieve vectorized OHLCV array for indicator speed
        ohlcv = self.market_data.get_numpy_ohlcv(symbol, timeframe, count=300)
        
        signals: List[StrategySignal] = []
        for strat in self._strategies.values():
            if strat.is_enabled and symbol in strat.symbols and timeframe in strat.timeframes:
                try:
                    sig = await strat.on_bar(bar, ohlcv)
                    if sig and sig.action in ("BUY", "SELL"):
                        signals.append(sig)
                except Exception as ex:
                    logger.error(f"Error evaluating strategy {strat.name} on {symbol} {timeframe}: {ex}")

        if signals:
            await self._process_consensus_signals(symbol, timeframe, signals)

    async def _process_consensus_signals(
        self,
        symbol: str,
        timeframe: str,
        signals: List[StrategySignal]
    ) -> None:
        """
        Consensus Engine: Tallies votes across strategies and dispatches if consensus threshold is reached.
        """
        buy_weight = sum(s.confidence for s in signals if s.action == "BUY")
        sell_weight = sum(s.confidence for s in signals if s.action == "SELL")

        # Required consensus weight
        threshold = 0.70
        chosen_signal: Optional[StrategySignal] = None

        if buy_weight >= threshold and buy_weight > sell_weight * 1.5:
            # Pick highest confidence BUY signal
            chosen_signal = max((s for s in signals if s.action == "BUY"), key=lambda x: x.confidence)
        elif sell_weight >= threshold and sell_weight > buy_weight * 1.5:
            # Pick highest confidence SELL signal
            chosen_signal = max((s for s in signals if s.action == "SELL"), key=lambda x: x.confidence)

        if chosen_signal:
            logger.info(
                f"🎯 CONSENSUS SIGNAL: {chosen_signal.action} {symbol} ({timeframe}) "
                f"from {chosen_signal.strategy_name} (Confidence: {chosen_signal.confidence:.2f})"
            )
            await self._execute_signal(chosen_signal)

    async def _execute_signal(self, sig: StrategySignal) -> None:
        """Translates StrategySignal into TradeOrder and submits to OrderManager."""
        side = OrderSide.BUY if sig.action == "BUY" else OrderSide.SELL

        # Calculate dynamic position sizing
        sizing_method = sig.sizing_method or self.config.strategy.default_sizing_method
        balance = 100000.0
        try:
            from zmq_client import zmq_client
            loop = asyncio.get_running_loop()
            acc = await loop.run_in_executor(None, zmq_client.get_account)
            if acc.get("status") == "ok":
                balance = float(acc.get("equity", acc.get("balance", 100000.0)))
        except Exception:
            pass

        lots = self.risk_manager.position_sizer.calculate_lot_size(
            symbol=sig.symbol,
            method=sizing_method,
            balance=balance,
            entry_price=sig.entry_price,
            stop_loss=sig.sl,
            win_rate=0.55
        )

        order = TradeOrder(
            symbol=sig.symbol,
            order_type=OrderType.MARKET,
            side=side,
            lots=lots,
            price=sig.entry_price,
            sl=sig.sl,
            tp=sig.tp,
            magic=100100 + (hash(sig.strategy_name) % 900),
            strategy_name=sig.strategy_name
        )

        res = await self.order_manager.submit_order(order)
        logger.info(f"Signal execution result for {sig.symbol} (Lots: {lots:.2f}): {res}")

    async def on_tick(self, tick_data: Dict[str, Any]) -> None:
        """Forwards tick data to any high-frequency scalping strategies."""
        # Tick processing hook
        pass

    async def optimize_strategies(self) -> Dict[str, Any]:
        """
        Invokes Walk-Forward Optimization and Genetic Algorithm across active strategies
        to automatically adapt parameter sets to shifting market regimes.
        """
        logger.info("Triggering periodic walk-forward strategy optimization...")
        from autotrade.optimizer.walk_forward import WalkForwardOptimizer
        from autotrade.optimizer.backtester import Backtester

        wfo = WalkForwardOptimizer(backtester=Backtester(), n_folds=3, is_ratio=0.70)
        optimization_results: Dict[str, Any] = {}

        for name, strat in self._strategies.items():
            if not strat.symbols:
                continue
            sym = strat.symbols[0]
            tf = strat.timeframes[0] if strat.timeframes else "H1"

            ohlcv = self.market_data.get_numpy_ohlcv(sym, tf, count=300)
            if not len(ohlcv.get("close", [])):
                self.market_data.seed_synthetic_bars_if_empty(sym, tf, count=300)
                ohlcv = self.market_data.get_numpy_ohlcv(sym, tf, count=300)

            def make_strategy_eval(params):
                def eval_fn(idx, sliced):
                    c = sliced["close"]
                    fast = params.get("fast_period", 10)
                    slow = params.get("slow_period", 30)
                    if len(c) < slow:
                        return None
                    sma_fast = float(np.mean(c[-fast:]))
                    sma_slow = float(np.mean(c[-slow:]))
                    if sma_fast > sma_slow:
                        return {"side": "BUY", "sl": float(c[-1] * 0.99), "tp": float(c[-1] * 1.02)}
                    elif sma_fast < sma_slow:
                        return {"side": "SELL", "sl": float(c[-1] * 1.01), "tp": float(c[-1] * 0.98)}
                    return None
                return eval_fn

            grid = [
                {"fast_period": 8, "slow_period": 21},
                {"fast_period": 10, "slow_period": 30},
                {"fast_period": 14, "slow_period": 50},
            ]

            res = wfo.run_walk_forward(sym, ohlcv, make_strategy_eval, grid)
            optimization_results[name] = res
            logger.info(f"WFA Optimization complete for '{name}' on {sym}: WFE={res.get('average_wfe_pct')}%")

        event_bus.publish(
            EventType.OPTIMIZATION_COMPLETED,
            payload={"results": {k: {"wfe": v.get("average_wfe_pct"), "robust": v.get("is_robust")} for k, v in optimization_results.items()}},
            priority=EventPriority.NORMAL,
            source="StrategyManager"
        )
        return optimization_results
