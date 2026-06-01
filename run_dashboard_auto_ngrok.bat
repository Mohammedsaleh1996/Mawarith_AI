@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting Mawareth AI Dashboard with automatic ngrok...
echo Local URL: http://127.0.0.1:8088
echo If ngrok.exe is installed or saved in C:\ngrok, the dashboard will start it automatically.
python dashboard_server.py
pause
