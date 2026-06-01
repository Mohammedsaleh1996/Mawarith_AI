# -*- coding: utf-8 -*-
"""Security smoke tests for Mawareth AI Dashboard v15.
Run while the dashboard is already running on http://127.0.0.1:8088.
"""
import sys
import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8088"
BASE = BASE.rstrip("/")

checks = []

def add(name, ok, detail=""):
    checks.append((name, ok, detail))

# Fresh session without cookies.
s = requests.Session()
try:
    r = s.get(BASE + "/", timeout=8, allow_redirects=False)
    add("GET / requires login page", r.status_code == 200 and ("login" in r.text.lower() or "تسجيل" in r.text), f"status={r.status_code}")
except Exception as e:
    add("GET / requires login page", False, repr(e))

try:
    r = s.get(BASE + "/api/config?mask=true", timeout=8)
    add("GET /api/config without login => 401", r.status_code == 401, f"status={r.status_code}, body={r.text[:120]}")
except Exception as e:
    add("GET /api/config without login => 401", False, repr(e))

try:
    r = s.get(BASE + "/api/logs?limit=1", timeout=8)
    add("GET /api/logs without login => 401", r.status_code == 401, f"status={r.status_code}, body={r.text[:120]}")
except Exception as e:
    add("GET /api/logs without login => 401", False, repr(e))

try:
    r = s.get(BASE + "/webhook/wapilot", timeout=8)
    add("GET /webhook/wapilot remains public", r.status_code == 200 and '"ok"' in r.text, f"status={r.status_code}, body={r.text[:120]}")
except Exception as e:
    add("GET /webhook/wapilot remains public", False, repr(e))

try:
    r = s.get(BASE + "/api/ngrok/detect", timeout=8)
    add("GET /api/ngrok/detect without login => 401", r.status_code == 401, f"status={r.status_code}, body={r.text[:120]}")
except Exception as e:
    add("GET /api/ngrok/detect without login => 401", False, repr(e))

try:
    r = s.post(BASE + "/api/login", json={"username":"admin", "password":"admin123"}, timeout=8)
    add("POST /api/login default admin succeeds", r.status_code == 200 and s.cookies.get("mawareth_session_v15"), f"status={r.status_code}, cookies={list(s.cookies.keys())}")
except Exception as e:
    add("POST /api/login default admin succeeds", False, repr(e))

try:
    r = s.get(BASE + "/api/me", timeout=8)
    add("GET /api/me after login succeeds", r.status_code == 200 and "admin" in r.text, f"status={r.status_code}, body={r.text[:120]}")
except Exception as e:
    add("GET /api/me after login succeeds", False, repr(e))

try:
    r = s.get(BASE + "/api/config?mask=true", timeout=8)
    add("GET /api/config after login succeeds", r.status_code == 200 and '"ok"' in r.text, f"status={r.status_code}, body={r.text[:120]}")
except Exception as e:
    add("GET /api/config after login succeeds", False, repr(e))

failed = [c for c in checks if not c[1]]
for name, ok, detail in checks:
    print(("PASS" if ok else "FAIL") + ": " + name + (" | " + detail if detail else ""))

if failed:
    print(f"SECURITY SMOKE TEST FAILED: {len(failed)}/{len(checks)} failed")
    sys.exit(1)
print(f"SECURITY SMOKE TEST PASSED: {len(checks)}/{len(checks)}")
