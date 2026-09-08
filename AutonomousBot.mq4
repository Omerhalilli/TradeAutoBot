//+------------------------------------------------------------------+
//|                                                AutonomousBot.mq4 |
//|                     Autonomous Multi-Symbol Market Scanner & Bot |
//|                     Compatible with MQL4 and MetaEditor          |
//+------------------------------------------------------------------+
#property copyright "Antigravity Automated Systems"
#property link      "https://t.me"
#property version   "1.00"
#property strict

#include <SymbolManager.mqh>
#include <StrategyEngine.mqh>
#include <RiskController.mqh>
#include <TradeExecutor.mqh>
#include <TelegramShared.mqh>

//--- INPUT PARAMETERS
input string             Sec_Risk                      = "=== 1. RISK & POSITION LIMITS ===";
input int                MaxOpenPositions              = 1;                 // Strict Global Open Positions Limit across ALL symbols
input int                MaxExposurePerCurrency        = 1;                 // Maximum Open Positions per Currency (e.g. USD)
input double             RiskPercent                   = 1.0;               // Risk Percentage of Balance/Equity per Trade
input double             MaxDailyLossPct               = 3.0;               // Daily Loss Circuit Breaker (%)
input int                CooldownMinutes               = 60;                // Per-Symbol Trade Cooldown (Minutes)

input string             Sec_Scanner                   = "=== 2. SCANNER & SYMBOLS ===";
input string             IncludeSymbols                = "";                // Whitelist Symbols (empty = all Market Watch)
input string             ExcludeSymbols                = "*RUB*,*TRY*,*ZAR*"; // Blacklist Wildcards (Exotics/High-Swap)
input int                BatchSize                     = 3;                 // Round-Robin Time-Sliced Batch Size
input int                TimerIntervalSec              = 2;                 // Scanner Timer Interval (Seconds)
input double             MaxSpreadPoints               = 40.0;              // Maximum Allowed Spread (Points)
input int                MinConfluenceScore            = 6;                 // Minimum Score to Execute Autonomous Trade (0-10)
input ENUM_TIMEFRAMES    ScanTimeframe                 = PERIOD_H1;         // Confluence Scoring Timeframe

input string             Sec_System                    = "=== 3. SYSTEM & EXECUTION ===";
input int                MagicNumber                   = 998801;            // Autonomous Bot Magic Number
input string             TradeComment                  = "AutoBot_Pro";     // Order Comment Prefix
input int                SlippagePoints                = 15;                // Maximum Allowed Slippage Points

// Global Scanner State
string g_Watchlist[];
int    g_TotalWatchlist    = 0;
int    g_CurrentScanIndex  = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("[AUTONOMOUS BOT] Initializing Autonomous Multi-Symbol Bot...");
   
   // Discover Market Watch symbols dynamically
   g_TotalWatchlist = DiscoverMarketWatchSymbols(g_Watchlist, IncludeSymbols, ExcludeSymbols);
   PrintFormat("[AUTONOMOUS BOT] Watchlist initialized with %d active symbols from Market Watch.", g_TotalWatchlist);

   // Start timer for staggered round-robin scanner
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
   PrintFormat("[AUTONOMOUS BOT] Deinitialized. Reason code: %d", reason);
}

//+------------------------------------------------------------------+
//| Staggered Round-Robin Scanner Batch                              |
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

      // 2. Pre-filter dormant/disabled symbols before calculating expensive indicators
      if(!PreFilterSymbol(sym, MaxSpreadPoints, 50, ScanTimeframe))
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

      // 6. Quantitative Confluence Scoring (EMA, RSI, MACD, Stochastic, Price Action)
      StrategySignal sig = EvaluateSymbolOpportunity(sym, ScanTimeframe, MinConfluenceScore);
      if(!sig.valid || sig.cmd < 0)
      {
         continue;
      }

      // 7. Volatility-Adjusted Risk Sizing (ATR-based strict dollar risk)
      double lots = CalculateRiskLots(sym, RiskPercent, sig.slPips);
      if(lots <= 0.0) continue;

      PrintFormat("[AUTONOMOUS OPPORTUNITY] %s | Signal: %s | Score: %d/10 | Lots: %.2f",
                  sym, (sig.cmd == OP_BUY ? "BUY" : "SELL"), sig.score, lots);

      // 8. Safe Order Execution with ECN two-step, requote exponential backoff, and latency logging
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
//| Expert timer function                                            |
//+------------------------------------------------------------------+
void OnTimer()
{
   // Process asynchronous outbox queue
   Telegram_ProcessQueue();

   // 1. Daily loss circuit breaker check
   if(CheckDailyLossCircuitBreaker(MaxDailyLossPct, MagicNumber))
   {
      return; // Halted for the day
   }

   // 2. Strict global open position limit check
   if(GetGlobalActivePositions(MagicNumber) >= MaxOpenPositions)
   {
      return; // Position already open across portfolio
   }

   // 3. Staggered time-sliced round-robin batch scan
   ScanNextSymbolBatch(BatchSize);
}

//+------------------------------------------------------------------+
//| Expert tick function (passive monitoring)                        |
//+------------------------------------------------------------------+
void OnTick()
{
   // Tick-level execution is delegated to OnTimer to prevent multi-symbol blocking
}
