//+------------------------------------------------------------------+
//|                                         AutoTradeFlagCheck.mqh   |
//|                  Institutional External EA Remote Pause Enforcer |
//|                                                                  |
//| Include this file in any external MT4 EA:                        |
//|    #include <AutoTradeFlagCheck.mqh>                             |
//|                                                                  |
//| In your EA's OnTick() function, check before placing trades:     |
//|    if(IsAutoTradePausedByTelegram()) return;                     |
//+------------------------------------------------------------------+
#property copyright "Antigravity Institutional Bridge"
#property strict

//+------------------------------------------------------------------+
//| Check if Telegram Bot has paused automated trading               |
//| Returns true if trading is PAUSED, false if ACTIVE               |
//+------------------------------------------------------------------+
bool IsAutoTradePausedByTelegram()
{
   // 1. High-Speed Memory Check: ZeroMQ Global Variable
   if(GlobalVariableCheck("AutoTrading_Paused"))
   {
      if(GlobalVariableGet("AutoTrading_Paused") > 0.5)
      {
         return true; // Trading remotely paused
      }
   }

   // 2. Persistent File Check: autotrade_state.flag in MQL4\Files
   int fileHandle = FileOpen("autotrade_state.flag", FILE_READ|FILE_TXT|FILE_ANSI);
   if(fileHandle != INVALID_HANDLE)
   {
      string firstLine = FileReadString(fileHandle);
      FileClose(fileHandle);
      
      StringTrimLeft(firstLine);
      StringTrimRight(firstLine);
      StringToUpper(firstLine);
      
      if(StringFind(firstLine, "PAUSED") >= 0)
      {
         return true; // File state indicates PAUSED
      }
   }

   return false; // Active, permitted to trade
}
