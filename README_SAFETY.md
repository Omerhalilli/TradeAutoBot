# Ultra-Safe Multi-Symbol Autonomous Trading Bot
## Institutional Architecture, Risk Management & Safeguards Specification

---

### Executive Overview & Core Philosophy: Safety First
The **Ultra-Safe Multi-Symbol Autonomous Trading Bot** is an institutional-grade algorithmic execution engine engineered for MetaTrader 4 (MT4) and high-frequency ZeroMQ bridges. The primary objective is **absolute capital preservation**. The engine scans the entire broker Market Watch catalog autonomously, but enters positions **only** when market conditions satisfy strict, multi-layered risk verification checks.

Every trade decision passes **8 distinct rings of pre-trade and post-trade risk validation**. If any single check fails, the order is immediately vetoed. Under no circumstances does the system employ martingale, grid averaging, or unshielded orders.

---

## 1. Safety Architecture Overview

```
                           [ Market Opportunity Detected ]
                                         │
                                         ▼
                   ┌───────────────────────────────────────────┐
                   │   RING 1: Global Account Protection       │
                   │   - Peak Drawdown Limit Check (10%)       │
                   │   - Daily / Weekly / Monthly Loss Breakers│
                   │   - Consecutive Loss Pause (3 losses->30m)│
                   │   - Max Concurrent Open Positions (1)     │
                   │   - Max Margin Utilization (50%)          │
                   └─────────────────────┬─────────────────────┘
                                         │ Passed
                                         ▼
                   ┌───────────────────────────────────────────┐
                   │   RING 2: Temporal & News Filters         │
                   │   - High-Impact Economic News Blackout    │
                   │   - Friday Afternoon Cutoff (18:00 GMT)   │
                   │   - Rollover Spread Blackout (21:50-23:30)│
                   │   - Session Liquidity Verification        │
                   └─────────────────────┬─────────────────────┘
                                         │ Passed
                                         ▼
                   ┌───────────────────────────────────────────┐
                   │   RING 3: Multi-Symbol Risk Coordination  │
                   │   - Currency Exposure Clamping (Max 1)    │
                   │   - Portfolio Risk Budget (Sum Risk <= 2%)│
                   │   - Symbol Cooldown (60 min)              │
                   │   - Exact Canonical Pair Matching         │
                   └─────────────────────┬─────────────────────┘
                                         │ Passed
                                         ▼
                   ┌───────────────────────────────────────────┐
                   │   RING 4: Quantitative Confluence Engine  │
                   │   - Multi-EMA (20/50/200) Trend Alignment │
                   │   - RSI Dynamic Momentum Filter           │
                   │   - MACD Cross & Signal Validation        │
                   │   - Stochastic Oscillator Exhaustion      │
                   │   - Confluence Threshold: Score >= 6/10   │
                   └─────────────────────┬─────────────────────┘
                                         │ Passed
                                         ▼
                   ┌───────────────────────────────────────────┐
                   │   RING 5: Per-Trade Safety Filters        │
                   │   - Spread Threshold Filter (<= 40 pts)   │
                   │   - ATR Volatility Bounds (10 - 150 pips) │
                   │   - Mandatory Protective SL and TP        │
                   │   - Minimum Reward-to-Risk Ratio >= 1.5:1 │
                   │   - Volatility-Adjusted Lot Sizing (0.5%) │
                   └─────────────────────┬─────────────────────┘
                                         │ Passed
                                         ▼
                   ┌───────────────────────────────────────────┐
                   │   RING 6: Pre-Execution Environment Check │
                   │   - Terminal Connection (IsConnected())   │
                   │   - Trade Allowed Context                 │
                   │   - Quote Freshness (Age <= 5 seconds)    │
                   │   - Account Free Margin Availability      │
                   └─────────────────────┬─────────────────────┘
                                         │ Passed
                                         ▼
                   ┌───────────────────────────────────────────┐
                   │   RING 7: Safe Execution Engine           │
                   │   - Max Slippage Clamping (15 points)     │
                   │   - Broker StopLevel / FreezeLevel Clamp  │
                   │   - ECN Two-Step Execution Mode           │
                   │   - Requote Exponential Backoff (3 tries) │
                   │   - Unprotected Order Auto-Liquidation    │
                   └─────────────────────┬─────────────────────┘
                                         │ Filled
                                         ▼
                   ┌───────────────────────────────────────────┐
                   │   RING 8: Trade Lifecycle & Monitoring    │
                   │   - Automated Break-Even (+1 pip @ +15 pips)
                   │   - Trailing Stop Engine (Fixed/ATR)      │
                   │   - Real-Time On-Chart HUD Telemetry      │
                   │   - Non-Blocking Outbox Telegram Alerts   │
                   └───────────────────────────────────────────┘
```

