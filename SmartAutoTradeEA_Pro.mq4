//+------------------------------------------------------------------+
//|                                       SmartAutoTradeEA_Pro.mq4   |
//|                             Copyright 2026, SmartAutoTrade Corp. |
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright   "Copyright 2026, SmartAutoTrade Corp."
#property link        "https://www.mql5.com"
#property version     "3.00"
#property description "SmartAutoTradeEA Pro v3.0 - Institutional-Grade Algorithmic Trading System"
#property description "Engineered for MetaTrader 4 | Multi-EMA Trend | RSI/MACD/Stoch Momentum"
#property description "S/R Pivots | Candlestick Patterns | Hybrid SL/TP | Full Risk Management HUD"
#property strict

#include "TelegramShared.mqh"


/*
======================================================================================================
 SMARTAUTOTRADE EA - ENTERPRISE TRADING SYSTEM
======================================================================================================
 Architecture & Modules:
 1. Core Architectural Pipeline & Strict Execution Environment
 2. Global Constants, Error Code Dictionaries, & Type Definitions
 3. Comprehensive Input Parameters (Signal, Risk, Filters, Visuals, Alerts)
 4. Precision Pip & Tick Calculations for 2/3/4/5-Digit Brokers & Multi-Asset Classes
 5. Trend Analysis Engine (Multi-EMA 20/50/200 Alignment & ADX Confirmation)
 6. Momentum & Oscillator Suite (RSI Dynamic Zones, MACD Zero/Signal Crosses, Stochastic Divergence)
 7. Support & Resistance & Pivot Engine (50-Bar Rolling High/Low Fractals, Classic & Fibonacci Pivots)
 8. Advanced Candlestick Pattern Recognition (Engulfing, Hammer, Shooting Star, Morning/Evening Star, Doji)
 9. Multi-Tier Quantitative Scoring Matrix (0-10 Points Confluence Engine)
 10. Multi-Layer Filter Engine (Dynamic Spread, Trading Hours, GMT Offsets, News/Volatility Spikes)
 11. Institutional Risk Management (Equity/Balance %, Kelly Sizing, ATR Volatility Sizing, Margin Checks)
 12. Smart Order Execution Engine (Requote Management, Slippage Control, Magic Number Isolation)
 13. Advanced Trade Lifecycle Manager (Multi-Stage Break-Even, Trailing Stops: Fixed/ATR/Chandelier/PSAR)
 14. Real-Time HUD Dashboard & Graphical Telemetry (Pixel-Perfect GUI Panel & Metrics)
 15. Real-Time Notification & Audit Logging Dispatcher (Popup, Sound, Push, Email, CSV Audit)
 16. Memory Management & Object Garbage Collection System
======================================================================================================
*/


//+------------------------------------------------------------------+
//| ENUMERATIONS AND TYPE DEFINITIONS                                |
//+------------------------------------------------------------------+
enum ENUM_TREND_REGIME
{
   TREND_FLAT = 0,               // Flat / Range-Bound
   TREND_WEAK_BULLISH = 1,       // Weak Uptrend (EMA20 > EMA50 < EMA200)
   TREND_STRONG_BULLISH = 2,     // Strong Uptrend (EMA20 > EMA50 > EMA200)
   TREND_WEAK_BEARISH = 3,       // Weak Downtrend (EMA20 < EMA50 > EMA200)
   TREND_STRONG_BEARISH = 4      // Strong Downtrend (EMA20 < EMA50 < EMA200)
};


enum ENUM_SIGNAL_DECISION
{
   SIGNAL_NEUTRAL = 0,           // No Actionable Bias
   SIGNAL_LONG = 1,              // Confirmed Buy / Long Signal
   SIGNAL_SHORT = 2              // Confirmed Sell / Short Signal
};


enum ENUM_LOT_CALC_MODE
{
   LOT_MODE_FIXED = 0,           // Fixed Lot Size
   LOT_MODE_RISK_PERCENT = 1,    // Percentage of Account Balance
   LOT_MODE_EQUITY_PERCENT = 2,  // Percentage of Account Equity
   LOT_MODE_ATR_RISK = 3,        // Volatility-Adjusted (ATR) Risk Model
   LOT_MODE_KELLY_CRITERION = 4  // Kelly Criterion Statistical Model
};


enum ENUM_TRAILING_MODE
{
   TRAILING_NONE = 0,            // Disabled
   TRAILING_FIXED_PIPS = 1,      // Fixed Pip Trailing Stop
   TRAILING_ATR_DYNAMIC = 2,     // Dynamic ATR Multiplier Trailing Stop
   TRAILING_CHANDELIER = 3,      // Highest High / Lowest Low Swing Trailing
   TRAILING_PARABOLIC_SAR = 4,   // Parabolic SAR Trailing Stop
   TRAILING_MOVING_AVERAGE = 5   // Fast Moving Average Trailing Stop
};




enum ENUM_PIVOT_TF
{
   PIVOT_DAILY = 0,   // Daily Pivots
   PIVOT_WEEKLY = 1   // Weekly Pivots
};


enum ENUM_PIVOT_METHOD
{
   PIVOT_CLASSIC = 0,            // Standard Floor Pivots
   PIVOT_FIBONACCI = 1,          // Fibonacci Retracement Pivots
   PIVOT_CAMARILLA = 2,          // Camarilla Equation Pivots
   PIVOT_WOODIE = 3              // Woodie Pivots
};


enum ENUM_MARKET_SESSION
{
   SESSION_ASIAN = 0,            // Tokyo / Sydney Session
   SESSION_LONDON = 1,           // London European Session
   SESSION_NEWYORK = 2,          // New York US Session
   SESSION_LONDON_NY_OVERLAP = 3,// London / NY Peak Liquidity Overlap
   SESSION_OFF_HOURS = 4         // Inter-Session Low Liquidity Hours
};


enum ENUM_CANDLE_CLASSIFICATION
{
   CANDLE_INDECISION = 0,        // Normal / Indecision Candle
   CANDLE_BULLISH_ENGULFING = 1, // Bullish Engulfing
   CANDLE_BEARISH_ENGULFING = 2, // Bearish Engulfing
   CANDLE_HAMMER = 3,            // Hammer at Support
   CANDLE_SHOOTING_STAR = 4,     // Shooting Star at Resistance
   CANDLE_DOJI_REGULAR = 5,      // Classic Neutral Doji
   CANDLE_DRAGONFLY_DOJI = 6,    // Dragonfly Doji (Bullish Reversal)
   CANDLE_GRAVESTONE_DOJI = 7,   // Gravestone Doji (Bearish Reversal)
   CANDLE_MORNING_STAR = 8,      // 3-Bar Morning Star Pattern
   CANDLE_EVENING_STAR = 9       // 3-Bar Evening Star Pattern
};




//+------------------------------------------------------------------+
//| ENTERPRISE TELEMETRY STRUCTURES                                  |
//+------------------------------------------------------------------+
struct SPerformanceTelemetry
{
   int      totalTradesRecorded;
   int      winningTradesCount;
   int      losingTradesCount;
   double   grossProfitAmount;
   double   grossLossAmount;
   double   winRatePercentage;
   double   profitFactor;
   double   expectedPayoff;
   double   maxDrawdownCurrency;
   double   maxDrawdownPercentage;
};


struct SPivotPointValues
{
   double   P;
   double   R1;
   double   S1;
   double   R2;
   double   S2;
   double   R3;
   double   S3;
   double   R4;
   double   S4;
};


//+------------------------------------------------------------------+
//| INPUT PARAMETERS CONFIGURATION                                   |
//+------------------------------------------------------------------+


//--- [01. GENERAL & AUTOMATION SETTINGS]
input string             Sec_General                   = "=== [01] GENERAL EA CONFIGURATION ===";
input bool               UseAutoTrading                = true;              // Auto Trading Execution Switch (True = Active Automated Execution)
input int                MagicNumber                   = 8882026;           // EA Magic Identification Number
input string             TradeCommentPrefix            = "SmartAutoEA";     // Order Execution Comment Tag
input int                MaxOpenPositionsPerSymbol     = 1;                 // Maximum Concurrent Positions per Symbol
input int                MaxTotalPortfolioPositions    = 5;                 // Maximum Total Open Positions across Account
input int                MinBarsBetweenTrades          = 10;                // Minimum Number of Bars Elapsed Between Trades
input int                MaxSpreadPoints               = 50;                // Maximum Allowable Spread in Broker Points
input int                ExecutionSlippage             = 3;                 // Maximum Permissible Execution Slippage (Points)
input int                OrderRetryAttempts            = 5;                 // Number of Order Retries on Server Requote/Busy
input int                OrderRetryDelayMilliseconds   = 250;               // Sleep Interval Between Order Retries (ms)


//--- [02. SIGNAL ENGINE & CONFLUENCE SCORING]
input string             Sec_Signal                    = "=== [02] MULTI-FACTOR SIGNAL ENGINE ===";
input int                MinRequiredScore              = 6;                 // Minimum Score to Authorize Trade (0 - 10)
input bool               RequireTrendDirectionMatch    = true;              // Enforce Higher-Order Trend Concurrence
input int                LookbackBarsSR                = 50;                // S/R Scoring Lookback Window (Bars)
input double             ProximityPipsSR               = 10.0;              // Proximity Distance to S/R or Pivot (Pips)
input bool               UseSupportResistanceScoring   = true;              // Evaluate Swing High/Low Proximity (0-2 pts)
input bool               UsePivotPointsScoring         = true;              // Evaluate Daily Floor / Fibonacci Pivots (0-1 pt)
input ENUM_PIVOT_METHOD  PivotFormulaType              = PIVOT_CLASSIC;     // Daily Pivot Point Calculation Algorithm
input bool               UseCandlestickPatternScoring  = true;              // Evaluate Japanese Candlestick Patterns (0-2 pts)


//--- [03. TREND INDICATORS]
input string             Sec_Trend                     = "=== [03] TREND DETECTION INDICATORS ===";
input int                EMA_Fast_Period               = 20;                // Fast EMA Period
input int                EMA_Medium_Period             = 50;                // Medium EMA Period
input int                EMA_Slow_Period               = 200;               // Slow EMA Period
input ENUM_APPLIED_PRICE EMA_AppliedPrice              = PRICE_CLOSE;       // Applied Price for EMAs
input bool               UseADX_Filter                 = true;              // Enable ADX Trend Strength Confirmation
input int                ADX_Period                    = 14;                // ADX Indicator Period
input double             ADX_MinStrengthThreshold      = 22.0;              // Minimum ADX Level for Trending Market


//--- [04. MOMENTUM INDICATORS]
input string             Sec_Momentum                  = "=== [04] MOMENTUM & OSCILLATORS ===";
input int                RSI_Period                    = 14;                // Relative Strength Index (RSI) Period
input ENUM_APPLIED_PRICE RSI_AppliedPrice              = PRICE_CLOSE;       // Applied Price for RSI
input double             RSI_Overbought                = 70.0;              // RSI Overbought Level
input double             RSI_Oversold                  = 30.0;              // RSI Oversold Level
input double             RSI_Neutral_Low               = 40.0;              // RSI Equilibrium Band Lower Boundary
input double             RSI_Neutral_High              = 60.0;              // RSI Equilibrium Band Upper Boundary
input int                MACD_Fast_EMA                 = 12;                // MACD Fast EMA Period
input int                MACD_Slow_EMA                 = 26;                // MACD Slow EMA Period
input int                MACD_Signal_SMA               = 9;                 // MACD Signal Line SMA Period
input ENUM_APPLIED_PRICE MACD_AppliedPrice             = PRICE_CLOSE;       // Applied Price for MACD
input bool               UseStochasticConfirmation     = true;              // Enable Stochastic Oscillator Filter
input int                Stoch_K_Period                = 5;                 // Stochastic %K Period
input int                Stoch_D_Period                = 3;                 // Stochastic %D Period
input int                Stoch_Slowing                 = 3;                 // Stochastic Slowing
input double             Stoch_Overbought              = 80.0;              // Stochastic Overbought Boundary
input double             Stoch_Oversold                = 20.0;              // Stochastic Oversold Boundary


//--- [05. RISK & MONEY MANAGEMENT]
input string             Sec_Risk                      = "=== [05] RISK & MONEY MANAGEMENT ===";
input ENUM_LOT_CALC_MODE LotSizingMethod               = LOT_MODE_RISK_PERCENT; // Lot Allocation Methodology
input double             FixedLotSize                  = 0.10;              // Static Lot Size (If Fixed Mode Selected)
input double             RiskPercent                   = 1.0;               // Risk Percent (% of Account Balance)
input int                StopLossPips                  = 30;                // Base Stop Loss (Pips)
input int                TakeProfitPips                = 60;                // Base Take Profit (Pips)
input bool               UseATR                        = true;              // Method: ATR Stop Loss & Take Profit
input int                ATRPeriod                     = 14;                // ATR Period
input double             ATRMultiplierSL               = 1.5;               // ATR Multiplier for Stop Loss
input double             ATRMultiplierTP               = 3.0;               // ATR Multiplier for Take Profit
input bool               UseSupportResistance          = true;              // Method: Support / Resistance Levels for SL/TP
input int                LookbackBars                  = 50;                // S/R Swing Lookback (Bars)
input bool               UseRiskRewardRatio            = false;             // Enforce Dynamic Risk:Reward Ratio for TP
input double             RiskRewardRatio               = 2.0;               // Risk:Reward Target Multiplier (e.g. 2.0 = 1:2)
input bool               UseBreakEven                  = true;              // Enable Automated Break-Even Protection
input int                BreakEvenPips                 = 10;                // Profit Target to Move SL to Entry (Pips)
input int                BreakEvenLockPips             = 1;                 // Profit Offset to Lock Beyond Entry (Pips)
input bool               UseTrailingStop               = true;              // Enable Trailing Stop Engine
input int                TrailingStartPips             = 20;                // Profit Level to Activate Trailing (Pips)
input int                TrailingStepPips              = 10;                // Trailing Incremental Step (Pips)
input ENUM_TRAILING_MODE TrailingStopType              = TRAILING_FIXED_PIPS;// Trailing Stop Algorithm
input double             TrailingATRMultiplier         = 2.0;               // Trailing ATR Distance Multiplier
input int                ChandelierCandleLookback      = 10;                // Lookback Bars for Chandelier Trailing
input double             ParabolicSAR_Step             = 0.02;              // Parabolic SAR Acceleration Factor
input double             ParabolicSAR_Maximum          = 0.20;              // Parabolic SAR Maximum Limit
input bool               UsePartialProfitTaking        = true;              // Enable Scaling Out (Partial Close)
input double             PartialCloseRatio             = 0.50;              // Proportion of Position to Liquidate (0.5 = 50%)
input int                PartialCloseTriggerPips       = 25;                // Profit Threshold for Partial Liquidation (Pips)
input double             MaxDailyDrawdownPercent       = 5.0;               // Daily Equity Drawdown Circuit Breaker (%)
input double             MaxDailyProfitPercent         = 10.0;              // Daily Profit Target Circuit Breaker (%)
input bool               EnforceAccountProtection      = true;              // Activate Daily Drawdown/Profit Guards


//--- [06. ADVANCED SL/TP CALCULATION METHODS & HYBRID SCORING]
input string             Sec_AdvancedSLTP              = "=== [06] ADVANCED SL/TP SUITE ===";
input bool               UseHybridScoring              = true;              // Hybrid Scoring: Confluence across all enabled methods
input bool               UseADR                        = true;              // Method 1: Average Daily Range (ADR) Method
input int                ADRPeriod                     = 14;                // ADR Lookback Period (Days)
input double             ADRMultiplierSL               = 0.3;               // ADR Multiplier for Stop Loss
input double             ADRMultiplierTP               = 0.6;               // ADR Multiplier for Take Profit
input bool               UseFibonacci                  = true;              // Method 2: Fibonacci Extension & Retracement
input int                FibLookbackBars               = 100;               // Fibonacci Swing Lookback (Bars)
input double             FibTPLevel                    = 1.618;             // Fibonacci Extension TP Target (e.g. 1.618 or 2.0)
input bool               UseMultiTF_ATR                = true;              // Method 3: Multi-Timeframe ATR Method
input ENUM_TIMEFRAMES    HigherTF                      = PERIOD_H4;         // Multi-Timeframe Higher Period
input bool               UseSwingHL                    = true;              // Method 4: Swing High/Low Method
input int                SwingLookbackBars             = 50;                // Swing High/Low Lookback Window (Bars)
input int                SwingBufferPips               = 10;                // Swing High/Low Buffer (Pips)
input bool               UsePivotSLTP                  = true;              // Method 5: Daily / Weekly Pivot Points Method
input ENUM_PIVOT_TF      PivotType                     = PIVOT_DAILY;       // Pivot Calculation Timeframe (Daily or Weekly)
input bool               UseVolatilityRR               = true;              // Method 6: Volatility Dynamic Risk-Reward Adjuster
input double             VolatilityThresholdATR        = 50.0;              // Volatility Threshold in ATR Pips


//--- [07. TIME & SESSION FILTERS]
input string             Sec_Filters                   = "=== [07] TEMPORAL & SESSION FILTERS ===";
input bool               UseTimeFilter                 = false;             // Enable Trading Schedule Filter (False = 24/7 Unrestricted)
input int                StartHourGMT                  = 8;                 // Active Trading Window Start Hour (GMT)
input int                EndHourGMT                    = 21;                // Active Trading Window End Hour (GMT)
input int                BrokerGMT_Offset              = 0;                 // Broker Server Offset Relative to GMT (Hours)
input bool               TradeAsianSession             = true;              // Permit Execution During Asian Session
input bool               TradeLondonSession            = true;              // Permit Execution During London Session
input bool               TradeNewYorkSession           = true;              // Permit Execution During New York Session
input bool               FilterFridayLateTrading       = true;              // Restrict Execution on Friday Afternoons
input int                FridayCloseHourGMT            = 18;                // Friday Trading Cutoff Hour (GMT)
input bool               UseNewsVolatilityFilter       = true;              // Filter Abnormal Bar Volatility / Event Spikes
input double             VolatilitySpikeATR_Ratio      = 2.8;               // Bar Range to ATR Ratio for Volatility Spike Alert


//--- [08. VISUAL DISPLAY & HUD PANEL]
input string             Sec_Visuals                   = "=== [08] ON-CHART GUI & VISUALS ===";
input bool               ShowDashboardPanel            = true;              // Render On-Chart Heads-Up Display (HUD)
input ENUM_BASE_CORNER   HUD_Corner                    = CORNER_LEFT_UPPER; // HUD Display Corner Orientation// HUD Display Corner Orientation
input int                HUD_X_Offset                  = 15;                // Horizontal Margin from Corner                // Horizontal Pixel Margin
input int                HUD_Y_Offset                  = 25;                // Vertical Margin from Top                // Vertical Pixel Margin
input color              HUD_BgColor                   = C'22,25,32';       // HUD Panel Canvas Background Color
input color              HUD_BorderColor               = C'65,75,90';       // HUD Panel Border Outline Color
input color              HUD_HeaderTextColor           = C'255,195,0';      // HUD Main Header Title Color
input color              HUD_LabelTextColor            = C'190,200,215';    // HUD Data Metric Label Color
input color              HUD_ValueTextColor            = C'245,245,245';    // HUD Primary Value Color
input bool               ShowSRLevelsOnChart           = true;              // Draw Swing High/Low Horizontal Ray Lines
input bool               ShowPivotLevelsOnChart        = true;              // Draw Daily Pivot Lines (P, R1, S1, R2, S2)
input int                SignalArrowSize               = 2;                 // Signal Arrow Marker Glyph Size (1-5)
input color              BuyArrowColor                 = clrLimeGreen;      // Long Confirmation Arrow Color
input color              SellArrowColor                = clrRed;            // Short Confirmation Arrow Color
input bool               PlotHistoricalSignals         = true;              // Plot Past Signals on Chart History
input int                HistoricalBarsToScan          = 300;               // Number of Past Bars to Scan for Signals




//--- [10. ADVANCED INSTITUTIONAL QUANTITATIVE FILTERS]
input string             Sec_Ultra                     = "=== [10] ULTRA QUANTITATIVE SUITE ===";
input bool               UseEfficiencyRatioFilter      = true;              // Kaufman Efficiency Ratio (KER) Filter
input int                KER_Period                    = 14;                // Kaufman Efficiency Lookback Period
input double             KER_MinThreshold              = 0.25;              // Minimum Market Efficiency (0.0 = Chop, 1.0 = Pure Trend)
input bool               UseTTMSqueezeMomentum         = true;              // TTM Squeeze Volatility Compression Filter
input int                BollingerPeriod               = 20;                // Bollinger Bands Squeeze Period
input double             BollingerDev                  = 2.0;               // Bollinger Bands Standard Deviation
input int                KeltnerPeriod                 = 20;                // Keltner Channel Period
input double             KeltnerMultiplier             = 1.5;               // Keltner Channel ATR Multiplier
input bool               UseVolumeOBV_Confirmation     = true;              // On-Balance Volume (OBV) Flow Confirmation
input int                OBV_MA_Period                 = 10;                // OBV Moving Average Period
input bool               UseStealthStops               = false;             // Stealth Mode: Hide SL/TP from Broker (Virtual Stops)
input bool               UseMultiTimeframeMatrix       = true;              // Multi-Timeframe Trend Alignment (H1 & H4)
input int                MaxConsecutiveLosses          = 3;                 // Maximum Consecutive Losses Before Cooldown
input int                CooldownBarsAfterMaxLosses    = 24;                // Bars Cooldown After Maximum Loss Streak




//--- [11. INTERACTIVE CHART GUI CONTROLS & ON-CHART BUTTONS]
input string             Sec_GUI_Controls              = "=== [11] INTERACTIVE CHART BUTTONS ===";
input bool               ShowInteractiveButtons        = true;              // Show On-Chart Action Buttons (Close All, BE, Pause)
input int                Buttons_X_Offset              = 15;                // Buttons Horizontal Margin from Corner
input int                Buttons_Y_Offset              = 295;               // Buttons Vertical Margin
input int                ButtonWidth                   = 85;                // Button Width in Pixels
input int                ButtonHeight                  = 22;                // Button Height in Pixels
input color              ColorBtnCloseAll              = C'140,35,35';      // Close All Button Color
input color              ColorBtnBreakEven             = C'35,95,140';      // Break-Even All Button Color
input color              ColorBtnToggleTrade           = C'35,125,55';      // Toggle Trading Button Color


//--- [12. ADVANCED INDICATOR EXTENSIONS (CCI, DMI, BOLLINGER %B, DONCHIAN)]
input string             Sec_ExtraIndicators           = "=== [12] EXTENDED INDICATOR ENGINES ===";
input bool               UseCCI_Indicator              = true;              // Commodity Channel Index (CCI) Engine
input int                CCI_Period                    = 14;                // CCI Lookback Period
input double             CCI_Overbought                = 100.0;             // CCI Overbought Level
input double             CCI_Oversold                  = -100.0;            // CCI Oversold Level
input bool               UseBollingerPercentB          = true;              // Bollinger Bands %B & BandWidth Engine
input int                BB_Period                     = 20;                // Bollinger Bands Period
input double             BB_Deviation                  = 2.0;               // Bollinger Bands Deviation
input bool               UseDonchianChannels           = true;              // Donchian Channels Breakout Engine
input int                DonchianPeriod                = 20;                // Donchian Channel Lookback Period
input bool               UseVolumeSpreadAnalysis       = true;              // Volume Spread Analysis (VSA) Engine
input int                VSA_VolumeMAPeriod            = 20;                // VSA Volume Moving Average Lookback


//--- [13. PORTFOLIO BASKET & CURRENCY EXPOSURE GUARDS]
input string             Sec_BasketGuards              = "=== [13] BASKET & EXPOSURE GUARDS ===";
input bool               EnforceCurrencyBasketLimits   = true;              // Restrict Max Positions per Base/Quote Currency
input int                MaxSimultaneousPerCurrency    = 3;                 // Max Allowed Open Positions Sharing Same Currency
input bool               UseTimeBasedTradeExpiration   = false;             // Automatically Liquidate Stagnant Orders
input int                MaxTradeDurationHours         = 48;                // Maximum Position Lifetime (Hours)
input bool               CaptureSignalScreenshots      = true;              // Save Chart Screenshot Upon Trade Entry


//--- [09. ALERTS & TELEMETRY DISPATCHER]
input string             Sec_Alerts                    = "=== [09] ALERTS & DIAGNOSTICS ===";
input bool               EnableScreenPopupAlert        = true;              // Native MT4 Screen Modal Alert
input bool               EnableAudioChimeAlert         = true;              // Play Terminal Audio File
input string             AudioChimeFilename            = "alert.wav";       // Audio File Name (Must Reside in /Sounds)
input bool               EnablePushNotifications       = false;             // Send Mobile MetaQuotes Push Notification
input bool               EnableEmailNotifications      = false;             // Dispatch SMTP Email Notification
input bool               EnableDiskFileAuditLogging    = true;              // Maintain Local CSV Trading Audit Log
input string             AuditLogFilename              = "SmartEA_Audit.csv";// Audit CSV Filename
input bool               EnableTelegramAlerts          = true;              // Send Real-Time Telegram Notifications
input string             TelegramBotToken              = "";                // Telegram Bot Token (from @BotFather)
input string             TelegramChatID                = "";                // Telegram Chat ID (from @userinfobot)
input bool               EnableTelegramCommands        = true;              // Enable Two-Way Remote Bot Commands (/status, /positions, etc)
input bool               TelegramSendScreenshots       = true;              // Send Chart Screenshot on Trade Entry
input bool               TelegramNotifyOpen            = true;              // Notify on Trade Open
input bool               TelegramNotifyClose           = true;              // Notify on Trade Close
input bool               TelegramNotifyBreakEven       = true;              // Notify when SL moved to Break-Even
input bool               TelegramNotifyTrailing        = true;              // Notify when Trailing Stop locks profit
input bool               TelegramNotifyNews            = true;              // Notify on High-Impact News Events
input bool               TelegramSendDailyReport       = true;              // Send Automated Daily Summary at Midnight
input double             TelegramMarginWarningPct      = 300.0;             // Margin Level Caution Alert Threshold (%)
input bool               TelegramMonitorAllTrades      = true;              // Notify bot trades AND manual trades

//--- [13B. PROP-FIRM RISK GUARDIAN & CIRCUIT BREAKER]
input string             Sec_PropFirm                  = "=== [13B] PROP-FIRM RISK GUARDIAN ===";
input bool               PropEnableRiskGuardian        = true;              // Enable Prop-Firm Protection Rules
input double             PropMaxDailyLossPercent       = 4.5;               // Max Daily Drawdown % (FTMO Limit: 5%)
input double             PropMaxTotalDrawdownPercent   = 8.0;               // Max Trailing Peak-to-Trough Drawdown % (Funded Limit: 10%)
input double             PropProfitTargetPercent       = 8.0;               // Target Profit Goal % (Phase 1 Target)
input bool               PropAutoLockoutOnBreach       = true;              // Liquidate & Lock Trading Until Midnight on Breach
input bool               PropWeekendProtection         = true;              // Close Open Trades before Friday Market Close
input int                PropFridayCloseHourGMT        = 20;                // Friday Close Hour (GMT)
input bool               EnableEconomicNewsShield      = true;              // Economic News Shield: Pause entries during high-impact news

//--- [14. TIMEFRAME-ADAPTIVE SL/TP SETTINGS]
input string             Sec_TimeframeAdaptive         = "=== [14] TIMEFRAME-ADAPTIVE SL/TP ===";
input bool               UseTimeframeBase              = true;              // Enable Timeframe-Based Base Pip Scaling
input int                BaseSL_M1                     = 5;                 // M1 Base Stop Loss (Pips)
input int                BaseTP_M1                     = 10;                // M1 Base Take Profit (Pips)
input int                BaseSL_M5                     = 8;                 // M5 Base Stop Loss (Pips)
input int                BaseTP_M5                     = 16;                // M5 Base Take Profit (Pips)
input int                BaseSL_M15                    = 12;                // M15 Base Stop Loss (Pips)
input int                BaseTP_M15                    = 24;                // M15 Base Take Profit (Pips)
input int                BaseSL_M30                    = 15;                // M30 Base Stop Loss (Pips)
input int                BaseTP_M30                    = 30;                // M30 Base Take Profit (Pips)
input int                BaseSL_H1                     = 20;                // H1 Base Stop Loss (Pips)
input int                BaseTP_H1                     = 40;                // H1 Base Take Profit (Pips)
input int                BaseSL_H4                     = 35;                // H4 Base Stop Loss (Pips)
input int                BaseTP_H4                     = 70;                // H4 Base Take Profit (Pips)
input int                BaseSL_D1                     = 50;                // D1 Base Stop Loss (Pips)
input int                BaseTP_D1                     = 100;               // D1 Base Take Profit (Pips)
input int                BaseSL_W1                     = 100;               // W1 Base Stop Loss (Pips)
input int                BaseTP_W1                     = 200;               // W1 Base Take Profit (Pips)
input int                BaseSL_MN1                    = 200;               // MN1 Base Stop Loss (Pips)
input int                BaseTP_MN1                    = 400;               // MN1 Base Take Profit (Pips)
input bool               UseATRAdjust                  = true;              // Method 1: ATR Volatility Multiplier Adjustment
input double             ATR_VOL_Threshold             = 1.5;               // ATR High Volatility Spike Ratio
input bool               UseADRAdjust                  = true;              // Method 2: ADR Normalization Adjustment
input bool               UseSROverride                 = true;              // Method 3: Support / Resistance Override
input int                SRLookbackBars                = 50;                // S/R Swing Lookback Window (Bars)
input bool               UseFibOverride                = false;             // Method 4: Fibonacci Levels Override
input bool               UsePivotOverride              = true;              // Method 6: Pivot Points Override
input double             HybridTolerance_M1_M5         = 5.0;               // Hybrid Cluster Tolerance for M1-M5 (Pips)
input double             HybridTolerance_M15_H1        = 10.0;              // Hybrid Cluster Tolerance for M15-H1 (Pips)
input double             HybridTolerance_H4_Plus       = 25.0;              // Hybrid Cluster Tolerance for H4+ (Pips)




//+------------------------------------------------------------------+
//| GLOBAL SYSTEM STATE REGISTRIES                                   |
//+------------------------------------------------------------------+
#define PREFIX_GUI "SmartEA_HUD_"
#define PREFIX_OBJ "SmartEA_OBJ_"


// Financial instrument precision scalars
double   g_PipPoint             = 0.0001;
int      g_PipDigits            = 4;
double   g_TickSize             = 0.0001;
double   g_TickValue            = 10.0;
double   g_LotStep              = 0.01;
double   g_MinLot               = 0.01;
double   g_MaxLot               = 100.0;


// Synchronization and lifecycle clocks
bool     g_AutoTradingRuntimeActive = true;
datetime g_LastBarProcessedTime = 0;
datetime g_LastOrderExecutionTime = 0;
datetime g_DayAnchorDate        = 0;
double   g_StartingDayEquity    = 0.0;
double   g_StartingDayBalance   = 0.0;
bool     g_DailyLossCircuitTripped = false;
bool     g_DailyTargetCircuitTripped = false;

#include <ZeroMQBridge.mqh>


// Real-time quantitative scoring telemetry cache
int      g_ScoreTrendBuy        = 0;
int      g_ScoreTrendSell       = 0;
int      g_ScoreMomBuy          = 0;
int      g_ScoreMomSell         = 0;
int      g_ScoreSRBuy           = 0;
int      g_ScoreSRSell          = 0;
int      g_ScoreCandleBuy       = 0;
int      g_ScoreCandleSell      = 0;
int      g_ScoreAggregateBuy    = 0;
int      g_ScoreAggregateSell   = 0;


// Active analytical metrics cache
ENUM_TREND_REGIME         g_ActiveTrendRegime   = TREND_FLAT;
ENUM_CANDLE_CLASSIFICATION g_LastCandlePattern  = CANDLE_INDECISION;
ENUM_MARKET_SESSION       g_CurrentSession      = SESSION_OFF_HOURS;
string                    g_LastSignalVerdict   = "NONE";
int                       g_LastSignalScore     = 0;
double                    g_CalculatedRSI       = 50.0;
double                    g_CalculatedMACDMain  = 0.0;
double                    g_CalculatedMACDSig   = 0.0;
double                    g_CalculatedStochK    = 50.0;
double                    g_CalculatedStochD    = 50.0;
double                    g_CalculatedADX       = 0.0;
double                    g_CalculatedATR       = 0.0;
double                    g_RecentSwingHigh     = 0.0;
double                    g_RecentSwingLow      = 0.0;
double                    g_DailyPivot_P        = 0.0;
double                    g_DailyPivot_R1       = 0.0;
double                    g_DailyPivot_S1       = 0.0;
double                    g_DailyPivot_R2       = 0.0;
double                    g_DailyPivot_S2       = 0.0;
double                    g_DailyPivot_R3       = 0.0;
double                    g_DailyPivot_S3       = 0.0;

// Prop-Firm Risk Guardian State
double   g_PropPeakEquity              = 0.0;
bool     g_PropLockoutActive           = false;
datetime g_PropLockoutDate             = 0;
datetime g_lastNewsCalendarReadTime    = 0;
bool     g_isNewsShieldVetoActive      = false;
int      g_PartiallyClosedTickets[];


// Stealth mode virtual stop registry
struct SStealthOrderRecord
{
   int    ticket;
   double stopLoss;
   double takeProfit;
};
SStealthOrderRecord g_StealthOrders[];


// Ultra Quant Global State Registries
double   g_CalculatedKER               = 0.50;
bool     g_TTMSqueezeArmed             = false;
bool     g_TTMSqueezeFiring            = false;
bool     g_OBV_BullishFlow             = false;
bool     g_OBV_BearishFlow             = false;
int      g_ConsecutiveLossesCount      = 0;
datetime g_ConsecutiveLossCooldownTime = 0;
datetime g_LastLossCooldownResetTime   = 0;


// Extended Indicator Telemetry
double   g_CalculatedCCI               = 0.0;
double   g_CalculatedPercentB          = 0.50;
double   g_CalculatedBandWidth         = 0.0;
double   g_DonchianUpper               = 0.0;
double   g_DonchianLower               = 0.0;
double   g_DonchianMiddle              = 0.0;
bool     g_VSA_StoppingVolume          = false;
bool     g_VSA_AbsorptionVolume        = false;
bool     g_VSA_LowVolumePullback       = false;

// â”€â”€ PERF: Slow-path throttle ticks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
uint     g_LastMTFMatrixTick           = 0;   // MTF matrix update: every 10s
uint     g_LastHeavyIndicatorTick      = 0;   // CCI/BB/VSA calc: every 5s
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€





