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
   
   int i = colon + 1;
   int len = StringLen(json);
   while(i < len && (StringGetChar(json, i) == ' ' || StringGetChar(json, i) == '\t')) i++;
   if(i >= len || StringGetChar(json, i) != '\"') return "";
   
   int quoteStart = i;
   int quoteEnd = StringFind(json, "\"", quoteStart + 1);
   if(quoteEnd < 0) return "";
   if(quoteEnd <= quoteStart + 1) return "";
   
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
   while(i < len && (StringGetChar(json, i) == ' ' || StringGetChar(json, i) == '\t' || StringGetChar(json, i) == '\"')) i++;
   
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
   json += "\"account_number\":\"" + IntegerToString(AccountNumber()) + "\",";
   
   int tradeMode = (int)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   string tradeModeStr = (tradeMode == 2) ? "REAL" : "DEMO";
   json += "\"trade_mode\":\"" + tradeModeStr + "\",";
   json += "\"account_name\":\"" + Zmq_JsonEscape(AccountName()) + "\",";
   
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
   json += "\"server_time\":\"" + TimeToStr(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "\",";
   
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
      
      string orderSym = OrderSymbol();
      int symDig = (int)MarketInfo(orderSym, MODE_DIGITS);
      if(symDig <= 0) symDig = Digits;
      
      if(count > 0) json += ",";
      
      json += "{";
      json += "\"ticket\":" + IntegerToString(OrderTicket()) + ",";
      json += "\"symbol\":\"" + Zmq_JsonEscape(orderSym) + "\",";
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
      
      string orderSym = OrderSymbol();
      int symDig = (int)MarketInfo(orderSym, MODE_DIGITS);
      if(symDig <= 0) symDig = Digits;
      
      if(count > 0) json += ",";
      
      json += "{";
      json += "\"ticket\":" + IntegerToString(OrderTicket()) + ",";
      json += "\"symbol\":\"" + Zmq_JsonEscape(orderSym) + "\",";
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

//+------------------------------------------------------------------+
//| Symbol Suffix & Fuzzy Matching Helper                            |
//+------------------------------------------------------------------+
bool Zmq_SymbolsMatch(string orderSym, string targetSym)
{
   string s1 = orderSym;
   string s2 = targetSym;
   StringToUpper(s1);
   StringToUpper(s2);
   StringTrimLeft(s1);
   StringTrimRight(s1);
   StringTrimLeft(s2);
   StringTrimRight(s2);
   
   if(s2 == "" || s2 == "*" || s2 == "ALL") return true;
   if(s1 == s2) return true;

   // Normalize financial aliases
   if(s2 == "GOLD") s2 = "XAUUSD";
   if(s2 == "SILVER") s2 = "XAGUSD";
   if(s2 == "OIL" || s2 == "CRUDE" || s2 == "WTI") s2 = "USOIL";
   if(s2 == "BRENT") s2 = "UKOIL";
   if(s2 == "BITCOIN" || s2 == "CRYPTO") s2 = "BTCUSD";

   if(s1 == "GOLD") s1 = "XAUUSD";
   if(s1 == "SILVER") s1 = "XAGUSD";
   if(s1 == "OIL" || s1 == "CRUDE" || s1 == "WTI") s1 = "USOIL";
   if(s1 == "BRENT") s1 = "UKOIL";
   if(s1 == "BITCOIN" || s1 == "CRYPTO") s1 = "BTCUSD";

   if(s1 == s2) return true;
   // User passed GBPUSD, broker has GBPUSDm, GBPUSD.ecn, pro.GBPUSD
   if(StringFind(s1, s2) >= 0) return true;
   // User passed GBPUSDm, broker has GBPUSD
   if(StringFind(s2, s1) >= 0) return true;
   return false;
}

//+------------------------------------------------------------------+
//| Multi-Broker Instrument Resolver & Market Watch Sync             |
//+------------------------------------------------------------------+
string Zmq_ResolveSymbol(string genericName)
{
   string base = genericName;
   StringToUpper(base);
   StringTrimLeft(base);
   StringTrimRight(base);
   
   if(base == "CURRENT" || base == "") return Symbol();
   if(base == "GOLD") base = "XAUUSD";
   if(base == "SILVER") base = "XAGUSD";
   if(base == "OIL" || base == "CRUDE" || base == "WTI") base = "USOIL";
   if(base == "BRENT") base = "UKOIL";
   if(base == "BITCOIN" || base == "CRYPTO") base = "BTCUSD";
   
   // 1. Direct match if broker supports exact name
   if(MarketInfo(base, MODE_POINT) > 0.0) return base;
   
   // 2. Check if active chart matches base
   string chartSym = Symbol();
   string upperChart = chartSym;
   StringToUpper(upperChart);
   if(StringFind(upperChart, base) >= 0) return chartSym;
   
   // 3. Check active market orders
   for(int k = 0; k < OrdersTotal(); k++)
   {
      if(OrderSelect(k, SELECT_BY_POS, MODE_TRADES))
      {
         string oSym = OrderSymbol();
         string upperOSym = oSym;
         StringToUpper(upperOSym);
         if(StringFind(upperOSym, base) >= 0) return oSym;
      }
   }
   
   // 4. Derive broker prefix/suffix from chart Symbol() (e.g. "_min", ".pro", "m")
   string standards[4];
   standards[0] = "GBPUSD";
   standards[1] = "EURUSD";
   standards[2] = "USDJPY";
   standards[3] = "XAUUSD";
   
   for(int s = 0; s < 4; s++)
   {
      int pos = StringFind(upperChart, standards[s]);
      if(pos >= 0)
      {
         string prefix = StringSubstr(chartSym, 0, pos);
         string suffix = StringSubstr(chartSym, pos + StringLen(standards[s]));
         string candidate = prefix + base + suffix;
         if(MarketInfo(candidate, MODE_POINT) > 0.0) return candidate;
         SymbolSelect(candidate, true);
         if(MarketInfo(candidate, MODE_POINT) > 0.0) return candidate;
         break;
      }
   }
   
   // 5. Search Market Watch symbols
   int total = SymbolsTotal(true);
   for(int i = 0; i < total; i++)
   {
      string s = SymbolName(i, true);
      string upperS = s;
      StringToUpper(upperS);
      if(StringFind(upperS, base) >= 0) return s;
   }
   
   // 6. Search full broker symbol catalog and add to Market Watch
   total = SymbolsTotal(false);
   for(int j = 0; j < total; j++)
   {
      string sAll = SymbolName(j, false);
      string upperSAll = sAll;
      StringToUpper(upperSAll);
      if(StringFind(upperSAll, base) >= 0)
      {
         SymbolSelect(sAll, true);
         return sAll;
      }
   }
   
   return base;
}

double Zmq_GetSpreadPoints(string sym)
{
   string resolved = Zmq_ResolveSymbol(sym);
   double spread = MarketInfo(resolved, MODE_SPREAD);
   double pt = MarketInfo(resolved, MODE_POINT);
   double ask = MarketInfo(resolved, MODE_ASK);
   double bid = MarketInfo(resolved, MODE_BID);
   if(spread <= 0.0 && pt > 0.0 && ask > bid)
   {
      spread = NormalizeDouble((ask - bid) / pt, 1);
   }
   return spread;
}

double Zmq_GetPipPoint(string sym)
{
   string resolved = Zmq_ResolveSymbol(sym);
   double pt = MarketInfo(resolved, MODE_POINT);
   int dig = (int)MarketInfo(resolved, MODE_DIGITS);
   if(pt <= 0.0)
   {
      if(dig == 3) return 0.01;
      if(dig == 5) return 0.0001;
      return 0.01;
   }
   if(dig == 3 || dig == 5)
      return pt * 10.0;
   return pt;
}

ENUM_TIMEFRAMES Zmq_StringToTimeframe(string tfStr)
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

string Zmq_HandleCloseSymbol(const string reqJson)
{
   string targetSymbol = Zmq_ExtractJsonString(reqJson, "symbol");
   int ticketParam = (int)Zmq_ExtractJsonNumber(reqJson, "ticket", 0);
   if(ticketParam == 0 && StringToInteger(targetSymbol) > 0)
   {
      ticketParam = (int)StringToInteger(targetSymbol);
   }
   
   StringToUpper(targetSymbol);
   StringTrimLeft(targetSymbol);
   StringTrimRight(targetSymbol);
   
   if(targetSymbol == "" && ticketParam == 0)
      return "{\"status\":\"error\",\"message\":\"Missing symbol or ticket parameter\"}";
   
   int closed = 0;
   int failed = 0;
   double realizedPL = 0.0;
   
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      
      if(ticketParam > 0)
      {
         if(OrderTicket() != ticketParam) continue;
      }
      else
      {
         if(!Zmq_SymbolsMatch(OrderSymbol(), targetSymbol)) continue;
      }
      
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
   
   if(ticket == 0 && StringToInteger(symbol) > 0)
   {
      ticket = (int)StringToInteger(symbol);
      symbol = "";
   }
   
   int modified = 0;
   int total = OrdersTotal();
   
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(ticket > 0 && OrderTicket() != ticket) continue;
      if(symbol != "" && !Zmq_SymbolsMatch(OrderSymbol(), symbol)) continue;
      
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
   
   if(ticket == 0 && StringToInteger(symbol) > 0)
   {
      ticket = (int)StringToInteger(symbol);
      symbol = "";
   }
   
   int modified = 0;
   int total = OrdersTotal();
   
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(ticket > 0 && OrderTicket() != ticket) continue;
      if(symbol != "" && !Zmq_SymbolsMatch(OrderSymbol(), symbol)) continue;
      
      if(OrderModify(OrderTicket(), OrderOpenPrice(), OrderStopLoss(), newTP, 0, clrDodgerBlue))
         modified++;
   }
   
   return "{\"status\":\"ok\",\"action\":\"MODIFY_TP\",\"modified_count\":" + IntegerToString(modified) + ",\"new_tp\":" + DoubleToString(newTP, 5) + "}";
}

