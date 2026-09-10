"""
Institutional Real-Time Risk Management & Pre-Trade Guardian.
Performs rigorous pre-order validation:
1. Midnight Rollover Spread Freeze (23:55 - 00:10 server time)
2. Live Pearson Covariance & Correlation Gatekeeper (directional correlation <= 0.75)
3. Dollar-Weighted Volatility Currency Exposure (Lots * ATR * Tick Value)
4. Dynamic Pip Valuation across FX, Metals, and Crosses
5. Prop-Firm Circuit Breakers: Daily Loss 2.0%, Trailing DD 8.0%, 3-Consecutive Loss Cooldown
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from autotrade.core.event_bus import event_bus, EventType, EventPriority
from autotrade.core.config_manager import get_config
from autotrade.risk.position_sizer import PositionSizer
from autotrade.risk.covariance import covariance_gatekeeper, canonical_symbol

logger = logging.getLogger("autotrade.risk.risk_manager")


@dataclass
class RiskCheckResult:
    """Consolidated outcome of the pre-order risk gatekeeper evaluation."""
    passed: bool
    reason: str = "Risk checks passed"
    adjusted_lots: float = 0.0
    risk_pct: float = 0.0
    warnings: List[str] = field(default_factory=list)
    correlation_exposure: Dict[str, float] = field(default_factory=dict)
    max_correlation: float = 0.0


class RiskManager:
    """
    Real-Time Risk Guardian enforcing institutional and prop-firm trading rules.
    """
    def __init__(self, position_sizer: Optional[PositionSizer] = None):
        self.config = get_config()
        self.position_sizer = position_sizer or PositionSizer()
        self.covariance = covariance_gatekeeper

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
                self._consecutive_losses = 0
                logger.warning(
                    f"RiskManager: {max_losses} consecutive losses reached. "
                    f"Cooldown activated for {cooldown_sec} seconds."
                )
        else:
            self._consecutive_losses = 0

    def is_rollover_window(self, server_time_str: Optional[str] = None) -> bool:
        """
        Detects dangerous interbank rollover window between 23:55 and 00:10 server time.
        During this window spreads widen 5x-20x, causing massive slippage and stop-outs.
        """
        now_dt = None
        if server_time_str:
            try:
                now_dt = datetime.strptime(str(server_time_str).strip(), "%Y.%m.%d %H:%M:%S")
            except Exception:
                pass
        if now_dt is None:
            # Fall back to UTC
            now_dt = datetime.now(timezone.utc)

        hour = now_dt.hour
        minute = now_dt.minute

        # 23:55 to 23:59
        if hour == 23 and minute >= 55:
            return True
        # 00:00 to 00:10
        if hour == 0 and minute <= 10:
            return True

        return False

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
        is_news_imminent: bool = False,
        server_time_str: Optional[str] = None,
        atr_value: Optional[float] = None
    ) -> RiskCheckResult:
        """
        Executes comprehensive institutional pre-flight risk checks before any order is submitted.
        """
        result = RiskCheckResult(passed=True, adjusted_lots=lots)
        balance = float(account_info.get("balance", 0.0))
        equity = float(account_info.get("equity", balance))
        margin_free = float(account_info.get("margin_free", account_info.get("free_margin", balance)))

        # Check 0: Mandatory SL and TP verification (never allow 0 stops)
        if sl <= 0.0 or tp <= 0.0:
            result.passed = False
            result.reason = "Mandatory Stop Loss and Take Profit must be specified."
            return result

        # Check 0a: Midnight Rollover Trading Freeze (23:55 - 00:10 server time)
        if self.is_rollover_window(server_time_str):
            result.passed = False
            result.reason = "Trading halt: Midnight rollover window (23:55 - 00:10). Spreads widened."
            logger.warning(f"RiskManager: Vetoing trade on {symbol}: {result.reason}")
            return result

        # Check 0b: Minimum Reward-to-Risk Ratio check (min 1.5:1)
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

        # Update peak equity
        if equity > self._peak_all_time_equity:
            self._peak_all_time_equity = equity

        # Check 0d: Peak Equity Drawdown Limit (Prop Firm High-Water Mark: max 8.0%)
        if self._peak_all_time_equity > 0:
            peak_dd_pct = ((self._peak_all_time_equity - equity) / self._peak_all_time_equity) * 100.0
            max_tot_dd = getattr(self.config.risk, "max_total_drawdown_pct", 8.0)
            if peak_dd_pct >= max_tot_dd:
                result.passed = False
                result.reason = f"Peak equity drawdown ({peak_dd_pct:.2f}%) exceeded maximum allowed ({max_tot_dd}%)."
                return result

        # Check 0e: Consecutive Loss Cooldown check (30 min cooldown after 3 losses)
        if time.time() < self._consecutive_pause_until:
            result.passed = False
            result.reason = f"Consecutive loss cooldown is active until {time.ctime(self._consecutive_pause_until)}."
            return result

        # Check 0f: Maximum Risk Per Trade using Dynamic Pip Value
        sym_canon = canonical_symbol(symbol)
        pip_unit = 0.01 if ("JPY" in sym_canon or "XAU" in sym_canon or "OIL" in sym_canon) else 0.0001
        sl_pips = (sl_dist / pip_unit) if pip_unit > 0 else 30.0
        pip_val = self.position_sizer.get_dynamic_pip_value(sym_canon)
        est_trade_risk_cash = sl_pips * pip_val * lots
        trade_risk_pct = (est_trade_risk_cash / equity * 100.0) if equity > 0 else 0.0
        result.risk_pct = round(trade_risk_pct, 2)

        max_risk_pct = getattr(self.config.risk, "max_account_risk_pct", 0.5)
        if trade_risk_pct > max_risk_pct * 1.15 and lots > 0.01:
            result.passed = False
            result.reason = f"Calculated trade risk ({trade_risk_pct:.2f}%) exceeds maximum per-trade limit ({max_risk_pct:.2f}%)."
            return result

        # Check 0g: Global Portfolio Risk Limit
        total_open_risk_cash = 0.0
        for p in open_positions:
            p_lots = float(p.get("lots", 0.0))
            p_price = float(p.get("price", p.get("open_price", 0.0)))
            p_sl = float(p.get("sl", 0.0))
            p_sym = canonical_symbol(str(p.get("symbol", "")))
            if p_sl > 0 and p_price > 0 and p_lots > 0:
                p_unit = 0.01 if ("JPY" in p_sym or "XAU" in p_sym or "OIL" in p_sym) else 0.0001
                p_pips = abs(p_price - p_sl) / p_unit
                p_pv = self.position_sizer.get_dynamic_pip_value(p_sym)
                total_open_risk_cash += p_pips * p_pv * p_lots

        portfolio_risk_pct = ((total_open_risk_cash + est_trade_risk_cash) / equity * 100.0) if equity > 0 else 0.0
        max_global_risk = getattr(self.config.risk, "max_global_risk_pct", 2.0)
        if portfolio_risk_pct > (max_global_risk + 0.05) and lots > 0.01:
            result.passed = False
            result.reason = f"Projected portfolio risk ({portfolio_risk_pct:.2f}%) exceeds global limit ({max_global_risk:.2f}%)."
            return result

        # Check 1: Daily Loss Circuit Breaker (Hard lock if daily drawdown reaches 2.0%)
        if self._is_daily_halted:
            result.passed = False
            result.reason = "Daily loss limit breached. Auto-trading is locked for the day."
            return result

        daily_drawdown_pct = 0.0
        if self._peak_daily_equity > 0:
            daily_drawdown_pct = ((self._peak_daily_equity - equity) / self._peak_daily_equity) * 100.0

        max_daily_loss = getattr(self.config.risk, "max_daily_loss_pct", 2.0)
        if daily_drawdown_pct >= max_daily_loss:
            self._is_daily_halted = True
            result.passed = False
            result.reason = f"Daily drawdown ({daily_drawdown_pct:.2f}%) exceeded maximum allowed ({max_daily_loss}%)."
            event_bus.publish(
                EventType.DAILY_LOSS_LIMIT_REACHED,
                payload={"drawdown_pct": daily_drawdown_pct, "equity": equity},
                priority=EventPriority.CRITICAL,
                source="RiskManager"
            )
            return result

        # Check 2: Maximum Concurrent Open Positions
        max_positions = getattr(self.config.risk, "max_open_positions", 8)
        if len(open_positions) >= max_positions:
            result.passed = False
            result.reason = f"Maximum open positions ({max_positions}) reached."
            return result

        # Check 3: Daily Trade Count Limit
        daily_limit = getattr(self.config.risk, "daily_trade_limit", 20)
        if self._daily_trades_count >= daily_limit:
            self._is_daily_halted = True
            result.passed = False
            result.reason = f"Daily trade count limit ({daily_limit}) reached. Trading halted."
            return result

        # Check 4: Volume & Lot Exposure Limits
        current_symbol_lots = sum(
            float(p.get("lots", 0.0)) for p in open_positions if canonical_symbol(str(p.get("symbol", ""))) == sym_canon
        )
        total_open_lots = sum(float(p.get("lots", 0.0)) for p in open_positions)

        max_lots_sym = getattr(self.config.risk, "max_lots_per_symbol", 2.0)
        if (current_symbol_lots + lots) > max_lots_sym:
            result.passed = False
            result.reason = f"Cumulative volume on {symbol} ({current_symbol_lots + lots:.2f}) exceeds limit ({max_lots_sym})."
            return result

        max_total_lots = getattr(self.config.risk, "max_total_lots", 10.0)
        if (total_open_lots + lots) > max_total_lots:
            result.passed = False
            result.reason = f"Portfolio volume ({total_open_lots + lots:.2f}) exceeds maximum allowable lots ({max_total_lots})."
            return result

        # Check 5: Free Margin Buffer Check
        est_margin_needed = (lots * 100000.0) / 100.0
        max_margin_usage = getattr(self.config.risk, "max_margin_usage_pct", 50.0)
        if est_margin_needed > margin_free * (max_margin_usage / 100.0):
            result.passed = False
            result.reason = f"Order margin requirement exceeds allowable free margin buffer ({max_margin_usage:.1f}%)."
            return result

        # Check 6: Real-Time Pearson Covariance & Correlation Gatekeeper
        corr_passed, corr_reason, max_corr = self.covariance.evaluate_candidate_correlation(
            candidate_symbol=sym_canon,
            candidate_direction=cmd,
            open_positions=open_positions
        )
        result.max_correlation = max_corr
        if not corr_passed:
            result.passed = False
            result.reason = corr_reason
            return result

        # Check 6b: Dollar-Weighted Volatility Currency Exposure
        vol_exp = self._calculate_dollar_weighted_exposure(open_positions, default_atr=atr_value or 0.0020)
        base_curr, quote_curr = self._split_currency_pair(sym_canon)
        eff_atr = atr_value if atr_value and atr_value > 0 else 0.0020
        eff_tick_val = pip_val
        cand_vol_dollar = lots * eff_atr * eff_tick_val * 1000.0

        dir_factor = 1.0 if cmd.upper() == "BUY" else -1.0
        base_exp = vol_exp.get(base_curr, 0.0) + dir_factor * cand_vol_dollar
        quote_exp = vol_exp.get(quote_curr, 0.0) - dir_factor * cand_vol_dollar

        # Maximum dollar volatility per currency: 5% of account balance
        max_curr_vol_dollar = balance * 0.05
        if abs(base_exp) > max_curr_vol_dollar or abs(quote_exp) > max_curr_vol_dollar:
            result.passed = False
            result.reason = f"Dollar-weighted volatility limit exceeded on {base_curr}/{quote_curr} (${abs(base_exp):.0f}/${abs(quote_exp):.0f} > ${max_curr_vol_dollar:.0f})."
            return result

        # Check 7: Volatility / High-Impact News Lot Scaling
        final_lots = lots
        if is_news_imminent:
            reduction_factor = (100.0 - getattr(self.config.risk, "news_volatility_reduction_pct", 50.0)) / 100.0
            final_lots = max(0.01, round(lots * reduction_factor, 2))
            result.warnings.append(
                f"High-impact news event imminent. Lot scaled from {lots:.2f} to {final_lots:.2f} (-50%)."
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
        clean = canonical_symbol(symbol)
        if len(clean) >= 6:
            return clean[:3], clean[3:6]
        return clean, "USD"

    def _calculate_dollar_weighted_exposure(
        self,
        open_positions: List[Dict[str, Any]],
        default_atr: float = 0.0020
    ) -> Dict[str, float]:
        """
        Calculates Net Dollar-Weighted Volatility Exposure:
        Exposure = Lots * ATR * Tick_Value * 1000
        Accounts for volatility parity between FX, Gold (4-8x FX volatility), and Commodities.
        """
        exposure: Dict[str, float] = {}
        for p in open_positions:
            sym = canonical_symbol(str(p.get("symbol", "")))
            cmd = str(p.get("cmd", "BUY")).upper()
            lots = float(p.get("lots", 0.01))
            atr = float(p.get("atr", default_atr))
            if atr <= 0:
                atr = default_atr

            tick_val = self.position_sizer.get_dynamic_pip_value(sym)
            vol_dollar = lots * atr * tick_val * 1000.0
            direction = 1.0 if "BUY" in cmd else -1.0

            base, quote = self._split_currency_pair(sym)
            exposure[base] = exposure.get(base, 0.0) + direction * vol_dollar
            exposure[quote] = exposure.get(quote, 0.0) - direction * vol_dollar

        return exposure
