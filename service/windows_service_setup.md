# 24/7 Windows Service & Daemon Deployment Guide

This guide describes how to run the MT4 Telegram Bot continuously in the background on Windows with automatic restart on failure.

---

## Method 1: Windows Service via NSSM (Recommended for 24/7 Production)

NSSM (Non-Sucking Service Manager) is the industry-standard tool to run any executable/script as a resilient native Windows Service.

### 1. Download NSSM
1. Download NSSM from [https://nssm.cc/download](https://nssm.cc/download) (or install via Chocolatey: choco install nssm / winget).
2. Extract 
ssm.exe (from win64/) to C:\Windows\System32\ or your bot directory.

### 2. Install the Service
Open an Administrator PowerShell / Command Prompt:
`cmd
nssm install MT4TelegramBot "python.exe" "C:\mt4-telegram-bridge\bot.py"
nssm set MT4TelegramBot AppDirectory "C:\mt4-telegram-bridge"
nssm set MT4TelegramBot Description "MT4 Telegram Bot & ZeroMQ Bridge 24/7"
`

### 3. Configure Auto-Restart & Resilience
`cmd
nssm set MT4TelegramBot AppRestartDelay 5000
nssm set MT4TelegramBot AppExit Default Restart
nssm set MT4TelegramBot AppStdout "C:\mt4-telegram-bridge\logs\service_stdout.log"
nssm set MT4TelegramBot AppStderr "C:\mt4-telegram-bridge\logs\service_stderr.log"
`

### 4. Start the Service
`cmd
nssm start MT4TelegramBot
`
To check status or stop:
`cmd
nssm status MT4TelegramBot
nssm stop MT4TelegramBot
`

---

## Method 2: Windows Task Scheduler (No Third-Party Tools)

To automatically launch the bot on Windows logon and keep it running:

1. Open **Task Scheduler** (	askschd.msc).
2. Click **Create Task...**
   - Name: MT4TelegramBot
   - Check **Run whether user is logged on or not**
   - Check **Run with highest privileges**
3. **Triggers Tab**:
   - New ➜ Begin the task: **At startup** (or **At log on**).
4. **Actions Tab**:
   - Action: **Start a program**
   - Program/script: C:\mt4-telegram-bridge\service\run_bot.bat
   - Start in: C:\mt4-telegram-bridge
5. **Settings Tab**:
   - Check: **If the task fails, restart every: 1 minute**
   - Attempt to restart up to: **99 times**
   - Uncheck: *Stop the task if it runs longer than...*
6. Click **OK** and save.

---

## Method 3: Self-Healing Batch Script Loop (un_bot.bat)

For manual or desktop execution, simply run:
`cmd
service\run_bot.bat
`
If Python encounters any fatal crash or network drop, the batch loop automatically restarts it after 5 seconds indefinitely.