string Zmq_HandleCloseHalf(const string reqJson)
{
   int ticket = (int)Zmq_ExtractJsonNumber(reqJson, "ticket", 0);
   string sym = Zmq_ExtractJsonString(reqJson, "symbol");
   if(ticket == 0 && StringToInteger(sym) > 0)
      ticket = (int)StringToInteger(sym);
      
   if(ticket <= 0)
      return "{\"status\":\"error\",\"message\":\"Missing or invalid ticket parameter\"}";
      
   if(!OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES))
      return "{\"status\":\"error\",\"message\":\"Order #" + IntegerToString(ticket) + " not found or already closed\"}";
      
   int type = OrderType();
   if(type != OP_BUY && type != OP_SELL)
      return "{\"status\":\"error\",\"message\":\"Not an active market order\"}";
      
   string orderSym = OrderSymbol();
   double totalLots = OrderLots();
   double minLot = MarketInfo(orderSym, MODE_MINLOT);
   double lotStep = MarketInfo(orderSym, MODE_LOTSTEP);
   if(lotStep <= 0.0) lotStep = 0.01;
   
   double halfLots = MathFloor((totalLots / 2.0) / lotStep) * lotStep;
   if(halfLots < minLot) halfLots = totalLots;
   
   RefreshRates();
   double closePrice = (type == OP_BUY) ? MarketInfo(orderSym, MODE_BID) : MarketInfo(orderSym, MODE_ASK);
   double plRatio = (totalLots > 0.0) ? (halfLots / totalLots) : 1.0;
   double estPL = (OrderProfit() + OrderSwap() + OrderCommission()) * plRatio;
   
   bool ok = OrderClose(ticket, halfLots, closePrice, 5, clrOrange);
   if(ok)
   {
      string json = "{";
      json += "\"status\":\"ok\",";
      json += "\"action\":\"CLOSE_HALF\",";
      json += "\"ticket\":" + IntegerToString(ticket) + ",";
      json += "\"closed_lots\":" + DoubleToString(halfLots, 2) + ",";
      json += "\"remaining_lots\":" + DoubleToString(totalLots - halfLots, 2) + ",";
      json += "\"realized_pl\":" + DoubleToString(estPL, 2);
      json += "}";
      return json;
   }
   else
   {
      return "{\"status\":\"error\",\"message\":\"OrderClose failed: Error " + IntegerToString(GetLastError()) + "\"}";
   }
}

