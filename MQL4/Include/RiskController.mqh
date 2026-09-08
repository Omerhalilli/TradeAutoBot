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
#include <TelegramShared.mqh>

// Dynamic cooldown tracking storage in memory
string   g_DynamicCoolSyms[];
datetime g_DynamicCoolTimes[];
int      g_DynamicCoolCount = 0;

//+------------------------------------------------------------------+
//| Strict Global Active Positions Counter                           |
//| Counts active market orders (OP_BUY, OP_SELL).                   |
//| If magicFilter == -1, checks account-wide (including manual).    |
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
   if(rawLots <= 0.0) return 0.0;

   double minLot  = MarketInfo(sym, MODE_MINLOT);
   double maxLot  = MarketInfo(sym, MODE_MAXLOT);
   double lotStep = MarketInfo(sym, MODE_LOTSTEP);
   if(lotStep <= 0.0) lotStep = 0.01;
   if(minLot <= 0.0)  minLot  = 0.01;
   if(maxLot <= 0.0)  maxLot  = 100.0;
   
   double lots = MathFloor((rawLots / lotStep) + 0.0000001) * lotStep;
   if(lots < minLot)
   {
      double freeMargin = AccountFreeMargin();
      double balance = AccountBalance();
      double marginReq = GetSymbolMinLotMargin(sym);
      if(marginReq > freeMargin * 0.50 || marginReq > balance)
      {
         return 0.0;
      }
      lots = minLot;
   }
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
double CalculateRiskLots(string sym, double riskPercent, double slPips, double maxMarginUsagePct = 50.0)
{
   if(slPips <= 0.0) slPips = 30.0;
   if(riskPercent <= 0.0) riskPercent = 0.5;
   
   double equity = AccountEquity();
   if(equity <= 0.0) equity = AccountBalance();
   if(equity <= 0.0) equity = 100.0;

   double riskAmount = equity * (riskPercent / 100.0);
   double pipVal = GetSymbolPipValue(sym);
   if(pipVal <= 0.0) pipVal = 10.0;

   double lossPerLot = slPips * pipVal;
   if(lossPerLot <= 0.0) return 0.0;

   double rawLots = riskAmount / lossPerLot;

   // Margin capacity verification (buffer based on maxMarginUsagePct, default 50% free margin)
   double minLot = MarketInfo(sym, MODE_MINLOT);
   if(minLot <= 0.0) minLot = 0.01;

   double marginReq = GetSymbolMinLotMargin(sym);
   double freeMargin = AccountFreeMargin();
   double balance = AccountBalance();
   double maxAffordableMargin = freeMargin * (maxMarginUsagePct / 100.0);

   if(marginReq > maxAffordableMargin || marginReq > balance)
   {
      PrintFormat("[RISK SIZING] Insufficient margin on %s: Min lot margin $%.2f > Max affordable $%.2f", sym, marginReq, maxAffordableMargin);
      return 0.0;
   }

   double marginPerLot = (minLot > 0.0) ? (marginReq / minLot) : MarketInfo(sym, MODE_MARGINREQUIRED);
   if(marginPerLot > 0.0)
   {
      double maxAffordableLots = maxAffordableMargin / marginPerLot;
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
//| Emergency Close All Open & Pending Positions                     |
//+------------------------------------------------------------------+
int CloseAllPositions(int magicFilter = -1, int slippage = 15, string reason = "EMERGENCY")
{
   int closed = 0;
   int total = OrdersTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(magicFilter != -1 && OrderMagicNumber() != magicFilter) continue;

      int ticket = OrderTicket();
      int type   = OrderType();
      string sym = OrderSymbol();
      double lots = OrderLots();

      if(type == OP_BUY)
      {
         RefreshRates();
         double bid = MarketInfo(sym, MODE_BID);
         if(OrderClose(ticket, lots, bid, slippage, clrRed))
         {
            closed++;
            PrintFormat("[EMERGENCY CLOSE] Closed BUY #%d on %s (Lots: %.2f, Reason: %s)", ticket, sym, lots, reason);
         }
      }
      else if(type == OP_SELL)
      {
         RefreshRates();
         double ask = MarketInfo(sym, MODE_ASK);
         if(OrderClose(ticket, lots, ask, slippage, clrRed))
         {
            closed++;
            PrintFormat("[EMERGENCY CLOSE] Closed SELL #%d on %s (Lots: %.2f, Reason: %s)", ticket, sym, lots, reason);
         }
      }
      else if(type >= OP_BUYLIMIT && type <= OP_SELLSTOP)
      {
         if(OrderDelete(ticket))
         {
            closed++;
            PrintFormat("[EMERGENCY DELETE] Deleted Pending Order #%d on %s (Reason: %s)", ticket, sym, reason);
         }
      }
   }
   return closed;
}

//+------------------------------------------------------------------+
//| Get Account-Specific Global Variable Key                         |
//+------------------------------------------------------------------+
string GetAccountRiskGVKey(string prefix)
{
   return StringFormat("%s_%d", prefix, AccountNumber());
}

//+------------------------------------------------------------------+
//| Peak Equity Drawdown Limit (Global Account Protection)          |
//| Stops bot and liquidates all positions if drawdown >= limit      |
//| Trading halts until manually reset or equity recovers above safe |
//| threshold (e.g. <= 5.0% drawdown).                               |
//+------------------------------------------------------------------+
bool CheckPeakDrawdownLimit(double maxDrawdownPct = 10.0, int magicFilter = -1, bool autoLiquidate = true, double recoveryThresholdPct = 5.0)
{
   string gvPeakKey = GetAccountRiskGVKey("AT_PEAK_EQ");
   string gvHaltKey = GetAccountRiskGVKey("AT_DD_HALT");

   double currentEquity = AccountEquity();
   if(currentEquity <= 0.0) currentEquity = AccountBalance();

   // Initialize or update peak equity
   if(!GlobalVariableCheck(gvPeakKey) || GlobalVariableGet(gvPeakKey) <= 0.0)
   {
      GlobalVariableSet(gvPeakKey, currentEquity);
   }

   double peakEquity = GlobalVariableGet(gvPeakKey);
   if(currentEquity > peakEquity)
   {
      peakEquity = currentEquity;
      GlobalVariableSet(gvPeakKey, peakEquity);
   }
   GlobalVariableSet("AT_PEAK_EQUITY", peakEquity);

   double ddPct = (peakEquity > 0.0) ? (((peakEquity - currentEquity) / peakEquity) * 100.0) : 0.0;

   // Check if already tripped
   bool isHalted = (GlobalVariableCheck(gvHaltKey) && GlobalVariableGet(gvHaltKey) > 0.5) ||
                   (GlobalVariableCheck("AT_DD_HALTED") && GlobalVariableGet("AT_DD_HALTED") > 0.5);
   if(isHalted)
   {
      // Auto-recovery: resume trading if equity recovers above safe threshold
      if(ddPct <= recoveryThresholdPct)
      {
         GlobalVariableDel(gvHaltKey);
         GlobalVariableDel("AT_DD_HALTED");
         PrintFormat("[MAX DRAWDOWN CIRCUIT BREAKER] Equity recovered above safe threshold (DD: %.2f%% <= %.2f%%). Resuming trading.",
                     ddPct, recoveryThresholdPct);
         return false;
      }
      return true;
   }

   if(ddPct >= maxDrawdownPct)
   {
      GlobalVariableSet(gvHaltKey, 1.0);
      GlobalVariableSet("AT_DD_HALTED", 1.0);
      PrintFormat("[MAX DRAWDOWN CIRCUIT BREAKER] Peak drawdown limit breached: %.2f%% >= %.2f%% (Peak: $%.2f, Equity: $%.2f). Halting bot!",
                  ddPct, maxDrawdownPct, peakEquity, currentEquity);

      if(autoLiquidate)
      {
         int closed = CloseAllPositions(magicFilter, 15, "MAX_DRAWDOWN_BREACH");
         PrintFormat("[MAX DRAWDOWN CIRCUIT BREAKER] Liquidated %d positions across portfolio.", closed);
      }

      string alertMsg = StringFormat(
         "🚨 <b>CRITICAL RISK ALERT: MAXIMUM DRAWDOWN LIMIT BREACHED</b>\n" +
         "━━━━━━━━━━━━━━━━━━━━━━━━━━\n" +
         "• <b>Peak Equity:</b> $%.2f\n" +
         "• <b>Current Equity:</b> $%.2f\n" +
         "• <b>Drawdown:</b> <b>%.2f%%</b> (Limit: <b>%.2f%%</b>)\n" +
         "• <b>Action:</b> All open positions liquidated. Autonomous trading HALTED.\n" +
         "━━━━━━━━━━━━━━━━━━━━━━━━━━\n" +
         "<i>Use /reset_risk to reset safeguards or deposit funds to recover above safe threshold.</i>",
         peakEquity, currentEquity, ddPct, maxDrawdownPct
      );
      Telegram_WriteOutboxPayload(alertMsg, "", "");
      return true;
   }

   return false;
}

//+------------------------------------------------------------------+
//| Periodic Loss Limits (Daily, Weekly, Monthly)                    |
//+------------------------------------------------------------------+
bool CheckPeriodicLossLimits(double maxDailyLossPct = 2.0, double maxWeeklyLossPct = 5.0, double maxMonthlyLossPct = 8.0, int magicFilter = -1)
{
   datetime now = TimeCurrent();
   datetime today = iTime(Symbol(), PERIOD_D1, 0);
   if(today <= 0) today = now - (now % 86400);

   datetime weekStart = iTime(Symbol(), PERIOD_W1, 0);
   if(weekStart <= 0) weekStart = today - (TimeDayOfWeek(now) * 86400);

   datetime monthStart = iTime(Symbol(), PERIOD_MN1, 0);
   if(monthStart <= 0) monthStart = today;

   string gvDayDate    = GetAccountRiskGVKey("AT_CB_DATE_D");
   string gvDayPeak    = GetAccountRiskGVKey("AT_CB_PEAK_D");
   string gvDayStartEq = GetAccountRiskGVKey("AT_CB_STARTEQ_D");
   string gvDayTrip    = GetAccountRiskGVKey("AT_CB_TRIPPED_D");

   string gvWeekDate    = GetAccountRiskGVKey("AT_CB_DATE_W");
   string gvWeekStartEq = GetAccountRiskGVKey("AT_CB_STARTEQ_W");
   string gvWeekTrip    = GetAccountRiskGVKey("AT_CB_TRIPPED_W");

   string gvMonthDate    = GetAccountRiskGVKey("AT_CB_DATE_M");
   string gvMonthStartEq = GetAccountRiskGVKey("AT_CB_STARTEQ_M");
   string gvMonthTrip    = GetAccountRiskGVKey("AT_CB_TRIPPED_M");

   double currentEquity = AccountEquity();
   if(currentEquity <= 0.0) currentEquity = AccountBalance();

   // Reset day stats on new day
   if(!GlobalVariableCheck(gvDayDate) || (datetime)GlobalVariableGet(gvDayDate) != today)
   {
      GlobalVariableSet(gvDayDate, (double)today);
      GlobalVariableSet(gvDayPeak, currentEquity);
      GlobalVariableSet(gvDayStartEq, currentEquity);
      GlobalVariableSet(gvDayTrip, 0.0);
      GlobalVariableSet("AT_CB_TRIPPED_D", 0.0);
   }

   // Reset week stats on new week
   if(!GlobalVariableCheck(gvWeekDate) || (datetime)GlobalVariableGet(gvWeekDate) != weekStart)
   {
      GlobalVariableSet(gvWeekDate, (double)weekStart);
      GlobalVariableSet(gvWeekStartEq, currentEquity);
      GlobalVariableSet(gvWeekTrip, 0.0);
      GlobalVariableSet("AT_CB_TRIPPED_W", 0.0);
   }

   // Reset month stats on new month
   if(!GlobalVariableCheck(gvMonthDate) || (datetime)GlobalVariableGet(gvMonthDate) != monthStart)
   {
      GlobalVariableSet(gvMonthDate, (double)monthStart);
      GlobalVariableSet(gvMonthStartEq, currentEquity);
      GlobalVariableSet(gvMonthTrip, 0.0);
      GlobalVariableSet("AT_CB_TRIPPED_M", 0.0);
   }

   // Check if already tripped
   bool dayTripped = (GlobalVariableCheck(gvDayTrip) && GlobalVariableGet(gvDayTrip) > 0.5) ||
                     (GlobalVariableCheck("AT_CB_TRIPPED_D") && GlobalVariableGet("AT_CB_TRIPPED_D") > 0.5);
   bool weekTripped = (GlobalVariableCheck(gvWeekTrip) && GlobalVariableGet(gvWeekTrip) > 0.5) ||
                      (GlobalVariableCheck("AT_CB_TRIPPED_W") && GlobalVariableGet("AT_CB_TRIPPED_W") > 0.5);
   bool monthTripped = (GlobalVariableCheck(gvMonthTrip) && GlobalVariableGet(gvMonthTrip) > 0.5) ||
                       (GlobalVariableCheck("AT_CB_TRIPPED_M") && GlobalVariableGet("AT_CB_TRIPPED_M") > 0.5);
   if(dayTripped || weekTripped || monthTripped) return true;

   // Update intraday peak
   double dayPeak = GlobalVariableGet(gvDayPeak);
   if(currentEquity > dayPeak)
   {
      dayPeak = currentEquity;
      GlobalVariableSet(gvDayPeak, dayPeak);
   }

   double dayStartEq   = GlobalVariableGet(gvDayStartEq);
   double weekStartEq  = GlobalVariableGet(gvWeekStartEq);
   double monthStartEq = GlobalVariableGet(gvMonthStartEq);
   if(dayStartEq <= 0.0)   dayStartEq   = currentEquity;
   if(weekStartEq <= 0.0)  weekStartEq  = currentEquity;
   if(monthStartEq <= 0.0) monthStartEq = currentEquity;

   // Calculate closed P/L
   double closedPLDay   = 0.0;
   double closedPLWeek  = 0.0;
   double closedPLMonth = 0.0;
   int histTotal = OrdersHistoryTotal();
   for(int h = 0; h < histTotal; h++)
   {
      if(!OrderSelect(h, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(magicFilter != -1 && OrderMagicNumber() != magicFilter) continue;
      datetime closeTime = OrderCloseTime();
      double pnl = OrderProfit() + OrderCommission() + OrderSwap();
      if(closeTime >= today)      closedPLDay   += pnl;
      if(closeTime >= weekStart)  closedPLWeek  += pnl;
      if(closeTime >= monthStart) closedPLMonth += pnl;
   }

   // Calculate floating P/L
   double floatingPL = 0.0;
   int openTotal = OrdersTotal();
   for(int o = 0; o < openTotal; o++)
   {
      if(!OrderSelect(o, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
      if(magicFilter != -1 && OrderMagicNumber() != magicFilter) continue;
      floatingPL += (OrderProfit() + OrderCommission() + OrderSwap());
   }

   double totalDayPL   = closedPLDay + floatingPL;
   double totalWeekPL  = closedPLWeek + floatingPL;
   double totalMonthPL = closedPLMonth + floatingPL;

   double dayLossPct   = (totalDayPL < 0.0)   ? ((MathAbs(totalDayPL) / dayStartEq) * 100.0) : 0.0;
   double weekLossPct  = (totalWeekPL < 0.0)  ? ((MathAbs(totalWeekPL) / weekStartEq) * 100.0) : 0.0;
   double monthLossPct = (totalMonthPL < 0.0) ? ((MathAbs(totalMonthPL) / monthStartEq) * 100.0) : 0.0;

   double dayPeakDDPct = (dayPeak > 0.0) ? (((dayPeak - currentEquity) / dayPeak) * 100.0) : 0.0;

   // 1. Daily breach
   if(dayLossPct >= maxDailyLossPct || dayPeakDDPct >= maxDailyLossPct)
   {
      GlobalVariableSet(gvDayTrip, 1.0);
      GlobalVariableSet("AT_CB_TRIPPED_D", 1.0);
      PrintFormat("[CIRCUIT BREAKER HALT] Daily loss limit breached: dd=%.2f%%, netLoss=%.2f%% >= %.2f%%. Halted until midnight.",
                  dayPeakDDPct, dayLossPct, maxDailyLossPct);
      string alertMsg = StringFormat(
         "🚨 <b>DAILY LOSS LIMIT BREACHED</b>\n" +
         "━━━━━━━━━━━━━━━━━━━━━━━━━━\n" +
         "• <b>Loss:</b> <b>%.2f%%</b> (Limit: <b>%.2f%%</b>)\n" +
         "• <b>Net P/L:</b> $%.2f | <b>Peak DD:</b> %.2f%%\n" +
         "• <b>Action:</b> Trading paused until tomorrow 00:00.\n" +
         "━━━━━━━━━━━━━━━━━━━━━━━━━━",
         dayLossPct, maxDailyLossPct, totalDayPL, dayPeakDDPct
      );
      Telegram_WriteOutboxPayload(alertMsg, "", "");
      return true;
   }

   // 2. Weekly breach
   if(weekLossPct >= maxWeeklyLossPct)
   {
      GlobalVariableSet(gvWeekTrip, 1.0);
      GlobalVariableSet("AT_CB_TRIPPED_W", 1.0);
      PrintFormat("[CIRCUIT BREAKER HALT] Weekly loss limit breached: %.2f%% >= %.2f%%. Halted until next week.",
                  weekLossPct, maxWeeklyLossPct);
      string alertMsg = StringFormat(
         "🚨 <b>WEEKLY LOSS LIMIT BREACHED</b>\n" +
         "━━━━━━━━━━━━━━━━━━━━━━━━━━\n" +
         "• <b>Weekly Loss:</b> <b>%.2f%%</b> (Limit: <b>%.2f%%</b>)\n" +
         "• <b>Action:</b> Trading paused for remainder of the week.\n" +
         "━━━━━━━━━━━━━━━━━━━━━━━━━━",
         weekLossPct, maxWeeklyLossPct
      );
      Telegram_WriteOutboxPayload(alertMsg, "", "");
      return true;
   }

   // 3. Monthly breach
   if(monthLossPct >= maxMonthlyLossPct)
   {
      GlobalVariableSet(gvMonthTrip, 1.0);
      GlobalVariableSet("AT_CB_TRIPPED_M", 1.0);
      PrintFormat("[CIRCUIT BREAKER HALT] Monthly loss limit breached: %.2f%% >= %.2f%%. Halted until next month.",
                  monthLossPct, maxMonthlyLossPct);
      string alertMsg = StringFormat(
         "🚨 <b>MONTHLY LOSS LIMIT BREACHED</b>\n" +
         "━━━━━━━━━━━━━━━━━━━━━━━━━━\n" +
         "• <b>Monthly Loss:</b> <b>%.2f%%</b> (Limit: <b>%.2f%%</b>)\n" +
         "• <b>Action:</b> Trading paused for remainder of the month.\n" +
         "━━━━━━━━━━━━━━━━━━━━━━━━━━",
         monthLossPct, maxMonthlyLossPct
      );
      Telegram_WriteOutboxPayload(alertMsg, "", "");
      return true;
   }

   return false;
}

// Backward compatibility wrapper
bool CheckDailyLossCircuitBreaker(double maxDailyLossPct = 2.0, int magicFilter = -1)
{
   return CheckPeriodicLossLimits(maxDailyLossPct, 5.0, 8.0, magicFilter);
}

//+------------------------------------------------------------------+
//| Maximum Consecutive Losses with Pause Period                     |
//+------------------------------------------------------------------+
bool CheckConsecutiveLossStreak(int maxConsecutiveLosses = 3, int pauseMinutes = 30, int magicFilter = -1)
{
   string gvPauseKey    = GetAccountRiskGVKey("AT_CONSEC_PAUSE");
   string gvLastTimeKey = GetAccountRiskGVKey("AT_CONSEC_LAST_TIME");
   datetime now = TimeCurrent();

   // 1. Check if pause is currently active
   if(GlobalVariableCheck(gvPauseKey))
   {
      datetime pauseUntil = (datetime)GlobalVariableGet(gvPauseKey);
      if(now < pauseUntil)
      {
         return true; // Cooldown active
      }
      else
      {
         GlobalVariableDel(gvPauseKey); // Cooldown expired
         GlobalVariableDel("AT_CONSEC_PAUSE_UNTIL");
      }
   }
   else if(GlobalVariableCheck("AT_CONSEC_PAUSE_UNTIL"))
   {
      datetime legacyUntil = (datetime)GlobalVariableGet("AT_CONSEC_PAUSE_UNTIL");
      if(now < legacyUntil)
      {
         return true;
      }
      else
      {
         GlobalVariableDel("AT_CONSEC_PAUSE_UNTIL");
      }
   }

   datetime lastPenalizedTime = 0;
   if(GlobalVariableCheck(gvLastTimeKey))
   {
      lastPenalizedTime = (datetime)GlobalVariableGet(gvLastTimeKey);
   }

   // 2. Scan trade history backwards to count consecutive losses closed AFTER last penalized pause
   int streak = 0;
   int histTotal = OrdersHistoryTotal();
   for(int i = histTotal - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(magicFilter != -1 && OrderMagicNumber() != magicFilter) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;

      datetime closeTime = OrderCloseTime();
      if(closeTime <= lastPenalizedTime)
      {
         // Stop scanning: this trade was already part of an earlier penalized streak or occurred before last pause
         break;
      }

      double netProfit = OrderProfit() + OrderCommission() + OrderSwap();
      if(netProfit < 0.0)
      {
         streak++;
         if(streak >= maxConsecutiveLosses)
         {
            datetime pauseUntilTime = now + (datetime)(pauseMinutes * 60);
            GlobalVariableSet(gvPauseKey, (double)pauseUntilTime);
            GlobalVariableSet("AT_CONSEC_PAUSE_UNTIL", (double)pauseUntilTime);
            GlobalVariableSet(gvLastTimeKey, (double)now);
            PrintFormat("[CONSECUTIVE LOSS PAUSE] %d consecutive losses detected. Trading paused for %d minutes.",
                        streak, pauseMinutes);
            string alertMsg = StringFormat(
               "⚠️ <b>CONSECUTIVE LOSS COOLDOWN TRIGGERED</b>\n" +
               "━━━━━━━━━━━━━━━━━━━━━━━━━━\n" +
               "• <b>Loss Streak:</b> <b>%d consecutive losing trades</b>\n" +
               "• <b>Action:</b> Trading paused for <b>%d minutes</b>\n" +
               "• <b>Resume Time:</b> %s\n" +
               "━━━━━━━━━━━━━━━━━━━━━━━━━━",
               streak, pauseMinutes, TimeToStr(pauseUntilTime, TIME_DATE|TIME_MINUTES)
            );
            Telegram_WriteOutboxPayload(alertMsg, "", "");
            return true;
         }
      }
      else if(netProfit > 0.0)
      {
         break; // Streak broken by win
      }
   }

   return false;
}

//+------------------------------------------------------------------+
//| Verify Margin Usage Capacity                                     |
//+------------------------------------------------------------------+
bool CheckMarginUsageAllowed(string sym, double lots, double maxMarginUsagePct = 50.0)
{
   double equity = AccountEquity();
   if(equity <= 0.0) equity = AccountBalance();
   if(equity <= 0.0) return false;

   double marginReqPerLot = MarketInfo(sym, MODE_MARGINREQUIRED);
   if(marginReqPerLot <= 0.0) marginReqPerLot = 1000.0;

   double tradeMargin = lots * marginReqPerLot;
   double currentMargin = AccountMargin();
   double totalProjectedMargin = currentMargin + tradeMargin;

   double maxAllowedMargin = equity * (maxMarginUsagePct / 100.0);
   if(totalProjectedMargin > maxAllowedMargin)
   {
      PrintFormat("[MARGIN SAFETY VETO] Trade on %s (%.2f lots, req $%.2f) exceeds margin limit: Projected $%.2f > Max allowed $%.2f (%.1f%% of equity $%.2f)",
                  sym, lots, tradeMargin, totalProjectedMargin, maxAllowedMargin, maxMarginUsagePct, equity);
      return false;
   }

   double freeMargin = AccountFreeMargin();
   if(tradeMargin > freeMargin * (maxMarginUsagePct / 100.0))
   {
      PrintFormat("[MARGIN SAFETY VETO] Trade margin $%.2f exceeds %.1f%% of free margin $%.2f",
                  tradeMargin, maxMarginUsagePct, freeMargin);
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
//| Global Portfolio Risk Budget Check                               |
//| Enforces sum(open risks) <= maxGlobalRiskPct                     |
//+------------------------------------------------------------------+
bool CheckGlobalPortfolioRisk(double newTradeRiskPct, double maxGlobalRiskPct = 2.0, int magicFilter = -1)
{
   double equity = AccountEquity();
   if(equity <= 0.0) equity = AccountBalance();
   if(equity <= 0.0) return false;

   double totalOpenRiskCurrency = 0.0;
   int total = OrdersTotal();
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
      if(magicFilter != -1 && OrderMagicNumber() != magicFilter) continue;

      string sym = OrderSymbol();
      double openPrice = OrderOpenPrice();
      double sl = OrderStopLoss();
      double pipPt = GetSymbolPipSize(sym);
      double pipVal = GetSymbolPipValue(sym);

      double slPips = 30.0;
      if(sl > 0.0 && pipPt > 0.0)
      {
         slPips = MathAbs(openPrice - sl) / pipPt;
      }
      double tradeRisk = slPips * pipVal * OrderLots();
      totalOpenRiskCurrency += tradeRisk;
   }

   double currentRiskPct = (totalOpenRiskCurrency / equity) * 100.0;
   if(currentRiskPct + newTradeRiskPct > maxGlobalRiskPct)
   {
      PrintFormat("[GLOBAL RISK LIMIT EXCEEDED] Current risk: %.2f%% + New trade: %.2f%% = %.2f%% > Limit: %.2f%%",
                  currentRiskPct, newTradeRiskPct, currentRiskPct + newTradeRiskPct, maxGlobalRiskPct);
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
//| Critical Margin Level Safety Check                               |
//+------------------------------------------------------------------+
bool CheckCriticalMarginCall(double criticalMarginLevelPct = 150.0, int magicFilter = -1)
{
   if(AccountMargin() > 0.0)
   {
      double marginLevel = (AccountEquity() / AccountMargin()) * 100.0;
      if(marginLevel < criticalMarginLevelPct)
      {
         PrintFormat("[CRITICAL MARGIN CALL] Margin level %.1f%% is below safety threshold %.1f%%. Emergency liquidation!",
                     marginLevel, criticalMarginLevelPct);
         CloseAllPositions(magicFilter, 15, "CRITICAL_MARGIN_CALL");
         string alertMsg = StringFormat(
            "🚨 <b>CRITICAL MARGIN CALL - POSITIONS LIQUIDATED</b>\n" +
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n" +
            "• <b>Margin Level:</b> <b>%.1f%%</b> (Critical Floor: <b>%.1f%%</b>)\n" +
            "• <b>Action:</b> Emergency close executed to protect account capital.",
            marginLevel, criticalMarginLevelPct
         );
         Telegram_WriteOutboxPayload(alertMsg, "", "");
         return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| News Event Filter Check                                          |
//+------------------------------------------------------------------+
bool IsNewsBlackoutActive(int leadMinutes = 30, int lagMinutes = 30)
{
   if(GlobalVariableCheck("AT_NEWS_BLOCKED"))
   {
      if(GlobalVariableGet("AT_NEWS_BLOCKED") > 0.5) return true;
   }
   string accGv = GetAccountRiskGVKey("AT_NEWS_BLOCKED");
   if(GlobalVariableCheck(accGv))
   {
      if(GlobalVariableGet(accGv) > 0.5) return true;
   }
   if(FileIsExist("news_blocked.flag"))
   {
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Friday Close / Weekend Cutoff Filter                             |
//+------------------------------------------------------------------+
bool IsFridayCloseCutoff(int cutoffHourGMT = 18, bool closeAllOnCutoff = false, int magicFilter = -1)
{
   datetime now = TimeGMT();
   if(now <= 0) now = TimeCurrent();
   int dayOfWeek = TimeDayOfWeek(now);
   int hour = TimeHour(now);

   if(dayOfWeek == 5 && hour >= cutoffHourGMT)
   {
      if(closeAllOnCutoff && GetGlobalActivePositions(magicFilter) > 0)
      {
         PrintFormat("[WEEKEND CLOSE] Friday cutoff reached (%02d:00 GMT). Closing all active trades.", cutoffHourGMT);
         CloseAllPositions(magicFilter, 15, "FRIDAY_WEEKEND_CLOSE");
      }
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Reset Risk Safeguards (Admin Override)                           |
//+------------------------------------------------------------------+
void ResetRiskSafeguards()
{
   GlobalVariableDel("AT_DD_HALTED");
   GlobalVariableDel("AT_CB_TRIPPED_D");
   GlobalVariableDel("AT_CB_TRIPPED_W");
   GlobalVariableDel("AT_CB_TRIPPED_M");
   GlobalVariableDel("AT_CONSEC_PAUSE_UNTIL");
   GlobalVariableSet("AT_PEAK_EQUITY", AccountEquity());

   // Account-specific keys
   GlobalVariableDel(GetAccountRiskGVKey("AT_DD_HALT"));
   GlobalVariableDel(GetAccountRiskGVKey("AT_CB_TRIPPED_D"));
   GlobalVariableDel(GetAccountRiskGVKey("AT_CB_TRIPPED_W"));
   GlobalVariableDel(GetAccountRiskGVKey("AT_CB_TRIPPED_M"));
   GlobalVariableDel(GetAccountRiskGVKey("AT_CONSEC_PAUSE"));
   GlobalVariableDel(GetAccountRiskGVKey("AT_CONSEC_LAST_TIME"));
   GlobalVariableSet(GetAccountRiskGVKey("AT_PEAK_EQ"), AccountEquity());

   PrintFormat("[RISK SAFEGUARDS RESET] Account #%d safeguards reset. Calibrated peak equity to $%.2f", AccountNumber(), AccountEquity());
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
