# -*- coding: utf-8 -*-
from __future__ import annotations
import json, sys
from pathlib import Path
import v45_full_scholarly_production as v45

def main():
    path = Path(__file__).resolve().parent / "v45_generated_tests.jsonl"
    if not path.exists():
        import v45_test_factory; v45_test_factory.main()
    ok = 0; total = 0; failures=[]
    context={"last_answer":"الحجب هو منع وارث من كل الميراث أو بعضه.", "last_question":"ما معنى الحجب؟", "last_dialect":"egyptian"}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        total += 1
        t=json.loads(line); q=t["q"]; r=v45.route(q, context)
        passed=True; why=[]
        if "must_intent" in t and r.intent != t["must_intent"]:
            passed=False; why.append(f"intent {r.intent} != {t['must_intent']}")
        if t.get("must_followup") and not r.followup:
            passed=False; why.append("not followup")
        if "must_allow_preamble" in t and r.allow_preamble != t["must_allow_preamble"]:
            passed=False; why.append(f"preamble {r.allow_preamble}")
        if "review_required" in t and r.review_required != t["review_required"]:
            passed=False; why.append(f"review {r.review_required}")
        reply = v45.social_reply(q, context) if r.social else (v45.followup_reply(q, context) if r.followup else "")
        for bad in t.get("must_not", []):
            if bad in reply:
                passed=False; why.append(f"bad phrase {bad}")
        if passed: ok += 1
        else: failures.append({"q":q,"route":r.to_dict(),"why":why,"reply":reply})
    report={"passed":ok,"total":total,"failures":failures}
    (Path(__file__).resolve().parent/"v45_full_intelligence_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"PASSED: {ok}/{total}")
    if failures:
        print(json.dumps(failures, ensure_ascii=False, indent=2)); sys.exit(1)

if __name__ == "__main__": main()