string Zmq_HandleSetBreakEven(const string reqJson)
{
   int ticket = (int)Zmq_ExtractJsonNumber(reqJson, "ticket", 0);
   string symbol = Zmq_ExtractJsonString(reqJson, "symbol");
   double lockPips = Zmq_ExtractJsonNumber(reqJson, "lock_pips", 1.0);
   if(lockPips < 0.0) lockPips = 0.0;
   
   if(ticket == 0 && StringToInteger(symbol) > 0)
   {
      ticket = (int)StringToInteger(symbol);
      symbol = "";
   }
   
   int modified = 0;
   int skipped = 0;
   int total = OrdersTotal();
   
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(ticket > 0 && OrderTicket() != ticket) continue;
      if(symbol != "" && !Zmq_SymbolsMatch(OrderSymbol(), symbol)) continue;
      
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL) continue;
      
      string sym = OrderSymbol();
      RefreshRates();
      double pipPoint = Zmq_GetPipPoint(sym);
      int digits = (int)MarketInfo(sym, MODE_DIGITS);
      double openPrice = OrderOpenPrice();
      double curSL = OrderStopLoss();
      
      double pt = MarketInfo(sym, MODE_POINT);
      if(pt <= 0.0) pt = (digits == 3 || digits == 5) ? 0.00001 : 0.001;
      double stopLevel = MarketInfo(sym, MODE_STOPLEVEL) * pt;
      double freezeLevel = MarketInfo(sym, MODE_FREEZELEVEL) * pt;
      if(stopLevel < freezeLevel) stopLevel = freezeLevel;
      if(stopLevel <= 0.0) stopLevel = pt * 5.0;

      if(type == OP_BUY)
      {
         double curBid = MarketInfo(sym, MODE_BID);
         if(curBid <= openPrice)
         {
            skipped++;
            continue;
         }
         
         double targetSL = NormalizeDouble(openPrice + (lockPips * pipPoint), digits);
         // If targetSL violates StopLevel distance from current market Bid, fallback to entry price
         if(curBid - targetSL < stopLevel)
         {
            targetSL = NormalizeDouble(openPrice, digits);
         }
         
         if(curBid - targetSL >= stopLevel && (curSL < targetSL || curSL == 0.0))
         {
            if(OrderModify(OrderTicket(), openPrice, targetSL, OrderTakeProfit(), 0, clrLimeGreen))
               modified++;
            else
               skipped++;
         }
         else
         {
            skipped++;
         }
      }
      else if(type == OP_SELL)
      {
         double curAsk = MarketInfo(sym, MODE_ASK);
         if(curAsk >= openPrice)
         {
            skipped++;
            continue;
         }
         
         double targetSL = NormalizeDouble(openPrice - (lockPips * pipPoint), digits);
         // If targetSL violates StopLevel distance from current market Ask, fallback to entry price
         if(targetSL - curAsk < stopLevel)
         {
            targetSL = NormalizeDouble(openPrice, digits);
         }
         
         if(targetSL - curAsk >= stopLevel && (curSL > targetSL || curSL == 0.0))
         {
            if(OrderModify(OrderTicket(), openPrice, targetSL, OrderTakeProfit(), 0, clrLimeGreen))
               modified++;
            else
               skipped++;
         }
         else
         {
            skipped++;
         }
      }
   }
   
   string json = "{";
   json += "\"status\":\"ok\",";
   json += "\"action\":\"SET_BREAKEVEN\",";
   json += "\"modified_count\":" + IntegerToString(modified) + ",";
   json += "\"skipped_count\":" + IntegerToString(skipped) + ",";
   json += "\"lock_pips\":" + DoubleToString(lockPips, 1) + ",";
   json += "\"target\":\"" + Zmq_JsonEscape(ticket > 0 ? IntegerToString(ticket) : (symbol == "" ? "ALL" : symbol)) + "\"";
   json += "}";
   return json;
}

