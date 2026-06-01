@echo off
chcp 65001 >nul
set /p TO=اكتب رقم واتساب المستلم بصيغة دولية بدون + أو معها: 
set /p MSG=اكتب رسالة اختبار الإرسال: 
powershell -NoProfile -ExecutionPolicy Bypass -Command "$body=@{to='%TO%';message='%MSG%'} | ConvertTo-Json -Compress; Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8088/api/wapilot/test-send' -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 8"
pause
