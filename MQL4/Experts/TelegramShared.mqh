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

// Clean Unicode / Emoji definitions immune to Windows code page corruption
#define TG_GREEN_CIRCLE (ShortToString(0xD83D) + ShortToString(0xDFE2))
#define TG_RED_CIRCLE   (ShortToString(0xD83D) + ShortToString(0xDD34))
#define TG_WARNING      (ShortToString(0x26A0) + ShortToString(0xFE0F))
#define TG_CHECK        (ShortToString(0x2705))
#define TG_CROSS        (ShortToString(0x274C))
#define TG_DOOR         (ShortToString(0xD83D) + ShortToString(0xDEAA))
#define TG_BULLET       (ShortToString(0x2022))
#define TG_CAMERA       (ShortToString(0xD83D) + ShortToString(0xDCF8))
#define TG_SHIELD       (ShortToString(0xD83D) + ShortToString(0xDEE1) + ShortToString(0xFE0F))
#define TG_SCISSORS     (ShortToString(0x2702) + ShortToString(0xFE0F))
#define TG_CHART_UP     (ShortToString(0xD83D) + ShortToString(0xDCC8))
#define TG_CHART_DOWN   (ShortToString(0xD83D) + ShortToString(0xDCC9))
#define TG_LOCK         (ShortToString(0xD83D) + ShortToString(0xDD12))
#define TG_SIREN        (ShortToString(0xD83D) + ShortToString(0xDEA8))
#define TG_DIVIDER      "-----------------------------------"
#define TG_ROCKET       (ShortToString(0xD83D) + ShortToString(0xDE80))
#define TG_MONEY        (ShortToString(0xD83D) + ShortToString(0xDCB0))
#define TG_CHART        (ShortToString(0xD83D) + ShortToString(0xDCCA))
#define TG_TARGET       (ShortToString(0xD83C) + ShortToString(0xDFAF))
#define TG_USER         (ShortToString(0xD83D) + ShortToString(0xDC64))
#define TG_CLOCK        (ShortToString(0x23F0))
#define TG_TICKET       (ShortToString(0xD83C) + ShortToString(0xDFAB))
#define TG_FIRE         (ShortToString(0xD83D) + ShortToString(0xDD25))
#define TG_PAUSE        (ShortToString(0x23F8) + ShortToString(0xFE0F))
#define TG_ARROW_UP     (ShortToString(0x2197))
#define TG_ARROW_DOWN   (ShortToString(0x2198))
#define TG_ARROW_RIGHT  (ShortToString(0x27A1))
#define TG_CASH         (ShortToString(0xD83D) + ShortToString(0xDCB5))
#define TG_CLIPBOARD    (ShortToString(0xD83D) + ShortToString(0xDCCB))

