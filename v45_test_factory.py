# -*- coding: utf-8 -*-
"""Generate broad smoke tests for dialogue, fiqh routing, money, ambiguity and social turns."""
from __future__ import annotations
import json
from pathlib import Path

TESTS = [
  {"q":"السلام عليكم كيف حالك", "must_intent":"social_greeting_status", "must_not":["بسم الله", "اكتب السؤال"]},
  {"q":"بخير الحمد لله", "must_intent":"social_status_reply", "must_not":["بسم الله", "ميراث"]},
  {"q":"مساء الفل", "must_intent":"social_greeting", "must_not":["بسم الله", "اكتب السؤال"]},
  {"q":"ما معنى الحجب؟", "must_intent":"fiqh_question", "must_allow_preamble": True},
  {"q":"مات شخص وترك زوجة وبنت وعم ومبلغ 100000 ريال", "must_intent":"inheritance_calculation", "must_allow_preamble": True},
  {"q":"ما افهم", "must_followup": True},
  {"q":"مات واحد وترك اخوه", "must_intent":"inheritance_calculation"},
  {"q":"مات شخص ثم ماتت زوجته وللزوجة اخ", "must_intent":"advanced_or_composite", "review_required": True},
]

def main():
    out = Path(__file__).resolve().parent / "v45_generated_tests.jsonl"
    out.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in TESTS), encoding="utf-8")
    print(out)

if __name__ == "__main__": main()
