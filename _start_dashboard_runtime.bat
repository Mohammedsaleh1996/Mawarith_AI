@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Mawareth AI Dashboard
echo ============================================
echo      Mawareth AI Dashboard Launcher
echo ============================================
echo.
if not exist "dashboard_server.py" (
  echo ERROR: dashboard_server.py not found.
  echo Please keep this EXE inside the project folder.
  pause
  exit /b 1
)
python --version >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python is not installed or not added to PATH.
  echo Install Python 3.11+ then run this EXE again.
  pause
  exit /b 1
)
if not exist "data" mkdir "data"
if not exist "data\.requirements_installed" (
  echo First run: installing dashboard requirements...
  python -m pip install -r requirements_dashboard.txt
  if errorlevel 1 (
    echo.
    echo ERROR: requirements installation failed.
    pause
    exit /b 1
  )
  echo ok>"data\.requirements_installed"
)
echo.
echo Starting dashboard on http://127.0.0.1:8088
start "" "http://127.0.0.1:8088"
echo.
echo Keep this window open while using the dashboard.
echo Press CTRL+C here to stop the server.
echo.
python dashboard_server.py
pause
