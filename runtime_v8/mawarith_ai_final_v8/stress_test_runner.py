# -*- coding: utf-8 -*-
import json
from mawarith_ai_runtime import answer, normalize_ar

passed = 0
failed = []
with open("stress_tests_final_v8.jsonl", "r", encoding="utf-8") as f:
    tests = [json.loads(line) for line in f if line.strip()]

for i, t in enumerate(tests, 1):
    out = answer(t["q"])
    norm_out = normalize_ar(out)
    ok = True
    for m in t.get("must", []):
        if normalize_ar(m) not in norm_out:
            ok = False
    for m in t.get("must_not", []):
        if normalize_ar(m) in norm_out:
            ok = False
    if ok:
        passed += 1
    else:
        failed.append((i, t["q"], out, t))

print(f"PASSED: {passed}/{len(tests)}")
if failed:
    print("FAILED TESTS:")
    for i, q, out, t in failed[:20]:
        print("#", i, q)
        print("Expected contains:", t.get("must"))
        print("Must not:", t.get("must_not"))
        print(out)
        print("-"*40)
    raise SystemExit(1)
print("All final stress tests passed.")
