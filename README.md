# 🤖 TradeAutoBot: MetaTrader 4 Algorithmic Trading Robot & 24/7 Telegram Remote Assistant

[![MetaTrader 4](https://img.shields.io/badge/MetaTrader-4-blue.svg)](https://www.metatrader4.com/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-green.svg)](https://www.python.org/)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot%20API-blue.svg)](https://core.telegram.org/bots)
[![ZeroMQ](https://img.shields.io/badge/ZeroMQ-IPC%20Bridge-orange.svg)](https://zeromq.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **The easiest way to run automated trading on MetaTrader 4 and monitor, inspect, and control your trades from your phone anywhere in the world.**

---

## 📖 Table of Contents
1. [What is TradeAutoBot?](#-what-is-tradeautobot)
2. [How Does It Work?](#-how-does-it-work)
3. [Features at a Glance](#-features-at-a-glance)
4. [Step-by-Step Installation Guide (For Normal People)](#-step-by-step-installation-guide-for-normal-people)
   - [Step 1: Download the Files](#step-1-download-the-files)
   - [Step 2: Install Python Libraries](#step-2-install-python-libraries)
   - [Step 3: Create Your Free Telegram Bot (2 Minutes)](#step-3-create-your-free-telegram-bot-2-minutes)
   - [Step 4: Configure Your Settings (.env)](#step-4-configure-your-settings-env)
   - [Step 5: Install Files into MetaTrader 4](#step-5-install-files-into-metatrader-4)
   - [Step 6: Attach the EA to a Chart](#step-6-attach-the-ea-to-a-chart)
   - [Step 7: Start the Bot](#step-7-start-the-bot)
5. [Telegram Commands Cheatsheet](#-telegram-commands-cheatsheet)
6. [How the AutoTrader Strategy Works (In Plain English)](#-how-the-autotrader-strategy-works-in-plain-english)
7. [Invest-AZ Multi-Account Switcher (Demo vs Real)](#-invest-az-multi-account-switcher-demo-vs-real)
8. [Frequently Asked Questions & Troubleshooting](#-frequently-asked-questions--troubleshooting)
9. [Project Directory Layout](#-project-directory-layout)

---

## 🤔 What is TradeAutoBot?

**TradeAutoBot** consists of two parts that work hand-in-hand:

1. **The AutoTrader Robot (`SmartAutoTradeEA_Pro`)**:
   An institutional-grade Expert Advisor running on your MetaTrader 4 terminal. It watches the market 24 hours a day, analyzes trends and momentum across multiple indicators, and opens BUY or SELL trades automatically with strict Stop Loss, Take Profit, and drawdown protection.

2. **The Telegram Command Center (`bot.py`)**:
   A personal assistant bot on Telegram that talks directly to your MetaTrader 4 in milliseconds. From your smartphone (iPhone/Android) or laptop, you can:
   - Check your account balance, equity, and floating profits.
   - See whether the robot is currently running **BUY** or **SELL** orders.
   - Switch between your **Demo** and **Real** accounts with 1 tap.
   - Request live **chart screenshots** delivered right into your chat.
   - Press an emergency **Panic Button** to close all trades instantly.
   - Receive automatic reminders **15 minutes before high-impact economic news** hits the market.

---

## ⚙️ How Does It Work?

```
 ┌──────────────────────────┐                    ┌──────────────────────────┐
 │   Your Phone (Telegram)  │                    │   ForexFactory Calendar  │
 └────────────┬─────────────┘                    └────────────┬─────────────┘
              │                                               │
              │ Messages & Buttons                            │ High-Impact News Data
              ▼                                               ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                    Python 3 24/7 Daemon (bot.py)                         │
 │   • Listens to your Telegram commands (/status, /positions, /screenshot) │
 │   • Sends 15-minute news alerts before market-moving events              │
 │   • Whitelist security (only YOU can control your terminal)              │
 └────────────────────────────────────┬─────────────────────────────────────┘
                                      │
                                      │ Ultra-Fast ZeroMQ (Port 5555)
                                      ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                 MetaTrader 4 (SmartAutoTradeEA_Pro)                      │
 │   • Embedded ZeroMQ Server (ZeroMQBridge.mqh)                            │
 │   • Multi-EMA Trend + RSI/MACD Momentum Scoring Engine                   │
 │   • Executes & Manages Trades (SL / TP / Trailing Stops)                 │
 │   • Daily Drawdown Circuit Breaker & Real-Time On-Chart HUD              │
 └──────────────────────────────────────────────────────────────────────────┘
```

Everything communicates locally on your machine with virtually zero delay (under 5 milliseconds). If MetaTrader 4 is closed or your internet drops, the bot gracefully informs you and automatically reconnects the moment MT4 comes back online.

---

## ✨ Features at a Glance

* 🤖 **Fully Automated Trading**: 10-point quantitative confluence engine combines Trend (Triple EMA + ADX), Momentum (RSI + MACD), Support & Resistance levels, and Candlestick patterns.
* 👥 **Invest-AZ Account Switcher**: Switch between **Demo** (e.g. Account `1234567`) and **Real** live trading with one tap.
* ⚡ **Live BUY/SELL Trade Diagnostics**: Instantly inspects active order count, total lots, floating P/L, ticket numbers, and stop levels.
* 📸 **Interactive 2-Step Screenshot Wizard**: Pick any symbol (GBPUSD, EURUSD, XAUUSD Gold, BTCUSD, etc.) and timeframe (M1 to D1) to receive an instant high-resolution chart picture in Telegram.
* 🚨 **Emergency Panic Button**: Liquidate all open market orders in one click with a confirmation safety prompt.
* 📅 **Economic News Shield**: Automated alerts 15 minutes before high-impact events with both Baku (`GMT+4`) and Broker (`GMT+3`) times.
* 🛡️ **Prop-Firm / Funded Account Guardian**: Tracks daily drawdown limits, trailing peak drawdown, and profit targets.
* ⏸️ **Remote Pause / Resume**: Freeze new trade entries before big events without closing MetaTrader 4.
* 🎨 **Dark Chart Color Theme**: Synchronize clean black background and green/red candlesticks across all open MT4 charts in one click.
* 🔒 **Ironclad Security**: Protected by an authorized Chat ID whitelist. Unauthorized users cannot see or touch your account.

---

## 🚀 Step-by-Step Installation Guide (For Normal People)

You do **not** need to be a programmer to set this up. Follow these simple steps:

### Prerequisites
1. **MetaTrader 4** installed (e.g. Invest-AZ MT4).
2. **Python 3.10 or higher** installed on Windows.  
   *(When installing Python from [python.org](https://www.python.org/), make sure to check the box that says **"Add Python to PATH"**!)*

---

### Step 1: Download the Files
* **Option A (Easy)**: Click the green **`Code`** button at the top of this GitHub page, then click **`Download ZIP`**. Extract the ZIP folder anywhere on your computer (e.g. your Desktop or Documents).
* **Option B (Git)**:
  ```bash
  git clone https://github.com/Omerhalilli/TradeAutoBot.git
  cd TradeAutoBot
  ```

---

### Step 2: Install Python Libraries
Open Command Prompt (`cmd`) or PowerShell, navigate to the folder, and run:
```bash
pip install -r requirements.txt
```
*(This installs `python-telegram-bot`, `pyzmq`, and `httpx`).*

---

### Step 3: Create Your Free Telegram Bot (2 Minutes)
1. Open the **Telegram** app on your phone or PC.
2. Search for **`@BotFather`** (the official verified Telegram bot maker).
3. Send the message: `/newbot`
4. Follow the prompt to give your bot a name (e.g. `MyInvestAZBot`) and a username ending in `bot` (e.g. `MyInvestAZ_TradeBot`).
5. BotFather will send you a **HTTP API Token** (looks like `1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ_1234567`). **Save this token!**
6. Next, search for **`@userinfobot`** in Telegram and press **Start**.
7. It will reply with your numeric **Id** (e.g. `123456789`). **Save this number!** This ensures only YOU can control the bot.

---

### Step 4: Configure Your Settings (.env)
In the project folder, you will find a file named `.env.example`.
1. Make a copy of `.env.example` and rename it to `.env` (or open `.env` if already present).
2. Open `.env` using **Notepad** and fill in your values:
   ```env
   # Your Bot Token from @BotFather
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

   # Your Numeric User ID from @userinfobot (comma-separated if multiple)
   ALLOWED_CHAT_IDS=your_telegram_chat_id_here

   # Connection settings (leave as default)
   ZMQ_SERVER_URL=tcp://127.0.0.1:5555

   # Timezone settings (Baku is GMT+4, Broker is GMT+3)
   USER_TIMEZONE=Asia/Baku
   BROKER_GMT_OFFSET=3
   ```
3. Save and close the file.

---

### Step 5: Install Files into MetaTrader 4
We have organized the files into an `MQL4` folder to make installation instant:

1. Open your **MetaTrader 4** terminal.
2. Click **File ➜ Open Data Folder** from the top menu. A Windows Explorer folder will open.
3. Simply **copy the `MQL4` folder** from this project into your MetaTrader 4 Data Folder (choose *Merge / Replace* if asked).
   * It places `SmartAutoTradeEA_Pro.ex4` into `MQL4/Experts/`
   * It places `ZeroMQBridge.mqh` and `AutoTradeFlagCheck.mqh` into `MQL4/Include/`
   * It places `libzmq.dll` into `MQL4/Libraries/`
4. In MetaTrader 4, open **Tools ➜ Options ➜ Expert Advisors** and ensure these two boxes are checked:
   * **[✓] Allow automated trading**
   * **[✓] Allow DLL imports**
5. Click **OK**.

---

### Step 6: Attach the EA to a Chart
1. In MT4, open the **Navigator** window (`Ctrl + N`).
2. Expand **Expert Advisors** ➜ Right-click and hit **Refresh**.
3. Drag **`SmartAutoTradeEA_Pro`** onto any chart window (e.g. `GBPUSD`, `H1`).
4. In the settings window:
   * Check **[✓] Allow live trading**
   * Check **[✓] Allow DLL imports**
   * Click **OK**.
5. Ensure the big **AutoTrading** button in the MT4 top toolbar is turned **GREEN** (active).
6. You will see the trading dashboard HUD appear directly on your chart!

---

### Step 7: Start the Bot
Simply **double-click `run_bot.bat`** in the main folder!

*(If you prefer running from the terminal: `python bot.py`)*

You will see:
```text
[INFO] Starting 24/7 MetaTrader 4 Telegram Bot...
[INFO] News alert background scheduler registered (every 60s)
[INFO] Bot application initialized. Starting polling...
```

Now open Telegram, find your bot, and send **`/start`**! 🎉

---

## 📱 Telegram Commands Cheatsheet

Everything is also accessible directly through Telegram's blue **`[Menu]`** button in your chat:

| Command | Action | Description |
| :--- | :--- | :--- |
| **`/boost`** or **`/turbo`** | ⚡ Turbo Boost | Instant 4 Hz telemetry, roundtrip latency (ms), major pair spreads, and one-touch actions. |
| **`/accounts`** or **`/switch`** | 👥 Switch Accounts | Toggle between Invest-AZ Demo and Real accounts with instant BUY/SELL diagnostics. |
| **`/status`** or **`/account`** | 📊 Account Overview | Check live balance, equity, used margin, free margin, margin level %, and server time. |
| **`/positions`** | 💼 Open Positions | List of all currently open market trades with ticket numbers, lots, and floating P/L. |
| **`/screenshot`** | 📸 Chart Photo | Interactive wizard: Pick symbol ➜ Pick timeframe ➜ Receive high-res chart photo. |
| **`/prop`** | 🛡️ Risk Guardian | Prop-firm scorecard showing daily loss limit, peak trailing drawdown, and phase targets. |
| **`/report`** | 📈 24h Performance | Audit summary of the last 24 hours: win rate %, profit factor, gross profit, and net P/L. |
| **`/panic`** | 🚨 Kill-Switch | Emergency button to immediately close **all** open trades with confirmation. |
| **`/close <SYMBOL>`** | ❌ Close Symbol | Closes all open trades for a specific pair (e.g. `/close XAUUSD` or `/close GBPUSD`). |
| **`/modify_sl <TICKET> <PRICE>`** | 🎯 Modify Stop Loss | Remotely change Stop Loss price on an open order. |
| **`/modify_tp <TICKET> <PRICE>`** | 💰 Modify Take Profit | Remotely change Take Profit price on an open order. |
| **`/news`** or **`/calendar`** | 📅 Economic News | Today's High & Medium impact events (use `/news week` for the full week). |
| **`/history`** | 📜 Closed Trades | View your last 10 closed deals (use `/history today` or `/history 20`). |
| **`/pause`** | ⏸️ Pause Robot | Freezes automated entries in MT4 without turning off your computer. |
| **`/resume`** | ▶️ Resume Robot | Unfreezes automated entries and resumes scanning for trading setups. |
| **`/colors`** | 🎨 Sync Colors | Applies institutional dark chart theme and green/red candles to all open charts. |
| **`/help`** | 🤖 Help Menu | Displays the full interactive command guide. |

---

## 🧠 How the AutoTrader Strategy Works (In Plain English)

The **SmartAutoTradeEA_Pro** algorithm does not guess. It uses a **10-Point Multi-Factor Confluence Matrix**:

```
 ┌────────────────────────────────────────────────────────┐
 │            10-POINT CONFLUENCE SCORING SYSTEM          │
 ├────────────────────────────────┬───────────────────────┤
 │ 1. Trend Direction (EMA 20/50) │ 2 Points              │
 │ 2. Long-Term Bias (EMA 200)    │ 2 Points              │
 │ 3. Trend Strength (ADX > 22)   │ 1 Point               │
 │ 4. RSI Momentum Dynamic Zones  │ 1 Point               │
 │ 5. MACD Signal Line Crossover  │ 1 Point               │
 │ 6. Key Support/Resistance Zone │ 1 Point               │
 │ 7. Pivot Points Proximity      │ 1 Point               │
 │ 8. Candlestick Confirmation    │ 1 Point               │
 ├────────────────────────────────┴───────────────────────┤
 │ Minimum Score Required to Trade: 6 / 10 Points         │
 └────────────────────────────────────────────────────────┘
```

### Risk Guardian & Protection Rules:
1. **Mandatory Stop Loss & Take Profit**: Every single trade has a mathematically calculated Stop Loss (based on ATR volatility and swing points). A trade is never left unprotected.
2. **Daily Loss Circuit Breaker**: If daily losses exceed the user-defined threshold (default 4.5%), the robot halts trading for the rest of the day to protect your capital.
3. **Spread Protection**: The robot automatically refuses to enter trades if broker spread spikes beyond acceptable limits (e.g. during major news).
4. **Weekend Shield**: Automatically manages exposure before the Friday market close.

---

## 👥 Invest-AZ Multi-Account Switcher (Demo vs Real)

When you send `/accounts` (or `/switch`) in Telegram, you get an interactive menu:

```text
👥 INVEST-AZ ACCOUNT SWITCHER & TRADE INSPECTOR
━━━━━━━━━━━━━━━━━━━━━━━━━━
🟢 Current Active Target: Invest-AZ Demo
• Number: 1234567
• Server: InvestAZ-Demo
• ZMQ Port: tcp://127.0.0.1:5555
━━━━━━━━━━━━━━━━━━━━━━━━━━
👇 Select an account below to switch control and inspect BUY/SELL functionality:
[ 🟢 🟡 DEMO — Invest-AZ Demo (1234567) [ACTIVE] ]
[ ⚪ 🔴 REAL — Invest-AZ Real (Real Live) ]
[ 🔄 Refresh Panel ]
```

### What happens when you tap an account?
1. The bot switches all remote controls (`/status`, `/positions`, `/close`, `/panic`) to that account.
2. It audits your positions and displays a **BUY / SELL Function Diagnostic**:
   ```text
   👥 ACCOUNT #1: INVEST-AZ DEMO [🟢 ACTIVE]
   ━━━━━━━━━━━━━━━━━━━━━━━━━━
   🔢 Account Number: 1234567 (🟡 DEMO)
   🏢 Broker: Invest-AZ Investment Company CJSC
   🌐 Server: InvestAZ-Demo
   💰 Balance / Equity: $10,000.00 / $10,000.00
   📊 Margin: $0.00 | Free: $10,000.00 (∞)
   📈 Floating P/L: +$0.00 USD
   ⏰ Server Time: 2026.09.04 09:26:04
   ━━━━━━━━━━━━━━━━━━━━━━━━━━
   ⚡ BUY / SELL FUNCTION DIAGNOSTICS:

   🟢 BUY FUNCTION: No active BUY positions running.
   🔴 SELL FUNCTION: No active SELL positions running.
   ━━━━━━━━━━━━━━━━━━━━━━━━━━
   [ 💼 Open Positions ]  [ 📸 Screenshot ]
   [ 🚨 Panic / Close ]   [ 👥 Switch Account ]
   ```
3. **Smart Terminal Detection**:  
   If you select **Real** in Telegram while your MetaTrader 4 terminal is currently logged into **Demo**, the bot automatically detects this and tells you:
   > ⚠️ **NOTICE:** *Target set to REAL, but your MT4 terminal is currently logged into DEMO (1234567).*  
   > 💡 *To execute on REAL: Open MT4 Navigator (Ctrl+N) ➜ Double-click your Real account to log in.*

---

## ❓ Frequently Asked Questions & Troubleshooting

#### Q: The bot says "⚠️ MT4 not connected". What should I do?
1. Make sure your MetaTrader 4 terminal is open and running.
2. Make sure `SmartAutoTradeEA_Pro` is attached to a chart (check for the smiling face in the top-right corner of the chart).
3. Make sure **Allow DLL imports** is checked in MT4 (**Tools ➜ Options ➜ Expert Advisors**).

#### Q: Can other people message my bot and close my trades?
**No.** The bot has an authorized chat whitelist (`ALLOWED_CHAT_IDS` in `.env`). Anyone else who messages your bot will receive an `Access Denied` alert and their commands will be blocked.

#### Q: How do I keep it running 24/7 if I turn off my computer?
If you turn off your PC, MetaTrader 4 stops running. To keep it running 24/7 without your PC on:
* Run it on a cheap Windows VPS (Virtual Private Server) from providers like ForexVPS, Contabo, or OVH.
* Or use a free Oracle Cloud Always-Free tier instance (see [`service/oracle_cloud_guide.md`](service/oracle_cloud_guide.md)).

#### Q: How do I temporarily stop trading during big news?
Just send **`/pause`** in Telegram! The robot will stop looking for new entries. When the news passes, send **`/resume`** to turn it back on.

---

## 📁 Project Directory Layout

```text
TradeAutoBot/
├── MQL4/                       # Copy this entire folder into MT4 Data Folder!
│   ├── Experts/
│   │   ├── SmartAutoTradeEA_Pro.ex4   # Compiled ready-to-run trading robot
│   │   └── SmartAutoTradeEA_Pro.mq4   # Full EA source code with embedded ZeroMQ
│   ├── Include/
│   │   ├── ZeroMQBridge.mqh           # ZeroMQ communication bridge & screenshot engine
│   │   ├── TelegramShared.mqh         # Unicode-safe Telegram emoji definitions
│   │   └── AutoTradeFlagCheck.mqh     # Remote pause checker for external EAs
│   └── Libraries/
│       └── libzmq.dll                 # High-speed ZeroMQ Windows library
├── bot.py                      # Main Telegram bot daemon with 24/7 auto-reconnect
├── handlers.py                 # Telegram command handlers & interactive screenshot wizard
├── account_manager.py          # Invest-AZ Demo & Real multi-account switcher
├── zmq_client.py               # ZeroMQ client with heartbeat recovery
├── news_service.py             # ForexFactory scraper & 15-minute news reminders
├── config.py                   # Configuration (.env) and rotating logger
├── run_bot.bat                 # 1-Click launcher for Windows
├── requirements.txt            # Python dependencies
├── .env.example                # Configuration template
├── data/                       # Persistent account settings and alert cache
├── logs/                       # Rotating bot logs
└── service/                    # 24/7 background service scripts (Linux & Windows)
```

---

## 📄 License
This project is open-source under the **MIT License**. Created for institutional and personal automated trading.
