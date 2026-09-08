//+------------------------------------------------------------------+
//|                                               RiskController.mqh |
//|                     Institutional Real-Time Risk & Safeguards    |
//|                     Compatible with MQL4 and MetaEditor          |
//+------------------------------------------------------------------+
#property copyright "Antigravity Automated Systems"
#property strict

#ifndef __RISK_CONTROLLER_MQH__
#define __RISK_CONTROLLER_MQH__

#include <SymbolManager.mqh>

// Dynamic cooldown tracking storage in memory
string   g_DynamicCoolSyms[];
datetime g_DynamicCoolTimes[];
int      g_DynamicCoolCount = 0;

//+------------------------------------------------------------------+
//| Strict Global Active Positions Counter                           |
//| Counts active market orders (OP_BUY, OP_SELL).                   |
//| If magicFilter == -1, checks account-wide (including manual).   |
//+------------------------------------------------------------------+
int GetGlobalActivePositions(int magicFilter = -1)
{
   int count = 0;
   int total = OrdersTotal();
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      
      // Only count active market positions (exclude pending limit/stop orders)
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
      
      // If magicFilter is specified, only count our bot's orders; 
      // if magicFilter is -1, enforce strict global account-wide limit (including manual trades)
      if(magicFilter == -1 || OrderMagicNumber() == magicFilter)
      {
         count++;
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| Verify if global position ceiling is reached                     |
//+------------------------------------------------------------------+
bool IsGlobalPositionLimitReached(int maxPositions = 1, int magicFilter = -1)
{
   return (GetGlobalActivePositions(magicFilter) >= maxPositions);
}

//+------------------------------------------------------------------+
//| Currency Exposure & Correlation Clamping                         |
//| Prevents over-leveraging on a single currency (e.g. USD)         |
//+------------------------------------------------------------------+
bool CanOpenCurrencyExposure(string sym, int maxExposurePerCurrency = 1, int magicFilter = -1)
{
   string baseTarget = "", quoteTarget = "";
   GetSymbolCurrencies(sym, baseTarget, quoteTarget);
   if(baseTarget == "" || quoteTarget == "") return true;

   int baseCount = 0;
   int quoteCount = 0;
   int total = OrdersTotal();

   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
      if(magicFilter != -1 && OrderMagicNumber() != magicFilter) continue;

      string oBase = "", oQuote = "";
      GetSymbolCurrencies(OrderSymbol(), oBase, oQuote);

      if(oBase == baseTarget || oQuote == baseTarget)
         baseCount++;
      if(oBase == quoteTarget || oQuote == quoteTarget)
         quoteCount++;
   }

   if(baseCount >= maxExposurePerCurrency)
   {
      PrintFormat("[RISK CLAMP] Currency exposure ceiling reached for %s (%d >= %d)", baseTarget, baseCount, maxExposurePerCurrency);
      return false;
   }
   if(quoteCount >= maxExposurePerCurrency)
   {
      PrintFormat("[RISK CLAMP] Currency exposure ceiling reached for %s (%d >= %d)", quoteTarget, quoteCount, maxExposurePerCurrency);
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
//| Lot Sizing Normalization and Step Clamping                       |
//+------------------------------------------------------------------+
double NormalizeSymbolLots(string sym, double rawLots)
{
   double minLot  = MarketInfo(sym, MODE_MINLOT);
   double maxLot  = MarketInfo(sym, MODE_MAXLOT);
   double lotStep = MarketInfo(sym, MODE_LOTSTEP);
   if(lotStep <= 0.0) lotStep = 0.01;
   if(minLot <= 0.0)  minLot  = 0.01;
   if(maxLot <= 0.0)  maxLot  = 100.0;
   
   double lots = MathFloor((rawLots / lotStep) + 0.0000001) * lotStep;
   if(lots < minLot) lots = minLot;
   if(lots > maxLot) lots = maxLot;

   int stepDecimals = 2;
   if(lotStep >= 1.0) stepDecimals = 0;
   else if(lotStep >= 0.1) stepDecimals = 1;
   else if(lotStep >= 0.01) stepDecimals = 2;
   else stepDecimals = 3;

   return NormalizeDouble(lots, stepDecimals);
}

//+------------------------------------------------------------------+
//| Volatility-Adjusted Risk Sizing (Strict Dollar / Equity %)       |
//+------------------------------------------------------------------+
double CalculateRiskLots(string sym, double riskPercent, double slPips)
{
   if(slPips <= 0.0) slPips = 30.0;
   
   double equity = AccountEquity();
   if(equity <= 0.0) equity = AccountBalance();
   if(equity <= 0.0) equity = 100.0;

   double riskAmount = equity * (riskPercent / 100.0);
   double pipVal = GetSymbolPipValue(sym);
   if(pipVal <= 0.0) pipVal = 10.0;

   double lossPerLot = slPips * pipVal;
   if(lossPerLot <= 0.0) return NormalizeSymbolLots(sym, 0.01);

   double rawLots = riskAmount / lossPerLot;

   // Margin capacity verification (buffer 85% free margin)
   double marginReq = MarketInfo(sym, MODE_MARGINREQUIRED);
   if(marginReq > 0.0)
   {
      double maxAffordableLots = (AccountFreeMargin() * 0.85) / marginReq;
      double minLot = MarketInfo(sym, MODE_MINLOT);
      if(minLot <= 0.0) minLot = 0.01;
      
      if(maxAffordableLots < minLot)
      {
         PrintFormat("[RISK SIZING] Insufficient margin on %s: Max affordable %.4f < Min lot %.2f", sym, maxAffordableLots, minLot);
         return 0.0;
      }
      if(rawLots > maxAffordableLots && maxAffordableLots > 0.0)
      {
         rawLots = maxAffordableLots;
      }
   }

   return NormalizeSymbolLots(sym, rawLots);
}

//+------------------------------------------------------------------+
//| Daily Loss Circuit Breaker with Persistent State                 |
//| Halts scanning if daily drawdown exceeds maxDailyLossPct         |
//| Latches halted state until midnight server time                  |
//+------------------------------------------------------------------+
bool CheckDailyLossCircuitBreaker(double maxDailyLossPct = 3.0, int magicFilter = -1)
{
   datetime today = iTime(Symbol(), PERIOD_D1, 0);
   if(today <= 0)
   {
      datetime now = TimeCurrent();
      today = now - (now % 86400);
   }

   string gvDateKey    = "AT_CB_DATE";
   string gvPeakKey    = "AT_CB_PEAK";
   string gvStartEqKey = "AT_CB_STARTEQ";
   string gvTripKey    = "AT_CB_TRIPPED";

   // Check if new day started (midnight reset)
   if(!GlobalVariableCheck(gvDateKey) || (datetime)GlobalVariableGet(gvDateKey) != today)
   {
      GlobalVariableSet(gvDateKey, (double)today);
      GlobalVariableSet(gvPeakKey, AccountEquity());
      GlobalVariableSet(gvStartEqKey, AccountEquity());
      GlobalVariableSet(gvTripKey, 0.0);
   }

   // If already tripped today, halt all autonomous activity until midnight server time
   if(GlobalVariableCheck(gvTripKey) && GlobalVariableGet(gvTripKey) > 0.5)
   {
      return true;
   }

   // Update intraday peak equity
   double peakEquity = GlobalVariableGet(gvPeakKey);
   double currentEquity = AccountEquity();
   if(currentEquity > peakEquity)
   {
      peakEquity = currentEquity;
      GlobalVariableSet(gvPeakKey, peakEquity);
   }

   double startEquity = GlobalVariableGet(gvStartEqKey);
   if(startEquity <= 0.0) startEquity = AccountBalance();
   if(startEquity <= 0.0) startEquity = 100.0;

   // 1. Peak equity drawdown %
   double ddPct = (peakEquity > 0.0) ? (((peakEquity - currentEquity) / peakEquity) * 100.0) : 0.0;

   // 2. Closed loss + floating loss today
   double closedPLToday = 0.0;
   int histTotal = OrdersHistoryTotal();
   for(int h = 0; h < histTotal; h++)
   {
      if(!OrderSelect(h, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(magicFilter != -1 && OrderMagicNumber() != magicFilter) continue;
      if(OrderCloseTime() >= today)
      {
         closedPLToday += (OrderProfit() + OrderCommission() + OrderSwap());
      }
   }

   double floatingPL = 0.0;
   int openTotal = OrdersTotal();
   for(int o = 0; o < openTotal; o++)
   {
      if(!OrderSelect(o, SELECT_BY_POS, MODE_TRADES)) continue;
      if(magicFilter != -1 && OrderMagicNumber() != magicFilter) continue;
      floatingPL += (OrderProfit() + OrderCommission() + OrderSwap());
   }

   double totalDailyPL = closedPLToday + floatingPL;
   double dailyLossPct = (totalDailyPL < 0.0) ? ((MathAbs(totalDailyPL) / startEquity) * 100.0) : 0.0;

   if(ddPct >= maxDailyLossPct || dailyLossPct >= maxDailyLossPct)
   {
      GlobalVariableSet(gvTripKey, 1.0);
      PrintFormat("[CIRCUIT BREAKER HALT] Daily loss limit breached: dd=%.2f%%, netLoss=%.2f%% >= %.2f%% (Peak: $%.2f, Equity: $%.2f, DayPL: $%.2f). Halted until midnight.",
                  ddPct, dailyLossPct, maxDailyLossPct, peakEquity, currentEquity, totalDailyPL);
      return true; // Breached - HALTED until midnight!
   }

   return false;
}

//+------------------------------------------------------------------+
//| Cooldown Guard with MT4 GlobalVariables & Dynamic Memory Array   |
//+------------------------------------------------------------------+
bool IsSymbolInCooldown(string sym, int cooldownMinutes = 60)
{
   string canon = CleanSymbolBase(sym);
   string gvKey = "AT_CD_" + canon;
   datetime now = TimeCurrent();
   datetime cdSec = (datetime)(cooldownMinutes * 60);

   // 1. Check persistent MT4 GlobalVariable (survives restarts)
   if(GlobalVariableCheck(gvKey))
   {
      datetime lastTime = (datetime)GlobalVariableGet(gvKey);
      if(now - lastTime < cdSec && now >= lastTime)
      {
         return true;
      }
   }

   // 2. Check dynamic in-memory array
   for(int c = 0; c < g_DynamicCoolCount; c++)
   {
      if(g_DynamicCoolSyms[c] == canon)
      {
         if(now - g_DynamicCoolTimes[c] < cdSec && now >= g_DynamicCoolTimes[c])
         {
            return true;
         }
         break;
      }
   }

   return false;
}

//+------------------------------------------------------------------+
//| Record Cooldown into persistent storage & dynamic memory array   |
//+------------------------------------------------------------------+
void RecordSymbolCooldown(string sym)
{
   string canon = CleanSymbolBase(sym);
   string gvKey = "AT_CD_" + canon;
   datetime now = TimeCurrent();

   // 1. Set persistent MT4 GlobalVariable
   GlobalVariableSet(gvKey, (double)now);

   // 2. Update dynamic array (without buffer overflow)
   bool found = false;
   for(int c = 0; c < g_DynamicCoolCount; c++)
   {
      if(g_DynamicCoolSyms[c] == canon)
      {
         g_DynamicCoolTimes[c] = now;
         found = true;
         break;
      }
   }

   if(!found)
   {
      ArrayResize(g_DynamicCoolSyms, g_DynamicCoolCount + 1);
      ArrayResize(g_DynamicCoolTimes, g_DynamicCoolCount + 1);
      g_DynamicCoolSyms[g_DynamicCoolCount] = canon;
      g_DynamicCoolTimes[g_DynamicCoolCount] = now;
      g_DynamicCoolCount++;
   }
}

#endif // __RISK_CONTROLLER_MQH__
