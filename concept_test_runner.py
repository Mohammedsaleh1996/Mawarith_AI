# -*- coding: utf-8 -*-
import json, argparse, datetime
from pathlib import Path
from mawarith_ai_runtime_v9 import answer, normalize_ar, detect_concept_key


def run_tests(test_file: str, report_file: str = "concept_report_v1.json") -> int:
    tests=[]
    with open(test_file,'r',encoding='utf-8') as f:
        for line in f:
            if line.strip(): tests.append(json.loads(line))
    passed=0; failed=[]; per={}
    for t in tests:
        ctx={}
        outputs=[]; ok=True; missing=[]; forbidden=[]
        turns=t.get('turns') or [t.get('q','')]
        for q in turns:
            out=answer(q, context=ctx)
            outputs.append({'q':q,'answer':out})
            ctx={'last_question':q,'last_answer':out,'last_concept':detect_concept_key(q) or ctx.get('last_concept')}
        final=outputs[-1]['answer'] if outputs else ''
        norm=normalize_ar(final)
        for m in t.get('must',[]):
            if normalize_ar(m) not in norm:
                ok=False; missing.append(m)
        for m in t.get('must_not',[]):
            if normalize_ar(m) in norm:
                ok=False; forbidden.append(m)
        cat=t.get('category','concept')
        per.setdefault(cat,{'passed':0,'total':0}); per[cat]['total']+=1
        if ok:
            passed+=1; per[cat]['passed']+=1
        else:
            failed.append({'id':t.get('id'), 'category':cat, 'turns':turns, 'missing':missing, 'forbidden':forbidden, 'outputs':outputs})
    report={'created_at':datetime.datetime.now().isoformat(timespec='seconds'), 'test_file':test_file, 'passed':passed, 'total':len(tests), 'failed_count':len(failed), 'per_category':per, 'failed':failed[:50]}
    with open(report_file,'w',encoding='utf-8') as f: json.dump(report,f,ensure_ascii=False,indent=2)
    print(f"PASSED: {passed}/{len(tests)}")
    for c,d in sorted(per.items()): print(f"- {c}: {d['passed']}/{d['total']}")
    print(f"Report written to: {report_file}")
    if failed:
        print('FAILED TESTS:')
        for x in failed[:10]:
            print('#',x['id'],x['category'],x['turns']); print('Missing:',x['missing']); print('Forbidden:',x['forbidden']); print(x['outputs'][-1]['answer']); print('-'*60)
        return 1
    print('All dynamic concept tests passed.')
    return 0

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--tests',default='concept_tests_v1.jsonl'); ap.add_argument('--report',default='concept_report_v1.json')
    args=ap.parse_args(); raise SystemExit(run_tests(args.tests,args.report))
