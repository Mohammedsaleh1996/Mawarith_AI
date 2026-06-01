@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting Mawareth AI Dashboard...
echo URL: http://127.0.0.1:8088
python dashboard_server.py
pause
