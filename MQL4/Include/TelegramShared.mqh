//+------------------------------------------------------------------+
//|                                               TelegramShared.mqh |
//|                        Telegram Bot API Notification Library     |
//|                        Compatible with both MQL4 and MQL5        |
//+------------------------------------------------------------------+
#property copyright "Antigravity Automated Systems"
#property link      "https://t.me"
#property strict

// Error code constants across MQL4 and MQL5
#ifndef ERR_FUNCTION_NOT_ALLOWED
#define ERR_FUNCTION_NOT_ALLOWED 4060
#endif

//+------------------------------------------------------------------+
//| Escape special JSON characters                                  |
//+------------------------------------------------------------------+
string Telegram_JsonEscape(string text)
{
   string result = "";
   int len = StringLen(text);
   for(int i = 0; i < len; i++)
   {
      ushort ch = StringGetCharacter(text, i);
      switch(ch)
      {
         case '\"': result += "\\\""; break;
         case '\\': result += "\\\\"; break;
         case 0x08: result += "\\b"; break;
         case 0x0C: result += "\\f"; break;
         case '\n': result += "\\n"; break;
         case '\r': result += "\\r"; break;
         case '\t': result += "\\t"; break;
         default:
            StringSetCharacter(result, StringLen(result), ch);
            break;
      }
   }
   return result;
}

//+------------------------------------------------------------------+
//| Escape HTML entities for Telegram HTML parse_mode                |
//+------------------------------------------------------------------+
string Telegram_EscapeHtml(string text)
{
   string result = text;
   StringReplace(result, "&", "&amp;");
   StringReplace(result, "<", "&lt;");
   StringReplace(result, ">", "&gt;");
   return result;
}

//+------------------------------------------------------------------+
//| Send message via Telegram Bot API with retry mechanism           |
//+------------------------------------------------------------------+
bool Telegram_SendMessage(const string botToken, 
                          const string chatId, 
                          const string messageTextHtml, 
                          const int retryCount = 3, 
                          const int retryDelaySec = 2,
                          const string replyMarkupJson = "")
{
   if(StringLen(botToken) == 0)
   {
      Print("[Telegram] Error: Bot Token is empty. Please configure InpTelegramToken.");
      return false;
   }
   
   if(StringLen(chatId) == 0)
   {
      Print("[Telegram] Error: Chat ID is empty. Please configure InpTelegramChatID.");
      return false;
   }
   
   string url = "https://api.telegram.org/bot" + botToken + "/sendMessage";
   string headers = "Content-Type: application/json\r\n";
   int timeout = 5000; // 5 seconds
   
   // Build JSON payload
   string escapedText = Telegram_JsonEscape(messageTextHtml);
   string jsonPayload;
   if(StringLen(replyMarkupJson) > 0)
   {
      jsonPayload = StringFormat("{\"chat_id\":\"%s\",\"text\":\"%s\",\"parse_mode\":\"HTML\",\"disable_web_page_preview\":true,\"reply_markup\":%s}",
                                 chatId, escapedText, replyMarkupJson);
   }
   else
   {
      jsonPayload = StringFormat("{\"chat_id\":\"%s\",\"text\":\"%s\",\"parse_mode\":\"HTML\",\"disable_web_page_preview\":true}",
                                 chatId, escapedText);
   }
   
   // Convert to UTF-8 char array
   uchar postData[];
   uchar resultData[];
   string resultHeaders = "";
   
   int payloadLen = StringLen(jsonPayload);
   StringToCharArray(jsonPayload, postData, 0, WHOLE_ARRAY, CP_UTF8);
   
   // StringToCharArray includes trailing null character, strip it for HTTP body
   int dataSize = ArraySize(postData);
   if(dataSize > 0 && postData[dataSize - 1] == 0)
   {
      ArrayResize(postData, dataSize - 1);
   }
   
   int attempts = MathMax(1, retryCount);
   for(int attempt = 1; attempt <= attempts; attempt++)
   {
      ResetLastError();
      int res = WebRequest("POST", url, headers, timeout, postData, resultData, resultHeaders);
      
      if(res == 200)
      {
         return true; // Sent successfully
      }
      
      int err = GetLastError();
      string responseBody = CharArrayToString(resultData, 0, WHOLE_ARRAY, CP_UTF8);
      
      // Common configuration error: WebRequest URL not whitelisted in terminal options
      if(err == ERR_FUNCTION_NOT_ALLOWED || err == 4060)
      {
         Print("==================================================================");
         Print("[Telegram] CRITICAL ERROR: WebRequest is not allowed in MetaTrader!");
         Print("[Telegram] FIX: Go to Tools -> Options -> Expert Advisors tab.");
         Print("[Telegram] 1. Check 'Allow WebRequest for listed URL:'");
         Print("[Telegram] 2. Add: https://api.telegram.org");
         Print("==================================================================");
         return false; // Retrying will not fix configuration
      }
      
      PrintFormat("[Telegram] Attempt %d/%d failed. HTTP Code: %d, Terminal Error: %d, Response: %s", 
                  attempt, attempts, res, err, responseBody);
      
      // If client-side error (400 Bad Request, 401 Unauthorized, 404 Not Found), don't retry fruitlessly
      if(res == 400 || res == 401 || res == 404)
      {
         Print("[Telegram] Aborting retries due to non-recoverable HTTP client error.");
         return false;
      }
      
      // Backoff before retry
      if(attempt < attempts)
      {
         Sleep(retryDelaySec * 1000);
      }
   }
   
   return false;
}

