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
input int                BatchSize                     = 0;                 // Scanner Batch Size (0 = Full Watchlist Scan Every Cycle)
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
uint   g_LastAutonomousBotTick = 0;

// Multi-Symbol New Bar Tracker (guarantees trade execution only on closed confirmed bars)
struct SymbolBarTracker {
   string sym;
   ENUM_TIMEFRAMES tf;
   datetime lastBarTime;
};

#define MAX_BAR_TRACKERS 512
SymbolBarTracker g_BarTrackers[MAX_BAR_TRACKERS];
int g_BarTrackersCount = 0;

bool IsNewBar(const string sym, const ENUM_TIMEFRAMES tf)
{
   datetime currentBarTime = iTime(sym, tf, 0);
   if(currentBarTime <= 0) return false;
   
   for(int i = 0; i < g_BarTrackersCount; i++)
   {
      if(g_BarTrackers[i].sym == sym && g_BarTrackers[i].tf == tf)
      {
         if(currentBarTime > g_BarTrackers[i].lastBarTime)
         {
            g_BarTrackers[i].lastBarTime = currentBarTime;
            return true;
         }
         return false; // Still inside current forming bar
      }
   }
   
   // First time encountering this symbol/tf: register current bar time and return false.
   // Guarantees we NEVER execute trades immediately on startup or on an unconfirmed half-bar!
   if(g_BarTrackersCount < MAX_BAR_TRACKERS)
   {
      g_BarTrackers[g_BarTrackersCount].sym = sym;
      g_BarTrackers[g_BarTrackersCount].tf = tf;
      g_BarTrackers[g_BarTrackersCount].lastBarTime = currentBarTime;
      g_BarTrackersCount++;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("[AUTONOMOUS BOT] Initializing Ultra-Safe Multi-Symbol Autonomous Bot v2.00...");

   if(MinConfluenceScore < 6 || MinConfluenceScore > 10)
   {
      Print("[INIT ERROR] MinConfluenceScore must be between 6 and 10 (score < 6 is strictly prohibited). Current: ", MinConfluenceScore);
      return(INIT_FAILED);
   }

   if(EmergencyKillSwitch)
   {
      Print("[AUTONOMOUS BOT] ⚠️ EMERGENCY KILL SWITCH IS ACTIVE. Auto-trading disabled.");
   }

   g_BarTrackersCount = 0;
   g_LastAutonomousBotTick = GetTickCount(); // Enforce startup stabilization delay

   // 1. Audit open orders and attach mandatory stops to any unprotected positions
   AuditAndEnforceOpenOrderStops(MagicNumber);

   // 2. Discover Market Watch symbols dynamically
   g_TotalWatchlist = DiscoverMarketWatchSymbols(g_Watchlist, IncludeSymbols, ExcludeSymbols);
   PrintFormat("[AUTONOMOUS BOT] Watchlist initialized with %d active symbols from Market Watch.", g_TotalWatchlist);

   // Seed all watchlist symbols into tracker so no symbol can execute on startup half-bar
   for(int wIdx = 0; wIdx < g_TotalWatchlist; wIdx++)
   {
      SymbolSelect(g_Watchlist[wIdx], true);
      IsNewBar(g_Watchlist[wIdx], ScanTimeframe);
   }

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
void ScanNextSymbolBatch(int batchSize = 0)
{
   if(g_TotalWatchlist <= 0)
   {
      g_TotalWatchlist = DiscoverMarketWatchSymbols(g_Watchlist, IncludeSymbols, ExcludeSymbols);
      if(g_TotalWatchlist <= 0) return;
   }

   // 1. Strict global position check: abort if maximum positions already open
   if(GetGlobalActivePositions(MagicNumber) >= MaxOpenPositions)
   {
      return;
   }

   uint nowTick = GetTickCount();
   if(g_LastAutonomousBotTick == 0)
   {
      g_LastAutonomousBotTick = nowTick;
      return; // Initial startup stabilization delay: never trade immediately on startup
   }
   if(nowTick - g_LastAutonomousBotTick < (uint)(TimerIntervalSec * 1000)) return;
   g_LastAutonomousBotTick = nowTick;

   int scanCount = (batchSize > 0) ? MathMin(batchSize, g_TotalWatchlist) : g_TotalWatchlist;
   if(batchSize <= 0) g_CurrentScanIndex = 0;

   StrategySignal bestSig;
   bestSig.valid = false;
   bestSig.cmd   = -1;
   bestSig.score = 0;
   double bestRankScore = -1.0;
   string bestSymbol    = "";
   double bestLots      = 0.0;
   int qualifiedCount   = 0;

   // 2. Scan every symbol one by one across the watchlist
   for(int i = 0; i < scanCount; i++)
   {
      string sym = g_Watchlist[g_CurrentScanIndex];
      g_CurrentScanIndex = (g_CurrentScanIndex + 1) % g_TotalWatchlist;
      g_LastScannedSymbol = sym;

      SymbolSelect(sym, true);

      // Bar confirmation: each symbol must be evaluated only on a confirmed new closed bar
      if(!IsNewBar(sym, ScanTimeframe))
      {
         continue;
      }

      // Pre-filter dormant/disabled symbols before computing indicators
      if(!PreFilterSymbol(sym, MaxSpreadPoints, 205, ScanTimeframe, UseTimeFilter, MaxMarginUsagePct))
      {
         continue;
      }

      // Check persistent per-symbol cooldown
      if(IsSymbolInCooldown(sym, CooldownMinutes))
      {
         continue;
      }

      // Exact canonical symbol matching: verify no existing open position on this pair
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

      // Currency exposure clamping (limit exposure per currency, e.g. USD)
      if(!CanOpenCurrencyExposure(sym, MaxExposurePerCurrency, MagicNumber))
      {
         continue;
      }

      // Quantitative Confluence Scoring (0-100 analysis scale, score 0-10)
      int effectiveMinScore = MathMax(6, MinConfluenceScore);
      StrategySignal sig = EvaluateSymbolOpportunity(sym, ScanTimeframe, effectiveMinScore, MinRewardToRisk, MinATRPips, MaxATRPips);
      g_LastScannedScore  = sig.score;
      g_LastScannedSignal = (sig.cmd == OP_BUY ? "BUY" : (sig.cmd == OP_SELL ? "SELL" : "HOLD"));

      // Confluence threshold: must stand on 6 or past 6 (Score >= 6; score < 6 strictly prohibited)
      if(!sig.valid || sig.cmd < 0 || sig.score < effectiveMinScore || sig.score < 6)
      {
         continue;
      }

      // Volatility-Adjusted Risk Sizing (0.5% risk limit)
      double lots = CalculateRiskLots(sym, MaxRiskPerTradePct, sig.slPips, MaxMarginUsagePct);
      if(lots <= 0.0) continue;

      // Margin utilization check (max 50% margin)
      if(!CheckMarginUsageAllowed(sym, lots, MaxMarginUsagePct))
      {
         continue;
      }

      // Global portfolio risk check
      if(!CheckGlobalPortfolioRisk(MaxRiskPerTradePct, MaxGlobalRiskPct, MagicNumber))
      {
         continue;
      }

      qualifiedCount++;

      // Composite ranking: prioritize higher analysis score (0-100), superior RR, lower spread
      double rankScore = (sig.analysisScore * 100.0) + (sig.rrRatio * 50.0) - (sig.spreadPoints * 2.0);
      if(rankScore > bestRankScore)
      {
         bestRankScore = rankScore;
         bestSig       = sig;
         bestSymbol    = sym;
         bestLots      = lots;
      }
   }

   // 3. Post-scan decision: If one or more qualified opportunities found, execute the best one!
   int finalEffectiveMinScore = MathMax(6, MinConfluenceScore);
   if(bestRankScore > 0.0 && bestSig.valid && bestSig.cmd >= 0 && bestSig.score >= 6 && bestSig.score >= finalEffectiveMinScore && bestSymbol != "")
   {
      PrintFormat("[AUTONOMOUS PORTFOLIO SELECTION] Scanned %d symbols (%d qualified >= %d). Selected BEST: %s | %s | Score: %d/10 (%.1f/100) | Lots: %.2f | RR: %.2f",
                  scanCount, qualifiedCount, MinConfluenceScore, bestSymbol,
                  (bestSig.cmd == OP_BUY ? "BUY" : "SELL"), bestSig.score, bestSig.analysisScore, bestLots, bestSig.rrRatio);

      int ticket = ExecuteOrderSafe(bestSymbol, bestSig.cmd, bestLots, bestSig.slPrice, bestSig.tpPrice, MagicNumber, TradeComment, SlippagePoints, MaxOpenPositions);
      if(ticket > 0)
      {
         RecordSymbolCooldown(bestSymbol);
         PrintFormat("[AUTONOMOUS BOT] Successfully filled %s on %s (Lots: %.2f, Score: %d/10, Ticket: #%d)",
                     (bestSig.cmd == OP_BUY ? "BUY" : "SELL"), bestSymbol, bestLots, bestSig.score, ticket);
      }
      else
      {
         PrintFormat("[AUTONOMOUS BOT] Order execution failed on %s. Cooldown activated.", bestSymbol);
         RecordSymbolCooldown(bestSymbol);
      }
   }
   else
   {
      // No symbol reached confluence score >= 6 or passed filters; wait cleanly for next cycle
      PrintFormat("[AUTONOMOUS SCAN CYCLE COMPLETE] Scanned %d symbols. No actionable setup meeting confluence threshold (Score >= %d/10). Capital safely preserved.",
                  scanCount, MinConfluenceScore);
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

   string gvPeak = GetAccountRiskGVKey("AT_PEAK_EQ");
   double peakEq = GlobalVariableCheck(gvPeak) ? GlobalVariableGet(gvPeak) : (GlobalVariableCheck("AT_PEAK_EQUITY") ? GlobalVariableGet("AT_PEAK_EQUITY") : equity);
   double peakDD = (peakEq > 0.0) ? (((peakEq - equity) / peakEq) * 100.0) : 0.0;

   string gvDayP = GetAccountRiskGVKey("AT_CB_PEAK_D");
   double dayPeak = GlobalVariableCheck(gvDayP) ? GlobalVariableGet(gvDayP) : (GlobalVariableCheck("AT_CB_PEAK_D") ? GlobalVariableGet("AT_CB_PEAK_D") : equity);
   double dayDD   = (dayPeak > 0.0) ? (((dayPeak - equity) / dayPeak) * 100.0) : 0.0;

   string gvDayStart = GetAccountRiskGVKey("AT_CB_STARTEQ_D");
   double dayStartEq = GlobalVariableCheck(gvDayStart) ? GlobalVariableGet(gvDayStart) : (GlobalVariableCheck("AT_CB_STARTEQ_D") ? GlobalVariableGet("AT_CB_STARTEQ_D") : equity);
   if(dayStartEq <= 0.0) dayStartEq = equity;

   // Remaining Daily Loss Allowance calculation
   double maxDailyDollar = dayStartEq * (MaxDailyLossPct / 100.0);
   double currentDailyLossDollar = MathMax(0.0, dayPeak - equity);
   double remainingDailyLossDollar = MathMax(0.0, maxDailyDollar - currentDailyLossDollar);
   double remainingDailyLossPct = (dayStartEq > 0.0) ? ((remainingDailyLossDollar / dayStartEq) * 100.0) : 0.0;

   // Total Portfolio Exposure calculation
   double totalRiskExposure = 0.0;
   int totOrders = OrdersTotal();
   for(int o = 0; o < totOrders; o++)
   {
      if(!OrderSelect(o, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
      if(MagicNumber != -1 && OrderMagicNumber() != MagicNumber) continue;

      string oSym = OrderSymbol();
      double oOpen = OrderOpenPrice();
      double oSL = OrderStopLoss();
      double oPipPt = GetSymbolPipSize(oSym);
      double oPipVal = GetSymbolPipValue(oSym);
      double oSLPips = (oSL > 0.0 && oPipPt > 0.0) ? (MathAbs(oOpen - oSL) / oPipPt) : 30.0;
      totalRiskExposure += (oSLPips * oPipVal * OrderLots());
   }
   double totalExposurePct = (equity > 0.0) ? ((totalRiskExposure / equity) * 100.0) : 0.0;

   int activePos = GetGlobalActivePositions(MagicNumber);
   bool isDDHalted = (GlobalVariableCheck(GetAccountRiskGVKey("AT_DD_HALT")) && GlobalVariableGet(GetAccountRiskGVKey("AT_DD_HALT")) > 0.5) ||
                     (GlobalVariableCheck("AT_DD_HALTED") && GlobalVariableGet("AT_DD_HALTED") > 0.5);
   bool isDayHalted = (GlobalVariableCheck(GetAccountRiskGVKey("AT_CB_TRIPPED_D")) && GlobalVariableGet(GetAccountRiskGVKey("AT_CB_TRIPPED_D")) > 0.5) ||
                      (GlobalVariableCheck("AT_CB_TRIPPED_D") && GlobalVariableGet("AT_CB_TRIPPED_D") > 0.5);
   bool isPaused = (GlobalVariableCheck(GetAccountRiskGVKey("AT_CONSEC_PAUSE")) && (TimeCurrent() < (datetime)GlobalVariableGet(GetAccountRiskGVKey("AT_CONSEC_PAUSE")))) ||
                   (GlobalVariableCheck("AT_CONSEC_PAUSE_UNTIL") && (TimeCurrent() < (datetime)GlobalVariableGet("AT_CONSEC_PAUSE_UNTIL")));

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
      "Remaining Daily Allowance: $%.2f (%.2f%%)\n" +
      "Total Risk Exposure: $%.2f (%.2f%% / Limit: %.1f%%)\n" +
      "-----------------------------------------------\n" +
      "Open Positions: %d / %d (Max)\n" +
      "Max Risk Per Trade: %.1f%% | Max Global Risk: %.1f%%\n" +
      "Min Score: %d/10 | Min RR: 1:%.1f | Max Spread: %.0f pts\n" +
      "Monitored Symbols: %d active\n" +
      "Last Scanned: %s (Signal: %s, Score: %d/10)\n" +
      "===============================================",
      statusStr, balance, equity, freeMargin, marginLevel,
      peakEq, peakDD, MaxDrawdownPct, dayDD, MaxDailyLossPct,
      remainingDailyLossDollar, remainingDailyLossPct,
      totalRiskExposure, totalExposurePct, MaxGlobalRiskPct,
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
