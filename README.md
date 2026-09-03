# 🏛️ Institutional MetaTrader 4 Telegram Bot & ZeroMQ Bridge (24/7 Production Ready)

A battle-tested, high-performance Python & MQL4 bridge integrating **MetaTrader 4 (MT4)** with **Telegram**. Built for continuous **24/7 unattended operation**, automatic network self-healing, zero-latency order execution, interactive multi-step chart capture, and persistent economic news alerts.

---

## 📑 Table of Contents
1. [Key Features & Capabilities](#-key-features--capabilities)
2. [Interactive 2-Step Screenshot Panel](#-interactive-2-step-screenshot-panel)
3. [Architecture & Resilience](#-architecture--resilience)
4. [Prerequisites & Quick Setup](#-prerequisites--quick-setup)
5. [MQL4 & mql4-zmq Installation](#-mql4--mql4-zmq-installation)
6. [Configuration (.env)](#-configuration-env)
7. [Running the Bot](#-running-the-bot)
8. [24/7 Production Service Deployment](#-247-production-service-deployment)
   - [Linux Systemd Service](#linux-systemd-service)
   - [Windows Service via NSSM](#windows-service-via-nssm)
   - [Windows Task Scheduler](#windows-task-scheduler)
9. [External EA Integration Snippet (Pause/Resume)](#-external-ea-integration-snippet)
10. [Resilience & Fault-Tolerance Verification](#-resilience--fault-tolerance-verification)
11. [Complete /help Command List](#-complete-help-command-list)

---

## 🚀 Key Features & Capabilities

* **24/7 Self-Healing Architecture**: Operates fully decoupled from MT4. If MT4 closes, crashes, or reboots, the bot stays online, gracefully responds ⚠️ MT4 not connected, retries connection every 5 seconds, and automatically reconnects the instant MT4 returns.
* **Interactive 2-Step Screenshot Wizard**: Type /screenshot to receive an interactive inline instrument picker (GBPUSD, EURUSD, XAUUSD, USDJPY, BTCUSD, USOIL, Active Chart). Tapping an instrument displays the timeframe grid (M1 to D1). Tapping a timeframe commands MT4 to render the chart, capture a 1280x720 PNG photo, and send it to chat with real-time Bid/Ask/Server Time telemetry.
* **Persistent Economic News Shield**: Scrapes high & medium impact economic events from ForexFactory (with offline fallback). Automatically reminds you **15 minutes** before high-impact releases with currency flags, forecast, and previous data. Dispatched alerts are persisted to disk (data/sent_alerts.json) so bot restarts **never duplicate alerts**.
* **Prop-Firm Risk Guardian**: Real-time evaluation of funded account rules (/prop): Daily Drawdown tracking, Trailing Peak Drawdown, Phase Target progress bar [■■□□□□□□□□], and weekend risk alerts.
* **24-Hour Performance Audit**: /report generates an institutional breakdown of closed trades: Win Rate %, Profit Factor, Net P/L, Gross Profit/Loss, and best/worst trades.
* **Emergency Remote Order Management**: Liquidate all trades (/panic or /closeall with interactive confirmation button), close individual symbols (/close XAUUSD), modify Stop Loss / Take Profit (/modify_sl, /modify_tp).
* **Remote AutoTrading Kill-Switch**: /pause_bot and /resume_bot immediately update both MT4 Global Variables and write to MQL4\Files\autotrade_state.flag, allowing external EAs to freeze/unfreeze new entries.
* **Security & Sandboxing**: Strict whitelist security: only authorized Telegram Chat IDs defined in .env can execute commands or click buttons. Unauthorized users receive ⛔ Access Denied.
* **Rotating File Logging**: All events, trades, and ZeroMQ queries are recorded to logs/bot.log with automatic 5MB rotating file handlers.

---

## 📸 Interactive 2-Step Screenshot Panel

The screenshot wizard lets you inspect any market chart from Telegram on demand:

`
User types /screenshot
      │
      ▼
┌────────────────────────────────────────┐
│ 📸 Interactive Chart Screenshot Panel  │
│ Select currency pair or instrument:    │
│ ┌───────────────┐  ┌─────────────────┐ │
│ │ 🇬🇧 GBPUSD     │  │ 🇪🇺 EURUSD       │ │
│ ├───────────────┤  ├─────────────────┤ │
│ │ 🪙 XAUUSD     │  │ 🇯🇵 USDJPY       │ │
│ ├───────────────┤  ├─────────────────┤ │
│ │ ₿ BTCUSD      │  │ 🛢️ USOIL        │ │
│ ├───────────────┴──┴─────────────────┤ │
│ │ 📊 Current Active Chart            │ │
│ └────────────────────────────────────┘ │
└──────────────────┬─────────────────────┘
                   │ User taps [ 🪙 XAUUSD ]
                   ▼
┌────────────────────────────────────────┐
│ 📸 Selected Instrument: XAUUSD         │
│ Choose timeframe to render & capture:  │
│ ┌───────────┐  ┌───────────┐  ┌──────┐ │
│ │ ⏱️ M1     │  │ ⏱️ M5     │  │ M15  │ │
│ ├───────────┼──┼───────────┼──┼──────┤ │
│ │ ⏱️ M30    │  │ ⏱️ H1     │  │ H4   │ │
│ ├───────────┼──┼───────────┼──┼──────┤ │
│ │ 📅 D1     │  │ 📅 W1     │  │ Back │ │
│ └───────────┴──┴───────────┴──┴──────┘ │
└──────────────────┬─────────────────────┘
                   │ User taps [ ⏱️ H1 ]
                   ▼
  1. Bot sends ZeroMQ: {"action":"SCREENSHOT", "symbol":"XAUUSD", "timeframe":"H1"}
  2. MT4 opens/renders XAUUSD H1 chart with clean candlestick theme
  3. MT4 calls ChartScreenShot() -> saves MQL4/Files/chart_screenshot.png
  4. Telegram Bot sends high-res photo with live Bid, Ask, and Server Time!
`

---

## 🏗️ Architecture & Resilience

`
┌────────────────────────────────────────────────────────┐
│                     Telegram User                      │
└───────────────────────────┬────────────────────────────┘
                            │ HTTPS Long-Polling (python-telegram-bot v20+)
                            │ Resilient DNS Hook (149.154.166.110 fallback)
                            ▼
┌────────────────────────────────────────────────────────┐
│                 Python Bridge Daemon                   │
│  - Rotating File Logger (logs/bot.log)                 │
│  - Persistent Sent Alerts Store (data/sent_alerts.json)│
│  - 5-Second Background Heartbeat & Auto-Reconnect Loop │
└───────────────────────────┬────────────────────────────┘
                            │ ZeroMQ REQ / REP (tcp://127.0.0.1:5555)
                            │ Non-blocking Lazy Pirate Socket Recovery
                            ▼
┌────────────────────────────────────────────────────────┐
│             MetaTrader 4 Terminal (InvestAZ)            │
│  - SmartAutoTradeEA_Pro.mq4 / MT4_ZeroMQ_Bridge.mq4    │
│  - libzmq.dll + mql4-zmq C++ Native Bridge             │
│  - OnTimer() 50ms REP Request Dispatcher               │
└────────────────────────────────────────────────────────┘
`

---

## 📦 Prerequisites & Quick Setup

### 1. Python Environment
Python 3.8 to 3.14 on Windows or Linux:
`ash
cd mt4-telegram-bridge
pip install -r requirements.txt
`

equirements.txt:
`	xt
python-telegram-bot>=20.0
pyzmq>=24.0.0
httpx>=0.24.0
`

### 2. Telegram Bot Setup
1. Open Telegram and message **@BotFather**.
2. Send /newbot, choose a name and username (e.g. MyMT4TradeBot).
3. Copy the **HTTP API Token** provided by BotFather.
4. Message **@userinfobot** to find your numerical **User ID** (e.g. your_telegram_chat_id_here).

---

## 🧩 MQL4 & mql4-zmq Installation

The MT4 bridge requires the ZeroMQ library for MQL4:

### 1. Copy ZeroMQ Library & Headers
Place the following files in your MT4 data directory (File ➜ Open Data Folder):
* libzmq.dll ➜ MQL4\Libraries\
* ZeroMQ header files (Zmq.mqh, Context.mqh, Socket.mqh, etc.) ➜ MQL4\Include\Zmq\
* ZeroMQBridge.mqh ➜ MQL4\Include\
* AutoTradeFlagCheck.mqh ➜ MQL4\Include\

### 2. Enable DLL Imports in MT4
1. In MT4, navigate to **Tools ➜ Options ➜ Expert Advisors**.
2. Check **Allow automated trading**.
3. Check **Allow DLL imports**.
4. Uncheck *Confirm DLL function calls*.
5. Click **OK**.

### 3. Attach the EA
* Open any chart (e.g. GBPUSD, H1).
* Drag & drop SmartAutoTradeEA_Pro.mq4 or MT4_ZeroMQ_Bridge.mq4 onto the chart.
* In the **Common** tab, ensure **Allow live trading** and **Allow DLL imports** are checked.
* The terminal will display: [ZMQ Bridge INIT] ZeroMQ REP Server listening on tcp://*:5555.

---

## ⚙️ Configuration (.env)

Create a .env file in the bot root directory:

`env
# ==============================================================================
# MetaTrader 4 Telegram Bot & ZeroMQ Bridge Configuration
# ==============================================================================

# Telegram Bot Token from @BotFather
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# Security: Allowed Telegram Chat ID(s) (Comma-separated for multiple owners)
ALLOWED_CHAT_IDS=your_telegram_chat_id_here

# ZeroMQ Bridge Server (MT4 EA runs REP server on this TCP port)
ZMQ_SERVER_URL=tcp://127.0.0.1:5555
ZMQ_TIMEOUT_MS=3000
ZMQ_RETRY_INTERVAL_SEC=5

# Economic News Reminder Settings
NEWS_REMINDER_LEAD_MINUTES=15
NEWS_IMPACT_FILTER=High,Medium
USER_TIMEZONE=Asia/Baku
BROKER_GMT_OFFSET=3

# Logging Level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO
`

---

## 🚀 Running the Bot

Start the bot locally:
`ash
python bot.py
`

Console Output:
`	ext
2026-09-03 22:46:05 - [INFO] - MT4BridgeBot: Starting 24/7 Telegram bot... Authorized Chat IDs: [your_telegram_chat_id_here]
2026-09-03 22:46:06 - [INFO] - MT4BridgeBot: Successfully synchronized Telegram Menu commands via set_my_commands
2026-09-03 22:46:06 - [INFO] - telegram.ext.Application: Application started
`

---

## 🔄 24/7 Production Service Deployment

### Linux Systemd Service

Create /etc/systemd/system/mt4-telegram-bot.service:
`ini
[Unit]
Description=MetaTrader 4 Institutional Telegram Bot & ZeroMQ Bridge
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/mt4-telegram-bridge
EnvironmentFile=/opt/mt4-telegram-bridge/.env
ExecStart=/usr/bin/python3 -u /opt/mt4-telegram-bridge/bot.py
Restart=always
RestartSec=5s
KillMode=mixed
TimeoutStopSec=10s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
`

Enable and start the service:
`ash
sudo systemctl daemon-reload
sudo systemctl enable mt4-telegram-bot
sudo systemctl start mt4-telegram-bot
sudo systemctl status mt4-telegram-bot
`

### Windows Service via NSSM

1. Download NSSM from [https://nssm.cc/download](https://nssm.cc/download).
2. Open Administrator Command Prompt:
`cmd
nssm install MT4TelegramBot "python.exe" "C:\mt4-telegram-bridge\bot.py"
nssm set MT4TelegramBot AppDirectory "C:\mt4-telegram-bridge"
nssm set MT4TelegramBot AppRestartDelay 5000
nssm set MT4TelegramBot AppExit Default Restart
nssm start MT4TelegramBot
`

### Windows Task Scheduler

Run service\run_bot.bat on system startup via Task Scheduler (	askschd.msc) with **Run with highest privileges** and **If task fails, restart every 1 minute**.

---

## 🛡️ External EA Integration Snippet

Include AutoTradeFlagCheck.mqh in any external MT4 EA to enforce Telegram remote pause/resume:

`mql4
#include <AutoTradeFlagCheck.mqh>

void OnTick()
{
   // 1. Enforce remote Telegram pause state
   if(IsAutoTradePausedByTelegram())
   {
      Comment("\n⚠️ TRADING REMOTELY PAUSED VIA TELEGRAM BOT");
      return; // Do not open new orders while paused
   }
   
   // 2. Normal trading robot logic follows...
}
`

How it works:
1. When you type /pause_bot in Telegram, the bot sets AutoTrading_Paused = 1 in MT4 memory AND writes PAUSED to MQL4\Files\autotrade_state.flag.
2. When you type /resume_bot, it sets AutoTrading_Paused = 0 AND writes ACTIVE to the flag file.
3. If MT4 is offline when paused, the flag file guarantees that trading is paused the moment MT4 is launched!

---

## 🧪 Resilience & Fault-Tolerance Verification

| Scenario | Expected Behavior | Verification Status |
| :--- | :--- | :--- |
| **MT4 Closed / Offline** | Bot stays online. Querying /account, /positions, /history, /modify_sl replies ⚠️ MT4 not connected. Bot does NOT crash or hang. | ✅ **VERIFIED** |
| **MT4 Re-Opened** | Heartbeat thread detects MT4 within 5 seconds. All commands immediately resume live data delivery. | ✅ **VERIFIED** |
| **ISP DNS Drop** | Resilient DNS hook redirects pi.telegram.org to 149.154.166.110. Long-polling never drops. | ✅ **VERIFIED** |
| **Bot Restarted** | Loads data/sent_alerts.json. High-impact news starting in <15m will NOT be re-alerted. | ✅ **VERIFIED** |
| **Interactive Screenshot** | Step 1 renders symbol picker ➜ Step 2 renders timeframes ➜ Step 3 renders chart in MT4 and uploads photo. | ✅ **VERIFIED** |

---

## 📋 Complete /help Command List

All commands are accessible in Telegram's native **[Menu]** button and command guide:

| Command | Arguments | Description |
| :--- | :--- | :--- |
| **/status** | *none* | Live Account Balance, Equity, Margin, Free Margin, Margin Level %, Floating P/L, Leverage, and Server Time. |
| **/positions** | *none* | View all open market positions with tickets, lots, floating profit, and current SL/TP levels. |
| **/screenshot** | [symbol] [timeframe] | Opens the **2-Step Interactive Screenshot Wizard**. (e.g. /screenshot or /screenshot XAUUSD H1). |
| **/prop** | *none* | Prop-Firm Risk Guardian scorecard: Daily Loss limit, Trailing Drawdown, Phase Target progress [■■□□□□□□□□]. |
| **/report** | *none* | 24-hour performance audit: Closed trades count, Win Rate %, Gross Profit/Loss, Profit Factor, Net P/L. |
| **/panic** | *none* | Emergency Kill-Switch: prompts with confirmation button [🚨 CONFIRM EMERGENCY LIQUIDATE ALL] to close all orders. |
| **/close** | [SYMBOL] | Liquidates all open positions for a specific currency pair or commodity (e.g. /close XAUUSD). |
| **/modify_sl** | [TICKET] [PRICE] | Remotely modifies Stop Loss for an open ticket (e.g. /modify_sl 35182476 1.35200). |
| **/modify_tp** | [TICKET] [PRICE] | Remotely modifies Take Profit for an open ticket (e.g. /modify_tp 35182476 1.36000). |
| **/history** | [N / today / lastweek] | Queries closed trades: /history (last 10), /history today, /history lastweek, /history 25. |
| **/colors** | *none* | Synchronizes the GBPUSD black & green/red candlestick color scheme across all open charts in MT4. |
| **/pause** | *none* | Remotely freezes automated trade entries in MT4 and writes PAUSED to utotrade_state.flag. |
| **/resume** | *none* | Remotely re-enables automated trade execution and writes ACTIVE to utotrade_state.flag. |
| **/news** | [week] | Today's High & Medium impact economic events with scheduled Baku (GMT+4) and Broker (GMT+3) times. |
| **/help** | *none* | Displays the interactive Command Center help guide. |
