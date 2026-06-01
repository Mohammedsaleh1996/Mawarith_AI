@echo off
chcp 65001 >nul
cd /d "%~dp0"
python mawarith_api.py
pause
