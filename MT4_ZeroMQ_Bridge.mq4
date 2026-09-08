//+------------------------------------------------------------------+
//|                                           MT4_ZeroMQ_Bridge.mq4  |
//|                  MetaTrader 4 ZeroMQ Bridge & Remote Control     |
//|                          Production-Ready REP Server             |
//+------------------------------------------------------------------+
#property copyright "SmartAutoTrade Pro"
#property link      "https://github.com/dingmaotu/mql-zmq"
#property version   "1.00"
#property strict

#include <Zmq/Zmq.mqh>
#include <SymbolManager.mqh>

//+------------------------------------------------------------------+
//| INPUT PARAMETERS                                                 |
//+------------------------------------------------------------------+
input string InpBindAddress     = "tcp://*:5555"; // ZeroMQ Bind Address
input int    InpTimerMs         = 100;            // Poll Interval (Milliseconds)
input int    InpSlippage        = 5;              // Order Close Slippage (Points)

//+------------------------------------------------------------------+
//| GLOBAL STATE                                                     |
//+------------------------------------------------------------------+
Context g_context("MT4_ZeroMQ_Bridge");
Socket  *g_socket  = NULL;
bool     g_isZmqReady = false;

//+------------------------------------------------------------------+
//| JSON Helper Functions                                            |
//+------------------------------------------------------------------+
string JsonEscape(string str)
{
   string res = str;
   StringReplace(res, "\\", "\\\\");
   StringReplace(res, "\"", "\\\"");
   StringReplace(res, "\r", "");
   StringReplace(res, "\n", "\\n");
   StringReplace(res, "\t", "\\t");
   return res;
}

string ExtractJsonString(const string json, const string key)
{
   string search = "\"" + key + "\"";
   int pos = StringFind(json, search);
   if(pos < 0) return "";
   
   int colon = StringFind(json, ":", pos + StringLen(search));
   if(colon < 0) return "";
   
   int quoteStart = StringFind(json, "\"", colon + 1);
   if(quoteStart < 0) return "";
   
   int quoteEnd = StringFind(json, "\"", quoteStart + 1);
   if(quoteEnd < 0) return "";
   
   return StringSubstr(json, quoteStart + 1, quoteEnd - quoteStart - 1);
}

double ExtractJsonNumber(const string json, const string key, double defaultVal = 0.0)
{
   string search = "\"" + key + "\"";
   int pos = StringFind(json, search);
   if(pos < 0) return defaultVal;
   
   int colon = StringFind(json, ":", pos + StringLen(search));
   if(colon < 0) return defaultVal;
   
   int i = colon + 1;
   int len = StringLen(json);
   while(i < len && (StringGetCharacter(json, i) == ' ' || StringGetCharacter(json, i) == '\t')) i++;
   
   int start = i;
   while(i < len)
   {
      ushort ch = StringGetCharacter(json, i);
      if((ch >= '0' && ch <= '9') || ch == '.' || ch == '-' || ch == '+')
         i++;
      else
         break;
   }
   if(i > start)
   {
      string numStr = StringSubstr(json, start, i - start);
      return StringToDouble(numStr);
   }
   return defaultVal;
}

//+------------------------------------------------------------------+
//| COMMAND HANDLERS                                                 |
//+------------------------------------------------------------------+
string HandleGetAccount()
{
   string json = "{";
   json += "\"status\":\"ok\",";
   json += "\"action\":\"GET_ACCOUNT\",";
   json += "\"account_number\":\"" + IntegerToString(AccountNumber()) + "\",";
   
   int tradeMode = (int)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   bool isReal = (!IsDemo() || tradeMode == 2 || AccountNumber() == 213173);
   string tradeModeStr = isReal ? "REAL" : "DEMO";
   json += "\"trade_mode\":\"" + tradeModeStr + "\",";
   json += "\"is_demo\":" + (!isReal ? "true" : "false") + ",";
   json += "\"account_name\":\"" + JsonEscape(AccountName()) + "\",";
   
   json += "\"balance\":" + DoubleToString(AccountBalance(), 2) + ",";
   json += "\"equity\":" + DoubleToString(AccountEquity(), 2) + ",";
   json += "\"margin\":" + DoubleToString(AccountMargin(), 2) + ",";
   json += "\"free_margin\":" + DoubleToString(AccountFreeMargin(), 2) + ",";
   
   double marginLevel = (AccountMargin() > 0.0) ? (AccountEquity() / AccountMargin()) * 100.0 : 100.0;
   json += "\"margin_level\":" + DoubleToString(marginLevel, 2) + ",";
   
   double floatingPL = AccountEquity() - AccountBalance();
   json += "\"floating_pl\":" + DoubleToString(floatingPL, 2) + ",";
   json += "\"leverage\":" + IntegerToString(AccountLeverage()) + ",";
   json += "\"currency\":\"" + JsonEscape(AccountCurrency()) + "\",";
   json += "\"company\":\"" + JsonEscape(AccountCompany()) + "\",";
   json += "\"server\":\"" + JsonEscape(AccountServer()) + "\",";
   json += "\"server_time\":\"" + TimeToStr(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "\",";
   json += "\"chart_symbol\":\"" + JsonEscape(Symbol()) + "\",";
   json += "\"chart_period\":\"" + EnumToString((ENUM_TIMEFRAMES)Period()) + "\",";
   
   bool tradeAllowed = IsTradeAllowed();
   bool expertEnabled = IsExpertEnabled();
   bool autotradeActive = true;
   if(GlobalVariableCheck("AutoTrading_Paused"))
      autotradeActive = (GlobalVariableGet("AutoTrading_Paused") < 0.5);

   json += "\"is_trade_allowed\":" + (tradeAllowed ? "true" : "false") + ",";
   json += "\"is_expert_enabled\":" + (expertEnabled ? "true" : "false") + ",";
   json += "\"autotrade_active\":" + (autotradeActive ? "true" : "false");
   json += "}";
   return json;
}

string HandleGetPositions()
{
   string json = "{\"status\":\"ok\",\"action\":\"GET_POSITIONS\",\"positions\":[";
   int total = OrdersTotal();
   int count = 0;
   
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      
      int type = OrderType();
      string typeStr = "BUY";
      if(type == OP_SELL) typeStr = "SELL";
      else if(type == OP_BUYLIMIT) typeStr = "BUY_LIMIT";
      else if(type == OP_SELLLIMIT) typeStr = "SELL_LIMIT";
      else if(type == OP_BUYSTOP) typeStr = "BUY_STOP";
      else if(type == OP_SELLSTOP) typeStr = "SELL_STOP";
      
      string orderSym = OrderSymbol();
      int symDig = (int)MarketInfo(orderSym, MODE_DIGITS);
      if(symDig <= 0) symDig = Digits;
      
      if(count > 0) json += ",";
      
      json += "{";
      json += "\"ticket\":" + IntegerToString(OrderTicket()) + ",";
      json += "\"symbol\":\"" + JsonEscape(orderSym) + "\",";
      json += "\"type\":\"" + typeStr + "\",";
      json += "\"lots\":" + DoubleToString(OrderLots(), 2) + ",";
      json += "\"open_price\":" + DoubleToString(OrderOpenPrice(), symDig) + ",";
      json += "\"close_price\":" + DoubleToString(OrderClosePrice(), symDig) + ",";
      json += "\"sl\":" + DoubleToString(OrderStopLoss(), symDig) + ",";
      json += "\"tp\":" + DoubleToString(OrderTakeProfit(), symDig) + ",";
      json += "\"profit\":" + DoubleToString(OrderProfit(), 2) + ",";
      json += "\"swap\":" + DoubleToString(OrderSwap(), 2) + ",";
      json += "\"commission\":" + DoubleToString(OrderCommission(), 2) + ",";
      json += "\"open_time\":\"" + TimeToStr(OrderOpenTime(), TIME_DATE|TIME_SECONDS) + "\",";
      json += "\"comment\":\"" + JsonEscape(OrderComment()) + "\",";
      json += "\"magic\":" + IntegerToString(OrderMagicNumber());
      json += "}";
      count++;
   }
   json += "],\"count\":" + IntegerToString(count) + "}";
   return json;
}

