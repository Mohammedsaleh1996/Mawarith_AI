# -*- coding: utf-8 -*-
import json, sys
from pathlib import Path
from mawarith_ai_runtime_v9 import answer, detect_concept_key

def ok_in(text, arr):
    return all(x in text for x in arr)

def ok_any(text, arr):
    return any(x in text for x in arr)

def main(path='conversation_human_tests_v36.jsonl'):
    total=passed=0
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        total += 1
        item=json.loads(line)
        q=item['question']
        a=answer(q, context={})
        good=True
        if 'must_include' in item:
            good = good and ok_in(a, item['must_include'])
        if 'must_include_any' in item:
            good = good and ok_any(a, item['must_include_any'])
        if 'followup' in item:
            ctx={'last_question':q,'last_answer':a,'last_concept':detect_concept_key(q),'last_dialect':'standard'}
            fa=answer(item['followup'], context=ctx)
            good = good and ok_in(fa, item.get('must_include_followup', []))
            if not good:
                print('FAIL FOLLOWUP:', q, '->', item['followup'], '\n', fa)
        if not good:
            print('FAIL:', q, '\n', a)
        else:
            passed += 1
    print(f'PASSED: {passed}/{total}')
    if passed != total:
        sys.exit(1)

if __name__=='__main__':
    main(sys.argv[1] if len(sys.argv)>1 else 'conversation_human_tests_v36.jsonl')