string Zmq_HandleSetTrailing(const string reqJson)
{
   int ticket = (int)Zmq_ExtractJsonNumber(reqJson, "ticket", 0);
   string symbol = Zmq_ExtractJsonString(reqJson, "symbol");
   double trailPips = Zmq_ExtractJsonNumber(reqJson, "trail_pips", 20.0);
   if(trailPips < 5.0) trailPips = 5.0;
   
   if(ticket == 0 && StringToInteger(symbol) > 0)
   {
      ticket = (int)StringToInteger(symbol);
      symbol = "";
   }
   
   int modified = 0;
   int skipped = 0;
   int total = OrdersTotal();
   
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(ticket > 0 && OrderTicket() != ticket) continue;
      if(symbol != "" && !Zmq_SymbolsMatch(OrderSymbol(), symbol)) continue;
      
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL) continue;
      
      string sym = OrderSymbol();
      RefreshRates();
      double pipPoint = Zmq_GetPipPoint(sym);
      int digits = (int)MarketInfo(sym, MODE_DIGITS);
      double openPrice = OrderOpenPrice();
      double curSL = OrderStopLoss();
      double trailDist = trailPips * pipPoint;
      
      double pt = MarketInfo(sym, MODE_POINT);
      if(pt <= 0.0) pt = (digits == 3 || digits == 5) ? 0.00001 : 0.001;
      double stopLevel = MarketInfo(sym, MODE_STOPLEVEL) * pt;
      double freezeLevel = MarketInfo(sym, MODE_FREEZELEVEL) * pt;
      if(stopLevel < freezeLevel) stopLevel = freezeLevel;
      if(stopLevel <= 0.0) stopLevel = pt * 5.0;
      
      if(type == OP_BUY)
      {
         double curBid = MarketInfo(sym, MODE_BID);
         if(curBid - openPrice > trailDist)
         {
            double newSL = NormalizeDouble(curBid - trailDist, digits);
            if(curBid - newSL >= stopLevel && (newSL > curSL))
            {
               if(OrderModify(OrderTicket(), openPrice, newSL, OrderTakeProfit(), 0, clrDodgerBlue))
                  modified++;
               else
                  skipped++;
            }
            else
            {
               skipped++;
            }
         }
         else
         {
            skipped++;
         }
      }
      else if(type == OP_SELL)
      {
         double curAsk = MarketInfo(sym, MODE_ASK);
         if(openPrice - curAsk > trailDist)
         {
            double newSL = NormalizeDouble(curAsk + trailDist, digits);
            if(newSL - curAsk >= stopLevel && (newSL < curSL || curSL == 0.0))
            {
               if(OrderModify(OrderTicket(), openPrice, newSL, OrderTakeProfit(), 0, clrDodgerBlue))
                  modified++;
               else
                  skipped++;
            }
            else
            {
               skipped++;
            }
         }
         else
         {
            skipped++;
         }
      }
   }
   
   string json = "{";
   json += "\"status\":\"ok\",";
   json += "\"action\":\"SET_TRAILING\",";
   json += "\"modified_count\":" + IntegerToString(modified) + ",";
   json += "\"skipped_count\":" + IntegerToString(skipped) + ",";
   json += "\"trail_pips\":" + DoubleToString(trailPips, 1) + ",";
   json += "\"target\":\"" + Zmq_JsonEscape(ticket > 0 ? IntegerToString(ticket) : (symbol == "" ? "ALL" : symbol)) + "\"";
   json += "}";
   return json;
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

