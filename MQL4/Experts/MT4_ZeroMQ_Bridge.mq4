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
   string tradeModeStr = (tradeMode == 2) ? "REAL" : "DEMO";
   json += "\"trade_mode\":\"" + tradeModeStr + "\",";
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
      string upperOSym = orderSym;
      StringToUpper(upperOSym);
      if(StringFind(upperOSym, targetSymbol) < 0) continue;
      
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
      if(symbol != "")
      {
         string upperSym = symbol;
         StringToUpper(upperSym);
         string upperOSym = OrderSymbol();
         StringToUpper(upperOSym);
         if(StringFind(upperOSym, upperSym) < 0) continue;
      }
      
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
      if(symbol != "")
      {
         string upperSym = symbol;
         StringToUpper(upperSym);
         string upperOSym = OrderSymbol();
         StringToUpper(upperOSym);
         if(StringFind(upperOSym, upperSym) < 0) continue;
      }
      
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







