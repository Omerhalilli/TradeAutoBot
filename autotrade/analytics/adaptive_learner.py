"""
Autonomous Self-Learning Performance Feedback Engine & Dynamic Bayesian Weight Calibrator.
Continuously learns from trade outcomes (Wins, Losses, MAE, MFE, Sessions, Regimes),
adapts setup score weights, quarantines underperforming assets, and self-calibrates Stop-Loss ATR multipliers.
"""

from __future__ import annotations
import asyncio
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
import logging
import math
import os
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union, NamedTuple

from autotrade.core.event_bus import event_bus, EventType, EventPriority
from autotrade.analytics.precision import PrecisionMath
from autotrade.data_layer.database import db_engine
from autotrade.risk.covariance import canonical_symbol

logger = logging.getLogger("autotrade.analytics.adaptive_learner")


class QuarantineCheck(NamedTuple):
    is_quarantined: bool
    remaining_seconds: float
    reason: str

    @property
    def quarantined_until(self) -> float:
        return time.time() + self.remaining_seconds


# ==============================================================================
# 1. DOMAIN SCHEMAS & DATA STRUCTURES
# ==============================================================================

@dataclass
class TradeLearningRecord:
    """Experiential feature snapshot and realized performance metrics for a closed trade."""
    ticket: int
    symbol: str
    direction: str                                # BUY or SELL
    session: str                                  # ASIAN, LONDON, NY, OVERLAP
    regime: str                                   # TRENDING, RANGING, HIGH_VOLATILITY
    entry_rsi: float = 50.0
    entry_adx: float = 0.0
    entry_cci: float = 0.0
    distance_to_ema20_pips: float = 0.0
    spread_at_entry: float = 0.0
    confluence_score: float = 0.0
    realized_pnl: float = 0.0
    return_r: float = 0.0                         # Gain / loss in multiples of initial risk (-1.0R, +2.0R)
    max_favorable_excursion_pips: float = 0.0     # MFE
    max_adverse_excursion_pips: float = 0.0       # MAE
    close_reason: str = "MANUAL"                  # SL, TP, TRAILING, BREAKEVEN, MANUAL
    open_price: float = 0.0
    close_price: float = 0.0
    initial_sl: float = 0.0
    initial_tp: float = 0.0
    lots: float = 0.01
    open_time: float = field(default_factory=time.time)
    close_time: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClusterPerformance:
    """Rolling statistical performance and Bayesian posterior metrics for a setup cluster."""
    cluster_key: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    consecutive_losses: int = 0
    win_rate: float = 0.5
    profit_factor: float = 1.0
    expectancy_r: float = 0.0
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0
    score_modifier: float = 0.0                   # -25.0 to +10.0 modifier
    last_r_multiples: List[float] = field(default_factory=list)
    alpha: float = 2.0                            # Beta distribution prior alpha
    beta: float = 2.0                             # Beta distribution prior beta
    last_updated: float = field(default_factory=time.time)


@dataclass
class SymbolQuarantineStatus:
    """Circuit-breaker status for an underperforming asset."""
    symbol: str
    is_quarantined: bool = False
    quarantined_until: float = 0.0
    reason: str = ""
    consecutive_sl_count: int = 0
    rolling_expectancy_r: float = 0.0


@dataclass
class MAEAdaptationStatus:
    """Rolling Maximum Adverse Excursion tracking for Stop-Loss ATR self-adaptation."""
    symbol: str
    recent_win_mae_ratios: List[float] = field(default_factory=list)
    sl_multiplier_adjustment: float = 0.0          # -0.2, 0.0, or +0.2
    median_mae_ratio: float = 0.5


# ==============================================================================
# 2. SESSION & REGIME CLASSIFIERS
# ==============================================================================

def resolve_trading_session(utc_timestamp: Optional[float] = None) -> str:
    """
    Resolves the active global institutional forex session from UTC time:
    - ASIAN:   00:00 - 08:00 UTC, 22:00 - 24:00 UTC
    - LONDON:  08:00 - 13:00 UTC
    - OVERLAP: 13:00 - 17:00 UTC (Peak London/NY confluence)
    - NY:      17:00 - 22:00 UTC
    """
    ts = utc_timestamp or time.time()
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    hour_frac = dt.hour + (dt.minute / 60.0)

    if 8.0 <= hour_frac < 13.0:
        return "LONDON"
    elif 13.0 <= hour_frac < 17.0:
        return "OVERLAP"
    elif 17.0 <= hour_frac < 22.0:
        return "NY"
    else:
        return "ASIAN"


