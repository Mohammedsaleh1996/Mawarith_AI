@echo off
chcp 65001 >nul
echo Starting Cloudflare Quick Tunnel for Mawareth AI Dashboard...
echo Dashboard local port: 8088
where cloudflared >nul 2>nul
if errorlevel 1 (
  echo cloudflared مش موجود في PATH.
  echo نزّله من Cloudflare ثم شغّل:
  echo cloudflared tunnel --url http://localhost:8088
  pause
  exit /b 1
)
cloudflared tunnel --url http://localhost:8088
pause
