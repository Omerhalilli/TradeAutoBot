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
#include <RiskController.mqh>

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
   double minDistance       = (MathMax(stopLevelPoints, freezeLevelPoints) + 3.0) * pt;

   double currentBid = MarketInfo(sym, MODE_BID);
   double currentAsk = MarketInfo(sym, MODE_ASK);
   if(currentBid <= 0.0) currentBid = (sym == Symbol()) ? Bid : openPrice;
   if(currentAsk <= 0.0) currentAsk = (sym == Symbol()) ? Ask : openPrice;

   if(cmd == OP_BUY)
   {
      // Buy order: StopLoss must be at least minDistance below BOTH Bid and openPrice
      if(sl > 0.0)
      {
         double maxAllowedSL = MathMin(currentBid, openPrice) - minDistance;
         if(sl > maxAllowedSL)
            sl = NormalizeDouble(maxAllowedSL, dig);
      }
      // Buy order: TakeProfit must be at least minDistance above BOTH Bid and openPrice
      if(tp > 0.0)
      {
         double minAllowedTP = MathMax(currentBid, openPrice) + minDistance;
         if(tp < minAllowedTP)
            tp = NormalizeDouble(minAllowedTP, dig);
      }
   }
   else if(cmd == OP_SELL)
   {
      // Sell order: StopLoss must be at least minDistance above BOTH Ask and openPrice
      if(sl > 0.0)
      {
         double minAllowedSL = MathMax(currentAsk, openPrice) + minDistance;
         if(sl < minAllowedSL)
            sl = NormalizeDouble(minAllowedSL, dig);
      }
      // Sell order: TakeProfit must be at least minDistance below BOTH Ask and openPrice
      if(tp > 0.0)
      {
         double maxAllowedTP = MathMin(currentAsk, openPrice) - minDistance;
         if(tp > maxAllowedTP)
            tp = NormalizeDouble(maxAllowedTP, dig);
      }
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

   for(int m = 0; m < 3; m++)
   {
      ResetLastError();
      if(sym == Symbol()) RefreshRates();

      double modifySL = sl;
      double modifyTP = tp;
      ClampStopLevels(sym, cmd, OrderOpenPrice(), modifySL, modifyTP);

      bool res = OrderModify(ticket, OrderOpenPrice(), modifySL, modifyTP, expiration, arrowColor);
      if(res)
      {
         PrintFormat("[ORDER MODIFY SUCCESS] Ticket #%d updated with SL: %f | TP: %f", ticket, modifySL, modifyTP);
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
//| Audit Open Orders & Enforce Mandatory Stop Loss / Take Profit    |
//| Ensures unexpected restart never leaves unprotected trades       |
//+------------------------------------------------------------------+
void AuditAndEnforceOpenOrderStops(int magicFilter = -1, double defaultATRMultiplierSL = 1.5, double defaultATRMultiplierTP = 3.0)
{
   int total = OrdersTotal();
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
      if(magicFilter != -1 && OrderMagicNumber() != magicFilter) continue;

      int ticket = OrderTicket();
      string sym = OrderSymbol();
      int cmd    = OrderType();
      double sl  = OrderStopLoss();
      double tp  = OrderTakeProfit();
      double openPrice = OrderOpenPrice();

      if(sl <= 0.0 || tp <= 0.0)
      {
         int dig = (int)MarketInfo(sym, MODE_DIGITS);
         if(dig <= 0) dig = Digits;
         double pipPt = GetSymbolPipSize(sym);
         if(pipPt <= 0.0) pipPt = 0.0001;

         double atr = iATR(sym, PERIOD_H1, 14, 1);
         double slDist = (atr > 0.0) ? (atr * defaultATRMultiplierSL) : (pipPt * 30.0);
         double tpDist = (atr > 0.0) ? (atr * defaultATRMultiplierTP) : (pipPt * 60.0);
         if(slDist < pipPt * 20.0) slDist = pipPt * 20.0;
         if(tpDist < slDist * 1.5) tpDist = slDist * 1.5;

         double newSL = sl;
         double newTP = tp;
         if(cmd == OP_BUY)
         {
            if(newSL <= 0.0) newSL = NormalizeDouble(openPrice - slDist, dig);
            if(newTP <= 0.0) newTP = NormalizeDouble(openPrice + tpDist, dig);
         }
         else if(cmd == OP_SELL)
         {
            if(newSL <= 0.0) newSL = NormalizeDouble(openPrice + slDist, dig);
            if(newTP <= 0.0) newTP = NormalizeDouble(openPrice - tpDist, dig);
         }

         PrintFormat("[STOP AUDIT] Attaching mandatory SL: %f | TP: %f to unshielded Ticket #%d (%s)", newSL, newTP, ticket, sym);
         Executor_SafeOrderModify(ticket, openPrice, newSL, newTP, 0, clrOrange);
      }
   }
}

//+------------------------------------------------------------------+
//| Active Position Lifecycle Manager (Break-Even, Trailing, Partial)|
//+------------------------------------------------------------------+
void Executor_ManageOpenPositions(int magicFilter = -1,
                                 bool useBreakEven = true,
                                 int beTriggerPips = 15,
                                 int beLockPips = 1,
                                 bool useTrailing = true,
                                 int trailStartPips = 20,
                                 int trailStepPips = 10,
                                 bool usePartialClose = false,
                                 int partialClosePips = 25,
                                 double partialCloseRatio = 0.50,
                                 int slippage = 15)
{
   int total = OrdersTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
      if(magicFilter != -1 && OrderMagicNumber() != magicFilter) continue;

      int ticket       = OrderTicket();
      string sym       = OrderSymbol();
      int cmd          = OrderType();
      double openPrice = OrderOpenPrice();
      double currentSL = OrderStopLoss();
      double currentTP = OrderTakeProfit();
      double lots      = OrderLots();

      int dig = (int)MarketInfo(sym, MODE_DIGITS);
      if(dig <= 0) dig = Digits;
      double pt = MarketInfo(sym, MODE_POINT);
      if(pt <= 0.0) pt = Point;
      double pipPt = GetSymbolPipSize(sym);
      if(pipPt <= 0.0) pipPt = pt * 10.0;

      double bid = MarketInfo(sym, MODE_BID);
      double ask = MarketInfo(sym, MODE_ASK);
      if(bid <= 0.0 || ask <= 0.0) continue;

      double currentPrice = (cmd == OP_BUY) ? bid : ask;
      double profitPips = (cmd == OP_BUY) ? ((currentPrice - openPrice) / pipPt) : ((openPrice - currentPrice) / pipPt);

      // 1. Partial Close Management
      if(usePartialClose && profitPips >= partialClosePips)
      {
         string pcKey = StringFormat("AT_PC_%d", ticket);
         if(!GlobalVariableCheck(pcKey))
         {
            double minLot = MarketInfo(sym, MODE_MINLOT);
            double lotStep = MarketInfo(sym, MODE_LOTSTEP);
            double closeLots = NormalizeDouble(MathFloor((lots * partialCloseRatio) / lotStep) * lotStep, 2);
            if(closeLots >= minLot && (lots - closeLots) >= minLot)
            {
               ResetLastError();
               if(OrderClose(ticket, closeLots, currentPrice, slippage, clrAqua))
               {
                  GlobalVariableSet(pcKey, 1.0);
                  PrintFormat("[PARTIAL CLOSE] Closed %.2f lots on Ticket #%d at +%.1f pips (Remaining: %.2f)",
                              closeLots, ticket, profitPips, lots - closeLots);
                  string alert = StringFormat(
                     "✂️ <b>PARTIAL PROFIT TAKEN</b>\n" +
                     "━━━━━━━━━━━━━━━━━━━━━━━━━━\n" +
                     "• <b>Ticket:</b> #%d (%s)\n" +
                     "• <b>Liquidated:</b> %.2f Lots\n" +
                     "• <b>Profit Secured:</b> +%.1f pips\n" +
                     "• <b>Remaining Volume:</b> %.2f Lots",
                     ticket, sym, closeLots, profitPips, lots - closeLots
                  );
                  Telegram_WriteOutboxPayload(alert, "", "");
               }
            }
         }
      }

      // 2. Break-Even Stop Management
      if(useBreakEven && profitPips >= beTriggerPips)
      {
         double bePrice = 0.0;
         bool needsBE = false;

         if(cmd == OP_BUY)
         {
            bePrice = NormalizeDouble(openPrice + (beLockPips * pipPt), dig);
            if(currentSL < bePrice) needsBE = true;
         }
         else if(cmd == OP_SELL)
         {
            bePrice = NormalizeDouble(openPrice - (beLockPips * pipPt), dig);
            if(currentSL <= 0.0 || currentSL > bePrice) needsBE = true;
         }

         if(needsBE)
         {
            if(Executor_SafeOrderModify(ticket, openPrice, bePrice, currentTP, 0, clrDodgerBlue))
            {
               PrintFormat("[BREAK-EVEN ACTIVATED] Ticket #%d SL locked at %f (+%d pip lock)", ticket, bePrice, beLockPips);
               string alert = StringFormat(
                  "🛡️ <b>BREAK-EVEN SECURED</b>\n" +
                  "━━━━━━━━━━━━━━━━━━━━━━━━━━\n" +
                  "• <b>Ticket:</b> #%d (%s)\n" +
                  "• <b>New Stop Loss:</b> %f (+%d pips)\n" +
                  "• <b>Trade is now risk-free!</b>",
                  ticket, sym, bePrice, beLockPips
               );
               Telegram_WriteOutboxPayload(alert, "", "");
            }
         }
      }

      // 3. Trailing Stop Management
      if(useTrailing && profitPips >= trailStartPips)
      {
         double newSL = 0.0;
         bool needsTrail = false;

         if(cmd == OP_BUY)
         {
            newSL = NormalizeDouble(bid - (trailStepPips * pipPt), dig);
            if(newSL < openPrice) newSL = openPrice;
            if(newSL > currentSL + (pipPt * 2.0) && newSL < bid)
            {
               needsTrail = true;
            }
         }
         else if(cmd == OP_SELL)
         {
            newSL = NormalizeDouble(ask + (trailStepPips * pipPt), dig);
            if(newSL > openPrice) newSL = openPrice;
            if((currentSL <= 0.0 || newSL < currentSL - (pipPt * 2.0)) && newSL > ask)
            {
               needsTrail = true;
            }
         }

         if(needsTrail)
         {
            if(Executor_SafeOrderModify(ticket, openPrice, newSL, currentTP, 0, clrGold))
            {
               PrintFormat("[TRAILING STOP ADJUSTED] Ticket #%d SL trailed to %f (+%.1f pips profit)", ticket, newSL, profitPips);
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Safe Order Execution Engine with ECN 2-Step & Requote Backoff    |
//| Enforces connection check, mandatory SL/TP, and RR >= 1.5        |
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
   // 1. Connection check
   if(!IsConnected())
   {
      PrintFormat("[CONNECTION VETO] Cannot dispatch order on %s: Terminal is disconnected.", sym);
      return -1;
   }
   if(!IsTradeAllowed())
   {
      PrintFormat("[TRADE CONTEXT VETO] Cannot dispatch order on %s: Trading context is busy or disabled.", sym);
      return -1;
   }

   // 2. Validate quote freshness (reject stale feeds)
   if(!IsQuoteFresh(sym, 5))
   {
      PrintFormat("[STALE FEED VETO] Cannot dispatch order on %s: Quote is older than 5 seconds.", sym);
      return -1;
   }

   // 3. Mandatory SL and TP verification (never allow 0 stops)
   if(stopLoss <= 0.0 || takeProfit <= 0.0)
   {
      PrintFormat("[SAFETY VETO] Cannot dispatch order on %s: Mandatory SL and TP required (SL: %f, TP: %f)", sym, stopLoss, takeProfit);
      return -1;
   }

   // 4. Pre-execution free margin verification
   ResetLastError();
   double freeMarginCheck = AccountFreeMarginCheck(sym, cmd, volume);
   if(GetLastError() == 134 || freeMarginCheck <= 0.0)
   {
      PrintFormat("[ORDER REJECTED] Margin check failed for %.2f lots on %s. Free Margin Check: %.2f", volume, sym, freeMarginCheck);
      return -1;
   }

   // 5. Symbol trade permission and direction validation
   if(!IsSymbolTradeAllowed(sym))
   {
      PrintFormat("[ORDER REJECTED] Trading is prohibited on %s (MODE_TRADEALLOWED <= 0). Cooldown activated.", sym);
      RecordSymbolCooldown(sym);
      return -1;
   }
   long symTradeMode = SymbolInfoInteger(sym, SYMBOL_TRADE_MODE);
   if(cmd == OP_BUY && symTradeMode == SYMBOL_TRADE_MODE_SHORTONLY)
   {
      PrintFormat("[ORDER REJECTED] Long trading prohibited on %s (SHORTONLY). Cooldown activated.", sym);
      RecordSymbolCooldown(sym);
      return -1;
   }
   if(cmd == OP_SELL && symTradeMode == SYMBOL_TRADE_MODE_LONGONLY)
   {
      PrintFormat("[ORDER REJECTED] Short trading prohibited on %s (LONGONLY). Cooldown activated.", sym);
      RecordSymbolCooldown(sym);
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
      if(!IsQuoteFresh(sym, 5))
      {
         PrintFormat("[STALE FEED VETO] Attempt %d: Price on %s is dormant (> 5s). Waiting for fresh quote...", attempts, sym);
         Sleep(200 * (1 << (attempts - 1)));
         continue;
      }

      double execPrice = (cmd == OP_BUY) ? MarketInfo(sym, MODE_ASK) : MarketInfo(sym, MODE_BID);
      if(execPrice <= 0.0)
      {
         Sleep(200);
         continue;
      }
      execPrice = NormalizeDouble(execPrice, dig);

      // Verify Reward-to-Risk ratio >= 1.49
      double riskDist = (cmd == OP_BUY) ? (execPrice - stopLoss) : (stopLoss - execPrice);
      double rewardDist = (cmd == OP_BUY) ? (takeProfit - execPrice) : (execPrice - takeProfit);
      if(riskDist > 0.0 && (rewardDist / riskDist) < 1.49)
      {
         PrintFormat("[SAFETY VETO] Reward-to-risk ratio on %s is %.2f < 1.50 minimum. Order rejected.", sym, rewardDist / riskDist);
         return -1;
      }

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
               PrintFormat("[CRITICAL SAFETY ERROR] Failed to attach mandatory SL/TP to Ticket #%d. Liquidating position to preserve capital!", ticket);
               bool closeRes = OrderClose(ticket, volume, (cmd == OP_BUY ? MarketInfo(sym, MODE_BID) : MarketInfo(sym, MODE_ASK)), slippagePoints, clrRed);
               if(!closeRes) PrintFormat("[CRITICAL SAFETY ERROR] OrderClose failed for Ticket #%d. Error: %d", ticket, GetLastError());
               return -1;
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

      // Immediate cooldown and abort on trade permission / restriction errors
      if(err == 4110 || err == 4111 || err == 4109 || err == 133 || err == 140 || err == 132 || err == 64)
      {
         PrintFormat("[SAFETY COOLDOWN] Trade disabled or direction restricted on %s (Error %d). Cooldown activated. Retries aborted.", sym, err);
         RecordSymbolCooldown(sym);
         break;
      }

      // Requote, Price changed, Off quotes, Context busy -> exponential backoff sleep
      if(err == 4 || err == 135 || err == 136 || err == 137 || err == 138 || err == 146)
      {
         Sleep(200 * (1 << (attempts - 1))); // 200ms, 400ms, 800ms
      }
      else
      {
         RecordSymbolCooldown(sym);
         break; // Non-retryable error (e.g. Market closed, Trade disabled)
      }
   }

   return ticket;
}

#endif // __TRADE_EXECUTOR_MQH__
