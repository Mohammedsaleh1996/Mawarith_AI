# -*- coding: utf-8 -*-
"""Generate broad local test cases for v41 without using RAG."""
import json
from pathlib import Path

social = [
    "السلام عليكم كيف حالك", "كيف حالك", "هلا", "اهلين", "مساء الفل", "صباح الخير", "شكرا", "تمام",
    "شلونك", "عامل ايه", "شنو اخبارك", "يا هلا", "مساء الورد", "صباح الفل"
]
fiqh = [
    "ما معنى الحجب؟", "وش يعني التعصيب؟", "شنو الرد في الميراث؟", "كم عدد الفروض المقدرة؟",
    "ما هي العمرية؟", "ما الفرق بين الأخ الشقيق والأخ لأب والأخ لأم؟", "ما ترتيب الحقوق المتعلقة بالتركة؟",
]
calc = [
    "مات شخص وترك زوجة وبنت وأخ شقيق ومبلغ 100000 ريال", "واحد مات وساب مراته وأمه وابنه وبنته والمال مية الف جنيه",
    "رجال توفى وخلف أبوه وأمه وبنتين", "مات شخص وترك 3 بنات وأم وعم ومبلغ مية ألف ريال وعليه دين عشرين ألف",
    "توفي عن زوجة وبنت ابن وأخ شقيق", "مات شخص وبعده ماتت زوجته وللزوجة المتوفية أخ وتركوا أربع بنات ومليون ريال",
]
ambiguous = [
    "مات وترك اخوه", "واحد مات وعنده عيال", "توفي وترك أخت", "مات وترك أقاربه", "فيه ورثة كتير مش عارفهم"
]

def main(out='v41_generated_smoke_tests.jsonl'):
    rows=[]
    for q in social:
        rows.append({'q':q,'group':'social','must_not_include':['بسم الله الرحمن الرحيم','اكتب السؤال بصيغة أوضح','تحليل المسألة']})
    for q in fiqh:
        rows.append({'q':q,'group':'fiqh','must_not_include':['Internal Server Error']})
    for q in calc:
        rows.append({'q':q,'group':'calculation','must_not_include':['Internal Server Error']})
    for q in ambiguous:
        rows.append({'q':q,'group':'ambiguous','must_include_any':['توضيح','حدد','اذكر','نوع']})
    Path(out).write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows),encoding='utf-8')
    print(f'wrote {len(rows)} tests to {out}')
if __name__=='__main__':
    main()
