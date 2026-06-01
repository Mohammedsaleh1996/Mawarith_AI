# -*- coding: utf-8 -*-
import json, sys
from pathlib import Path
from mawarith_ai_runtime_v9 import answer

def run(path='v41_foundation_tests.jsonl'):
    p=Path(path)
    total=passed=0
    fails=[]
    for line in p.read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        total+=1
        t=json.loads(line)
        q=t['q']; ctx=t.get('context') or {}
        out=answer(q, context=ctx)
        ok=True; reasons=[]
        inc=t.get('must_include_any') or []
        if inc and not any(x in out for x in inc):
            ok=False; reasons.append('missing_any='+str(inc))
        for x in t.get('must_not_include') or []:
            if x in out:
                ok=False; reasons.append('forbidden='+x)
        if ok: passed+=1
        else: fails.append({'q':q,'reasons':reasons,'out':out[:600]})
    print(f'PASSED: {passed}/{total}')
    if fails:
        print(json.dumps(fails,ensure_ascii=False,indent=2))
        return 1
    return 0
if __name__=='__main__':
    sys.exit(run(sys.argv[1] if len(sys.argv)>1 else 'v41_foundation_tests.jsonl'))
