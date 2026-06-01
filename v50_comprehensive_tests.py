# -*- coding: utf-8 -*-
from v50_comprehensive_scholarly_understanding import route, diagnose

TESTS = [
    ("ما هو المصطلح الذي يطلق على النصيب المقدر شرعا للوارث في كتاب الله، والذي لا يزيد إلا بالرد ولا ينقص إلا بالعول؟", "fard"),
    ("ما اسم السهم الشرعي المحدد للوارث؟", "fard"),
    ("ماذا يسمى الوارث الذي ليس له سهم مقدر، بل يأخذ كل المال إذا انفرد، أو يأخذ ما تبقى من التركة بعد أصحاب الفروض؟", "asib"),
    ("شنو يسمون اللي ما له فرض وياخذ الباقي؟", "asib"),
    ("ما هو المصطلح الذي يعبر عن منع شخص معين من ميراثه كله أو بعضه لوجود شخص آخر أقرب منه للميت؟", "hajb"),
    ("وش يسمون اللي يمنع الوارث من الميراث كله أو ينقص نصيبه عشان فيه واحد أقرب؟", "hajb"),
    ("ماذا يسمى منع الوارث من الميراث كله؟", "hajb_hirman"),
    ("ما المصطلح الذي يعني انتقال الوارث من نصيب أكبر لنصيب أقل؟", "hajb_nuqsan"),
    ("ما اسم زيادة مجموع الفروض على أصل المسألة؟", "awl"),
    ("ما المصطلح الذي يدل على رجوع الباقي لأصحاب الفروض عند عدم العاصب؟", "radd"),
    ("ما معنى الكلالة؟", "kalala"),
    ("ما هي العمريتان؟", "umariyya"),
    ("ما المقصود بالتخارج؟", "takharuj"),
    ("ما الفرق بين العول والرد؟", None),
    ("كم عدد الفروض المقدرة؟", "fixed_shares"),
]

failures = []
for q, expected in TESTS:
    r = route(q, name="مدير النظام")
    ok = bool(r.answer) and (expected is None or r.concept_id == expected)
    if not ok:
        failures.append((q, expected, r, diagnose(q)))

if failures:
    for q, exp, r, diag in failures:
        print("FAILED:", q)
        print("expected:", exp, "got:", r.concept_id, r.action, r.intent, r.confidence, r.reason)
        print(diag)
    raise SystemExit(1)
print(f"PASSED: {len(TESTS)}/{len(TESTS)} v50 comprehensive semantic tests")
