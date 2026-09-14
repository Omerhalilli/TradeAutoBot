//+------------------------------------------------------------------+
//|                                                SymbolManager.mqh |
//|                         Institutional Symbol Discovery & Filters |
//|                         Compatible with MQL4 and MetaEditor      |
//+------------------------------------------------------------------+
#property copyright "Antigravity Automated Systems"
#property strict

#ifndef __SYMBOL_MANAGER_MQH__
#define __SYMBOL_MANAGER_MQH__

//+------------------------------------------------------------------+
//| Strip broker prefixes/suffixes and normalize canonical base      |
//+------------------------------------------------------------------+
string CleanSymbolBase(string sym)
{
   string s = sym;
   StringToUpper(s);
   StringTrimLeft(s);
   StringTrimRight(s);
   
   // Direct aliases
   if(StringFind(s, "GOLD") >= 0) return "XAUUSD";
   if(StringFind(s, "SILVER") >= 0) return "XAGUSD";
   if(StringFind(s, "USOIL") >= 0 || StringFind(s, "WTI") >= 0 || StringFind(s, "CRUDE") >= 0) return "USOIL";
   if(StringFind(s, "UKOIL") >= 0 || StringFind(s, "BRENT") >= 0) return "UKOIL";
   if(StringFind(s, "BTC") >= 0) return "BTCUSD";
   
   // Check known forex & metal currency combinations (23x23)
   string currs[23] = {"EUR", "GBP", "USD", "AUD", "NZD", "CAD", "CHF", "JPY", 
                       "XAU", "XAG", "BTC", "ETH", "TRY", "ZAR", "SEK", "NOK", 
                       "MXN", "SGD", "HKD", "PLN", "CNH", "HUF", "CZK"};
   for(int i = 0; i < 23; i++)
   {
      for(int j = 0; j < 23; j++)
      {
         if(i == j) continue;
         string pair = currs[i] + currs[j];
         if(StringFind(s, pair) >= 0)
         {
            return pair;
         }
      }
   }
   
   // Filter out special characters
   string cleaned = "";
   int len = StringLen(s);
   for(int k = 0; k < len; k++)
   {
      ushort ch = StringGetCharacter(s, k);
      if((ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9'))
      {
         cleaned = cleaned + ShortToString(ch);
      }
   }
   
   // If stripped string length >= 6, return first 6 characters
   if(StringLen(cleaned) >= 6)
      return StringSubstr(cleaned, 0, 6);
      
   return (cleaned != "") ? cleaned : s;
}

//+------------------------------------------------------------------+
//| Exact canonical symbol comparison                                |
//+------------------------------------------------------------------+
bool AreSymbolsMatching(string sym1, string sym2)
{
   return (CleanSymbolBase(sym1) == CleanSymbolBase(sym2));
}

//+------------------------------------------------------------------+
//| Verify broker allows active trading on the symbol                |
//+------------------------------------------------------------------+
bool IsSymbolTradeAllowed(string sym)
{
   if(sym == "") return false;
   if(MarketInfo(sym, MODE_TRADEALLOWED) <= 0.0) return false;
   
   double bid = MarketInfo(sym, MODE_BID);
   double ask = MarketInfo(sym, MODE_ASK);
   if(bid <= 0.0 && ask <= 0.0) return false;
   
   long tradeMode = SymbolInfoInteger(sym, SYMBOL_TRADE_MODE);
   if(tradeMode == SYMBOL_TRADE_MODE_DISABLED || tradeMode == SYMBOL_TRADE_MODE_CLOSEONLY)
   {
      return false;
   }
   
   return true;
}

//+------------------------------------------------------------------+
//| Extract broker prefix and suffix from current chart symbol       |
//+------------------------------------------------------------------+
string GetChartBrokerSuffix()
{
   string chartSym = Symbol();
   string canon = CleanSymbolBase(chartSym);
   if(canon == "") return "";
   int pos = StringFind(chartSym, canon);
   if(pos >= 0)
   {
      int suffixStart = pos + StringLen(canon);
      if(suffixStart < StringLen(chartSym))
      {
         return StringSubstr(chartSym, suffixStart);
      }
   }
   return "";
}

string GetChartBrokerPrefix()
{
   string chartSym = Symbol();
   string canon = CleanSymbolBase(chartSym);
   if(canon == "") return "";
   int pos = StringFind(chartSym, canon);
   if(pos > 0)
   {
      return StringSubstr(chartSym, 0, pos);
   }
   return "";
}

//+------------------------------------------------------------------+
//| Resolve broker-specific symbol from standard or generic name     |
//| Prioritizes trade-allowed symbols across Market Watch and Catalog|
//+------------------------------------------------------------------+
string ResolveBrokerSymbol(string standardName)
{
   string base = standardName;
   StringTrimLeft(base);
   StringTrimRight(base);
   StringToUpper(base);
   
   if(base == "CURRENT" || base == "") return Symbol();
   
   string canonTarget = CleanSymbolBase(base);
   
   // 1. Try using the current chart symbol's broker prefix/suffix
   string chartSuffix = GetChartBrokerSuffix();
   string chartPrefix = GetChartBrokerPrefix();
   string chartCand = chartPrefix + canonTarget + chartSuffix;
   if(IsSymbolTradeAllowed(chartCand))
   {
      SymbolSelect(chartCand, true);
      return chartCand;
   }
   
   // 2. Scan Market Watch (SymbolsTotal(true)) for trade-allowed canonical match
   int totalMW = SymbolsTotal(true);
   for(int i = 0; i < totalMW; i++)
   {
      string s = SymbolName(i, true);
      if(CleanSymbolBase(s) == canonTarget && IsSymbolTradeAllowed(s))
      {
         return s;
      }
   }
   
   // 3. Direct match if trade is allowed
   if(IsSymbolTradeAllowed(base))
   {
      SymbolSelect(base, true);
      return base;
   }
   
   // 4. Try known broker suffix variants
   string commonSuffixes[9] = {"_min", ".pro", ".ecn", "m", "_m", ".r", ".a", "micro", ".raw"};
   for(int k = 0; k < 9; k++)
   {
      string cand = canonTarget + commonSuffixes[k];
      if(MarketInfo(cand, MODE_BID) > 0.0 || MarketInfo(cand, MODE_POINT) > 0.0)
      {
         SymbolSelect(cand, true);
         if(IsSymbolTradeAllowed(cand)) return cand;
      }
   }
   
   // 5. Scan full broker catalog (SymbolsTotal(false)) for trade-allowed match
   int totalAll = SymbolsTotal(false);
   for(int j = 0; j < totalAll; j++)
   {
      string sAll = SymbolName(j, false);
      if(CleanSymbolBase(sAll) == canonTarget && IsSymbolTradeAllowed(sAll))
      {
         SymbolSelect(sAll, true);
         return sAll;
      }
   }
   
   // 6. Secondary fallback: check Market Watch for candidate with quotes
   for(int m = 0; m < totalMW; m++)
   {
      string sMW = SymbolName(m, true);
      if(CleanSymbolBase(sMW) == canonTarget && (MarketInfo(sMW, MODE_BID) > 0.0 || MarketInfo(sMW, MODE_POINT) > 0.0))
      {
         return sMW;
      }
   }

   // 7. Final fallback: direct base if quotes exist, else standardName
   if(MarketInfo(base, MODE_BID) > 0.0 || MarketInfo(base, MODE_POINT) > 0.0) return base;

   return standardName;
}

//+------------------------------------------------------------------+
//| Wildcard string matcher supporting '*' and '?' (Iterative)       |
//+------------------------------------------------------------------+
bool MatchesPattern(string text, string pattern)
{
   string t = text;
   string p = pattern;
   StringToUpper(t);
   StringToUpper(p);
   StringTrimLeft(t);
   StringTrimRight(t);
   StringTrimLeft(p);
   StringTrimRight(p);
   
   int tLen = StringLen(t);
   int pLen = StringLen(p);
   
   int tIdx = 0, pIdx = 0;
   int starIdx = -1, matchIdx = 0;
   
   while(tIdx < tLen)
   {
      if(pIdx < pLen && (StringGetCharacter(p, pIdx) == '?' || StringGetCharacter(p, pIdx) == StringGetCharacter(t, tIdx)))
      {
         pIdx++;
         tIdx++;
      }
      else if(pIdx < pLen && StringGetCharacter(p, pIdx) == '*')
      {
         starIdx = pIdx;
         matchIdx = tIdx;
         pIdx++;
      }
      else if(starIdx != -1)
      {
         pIdx = starIdx + 1;
         matchIdx++;
         tIdx = matchIdx;
      }
      else
      {
         return false;
      }
   }
   
   while(pIdx < pLen && StringGetCharacter(p, pIdx) == '*')
   {
      pIdx++;
   }
   
   return (pIdx == pLen);
}

//+------------------------------------------------------------------+
//| Verify if a symbol passes structured whitelist and blacklist     |
//+------------------------------------------------------------------+
bool IsSymbolAllowed(string sym, string includeSymbols = "", string excludeSymbols = "")
{
   string rawSym = sym;
   StringToUpper(rawSym);
   string canon = CleanSymbolBase(sym);
   
   // 1. Blacklist check
   string excl = excludeSymbols;
   StringTrimLeft(excl);
   StringTrimRight(excl);
   if(StringLen(excl) > 0)
   {
      int start = 0;
      int len = StringLen(excl);
      while(start < len)
      {
         int comma = StringFind(excl, ",", start);
         string token = (comma >= 0) ? StringSubstr(excl, start, comma - start) : StringSubstr(excl, start);
         StringTrimLeft(token);
         StringTrimRight(token);
         StringToUpper(token);
         start = (comma >= 0) ? comma + 1 : len;
         
         if(StringLen(token) == 0) continue;
         if(MatchesPattern(rawSym, token) || MatchesPattern(canon, token))
         {
            return false; // Excluded!
         }
      }
   }
   
   // 2. Whitelist check
   string incl = includeSymbols;
   StringTrimLeft(incl);
   StringTrimRight(incl);
   if(StringLen(incl) > 0)
   {
      bool matched = false;
      int start = 0;
      int len = StringLen(incl);
      while(start < len)
      {
         int comma = StringFind(incl, ",", start);
         string token = (comma >= 0) ? StringSubstr(incl, start, comma - start) : StringSubstr(incl, start);
         StringTrimLeft(token);
         StringTrimRight(token);
         StringToUpper(token);
         start = (comma >= 0) ? comma + 1 : len;
         
         if(StringLen(token) == 0) continue;
         if(MatchesPattern(rawSym, token) || MatchesPattern(canon, token))
         {
            matched = true;
            break;
         }
      }
      if(!matched) return false; // Not in whitelist
   }
   
   return true;
}

//+------------------------------------------------------------------+
//| Calculate required margin for minimum lot on a symbol            |
//+------------------------------------------------------------------+
double GetSymbolMinLotMargin(string sym)
{
   double minLot = MarketInfo(sym, MODE_MINLOT);
   if(minLot <= 0.0) minLot = 0.01;
   
   // Priority 1: Built-in MT4 AccountFreeMarginCheck (authoritative broker calculation)
   ResetLastError();
   double freeMarginBefore = AccountFreeMargin();
   if(freeMarginBefore > 0.0)
   {
      double check = AccountFreeMarginCheck(sym, OP_BUY, minLot);
      int err = GetLastError();
      if(err == 0 && check > 0.0 && check < freeMarginBefore)
      {
         return (freeMarginBefore - check);
      }
   }

   // Priority 2: MODE_MARGINREQUIRED
   double marginPerLot = MarketInfo(sym, MODE_MARGINREQUIRED);
   if(marginPerLot > 0.0)
   {
      return (marginPerLot * minLot);
   }

   // Priority 3: Mathematical Currency-Aware Margin Approximation
   double contractSize = MarketInfo(sym, MODE_LOTSIZE);
   if(contractSize <= 0.0) contractSize = 100000.0;
   double leverage = (double)AccountLeverage();
   if(leverage <= 0.0) leverage = 100.0;

   string canon = CleanSymbolBase(sym);
   string baseCurr = (StringLen(canon) >= 3) ? StringSubstr(canon, 0, 3) : "USD";
   string quoteCurr = (StringLen(canon) >= 6) ? StringSubstr(canon, 3, 3) : "USD";
   string accCurr = AccountCurrency();
   if(accCurr == "") accCurr = "USD";

   double notionalInBase = contractSize * minLot;
   double marginReq = notionalInBase / leverage;

   if(baseCurr != accCurr)
   {
      if(quoteCurr == accCurr)
      {
         double price = MarketInfo(sym, MODE_ASK);
         if(price <= 0.0) price = MarketInfo(sym, MODE_BID);
         if(price > 0.0) marginReq = (notionalInBase * price) / leverage;
      }
      else
      {
         string convSym = baseCurr + accCurr;
         string brokerConv = ResolveBrokerSymbol(convSym);
         double convP = MarketInfo(brokerConv, MODE_BID);
         if(convP > 0.0)
         {
            marginReq = (notionalInBase * convP) / leverage;
         }
      }
   }

   return marginReq;
}

//+------------------------------------------------------------------+
//| Check if symbol is tradeable and affordable for account balance  |
//+------------------------------------------------------------------+
bool IsSymbolTradeableForBalance(string sym, double maxMarginUsagePct = 50.0)
{
   // 1. Basic broker trade permission
   if(!IsSymbolTradeAllowed(sym)) return false;
   
   // 2. Account balance and free margin sanity
   double freeMargin = AccountFreeMargin();
   double balance    = AccountBalance();
   if(freeMargin <= 0.0 || balance <= 0.0) return false;
   
   double minLot = MarketInfo(sym, MODE_MINLOT);
   if(minLot <= 0.0) minLot = 0.01;
   
   // 3. Margin affordability check:
   // marginReq = MarketInfo(sym, MODE_MARGINREQUIRED) * MarketInfo(sym, MODE_MINLOT);
   double marginReq = GetSymbolMinLotMargin(sym);
   double maxAffordableMargin = freeMargin * (maxMarginUsagePct / 100.0);
   
   // If marginReq > AccountFreeMargin() * (MaxMarginUsagePct / 100.0) or marginReq > AccountBalance(), cannot trade
   if(marginReq > maxAffordableMargin || marginReq > balance)
   {
      return false;
   }
   
   // 4. Validate AccountFreeMarginCheck directly if available
   ResetLastError();
   double testCheck = AccountFreeMarginCheck(sym, OP_BUY, minLot);
   int err = GetLastError();
   if(err == 134 || (testCheck <= 0.0 && freeMargin > 0.0 && err == 0))
   {
      return false;
   }
   
   return true;
}

//+------------------------------------------------------------------+
//| Discover active symbols from Market Watch dynamically            |
//| Filters by whitelist, blacklist, tradeability, and margin buffer |
//+------------------------------------------------------------------+
int DiscoverMarketWatchSymbols(string &outSymbols[], string includeSymbols = "", string excludeSymbols = "", double maxMarginUsagePct = 50.0)
{
   int totalMW = SymbolsTotal(true);
   ArrayResize(outSymbols, 0);
   int count = 0;
   
   for(int i = 0; i < totalMW; i++)
   {
      string sym = SymbolName(i, true);
      if(sym == "") continue;
      
      if(!IsSymbolAllowed(sym, includeSymbols, excludeSymbols)) continue;
      if(!IsSymbolTradeAllowed(sym)) continue;
      if(!IsSymbolTradeableForBalance(sym, maxMarginUsagePct)) continue;
      
      ArrayResize(outSymbols, count + 1);
      outSymbols[count] = sym;
      count++;
   }

   // If Market Watch has very few symbols (< 5) or count == 0, scan broker catalog
   if(count < 5)
   {
      int totalAll = SymbolsTotal(false);
      int maxCatalog = (totalAll > 200) ? 200 : totalAll;
      for(int j = 0; j < maxCatalog; j++)
      {
         string catSym = SymbolName(j, false);
         if(catSym == "") continue;
         
         bool exists = false;
         for(int k = 0; k < count; k++)
         {
            if(outSymbols[k] == catSym) { exists = true; break; }
         }
         if(exists) continue;
         
         if(!IsSymbolAllowed(catSym, includeSymbols, excludeSymbols)) continue;
         if(!IsSymbolTradeAllowed(catSym)) continue;
         if(!IsSymbolTradeableForBalance(catSym, maxMarginUsagePct)) continue;
         
         SymbolSelect(catSym, true);
         ArrayResize(outSymbols, count + 1);
         outSymbols[count] = catSym;
         count++;
         if(count >= 50) break;
      }
   }
   
   return count;
}

//+------------------------------------------------------------------+
//| Check quote freshness using MarketInfo MODE_TIME (maxAgeSec)     |
//+------------------------------------------------------------------+
bool IsQuoteFresh(string sym, int maxAgeSec = 180)
{
   if(IsTesting()) return true;
   datetime quoteTime = (datetime)MarketInfo(sym, MODE_TIME);
   if(quoteTime <= 0)
   {
      if(sym == Symbol() && TimeCurrent() > 0) quoteTime = TimeCurrent();
      else
      {
         datetime lastBar = iTime(sym, PERIOD_H1, 0);
         if(lastBar > 0) quoteTime = lastBar;
         else return false;
      }
   }
   datetime now = TimeCurrent();
   if(quoteTime > now) return true; // Clock skew/future tick
   if(now - quoteTime > maxAgeSec)
   {
      if(now - quoteTime <= 300) return true;
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| Deconstruct symbol into base and quote currencies                |
//+------------------------------------------------------------------+
void GetSymbolCurrencies(string sym, string &baseCurr, string &quoteCurr)
{
   string canon = CleanSymbolBase(sym);
   if(StringLen(canon) >= 6)
   {
      baseCurr  = StringSubstr(canon, 0, 3);
      quoteCurr = StringSubstr(canon, 3, 3);
   }
   else
   {
      baseCurr  = canon;
      quoteCurr = "USD";
   }
}

//+------------------------------------------------------------------+
//| Session & Liquidity filter per symbol class                      |
//+------------------------------------------------------------------+
bool IsSessionActiveForSymbol(string sym)
{
   datetime now = TimeCurrent();
   int hour = TimeHour(now);
   int min  = TimeMinute(now);
   string base = "", quote = "";
   GetSymbolCurrencies(sym, base, quote);
   
   // 1. Universal rollover blackout window (21:45 - 23:45 server time)
   // Spreads on ALL pairs widen up to 10x-20x during bank rollover
   if((hour == 21 && min >= 45) || hour == 22 || (hour == 23 && min <= 45))
   {
      return false; // Dead rollover window across entire broker feed
   }

   // 2. Asian / JPY pairs: Active during Tokyo session & London/NY overlap (00:00 - 19:00 server time)
   // Avoids dead liquidity / spread blowout transition between 19:00 and 23:45
   if(base == "JPY" || quote == "JPY" || base == "AUD" || quote == "AUD" || base == "NZD" || quote == "NZD")
   {
      if(hour >= 0 && hour <= 19) return true;
      return false;
   }
   
   // 3. European & US pairs: Active during London/NY core hours (06:00 - 21:00)
   if(hour >= 6 && hour <= 21)
   {
      return true;
   }
   
   return false; // Outside active liquid session hours
}

//+------------------------------------------------------------------+
//| Pre-filter symbol before expensive indicator calculations        |
//+------------------------------------------------------------------+
bool PreFilterSymbol(string sym, double maxSpreadPoints = 40.0, int minBars = 205, ENUM_TIMEFRAMES tf = PERIOD_H1, bool checkSession = true, double maxMarginUsagePct = 50.0)
{
   // 1. Session & liquidity filter (protect against dead liquidity hours)
   if(checkSession && !IsSessionActiveForSymbol(sym)) return false;

   // 2. Broker allows trading and direction check
   if(!IsSymbolTradeAllowed(sym)) return false;

   // 3. Margin affordability for account balance
   if(!IsSymbolTradeableForBalance(sym, maxMarginUsagePct)) return false;
   
   // 4. Quote freshness check (skip dormant / desynchronized feeds)
   if(!IsQuoteFresh(sym, 5)) return false;
   
   // 5. Valid price quotes
   double bid = MarketInfo(sym, MODE_BID);
   double ask = MarketInfo(sym, MODE_ASK);
   if(bid <= 0.0 || ask <= 0.0 || ask < bid) return false;
   
   // 6. Spread check
   double pt = MarketInfo(sym, MODE_POINT);
   if(pt <= 0.0) return false;
   double spread = MarketInfo(sym, MODE_SPREAD);
   if(spread <= 0.0) spread = (ask - bid) / pt;
   if(maxSpreadPoints > 0.0 && spread > maxSpreadPoints) return false;
   
   // 7. History depth and volume check
   if(iBars(sym, tf) < minBars) return false;
   if(iVolume(sym, tf, 0) == 0 && (sym != Symbol() || Volume[0] == 0))
   {
      // Dormant tick volume on current bar
      // Allow if previous bar has healthy volume
      if(iVolume(sym, tf, 1) < 5) return false;
   }
   
   return true;
}

//+------------------------------------------------------------------+
//| Dynamic per-symbol pip point calculation (JPY vs 5-digit vs Gold)|
//+------------------------------------------------------------------+
double GetSymbolPipSize(string sym)
{
   int digits = (int)MarketInfo(sym, MODE_DIGITS);
   double pt  = MarketInfo(sym, MODE_POINT);
   if(pt <= 0.0)
   {
      if(digits == 3) return 0.01;
      if(digits == 5) return 0.0001;
      return 0.01;
   }
   if(digits == 3 || digits == 5) return pt * 10.0;
   return pt;
}

//+------------------------------------------------------------------+
//| Dynamic pip dollar value per lot                                 |
//+------------------------------------------------------------------+
double GetSymbolPipValue(string sym)
{
   double tickValue = MarketInfo(sym, MODE_TICKVALUE);
   double tickSize  = MarketInfo(sym, MODE_TICKSIZE);
   double pipSize   = GetSymbolPipSize(sym);
   double pt        = MarketInfo(sym, MODE_POINT);
   
   if(tickSize <= 0.0)  tickSize  = (pt > 0.0) ? pt : 0.0001;
   if(tickValue <= 0.0) tickValue = 10.0;
   
   double pipVal = tickValue * (pipSize / tickSize);
   if(pipVal <= 0.0) pipVal = 10.0;
   return pipVal;
}

//+------------------------------------------------------------------+
//| Dynamic Market Watch Discovery: Discover, filter, and synchronize|
//| all active, tradable instruments directly from MT4 Market Watch  |
//+------------------------------------------------------------------+
int GetMarketWatchTradableSymbols(string &outSymbols[], double maxSpreadPoints = 150.0)
{
   ArrayResize(outSymbols, 0);
   int total = SymbolsTotal(true); // Market Watch selected symbols
   
   for(int i = 0; i < total; i++)
   {
      string sym = SymbolName(i, true);
      if(StringLen(sym) == 0) continue;
      
      // Filter 1: Must have trading allowed (excludes greyed-out pairs like EURAZN, USDAZN)
      if(!MarketInfo(sym, MODE_TRADEALLOWED)) continue;
      
      long tradeMode = SymbolInfoInteger(sym, SYMBOL_TRADE_MODE);
      if(tradeMode == SYMBOL_TRADE_MODE_DISABLED || tradeMode == SYMBOL_TRADE_MODE_CLOSEONLY) continue;

      // Price sanity check
      double bid = MarketInfo(sym, MODE_BID);
      double ask = MarketInfo(sym, MODE_ASK);
      if(bid <= 0.0 || ask <= 0.0 || ask < bid) continue;
      
      // Filter 2: Spread sanity check (exclude illiquid pairs with spread > 150 points / 15 pips)
      double sp = MarketInfo(sym, MODE_SPREAD);
      double pt = MarketInfo(sym, MODE_POINT);
      if(sp <= 0.0 && pt > 0.0) sp = (ask - bid) / pt;
      if(sp <= 0.0 || (maxSpreadPoints > 0.0 && sp > maxSpreadPoints)) continue;
      
      // Filter 3: Exotic blacklist filter
      string upperSym = sym;
      StringToUpper(upperSym);
      if(StringFind(upperSym, "AZN") >= 0 || StringFind(upperSym, "TRY") >= 0 || 
         StringFind(upperSym, "RUB") >= 0 || StringFind(upperSym, "ZAR") >= 0) continue;
      
      // Add valid tradable symbol with its native broker suffix (e.g., CADJPY_min)
      int sz = ArraySize(outSymbols);
      ArrayResize(outSymbols, sz + 1);
      outSymbols[sz] = sym;
   }

   // Safety fallback: if Market Watch yielded 0 symbols, add active chart symbol if tradable
   if(ArraySize(outSymbols) == 0)
   {
      string curSym = Symbol();
      if(MarketInfo(curSym, MODE_TRADEALLOWED) > 0.0)
      {
         ArrayResize(outSymbols, 1);
         outSymbols[0] = curSym;
      }
   }

   return ArraySize(outSymbols);
}

#endif // __SYMBOL_MANAGER_MQH__
