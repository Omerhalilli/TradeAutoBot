//+------------------------------------------------------------------+
//|                                                TradeExecutor.mqh |
//|                     Safe Order Execution, ECN & Requote Handlers |
//|                     Compatible with MQL4 and MetaEditor          |
//+------------------------------------------------------------------+
#property copyright "Antigravity Automated Systems"
#property strict

#ifndef __TRADE_EXECUTOR_MQH__
#define __TRADE_EXECUTOR_MQH__

#include <SymbolManager.mqh>
#include <TelegramShared.mqh>

//+------------------------------------------------------------------+
//| Broker StopLevel & FreezeLevel Clamp                             |
//+------------------------------------------------------------------+
bool ClampStopLevels(const string sym, const int cmd, const double openPrice, double &sl, double &tp)
{
   double pt = MarketInfo(sym, MODE_POINT);
   if(pt <= 0.0) pt = Point;
   int dig = (int)MarketInfo(sym, MODE_DIGITS);
   if(dig <= 0) dig = Digits;

   double stopLevelPoints   = MarketInfo(sym, MODE_STOPLEVEL);
   double freezeLevelPoints = MarketInfo(sym, MODE_FREEZELEVEL);
   double minDistance       = (MathMax(stopLevelPoints, freezeLevelPoints) + 2.0) * pt;

   if(cmd == OP_BUY)
   {
      if(sl > 0.0 && (openPrice - sl) < minDistance)
         sl = NormalizeDouble(openPrice - minDistance, dig);
      if(tp > 0.0 && (tp - openPrice) < minDistance)
         tp = NormalizeDouble(openPrice + minDistance, dig);
   }
   else if(cmd == OP_SELL)
   {
      if(sl > 0.0 && (sl - openPrice) < minDistance)
         sl = NormalizeDouble(openPrice + minDistance, dig);
      if(tp > 0.0 && (openPrice - tp) < minDistance)
         tp = NormalizeDouble(openPrice - minDistance, dig);
   }

   if(sl > 0.0) sl = NormalizeDouble(sl, dig);
   if(tp > 0.0) tp = NormalizeDouble(tp, dig);

   return true;
}

//+------------------------------------------------------------------+
//| Safe OrderModify with retries and StopLevel verification         |
//+------------------------------------------------------------------+
bool Executor_SafeOrderModify(const int ticket, const double price, double sl, double tp, const datetime expiration = 0, const color arrowColor = clrNONE)
{
   if(!OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES)) return false;
   
   string sym = OrderSymbol();
   int cmd = OrderType();
   int dig = (int)MarketInfo(sym, MODE_DIGITS);
   if(dig <= 0) dig = Digits;

   ClampStopLevels(sym, cmd, OrderOpenPrice(), sl, tp);

   for(int m = 0; m < 3; m++)
   {
      ResetLastError();
      if(sym == Symbol()) RefreshRates();

      bool res = OrderModify(ticket, OrderOpenPrice(), sl, tp, expiration, arrowColor);
      if(res)
      {
         PrintFormat("[ORDER MODIFY SUCCESS] Ticket #%d updated with SL: %f | TP: %f", ticket, sl, tp);
         return true;
      }

      int err = GetLastError();
      if(err == 1 || err == 0) return true; // No changes or success
      
      PrintFormat("[ORDER MODIFY RETRY] Ticket #%d attempt %d/3 failed (Error %d). Backoff...", ticket, m + 1, err);
      Sleep(200 * (1 << m));
   }

   return false;
}

//+------------------------------------------------------------------+
//| Non-Blocking Outbox Execution Notification                       |
//+------------------------------------------------------------------+
void DispatchExecutionAlertOutbox(int ticket, string sym, int cmd, double lots, double price, double sl, double tp, uint latencyMs)
{
   string typeStr = (cmd == OP_BUY) ? "BUY" : "SELL";
   string circle  = (cmd == OP_BUY) ? TG_GREEN_CIRCLE : TG_RED_CIRCLE;
   
   string html = StringFormat(
      "%s <b>AUTONOMOUS ORDER EXECUTED</b>\n" +
      "%s\n" +
      "<b>Ticket:</b> #%d\n" +
      "<b>Symbol:</b> %s\n" +
      "<b>Action:</b> %s\n" +
      "<b>Volume:</b> %.2f Lots\n" +
      "<b>Entry Price:</b> %f\n" +
      "<b>Stop Loss:</b> %f\n" +
      "<b>Take Profit:</b> %f\n" +
      "<b>Latency:</b> %u ms\n" +
      "<b>Time:</b> %s\n" +
      "%s",
      circle,
      TG_DIVIDER,
      ticket,
      sym,
      typeStr,
      lots,
      price,
      sl,
      tp,
      latencyMs,
      TimeToStr(TimeCurrent(), TIME_DATE|TIME_SECONDS),
      TG_DIVIDER
   );

   // Construct Telegram action buttons (Close, BE, Half)
   string markup = StringFormat(
      "{\"inline_keyboard\":[[{\"text\":\"❌ Close #%d\",\"callback_data\":\"/close_%d\"}," +
      "{\"text\":\"🛡️ BE\",\"callback_data\":\"/be_%d\"}," +
      "{\"text\":\"✂️ Half\",\"callback_data\":\"/half_%d\"}]]}",
      ticket, ticket, ticket, ticket
   );

   // Ultra-fast non-blocking outbox write (<0.1ms)
   Telegram_WriteOutboxPayload(html, "", markup);
}