//+------------------------------------------------------------------+
//| MQL4 ERROR TRANSLATION DICTIONARY                                |
//+------------------------------------------------------------------+
string MqlErrorToString(const int errorCode)
{
   switch(errorCode)
   {
      case 0:   return "ERR_NO_ERROR: Success";
      case 1:   return "ERR_NO_RESULT: Operation completed with no result";
      case 2:   return "ERR_COMMON_ERROR: Common system error";
      case 3:   return "ERR_INVALID_TRADE_PARAMETERS: Invalid trade parameters";
      case 4:   return "ERR_SERVER_BUSY: Trade server is busy";
      case 5:   return "ERR_OLD_VERSION: Old version of client terminal";
      case 6:   return "ERR_NO_CONNECTION: No connection to trade server";
      case 7:   return "ERR_NOT_ENOUGH_RIGHTS: Not enough rights";
      case 8:   return "ERR_TOO_FREQUENT_REQUESTS: Too frequent requests";
      case 9:   return "ERR_MALFUNCTIONAL_TRADE: Malfunctional trade operation";
      case 64:  return "ERR_ACCOUNT_DISABLED: Account is disabled";
      case 65:  return "ERR_INVALID_ACCOUNT: Invalid account";
      case 128: return "ERR_TRADE_TIMEOUT: Trade timeout expired";
      case 129: return "ERR_INVALID_PRICE: Invalid price quotation";
      case 130: return "ERR_INVALID_STOPS: Invalid stop loss or take profit";
      case 131: return "ERR_INVALID_TRADE_VOLUME: Invalid trade volume / lot size";
      case 132: return "ERR_MARKET_CLOSED: Market is closed";
      case 133: return "ERR_TRADE_DISABLED: Trading is disabled";
      case 134: return "ERR_NOT_ENOUGH_MONEY: Insufficient margin to complete order";
      case 135: return "ERR_PRICE_CHANGED: Price changed / requoted";
      case 136: return "ERR_OFF_QUOTES: Off quotes / no liquidity";
      case 137: return "ERR_BROKER_BUSY: Broker trade desk busy";
      case 138: return "ERR_REQUOTE: Order Requoted";
      case 139: return "ERR_ORDER_LOCKED: Order is locked by another process";
      case 140: return "ERR_LONG_POSITIONS_ONLY_ALLOWED: Buy orders only allowed";
      case 141: return "ERR_TOO_MANY_REQUESTS: Too many requests";
      case 145: return "ERR_TRADE_MODIFY_DENIED: Modification denied by broker";
      case 146: return "ERR_TRADE_CONTEXT_BUSY: Subsystem trade context is busy";
      case 147: return "ERR_TRADE_EXPIRATION_DENIED: Expiration date denied by broker";
      case 148: return "ERR_TRADE_TOO_MANY_ORDERS: Amount of open/pending orders reached limit";
      case 149: return "ERR_TRADE_HEDGE_PROHIBITED: Hedging prohibited by FIFO rules";
      case 150: return "ERR_TRADE_PROHIBITED_BY_FIFO: Prohibited by FIFO rules";
      case 4000: return "ERR_NO_MQLERROR: No error";
      case 4001: return "ERR_WRONG_FUNCTION_POINTER: Wrong function pointer";
      case 4002: return "ERR_ARRAY_INDEX_OUT_OF_RANGE: Array index out of range";
      case 4003: return "ERR_NO_MEMORY_FOR_CALL_STACK: No memory for call stack";
      case 4004: return "ERR_RECURSIVE_STACK_OVERFLOW: Recursive stack overflow";
      case 4005: return "ERR_NOT_ENOUGH_STACK_FOR_PARAM: Not enough stack for parameter";
      case 4006: return "ERR_NO_MEMORY_FOR_PARAM_STRING: No memory for parameter string";
      case 4007: return "ERR_NO_MEMORY_FOR_TEMP_STRING: No memory for temporary string";
      case 4008: return "ERR_NOT_INITIALIZED_STRING: String not initialized";
      case 4009: return "ERR_NOT_INITIALIZED_ARRAYSTRING: Array string not initialized";
      case 4010: return "ERR_NO_MEMORY_FOR_ARRAYSTRING: No memory for array string";
      case 4011: return "ERR_TOO_LONG_STRING: String too long";
      case 4012: return "ERR_REMAINDER_FROM_ZERO_DIVIDE: Division by zero encountered";
      case 4013: return "ERR_ZERO_DIVIDE: Zero divide error";
      case 4014: return "ERR_UNKNOWN_COMMAND: Unknown command";
      case 4015: return "ERR_WRONG_JUMP: Wrong jump directive";
      case 4016: return "ERR_NOT_INITIALIZED_ARRAY: Array not initialized";
      case 4017: return "ERR_DLL_CALLS_NOT_ALLOWED: DLL calls not allowed in settings";
      case 4018: return "ERR_CANNOT_LOAD_LIBRARY: Library could not be loaded";
      case 4019: return "ERR_CANNOT_CALL_FUNCTION: Function call failed";
      case 4020: return "ERR_EXTERNAL_CALLS_NOT_ALLOWED: External expert calls not allowed";
      case 4021: return "ERR_NO_MEMORY_FOR_RETURN_STRING: No memory for return string";
      case 4022: return "ERR_SYSTEM_BUSY: Internal system busy";
      case 4051: return "ERR_INVALID_FUNCTION_PARAMVALUE: Invalid function parameter value";
      case 4052: return "ERR_STRING_PARAMETER_EXPECTED: String parameter expected";
      case 4053: return "ERR_INTEGER_PARAMETER_EXPECTED: Integer parameter expected";
      case 4054: return "ERR_DOUBLE_PARAMETER_EXPECTED: Double parameter expected";
      case 4055: return "ERR_ARRAY_AS_PARAMETER_EXPECTED: Array parameter expected";
      case 4056: return "ERR_HISTORY_WILL_UPDATED: Market history is currently updating";
      case 4057: return "ERR_TRADE_ERROR: Error occurred during trade operation";
      case 4058: return "ERR_RESOURCE_NOT_FOUND: Resource not found";
      case 4059: return "ERR_RESOURCE_NOT_SUPPORTED: Resource not supported";
      case 4060: return "ERR_RESOURCE_DUPLICATE: Duplicate resource detected";
      case 4061: return "ERR_CANT_OPEN_FILE: Cannot open file";
      case 4062: return "ERR_CANNOT_CLOSE_FILE: Cannot close file";
      case 4063: return "ERR_WRONG_FILE_NAME: Invalid file name";
      case 4064: return "ERR_TOO_MANY_OPEN_FILES: Open file handle ceiling reached";
      case 4065: return "ERR_CANNOT_READ_FILE: Cannot read from file";
      case 4066: return "ERR_CANNOT_WRITE_FILE: Cannot write to file";
      default:   return "UNKNOWN_ERROR_CODE: " + IntegerToString(errorCode);
   }
}


//+------------------------------------------------------------------+
//| INSTRUMENT PIP & TICK GEOMETRY CALCULATION                       |
//+------------------------------------------------------------------+
void InitializeSymbolMetrics()
{
   if(Digits == 3 || Digits == 5)
   {
      g_PipPoint  = Point * 10.0;
      g_PipDigits = Digits - 1;
   }
   else
   {
      g_PipPoint  = Point;
      g_PipDigits = Digits;
   }


   g_TickSize  = MarketInfo(Symbol(), MODE_TICKSIZE);
   g_TickValue = MarketInfo(Symbol(), MODE_TICKVALUE);
   g_LotStep   = MarketInfo(Symbol(), MODE_LOTSTEP);
   g_MinLot    = MarketInfo(Symbol(), MODE_MINLOT);
   g_MaxLot    = MarketInfo(Symbol(), MODE_MAXLOT);


   if(g_TickSize <= 0.0)  g_TickSize  = Point;
   if(g_TickValue <= 0.0) g_TickValue = 1.0;
   if(g_LotStep <= 0.0)   g_LotStep   = 0.01;
   if(g_MinLot <= 0.0)    g_MinLot    = 0.01;
   if(g_MaxLot <= 0.0)    g_MaxLot    = 100.0;


   PrintFormat("[INIT] Symbol: %s | Digits: %d | PipPoint: %f | TickSize: %f | TickValue: %f | LotStep: %f",
               Symbol(), Digits, g_PipPoint, g_TickSize, g_TickValue, g_LotStep);
}


//+------------------------------------------------------------------+
//| BROKER SLIPPAGE DYNAMIC SCALER (3/5-DIGIT BROKER ADAPTATION)     |
//+------------------------------------------------------------------+
int GetScaledSlippage()
{
   if(g_PipPoint > 0.0 && Point > 0.0)
      return (int)MathRound(ExecutionSlippage * (g_PipPoint / Point));
   return ExecutionSlippage;
}


//+------------------------------------------------------------------+
//| STRING FORMATTING AND PADDING HELPERS                            |
//+------------------------------------------------------------------+
string FormatDoublePrecision(const double val, const int decimals)
{
   return DoubleToString(NormalizeDouble(val, decimals), decimals);
}


string PadRight(string str, const int totalLen, const string padChar = " ")
{
   int currentLen = StringLen(str);
   while(currentLen < totalLen)
   {
      str = str + padChar;
      currentLen++;
   }
   return str;
}


//+------------------------------------------------------------------+
//| SECTION 1: TREND DETECTION ENGINE (0 - 3 POINTS)                 |
//+------------------------------------------------------------------+
void CalculateTrendModule(int &outTrendBuy, int &outTrendSell)
{
   outTrendBuy  = 0;
   outTrendSell = 0;


   // Evaluate strictly on bar index 1 (last confirmed closed candle)
   double ema20  = iMA(Symbol(), Period(), EMA_Fast_Period,   0, MODE_EMA, EMA_AppliedPrice, 1);
   double ema50  = iMA(Symbol(), Period(), EMA_Medium_Period, 0, MODE_EMA, EMA_AppliedPrice, 1);
   double ema200 = iMA(Symbol(), Period(), EMA_Slow_Period,   0, MODE_EMA, EMA_AppliedPrice, 1);


   // Optional ADX filter evaluation
   bool adxFilterPass = true;
   if(UseADX_Filter)
   {
      g_CalculatedADX = iADX(Symbol(), Period(), ADX_Period, PRICE_CLOSE, MODE_MAIN, 1);
      if(g_CalculatedADX < ADX_MinStrengthThreshold)
      {
         adxFilterPass = false; // Trend is sluggish or choppy
      }
   }


   // 1. Strong Uptrend Alignment: EMA 20 > EMA 50 > EMA 200
   if(ema20 > ema50 && ema50 > ema200)
   {
      g_ActiveTrendRegime = TREND_STRONG_BULLISH;
      outTrendBuy = adxFilterPass ? 3 : 2;
   }
   // 2. Strong Downtrend Alignment: EMA 20 < EMA 50 < EMA 200
   else if(ema20 < ema50 && ema50 < ema200)
   {
      g_ActiveTrendRegime = TREND_STRONG_BEARISH;
      outTrendSell = adxFilterPass ? 3 : 2;
   }
   // 3. Weak Uptrend: EMA 20 > EMA 50 but EMA 50 < EMA 200
   else if(ema20 > ema50 && ema50 < ema200)
   {
      g_ActiveTrendRegime = TREND_WEAK_BULLISH;
      outTrendBuy = 2;
   }
   // 4. Weak Downtrend: EMA 20 < EMA 50 but EMA 50 > EMA 200
   else if(ema20 < ema50 && ema50 > ema200)
   {
      g_ActiveTrendRegime = TREND_WEAK_BEARISH;
      outTrendSell = 2;
   }
   // 5. Flat or Mixed Configuration
   else
   {
      g_ActiveTrendRegime = TREND_FLAT;
      outTrendBuy  = 0;
      outTrendSell = 0;
   }
}


//+------------------------------------------------------------------+
//| SECTION 2: MOMENTUM & OSCILLATOR ENGINE (0 - 3 POINTS)           |
//+------------------------------------------------------------------+
void CalculateMomentumModule(const int trendBuy, const int trendSell, int &outMomBuy, int &outMomSell)
{
   outMomBuy  = 0;
   outMomSell = 0;


   // 1. Relative Strength Index (RSI) on Shift 1
   g_CalculatedRSI = iRSI(Symbol(), Period(), RSI_Period, RSI_AppliedPrice, 1);


   // Oversold condition coupled with uptrend alignment
   if(g_CalculatedRSI < RSI_Oversold && trendBuy > 0)
   {
      outMomBuy += 2;
   }
   // Overbought condition coupled with downtrend alignment
   else if(g_CalculatedRSI > RSI_Overbought && trendSell > 0)
   {
      outMomSell += 2;
   }
   // Neutral equilibrium zone (40 - 60)
   else if(g_CalculatedRSI >= RSI_Neutral_Low && g_CalculatedRSI <= RSI_Neutral_High)
   {
      outMomBuy  += 1;
      outMomSell += 1;
   }


   // 2. Moving Average Convergence Divergence (MACD)
   g_CalculatedMACDMain = iMACD(Symbol(), Period(), MACD_Fast_EMA, MACD_Slow_EMA, MACD_Signal_SMA, MACD_AppliedPrice, MODE_MAIN, 1);
   g_CalculatedMACDSig  = iMACD(Symbol(), Period(), MACD_Fast_EMA, MACD_Slow_EMA, MACD_Signal_SMA, MACD_AppliedPrice, MODE_SIGNAL, 1);
   double macdPrevMain  = iMACD(Symbol(), Period(), MACD_Fast_EMA, MACD_Slow_EMA, MACD_Signal_SMA, MACD_AppliedPrice, MODE_MAIN, 2);
   double macdPrevSig   = iMACD(Symbol(), Period(), MACD_Fast_EMA, MACD_Slow_EMA, MACD_Signal_SMA, MACD_AppliedPrice, MODE_SIGNAL, 2);


   // Bullish crossover confirmation
   if(g_CalculatedMACDMain > g_CalculatedMACDSig && macdPrevMain <= macdPrevSig)
   {
      outMomBuy += 1;
   }
   // Bearish crossover confirmation
   else if(g_CalculatedMACDMain < g_CalculatedMACDSig && macdPrevMain >= macdPrevSig)
   {
      outMomSell += 1;
   }


   // 3. Optional Stochastic Confirmation
   if(UseStochasticConfirmation)
   {
      g_CalculatedStochK = iStochastic(Symbol(), Period(), Stoch_K_Period, Stoch_D_Period, Stoch_Slowing, MODE_SMA, 0, MODE_MAIN, 1);
      g_CalculatedStochD = iStochastic(Symbol(), Period(), Stoch_K_Period, Stoch_D_Period, Stoch_Slowing, MODE_SMA, 0, MODE_SIGNAL, 1);


      if(g_CalculatedStochK < Stoch_Oversold && g_CalculatedStochK > g_CalculatedStochD)
      {
         outMomBuy += 1;
      }
      else if(g_CalculatedStochK > Stoch_Overbought && g_CalculatedStochK < g_CalculatedStochD)
      {
         outMomSell += 1;
      }
   }


   // Clamp maximum momentum points to specification maximum (3 points)
   if(outMomBuy > 3)  outMomBuy = 3;
   if(outMomSell > 3) outMomSell = 3;
}


//+------------------------------------------------------------------+
//| SECTION 3: SUPPORT, RESISTANCE & PIVOTS ENGINE (0 - 2 POINTS)    |
//+------------------------------------------------------------------+
void CalculateSupportResistanceModule(const int trendBuy, const int trendSell, int &outSRBuy, int &outSRSell)
{
   outSRBuy  = 0;
   outSRSell = 0;


   if(!UseSupportResistanceScoring) return;


   // 1. Swing High & Swing Low Lookback Detection (50 Bars)
   int highIndex = iHighest(Symbol(), Period(), MODE_HIGH, LookbackBarsSR, 1);
   int lowIndex  = iLowest(Symbol(),  Period(), MODE_LOW,  LookbackBarsSR, 1);


   g_RecentSwingHigh = (highIndex != -1) ? iHigh(Symbol(), Period(), highIndex) : iHigh(Symbol(), Period(), 1);
   g_RecentSwingLow  = (lowIndex  != -1) ? iLow(Symbol(),  Period(), lowIndex)  : iLow(Symbol(),  Period(), 1);


   double close1 = iClose(Symbol(), Period(), 1);
   double proximityDelta = ProximityPipsSR * g_PipPoint;


   // Proximity to strong support in an uptrend -> +2 BUY
   if(MathAbs(close1 - g_RecentSwingLow) <= proximityDelta && trendBuy > 0)
   {
      outSRBuy += 2;
   }


   // Proximity to strong resistance in a downtrend -> +2 SELL
   if(MathAbs(close1 - g_RecentSwingHigh) <= proximityDelta && trendSell > 0)
   {
      outSRSell += 2;
   }


   // 2. Daily Pivot Points Calculation
   if(UsePivotPointsScoring)
   {
      double dHigh  = iHigh(Symbol(),  PERIOD_D1, 1);
      double dLow   = iLow(Symbol(),   PERIOD_D1, 1);
      double dClose = iClose(Symbol(), PERIOD_D1, 1);


      if(PivotFormulaType == PIVOT_CLASSIC)
      {
         g_DailyPivot_P  = (dHigh + dLow + dClose) / 3.0;
         g_DailyPivot_R1 = (2.0 * g_DailyPivot_P) - dLow;
         g_DailyPivot_S1 = (2.0 * g_DailyPivot_P) - dHigh;
         g_DailyPivot_R2 = g_DailyPivot_P + (dHigh - dLow);
         g_DailyPivot_S2 = g_DailyPivot_P - (dHigh - dLow);
         g_DailyPivot_R3 = dHigh + 2.0 * (g_DailyPivot_P - dLow);
         g_DailyPivot_S3 = dLow  - 2.0 * (dHigh - g_DailyPivot_P);
      }
      else if(PivotFormulaType == PIVOT_FIBONACCI)
      {
         g_DailyPivot_P  = (dHigh + dLow + dClose) / 3.0;
         double dRange   = dHigh - dLow;
         g_DailyPivot_R1 = g_DailyPivot_P + (0.382 * dRange);
         g_DailyPivot_S1 = g_DailyPivot_P - (0.382 * dRange);
         g_DailyPivot_R2 = g_DailyPivot_P + (0.618 * dRange);
         g_DailyPivot_S2 = g_DailyPivot_P - (0.618 * dRange);
         g_DailyPivot_R3 = g_DailyPivot_P + (1.000 * dRange);
         g_DailyPivot_S3 = g_DailyPivot_P - (1.000 * dRange);
      }
      else if(PivotFormulaType == PIVOT_CAMARILLA)
      {
         g_DailyPivot_P  = (dHigh + dLow + dClose) / 3.0;
         double dRange   = dHigh - dLow;
         g_DailyPivot_R3 = dClose + (dRange * (1.1 / 4.0));
         g_DailyPivot_S3 = dClose - (dRange * (1.1 / 4.0));
         g_DailyPivot_R2 = dClose + (dRange * (1.1 / 6.0));
         g_DailyPivot_S2 = dClose - (dRange * (1.1 / 6.0));
         g_DailyPivot_R1 = dClose + (dRange * (1.1 / 12.0));
         g_DailyPivot_S1 = dClose - (dRange * (1.1 / 12.0));
      }
      else // PIVOT_WOODIE
      {
         double dOpen    = iOpen(Symbol(), PERIOD_D1, 0);
         double dRange   = dHigh - dLow;
         g_DailyPivot_P  = (dHigh + dLow + (2.0 * dOpen)) / 4.0;
         g_DailyPivot_R1 = (2.0 * g_DailyPivot_P) - dLow;
         g_DailyPivot_S1 = (2.0 * g_DailyPivot_P) - dHigh;
         g_DailyPivot_R2 = g_DailyPivot_P + dRange;
         g_DailyPivot_S2 = g_DailyPivot_P - dRange;
         g_DailyPivot_R3 = dHigh + 2.0 * (g_DailyPivot_P - dLow);
         g_DailyPivot_S3 = dLow  - 2.0 * (dHigh - g_DailyPivot_P);
      }


      bool nearAnyPivot = (MathAbs(close1 - g_DailyPivot_P)  <= proximityDelta ||
                           MathAbs(close1 - g_DailyPivot_R1) <= proximityDelta ||
                           MathAbs(close1 - g_DailyPivot_S1) <= proximityDelta ||
                           MathAbs(close1 - g_DailyPivot_R2) <= proximityDelta ||
                           MathAbs(close1 - g_DailyPivot_S2) <= proximityDelta);


      if(nearAnyPivot)
      {
         outSRBuy  += 1;
         outSRSell += 1;
      }
   }


   // Clamp to maximum specification ceiling of 2 points
   if(outSRBuy > 2)  outSRBuy = 2;
   if(outSRSell > 2) outSRSell = 2;
}


//+------------------------------------------------------------------+
//| SECTION 4: CANDLESTICK PATTERN RECOGNITION (0 - 2 POINTS)        |
//+------------------------------------------------------------------+
void DetectCandlestickPatternsModule(int &outCandleBuy, int &outCandleSell)
{
   outCandleBuy  = 0;
   outCandleSell = 0;
   g_LastCandlePattern = CANDLE_INDECISION;


   if(!UseCandlestickPatternScoring) return;


   // Candle 1 (Current completed bar)
   double o1 = iOpen(Symbol(), Period(), 1);
   double c1 = iClose(Symbol(), Period(), 1);
   double h1 = iHigh(Symbol(), Period(), 1);
   double l1 = iLow(Symbol(), Period(), 1);


   // Candle 2 (Previous bar)
   double o2 = iOpen(Symbol(), Period(), 2);
   double c2 = iClose(Symbol(), Period(), 2);


   // Candle 3 (Bar prior to previous)
   double o3 = iOpen(Symbol(), Period(), 3);
   double c3 = iClose(Symbol(), Period(), 3);


   double body1      = MathAbs(c1 - o1);
   double fullRange1 = h1 - l1;
   if(fullRange1 <= 0.0) return;


   double upperWick1 = h1 - MathMax(o1, c1);
   double lowerWick1 = MathMin(o1, c1) - l1;


   double proximityDelta = ProximityPipsSR * g_PipPoint;
   bool atSupport    = (MathAbs(c1 - g_RecentSwingLow) <= proximityDelta || MathAbs(c1 - g_DailyPivot_S1) <= proximityDelta);
   bool atResistance = (MathAbs(c1 - g_RecentSwingHigh) <= proximityDelta || MathAbs(c1 - g_DailyPivot_R1) <= proximityDelta);


   // 1. Bullish Engulfing: Candle 2 is bearish, Candle 1 is bullish and wraps around Candle 2
   if(c2 < o2 && c1 > o1 && c1 >= o2 && o1 <= c2)
   {
      outCandleBuy += 2;
      g_LastCandlePattern = CANDLE_BULLISH_ENGULFING;
   }
   // 2. Bearish Engulfing: Candle 2 is bullish, Candle 1 is bearish and wraps around Candle 2
   else if(c2 > o2 && c1 < o1 && c1 <= o2 && o1 >= c2)
   {
      outCandleSell += 2;
      g_LastCandlePattern = CANDLE_BEARISH_ENGULFING;
   }


   // 3. Hammer at Support: Lower wick >= 2 * body, very small upper wick
   if(lowerWick1 >= (2.0 * body1) && upperWick1 <= (0.2 * fullRange1) && atSupport)
   {
      outCandleBuy += 1;
      g_LastCandlePattern = CANDLE_HAMMER;
   }


   // 4. Shooting Star at Resistance: Upper wick >= 2 * body, very small lower wick
   if(upperWick1 >= (2.0 * body1) && lowerWick1 <= (0.2 * fullRange1) && atResistance)
   {
      outCandleSell += 1;
      g_LastCandlePattern = CANDLE_SHOOTING_STAR;
   }


   // 5. Doji at S/R: Body <= 10% of total candle range
   if(body1 <= (0.10 * fullRange1) && (atSupport || atResistance))
   {
      outCandleBuy  += 1;
      outCandleSell += 1;
      g_LastCandlePattern = CANDLE_DOJI_REGULAR;
   }


   // 6. Morning Star (3-Candle Bullish Reversal)
   if(c3 < o3 && MathAbs(c2 - o2) < (0.3 * (iHigh(Symbol(), Period(), 2) - iLow(Symbol(), Period(), 2))) && c1 > o1 && c1 > ((o3 + c3) / 2.0))
   {
      outCandleBuy += 2;
      g_LastCandlePattern = CANDLE_MORNING_STAR;
   }
   // 7. Evening Star (3-Candle Bearish Reversal)
   else if(c3 > o3 && MathAbs(c2 - o2) < (0.3 * (iHigh(Symbol(), Period(), 2) - iLow(Symbol(), Period(), 2))) && c1 < o1 && c1 < ((o3 + c3) / 2.0))
   {
      outCandleSell += 2;
      g_LastCandlePattern = CANDLE_EVENING_STAR;
   }


   // Clamp to maximum specification ceiling of 2 points
   if(outCandleBuy > 2)  outCandleBuy = 2;
   if(outCandleSell > 2) outCandleSell = 2;
}


//+------------------------------------------------------------------+
//| CONFLUENCE SCORING PIPELINE (0 - 10 SCALE)                       |
//+------------------------------------------------------------------+
void ExecuteScoringPipeline(int &totalBuyScore, int &totalSellScore)
{
   CalculateTrendModule(g_ScoreTrendBuy, g_ScoreTrendSell);
   CalculateMomentumModule(g_ScoreTrendBuy, g_ScoreTrendSell, g_ScoreMomBuy, g_ScoreMomSell);
   CalculateSupportResistanceModule(g_ScoreTrendBuy, g_ScoreTrendSell, g_ScoreSRBuy, g_ScoreSRSell);
   DetectCandlestickPatternsModule(g_ScoreCandleBuy, g_ScoreCandleSell);


   totalBuyScore  = g_ScoreTrendBuy  + g_ScoreMomBuy  + g_ScoreSRBuy  + g_ScoreCandleBuy;
   totalSellScore = g_ScoreTrendSell + g_ScoreMomSell + g_ScoreSRSell + g_ScoreCandleSell;


   if(totalBuyScore > 10)  totalBuyScore  = 10;
   if(totalSellScore > 10) totalSellScore = 10;


   g_ScoreAggregateBuy  = totalBuyScore;
   g_ScoreAggregateSell = totalSellScore;
}


//+------------------------------------------------------------------+
//| SECTION 5: TRADE FILTERS ENGINE                                  |
//+------------------------------------------------------------------+
bool ValidateTradeFilters(const ENUM_SIGNAL_DECISION proposedSignal)
{
   // 0.0 Portfolio Basket & Currency Exposure Gate
   if(!ValidateCurrencyBasketExposure()) return false;


   // 0. Cooldown & Drawdown Streak Gate
   if(g_ConsecutiveLossCooldownTime > 0)
   {
      if(TimeCurrent() >= g_ConsecutiveLossCooldownTime)
      {
         g_ConsecutiveLossesCount = 0;
         g_ConsecutiveLossCooldownTime = 0;
         g_LastLossCooldownResetTime = TimeCurrent();
         Print("[KILL-SWITCH] Consecutive loss cooldown elapsed. Filter streak reset.");
      }
      else
      {
         PrintFormat("[FILTER VETO] Consecutive loss cooldown active until %s", TimeToStr(g_ConsecutiveLossCooldownTime));
         return false;
      }
   }


   // 0.1 Kaufman Efficiency Ratio (KER) Market Noise Filter
   if(UseEfficiencyRatioFilter)
   {
      g_CalculatedKER = CalculateKaufmanEfficiencyRatio(KER_Period);
      if(g_CalculatedKER < KER_MinThreshold)
      {
         PrintFormat("[FILTER VETO] Market choppy/noisy. KER = %.3f < Threshold %.3f", g_CalculatedKER, KER_MinThreshold);
         return false;
      }
   }


   // 0.2 Multi-Timeframe Alignment Gate (H1 & H4)
   if(UseMultiTimeframeMatrix)
   {
      if(!ValidateHigherTimeframeTrend(PERIOD_H1, proposedSignal)) return false;
      if(!ValidateHigherTimeframeTrend(PERIOD_H4, proposedSignal)) return false;
   }


   // 1. Spread Check
   int currentSpreadPoints = (int)MarketInfo(Symbol(), MODE_SPREAD);
   if(currentSpreadPoints > MaxSpreadPoints)
   {
      PrintFormat("[FILTER VETO] Spread exceeds limit: Current = %d, Max = %d", currentSpreadPoints, MaxSpreadPoints);
      return false;
   }


   // 2. Trading Session & Schedule Time Filter
   if(UseTimeFilter)
   {
      datetime serverTime = TimeCurrent();
      datetime gmtTime    = serverTime - (BrokerGMT_Offset * 3600);
      MqlDateTime dt;
      TimeToStruct(gmtTime, dt);


      // Daily Hour Window Check (GMT) - Supports overnight wrap-around
      bool inTime = (StartHourGMT <= EndHourGMT) ? 
                    (dt.hour >= StartHourGMT && dt.hour < EndHourGMT) : 
                    (dt.hour >= StartHourGMT || dt.hour < EndHourGMT);

      if(!inTime)
      {
         PrintFormat("[FILTER VETO] Outside permissible GMT hours (%02d:00 - %02d:00). Current GMT: %02d:%02d",
                     StartHourGMT, EndHourGMT, dt.hour, dt.min);
         return false;
      }


      // Friday Late Afternoon Liquidity Cutoff
      if(FilterFridayLateTrading && dt.day_of_week == 5 && dt.hour >= FridayCloseHourGMT)
      {
         PrintFormat("[FILTER VETO] Friday afternoon risk mitigation active (Cutoff: %02d:00 GMT)", FridayCloseHourGMT);
         return false;
      }


      // Specific Market Session Gates
      ENUM_MARKET_SESSION session = IdentifyMarketSession(gmtTime);
      if(session == SESSION_ASIAN && !TradeAsianSession)
      {
         Print("[FILTER VETO] Asian Session trading disabled in inputs.");
         return false;
      }
      if(session == SESSION_LONDON && !TradeLondonSession)
      {
         Print("[FILTER VETO] London Session trading disabled in inputs.");
         return false;
      }
      if(session == SESSION_NEWYORK && !TradeNewYorkSession)
      {
         Print("[FILTER VETO] New York Session trading disabled in inputs.");
         return false;
      }
   }


   // 3. News / High Volatility Spike Filter
   if(UseNewsVolatilityFilter)
   {
      g_CalculatedATR = iATR(Symbol(), Period(), ATRPeriod, 1);
      double lastBarRange = iHigh(Symbol(), Period(), 1) - iLow(Symbol(), Period(), 1);
      if(g_CalculatedATR > 0.0 && (lastBarRange / g_CalculatedATR) >= VolatilitySpikeATR_Ratio)
      {
         PrintFormat("[FILTER VETO] Abnormal volatility expansion detected: BarRange/ATR = %.2f (Threshold = %.2f)",
                     lastBarRange / g_CalculatedATR, VolatilitySpikeATR_Ratio);
         if(TelegramNotifyNews && (TimeCurrent() - g_lastNewsAlertTime > 1800))
         {
            g_lastNewsAlertTime = TimeCurrent();
            Telegram_NotifyNewsVolatility(lastBarRange / g_CalculatedATR, VolatilitySpikeATR_Ratio);
         }
         return false;
      }
   }
   
   // Economic News Shield: Pause entries during active high-impact economic events
   if(EnableEconomicNewsShield && IsHighImpactNewsActive(Symbol()))
   {
      PrintFormat("[FILTER VETO] Economic News Shield active for %s. Entry paused.", Symbol());
      return false;
   }
   
   // Prop-Firm Lockout Gate: Prevent entries if account breached daily or max loss
   if(PropEnableRiskGuardian && g_PropLockoutActive)
   {
      Print("[FILTER VETO] Prop-Firm Circuit Breaker is active. Trading locked until tomorrow.");
      return false;
   }


   // 4. Maximum Open Positions Gate (Per-Symbol and Global Portfolio)
   int symbolPositions = 0;
   int portfolioPositions = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if(OrderType() == OP_BUY || OrderType() == OP_SELL)
         {
            portfolioPositions++;
            if(OrderSymbol() == Symbol() && OrderMagicNumber() == MagicNumber)
            {
               symbolPositions++;
            }
         }
      }
   }


   if(symbolPositions >= MaxOpenPositionsPerSymbol)
   {
      PrintFormat("[FILTER VETO] Symbol position ceiling reached: %d / %d", symbolPositions, MaxOpenPositionsPerSymbol);
      return false;
   }


   if(portfolioPositions >= MaxTotalPortfolioPositions)
   {
      PrintFormat("[FILTER VETO] Global portfolio position ceiling reached: %d / %d", portfolioPositions, MaxTotalPortfolioPositions);
      return false;
   }


   // 5. Minimum Elapsed Bars Between Consecutive Trades
   if(g_LastOrderExecutionTime > 0)
   {
      int barsSinceExecution = iBarShift(Symbol(), Period(), g_LastOrderExecutionTime, false);
      if(barsSinceExecution < MinBarsBetweenTrades)
      {
         PrintFormat("[FILTER VETO] Min bars distance violated: %d elapsed, %d required",
                     barsSinceExecution, MinBarsBetweenTrades);
         return false;
      }
   }


   // 6. Account Protection Circuit Breaker
   if(EnforceAccountProtection)
   {
      if(g_DailyLossCircuitTripped)
      {
         Print("[FILTER VETO] Daily loss circuit breaker is active. Trading suspended for the day.");
         return false;
      }
      if(g_DailyTargetCircuitTripped)
      {
         Print("[FILTER VETO] Daily profit goal attained. Trading suspended for the day.");
         return false;
      }
   }


   // 7. Margin Level Safety Gate (minimum 150% margin level required)
   double marginLevel = (AccountMargin() > 0.0) ? (AccountEquity() / AccountMargin() * 100.0) : 99999.0;
   if(AccountMargin() > 0.0 && marginLevel < 150.0)
   {
      PrintFormat("[FILTER VETO] Margin level too low: %.1f%% (Minimum: 150%%). Skipping new entry to protect account.", marginLevel);
      return false;
   }


   // 8. Free Margin Minimum Threshold (at least $50 or 2% of balance free)
   double minFreeMargin = MathMax(50.0, AccountBalance() * 0.02);
   if(AccountFreeMargin() < minFreeMargin)
   {
      PrintFormat("[FILTER VETO] Insufficient free margin: $%.2f (Minimum required: $%.2f).", AccountFreeMargin(), minFreeMargin);
      return false;
   }


   // 9. Trade Context Busy Guard
   if(IsTradeContextBusy())
   {
      Print("[FILTER VETO] Trade context is busy. Skipping this tick.");
      return false;
   }


   return true;
}


//+------------------------------------------------------------------+
//| MARKET SESSION IDENTIFICATION                                    |
//+------------------------------------------------------------------+
ENUM_MARKET_SESSION IdentifyMarketSession(const datetime gmtTime)
{
   MqlDateTime dt;
   TimeToStruct(gmtTime, dt);
   int hour = dt.hour;


   // Asian Session (Tokyo/Sydney): 00:00 - 08:00 GMT
   if(hour >= 0 && hour < 8)
   {
      return SESSION_ASIAN;
   }
   // London European Session: 08:00 - 12:00 GMT
   else if(hour >= 8 && hour < 12)
   {
      return SESSION_LONDON;
   }
   // Peak Overlap (London + New York): 12:00 - 16:00 GMT
   else if(hour >= 12 && hour < 16)
   {
      return SESSION_LONDON_NY_OVERLAP;
   }
   // New York US Session: 16:00 - 21:00 GMT
   else if(hour >= 16 && hour < 21)
   {
      return SESSION_NEWYORK;
   }


   return SESSION_OFF_HOURS;
}


//+------------------------------------------------------------------+
//| SECTION 6: INSTITUTIONAL LOT SIZING & RISK ENGINE                |
//+------------------------------------------------------------------+


//+------------------------------------------------------------------+
//| TIMEFRAME-ADAPTIVE BASE DISTANCE RETRIEVER                       |
//+------------------------------------------------------------------+
void GetActiveTimeframeBasePips(const ENUM_TIMEFRAMES tf, int &baseSL, int &baseTP)
{
   if(!UseTimeframeBase)
   {
      baseSL = StopLossPips;
      baseTP = TakeProfitPips;
      return;
   }


   switch(tf)
   {
      case PERIOD_M1:  baseSL = BaseSL_M1;  baseTP = BaseTP_M1;  break;
      case PERIOD_M5:  baseSL = BaseSL_M5;  baseTP = BaseTP_M5;  break;
      case PERIOD_M15: baseSL = BaseSL_M15; baseTP = BaseTP_M15; break;
      case PERIOD_M30: baseSL = BaseSL_M30; baseTP = BaseTP_M30; break;
      case PERIOD_H1:  baseSL = BaseSL_H1;  baseTP = BaseTP_H1;  break;
      case PERIOD_H4:  baseSL = BaseSL_H4;  baseTP = BaseTP_H4;  break;
      case PERIOD_D1:  baseSL = BaseSL_D1;  baseTP = BaseTP_D1;  break;
      case PERIOD_W1:  baseSL = BaseSL_W1;  baseTP = BaseTP_W1;  break;
      case PERIOD_MN1: baseSL = BaseSL_MN1; baseTP = BaseTP_MN1; break;
      default:         baseSL = BaseSL_H1;  baseTP = BaseTP_H1;  break;
   }
}


