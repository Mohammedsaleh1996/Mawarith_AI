@echo off
chcp 65001 >nul
cd /d "%~dp0"
python stress_test_runner.py
pause
