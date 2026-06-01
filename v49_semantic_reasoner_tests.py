# -*- coding: utf-8 -*-
import v49_semantic_reasoner as eng

CASES = [
    ("ما هو المصطلح الذي يطلق على النصيب المقدر شرعا للوارث في كتاب الله، والذي لا يزيد إلا بالرد ولا ينقص إلا بالعول؟", "fard", ["الفَرْض", "النصيب"], ["العول هو", "الرَّد هو", "المصطلح المقصود هو: العول"]),
    ("ما اسم السهم الشرعي المحدد للوارث؟", "fard", ["الفَرْض"], ["العاصب"]),
    ("وش يسمون الحصة المقدرة للوارث في القرآن؟", "fard", ["الفَرْض"], ["العاصب"]),
    ("ماذا يسمى الوارث الذي ليس له سهم مقدر بل يأخذ كل المال إذا انفرد أو يأخذ ما تبقى من التركة بعد أصحاب الفروض؟", "asib", ["العاصب"], ["المصطلح المقصود هو: الفَرْض"]),
    ("ما اسم الوارث اللي بياخد الباقي بعد أصحاب الفروض؟", "asib", ["العاصب"], ["الفَرْض هو"]),
    ("شنو يسمون اللي ما له فرض وياخذ الباقي؟", "asib", ["العاصب"], ["الفَرْض"]),
    ("ما معنى التعصيب؟", "tasib", ["التعصيب"], []),
    ("ما الفرق بين الفرض والتعصيب؟", "", ["الفرق", "الفَرْض", "التعصيب"], []),
    ("مات رجل وترك زوجة وبنت وأخ شقيق", "PASS", [], []),
    ("مساء الفل", "SOCIAL", ["مساء"], ["بسم الله", "اكتب السؤال"]),
]

def main():
    failed = []
    for q, expected, must, must_not in CASES:
        r = eng.route(q, name="مدير النظام")
        if expected == "PASS":
            ok = r.action == "pass" and r.intent == "inheritance_calculation"
            ans = ""
        elif expected == "SOCIAL":
            ans = r.answer
            ok = r.action == "answer" and r.intent == "social"
        else:
            ans = r.answer
            ok = r.action == "answer" and r.concept_id == expected
        if ok and must:
            ok = all(x in ans for x in must)
        if ok and must_not:
            ok = not any(x in ans for x in must_not)
        if not ok:
            failed.append((q, expected, r.action, r.intent, r.concept_id, r.confidence, ans[:300], r.reason))
    if failed:
        for f in failed:
            print("FAILED:", f)
        raise SystemExit(1)
    print(f"PASSED: {len(CASES)}/{len(CASES)} v49 semantic reasoner tests")

if __name__ == "__main__":
    main()
