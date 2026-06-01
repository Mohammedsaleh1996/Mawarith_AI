$ErrorActionPreference = "Stop"

Write-Host "[Mawareth AI] Checking Python..." -ForegroundColor Cyan
python --version

Write-Host "[Mawareth AI] Upgrading pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip setuptools wheel

if (Test-Path ".\requirements_dashboard.txt") {
    Write-Host "[Mawareth AI] Installing core dashboard requirements..." -ForegroundColor Cyan
    python -m pip install -r ".\requirements_dashboard.txt"
} else {
    Write-Host "[Mawareth AI] requirements_dashboard.txt not found, skipping core requirements." -ForegroundColor Yellow
}

Write-Host "[Mawareth AI] Installing v37 intelligence enhancements..." -ForegroundColor Cyan
$packages = @(
    "PyArabic",
    "rapidfuzz",
    "Babel",
    "dateparser",
    "tenacity",
    "httpx",
    "APScheduler",
    "structlog",
    "keyring"
)

python -m pip install @packages

Write-Host "[Mawareth AI] Verifying imports..." -ForegroundColor Cyan
$verifyScript = @'
mods = [
    "pyarabic",
    "rapidfuzz",
    "babel",
    "dateparser",
    "tenacity",
    "httpx",
    "apscheduler",
    "structlog",
    "keyring",
]
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
'@

$tempFile = Join-Path $env:TEMP "mawareth_ai_verify_imports.py"
Set-Content -Path $tempFile -Value $verifyScript -Encoding UTF8
python $tempFile
Remove-Item $tempFile -Force -ErrorAction SilentlyContinue

Write-Host "[Mawareth AI] Done. Run: .\run_dashboard_full_auto.bat" -ForegroundColor Green
