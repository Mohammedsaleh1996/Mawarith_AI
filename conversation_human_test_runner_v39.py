# -*- coding: utf-8 -*-
import json, sys
from mawarith_ai_runtime_v9 import answer

path = sys.argv[1] if len(sys.argv) > 1 else 'conversation_human_tests_v39.jsonl'
ok=0; total=0
for line in open(path, encoding='utf-8'):
    if not line.strip():
        continue
    t=json.loads(line); total += 1
    out=answer(t['question'], context={})
    good = True
    if t.get('must_include_any'):
        good = good and any(x in out for x in t['must_include_any'])
    if t.get('must_include'):
        good = good and all(x in out for x in t['must_include'])
    if t.get('must_not_include'):
        good = good and not any(x in out for x in t['must_not_include'])
    if good:
        ok += 1
    else:
        print('FAIL:', t['question'])
        print(out)
print(f'PASSED: {ok}/{total}')
if ok != total:
    sys.exit(1)
