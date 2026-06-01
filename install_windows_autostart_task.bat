@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Installing Windows startup task for Mawareth AI Dashboard...
schtasks /Create /TN "MawarethAI_Dashboard" /SC ONLOGON /RL LIMITED /TR "\"%~dp0Start_Mawareth_AI_Dashboard.exe\"" /F
if %ERRORLEVEL% EQU 0 (
  echo Done. The dashboard launcher will start when this Windows user logs in.
) else (
  echo Failed to create task. Try running this file as Administrator.
)
pause
