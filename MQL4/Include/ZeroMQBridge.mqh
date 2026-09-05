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

int Zmq_GetLotDecimals(double lotStep)
{
   int stepDecimals = 0;
   if(lotStep < 1.0 && lotStep > 0.0)
   {
      string stepStr = DoubleToString(lotStep, 8);
      int dotPos = StringFind(stepStr, ".");
      if(dotPos >= 0)
      {
         int lastNonZero = StringLen(stepStr) - 1;
         while(lastNonZero > dotPos && StringGetCharacter(stepStr, lastNonZero) == '0')
            lastNonZero--;
         stepDecimals = lastNonZero - dotPos;
      }
   }
   if(stepDecimals < 0) stepDecimals = 2;
   return stepDecimals;
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
   while(i < len && (StringGetCharacter(json, i) == ' ' || StringGetCharacter(json, i) == '\t')) i++;
   if(i >= len || StringGetCharacter(json, i) != '\"') return "";
   
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
   while(i < len && (StringGetCharacter(json, i) == ' ' || StringGetCharacter(json, i) == '\t' || StringGetCharacter(json, i) == '\"')) i++;
   
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
   json += "\"chart_symbol\":\"" + Zmq_JsonEscape(Symbol()) + "\",";
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
      
      string orderSym = OrderSymbol();
      int digits = (int)MarketInfo(orderSym, MODE_DIGITS);
      if(digits <= 0) digits = Digits;
      double pl = OrderProfit() + OrderSwap() + OrderCommission();
      
      bool ok = false;
      for(int r = 0; r < 3; r++)
      {
         RefreshRates();
         double closePrice = (type == OP_BUY) ? MarketInfo(orderSym, MODE_BID) : MarketInfo(orderSym, MODE_ASK);
         closePrice = NormalizeDouble(closePrice, digits);
         ResetLastError();
         ok = OrderClose(OrderTicket(), OrderLots(), closePrice, 5, clrOrangeRed);
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
   StringReplace(base, "/", "");
   StringReplace(base, "\\", "");
   StringReplace(base, "-", "");
   StringReplace(base, ".", "");
   StringReplace(base, " ", "");
   
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
      
      int digits = (int)MarketInfo(OrderSymbol(), MODE_DIGITS);
      if(digits <= 0) digits = Digits;
      double pl = OrderProfit() + OrderSwap() + OrderCommission();
      
      bool ok = false;
      for(int retries = 0; retries < 3; retries++)
      {
         RefreshRates();
         double closePrice = (type == OP_BUY) ? MarketInfo(OrderSymbol(), MODE_BID) : MarketInfo(OrderSymbol(), MODE_ASK);
         closePrice = NormalizeDouble(closePrice, digits);
         ResetLastError();
         ok = OrderClose(OrderTicket(), OrderLots(), closePrice, 5, clrOrangeRed);
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
   
   if(ticketParam > 0 && closed == 0)
   {
      string failMsg = (failed > 0) ? ("Failed to close order #" + IntegerToString(ticketParam) + ": " + Zmq_ErrorDescription(GetLastError())) : ("Order #" + IntegerToString(ticketParam) + " not found or already closed");
      return "{\"status\":\"error\",\"action\":\"CLOSE_SYMBOL\",\"symbol\":\"" + targetSymbol + "\",\"ticket\":" + IntegerToString(ticketParam) + ",\"closed_count\":0,\"failed_count\":" + IntegerToString(failed) + ",\"message\":\"" + Zmq_JsonEscape(failMsg) + "\"}";
   }
   
   string json = "{";
   json += "\"status\":\"ok\",";
   json += "\"action\":\"CLOSE_SYMBOL\",";
   json += "\"symbol\":\"" + targetSymbol + "\",";
   json += "\"ticket\":" + IntegerToString(ticketParam) + ",";
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
   int lastErr = 0;
   int total = OrdersTotal();
   
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(ticket > 0 && OrderTicket() != ticket) continue;
      if(symbol != "" && !Zmq_SymbolsMatch(OrderSymbol(), symbol)) continue;
      
      int digits = (int)MarketInfo(OrderSymbol(), MODE_DIGITS);
      if(digits <= 0) digits = Digits;
      double slVal = (newSL > 0.0) ? NormalizeDouble(newSL, digits) : 0.0;
      
      ResetLastError();
      if(OrderModify(OrderTicket(), OrderOpenPrice(), slVal, OrderTakeProfit(), 0, clrGold))
         modified++;
      else
         lastErr = GetLastError();
   }
   
   if(ticket > 0 && modified == 0)
   {
      string desc = (lastErr != 0) ? Zmq_ErrorDescription(lastErr) : "Order not found or parameters unchanged";
      return "{\"status\":\"error\",\"action\":\"MODIFY_SL\",\"modified_count\":0,\"error_code\":" + IntegerToString(lastErr) + ",\"message\":\"" + Zmq_JsonEscape(desc) + "\"}";
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
   int lastErr = 0;
   int total = OrdersTotal();
   
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(ticket > 0 && OrderTicket() != ticket) continue;
      if(symbol != "" && !Zmq_SymbolsMatch(OrderSymbol(), symbol)) continue;
      
      int digits = (int)MarketInfo(OrderSymbol(), MODE_DIGITS);
      if(digits <= 0) digits = Digits;
      double tpVal = (newTP > 0.0) ? NormalizeDouble(newTP, digits) : 0.0;
      
      ResetLastError();
      if(OrderModify(OrderTicket(), OrderOpenPrice(), OrderStopLoss(), tpVal, 0, clrDodgerBlue))
         modified++;
      else
         lastErr = GetLastError();
   }
   
   if(ticket > 0 && modified == 0)
   {
      string desc = (lastErr != 0) ? Zmq_ErrorDescription(lastErr) : "Order not found or parameters unchanged";
      return "{\"status\":\"error\",\"action\":\"MODIFY_TP\",\"modified_count\":0,\"error_code\":" + IntegerToString(lastErr) + ",\"message\":\"" + Zmq_JsonEscape(desc) + "\"}";
   }
   
   return "{\"status\":\"ok\",\"action\":\"MODIFY_TP\",\"modified_count\":" + IntegerToString(modified) + ",\"new_tp\":" + DoubleToString(newTP, 5) + "}";
}

string Zmq_HandleModifyOrder(const string reqJson)
{
   int ticket = (int)Zmq_ExtractJsonNumber(reqJson, "ticket", 0);
   string symbol = Zmq_ExtractJsonString(reqJson, "symbol");
   double newSL = Zmq_ExtractJsonNumber(reqJson, "sl", -1.0);
   double newTP = Zmq_ExtractJsonNumber(reqJson, "tp", -1.0);
   
   if(ticket == 0 && StringToInteger(symbol) > 0)
   {
      ticket = (int)StringToInteger(symbol);
      symbol = "";
   }
   
   int modified = 0;
   int lastErr = 0;
   int total = OrdersTotal();
   
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(ticket > 0 && OrderTicket() != ticket) continue;
      if(symbol != "" && !Zmq_SymbolsMatch(OrderSymbol(), symbol)) continue;
      
      int digits = (int)MarketInfo(OrderSymbol(), MODE_DIGITS);
      if(digits <= 0) digits = Digits;
      
      double setSL = (newSL >= 0.0) ? NormalizeDouble(newSL, digits) : OrderStopLoss();
      double setTP = (newTP >= 0.0) ? NormalizeDouble(newTP, digits) : OrderTakeProfit();
      
      ResetLastError();
      if(OrderModify(OrderTicket(), OrderOpenPrice(), setSL, setTP, 0, clrGold))
         modified++;
      else
         lastErr = GetLastError();
   }
   
   if(ticket > 0 && modified == 0)
   {
      string desc = (lastErr != 0) ? Zmq_ErrorDescription(lastErr) : "Order not found or parameters unchanged";
      return "{\"status\":\"error\",\"action\":\"MODIFY_ORDER\",\"modified_count\":0,\"error_code\":" + IntegerToString(lastErr) + ",\"message\":\"" + Zmq_JsonEscape(desc) + "\"}";
   }
   
   return "{\"status\":\"ok\",\"action\":\"MODIFY_ORDER\",\"modified_count\":" + IntegerToString(modified) + ",\"new_sl\":" + DoubleToString(newSL, 5) + ",\"new_tp\":" + DoubleToString(newTP, 5) + "}";
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
   if(minLot <= 0.0) minLot = 0.01;
   
   int lotDecimals = Zmq_GetLotDecimals(lotStep);
   double reqLots = Zmq_ExtractJsonNumber(reqJson, "lots", 0.0);
   double closeLots = 0.0;
   if(reqLots > 0.0 && reqLots < totalLots)
   {
      closeLots = MathFloor((reqLots / lotStep) + 0.000001) * lotStep;
      if(closeLots < minLot) closeLots = minLot;
   }
   else
   {
      closeLots = MathFloor(((totalLots / 2.0) / lotStep) + 0.000001) * lotStep;
      if(closeLots < minLot) closeLots = totalLots;
   }
   if((totalLots - closeLots) > 0.000001 && (totalLots - closeLots) < minLot)
   {
      closeLots = totalLots;
   }
   closeLots = NormalizeDouble(closeLots, lotDecimals);
   
   int digits = (int)MarketInfo(orderSym, MODE_DIGITS);
   if(digits <= 0) digits = Digits;
   
   bool ok = false;
   int lastErr = 0;
   for(int r = 0; r < 3; r++)
   {
      RefreshRates();
      double closePrice = (type == OP_BUY) ? MarketInfo(orderSym, MODE_BID) : MarketInfo(orderSym, MODE_ASK);
      closePrice = NormalizeDouble(closePrice, digits);
      ResetLastError();
      ok = OrderClose(ticket, closeLots, closePrice, 5, clrOrange);
      if(ok) break;
      lastErr = GetLastError();
      if(lastErr != 135 && lastErr != 136 && lastErr != 137 && lastErr != 138 && lastErr != 146) break;
      Sleep(50);
   }
   
   if(ok)
   {
      double plRatio = (totalLots > 0.0) ? (closeLots / totalLots) : 1.0;
      double estPL = (OrderProfit() + OrderSwap() + OrderCommission()) * plRatio;
      string json = "{";
      json += "\"status\":\"ok\",";
      json += "\"action\":\"CLOSE_HALF\",";
      json += "\"ticket\":" + IntegerToString(ticket) + ",";
      json += "\"closed_lots\":" + DoubleToString(closeLots, lotDecimals) + ",";
      json += "\"remaining_lots\":" + DoubleToString(totalLots - closeLots, lotDecimals) + ",";
      json += "\"realized_pl\":" + DoubleToString(estPL, 2);
      json += "}";
      return json;
   }
   else
   {
      string desc = Zmq_ErrorDescription(lastErr);
      return "{\"status\":\"error\",\"action\":\"CLOSE_HALF\",\"ticket\":" + IntegerToString(ticket) + ",\"error_code\":" + IntegerToString(lastErr) + ",\"message\":\"OrderClose failed: " + Zmq_JsonEscape(desc) + "\"}";
   }
}

