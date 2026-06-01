@echo off
chcp 65001 >nul
set PUBLIC_URL=https://favorable-erased-hatbox.ngrok-free.dev/webhook/wapilot
echo Testing public ngrok WAPilot webhook URL: %PUBLIC_URL%
curl -i %PUBLIC_URL%
echo.
echo If this does not return JSON with ok=true, then ngrok is not pointing to this dashboard/port or the URL changed.
pause