//+------------------------------------------------------------------+
//| Format money value with +/- and 2 decimals                       |
//+------------------------------------------------------------------+
string Telegram_FormatMoney(double amount, string currency = "USD")
{
   string sign = (amount >= 0.0) ? "+" : "";
   return StringFormat("%s%.2f %s", sign, amount, currency);
}

//+------------------------------------------------------------------+
//| Format double price according to symbol digits                   |
//+------------------------------------------------------------------+
string Telegram_FormatPrice(double price, int digits)
{
   if(price <= 0.0) return "None";
   return DoubleToString(price, digits);
}

//+------------------------------------------------------------------+
//| Telegram Incoming Update Data Structure                          |
//+------------------------------------------------------------------+
struct TelegramUpdateMessage
{
   int    update_id;
   string sender_id;
   string text;
};

//+------------------------------------------------------------------+
//| Query updates from Telegram via getUpdates                       |
//+------------------------------------------------------------------+
int Telegram_GetUpdates(const string botToken, int offset, string &responseJson)
{
   string url = "https://api.telegram.org/bot" + botToken + "/getUpdates?offset=" + IntegerToString(offset) + "&limit=10&timeout=0";
   string headers = "";
   uchar postData[];
   uchar resultData[];
   string resultHeaders = "";
   
   ResetLastError();
   int res = WebRequest("GET", url, headers, 3000, postData, resultData, resultHeaders);
   if(res == 200)
   {
      responseJson = CharArrayToString(resultData, 0, WHOLE_ARRAY, CP_UTF8);
      return 200;
   }
   return res;
}

//+------------------------------------------------------------------+
//| Parse incoming update JSON string into message array             |
//+------------------------------------------------------------------+
int Telegram_ParseUpdates(const string json, TelegramUpdateMessage &updates[])
{
   ArrayResize(updates, 0);
   int len = StringLen(json);
   int pos = 0;
   
   while(pos < len)
   {
      int uPos = StringFind(json, "\"update_id\":", pos);
      if(uPos < 0) break;
      uPos += 12;
      
      int uEnd = StringFind(json, ",", uPos);
      if(uEnd < 0) break;
      int updateId = (int)StringToInteger(StringSubstr(json, uPos, uEnd - uPos));
      
      int nextUpdate = StringFind(json, "\"update_id\":", uEnd);
      int blockLimit = (nextUpdate > 0) ? nextUpdate : len;
      
      string senderId = "";
      string text = "";
      
      // Check if update is a callback_query (inline keyboard button click)
      int cbPos = StringFind(json, "\"callback_query\":", uEnd);
      if(cbPos > 0 && cbPos < blockLimit)
      {
         int fromPos = StringFind(json, "\"from\":{", cbPos);
         if(fromPos > 0 && fromPos < blockLimit)
         {
            int idPos = StringFind(json, "\"id\":", fromPos);
            if(idPos > 0 && idPos < blockLimit)
            {
               idPos += 5;
               int idEnd = StringFind(json, ",", idPos);
               if(idEnd > 0 && idEnd < blockLimit)
               {
                  senderId = StringSubstr(json, idPos, idEnd - idPos);
                  StringTrimLeft(senderId);
                  StringTrimRight(senderId);
               }
            }
         }
         
         int dataPos = StringFind(json, "\"data\":\"", cbPos);
         if(dataPos > 0 && dataPos < blockLimit)
         {
            dataPos += 8;
            int dataEnd = dataPos;
            while(dataEnd < blockLimit)
            {
               ushort ch = StringGetCharacter(json, dataEnd);
               if(ch == '\"' && StringGetCharacter(json, dataEnd - 1) != '\\')
                  break;
               dataEnd++;
            }
            text = StringSubstr(json, dataPos, dataEnd - dataPos);
         }
      }
      else
      {
         // Regular message update
         int chatPos = StringFind(json, "\"chat\":{", uEnd);
         if(chatPos > 0 && chatPos < blockLimit)
         {
            int idPos = StringFind(json, "\"id\":", chatPos);
            if(idPos > 0 && idPos < blockLimit)
            {
               idPos += 5;
               int idEnd = StringFind(json, ",", idPos);
               if(idEnd > 0 && idEnd < blockLimit)
               {
                  senderId = StringSubstr(json, idPos, idEnd - idPos);
                  StringTrimLeft(senderId);
                  StringTrimRight(senderId);
               }
            }
         }
         
         int textPos = StringFind(json, "\"text\":\"", uEnd);
         if(textPos > 0 && textPos < blockLimit)
         {
            textPos += 8;
            int textEnd = textPos;
            while(textEnd < blockLimit)
            {
               ushort ch = StringGetCharacter(json, textEnd);
               if(ch == '\"' && StringGetCharacter(json, textEnd - 1) != '\\')
                  break;
               textEnd++;
            }
            text = StringSubstr(json, textPos, textEnd - textPos);
         }
      }
      
      StringReplace(text, "\\/", "/");
      
      int sz = ArraySize(updates);
      ArrayResize(updates, sz + 1);
      updates[sz].update_id = updateId;
      updates[sz].sender_id = senderId;
      updates[sz].text      = text;
      
      pos = (nextUpdate > 0) ? nextUpdate : len;
   }
   
   return ArraySize(updates);
}