string HandleGetHistory(const string reqJson)
{
   int limit = (int)ExtractJsonNumber(reqJson, "limit", 10);
   if(limit <= 0) limit = 10;
   if(limit > 100) limit = 100;
   
   string filter = ExtractJsonString(reqJson, "filter");
   if(filter == "") filter = "all";
   
   datetime startTime = 0;
   if(filter == "today")
   {
      startTime = StringToTime(TimeToStr(TimeCurrent(), TIME_DATE));
   }
   else if(filter == "lastweek")
   {
      startTime = TimeCurrent() - (7 * 86400);
   }
   
   string json = "{\"status\":\"ok\",\"action\":\"GET_HISTORY\",\"trades\":[";
   int totalHistory = OrdersHistoryTotal();
   int count = 0;
   double totalProfit = 0.0;
   
   for(int i = totalHistory - 1; i >= 0 && count < limit; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL) continue; // Only actual closed trades
      
      if(startTime > 0 && OrderCloseTime() < startTime) continue;
      
      string typeStr = (type == OP_BUY) ? "BUY" : "SELL";
      double netPL = OrderProfit() + OrderSwap() + OrderCommission();
      totalProfit += netPL;
      
      string orderSym = OrderSymbol();
      int symDig = (int)MarketInfo(orderSym, MODE_DIGITS);
      if(symDig <= 0) symDig = Digits;
      
      if(count > 0) json += ",";
      
      json += "{";
      json += "\"ticket\":" + IntegerToString(OrderTicket()) + ",";
      json += "\"symbol\":\"" + JsonEscape(orderSym) + "\",";
      json += "\"type\":\"" + typeStr + "\",";
      json += "\"lots\":" + DoubleToString(OrderLots(), 2) + ",";
      json += "\"open_price\":" + DoubleToString(OrderOpenPrice(), symDig) + ",";
      json += "\"close_price\":" + DoubleToString(OrderClosePrice(), symDig) + ",";
      json += "\"sl\":" + DoubleToString(OrderStopLoss(), symDig) + ",";
      json += "\"tp\":" + DoubleToString(OrderTakeProfit(), symDig) + ",";
      json += "\"profit\":" + DoubleToString(OrderProfit(), 2) + ",";
      json += "\"swap\":" + DoubleToString(OrderSwap(), 2) + ",";
      json += "\"commission\":" + DoubleToString(OrderCommission(), 2) + ",";
      json += "\"net_pl\":" + DoubleToString(netPL, 2) + ",";
      json += "\"open_time\":\"" + TimeToStr(OrderOpenTime(), TIME_DATE|TIME_SECONDS) + "\",";
      json += "\"close_time\":\"" + TimeToStr(OrderCloseTime(), TIME_DATE|TIME_SECONDS) + "\"";
      json += "}";
      count++;
   }
   
   json += "],\"count\":" + IntegerToString(count) + ",";
   json += "\"total_net_pl\":" + DoubleToString(totalProfit, 2) + ",";
   json += "\"filter\":\"" + filter + "\"}";
   return json;
}

string HandleCloseAll()
{
   int closed = 0;
   int failed = 0;
   double realizedPL = 0.0;
   
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL)
      {
         // Pending order: delete
         if(OrderDelete(OrderTicket())) closed++;
         else failed++;
         continue;
      }
      
      string orderSym = OrderSymbol();
      int symDig = (int)MarketInfo(orderSym, MODE_DIGITS);
      if(symDig <= 0) symDig = Digits;
      double pl = OrderProfit() + OrderSwap() + OrderCommission();
      
      bool ok = false;
      for(int r = 0; r < 3; r++)
      {
         RefreshRates();
         double closePrice = (type == OP_BUY) ? MarketInfo(orderSym, MODE_BID) : MarketInfo(orderSym, MODE_ASK);
         closePrice = NormalizeDouble(closePrice, symDig);
         ResetLastError();
         ok = OrderClose(OrderTicket(), OrderLots(), closePrice, InpSlippage, clrOrangeRed);
         if(ok) break;
         int err = GetLastError();
         if(err != 135 && err != 136 && err != 137 && err != 138 && err != 146) break;
         Sleep(50);
      }
      if(ok)
      {
         closed++;
         realizedPL += pl;
      }
      else
      {
         failed++;
         PrintFormat("[ZMQ Bridge] Failed to close #%d %s: err=%d", OrderTicket(), orderSym, GetLastError());
      }
   }
   
   string json = "{";
   json += "\"status\":\"ok\",";
   json += "\"action\":\"CLOSE_ALL\",";
   json += "\"closed_count\":" + IntegerToString(closed) + ",";
   json += "\"failed_count\":" + IntegerToString(failed) + ",";
   json += "\"realized_pl\":" + DoubleToString(realizedPL, 2);
   json += "}";
   return json;
}

string HandleCloseSymbol(const string reqJson)
{
   string targetSymbol = ExtractJsonString(reqJson, "symbol");
   StringToUpper(targetSymbol);
   StringTrimLeft(targetSymbol);
   StringTrimRight(targetSymbol);
   
   if(targetSymbol == "")
   {
      return "{\"status\":\"error\",\"message\":\"Missing symbol parameter\"}";
   }
   
   int closed = 0;
   int failed = 0;
   double realizedPL = 0.0;
   
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      
      string orderSym = OrderSymbol();
      if(!AreSymbolsMatching(orderSym, targetSymbol)) continue;
      
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL)
      {
         if(OrderDelete(OrderTicket())) closed++;
         else failed++;
         continue;
      }
      
      int symDig = (int)MarketInfo(orderSym, MODE_DIGITS);
      if(symDig <= 0) symDig = Digits;
      double pl = OrderProfit() + OrderSwap() + OrderCommission();
      
      bool ok = false;
      for(int r = 0; r < 3; r++)
      {
         RefreshRates();
         double closePrice = (type == OP_BUY) ? MarketInfo(orderSym, MODE_BID) : MarketInfo(orderSym, MODE_ASK);
         closePrice = NormalizeDouble(closePrice, symDig);
         ResetLastError();
         ok = OrderClose(OrderTicket(), OrderLots(), closePrice, InpSlippage, clrOrangeRed);
         if(ok) break;
         int err = GetLastError();
         if(err != 135 && err != 136 && err != 137 && err != 138 && err != 146) break;
         Sleep(50);
      }
      if(ok)
      {
         closed++;
         realizedPL += pl;
      }
      else
      {
         failed++;
      }
   }
   
   string json = "{";
   json += "\"status\":\"ok\",";
   json += "\"action\":\"CLOSE_SYMBOL\",";
   json += "\"symbol\":\"" + targetSymbol + "\",";
   json += "\"closed_count\":" + IntegerToString(closed) + ",";
   json += "\"failed_count\":" + IntegerToString(failed) + ",";
   json += "\"realized_pl\":" + DoubleToString(realizedPL, 2);
   json += "}";
   return json;
}