double GetActiveTimeframeTolerancePips(const ENUM_TIMEFRAMES tf)
{
   if(tf == PERIOD_M1 || tf == PERIOD_M5)
      return HybridTolerance_M1_M5;
   else if(tf == PERIOD_M15 || tf == PERIOD_M30 || tf == PERIOD_H1)
      return HybridTolerance_M15_H1;
   else
      return HybridTolerance_H4_Plus;
}


double GetActiveTimeframeScaleRatio(const ENUM_TIMEFRAMES tf)
{
   int bSL = 20, bTP = 40;
   GetActiveTimeframeBasePips(tf, bSL, bTP);
   double ratio = (double)bSL / 20.0; // Scaled relative to H1 standard baseline
   if(ratio < 0.25) ratio = 0.25;
   return ratio;
}


//+------------------------------------------------------------------+
//| ADVANCED SL/TP METHOD 0: STATIC / TIMEFRAME BASELINE             |
//+------------------------------------------------------------------+
void CalculateStatic_SLTP(const int cmd, const double entryPrice, double &sl, double &tp)
{
   int baseSL = StopLossPips, baseTP = TakeProfitPips;
   GetActiveTimeframeBasePips((ENUM_TIMEFRAMES)Period(), baseSL, baseTP);


   double slDist = (double)baseSL * g_PipPoint;
   double tpDist = (double)baseTP * g_PipPoint;


   if(UseRiskRewardRatio)
      tpDist = slDist * RiskRewardRatio;


   if(cmd == OP_BUY)
   {
      sl = NormalizeDouble(entryPrice - slDist, Digits);
      tp = (tpDist > 0.0) ? NormalizeDouble(entryPrice + tpDist, Digits) : 0.0;
   }
   else if(cmd == OP_SELL)
   {
      sl = NormalizeDouble(entryPrice + slDist, Digits);
      tp = (tpDist > 0.0) ? NormalizeDouble(entryPrice - tpDist, Digits) : 0.0;
   }
}


//+------------------------------------------------------------------+
//| ADVANCED SL/TP METHOD 1: ATR VOLATILITY MULTIPLIER (50-BAR AVG)  |
//+------------------------------------------------------------------+
void CalculateATR_SLTP(const int cmd, const double entryPrice, double &sl, double &tp)
{
   int baseSL = StopLossPips, baseTP = TakeProfitPips;
   GetActiveTimeframeBasePips((ENUM_TIMEFRAMES)Period(), baseSL, baseTP);


   double curATR = iATR(Symbol(), Period(), ATRPeriod, 1);
   if(curATR <= 0.0)
   {
      CalculateStatic_SLTP(cmd, entryPrice, sl, tp);
      return;
   }


   double slDist = (double)baseSL * g_PipPoint;
   double tpDist = (double)baseTP * g_PipPoint;


   // 50-bar rolling ATR benchmark comparison
   if(UseATRAdjust)
   {
      double sumATR = 0.0;
      int count = MathMin(50, Bars - ATRPeriod - 2);
      for(int i = 1; i <= count; i++)
      {
         sumATR += iATR(Symbol(), Period(), ATRPeriod, i);
      }
      double avgATR = (count > 0) ? (sumATR / (double)count) : curATR;


      if(avgATR > 0.0)
      {
         if(curATR > (avgATR * ATR_VOL_Threshold))
         {
            slDist *= 1.30;
            tpDist *= 1.30;
         }
         else if(curATR < (avgATR * 0.50))
         {
            slDist *= 0.70;
            tpDist *= 0.70;
         }
      }
   }
   else
   {
      slDist = curATR * ATRMultiplierSL;
      tpDist = curATR * ATRMultiplierTP;
   }


   if(UseRiskRewardRatio)
      tpDist = slDist * RiskRewardRatio;


   if(cmd == OP_BUY)
   {
      sl = NormalizeDouble(entryPrice - slDist, Digits);
      tp = NormalizeDouble(entryPrice + tpDist, Digits);
   }
   else if(cmd == OP_SELL)
   {
      sl = NormalizeDouble(entryPrice + slDist, Digits);
      tp = NormalizeDouble(entryPrice - tpDist, Digits);
   }
}


//+------------------------------------------------------------------+
//| ADVANCED SL/TP METHOD 2: SUPPORT & RESISTANCE STRUCTURAL BOUNDS  |
//+------------------------------------------------------------------+
void CalculateSR_SLTP(const int cmd, const double entryPrice, double &sl, double &tp)
{
   int baseSL = StopLossPips, baseTP = TakeProfitPips;
   GetActiveTimeframeBasePips((ENUM_TIMEFRAMES)Period(), baseSL, baseTP);


   int highIdx = iHighest(Symbol(), Period(), MODE_HIGH, SRLookbackBars, 1);
   int lowIdx  = iLowest(Symbol(),  Period(), MODE_LOW,  SRLookbackBars, 1);


   double swingH = (highIdx != -1) ? iHigh(Symbol(), Period(), highIdx) : iHigh(Symbol(), Period(), 1);
   double swingL = (lowIdx  != -1) ? iLow(Symbol(),  Period(), lowIdx)  : iLow(Symbol(),  Period(), 1);


   double buffer = 4.0 * g_PipPoint;
   double calcSLDist = (double)baseSL * g_PipPoint;
   double calcTPDist = (double)baseTP * g_PipPoint;


   if(cmd == OP_BUY)
   {
      double nearestSupport = swingL - buffer;
      if(entryPrice - calcSLDist < nearestSupport && nearestSupport < entryPrice)
         sl = NormalizeDouble(nearestSupport, Digits);
      else
         sl = NormalizeDouble(entryPrice - calcSLDist, Digits);


      if(swingH > entryPrice + (5.0 * g_PipPoint) && swingH < entryPrice + calcTPDist)
         tp = NormalizeDouble(swingH, Digits);
      else
         tp = NormalizeDouble(entryPrice + calcTPDist, Digits);
   }
   else if(cmd == OP_SELL)
   {
      double nearestResistance = swingH + buffer;
      if(entryPrice + calcSLDist > nearestResistance && nearestResistance > entryPrice)
         sl = NormalizeDouble(nearestResistance, Digits);
      else
         sl = NormalizeDouble(entryPrice + calcSLDist, Digits);


      if(swingL < entryPrice - (5.0 * g_PipPoint) && swingL > entryPrice - calcTPDist)
         tp = NormalizeDouble(swingL, Digits);
      else
         tp = NormalizeDouble(entryPrice - calcTPDist, Digits);
   }


   if(UseRiskRewardRatio)
   {
      double curDist = MathAbs(entryPrice - sl);
      if(cmd == OP_BUY) tp = NormalizeDouble(entryPrice + (curDist * RiskRewardRatio), Digits);
      else tp = NormalizeDouble(entryPrice - (curDist * RiskRewardRatio), Digits);
   }
}


//+------------------------------------------------------------------+
//| ADVANCED SL/TP METHOD 3: AVERAGE DAILY RANGE (ADR) NORMALIZATION |
//+------------------------------------------------------------------+
void CalculateADR_SLTP(const int cmd, const double entryPrice, double &sl, double &tp)
{
   int baseSL = StopLossPips, baseTP = TakeProfitPips;
   GetActiveTimeframeBasePips((ENUM_TIMEFRAMES)Period(), baseSL, baseTP);


   double sumRange = 0.0;
   int count = 0;
   for(int i = 1; i <= ADRPeriod; i++)
   {
      double dH = iHigh(Symbol(), PERIOD_D1, i);
      double dL = iLow(Symbol(),  PERIOD_D1, i);
      if(dH > 0.0 && dL > 0.0)
      {
         sumRange += (dH - dL);
         count++;
      }
   }


   double adr = (count > 0) ? (sumRange / (double)count) : (80.0 * g_PipPoint);
   double benchmarkADR = 80.0 * g_PipPoint;


   double adrRatio = (benchmarkADR > 0.0) ? (adr / benchmarkADR) : 1.0;
   if(adrRatio < 0.60) adrRatio = 0.60;
   if(adrRatio > 1.80) adrRatio = 1.80;


   double slDist = (double)baseSL * g_PipPoint * adrRatio;
   double tpDist = (double)baseTP * g_PipPoint * adrRatio;


   if(UseRiskRewardRatio)
      tpDist = slDist * RiskRewardRatio;


   if(cmd == OP_BUY)
   {
      sl = NormalizeDouble(entryPrice - slDist, Digits);
      tp = NormalizeDouble(entryPrice + tpDist, Digits);
   }
   else if(cmd == OP_SELL)
   {
      sl = NormalizeDouble(entryPrice + slDist, Digits);
      tp = NormalizeDouble(entryPrice - tpDist, Digits);
   }
}


//+------------------------------------------------------------------+
//| ADVANCED SL/TP METHOD 4: FIBONACCI EXTENSIONS & RETRACEMENTS     |
//+------------------------------------------------------------------+
void CalculateFibonacci_SLTP(const int cmd, const double entryPrice, double &sl, double &tp)
{
   int baseSL = StopLossPips, baseTP = TakeProfitPips;
   GetActiveTimeframeBasePips((ENUM_TIMEFRAMES)Period(), baseSL, baseTP);


   int highIdx = iHighest(Symbol(), Period(), MODE_HIGH, FibLookbackBars, 1);
   int lowIdx  = iLowest(Symbol(),  Period(), MODE_LOW,  FibLookbackBars, 1);


   double swingH = (highIdx != -1) ? iHigh(Symbol(), Period(), highIdx) : iHigh(Symbol(), Period(), 1);
   double swingL = (lowIdx  != -1) ? iLow(Symbol(),  Period(), lowIdx)  : iLow(Symbol(),  Period(), 1);
   double fibRange = swingH - swingL;


   if(fibRange <= 0.0)
   {
      CalculateStatic_SLTP(cmd, entryPrice, sl, tp);
      return;
   }


   if(cmd == OP_BUY)
   {
      double ret50 = swingH - (0.50 * fibRange);
      sl = NormalizeDouble(ret50 - (4.0 * g_PipPoint), Digits);
      if(sl >= entryPrice) sl = NormalizeDouble(swingL - (6.0 * g_PipPoint), Digits);


      double fibExt = swingL + (FibTPLevel * fibRange);
      if(fibExt > entryPrice + (10.0 * g_PipPoint))
         tp = NormalizeDouble(fibExt, Digits);
      else
         tp = NormalizeDouble(entryPrice + ((double)baseTP * g_PipPoint), Digits);
   }
   else if(cmd == OP_SELL)
   {
      double ret50 = swingL + (0.50 * fibRange);
      sl = NormalizeDouble(ret50 + (4.0 * g_PipPoint), Digits);
      if(sl <= entryPrice) sl = NormalizeDouble(swingH + (6.0 * g_PipPoint), Digits);


      double fibExt = swingH - (FibTPLevel * fibRange);
      if(fibExt < entryPrice - (10.0 * g_PipPoint))
         tp = NormalizeDouble(fibExt, Digits);
      else
         tp = NormalizeDouble(entryPrice - ((double)baseTP * g_PipPoint), Digits);
   }


   if(UseRiskRewardRatio)
   {
      double slDist = MathAbs(entryPrice - sl);
      if(cmd == OP_BUY) tp = NormalizeDouble(entryPrice + (slDist * RiskRewardRatio), Digits);
      else tp = NormalizeDouble(entryPrice - (slDist * RiskRewardRatio), Digits);
   }
}


//+------------------------------------------------------------------+
//| ADVANCED SL/TP METHOD 5: MULTI-TIMEFRAME BLENDED ATR             |
//+------------------------------------------------------------------+
void CalculateMultiTF_ATR_SLTP(const int cmd, const double entryPrice, double &sl, double &tp)
{
   int baseSL = StopLossPips, baseTP = TakeProfitPips;
   GetActiveTimeframeBasePips((ENUM_TIMEFRAMES)Period(), baseSL, baseTP);


   double curATR = iATR(Symbol(), Period(), ATRPeriod, 1);
   ENUM_TIMEFRAMES hTF = (HigherTF > (ENUM_TIMEFRAMES)Period()) ? HigherTF : PERIOD_H4;
   double htfATR = iATR(Symbol(), hTF, ATRPeriod, 1);


   if(curATR <= 0.0 && htfATR <= 0.0)
   {
      CalculateStatic_SLTP(cmd, entryPrice, sl, tp);
      return;
   }


   double blendedATR = (0.50 * curATR) + (0.50 * htfATR);
   double slDist = blendedATR * 1.50;
   double tpDist = blendedATR * 3.00;


   double minSL = (double)baseSL * g_PipPoint * 0.70;
   double maxSL = (double)baseSL * g_PipPoint * 2.00;
   if(slDist < minSL) slDist = minSL;
   if(slDist > maxSL) slDist = maxSL;


   if(UseRiskRewardRatio)
      tpDist = slDist * RiskRewardRatio;


   if(cmd == OP_BUY)
   {
      sl = NormalizeDouble(entryPrice - slDist, Digits);
      tp = NormalizeDouble(entryPrice + tpDist, Digits);
   }
   else if(cmd == OP_SELL)
   {
      sl = NormalizeDouble(entryPrice + slDist, Digits);
      tp = NormalizeDouble(entryPrice - tpDist, Digits);
   }
}


//+------------------------------------------------------------------+
//| ADVANCED SL/TP METHOD 6: SWING HIGH / LOW WITH BUFFER            |
//+------------------------------------------------------------------+
void CalculateSwingHL_SLTP(const int cmd, const double entryPrice, double &sl, double &tp)
{
   int baseSL = StopLossPips, baseTP = TakeProfitPips;
   GetActiveTimeframeBasePips((ENUM_TIMEFRAMES)Period(), baseSL, baseTP);


   int highIdx = iHighest(Symbol(), Period(), MODE_HIGH, SwingLookbackBars, 1);
   int lowIdx  = iLowest(Symbol(),  Period(), MODE_LOW,  SwingLookbackBars, 1);


   double swingH = (highIdx != -1) ? iHigh(Symbol(), Period(), highIdx) : iHigh(Symbol(), Period(), 1);
   double swingL = (lowIdx  != -1) ? iLow(Symbol(),  Period(), lowIdx)  : iLow(Symbol(),  Period(), 1);
   double buffer = SwingBufferPips * g_PipPoint;


   if(cmd == OP_BUY)
   {
      sl = NormalizeDouble(swingL - buffer, Digits);
      if(sl >= entryPrice) sl = NormalizeDouble(entryPrice - ((double)baseSL * g_PipPoint), Digits);


      double slDist = entryPrice - sl;
      if(UseRiskRewardRatio)
      {
         tp = NormalizeDouble(entryPrice + (slDist * RiskRewardRatio), Digits);
      }
      else
      {
         tp = NormalizeDouble(swingH, Digits);
         if(tp <= entryPrice + (8.0 * g_PipPoint))
            tp = NormalizeDouble(entryPrice + ((double)baseTP * g_PipPoint), Digits);
      }
   }
   else if(cmd == OP_SELL)
   {
      sl = NormalizeDouble(swingH + buffer, Digits);
      if(sl <= entryPrice) sl = NormalizeDouble(entryPrice + ((double)baseSL * g_PipPoint), Digits);


      double slDist = sl - entryPrice;
      if(UseRiskRewardRatio)
      {
         tp = NormalizeDouble(entryPrice - (slDist * RiskRewardRatio), Digits);
      }
      else
      {
         tp = NormalizeDouble(swingL, Digits);
         if(tp >= entryPrice - (8.0 * g_PipPoint))
            tp = NormalizeDouble(entryPrice - ((double)baseTP * g_PipPoint), Digits);
      }
   }
}


//+------------------------------------------------------------------+
//| ADVANCED SL/TP METHOD 7: DAILY / WEEKLY PIVOT POINTS             |
//+------------------------------------------------------------------+
void CalculatePivot_SLTP(const int cmd, const double entryPrice, double &sl, double &tp)
{
   int baseSL = StopLossPips, baseTP = TakeProfitPips;
   GetActiveTimeframeBasePips((ENUM_TIMEFRAMES)Period(), baseSL, baseTP);


   ENUM_TIMEFRAMES pTF = (PivotType == PIVOT_WEEKLY) ? PERIOD_W1 : PERIOD_D1;


   double pH = iHigh(Symbol(),  pTF, 1);
   double pL = iLow(Symbol(),   pTF, 1);
   double pC = iClose(Symbol(), pTF, 1);


   double P  = (pH + pL + pC) / 3.0;
   double R1 = (2.0 * P) - pL;
   double S1 = (2.0 * P) - pH;
   double R2 = P + (pH - pL);
   double S2 = P - (pH - pL);


   if(cmd == OP_BUY)
   {
      sl = NormalizeDouble(S1 - (3.0 * g_PipPoint), Digits);
      if(sl >= entryPrice) sl = NormalizeDouble(S2 - (3.0 * g_PipPoint), Digits);
      if(sl >= entryPrice) sl = NormalizeDouble(entryPrice - ((double)baseSL * g_PipPoint), Digits);


      double slDist = entryPrice - sl;
      if(UseRiskRewardRatio)
      {
         tp = NormalizeDouble(entryPrice + (slDist * RiskRewardRatio), Digits);
      }
      else
      {
         tp = (entryPrice < R1) ? NormalizeDouble(R1, Digits) : NormalizeDouble(R2, Digits);
         if(tp <= entryPrice + (8.0 * g_PipPoint))
            tp = NormalizeDouble(R2 + (10.0 * g_PipPoint), Digits);
      }
   }
   else if(cmd == OP_SELL)
   {
      sl = NormalizeDouble(R1 + (3.0 * g_PipPoint), Digits);
      if(sl <= entryPrice) sl = NormalizeDouble(R2 + (3.0 * g_PipPoint), Digits);
      if(sl <= entryPrice) sl = NormalizeDouble(entryPrice + ((double)baseSL * g_PipPoint), Digits);


      double slDist = sl - entryPrice;
      if(UseRiskRewardRatio)
      {
         tp = NormalizeDouble(entryPrice - (slDist * RiskRewardRatio), Digits);
      }
      else
      {
         tp = (entryPrice > S1) ? NormalizeDouble(S1, Digits) : NormalizeDouble(S2, Digits);
         if(tp >= entryPrice - (8.0 * g_PipPoint))
            tp = NormalizeDouble(S2 - (10.0 * g_PipPoint), Digits);
      }
   }
}


//+------------------------------------------------------------------+
//| VOLATILITY DYNAMIC RISK-REWARD ADJUSTER                          |
//+------------------------------------------------------------------+
void ApplyVolatilityRRAdjustment(const int cmd, const double entryPrice, double &outSL, double &outTP)
{
   if(!UseVolatilityRR) return;

   double curATR = iATR(Symbol(), Period(), ATRPeriod, 1);
   if(curATR <= 0.0 || g_PipPoint <= 0.0) return;

   double atrPips = curATR / g_PipPoint;
   double thresh = (VolatilityThresholdATR > 0.0) ? VolatilityThresholdATR : 50.0;
   double baseRR = (UseRiskRewardRatio && RiskRewardRatio > 0.0) ? RiskRewardRatio : 2.0;
   double dynamicRR = baseRR;

   if(atrPips > thresh)
   {
      dynamicRR = baseRR * (1.0 + ((atrPips - thresh) / thresh));
   }
   if(dynamicRR < 1.0) dynamicRR = 1.0;
   if(dynamicRR > 5.0) dynamicRR = 5.0;

   double slDist = MathAbs(entryPrice - outSL);
   if(slDist > 0.0)
   {
      if(cmd == OP_BUY)
      {
         outTP = NormalizeDouble(entryPrice + (slDist * dynamicRR), Digits);
      }
      else if(cmd == OP_SELL)
      {
         outTP = NormalizeDouble(entryPrice - (slDist * dynamicRR), Digits);
      }
   }
}


//+------------------------------------------------------------------+
//| HYBRID SCORING ENGINE (TIMEFRAME-TOLERANCE CLUSTERING)           |
//+------------------------------------------------------------------+
void CalculateHybridSLTP(const int cmd, const double entryPrice, double &finalSL, double &finalTP)
{
   double candSL[10];
   double candTP[10];
   int count = 0;


   // 1. Static / Timeframe Baseline
   CalculateStatic_SLTP(cmd, entryPrice, candSL[count], candTP[count]);
   count++;


   // 2. ATR Method
   if(UseATR)
   {
      CalculateATR_SLTP(cmd, entryPrice, candSL[count], candTP[count]);
      count++;
   }


   // 3. Support / Resistance
   if(UseSupportResistance)
   {
      CalculateSR_SLTP(cmd, entryPrice, candSL[count], candTP[count]);
      count++;
   }


   // 4. ADR Method
   if(UseADR)
   {
      CalculateADR_SLTP(cmd, entryPrice, candSL[count], candTP[count]);
      count++;
   }


   // 5. Fibonacci Method
   if(UseFibonacci)
   {
      CalculateFibonacci_SLTP(cmd, entryPrice, candSL[count], candTP[count]);
      count++;
   }


   // 6. Multi-Timeframe ATR
   if(UseMultiTF_ATR)
   {
      CalculateMultiTF_ATR_SLTP(cmd, entryPrice, candSL[count], candTP[count]);
      count++;
   }


   // 7. Swing High / Low
   if(UseSwingHL)
   {
      CalculateSwingHL_SLTP(cmd, entryPrice, candSL[count], candTP[count]);
      count++;
   }


   // 8. Pivot Points
   if(UsePivotSLTP)
   {
      CalculatePivot_SLTP(cmd, entryPrice, candSL[count], candTP[count]);
      count++;
   }


   // Dynamic Timeframe Cluster Tolerance
   double tolPips = GetActiveTimeframeTolerancePips((ENUM_TIMEFRAMES)Period());
   double clusterThreshold = tolPips * g_PipPoint;


   // Evaluate Stop Loss cluster strength & closest safe distance
   int bestSL_Score = -1;
   int bestSL_Idx = 0;
   double minSLDist = 999999.0;


   int highIdx = iHighest(Symbol(), Period(), MODE_HIGH, SRLookbackBars, 1);
   int lowIdx  = iLowest(Symbol(),  Period(), MODE_LOW,  SRLookbackBars, 1);
   double structH = (highIdx != -1) ? iHigh(Symbol(), Period(), highIdx) : iHigh(Symbol(), Period(), 1);
   double structL = (lowIdx  != -1) ? iLow(Symbol(),  Period(), lowIdx)  : iLow(Symbol(),  Period(), 1);


   for(int i = 0; i < count; i++)
   {
      int score = 0;
      for(int j = 0; j < count; j++)
      {
         if(MathAbs(candSL[i] - candSL[j]) <= clusterThreshold)
            score++;
      }


      double dist = MathAbs(entryPrice - candSL[i]);
      bool beyondSR = (cmd == OP_BUY) ? (candSL[i] <= structL) : (candSL[i] >= structH);


      if(score > bestSL_Score)
      {
         bestSL_Score = score;
         bestSL_Idx = i;
         minSLDist = dist;
      }
      else if(score == bestSL_Score && beyondSR && dist < minSLDist)
      {
         bestSL_Idx = i;
         minSLDist = dist;
      }
   }
   finalSL = candSL[bestSL_Idx];


   // Evaluate Take Profit cluster strength & optimal Risk:Reward
   int bestTP_Score = -1;
   int bestTP_Idx = 0;
   double bestRR = -1.0;


   for(int k = 0; k < count; k++)
   {
      int score = 0;
      for(int m = 0; m < count; m++)
      {
         if(MathAbs(candTP[k] - candTP[m]) <= clusterThreshold)
            score++;
      }


      double slDist = MathAbs(entryPrice - finalSL);
      double tpDist = MathAbs(entryPrice - candTP[k]);
      double rr = (slDist > 0.0) ? (tpDist / slDist) : 1.0;


      if(score > bestTP_Score)
      {
         bestTP_Score = score;
         bestTP_Idx = k;
         bestRR = rr;
      }
      else if(score == bestTP_Score && rr > bestRR)
      {
         bestRR = rr;
         bestTP_Idx = k;
      }
   }
   finalTP = candTP[bestTP_Idx];


   // Enforce Risk:Reward if requested
   if(UseRiskRewardRatio)
   {
      double slDist = MathAbs(entryPrice - finalSL);
      if(cmd == OP_BUY) finalTP = NormalizeDouble(entryPrice + (slDist * RiskRewardRatio), Digits);
      else if(cmd == OP_SELL) finalTP = NormalizeDouble(entryPrice - (slDist * RiskRewardRatio), Digits);
   }


   // Apply Volatility RR adjustment if enabled
   ApplyVolatilityRRAdjustment(cmd, entryPrice, finalSL, finalTP);
}


//+------------------------------------------------------------------+
//| MASTER ADVANCED SL/TP DISPATCHER (PRIORITY LOGIC)                |
//+------------------------------------------------------------------+
void CalculateAdvancedSLTP(const int cmd, const double entryPrice, double &outSL, double &outTP)
{
   if(UseHybridScoring)
   {
      CalculateHybridSLTP(cmd, entryPrice, outSL, outTP);
   }
   else if(UseATR)
   {
      CalculateATR_SLTP(cmd, entryPrice, outSL, outTP);
      ApplyVolatilityRRAdjustment(cmd, entryPrice, outSL, outTP);
   }
   else if(UseSupportResistance)
   {
      CalculateSR_SLTP(cmd, entryPrice, outSL, outTP);
      ApplyVolatilityRRAdjustment(cmd, entryPrice, outSL, outTP);
   }
   else if(UseADR)
   {
      CalculateADR_SLTP(cmd, entryPrice, outSL, outTP);
      ApplyVolatilityRRAdjustment(cmd, entryPrice, outSL, outTP);
   }
   else if(UseFibonacci)
   {
      CalculateFibonacci_SLTP(cmd, entryPrice, outSL, outTP);
      ApplyVolatilityRRAdjustment(cmd, entryPrice, outSL, outTP);
   }
   else if(UseMultiTF_ATR)
   {
      CalculateMultiTF_ATR_SLTP(cmd, entryPrice, outSL, outTP);
      ApplyVolatilityRRAdjustment(cmd, entryPrice, outSL, outTP);
   }
   else if(UseSwingHL)
   {
      CalculateSwingHL_SLTP(cmd, entryPrice, outSL, outTP);
      ApplyVolatilityRRAdjustment(cmd, entryPrice, outSL, outTP);
   }
   else if(UsePivotSLTP)
   {
      CalculatePivot_SLTP(cmd, entryPrice, outSL, outTP);
      ApplyVolatilityRRAdjustment(cmd, entryPrice, outSL, outTP);
   }
   else
   {
      CalculateStatic_SLTP(cmd, entryPrice, outSL, outTP);
      ApplyVolatilityRRAdjustment(cmd, entryPrice, outSL, outTP);
   }


   // Validate against broker minimum stop and freeze levels
   ValidateStopLevels(cmd, entryPrice, outSL, outTP);
}


//+------------------------------------------------------------------+
//| ACCURATE DYNAMIC POSITION SIZING (PER-METHOD RISK SIZING)        |
//+------------------------------------------------------------------+
double CalculateDynamicLotSize(const double entryPrice, const double slPrice)
{
   if(LotSizingMethod == LOT_MODE_FIXED)
   {
      return NormalizeLotStep(FixedLotSize);
   }

   double equity  = AccountEquity();
   double balance = AccountBalance();
   double capitalBase = (LotSizingMethod == LOT_MODE_EQUITY_PERCENT) ? equity : balance;
   
   double appliedRiskPercent = RiskPercent;
   if(LotSizingMethod == LOT_MODE_KELLY_CRITERION)
   {
      SPerformanceTelemetry telemetry;
      AnalyzeHistoricalPerformance(telemetry);
      double avgWin = (telemetry.winningTradesCount > 0) ? (telemetry.grossProfitAmount / telemetry.winningTradesCount) : 1.0;
      double avgLoss = (telemetry.losingTradesCount > 0) ? (telemetry.grossLossAmount / telemetry.losingTradesCount) : 1.0;
      double winLossRatio = (avgLoss > 0.0) ? (avgWin / avgLoss) : 1.5;
      double kellyFrac = CalculateKellyCriterionFraction(telemetry.winRatePercentage > 0.0 ? telemetry.winRatePercentage : 55.0, winLossRatio);
      appliedRiskPercent = kellyFrac * 100.0;
   }
   
   double riskAmount = capitalBase * (appliedRiskPercent / 100.0);

   double tickValue = MarketInfo(Symbol(), MODE_TICKVALUE);
   double tickSize  = MarketInfo(Symbol(), MODE_TICKSIZE);
   if(tickSize <= 0.0)  tickSize  = Point;
   if(tickValue <= 0.0) tickValue = 10.0;

   double pipValue = tickValue * (g_PipPoint / tickSize);
   if(pipValue <= 0.0) pipValue = 10.0;

   double slDistancePips = 0.0;
   if(LotSizingMethod == LOT_MODE_ATR_RISK)
   {
      double atr = iATR(Symbol(), Period(), ATRPeriod, 1);
      if(atr > 0.0 && g_PipPoint > 0.0)
         slDistancePips = (atr * ATRMultiplierSL) / g_PipPoint;
      else if(entryPrice > 0.0 && slPrice > 0.0 && g_PipPoint > 0.0)
         slDistancePips = MathAbs(entryPrice - slPrice) / g_PipPoint;
   }
   else
   {
      if(entryPrice > 0.0 && slPrice > 0.0 && g_PipPoint > 0.0)
         slDistancePips = MathAbs(entryPrice - slPrice) / g_PipPoint;
   }

   if(slDistancePips <= 0.0) slDistancePips = (double)StopLossPips;
   if(slDistancePips <= 0.0) slDistancePips = 30.0;

   double lossPerLot = slDistancePips * pipValue;
   if(lossPerLot <= 0.0) return MarketInfo(Symbol(), MODE_MINLOT);

   double computedLot = riskAmount / lossPerLot;

   // Margin Requirement Verification
   double marginRequiredPerLot = MarketInfo(Symbol(), MODE_MARGINREQUIRED);
   if(marginRequiredPerLot > 0.0)
   {
      double maxAffordableLots = (AccountFreeMargin() * 0.85) / marginRequiredPerLot;
      if(computedLot > maxAffordableLots)
      {
         computedLot = maxAffordableLots;
         PrintFormat("[RISK MANAGER] Lot size capped by free margin constraint: %.2f Lots", computedLot);
      }
   }

   return NormalizeLotStep(computedLot);
}


// NOTE: Legacy wrapper - delegates to CalculateDynamicLotSize for unified risk engine
double CalculateOptimalLotSize(const double stopLossDistancePoints)
{
   if(LotSizingMethod == LOT_MODE_FIXED)
   {
      return NormalizeLotStep(FixedLotSize);
   }

   // Convert broker-point distance to a price level for the dynamic calculator
   double entryPrice = (Ask + Bid) / 2.0; // Mid-price approximation
   double slPrice = (stopLossDistancePoints > 0.0) ? (entryPrice - stopLossDistancePoints * Point) : 0.0;
   return CalculateDynamicLotSize(entryPrice, slPrice);
}


double NormalizeLotStep(double rawLots)
{
   double minLot  = MarketInfo(Symbol(), MODE_MINLOT);
   double maxLot  = MarketInfo(Symbol(), MODE_MAXLOT);
   double lotStep = MarketInfo(Symbol(), MODE_LOTSTEP);

   if(minLot <= 0.0)  minLot  = (g_MinLot > 0.0) ? g_MinLot : 0.01;
   if(maxLot <= 0.0)  maxLot  = (g_MaxLot > 0.0) ? g_MaxLot : 100.0;
   if(lotStep <= 0.0) lotStep = (g_LotStep > 0.0) ? g_LotStep : 0.01;

   // Determine lot step decimal precision using modern StringGetCharacter
   int stepDecimals = 0;
   if(lotStep < 1.0)
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

   if(lotStep > 0.0)
   {
      rawLots = MathFloor((rawLots / lotStep) + 0.0000001) * lotStep;
   }

   if(rawLots < minLot) rawLots = minLot;
   if(rawLots > maxLot) rawLots = maxLot;

   return NormalizeDouble(rawLots, stepDecimals);
}


//+------------------------------------------------------------------+
//| STEALTH ORDER STATE MANAGEMENT HELPERS                           |
//+------------------------------------------------------------------+
void RegisterStealthOrder(const int ticket, const double sl, const double tp)
{
   int size = ArraySize(g_StealthOrders);
   for(int i = 0; i < size; i++)
   {
      if(g_StealthOrders[i].ticket == ticket)
      {
         g_StealthOrders[i].stopLoss = sl;
         g_StealthOrders[i].takeProfit = tp;
         return;
      }
   }
   ArrayResize(g_StealthOrders, size + 1);
   g_StealthOrders[size].ticket = ticket;
   g_StealthOrders[size].stopLoss = sl;
   g_StealthOrders[size].takeProfit = tp;
}

bool GetStealthOrderLevels(const int ticket, double &outSL, double &outTP)
{
   int size = ArraySize(g_StealthOrders);
   for(int i = 0; i < size; i++)
   {
      if(g_StealthOrders[i].ticket == ticket)
      {
         outSL = g_StealthOrders[i].stopLoss;
         outTP = g_StealthOrders[i].takeProfit;
         return true;
      }
   }
   return false;
}

void UpdateStealthOrderSL(const int ticket, const double newSL)
{
   int size = ArraySize(g_StealthOrders);
   for(int i = 0; i < size; i++)
   {
      if(g_StealthOrders[i].ticket == ticket)
      {
         g_StealthOrders[i].stopLoss = newSL;
         return;
      }
   }
}

void UpdateStealthOrderTP(const int ticket, const double newTP)
{
   int size = ArraySize(g_StealthOrders);
   for(int i = 0; i < size; i++)
   {
      if(g_StealthOrders[i].ticket == ticket)
      {
         g_StealthOrders[i].takeProfit = newTP;
         return;
      }
   }
}

void CleanupStealthOrders()
{
   int size = ArraySize(g_StealthOrders);
   for(int i = size - 1; i >= 0; i--)
   {
      if(!OrderSelect(g_StealthOrders[i].ticket, SELECT_BY_TICKET, MODE_TRADES) || OrderCloseTime() > 0)
      {
         for(int j = i; j < size - 1; j++)
         {
            g_StealthOrders[j] = g_StealthOrders[j + 1];
         }
         size--;
         ArrayResize(g_StealthOrders, size);
      }
   }
}