//+------------------------------------------------------------------+
//| Safe Order Execution Engine with ECN 2-Step & Requote Backoff    |
//+------------------------------------------------------------------+
int ExecuteOrderSafe(const string sym, 
                     const int cmd, 
                     const double volume, 
                     const double stopLoss, 
                     const double takeProfit, 
                     const int magic, 
                     const string comment = "AutoBot", 
                     const int slippagePoints = 15)
{
   // 1. Validate quote freshness (reject stale feeds)
   if(!IsQuoteFresh(sym, 5))
   {
      PrintFormat("[STALE FEED VETO] Cannot dispatch order on %s: Quote is older than 5 seconds.", sym);
      return -1;
   }

   // 2. Pre-execution free margin verification
   ResetLastError();
   double freeMarginCheck = AccountFreeMarginCheck(sym, cmd, volume);
   if(GetLastError() == 134 || freeMarginCheck <= 0.0)
   {
      PrintFormat("[ORDER REJECTED] Margin check failed for %.2f lots on %s. Free Margin Check: %.2f", volume, sym, freeMarginCheck);
      return -1;
   }

   int dig = (int)MarketInfo(sym, MODE_DIGITS);
   if(dig <= 0) dig = Digits;

   // ECN market execution check: Brokers with 0 StopLevel require 0 SL/TP on initial send
   double stopLevel = MarketInfo(sym, MODE_STOPLEVEL);
   bool isECN = (stopLevel == 0.0);

   int ticket = -1;
   int attempts = 0;
   const int maxAttempts = 3;
   color arrowColor = (cmd == OP_BUY) ? clrBlue : clrRed;

   uint tStart = GetTickCount();

   while(attempts < maxAttempts && ticket < 0)
   {
      attempts++;
      ResetLastError();
      if(sym == Symbol()) RefreshRates();

      // Retrieve fresh quotes per attempt
      double execPrice = (cmd == OP_BUY) ? MarketInfo(sym, MODE_ASK) : MarketInfo(sym, MODE_BID);
      if(execPrice <= 0.0)
      {
         Sleep(200);
         continue;
      }
      execPrice = NormalizeDouble(execPrice, dig);

      double sendSL = stopLoss;
      double sendTP = takeProfit;
      if(sendSL > 0.0 || sendTP > 0.0)
      {
         ClampStopLevels(sym, cmd, execPrice, sendSL, sendTP);
      }

      // If ECN broker, open first with 0 SL and 0 TP
      if(isECN)
      {
         sendSL = 0.0;
         sendTP = 0.0;
      }

      ticket = OrderSend(sym, cmd, volume, execPrice, slippagePoints, sendSL, sendTP, comment, magic, 0, arrowColor);

      if(ticket > 0)
      {
         uint latencyMs = GetTickCount() - tStart;
         PrintFormat("[ORDER FILLED] Ticket #%d | Symbol: %s | Type: %s | Lots: %.2f | Price: %f | Latency: %u ms",
                     ticket, sym, (cmd == OP_BUY ? "BUY" : "SELL"), volume, execPrice, latencyMs);

         // Second step for ECN: Attach SL & TP via Executor_SafeOrderModify
         if(isECN && (stopLoss > 0.0 || takeProfit > 0.0))
         {
            if(!Executor_SafeOrderModify(ticket, execPrice, stopLoss, takeProfit, 0, arrowColor))
            {
               PrintFormat("[ECN WARNING] Failed to attach SL/TP on Ticket #%d after execution.", ticket);
            }
         }

         // Non-blocking outbox alert to Telegram
         DispatchExecutionAlertOutbox(ticket, sym, cmd, volume, execPrice, stopLoss, takeProfit, latencyMs);
         return ticket;
      }

      int err = GetLastError();
      PrintFormat("[ORDER ERROR] Attempt %d/%d failed for %s. Error: %d", attempts, maxAttempts, sym, err);

      // Error 130 on instant execution -> switch to ECN two-step immediately
      if(err == 130 && !isECN && (stopLoss > 0.0 || takeProfit > 0.0))
      {
         isECN = true;
         continue;
      }

      // Requote, Price changed, Off quotes, Context busy -> exponential backoff sleep
      if(err == 4 || err == 135 || err == 136 || err == 137 || err == 138 || err == 146)
      {
         Sleep(200 * (1 << (attempts - 1))); // 200ms, 400ms, 800ms
      }
      else
      {
         break; // Non-retryable error (e.g. Market closed, Trade disabled)
      }
   }

   return ticket;
}

#endif // __TRADE_EXECUTOR_MQH__
