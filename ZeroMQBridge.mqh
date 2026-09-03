void ZmqDebugLog(string msg)
{
   Print("[ZMQ Bridge] " + msg);
   int h = FileOpen("zmq_bridge_debug.txt", FILE_READ|FILE_WRITE|FILE_TXT);
   if(h != INVALID_HANDLE)
   {
      FileSeek(h, 0, SEEK_END);
      FileWriteString(h, TimeToStr(TimeCurrent(), TIME_SECONDS) + " " + msg + "\r\n");
      FileClose(h);
   }
}
//+------------------------------------------------------------------+
//|                                              ZeroMQBridge.mqh    |
//|                  MetaTrader 4 ZeroMQ Bridge & Remote Control     |
//|               Integrated Module for Institutional EAs            |
//+------------------------------------------------------------------+
#property strict

#include <Zmq/Zmq.mqh>

//+------------------------------------------------------------------+
//| INPUT / CONFIG                                                   |
//+------------------------------------------------------------------+
input string InpZmqBindAddress = "tcp://*:5555"; // ZeroMQ Bind Address

//+------------------------------------------------------------------+
//| GLOBAL STATE                                                     |
//+------------------------------------------------------------------+
Context g_zmqContext("MT4_ZeroMQ_Bridge");
Socket *g_zmqSocket = NULL;
bool    g_zmqReady  = false;

// Forward declare external EA runtime toggle if present


//+------------------------------------------------------------------+
//| JSON Helpers                                                     |
//+------------------------------------------------------------------+
string Zmq_JsonEscape(string str)
{
   string res = str;
   StringReplace(res, "\\", "\\\\");
   StringReplace(res, "\"", "\\\"");
   StringReplace(res, "\r", "");
   StringReplace(res, "\n", "\\n");
   StringReplace(res, "\t", "\\t");
   return res;
}

string Zmq_ExtractJsonString(const string json, const string key)
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

