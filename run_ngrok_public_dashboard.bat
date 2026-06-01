@echo off
chcp 65001 >nul
echo Starting ngrok public tunnel for Mawareth AI Dashboard...
echo Dashboard local port: 8088
echo.
where ngrok >nul 2>nul
if errorlevel 1 (
  echo ngrok.exe مش موجود في PATH.
  echo نزّله أو ضع ngrok.exe بجانب هذا الملف ثم شغّل الأمر يدويًا:
  echo ngrok http 8088
  pause
  exit /b 1
)
ngrok http 8088
pause