---

## 2. Detailed Safety Requirement Categories

### Category 1: Global Account Protection
1. **Maximum Drawdown Limit (Equity-Based from Peak):**
   - Tracked via persistent MT4 GlobalVariable `AT_PEAK_EQUITY`.
   - If current equity drops by `MaxDrawdownPct` (default: **10.0%**) from peak equity:
     - All open positions across the entire portfolio are immediately liquidated.
     - Autonomous trading is latched into halted state (`AT_DD_HALTED = 1.0`).
     - A high-priority emergency notification is dispatched to Telegram.
     - Trading remains locked until an operator issues `/reset_risk`.

2. **Periodic Loss Limits (Daily, Weekly, Monthly):**
   - **Daily Loss Limit (`MaxDailyLossPct` = 2.0%):** If closed + floating losses for the trading day exceed 2.0% of starting equity, trading is halted until midnight server time (`AT_CB_TRIPPED_D = 1.0`).
   - **Weekly Loss Limit (`MaxWeeklyLossPct` = 5.0%):** If net loss for the calendar week reaches 5.0%, trading halts until Monday 00:00 server time.
   - **Monthly Loss Limit (`MaxMonthlyLossPct` = 8.0%):** If net loss for the calendar month reaches 8.0%, trading halts until the 1st of the next month.

3. **Maximum Consecutive Losses Guard:**
   - Evaluates closed deal history. If `MaxConsecutiveLosses` (default: **3**) consecutive losing trades occur:
     - The bot enters a **30-minute cooling-off period** (`ConsecutiveLossCooldownMin = 30`).
     - All autonomous entries are paused to prevent market whipsaw traps.

4. **Maximum Total Open Positions:**
   - Strict hard limit across the entire portfolio (`MaxOpenPositions` = **1**).
   - The scanner immediately aborts evaluation whenever an open market position exists.

5. **Maximum Margin Usage Buffer:**
   - Hard ceiling on margin utilization (`MaxMarginUsagePct` = **50.0%**).
   - Before order entry, projected margin requirement is verified. If `(AccountMargin() + TradeMargin) / Equity > 50%`, the trade is rejected or lot size clamped.
   - Critical margin call threshold at 150%: if margin level drops below 150%, emergency liquidation triggers.

---

### Category 2: Per-Trade Safety Filters
1. **Mandatory Stop Loss (SL) and Take Profit (TP):**
   - Every order MUST carry valid SL and TP. The bot strictly refuses to open any unshielded order.
   - Even if user configures 0, the engine enforces safe ATR-based default SL (`1.5 * ATR`) and TP (`3.0 * ATR`).

2. **Maximum Risk per Trade:**
   - Configured as `MaxRiskPerTradePct` = **0.5%** of account balance/equity.
   - Lots are calculated using exact symbol pip value:
     $$\text{Lots} = \frac{\text{Equity} \times (\text{RiskPct} / 100)}{\text{SL Pips} \times \text{Symbol Pip Value}}$$
   - Lot sizes are normalized and clamped to `MODE_LOTSTEP`, `MODE_MINLOT`, and `MODE_MAXLOT`.

