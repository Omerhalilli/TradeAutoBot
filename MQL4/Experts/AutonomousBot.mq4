//+------------------------------------------------------------------+
//|                                                AutonomousBot.mq4 |
//|                     Autonomous Multi-Symbol Market Scanner & Bot |
//|                     Ultra-Safe Institutional Risk Architecture   |
//|                     Compatible with MQL4 and MetaEditor          |
//+------------------------------------------------------------------+
#property copyright "Antigravity Automated Systems"
#property link      "https://t.me"
#property version   "2.00"
#property strict

#include <SymbolManager.mqh>
#include <StrategyEngine.mqh>
#include <RiskController.mqh>
#include <TradeExecutor.mqh>
#include <TelegramShared.mqh>

//--- [01] GLOBAL ACCOUNT PROTECTION
input string             Sec_GlobalRisk                = "=== 1. GLOBAL ACCOUNT PROTECTION ===";
input int                MaxOpenPositions              = 1;                 // Strict Global Limit on Open Trades (Default: 1)
input double             MaxRiskPerTradePct            = 0.5;               // Risk Percentage of Balance/Equity per Trade (0.5%)
input double             MaxGlobalRiskPct              = 2.0;               // Maximum Global Exposure Limit across Portfolio (2.0%)
input double             MaxDailyLossPct               = 2.0;               // Daily Loss Circuit Breaker (%)
input double             MaxWeeklyLossPct              = 5.0;               // Weekly Loss Circuit Breaker (%)
input double             MaxMonthlyLossPct             = 8.0;               // Monthly Loss Circuit Breaker (%)
input double             MaxDrawdownPct                = 10.0;              // Maximum Peak Equity Drawdown Limit (%)
input int                MaxConsecutiveLosses          = 3;                 // Maximum Consecutive Losses Before Cooldown
input int                ConsecutiveLossCooldownMin    = 30;                // Pause Duration After Max Consecutive Losses (Minutes)
input double             MaxMarginUsagePct             = 50.0;              // Maximum Margin Utilization Allowed (%)
input int                MaxExposurePerCurrency        = 1;                 // Maximum Concurrent Trades per Currency (e.g. USD)
input bool               EmergencyKillSwitch           = false;             // Emergency Kill Switch (Close all & halt immediately)

//--- [02] PER-TRADE & SCANNER SAFETY FILTERS
input string             Sec_PerTradeSafety            = "=== 2. PER-TRADE & SCANNER SAFETY FILTERS ===";
input int                MinConfluenceScore            = 6;                 // Minimum Confluence Score to Execute (stands on 6 or past 6)
input double             MinRewardToRisk               = 1.5;               // Minimum Reward-to-Risk Ratio (TP >= 1.5 * SL)
input double             MaxSpreadPoints               = 40.0;              // Maximum Allowed Spread (Points)
input double             MinATRPips                    = 10.0;              // Minimum ATR in Pips (Filter dead / choppy market)
input double             MaxATRPips                    = 150.0;             // Maximum ATR in Pips (Filter extreme volatility / spikes)
input int                CooldownMinutes               = 60;                // Per-Symbol Trade Cooldown (Minutes)
input string             IncludeSymbols                = "";                // Whitelist Symbols (empty = all Market Watch)
input string             ExcludeSymbols                = "*RUB*,*TRY*,*ZAR*"; // Blacklist Wildcards (Exotics/High-Swap)
input ENUM_TIMEFRAMES    ScanTimeframe                 = PERIOD_H1;         // Confluence Scoring Timeframe
input int                BatchSize                     = 3;                 // Round-Robin Time-Sliced Batch Size
input int                TimerIntervalSec              = 2;                 // Scanner Timer Interval (Seconds)

//--- [03] TRADE MANAGEMENT & LIFECYCLE
input string             Sec_TradeManagement           = "=== 3. TRADE MANAGEMENT & LIFECYCLE ===";
input bool               UseBreakEven                  = true;              // Enable Automated Break-Even Protection
input int                BreakEvenTriggerPips          = 15;                // Profit in Pips to Move SL to Entry
input int                BreakEvenLockPips             = 1;                 // Profit Offset Locked Beyond Entry (Pips)
input bool               UseTrailingStop               = true;              // Enable Trailing Stop Engine
input int                TrailingStartPips             = 20;                // Profit Level to Activate Trailing (Pips)
input int                TrailingStepPips              = 10;                // Trailing Incremental Step (Pips)
input bool               UsePartialClose               = false;             // Enable Partial Take Profit
input int                PartialCloseTriggerPips       = 25;                // Profit Level for Partial Close (Pips)
input double             PartialCloseRatio             = 0.50;              // Ratio of Position to Liquidate (0.5 = 50%)

