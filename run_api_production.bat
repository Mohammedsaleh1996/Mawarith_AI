chcp 65001 >nul
python -m uvicorn mawarith_api_production:app --host 127.0.0.1 --port 8000
pause
