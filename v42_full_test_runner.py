# -*- coding: utf-8 -*-
from __future__ import annotations
import json
from pathlib import Path
from v42_full_intelligence import classify, social_reply, should_send_processing_notice, should_use_fatwa_preamble, followup_response

TESTS = [
    {"q":"السلام عليكم كيف حالك", "intent":"social_greeting_status", "not_contains":["تفضل بسؤالك", "بسم الله", "تحليل المسألة"]},
    {"q":"كيف حالك", "intent":"social_status", "not_contains":["وعليكم السلام", "تفضل بسؤالك", "بسم الله"]},
    {"q":"مساء الفل", "intent":"social_greeting", "not_contains":["بسم الله", "اكتب السؤال"]},
    {"q":"ما معنى الحجب؟", "intent":"fiqh_question"},
    {"q":"مات شخص وترك زوجة وبنت وأخ شقيق", "intent":"calculation"},
    {"q":"ما افهم", "intent":"followup_simplify"},
    {"q":"هات مثال بالأرقام", "intent":"followup_example"},
    {"q":"مات شخص ثم ماتت زوجته", "intent":"advanced_or_composite"},
]

def main():
    results=[]
    ok=0
    for t in TESTS:
        r=classify(t["q"], {})
        passed = r.name == t["intent"]
        reply = social_reply(t["q"], {}) if r.name.startswith("social") else ""
        for bad in t.get("not_contains", []):
            if bad in reply:
                passed=False
        results.append({"q":t["q"],"expected":t["intent"],"actual":r.name,"passed":passed,"reply":reply})
        ok += int(passed)
    out={"passed":ok,"total":len(TESTS),"results":results}
    Path("v42_full_intelligence_report.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"PASSED: {ok}/{len(TESTS)}")
    if ok != len(TESTS):
        raise SystemExit(1)

if __name__ == "__main__":
    main()
