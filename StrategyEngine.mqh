//+------------------------------------------------------------------+
//|                                               StrategyEngine.mqh |
//|          Institutional Quantitative Confluence Scoring & Signals |
//|          Comprehensive 0-100 Multi-Indicator Scoring Engine      |
//|          Compatible with MQL4 and MetaEditor                     |
//+------------------------------------------------------------------+
#property copyright "Antigravity Automated Systems"
#property strict

#ifndef __STRATEGY_ENGINE_MQH__
#define __STRATEGY_ENGINE_MQH__

#include <SymbolManager.mqh>

//+------------------------------------------------------------------+
//| Strategy Signal Evaluation Result                                |
//+------------------------------------------------------------------+
struct StrategySignal
{
   string symbol;
   int    cmd;               // OP_BUY, OP_SELL, or -1 (HOLD)
   int    score;             // Final Confluence Score (0 - 10)
   double analysisScore;     // Evaluated 0 - 100 Scale Analysis Points
   double buyScore100;       // Evaluated Buy Points (0 - 100)
   double sellScore100;      // Evaluated Sell Points (0 - 100)
   int    buyScore;          // Confluence score (0 - 10)
   int    sellScore;         // Confluence score (0 - 10)
   double rsi;               // Relative Strength Index (14)
   double macd;              // MACD Main line
   double macdSig;           // MACD Signal line
   double stochK;            // Stochastic %K
   double stochD;            // Stochastic %D
   double adx;               // Average Directional Index (14)
   double atr;               // Average True Range (14)
   double atrPips;           // ATR expressed in pips
   double spreadPoints;      // Current broker spread in points
   double entryPrice;        // Recommended entry price
   double slPrice;           // Protective stop loss price
   double tpPrice;           // Target take profit price
   double slPips;            // Stop loss distance in pips
   double tpPips;            // Take profit distance in pips
   double rrRatio;           // Reward-to-Risk ratio
   string trend;             // Trend regime ("STRONG BULLISH", "BULLISH", "BEARISH", "STRONG BEARISH", "NEUTRAL")
   string pattern;           // Recognized candlestick pattern
   string htfTrend;          // Higher timeframe H4 trend confirmation
   bool   valid;             // Flag indicating if signal is valid and actionable
};

//+------------------------------------------------------------------+
//| Candlestick Pattern Recognition Helper                           |
//+------------------------------------------------------------------+
string DetectCandlePattern(string sym, ENUM_TIMEFRAMES tf, int &candleBuy, int &candleSell)
{
   candleBuy  = 0;
   candleSell = 0;
   string patternName = "NONE";

   if(iBars(sym, tf) < 5) return patternName;

   double o1 = iOpen(sym, tf, 1);
   double c1 = iClose(sym, tf, 1);
   double h1 = iHigh(sym, tf, 1);
   double l1 = iLow(sym, tf, 1);

   double o2 = iOpen(sym, tf, 2);
   double c2 = iClose(sym, tf, 2);
   double h2 = iHigh(sym, tf, 2);
   double l2 = iLow(sym, tf, 2);

   double o3 = iOpen(sym, tf, 3);
   double c3 = iClose(sym, tf, 3);

   double body1 = MathAbs(c1 - o1);
   double range1 = h1 - l1;
   if(range1 <= 0.0) return patternName;

   double upperWick1 = h1 - MathMax(o1, c1);
   double lowerWick1 = MathMin(o1, c1) - l1;

   // Doji Family (body <= 10% of candle range)
   if(body1 <= (0.10 * range1))
   {
      if(lowerWick1 >= (0.65 * range1))
      {
         candleBuy += 4;
         patternName = "DRAGONFLY_DOJI";
         return patternName;
      }
      else if(upperWick1 >= (0.65 * range1))
      {
         candleSell += 4;
         patternName = "GRAVESTONE_DOJI";
         return patternName;
      }
      candleBuy  += 1;
      candleSell += 1;
      patternName = "DOJI";
      return patternName;
   }

   // 1. Bullish Engulfing: previous bearish, current wraps previous body
   if(c2 < o2 && c1 > o1 && c1 >= o2 && o1 <= c2)
   {
      candleBuy += 6;
      patternName = "BULLISH_ENGULFING";
      return patternName;
   }
   // 2. Bearish Engulfing: previous bullish, current wraps previous body
   if(c2 > o2 && c1 < o1 && c1 <= o2 && o1 >= c2)
   {
      candleSell += 6;
      patternName = "BEARISH_ENGULFING";
      return patternName;
   }
   // 3. Hammer: long lower shadow, small real body (> 10% range), small upper shadow
   if(body1 > (0.10 * range1) && lowerWick1 >= (2.0 * body1) && upperWick1 <= (0.20 * range1))
   {
      candleBuy += 5;
      patternName = "HAMMER";
      return patternName;
   }
   // 4. Shooting Star: long upper shadow, small real body (> 10% range), small lower shadow
   if(body1 > (0.10 * range1) && upperWick1 >= (2.0 * body1) && lowerWick1 <= (0.20 * range1))
   {
      candleSell += 5;
      patternName = "SHOOTING_STAR";
      return patternName;
   }
   // 5. Morning Star: 3-bar bullish reversal
   if(c3 < o3 && MathAbs(c2 - o2) < (0.3 * (h2 - l2)) && c1 > o1 && c1 > ((o3 + c3) / 2.0))
   {
      candleBuy += 6;
      patternName = "MORNING_STAR";
      return patternName;
   }
   // 6. Evening Star: 3-bar bearish reversal
   if(c3 > o3 && MathAbs(c2 - o2) < (0.3 * (h2 - l2)) && c1 < o1 && c1 < ((o3 + c3) / 2.0))
   {
      candleSell += 6;
      patternName = "EVENING_STAR";
      return patternName;
   }

   // Directional bar
   if(c1 > o1) candleBuy += 2;
   else if(c1 < o1) candleSell += 2;

   return patternName;
}

