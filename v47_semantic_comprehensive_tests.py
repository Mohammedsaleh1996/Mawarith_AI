# -*- coding: utf-8 -*-
from v47_full_understanding_engine import answer, question_type, detect_concept_key

TESTS = [
    ("ما هو المصطلح الذي يطلق على النصيب المقدر شرعا للوارث في كتاب الله، والذي لا يزيد إلا بالرد ولا ينقص إلا بالعول؟", "الفَرْض", ["العَوْل:", "الرَّد:"]),
    ("ما اسم النصيب المحدد للوارث شرعا؟", "الفَرْض", ["العَوْل:"]),
    ("وش يسمون السهم الشرعي المقدر للوارث؟", "الفَرْض", ["العَوْل:"]),
    ("ايه اسم الحصة المقدرة شرعا في الميراث؟", "الفَرْض", ["العَوْل:"]),
    ("ما معنى العول؟", "العَوْل", ["الفَرْض:"]),
    ("ما معنى الرد؟", "الرَّد", ["العَوْل:"]),
    ("ما الفرق بين العول والرد؟", "الفرق", []),
    ("كم عدد الفروض المقدرة وما هي؟", "الفروض المقدّرة", []),
    ("ما معنى الحجب؟", "الحَجْب", []),
    ("ما الفرق بين حجب الحرمان وحجب النقصان؟", "الفرق", []),
    ("ما معنى التعصيب؟", "التعصيب", []),
    ("ما هي العمرية؟", "العُمَرِيَّتان", []),
    ("ما المقصود بالمناسخات؟", "المناسخات", []),
    ("ما هي موانع الإرث؟", "موانع الإرث", []),
    ("ما هي الحقوق المتعلقة بالتركة؟", "الحقوق المتعلقة بالتركة", []),
    ("السلام عليكم كيف حالك", "الحمد", ["بسم الله", "اكتب السؤال"]),
    ("مساء الفل", "مساء", ["بسم الله", "اكتب السؤال"]),
    ("بخير الحمد لله", "الحمد", ["بسم الله", "اكتب السؤال"]),
]

ctx = {}
ok = 0
for q, must, bads in TESTS:
    out = answer(q, ctx, name="مدير النظام") or {"answer":""}
    a = out.get("answer", "")
    if must not in a:
        raise AssertionError(f"Missing {must!r} for {q!r}\n{a}")
    for b in bads:
        if b in a:
            raise AssertionError(f"Unexpected {b!r} for {q!r}\n{a}")
    if out.get("concept_id"):
        ctx["last_concept"] = out.get("concept_id")
    ok += 1
# Followup should use context
ctx["last_concept"] = "hajb"
out = answer("ما افهم", ctx, name="مدير النظام") or {"answer":""}
if "الحَجْب" not in out["answer"] and "الحجب" not in out["answer"]:
    raise AssertionError("followup did not use last concept")
print(f"PASSED: {ok+1}/{ok+1} v47 comprehensive semantic tests")