3. **Minimum Reward-to-Risk Ratio:**
   - Enforces a minimum **1.5:1** Reward-to-Risk ratio (`MinRewardToRisk = 1.5`).
   - Trades where TP distance < `1.5 * SL distance` are automatically adjusted or rejected.

4. **Spread Filter:**
   - Per-symbol maximum spread ceiling (`MaxSpreadPoints = 40.0` points / 4.0 pips on forex).
   - During spread widening or news releases, symbols exceeding this ceiling are skipped.

5. **ATR Volatility Filter:**
   - Lower threshold (`MinATRPips = 10.0`): skips dormant, choppy markets where slippage eats edge.
   - Upper threshold (`MaxATRPips = 150.0`): skips extreme volatility spikes and unpredictable news candles.

6. **Time & Session Filters:**
   - Rollover blackout: 21:50 to 23:30 broker time (all trading blocked during illiquid bank rollover).
   - Major sessions: London (07:00-16:00 GMT) and New York (12:00-21:00 GMT).
   - Asian session allowed only for JPY, AUD, NZD crosses.

---

### Category 3: Order Execution & Management Safety
1. **Slippage Control:**
   - Strict maximum slippage limit (`SlippagePoints = 15` points / 1.5 pips).
   - If market slips beyond this threshold during submission, the order is rejected by broker.

2. **ECN Two-Step Execution & Failsafe:**
   - For ECN brokers requiring zero initial stops, the order is opened first and modified immediately with SL/TP.
   - **Emergency Failsafe:** If attaching SL/TP fails after 3 retry attempts, the order is **immediately closed** (`OrderClose`) to ensure capital is never exposed without protection.

3. **Automated Break-Even Protection:**
   - When floating profit reaches `BreakEvenTriggerPips` (default: **15 pips**), SL is shifted to Entry Price + `BreakEvenLockPips` (default: **+1 pip**).
   - Once break-even is activated, the position is guaranteed risk-free.

4. **Dynamic Trailing Stop Engine:**
   - Activates after profit reaches `TrailingStartPips` (default: **20 pips**).
   - Trails protective SL in incremental steps (`TrailingStepPips = 10` pips).

5. **Partial Profit Taking (Scale-Out):**
   - Optional liquidation of `PartialCloseRatio` (e.g. 50%) at `PartialCloseTriggerPips` (e.g. 25 pips).

6. **Emergency Kill Switch:**
   - Configurable `EmergencyKillSwitch` input parameter and `AT_KILL_SWITCH` MT4 GlobalVariable.
   - When triggered, all positions are instantly liquidated and the scanner halts.

---

### Category 4: Multi-Symbol Risk Coordination
1. **Currency Exposure & Correlation Clamping:**
   - Deconstructs symbols into canonical base and quote currencies (e.g. EURUSD -> EUR, USD).
   - Enforces `MaxExposurePerCurrency = 1`. If an order is already open on EURUSD, no other EUR or USD pair can be entered simultaneously.
   - Eliminates hidden portfolio correlation risks (e.g. holding EURUSD Buy + GBPUSD Buy simultaneously).

2. **Global Exposure Limit:**
   - Portfolio risk budget: `MaxGlobalRiskPct = 2.0%`.
   - Total cumulative dollar risk across all active trades cannot exceed 2.0% of account equity.

3. **Symbol Priority with Safety:**
   - When multiple instruments show confluence signals simultaneously, the engine ranks setups:
     1. Lowest spread
     2. Highest confluence score
     3. Best Reward-to-Risk ratio
   - Only the single safest candidate is executed.

4. **Strictly Prohibited: No Martingale, No Grid:**
   - All trade volumes are calculated purely from initial risk percentage and stop-loss distance.
   - Position sizing is never multiplied after a loss. No grid orders or averaging down.

---

### Category 5: News and Event Protection
1. **High-Impact News Blackout:**
   - Reads economic calendar events from the Python bridge (`news_service.py`).
   - Automatically pauses trade entries 30 minutes before and 30 minutes after High-Impact events (`AT_NEWS_BLOCKED = 1.0`).