//--- [04] TIME, SESSION & NEWS FILTERS
input string             Sec_TimeFilters               = "=== 4. TIME & NEWS FILTERS ===";
input bool               UseTimeFilter                 = true;              // Enforce Session & Liquidity Filter
input int                FridayCutoffHourGMT           = 18;                // Friday Trading Cutoff Hour (GMT)
input bool               CloseTradesOnFriday           = false;             // Close Open Positions on Friday Afternoon
input bool               UseNewsFilter                 = true;              // Avoid Trading Around High-Impact News

//--- [05] SYSTEM & EXECUTION
input string             Sec_System                    = "=== 5. SYSTEM & EXECUTION ===";
input int                MagicNumber                   = 998801;            // Autonomous Bot Magic Number
input string             TradeComment                  = "AutoBot_Safe";    // Order Comment Prefix
input int                SlippagePoints                = 15;                // Maximum Allowed Slippage Points

// Global Scanner State
string g_Watchlist[];
int    g_TotalWatchlist    = 0;
int    g_CurrentScanIndex  = 0;
string g_LastScannedSymbol = "None";
int    g_LastScannedScore  = 0;
string g_LastScannedSignal = "HOLD";

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("[AUTONOMOUS BOT] Initializing Ultra-Safe Multi-Symbol Autonomous Bot v2.00...");

   if(EmergencyKillSwitch)
   {
      Print("[AUTONOMOUS BOT] ⚠️ EMERGENCY KILL SWITCH IS ACTIVE. Auto-trading disabled.");
   }

   // 1. Audit open orders and attach mandatory stops to any unprotected positions
   AuditAndEnforceOpenOrderStops(MagicNumber);

   // 2. Discover Market Watch symbols dynamically
   g_TotalWatchlist = DiscoverMarketWatchSymbols(g_Watchlist, IncludeSymbols, ExcludeSymbols);
   PrintFormat("[AUTONOMOUS BOT] Watchlist initialized with %d active symbols from Market Watch.", g_TotalWatchlist);

   // 3. Start timer for staggered round-robin scanner
   EventSetTimer(TimerIntervalSec);

   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Telegram_FlushQueue();
   Comment("");
   PrintFormat("[AUTONOMOUS BOT] Deinitialized. Reason code: %d", reason);
}

