# -*- coding: utf-8 -*-
import sys
import v46_semantic_concept_engine as eng

cases = [
    ("ما هو المصطلح الذي يطلق على النصيب المقدر شرعا للوارث في كتاب الله، والذي لا يزيد إلا بالرد ولا ينقص إلا بالعول؟", "fard", ["الفرض", "النصيب"], ["المصطلح المقصود هو: **العَوْل**"]),
    ("ما اسم النصيب المحدد في القرآن للوارث؟", "fard", ["الفرض"], []),
    ("وش يسمون السهم الشرعي المقدر للوارث؟", "fard", ["الفرض"], []),
    ("ماذا يسمى النصيب اللي يزيد بالرد وينقص بالعول؟", "fard", ["الفرض"], []),
    ("ما هي الفروض المقدرة في المواريث؟", "fixed_shares", ["النصف", "الربع", "السدس"], []),
    ("ما معنى العول؟", "awl", ["العول", "زيادة مجموع الفروض"], []),
    ("شنو يعني الرد في الميراث؟", "radd", ["الرد", "رجوع الباقي"], []),
    ("ما الفرق بين حجب الحرمان وحجب النقصان؟", "hajb", ["الحجب"], []),
    ("ما هي العمرية؟", "umariyyat", ["العمر", "ثلث الباقي"], []),
]

ok = 0
for q, expected, must, must_not in cases:
    out = eng.answer(q, {}, "مدير النظام")
    if not out:
        print("FAIL no answer:", q)
        sys.exit(1)
    cid = out["concept_id"]
    ans = out["answer"]
    if cid != expected:
        print("FAIL concept", q, "expected", expected, "got", cid)
        print(ans)
        sys.exit(1)
    for m in must:
        if m not in ans:
            print("FAIL missing", m, "in", q)
            print(ans)
            sys.exit(1)
    for m in must_not:
        if m in ans:
            print("FAIL must-not", m, "in", q)
            print(ans)
            sys.exit(1)
    ok += 1
print(f"PASSED: {ok}/{len(cases)} v46 semantic concept tests")