double Zmq_ExtractJsonNumber(const string json, const string key, double defaultVal = 0.0)
{
   string search = "\"" + key + "\"";
   int pos = StringFind(json, search);
   if(pos < 0) return defaultVal;
   
   int colon = StringFind(json, ":", pos + StringLen(search));
   if(colon < 0) return defaultVal;
   
   int i = colon + 1;
   int len = StringLen(json);
   while(i < len && (StringGetChar(json, i) == ' ' || StringGetChar(json, i) == '\t')) i++;
   
   int start = i;
   while(i < len)
   {
      ushort ch = StringGetChar(json, i);
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
//| Command Handlers                                                 |
//+------------------------------------------------------------------+
string Zmq_HandleGetAccount()
{
   string json = "{";
   json += "\"status\":\"ok\",";
   json += "\"action\":\"GET_ACCOUNT\",";
   json += "\"balance\":" + DoubleToString(AccountBalance(), 2) + ",";
   json += "\"equity\":" + DoubleToString(AccountEquity(), 2) + ",";
   json += "\"margin\":" + DoubleToString(AccountMargin(), 2) + ",";
   json += "\"free_margin\":" + DoubleToString(AccountFreeMargin(), 2) + ",";
   
   double marginLevel = (AccountMargin() > 0.0) ? (AccountEquity() / AccountMargin()) * 100.0 : 100.0;
   json += "\"margin_level\":" + DoubleToString(marginLevel, 2) + ",";
   
   double floatingPL = AccountEquity() - AccountBalance();
   json += "\"floating_pl\":" + DoubleToString(floatingPL, 2) + ",";
   json += "\"leverage\":" + IntegerToString(AccountLeverage()) + ",";
   json += "\"currency\":\"" + Zmq_JsonEscape(AccountCurrency()) + "\",";
   json += "\"company\":\"" + Zmq_JsonEscape(AccountCompany()) + "\",";
   json += "\"server\":\"" + Zmq_JsonEscape(AccountServer()) + "\",";
   json += "\"server_time\":\"" + TimeToStr(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "\"";
   json += "}";
   return json;
}

string Zmq_HandleGetPositions()
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
      
      if(count > 0) json += ",";
      
      json += "{";
      json += "\"ticket\":" + IntegerToString(OrderTicket()) + ",";
      json += "\"symbol\":\"" + Zmq_JsonEscape(OrderSymbol()) + "\",";
      json += "\"type\":\"" + typeStr + "\",";
      json += "\"lots\":" + DoubleToString(OrderLots(), 2) + ",";
      json += "\"open_price\":" + DoubleToString(OrderOpenPrice(), Digits) + ",";
      json += "\"close_price\":" + DoubleToString(OrderClosePrice(), Digits) + ",";
      json += "\"sl\":" + DoubleToString(OrderStopLoss(), Digits) + ",";
      json += "\"tp\":" + DoubleToString(OrderTakeProfit(), Digits) + ",";
      json += "\"profit\":" + DoubleToString(OrderProfit(), 2) + ",";
      json += "\"swap\":" + DoubleToString(OrderSwap(), 2) + ",";
      json += "\"commission\":" + DoubleToString(OrderCommission(), 2) + ",";
      json += "\"open_time\":\"" + TimeToStr(OrderOpenTime(), TIME_DATE|TIME_SECONDS) + "\",";
      json += "\"comment\":\"" + Zmq_JsonEscape(OrderComment()) + "\",";
      json += "\"magic\":" + IntegerToString(OrderMagicNumber());
      json += "}";
      count++;
   }
   json += "],\"count\":" + IntegerToString(count) + "}";
   return json;
}

string Zmq_HandleGetHistory(const string reqJson)
{
   int limit = (int)Zmq_ExtractJsonNumber(reqJson, "limit", 10);
   if(limit <= 0) limit = 10;
   if(limit > 100) limit = 100;
   
   string filter = Zmq_ExtractJsonString(reqJson, "filter");
   if(filter == "") filter = "all";
   
   datetime startTime = 0;
   if(filter == "today")
      startTime = StringToTime(TimeToStr(TimeCurrent(), TIME_DATE));
   else if(filter == "lastweek")
      startTime = TimeCurrent() - (7 * 86400);
   
   string json = "{\"status\":\"ok\",\"action\":\"GET_HISTORY\",\"trades\":[";
   int totalHistory = OrdersHistoryTotal();
   int count = 0;
   double totalProfit = 0.0;
   
   for(int i = totalHistory - 1; i >= 0 && count < limit; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL) continue;
      
      if(startTime > 0 && OrderCloseTime() < startTime) continue;
      
      string typeStr = (type == OP_BUY) ? "BUY" : "SELL";
      double netPL = OrderProfit() + OrderSwap() + OrderCommission();
      totalProfit += netPL;
      
      if(count > 0) json += ",";
      
      json += "{";
      json += "\"ticket\":" + IntegerToString(OrderTicket()) + ",";
      json += "\"symbol\":\"" + Zmq_JsonEscape(OrderSymbol()) + "\",";
      json += "\"type\":\"" + typeStr + "\",";
      json += "\"lots\":" + DoubleToString(OrderLots(), 2) + ",";
      json += "\"open_price\":" + DoubleToString(OrderOpenPrice(), Digits) + ",";
      json += "\"close_price\":" + DoubleToString(OrderClosePrice(), Digits) + ",";
      json += "\"sl\":" + DoubleToString(OrderStopLoss(), Digits) + ",";
      json += "\"tp\":" + DoubleToString(OrderTakeProfit(), Digits) + ",";
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

string Zmq_HandleCloseAll()
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
         if(OrderDelete(OrderTicket())) closed++;
         else failed++;
         continue;
      }
      
      RefreshRates();
      double closePrice = (type == OP_BUY) ? MarketInfo(OrderSymbol(), MODE_BID) : MarketInfo(OrderSymbol(), MODE_ASK);
      double pl = OrderProfit() + OrderSwap() + OrderCommission();
      
      bool ok = OrderClose(OrderTicket(), OrderLots(), closePrice, 5, clrOrangeRed);
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
   json += "\"action\":\"CLOSE_ALL\",";
   json += "\"closed_count\":" + IntegerToString(closed) + ",";
   json += "\"failed_count\":" + IntegerToString(failed) + ",";
   json += "\"realized_pl\":" + DoubleToString(realizedPL, 2);
   json += "}";
   return json;
}

