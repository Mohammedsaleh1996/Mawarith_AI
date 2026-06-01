
# -*- coding: utf-8 -*-
"""Local smoke test for settings secret-preserve guard.
Run while dashboard is running: python settings_guard_smoke_test.py
"""
import json, urllib.request
BASE='http://127.0.0.1:8088'

def get(path):
    return json.loads(urllib.request.urlopen(BASE+path, timeout=10).read().decode('utf-8'))

def post(path, payload):
    data=json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req=urllib.request.Request(BASE+path, data=data, headers={'Content-Type':'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))

before=get('/api/config?mask=True')
print('before telegram:', before.get('telegram',{}).get('bot_token_masked'))
print('before wapilot:', before.get('wapilot',{}).get('api_token_masked'))
res=post('/api/config', {
  'telegram': {'bot_token': ''},
  'wapilot': {'api_token': '', 'instance_id': before.get('wapilot',{}).get('instance_id','')},
})
print('save response:', res)
after=get('/api/config?mask=True')
print('after telegram:', after.get('telegram',{}).get('bot_token_masked'))
print('after wapilot:', after.get('wapilot',{}).get('api_token_masked'))
assert before.get('telegram',{}).get('bot_token_masked') == after.get('telegram',{}).get('bot_token_masked')
assert before.get('wapilot',{}).get('api_token_masked') == after.get('wapilot',{}).get('api_token_masked')
print('OK: blank token fields preserved both integrations')
