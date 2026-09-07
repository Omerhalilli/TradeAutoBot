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
//| Deduplication & Debounce Configuration                           |
//+------------------------------------------------------------------+
#define TG_DEBOUNCE_SLOTS 32
#define TG_DEFAULT_DEBOUNCE_SEC 10

//+------------------------------------------------------------------+
//| Fast DJB2 string hashing for message deduplication               |
//+------------------------------------------------------------------+
uint Telegram_HashText(const string text)
{
   uint hash = 5381;
   int len = StringLen(text);
   for(int i = 0; i < len; i++)
   {
      hash = ((hash << 5) + hash) + (uint)StringGetChar(text, i);
   }
   return hash;
}

//+------------------------------------------------------------------+
//| Check if message is a duplicate within the debounce window       |
//| (Cross-chart terminal ring buffer + local instance guard)         |
//+------------------------------------------------------------------+
bool Telegram_IsDuplicateMessage(const string text, const int debounceSeconds = TG_DEFAULT_DEBOUNCE_SEC)
{
   if(debounceSeconds <= 0 || StringLen(text) == 0) return false;
   
   uint hash = Telegram_HashText(text);
   datetime now = TimeLocal();
   
   // 1. Check terminal-wide GlobalVariables ring buffer
   for(int i = 0; i < TG_DEBOUNCE_SLOTS; i++)
   {
      string hKey = StringFormat("TG_DEB_H_%d", i);
      string tKey = StringFormat("TG_DEB_T_%d", i);
      if(GlobalVariableCheck(hKey) && GlobalVariableCheck(tKey))
      {
         uint entryHash = (uint)GlobalVariableGet(hKey);
         datetime entryTime = (datetime)GlobalVariableGet(tKey);
         if(entryHash == hash && MathAbs((int)(now - entryTime)) < debounceSeconds)
         {
            return true; // Duplicate detected within debounce window
         }
      }
   }
   
   // 2. Record this message into the global ring buffer slot
   int slot = 0;
   if(GlobalVariableCheck("TG_DEB_PTR"))
   {
      slot = (int)GlobalVariableGet("TG_DEB_PTR") % TG_DEBOUNCE_SLOTS;
   }
   if(slot < 0 || slot >= TG_DEBOUNCE_SLOTS) slot = 0;

   GlobalVariableSet(StringFormat("TG_DEB_H_%d", slot), (double)hash);
   GlobalVariableSet(StringFormat("TG_DEB_T_%d", slot), (double)now);
   GlobalVariableSet("TG_DEB_PTR", (double)((slot + 1) % TG_DEBOUNCE_SLOTS));
   
   return false;
}

//+------------------------------------------------------------------+
//| Send message via Telegram Bot API with retry mechanism           |
//+------------------------------------------------------------------+
//+------------------------------------------------------------------+
//| Asynchronous In-Memory Message Queue & Helpers                   |
//+------------------------------------------------------------------+
struct TelegramQueueItem
{
   string token;
   string chat;
   string textHtml;
   string markupJson;
   datetime queueTime;
};

#define TG_QUEUE_MAX_SIZE 64
TelegramQueueItem g_tgMsgQueue[TG_QUEUE_MAX_SIZE];
int g_tgQueueHead  = 0;
int g_tgQueueTail  = 0;
int g_tgQueueCount = 0;