//+------------------------------------------------------------------+
//| Escape special JSON characters                                  |
//+------------------------------------------------------------------+
string Telegram_JsonEscape(string text)
{
   string result = text;
   StringReplace(result, "\\", "\\\\");
   StringReplace(result, "\"", "\\\"");
   StringReplace(result, ShortToString(0x08), "\\b");
   StringReplace(result, ShortToString(0x0C), "\\f");
   StringReplace(result, "\r", "");
   StringReplace(result, "\n", "\\n");
   StringReplace(result, "\t", "\\t");
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
   string activeToken = botToken;
   if(StringLen(activeToken) == 0)
   {
      Print("[Telegram] ERROR: Bot token is empty. Configure TelegramBotToken in EA inputs.");
      return false;
   }
   string activeChat = chatId;
   if(StringLen(activeChat) == 0)
   {
      Print("[Telegram] ERROR: Chat ID is empty. Configure TelegramChatID in EA inputs.");
      return false;
   }
      
   string url = "https://api.telegram.org/bot" + activeToken + "/sendMessage";
   string headers = "Content-Type: application/json\r\n";
   int timeout = 5000; // 5 seconds
   
   // Build JSON payload
   string escapedText = Telegram_JsonEscape(messageTextHtml);
   string jsonPayload;
   if(StringLen(replyMarkupJson) > 0)
   {
      jsonPayload = StringFormat("{\"chat_id\":\"%s\",\"text\":\"%s\",\"parse_mode\":\"HTML\",\"disable_web_page_preview\":true,\"reply_markup\":%s}",
                                 activeChat, escapedText, replyMarkupJson);
   }
   else
   {
      jsonPayload = StringFormat("{\"chat_id\":\"%s\",\"text\":\"%s\",\"parse_mode\":\"HTML\",\"disable_web_page_preview\":true}",
                                 activeChat, escapedText);
   }
   
   // Convert to UTF-8 char array
   uchar postData[];
   uchar resultData[];
   string resultHeaders = "";
   
   StringToCharArray(jsonPayload, postData, 0, WHOLE_ARRAY, CP_UTF8);
   
   // StringToCharArray includes trailing null character, strip it for HTTP body and file outbox
   int dataSize = ArraySize(postData);
   if(dataSize > 0 && postData[dataSize - 1] == 0)
   {
      ArrayResize(postData, dataSize - 1);
      dataSize--;
   }

   // Fail-safe outbox buffer for external Python bot dispatcher (pure UTF-8 binary)
   string uniqueOutName = StringFormat("tg_out_%u_%d.json", (uint)GetTickCount(), MathRand());
   int uHandle = FileOpen(uniqueOutName, FILE_WRITE|FILE_BIN);
   if(uHandle != INVALID_HANDLE)
   {
      FileWriteArray(uHandle, postData, 0, dataSize);
      FileClose(uHandle);
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
   string callback_id;  // Populated when update is an inline button click
};

//+------------------------------------------------------------------+
//| Extract string or numeric field from JSON with whitespace safety |
//+------------------------------------------------------------------+
string Telegram_ExtractJsonField(const string json, const string fieldName, int startPos, int limitPos)
{
   string searchStr = "\"" + fieldName + "\"";
   int pos = StringFind(json, searchStr, startPos);
   if(pos < 0 || pos >= limitPos) return "";
   
   pos += StringLen(searchStr);
   int len = StringLen(json);
   if(limitPos > len) limitPos = len;
   
   // Skip colon and any whitespace
   while(pos < limitPos)
   {
      ushort c = StringGetCharacter(json, pos);
      if(c == ':' || c == ' ' || c == '\t' || c == '\r' || c == '\n') pos++;
      else break;
   }
   if(pos >= limitPos) return "";
   
   // Quoted string
   if(StringGetCharacter(json, pos) == '\"')
   {
      pos++;
      int endPos = pos;
      while(endPos < limitPos)
      {
         ushort c = StringGetCharacter(json, endPos);
         if(c == '\"' && StringGetCharacter(json, endPos - 1) != '\\') break;
         endPos++;
      }
      return StringSubstr(json, pos, endPos - pos);
   }
   else
   {
      // Numeric or unquoted value
      int endPos = pos;
      while(endPos < limitPos)
      {
         ushort c = StringGetCharacter(json, endPos);
         if(c == ',' || c == '}' || c == ']' || c == ' ' || c == '\r' || c == '\n') break;
         endPos++;
      }
      return StringSubstr(json, pos, endPos - pos);
   }
}

//+------------------------------------------------------------------+
//| Query updates from Telegram via getUpdates with allowed_updates  |
//+------------------------------------------------------------------+
int Telegram_GetUpdates(const string botToken, int offset, string &responseJson)
{
   string url = "https://api.telegram.org/bot" + botToken + "/getUpdates?offset=" + IntegerToString(offset) + "&limit=10&timeout=0&allowed_updates=%5B%22message%22%2C%22callback_query%22%5D";
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
//| Acknowledge Telegram callback query to dismiss client spinner    |
//+------------------------------------------------------------------+
void Telegram_AnswerCallbackQuery(const string botToken, const string callbackId, const string textMsg = "")
{
   if(callbackId == "") return;
   string url = "https://api.telegram.org/bot" + botToken + "/answerCallbackQuery?callback_query_id=" + callbackId;
   string headers = "";
   uchar postData[];
   uchar resultData[];
   string resultHeaders = "";
   ResetLastError();
   WebRequest("GET", url, headers, 2000, postData, resultData, resultHeaders);
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
      
      string senderId   = "";
      string text       = "";
      string callbackId = "";
      
      // Check if update is a callback_query (inline keyboard button click)
      int cbPos = StringFind(json, "\"callback_query\"", uEnd);
      if(cbPos > 0 && cbPos < blockLimit)
      {
         callbackId = Telegram_ExtractJsonField(json, "id", cbPos, blockLimit);
         text       = Telegram_ExtractJsonField(json, "data", cbPos, blockLimit);
         
         // Extract user id from "from": {"id": ...}
         int fromPos = StringFind(json, "\"from\"", cbPos);
         if(fromPos > 0 && fromPos < blockLimit)
         {
            senderId = Telegram_ExtractJsonField(json, "id", fromPos, blockLimit);
         }
         
         // Fallback to chat id in "message":{"chat":{"id": ...}}
         if(senderId == "")
         {
            int chatPos = StringFind(json, "\"chat\"", cbPos);
            if(chatPos > 0 && chatPos < blockLimit)
            {
               senderId = Telegram_ExtractJsonField(json, "id", chatPos, blockLimit);
            }
         }
      }
      else
      {
         // Regular message update
         int chatPos = StringFind(json, "\"chat\"", uEnd);
         if(chatPos > 0 && chatPos < blockLimit)
         {
            senderId = Telegram_ExtractJsonField(json, "id", chatPos, blockLimit);
         }
         text = Telegram_ExtractJsonField(json, "text", uEnd, blockLimit);
      }
      
      StringReplace(text, "\\/", "/");
      
      int sz = ArraySize(updates);
      ArrayResize(updates, sz + 1, 32);
      updates[sz].update_id   = updateId;
      updates[sz].sender_id   = senderId;
      updates[sz].text        = text;
      updates[sz].callback_id = callbackId;
      
      pos = (nextUpdate > 0) ? nextUpdate : len;
   }
   
   return ArraySize(updates);
}

//+------------------------------------------------------------------+
//| Send Photo via Telegram sendPhoto multipart/form-data            |
//+------------------------------------------------------------------+
// 5-parameter version with interactive reply_markup support
bool Telegram_SendPhoto(const string botToken, const string chatId, const string filename, const string captionHtml, const string replyMarkupJson)
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

//+------------------------------------------------------------------+
//| 4-parameter overload for backward compatibility                  |
//+------------------------------------------------------------------+
bool Telegram_SendPhoto(const string botToken, const string chatId, const string filename, const string captionHtml)
{
   return Telegram_SendPhoto(botToken, chatId, filename, captionHtml, "");
}