string Zmq_HandleCloseSymbol(const string reqJson)
{
   string targetSymbol = Zmq_ExtractJsonString(reqJson, "symbol");
   StringToUpper(targetSymbol);
   StringTrimLeft(targetSymbol);
   StringTrimRight(targetSymbol);
   
   if(targetSymbol == "")
      return "{\"status\":\"error\",\"message\":\"Missing symbol parameter\"}";
   
   int closed = 0;
   int failed = 0;
   double realizedPL = 0.0;
   
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      
      string orderSym = OrderSymbol();
      StringToUpper(orderSym);
      if(StringFind(orderSym, targetSymbol) < 0) continue;
      
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL)
      {
         if(OrderDelete(OrderTicket())) closed++;
         else failed++;
         continue;
      }
      
      RefreshRates();
      double closePrice = (type == OP_BUY) ? MarketInfo(OrderSymbol(), MODE_BID) : MarketInfo(OrderSymbol(), MODE_ASK);
      double pl = OrderProfit() + OrderSwap() + OrderCommission();
      
      bool ok = OrderClose(OrderTicket(), OrderLots(), closePrice, 5, clrOrangeRed);
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

string Zmq_HandleModifySL(const string reqJson)
{
   int ticket = (int)Zmq_ExtractJsonNumber(reqJson, "ticket", 0);
   string symbol = Zmq_ExtractJsonString(reqJson, "symbol");
   double newSL = Zmq_ExtractJsonNumber(reqJson, "sl", 0.0);
   
   int modified = 0;
   int total = OrdersTotal();
   
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(ticket > 0 && OrderTicket() != ticket) continue;
      if(symbol != "" && OrderSymbol() != symbol) continue;
      
      if(OrderModify(OrderTicket(), OrderOpenPrice(), newSL, OrderTakeProfit(), 0, clrGold))
         modified++;
   }
   
   return "{\"status\":\"ok\",\"action\":\"MODIFY_SL\",\"modified_count\":" + IntegerToString(modified) + ",\"new_sl\":" + DoubleToString(newSL, 5) + "}";
}

string Zmq_HandleModifyTP(const string reqJson)
{
   int ticket = (int)Zmq_ExtractJsonNumber(reqJson, "ticket", 0);
   string symbol = Zmq_ExtractJsonString(reqJson, "symbol");
   double newTP = Zmq_ExtractJsonNumber(reqJson, "tp", 0.0);
   
   int modified = 0;
   int total = OrdersTotal();
   
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(ticket > 0 && OrderTicket() != ticket) continue;
      if(symbol != "" && OrderSymbol() != symbol) continue;
      
      if(OrderModify(OrderTicket(), OrderOpenPrice(), OrderStopLoss(), newTP, 0, clrDodgerBlue))
         modified++;
   }
   
   return "{\"status\":\"ok\",\"action\":\"MODIFY_TP\",\"modified_count\":" + IntegerToString(modified) + ",\"new_tp\":" + DoubleToString(newTP, 5) + "}";
}

string Zmq_HandlePauseBot()
{
   GlobalVariableSet("AutoTrading_Paused", 1.0);
   g_AutoTradingRuntimeActive = false;
   
   int h = FileOpen("autotrade_state.flag", FILE_WRITE|FILE_TXT);
   if(h != INVALID_HANDLE)
   {
      FileWriteString(h, "PAUSED\nTimestamp=" + IntegerToString((int)TimeCurrent()));
      FileClose(h);
   }
   
   Print("[ZMQ Bridge] AutoTrading PAUSED by remote command");
   return "{\"status\":\"ok\",\"action\":\"PAUSE_BOT\",\"autotrading\":\"PAUSED\"}";
}

string Zmq_HandleResumeBot()
{
   GlobalVariableSet("AutoTrading_Paused", 0.0);
   g_AutoTradingRuntimeActive = true;
   
   int h = FileOpen("autotrade_state.flag", FILE_WRITE|FILE_TXT);
   if(h != INVALID_HANDLE)
   {
      FileWriteString(h, "ACTIVE\nTimestamp=" + IntegerToString((int)TimeCurrent()));
      FileClose(h);
   }
   
   Print("[ZMQ Bridge] AutoTrading RESUMED by remote command");
   return "{\"status\":\"ok\",\"action\":\"RESUME_BOT\",\"autotrading\":\"ACTIVE\"}";
}

