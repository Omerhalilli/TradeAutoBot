Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\mt4-telegram-bridge"
WshShell.Run "pythonw.exe bot.py", 0, False