// Write message payload directly to MT4 Files outbox for Python dispatcher (<0.5ms)
bool Telegram_WriteOutboxPayload(const string textHtml, const string chatId = "", const string replyMarkupJson = "")
{
   string escapedText = Telegram_JsonEscape(textHtml);
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
   
   uchar postData[];
   StringToCharArray(jsonPayload, postData, 0, WHOLE_ARRAY, CP_UTF8);
   int dataSize = ArraySize(postData);
   if(dataSize > 0 && postData[dataSize - 1] == 0)
   {
      ArrayResize(postData, dataSize - 1);
      dataSize--;
   }
   
   string uniqueOutName = StringFormat("tg_out_%u_%d.json", (uint)GetTickCount(), MathRand());
   int uHandle = FileOpen(uniqueOutName, FILE_WRITE|FILE_BIN);
   if(uHandle != INVALID_HANDLE)
   {
      FileWriteArray(uHandle, postData, 0, dataSize);
      FileClose(uHandle);
      PrintFormat("[Telegram] Queued message to fail-safe outbox for Python dispatcher: %s", uniqueOutName);
      return true;
   }
   else
   {
      PrintFormat("[Telegram] ERROR: Failed to write outbox file %s (Error %d)", uniqueOutName, GetLastError());
   }
   return false;
}

// WebRequest permission tracking cache to eliminate redundant stalls and log spam when disabled in MT4 options
static bool g_tgWebRequestDisabled = false;

// Low-latency direct HTTP WebRequest post to Telegram API (minimal 1000ms timeout, 0 sleep)
bool Telegram_DirectPost(const string botToken, const string chatId, const string textHtml, const string replyMarkupJson = "", const int timeoutMs = 1000)
{
   if(IsStopped()) return false;
   if(g_tgWebRequestDisabled) return false;
   if(StringLen(botToken) == 0 || StringLen(chatId) == 0) return false;
   
   string escapedText = Telegram_JsonEscape(textHtml);
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
   
   uchar postData[];
   StringToCharArray(jsonPayload, postData, 0, WHOLE_ARRAY, CP_UTF8);
   int dataSize = ArraySize(postData);
   if(dataSize > 0 && postData[dataSize - 1] == 0)
   {
      ArrayResize(postData, dataSize - 1);
      dataSize--;
   }
   
   string url = "https://api.telegram.org/bot" + botToken + "/sendMessage";
   string headers = "Content-Type: application/json\r\n";
   uchar resultData[];
   string resultHeaders = "";
   
   ResetLastError();
   int res = WebRequest("POST", url, headers, timeoutMs, postData, resultData, resultHeaders);
   if(res == 200)
   {
      return true;
   }
   
   int err = GetLastError();
   if(err == ERR_FUNCTION_NOT_ALLOWED || err == 4060)
   {
      g_tgWebRequestDisabled = true;
      PrintFormat("[Telegram] WebRequest not permitted in MT4 options (Error %d). Switched permanently to ultra-low latency outbox dispatcher.", err);
   }
   else
   {
      string responseBody = CharArrayToString(resultData, 0, WHOLE_ARRAY, CP_UTF8);
      PrintFormat("[Telegram] Direct WebRequest returned HTTP %d (Terminal Error %d): %s", res, err, responseBody);
   }
   return false;
}

// Enqueue message into ring buffer
bool Telegram_QueueEnqueue(const string token, const string chat, const string textHtml, const string markupJson)
{
   if(IsStopped()) return false;
   if(g_tgQueueCount >= TG_QUEUE_MAX_SIZE)
   {
      // Buffer full: flush oldest to outbox to prevent message drop
      Telegram_WriteOutboxPayload(g_tgMsgQueue[g_tgQueueHead].textHtml, g_tgMsgQueue[g_tgQueueHead].chat, g_tgMsgQueue[g_tgQueueHead].markupJson);
      g_tgQueueHead = (g_tgQueueHead + 1) % TG_QUEUE_MAX_SIZE;
      g_tgQueueCount--;
   }
   
   g_tgMsgQueue[g_tgQueueTail].token = token;
   g_tgMsgQueue[g_tgQueueTail].chat = chat;
   g_tgMsgQueue[g_tgQueueTail].textHtml = textHtml;
   g_tgMsgQueue[g_tgQueueTail].markupJson = markupJson;
   g_tgMsgQueue[g_tgQueueTail].queueTime = TimeLocal();
   
   g_tgQueueTail = (g_tgQueueTail + 1) % TG_QUEUE_MAX_SIZE;
   g_tgQueueCount++;
   return true;
}