string Zmq_HandleResetSafeguards()
{
   double curEquity = AccountEquity();
   int accNum = AccountNumber();
   string peakKey = StringFormat("Prop_Peak_Eq_%d", accNum);
   string startKey = StringFormat("Prop_Start_Eq_%d", accNum);
   string dayKey = StringFormat("Prop_Day_%d", accNum);
   
   GlobalVariableSet(dayKey, TimeDay(TimeCurrent()));
   GlobalVariableSet(startKey, curEquity);
   GlobalVariableSet(peakKey, curEquity);
   GlobalVariableSet("Prop_Starting_Day_Equity", curEquity);
   GlobalVariableSet("Prop_Peak_Equity", curEquity);
   GlobalVariableSet("AutoTrading_Paused", 0.0);
   
   g_DayAnchorDate = TimeCurrent();
   g_StartingDayEquity = curEquity;
   g_StartingDayBalance = AccountBalance();
   g_PropPeakEquity = curEquity;
   g_DailyLossCircuitTripped = false;
   g_DailyTargetCircuitTripped = false;
   g_PropLockoutActive = false;
   g_AutoTradingRuntimeActive = true;
   
   PrintFormat("[SAFEGUARDS RESET] Account #%d risk anchors reset to live equity $%.2f", accNum, curEquity);
   
   string json = "{";
   json += "\"status\":\"ok\",";
   json += "\"action\":\"RESET_SAFEGUARDS\",";
   json += "\"account\":\"" + IntegerToString(accNum) + "\",";
   json += "\"equity\":" + DoubleToString(curEquity, 2) + ",";
   json += "\"message\":\"All performance anchors and drawdowns have been recalibrated to live equity.\"";
   json += "}";
   return json;
}

string Zmq_HandleGetProp()
{
   double curEquity = AccountEquity();
   double curBalance = AccountBalance();
   int accNum = AccountNumber();
   
   // Key global variables by AccountNumber() to isolate accounts
   string peakKey = StringFormat("Prop_Peak_Eq_%d", accNum);
   string startKey = StringFormat("Prop_Start_Eq_%d", accNum);
   string dayKey = StringFormat("Prop_Day_%d", accNum);
   
   int today = TimeDay(TimeCurrent());
   
   // Check if day changed for this account
   if(!GlobalVariableCheck(dayKey) || (int)GlobalVariableGet(dayKey) != today)
   {
      GlobalVariableSet(dayKey, today);
      GlobalVariableSet(startKey, curEquity);
   }
   
   double startEquity = curEquity;
   if(GlobalVariableCheck(startKey))
   {
      startEquity = GlobalVariableGet(startKey);
      // Sanity check: If starting equity is drastically larger (> 300%) or <= 0, recalibrate
      if(startEquity <= 0.0 || (startEquity > curEquity * 3.0 && curEquity > 0.0))
      {
         startEquity = curEquity;
         GlobalVariableSet(startKey, startEquity);
      }
   }
   else
   {
      startEquity = curEquity;
      GlobalVariableSet(startKey, startEquity);
   }
   
   double peakEq = curEquity;
   if(GlobalVariableCheck(peakKey))
   {
      peakEq = GlobalVariableGet(peakKey);
      // Sanity check: If peak equity is drastically larger (> 300%) or <= 0, recalibrate
      if(peakEq <= 0.0 || (peakEq > curEquity * 3.0 && curEquity > 0.0) || curEquity > peakEq)
      {
         peakEq = curEquity;
         GlobalVariableSet(peakKey, peakEq);
      }
   }
   else
   {
      peakEq = curEquity;
      GlobalVariableSet(peakKey, peakEq);
   }
   
   // Clean up legacy unscoped global variables if they don't match live equity scale
   if(GlobalVariableCheck("Prop_Starting_Day_Equity"))
   {
      double oldStart = GlobalVariableGet("Prop_Starting_Day_Equity");
      if(oldStart > curEquity * 3.0 || oldStart <= 0.0)
         GlobalVariableSet("Prop_Starting_Day_Equity", curEquity);
   }
   if(GlobalVariableCheck("Prop_Peak_Equity"))
   {
      double oldPeak = GlobalVariableGet("Prop_Peak_Equity");
      if(oldPeak > curEquity * 3.0 || oldPeak <= 0.0)
         GlobalVariableSet("Prop_Peak_Equity", curEquity);
   }
   
   // Synchronize EA internal variables if they were stuck on old demo equity
   if(g_StartingDayEquity <= 0.0 || (g_StartingDayEquity > curEquity * 3.0 && curEquity > 0.0))
   {
      g_StartingDayEquity = curEquity;
      g_StartingDayBalance = curBalance;
      g_PropPeakEquity = curEquity;
      g_DailyLossCircuitTripped = false;
      g_PropLockoutActive = false;
   }
   
   double maxDailyPct = 4.5;
   double maxTotalPct = 8.0;
   double targetGoalPct = 8.0;
   
   double dayLoss = (startEquity > curEquity) ? (startEquity - curEquity) : 0.0;
   double dayLossLimit = startEquity * (maxDailyPct / 100.0);
   double dayLossPct = (startEquity > 0.0) ? (dayLoss / startEquity * 100.0) : 0.0;
   
   double peakLoss = (peakEq > curEquity) ? (peakEq - curEquity) : 0.0;
   double peakLossLimit = peakEq * (maxTotalPct / 100.0);
   double peakLossPct = (peakEq > 0.0) ? (peakLoss / peakEq * 100.0) : 0.0;
   
   double currentGain = (curEquity > startEquity) ? (curEquity - startEquity) : 0.0;
   double targetProfitGoal = startEquity * (targetGoalPct / 100.0);
   
   string dayStatus = (dayLossPct < maxDailyPct * 0.7) ? "Safe" : ((dayLossPct < maxDailyPct) ? "Caution" : "BREACHED");
   string peakStatus = (peakLossPct < maxTotalPct * 0.7) ? "Safe" : ((peakLossPct < maxTotalPct) ? "Caution" : "BREACHED");
   
   bool isPaused = false;
   if(GlobalVariableCheck("AutoTrading_Paused"))
      isPaused = (GlobalVariableGet("AutoTrading_Paused") > 0.5);
      
   string json = "{";
   json += "\"status\":\"ok\",";
   json += "\"action\":\"GET_PROP\",";
   json += "\"account\":\"" + IntegerToString(accNum) + "\",";
   json += "\"company\":\"" + Zmq_JsonEscape(AccountCompany()) + "\",";
   json += "\"currency\":\"" + Zmq_JsonEscape(AccountCurrency()) + "\",";
   json += "\"equity\":" + DoubleToString(curEquity, 2) + ",";
   json += "\"peak_equity\":" + DoubleToString(peakEq, 2) + ",";
   json += "\"day_loss\":" + DoubleToString(dayLoss, 2) + ",";
   json += "\"day_loss_limit\":" + DoubleToString(dayLossLimit, 2) + ",";
   json += "\"day_loss_pct\":" + DoubleToString(dayLossPct, 2) + ",";
   json += "\"day_status\":\"" + dayStatus + "\",";
   json += "\"peak_loss\":" + DoubleToString(peakLoss, 2) + ",";
   json += "\"peak_loss_limit\":" + DoubleToString(peakLossLimit, 2) + ",";
   json += "\"peak_loss_pct\":" + DoubleToString(peakLossPct, 2) + ",";
   json += "\"peak_status\":\"" + peakStatus + "\",";
   json += "\"current_gain\":" + DoubleToString(currentGain, 2) + ",";
   json += "\"target_profit_goal\":" + DoubleToString(targetProfitGoal, 2) + ",";
   json += "\"max_daily_limit_pct\":" + DoubleToString(maxDailyPct, 1) + ",";
   json += "\"max_total_limit_pct\":" + DoubleToString(maxTotalPct, 1) + ",";
   json += "\"target_goal_pct\":" + DoubleToString(targetGoalPct, 1) + ",";
   json += "\"lockout_active\":" + ((dayLossPct >= maxDailyPct || g_PropLockoutActive) ? "true" : "false") + ",";
   json += "\"autotrading_active\":" + (isPaused ? "false" : "true") + ",";
   json += "\"weekend_shield\":\"Friday 21:00 GMT (Active)\"";
   json += "}";
   return json;
}

