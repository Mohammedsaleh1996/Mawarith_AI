# -*- coding: utf-8 -*-
import json, sys
from pathlib import Path
from mawarith_ai_runtime_v9 import answer
from human_conversation_enhancer import is_pure_social_message

TESTS = Path('conversation_human_tests_v40.jsonl')
failed=[]
for i,line in enumerate(TESTS.read_text(encoding='utf-8').splitlines(),1):
    if not line.strip(): continue
    t=json.loads(line)
    q=t['q']
    a=answer(q, context={})
    # in full dashboard, social gets hard-guarded too; runtime should also pass
    for bad in t.get('must_not_include',[]):
        if bad in a:
            failed.append((i,q,'must_not_include',bad,a))
    inc=t.get('must_include_any') or []
    if inc and not any(x in a for x in inc):
        failed.append((i,q,'must_include_any',inc,a))
if failed:
    print('FAILED', len(failed))
    for f in failed:
        print('\nCASE', f[0], f[1], f[2], f[3], '\nANSWER:', f[4])
    sys.exit(1)
print('PASSED: v40 natural chat tests')
