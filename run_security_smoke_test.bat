@echo off
chcp 65001 >nul
python security_smoke_test.py http://127.0.0.1:8088
pause
