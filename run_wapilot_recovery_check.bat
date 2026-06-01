@echo off
chcp 65001 >nul
cd /d "%~dp0"
python wapilot_recovery_check.py
pause