2. **Friday Afternoon Cutoff & Weekend Handling:**
   - Enforces `FridayCutoffHourGMT = 18`. No new orders are permitted after 18:00 GMT on Fridays.
   - Optional `CloseTradesOnFriday` parameter to liquidate all positions prior to weekend market close.

---

### Category 6: Error Handling & Fail-Safe Mechanisms
1. **Connection Loss Guard:**
   - Pre-flight checks on `IsConnected()` and `IsTradeAllowed()`. If connection is lost, orders are withheld.

2. **Order Rejection Exponential Backoff:**
   - If an order is rejected (e.g., context busy, off quotes), the bot logs the error code and applies a 300-second backoff cooldown on that symbol instead of rapid retry spamming.

3. **Unexpected Restart & Crash Recovery:**
   - On `OnInit()`, the bot executes `AuditAndEnforceOpenOrderStops()`.
   - Any unshielded orders found on the account are immediately fitted with conservative ATR-based SL and TP.

---

### Category 7: Logging, Monitoring, and Alerts
1. **Comprehensive Audit Trail:**
   - Every filter decision, spread rejection, margin calculation, and order lifecycle event is recorded with millisecond timestamps in MT4 logs and rotating Python log files.

2. **Real-Time Interactive Telegram Alerts:**
   - Executions, break-even updates, trailing shifts, and circuit breaker halts are dispatched instantly via non-blocking outbox queues.
   - Alerts include interactive Telegram inline keyboard buttons: `[❌ Close]`, `[🛡️ BE]`, `[✂️ Half]`.

3. **On-Chart Heads-Up Display (HUD):**
   - Real-time dashboard rendered directly onto the MT4 chart showing:
     - Current System Status (`🟢 ACTIVE & SCANNING`, `🚨 CIRCUIT BREAKER HALT`, etc.)
     - Account Balance, Equity, Free Margin, and Margin Level %
     - Peak Equity and Peak Drawdown % vs `MaxDrawdownPct` Limit
     - Intraday Drawdown % vs `MaxDailyLossPct` Limit
     - Open Positions count vs `MaxOpenPositions`
     - Global Risk Exposure % vs `MaxGlobalRiskPct`
     - Monitored Symbols count and last evaluated symbol scorecard

---

## 3. Configuration & Parameter Reference