//+------------------------------------------------------------------+
//| Staggered Round-Robin Scanner Batch                              |
//| Enforces score >= 6 trade entry, mandatory SL/TP, and risk caps  |
//+------------------------------------------------------------------+
void ScanNextSymbolBatch(int batchSize = 3)
{
   if(g_TotalWatchlist <= 0)
   {
      g_TotalWatchlist = DiscoverMarketWatchSymbols(g_Watchlist, IncludeSymbols, ExcludeSymbols);
      if(g_TotalWatchlist <= 0) return;
   }

   for(int i = 0; i < batchSize; i++)
   {
      // 1. Atomic verification before evaluating symbol:
      // If MaxOpenPositions limit reached, abort immediately across all remaining symbols
      if(GetGlobalActivePositions(MagicNumber) >= MaxOpenPositions)
      {
         return;
      }

      string sym = g_Watchlist[g_CurrentScanIndex];
      g_CurrentScanIndex = (g_CurrentScanIndex + 1) % g_TotalWatchlist;
      g_LastScannedSymbol = sym;

      // 2. Pre-filter dormant/disabled symbols before calculating expensive indicators
      if(!PreFilterSymbol(sym, MaxSpreadPoints, 50, ScanTimeframe, UseTimeFilter))
      {
         continue;
      }

      // 3. Check persistent cooldown
      if(IsSymbolInCooldown(sym, CooldownMinutes))
      {
         continue;
      }

      // 4. Exact canonical symbol matching: verify no existing position is open for this pair
      bool hasPosition = false;
      for(int k = 0; k < OrdersTotal(); k++)
      {
         if(!OrderSelect(k, SELECT_BY_POS, MODE_TRADES)) continue;
         if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
         if(AreSymbolsMatching(OrderSymbol(), sym))
         {
            hasPosition = true;
            break;
         }
      }
      if(hasPosition) continue;

      // 5. Currency exposure / correlation clamping (limit exposure per currency)
      if(!CanOpenCurrencyExposure(sym, MaxExposurePerCurrency, MagicNumber))
      {
         continue;
      }

      // 6. Quantitative Confluence Scoring (EMA, RSI, MACD, Stochastic, Price Action, ATR volatility)
      StrategySignal sig = EvaluateSymbolOpportunity(sym, ScanTimeframe, MinConfluenceScore, MinRewardToRisk, MinATRPips, MaxATRPips);
      g_LastScannedScore  = sig.score;
      g_LastScannedSignal = (sig.cmd == OP_BUY ? "BUY" : (sig.cmd == OP_SELL ? "SELL" : "HOLD"));

      // Confluence threshold: must stand on 6 or past 6 (>= 6)
      if(!sig.valid || sig.cmd < 0 || sig.score < MinConfluenceScore)
      {
         continue;
      }

      // 7. Volatility-Adjusted Risk Sizing (ATR-based strict dollar risk)
      double lots = CalculateRiskLots(sym, MaxRiskPerTradePct, sig.slPips, MaxMarginUsagePct);
      if(lots <= 0.0) continue;

      // 8. Pre-flight Margin Utilization Check (max 50% free margin)
      if(!CheckMarginUsageAllowed(sym, lots, MaxMarginUsagePct))
      {
         continue;
      }

      // 9. Global Portfolio Risk Budget Check (sum open risks <= MaxGlobalRiskPct)
      if(!CheckGlobalPortfolioRisk(MaxRiskPerTradePct, MaxGlobalRiskPct, MagicNumber))
      {
         continue;
      }

      PrintFormat("[AUTONOMOUS OPPORTUNITY DETECTED] %s | Signal: %s | Score: %d/10 | Lots: %.2f | SL: %f | TP: %f | RR: %.2f",
                  sym, (sig.cmd == OP_BUY ? "BUY" : "SELL"), sig.score, lots, sig.slPrice, sig.tpPrice, (sig.tpPips / sig.slPips));

      // 10. Safe Order Execution with ECN two-step, requote exponential backoff, and latency logging
      int ticket = ExecuteOrderSafe(sym, sig.cmd, lots, sig.slPrice, sig.tpPrice, MagicNumber, TradeComment, SlippagePoints);
      if(ticket > 0)
      {
         RecordSymbolCooldown(sym);
         PrintFormat("[AUTONOMOUS BOT] Successfully filled %s on %s (Lots: %.2f, Score: %d/10, Ticket: #%d)",
                     (sig.cmd == OP_BUY ? "BUY" : "SELL"), sym, lots, sig.score, ticket);

         // Strict position limit enforced: abort scan immediately across all other symbols
         return;
      }
   }
}

//+------------------------------------------------------------------+
//| Update On-Chart Real-Time Risk Dashboard                         |
//+------------------------------------------------------------------+
void UpdateChartHUD()
{
   double equity  = AccountEquity();
   double balance = AccountBalance();
   double freeMargin = AccountFreeMargin();
   double marginLevel = (AccountMargin() > 0.0) ? ((equity / AccountMargin()) * 100.0) : 0.0;

   double peakEq = GlobalVariableCheck("AT_PEAK_EQUITY") ? GlobalVariableGet("AT_PEAK_EQUITY") : equity;
   double peakDD = (peakEq > 0.0) ? (((peakEq - equity) / peakEq) * 100.0) : 0.0;

   double dayPeak = GlobalVariableCheck("AT_CB_PEAK_D") ? GlobalVariableGet("AT_CB_PEAK_D") : equity;
   double dayDD   = (dayPeak > 0.0) ? (((dayPeak - equity) / dayPeak) * 100.0) : 0.0;

   int activePos = GetGlobalActivePositions(MagicNumber);
   bool isDDHalted = GlobalVariableCheck("AT_DD_HALTED") && (GlobalVariableGet("AT_DD_HALTED") > 0.5);
   bool isDayHalted = GlobalVariableCheck("AT_CB_TRIPPED_D") && (GlobalVariableGet("AT_CB_TRIPPED_D") > 0.5);
   bool isPaused = GlobalVariableCheck("AT_CONSEC_PAUSE_UNTIL") && (TimeCurrent() < (datetime)GlobalVariableGet("AT_CONSEC_PAUSE_UNTIL"));

   string statusStr = "🟢 ACTIVE & SCANNING";
   if(EmergencyKillSwitch) statusStr = "🚨 KILL SWITCH ACTIVE (HALTED)";
   else if(isDDHalted)     statusStr = "🚨 MAX DRAWDOWN HALT (HALTED)";
   else if(isDayHalted)    statusStr = "⏸️ DAILY LOSS LIMIT HALTED";
   else if(isPaused)       statusStr = "⚠️ CONSECUTIVE LOSS COOLDOWN";
   else if(activePos >= MaxOpenPositions) statusStr = "🔒 POSITION LIMIT REACHED";

   string hud = StringFormat(
      "=== ULTRA-SAFE AUTONOMOUS TRADING BOT v2.00 ===\n" +
      "Status: %s\n" +
      "-----------------------------------------------\n" +
      "Account Balance: $%.2f | Equity: $%.2f\n" +
      "Free Margin: $%.2f | Margin Level: %.1f%%\n" +
      "Peak Equity: $%.2f | Peak Drawdown: %.2f%% (Limit: %.1f%%)\n" +
      "Intraday Drawdown: %.2f%% (Limit: %.1f%%)\n" +
      "-----------------------------------------------\n" +
      "Open Positions: %d / %d (Max)\n" +
      "Max Risk Per Trade: %.1f%% | Max Global Risk: %.1f%%\n" +
      "Min Score: %d/10 | Min RR: 1:%.1f | Max Spread: %.0f pts\n" +
      "Monitored Symbols: %d active\n" +
      "Last Scanned: %s (Signal: %s, Score: %d/10)\n" +
      "===============================================",
      statusStr, balance, equity, freeMargin, marginLevel,
      peakEq, peakDD, MaxDrawdownPct, dayDD, MaxDailyLossPct,
      activePos, MaxOpenPositions, MaxRiskPerTradePct, MaxGlobalRiskPct,
      MinConfluenceScore, MinRewardToRisk, MaxSpreadPoints,
      g_TotalWatchlist, g_LastScannedSymbol, g_LastScannedSignal, g_LastScannedScore
   );

   Comment(hud);
}