string Zmq_HandleGetReport()
{
   datetime now = TimeCurrent();
   datetime fromTime = now - 86400;
   
   int totalTrades = 0;
   int winCount = 0;
   int lossCount = 0;
   double grossProfit = 0.0;
   double grossLoss = 0.0;
   double maxWin = 0.0;
   double maxLoss = 0.0;
   string bestSymbol = "-";
   string worstSymbol = "-";
   
   int historyTotal = OrdersHistoryTotal();
   for(int i = 0; i < historyTotal; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL) continue;
      
      datetime cTime = OrderCloseTime();
      if(cTime < fromTime || cTime > now) continue;
      
      totalTrades++;
      double net = OrderProfit() + OrderSwap() + OrderCommission();
      if(net >= 0.0)
      {
         winCount++;
         grossProfit += net;
         if(net > maxWin)
         {
            maxWin = net;
            bestSymbol = OrderSymbol();
         }
      }
      else
      {
         lossCount++;
         grossLoss += MathAbs(net);
         if(net < maxLoss)
         {
            maxLoss = net;
            worstSymbol = OrderSymbol();
         }
      }
   }
   
   double netTotal = grossProfit - grossLoss;
   double winRate = (totalTrades > 0) ? ((double)winCount / (double)totalTrades * 100.0) : 0.0;
   double profitFactor = (grossLoss > 0.0) ? (grossProfit / grossLoss) : (grossProfit > 0 ? 99.9 : 0.0);
   
   string json = "{";
   json += "\"status\":\"ok\",";
   json += "\"action\":\"GET_REPORT\",";
   json += "\"period\":\"Last 24 Hours\",";
   json += "\"account\":\"" + IntegerToString(AccountNumber()) + "\",";
   json += "\"company\":\"" + Zmq_JsonEscape(AccountCompany()) + "\",";
   json += "\"currency\":\"" + Zmq_JsonEscape(AccountCurrency()) + "\",";
   json += "\"total_trades\":" + IntegerToString(totalTrades) + ",";
   json += "\"win_count\":" + IntegerToString(winCount) + ",";
   json += "\"loss_count\":" + IntegerToString(lossCount) + ",";
   json += "\"win_rate\":" + DoubleToString(winRate, 1) + ",";
   json += "\"gross_profit\":" + DoubleToString(grossProfit, 2) + ",";
   json += "\"gross_loss\":" + DoubleToString(grossLoss, 2) + ",";
   json += "\"profit_factor\":" + DoubleToString(profitFactor, 2) + ",";
   json += "\"net_pl\":" + DoubleToString(netTotal, 2) + ",";
   json += "\"best_symbol\":\"" + Zmq_JsonEscape(bestSymbol) + "\",";
   json += "\"best_profit\":" + DoubleToString(maxWin, 2) + ",";
   json += "\"worst_symbol\":\"" + Zmq_JsonEscape(worstSymbol) + "\",";
   json += "\"worst_loss\":" + DoubleToString(maxLoss, 2) + ",";
   json += "\"ending_balance\":" + DoubleToString(AccountBalance(), 2) + ",";
   json += "\"ending_equity\":" + DoubleToString(AccountEquity(), 2);
   json += "}";
   return json;
}