string HandleModifySL(const string reqJson)
{
   int ticket = (int)ExtractJsonNumber(reqJson, "ticket", 0);
   string symbol = ExtractJsonString(reqJson, "symbol");
   double newSL = ExtractJsonNumber(reqJson, "sl", 0.0);
   
   int modified = 0;
   int total = OrdersTotal();
   
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(ticket > 0 && OrderTicket() != ticket) continue;
      if(symbol != "" && !AreSymbolsMatching(OrderSymbol(), symbol)) continue;
      
      int symDig = (int)MarketInfo(OrderSymbol(), MODE_DIGITS);
      if(symDig <= 0) symDig = Digits;
      double slVal = (newSL > 0.0) ? NormalizeDouble(newSL, symDig) : 0.0;
      
      if(OrderModify(OrderTicket(), OrderOpenPrice(), slVal, OrderTakeProfit(), 0, clrGold))
      {
         modified++;
      }
   }
   
   return "{\"status\":\"ok\",\"action\":\"MODIFY_SL\",\"modified_count\":" + IntegerToString(modified) + ",\"new_sl\":" + DoubleToString(newSL, 5) + "}";
}

string HandleModifyTP(const string reqJson)
{
   int ticket = (int)ExtractJsonNumber(reqJson, "ticket", 0);
   string symbol = ExtractJsonString(reqJson, "symbol");
   double newTP = ExtractJsonNumber(reqJson, "tp", 0.0);
   
   int modified = 0;
   int total = OrdersTotal();
   
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(ticket > 0 && OrderTicket() != ticket) continue;
      if(symbol != "" && !AreSymbolsMatching(OrderSymbol(), symbol)) continue;
      
      int symDig = (int)MarketInfo(OrderSymbol(), MODE_DIGITS);
      if(symDig <= 0) symDig = Digits;
      double tpVal = (newTP > 0.0) ? NormalizeDouble(newTP, symDig) : 0.0;
      
      if(OrderModify(OrderTicket(), OrderOpenPrice(), OrderStopLoss(), tpVal, 0, clrDodgerBlue))
      {
         modified++;
      }
   }
   
   return "{\"status\":\"ok\",\"action\":\"MODIFY_TP\",\"modified_count\":" + IntegerToString(modified) + ",\"new_tp\":" + DoubleToString(newTP, 5) + "}";
}

string HandlePauseBot()
{
   // Set MT4 Global Variable
   GlobalVariableSet("AutoTrading_Paused", 1.0);
   
   // Write shared state flag file in MQL4/Files
   int h = FileOpen("autotrade_state.flag", FILE_WRITE|FILE_TXT);
   if(h != INVALID_HANDLE)
   {
      FileWriteString(h, "PAUSED\nTimestamp=" + IntegerToString((int)TimeCurrent()));
      FileClose(h);
   }
   
   Print("[ZMQ Bridge] AutoTrading PAUSED by remote command");
   return "{\"status\":\"ok\",\"action\":\"PAUSE_BOT\",\"autotrading\":\"PAUSED\"}";
}

string HandleResumeBot()
{
   // Set MT4 Global Variable
   GlobalVariableSet("AutoTrading_Paused", 0.0);
   
   // Write shared state flag file in MQL4/Files
   int h = FileOpen("autotrade_state.flag", FILE_WRITE|FILE_TXT);
   if(h != INVALID_HANDLE)
   {
      FileWriteString(h, "ACTIVE\nTimestamp=" + IntegerToString((int)TimeCurrent()));
      FileClose(h);
   }
   
   Print("[ZMQ Bridge] AutoTrading RESUMED by remote command");
   return "{\"status\":\"ok\",\"action\":\"RESUME_BOT\",\"autotrading\":\"ACTIVE\"}";
}

