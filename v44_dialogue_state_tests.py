# -*- coding: utf-8 -*-
import sys
import v44_dialogue_state_machine as v44

BAD_SOCIAL = ["بسم الله", "اكتب السؤال", "مواريث", "الميراث", "تفضل بسؤالك", "والله أعلم", "جار"]

cases = [
    ("ازيك", "social_status"),
    ("بخير الحمد لله", "social_status_reply"),
    ("مساء الفل", "social_greeting"),
    ("السلام عليكم كيف حالك", "social_greeting_status"),
    ("هلا", "social_greeting"),
    ("شكرا", "social_thanks"),
    ("ما معنى الحجب؟", "fiqh_question"),
    ("مات شخص وترك زوجة وبنت", "inheritance_calculation"),
    ("ممكن تبسطها", "followup_simplify"),
]

for q, expected in cases:
    r = v44.classify(q, {})
    print(q, "=>", r.intent, r.reason)
    if r.intent != expected:
        raise AssertionError(f"{q!r}: expected {expected}, got {r.intent}")
    if r.social:
        ans = v44.social_reply(q, {})
        bad = [b for b in BAD_SOCIAL if b in ans]
        if bad:
            raise AssertionError(f"Social reply leaked domain/fatwa terms for {q!r}: {ans!r}")
    if expected in {"fiqh_question", "inheritance_calculation"}:
        if not v44.should_use_fatwa_preamble(q, "الحجب هو كذا" if expected == "fiqh_question" else "الزوجة: 1/8"):
            raise AssertionError(f"Expected preamble for {q}")

# Social must beat unknown/fatwa even after previous social context.
ctx = {"last_answer": "الحمد لله بخير، إنت عامل إيه؟", "last_dialect": "egyptian"}
r = v44.classify("الحمد لله تمام", ctx)
assert r.social and r.intent == "social_status_reply", r

print("PASSED: v44 dialogue state machine tests")
