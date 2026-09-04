# 🤖 TradeAutoBot

> **Resilient 24/7 Telegram Command Center & ZeroMQ Bridge for MetaTrader 4**

TradeAutoBot connects MetaTrader 4 (MT4) directly to Telegram using an ultra-low-latency ZeroMQ IPC channel. It allows traders to monitor accounts, manage active positions, execute emergency closes, receive automated high-impact economic news reminders, and capture on-demand chart screenshots using an interactive multi-step wizard.

---

## ⚡ Key Features

* **📸 Interactive 2-Step Screenshot Wizard**: /screenshot presents an interactive instrument picker (GBPUSD, EURUSD, XAUUSD, USDJPY, BTCUSD, USOIL, Active Chart) followed by a timeframe selector (M1 to D1), automatically rendering and returning high-res 1280x720 chart images.
* **🛡️ 24/7 Self-Healing Resilience**: Decoupled Python architecture. If MT4 closes or restarts, the bot gracefully replies ⚠️ MT4 not connected, checks connectivity every 5 seconds, and auto-reconnects when MT4 returns.
* **📅 Economic Calendar & News Shield**: Automatically fetches high/medium impact events from ForexFactory and broadcasts 15-minute lead warnings. Dispatched alerts persist across bot reboots to avoid duplicate spam.
* **📊 Remote Trade & Risk Management**: Live account metrics (/status), open positions (/positions), closed trade history (/history), 24h performance audit (/report), and prop-firm drawdown tracker (/prop).
* **👥 Multi-Account & Profile Switcher**: `/accounts` or `/switch` displays an interactive inline panel to switch between multiple accounts (e.g. Invest-AZ Demo, Prop-Firm Challenge, Live Scalper). Instantly inspects whether the selected account has active **BUY or SELL** functions running with real-time exposure breakdown.
* **🚨 Emergency Controls**: Remote emergency kill-switch (/panic or /closeall with confirmation buttons), single-symbol liquidation (/close), SL/TP modification (/modify_sl, /modify_tp), and remote autotrade pause (/pause, /resume).
* **🔒 Security**: Whitelist-restricted to authorized Telegram Chat IDs defined in .env.

---

## 📋 Command Reference

| Command | Description |
| :--- | :--- |
| **/accounts** | **Multi-Account Profile Switcher**: Switch accounts & inspect active BUY/SELL functions |
| **/status** | Balance, Equity, Margin, Free Margin, Floating P/L & Server Time |
| **/positions** | View all open market orders with floating P/L and SL/TP |
| **/screenshot** | **Interactive 2-step screenshot wizard** (Select Symbol ➜ Select Timeframe) |
| **/prop** | Prop-Firm Risk Guardian scorecard (Daily loss limit, Trailing DD, Target progress) |
| **/report** | 24-hour performance summary (Win rate %, Profit Factor, Net P/L, best/worst trade) |
| **/panic** | Emergency kill-switch to liquidate all positions with interactive confirmation |
| **/close <SYMBOL>** | Liquidate all open trades for a specific symbol (e.g. /close XAUUSD) |
| **/modify_sl <TICKET> <PRICE>** | Update Stop Loss for an open ticket |
| **/modify_tp <TICKET> <PRICE>** | Update Take Profit for an open ticket |
| **/history [N/today/lastweek]** | Closed trade history with ticket, price, and net P/L |
| **/colors** | Synchronize GBPUSD dark candlestick color theme across all open MT4 charts |
| **/pause** | Pause automated trade entries (sets global variable and writes autotrade_state.flag) |
| **/resume** | Resume automated trade entries |
| **/news [week]** | Upcoming high/medium impact events in user (GMT+4) and broker (GMT+3) times |
| **/help** | Displays interactive command guide |

---

## 🚀 Quick Setup

### 1. Python Environment
`ash
pip install -r requirements.txt
`

### 2. Configuration (.env)
Copy .env.example to .env and fill in your credentials:
`env
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
ALLOWED_CHAT_IDS=your_telegram_chat_id
ZMQ_SERVER_URL=tcp://127.0.0.1:5555
USER_TIMEZONE=Asia/Baku
BROKER_GMT_OFFSET=3
`

### 3. MT4 Setup
1. Copy libzmq.dll into MQL4/Libraries/.
2. Copy ZeroMQBridge.mqh and AutoTradeFlagCheck.mqh into MQL4/Include/.
3. In MT4: **Tools ➜ Options ➜ Expert Advisors** ➜ Enable **[✓] Allow automated trading** and **[✓] Allow DLL imports**.
4. Attach SmartAutoTradeEA_Pro.mq4 (or MT4_ZeroMQ_Bridge.mq4) to any chart (e.g. GBPUSD, H1).

### 4. Run Bot
`ash
python bot.py
`
*(Windows Service and Linux systemd configurations are available in service/)*.

---

## 🔌 External EA Remote Pause Integration

To allow external trading robots to honor Telegram /pause and /resume commands, include AutoTradeFlagCheck.mqh:

`mql4
#include <AutoTradeFlagCheck.mqh>

void OnTick()
{
   if(IsAutoTradePausedByTelegram())
   {
      Comment("\n⚠️ TRADING REMOTELY PAUSED VIA TELEGRAM");
      return; // Freeze new order execution
   }
   
   // Normal strategy logic...
}
`

---

## 📁 Project Structure

`	ext
├── bot.py                  # Main Telegram bot daemon with 24/7 reconnect loop
├── handlers.py             # Telegram command & interactive screenshot wizard handlers
├── account_manager.py      # Multi-account & profile registry, active switcher, and persistence
├── zmq_client.py           # ZeroMQ client with dynamic endpoint switching & auto-reconnect
├── news_service.py         # Economic calendar scraper with persistent sent-alerts cache
├── config.py               # Configuration loader (.env, config.ini) & rotating file logger
├── AutoTradeFlagCheck.mqh  # Modular MQL4 header to pause external trading robots
├── ZeroMQBridge.mqh        # Core MQL4 ZeroMQ REP server & chart screenshot engine
├── SmartAutoTradeEA_Pro.mq4# Complete trading robot with integrated ZeroMQ bridge
├── requirements.txt        # Python dependencies (python-telegram-bot, pyzmq, httpx)
├── .env.example            # Environment variables template
└── service/                # Linux systemd unit & Windows service setup scripts
`

---

## 📄 License
MIT License. Created for institutional algorithmic trading.