def resolve_rsi_zone(rsi: float) -> str:
    """Categorizes RSI momentum into distinct behavioral corridors."""
    if rsi < 35.0:
        return "OVERSOLD"
    elif rsi < 45.0:
        return "BEAR_MOMENTUM"
    elif rsi <= 55.0:
        return "NEUTRAL"
    elif rsi <= 65.0:
        return "BULL_MOMENTUM"
    else:
        return "OVERBOUGHT"


def build_cluster_key(symbol: str, session: str, rsi_zone: str) -> str:
    """Constructs unique composite key for a market setup cluster."""
    canon = canonical_symbol(symbol)
    return f"{canon}_{session.upper()}_{rsi_zone.upper()}"


# ==============================================================================
# 3. EXPERIENTIAL TRADE MEMORY
# ==============================================================================

class TradeMemory:
    """
    Thread-safe experiential trade state recorder.
    Persists closed trade feature vectors into SQLite trade_learning_memory
    and maintains an in-memory circular cache for real-time model evaluation.
    """
    def __init__(self, max_in_memory: int = 1000, capacity: Optional[int] = None, in_memory_only: bool = False):
        self.max_in_memory = capacity if capacity is not None else max_in_memory
        self.in_memory_only = in_memory_only
        self._lock = threading.RLock()
        self._memory: deque[TradeLearningRecord] = deque(maxlen=self.max_in_memory)
        if not self.in_memory_only:
            self._load_from_db()

    def _load_from_db(self) -> None:
        """Hydrates the in-memory cache with recent trades from SQLite."""
        try:
            rows = db_engine.fetch_recent_learning_trades(limit=self.max_in_memory)
            with self._lock:
                for r in rows:
                    rec = TradeLearningRecord(
                        ticket=int(r.get("ticket", 0)),
                        symbol=str(r.get("symbol", "")),
                        direction=str(r.get("direction", "BUY")),
                        session=str(r.get("session", "UNKNOWN")),
                        regime=str(r.get("regime", "UNKNOWN")),
                        entry_rsi=float(r.get("entry_rsi", 50.0)),
                        entry_adx=float(r.get("entry_adx", 0.0)),
                        entry_cci=float(r.get("entry_cci", 0.0)),
                        distance_to_ema20_pips=float(r.get("distance_to_ema20_pips", 0.0)),
                        spread_at_entry=float(r.get("spread_at_entry", 0.0)),
                        confluence_score=float(r.get("confluence_score", 0.0)),
                        realized_pnl=float(r.get("realized_pnl", 0.0)),
                        return_r=float(r.get("return_r", 0.0)),
                        max_favorable_excursion_pips=float(r.get("max_favorable_excursion_pips", 0.0)),
                        max_adverse_excursion_pips=float(r.get("max_adverse_excursion_pips", 0.0)),
                        close_reason=str(r.get("close_reason", "MANUAL")),
                        open_price=float(r.get("open_price", 0.0)),
                        close_price=float(r.get("close_price", 0.0)),
                        initial_sl=float(r.get("initial_sl", 0.0)),
                        initial_tp=float(r.get("initial_tp", 0.0)),
                        lots=float(r.get("lots", 0.01)),
                        open_time=float(r.get("open_time", 0.0)),
                        close_time=float(r.get("close_time", 0.0)),
                        created_at=float(r.get("created_at", 0.0))
                    )
                    self._memory.append(rec)
            if rows:
                logger.info(f"TradeMemory: Warmed cache with {len(rows)} historical learning trades from SQLite.")
        except Exception as ex:
            logger.warning(f"TradeMemory: Cache warming notice: {ex}")

    def record_trade(self, record: TradeLearningRecord) -> None:
        """Stores trade record into in-memory queue and persists to SQLite."""
        with self._lock:
            self._memory.append(record)
        if not self.in_memory_only:
            try:
                db_engine.insert_trade_learning_record(record.to_dict())
            except Exception as ex:
                logger.error(f"TradeMemory: Failed to persist trade #{record.ticket} to SQLite: {ex}")

    def get_recent_trades(self, limit: int = 100, symbol: Optional[str] = None) -> List[TradeLearningRecord]:
        """Retrieves chronological recent trades, optionally filtered by symbol."""
        with self._lock:
            trades = list(self._memory)
        if symbol:
            canon = canonical_symbol(symbol)
            trades = [t for t in trades if canonical_symbol(t.symbol) == canon]
        return trades[-limit:]

    def get_all_trades(self) -> List[TradeLearningRecord]:
        """Returns snapshot copy of all trades in memory."""
        with self._lock:
            return list(self._memory)