// Drain pending messages from queue (called from OnTimer)
void Telegram_ProcessQueue()
{
   if(IsStopped()) return;
   if(g_tgQueueCount <= 0) return;

   int toProcess = MathMin(3, g_tgQueueCount);
   for(int i = 0; i < toProcess; i++)
   {
      if(IsStopped() || g_tgQueueCount <= 0) break;

      TelegramQueueItem item = g_tgMsgQueue[g_tgQueueHead];
      bool sent = false;

      if(!g_tgWebRequestDisabled && StringLen(item.token) > 0 && StringLen(item.chat) > 0)
      {
         sent = Telegram_DirectPost(item.token, item.chat, item.textHtml, item.markupJson, 1000);
      }

      if(!sent)
      {
         // Direct post failed, token empty, or WebRequest disabled -> write to fail-safe outbox immediately (<0.1ms)
         Telegram_WriteOutboxPayload(item.textHtml, item.chat, item.markupJson);
      }

      g_tgQueueHead = (g_tgQueueHead + 1) % TG_QUEUE_MAX_SIZE;
      g_tgQueueCount--;
   }
}

// Flush all queued messages on EA deinitialization
void Telegram_FlushQueue()
{
   while(g_tgQueueCount > 0)
   {
      TelegramQueueItem item = g_tgMsgQueue[g_tgQueueHead];
      Telegram_WriteOutboxPayload(item.textHtml, item.chat, item.markupJson);
      g_tgQueueHead = (g_tgQueueHead + 1) % TG_QUEUE_MAX_SIZE;
      g_tgQueueCount--;
   }
}

//+------------------------------------------------------------------+
//| Send message via Telegram Bot API with queue & outbox fallback   |
//+------------------------------------------------------------------+
bool Telegram_SendMessage(const string botToken, 
                          const string chatId, 
                          const string messageTextHtml, 
                          const int retryCount = 1, 
                          const int retryDelaySec = 0,
                          const string replyMarkupJson = "")
{
   if(IsStopped()) return false;
   if(StringLen(messageTextHtml) == 0) return false;

   // Debounce guard: suppress duplicate messages sent within the debounce window
   if(Telegram_IsDuplicateMessage(messageTextHtml, TG_DEFAULT_DEBOUNCE_SEC))
   {
      Print("[Telegram] Debounce: duplicate message suppressed within debounce window.");
      return true;
   }

   string activeToken = botToken;
   string activeChat = chatId;
      
   // If direct WebRequest parameters are missing or WebRequest is disabled in MT4 options, write instantly to outbox (<0.1ms)
   if(g_tgWebRequestDisabled || StringLen(activeToken) == 0 || StringLen(activeChat) == 0)
   {
      return Telegram_WriteOutboxPayload(messageTextHtml, activeChat, replyMarkupJson);
   }

   // If message queue is currently empty, attempt immediate non-blocking WebRequest (1000ms timeout max)
   if(g_tgQueueCount == 0)
   {
      if(Telegram_DirectPost(activeToken, activeChat, messageTextHtml, replyMarkupJson, 1000))
      {
         return true; // Sent successfully via WebRequest!
      }
   }

   // Direct WebRequest failed or queue has pending items -> enqueue for asynchronous timer dispatch
   return Telegram_QueueEnqueue(activeToken, activeChat, messageTextHtml, replyMarkupJson);
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
   
   // High-frequency non-blocking check: wait up to 1000ms in 15ms increments for screenshot flush
   for(int w = 0; w < 65; w++)
   {
      if(IsStopped()) return false;
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
      Sleep(15);
   }
   
   if(IsStopped() || fileHandle == INVALID_HANDLE || fileSize <= 100)
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
   
   if(IsStopped())
   {
      FileDelete(filename);
      return false;
   }

   ResetLastError();
   int res = WebRequest("POST", url, headers, 2500, bodyBytes, resultData, resultHeaders);
   
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
