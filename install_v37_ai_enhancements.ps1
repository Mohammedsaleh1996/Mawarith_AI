# مفتي المواريث الذكي - تثبيت إضافات الذكاء والمحادثة v37
# متوافق مع Python 3.11.9
# شغّله من PowerShell داخل مجلد المشروع:
# powershell -ExecutionPolicy Bypass -File .\install_v37_ai_enhancements.ps1

$ErrorActionPreference = "Stop"
Write-Host "[Mawareth AI] Checking Python..." -ForegroundColor Cyan
python --version

Write-Host "[Mawareth AI] Upgrading pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip setuptools wheel

Write-Host "[Mawareth AI] Installing core dashboard requirements..." -ForegroundColor Cyan
python -m pip install -r requirements_dashboard.txt

Write-Host "[Mawareth AI] Installing v37 intelligence enhancements..." -ForegroundColor Cyan
python -m pip install `
  PyArabic `
  rapidfuzz `
  Babel `
  dateparser `
  tenacity `
  httpx `
  APScheduler `
  structlog `
  keyring

Write-Host "[Mawareth AI] Verifying imports..." -ForegroundColor Cyan
python - <<'PY'
import sys
mods = ["pyarabic", "rapidfuzz", "babel", "dateparser", "tenacity", "httpx", "apscheduler", "structlog", "keyring"]
failed = []
for m in mods:
    try:
        __import__(m)
        print(f"OK: {m}")
    except Exception as e:
        print(f"FAIL: {m} -> {e}")
        failed.append(m)
if failed:
    raise SystemExit(1)
print("All v37 enhancement modules are available.")
PY

Write-Host "[Mawareth AI] Done. Run: .\run_dashboard_full_auto.bat" -ForegroundColor Green
