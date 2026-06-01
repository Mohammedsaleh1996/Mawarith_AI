@echo off
chcp 65001 >nul
echo Removing Windows startup task for Mawareth AI Dashboard...
schtasks /Delete /TN "MawarethAI_Dashboard" /F
pause
