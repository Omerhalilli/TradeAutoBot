//+------------------------------------------------------------------+
//|                                               StrategyEngine.mqh |
//|                        Quantitative Confluence Scoring & Signals |
//|                        Compatible with MQL4 and MetaEditor       |
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
   int    cmd;          // OP_BUY, OP_SELL, or -1 (HOLD)
   int    score;        // Final Confluence Score (0 - 10)
   int    buyScore;     // Evaluated Buy Points (0 - 10)
   int    sellScore;    // Evaluated Sell Points (0 - 10)
   double rsi;
   double atr;
   double entryPrice;
   double slPrice;
   double tpPrice;
   double slPips;
   double tpPips;
   string trend;
   bool   valid;
};

//+------------------------------------------------------------------+
//| Quantitative Confluence Scoring (Pure Math & Multi-Timeframe)    |
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
   sig.symbol     = sym;
   sig.cmd        = -1;
   sig.score      = 0;
   sig.buyScore   = 0;
   sig.sellScore  = 0;
   sig.rsi        = 50.0;
   sig.atr        = 0.0;
   sig.entryPrice = 0.0;
   sig.slPrice    = 0.0;
   sig.tpPrice    = 0.0;
   sig.slPips     = 30.0;
   sig.tpPips     = 60.0;
   sig.trend      = "NEUTRAL";
   sig.valid      = false;

   if(iBars(sym, tf) < 50) return sig;

   double pt = MarketInfo(sym, MODE_POINT);
   if(pt <= 0.0) return sig;

   double ask = MarketInfo(sym, MODE_ASK);
   double bid = MarketInfo(sym, MODE_BID);
   if(ask <= 0.0 || bid <= 0.0) return sig;

   int dig = (int)MarketInfo(sym, MODE_DIGITS);
   double pipPt = GetSymbolPipSize(sym);

   // Indicators calculation
   double ema20  = iMA(sym, tf, 20,  0, MODE_EMA, PRICE_CLOSE, 1);
   double ema50  = iMA(sym, tf, 50,  0, MODE_EMA, PRICE_CLOSE, 1);
   double ema200 = iMA(sym, tf, 200, 0, MODE_EMA, PRICE_CLOSE, 1);

   double rsi      = iRSI(sym, tf, 14, PRICE_CLOSE, 1);
   double macd     = iMACD(sym, tf, 12, 26, 9, PRICE_CLOSE, MODE_MAIN, 1);
   double macd_sig = iMACD(sym, tf, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 1);
   double stoch_k  = iStochastic(sym, tf, 5, 3, 3, MODE_SMA, 0, MODE_MAIN, 1);
   double stoch_d  = iStochastic(sym, tf, 5, 3, 3, MODE_SMA, 0, MODE_SIGNAL, 1);
   double atr      = iATR(sym, tf, 14, 1);

   sig.rsi = rsi;
   sig.atr = atr;

   // Volatility Filter: avoid dead chop (< minATRPips) or news volatility spikes (> maxATRPips)
   double atrPips = (pipPt > 0.0) ? (atr / pipPt) : 0.0;
   if(minATRPips > 0.0 && atrPips < minATRPips)
   {
      return sig; // Dead/ranging market
   }
   if(maxATRPips > 0.0 && atrPips > maxATRPips)
   {
      return sig; // Excessive news volatility
   }

   int buyScore  = 0;
   int sellScore = 0;

   // 1. Trend Alignment (0 - 3 points)
   if(ema200 > 0.0)
   {
      if(ema20 > ema50 && ema50 > ema200)      { buyScore += 3;  sig.trend = "STRONG BULLISH"; }
      else if(ema20 > ema50)                   { buyScore += 2;  sig.trend = "BULLISH"; }
      
      if(ema20 < ema50 && ema50 < ema200)      { sellScore += 3; sig.trend = "STRONG BEARISH"; }
      else if(ema20 < ema50)                   { sellScore += 2; sig.trend = "BEARISH"; }
   }
   else
   {
      if(ema20 > ema50) { buyScore += 2;  sig.trend = "BULLISH"; }
      if(ema20 < ema50) { sellScore += 2; sig.trend = "BEARISH"; }
   }

   // 2. RSI Momentum (0 - 2 points)
   if(rsi > 50.0 && rsi < 70.0) buyScore += 2;
   else if(rsi <= 32.0) buyScore += 2; // Oversold exhaustion bounce

   if(rsi < 50.0 && rsi > 30.0) sellScore += 2;
   else if(rsi >= 68.0) sellScore += 2; // Overbought exhaustion reversal

   // 3. MACD Signal Alignment (0 - 2 points)
   if(macd > macd_sig && macd > 0.0) buyScore += 2;
   else if(macd > macd_sig)          buyScore += 1;

   if(macd < macd_sig && macd < 0.0) sellScore += 2;
   else if(macd < macd_sig)          sellScore += 1;

   // 4. Stochastic Cross (0 - 2 points)
   if(stoch_k > stoch_d && stoch_k < 80.0) buyScore += 2;
   if(stoch_k < stoch_d && stoch_k > 20.0) sellScore += 2;

   // 5. Price Action Candlestick (0 - 1 point)
   if(iClose(sym, tf, 1) > iOpen(sym, tf, 1)) buyScore += 1;
   if(iClose(sym, tf, 1) < iOpen(sym, tf, 1)) sellScore += 1;

   if(buyScore > 10)  buyScore  = 10;
   if(sellScore > 10) sellScore = 10;

   sig.buyScore  = buyScore;
   sig.sellScore = sellScore;

   int finalScore = MathMax(buyScore, sellScore);
   sig.score = finalScore;

   // Score threshold: must stand on 6 or past 6 (>= minConfluenceScore)
   if(finalScore < minConfluenceScore)
   {
      return sig; // Insufficient confluence
   }

   if(buyScore >= minConfluenceScore && buyScore > sellScore)
   {
      sig.cmd = OP_BUY;
      sig.entryPrice = ask;
   }
   else if(sellScore >= minConfluenceScore && sellScore > buyScore)
   {
      sig.cmd = OP_SELL;
      sig.entryPrice = bid;
   }
   else
   {
      return sig; // Indecisive or tied
   }

   // Dynamic ATR-based Stop Loss & Take Profit calculation (conservative institutional sizing)
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

   if(sig.cmd == OP_BUY)
   {
      sig.slPrice = NormalizeDouble(sig.entryPrice - slDist, dig);
      sig.tpPrice = NormalizeDouble(sig.entryPrice + tpDist, dig);
   }
   else if(sig.cmd == OP_SELL)
   {
      sig.slPrice = NormalizeDouble(sig.entryPrice + slDist, dig);
      sig.tpPrice = NormalizeDouble(sig.entryPrice - tpDist, dig);
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
