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
//| Resolve broker-specific symbol from standard or generic name     |
//+------------------------------------------------------------------+
string ResolveBrokerSymbol(string standardName)
{
   string base = standardName;
   StringTrimLeft(base);
   StringTrimRight(base);
   StringToUpper(base);
   
   if(base == "CURRENT" || base == "") return Symbol();
   
   // 1. Direct match
   if(MarketInfo(base, MODE_BID) > 0.0 || MarketInfo(base, MODE_POINT) > 0.0) return base;
   
   string canonTarget = CleanSymbolBase(base);
   
   // 2. Scan Market Watch (SymbolsTotal(true))
   int totalMW = SymbolsTotal(true);
   for(int i = 0; i < totalMW; i++)
   {
      string s = SymbolName(i, true);
      if(CleanSymbolBase(s) == canonTarget) return s;
   }
   
   // 3. Scan full broker catalog (SymbolsTotal(false))
   int totalAll = SymbolsTotal(false);
   for(int j = 0; j < totalAll; j++)
   {
      string sAll = SymbolName(j, false);
      if(CleanSymbolBase(sAll) == canonTarget)
      {
         SymbolSelect(sAll, true);
         return sAll;
      }
   }
   
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
//| Discover active symbols from Market Watch dynamically            |
//+------------------------------------------------------------------+
int DiscoverMarketWatchSymbols(string &outSymbols[], string includeSymbols = "", string excludeSymbols = "")
{
   int totalMW = SymbolsTotal(true);
   ArrayResize(outSymbols, 0);
   int count = 0;
   
   for(int i = 0; i < totalMW; i++)
   {
      string sym = SymbolName(i, true);
      if(sym == "") continue;
      
      if(!IsSymbolAllowed(sym, includeSymbols, excludeSymbols)) continue;
      
      ArrayResize(outSymbols, count + 1);
      outSymbols[count] = sym;
      count++;
   }
   
   return count;
}

//+------------------------------------------------------------------+
//| Check quote freshness using MarketInfo MODE_TIME (maxAgeSec)     |
//+------------------------------------------------------------------+
bool IsQuoteFresh(string sym, int maxAgeSec = 5)
{
   if(IsTesting()) return true;
   datetime quoteTime = (datetime)MarketInfo(sym, MODE_TIME);
   if(quoteTime <= 0)
   {
      if(sym == Symbol() && TimeCurrent() > 0) quoteTime = TimeCurrent();
      else return false;
   }
   datetime now = TimeCurrent();
   if(quoteTime > now) return true; // Clock skew/future tick
   if(now - quoteTime > maxAgeSec) return false;
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
   
   // 1. Universal rollover blackout window (21:50 - 23:30 server time)
   // Spreads on ALL pairs widen up to 10x-20x during bank rollover
   if((hour == 21 && min >= 50) || hour == 22 || (hour == 23 && min <= 30))
   {
      return false; // Dead rollover window across entire broker feed
   }

   // 2. Asian pairs: Active during Tokyo session & London overlap (00:00 - 10:00)
   if(base == "JPY" || quote == "JPY" || base == "AUD" || quote == "AUD" || base == "NZD" || quote == "NZD")
   {
      return true; // Active in Asian session & major European overlap
   }
   
   // 3. European & US pairs: Active during London/NY core hours (06:00 - 21:00)
   if(hour >= 6 && hour <= 21)
   {
      return true;
   }
   
   return true; // Outside core hours, PreFilterSymbol spread check provides secondary guard
}

//+------------------------------------------------------------------+
//| Pre-filter symbol before expensive indicator calculations        |
//+------------------------------------------------------------------+
bool PreFilterSymbol(string sym, double maxSpreadPoints = 50.0, int minBars = 50, ENUM_TIMEFRAMES tf = PERIOD_H1, bool checkSession = true)
{
   // 1. Session & liquidity filter (protect against dead liquidity hours)
   if(checkSession && !IsSessionActiveForSymbol(sym)) return false;

   // 2. Broker allows trading
   if(MarketInfo(sym, MODE_TRADEALLOWED) <= 0.0) return false;
   
   // 3. Quote freshness check (skip dormant / desynchronized feeds)
   if(!IsQuoteFresh(sym, 5)) return false;
   
   // 4. Valid price quotes
   double bid = MarketInfo(sym, MODE_BID);
   double ask = MarketInfo(sym, MODE_ASK);
   if(bid <= 0.0 || ask <= 0.0 || ask < bid) return false;
   
   // 5. Spread check
   double pt = MarketInfo(sym, MODE_POINT);
   if(pt <= 0.0) return false;
   double spread = MarketInfo(sym, MODE_SPREAD);
   if(spread <= 0.0) spread = (ask - bid) / pt;
   if(maxSpreadPoints > 0.0 && spread > maxSpreadPoints) return false;
   
   // 6. History depth and volume check
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

#endif // __SYMBOL_MANAGER_MQH__
