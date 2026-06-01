@echo off
chcp 65001 >nul
echo Testing local WAPilot webhook endpoint...
curl -i http://127.0.0.1:8088/webhook/wapilot
echo.
echo Simulating incoming WhatsApp message locally without sending via WAPilot...
curl -X POST http://127.0.0.1:8088/api/wapilot/simulate-incoming -H "Content-Type: application/json" -d "{\"sender\":\"dashboard-test\",\"text\":\"مات شخص وترك 3 بنات وام وعم والتركة 100000 ريال\"}"
echo.
pause
