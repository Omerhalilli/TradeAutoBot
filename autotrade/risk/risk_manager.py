"""
Institutional Real-Time Risk Management & Pre-Trade Guardian.
Performs rigorous pre-order validation, leverage & margin verification,
currency correlation exposure control, dynamic news volatility scaling,
and automatic circuit-breaker trading halts.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from autotrade.core.event_bus import event_bus, EventType, EventPriority
from autotrade.core.config_manager import get_config
from autotrade.risk.position_sizer import PositionSizer

logger = logging.getLogger("autotrade.risk.risk_manager")


@dataclass
class RiskCheckResult:
    """Consolidated outcome of the pre-order risk gatekeeper evaluation."""
    passed: bool
    reason: str = "Risk checks passed"
    adjusted_lots: float = 0.0
    risk_pct: float = 0.0
    warnings: List[str] = field(default_factory=list)
    correlation_exposure: Dict[str, int] = field(default_factory=dict)


class RiskManager:
    """
    Real-Time Risk Guardian enforcing institutional and prop-firm trading rules.
    """
    def __init__(self, position_sizer: Optional[PositionSizer] = None):
        self.config = get_config()
        self.position_sizer = position_sizer or PositionSizer()
        
        # Runtime risk tracking state
        self._daily_trades_count: int = 0
        self._daily_loss_amount: float = 0.0
        self._peak_daily_equity: float = 0.0
        self._peak_all_time_equity: float = 0.0
        self._consecutive_losses: int = 0
        self._consecutive_pause_until: float = 0.0
        self._daily_start_balance: float = 0.0
        self._is_daily_halted: bool = False
        self._last_day_reset: float = time.time()

    def reset_daily_stats(self, current_balance: float, current_equity: float) -> None:
        """Calibrates baseline metrics at the start of a new trading day."""
        self._daily_trades_count = 0
        self._daily_loss_amount = 0.0
        self._peak_daily_equity = max(current_balance, current_equity)
        if self._peak_all_time_equity <= 0:
            self._peak_all_time_equity = max(current_balance, current_equity)
        self._daily_start_balance = current_balance
        self._is_daily_halted = False
        self._last_day_reset = time.time()
        logger.info(f"Daily risk safeguards reset. Baseline balance: ${current_balance:,.2f}")

    def record_trade_result(self, profit: float) -> None:
        """Tracks consecutive loss streaks for cooldown enforcement."""
        if profit < 0:
            self._consecutive_losses += 1
            max_losses = getattr(self.config.risk, "max_consecutive_losses", 3)
            if self._consecutive_losses >= max_losses:
                cooldown_sec = getattr(self.config.risk, "consecutive_loss_cooldown_sec", 1800)
                self._consecutive_pause_until = time.time() + cooldown_sec
                self._consecutive_losses = 0  # Reset streak counter so next sequence requires full count
                logger.warning(
                    f"RiskManager: {max_losses} consecutive losses reached. "
                    f"Cooldown activated for {cooldown_sec} seconds."
                )
        else:
            self._consecutive_losses = 0

    def evaluate_order_risk(
        self,
        symbol: str,
        cmd: str,  # BUY or SELL
        lots: float,
        price: float,
        sl: float,
        tp: float,
        account_info: Dict[str, Any],
        open_positions: List[Dict[str, Any]],
        is_news_imminent: bool = False
    ) -> RiskCheckResult:
        """
        Executes pre-flight risk checks before any order is submitted to the market.
        Returns RiskCheckResult indicating approval or rejection with detailed rationale.
        """
        result = RiskCheckResult(passed=True, adjusted_lots=lots)
        balance = float(account_info.get("balance", 0.0))
        equity = float(account_info.get("equity", balance))
        margin_free = float(account_info.get("margin_free", balance))

        # Check 0: Mandatory SL and TP verification (never allow 0 stops)
        if sl <= 0.0 or tp <= 0.0:
            result.passed = False
            result.reason = "Mandatory Stop Loss and Take Profit must be specified."
            return result

        # Check 0b: Minimum Reward-to-Risk Ratio check (default 1.5:1)
        sl_dist = abs(price - sl)
        tp_dist = abs(tp - price)
        rr = tp_dist / sl_dist if sl_dist > 0 else 0.0
        min_rr = getattr(self.config.risk, "min_risk_reward_ratio", 1.5)
        if rr < (min_rr - 0.01):
            result.passed = False
            result.reason = f"Reward-to-risk ratio ({rr:.2f}) is below minimum required ({min_rr:.2f}:1)."
            return result

        # Check 0c: Calibration baseline check
        if self._daily_start_balance <= 0:
            self.reset_daily_stats(balance, equity)

        # Update all-time peak equity
        if equity > self._peak_all_time_equity:
            self._peak_all_time_equity = equity

        # Check 0d: Peak Equity Drawdown Limit (Global Account Protection)
        if self._peak_all_time_equity > 0:
            peak_dd_pct = ((self._peak_all_time_equity - equity) / self._peak_all_time_equity) * 100.0
            if peak_dd_pct >= self.config.risk.max_total_drawdown_pct:
                result.passed = False
                result.reason = f"Peak equity drawdown ({peak_dd_pct:.2f}%) exceeded maximum allowed ({self.config.risk.max_total_drawdown_pct}%)."
                return result

        # Check 0e: Consecutive Loss Cooldown check
        if time.time() < self._consecutive_pause_until:
            result.passed = False
            result.reason = f"Consecutive loss cooldown is active until {time.ctime(self._consecutive_pause_until)}."
            return result

        # Check 0f: Maximum Risk Per Trade (e.g. 0.5% of equity/balance)
        sym_upper = symbol.upper()
        pip_size = 0.01 if ("JPY" in sym_upper or "XAU" in sym_upper or "OIL" in sym_upper) else 0.0001
        sl_pips = sl_dist / pip_size if pip_size > 0 else 30.0
        pip_val = 100.0 if "XAU" in sym_upper else (9.0 if "JPY" in sym_upper else 10.0)
        est_trade_risk_cash = sl_pips * pip_val * lots
        trade_risk_pct = (est_trade_risk_cash / equity * 100.0) if equity > 0 else 0.0
        result.risk_pct = round(trade_risk_pct, 2)

        max_risk_pct = getattr(self.config.risk, "max_account_risk_pct", 0.5)
        # Allow minor rounding tolerance up to 1.1x max risk for minimum broker lot size (0.01)
        if trade_risk_pct > max_risk_pct * 1.10 and lots > 0.01:
            result.passed = False
            result.reason = f"Calculated trade risk ({trade_risk_pct:.2f}%) exceeds maximum per-trade limit ({max_risk_pct:.2f}%)."
            return result

        # Check 0g: Global Portfolio Risk Limit (Cap total risk across all open positions)
        total_open_risk_cash = 0.0
        for p in open_positions:
            p_lots = float(p.get("lots", 0.0))
            p_price = float(p.get("price", p.get("open_price", 0.0)))
            p_sl = float(p.get("sl", 0.0))
            p_sym = str(p.get("symbol", "")).upper()
            if p_sl > 0 and p_price > 0 and p_lots > 0:
                p_pip_sz = 0.01 if ("JPY" in p_sym or "XAU" in p_sym or "OIL" in p_sym) else 0.0001
                p_pips = abs(p_price - p_sl) / p_pip_sz
                p_pv = 100.0 if "XAU" in p_sym else (9.0 if "JPY" in p_sym else 10.0)
                total_open_risk_cash += p_pips * p_pv * p_lots

        portfolio_risk_pct = ((total_open_risk_cash + est_trade_risk_cash) / equity * 100.0) if equity > 0 else 0.0
        max_global_risk = getattr(self.config.risk, "max_global_risk_pct", 2.0)
        if portfolio_risk_pct > (max_global_risk + 0.05) and lots > 0.01:
            result.passed = False
            result.reason = f"Projected portfolio risk ({portfolio_risk_pct:.2f}%) exceeds global limit ({max_global_risk:.2f}%)."
            return result

        # Check 1: Daily Loss Circuit Breaker
        if self._is_daily_halted:
            result.passed = False
            result.reason = "Daily loss limit breached. Auto-trading is locked for the day."
            return result

        daily_drawdown_pct = 0.0
        if self._peak_daily_equity > 0:
            daily_drawdown_pct = ((self._peak_daily_equity - equity) / self._peak_daily_equity) * 100.0

        if daily_drawdown_pct >= self.config.risk.max_daily_loss_pct:
            self._is_daily_halted = True
            result.passed = False
            result.reason = f"Daily drawdown ({daily_drawdown_pct:.2f}%) exceeded maximum allowed ({self.config.risk.max_daily_loss_pct}%)."
            
            event_bus.publish(
                EventType.DAILY_LOSS_LIMIT_REACHED,
                payload={"drawdown_pct": daily_drawdown_pct, "equity": equity},
                priority=EventPriority.CRITICAL,
                source="RiskManager"
            )
            return result

        # Check 2: Maximum Concurrent Open Positions
        if len(open_positions) >= self.config.risk.max_open_positions:
            result.passed = False
            result.reason = f"Maximum open positions ({self.config.risk.max_open_positions}) reached."
            event_bus.publish(
                EventType.TELEGRAM_NOTIFICATION,
                payload={"message": f"⚠️ <b>Risk Alert:</b> Maximum open positions limit ({self.config.risk.max_open_positions}) reached.", "priority": "HIGH"},
                priority=EventPriority.HIGH,
                source="RiskManager"
            )
            return result

        # Check 3: Daily Trade Count Limit
        if self._daily_trades_count >= self.config.risk.daily_trade_limit:
            self._is_daily_halted = True
            result.passed = False
            result.reason = f"Daily trade count limit ({self.config.risk.daily_trade_limit}) reached. Trading halted."
            event_bus.publish(
                EventType.DAILY_LOSS_LIMIT_REACHED,
                payload={"reason": "Daily trade count limit reached", "trades": self._daily_trades_count},
                priority=EventPriority.CRITICAL,
                source="RiskManager"
            )
            event_bus.publish(
                EventType.TELEGRAM_NOTIFICATION,
                payload={"message": f"🚨 <b>TRADING HALTED:</b> Daily trade count limit ({self.config.risk.daily_trade_limit}) reached!", "priority": "CRITICAL"},
                priority=EventPriority.CRITICAL,
                source="RiskManager"
            )
            return result

        # Check 4: Volume & Lot Exposure Limits
        current_symbol_lots = sum(
            float(p.get("lots", 0.0)) for p in open_positions if p.get("symbol", "").upper() == symbol.upper()
        )
        total_open_lots = sum(float(p.get("lots", 0.0)) for p in open_positions)

        if (current_symbol_lots + lots) > self.config.risk.max_lots_per_symbol:
            result.passed = False
            result.reason = f"Cumulative volume on {symbol} ({current_symbol_lots + lots:.2f}) exceeds limit ({self.config.risk.max_lots_per_symbol})."
            return result

        if (total_open_lots + lots) > self.config.risk.max_total_lots:
            result.passed = False
            result.reason = f"Portfolio volume ({total_open_lots + lots:.2f}) exceeds maximum allowable lots ({self.config.risk.max_total_lots})."
            return result

        # Check 5: Margin Capacity Check (Maximum Margin Usage limit)
        est_margin_needed = (lots * 100000.0) / 100.0  # Approx 1:100 leverage
        max_margin_usage = getattr(self.config.risk, "max_margin_usage_pct", 50.0)
        if est_margin_needed > margin_free * (max_margin_usage / 100.0):
            result.passed = False
            result.reason = f"Order margin requirement exceeds allowable free margin buffer ({max_margin_usage:.1f}%)."
            return result

        # Check 6: Currency Correlation Exposure Control
        base_curr, quote_curr = self._split_currency_pair(symbol)
        curr_exposure = self._calculate_currency_exposure(open_positions)
        
        # Net direction exposure
        dir_factor = 1 if cmd.upper() == "BUY" else -1
        base_exp = curr_exposure.get(base_curr, 0) + dir_factor
        quote_exp = curr_exposure.get(quote_curr, 0) - dir_factor

        if abs(base_exp) > self.config.risk.max_correlated_positions or abs(quote_exp) > self.config.risk.max_correlated_positions:
            result.passed = False
            result.reason = f"Correlation exposure limit exceeded on {base_curr}/{quote_curr} ({base_exp}/{quote_exp}). Limit: {self.config.risk.max_correlated_positions}."
            return result

        # Check 7: Volatility / High-Impact News Lot Scaling
        final_lots = lots
        if is_news_imminent:
            reduction_factor = (100.0 - self.config.risk.news_volatility_reduction_pct) / 100.0
            final_lots = max(0.01, round(lots * reduction_factor, 2))
            result.warnings.append(
                f"High-impact news event imminent. Lot scaled from {lots:.2f} to {final_lots:.2f} (-{self.config.risk.news_volatility_reduction_pct}%)."
            )

        result.adjusted_lots = final_lots
        if result.passed:
            self._daily_trades_count += 1
        
        event_bus.publish(
            EventType.RISK_CHECK_PASSED if result.passed else EventType.RISK_CHECK_FAILED,
            payload={"symbol": symbol, "cmd": cmd, "passed": result.passed, "reason": result.reason},
            priority=EventPriority.NORMAL,
            source="RiskManager"
        )
        return result

    def _split_currency_pair(self, symbol: str) -> Tuple[str, str]:
        """Deconstructs instrument symbol into base and quote currency components."""
        from autotrade.core.autonomous_trader import canonical_symbol
        clean = canonical_symbol(symbol)
        if len(clean) >= 6:
            return clean[:3], clean[3:6]
        return clean, "USD"

    def _calculate_currency_exposure(self, open_positions: List[Dict[str, Any]]) -> Dict[str, int]:
        """Builds net directional currency exposure tally across all open trades."""
        exposure: Dict[str, int] = {}
        for p in open_positions:
            sym = p.get("symbol", "")
            cmd = p.get("cmd", "BUY").upper()
            base, quote = self._split_currency_pair(sym)
            direction = 1 if "BUY" in cmd else -1
            
            exposure[base] = exposure.get(base, 0) + direction
            exposure[quote] = exposure.get(quote, 0) - direction
        return exposure