string Zmq_HandleApplyColors()
{
   int syncedCount = 0;
   long currChart = ChartFirst();
   while(currChart >= 0)
   {
      ChartSetInteger(currChart, CHART_COLOR_BACKGROUND, clrBlack);
      ChartSetInteger(currChart, CHART_COLOR_FOREGROUND, clrWhiteSmoke);
      ChartSetInteger(currChart, CHART_COLOR_GRID, C'25,28,36');
      ChartSetInteger(currChart, CHART_COLOR_CHART_UP, C'38,166,154');
      ChartSetInteger(currChart, CHART_COLOR_CHART_DOWN, C'239,83,80');
      ChartSetInteger(currChart, CHART_COLOR_CANDLE_BULL, C'38,166,154');
      ChartSetInteger(currChart, CHART_COLOR_CANDLE_BEAR, C'239,83,80');
      ChartSetInteger(currChart, CHART_COLOR_CHART_LINE, clrSilver);
      ChartSetInteger(currChart, CHART_MODE, CHART_CANDLES);
      ChartSetInteger(currChart, CHART_SHOW_GRID, false);
      ChartRedraw(currChart);
      syncedCount++;
      currChart = ChartNext(currChart);
   }
   
   return "{\"status\":\"ok\",\"action\":\"APPLY_COLORS\",\"synced_count\":" + IntegerToString(syncedCount) + "}";
}

