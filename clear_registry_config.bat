@echo off
chcp 65001 >nul
echo WARNING: This will delete saved Telegram/WaPilot settings from Windows Registry.
echo Registry path: HKCU\Software\MawarethAI\Dashboard
set /p CONFIRM=Type DELETE to continue: 
if /I not "%CONFIRM%"=="DELETE" (
  echo Cancelled.
  pause
  exit /b 0
)
python - <<PY
from registry_config import delete_registry_config
print('Deleted' if delete_registry_config() else 'Could not delete or not on Windows')
PY
pause
