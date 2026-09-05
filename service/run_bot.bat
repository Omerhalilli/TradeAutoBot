@echo off
title MT4 Telegram Bot 24/7 Daemon
cd /d "%~dp0\.."
echo [INFO] Starting 24/7 MetaTrader 4 Telegram Bot...
:LOOP
python bot.py
if %ERRORLEVEL% EQU 1 (
    echo [ERROR] Bot exited due to configuration error. Check .env and logs/bot.log.
    pause
    exit /b 1
)
echo [WARNING] Bot process exited with code %ERRORLEVEL%. Auto-restarting in 5 seconds...
timeout /t 5 /nobreak >nul
goto LOOP
