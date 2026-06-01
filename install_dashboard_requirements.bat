@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install -r requirements_dashboard.txt
pause