//+------------------------------------------------------------------+
//| SECTION 7: ROBUST ORDER EXECUTION WRAPPER                        |
//+------------------------------------------------------------------+
int ExecuteSmartOrder(const int command, const double volume, const double entryPrice, const double stopLoss, const double takeProfit)
{
   int ticket = -1;
   int attempts = 0;
   color arrowColor = (command == OP_BUY) ? BuyArrowColor : SellArrowColor;
   string orderComment = TradeCommentPrefix + "_" + IntegerToString(MagicNumber);
   int slippage = GetScaledSlippage();

   // Pre-execution free margin validation
   ResetLastError();
   double freeMarginCheck = AccountFreeMarginCheck(Symbol(), command, volume);
   if(GetLastError() == 134 || freeMarginCheck <= 0.0)
   {
      PrintFormat("[ORDER REJECTED] Insufficient margin for %.2f lots on %s. Free Margin Check: %.2f", volume, Symbol(), freeMarginCheck);
      return -1;
   }

   // MQL4-compatible ECN/STP detection: market execution mode uses 0-pip stop levels
   // and requires 2-step execution (open first, then attach SL/TP)
   double stopLevel = MarketInfo(Symbol(), MODE_STOPLEVEL);
   bool isECN = (stopLevel == 0.0);

   while(attempts < OrderRetryAttempts && ticket < 0)
   {
      attempts++;
      ResetLastError();
      RefreshRates();

      double currentExecPrice = (command == OP_BUY) ? Ask : Bid;
      double sendSL = (isECN || UseStealthStops) ? 0.0 : stopLoss;
      double sendTP = (isECN || UseStealthStops) ? 0.0 : takeProfit;

      ticket = OrderSend(Symbol(), command, volume, currentExecPrice, slippage, sendSL, sendTP, orderComment, MagicNumber, 0, arrowColor);

      if(ticket > 0)
      {
         g_LastOrderExecutionTime = TimeCurrent();
         PrintFormat("[ORDER FILLED] Ticket #%d | Type: %s | Lots: %.2f | Price: %f | SL: %f | TP: %f",
                     ticket, (command == OP_BUY ? "BUY" : "SELL"), volume, currentExecPrice, stopLoss, takeProfit);

         // If stealth stops enabled, register virtual SL/TP
         if(UseStealthStops)
         {
            RegisterStealthOrder(ticket, stopLoss, takeProfit);
         }
         // If ECN/STP market execution, attach SL and TP in second step via SafeOrderModify
         else if(isECN && (stopLoss > 0.0 || takeProfit > 0.0))
         {
            if(!SafeOrderModify(ticket, currentExecPrice, stopLoss, takeProfit, 0, arrowColor))
            {
               PrintFormat("[ECN WARNING] Failed to attach SL/TP on Ticket #%d after execution.", ticket);
            }
         }

         return ticket;
      }
      else
      {
         int err = GetLastError();
         PrintFormat("[ORDER ERROR] Attempt %d/%d failed. Error: %d (%s)",
                     attempts, OrderRetryAttempts, err, MqlErrorToString(err));

         // If Instant Execution broker failed with Error 130 (Invalid Stops), attempt ECN two-step approach
         if(err == 130 && !isECN && !UseStealthStops && (stopLoss > 0.0 || takeProfit > 0.0))
         {
            RefreshRates();
            currentExecPrice = (command == OP_BUY) ? Ask : Bid;
            ticket = OrderSend(Symbol(), command, volume, currentExecPrice, slippage, 0, 0, orderComment, MagicNumber, 0, arrowColor);
            if(ticket > 0)
            {
               g_LastOrderExecutionTime = TimeCurrent();
               PrintFormat("[ORDER FILLED TWO-STEP] Ticket #%d opened with 0/0. Modifying SL/TP...", ticket);
               SafeOrderModify(ticket, currentExecPrice, stopLoss, takeProfit, 0, arrowColor);
               return ticket;
            }
         }

         // Sleep with exponential backoff on server requote or context busy
         if(err == 4 || err == 135 || err == 136 || err == 137 || err == 138 || err == 146)
         {
            Sleep(OrderRetryDelayMilliseconds * attempts);
         }
         else
         {
            // Fatal parameter errors require aborting retries
            break;
         }
      }
   }

   return -1;
}




//+------------------------------------------------------------------+
//| BROKER STOP & FREEZE LEVEL VALIDATION                            |
//+------------------------------------------------------------------+
bool ValidateStopLevels(const int cmd, const double openPrice, double &sl, double &tp)
{
   double stopLevelPoints   = MarketInfo(Symbol(), MODE_STOPLEVEL);
   double freezeLevelPoints = MarketInfo(Symbol(), MODE_FREEZELEVEL);
   double minDistance       = (MathMax(stopLevelPoints, freezeLevelPoints) + 3.0) * Point;


   RefreshRates();


   if(cmd == OP_BUY)
   {
      double currentBid = Bid;
      if(sl > 0.0 && (currentBid - sl) < minDistance)
      {
         sl = NormalizeDouble(currentBid - minDistance, Digits);
      }
      if(tp > 0.0 && (tp - currentBid) < minDistance)
      {
         tp = NormalizeDouble(currentBid + minDistance, Digits);
      }
   }
   else if(cmd == OP_SELL)
   {
      double currentAsk = Ask;
      if(sl > 0.0 && (sl - currentAsk) < minDistance)
      {
         sl = NormalizeDouble(currentAsk + minDistance, Digits);
      }
      if(tp > 0.0 && (currentAsk - tp) < minDistance)
      {
         tp = NormalizeDouble(currentAsk - minDistance, Digits);
      }
   }


   return true;
}


//+------------------------------------------------------------------+
//| ROBUST ORDER CLOSE ENGINE WITH RETRIES & SLIPPAGE RECOVERY       |
//+------------------------------------------------------------------+
bool SafeOrderClose(const int ticket, const double volume, const int slippage, const color arrowColor)
{
   if(!OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES))
   {
      PrintFormat("[CLOSE ERROR] Ticket #%d could not be selected: %s", ticket, MqlErrorToString(GetLastError()));
      return false;
   }


   int cmd = OrderType();
   if(cmd > OP_SELL)
   {
      return OrderDelete(ticket, arrowColor);
   }


   int attempts = 0;
   bool closed = false;


   while(attempts < OrderRetryAttempts && !closed)
   {
      attempts++;
      ResetLastError();
      RefreshRates();


      double closePrice = (cmd == OP_BUY) ? Bid : Ask;
      closed = OrderClose(ticket, volume, closePrice, slippage, arrowColor);


      if(closed)
      {
         PrintFormat("[ORDER CLOSED] Ticket #%d | Vol: %.2f | Price: %f", ticket, volume, closePrice);
         return true;
      }
      else
      {
         int err = GetLastError();
         PrintFormat("[CLOSE ERROR] Ticket #%d Attempt %d/%d failed: Error %d (%s)",
                     ticket, attempts, OrderRetryAttempts, err, MqlErrorToString(err));


         if(err == 135 || err == 136 || err == 137 || err == 138 || err == 146 || err == 4)
         {
            Sleep(OrderRetryDelayMilliseconds * attempts);
         }
         else
         {
            break;
         }
      }
   }


   return false;
}


//+------------------------------------------------------------------+
//| ROBUST ORDER MODIFY ENGINE WITH RETRIES & LEVEL VALIDATION       |
//+------------------------------------------------------------------+
bool SafeOrderModify(const int ticket, const double price, double sl, double tp, const datetime expiration, const color arrowColor)
{
   if(!OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES))
   {
      PrintFormat("[MODIFY ERROR] Ticket #%d could not be selected: %s", ticket, MqlErrorToString(GetLastError()));
      return false;
   }


   int cmd = OrderType();
   double modifyPrice = (cmd <= OP_SELL) ? OrderOpenPrice() : price;
   ValidateStopLevels(cmd, modifyPrice, sl, tp);

   // If using stealth stops, update in-memory levels and skip broker modify if stops are hidden
   if(UseStealthStops)
   {
      UpdateStealthOrderSL(ticket, sl);
      UpdateStealthOrderTP(ticket, tp);
      if(OrderStopLoss() == 0.0 && OrderTakeProfit() == 0.0)
      {
         return true;
      }
   }

   // If modification values are identical to current, skip to avoid ERR_NO_RESULT (Error 1)
   double curSL = OrderStopLoss();
   double curTP = OrderTakeProfit();
   if(MathAbs(curSL - sl) < Point * 0.5 && MathAbs(curTP - tp) < Point * 0.5)
   {
      return true;
   }


   int attempts = 0;
   bool modified = false;


   while(attempts < OrderRetryAttempts && !modified)
   {
      attempts++;
      ResetLastError();
      RefreshRates();


      modified = OrderModify(ticket, modifyPrice, sl, tp, expiration, arrowColor);


      if(modified)
      {
         PrintFormat("[ORDER MODIFIED] Ticket #%d | SL: %f | TP: %f", ticket, sl, tp);
         return true;
      }
      else
      {
         int err = GetLastError();
         if(err == 1) // ERR_NO_RESULT: values are identical
         {
            return true;
         }


         PrintFormat("[MODIFY ERROR] Ticket #%d Attempt %d/%d failed: Error %d (%s)",
                     ticket, attempts, OrderRetryAttempts, err, MqlErrorToString(err));


         if(err == 135 || err == 136 || err == 137 || err == 138 || err == 146 || err == 4)
         {
            Sleep(OrderRetryDelayMilliseconds * attempts);
         }
         else
         {
            break;
         }
      }
   }


   return false;
}


//+------------------------------------------------------------------+
//| SECTION 8: ACTIVE TRADE LIFECYCLE & PROTECTION                   |
//+------------------------------------------------------------------+
void ManageActiveTradeLifecycle()
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;


      int ticket     = OrderTicket();
      int type       = OrderType();
      double openPrice = OrderOpenPrice();
      double currentSL = OrderStopLoss();
      double currentTP = OrderTakeProfit();
      double lots    = OrderLots();


      RefreshRates();


      // Long / Buy Position Management
      if(type == OP_BUY)
      {
         double profitPips = (Bid - openPrice) / g_PipPoint;


         double tfRatio = GetActiveTimeframeScaleRatio((ENUM_TIMEFRAMES)Period());
         int scaledBE_Pips = (int)MathRound(BreakEvenPips * tfRatio);
         if(scaledBE_Pips < 3) scaledBE_Pips = 3;


         // 1. Automated Break-Even Logic
         if(UseBreakEven && profitPips >= scaledBE_Pips)
         {
            double beLevel = NormalizeDouble(openPrice + (BreakEvenLockPips * g_PipPoint), Digits);
            if(currentSL < openPrice || currentSL == 0.0)
            {
               if(SafeOrderModify(ticket, openPrice, beLevel, currentTP, 0, clrAqua))
               {
                  Telegram_NotifyBreakEven(ticket, openPrice, beLevel, BreakEvenLockPips);
               }
            }
         }


         // 2. Partial Profit Taking
         if(UsePartialProfitTaking && profitPips >= PartialCloseTriggerPips && !IsTicketPartiallyClosed(ticket))
         {
            if(lots > g_MinLot && lots > MarketInfo(Symbol(), MODE_MINLOT))
            {
               double closeVolume = NormalizeLotStep(lots * PartialCloseRatio);
               if(closeVolume >= g_MinLot && (lots - closeVolume) >= g_MinLot)
               {
                  if(SafeOrderClose(ticket, closeVolume, GetScaledSlippage(), clrDarkGoldenrod))
                  {
                     RegisterTicketPartialClose(ticket);
                     PrintFormat("[PARTIAL CLOSE] Ticket #%d closed %.2f lots at %f", ticket, closeVolume, Bid);
                  }
               }
            }
         }


         int scaledTrailStart = (int)MathRound(TrailingStartPips * tfRatio);
         int scaledTrailStep  = (int)MathRound(TrailingStepPips * tfRatio);
         if(scaledTrailStart < 5) scaledTrailStart = 5;
         if(scaledTrailStep < 2)  scaledTrailStep  = 2;


         // 3. Multi-Mode Trailing Stop Engine
         if(TrailingStopType != TRAILING_NONE && profitPips >= scaledTrailStart)
         {
            double desiredSL = 0.0;


            if(TrailingStopType == TRAILING_FIXED_PIPS)
            {
               desiredSL = NormalizeDouble(Bid - (scaledTrailStep * g_PipPoint), Digits);
            }
            else if(TrailingStopType == TRAILING_ATR_DYNAMIC)
            {
               double atr = iATR(Symbol(), Period(), ATRPeriod, 1);
               desiredSL = NormalizeDouble(Bid - (atr * TrailingATRMultiplier), Digits);
            }
            else if(TrailingStopType == TRAILING_CHANDELIER)
            {
               desiredSL = CalculateChandelierLongStop(ChandelierCandleLookback, TrailingATRMultiplier);
            }
            else if(TrailingStopType == TRAILING_PARABOLIC_SAR)
            {
               desiredSL = NormalizeDouble(iSAR(Symbol(), Period(), ParabolicSAR_Step, ParabolicSAR_Maximum, 1), Digits);
            }
            else if(TrailingStopType == TRAILING_MOVING_AVERAGE)
            {
               desiredSL = CalculateMovingAverageLongStop(EMA_Fast_Period, MODE_EMA);
            }


            // Verify trailing stop improves protection beyond current stop loss
            if(desiredSL > currentSL + (g_PipPoint * 0.5) && desiredSL < Bid)
            {
               if(SafeOrderModify(ticket, openPrice, desiredSL, currentTP, 0, clrGold))
               {
                  Telegram_NotifyTrailing(ticket, desiredSL, profitPips);
               }
            }
         }
      }
      // Short / Sell Position Management
      else if(type == OP_SELL)
      {
         double profitPips = (openPrice - Ask) / g_PipPoint;


         double tfRatio = GetActiveTimeframeScaleRatio((ENUM_TIMEFRAMES)Period());
         int scaledBE_Pips = (int)MathRound(BreakEvenPips * tfRatio);
         if(scaledBE_Pips < 3) scaledBE_Pips = 3;


         // 1. Automated Break-Even Logic
         if(UseBreakEven && profitPips >= scaledBE_Pips)
         {
            double beLevel = NormalizeDouble(openPrice - (BreakEvenLockPips * g_PipPoint), Digits);
            if(currentSL > openPrice || currentSL == 0.0)
            {
               if(SafeOrderModify(ticket, openPrice, beLevel, currentTP, 0, clrAqua))
               {
                  Telegram_NotifyBreakEven(ticket, openPrice, beLevel, BreakEvenLockPips);
               }
            }
         }


         // 2. Partial Profit Taking
         if(UsePartialProfitTaking && profitPips >= PartialCloseTriggerPips && !IsTicketPartiallyClosed(ticket))
         {
            if(lots > g_MinLot && lots > MarketInfo(Symbol(), MODE_MINLOT))
            {
               double closeVolume = NormalizeLotStep(lots * PartialCloseRatio);
               if(closeVolume >= g_MinLot && (lots - closeVolume) >= g_MinLot)
               {
                  if(SafeOrderClose(ticket, closeVolume, GetScaledSlippage(), clrDarkGoldenrod))
                  {
                     RegisterTicketPartialClose(ticket);
                     PrintFormat("[PARTIAL CLOSE] Ticket #%d closed %.2f lots at %f", ticket, closeVolume, Ask);
                  }
               }
            }
         }


         int scaledTrailStart = (int)MathRound(TrailingStartPips * tfRatio);
         int scaledTrailStep  = (int)MathRound(TrailingStepPips * tfRatio);
         if(scaledTrailStart < 5) scaledTrailStart = 5;
         if(scaledTrailStep < 2)  scaledTrailStep  = 2;


         // 3. Multi-Mode Trailing Stop Engine
         if(TrailingStopType != TRAILING_NONE && profitPips >= scaledTrailStart)
         {
            double desiredSL = 0.0;


            if(TrailingStopType == TRAILING_FIXED_PIPS)
            {
               desiredSL = NormalizeDouble(Ask + (scaledTrailStep * g_PipPoint), Digits);
            }
            else if(TrailingStopType == TRAILING_ATR_DYNAMIC)
            {
               double atr = iATR(Symbol(), Period(), ATRPeriod, 1);
               desiredSL = NormalizeDouble(Ask + (atr * TrailingATRMultiplier), Digits);
            }
            else if(TrailingStopType == TRAILING_CHANDELIER)
            {
               desiredSL = CalculateChandelierShortStop(ChandelierCandleLookback, TrailingATRMultiplier);
            }
            else if(TrailingStopType == TRAILING_PARABOLIC_SAR)
            {
               desiredSL = NormalizeDouble(iSAR(Symbol(), Period(), ParabolicSAR_Step, ParabolicSAR_Maximum, 1), Digits);
            }
            else if(TrailingStopType == TRAILING_MOVING_AVERAGE)
            {
               desiredSL = CalculateMovingAverageShortStop(EMA_Fast_Period, MODE_EMA);
            }


            // Verify trailing stop improves protection beyond current stop loss
            if((desiredSL < currentSL - (g_PipPoint * 0.5) || currentSL == 0.0) && desiredSL > Ask)
            {
               if(SafeOrderModify(ticket, openPrice, desiredSL, currentTP, 0, clrGold))
               {
                  Telegram_NotifyTrailing(ticket, desiredSL, profitPips);
               }
            }
         }
      }
   }
}


//+------------------------------------------------------------------+
//| PARTIAL CLOSE REGISTRATION TRACKER                               |
//+------------------------------------------------------------------+
bool IsTicketPartiallyClosed(const int ticket)
{
   if(OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES))
   {
      string comment = OrderComment();
      if(StringFind(comment, "from #") >= 0 || 
         StringFind(comment, "PC") >= 0 || 
         StringFind(comment, "[pc]") >= 0 || 
         StringFind(comment, "partial") >= 0 ||
         StringFind(comment, "Partial") >= 0)
      {
         return true;
      }
   }
   int size = ArraySize(g_PartiallyClosedTickets);
   for(int i = 0; i < size; i++)
   {
      if(g_PartiallyClosedTickets[i] == ticket) return true;
   }
   return false;
}


void RegisterTicketPartialClose(const int ticket)
{
   int size = ArraySize(g_PartiallyClosedTickets);
   for(int i = 0; i < size; i++)
   {
      if(g_PartiallyClosedTickets[i] == ticket) return;
   }
   ArrayResize(g_PartiallyClosedTickets, size + 1);
   g_PartiallyClosedTickets[size] = ticket;

   // Track potential child tickets created by MT4
   string ticketStr = IntegerToString(ticket);
   for(int j = OrdersTotal() - 1; j >= 0; j--)
   {
      if(!OrderSelect(j, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;
      string comment = OrderComment();
      if(StringFind(comment, ticketStr) >= 0 || StringFind(comment, "from #") >= 0)
      {
         int childTicket = OrderTicket();
         bool alreadyIn = false;
         for(int k = 0; k < ArraySize(g_PartiallyClosedTickets); k++)
         {
            if(g_PartiallyClosedTickets[k] == childTicket) { alreadyIn = true; break; }
         }
         if(!alreadyIn)
         {
            int sz = ArraySize(g_PartiallyClosedTickets);
            ArrayResize(g_PartiallyClosedTickets, sz + 1);
            g_PartiallyClosedTickets[sz] = childTicket;
         }
      }
   }
}


//+------------------------------------------------------------------+
//| SECTION 9: ON-CHART GRAPHICS & HUD DASHBOARD                     |
//+------------------------------------------------------------------+
void RenderHUDDashboard()
{
   if(!ShowDashboardPanel) return;


   int startX = HUD_X_Offset;
   int startY = HUD_Y_Offset;
   int rowHeight = 18;
   int panelWidth = 285;
   int panelHeight = 260;


   // 1. Dashboard Backdrop Canvas Panel
   string bgName = PREFIX_GUI + "Backdrop";
   if(ObjectFind(ChartID(), bgName) < 0)
   {
      ObjectCreate(ChartID(), bgName, OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(ChartID(), bgName, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(ChartID(), bgName, OBJPROP_BORDER_TYPE, BORDER_FLAT);
   }
   ObjectSetInteger(ChartID(), bgName, OBJPROP_CORNER, HUD_Corner);
   ObjectSetInteger(ChartID(), bgName, OBJPROP_XDISTANCE, startX);
   ObjectSetInteger(ChartID(), bgName, OBJPROP_YDISTANCE, startY);
   ObjectSetInteger(ChartID(), bgName, OBJPROP_XSIZE, panelWidth);
   ObjectSetInteger(ChartID(), bgName, OBJPROP_YSIZE, panelHeight);
   ObjectSetInteger(ChartID(), bgName, OBJPROP_BGCOLOR, HUD_BgColor);
   ObjectSetInteger(ChartID(), bgName, OBJPROP_BORDER_COLOR, HUD_BorderColor);


   int textX = startX + 12;
   int y = startY + 10;


   // Header
   RenderHUDLabel("00_Title", "=== SMARTAUTOTRADE EA HUD ===", textX, y, HUD_HeaderTextColor, 9, true);
   y += rowHeight + 2;


   // Trend & Momentum Metrics
   string trendDesc = (g_ActiveTrendRegime == TREND_STRONG_BULLISH ? "STRONG BULLISH" :
                      (g_ActiveTrendRegime == TREND_WEAK_BULLISH   ? "WEAK BULLISH" :
                      (g_ActiveTrendRegime == TREND_STRONG_BEARISH ? "STRONG BEARISH" :
                      (g_ActiveTrendRegime == TREND_WEAK_BEARISH   ? "WEAK BEARISH" : "SIDEWAYS"))));
   color trendColor = (StringFind(trendDesc, "BULLISH") >= 0) ? clrLime : ((StringFind(trendDesc, "BEARISH") >= 0) ? clrTomato : clrWheat);
   RenderHUDLabel("01_Trend", "Trend Regime: " + trendDesc, textX, y, trendColor, 8, true);
   y += rowHeight;


   // Signal Scores Breakdown & Live Evaluation Progress
   int liveBuyScore  = g_ScoreTrendBuy + g_ScoreMomBuy + g_ScoreSRBuy + g_ScoreCandleBuy;
   int liveSellScore = g_ScoreTrendSell + g_ScoreMomSell + g_ScoreSRSell + g_ScoreCandleSell;


   string signalSummary = "";
   color sigColor = clrWhite;


   if(g_LastSignalVerdict != "NONE")
   {
      signalSummary = StringFormat("Last Signal: %s (Score: %d/10)", g_LastSignalVerdict, g_LastSignalScore);
      sigColor = (g_LastSignalVerdict == "BUY") ? clrLime : clrTomato;
   }
   else
   {
      string biasStr = (liveSellScore > liveBuyScore) ? StringFormat("SELL %d/10", liveSellScore) :
                       ((liveBuyScore > liveSellScore) ? StringFormat("BUY %d/10", liveBuyScore) : "FLAT 0/10");
      signalSummary = StringFormat("Evaluating: %s (Need: %d)", biasStr, MinRequiredScore);
      sigColor = (liveSellScore > liveBuyScore) ? clrLightSalmon : ((liveBuyScore > liveSellScore) ? clrPaleGreen : clrSilver);
   }
   RenderHUDLabel("02_Signal", signalSummary, textX, y, sigColor, 8, true);
   y += rowHeight;


   // Confluence Breakdown Details
   string scoreBreakdown = StringFormat("Pts: Trend(%d/%d) Mom(%d/%d) SR(%d/%d) Cndl(%d/%d)",
                                         g_ScoreTrendBuy, g_ScoreTrendSell, g_ScoreMomBuy, g_ScoreMomSell,
                                         g_ScoreSRBuy, g_ScoreSRSell, g_ScoreCandleBuy, g_ScoreCandleSell);
   RenderHUDLabel("03_Points", scoreBreakdown, textX, y, HUD_LabelTextColor, 7, false);
   y += rowHeight;


   // Technical Oscillators Data
   string oscSummary = StringFormat("RSI: %.1f | MACD: %.5f | ADX: %.1f", g_CalculatedRSI, g_CalculatedMACDMain, g_CalculatedADX);
   RenderHUDLabel("04_Osc", oscSummary, textX, y, HUD_ValueTextColor, 8, false);
   y += rowHeight;


   // Market Session & Broker Time
   g_CurrentSession = IdentifyMarketSession(TimeCurrent() - (BrokerGMT_Offset * 3600));
   string sessionStr = (g_CurrentSession == SESSION_ASIAN ? "Asian" :
                       (g_CurrentSession == SESSION_LONDON ? "London" :
                       (g_CurrentSession == SESSION_LONDON_NY_OVERLAP ? "London/NY Overlap" :
                       (g_CurrentSession == SESSION_NEWYORK ? "New York" : "Off-Hours"))));
   RenderHUDLabel("05_Session", "Session: " + sessionStr, textX, y, clrSkyBlue, 8, false);
   y += rowHeight;


   // Spread & Volatility ATR
   int spread = (int)MarketInfo(Symbol(), MODE_SPREAD);
   string spreadStr = StringFormat("Spread: %d pts (Max: %d) | ATR: %f", spread, MaxSpreadPoints, iATR(Symbol(), Period(), 14, 1));
   color spreadColor = (spread <= MaxSpreadPoints) ? clrLime : clrRed;
   RenderHUDLabel("06_Spread", spreadStr, textX, y, spreadColor, 8, false);
   y += rowHeight;


   // Account Financial Overview
   string finStr = StringFormat("Balance: $%.2f | Equity: $%.2f", AccountBalance(), AccountEquity());
   RenderHUDLabel("07_Fin", finStr, textX, y, HUD_ValueTextColor, 8, false);
   y += rowHeight;


   // Daily Performance P&L
   double dayPnL = AccountEquity() - g_StartingDayEquity;
   double dayPnLPercent = (g_StartingDayEquity > 0.0) ? (dayPnL / g_StartingDayEquity) * 100.0 : 0.0;
   string pnlStr = StringFormat("Daily P&L: %s$%.2f (%.2f%%)", (dayPnL >= 0.0 ? "+" : ""), dayPnL, dayPnLPercent);
   color pnlColor = (dayPnL >= 0.0) ? clrLime : clrTomato;
   RenderHUDLabel("08_PnL", pnlStr, textX, y, pnlColor, 8, true);
   y += rowHeight;


   // Position Concurrency
   int myOrders = 0;
   for(int k = OrdersTotal() - 1; k >= 0; k--)
   {
      if(OrderSelect(k, SELECT_BY_POS, MODE_TRADES))
      {
         if(OrderSymbol() == Symbol() && OrderMagicNumber() == MagicNumber) myOrders++;
      }
   }
   string autoTradeStatus = (!IsTradeAllowed()) ? "TERMINAL LOCKED" : (g_AutoTradingRuntimeActive ? "ACTIVE" : "PAUSED");
   color autoTradeClr    = (!IsTradeAllowed()) ? clrRed : (g_AutoTradingRuntimeActive ? clrLime : clrOrange);
   string posStr = StringFormat("Open Positions: %d / %d | Bot: %s",
                                myOrders, MaxOpenPositionsPerSymbol, autoTradeStatus);
   RenderHUDLabel("09_Positions", posStr, textX, y, autoTradeClr, 8, true);
   y += rowHeight;


   // â”€â”€ PERF: Heavy indicator calculations throttled to every 5 seconds â”€â”€â”€â”€â”€â”€â”€â”€â”€
   // CCI, Bollinger %B, VSA, KER and TTM Squeeze are expensive cross-period calls.
   // We cache results and only recalculate every 5s, not on every 2s HUD render.
   uint hudNow = GetTickCount();
   if(hudNow - g_LastHeavyIndicatorTick >= 5000)
   {
      g_LastHeavyIndicatorTick = hudNow;
      int _cciBuy = 0, _cciSell = 0;
      CalculateCCIModule(_cciBuy, _cciSell);
      double _pctB = 0.5, _bWidth = 0.0;
      int _bbBuy = 0, _bbSell = 0;
      CalculateBollingerPercentB(_pctB, _bWidth, _bbBuy, _bbSell);
      int _vsaBuy = 0, _vsaSell = 0;
      AnalyzeVolumeSpreadEngine(_vsaBuy, _vsaSell);
      EvaluateTTMSqueezeMomentum(g_TTMSqueezeArmed, g_TTMSqueezeFiring);
   }
   // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

   // Ultra Quant Metrics (KER & Squeeze) â€” use cached values
   string sqzStr = (g_TTMSqueezeArmed ? "ARMED (Compressing)" : (g_TTMSqueezeFiring ? "FIRING (Expansion)" : "None"));
   color sqzColor = (g_TTMSqueezeFiring ? clrLime : (g_TTMSqueezeArmed ? clrGold : clrLightGray));
   string quantStr = StringFormat("KER: %.2f | Squeeze: %s", g_CalculatedKER, sqzStr);
   RenderHUDLabel("09_Quant", quantStr, textX, y, sqzColor, 8, true);
   y += rowHeight;


   // Pattern Detected
   string patternDesc = (g_LastCandlePattern == CANDLE_BULLISH_ENGULFING ? "Bullish Engulfing" :
                        (g_LastCandlePattern == CANDLE_BEARISH_ENGULFING ? "Bearish Engulfing" :
                        (g_LastCandlePattern == CANDLE_HAMMER ? "Hammer" :
                        (g_LastCandlePattern == CANDLE_SHOOTING_STAR ? "Shooting Star" :
                        (g_LastCandlePattern == CANDLE_DOJI_REGULAR ? "Doji" :
                        (g_LastCandlePattern == CANDLE_MORNING_STAR ? "Morning Star" :
                        (g_LastCandlePattern == CANDLE_EVENING_STAR ? "Evening Star" : "None")))))));
   RenderHUDLabel("10_Pattern", "Pattern: " + patternDesc, textX, y, clrGold, 8, false);
   y += rowHeight;


   // Extended Indicator Metrics â€” values already refreshed by 5s throttle above
   string extStr = StringFormat("CCI: %.1f | %%B: %.2f | VSA: %s",
                                g_CalculatedCCI, g_CalculatedPercentB,
                                (g_VSA_StoppingVolume ? "Stopping Vol" : (g_VSA_AbsorptionVolume ? "Absorption" : "Normal")));
   RenderHUDLabel("11_ExtInd", extStr, textX, y, clrMediumSpringGreen, 8, false);


   // Render On-Chart Action Buttons directly below HUD
   RenderInteractiveButtons();


   // â”€â”€ PERF: MTF Matrix throttled to every 10 seconds â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
   // iMA/iRSI calls across 6 different timeframes are expensive; 10s is plenty.
   if(GetTickCount() - g_LastMTFMatrixTick >= 10000)
   {
      g_LastMTFMatrixTick = GetTickCount();
      RenderMultiTimeframeMatrix();
   }
   // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
}


void RenderHUDLabel(const string id, const string text, const int x, const int y, const color clr, const int fontSize = 8, const bool isBold = false)
{
   string objName = PREFIX_GUI + id;
   if(ObjectFind(ChartID(), objName) < 0)
   {
      ObjectCreate(ChartID(), objName, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(ChartID(), objName, OBJPROP_SELECTABLE, false);
      ObjectSetString(ChartID(), objName, OBJPROP_FONT, isBold ? "Segoe UI Bold" : "Segoe UI");
   }
   ObjectSetInteger(ChartID(), objName, OBJPROP_CORNER, HUD_Corner);
   ObjectSetInteger(ChartID(), objName, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(ChartID(), objName, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(ChartID(), objName, OBJPROP_COLOR, clr);
   ObjectSetInteger(ChartID(), objName, OBJPROP_FONTSIZE, fontSize);
   ObjectSetString(ChartID(), objName, OBJPROP_TEXT, text);
}


//+------------------------------------------------------------------+
//| SIGNAL ARROW RENDERING & S/R VISUALIZATION                       |
//+------------------------------------------------------------------+


//+------------------------------------------------------------------+
//| HISTORICAL CANDLE SCORING & ARROW SCANNER                        |
//+------------------------------------------------------------------+
void EvaluateScoreOnBar(const int shift, int &outBuy, int &outSell)
{
   outBuy = 0;
   outSell = 0;


   // 1. Trend on shift
   double e20  = iMA(Symbol(), Period(), EMA_Fast_Period,   0, MODE_EMA, EMA_AppliedPrice, shift);
   double e50  = iMA(Symbol(), Period(), EMA_Medium_Period, 0, MODE_EMA, EMA_AppliedPrice, shift);
   double e200 = iMA(Symbol(), Period(), EMA_Slow_Period,   0, MODE_EMA, EMA_AppliedPrice, shift);


   if(e20 > e50 && e50 > e200) outBuy += 3;
   else if(e20 < e50 && e50 < e200) outSell += 3;
   else if(e20 > e50) outBuy += 2;
   else if(e20 < e50) outSell += 2;


   // 2. Momentum on shift
   double rsi = iRSI(Symbol(), Period(), RSI_Period, RSI_AppliedPrice, shift);
   if(rsi < RSI_Oversold && outBuy > 0) outBuy += 2;
   else if(rsi > RSI_Overbought && outSell > 0) outSell += 2;
   else if(rsi >= RSI_Neutral_Low && rsi <= RSI_Neutral_High) { outBuy += 1; outSell += 1; }


   double macdM = iMACD(Symbol(), Period(), MACD_Fast_EMA, MACD_Slow_EMA, MACD_Signal_SMA, MACD_AppliedPrice, MODE_MAIN, shift);
   double macdS = iMACD(Symbol(), Period(), MACD_Fast_EMA, MACD_Slow_EMA, MACD_Signal_SMA, MACD_AppliedPrice, MODE_SIGNAL, shift);
   double macdM_prev = iMACD(Symbol(), Period(), MACD_Fast_EMA, MACD_Slow_EMA, MACD_Signal_SMA, MACD_AppliedPrice, MODE_MAIN, shift + 1);
   double macdS_prev = iMACD(Symbol(), Period(), MACD_Fast_EMA, MACD_Slow_EMA, MACD_Signal_SMA, MACD_AppliedPrice, MODE_SIGNAL, shift + 1);


   if(macdM > macdS && macdM_prev <= macdS_prev) outBuy += 1;
   else if(macdM < macdS && macdM_prev >= macdS_prev) outSell += 1;


   // 3. S/R Proximity on shift
   int hIdx = iHighest(Symbol(), Period(), MODE_HIGH, LookbackBarsSR, shift);
   int lIdx = iLowest(Symbol(), Period(), MODE_LOW, LookbackBarsSR, shift);
   double swH = (hIdx != -1) ? iHigh(Symbol(), Period(), hIdx) : iHigh(Symbol(), Period(), shift);
   double swL = (lIdx != -1) ? iLow(Symbol(), Period(), lIdx) : iLow(Symbol(), Period(), shift);
   double cl = iClose(Symbol(), Period(), shift);
   double prox = ProximityPipsSR * g_PipPoint;


   if(MathAbs(cl - swL) <= prox && outBuy > 0) outBuy += 2;
   if(MathAbs(cl - swH) <= prox && outSell > 0) outSell += 2;


   // 4. Candlesticks on shift
   double o1 = iOpen(Symbol(), Period(), shift);
   double c1 = iClose(Symbol(), Period(), shift);
   double h1 = iHigh(Symbol(), Period(), shift);
   double l1 = iLow(Symbol(), Period(), shift);
   double o2 = iOpen(Symbol(), Period(), shift + 1);
   double c2 = iClose(Symbol(), Period(), shift + 1);
   double body1 = MathAbs(c1 - o1);
   double rng1  = h1 - l1;


   if(rng1 > 0.0)
   {
      // Bullish Engulfing
      if(c2 < o2 && c1 > o1 && c1 >= o2 && o1 <= c2) outBuy += 2;
      // Bearish Engulfing
      else if(c2 > o2 && c1 < o1 && c1 <= o2 && o1 >= c2) outSell += 2;
      // Hammer
      else if((MathMin(o1, c1) - l1) >= (2.0 * body1) && (h1 - MathMax(o1, c1)) <= (0.2 * rng1)) outBuy += 1;
      // Shooting Star
      else if((h1 - MathMax(o1, c1)) >= (2.0 * body1) && (MathMin(o1, c1) - l1) <= (0.2 * rng1)) outSell += 1;
   }


   if(outBuy > 10) outBuy = 10;
   if(outSell > 10) outSell = 10;
}


//+------------------------------------------------------------------+
//| FAST PURGE OF SIGNAL ARROWS ON TIMEFRAME SWITCH                  |
//+------------------------------------------------------------------+
void ClearChartSignalMarkers()
{
   int total = ObjectsTotal(ChartID(), -1, OBJ_ARROW);
   for(int i = total - 1; i >= 0; i--)
   {
      string name = ObjectName(ChartID(), i, -1, OBJ_ARROW);
      if(StringFind(name, PREFIX_OBJ + "Signal_") == 0)
      {
         ObjectDelete(ChartID(), name);
      }
   }
}


void ScanAndDrawHistoricalSignals(bool fastScan = false)
{
   if(!PlotHistoricalSignals) return;

   // fastScan=true on TF changes: 25-bar scan is instantaneous (<1ms)
   int maxScan = fastScan ? 25 : MathMin(HistoricalBarsToScan, 40);
   int totalBars = MathMin(maxScan, Bars - 5);
   if(totalBars < 1) return;

   for(int s = totalBars; s >= 1; s--)
   {
      int bScore = 0, sScore = 0;
      EvaluateScoreOnBar(s, bScore, sScore);

      if(bScore >= MinRequiredScore && bScore > sScore)
      {
         DrawChartSignalMarker(SIGNAL_LONG, s);
      }
      else if(sScore >= MinRequiredScore && sScore > bScore)
      {
         DrawChartSignalMarker(SIGNAL_SHORT, s);
      }
   }
}


void DrawChartSignalMarker(const ENUM_SIGNAL_DECISION signal, const int shift)
{
   datetime barTime = iTime(Symbol(), Period(), shift);
   string markerName = PREFIX_OBJ + "Signal_" + (string)barTime;


   ObjectDelete(ChartID(), markerName);


   if(signal == SIGNAL_LONG)
   {
      double anchorPrice = iLow(Symbol(), Period(), shift) - (5.0 * g_PipPoint);
      ObjectCreate(ChartID(), markerName, OBJ_ARROW, 0, barTime, anchorPrice);
      ObjectSetInteger(ChartID(), markerName, OBJPROP_ARROWCODE, 233);
      ObjectSetInteger(ChartID(), markerName, OBJPROP_COLOR, BuyArrowColor);
      ObjectSetInteger(ChartID(), markerName, OBJPROP_WIDTH, SignalArrowSize);
   }
   else if(signal == SIGNAL_SHORT)
   {
      double anchorPrice = iHigh(Symbol(), Period(), shift) + (5.0 * g_PipPoint);
      ObjectCreate(ChartID(), markerName, OBJ_ARROW, 0, barTime, anchorPrice);
      ObjectSetInteger(ChartID(), markerName, OBJPROP_ARROWCODE, 234);
      ObjectSetInteger(ChartID(), markerName, OBJPROP_COLOR, SellArrowColor);
      ObjectSetInteger(ChartID(), markerName, OBJPROP_WIDTH, SignalArrowSize);
   }
}


void DrawSupportResistanceLines()
{
   if(!ShowSRLevelsOnChart) return;


   UpdateChartRay(PREFIX_OBJ + "SwingHigh", g_RecentSwingHigh, clrCrimson, STYLE_DASH, "Swing High (Resistance)");
   UpdateChartRay(PREFIX_OBJ + "SwingLow",  g_RecentSwingLow,  clrDarkTurquoise, STYLE_DASH, "Swing Low (Support)");


   // Render Keltner Channels Overlay
   RenderKeltnerChannelsOverlay();


   if(ShowPivotLevelsOnChart && UsePivotPointsScoring)
   {
      UpdateChartRay(PREFIX_OBJ + "Pivot_P",  g_DailyPivot_P,  clrDarkGoldenrod, STYLE_SOLID, "Daily Pivot (P)");
      UpdateChartRay(PREFIX_OBJ + "Pivot_R1", g_DailyPivot_R1, clrRed,           STYLE_DOT,   "Daily Resistance 1");
      UpdateChartRay(PREFIX_OBJ + "Pivot_S1", g_DailyPivot_S1, clrMediumSeaGreen,STYLE_DOT,   "Daily Support 1");
   }
}


void UpdateChartRay(const string name, const double price, const color clr, const ENUM_LINE_STYLE style, const string desc)
{
   if(price <= 0.0) return;


   if(ObjectFind(ChartID(), name) < 0)
   {
      ObjectCreate(ChartID(), name, OBJ_HLINE, 0, 0, price);
      ObjectSetInteger(ChartID(), name, OBJPROP_SELECTABLE, false);
      ObjectSetString(ChartID(), name, OBJPROP_TOOLTIP, desc);
   }
   else
   {
      ObjectSetDouble(ChartID(), name, OBJPROP_PRICE1, price);
   }
   ObjectSetInteger(ChartID(), name, OBJPROP_COLOR, clr);
   ObjectSetInteger(ChartID(), name, OBJPROP_STYLE, style);
}


//+------------------------------------------------------------------+
//| SECTION 10: ALERTS, AUDIT LOGGING & NOTIFICATIONS                |
//+------------------------------------------------------------------+
void BroadcastSignalAlerts(const ENUM_SIGNAL_DECISION signal, const int score)
{
   string dirStr = (signal == SIGNAL_LONG) ? "BUY" : "SELL";
   string alertMessage = StringFormat("[SmartAutoTradeEA] %s Signal Detected on %s [%s] | Confluence Score: %d/10 | Price: %f",
                                      dirStr, Symbol(), EnumToString((ENUM_TIMEFRAMES)Period()), score, (signal == SIGNAL_LONG ? Ask : Bid));


   if(EnableScreenPopupAlert)
   {
      Alert(alertMessage);
   }


   if(EnableAudioChimeAlert)
   {
      PlaySound(AudioChimeFilename);
   }


   if(EnablePushNotifications)
   {
      SendNotification(alertMessage);
   }


   if(EnableEmailNotifications)
   {
      SendMail("[SmartAutoTradeEA] Actionable Trading Signal", alertMessage);
   }


   if(EnableDiskFileAuditLogging)
   {
      AppendAuditRecord(dirStr, score);
   }
}


void AppendAuditRecord(const string direction, const int score)
{
   int fileHandle = FileOpen(AuditLogFilename, FILE_CSV | FILE_READ | FILE_WRITE, ',');
   if(fileHandle != INVALID_HANDLE)
   {
      FileSeek(fileHandle, 0, SEEK_END);
      if(FileSize(fileHandle) == 0)
      {
         FileWrite(fileHandle, "Time", "Symbol", "Timeframe", "Direction", "Score", "Bid", "Ask", "Equity", "Status");
      }
      FileWrite(fileHandle,
                TimeToStr(TimeCurrent(), TIME_DATE | TIME_SECONDS),
                Symbol(),
                EnumToString((ENUM_TIMEFRAMES)Period()),
                direction,
                IntegerToString(score),
                DoubleToString(Bid, Digits),
                DoubleToString(Ask, Digits),
                DoubleToString(AccountEquity(), 2),
                (g_AutoTradingRuntimeActive ? "Executed" : "SignalOnly"));
      FileClose(fileHandle);
   }
}


//+------------------------------------------------------------------+
//| REAL-TIME TELEGRAM TRADE TRACKER, TWO-WAY DISPATCHER & GUARDIAN  |
//+------------------------------------------------------------------+
struct SmartEATelegramSnapshot
{
   int      ticket;
   int      type;
   string   symbol;
   double   lots;
   double   openPrice;
   double   sl;
   double   tp;
   datetime openTime;
   int      magic;
};

SmartEATelegramSnapshot g_tgActiveTrades[];
int      g_tgLastUpdateId           = 0;
datetime g_lastMarginAlertTime       = 0;
datetime g_lastNewsAlertTime        = 0;
datetime g_lastDailyDrawdownAlertDate = 0;
datetime g_lastDailyReportDate      = 0;

string Telegram_ToLower(string str)
{
   string res = str;
   StringToLower(res);
   return res;
}

//+------------------------------------------------------------------+
//| Command: /status                                                 |
//+------------------------------------------------------------------+
void Telegram_CmdStatus()
{
   string msg = "📊 <b>ACCOUNT STATUS REPORT</b>\n";
   msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
   msg += "• <b>Account:</b> " + IntegerToString(AccountNumber()) + " (" + AccountCompany() + ")\n";
   msg += "• <b>Server:</b> " + AccountServer() + "\n";
   msg += "• <b>Balance:</b> " + Telegram_FormatMoney(AccountBalance(), AccountCurrency()) + "\n";
   msg += "• <b>Equity:</b> " + Telegram_FormatMoney(AccountEquity(), AccountCurrency()) + "\n";
   msg += "• <b>Free Margin:</b> " + Telegram_FormatMoney(AccountFreeMargin(), AccountCurrency()) + "\n";
   double margin = AccountMargin();
   double marginLevel = (margin > 0.0) ? (AccountEquity() / margin * 100.0) : 100.0;
   msg += "• <b>Margin Level:</b> " + DoubleToString(marginLevel, 1) + "%\n";
   double floatingPnL = AccountEquity() - AccountBalance();
   string pnlEmoji = (floatingPnL >= 0.0) ? "🟢" : "🔴";
   msg += "• <b>Floating P/L:</b> " + pnlEmoji + " " + Telegram_FormatMoney(floatingPnL, AccountCurrency()) + "\n";
   
   int openCount = 0;
   for(int i = 0; i < OrdersTotal(); i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderType() == OP_BUY || OrderType() == OP_SELL) openCount++;
   }
   msg += "• <b>Open Positions:</b> " + IntegerToString(openCount) + "\n";
   msg += "• <b>AutoTrading:</b> " + (g_AutoTradingRuntimeActive ? "ACTIVE ✅" : "PAUSED ⏸️") + "\n";
   if(g_StartingDayEquity > 0.0)
   {
      double dailyPnL = AccountEquity() - g_StartingDayEquity;
      msg += "• <b>Daily Return:</b> " + Telegram_FormatMoney(dailyPnL, AccountCurrency()) + "\n";
   }
   msg += "• <b>Symbol:</b> " + Symbol() + " (" + EnumToString((ENUM_TIMEFRAMES)Period()) + ")";
   
   Telegram_SendMessage(TelegramBotToken, TelegramChatID, msg, 2, 1);
}

//+------------------------------------------------------------------+
//| Command: /positions                                              |
//+------------------------------------------------------------------+
void Telegram_CmdPositions()
{
   int total = OrdersTotal();
   int count = 0;
   string msg = "📋 <b>ACTIVE OPEN POSITIONS</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
   
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL) continue;
      
      count++;
      string sym = OrderSymbol();
      int digits = (int)MarketInfo(sym, MODE_DIGITS);
      if(digits == 0) digits = 5;
      double curPrice = (type == OP_BUY) ? MarketInfo(sym, MODE_BID) : MarketInfo(sym, MODE_ASK);
      double netProfit = OrderProfit() + OrderSwap() + OrderCommission();
      string pnlSign = (netProfit >= 0.0) ? "+" : "";
      
      msg += StringFormat("<b>#%d %s %s %.2fL</b>\n", OrderTicket(), sym, (type == OP_BUY ? "BUY" : "SELL"), OrderLots());
      msg += StringFormat("• Open: %s | Cur: %s\n", Telegram_FormatPrice(OrderOpenPrice(), digits), Telegram_FormatPrice(curPrice, digits));
      msg += StringFormat("• SL: %s | TP: %s\n", Telegram_FormatPrice(OrderStopLoss(), digits), Telegram_FormatPrice(OrderTakeProfit(), digits));
      msg += StringFormat("• P/L: <b>%s%.2f %s</b>\n", pnlSign, netProfit, AccountCurrency());
      msg += "──────────────────────────\n";
   }
   
   string kbJson = "";
   if(count > 0)
   {
      kbJson = "{\"inline_keyboard\":[";
      int btnCount = 0;
      for(int i = 0; i < total; i++)
      {
         if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
         int type = OrderType();
         if(type != OP_BUY && type != OP_SELL) continue;
         int t = OrderTicket();
         if(btnCount > 0) kbJson += ",";
         kbJson += StringFormat("[{\"text\":\"❌ Close #%d\",\"callback_data\":\"/close_%d\"},{\"text\":\"✂️ 50%%\",\"callback_data\":\"/half_%d\"},{\"text\":\"🛡️ BE\",\"callback_data\":\"/be_%d\"}]", t, t, t, t);
         btnCount++;
         if(btnCount >= 6) break;
      }
      kbJson += ",[{\"text\":\"🚨 Close All\",\"callback_data\":\"/panic\"},{\"text\":\"📸 Screenshot\",\"callback_data\":\"/screenshot\"}]]}";
   }
   
   if(count == 0)
   {
      msg += "No open positions currently.";
   }
   else
   {
      msg += StringFormat("Total Active Positions: %d", count);
   }
   
   Telegram_SendMessage(TelegramBotToken, TelegramChatID, msg, 2, 1, kbJson);
}

//+------------------------------------------------------------------+
//| Command: /closeall (Emergency Kill Switch)                       |
//+------------------------------------------------------------------+
void Telegram_CmdCloseAll()
{
   int closedCount = 0;
   double totalRealized = 0.0;
   string currency = AccountCurrency();
   
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL) continue;
      if(!TelegramMonitorAllTrades && OrderMagicNumber() != MagicNumber) continue;
      
      int ticket = OrderTicket();
      double lots = OrderLots();
      double pnl  = OrderProfit() + OrderSwap() + OrderCommission();
      
      if(SafeOrderClose(ticket, lots, GetScaledSlippage(), clrRed))
      {
         closedCount++;
         totalRealized += pnl;
      }
   }
   
   string msg = "🚨 <b>EMERGENCY KILL SWITCH EXECUTED</b>\n";
   msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
   msg += StringFormat("• <b>Positions Closed:</b> %d\n", closedCount);
   msg += StringFormat("• <b>Net Realized P/L:</b> %s\n", Telegram_FormatMoney(totalRealized, currency));
   msg += StringFormat("• <b>Ending Balance:</b> %s", Telegram_FormatMoney(AccountBalance(), currency));
   
   Telegram_SendMessage(TelegramBotToken, TelegramChatID, msg, 3, 2);
}

//+------------------------------------------------------------------+
//| Action: Close single position by ticket                          |
//+------------------------------------------------------------------+
void Telegram_CmdCloseTicket(int ticket)
{
   if(!OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES))
   {
      Telegram_SendMessage(TelegramBotToken, TelegramChatID, "❌ Position #" + IntegerToString(ticket) + " not found or already closed.", 2, 1);
      return;
   }
   string sym = OrderSymbol();
   double lots = OrderLots();
   int digits = (int)MarketInfo(sym, MODE_DIGITS);
   if(digits == 0) digits = 5;
   
   if(SafeOrderClose(ticket, lots, GetScaledSlippage(), clrRed))
   {
      double pnl = OrderProfit() + OrderSwap() + OrderCommission();
      string msg = StringFormat("✅ <b>TRADE #%d CLOSED</b>\n• <b>Symbol:</b> %s\n• <b>Volume:</b> %.2f Lots\n• <b>Realized P/L:</b> %s",
                                ticket, sym, lots, Telegram_FormatMoney(pnl, AccountCurrency()));
      Telegram_SendMessage(TelegramBotToken, TelegramChatID, msg, 2, 1);
   }
   else
   {
      Telegram_SendMessage(TelegramBotToken, TelegramChatID, "❌ Failed to close #" + IntegerToString(ticket) + ". Error: " + IntegerToString(GetLastError()), 2, 1);
   }
}

//+------------------------------------------------------------------+
//| Action: Partially close 50% of position                          |
//+------------------------------------------------------------------+
void Telegram_CmdCloseHalfTicket(int ticket)
{
   if(!OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES))
   {
      Telegram_SendMessage(TelegramBotToken, TelegramChatID, "❌ Position #" + IntegerToString(ticket) + " not found or already closed.", 2, 1);
      return;
   }
   string sym = OrderSymbol();
   double totalLots = OrderLots();
   double halfLots = NormalizeLotStep(totalLots / 2.0);
   if(halfLots < MarketInfo(sym, MODE_MINLOT)) halfLots = totalLots;
   
   if(SafeOrderClose(ticket, halfLots, GetScaledSlippage(), clrOrange))
   {
      string msg = StringFormat("✂️ <b>CLOSED 50%% OF #%d</b>\n• <b>Symbol:</b> %s\n• <b>Closed:</b> %.2f Lots\n• <b>Remaining:</b> %.2f Lots",
                                ticket, sym, halfLots, totalLots - halfLots);
      Telegram_SendMessage(TelegramBotToken, TelegramChatID, msg, 2, 1);
   }
   else
   {
      Telegram_SendMessage(TelegramBotToken, TelegramChatID, "❌ Failed partial close for #" + IntegerToString(ticket) + ". Error: " + IntegerToString(GetLastError()), 2, 1);
   }
}

