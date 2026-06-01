@echo off
chcp 65001 >nul
echo Checking ngrok discovery from CMD...
where ngrok
if errorlevel 1 echo where ngrok did not find ngrok.
echo.
echo Checking ngrok version through command alias...
ngrok version
echo.
echo If ngrok version appears above, the dashboard can start ngrok by command name even if installed from Windows Store.
pause
