# -*- coding: utf-8 -*-
import json, sys, urllib.request
url = 'http://127.0.0.1:8088/api/wapilot/recovery-check'
try:
    with urllib.request.urlopen(url, timeout=10) as r:
        data = json.loads(r.read().decode('utf-8'))
except Exception as e:
    print('FAILED to call dashboard recovery endpoint:', type(e).__name__, e)
    print('تأكد أن الداشبورد شغال على http://127.0.0.1:8088')
    sys.exit(1)
print(json.dumps(data, ensure_ascii=False, indent=2))
if not data.get('ok'):
    print('\nإجراءات مطلوبة:')
    for a in data.get('actions', []):
        print('-', a)