//+------------------------------------------------------------------+
//| Zmq_ErrorDescription: Human-readable error dictionary           |
//+------------------------------------------------------------------+
string Zmq_ErrorDescription(int err)
{
   switch(err)
   {
      case 0:    return "No error";
      case 1:    return "No error, but trade result unknown";
      case 2:    return "Common error";
      case 3:    return "Invalid trade parameters";
      case 4:    return "Trade server is busy. Retrying...";
      case 5:    return "Old version of client terminal";
      case 6:    return "No connection with trade server";
      case 7:    return "Not enough rights";
      case 8:    return "Too frequent requests";
      case 9:    return "Malfunctional trade operation";
      case 64:   return "Account disabled";
      case 65:   return "Invalid account";
      case 128:  return "Trade timeout";
      case 129:  return "Invalid price";
      case 130:  return "Invalid stops (SL/TP distance too close or invalid for broker)";
      case 131:  return "Invalid trade volume / lot size";
      case 132:  return "Market is closed (Weekend / Holiday). FX pairs trade Mon-Fri";
      case 133:  return "Trade is disabled by broker";
      case 134:  return "Not enough money / margin to complete trade";
      case 135:  return "Price changed (requote)";
      case 136:  return "Off quotes";
      case 137:  return "Broker is busy";
      case 138:  return "Requote";
      case 139:  return "Order is locked";
      case 140:  return "Long positions only allowed";
      case 141:  return "Too many requests";
      case 145:  return "Modification denied: order is too close to market";
      case 146:  return "Trade context is busy";
      case 147:  return "Expirations are denied by broker";
      case 148:  return "Amount of open and pending orders reached broker limit";
      case 4051: return "Invalid function parameter value";
      case 4062: return "Cannot open file";
      case 4106: return "Unknown symbol";
      case 4107: return "Invalid price parameter for trade function";
      case 4108: return "Invalid ticket";
      case 4109: return "Trade not allowed! Enable 'AutoTrading' button in MT4 toolbar and F7 'Allow live trading'";
      case 4110: return "Longs not allowed";
      case 4111: return "Shorts not allowed";
      default:   return "Broker error code " + IntegerToString(err);
   }
}