//+------------------------------------------------------------------+
//| Comprehensive 0 - 100 Multi-Indicator Confluence Scoring Engine  |
//| Enforces score >= 6 for trade entry, minimum 1.5:1 RR, and ATR   |
//| volatility bounds.                                               |
//+------------------------------------------------------------------+
StrategySignal EvaluateSymbolOpportunity(string sym, 
                                          ENUM_TIMEFRAMES tf = PERIOD_H1, 
                                          int minConfluenceScore = 6,
                                          double minRewardToRisk = 1.5,
                                          double minATRPips = 10.0,
                                          double maxATRPips = 150.0)
{
   StrategySignal sig;
   sig.symbol        = sym;
   sig.cmd           = -1;
   sig.score         = 0;
   sig.analysisScore = 0.0;
   sig.buyScore100   = 0.0;
   sig.sellScore100  = 0.0;
   sig.buyScore      = 0;
   sig.sellScore     = 0;
   sig.rsi           = 50.0;
   sig.macd          = 0.0;
   sig.macdSig       = 0.0;
   sig.stochK        = 50.0;
   sig.stochD        = 50.0;
   sig.adx           = 0.0;
   sig.atr           = 0.0;
   sig.atrPips       = 0.0;
   sig.spreadPoints  = 0.0;
   sig.entryPrice    = 0.0;
   sig.slPrice       = 0.0;
   sig.tpPrice       = 0.0;
   sig.slPips        = 30.0;
   sig.tpPips        = 60.0;
   sig.rrRatio       = 2.0;
   sig.trend         = "NEUTRAL";
   sig.pattern       = "NONE";
   sig.htfTrend      = "NEUTRAL";
   sig.valid         = false;

   if(iBars(sym, tf) < 60) return sig;

   double pt = MarketInfo(sym, MODE_POINT);
   if(pt <= 0.0) return sig;

   double ask = MarketInfo(sym, MODE_ASK);
   double bid = MarketInfo(sym, MODE_BID);
   if(ask <= 0.0 || bid <= 0.0) return sig;

   int dig = (int)MarketInfo(sym, MODE_DIGITS);
   double pipPt = GetSymbolPipSize(sym);
   sig.spreadPoints = (ask - bid) / pt;

   // -----------------------------------------------------------------
   // Core Indicator Calculations on Primary Timeframe (H1)
   // -----------------------------------------------------------------
   double ema20  = iMA(sym, tf, 20,  0, MODE_EMA, PRICE_CLOSE, 1);
   double ema50  = iMA(sym, tf, 50,  0, MODE_EMA, PRICE_CLOSE, 1);
   double ema200 = iMA(sym, tf, 200, 0, MODE_EMA, PRICE_CLOSE, 1);
   double close1 = iClose(sym, tf, 1);

   double rsi      = iRSI(sym, tf, 14, PRICE_CLOSE, 1);
   double macd     = iMACD(sym, tf, 12, 26, 9, PRICE_CLOSE, MODE_MAIN, 1);
   double macd_sig = iMACD(sym, tf, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 1);
   double macdPrev = iMACD(sym, tf, 12, 26, 9, PRICE_CLOSE, MODE_MAIN, 2);
   double macdPrevSig = iMACD(sym, tf, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 2);

   double stoch_k  = iStochastic(sym, tf, 5, 3, 3, MODE_SMA, 0, MODE_MAIN, 1);
   double stoch_d  = iStochastic(sym, tf, 5, 3, 3, MODE_SMA, 0, MODE_SIGNAL, 1);

   double adx_main = iADX(sym, tf, 14, PRICE_CLOSE, MODE_MAIN, 1);
   double adx_plus = iADX(sym, tf, 14, PRICE_CLOSE, MODE_PLUSDI, 1);
   double adx_minus= iADX(sym, tf, 14, PRICE_CLOSE, MODE_MINUSDI, 1);

   double bb_up  = iBands(sym, tf, 20, 2, 0, PRICE_CLOSE, MODE_UPPER, 1);
   double bb_low = iBands(sym, tf, 20, 2, 0, PRICE_CLOSE, MODE_LOWER, 1);
   double bb_mid = iBands(sym, tf, 20, 2, 0, PRICE_CLOSE, MODE_MAIN, 1);

   double atr = iATR(sym, tf, 14, 1);

   sig.rsi     = NormalizeDouble(rsi, 2);
   sig.macd    = NormalizeDouble(macd, 6);
   sig.macdSig = NormalizeDouble(macd_sig, 6);
   sig.stochK  = NormalizeDouble(stoch_k, 2);
   sig.stochD  = NormalizeDouble(stoch_d, 2);
   sig.adx     = NormalizeDouble(adx_main, 2);
   sig.atr     = atr;

   // Volatility metrics: normalize ATR in pips for scoring and stop sizing
   double atrPips = (pipPt > 0.0) ? (atr / pipPt) : 0.0;
   sig.atrPips = NormalizeDouble(atrPips, 1);

   // -----------------------------------------------------------------
   // 0 - 100 INSTITUTIONAL SCORING MODULES
   // -----------------------------------------------------------------
   double buyPoints  = 0.0;
   double sellPoints = 0.0;

   // =================================================================
   // 1. TREND ALIGNMENT & ADX STRENGTH (0 - 25 points)
   // =================================================================
   if(ema200 > 0.0)
   {
      if(ema20 > ema50 && ema50 > ema200)
      {
         buyPoints += 12.0;
         sig.trend = "STRONG BULLISH";
      }
      else if(ema20 > ema50)
      {
         buyPoints += 8.0;
         sig.trend = "BULLISH";
      }

      if(ema20 < ema50 && ema50 < ema200)
      {
         sellPoints += 12.0;
         sig.trend = "STRONG BEARISH";
      }
      else if(ema20 < ema50)
      {
         sellPoints += 8.0;
         sig.trend = "BEARISH";
      }

      if(close1 > ema200) buyPoints += 4.0;
      if(close1 < ema200) sellPoints += 4.0;
   }
   else
   {
      if(ema20 > ema50) { buyPoints += 8.0;  sig.trend = "BULLISH"; }
      if(ema20 < ema50) { sellPoints += 8.0; sig.trend = "BEARISH"; }
   }

   // ADX Trend Strength Confirmation (0 - 9 points)
   if(adx_main >= 25.0)
   {
      // Strong trend regime active
      if(adx_plus > adx_minus) buyPoints += 7.0;
      else if(adx_minus > adx_plus) sellPoints += 7.0;

      if(adx_main >= 35.0)
      {
         if(adx_plus > adx_minus) buyPoints += 2.0;
         else if(adx_minus > adx_plus) sellPoints += 2.0;
      }
   }
   else if(adx_main >= 20.0)
   {
      if(adx_plus > adx_minus) buyPoints += 4.0;
      else if(adx_minus > adx_plus) sellPoints += 4.0;
   }

   // =================================================================
   // 2. MOMENTUM & OSCILLATORS (0 - 25 points)
   // =================================================================
   // RSI Momentum (0 - 10 points)
   if(rsi > 50.0 && rsi < 68.0) buyPoints += 10.0;
   else if(rsi <= 32.0)         buyPoints += 8.0; // Oversold bounce setup
   else if(rsi >= 45.0 && rsi <= 50.0) buyPoints += 4.0;

   if(rsi < 50.0 && rsi > 32.0) sellPoints += 10.0;
   else if(rsi >= 68.0)         sellPoints += 8.0; // Overbought exhaustion setup
   else if(rsi >= 50.0 && rsi <= 55.0) sellPoints += 4.0;

   // MACD Crossover & Alignment (0 - 8 points)
   if(macd > macd_sig && macd > 0.0)
   {
      buyPoints += 8.0;
   }
   else if(macd > macd_sig)
   {
      buyPoints += 5.0;
   }
   if(macd > macd_sig && macdPrev <= macdPrevSig) buyPoints += 2.0; // Fresh crossover

   if(macd < macd_sig && macd < 0.0)
   {
      sellPoints += 8.0;
   }
   else if(macd < macd_sig)
   {
      sellPoints += 5.0;
   }
   if(macd < macd_sig && macdPrev >= macdPrevSig) sellPoints += 2.0; // Fresh crossover

   // Stochastic Alignment (0 - 7 points)
   if(stoch_k > stoch_d && stoch_k < 80.0)
   {
      buyPoints += 5.0;
      if(stoch_k < 30.0) buyPoints += 2.0; // Oversold turning up
   }
   if(stoch_k < stoch_d && stoch_k > 20.0)
   {
      sellPoints += 5.0;
      if(stoch_k > 70.0) sellPoints += 2.0; // Overbought turning down
   }

   // =================================================================
   // 3. VOLATILITY & BOLLINGER BANDS (0 - 15 points)
   // =================================================================
   if(bb_up > bb_low && bb_up > 0.0)
   {
      // Proximity to lower band with bullish reaction
      double low1 = iLow(sym, tf, 1);
      double high1 = iHigh(sym, tf, 1);

      if(low1 <= bb_low && close1 > bb_low) buyPoints += 8.0; // Strong bounce off lower band
      else if(close1 > bb_mid) buyPoints += 4.0;

      if(high1 >= bb_up && close1 < bb_up) sellPoints += 8.0; // Strong rejection from upper band
      else if(close1 < bb_mid && low1 > bb_low) sellPoints += 4.0; // Bearish side of bands without conflicting lower bounce
   }

   // ATR expansion check (0 - 5 points)
   double atrShort = iATR(sym, tf, 7, 1);
   if(atrShort > atr)
   {
      buyPoints  += 2.5;
      sellPoints += 2.5;
   }

   // =================================================================
   // 4. KEY SUPPORT / RESISTANCE & DAILY PIVOTS (0 - 15 points)
   // =================================================================
   // Swing High/Low lookback (50 bars)
   int highBar = iHighest(sym, tf, MODE_HIGH, 50, 1);
   int lowBar  = iLowest(sym,  tf, MODE_LOW,  50, 1);
   double swingHigh = (highBar != -1) ? iHigh(sym, tf, highBar) : close1;
   double swingLow  = (lowBar  != -1) ? iLow(sym,  tf, lowBar)  : close1;

   double proximityDist = (atr > 0.0) ? (atr * 1.2) : (pipPt * 20.0);
   if(MathAbs(close1 - swingLow) <= proximityDist && close1 > swingLow)
   {
      buyPoints += 7.0; // Rebound from swing support
   }
   if(MathAbs(close1 - swingHigh) <= proximityDist && close1 < swingHigh)
   {
      sellPoints += 7.0; // Rebound from swing resistance
   }

   // Daily Pivot Points
   double dHigh  = iHigh(sym, PERIOD_D1, 1);
   double dLow   = iLow(sym,  PERIOD_D1, 1);
   double dClose = iClose(sym, PERIOD_D1, 1);
   if(dHigh > 0.0 && dLow > 0.0 && dClose > 0.0)
   {
      double pivotP  = (dHigh + dLow + dClose) / 3.0;
      double pivotS1 = (2.0 * pivotP) - dHigh;
      double pivotR1 = (2.0 * pivotP) - dLow;

      if(close1 > pivotP && MathAbs(close1 - pivotP) <= proximityDist) buyPoints += 8.0;
      else if(close1 > pivotS1 && MathAbs(close1 - pivotS1) <= proximityDist) buyPoints += 8.0;

      if(close1 < pivotP && MathAbs(close1 - pivotP) <= proximityDist) sellPoints += 8.0;
      else if(close1 < pivotR1 && MathAbs(close1 - pivotR1) <= proximityDist) sellPoints += 8.0;
   }

   // =================================================================
   // 5. PRICE ACTION, CANDLESTICK PATTERNS & VOLUME / VSA (0 - 10 points)
   // =================================================================
   int candleBuy = 0;
   int candleSell = 0;
   sig.pattern = DetectCandlePattern(sym, tf, candleBuy, candleSell);
   buyPoints  += candleBuy;
   sellPoints += candleSell;

   // Tick Volume expansion (0 - 3 points)
   long vol1 = iVolume(sym, tf, 1);
   long vol2 = iVolume(sym, tf, 2);
   if(vol1 > vol2 && vol1 > 0)
   {
      if(close1 > iOpen(sym, tf, 1)) buyPoints += 3.0;
      else if(close1 < iOpen(sym, tf, 1)) sellPoints += 3.0;
   }

   // =================================================================
   // 6. MULTI-TIMEFRAME (MTF) CONFLUENCE (0 - 10 points)
   // =================================================================
   if(iBars(sym, PERIOD_H4) >= 50)
   {
      double h4_ema50  = iMA(sym, PERIOD_H4, 50,  0, MODE_EMA, PRICE_CLOSE, 1);
      double h4_ema200 = iMA(sym, PERIOD_H4, 200, 0, MODE_EMA, PRICE_CLOSE, 1);
      double h4_close  = iClose(sym, PERIOD_H4, 1);

      if(h4_ema50 > h4_ema200 && h4_close > h4_ema50)
      {
         buyPoints += 10.0;
         sig.htfTrend = "BULLISH";
      }
      else if(h4_ema50 > h4_ema200)
      {
         buyPoints += 6.0;
         sig.htfTrend = "MODERATE BULLISH";
      }
      else if(h4_ema50 < h4_ema200 && h4_close < h4_ema50)
      {
         sellPoints += 10.0;
         sig.htfTrend = "BEARISH";
      }
      else if(h4_ema50 < h4_ema200)
      {
         sellPoints += 6.0;
         sig.htfTrend = "MODERATE BEARISH";
      }
   }

   // Cap points to maximum 100
   if(buyPoints > 100.0)  buyPoints = 100.0;
   if(sellPoints > 100.0) sellPoints = 100.0;

   sig.buyScore100  = NormalizeDouble(buyPoints, 1);
   sig.sellScore100 = NormalizeDouble(sellPoints, 1);

   // Map 0-100 scale to 0-10 Confluence Score (60 points = score 6, 70 = 7, etc.)
   int buyScore10  = (int)MathRound(buyPoints / 10.0);
   int sellScore10 = (int)MathRound(sellPoints / 10.0);
   if(buyScore10 > 10)  buyScore10 = 10;
   if(sellScore10 > 10) sellScore10 = 10;

   sig.buyScore  = buyScore10;
   sig.sellScore = sellScore10;

   double finalAnalysis = MathMax(buyPoints, sellPoints);
   int finalScore       = MathMax(buyScore10, sellScore10);

   sig.analysisScore = NormalizeDouble(finalAnalysis, 1);
   sig.score         = finalScore;

   // -----------------------------------------------------------------
   // Dynamic ATR-based Stop Loss & Take Profit Calculation
   // (Calculated for telemetry, monitoring, and prospective execution)
   // -----------------------------------------------------------------
   double slDist = (atr > 0.0) ? (atr * 1.5) : (pipPt * 30.0);
   double tpDist = (atr > 0.0) ? (atr * 3.0) : (pipPt * 60.0);

   if(pipPt > 0.0)
   {
      sig.slPips = NormalizeDouble(slDist / pipPt, 1);
      sig.tpPips = NormalizeDouble(tpDist / pipPt, 1);
   }
   if(sig.slPips < 15.0) { sig.slPips = 20.0; slDist = sig.slPips * pipPt; }

   // Enforce strict minimum Reward-to-Risk ratio (default 1.5:1)
   if(minRewardToRisk < 1.0) minRewardToRisk = 1.5;
   if(tpDist < slDist * minRewardToRisk)
   {
      tpDist = slDist * minRewardToRisk;
      if(pipPt > 0.0) sig.tpPips = NormalizeDouble(tpDist / pipPt, 1);
   }
   if(sig.tpPips < 30.0) { sig.tpPips = 30.0; tpDist = sig.tpPips * pipPt; }

   sig.rrRatio = (sig.slPips > 0.0) ? NormalizeDouble(sig.tpPips / sig.slPips, 2) : 2.0;

   // Directional assignment & prospective stops
   long symTradeMode = SymbolInfoInteger(sym, SYMBOL_TRADE_MODE);
   if(buyScore10 > sellScore10)
   {
      sig.entryPrice = ask;
      sig.slPrice = NormalizeDouble(ask - slDist, dig);
      sig.tpPrice = NormalizeDouble(ask + tpDist, dig);
      if(buyScore10 >= minConfluenceScore && symTradeMode != SYMBOL_TRADE_MODE_SHORTONLY && symTradeMode != SYMBOL_TRADE_MODE_DISABLED && symTradeMode != SYMBOL_TRADE_MODE_CLOSEONLY)
      {
         sig.cmd = OP_BUY;
      }
   }
   else if(sellScore10 > buyScore10)
   {
      sig.entryPrice = bid;
      sig.slPrice = NormalizeDouble(bid + slDist, dig);
      sig.tpPrice = NormalizeDouble(bid - tpDist, dig);
      if(sellScore10 >= minConfluenceScore && symTradeMode != SYMBOL_TRADE_MODE_LONGONLY && symTradeMode != SYMBOL_TRADE_MODE_DISABLED && symTradeMode != SYMBOL_TRADE_MODE_CLOSEONLY)
      {
         sig.cmd = OP_SELL;
      }
   }
   else
   {
      sig.entryPrice = (ask + bid) / 2.0;
      sig.slPrice = NormalizeDouble(sig.entryPrice - slDist, dig);
      sig.tpPrice = NormalizeDouble(sig.entryPrice + tpDist, dig);
      sig.cmd = -1; // Tied direction
   }

   // Volatility gate for actionable trade execution
   if(minATRPips > 0.0 && atrPips < minATRPips)
   {
      sig.valid = false;
      return sig; // Insufficient ATR volatility for trade entry
   }
   if(maxATRPips > 0.0 && atrPips > maxATRPips)
   {
      sig.valid = false;
      return sig; // Excessive volatility spike
   }

   // Confluence Threshold: must stand on 6 or past 6 (>= minConfluenceScore)
   if(finalScore < minConfluenceScore || sig.cmd < 0)
   {
      sig.valid = false;
      return sig; // Insufficient confluence for trade execution
   }

   // Mandatory stops verification: never allow 0 SL or 0 TP
   if(sig.slPrice <= 0.0 || sig.tpPrice <= 0.0)
   {
      sig.valid = false;
      return sig;
   }

   sig.valid = true;
   return sig;
}

#endif // __STRATEGY_ENGINE_MQH__