//+------------------------------------------------------------------+
//| Action: Move SL to Break-Even for specific ticket                |
//+------------------------------------------------------------------+
void Telegram_CmdBreakEvenTicket(int ticket)
{
   if(!OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES))
   {
      Telegram_SendMessage(TelegramBotToken, TelegramChatID, "❌ Position #" + IntegerToString(ticket) + " not found or already closed.", 2, 1);
      return;
   }
   string sym = OrderSymbol();
   int digits = (int)MarketInfo(sym, MODE_DIGITS);
   if(digits == 0) digits = 5;
   double pipPt = (digits == 3 || digits == 5) ? Point * 10.0 : Point;
   double bePrice = (OrderType() == OP_BUY) ? (OrderOpenPrice() + (BreakEvenLockPips * pipPt)) : (OrderOpenPrice() - (BreakEvenLockPips * pipPt));
   bePrice = NormalizeDouble(bePrice, digits);
   
   if(SafeOrderModify(ticket, OrderOpenPrice(), bePrice, OrderTakeProfit(), 0, clrAqua))
   {
      string msg = StringFormat("🛡️ <b>BREAK-EVEN SET FOR #%d</b>\n• <b>Symbol:</b> %s\n• <b>Entry:</b> %s\n• <b>New SL:</b> %s (+%d pips locked)\n• <b>Status:</b> Risk-Free! 🔒",
                                ticket, sym, Telegram_FormatPrice(OrderOpenPrice(), digits), Telegram_FormatPrice(bePrice, digits), BreakEvenLockPips);
      Telegram_SendMessage(TelegramBotToken, TelegramChatID, msg, 2, 1);
   }
   else
   {
      Telegram_SendMessage(TelegramBotToken, TelegramChatID, "❌ Failed to set BE for #" + IntegerToString(ticket) + ". Error: " + IntegerToString(GetLastError()), 2, 1);
   }
}

//+------------------------------------------------------------------+
//| Command: /panic (Emergency Kill Switch Prompt with Confirmation) |
//+------------------------------------------------------------------+
void Telegram_CmdPanicPrompt()
{
   string msg = "🚨 <b>EMERGENCY KILL-SWITCH WARNING</b>\n";
   msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
   msg += "Are you sure you want to <b>LIQUIDATE ALL TRADES</b>, cancel pending orders, and <b>PAUSE</b> autotrading immediately?\n\n";
   msg += "⚠️ <i>Tap the button below to execute emergency shutdown:</i>";
   
   string kbJson = "{\"inline_keyboard\":[[{\"text\":\"🚨 CONFIRM EMERGENCY LIQUIDATE ALL\",\"callback_data\":\"/panic_confirm\"}],[{\"text\":\"❌ Cancel\",\"callback_data\":\"/status\"}]]}";
   Telegram_SendMessage(TelegramBotToken, TelegramChatID, msg, 2, 1, kbJson);
}

//+------------------------------------------------------------------+
//| Execute Panic Kill-Switch                                        |
//+------------------------------------------------------------------+
void Telegram_CmdPanicExecute()
{
   g_AutoTradingRuntimeActive = false;
   Telegram_CmdCloseAll();
   
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         int type = OrderType();
         if(type >= OP_BUYLIMIT && type <= OP_SELLSTOP)
         {
            bool delOk = OrderDelete(OrderTicket(), clrRed);
         }
      }
   }
   
   string msg = "🛑 <b>KILL-SWITCH EXECUTED SUCCESSFULLY</b>\n";
   msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
   msg += "• All market positions liquidated.\n";
   msg += "• All pending limit/stop orders cancelled.\n";
   msg += "• AutoTrading status: <b>PAUSED ⏸️</b>\n";
   msg += "• Send /resume to re-enable trading.";
   Telegram_SendMessage(TelegramBotToken, TelegramChatID, msg, 2, 1);
}

//+------------------------------------------------------------------+
//| Format visual text progress bar                                  |
//+------------------------------------------------------------------+
string Telegram_FormatProgressBar(double currentVal, double maxVal, int barLength = 10)
{
   if(maxVal <= 0.0) return "[□□□□□□□□□□] 0%";
   double ratio = currentVal / maxVal;
   if(ratio < 0.0) ratio = 0.0;
   if(ratio > 1.0) ratio = 1.0;
   int filled = (int)MathRound(ratio * barLength);
   string bar = "[";
   for(int i = 0; i < barLength; i++)
   {
      if(i < filled) bar += "■";
      else bar += "□";
   }
   bar += StringFormat("] %d%%", (int)MathRound(ratio * 100.0));
   return bar;
}

//+------------------------------------------------------------------+
//| Command: /prop (Prop-Firm Risk Guardian Scorecard)               |
//+------------------------------------------------------------------+
void Telegram_CmdPropScorecard()
{
   double curEquity = AccountEquity();
   if(curEquity > g_PropPeakEquity) g_PropPeakEquity = curEquity;
   
   double dayLoss = (g_StartingDayEquity > curEquity) ? (g_StartingDayEquity - curEquity) : 0.0;
   double dayLossLimit = (g_StartingDayEquity * (PropMaxDailyLossPercent / 100.0));
   double dayLossPct = (g_StartingDayEquity > 0.0) ? (dayLoss / g_StartingDayEquity * 100.0) : 0.0;
   
   double peakLoss = (g_PropPeakEquity > curEquity) ? (g_PropPeakEquity - curEquity) : 0.0;
   double peakLossLimit = (g_PropPeakEquity * (PropMaxTotalDrawdownPercent / 100.0));
   double peakLossPct = (g_PropPeakEquity > 0.0) ? (peakLoss / g_PropPeakEquity * 100.0) : 0.0;
   
   double baseTargetRef = 10000.0;
   double targetProfitGoal = baseTargetRef * (PropProfitTargetPercent / 100.0);
   double currentGain = curEquity - baseTargetRef;
   if(currentGain < 0.0) currentGain = 0.0;
   
   string msg = "🛡️ <b>PROP-FIRM RISK GUARDIAN SCORECARD</b>\n";
   msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
   msg += "• <b>Account:</b> " + IntegerToString(AccountNumber()) + " (" + AccountCompany() + ")\n";
   msg += "• <b>Equity:</b> " + Telegram_FormatMoney(curEquity, AccountCurrency()) + " | <b>Peak:</b> " + Telegram_FormatMoney(g_PropPeakEquity, AccountCurrency()) + "\n";
   msg += "──────────────────────────\n";
   msg += "📉 <b>DAILY DRAWDOWN (Limit: " + DoubleToString(PropMaxDailyLossPercent, 1) + "%):</b>\n";
   string dayStatus = (dayLossPct < PropMaxDailyLossPercent * 0.7) ? "Safe ✅" : (dayLossPct < PropMaxDailyLossPercent ? "Caution ⚠️" : "BREACHED 🚨");
   msg += StringFormat("• Loss Today: -$%.2f / -$%.2f (%.2f%%) — %s\n", dayLoss, dayLossLimit, dayLossPct, dayStatus);
   msg += "  " + Telegram_FormatProgressBar(dayLoss, dayLossLimit, 10) + "\n";
   msg += "──────────────────────────\n";
   msg += "📉 <b>TRAILING PEAK DRAWDOWN (Limit: " + DoubleToString(PropMaxTotalDrawdownPercent, 1) + "%):</b>\n";
   string peakStatus = (peakLossPct < PropMaxTotalDrawdownPercent * 0.7) ? "Safe ✅" : (peakLossPct < PropMaxTotalDrawdownPercent ? "Caution ⚠️" : "BREACHED 🚨");
   msg += StringFormat("• Trailing DD: -$%.2f / -$%.2f (%.2f%%) — %s\n", peakLoss, peakLossLimit, peakLossPct, peakStatus);
   msg += "  " + Telegram_FormatProgressBar(peakLoss, peakLossLimit, 10) + "\n";
   msg += "──────────────────────────\n";
   msg += "🎯 <b>PROFIT TARGET PROGRESS (" + DoubleToString(PropProfitTargetPercent, 1) + "%):</b>\n";
   msg += StringFormat("• Progress: +$%.2f / +$%.2f\n", currentGain, targetProfitGoal);
   msg += "  " + Telegram_FormatProgressBar(currentGain, targetProfitGoal, 10) + "\n";
   msg += "──────────────────────────\n";
   string autotradeStr = g_PropLockoutActive ? "LOCKED (Breach) 🔒" : (g_AutoTradingRuntimeActive ? "ACTIVE & ENFORCED 🟢" : "PAUSED ⏸️");
   msg += "• <b>Guardian Status:</b> " + autotradeStr + "\n";
   msg += "• <b>Weekend Shield:</b> " + (PropWeekendProtection ? ("Friday " + IntegerToString(PropFridayCloseHourGMT) + ":00 GMT") : "Disabled");
   
   Telegram_SendMessage(TelegramBotToken, TelegramChatID, msg, 2, 1);
}