string Zmq_HandleScreenshot(const string reqJson)
{
   string targetSymbol = Zmq_ExtractJsonString(reqJson, "symbol");
   string tfParam = Zmq_ExtractJsonString(reqJson, "timeframe");
   int width = (int)Zmq_ExtractJsonNumber(reqJson, "width", 1280);
   int height = (int)Zmq_ExtractJsonNumber(reqJson, "height", 720);
   if(width <= 0) width = 1280;
   if(height <= 0) height = 720;
   
   StringTrimLeft(targetSymbol);
   StringTrimRight(targetSymbol);
   StringToUpper(targetSymbol);
   
   if(targetSymbol == "" || targetSymbol == "CURRENT")
      targetSymbol = Symbol();
      
   string matchedSymbol = Zmq_ResolveSymbol(targetSymbol);
   
   ENUM_TIMEFRAMES tf = Zmq_StringToTimeframe(tfParam);
   string tfStr = EnumToString(tf);
   string cleanTfStr = tfStr;
   StringReplace(cleanTfStr, "PERIOD_", "");
   
   string filename = "snap_" + matchedSymbol + "_" + cleanTfStr + ".png";
   
   long targetChartId = -1;
   bool tempChartOpened = false;
   
   if(matchedSymbol == Symbol() && tf == (ENUM_TIMEFRAMES)Period())
   {
      targetChartId = 0;
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
      
      if(targetChartId < 0)
      {
         targetChartId = ChartOpen(matchedSymbol, tf);
         if(targetChartId > 0)
         {
            tempChartOpened = true;
            ChartRedraw(targetChartId);
            Sleep(80);
         }
      }
   }
   
   if(targetChartId < 0)
      targetChartId = 0;
      
   ChartRedraw(targetChartId);
   bool shotOk = ChartScreenShot(targetChartId, filename, width, height, ALIGN_RIGHT);
   
   if(tempChartOpened)
   {
      // Allow MT4 graphics engine to render and flush PNG to disk before closing temporary chart
      for(int w = 0; w < 15; w++)
      {
         if(FileIsExist(filename)) break;
         Sleep(50);
      }
      ChartClose(targetChartId);
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
   
   string json = "{";
   json += "\"status\":\"ok\",";
   json += "\"action\":\"SCREENSHOT\",";
   json += "\"filename\":\"" + filename + "\",";
   json += "\"symbol\":\"" + matchedSymbol + "\",";
   json += "\"timeframe\":\"" + cleanTfStr + "\",";
   json += "\"bid\":" + DoubleToString(bid, symDig) + ",";
   json += "\"ask\":" + DoubleToString(ask, symDig) + ",";
   json += "\"server_time\":\"" + TimeToStr(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "\"";
   json += "}";
   return json;
}

string Zmq_HandleGetBoost()
{
   string json = "{";
   json += "\"status\":\"ok\",";
   json += "\"action\":\"GET_BOOST\",";
   json += "\"server_time\":\"" + TimeToStr(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "\",";
   json += "\"system\":\"SmartAutoTradeEA Institutional Pro v3.0\",";
   json += "\"engine_hz\":4,";
   json += "\"active_orders\":" + IntegerToString(OrdersTotal()) + ",";
   
   double totalLots = 0.0;
   double totalProfit = 0.0;
   for(int i = 0; i < OrdersTotal(); i++)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         totalLots += OrderLots();
         totalProfit += OrderProfit() + OrderSwap() + OrderCommission();
      }
   }
   json += "\"total_lots\":" + DoubleToString(totalLots, 2) + ",";
   json += "\"floating_pl\":" + DoubleToString(totalProfit, 2) + ",";
   json += "\"balance\":" + DoubleToString(AccountBalance(), 2) + ",";
   json += "\"equity\":" + DoubleToString(AccountEquity(), 2) + ",";
   json += "\"free_margin\":" + DoubleToString(AccountFreeMargin(), 2) + ",";
   
   double spreadGBP = Zmq_GetSpreadPoints("GBPUSD");
   double spreadEUR = Zmq_GetSpreadPoints("EURUSD");
   double spreadGOLD = Zmq_GetSpreadPoints("XAUUSD");
   json += "\"spread_gbpusd\":" + DoubleToString(spreadGBP, 1) + ",";
   json += "\"spread_eurusd\":" + DoubleToString(spreadEUR, 1) + ",";
   json += "\"spread_xauusd\":" + DoubleToString(spreadGOLD, 1) + ",";
   
   bool isPaused = false;
   if(GlobalVariableCheck("AutoTrading_Paused"))
      isPaused = (GlobalVariableGet("AutoTrading_Paused") > 0.5);
   json += "\"autotrading_active\":" + (isPaused ? "false" : "true");
   json += "}";
   return json;
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
   if(action == "CLOSE_ALL" || action == "PANIC")
      return Zmq_HandleCloseAll();
   if(action == "CLOSE_SYMBOL" || action == "CLOSE")
      return Zmq_HandleCloseSymbol(reqStr);
   if(action == "CLOSE_HALF" || action == "HALF" || action == "CLOSEHALF")
      return Zmq_HandleCloseHalf(reqStr);
   if(action == "MODIFY_SL")
      return Zmq_HandleModifySL(reqStr);
   if(action == "MODIFY_TP")
      return Zmq_HandleModifyTP(reqStr);
   if(action == "SET_BREAKEVEN" || action == "BREAKEVEN" || action == "BE")
      return Zmq_HandleSetBreakEven(reqStr);
   if(action == "SET_TRAILING" || action == "TRAILING" || action == "TRAIL")
      return Zmq_HandleSetTrailing(reqStr);
   if(action == "PAUSE_BOT" || action == "PAUSE")
      return Zmq_HandlePauseBot();
   if(action == "RESUME_BOT" || action == "RESUME")
      return Zmq_HandleResumeBot();
   if(action == "PING")
      return Zmq_HandlePing();
   if(action == "GET_PROP" || action == "PROP")
      return Zmq_HandleGetProp();
   if(action == "GET_REPORT" || action == "REPORT")
      return Zmq_HandleGetReport();
   if(action == "APPLY_COLORS" || action == "COLORS")
      return Zmq_HandleApplyColors();
   if(action == "SCREENSHOT" || action == "GET_SCREENSHOT")
      return Zmq_HandleScreenshot(reqStr);
   if(action == "GET_BOOST" || action == "BOOST")
      return Zmq_HandleGetBoost();
   if(action == "RESET_SAFEGUARDS" || action == "RESET_PROP" || action == "RESET")
      return Zmq_HandleResetSafeguards();
   if(action == "RELOAD_EA" || action == "RELOAD")
   {
      ChartSetSymbolPeriod(0, Symbol(), (ENUM_TIMEFRAMES)Period());
      return "{\"status\":\"ok\",\"action\":\"RELOAD_EA\",\"message\":\"EA reloaded from disk\"}";
   }
      
   return "{\"status\":\"error\",\"message\":\"Unknown action: " + Zmq_JsonEscape(action) + "\"}";
}

//+------------------------------------------------------------------+
//| Lifecycle Hooks                                                  |
//+------------------------------------------------------------------+
void ZeroMQ_Init(string bindAddress = "tcp://*:5555")
{
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
      EventKillTimer();
      if(!EventSetMillisecondTimer(250))
      {
         EventSetTimer(1);
      }
      PrintFormat("[ZeroMQ Bridge ACTIVE] Listening on %s", bindAddress);
   }
   else
   {
      PrintFormat("[ZeroMQ ERROR] Failed to bind socket to %s (Error: %d)", bindAddress, zmq_errno());
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
   
   for(int iter = 0; iter < 10; iter++)
   {
      uchar reqBuf[];
      ArrayResize(reqBuf, 4096);
      int bytesRecv = zmq_recv(g_zmqSocket.ref(), reqBuf, 4096, 1); // 1 = ZMQ_DONTWAIT
      if(bytesRecv <= 0) break;
      
      string reqStr = CharArrayToString(reqBuf, 0, bytesRecv, CP_UTF8);
      string replyStr = Zmq_ProcessRequest(reqStr);
      
      uchar replyBuf[];
      StringToCharArray(replyStr, replyBuf, 0, WHOLE_ARRAY, CP_UTF8);
      int sendLen = ArraySize(replyBuf) - 1;
      if(sendLen < 0) sendLen = 0;
      
      zmq_send(g_zmqSocket.ref(), replyBuf, sendLen, 0);
   }
}
//+------------------------------------------------------------------+









