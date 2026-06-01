@echo off
chcp 65001 >nul
set RULE=Mawareth AI Dashboard 8088
netsh advfirewall firewall add rule name="%RULE%" dir=in action=allow protocol=TCP localport=8088
pause