# ==============================================================================
# 4. ADAPTIVE LEARNER & BAYESIAN CALIBRATOR
# ==============================================================================

class AdaptiveLearner:
    """
    Self-Learning Performance Feedback Engine.
    Executes online Bayesian reinforcement learning across market clusters,
    dynamically modifies confluence scores, quarantines struggling assets,
    and self-adapts Stop-Loss ATR multipliers based on realized MAE.
    """
    def __init__(
        self,
        max_history_window: int = 20,
        memory: Optional[TradeMemory] = None,
        memory_capacity: Optional[int] = None,
        in_memory_only: bool = False
    ):
        self.max_history_window = max_history_window
        self.in_memory_only = in_memory_only
        self.memory = memory or (TradeMemory(capacity=memory_capacity, in_memory_only=in_memory_only) if (memory_capacity or in_memory_only) else TradeMemory())
        self._lock = threading.RLock()

        # In-memory fast cache
        self._clusters: Dict[str, ClusterPerformance] = {}
        self._quarantine: Dict[str, SymbolQuarantineStatus] = {}
        self._mae_stats: Dict[str, MAEAdaptationStatus] = {}

        # Hydrate internal models from historical trades if not in isolated in-memory mode
        if not self.in_memory_only:
            self._rebuild_models()

    def _rebuild_models(self) -> None:
        """Reconstructs cluster stats, quarantines, and MAE adaptations from memory."""
        trades = self.memory.get_all_trades()
        for t in trades:
            self._update_model_for_trade(t, emit_events=False)

    # --------------------------------------------------------------------------
    # Hook: Trade Closure Event Dispatcher
    # --------------------------------------------------------------------------
    def on_trade_closed(self, trade_data: Union[TradeLearningRecord, Dict[str, Any]]) -> None:
        """
        Primary lifecycle hook invoked by PositionTracker whenever a position closes.
        Ingests the trade outcome, updates Bayesian weights, checks quarantine,
        and triggers ATR multiplier self-adaptation.
        """
        if isinstance(trade_data, TradeLearningRecord):
            rec = trade_data
        elif isinstance(trade_data, dict):
            # Resolve return_r if not directly supplied
            open_p = float(trade_data.get("open_price", trade_data.get("price", 0.0)))
            close_p = float(trade_data.get("close_price", 0.0))
            init_sl = float(trade_data.get("initial_sl", trade_data.get("sl", 0.0)))
            cmd = str(trade_data.get("direction", trade_data.get("cmd", "BUY"))).upper()
            is_buy = "BUY" in cmd

            return_r = float(trade_data.get("return_r", 0.0))
            if return_r == 0.0 and open_p > 0 and init_sl > 0:
                r_dist = abs(open_p - init_sl)
                if r_dist > 0 and close_p > 0:
                    profit_dist = (close_p - open_p) if is_buy else (open_p - close_p)
                    return_r = round(profit_dist / r_dist, 2)
            if return_r == 0.0:
                pnl = float(trade_data.get("realized_pnl", trade_data.get("pnl", 0.0)))
                # Approximate 0.5% risk default if initial risk cash not recorded
                lots = float(trade_data.get("lots", 0.01))
                if pnl > 0:
                    return_r = 1.5
                elif pnl < 0:
                    return_r = -1.0

            session = str(trade_data.get("session", "")).upper()
            if not session or session == "UNKNOWN":
                session = resolve_trading_session(float(trade_data.get("close_time", time.time())))

            regime = str(trade_data.get("regime", "")).upper()
            if not regime or regime == "UNKNOWN":
                regime = "TRENDING" if float(trade_data.get("entry_adx", 25.0)) > 25.0 else "RANGING"

            rec = TradeLearningRecord(
                ticket=int(trade_data.get("ticket", 0)),
                symbol=str(trade_data.get("symbol", "")),
                direction="BUY" if is_buy else "SELL",
                session=session,
                regime=regime,
                entry_rsi=float(trade_data.get("entry_rsi", 50.0)),
                entry_adx=float(trade_data.get("entry_adx", 0.0)),
                entry_cci=float(trade_data.get("entry_cci", 0.0)),
                distance_to_ema20_pips=float(trade_data.get("distance_to_ema20_pips", 0.0)),
                spread_at_entry=float(trade_data.get("spread_at_entry", 0.0)),
                confluence_score=float(trade_data.get("confluence_score", 0.0)),
                realized_pnl=float(trade_data.get("realized_pnl", trade_data.get("pnl", 0.0))),
                return_r=return_r,
                max_favorable_excursion_pips=float(trade_data.get("max_favorable_excursion_pips", trade_data.get("mfe_pips", 0.0))),
                max_adverse_excursion_pips=float(trade_data.get("max_adverse_excursion_pips", trade_data.get("mae_pips", 0.0))),
                close_reason=str(trade_data.get("close_reason", "MANUAL")).upper(),
                open_price=open_p,
                close_price=close_p,
                initial_sl=init_sl,
                initial_tp=float(trade_data.get("initial_tp", trade_data.get("tp", 0.0))),
                lots=float(trade_data.get("lots", 0.01)),
                open_time=float(trade_data.get("open_time", time.time())),
                close_time=float(trade_data.get("close_time", time.time()))
            )
        else:
            return

        # Save to TradeMemory and database
        self.memory.record_trade(rec)

        # Update in-memory models
        with self._lock:
            self._update_model_for_trade(rec, emit_events=True)

    def _update_model_for_trade(self, rec: TradeLearningRecord, emit_events: bool = True) -> None:
        """Internal worker updating cluster statistics, quarantine gates, and MAE adaptation."""
        canon = canonical_symbol(rec.symbol)
        rsi_zone = resolve_rsi_zone(rec.entry_rsi)
        session = rec.session if rec.session else resolve_trading_session(rec.close_time)

        cluster_key = build_cluster_key(canon, session, rsi_zone)
        symbol_key = f"{canon}_ALL"

        # Update specific cluster and aggregate symbol cluster
        for key in (cluster_key, symbol_key):
            self._apply_trade_to_cluster(key, rec)

        # Update Autonomous Symbol Quarantine
        self._evaluate_symbol_quarantine(canon, rec, emit_events=emit_events)

        # Update Volatility & Stop-Loss Self-Adaptation
        self._evaluate_mae_adaptation(canon, rec)

    def _apply_trade_to_cluster(self, key: str, rec: TradeLearningRecord) -> None:
        """Updates rolling metrics and Bayesian Beta posterior for a cluster."""
        perf = self._clusters.get(key)
        if not perf:
            perf = ClusterPerformance(cluster_key=key)
            self._clusters[key] = perf

        is_win = rec.return_r > 0.0
        perf.total_trades += 1
        if is_win:
            perf.wins += 1
            perf.consecutive_losses = 0
        else:
            perf.losses += 1
            perf.consecutive_losses += 1

        perf.last_r_multiples.append(rec.return_r)
        if len(perf.last_r_multiples) > self.max_history_window:
            perf.last_r_multiples.pop(0)

        # Rolling 20-trade evaluation
        recent_r = perf.last_r_multiples
        n_recent = len(recent_r)
        recent_wins = [r for r in recent_r if r > 0.0]
        recent_losses = [abs(r) for r in recent_r if r <= 0.0]

        # Bayesian Beta posterior update: prior (2, 2)
        perf.alpha = 2.0 + len(recent_wins)
        perf.beta = 2.0 + len(recent_losses)
        perf.win_rate = perf.alpha / (perf.alpha + perf.beta)

        perf.avg_win_r = float(sum(recent_wins) / len(recent_wins)) if recent_wins else 0.0
        perf.avg_loss_r = float(sum(recent_losses) / len(recent_losses)) if recent_losses else 0.0

        # Mathematical Expectancy E = (P_win * Avg Win) - (P_loss * Avg Loss)
        p_win = len(recent_wins) / n_recent if n_recent > 0 else perf.win_rate
        p_loss = 1.0 - p_win
        perf.expectancy_r = round((p_win * perf.avg_win_r) - (p_loss * perf.avg_loss_r), 2)

        # Profit Factor
        gross_win = sum(recent_wins)
        gross_loss = sum(recent_losses)
        perf.profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0.0 else (5.0 if gross_win > 0 else 1.0)

        # ----------------------------------------------------------------------
        # Setup-Condition Score Modifier:
        # - E < 0 or 2 consecutive losses -> Penalty (-10 to -25 points)
        # - E > 1.2R and PF > 1.8 -> Positive boost (+10 points)
        # ----------------------------------------------------------------------
        score_mod = 0.0
        if perf.consecutive_losses >= 2:
            score_mod = -15.0
            if perf.expectancy_r < -0.3:
                score_mod = -25.0
        elif perf.expectancy_r < -0.3:
            score_mod = -25.0
        elif perf.expectancy_r < 0.0:
            score_mod = -10.0
        elif perf.expectancy_r > 1.2 and perf.profit_factor > 1.8:
            score_mod = 10.0
        elif perf.expectancy_r > 0.8 and perf.profit_factor > 1.5:
            score_mod = 5.0

        perf.score_modifier = score_mod
        perf.last_updated = time.time()

    def _evaluate_symbol_quarantine(self, symbol: str, rec: TradeLearningRecord, emit_events: bool = True) -> None:
        """
        Autonomous Symbol Quarantine (Asset Circuit Breaker):
        Quarantines an asset for 48 hours if:
        1. Takes 2 consecutive full stop-loss hits.
        2. Has an expectancy of < -0.5R over its last 5 trades.
        """
        now = time.time()
        q_status = self._quarantine.get(symbol)
        if not q_status:
            q_status = SymbolQuarantineStatus(symbol=symbol)
            self._quarantine[symbol] = q_status

        # Check existing active quarantine
        if q_status.is_quarantined and now < q_status.quarantined_until:
            return

        # Fetch last 5 trades for this symbol
        recent_sym_trades = self.memory.get_recent_trades(5, symbol=symbol)
        if not recent_sym_trades:
            return

        # 1. Check for 2 consecutive full Stop-Loss hits
        is_sl_hit = (rec.close_reason == "SL" or rec.return_r <= -0.9)
        if is_sl_hit:
            q_status.consecutive_sl_count += 1
        else:
            q_status.consecutive_sl_count = 0

        # 2. Check rolling expectancy over last 5 trades
        recent_5_r = [t.return_r for t in recent_sym_trades]
        exp_5 = round(sum(recent_5_r) / len(recent_5_r), 2)
        q_status.rolling_expectancy_r = exp_5

        should_quarantine = False
        reason = ""

        if q_status.consecutive_sl_count >= 2:
            should_quarantine = True
            reason = f"Asset Circuit Breaker: 2 consecutive full Stop-Loss hits on {symbol}."
        elif len(recent_5_r) >= 3 and exp_5 < -0.5:
            should_quarantine = True
            reason = f"Asset Circuit Breaker: Expectancy ({exp_5:.2f}R) < -0.5R over last {len(recent_5_r)} trades on {symbol}."

        if should_quarantine:
            quarantine_duration = 48 * 3600.0  # 48 hours in seconds (172,800s)
            q_status.is_quarantined = True
            q_status.quarantined_until = now + quarantine_duration
            q_status.reason = reason
            logger.warning(f"🚨 [ADAPTIVE QUARANTINE ACTIVATED] {reason} Quarantined for 48 hours.")

            if emit_events:
                event_bus.publish(
                    getattr(EventType, "SYMBOL_QUARANTINED", EventType.RISK_CHECK_FAILED),
                    payload={
                        "symbol": symbol,
                        "duration_hours": 48,
                        "quarantined_until": q_status.quarantined_until,
                        "reason": reason,
                        "source": "AdaptiveLearner"
                    },
                    priority=EventPriority.HIGH,
                    source="AdaptiveLearner"
                )

    def _evaluate_mae_adaptation(self, symbol: str, rec: TradeLearningRecord) -> None:
        """
        Volatility & Stop-Loss Self-Adaptation:
        Compares realized MAE against initial Stop Loss for winning trades:
        - If winning trades consistently experience MAE >= 80% of SL before hitting TP:
          dynamically widens ATR multiplier by +0.2x.
        - If winning trades exit cleanly with MAE < 30% of SL:
          tightens ATR multiplier by -0.2x.
        """
        if rec.return_r <= 0.0:
            return  # Only evaluate MAE noise behavior on winning trades

        status = self._mae_stats.get(symbol)
        if not status:
            status = MAEAdaptationStatus(symbol=symbol)
            self._mae_stats[symbol] = status

        pip_size = float(PrecisionMath.get_pip_size(symbol))
        if pip_size <= 0.0:
            pip_size = 0.0001

        # Determine initial SL distance in pips
        initial_sl_pips = 0.0
        if rec.initial_sl > 0 and rec.open_price > 0:
            initial_sl_pips = abs(rec.open_price - rec.initial_sl) / pip_size

        if initial_sl_pips <= 0.0:
            return

        mae_pips = max(0.0, rec.max_adverse_excursion_pips)
        mae_ratio = min(2.0, mae_pips / initial_sl_pips)

        status.recent_win_mae_ratios.append(mae_ratio)
        if len(status.recent_win_mae_ratios) > 10:
            status.recent_win_mae_ratios.pop(0)

        ratios = status.recent_win_mae_ratios
        if len(ratios) >= 3:
            sorted_r = sorted(ratios)
            mid = len(sorted_r) // 2
            med_mae = (sorted_r[mid] if len(sorted_r) % 2 != 0 else (sorted_r[mid - 1] + sorted_r[mid]) / 2.0)
            status.median_mae_ratio = round(med_mae, 2)

            if med_mae >= 0.80:
                # Widen ATR multiplier by +0.2x to prevent premature wicks
                status.sl_multiplier_adjustment = 0.20
                logger.info(f"📐 [SL ATR ADAPTATION] {symbol} winning trades median MAE={med_mae:.2f} >= 0.80 SL. Widening ATR multiplier by +0.2x.")
            elif med_mae < 0.30:
                # Clean breakout with low noise: tighten ATR multiplier by -0.2x for better RR
                status.sl_multiplier_adjustment = -0.20
                logger.info(f"📐 [SL ATR ADAPTATION] {symbol} winning trades median MAE={med_mae:.2f} < 0.30 SL. Tightening ATR multiplier by -0.2x.")
            else:
                status.sl_multiplier_adjustment = 0.0

    # --------------------------------------------------------------------------
    # Hook: Pipeline Screening Score Modifier
    # --------------------------------------------------------------------------
    def get_score_modifier(self, symbol: str, features: Optional[Dict[str, Any]] = None) -> float:
        """
        Fast O(1) in-memory lookup called by pipeline.py during candidate screening.
        Modifies raw confluence score (-25.0 to +10.0) based on rolling Bayesian edge.
        """
        feats = features or {}
        canon = canonical_symbol(symbol)
        session = str(feats.get("session", "")).upper()
        if not session or session == "UNKNOWN":
            session = resolve_trading_session()

        rsi = float(feats.get("entry_rsi", feats.get("rsi", 50.0)))
        rsi_zone = resolve_rsi_zone(rsi)

        cluster_key = build_cluster_key(canon, session, rsi_zone)
        symbol_key = f"{canon}_ALL"

        with self._lock:
            # 1. Check primary setup cluster (Symbol + Session + RSI_Zone)
            cluster_perf = self._clusters.get(cluster_key)
            if cluster_perf and (cluster_perf.consecutive_losses >= 2 or cluster_perf.total_trades >= 3):
                return cluster_perf.score_modifier

            # 2. Hierarchical fallback: Aggregate Symbol Performance
            sym_perf = self._clusters.get(symbol_key)
            if sym_perf and (sym_perf.consecutive_losses >= 2 or sym_perf.total_trades >= 3):
                return sym_perf.score_modifier

        return 0.0

    # --------------------------------------------------------------------------
    # Hook: Autonomous Symbol Quarantine Interface
    # --------------------------------------------------------------------------
    def is_symbol_quarantined(self, symbol: str) -> bool:
        """
        Checks if symbol is currently in an active 48-hour quarantine freeze.
        Called by pipeline.py and risk_manager.py.
        """
        canon = canonical_symbol(symbol)
        now = time.time()
        with self._lock:
            st = self._quarantine.get(canon)
            if st and st.is_quarantined:
                if now < st.quarantined_until:
                    return True
                else:
                    # Quarantine expired
                    st.is_quarantined = False
                    st.consecutive_sl_count = 0
                    logger.info(f"✅ [ADAPTIVE QUARANTINE RELEASED] {canon} 48h freeze period completed. Trading resumed.")
                    return False
        return False

    def get_quarantine_status(self, symbol: str) -> QuarantineCheck:
        """Returns named tuple of (is_quarantined, remaining_seconds, reason)."""
        canon = canonical_symbol(symbol)
        now = time.time()
        with self._lock:
            st = self._quarantine.get(canon)
            if st and st.is_quarantined:
                rem = max(0.0, st.quarantined_until - now)
                if rem > 0:
                    return QuarantineCheck(True, rem, st.reason)
                else:
                    st.is_quarantined = False
                    st.consecutive_sl_count = 0
        return QuarantineCheck(False, 0.0, "")

    def get_quarantine_record(self, symbol: str) -> Optional[SymbolQuarantineStatus]:
        """Returns internal SymbolQuarantineStatus tracking record."""
        canon = canonical_symbol(symbol)
        with self._lock:
            return self._quarantine.get(canon)

    def reset_quarantine(self, symbol: Optional[str] = None) -> None:
        """Resets quarantine status for a specific symbol or all symbols."""
        with self._lock:
            if symbol:
                canon = canonical_symbol(symbol)
                if canon in self._quarantine:
                    self._quarantine[canon].is_quarantined = False
                    self._quarantine[canon].consecutive_sl_count = 0
            else:
                for st in self._quarantine.values():
                    st.is_quarantined = False
                    st.consecutive_sl_count = 0

    def clear_all_quarantines(self) -> None:
        """Clears all active symbol quarantines."""
        self.reset_quarantine()

    def clear_quarantine(self, symbol: str) -> None:
        """Clears quarantine for a specific symbol."""
        self.reset_quarantine(symbol)

    def quarantine_symbol(
        self,
        symbol: str,
        duration_sec: float = 172800.0,
        reason: str = "Manual / Autonomous Quarantine"
    ) -> None:
        """Quarantines a symbol for the specified duration (default 48 hours)."""
        canon = canonical_symbol(symbol)
        now = time.time()
        with self._lock:
            q_status = self._quarantine.get(canon)
            if not q_status:
                q_status = SymbolQuarantineStatus(symbol=canon)
                self._quarantine[canon] = q_status
            q_status.is_quarantined = True
            q_status.quarantined_until = now + duration_sec
            q_status.reason = reason

    # --------------------------------------------------------------------------
    # Hook: Volatility & Stop-Loss Self-Adaptation Interface
    # --------------------------------------------------------------------------
    def get_sl_atr_multiplier_adjustment(self, symbol: str) -> float:
        """Returns dynamic ATR multiplier adjustment (-0.2, 0.0, +0.2)."""
        canon = canonical_symbol(symbol)
        with self._lock:
            st = self._mae_stats.get(canon)
            if st:
                return st.sl_multiplier_adjustment
        return 0.0

    def get_adapted_sl_multiplier(self, symbol: str, base_multiplier: float = 2.0) -> float:
        """Returns effective dynamic ATR multiplier incorporating realized MAE learning."""
        adj = self.get_sl_atr_multiplier_adjustment(symbol)
        return max(1.5, min(3.0, round(base_multiplier + adj, 2)))

    # --------------------------------------------------------------------------
    # Telemetry & Status Formatting
    # --------------------------------------------------------------------------
    def get_learning_telemetry(self) -> Dict[str, Any]:
        """Returns serializable diagnostic dictionary of adaptive learning state."""
        with self._lock:
            clusters_summary = {
                k: {
                    "trades": v.total_trades,
                    "win_rate": round(v.win_rate, 2),
                    "expectancy_r": v.expectancy_r,
                    "profit_factor": v.profit_factor,
                    "score_modifier": v.score_modifier,
                    "consecutive_losses": v.consecutive_losses
                }
                for k, v in self._clusters.items() if v.total_trades > 0
            }
            quarantine_summary = {
                k: {
                    "quarantined": v.is_quarantined,
                    "remaining_sec": max(0.0, v.quarantined_until - time.time()),
                    "reason": v.reason
                }
                for k, v in self._quarantine.items() if v.is_quarantined
            }
            mae_summary = {
                k: {
                    "adjustment": v.sl_multiplier_adjustment,
                    "median_mae_ratio": v.median_mae_ratio
                }
                for k, v in self._mae_stats.items()
            }
        return {
            "total_trades_learned": len(self.memory.get_all_trades()),
            "active_clusters_count": len(clusters_summary),
            "clusters": clusters_summary,
            "quarantined_assets": quarantine_summary,
            "mae_adaptations": mae_summary
        }


# Global singleton instance
adaptive_learner = AdaptiveLearner()