//+------------------------------------------------------------------+
//| Expert timer function                                            |
//+------------------------------------------------------------------+
void OnTimer()
{
   // 1. Process asynchronous outbox queue
   Telegram_ProcessQueue();

   // 2. Emergency Kill Switch check
   if(EmergencyKillSwitch)
   {
      CloseAllPositions(MagicNumber, SlippagePoints, "KILL_SWITCH_INPUT");
      UpdateChartHUD();
      return;
   }

   // 3. Critical Margin Level check (<150%)
   if(CheckCriticalMarginCall(150.0, MagicNumber))
   {
      UpdateChartHUD();
      return;
   }

   // 4. Peak Equity Drawdown circuit breaker check (default 10.0%)
   if(CheckPeakDrawdownLimit(MaxDrawdownPct, MagicNumber, true))
   {
      UpdateChartHUD();
      return;
   }

   // 5. Periodic Loss Limits (Daily 2%, Weekly 5%, Monthly 8%)
   if(CheckPeriodicLossLimits(MaxDailyLossPct, MaxWeeklyLossPct, MaxMonthlyLossPct, MagicNumber))
   {
      UpdateChartHUD();
      return;
   }

   // 6. Maximum Consecutive Losses check (3 losses -> 30m pause)
   if(CheckConsecutiveLossStreak(MaxConsecutiveLosses, ConsecutiveLossCooldownMin, MagicNumber))
   {
      UpdateChartHUD();
      return;
   }

   // 7. Friday afternoon cutoff check
   if(IsFridayCloseCutoff(FridayCutoffHourGMT, CloseTradesOnFriday, MagicNumber))
   {
      UpdateChartHUD();
      return;
   }

   // 8. High-Impact News filter check
   if(UseNewsFilter && IsNewsBlackoutActive())
   {
      UpdateChartHUD();
      return;
   }

   // 9. Active position lifecycle management (Break-Even, Trailing Stop, Partial Close)
   Executor_ManageOpenPositions(
      MagicNumber,
      UseBreakEven,
      BreakEvenTriggerPips,
      BreakEvenLockPips,
      UseTrailingStop,
      TrailingStartPips,
      TrailingStepPips,
      UsePartialClose,
      PartialCloseTriggerPips,
      PartialCloseRatio,
      SlippagePoints
   );

   // 10. Render real-time HUD
   UpdateChartHUD();

   // 11. Strict global open position limit check
   if(GetGlobalActivePositions(MagicNumber) >= MaxOpenPositions)
   {
      return; // Portfolio position limit reached
   }

   // 12. Staggered time-sliced round-robin batch scan
   ScanNextSymbolBatch(BatchSize);
}

//+------------------------------------------------------------------+
//| Expert tick function (passive monitoring)                        |
//+------------------------------------------------------------------+
void OnTick()
{
   // Multi-symbol surveillance delegated to OnTimer to avoid chart thread blocking
}