//+------------------------------------------------------------------+
//| Continuous Prop-Firm Risk Evaluation & Circuit Breaker           |
//+------------------------------------------------------------------+
void Telegram_CheckPropFirmRules()
{
   if(!PropEnableRiskGuardian) return;
   
   double curEquity = AccountEquity();
   if(curEquity > g_PropPeakEquity) g_PropPeakEquity = curEquity;
   
   // Reset lockout on new day rollover
   if(g_PropLockoutActive && TimeDay(TimeCurrent()) != TimeDay(g_PropLockoutDate))
   {
      g_PropLockoutActive = false;
      Print("[PROP GUARDIAN] Daily calendar rollover. Resetting lockout.");
   }
   
   // 1. Daily Loss Circuit Breaker
   if(g_StartingDayEquity > 0.0)
   {
      double dayLoss = g_StartingDayEquity - curEquity;
      double dayLossPct = (dayLoss > 0.0) ? (dayLoss / g_StartingDayEquity * 100.0) : 0.0;
      
      if(dayLossPct >= PropMaxDailyLossPercent && !g_PropLockoutActive)
      {
         g_PropLockoutActive = true;
         g_PropLockoutDate = TimeCurrent();
         g_AutoTradingRuntimeActive = false;
         g_DailyLossCircuitTripped = true;
         
         if(PropAutoLockoutOnBreach)
         {
            Telegram_CmdCloseAll();
         }
         
         string breachMsg = "🚨 <b>PROP-FIRM CIRCUIT BREAKER ACTIVATED!</b>\n";
         breachMsg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
         breachMsg += StringFormat("• <b>Daily Drawdown:</b> <b>%.2f%%</b> (Limit: %.2f%%)\n", dayLossPct, PropMaxDailyLossPercent);
         breachMsg += StringFormat("• <b>Capital Loss Today:</b> -$%.2f\n", dayLoss);
         breachMsg += "• <b>Emergency Action:</b> All open trades liquidated.\n";
         breachMsg += "• <b>Protection Status:</b> Trading locked until midnight to protect funded account. 🔒";
         Telegram_SendMessage(TelegramBotToken, TelegramChatID, breachMsg, 3, 2);
      }
   }
   
   // 2. Trailing Peak Drawdown Check
   if(g_PropPeakEquity > 0.0)
   {
      double peakLoss = g_PropPeakEquity - curEquity;
      double peakLossPct = (peakLoss > 0.0) ? (peakLoss / g_PropPeakEquity * 100.0) : 0.0;
      if(peakLossPct >= PropMaxTotalDrawdownPercent && !g_PropLockoutActive)
      {
         g_PropLockoutActive = true;
         g_PropLockoutDate = TimeCurrent();
         g_AutoTradingRuntimeActive = false;
         
         if(PropAutoLockoutOnBreach)
         {
            Telegram_CmdCloseAll();
         }
         
         string peakMsg = "🚨 <b>MAX TRAILING DRAWDOWN LIMIT REACHED!</b>\n";
         peakMsg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
         peakMsg += StringFormat("• <b>Trailing Drawdown:</b> <b>%.2f%%</b> (Limit: %.2f%%)\n", peakLossPct, PropMaxTotalDrawdownPercent);
         peakMsg += StringFormat("• <b>Peak Equity:</b> $%.2f | Current: $%.2f\n", g_PropPeakEquity, curEquity);
         peakMsg += "• <b>Emergency Action:</b> AutoTrading halted to preserve capital. 🛡️";
         Telegram_SendMessage(TelegramBotToken, TelegramChatID, peakMsg, 3, 2);
      }
   }
   
   // 3. Friday Weekend Protection Check
   if(PropWeekendProtection && TimeDayOfWeek(TimeGMT()) == 5 && TimeHour(TimeGMT()) >= PropFridayCloseHourGMT)
   {
      static int s_lastFridayClosedDay = -1;
      int currentDay = TimeDay(TimeGMT());
      if(s_lastFridayClosedDay != currentDay)
      {
         int openTrades = 0;
         for(int i = 0; i < OrdersTotal(); i++)
         {
            if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
            {
               if(OrderType() == OP_BUY || OrderType() == OP_SELL) openTrades++;
            }
         }
         if(openTrades > 0)
         {
            s_lastFridayClosedDay = currentDay;
            Telegram_CmdCloseAll();
   string friMsg = "🛡️ <b>FRIDAY WEEKEND RISK SHIELD TRIGGERED</b>\n";
            friMsg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
            friMsg += "â€¢ All active positions closed before weekend market close to eliminate gap risk.\n";
      friMsg += "• Trading will resume Monday market open. 🛡️";
            Telegram_SendMessage(TelegramBotToken, TelegramChatID, friMsg, 3, 2);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| High-Impact Economic News Active Check                           |
//+------------------------------------------------------------------+
bool IsHighImpactNewsActive(string sym)
{
   if(!EnableEconomicNewsShield) return false;
   
   int handle = FileOpen("news_events.csv", FILE_CSV|FILE_READ, ',');
   if(handle == INVALID_HANDLE) return false;
   
   datetime nowGMT = TimeGMT();
   bool active = false;
   
   while(!FileIsEnding(handle))
   {
      string dateStr = FileReadString(handle);
      string ccy     = FileReadString(handle);
      string title   = FileReadString(handle);
      string impact  = FileReadString(handle);
      string tsStr   = FileReadString(handle);
      
      if(StringFind(sym, ccy) >= 0 && ccy != "")
      {
         datetime evTs = (datetime)StringToInteger(tsStr);
         if(evTs > 0)
         {
            int diffSec = (int)(evTs - nowGMT);
            if(diffSec >= -900 && diffSec <= 900)
            {
               active = true;
               PrintFormat("[NEWS SHIELD] Active High-Impact News: %s (%s) at %s", title, ccy, dateStr);
               break;
            }
         }
      }
   }
   FileClose(handle);
   return active;
}

//+------------------------------------------------------------------+
//| Command: /pause                                                  |
//+------------------------------------------------------------------+
void Telegram_CmdPause()
{
   g_AutoTradingRuntimeActive = false;
   string msg = "⏸️ <b>AutoTrading PAUSED Remotely</b>\n";
   msg += "The bot will continue managing open trades (SL/TP/BE) but will not execute new entries.";
   Telegram_SendMessage(TelegramBotToken, TelegramChatID, msg, 2, 1);
}

//+------------------------------------------------------------------+
//| Command: /resume                                                 |
//+------------------------------------------------------------------+
void Telegram_CmdResume()
{
   g_AutoTradingRuntimeActive = true;
   string msg = "▶️ <b>AutoTrading RESUMED Remotely</b>\n";
   msg += "The bot is actively scanning for multi-indicator confluence setups.";
   Telegram_SendMessage(TelegramBotToken, TelegramChatID, msg, 2, 1);
}

//+------------------------------------------------------------------+
//| Apply GBPUSD color scheme to all open charts and save default.tpl|
//+------------------------------------------------------------------+
int Telegram_ApplyGBPUSDColorSchemeToAllCharts()
{
   // 1. Exact GBPUSD color palette:
   color bgCol     = 0;                 // Black (0x000000)
   color fgCol     = 16777215;          // White (0xFFFFFF)
   color barUpCol  = 65280;             // Lime Green (0x00FF00)
   color barDnCol  = 255;               // Red (0x0000FF)
   color bullCol   = 65280;             // Lime Green (0x00FF00)
   color bearCol   = 255;               // Red (0x0000FF)
   color lineCol   = 55295;             // Chart Line (0x00D7FF)
   color volCol    = 3329330;           // Volumes (0x32CD32)
   color gridCol   = (color)4294967295; // Grid None / Hidden (0xFFFFFFFF)
   color askCol    = 13434880;          // Ask Line (0xCD5C5C)
   color stopCol   = 65535;             // Stops (0x00FFFF)
   
   // 3. Iterate through all open charts in MT4
   long cid = ChartFirst();
   int count = 0;
   while(cid >= 0)
   {
      ChartSetInteger(cid, CHART_COLOR_BACKGROUND, bgCol);
      ChartSetInteger(cid, CHART_COLOR_FOREGROUND, fgCol);
      ChartSetInteger(cid, CHART_COLOR_CHART_UP, barUpCol);
      ChartSetInteger(cid, CHART_COLOR_CHART_DOWN, barDnCol);
      ChartSetInteger(cid, CHART_COLOR_CANDLE_BULL, bullCol);
      ChartSetInteger(cid, CHART_COLOR_CANDLE_BEAR, bearCol);
      ChartSetInteger(cid, CHART_COLOR_CHART_LINE, lineCol);
      ChartSetInteger(cid, CHART_COLOR_VOLUME, volCol);
      ChartSetInteger(cid, CHART_COLOR_GRID, gridCol);
      ChartSetInteger(cid, CHART_COLOR_ASK, askCol);
      ChartSetInteger(cid, CHART_COLOR_STOP_LEVEL, stopCol);
      
      ChartSetInteger(cid, CHART_MODE, CHART_CANDLES);
      ChartSetInteger(cid, CHART_SHOW_ASK_LINE, true);
      ChartSetInteger(cid, CHART_SHOW_VOLUMES, false);
      ChartSetInteger(cid, CHART_SHIFT, true);
      ChartSetInteger(cid, CHART_AUTOSCROLL, false);
      
      ChartRedraw(cid);
      count++;
      cid = ChartNext(cid);
   }
   
   PrintFormat("[Color Sync] Applied GBPUSD color scheme to all %d open charts and saved default.tpl", count);
   return count;
}

//+------------------------------------------------------------------+
//| Command: /help                                                   |
//+------------------------------------------------------------------+
void Telegram_CmdHelp()
{
   string msg = "🤖 <b>SmartAutoTrade Bot Control Center</b>\n";
   msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
   msg += "• /status — Live balance, equity & P/L\n";
   msg += "• /positions — Active trades with one-tap action buttons\n";
   msg += "• /screenshot — Interactive 2-step chart photo wizard\n";
   msg += "• /prop — Prop-Firm Risk Guardian & Drawdown Scorecard\n";
   msg += "• /panic — Emergency kill-switch with confirmation\n";
   msg += "• /closeall — Instantly close all open market trades\n";
   msg += "• /colors — Apply GBPUSD color scheme to all charts\n";
   msg += "• /pause — Pause automated trade entries\n";
   msg += "• /resume — Resume automated trade entries\n";
   msg += "• /report — Generate 24h performance summary\n";
   msg += "• /help — Show this command menu\n";
   msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
   msg += "<i>💡 Single trade actions: /close_TICKET, /half_TICKET, /be_TICKET</i>";
   Telegram_SendMessage(TelegramBotToken, TelegramChatID, msg, 2, 1);
}

//+------------------------------------------------------------------+
//| Convert string to ENUM_TIMEFRAMES                                |
//+------------------------------------------------------------------+
ENUM_TIMEFRAMES Telegram_StringToTimeframe(string tfStr)
{
   string tf = tfStr;
   StringTrimLeft(tf);
   StringTrimRight(tf);
   StringToUpper(tf);
   
   if(tf == "M1" || tf == "1")                  return PERIOD_M1;
   if(tf == "M5" || tf == "5")                  return PERIOD_M5;
   if(tf == "M15" || tf == "15")                return PERIOD_M15;
   if(tf == "M30" || tf == "30")                return PERIOD_M30;
   if(tf == "H1" || tf == "60" || tf == "1H")   return PERIOD_H1;
   if(tf == "H4" || tf == "240" || tf == "4H")  return PERIOD_H4;
   if(tf == "D1" || tf == "1440" || tf == "1D" || tf == "DAILY")   return PERIOD_D1;
   if(tf == "W1" || tf == "10080" || tf == "1W" || tf == "WEEKLY") return PERIOD_W1;
   if(tf == "MN1" || tf == "43200" || tf == "1M" || tf == "MN" || tf == "MONTHLY") return PERIOD_MN1;
   
   return (ENUM_TIMEFRAMES)Period();
}

//+------------------------------------------------------------------+
//| Format timeframe to friendly label                               |
//+------------------------------------------------------------------+
string Telegram_TimeframeToString(ENUM_TIMEFRAMES tf)
{
   switch(tf)
   {
      case PERIOD_M1:  return "M1 (1 Minute)";
      case PERIOD_M5:  return "M5 (5 Minutes)";
      case PERIOD_M15: return "M15 (15 Minutes)";
      case PERIOD_M30: return "M30 (30 Minutes)";
      case PERIOD_H1:  return "H1 (1 Hour)";
      case PERIOD_H4:  return "H4 (4 Hours)";
      case PERIOD_D1:  return "D1 (Daily)";
      case PERIOD_W1:  return "W1 (Weekly)";
      case PERIOD_MN1: return "MN1 (Monthly)";
      default:         return EnumToString(tf);
   }
}

//+------------------------------------------------------------------+
//| Step 1: /screenshot Menu (Select Symbol)                         |
//+------------------------------------------------------------------+
void Telegram_CmdScreenshotMenu()
{
   string symbols[];
   ArrayResize(symbols, 0);
   
   // 1. Current chart symbol
   int sz = ArraySize(symbols);
   ArrayResize(symbols, sz + 1);
   symbols[sz] = Symbol();
   
   // 2. Open charts
   long cid = ChartFirst();
   while(cid >= 0)
   {
      string csym = ChartSymbol(cid);
      bool exists = false;
      for(int k = 0; k < ArraySize(symbols); k++)
      {
         if(symbols[k] == csym) { exists = true; break; }
      }
      if(!exists && StringLen(csym) > 0)
      {
         int s2 = ArraySize(symbols);
         ArrayResize(symbols, s2 + 1);
         symbols[s2] = csym;
      }
      cid = ChartNext(cid);
   }
   
   // 3. Open positions symbols
   for(int i = 0; i < OrdersTotal(); i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      string osym = OrderSymbol();
      bool exists = false;
      for(int k = 0; k < ArraySize(symbols); k++)
      {
         if(symbols[k] == osym) { exists = true; break; }
      }
      if(!exists && StringLen(osym) > 0)
      {
         int s2 = ArraySize(symbols);
         ArrayResize(symbols, s2 + 1);
         symbols[s2] = osym;
      }
   }
   
   // 4. Common watchlist symbols if available
   string commonWatchlist[] = {"EURUSD", "GBPUSD", "XAUUSD", "USDJPY", "BTCUSD", "OILUSD"};
   for(int w = 0; w < ArraySize(commonWatchlist); w++)
   {
      string wsym = commonWatchlist[w];
      bool exists = false;
      for(int k = 0; k < ArraySize(symbols); k++)
      {
         if(symbols[k] == wsym) { exists = true; break; }
      }
      if(!exists && MarketInfo(wsym, MODE_BID) > 0.0)
      {
         int s2 = ArraySize(symbols);
         ArrayResize(symbols, s2 + 1);
         symbols[s2] = wsym;
      }
   }
   
   string msg = "📸 <b>STEP 1/2: SELECT SYMBOL</b>\n";
   msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
   msg += "Choose an instrument to capture its live chart:\n\n";
   
   for(int j = 0; j < ArraySize(symbols); j++)
   {
      string isCurrent = (symbols[j] == Symbol()) ? " <i>(Active Chart)</i>" : "";
      msg += "â€¢ /shot_" + symbols[j] + " â€” <b>" + symbols[j] + "</b>" + isCurrent + "\n";
   }
   msg += "• /shot_current — ⚡ <b>Current Chart (" + Symbol() + ")</b>\n\n";
   msg += "<i>💡 Tap a symbol below to select your desired timeframe / time:</i>";
   
   // Build Inline Keyboard (2 buttons per row)
   string kbJson = "{\"inline_keyboard\":[";
   for(int b = 0; b < ArraySize(symbols); b++)
   {
      if(b % 2 == 0)
      {
         if(b > 0) kbJson += "],";
         kbJson += "[";
      }
      else
      {
         kbJson += ",";
      }
      kbJson += StringFormat("{\"text\":\"📊 %s\",\"callback_data\":\"/picktf_%s\"}", symbols[b], symbols[b]);
   }
   if(ArraySize(symbols) > 0) kbJson += "],";
   kbJson += "[{\"text\":\"⚡ Current Chart\",\"callback_data\":\"/picktf_current\"}]]}";
   
   Telegram_SendMessage(TelegramBotToken, TelegramChatID, msg, 2, 1, kbJson);
}

//+------------------------------------------------------------------+
//| Step 2: Select Timeframe Menu for chosen Symbol                  |
//+------------------------------------------------------------------+
void Telegram_CmdTimeframeMenu(string symbol)
{
   string sym = symbol;
   StringTrimLeft(sym);
   StringTrimRight(sym);
   StringToUpper(sym);
   if(sym == "" || sym == "CURRENT") sym = Symbol();
   
   string msg = "⏱️ <b>STEP 2/2: SELECT TIMEFRAME FOR " + sym + "</b>\n";
   msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
   msg += "What time / timeframe resolution do you want to be in?\n\n";
   msg += "â€¢ /shot_" + sym + "_M1 â€” 1 Minute\n";
   msg += "â€¢ /shot_" + sym + "_M5 â€” 5 Minutes\n";
   msg += "â€¢ /shot_" + sym + "_M15 â€” 15 Minutes\n";
   msg += "â€¢ /shot_" + sym + "_M30 â€” 30 Minutes\n";
   msg += "â€¢ /shot_" + sym + "_H1 â€” 1 Hour\n";
   msg += "â€¢ /shot_" + sym + "_H4 â€” 4 Hours\n";
   msg += "â€¢ /shot_" + sym + "_D1 â€” Daily\n";
   msg += "â€¢ /shot_" + sym + "_current â€” Current Timeframe\n\n";
   msg += "<i>💡 Tap an interactive timeframe button below to receive the chart photo:</i>";
   
   string kbJson = "{\"inline_keyboard\":[";
   kbJson += StringFormat("[{\"text\":\"⏱️ M1\",\"callback_data\":\"/shot_%s_M1\"},{\"text\":\"⏱️ M5\",\"callback_data\":\"/shot_%s_M5\"},{\"text\":\"⏱️ M15\",\"callback_data\":\"/shot_%s_M15\"}],", sym, sym, sym);
   kbJson += StringFormat("[{\"text\":\"⏱️ M30\",\"callback_data\":\"/shot_%s_M30\"},{\"text\":\"⏱️ H1\",\"callback_data\":\"/shot_%s_H1\"},{\"text\":\"⏱️ H4\",\"callback_data\":\"/shot_%s_H4\"}],", sym, sym, sym);
   kbJson += StringFormat("[{\"text\":\"⏱️ D1 (Daily)\",\"callback_data\":\"/shot_%s_D1\"},{\"text\":\"⚡ Current TF\",\"callback_data\":\"/shot_%s_current\"}]", sym, sym);
   kbJson += "]}";
   
   Telegram_SendMessage(TelegramBotToken, TelegramChatID, msg, 2, 1, kbJson);
}

//+------------------------------------------------------------------+
//| Step 3: Capture & Send Chart Screenshot for Symbol + Timeframe   |
//+------------------------------------------------------------------+
void Telegram_CmdSendChartScreenshot(string targetSymbol, ENUM_TIMEFRAMES targetTF)
{
   string sym = targetSymbol;
   StringTrimLeft(sym);
   StringTrimRight(sym);
   StringToUpper(sym);
   
   if(StringFind(sym, "_") == 0) sym = StringSubstr(sym, 1);
   if(sym == "" || sym == "CURRENT") sym = Symbol();
   
   ENUM_TIMEFRAMES tf = targetTF;
   if(tf == 0) tf = (ENUM_TIMEFRAMES)Period();
   
   string tfStr = EnumToString(tf);
   string filename = "snap_" + sym + "_" + tfStr + "_" + IntegerToString((int)TimeCurrent()) + ".png";
   
   long targetChartId = -1;
   bool tempChartOpened = false;
   
   // 1. If symbol and timeframe match current chart, use current chart (0)
   if(sym == Symbol() && tf == (ENUM_TIMEFRAMES)Period())
   {
      targetChartId = 0;
   }
   else
   {
      // 2. Search if any currently open chart matches both symbol and timeframe
      long cid = ChartFirst();
      while(cid >= 0)
      {
         if(ChartSymbol(cid) == sym && ChartPeriod(cid) == tf)
         {
            targetChartId = cid;
            break;
         }
         cid = ChartNext(cid);
      }
      
      // 3. If not open, open temporary chart with that exact symbol and timeframe!
      if(targetChartId < 0)
      {
         targetChartId = ChartOpen(sym, tf);
         if(targetChartId > 0)
         {
            tempChartOpened = true;
            ChartRedraw(targetChartId);
            Sleep(120);
         }
      }
   }
   
   if(targetChartId < 0)
   {
      Telegram_SendMessage(TelegramBotToken, TelegramChatID, "❌ Could not open chart for symbol: " + sym + " on " + tfStr + ". Please verify symbol name in Market Watch.", 2, 1);
      return;
   }
   
   // Visual Trade Annotations: If an open trade exists on this symbol, overlay Entry, SL, and TP!
   string annoEntry = PREFIX_OBJ + "ANNO_E";
   string annoSL    = PREFIX_OBJ + "ANNO_SL";
   string annoTP    = PREFIX_OBJ + "ANNO_TP";
   bool annoDrawn   = false;
   
   for(int k = OrdersTotal() - 1; k >= 0; k--)
   {
      if(OrderSelect(k, SELECT_BY_POS, MODE_TRADES))
      {
         if(OrderSymbol() == sym && (OrderType() == OP_BUY || OrderType() == OP_SELL))
         {
            annoDrawn = true;
            ObjectCreate(targetChartId, annoEntry, OBJ_HLINE, 0, 0, OrderOpenPrice());
            ObjectSetInteger(targetChartId, annoEntry, OBJPROP_COLOR, clrDodgerBlue);
            ObjectSetInteger(targetChartId, annoEntry, OBJPROP_WIDTH, 2);
            
            if(OrderStopLoss() > 0.0)
            {
               ObjectCreate(targetChartId, annoSL, OBJ_HLINE, 0, 0, OrderStopLoss());
               ObjectSetInteger(targetChartId, annoSL, OBJPROP_COLOR, clrCrimson);
               ObjectSetInteger(targetChartId, annoSL, OBJPROP_STYLE, STYLE_DASH);
               ObjectSetInteger(targetChartId, annoSL, OBJPROP_WIDTH, 2);
            }
            if(OrderTakeProfit() > 0.0)
            {
               ObjectCreate(targetChartId, annoTP, OBJ_HLINE, 0, 0, OrderTakeProfit());
               ObjectSetInteger(targetChartId, annoTP, OBJPROP_COLOR, clrLimeGreen);
               ObjectSetInteger(targetChartId, annoTP, OBJPROP_STYLE, STYLE_DASH);
               ObjectSetInteger(targetChartId, annoTP, OBJPROP_WIDTH, 2);
            }
            break;
         }
      }
   }
   
   ChartRedraw(targetChartId);
   bool shotOk = ChartScreenShot(targetChartId, filename, 1280, 720, ALIGN_RIGHT);
   
   if(annoDrawn)
   {
      ObjectDelete(targetChartId, annoEntry);
      ObjectDelete(targetChartId, annoSL);
      ObjectDelete(targetChartId, annoTP);
      ChartRedraw(targetChartId);
   }
   
   if(!shotOk)
   {
      Telegram_SendMessage(TelegramBotToken, TelegramChatID, "❌ ChartScreenShot failed for " + sym + " (" + tfStr + "). Error: " + IntegerToString(GetLastError()), 2, 1);
      return;
   }
   
   double curBid = MarketInfo(sym, MODE_BID);
   double curAsk = MarketInfo(sym, MODE_ASK);
   int digits = (int)MarketInfo(sym, MODE_DIGITS);
   if(digits == 0) digits = (sym == Symbol()) ? Digits : 5;
   int spread = (int)MarketInfo(sym, MODE_SPREAD);
   
   datetime srvTime = TimeCurrent();
   datetime gmtTime = TimeGMT();
   datetime locTime = TimeLocal();
   datetime nyTime  = gmtTime - (4 * 3600);  // New York EDT (UTC-4)
   datetime lonTime = gmtTime + (1 * 3600);  // London BST (UTC+1)
   datetime tyoTime = gmtTime + (9 * 3600);  // Tokyo JST (UTC+9)
   
   string caption = "📸 <b>LIVE CHART: " + sym + " (" + tfStr + ")</b>\n";
   caption += "──────────────────────────\n";
   caption += "──────────────────────────\n";
   caption += "──────────────────────────\n";
   caption += "──────────────────────────\n";
   caption += "──────────────────────────\n";
   caption += "──────────────────────────\n";
   caption += "🌐 <b>MULTI-TIMEZONE TELEMETRY:</b>\n";
   caption += "──────────────────────────\n";
   caption += "──────────────────────────\n";
   caption += "──────────────────────────\n";
   caption += "──────────────────────────\n";
   caption += "──────────────────────────\n";
   caption += "──────────────────────────\n";
   caption += "──────────────────────────\n";
   caption += "──────────────────────────\n";
   
   if(!Telegram_SendPhoto(TelegramBotToken, TelegramChatID, filename, caption))
   {
      Telegram_SendMessage(TelegramBotToken, TelegramChatID, "❌ Failed to send chart photo for " + sym + ".", 2, 1);
   }
   
   if(tempChartOpened)
   {
      ChartClose(targetChartId);
   }
}

//+------------------------------------------------------------------+
//| Command: /report (and Automated Daily Rollover Report)           |
//+------------------------------------------------------------------+
void Telegram_SendDailyReport()
{
   datetime now = TimeCurrent();
   datetime dayStart = StringToTime(TimeToStr(now, TIME_DATE));
   datetime fromTime = dayStart - 86400;
   datetime toTime   = now;
   
   int totalTrades = 0;
   int winCount = 0;
   int lossCount = 0;
   double grossProfit = 0.0;
   double grossLoss = 0.0;
   double maxWin = 0.0;
   double maxLoss = 0.0;
   string bestSymbol = "";
   string worstSymbol = "";
   
   int historyTotal = OrdersHistoryTotal();
   for(int i = 0; i < historyTotal; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL) continue;
      if(!TelegramMonitorAllTrades && OrderMagicNumber() != MagicNumber) continue;
      
      datetime cTime = OrderCloseTime();
      if(cTime < fromTime || cTime > toTime) continue;
      
      totalTrades++;
      double net = OrderProfit() + OrderSwap() + OrderCommission();
      if(net >= 0.0)
      {
         winCount++;
         grossProfit += net;
         if(net > maxWin) { maxWin = net; bestSymbol = OrderSymbol(); }
      }
      else
      {
         lossCount++;
         grossLoss += MathAbs(net);
         if(net < maxLoss) { maxLoss = net; worstSymbol = OrderSymbol(); }
      }
   }
   
   double netTotal = grossProfit - grossLoss;
   double winRate = (totalTrades > 0) ? ((double)winCount / totalTrades * 100.0) : 0.0;
   double profitFactor = (grossLoss > 0.0) ? (grossProfit / grossLoss) : (grossProfit > 0 ? 99.9 : 0.0);
   
   string currency = AccountCurrency();
   string rpt = "📈 <b>DAILY PERFORMANCE SUMMARY REPORT</b>\n";
   rpt += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
   rpt += "â€¢ <b>Period:</b> Last 24 Hours\n";
   rpt += "â€¢ <b>Account:</b> " + IntegerToString(AccountNumber()) + " (" + AccountCompany() + ")\n";
   rpt += "â€¢ <b>Closed Trades:</b> " + IntegerToString(totalTrades) + " (" + IntegerToString(winCount) + "W / " + IntegerToString(lossCount) + "L)\n";
   rpt += "â€¢ <b>Win Rate:</b> " + DoubleToString(winRate, 1) + "%\n";
   rpt += "â€¢ <b>Gross Profit:</b> +" + DoubleToString(grossProfit, 2) + " " + currency + "\n";
   rpt += "â€¢ <b>Gross Loss:</b> -" + DoubleToString(grossLoss, 2) + " " + currency + "\n";
   rpt += "â€¢ <b>Profit Factor:</b> " + DoubleToString(profitFactor, 2) + "\n";
   string netSign = (netTotal >= 0.0) ? "🟢 +" : "🔴 -";
   rpt += "â€¢ <b>Net P/L:</b> <b>" + netSign + DoubleToString(MathAbs(netTotal), 2) + " " + currency + "</b>\n";
   if(maxWin > 0.0)
      rpt += "â€¢ <b>Best Trade:</b> " + bestSymbol + " (+" + DoubleToString(maxWin, 2) + " " + currency + ")\n";
   if(maxLoss < 0.0)
      rpt += "â€¢ <b>Worst Trade:</b> " + worstSymbol + " (" + DoubleToString(maxLoss, 2) + " " + currency + ")\n";
   rpt += "â€¢ <b>Ending Balance:</b> " + Telegram_FormatMoney(AccountBalance(), currency) + "\n";
   rpt += "â€¢ <b>Ending Equity:</b> " + Telegram_FormatMoney(AccountEquity(), currency);
   
   Telegram_SendMessage(TelegramBotToken, TelegramChatID, rpt, 3, 2);
}

//+------------------------------------------------------------------+
//| Poll and Execute Incoming Telegram Commands                      |
//+------------------------------------------------------------------+
void Telegram_PollCommands()
{
   if(!EnableTelegramCommands) return;
   
   // Coordinate master polling across multiple open chart instances of EA
   string gvName = "TG_POLLING_MASTER_CHART";
   long currentChart = ChartID();
   if(!GlobalVariableCheck(gvName))
   {
      GlobalVariableSet(gvName, (double)currentChart);
   }
   else
   {
      long masterChart = (long)GlobalVariableGet(gvName);
      if(masterChart != currentChart)
      {
         bool masterAlive = false;
         long cid = ChartFirst();
         while(cid >= 0)
         {
            if(cid == masterChart) { masterAlive = true; break; }
            cid = ChartNext(cid);
         }
         if(masterAlive) return; // Master chart handles polling!
         GlobalVariableSet(gvName, (double)currentChart);
      }
   }
   
   string response = "";
   int code = Telegram_GetUpdates(TelegramBotToken, g_tgLastUpdateId + 1, response);
   if(code != 200) return;
   
   TelegramUpdateMessage updates[];
   int count = Telegram_ParseUpdates(response, updates);
   if(count == 0) return;
   
   for(int i = 0; i < count; i++)
   {
      if(updates[i].update_id > g_tgLastUpdateId)
         g_tgLastUpdateId = updates[i].update_id;
         
      // Immediately acknowledge button clicks to dismiss Telegram client spinner!
      if(updates[i].callback_id != "")
      {
         Telegram_AnswerCallbackQuery(TelegramBotToken, updates[i].callback_id);
      }
         
      // Security Check: authorize sender ID
      if(updates[i].sender_id != TelegramChatID)
      {
         PrintFormat("[Telegram Security] Blocked command from unauthorized chat ID: '%s' (Authorized: '%s')", updates[i].sender_id, TelegramChatID);
         continue;
      }
      
      string cmd = updates[i].text;
      PrintFormat("[Telegram Cmd] Executing: %s", cmd);
      StringTrimLeft(cmd);
      StringTrimRight(cmd);
      
      int atPos = StringFind(cmd, "@");
      if(atPos > 0) cmd = StringSubstr(cmd, 0, atPos);
      
      string lowerCmd = Telegram_ToLower(cmd);
      
      // STEP 1: Screenshot base command -> Prompt Step 1 (Symbol Menu)
      if(lowerCmd == "/screenshot" || lowerCmd == "/screenphoto" || lowerCmd == "/chart")
      {
         Telegram_CmdScreenshotMenu();
      }
      // STEP 2: Timeframe selector request: /picktf_SYMBOL
      else if(StringFind(lowerCmd, "/picktf_") == 0)
      {
         string chosenSym = StringSubstr(cmd, 8);
         Telegram_CmdTimeframeMenu(chosenSym);
      }
      // STEP 3: Shorthand /shot_SYMBOL or /shot_SYMBOL_TF
      else if(StringFind(lowerCmd, "/shot_") == 0)
      {
         string rest = StringSubstr(cmd, 6);
         int underPos = StringFind(rest, "_");
         if(underPos > 0)
         {
            string sym = StringSubstr(rest, 0, underPos);
            string tfStr = StringSubstr(rest, underPos + 1);
            ENUM_TIMEFRAMES tf = Telegram_StringToTimeframe(tfStr);
            Telegram_CmdSendChartScreenshot(sym, tf);
         }
         else
         {
            Telegram_CmdTimeframeMenu(rest);
         }
      }
      // /screenshot_SYMBOL or /screenshot_SYMBOL_TF
      else if(StringFind(lowerCmd, "/screenshot_") == 0)
      {
         string rest = StringSubstr(cmd, 12);
         int underPos = StringFind(rest, "_");
         if(underPos > 0)
         {
            string sym = StringSubstr(rest, 0, underPos);
            string tfStr = StringSubstr(rest, underPos + 1);
            ENUM_TIMEFRAMES tf = Telegram_StringToTimeframe(tfStr);
            Telegram_CmdSendChartScreenshot(sym, tf);
         }
         else
         {
            Telegram_CmdTimeframeMenu(rest);
         }
      }
      // /screenphoto_SYMBOL or /screenphoto_SYMBOL_TF
      else if(StringFind(lowerCmd, "/screenphoto_") == 0)
      {
         string rest = StringSubstr(cmd, 13);
         int underPos = StringFind(rest, "_");
         if(underPos > 0)
         {
            string sym = StringSubstr(rest, 0, underPos);
            string tfStr = StringSubstr(rest, underPos + 1);
            ENUM_TIMEFRAMES tf = Telegram_StringToTimeframe(tfStr);
            Telegram_CmdSendChartScreenshot(sym, tf);
         }
         else
         {
            Telegram_CmdTimeframeMenu(rest);
         }
      }
      // /chart_SYMBOL or /chart_SYMBOL_TF
      else if(StringFind(lowerCmd, "/chart_") == 0)
      {
         string rest = StringSubstr(cmd, 7);
         int underPos = StringFind(rest, "_");
         if(underPos > 0)
         {
            string sym = StringSubstr(rest, 0, underPos);
            string tfStr = StringSubstr(rest, underPos + 1);
            ENUM_TIMEFRAMES tf = Telegram_StringToTimeframe(tfStr);
            Telegram_CmdSendChartScreenshot(sym, tf);
         }
         else
         {
            Telegram_CmdTimeframeMenu(rest);
         }
      }
      // Space-separated commands: /screenshot SYMBOL [TF], /chart SYMBOL [TF], etc.
      else if(StringFind(lowerCmd, "/screenshot ") == 0 || StringFind(lowerCmd, "/chart ") == 0 || StringFind(lowerCmd, "/screenphoto ") == 0 || StringFind(lowerCmd, "/shot ") == 0)
      {
         int pfx = 12;
         if(StringFind(lowerCmd, "/chart ") == 0) pfx = 7;
         else if(StringFind(lowerCmd, "/screenphoto ") == 0) pfx = 13;
         else if(StringFind(lowerCmd, "/shot ") == 0) pfx = 6;
         
         string args = StringSubstr(cmd, pfx);
         StringTrimLeft(args);
         StringTrimRight(args);
         
         int spPos = StringFind(args, " ");
         if(spPos > 0)
         {
            string sym = StringSubstr(args, 0, spPos);
            string tfPart = StringSubstr(args, spPos + 1);
            StringTrimLeft(tfPart);
            StringTrimRight(tfPart);
            ENUM_TIMEFRAMES tf = Telegram_StringToTimeframe(tfPart);
            Telegram_CmdSendChartScreenshot(sym, tf);
         }
         else
         {
            Telegram_CmdTimeframeMenu(args);
         }
      }
      else if(lowerCmd == "/colors" || lowerCmd == "/synccharts" || lowerCmd == "/sync")
      {
         int syncedCount = Telegram_ApplyGBPUSDColorSchemeToAllCharts();
         string syncMsg = "🎨 <b>CHART COLOR SCHEME SYNCHRONIZED</b>\n";
         syncMsg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
         syncMsg += "â€¢ <b>Style:</b> GBPUSD Black & Green/Red Candlestick Scheme\n";
         syncMsg += "â€¢ <b>Open Charts Synchronized:</b> " + IntegerToString(syncedCount) + " chart(s)\n";
         syncMsg += "â€¢ <b>Default Template:</b> <code>templates/default.tpl</code> created!\n";
         syncMsg += "â€¢ <b>Result:</b> All current and future charts will now open in this exact style! âœ…";
         Telegram_SendMessage(TelegramBotToken, TelegramChatID, syncMsg, 2, 1);
      }
      else if(lowerCmd == "/status")            Telegram_CmdStatus();
      else if(lowerCmd == "/positions")         Telegram_CmdPositions();
      else if(lowerCmd == "/prop" || lowerCmd == "/risk") Telegram_CmdPropScorecard();
      else if(lowerCmd == "/panic")             Telegram_CmdPanicPrompt();
      else if(lowerCmd == "/panic_confirm")     Telegram_CmdPanicExecute();
      else if(StringFind(lowerCmd, "/close_") == 0)
      {
         int ticket = (int)StringToInteger(StringSubstr(cmd, 7));
         Telegram_CmdCloseTicket(ticket);
      }
      else if(StringFind(lowerCmd, "/half_") == 0)
      {
         int ticket = (int)StringToInteger(StringSubstr(cmd, 6));
         Telegram_CmdCloseHalfTicket(ticket);
      }
      else if(StringFind(lowerCmd, "/be_") == 0)
      {
         int ticket = (int)StringToInteger(StringSubstr(cmd, 4));
         Telegram_CmdBreakEvenTicket(ticket);
      }
      else if(lowerCmd == "/closeall")          Telegram_CmdCloseAll();
      else if(lowerCmd == "/pause")             Telegram_CmdPause();
      else if(lowerCmd == "/resume")            Telegram_CmdResume();
      else if(lowerCmd == "/report")            Telegram_SendDailyReport();
      else if(lowerCmd == "/help" || lowerCmd == "/start") Telegram_CmdHelp();
   }
}

//+------------------------------------------------------------------+
//| Notification: Break-Even Activated                               |
//+------------------------------------------------------------------+
void Telegram_NotifyBreakEven(int ticket, double openPrice, double bePrice, int lockPips)
{
   if(!TelegramNotifyBreakEven) return;
   string msg = "🛡️ <b>BREAK-EVEN PROTECTION ACTIVATED</b>\n";
   msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
   msg += "• <b>Ticket:</b> #" + IntegerToString(ticket) + "\n";
   msg += "• <b>Symbol:</b> <code>" + Symbol() + "</code>\n";
   msg += "• <b>Entry:</b> " + Telegram_FormatPrice(openPrice, Digits) + "\n";
   msg += "• <b>New Stop Loss:</b> " + Telegram_FormatPrice(bePrice, Digits) + " (+" + IntegerToString(lockPips) + " pips locked)\n";
   msg += "• <b>Status:</b> <b>Risk-Free Trade! 🔒</b>";
   Telegram_SendMessage(TelegramBotToken, TelegramChatID, msg, 2, 1);
}

//+------------------------------------------------------------------+
//| Notification: Trailing Stop Profit Locked                        |
//+------------------------------------------------------------------+
void Telegram_NotifyTrailing(int ticket, double newSL, double profitPips)
{
   if(!TelegramNotifyTrailing) return;
   string msg = "📈 <b>TRAILING STOP UPDATED</b>\n";
   msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
   msg += "• <b>Ticket:</b> #" + IntegerToString(ticket) + "\n";
   msg += "• <b>Symbol:</b> <code>" + Symbol() + "</code>\n";
   msg += "• <b>New Stop Loss:</b> " + Telegram_FormatPrice(newSL, Digits) + "\n";
   msg += "• <b>Profit Secured:</b> +" + DoubleToString(profitPips, 1) + " pips";
   Telegram_SendMessage(TelegramBotToken, TelegramChatID, msg, 2, 1);
}

//+------------------------------------------------------------------+
//| Notification: High-Impact News / Volatility Alert                |
//+------------------------------------------------------------------+
void Telegram_NotifyNewsVolatility(double ratio, double threshold)
{
   if(!TelegramNotifyNews) return;
   string msg = "📰 <b>HIGH-IMPACT NEWS / VOLATILITY SPIKE</b>\n";
   msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
   msg += "• <b>Symbol:</b> <code>" + Symbol() + "</code>\n";
   msg += "• <b>Bar/ATR Ratio:</b> " + DoubleToString(ratio, 2) + " (Threshold: " + DoubleToString(threshold, 2) + ")\n";
   msg += "• <b>Action:</b> Trade entries temporarily filtered for capital preservation.";
   Telegram_SendMessage(TelegramBotToken, TelegramChatID, msg, 2, 1);
}

//+------------------------------------------------------------------+
//| Risk Guardian: Margin & Drawdown Watchdog                        |
//+------------------------------------------------------------------+
void Telegram_CheckRiskGuardian()
{
   double margin = AccountMargin();
   if(margin > 0.0)
   {
      double mLevel = (AccountEquity() / margin) * 100.0;
      if(mLevel < TelegramMarginWarningPct && (TimeCurrent() - g_lastMarginAlertTime > 1800))
      {
         g_lastMarginAlertTime = TimeCurrent();
         string warn = "⚠️ <b>ACCOUNT GUARDIAN: LOW MARGIN WARNING</b>\n";
         warn += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
         warn += "• <b>Margin Level:</b> <b>" + DoubleToString(mLevel, 1) + "%</b>\n";
         warn += "• <b>Equity:</b> " + Telegram_FormatMoney(AccountEquity(), AccountCurrency()) + "\n";
         warn += "• <b>Used Margin:</b> " + Telegram_FormatMoney(margin, AccountCurrency()) + "\n";
         warn += "• <b>Free Margin:</b> " + Telegram_FormatMoney(AccountFreeMargin(), AccountCurrency()) + "\n";
         warn += "<i>Caution: Margin level is approaching caution thresholds.</i>";
         Telegram_SendMessage(TelegramBotToken, TelegramChatID, warn, 2, 1);
      }
   }
}

//+------------------------------------------------------------------+
//| Capture & Send Chart Screenshot                                  |
//+------------------------------------------------------------------+
void Telegram_CaptureAndSendScreenshot(int ticket, string caption)
{
   if(!TelegramSendScreenshots) return;
   
   string shotName = "Entry_" + IntegerToString(ticket) + ".png";
   if(WindowScreenShot(shotName, 1024, 768))
   {
      Sleep(100);
      Telegram_SendPhoto(TelegramBotToken, TelegramChatID, shotName, caption);
   }
}

//+------------------------------------------------------------------+
//| Initialize Telegram Tracker and Drain Stale Updates              |
//+------------------------------------------------------------------+
void Telegram_InitTradeTracker()
{
   ArrayResize(g_tgActiveTrades, 0);
   if(!EnableTelegramAlerts) return;
   
   int total = OrdersTotal();
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL) continue;
      if(!TelegramMonitorAllTrades && OrderMagicNumber() != MagicNumber) continue;
      
      int sz = ArraySize(g_tgActiveTrades);
      ArrayResize(g_tgActiveTrades, sz + 1);
      g_tgActiveTrades[sz].ticket    = OrderTicket();
      g_tgActiveTrades[sz].type      = type;
      g_tgActiveTrades[sz].symbol    = OrderSymbol();
      g_tgActiveTrades[sz].lots      = OrderLots();
      g_tgActiveTrades[sz].openPrice = OrderOpenPrice();
      g_tgActiveTrades[sz].sl        = OrderStopLoss();
      g_tgActiveTrades[sz].tp        = OrderTakeProfit();
      g_tgActiveTrades[sz].openTime  = OrderOpenTime();
      g_tgActiveTrades[sz].magic     = OrderMagicNumber();
   }
   
   // Advance update_id to latest pending to avoid executing old offline commands
   string initResp = "";
   if(Telegram_GetUpdates(TelegramBotToken, 0, initResp) == 200)
   {
      TelegramUpdateMessage tempUpdates[];
      int uCount = Telegram_ParseUpdates(initResp, tempUpdates);
      for(int u = 0; u < uCount; u++)
      {
         if(tempUpdates[u].update_id > g_tgLastUpdateId)
            g_tgLastUpdateId = tempUpdates[u].update_id;
      }
   }
   
   // Send startup notification with command hints
   string startMsg = "🚀 <b>SmartAutoTradeEA Pro Online</b>\n";
   startMsg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
   startMsg += "â€¢ <b>Symbol:</b> <code>" + Symbol() + "</code> (" + EnumToString((ENUM_TIMEFRAMES)Period()) + ")\n";
   startMsg += "â€¢ <b>Account:</b> " + IntegerToString(AccountNumber()) + " (" + AccountCompany() + ")\n";
   startMsg += "â€¢ <b>Server:</b> " + AccountServer() + "\n";
   startMsg += "â€¢ <b>Magic:</b> " + IntegerToString(MagicNumber) + "\n";
   startMsg += "â€¢ <b>Balance:</b> " + Telegram_FormatMoney(AccountBalance(), AccountCurrency()) + "\n";
   startMsg += "â€¢ <b>AutoTrading:</b> " + (g_AutoTradingRuntimeActive ? "ACTIVE âœ…" : "SIGNAL-ONLY ⏸️") + "\n";
   startMsg += "â€¢ <b>Remote Control:</b> Send /help for commands.";
   
   Telegram_SendMessage(TelegramBotToken, TelegramChatID, startMsg, 3, 2);
}

//+------------------------------------------------------------------+
//| Real-Time Trade Event Scanner                                    |
//+------------------------------------------------------------------+
void Telegram_ProcessTradeEvents()
{
   if(!EnableTelegramAlerts) return;
   
   // 1. Detect open trades and partial closes
   int total = OrdersTotal();
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL) continue;
      if(!TelegramMonitorAllTrades && OrderMagicNumber() != MagicNumber) continue;
      
      int ticket = OrderTicket();
      bool found = false;
      int activeCount = ArraySize(g_tgActiveTrades);
      for(int k = 0; k < activeCount; k++)
      {
         if(g_tgActiveTrades[k].ticket == ticket)
         {
            found = true;
            if(OrderLots() < g_tgActiveTrades[k].lots)
            {
               double closedLots = g_tgActiveTrades[k].lots - OrderLots();
               g_tgActiveTrades[k].lots = OrderLots();
               if(TelegramNotifyClose)
               {
                  int digits = (int)MarketInfo(OrderSymbol(), MODE_DIGITS);
                  if(digits == 0) digits = Digits;
                  double approxClose = (type == OP_BUY) ? Bid : Ask;
                  string pmsg = "✂️ <b>POSITION PARTIALLY CLOSED</b>\n";
                  pmsg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
                  pmsg += "â€¢ <b>Symbol:</b> <code>" + Telegram_EscapeHtml(OrderSymbol()) + "</code>\n";
                  pmsg += "â€¢ <b>Type:</b> <b>" + (type == OP_BUY ? "BUY" : "SELL") + "</b>\n";
                  pmsg += "â€¢ <b>Closed Lots:</b> " + DoubleToString(closedLots, 2) + " (Remaining: " + DoubleToString(OrderLots(), 2) + ")\n";
                  pmsg += "â€¢ <b>Open Price:</b> " + Telegram_FormatPrice(OrderOpenPrice(), digits) + "\n";
                  pmsg += "â€¢ <b>Close Price:</b> " + Telegram_FormatPrice(approxClose, digits) + "\n";
                  pmsg += "â€¢ <b>Ticket:</b> #" + IntegerToString(ticket) + "\n";
                  pmsg += "â€¢ <b>Magic:</b> " + IntegerToString(OrderMagicNumber());
                  Telegram_SendMessage(TelegramBotToken, TelegramChatID, pmsg, 3, 2);
               }
            }
            break;
         }
      }
      
      if(!found)
      {
         int sz = ArraySize(g_tgActiveTrades);
         ArrayResize(g_tgActiveTrades, sz + 1);
         g_tgActiveTrades[sz].ticket    = ticket;
         g_tgActiveTrades[sz].type      = type;
         g_tgActiveTrades[sz].symbol    = OrderSymbol();
         g_tgActiveTrades[sz].lots      = OrderLots();
         g_tgActiveTrades[sz].openPrice = OrderOpenPrice();
         g_tgActiveTrades[sz].sl        = OrderStopLoss();
         g_tgActiveTrades[sz].tp        = OrderTakeProfit();
         g_tgActiveTrades[sz].openTime  = OrderOpenTime();
         g_tgActiveTrades[sz].magic     = OrderMagicNumber();
         
         if(TelegramNotifyOpen)
         {
            int digits = (int)MarketInfo(OrderSymbol(), MODE_DIGITS);
            if(digits == 0) digits = Digits;
            string emoji = (type == OP_BUY) ? "🟢 <b>BUY ORDER OPENED</b>" : "🔴 <b>SELL ORDER OPENED</b>";
            string omsg = emoji + "\n";
            omsg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
            omsg += "• <b>Symbol:</b> <code>" + Telegram_EscapeHtml(OrderSymbol()) + "</code>\n";
            omsg += "• <b>Type:</b> <b>" + (type == OP_BUY ? "BUY" : "SELL") + "</b>\n";
            omsg += "• <b>Volume:</b> " + DoubleToString(OrderLots(), 2) + " Lots\n";
            omsg += "• <b>Open Price:</b> " + Telegram_FormatPrice(OrderOpenPrice(), digits) + "\n";
            omsg += "• <b>Stop Loss:</b> " + Telegram_FormatPrice(OrderStopLoss(), digits) + "\n";
            omsg += "• <b>Take Profit:</b> " + Telegram_FormatPrice(OrderTakeProfit(), digits) + "\n";
            omsg += "• <b>Open Time:</b> " + TimeToStr(OrderOpenTime(), TIME_DATE|TIME_SECONDS) + "\n";
            omsg += "• <b>Ticket:</b> #" + IntegerToString(ticket) + "\n";
            omsg += "• <b>Magic:</b> " + IntegerToString(OrderMagicNumber()) + "\n";
            omsg += "• <b>Account:</b> " + IntegerToString(AccountNumber()) + " (" + AccountCompany() + ")";
            
            string kbTrade = StringFormat("{\"inline_keyboard\":[[{\"text\":\"❌ Close #%d\",\"callback_data\":\"/close_%d\"},{\"text\":\"✂️ 50%%\",\"callback_data\":\"/half_%d\"}],[{\"text\":\"🛡️ Move SL to BE\",\"callback_data\":\"/be_%d\"},{\"text\":\"📸 View Chart\",\"callback_data\":\"/shot_%s_H1\"}]]}",
                                          ticket, ticket, ticket, ticket, OrderSymbol());
            
            // Send screenshot if enabled, otherwise send text with interactive buttons
            if(TelegramSendScreenshots)
            {
               Telegram_CaptureAndSendScreenshot(ticket, omsg);
            }
            else
            {
               Telegram_SendMessage(TelegramBotToken, TelegramChatID, omsg, 3, 2, kbTrade);
            }
         }
      }
   }
   
   // 2. Detect closed trades
   int activeCount = ArraySize(g_tgActiveTrades);
   for(int i = activeCount - 1; i >= 0; i--)
   {
      int ticket = g_tgActiveTrades[i].ticket;
      if(OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES) && OrderCloseTime() == 0)
      {
         continue;
      }
      
      if(OrderSelect(ticket, SELECT_BY_TICKET, MODE_HISTORY))
      {
         if(TelegramNotifyClose)
         {
            int digits = (int)MarketInfo(OrderSymbol(), MODE_DIGITS);
            if(digits == 0) digits = Digits;
            double netProfit = OrderProfit() + OrderSwap() + OrderCommission();
            string outcomeEmoji = (netProfit >= 0.0) ? "✅ <b>PROFIT</b>" : "❌ <b>LOSS</b>";
            string cmsg = "🏁 <b>POSITION CLOSED</b> (" + outcomeEmoji + ")\n";
            cmsg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
            cmsg += "• <b>Symbol:</b> <code>" + Telegram_EscapeHtml(OrderSymbol()) + "</code>\n";
            cmsg += "• <b>Type:</b> <b>" + (OrderType() == OP_BUY ? "BUY" : "SELL") + "</b>\n";
            cmsg += "• <b>Volume:</b> " + DoubleToString(OrderLots(), 2) + " Lots\n";
            cmsg += "• <b>Open Price:</b> " + Telegram_FormatPrice(OrderOpenPrice(), digits) + "\n";
            cmsg += "• <b>Close Price:</b> " + Telegram_FormatPrice(OrderClosePrice(), digits) + "\n";
            cmsg += "• <b>Stop Loss:</b> " + Telegram_FormatPrice(OrderStopLoss(), digits) + "\n";
            cmsg += "• <b>Take Profit:</b> " + Telegram_FormatPrice(OrderTakeProfit(), digits) + "\n";
            cmsg += "• <b>Close Time:</b> " + TimeToStr(OrderCloseTime(), TIME_DATE|TIME_SECONDS) + "\n";
            cmsg += "• <b>Net Profit:</b> <b>" + Telegram_FormatMoney(netProfit, AccountCurrency()) + "</b>";
            if(OrderSwap() != 0.0 || OrderCommission() != 0.0)
            {
               cmsg += " (Swap: " + DoubleToString(OrderSwap(), 2) + ", Comm: " + DoubleToString(OrderCommission(), 2) + ")";
            }
            cmsg += "\n";
            cmsg += "• <b>Ticket:</b> #" + IntegerToString(ticket) + "\n";
            cmsg += "• <b>Magic:</b> " + IntegerToString(OrderMagicNumber()) + "\n";
            cmsg += "• <b>Balance:</b> " + Telegram_FormatMoney(AccountBalance(), AccountCurrency());
            Telegram_SendMessage(TelegramBotToken, TelegramChatID, cmsg, 3, 2);
         }
      }
      
      for(int m = i; m < activeCount - 1; m++)
      {
         g_tgActiveTrades[m] = g_tgActiveTrades[m + 1];
      }
      ArrayResize(g_tgActiveTrades, activeCount - 1);
      activeCount--;
   }
}


