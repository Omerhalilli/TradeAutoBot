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
        self._daily_start_balance: float = 0.0
        self._is_daily_halted: bool = False
        self._last_day_reset: float = time.time()

    def reset_daily_stats(self, current_balance: float, current_equity: float) -> None:
        """Calibrates baseline metrics at the start of a new trading day."""
        self._daily_trades_count = 0
        self._daily_loss_amount = 0.0
        self._peak_daily_equity = max(current_balance, current_equity)
        self._daily_start_balance = current_balance
        self._is_daily_halted = False
        self._last_day_reset = time.time()
        logger.info(f"Daily risk safeguards reset. Baseline balance: ${current_balance:,.2f}")

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

        # Check 0: Calibration baseline check
        if self._daily_start_balance <= 0:
            self.reset_daily_stats(balance, equity)

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

        # Check 5: Margin Capacity Check
        est_margin_needed = (lots * 100000.0) / 100.0  # Approx 1:100 leverage
        if est_margin_needed > margin_free * 0.70:
            result.passed = False
            result.reason = "Insufficient free margin to sustain order buffer."
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
        clean = symbol.upper().replace(".PRO", "").replace(".RAW", "").replace("+", "").replace("M", "")
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
