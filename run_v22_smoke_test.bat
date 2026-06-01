@echo off
chcp 65001 >nul
cd /d "%~dp0"
python run_v22_smoke_test.py
pause