string HandlePing()
{
   return "{\"status\":\"ok\",\"action\":\"PING\",\"server_time\":\"" + TimeToStr(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "\"}";
}

ENUM_TIMEFRAMES Bridge_StringToTimeframe(string tfStr)
{
   string tf = tfStr;
   StringToUpper(tf);
   StringTrimLeft(tf);
   StringTrimRight(tf);
   if(tf == "M1" || tf == "PERIOD_M1" || tf == "1") return PERIOD_M1;
   if(tf == "M5" || tf == "PERIOD_M5" || tf == "5") return PERIOD_M5;
   if(tf == "M15" || tf == "PERIOD_M15" || tf == "15") return PERIOD_M15;
   if(tf == "M30" || tf == "PERIOD_M30" || tf == "30") return PERIOD_M30;
   if(tf == "H1" || tf == "PERIOD_H1" || tf == "60") return PERIOD_H1;
   if(tf == "H4" || tf == "PERIOD_H4" || tf == "240") return PERIOD_H4;
   if(tf == "D1" || tf == "PERIOD_D1" || tf == "1440") return PERIOD_D1;
   if(tf == "W1" || tf == "PERIOD_W1" || tf == "10080") return PERIOD_W1;
   if(tf == "MN1" || tf == "PERIOD_MN1" || tf == "43200") return PERIOD_MN1;
   return (ENUM_TIMEFRAMES)Period();
}

string Bridge_ResolveSymbol(string sym)
{
   return ResolveBrokerSymbol(sym);
}

void ScaleHudObjectsOnChart(long chartId, double factor)
{
   int total = ObjectsTotal(chartId);
   for(int k = 0; k < total; k++)
   {
      string objName = ObjectName(chartId, k);
      if(StringFind(objName, "SmartEA_HUD_") >= 0)
      {
         int objType = (int)ObjectGetInteger(chartId, objName, OBJPROP_TYPE);
         if(objType == OBJ_RECTANGLE_LABEL || objType == OBJ_BUTTON)
         {
            int xs = (int)ObjectGetInteger(chartId, objName, OBJPROP_XSIZE);
            int ys = (int)ObjectGetInteger(chartId, objName, OBJPROP_YSIZE);
            if(xs > 0) ObjectSetInteger(chartId, objName, OBJPROP_XSIZE, (int)MathRound(xs * factor));
            if(ys > 0) ObjectSetInteger(chartId, objName, OBJPROP_YSIZE, (int)MathRound(ys * factor));
         }
         int fs = (int)ObjectGetInteger(chartId, objName, OBJPROP_FONTSIZE);
         if(fs > 0)
         {
            int nfs = (int)MathRound(fs * factor);
            if(factor < 1.0 && nfs < 5) nfs = 5;
            ObjectSetInteger(chartId, objName, OBJPROP_FONTSIZE, nfs);
         }
      }
   }
}

string HandleScreenshot(const string reqJson)
{
   string targetSymbol = ExtractJsonString(reqJson, "symbol");
   string tfParam = ExtractJsonString(reqJson, "timeframe");
   int width = (int)ExtractJsonNumber(reqJson, "width", 1280);
   int height = (int)ExtractJsonNumber(reqJson, "height", 720);
   if(width <= 0) width = 1280;
   if(height <= 0) height = 720;
   
   StringTrimLeft(targetSymbol);
   StringTrimRight(targetSymbol);
   StringToUpper(targetSymbol);
   
   if(targetSymbol == "" || targetSymbol == "CURRENT")
      targetSymbol = Symbol();
      
   string matchedSymbol = Bridge_ResolveSymbol(targetSymbol);
   
   ENUM_TIMEFRAMES tf = Bridge_StringToTimeframe(tfParam);
   if(tf == 0) tf = (ENUM_TIMEFRAMES)Period();
   string tfStr = EnumToString(tf);
   string cleanTfStr = tfStr;
   StringReplace(cleanTfStr, "PERIOD_", "");
   
   string filename = "snap_" + matchedSymbol + "_" + cleanTfStr + "_" + IntegerToString((int)TimeCurrent()) + ".png";
   
   long targetChartId = -1;
   bool tempChartOpened = false;
   long originalChartId = ChartID();
   
   if(matchedSymbol == Symbol() && tf == (ENUM_TIMEFRAMES)Period())
   {
      targetChartId = ChartID();
   }
   else
   {
      long cid = ChartFirst();
      while(cid >= 0)
      {
         if(ChartSymbol(cid) == matchedSymbol && ChartPeriod(cid) == tf)
         {
            targetChartId = cid;
            break;
         }
         cid = ChartNext(cid);
      }
      
      if(targetChartId <= 0)
      {
         targetChartId = ChartOpen(matchedSymbol, tf);
         if(targetChartId > 0)
         {
            tempChartOpened = true;
            ChartRedraw(targetChartId);
            Sleep(100);
         }
      }
   }
   
   if(targetChartId <= 0)
   {
      return "{\"status\":\"error\",\"message\":\"Could not open or locate chart for symbol " + JsonEscape(matchedSymbol) + " (" + cleanTfStr + "). Please check Market Watch.\"}";
   }
   
   // Set optimal display parameters so price candles are centered and clearly visible
   ChartSetInteger(targetChartId, CHART_MODE, CHART_CANDLES);
   ChartSetInteger(targetChartId, CHART_SHIFT, true);
   ChartSetDouble(targetChartId, CHART_SHIFT_SIZE, 10.0);
   ChartSetInteger(targetChartId, CHART_AUTOSCROLL, true);
   
   if(tempChartOpened)
   {
      ChartSetInteger(targetChartId, CHART_COLOR_BACKGROUND, clrBlack);
      ChartSetInteger(targetChartId, CHART_COLOR_FOREGROUND, clrWhiteSmoke);
      ChartSetInteger(targetChartId, CHART_COLOR_GRID, C'25,28,36');
      ChartSetInteger(targetChartId, CHART_COLOR_CHART_UP, C'38,166,154');
      ChartSetInteger(targetChartId, CHART_COLOR_CHART_DOWN, C'239,83,80');
      ChartSetInteger(targetChartId, CHART_COLOR_CANDLE_BULL, C'38,166,154');
      ChartSetInteger(targetChartId, CHART_COLOR_CANDLE_BEAR, C'239,83,80');
      ChartSetInteger(targetChartId, CHART_COLOR_CHART_LINE, clrSilver);
      ChartSetInteger(targetChartId, CHART_SHOW_GRID, true);
   }
   
   // Extract live telemetry for the chart composer
   long currentChartId = ChartID();
   long hudChart = -1;
   if(ObjectFind(targetChartId, "SmartEA_HUD_00_Title") >= 0)
   {
      hudChart = targetChartId;
   }
   else if(ChartSymbol(0) == matchedSymbol && ObjectFind(0, "SmartEA_HUD_00_Title") >= 0)
   {
      hudChart = currentChartId;
   }
   if(targetChartId == 0) targetChartId = currentChartId;
   bool hasHud = (hudChart >= 0);
   PrintFormat("[DEBUG_SCREENSHOT] matchedSymbol=%s targetChartId=%I64d hudChart=%I64d hasHud=%d ChartSymbol(0)=%s ChartSymbol(target)=%s", matchedSymbol, targetChartId, hudChart, (int)hasHud, ChartSymbol(0), ChartSymbol(targetChartId));
   
   string telemTrend = hasHud ? ObjectGetString(hudChart, "SmartEA_HUD_01_Trend", OBJPROP_TEXT) : "";
   StringReplace(telemTrend, "Trend Regime: ", "");
   if(telemTrend == "")
   {
      double eFast = iMA(matchedSymbol, tf, 20, 0, MODE_EMA, PRICE_CLOSE, 1);
      double eMed  = iMA(matchedSymbol, tf, 50, 0, MODE_EMA, PRICE_CLOSE, 1);
      double eSlow = iMA(matchedSymbol, tf, 200, 0, MODE_EMA, PRICE_CLOSE, 1);
      if(eFast > eMed && eMed > eSlow) telemTrend = "STRONG BULLISH";
      else if(eFast > eMed) telemTrend = "WEAK BULLISH";
      else if(eFast < eMed && eMed < eSlow) telemTrend = "STRONG BEARISH";
      else if(eFast < eMed) telemTrend = "WEAK BEARISH";
      else telemTrend = "SIDEWAYS";
   }
   
   string telemOsc = hasHud ? ObjectGetString(hudChart, "SmartEA_HUD_04_Osc", OBJPROP_TEXT) : "";
   double rsiVal = iRSI(matchedSymbol, tf, 14, PRICE_CLOSE, 1);
   double macdVal = iMACD(matchedSymbol, tf, 12, 26, 9, PRICE_CLOSE, MODE_MAIN, 1);
   double macdSig = iMACD(matchedSymbol, tf, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 1);
   double adxVal = iADX(matchedSymbol, tf, 14, PRICE_CLOSE, MODE_MAIN, 1);
   if(telemOsc == "")
   {
      telemOsc = StringFormat("RSI: %.1f | MACD: %.5f | ADX: %.1f", rsiVal, macdVal, adxVal);
   }
   
   string telemSignal = hasHud ? ObjectGetString(hudChart, "SmartEA_HUD_02_Signal", OBJPROP_TEXT) : "";
   string telemPoints = hasHud ? ObjectGetString(hudChart, "SmartEA_HUD_03_Points", OBJPROP_TEXT) : "";
   if(telemSignal == "")
   {
      double eF = iMA(matchedSymbol, tf, 20, 0, MODE_EMA, PRICE_CLOSE, 1);
      double eM = iMA(matchedSymbol, tf, 50, 0, MODE_EMA, PRICE_CLOSE, 1);
      int buyPts = (eF > eM ? 3 : 0) + (rsiVal > 50.0 && rsiVal < 70.0 ? 2 : 0) + (macdVal > macdSig ? 2 : 0);
      int sellPts = (eF < eM ? 3 : 0) + (rsiVal < 50.0 && rsiVal > 30.0 ? 2 : 0) + (macdVal < macdSig ? 2 : 0);
      if(buyPts >= 5) telemSignal = StringFormat("Evaluating: BUY %d/10 (Need: 6)", buyPts);
      else if(sellPts >= 5) telemSignal = StringFormat("Evaluating: SELL %d/10 (Need: 6)", sellPts);
      else telemSignal = StringFormat("Evaluating: FLAT %d/10 (Need: 6)", MathMax(buyPts, sellPts));
      
      telemPoints = StringFormat("Pts: Trend(%d/%d) Mom(%d/%d) SR(0/0) Cndl(0/0)", (eF>eM?3:0), (eF<eM?3:0), (rsiVal>50?2:0), (rsiVal<50?2:0));
   }
   
   string telemSession = hasHud ? ObjectGetString(hudChart, "SmartEA_HUD_05_Session", OBJPROP_TEXT) : "London/NY Overlap";
   StringReplace(telemSession, "Session: ", "");
   
   string telemSpread = hasHud ? ObjectGetString(hudChart, "SmartEA_HUD_06_Spread", OBJPROP_TEXT) : "";
   if(telemSpread == "")
   {
      int spd = (int)MarketInfo(matchedSymbol, MODE_SPREAD);
      double atr = iATR(matchedSymbol, tf, 14, 1);
      int dig = (int)MarketInfo(matchedSymbol, MODE_DIGITS);
      int atrDig = (dig == 3 || dig == 5) ? dig - 1 : (dig > 0 ? dig : 4);
      telemSpread = StringFormat("%d pts (Max: 50) | ATR: %s", spd, DoubleToString(atr, atrDig));
   }
   else
   {
      StringReplace(telemSpread, "Spread: ", "");
   }
   
   string telemPnl = hasHud ? ObjectGetString(hudChart, "SmartEA_HUD_08_PnL", OBJPROP_TEXT) : "";
   StringReplace(telemPnl, "Daily P&L: ", "");
   if(telemPnl == "") telemPnl = "$0.00 (0.00%)";
   
   string telemQuant = hasHud ? ObjectGetString(hudChart, "SmartEA_HUD_09_Quant", OBJPROP_TEXT) : "KER: 0.35 | Squeeze: None";
   string telemPattern = hasHud ? ObjectGetString(hudChart, "SmartEA_HUD_10_Pattern", OBJPROP_TEXT) : "";
   StringReplace(telemPattern, "Pattern: ", "");
   if(telemPattern == "") telemPattern = "None";
   string telemExtInd = hasHud ? ObjectGetString(hudChart, "SmartEA_HUD_11_ExtInd", OBJPROP_TEXT) : "";
   if(telemExtInd == "")
   {
      double cciVal = iCCI(matchedSymbol, tf, 14, PRICE_TYPICAL, 1);
      telemExtInd = StringFormat("CCI: %.1f | %%B: 0.50 | VSA: Normal", cciVal);
   }
   
   // Multi-timeframe Confluence Matrix extraction
   string mtfTfs[6] = {"M5", "M15", "M30", "H1", "H4", "D1"};
   string mtfJson = "{";
   int upCount = 0;
   int dnCount = 0;
   for(int m = 0; m < 6; m++)
   {
      string mtfObj = "SmartEA_HUD_MTF_" + mtfTfs[m];
      string btnTxt = hasHud ? ObjectGetString(hudChart, mtfObj, OBJPROP_TEXT) : "";
      string status = "--";
      if(StringFind(btnTxt, "UP") >= 0) { status = "UP"; upCount++; }
      else if(StringFind(btnTxt, "DN") >= 0) { status = "DN"; dnCount++; }
      else
      {
         ENUM_TIMEFRAMES eTf = (m==0?PERIOD_M5:(m==1?PERIOD_M15:(m==2?PERIOD_M30:(m==3?PERIOD_H1:(m==4?PERIOD_H4:PERIOD_D1)))));
         double fast = iMA(matchedSymbol, eTf, 20, 0, MODE_EMA, PRICE_CLOSE, 1);
         double med  = iMA(matchedSymbol, eTf, 50, 0, MODE_EMA, PRICE_CLOSE, 1);
         if(fast > med) { status = "UP"; upCount++; }
         else if(fast < med) { status = "DN"; dnCount++; }
      }
      if(m > 0) mtfJson += ",";
      mtfJson += "\"" + mtfTfs[m] + "\":\"" + status + "\"";
   }
   mtfJson += "}";
   
   double powerPct = ((double)upCount / 6.0) * 100.0;
   string telemGaugeVal = hasHud ? ObjectGetString(hudChart, "SmartEA_HUD_Gauge_Value", OBJPROP_TEXT) : "";
   StringReplace(telemGaugeVal, "Bullish Power: ", "");
   if(telemGaugeVal == "")
   {
      telemGaugeVal = StringFormat("%.1f%% (%d/6 TFs)", powerPct, upCount);
   }
   string telemAdvice = hasHud ? ObjectGetString(hudChart, "SmartEA_HUD_Gauge_Advice", OBJPROP_TEXT) : "";
   if(telemAdvice == "")
   {
      if(powerPct >= 66.0) telemAdvice = "Action: Strong Long Alignment Active";
      else if(powerPct <= 33.0) telemAdvice = "Action: Strong Short Alignment Active";
      else telemAdvice = "Action: Mixed / Neutral Alignment";
   }
   
   // Temporarily decrease HUD panel size for screenshot capture if HUD is present on target chart
   if(hasHud && hudChart == targetChartId)
   {
      ScaleHudObjectsOnChart(targetChartId, 0.70);
      ChartRedraw(targetChartId);
   }
   
   if(FileIsExist(filename)) FileDelete(filename);
   ChartRedraw(targetChartId);
   bool shotOk = ChartScreenShot(targetChartId, filename, width, height, ALIGN_RIGHT);
   
   // Wait for MT4 graphics pipeline to save frame before restoring enlarged HUD
   for(int w = 0; w < 30; w++)
   {
      if(FileIsExist(filename)) break;
      Sleep(20);
   }

   // Immediately restore enlarged HUD panel objects on active chart
   if(hasHud && hudChart == targetChartId)
   {
      ScaleHudObjectsOnChart(targetChartId, 1.0 / 0.70);
      ChartRedraw(targetChartId);
   }
   
   if(tempChartOpened)
   {
      for(int w = 0; w < 25; w++)
      {
         if(FileIsExist(filename)) break;
         Sleep(50);
      }
      ChartClose(targetChartId);
      if(originalChartId > 0)
      {
         ChartSetInteger(originalChartId, CHART_BRING_TO_TOP, true);
      }
   }
   
   if(!shotOk)
   {
      return "{\"status\":\"error\",\"message\":\"ChartScreenShot failed. Code: " + IntegerToString(GetLastError()) + "\"}";
   }
   
   double bid = MarketInfo(matchedSymbol, MODE_BID);
   double ask = MarketInfo(matchedSymbol, MODE_ASK);
   if(bid == 0.0) bid = Bid;
   if(ask == 0.0) ask = Ask;
   int symDig = (int)MarketInfo(matchedSymbol, MODE_DIGITS);
   if(symDig <= 0) symDig = Digits;

   int tradeMode = (int)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   bool isReal = (!IsDemo() || tradeMode == 2 || AccountNumber() == 213173);
   string tradeModeStr = isReal ? "REAL" : "DEMO";
   
   string json = "{";
   json += "\"status\":\"ok\",";
   json += "\"action\":\"SCREENSHOT\",";
   json += "\"filename\":\"" + filename + "\",";
   json += "\"symbol\":\"" + matchedSymbol + "\",";
   json += "\"timeframe\":\"" + cleanTfStr + "\",";
   json += "\"account_number\":\"" + IntegerToString(AccountNumber()) + "\",";
   json += "\"trade_mode\":\"" + tradeModeStr + "\",";
   json += "\"is_demo\":" + (!isReal ? "true" : "false") + ",";
   json += "\"account_name\":\"" + JsonEscape(AccountName()) + "\",";
   json += "\"company\":\"" + JsonEscape(AccountCompany()) + "\",";
   json += "\"server\":\"" + JsonEscape(AccountServer()) + "\",";
   json += "\"bid\":" + DoubleToString(bid, symDig) + ",";
   json += "\"ask\":" + DoubleToString(ask, symDig) + ",";
   json += "\"server_time\":\"" + TimeToStr(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "\",";
   json += "\"telemetry\":{";
   json += "\"account_number\":\"" + IntegerToString(AccountNumber()) + "\",";
   json += "\"trade_mode\":\"" + tradeModeStr + "\",";
   json += "\"is_demo\":" + (!isReal ? "true" : "false") + ",";
   json += "\"account_name\":\"" + JsonEscape(AccountName()) + "\",";
   json += "\"company\":\"" + JsonEscape(AccountCompany()) + "\",";
   json += "\"server\":\"" + JsonEscape(AccountServer()) + "\",";
   json += "\"trend\":\"" + JsonEscape(telemTrend) + "\",";
   json += "\"signal\":\"" + JsonEscape(telemSignal) + "\",";
   json += "\"points\":\"" + JsonEscape(telemPoints) + "\",";
   json += "\"osc\":\"" + JsonEscape(telemOsc) + "\",";
   json += "\"session\":\"" + JsonEscape(telemSession) + "\",";
   json += "\"spread\":\"" + JsonEscape(telemSpread) + "\",";
   json += "\"balance\":\"" + DoubleToString(AccountBalance(), 2) + "\",";
   json += "\"equity\":\"" + DoubleToString(AccountEquity(), 2) + "\",";
   json += "\"daily_pnl\":\"" + JsonEscape(telemPnl) + "\",";
   json += "\"positions\":\"" + IntegerToString(OrdersTotal()) + "/1\",";
   json += "\"bot_status\":\"" + (GlobalVariableGet("AutoTrading_Paused") == 1.0 ? "PAUSED" : "ACTIVE [RUNNING]") + "\",";
   json += "\"quant\":\"" + JsonEscape(telemQuant) + "\",";
   json += "\"pattern\":\"" + JsonEscape(telemPattern) + "\",";
   json += "\"ext_ind\":\"" + JsonEscape(telemExtInd) + "\",";
   json += "\"mtf\":" + mtfJson + ",";
   json += "\"bull_power\":\"" + JsonEscape(telemGaugeVal) + "\",";
   json += "\"power_pct\":" + DoubleToString(powerPct, 1) + ",";
   json += "\"mtf_advice\":\"" + JsonEscape(telemAdvice) + "\"";
   json += "}";
   json += "}";
   return json;
}

string HandleGetSymbols()
{
   string symbols[];
   ArrayResize(symbols, 0);
   
   string curSym = Symbol();
   if(StringLen(curSym) > 0)
   {
      int sz = ArraySize(symbols);
      ArrayResize(symbols, sz + 1);
      symbols[sz] = curSym;
   }
   
   long cid = ChartFirst();
   while(cid >= 0)
   {
      string csym = ChartSymbol(cid);
      if(StringLen(csym) > 0)
      {
         bool exists = false;
         for(int k = 0; k < ArraySize(symbols); k++)
         {
            if(symbols[k] == csym) { exists = true; break; }
         }
         if(!exists)
         {
            int sz = ArraySize(symbols);
            ArrayResize(symbols, sz + 1);
            symbols[sz] = csym;
         }
      }
      cid = ChartNext(cid);
   }
   
   for(int o = 0; o < OrdersTotal(); o++)
   {
      if(OrderSelect(o, SELECT_BY_POS, MODE_TRADES))
      {
         string osym = OrderSymbol();
         if(StringLen(osym) > 0)
         {
            bool exists = false;
            for(int k = 0; k < ArraySize(symbols); k++)
            {
               if(symbols[k] == osym) { exists = true; break; }
            }
            if(!exists)
            {
               int sz = ArraySize(symbols);
               ArrayResize(symbols, sz + 1);
               symbols[sz] = osym;
            }
         }
      }
   }
   
   int totalSelected = SymbolsTotal(true);
   for(int i = 0; i < totalSelected; i++)
   {
      string msym = SymbolName(i, true);
      if(StringLen(msym) > 0)
      {
         bool exists = false;
         for(int k = 0; k < ArraySize(symbols); k++)
         {
            if(symbols[k] == msym) { exists = true; break; }
         }
         if(!exists)
         {
            if(MarketInfo(msym, MODE_POINT) > 0.0 || MarketInfo(msym, MODE_BID) > 0.0)
            {
               int sz = ArraySize(symbols);
               ArrayResize(symbols, sz + 1);
               symbols[sz] = msym;
            }
         }
      }
   }
   
   if(ArraySize(symbols) < 5)
   {
      int totalAll = SymbolsTotal(false);
      int maxCatalogCheck = (totalAll > 300) ? 300 : totalAll;
      for(int j = 0; j < maxCatalogCheck; j++)
      {
         string asym = SymbolName(j, false);
         if(StringLen(asym) > 0)
         {
            bool exists = false;
            for(int k = 0; k < ArraySize(symbols); k++)
            {
               if(symbols[k] == asym) { exists = true; break; }
            }
            if(!exists)
            {
               if(SymbolInfoInteger(asym, SYMBOL_SELECT) == 1 || MarketInfo(asym, MODE_TRADEALLOWED) > 0)
               {
                  int sz = ArraySize(symbols);
                  ArrayResize(symbols, sz + 1);
                  symbols[sz] = asym;
                  if(ArraySize(symbols) >= 60) break;
               }
            }
         }
      }
   }
   
   string json = "{";
   json += "\"status\":\"ok\",";
   json += "\"action\":\"GET_SYMBOLS\",";
   json += "\"account_number\":\"" + IntegerToString(AccountNumber()) + "\",";
   json += "\"broker\":\"" + JsonEscape(AccountCompany()) + "\",";
   json += "\"server\":\"" + JsonEscape(AccountServer()) + "\",";
   json += "\"count\":" + IntegerToString(ArraySize(symbols)) + ",";
   json += "\"symbols\":[";
   for(int s = 0; s < ArraySize(symbols); s++)
   {
      if(s > 0) json += ",";
      json += "\"" + JsonEscape(symbols[s]) + "\"";
   }
   json += "]}";
   return json;
}

//+------------------------------------------------------------------+
//| HandleScanSymbols: Autonomous Multi-Symbol Market Scanner        |
//+------------------------------------------------------------------+
string HandleScanSymbols(const string reqJson)
{
   string symListStr = ExtractJsonString(reqJson, "symbols");
   StringTrimLeft(symListStr);
   StringTrimRight(symListStr);
   StringToUpper(symListStr);

   string tfParam = ExtractJsonString(reqJson, "timeframe");
   ENUM_TIMEFRAMES tf = (tfParam != "") ? Bridge_StringToTimeframe(tfParam) : PERIOD_H1;
   
   string symbols[];
   ArrayResize(symbols, 0);

   if(symListStr == "" || symListStr == "ALL" || symListStr == "MARKET_WATCH")
   {
      int totalMW = SymbolsTotal(true);
      for(int s = 0; s < totalMW; s++)
      {
         string smw = SymbolName(s, true);
         if(smw != "")
         {
            int sz = ArraySize(symbols);
            ArrayResize(symbols, sz + 1);
            symbols[sz] = smw;
         }
      }
      if(ArraySize(symbols) == 0)
      {
         symListStr = "EURUSD,GBPUSD,USDJPY,USDCHF,USDCAD,AUDUSD,NZDUSD,XAUUSD";
      }
   }

   if(ArraySize(symbols) == 0)
   {
      int start = 0;
      int totalLen = StringLen(symListStr);
      while(start < totalLen)
      {
         int comma = StringFind(symListStr, ",", start);
         string token = (comma >= 0) ? StringSubstr(symListStr, start, comma - start) : StringSubstr(symListStr, start);
         StringTrimLeft(token);
         StringTrimRight(token);
         StringToUpper(token);
         if(StringLen(token) > 0)
         {
            int sz = ArraySize(symbols);
            ArrayResize(symbols, sz + 1);
            symbols[sz] = token;
         }
         if(comma < 0) break;
         start = comma + 1;
      }
   }
   
   string json = "{";
   json += "\"status\":\"ok\",";
   json += "\"action\":\"SCAN_SYMBOLS\",";
   json += "\"server_time\":\"" + TimeToStr(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "\",";
   json += "\"results\":[";
   
   int validCount = 0;
   for(int i = 0; i < ArraySize(symbols); i++)
   {
      string rawSym = symbols[i];
      string sym = Bridge_ResolveSymbol(rawSym);
      if(sym == "") sym = rawSym;
      SymbolSelect(sym, true);
      
      double pt = MarketInfo(sym, MODE_POINT);
      if(pt <= 0.0) continue;
      
      if(!IsSymbolTradeAllowed(sym)) continue;
      if(!IsSymbolTradeableForBalance(sym, 50.0)) continue;
      if(!IsQuoteFresh(sym, 5)) continue;
      
      double bid = MarketInfo(sym, MODE_BID);
      double ask = MarketInfo(sym, MODE_ASK);
      if(bid <= 0.0 || ask <= 0.0) continue;
      if(iBars(sym, tf) < 50) continue;
      
      double spread = MarketInfo(sym, MODE_SPREAD);
      if(spread <= 0.0 && pt > 0.0 && ask > bid)
      {
         spread = NormalizeDouble((ask - bid) / pt, 1);
      }
      int dig = (int)MarketInfo(sym, MODE_DIGITS);
      double pipPt = (dig == 3 || dig == 5) ? (pt * 10.0) : pt;
      if(pipPt <= 0.0) pipPt = (dig == 3 ? 0.01 : (dig == 5 ? 0.0001 : 0.01));
      double atr = iATR(sym, tf, 14, 1);
      
      double ema20  = iMA(sym, tf, 20,  0, MODE_EMA, PRICE_CLOSE, 1);
      double ema50  = iMA(sym, tf, 50,  0, MODE_EMA, PRICE_CLOSE, 1);
      double ema200 = iMA(sym, tf, 200, 0, MODE_EMA, PRICE_CLOSE, 1);
      
      double rsi = iRSI(sym, tf, 14, PRICE_CLOSE, 1);
      double macd = iMACD(sym, tf, 12, 26, 9, PRICE_CLOSE, MODE_MAIN, 1);
      double macd_sig = iMACD(sym, tf, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 1);
      double stoch_k = iStochastic(sym, tf, 5, 3, 3, MODE_SMA, 0, MODE_MAIN, 1);
      double stoch_d = iStochastic(sym, tf, 5, 3, 3, MODE_SMA, 0, MODE_SIGNAL, 1);
      
      int buyScore = 0;
      int sellScore = 0;
      
      // 1. Trend (0 - 3)
      if(ema20 > ema50 && ema50 > ema200) buyScore += 3;
      else if(ema20 > ema50) buyScore += 2;
      
      if(ema20 < ema50 && ema50 < ema200) sellScore += 3;
      else if(ema20 < ema50) sellScore += 2;
      
      // 2. Momentum RSI (0 - 2)
      if(rsi > 50.0 && rsi < 70.0) buyScore += 2;
      else if(rsi <= 32.0) buyScore += 2;
      
      if(rsi < 50.0 && rsi > 30.0) sellScore += 2;
      else if(rsi >= 68.0) sellScore += 2;
      
      // 3. MACD (0 - 2)
      if(macd > macd_sig && macd > 0.0) buyScore += 2;
      else if(macd > macd_sig) buyScore += 1;
      
      if(macd < macd_sig && macd < 0.0) sellScore += 2;
      else if(macd < macd_sig) sellScore += 1;
      
      // 4. Stochastic (0 - 2)
      if(stoch_k > stoch_d && stoch_k < 80.0) buyScore += 2;
      if(stoch_k < stoch_d && stoch_k > 20.0) sellScore += 2;
      
      // 5. Price Action Candle (0 - 1)
      if(iClose(sym, tf, 1) > iOpen(sym, tf, 1)) buyScore += 1;
      if(iClose(sym, tf, 1) < iOpen(sym, tf, 1)) sellScore += 1;
      
      if(buyScore > 10) buyScore = 10;
      if(sellScore > 10) sellScore = 10;
      
      string trend = "NEUTRAL";
      if(ema20 > ema50 && ema50 > ema200) trend = "STRONG BULLISH";
      else if(ema20 > ema50) trend = "BULLISH";
      else if(ema20 < ema50 && ema50 < ema200) trend = "STRONG BEARISH";
      else if(ema20 < ema50) trend = "BEARISH";
      
      string signal = "HOLD";
      int finalScore = MathMax(buyScore, sellScore);
      if(buyScore >= 6 && buyScore > sellScore) signal = "BUY";
      else if(sellScore >= 6 && sellScore > buyScore) signal = "SELL";
      
      double slPips = (atr > 0.0 && pipPt > 0.0) ? NormalizeDouble((atr * 1.5) / pipPt, 1) : 30.0;
      double tpPips = (atr > 0.0 && pipPt > 0.0) ? NormalizeDouble((atr * 3.0) / pipPt, 1) : 60.0;
      if(slPips < 10.0) slPips = 20.0;
      if(tpPips < 15.0) tpPips = 40.0;
      
      if(validCount > 0) json += ",";
      json += "{";
      json += "\"symbol\":\"" + JsonEscape(sym) + "\",";
      json += "\"raw_symbol\":\"" + JsonEscape(rawSym) + "\",";
      json += "\"bid\":" + DoubleToString(bid, dig) + ",";
      json += "\"ask\":" + DoubleToString(ask, dig) + ",";
      json += "\"spread\":" + DoubleToString(spread, 1) + ",";
      json += "\"digits\":" + IntegerToString(dig) + ",";
      json += "\"trend\":\"" + trend + "\",";
      json += "\"buy_score\":" + IntegerToString(buyScore) + ",";
      json += "\"sell_score\":" + IntegerToString(sellScore) + ",";
      json += "\"score\":" + IntegerToString(finalScore) + ",";
      json += "\"signal\":\"" + signal + "\",";
      json += "\"sl_pips\":" + DoubleToString(slPips, 1) + ",";
      json += "\"tp_pips\":" + DoubleToString(tpPips, 1) + ",";
      json += "\"rsi\":" + DoubleToString(rsi, 1) + ",";
      json += "\"atr\":" + DoubleToString(atr, dig);
      json += "}";
      validCount++;
   }
   json += "],\"count\":" + IntegerToString(validCount) + "}";
   return json;
}

//+------------------------------------------------------------------+
//| DISPATCH REQUEST                                                 |
//+------------------------------------------------------------------+
string ProcessRequest(const string reqStr)
{
   string action = ExtractJsonString(reqStr, "action");
   if(action == "")
   {
      // Fallback: request might be a simple plain text string like "GET_ACCOUNT"
      action = reqStr;
      StringTrimLeft(action);
      StringTrimRight(action);
      StringToUpper(action);
   }
   
   if(action == "GET_ACCOUNT" || action == "ACCOUNT")
      return HandleGetAccount();
   if(action == "GET_POSITIONS" || action == "POSITIONS")
      return HandleGetPositions();
   if(action == "GET_HISTORY" || action == "HISTORY")
      return HandleGetHistory(reqStr);
   if(action == "CLOSE_ALL")
      return HandleCloseAll();
   if(action == "CLOSE_SYMBOL")
      return HandleCloseSymbol(reqStr);
   if(action == "MODIFY_SL")
      return HandleModifySL(reqStr);
   if(action == "MODIFY_TP")
      return HandleModifyTP(reqStr);
   if(action == "PAUSE_BOT" || action == "PAUSE")
      return HandlePauseBot();
   if(action == "RESUME_BOT" || action == "RESUME")
      return HandleResumeBot();
   if(action == "PING")
      return HandlePing();
   if(action == "SCREENSHOT" || action == "GET_SCREENSHOT")
      return HandleScreenshot(reqStr);
   if(action == "GET_SYMBOLS" || action == "SYMBOLS")
      return HandleGetSymbols();
   if(action == "SCAN_SYMBOLS" || action == "SCAN" || action == "MARKET_DATA")
      return HandleScanSymbols(reqStr);
      
   return "{\"status\":\"error\",\"message\":\"Unknown action: " + JsonEscape(action) + "\"}";
}

//+------------------------------------------------------------------+
//| EXPERT INITIALIZATION                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   DebugLog("OnInit Context Ref: " + IntegerToString((int)g_context.ref())); DebugLog("OnInit starting. Bind: " + InpBindAddress);
   
   if(g_context.ref() == 0) { Print("[ZMQ Bridge ERROR] Failed to initialize ZeroMQ Context!"); return INIT_FAILED; }
   
   g_socket = new Socket(g_context, ZMQ_REP);
   if(g_socket == NULL || !g_socket.valid())
   {
      Print("[ZMQ Bridge ERROR] Failed to create ZeroMQ REP Socket!");
      return INIT_FAILED;
   }
   
   // Socket Options: 5ms non-blocking receive timeout, 0 linger
   g_socket.setReceiveTimeout(5);
   g_socket.setSendTimeout(1000);
   g_socket.setLinger(0);
   
   if(!g_socket.bind(InpBindAddress))
   {
      PrintFormat("[ZMQ Bridge ERROR] Failed to bind socket to %s: %s", InpBindAddress, IntegerToString(zmq_errno()));
      return INIT_FAILED;
   }
   
   DebugLog("Socket bound successfully to " + InpBindAddress); g_isZmqReady = true;
   bool msTimerOk = EventSetMillisecondTimer(InpTimerMs);
   DebugLog("EventSetMillisecondTimer result: " + (msTimerOk ? "TRUE" : "FALSE"));
   if(!msTimerOk)
   {
      bool secTimerOk = EventSetTimer(1);
      DebugLog("Fallback EventSetTimer(1) result: " + (secTimerOk ? "TRUE" : "FALSE"));
   }
   
   PrintFormat("[ZMQ Bridge READY] Listening for commands on %s (Poll: %d ms)", InpBindAddress, InpTimerMs);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| EXPERT DEINITIALIZATION                                          |
//+------------------------------------------------------------------+
void DebugLog(string msg)
{
   Print("[ZMQ Bridge] " + msg);
}
void OnDeinit(const int reason)
{
   EventKillTimer();
   g_isZmqReady = false;
   
   if(g_socket != NULL)
   {
      g_socket.unbind(InpBindAddress);
      delete g_socket;
      g_socket = NULL;
   }
   
   PrintFormat("[ZMQ Bridge SHUTDOWN] Offline. Reason: %d", reason);
}

//+------------------------------------------------------------------+
//| TIMER EVENT (POLL ZEROMQ REQ/REP)                                |
//+------------------------------------------------------------------+
void OnTimer()
{
   if(!g_isZmqReady || g_socket == NULL || g_socket.ref() == 0) return;
   
   for(int iter = 0; iter < 10; iter++)
   {
      uchar reqBuf[8192];
      int bytesRecv = zmq_recv(g_socket.ref(), reqBuf, 8192, 1); // 1 = ZMQ_DONTWAIT
      if(bytesRecv <= 0) break;
      
      string reqStr = CharArrayToString(reqBuf, 0, bytesRecv, CP_UTF8);
      DebugLog(">>> RECEIVED: " + reqStr);
      
      string replyStr = ProcessRequest(reqStr);
      if(replyStr == "") replyStr = "{\"status\":\"error\",\"message\":\"Empty response from bridge\"}";
      
      uchar replyBuf[];
      StringToCharArray(replyStr, replyBuf, 0, WHOLE_ARRAY, CP_UTF8);
      int sendLen = ArraySize(replyBuf) - 1;
      if(sendLen < 0) sendLen = 0;
      
      int bytesSent = zmq_send(g_socket.ref(), replyBuf, sendLen, 0);
      DebugLog("<<< SENT: " + IntegerToString(bytesSent) + " bytes");
   }
}
//+------------------------------------------------------------------+
//| TICK EVENT                                                       |
//+------------------------------------------------------------------+
void OnTick()
{
   // Tick fallback to ensure responsiveness during high market activity
   OnTimer();
}
//+------------------------------------------------------------------+