| Parameter | Type | Default | Description |
|---|---|---|---|
| `MaxOpenPositions` | `int` | `1` | Strict limit on simultaneous open trades across ALL symbols |
| `MaxRiskPerTradePct` | `double` | `0.5` | Risk percentage of balance/equity per individual trade |
| `MaxGlobalRiskPct` | `double` | `2.0` | Maximum cumulative risk percentage across all open trades |
| `MaxDailyLossPct` | `double` | `2.0` | Daily loss circuit breaker threshold (%) |
| `MaxWeeklyLossPct` | `double` | `5.0` | Weekly loss circuit breaker threshold (%) |
| `MaxMonthlyLossPct` | `double` | `8.0` | Monthly loss circuit breaker threshold (%) |
| `MaxDrawdownPct` | `double` | `10.0` | Maximum peak equity drawdown limit (%) before full liquidation |
| `MaxConsecutiveLosses` | `int` | `3` | Consecutive losses before triggering pause |
| `ConsecutiveLossCooldownMin` | `int` | `30` | Duration of cooldown pause after consecutive losses (minutes) |
| `MaxMarginUsagePct` | `double` | `50.0` | Maximum allowable margin utilization percentage |
| `MaxExposurePerCurrency` | `int` | `1` | Maximum open trades involving the same currency |
| `EmergencyKillSwitch` | `bool` | `false` | Emergency kill switch (instantly closes all trades & halts) |
| `MinConfluenceScore` | `int` | `6` | Minimum score to enter trade (score stands on 6 or past 6) |
| `MinRewardToRisk` | `double` | `1.5` | Minimum Reward-to-Risk ratio (TP >= 1.5 * SL) |
| `MaxSpreadPoints` | `double` | `40.0` | Maximum allowed spread in broker points |
| `MinATRPips` | `double` | `10.0` | Minimum ATR in pips (filter choppy/dormant market) |
| `MaxATRPips` | `double` | `150.0` | Maximum ATR in pips (filter extreme news volatility) |
| `CooldownMinutes` | `int` | `60` | Per-symbol cooldown period after closing a trade |
| `ScanTimeframe` | `ENUM_TIMEFRAMES` | `PERIOD_H1` | Confluence evaluation chart timeframe |
| `BatchSize` | `int` | `3` | Round-robin time-sliced scanning batch size |
| `TimerIntervalSec` | `int` | `2` | Timer execution frequency in seconds |
| `UseBreakEven` | `bool` | `true` | Automated break-even stop protection switch |
| `BreakEvenTriggerPips` | `int` | `15` | Profit threshold to move SL to entry |
| `BreakEvenLockPips` | `int` | `1` | Profit offset locked beyond entry |
| `UseTrailingStop` | `bool` | `true` | Automated trailing stop switch |
| `TrailingStartPips` | `int` | `20` | Profit threshold to activate trailing stop |
| `TrailingStepPips` | `int` | `10` | Trailing stop incremental step |
| `UseTimeFilter` | `bool` | `true` | Session liquidity & rollover filter switch |
| `FridayCutoffHourGMT` | `int` | `18` | Friday cutoff hour to halt new orders |
| `CloseTradesOnFriday` | `bool` | `false` | Close open positions before weekend |
| `UseNewsFilter` | `bool` | `true` | Filter trades around high-impact economic news |
| `MagicNumber` | `int` | `998801` | Unique EA magic identification number |
| `SlippagePoints` | `int` | `15` | Maximum permissible execution slippage (points) |

---

## 4. Verification & Testing Record

### Automated Compilation Verification
All MQL4 files compiled using MetaEditor via Wine with **0 errors and 0 warnings**:
- `AutonomousBot.mq4` -> `AutonomousBot.ex4` (0 errors, 0 warnings)
- `SmartAutoTradeEA_Pro.mq4` -> `SmartAutoTradeEA_Pro.ex4` (0 errors, 0 warnings)
- `MT4_ZeroMQ_Bridge.mq4` -> `MT4_ZeroMQ_Bridge.ex4` (0 errors, 0 warnings)

### Automated Test Suite Results
- **Unit Test Discovery (`tests/`):** **118 / 118 passed** (100% pass rate)
- **Full End-to-End Suite (`test_full_suite.py`):** **27 / 27 passed** (100% pass rate)
- Verified modules:
  - Configuration loading & schema verification
  - ZeroMQ IPC messaging and latency verification
  - Currency exposure & correlation clamping
  - Daily loss circuit breaker & peak drawdown protection
  - Consecutive loss cooldown tracking
  - Margin capacity verification
  - Mandatory SL/TP enforcement & Reward-to-Risk >= 1.5:1
  - Break-Even and Trailing Stop management
  - Telegram outbox atomic delivery and deduplication
  - Mocked autonomous execution pipeline

---

## 5. Deployment Instructions

1. **Deploy Compiled EAs:**
   - Copy `AutonomousBot.ex4`, `SmartAutoTradeEA_Pro.ex4`, and `MT4_ZeroMQ_Bridge.ex4` into your MetaTrader 4 terminal's `MQL4/Experts` folder.
   - Copy all `.mqh` files into `MQL4/Include`.

2. **Configure Python Environment:**
   - Copy `config.example.ini` to `config.ini` or `.env.example` to `.env`.
   - Configure your Telegram Bot Token and authorized chat ID.

3. **Attach to Chart:**
   - Attach `MT4_ZeroMQ_Bridge.ex4` to a single chart (e.g. EURUSD M1) with DLL imports enabled.
   - Attach `AutonomousBot.ex4` to another chart (e.g. GBPUSD H1) with AutoTrading enabled.
   - The on-chart HUD will immediately display active surveillance status and risk metrics.