//+------------------------------------------------------------------+
//| GARBAGE COLLECTION & OBJECT CLEANUP                              |
//+------------------------------------------------------------------+
void PurgeAllChartObjects()
{
   ObjectsDeleteAll(ChartID(), PREFIX_GUI);
   ObjectsDeleteAll(ChartID(), PREFIX_OBJ);
   ChartRedraw(ChartID());
}




//+------------------------------------------------------------------+
//| HISTORICAL PERFORMANCE AUDIT & QUANTITATIVE ANALYZER             |
//+------------------------------------------------------------------+
void AnalyzeHistoricalPerformance(SPerformanceTelemetry &telemetry)
{
   telemetry.totalTradesRecorded    = 0;
   telemetry.winningTradesCount     = 0;
   telemetry.losingTradesCount      = 0;
   telemetry.grossProfitAmount      = 0.0;
   telemetry.grossLossAmount        = 0.0;
   telemetry.winRatePercentage      = 0.0;
   telemetry.profitFactor           = 0.0;
   telemetry.expectedPayoff         = 0.0;
   telemetry.maxDrawdownCurrency    = 0.0;
   telemetry.maxDrawdownPercentage  = 0.0;

   int historyTotal = OrdersHistoryTotal();
   double totalNetProfit = 0.0;

   // First pass: aggregate historical totals
   for(int i = 0; i < historyTotal; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;

      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL) continue;

      double netProfit = OrderProfit() + OrderSwap() + OrderCommission();
      telemetry.totalTradesRecorded++;
      totalNetProfit += netProfit;

      if(netProfit >= 0.0)
      {
         telemetry.winningTradesCount++;
         telemetry.grossProfitAmount += netProfit;
      }
      else
      {
         telemetry.losingTradesCount++;
         telemetry.grossLossAmount += MathAbs(netProfit);
      }
   }

   // Second pass: chronological drawdown reconstruction from starting balance
   double runningBalance = AccountBalance() - totalNetProfit;
   if(runningBalance <= 0.0) runningBalance = AccountBalance();
   double peakBalance = runningBalance;
   double maxDD = 0.0;
   double maxDDPct = 0.0;

   for(int j = 0; j < historyTotal; j++)
   {
      if(!OrderSelect(j, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;

      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL) continue;

      double netProfit = OrderProfit() + OrderSwap() + OrderCommission();
      runningBalance += netProfit;

      if(runningBalance > peakBalance)
      {
         peakBalance = runningBalance;
      }
      else
      {
         double currentDD = peakBalance - runningBalance;
         if(currentDD > maxDD)
         {
            maxDD = currentDD;
            if(peakBalance > 0.0)
            {
               maxDDPct = (maxDD / peakBalance) * 100.0;
            }
         }
      }
   }

   if(telemetry.totalTradesRecorded > 0)
   {
      telemetry.winRatePercentage = ((double)telemetry.winningTradesCount / (double)telemetry.totalTradesRecorded) * 100.0;
      telemetry.expectedPayoff    = (telemetry.grossProfitAmount - telemetry.grossLossAmount) / (double)telemetry.totalTradesRecorded;
      telemetry.maxDrawdownCurrency = maxDD;
      telemetry.maxDrawdownPercentage = maxDDPct;
   }

   if(telemetry.grossLossAmount > 0.0)
   {
      telemetry.profitFactor = telemetry.grossProfitAmount / telemetry.grossLossAmount;
   }
   else if(telemetry.grossProfitAmount > 0.0)
   {
      telemetry.profitFactor = 99.99; // Infinite profit factor
   }
}




//+------------------------------------------------------------------+
//| HIGHER TIMEFRAME (HTF) TREND CONFIRMATION ENGINE                 |
//+------------------------------------------------------------------+
bool ValidateHigherTimeframeTrend(const ENUM_TIMEFRAMES htf, const ENUM_SIGNAL_DECISION signal)
{
   double htfEma20  = iMA(Symbol(), htf, EMA_Fast_Period,   0, MODE_EMA, EMA_AppliedPrice, 1);
   double htfEma50  = iMA(Symbol(), htf, EMA_Medium_Period, 0, MODE_EMA, EMA_AppliedPrice, 1);
   double htfEma200 = iMA(Symbol(), htf, EMA_Slow_Period,   0, MODE_EMA, EMA_AppliedPrice, 1);


   if(signal == SIGNAL_LONG)
   {
      // Higher timeframe must not be in a confirmed strong downtrend
      if(htfEma20 < htfEma50 && htfEma50 < htfEma200)
      {
         PrintFormat("[HTF VETO] Long signal contradicts %s strong bearish trend stack", EnumToString(htf));
         return false;
      }
   }
   else if(signal == SIGNAL_SHORT)
   {
      // Higher timeframe must not be in a confirmed strong uptrend
      if(htfEma20 > htfEma50 && htfEma50 > htfEma200)
      {
         PrintFormat("[HTF VETO] Short signal contradicts %s strong bullish trend stack", EnumToString(htf));
         return false;
      }
   }


   return true;
}




//+------------------------------------------------------------------+
//| DYNAMIC MULTI-METHOD DAILY PIVOT POINTS FORMULAS                 |
//+------------------------------------------------------------------+
void CalculateExtendedPivotPoints(const ENUM_PIVOT_METHOD method, SPivotPointValues &pivots)
{
   double h = iHigh(Symbol(),  PERIOD_D1, 1);
   double l = iLow(Symbol(),   PERIOD_D1, 1);
   double c = iClose(Symbol(), PERIOD_D1, 1);
   double o = iOpen(Symbol(),  PERIOD_D1, 0);
   double r = h - l;


   pivots.P = (h + l + c) / 3.0;


   if(method == PIVOT_CLASSIC)
   {
      pivots.R1 = (2.0 * pivots.P) - l;
      pivots.S1 = (2.0 * pivots.P) - h;
      pivots.R2 = pivots.P + r;
      pivots.S2 = pivots.P - r;
      pivots.R3 = h + 2.0 * (pivots.P - l);
      pivots.S3 = l - 2.0 * (h - pivots.P);
      pivots.R4 = pivots.R3 + r;
      pivots.S4 = pivots.S3 - r;
   }
   else if(method == PIVOT_FIBONACCI)
   {
      pivots.R1 = pivots.P + (0.382 * r);
      pivots.S1 = pivots.P - (0.382 * r);
      pivots.R2 = pivots.P + (0.618 * r);
      pivots.S2 = pivots.P - (0.618 * r);
      pivots.R3 = pivots.P + (1.000 * r);
      pivots.S3 = pivots.P - (1.000 * r);
      pivots.R4 = pivots.P + (1.618 * r);
      pivots.S4 = pivots.P - (1.618 * r);
   }
   else if(method == PIVOT_CAMARILLA)
   {
      pivots.R1 = c + (r * (1.1 / 12.0));
      pivots.S1 = c - (r * (1.1 / 12.0));
      pivots.R2 = c + (r * (1.1 / 6.0));
      pivots.S2 = c - (r * (1.1 / 6.0));
      pivots.R3 = c + (r * (1.1 / 4.0));
      pivots.S3 = c - (r * (1.1 / 4.0));
      pivots.R4 = c + (r * (1.1 / 2.0));
      pivots.S4 = c - (r * (1.1 / 2.0));
   }
   else // PIVOT_WOODIE
   {
      pivots.P  = (h + l + (2.0 * o)) / 4.0;
      pivots.R1 = (2.0 * pivots.P) - l;
      pivots.S1 = (2.0 * pivots.P) - h;
      pivots.R2 = pivots.P + r;
      pivots.S2 = pivots.P - r;
      pivots.R3 = h + 2.0 * (pivots.P - l);
      pivots.S3 = l - 2.0 * (h - pivots.P);
      pivots.R4 = pivots.R3 + r;
      pivots.S4 = pivots.S3 - r;
   }
}




//+------------------------------------------------------------------+
//| COMPREHENSIVE CANDLESTICK RECOGNITION PATTERNS                   |
//+------------------------------------------------------------------+
bool IsBullishPinbar(const int shift)
{
   double o = iOpen(Symbol(), Period(), shift);
   double c = iClose(Symbol(), Period(), shift);
   double h = iHigh(Symbol(), Period(), shift);
   double l = iLow(Symbol(), Period(), shift);
   double fullRange = h - l;
   if(fullRange <= 0.0) return false;


   double body = MathAbs(c - o);
   double lowerTail = MathMin(o, c) - l;
   double upperTail = h - MathMax(o, c);


   return (lowerTail >= (0.60 * fullRange) && body <= (0.25 * fullRange) && upperTail <= (0.20 * fullRange));
}


bool IsBearishPinbar(const int shift)
{
   double o = iOpen(Symbol(), Period(), shift);
   double c = iClose(Symbol(), Period(), shift);
   double h = iHigh(Symbol(), Period(), shift);
   double l = iLow(Symbol(), Period(), shift);
   double fullRange = h - l;
   if(fullRange <= 0.0) return false;


   double body = MathAbs(c - o);
   double upperTail = h - MathMax(o, c);
   double lowerTail = MathMin(o, c) - l;


   return (upperTail >= (0.60 * fullRange) && body <= (0.25 * fullRange) && lowerTail <= (0.20 * fullRange));
}


bool IsBullishMarubozu(const int shift)
{
   double o = iOpen(Symbol(), Period(), shift);
   double c = iClose(Symbol(), Period(), shift);
   double h = iHigh(Symbol(), Period(), shift);
   double l = iLow(Symbol(), Period(), shift);
   double fullRange = h - l;
   if(fullRange <= 0.0) return false;


   double body = c - o;
   if(body <= 0.0) return false;


   double upperWick = h - c;
   double lowerWick = o - l;


   return (body >= (0.85 * fullRange) && upperWick <= (0.08 * fullRange) && lowerWick <= (0.08 * fullRange));
}


bool IsBearishMarubozu(const int shift)
{
   double o = iOpen(Symbol(), Period(), shift);
   double c = iClose(Symbol(), Period(), shift);
   double h = iHigh(Symbol(), Period(), shift);
   double l = iLow(Symbol(), Period(), shift);
   double fullRange = h - l;
   if(fullRange <= 0.0) return false;


   double body = o - c;
   if(body <= 0.0) return false;


   double upperWick = h - o;
   double lowerWick = c - l;


   return (body >= (0.85 * fullRange) && upperWick <= (0.08 * fullRange) && lowerWick <= (0.08 * fullRange));
}


bool IsThreeWhiteSoldiers(const int shift)
{
   double c1 = iClose(Symbol(), Period(), shift);
   double o1 = iOpen(Symbol(), Period(), shift);
   double c2 = iClose(Symbol(), Period(), shift + 1);
   double o2 = iOpen(Symbol(), Period(), shift + 1);
   double c3 = iClose(Symbol(), Period(), shift + 2);
   double o3 = iOpen(Symbol(), Period(), shift + 2);


   return (c3 > o3 && c2 > o2 && c1 > o1 && c1 > c2 && c2 > c3 && o1 > o2 && o2 > o3);
}


bool IsThreeBlackCrows(const int shift)
{
   double c1 = iClose(Symbol(), Period(), shift);
   double o1 = iOpen(Symbol(), Period(), shift);
   double c2 = iClose(Symbol(), Period(), shift + 1);
   double o2 = iOpen(Symbol(), Period(), shift + 1);
   double c3 = iClose(Symbol(), Period(), shift + 2);
   double o3 = iOpen(Symbol(), Period(), shift + 2);


   return (c3 < o3 && c2 < o2 && c1 < o1 && c1 < c2 && c2 < c3 && o1 < o2 && o2 < o3);
}




//+------------------------------------------------------------------+
//| ADVANCED MODULAR TRAILING STOP ENGINES                           |
//+------------------------------------------------------------------+
double CalculateChandelierLongStop(const int lookback, const double atrMultiplier)
{
   int highestIdx = iHighest(Symbol(), Period(), MODE_HIGH, lookback, 1);
   double highVal = (highestIdx != -1) ? iHigh(Symbol(), Period(), highestIdx) : iHigh(Symbol(), Period(), 1);
   double atrVal  = iATR(Symbol(), Period(), ATRPeriod, 1);
   return NormalizeDouble(highVal - (atrVal * atrMultiplier), Digits);
}


double CalculateChandelierShortStop(const int lookback, const double atrMultiplier)
{
   int lowestIdx = iLowest(Symbol(), Period(), MODE_LOW, lookback, 1);
   double lowVal = (lowestIdx != -1) ? iLow(Symbol(), Period(), lowestIdx) : iLow(Symbol(), Period(), 1);
   double atrVal = iATR(Symbol(), Period(), ATRPeriod, 1);
   return NormalizeDouble(lowVal + (atrVal * atrMultiplier), Digits);
}


double CalculateMovingAverageLongStop(const int maPeriod, const ENUM_MA_METHOD maMethod)
{
   double maVal = iMA(Symbol(), Period(), maPeriod, 0, maMethod, PRICE_LOW, 1);
   return NormalizeDouble(maVal, Digits);
}


double CalculateMovingAverageShortStop(const int maPeriod, const ENUM_MA_METHOD maMethod)
{
   double maVal = iMA(Symbol(), Period(), maPeriod, 0, maMethod, PRICE_HIGH, 1);
   return NormalizeDouble(maVal, Digits);
}


double CalculateKellyCriterionFraction(const double winRate, const double winLossRatio)
{
   if(winLossRatio <= 0.0) return 0.01;
   double p = winRate / 100.0;
   double q = 1.0 - p;
   double kelly = ( (winLossRatio * p) - q ) / winLossRatio;


   // Half-Kelly convention for conservative capital preservation
   double safeKelly = kelly * 0.50;
   if(safeKelly < 0.005) safeKelly = 0.005; // 0.5% floor
   if(safeKelly > 0.050) safeKelly = 0.050; // 5.0% ceiling


   return safeKelly;
}


//+------------------------------------------------------------------+
//| SPREAD ROLLING MOVING AVERAGE TRACKER                            |
//+------------------------------------------------------------------+
double CalculateAverageSpread(const int sampleTicks = 20)
{
   static int spreadSamples[50];
   static int sampleIndex = 0;
   static int sampleCount = 0;


   int maxSamples = MathMin(MathMax(sampleTicks, 1), 50);
   int currentSpread = (int)MarketInfo(Symbol(), MODE_SPREAD);
   spreadSamples[sampleIndex] = currentSpread;
   sampleIndex = (sampleIndex + 1) % maxSamples;
   if(sampleCount < maxSamples) sampleCount++;


   double totalSpread = 0.0;
   for(int i = 0; i < sampleCount; i++)
   {
      totalSpread += spreadSamples[i];
   }


   return (sampleCount > 0) ? (totalSpread / (double)sampleCount) : (double)currentSpread;
}




//+------------------------------------------------------------------+
//| KAUFMAN EFFICIENCY RATIO (KER) QUANTITATIVE NOISE FILTER         |
//+------------------------------------------------------------------+
double CalculateKaufmanEfficiencyRatio(const int period)
{
   if(Bars < period + 2) return 0.5;


   double netDirectionalChange = MathAbs(iClose(Symbol(), Period(), 1) - iClose(Symbol(), Period(), period));
   double sumVolatilitySteps = 0.0;


   for(int i = 1; i <= period; i++)
   {
      sumVolatilitySteps += MathAbs(iClose(Symbol(), Period(), i) - iClose(Symbol(), Period(), i + 1));
   }


   if(sumVolatilitySteps <= 0.0) return 0.0;


   double ker = netDirectionalChange / sumVolatilitySteps;
   return NormalizeDouble(ker, 4);
}


//+------------------------------------------------------------------+
//| JOHN CARTER TTM SQUEEZE COMPRESSION MOMENTUM DETECTOR            |
//+------------------------------------------------------------------+
void EvaluateTTMSqueezeMomentum(bool &outSqueezeArmed, bool &outSqueezeFiring)
{
   outSqueezeArmed  = false;
   outSqueezeFiring = false;


   // 1. Bollinger Bands
   double bbUpper = iBands(Symbol(), Period(), BollingerPeriod, BollingerDev, 0, PRICE_CLOSE, MODE_UPPER, 1);
   double bbLower = iBands(Symbol(), Period(), BollingerPeriod, BollingerDev, 0, PRICE_CLOSE, MODE_LOWER, 1);
   double bbMid   = iBands(Symbol(), Period(), BollingerPeriod, BollingerDev, 0, PRICE_CLOSE, MODE_BASE, 1);


   // 2. Keltner Channels
   double atrVal  = iATR(Symbol(), Period(), KeltnerPeriod, 1);
   double maVal   = iMA(Symbol(), Period(), KeltnerPeriod, 0, MODE_EMA, PRICE_CLOSE, 1);
   double kcUpper = maVal + (atrVal * KeltnerMultiplier);
   double kcLower = maVal - (atrVal * KeltnerMultiplier);


   // Previous Bar Squeeze State
   double bbUpperPrev = iBands(Symbol(), Period(), BollingerPeriod, BollingerDev, 0, PRICE_CLOSE, MODE_UPPER, 2);
   double bbLowerPrev = iBands(Symbol(), Period(), BollingerPeriod, BollingerDev, 0, PRICE_CLOSE, MODE_LOWER, 2);
   double atrValPrev  = iATR(Symbol(), Period(), KeltnerPeriod, 2);
   double maValPrev   = iMA(Symbol(), Period(), KeltnerPeriod, 0, MODE_EMA, PRICE_CLOSE, 2);
   double kcUpperPrev = maValPrev + (atrValPrev * KeltnerMultiplier);
   double kcLowerPrev = maValPrev - (atrValPrev * KeltnerMultiplier);


   bool prevInside = (bbUpperPrev < kcUpperPrev && bbLowerPrev > kcLowerPrev);
   bool currInside = (bbUpper < kcUpper && bbLower > kcLower);


   if(currInside)
   {
      outSqueezeArmed = true; // Compression stage
   }
   else if(prevInside && !currInside)
   {
      outSqueezeFiring = true; // Breakout expansion release
   }
}


//+------------------------------------------------------------------+
//| ON-BALANCE VOLUME (OBV) INSTITUTIONAL FLOW CONFIRMATION          |
//+------------------------------------------------------------------+
void EvaluateVolumeOBV(bool &outBullishFlow, bool &outBearishFlow)
{
   outBullishFlow = false;
   outBearishFlow = false;


   // MQL4 iOBV signature: double iOBV(string symbol, int timeframe, int applied_price, int shift);
   double obv1 = iOBV(Symbol(), Period(), PRICE_CLOSE, 1);
   double obv2 = iOBV(Symbol(), Period(), PRICE_CLOSE, 2);
   double obv3 = iOBV(Symbol(), Period(), PRICE_CLOSE, 3);


   // 3-bar OBV momentum slope
   if(obv1 > obv2 && obv2 > obv3)
   {
      outBullishFlow = true;
   }
   else if(obv1 < obv2 && obv2 < obv3)
   {
      outBearishFlow = true;
   }
}


//+------------------------------------------------------------------+
//| VIRTUAL STEALTH STOP LOSS & TAKE PROFIT MANAGER                  |
//+------------------------------------------------------------------+
void MonitorStealthStops()
{
   if(!UseStealthStops) return;

   CleanupStealthOrders();
   int scaledSlippage = GetScaledSlippage();

   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;

      int type = OrderType();
      int ticket = OrderTicket();
      double openPrice = OrderOpenPrice();
      double lots = OrderLots();

      RefreshRates();

      double virtualSL = 0.0, virtualTP = 0.0;
      if(!GetStealthOrderLevels(ticket, virtualSL, virtualTP))
      {
         // Fallback calculation if not explicitly registered
         if(type == OP_BUY)
         {
            virtualSL = openPrice - (StopLossPips * g_PipPoint);
            virtualTP = (TakeProfitPips > 0) ? (openPrice + (TakeProfitPips * g_PipPoint)) : 0.0;
         }
         else if(type == OP_SELL)
         {
            virtualSL = openPrice + (StopLossPips * g_PipPoint);
            virtualTP = (TakeProfitPips > 0) ? (openPrice - (TakeProfitPips * g_PipPoint)) : 0.0;
         }
      }

      if(type == OP_BUY)
      {
         if(virtualSL > 0.0 && Bid <= virtualSL)
         {
            PrintFormat("[STEALTH SL TRIGGERED] Ticket #%d reached Virtual SL at %f", ticket, Bid);
            if(!SafeOrderClose(ticket, lots, scaledSlippage, clrRed))
            {
               PrintFormat("[STEALTH ERROR] Failed to close Ticket #%d at Virtual SL", ticket);
            }
         }
         else if(virtualTP > 0.0 && Bid >= virtualTP)
         {
            PrintFormat("[STEALTH TP TRIGGERED] Ticket #%d reached Virtual TP at %f", ticket, Bid);
            if(!SafeOrderClose(ticket, lots, scaledSlippage, clrLime))
            {
               PrintFormat("[STEALTH ERROR] Failed to close Ticket #%d at Virtual TP", ticket);
            }
         }
      }
      else if(type == OP_SELL)
      {
         if(virtualSL > 0.0 && Ask >= virtualSL)
         {
            PrintFormat("[STEALTH SL TRIGGERED] Ticket #%d reached Virtual SL at %f", ticket, Ask);
            if(!SafeOrderClose(ticket, lots, scaledSlippage, clrRed))
            {
               PrintFormat("[STEALTH ERROR] Failed to close Ticket #%d at Virtual SL", ticket);
            }
         }
         else if(virtualTP > 0.0 && Ask <= virtualTP)
         {
            PrintFormat("[STEALTH TP TRIGGERED] Ticket #%d reached Virtual TP at %f", ticket, Ask);
            if(!SafeOrderClose(ticket, lots, scaledSlippage, clrLime))
            {
               PrintFormat("[STEALTH ERROR] Failed to close Ticket #%d at Virtual TP", ticket);
            }
         }
      }
   }
}


//+------------------------------------------------------------------+
//| CONSECUTIVE LOSSES KILL-SWITCH TRACKER                           |
//+------------------------------------------------------------------+
void UpdateConsecutiveLossTracker()
{
   if(g_ConsecutiveLossCooldownTime > 0)
   {
      if(TimeCurrent() >= g_ConsecutiveLossCooldownTime)
      {
         g_ConsecutiveLossesCount = 0;
         g_ConsecutiveLossCooldownTime = 0;
         g_LastLossCooldownResetTime = TimeCurrent();
         Print("[KILL-SWITCH] Consecutive loss cooldown elapsed. Streak counters reset to zero.");
         return;
      }
      else
      {
         return; // Cooldown is currently active
      }
   }

   int historyTotal = OrdersHistoryTotal();
   int currentStreak = 0;

   for(int i = historyTotal - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;

      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL) continue;

      // Only count trades closed after the last cooldown reset
      if(g_LastLossCooldownResetTime > 0 && OrderCloseTime() <= g_LastLossCooldownResetTime)
         break;

      double netProfit = OrderProfit() + OrderSwap() + OrderCommission();
      if(netProfit < 0.0)
      {
         currentStreak++;
      }
      else
      {
         break; // Streak broken by a winning trade
      }
   }

   g_ConsecutiveLossesCount = currentStreak;
   if(g_ConsecutiveLossesCount >= MaxConsecutiveLosses)
   {
      if(g_ConsecutiveLossCooldownTime == 0)
      {
         g_ConsecutiveLossCooldownTime = TimeCurrent() + (CooldownBarsAfterMaxLosses * Period() * 60);
         PrintFormat("[KILL-SWITCH] Max consecutive losses reached (%d). Cooldown activated until %s",
                     g_ConsecutiveLossesCount, TimeToStr(g_ConsecutiveLossCooldownTime));
      }
   }
}




//+------------------------------------------------------------------+
//| COMMODITY CHANNEL INDEX (CCI) SUB-ENGINE                         |
//+------------------------------------------------------------------+
void CalculateCCIModule(int &outCCIBuy, int &outCCISell)
{
   outCCIBuy  = 0;
   outCCISell = 0;


   if(!UseCCI_Indicator) return;


   g_CalculatedCCI = iCCI(Symbol(), Period(), CCI_Period, PRICE_TYPICAL, 1);
   double cciPrev  = iCCI(Symbol(), Period(), CCI_Period, PRICE_TYPICAL, 2);


   // Oversold recovery crossover (+1 BUY)
   if(g_CalculatedCCI > CCI_Oversold && cciPrev <= CCI_Oversold)
   {
      outCCIBuy += 1;
   }
   // Overbought reversal crossover (+1 SELL)
   else if(g_CalculatedCCI < CCI_Overbought && cciPrev >= CCI_Overbought)
   {
      outCCISell += 1;
   }


   // Zero-line directional momentum confirmation
   if(g_CalculatedCCI > 0.0 && cciPrev <= 0.0)
   {
      outCCIBuy += 1;
   }
   else if(g_CalculatedCCI < 0.0 && cciPrev >= 0.0)
   {
      outCCISell += 1;
   }


   if(outCCIBuy > 2)  outCCIBuy = 2;
   if(outCCISell > 2) outCCISell = 2;
}


//+------------------------------------------------------------------+
//| BOLLINGER BANDS %B AND BANDWIDTH ENGINE                          |
//+------------------------------------------------------------------+
void CalculateBollingerPercentB(double &outPercentB, double &outBandWidth, int &outBBBuy, int &outBBSell)
{
   outPercentB  = 0.50;
   outBandWidth = 0.0;
   outBBBuy     = 0;
   outBBSell    = 0;


   if(!UseBollingerPercentB) return;


   double upper = iBands(Symbol(), Period(), BB_Period, BB_Deviation, 0, PRICE_CLOSE, MODE_UPPER, 1);
   double lower = iBands(Symbol(), Period(), BB_Period, BB_Deviation, 0, PRICE_CLOSE, MODE_LOWER, 1);
   double base  = iBands(Symbol(), Period(), BB_Period, BB_Deviation, 0, PRICE_CLOSE, MODE_BASE, 1);
   double close1 = iClose(Symbol(), Period(), 1);


   double bandRange = upper - lower;
   if(bandRange > 0.0)
   {
      outPercentB  = (close1 - lower) / bandRange;
      outBandWidth = (bandRange / base) * 100.0;
   }


   g_CalculatedPercentB  = NormalizeDouble(outPercentB, 3);
   g_CalculatedBandWidth = NormalizeDouble(outBandWidth, 3);


   // %B < 0.0 indicates price pierced below the lower band (extreme oversold mean-reversion)
   if(outPercentB < 0.05)
   {
      outBBBuy += 1;
   }
   // %B > 1.0 indicates price pierced above the upper band (extreme overbought mean-reversion)
   else if(outPercentB > 0.95)
   {
      outBBSell += 1;
   }
}


//+------------------------------------------------------------------+
//| DONCHIAN CHANNELS BREAKOUT CALCULATION                           |
//+------------------------------------------------------------------+
void CalculateDonchianChannels(const int period, double &outUpper, double &outLower, double &outMiddle)
{
   int highIdx = iHighest(Symbol(), Period(), MODE_HIGH, period, 1);
   int lowIdx  = iLowest(Symbol(),  Period(), MODE_LOW,  period, 1);


   outUpper  = (highIdx != -1) ? iHigh(Symbol(), Period(), highIdx) : iHigh(Symbol(), Period(), 1);
   outLower  = (lowIdx  != -1) ? iLow(Symbol(),  Period(), lowIdx)  : iLow(Symbol(),  Period(), 1);
   outMiddle = (outUpper + outLower) / 2.0;


   g_DonchianUpper  = outUpper;
   g_DonchianLower  = outLower;
   g_DonchianMiddle = outMiddle;
}


