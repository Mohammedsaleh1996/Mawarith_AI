# -*- coding: utf-8 -*-
import json, sys
import dashboard_server as d

def main():
    ok=0; total=0
    with open('v43_human_guard_tests.jsonl','r',encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            total+=1
            t=json.loads(line)
            ans=d.ask_runtime(t['question'], channel='test', user_id='v43', user_name='Elsaleh', raw={})['answer']
            fail=[]
            for x in t.get('must_include',[]):
                if x not in ans: fail.append(f'missing {x}')
            for x in t.get('must_not_include',[]):
                if x in ans: fail.append(f'forbidden {x}')
            if fail:
                print('FAIL:',t['question'],fail,'\nANS:',ans[:500])
            else:
                ok+=1
    print(f'PASSED: {ok}/{total}')
    if ok!=total: sys.exit(1)
if __name__=='__main__': main()