//+------------------------------------------------------------------+
//| Send Photo via Telegram sendPhoto multipart/form-data            |
//+------------------------------------------------------------------+
bool Telegram_SendPhoto(const string botToken, const string chatId, const string filename, const string captionHtml, const string replyMarkupJson = "")
{
   int fileHandle = INVALID_HANDLE;
   int fileSize = 0;
   
   // Wait up to 2500ms for MT4/MT5 to flush the image file to disk
   for(int w = 0; w < 25; w++)
   {
      if(FileIsExist(filename))
      {
         fileHandle = FileOpen(filename, FILE_BIN | FILE_READ);
         if(fileHandle != INVALID_HANDLE)
         {
            fileSize = (int)FileSize(fileHandle);
            if(fileSize > 100)
            {
               break; // File is ready and non-empty!
            }
            FileClose(fileHandle);
            fileHandle = INVALID_HANDLE;
         }
      }
      Sleep(100);
   }
   
   if(fileHandle == INVALID_HANDLE || fileSize <= 100)
   {
      if(fileHandle != INVALID_HANDLE) FileClose(fileHandle);
      PrintFormat("[Telegram] Failed to open image or image empty: %s (Error %d)", filename, GetLastError());
      return false;
   }
   
   uchar fileBytes[];
   ArrayResize(fileBytes, fileSize);
   FileReadArray(fileHandle, fileBytes, 0, fileSize);
   FileClose(fileHandle);
   
   string boundary = "--------------------MqlBoundary9876543210";
   string headers = "Content-Type: multipart/form-data; boundary=" + boundary + "\r\n";
   
   string part1 = "--" + boundary + "\r\n" +
                  "Content-Disposition: form-data; name=\"chat_id\"\r\n\r\n" +
                  chatId + "\r\n" +
                  "--" + boundary + "\r\n" +
                  "Content-Disposition: form-data; name=\"caption\"\r\n\r\n" +
                  captionHtml + "\r\n" +
                  "--" + boundary + "\r\n" +
                  "Content-Disposition: form-data; name=\"parse_mode\"\r\n\r\n" +
                  "HTML\r\n";

   if(StringLen(replyMarkupJson) > 0)
   {
      part1 += "--" + boundary + "\r\n" +
               "Content-Disposition: form-data; name=\"reply_markup\"\r\n\r\n" +
               replyMarkupJson + "\r\n";
   }

   part1 += "--" + boundary + "\r\n" +
            "Content-Disposition: form-data; name=\"photo\"; filename=\"" + filename + "\"\r\n" +
            "Content-Type: image/png\r\n\r\n";
                  
   string part2 = "\r\n--" + boundary + "--\r\n";
   
   uchar part1Bytes[];
   uchar part2Bytes[];
   StringToCharArray(part1, part1Bytes, 0, WHOLE_ARRAY, CP_UTF8);
   StringToCharArray(part2, part2Bytes, 0, WHOLE_ARRAY, CP_UTF8);
   
   int p1Size = ArraySize(part1Bytes);
   if(p1Size > 0 && part1Bytes[p1Size - 1] == 0) p1Size--;
   
   int p2Size = ArraySize(part2Bytes);
   if(p2Size > 0 && part2Bytes[p2Size - 1] == 0) p2Size--;
   
   int totalSize = p1Size + fileSize + p2Size;
   uchar bodyBytes[];
   ArrayResize(bodyBytes, totalSize);
   
   ArrayCopy(bodyBytes, part1Bytes, 0, 0, p1Size);
   ArrayCopy(bodyBytes, fileBytes, p1Size, 0, fileSize);
   ArrayCopy(bodyBytes, part2Bytes, p1Size + fileSize, 0, p2Size);
   
   uchar resultData[];
   string resultHeaders = "";
   string url = "https://api.telegram.org/bot" + botToken + "/sendPhoto";
   
   ResetLastError();
   int res = WebRequest("POST", url, headers, 15000, bodyBytes, resultData, resultHeaders);
   
   // Clean up local screenshot
   FileDelete(filename);
   
   if(res == 200)
   {
      return true;
   }
   
   string responseBody = CharArrayToString(resultData, 0, WHOLE_ARRAY, CP_UTF8);
   PrintFormat("[Telegram] sendPhoto failed. HTTP Code: %d, Terminal Error: %d, Response: %s", res, GetLastError(), responseBody);
   return false;
}
