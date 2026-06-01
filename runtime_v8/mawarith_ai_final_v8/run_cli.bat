@echo off
chcp 65001 >nul
cd /d "%~dp0"
python mawarith_ai_runtime.py
pause
