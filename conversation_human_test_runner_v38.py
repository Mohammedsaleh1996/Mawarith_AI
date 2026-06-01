# -*- coding: utf-8 -*-
import json, sys
from mawarith_ai_runtime_v9 import answer

def main():
    ok=0; total=0
    for line in open('conversation_human_tests_v38.jsonl',encoding='utf-8'):
        if not line.strip(): continue
        t=json.loads(line); total+=1
        out=answer(t['question'], context={})
        if any(x in out for x in t.get('must_include_any', [])) and not any(x in out for x in t.get('must_not_include', [])):
            ok+=1
        else:
            print('FAIL:', t['question'])
            print(out)
    print(f'PASSED: {ok}/{total}')
    if ok!=total: sys.exit(1)
if __name__=='__main__': main()
