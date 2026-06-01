# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient
import dashboard_server as ds

c = TestClient(ds.app)
print('Running Mawareth AI v22 smoke tests...')
assert c.get('/api/config').status_code == 401, 'config must be protected before login'
assert c.get('/webhook/wapilot').status_code == 200, 'wapilot probe must remain public'
r = c.post('/api/login', json={'username':'admin','password':'admin123','remember':False})
assert r.status_code == 200, r.text
for url in ['/api/me','/api/health/full','/api/conversations/threads','/api/review/items','/api/login-attempts','/api/operational/mode']:
    rr = c.get(url)
    assert rr.status_code == 200, f'{url} -> {rr.status_code}: {rr.text[:200]}'
rr = c.post('/api/system-test/run')
assert rr.status_code == 200, rr.text
print('V22 SMOKE TEST PASSED')
