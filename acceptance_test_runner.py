# -*- coding: utf-8 -*-
import json, os, sys, argparse, datetime
from pathlib import Path

# Import v8 runtime without modifying it
HERE = Path(__file__).resolve().parent
from mawarith_ai_runtime_v9 import answer, normalize_ar  # noqa


def run_tests(test_file: str, report_file: str = "acceptance_report_public_v1.json") -> int:
    tests = []
    with open(test_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                tests.append(json.loads(line))

    passed = 0
    failed = []
    per_category = {}

    for t in tests:
        out = answer(t["q"])
        norm_out = normalize_ar(out)
        ok = True
        missing = []
        forbidden = []
        for m in t.get("must", []):
            if normalize_ar(m) not in norm_out:
                ok = False
                missing.append(m)
        for m in t.get("must_not", []):
            if normalize_ar(m) in norm_out:
                ok = False
                forbidden.append(m)
        cat = t.get("category", "uncategorized")
        per_category.setdefault(cat, {"passed": 0, "total": 0})
        per_category[cat]["total"] += 1
        if ok:
            passed += 1
            per_category[cat]["passed"] += 1
        else:
            failed.append({
                "id": t.get("id"),
                "category": cat,
                "question": t.get("q"),
                "missing": missing,
                "forbidden": forbidden,
                "output": out,
            })

    report = {
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "test_file": test_file,
        "passed": passed,
        "total": len(tests),
        "failed_count": len(failed),
        "per_category": per_category,
        "failed": failed[:50],
    }
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"PASSED: {passed}/{len(tests)}")
    for cat, d in sorted(per_category.items()):
        print(f"- {cat}: {d['passed']}/{d['total']}")
    print(f"Report written to: {report_file}")

    if failed:
        print("FAILED TESTS:")
        for item in failed[:20]:
            print("#", item["id"], item["category"], item["question"])
            print("Missing:", item["missing"])
            print("Forbidden:", item["forbidden"])
            print(item["output"])
            print("-" * 60)
        return 1
    print("All public acceptance tests passed.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests", default="acceptance_tests_public_v1.jsonl")
    parser.add_argument("--report", default="acceptance_report_public_v1.json")
    args = parser.parse_args()
    raise SystemExit(run_tests(args.tests, args.report))
