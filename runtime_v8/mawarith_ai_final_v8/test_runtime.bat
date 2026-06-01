@echo off
chcp 65001 >nul
cd /d "%~dp0"
python quick_test.py
pause
