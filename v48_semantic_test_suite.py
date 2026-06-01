# -*- coding: utf-8 -*-
import v48_scholarly_intelligence_engine as e

def check(q, must=None, must_not=None, action_answer=True, context=None):
    out = e.answer(q, context=context or {"last_concept":"hajb"}, name="مدير النظام")
    if action_answer and not out:
        raise AssertionError(f"NO ANSWER: {q}")
    if not action_answer and out:
        raise AssertionError(f"SHOULD PASS, GOT: {q} => {out['answer'][:120]}")
    if out:
        a = out["answer"]
        for m in must or []:
            if m not in a:
                raise AssertionError(f"MISSING {m!r}: {q} => {a}")
        for m in must_not or []:
            if m in a:
                raise AssertionError(f"FORBIDDEN {m!r}: {q} => {a}")
    return True

cases = [
    ("ما هو المصطلح الذي يطلق على النصيب المقدر شرعا للوارث في كتاب الله، والذي لا يزيد إلا بالرد ولا ينقص إلا بالعول؟", ["الفَرْض"], ["العَوْل:", "الرَّد:"]),
    ("ما اسم النصيب المحدد شرعا للوارث؟", ["الفَرْض"], []),
    ("وش يسمون السهم الشرعي المقدر للوارث؟", ["الفَرْض"], []),
    ("ماذا يسمى نصيب النصف والربع والثمن في المواريث؟", ["الفروض المقدّرة"], []),
    ("كم عدد الفروض المقدرة في كتاب الله؟", ["ستة"], []),
    ("ما الفرق بين العول والرد؟", ["الفرق"], []),
    ("ما معنى الحجب؟", ["الحَجْب"], []),
    ("اشرح العاصب بالغير", ["العاصب بالغير"], []),
    ("ما افهم", ["الحَجْب"], []),
    ("السلام عليكم كيف حالك", ["وعليكم السلام"], ["بسم الله", "المواريث"]),
    ("مساء الفل", ["مساء"], ["بسم الله", "اكتب السؤال"]),
]
for q, must, must_not in cases:
    check(q, must, must_not)
# Calculation must pass through to inheritance engine, not concept answer.
assert e.answer("مات رجل وترك زوجة وبنت وأخ شقيق") is None
print("PASSED: v48 semantic/intelligence suite")
