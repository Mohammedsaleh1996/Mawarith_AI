@echo off
chcp 65001 >nul
echo Checking SQL Server status...
python - <<PY
import requests, json
try:
    r=requests.get('http://127.0.0.1:8088/api/sqlserver/status', timeout=10)
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))
except Exception as e:
    print('ERROR:', e)
PY
pause