string Zmq_HandlePing()
{
   return "{\"status\":\"ok\",\"action\":\"PING\",\"server_time\":\"" + TimeToStr(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "\"}";
}

//+------------------------------------------------------------------+
//| Request Dispatcher                                               |
//+------------------------------------------------------------------+
string Zmq_ProcessRequest(const string reqStr)
{
   string action = Zmq_ExtractJsonString(reqStr, "action");
   if(action == "")
   {
      action = reqStr;
      StringTrimLeft(action);
      StringTrimRight(action);
      StringToUpper(action);
   }
   
   if(action == "GET_ACCOUNT" || action == "ACCOUNT")
      return Zmq_HandleGetAccount();
   if(action == "GET_POSITIONS" || action == "POSITIONS")
      return Zmq_HandleGetPositions();
   if(action == "GET_HISTORY" || action == "HISTORY")
      return Zmq_HandleGetHistory(reqStr);
   if(action == "CLOSE_ALL")
      return Zmq_HandleCloseAll();
   if(action == "CLOSE_SYMBOL")
      return Zmq_HandleCloseSymbol(reqStr);
   if(action == "MODIFY_SL")
      return Zmq_HandleModifySL(reqStr);
   if(action == "MODIFY_TP")
      return Zmq_HandleModifyTP(reqStr);
   if(action == "PAUSE_BOT" || action == "PAUSE")
      return Zmq_HandlePauseBot();
   if(action == "RESUME_BOT" || action == "RESUME")
      return Zmq_HandleResumeBot();
   if(action == "PING")
      return Zmq_HandlePing();
      
   return "{\"status\":\"error\",\"message\":\"Unknown action: " + Zmq_JsonEscape(action) + "\"}";
}

//+------------------------------------------------------------------+
//| Lifecycle Hooks                                                  |
//+------------------------------------------------------------------+
void ZeroMQ_Init(string bindAddress = "tcp://*:5555")
{
   ZmqDebugLog("ZeroMQ_Init called with " + bindAddress + ". Context ref: " + IntegerToString((int)g_zmqContext.ref()));
   if(g_zmqContext.ref() == 0)
   {
      Print("[ZeroMQ ERROR] Context initialization failed");
      return;
   }
   
   g_zmqSocket = new Socket(g_zmqContext, ZMQ_REP);
   if(g_zmqSocket == NULL || !g_zmqSocket.valid())
   {
      Print("[ZeroMQ ERROR] Socket initialization failed");
      return;
   }
   
   g_zmqSocket.setReceiveTimeout(5);
   g_zmqSocket.setSendTimeout(1000);
   g_zmqSocket.setLinger(0);
   
   if(g_zmqSocket.bind(bindAddress))
   {
            g_zmqReady = true; 
      ZmqDebugLog("ZeroMQ_Init SUCCESS: bound to " + bindAddress);
            EventKillTimer();
      bool tOk =                   EventKillTimer();
      EventSetMillisecondTimer(250);
      ZmqDebugLog("EventSetMillisecondTimer(250) started");
      PrintFormat("[ZeroMQ Bridge ACTIVE] Listening on %s", bindAddress);
   }
   else
   {
      ZmqDebugLog("Failed to bind: " + IntegerToString(zmq_errno()));
   }
}

void ZeroMQ_Deinit(string bindAddress = "tcp://*:5555")
{
   g_zmqReady = false;
   if(g_zmqSocket != NULL)
   {
      g_zmqSocket.unbind(bindAddress);
      delete g_zmqSocket;
      g_zmqSocket = NULL;
   }
}

void ZeroMQ_Poll()
{
   if(!g_zmqReady || g_zmqSocket == NULL || g_zmqSocket.ref() == 0) return;
   
   uchar reqBuf[];
   ArrayResize(reqBuf, 4096);
   int bytesRecv = zmq_recv(g_zmqSocket.ref(), reqBuf, 4096, 1); // 1 = ZMQ_DONTWAIT
   if(bytesRecv > 0)
   {
      string reqStr = CharArrayToString(reqBuf, 0, bytesRecv, CP_UTF8);
      ZmqDebugLog(">>> RECV: " + reqStr);
      
      string replyStr = Zmq_ProcessRequest(reqStr);
      
      uchar replyBuf[];
      StringToCharArray(replyStr, replyBuf, 0, WHOLE_ARRAY, CP_UTF8);
      int sendLen = StringLen(replyStr);
      
      int bytesSent = zmq_send(g_zmqSocket.ref(), replyBuf, sendLen, 0);
      ZmqDebugLog("<<< SENT: " + IntegerToString(bytesSent) + " bytes");
   }
}
//+------------------------------------------------------------------+









