@echo off
chcp 65001 >nul
powershell -ExecutionPolicy Bypass -File "%~dp0install_v37_ai_enhancements.ps1"
pause