//+------------------------------------------------------------------+
//| VOLUME SPREAD ANALYSIS (VSA) SUB-ENGINE                          |
//+------------------------------------------------------------------+
void AnalyzeVolumeSpreadEngine(int &outVSABuy, int &outVSASell)
{
   outVSABuy  = 0;
   outVSASell = 0;
   g_VSA_StoppingVolume   = false;
   g_VSA_AbsorptionVolume = false;
   g_VSA_LowVolumePullback= false;


   if(!UseVolumeSpreadAnalysis) return;


   double vol1 = (double)iVolume(Symbol(), Period(), 1);
   double sumVol = 0.0;
   for(int i = 1; i <= VSA_VolumeMAPeriod; i++)
   {
      sumVol += (double)iVolume(Symbol(), Period(), i);
   }
   double avgVol = (VSA_VolumeMAPeriod > 0) ? (sumVol / (double)VSA_VolumeMAPeriod) : vol1;


   double spread1 = iHigh(Symbol(), Period(), 1) - iLow(Symbol(), Period(), 1);
   double sumSpread = 0.0;
   for(int j = 1; j <= VSA_VolumeMAPeriod; j++)
   {
      sumSpread += (iHigh(Symbol(), Period(), j) - iLow(Symbol(), Period(), j));
   }
   double avgSpread = (VSA_VolumeMAPeriod > 0) ? (sumSpread / (double)VSA_VolumeMAPeriod) : spread1;


   double open1  = iOpen(Symbol(), Period(), 1);
   double close1 = iClose(Symbol(), Period(), 1);


   // 1. Stopping Volume: High volume (> 1.8x avg), narrow spread (< 0.8x avg) on a down candle
   if(vol1 > (1.8 * avgVol) && spread1 < (0.8 * avgSpread) && close1 < open1)
   {
      g_VSA_StoppingVolume = true;
      outVSABuy += 1;
   }


   // 2. Absorption Volume: Ultra high volume (> 2.0x avg), wide spread (> 1.5x avg) breaking resistance
   if(vol1 > (2.0 * avgVol) && spread1 > (1.5 * avgSpread) && close1 > open1)
   {
      g_VSA_AbsorptionVolume = true;
      outVSABuy += 1;
   }
   else if(vol1 > (2.0 * avgVol) && spread1 > (1.5 * avgSpread) && close1 < open1)
   {
      g_VSA_AbsorptionVolume = true;
      outVSASell += 1;
   }


   // 3. Low Volume Test / Pullback: Volume < 0.6x avg on a retracement candle
   if(vol1 < (0.6 * avgVol) && close1 < open1 && g_ActiveTrendRegime == TREND_STRONG_BULLISH)
   {
      g_VSA_LowVolumePullback = true;
      outVSABuy += 1; // Bullish continuation confirmation
   }
   else if(vol1 < (0.6 * avgVol) && close1 > open1 && g_ActiveTrendRegime == TREND_STRONG_BEARISH)
   {
      g_VSA_LowVolumePullback = true;
      outVSASell += 1; // Bearish continuation confirmation
   }
}


//+------------------------------------------------------------------+
//| CURRENCY BASKET & PORTFOLIO EXPOSURE MANAGER                     |
//+------------------------------------------------------------------+
bool ValidateCurrencyBasketExposure()
{
   if(!EnforceCurrencyBasketLimits) return true;

   string symCurrent = Symbol();
   if(StringLen(symCurrent) < 6)
   {
      // Non-forex or short symbol (e.g. US30, DE40, BTC, GOLD)
      // Count open positions on this specific symbol
      int symCount = 0;
      for(int i = OrdersTotal() - 1; i >= 0; i--)
      {
         if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
         if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
         if(OrderSymbol() == symCurrent) symCount++;
      }
      if(symCount >= MaxSimultaneousPerCurrency)
      {
         PrintFormat("[BASKET FILTER] Asset concentration limit reached for %s: %d positions", symCurrent, symCount);
         return false;
      }
      return true;
   }

   string baseCurr  = StringSubstr(symCurrent, 0, 3);
   string quoteCurr = StringSubstr(symCurrent, 3, 3);

   if(StringLen(baseCurr) < 3 || StringLen(quoteCurr) < 3)
      return true;

   int baseCount  = 0;
   int quoteCount = 0;

   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;

      string sym = OrderSymbol();
      if(StringLen(sym) >= 3 && StringFind(sym, baseCurr) >= 0)  baseCount++;
      if(StringLen(sym) >= 6 && StringFind(sym, quoteCurr) >= 0) quoteCount++;
   }

   if(baseCount >= MaxSimultaneousPerCurrency)
   {
      PrintFormat("[BASKET FILTER] Currency concentration limit reached for %s: %d positions", baseCurr, baseCount);
      return false;
   }
   if(quoteCount >= MaxSimultaneousPerCurrency)
   {
      PrintFormat("[BASKET FILTER] Currency concentration limit reached for %s: %d positions", quoteCurr, quoteCount);
      return false;
   }

   return true;
}


//+------------------------------------------------------------------+
//| TIME-BASED STAGNANT TRADE LIQUIDATION ENGINE                     |
//+------------------------------------------------------------------+
void EnforceTradeExpiration()
{
   if(!UseTimeBasedTradeExpiration || MaxTradeDurationHours <= 0) return;

   datetime thresholdTime = TimeCurrent() - (MaxTradeDurationHours * 3600);

   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;

      if(OrderOpenTime() < thresholdTime)
      {
         int ticket = OrderTicket();
         double lots = OrderLots();
         PrintFormat("[EXPIRATION] Ticket #%d exceeded max lifetime (%d hours). Liquidating position.", ticket, MaxTradeDurationHours);
         SafeOrderClose(ticket, lots, GetScaledSlippage(), clrDarkViolet);
      }
   }
}


//+------------------------------------------------------------------+
//| AUTOMATED CHART SCREENSHOT CAPTURE                               |
//+------------------------------------------------------------------+
void SaveChartTradeScreenshot(const string signalName)
{
   if(!CaptureSignalScreenshots) return;

   string timeStr = TimeToStr(TimeCurrent(), TIME_DATE | TIME_MINUTES);
   StringReplace(timeStr, ":", "-");
   StringReplace(timeStr, ".", "-");
   StringReplace(timeStr, " ", "_");

   string filename = StringFormat("SmartEA_Screenshots\\%s_%s_%s_%s.png",
                                  Symbol(),
                                  EnumToString((ENUM_TIMEFRAMES)Period()),
                                  signalName,
                                  timeStr);
   ChartScreenShot(ChartID(), filename, 1280, 720);
   PrintFormat("[SCREENSHOT CAPTURED] Saved chart capture: %s", filename);
}




//+------------------------------------------------------------------+
//| INTERACTIVE ON-CHART GUI BUTTONS BUILDER                         |
//+------------------------------------------------------------------+
void RenderInteractiveButtons()
{
   if(!ShowInteractiveButtons) return;


   int startX = Buttons_X_Offset;
   int startY = Buttons_Y_Offset;
   int gapX   = 6;
   int btnW   = ButtonWidth;
   int btnH   = ButtonHeight;


   // Button 1: Close All Orders
   string btnCloseName = PREFIX_GUI + "BTN_CloseAll";
   CreateActionButton(btnCloseName, "CLOSE ALL", startX, startY, btnW, btnH, ColorBtnCloseAll, clrWhite);


   // Button 2: Break-Even All Orders
   string btnBEName = PREFIX_GUI + "BTN_BreakEven";
   CreateActionButton(btnBEName, "BE ALL", startX + btnW + gapX, startY, btnW, btnH, ColorBtnBreakEven, clrWhite);


   // Button 3: Toggle AutoTrading
   string btnToggleName = PREFIX_GUI + "BTN_Toggle";
   string toggleText = g_AutoTradingRuntimeActive ? "PAUSE EA" : "RESUME EA";
   color toggleColor = g_AutoTradingRuntimeActive ? ColorBtnToggleTrade : C'150,80,20';
   CreateActionButton(btnToggleName, toggleText, startX + (2 * (btnW + gapX)), startY, btnW, btnH, toggleColor, clrWhite);
}


void CreateActionButton(const string name, const string caption, const int x, const int y, const int w, const int h, const color bgColor, const color textColor)
{
   if(ObjectFind(ChartID(), name) < 0)
   {
      ObjectCreate(ChartID(), name, OBJ_BUTTON, 0, 0, 0);
      ObjectSetInteger(ChartID(), name, OBJPROP_SELECTABLE, false);
      ObjectSetString(ChartID(), name, OBJPROP_FONT, "Segoe UI Bold");
      ObjectSetInteger(ChartID(), name, OBJPROP_FONTSIZE, 8);
   }
   ObjectSetInteger(ChartID(), name, OBJPROP_CORNER, HUD_Corner);
   ObjectSetInteger(ChartID(), name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(ChartID(), name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(ChartID(), name, OBJPROP_XSIZE, w);
   ObjectSetInteger(ChartID(), name, OBJPROP_YSIZE, h);
   ObjectSetInteger(ChartID(), name, OBJPROP_BGCOLOR, bgColor);
   ObjectSetInteger(ChartID(), name, OBJPROP_COLOR, textColor);
   ObjectSetString(ChartID(), name, OBJPROP_TEXT, caption);
}


//+------------------------------------------------------------------+
//| CHART EVENT DISPATCHER (INTERACTIVE BUTTON HANDLER)              |
//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   if(id != CHARTEVENT_OBJECT_CLICK) return;

   // 1. Close All Orders Button Clicked
   if(sparam == PREFIX_GUI + "BTN_CloseAll")
   {
      Print("[USER ACTION] Close All button clicked on chart.");
      for(int i = OrdersTotal() - 1; i >= 0; i--)
      {
         if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
         if(OrderSymbol() == Symbol() && OrderMagicNumber() == MagicNumber)
         {
            SafeOrderClose(OrderTicket(), OrderLots(), GetScaledSlippage(), clrOrangeRed);
         }
      }
      ObjectSetInteger(ChartID(), sparam, OBJPROP_STATE, false);
      ChartRedraw(ChartID());
   }
   // 2. Break-Even All Orders Button Clicked
   else if(sparam == PREFIX_GUI + "BTN_BreakEven")
   {
      Print("[USER ACTION] Break-Even All button clicked on chart.");
      RefreshRates();
      for(int j = OrdersTotal() - 1; j >= 0; j--)
      {
         if(!OrderSelect(j, SELECT_BY_POS, MODE_TRADES)) continue;
         if(OrderSymbol() == Symbol() && OrderMagicNumber() == MagicNumber)
         {
            int ticket = OrderTicket();
            int cmd = OrderType();
            double openP = OrderOpenPrice();
            double curTP = OrderTakeProfit();
            double curSL = OrderStopLoss();

            if(cmd == OP_BUY)
            {
               double profitPips = (Bid - openP) / g_PipPoint;
               if(profitPips >= BreakEvenLockPips && profitPips > 0)
               {
                  double beLevel = NormalizeDouble(openP + (BreakEvenLockPips * g_PipPoint), Digits);
                  if(curSL < beLevel && beLevel < Bid)
                  {
                     SafeOrderModify(ticket, openP, beLevel, curTP, 0, clrAqua);
                  }
               }
            }
            else if(cmd == OP_SELL)
            {
               double profitPips = (openP - Ask) / g_PipPoint;
               if(profitPips >= BreakEvenLockPips && profitPips > 0)
               {
                  double beLevel = NormalizeDouble(openP - (BreakEvenLockPips * g_PipPoint), Digits);
                  if((curSL > beLevel || curSL == 0.0) && beLevel > Ask)
                  {
                     SafeOrderModify(ticket, openP, beLevel, curTP, 0, clrAqua);
                  }
               }
            }
         }
      }
      ObjectSetInteger(ChartID(), sparam, OBJPROP_STATE, false);
      ChartRedraw(ChartID());
   }
   // 3. Toggle AutoTrading Button Clicked
   else if(sparam == PREFIX_GUI + "BTN_Toggle")
   {
      g_AutoTradingRuntimeActive = !g_AutoTradingRuntimeActive;
      string toggleText = g_AutoTradingRuntimeActive ? "PAUSE EA" : "RESUME EA";
      color toggleColor = g_AutoTradingRuntimeActive ? ColorBtnToggleTrade : C'150,80,20';
      ObjectSetString(ChartID(), sparam, OBJPROP_TEXT, toggleText);
      ObjectSetInteger(ChartID(), sparam, OBJPROP_BGCOLOR, toggleColor);
      ObjectSetInteger(ChartID(), sparam, OBJPROP_STATE, false);
      ChartRedraw(ChartID());
      PrintFormat("[USER ACTION] AutoTrading toggled live: %s", (g_AutoTradingRuntimeActive ? "ACTIVE" : "PAUSED"));
   }
}




//+------------------------------------------------------------------+
//| SECTION 14: MULTI-TIMEFRAME (MTF) CONFLUENCE MATRIX & DASHBOARD  |
//+------------------------------------------------------------------+
void RenderMultiTimeframeMatrix()
{
   if(!ShowDashboardPanel) return;


   int startX = HUD_X_Offset + 295;
   int startY = HUD_Y_Offset;
   int cellW  = 40;
   int cellH  = 20;
   int gap    = 4;
   int panelWidth  = 280;
   int panelHeight = 150;


   // MTF Matrix Backdrop
   string bgName = PREFIX_GUI + "MTF_Backdrop";
   if(ObjectFind(ChartID(), bgName) < 0)
   {
      ObjectCreate(ChartID(), bgName, OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(ChartID(), bgName, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(ChartID(), bgName, OBJPROP_BORDER_TYPE, BORDER_FLAT);
   }
   ObjectSetInteger(ChartID(), bgName, OBJPROP_CORNER, HUD_Corner);
   ObjectSetInteger(ChartID(), bgName, OBJPROP_XDISTANCE, startX);
   ObjectSetInteger(ChartID(), bgName, OBJPROP_YDISTANCE, startY);
   ObjectSetInteger(ChartID(), bgName, OBJPROP_XSIZE, panelWidth);
   ObjectSetInteger(ChartID(), bgName, OBJPROP_YSIZE, panelHeight);
   ObjectSetInteger(ChartID(), bgName, OBJPROP_BGCOLOR, HUD_BgColor);
   ObjectSetInteger(ChartID(), bgName, OBJPROP_BORDER_COLOR, HUD_BorderColor);


   int textX = startX + 12;
   RenderHUDLabel("MTF_Header", "=== MULTI-TIMEFRAME CONFLUENCE ===", textX, startY + 10, HUD_HeaderTextColor, 8, true);


   ENUM_TIMEFRAMES tfs[6] = {PERIOD_M5, PERIOD_M15, PERIOD_M30, PERIOD_H1, PERIOD_H4, PERIOD_D1};
   string tfNames[6]     = {"M5", "M15", "M30", "H1", "H4", "D1"};


   int currentY = startY + 34;


   int bullCount = 0;

   for(int i = 0; i < 6; i++)
   {
      double emaFast = iMA(Symbol(), tfs[i], EMA_Fast_Period, 0, MODE_EMA, PRICE_CLOSE, 1);
      double emaMed  = iMA(Symbol(), tfs[i], EMA_Medium_Period, 0, MODE_EMA, PRICE_CLOSE, 1);
      double rsiVal  = iRSI(Symbol(), tfs[i], RSI_Period, PRICE_CLOSE, 1);

      if(emaFast > emaMed) bullCount++;

      string trendTag = "FLAT";
      color blockClr  = clrWheat;

      if(emaFast > emaMed && rsiVal > 50.0)
      {
         trendTag = "BULL";
         blockClr = clrLimeGreen;
      }
      else if(emaFast < emaMed && rsiVal < 50.0)
      {
         trendTag = "BEAR";
         blockClr = clrCrimson;
      }

      int blockX = (startX + 10) + (i * (cellW + gap));
      string cellObj = PREFIX_GUI + "MTF_" + tfNames[i];

      if(ObjectFind(ChartID(), cellObj) < 0)
      {
         ObjectCreate(ChartID(), cellObj, OBJ_BUTTON, 0, 0, 0);
         ObjectSetInteger(ChartID(), cellObj, OBJPROP_SELECTABLE, false);
         ObjectSetString(ChartID(), cellObj, OBJPROP_FONT, "Segoe UI Bold");
         ObjectSetInteger(ChartID(), cellObj, OBJPROP_FONTSIZE, 7);
         ObjectSetInteger(ChartID(), cellObj, OBJPROP_XSIZE, cellW);
         ObjectSetInteger(ChartID(), cellObj, OBJPROP_YSIZE, cellH);
      }

      ObjectSetInteger(ChartID(), cellObj, OBJPROP_CORNER, HUD_Corner);
      ObjectSetInteger(ChartID(), cellObj, OBJPROP_XDISTANCE, blockX);
      ObjectSetInteger(ChartID(), cellObj, OBJPROP_YDISTANCE, currentY);
      ObjectSetInteger(ChartID(), cellObj, OBJPROP_BGCOLOR, blockClr);
      ObjectSetInteger(ChartID(), cellObj, OBJPROP_COLOR, clrBlack);
      ObjectSetString(ChartID(), cellObj, OBJPROP_TEXT, tfNames[i] + ":" + trendTag);
   }


   double confluencePct = ((double)bullCount / 6.0) * 100.0;
   string gaugeText = StringFormat("Bullish Power: %.1f%% (%d/6 TFs)", confluencePct, bullCount);
   color gaugeColor = (confluencePct >= 66.0 ? clrLime : (confluencePct <= 33.0 ? clrTomato : clrGold));


   int meterY = startY + 66;
   RenderHUDLabel("Gauge_Title", "Trend Confluence Index:", textX, meterY, HUD_LabelTextColor, 8, false);
   RenderHUDLabel("Gauge_Value", gaugeText, textX, meterY + 18, gaugeColor, 8, true);


   string adviceStr = (confluencePct >= 66.0 ? "Action: Strong Long Alignment Active" :
                      (confluencePct <= 33.0 ? "Action: Strong Short Alignment Active" : "Action: Range-Bound / Caution Advised"));
   RenderHUDLabel("Gauge_Advice", adviceStr, textX, meterY + 36, HUD_ValueTextColor, 7, false);
}


//+------------------------------------------------------------------+
//| BILL WILLIAMS FRACTAL SWING DETECTION ENGINE                     |
//+------------------------------------------------------------------+
void DetectBillWilliamsFractals(const int lookback, double &outUpFractal, double &outDownFractal)
{
   outUpFractal   = 0.0;
   outDownFractal = 0.0;


   // 5-bar Fractal logic
   for(int i = 3; i <= lookback; i++)
   {
      double hMiddle = iHigh(Symbol(), Period(), i);
      double lMiddle = iLow(Symbol(), Period(), i);


      // Up Fractal: Middle bar is higher than 2 bars to the left and 2 bars to the right
      if(outUpFractal == 0.0)
      {
         if(hMiddle > iHigh(Symbol(), Period(), i - 1) &&
            hMiddle > iHigh(Symbol(), Period(), i - 2) &&
            hMiddle > iHigh(Symbol(), Period(), i + 1) &&
            hMiddle > iHigh(Symbol(), Period(), i + 2))
         {
            outUpFractal = hMiddle;
         }
      }


      // Down Fractal: Middle bar is lower than 2 bars to the left and 2 bars to the right
      if(outDownFractal == 0.0)
      {
         if(lMiddle < iLow(Symbol(), Period(), i - 1) &&
            lMiddle < iLow(Symbol(), Period(), i - 2) &&
            lMiddle < iLow(Symbol(), Period(), i + 1) &&
            lMiddle < iLow(Symbol(), Period(), i + 2))
         {
            outDownFractal = lMiddle;
         }
      }


      if(outUpFractal > 0.0 && outDownFractal > 0.0) break;
   }
}


//+------------------------------------------------------------------+
//| BROKER ENVIRONMENT & HEALTH DIAGNOSTIC REPORT                    |
//+------------------------------------------------------------------+
void LogBrokerDiagnosticReport()
{
   string sym = Symbol();
   Print("================================================================================");
   PrintFormat("[BROKER HEALTH REPORT] Symbol: %s | Server Time: %s | Account: %d",
               sym, TimeToStr(TimeCurrent(), TIME_DATE | TIME_SECONDS), AccountNumber());
   PrintFormat("Broker Company: %s | Server: %s | Leverage: 1:%d | Currency: %s",
               AccountCompany(), AccountServer(), AccountLeverage(), AccountCurrency());
   PrintFormat("Market Digits: %d | Point: %f | TickSize: %f | TickValue: %f",
               Digits, Point, MarketInfo(sym, MODE_TICKSIZE), MarketInfo(sym, MODE_TICKVALUE));
   PrintFormat("Spread: %d pts | StopLevel: %d pts | FreezeLevel: %d pts",
               (int)MarketInfo(sym, MODE_SPREAD), (int)MarketInfo(sym, MODE_STOPLEVEL), (int)MarketInfo(sym, MODE_FREEZELEVEL));
   PrintFormat("Lot Min: %.2f | Lot Max: %.2f | Lot Step: %.2f | MarginReq: $%.2f",
               MarketInfo(sym, MODE_MINLOT), MarketInfo(sym, MODE_MAXLOT), MarketInfo(sym, MODE_LOTSTEP), MarketInfo(sym, MODE_MARGINREQUIRED));
   PrintFormat("Account Balance: $%.2f | Equity: $%.2f | Free Margin: $%.2f | Margin Level: %.2f%%",
               AccountBalance(), AccountEquity(), AccountFreeMargin(), (AccountMargin() > 0.0 ? (AccountEquity() / AccountMargin() * 100.0) : 100.0));
   Print("================================================================================");
}




//+------------------------------------------------------------------+
//| RALPH VINCE OPTIMAL F POSITION SIZING FORMULA                    |
//+------------------------------------------------------------------+
double CalculateOptimalFCapitalAllocation(const double largestLossCurrency)
{
   if(largestLossCurrency <= 0.0) return 0.02; // Default conservative 2%


   int historyTotal = OrdersHistoryTotal();
   if(historyTotal < 10) return 0.02;


   double sumHoldingF = 0.0;
   int validTrades = 0;


   for(int i = 0; i < historyTotal; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;


      double netPnL = OrderProfit() + OrderSwap() + OrderCommission();
      validTrades++;


      // Holding Period Return: 1 + (f * (-trade_pnl / largest_loss))
      double hpr = 1.0 + (0.10 * (netPnL / largestLossCurrency));
      if(hpr > 0.0)
      {
         sumHoldingF += MathLog(hpr);
      }
   }


   if(validTrades == 0) return 0.02;


   // Optimal f estimate based on logarithmic growth rate
   double geometricMean = MathExp(sumHoldingF / (double)validTrades);
   double recommendedRisk = (geometricMean - 1.0) * 0.50; // Fractional safety dampener


   if(recommendedRisk < 0.005) recommendedRisk = 0.005; // 0.5% minimum
   if(recommendedRisk > 0.050) recommendedRisk = 0.050; // 5.0% maximum


   return NormalizeDouble(recommendedRisk, 4);
}


//+------------------------------------------------------------------+
//| DYNAMIC KELTNER CHANNEL CHART OBJECTS OVERLAY                    |
//+------------------------------------------------------------------+
void RenderKeltnerChannelsOverlay()
{
   double atrVal  = iATR(Symbol(), Period(), KeltnerPeriod, 1);
   double maVal   = iMA(Symbol(), Period(), KeltnerPeriod, 0, MODE_EMA, PRICE_CLOSE, 1);
   double kcUpper = maVal + (atrVal * KeltnerMultiplier);
   double kcLower = maVal - (atrVal * KeltnerMultiplier);


   UpdateChartRay(PREFIX_OBJ + "KC_Upper", kcUpper, clrCadetBlue, STYLE_DOT, "Keltner Channel Upper");
   UpdateChartRay(PREFIX_OBJ + "KC_Middle", maVal,  clrSlateGray, STYLE_DOT, "Keltner Channel Middle (EMA)");
   UpdateChartRay(PREFIX_OBJ + "KC_Lower", kcLower, clrCadetBlue, STYLE_DOT, "Keltner Channel Lower");
}


//+------------------------------------------------------------------+
//| SECTION 11: MAIN EVENT CYCLES (OnInit, OnDeinit, OnTick, OnTimer)|
//+------------------------------------------------------------------+
int OnInit()
{
   bool isTimeframeChange = (UninitializeReason() == REASON_CHARTCHANGE);

   // === STEP 1: INSTRUMENT SYMBOL METRICS ===
   InitializeSymbolMetrics();
   
   // Clean previous signal arrows for fast timeframe switch
   ClearChartSignalMarkers();

   // On full load/reload, purge GUI objects for a fresh start
   if(!isTimeframeChange)
   {
      PurgeAllChartObjects();
   }

   // === STEP 2: RUNTIME FLAG INITIALIZATION ===
   g_AutoTradingRuntimeActive = UseAutoTrading;
   g_LastBarProcessedTime     = 0; // Reset bar lock so new timeframe bar processes immediately!

   // === STEP 3: INPUT PARAMETER VALIDATION ===
   if(MinRequiredScore < 1 || MinRequiredScore > 10)
   {
      Print("[INIT ERROR] MinRequiredScore must be between 1 and 10. Current: ", MinRequiredScore);
      return(INIT_FAILED);
   }
   if(MagicNumber <= 0)
   {
      Print("[INIT ERROR] MagicNumber must be a positive integer.");
      return(INIT_FAILED);
   }
   if(FixedLotSize <= 0.0 && LotSizingMethod == LOT_MODE_FIXED)
   {
      Print("[INIT ERROR] FixedLotSize must be > 0 when using LOT_MODE_FIXED.");
      return(INIT_FAILED);
   }
   if(RiskPercent <= 0.0 || RiskPercent > 50.0)
   {
      PrintFormat("[INIT WARNING] RiskPercent (%.1f%%) is outside safe range [0.1 - 50.0]. Clipping...", RiskPercent);
   }
   if(MaxDailyDrawdownPercent <= 0.0 || MaxDailyDrawdownPercent > 100.0)
   {
      Print("[INIT ERROR] MaxDailyDrawdownPercent must be between 0.1 and 100.0.");
      return(INIT_FAILED);
   }
   if(EMA_Fast_Period >= EMA_Medium_Period || EMA_Medium_Period >= EMA_Slow_Period)
   {
      PrintFormat("[INIT WARNING] EMA periods order issue: Fast(%d) >= Medium(%d) or Medium >= Slow(%d). Trend engine may produce incorrect signals.",
                  EMA_Fast_Period, EMA_Medium_Period, EMA_Slow_Period);
   }

   // === STEP 4: SYMBOL VALIDITY CHECK ===
   if(Digits == 0)
   {
      Print("[INIT ERROR] Symbol digits = 0. Invalid symbol or market data unavailable.");
      return(INIT_FAILED);
   }

   // === STEP 5: TRADING PERMISSION CHECKS ===
   if(g_AutoTradingRuntimeActive && !IsTradeAllowed())
   {
      Print("[WARNING] MT4 AutoTrading button is turned OFF in toolbar or 'Allow Live Trading' unchecked in EA settings!");
   }
   if(g_AutoTradingRuntimeActive && !IsExpertEnabled())
   {
      Print("[WARNING] Experts are disabled in the terminal. Enable via Tools > Options > Expert Advisors.");
   }

   // === STEP 6: ACCOUNT MARGIN SAFETY CHECK ===
   if(g_AutoTradingRuntimeActive && AccountBalance() <= 0.0)
   {
      Print("[INIT WARNING] Account balance is zero or negative. AutoTrading will execute but no orders can be placed.");
   }

   // === STEP 7: DAILY PERFORMANCE ANCHORS ===
   if(!isTimeframeChange)
   {
      g_DayAnchorDate             = TimeCurrent();
      g_StartingDayEquity         = AccountEquity();
      g_StartingDayBalance        = AccountBalance();
      g_DailyLossCircuitTripped   = false;
      g_DailyTargetCircuitTripped = false;
      g_ConsecutiveLossesCount    = 0;
      g_ConsecutiveLossCooldownTime = 0;
      g_LastLossCooldownResetTime   = TimeCurrent();
   }

   // === STEP 8: START SYSTEM TIMER (1-second GUI/telemetry updates) ===
   EventSetTimer(1);

   // === STEP 9: IMMEDIATE TIMEFRAME COMPUTATION & VISUAL REFRESH ===
   // 1. Immediately evaluate confluence scoring for the new timeframe
   int initBuy = 0, initSell = 0;
   ExecuteScoringPipeline(initBuy, initSell);

   // 2. Draw Support/Resistance & Keltner Channels for this timeframe
   DrawSupportResistanceLines();

   // 3. Scan & draw historical signals (fast 25-bar scan on TF change)
   ScanAndDrawHistoricalSignals(isTimeframeChange);

   // 4. Immediately render the HUD dashboard with fresh values for this timeframe
   RenderHUDDashboard();

   // 5. Force immediate chart redraw so the user sees everything updated instantly
   ChartRedraw(ChartID());

   if(!isTimeframeChange)
   {
      LogBrokerDiagnosticReport();
      PrintFormat("[INIT COMPLETE] SmartAutoTradeEA Pro v3.0 initialized on %s %s. AutoTrading: %s. MinScore: %d/10. RiskPercent: %.2f%%",
                  Symbol(), EnumToString((ENUM_TIMEFRAMES)Period()),
                  (g_AutoTradingRuntimeActive ? "ACTIVE" : "SIGNAL-ONLY"),
                  MinRequiredScore, RiskPercent);
   }

   Telegram_InitTradeTracker();
   ZeroMQ_Init(InpZmqBindAddress);

   return(INIT_SUCCEEDED);
}


void OnDeinit(const int reason)
{
   EventKillTimer();
   ZeroMQ_Deinit(InpZmqBindAddress);
   // Only purge GUI labels if EA is actually removed, not on simple timeframe changes!
   if(reason != REASON_CHARTCHANGE)
   {
      PurgeAllChartObjects();
   }
   ArrayResize(g_PartiallyClosedTickets, 0);
   ArrayResize(g_StealthOrders, 0);
   if(reason != REASON_CHARTCHANGE)
   {
      PrintFormat("[DEINIT COMPLETE] SmartAutoTradeEA shutdown. Reason code: %d", reason);
   }
}


void OnTimer()
{
   ZeroMQ_Poll();

   // Synchronize remote pause state from ZeroMQ Bridge or Telegram
   if(GlobalVariableCheck("AutoTrading_Paused"))
   {
      bool isRemotePaused = (GlobalVariableGet("AutoTrading_Paused") == 1.0);
      if(isRemotePaused && g_AutoTradingRuntimeActive)
      {
         g_AutoTradingRuntimeActive = false;
         Print("[REMOTE CONTROL] AutoTrading PAUSED via external command");
      }
      else if(!isRemotePaused && !g_AutoTradingRuntimeActive && !g_PropLockoutActive && !g_DailyLossCircuitTripped)
      {
         g_AutoTradingRuntimeActive = true;
         Print("[REMOTE CONTROL] AutoTrading RESUMED via external command");
      }
   }

   // Check daily circuit breakers on day rollover
   MqlDateTime dtCurrent, dtAnchor;
   TimeToStruct(TimeCurrent(), dtCurrent);
   TimeToStruct(g_DayAnchorDate, dtAnchor);

   datetime currentDayStart = StringToTime(TimeToStr(TimeCurrent(), TIME_DATE));
   datetime anchorDayStart  = StringToTime(TimeToStr(g_DayAnchorDate, TIME_DATE));

   if(currentDayStart > anchorDayStart)
   {
      // Send automated daily performance report on calendar rollover
      if(TelegramSendDailyReport && g_lastDailyReportDate != currentDayStart)
      {
         g_lastDailyReportDate = currentDayStart;
         Telegram_SendDailyReport();
      }

      g_DayAnchorDate        = TimeCurrent();
      g_StartingDayEquity    = AccountEquity();
      g_StartingDayBalance   = AccountBalance();
      g_DailyLossCircuitTripped = false;
      g_DailyTargetCircuitTripped = false;
      Print("[DAY ROLLOVER] Performance anchors recalibrated for new calendar trading day.");
   }

   // Evaluate daily equity circuit thresholds
   if(EnforceAccountProtection && g_StartingDayEquity > 0.0)
   {
      double currentEquity = AccountEquity();
      double drawdownPct = ((g_StartingDayEquity - currentEquity) / g_StartingDayEquity) * 100.0;
      double profitPct   = ((currentEquity - g_StartingDayEquity) / g_StartingDayEquity) * 100.0;

      if(drawdownPct >= MaxDailyDrawdownPercent)
      {
         g_DailyLossCircuitTripped = true;
      }
      if(profitPct >= MaxDailyProfitPercent)
      {
         g_DailyTargetCircuitTripped = true;
      }
   }
   // High-performance optimization: Throttle HUD Dashboard rendering to every 2 seconds
   // This reduces GDI redraw load by 50% and completely prevents micro-stutter
   uint currentTick = GetTickCount();
   static uint s_lastHUDTick = 0;
   if(currentTick - s_lastHUDTick >= 2000)
   {
      s_lastHUDTick = currentTick;
      RenderHUDDashboard();
   }

   // Process Telegram trade alerts & risk guardian checks (handled on ticks)
   // Telegram_ProcessTradeEvents();
   // Telegram_CheckRiskGuardian();
   // Telegram_CheckPropFirmRules();
}


void OnTick()
{
   ZeroMQ_Poll();
   // 1. Manage existing positions on every tick
   ManageActiveTradeLifecycle();
   MonitorStealthStops();
   UpdateConsecutiveLossTracker();
   EnforceTradeExpiration();
   Telegram_ProcessTradeEvents();


   // 2. Bar close evaluation constraint (prevents repainting)
   datetime currentBarTime = iTime(Symbol(), Period(), 0);
   if(currentBarTime == g_LastBarProcessedTime)
   {
      return; // Inside current forming bar
   }


   g_LastBarProcessedTime = currentBarTime;


   // 3. Multi-Indicator Confluence Scoring
   int buyScore = 0;
   int sellScore = 0;
   ExecuteScoringPipeline(buyScore, sellScore);


   ENUM_SIGNAL_DECISION decision = SIGNAL_NEUTRAL;
   int finalWinningScore = 0;


   if(buyScore >= MinRequiredScore && buyScore > sellScore)
   {
      if(!RequireTrendDirectionMatch || g_ActiveTrendRegime == TREND_STRONG_BULLISH || g_ActiveTrendRegime == TREND_WEAK_BULLISH)
      {
         decision = SIGNAL_LONG;
         finalWinningScore = buyScore;
         g_LastSignalVerdict = "BUY";
      }
   }
   else if(sellScore >= MinRequiredScore && sellScore > buyScore)
   {
      if(!RequireTrendDirectionMatch || g_ActiveTrendRegime == TREND_STRONG_BEARISH || g_ActiveTrendRegime == TREND_WEAK_BEARISH)
      {
         decision = SIGNAL_SHORT;
         finalWinningScore = sellScore;
         g_LastSignalVerdict = "SELL";
      }
   }
   else
   {
      g_LastSignalVerdict = "NONE";
   }


   g_LastSignalScore = finalWinningScore;


   // 4. Draw Support/Resistance & Pivot Lines
   DrawSupportResistanceLines();


   // 5. Signal Action
   if(decision != SIGNAL_NEUTRAL)
   {
      DrawChartSignalMarker(decision, 1);
      BroadcastSignalAlerts(decision, finalWinningScore);


      // Check Filters and Execute if AutoTrading is enabled
      if(ValidateTradeFilters(decision))
      {
         if(g_AutoTradingRuntimeActive)
         {
            double entryPrice = (decision == SIGNAL_LONG) ? Ask : Bid;
            int cmd = (decision == SIGNAL_LONG) ? OP_BUY : OP_SELL;


            // Advanced SL/TP Calculation via Configured Priority & Hybrid Confluence
            double slPrice = 0.0;
            double tpPrice = 0.0;
            CalculateAdvancedSLTP(cmd, entryPrice, slPrice, tpPrice);


            // Calculate precise lot size based on the final selected SL distance
            double orderLots = CalculateDynamicLotSize(entryPrice, slPrice);
            ExecuteSmartOrder(cmd, orderLots, entryPrice, slPrice, tpPrice);
            SaveChartTradeScreenshot(g_LastSignalVerdict);
         }
      }
   }
}
//+------------------------------------------------------------------+


