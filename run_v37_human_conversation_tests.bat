@echo off
chcp 65001 >nul
python - <<PY
from mawarith_ai_runtime_v9 import answer
cases = [
    ("السلام عليكم", "وعليكم"),
    ("ما معنى الحجب؟", "الحجب"),
]
ctx = {"last_question":"ما معنى الحجب؟", "last_answer":"الحجب هو منع وارث من ميراثه كله أو بعضه بسبب وجود وارث أقرب.", "last_concept":"hajb", "last_dialect":"egyptian"}
follow = answer("ما افهم", ctx)
print("FOLLOWUP:\n", follow)
assert "الحجب" in follow and "اكتب السؤال" not in follow
for q, must in cases:
    a = answer(q)
    print("\nQ:", q, "\nA:", a[:500])
    assert must in a
print("PASSED: v37 human conversation checks")
PY
pause
