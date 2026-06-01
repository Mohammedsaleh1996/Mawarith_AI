@echo off
chcp 65001 >nul
echo Running SQL Server sync now...
python - <<PY
import requests, json
try:
    r=requests.post('http://127.0.0.1:8088/api/sqlserver/sync-now', timeout=60)
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))
except Exception as e:
    print('ERROR:', e)
PY
pause
