@echo off
chcp 65001 >nul
cd /d "%~dp0"
set MAWARETH_FULL_AUTO=1
echo ==========================================================
echo  Mawareth AI Dashboard - Full Auto Boot
echo ==========================================================
echo Dashboard local: http://127.0.0.1:8088
echo Mobile/LAN:      http://YOUR-PC-IP:8088
echo ngrok:           will auto-start if ngrok.exe is available
echo WaPilot webhook: will auto-update to https://.../webhook/wapilot
echo ==========================================================
python dashboard_server.py
pause
