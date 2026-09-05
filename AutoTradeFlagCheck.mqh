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
         return true; // Trading remotely paused in memory
   }

   // 2. Periodic Persistent File Check (throttled to at most once per 1000ms to eliminate disk I/O load)
   static uint s_lastDiskCheck = 0;
   static bool s_cachedFilePaused = false;
   uint now = GetTickCount();
   if(now - s_lastDiskCheck >= 1000 || s_lastDiskCheck == 0)
   {
      s_lastDiskCheck = now;
      s_cachedFilePaused = false;
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
            s_cachedFilePaused = true;
            GlobalVariableSet("AutoTrading_Paused", 1.0);
         }
      }
   }

   return s_cachedFilePaused;
}