//+------------------------------------------------------------------+
//| Zmq_HandleOpenOrder: Market & Pending Order Execution            |
//+------------------------------------------------------------------+
string Zmq_HandleOpenOrder(const string reqJson)
{
   if(!IsExpertEnabled())
   {
      return "{\"status\":\"error\",\"action\":\"OPEN_ORDER\",\"error_code\":4109,\"message\":\"MT4 AutoTrading is OFF! Click the 'AutoTrading' button in the MT4 toolbar.\"}";
   }
   if(!IsTradeAllowed())
   {
      return "{\"status\":\"error\",\"action\":\"OPEN_ORDER\",\"error_code\":4109,\"message\":\"Live trading not allowed! Press F7 -> Common -> Check 'Allow live trading'.\"}";
   }

   string rawSym = Zmq_ExtractJsonString(reqJson, "symbol");
   if(rawSym == "" || rawSym == "CURRENT") rawSym = Symbol();
   string sym = Zmq_ResolveSymbol(rawSym);
   
   // Ensure symbol is active in Market Watch
   SymbolSelect(sym, true);
   
   string cmdStr = Zmq_ExtractJsonString(reqJson, "cmd");
   StringToUpper(cmdStr);
   int cmd = OP_BUY;
   if(cmdStr == "SELL" || cmdStr == "1" || cmdStr == "OP_SELL")
      cmd = OP_SELL;
   else if(cmdStr == "BUY" || cmdStr == "0" || cmdStr == "OP_BUY")
      cmd = OP_BUY;
      
   double lots = Zmq_ExtractJsonNumber(reqJson, "lots", 0.01);
   if(lots <= 0.0) lots = 0.01;
   
   // Normalize lot size to broker specifications
   double minLot  = MarketInfo(sym, MODE_MINLOT);
   double maxLot  = MarketInfo(sym, MODE_MAXLOT);
   double lotStep = MarketInfo(sym, MODE_LOTSTEP);
   if(minLot <= 0.0) minLot = 0.01;
   if(maxLot <= 0.0) maxLot = 100.0;
   if(lotStep <= 0.0) lotStep = 0.01;
   
   lots = MathMax(minLot, MathMin(maxLot, lots));
   lots = MathFloor((lots / lotStep) + 0.000001) * lotStep;
   int lotDecimals = Zmq_GetLotDecimals(lotStep);
   lots = NormalizeDouble(lots, lotDecimals);
   
   int digits = (int)MarketInfo(sym, MODE_DIGITS);
   if(digits <= 0) digits = Digits;
   
   double sl = Zmq_ExtractJsonNumber(reqJson, "sl", 0.0);
   double tp = Zmq_ExtractJsonNumber(reqJson, "tp", 0.0);
   double slPips = Zmq_ExtractJsonNumber(reqJson, "sl_pips", 0.0);
   double tpPips = Zmq_ExtractJsonNumber(reqJson, "tp_pips", 0.0);
   
   double point = MarketInfo(sym, MODE_POINT);
   if(point <= 0.0) point = Point;
   double pipPoint = (digits == 3 || digits == 5) ? point * 10.0 : point;
   if(pipPoint <= 0.0) pipPoint = point;

   int magic = (int)Zmq_ExtractJsonNumber(reqJson, "magic", 8882026);
   int slippage = (int)Zmq_ExtractJsonNumber(reqJson, "slippage", 5);
   string comment = Zmq_ExtractJsonString(reqJson, "comment");
   if(comment == "") comment = "TelegramTrade";
   
   color arrowClr = (cmd == OP_BUY) ? clrLimeGreen : clrTomato;
   
   double reqPrice = Zmq_ExtractJsonNumber(reqJson, "price", 0.0);
   
   int attempts = 0;
   int ticket = -1;
   int lastErr = 0;
   double fillPrice = 0.0;
   double finalSL = sl;
   double finalTP = tp;
   
   while(attempts < 3 && ticket < 0)
   {
      attempts++;
      RefreshRates();
      double ask = MarketInfo(sym, MODE_ASK);
      double bid = MarketInfo(sym, MODE_BID);
      
      if(ask <= 0.0 || bid <= 0.0)
      {
         return "{\"status\":\"error\",\"action\":\"OPEN_ORDER\",\"error_code\":132,\"message\":\"No live quotes for " + Zmq_JsonEscape(sym) + ". Market is Closed (Weekend / Holiday).\"}";
      }
      
      double price = (cmd == OP_BUY) ? ask : bid;
      if(reqPrice > 0.0) price = reqPrice;
      price = NormalizeDouble(price, digits);
      
      // Calculate relative SL/TP if passed as pips
      finalSL = sl;
      finalTP = tp;
      if(slPips > 0.0 && finalSL == 0.0)
      {
         finalSL = (cmd == OP_BUY) ? (price - (slPips * pipPoint)) : (price + (slPips * pipPoint));
      }
      if(tpPips > 0.0 && finalTP == 0.0)
      {
         finalTP = (cmd == OP_BUY) ? (price + (tpPips * pipPoint)) : (price - (tpPips * pipPoint));
      }
      // Auto-detect small pip distances if entered as small integer (e.g. sl=20 on EURUSD 1.08)
      if(finalSL > 0.0 && finalSL < 500.0)
      {
         if((cmd == OP_BUY && finalSL > price) || (price > 0.1 && finalSL < price * 0.2))
         {
            finalSL = (cmd == OP_BUY) ? (price - (finalSL * pipPoint)) : (price + (finalSL * pipPoint));
         }
      }
      if(finalTP > 0.0 && finalTP < 500.0)
      {
         if((cmd == OP_SELL && finalTP > price) || (price > 0.1 && finalTP < price * 0.2))
         {
            finalTP = (cmd == OP_BUY) ? (price + (finalTP * pipPoint)) : (price - (finalTP * pipPoint));
         }
      }
      if(finalSL > 0.0) finalSL = NormalizeDouble(finalSL, digits);
      if(finalTP > 0.0) finalTP = NormalizeDouble(finalTP, digits);
      
      ResetLastError();
      ticket = OrderSend(sym, cmd, lots, price, slippage, finalSL, finalTP, comment, magic, 0, arrowClr);
      
      if(ticket > 0)
      {
         fillPrice = price;
         if(OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES))
            fillPrice = OrderOpenPrice();
         break;
      }
      
      lastErr = GetLastError();
      
      // ECN fallback: If initial OrderSend fails due to invalid stops (Error 130), send 0/0 then modify
      if(lastErr == 130 && (finalSL > 0.0 || finalTP > 0.0))
      {
         RefreshRates();
         price = (cmd == OP_BUY) ? MarketInfo(sym, MODE_ASK) : MarketInfo(sym, MODE_BID);
         ticket = OrderSend(sym, cmd, lots, price, slippage, 0, 0, comment, magic, 0, arrowClr);
         if(ticket > 0)
         {
            fillPrice = price;
            if(OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES))
               fillPrice = OrderOpenPrice();
            bool modRes = OrderModify(ticket, fillPrice, finalSL, finalTP, 0, arrowClr);
            if(!modRes) PrintFormat("[ZeroMQ ECN] OrderModify warning: %d", GetLastError());
            break;
         }
         lastErr = GetLastError();
      }
      
      // Temporary retryable conditions
      if(lastErr == 4 || lastErr == 135 || lastErr == 136 || lastErr == 137 || lastErr == 138 || lastErr == 146)
      {
         RefreshRates();
      }
      else
      {
         break;
      }
   }
   
   if(ticket > 0)
   {
      string json = "{";
      json += "\"status\":\"ok\",";
      json += "\"action\":\"OPEN_ORDER\",";
      json += "\"ticket\":" + IntegerToString(ticket) + ",";
      json += "\"symbol\":\"" + Zmq_JsonEscape(sym) + "\",";
      json += "\"cmd\":\"" + (cmd == OP_BUY ? "BUY" : "SELL") + "\",";
      json += "\"lots\":" + DoubleToString(lots, lotDecimals) + ",";
      json += "\"price\":" + DoubleToString(fillPrice, digits) + ",";
      json += "\"sl\":" + DoubleToString(finalSL, digits) + ",";
      json += "\"tp\":" + DoubleToString(finalTP, digits);
      json += "}";
      return json;
   }
   else
   {
      string desc = Zmq_ErrorDescription(lastErr);
      return "{\"status\":\"error\",\"action\":\"OPEN_ORDER\",\"error_code\":" + IntegerToString(lastErr) + ",\"message\":\"OrderSend failed: " + Zmq_JsonEscape(desc) + "\"}";
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
   int hFlag = FileOpen("autotrade_state.flag", FILE_WRITE|FILE_TXT);
   if(hFlag != INVALID_HANDLE)
   {
      FileWriteString(hFlag, "ACTIVE\nTimestamp=" + IntegerToString((int)TimeCurrent()));
      FileClose(hFlag);
   }
   
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
         int oType = OrderType();
         if(oType == OP_BUY || oType == OP_SELL)
         {
            totalLots += OrderLots();
            totalProfit += OrderProfit() + OrderSwap() + OrderCommission();
         }
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
   if(action == "CLOSE_HALF" || action == "HALF" || action == "CLOSEHALF" || action == "CLOSE_PARTIAL")
      return Zmq_HandleCloseHalf(reqStr);
   if(action == "MODIFY_ORDER" || action == "MODIFY_STOPS")
      return Zmq_HandleModifyOrder(reqStr);
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
   if(action == "OPEN_ORDER" || action == "ORDER_SEND" || action == "BUY" || action == "SELL")
      return Zmq_HandleOpenOrder(reqStr);
   if(action == "CLOSE_TICKET")
      return Zmq_HandleCloseSymbol(reqStr);
   if(action == "DEBUG_CHART")
   {
      string json = "{";
      json += "\"status\":\"ok\",";
      json += "\"dpi\":" + IntegerToString(TerminalInfoInteger(TERMINAL_SCREEN_DPI)) + ",";
      json += "\"chart_w\":" + IntegerToString((int)ChartGetInteger(0, CHART_WIDTH_IN_PIXELS)) + ",";
      json += "\"chart_h\":" + IntegerToString((int)ChartGetInteger(0, CHART_HEIGHT_IN_PIXELS)) + ",";
      json += "\"objects\":[";
      int tot = ObjectsTotal();
      int found = 0;
      for(int i = 0; i < tot; i++)
      {
         string oName = ObjectName(0, i);
         if(StringFind(oName, "SmartEA_HUD_") >= 0)
         {
            if(found > 0) json += ",";
            json += "{\"name\":\"" + oName + "\",";
            json += "\"type\":" + IntegerToString((int)ObjectGetInteger(0, oName, OBJPROP_TYPE)) + ",";
            json += "\"x\":" + IntegerToString((int)ObjectGetInteger(0, oName, OBJPROP_XDISTANCE)) + ",";
            json += "\"y\":" + IntegerToString((int)ObjectGetInteger(0, oName, OBJPROP_YDISTANCE)) + ",";
            json += "\"w\":" + IntegerToString((int)ObjectGetInteger(0, oName, OBJPROP_XSIZE)) + ",";
            json += "\"h\":" + IntegerToString((int)ObjectGetInteger(0, oName, OBJPROP_YSIZE)) + ",";
            json += "\"font\":\"" + ObjectGetString(0, oName, OBJPROP_FONT) + "\",";
            json += "\"fontsize\":" + IntegerToString((int)ObjectGetInteger(0, oName, OBJPROP_FONTSIZE)) + ",";
            json += "\"text\":\"" + Zmq_JsonEscape(ObjectGetString(0, oName, OBJPROP_TEXT)) + "\"}";
            found++;
         }
      }
      json += "]}";
      return json;
   }
   if(action == "PURGE_GUI")
   {
      ObjectsDeleteAll(ChartID(), "SmartEA_HUD_");
      ChartRedraw(ChartID());
      return "{\"status\":\"ok\",\"action\":\"PURGE_GUI\",\"message\":\"HUD objects purged\"}";
   }
   if(action == "RELOAD_EA" || action == "RELOAD")
   {
      ENUM_TIMEFRAMES curTf = (ENUM_TIMEFRAMES)Period();
      ENUM_TIMEFRAMES tempTf = (curTf == PERIOD_H1) ? PERIOD_H4 : PERIOD_H1;
      ChartSetSymbolPeriod(0, Symbol(), tempTf);
      return "{\"status\":\"ok\",\"action\":\"RELOAD_EA\",\"message\":\"Chart timeframe toggled to force EA reload\"}";
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
      uchar reqBuf[8192];
      int bytesRecv = zmq_recv(g_zmqSocket.ref(), reqBuf, 8192, 1); // 1 = ZMQ_DONTWAIT
      if(bytesRecv <= 0) break;
      
      string reqStr = CharArrayToString(reqBuf, 0, bytesRecv, CP_UTF8);
      string replyStr = Zmq_ProcessRequest(reqStr);
      if(replyStr == "") replyStr = "{\"status\":\"error\",\"message\":\"Empty response from EA\"}";
      
      uchar replyBuf[];
      StringToCharArray(replyStr, replyBuf, 0, WHOLE_ARRAY, CP_UTF8);
      int sendLen = ArraySize(replyBuf) - 1;
      if(sendLen < 0) sendLen = 0;
      
      int bytesSent = zmq_send(g_zmqSocket.ref(), replyBuf, sendLen, 0);
      if(bytesSent < 0)
      {
         PrintFormat("[ZeroMQ ERROR] Failed to send reply (Error: %d)", zmq_errno());
      }
   }
}
//+------------------------------------------------------------------+









