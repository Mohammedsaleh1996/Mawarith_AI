# -*- coding: utf-8 -*-
"""Build a non-RAG scholarly rule corpus index from local Sheikh/reference text files.
The output is metadata: concepts, synonyms, file hits, and safety policy. Runtime does not retrieve passages.
"""
from __future__ import annotations
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "corpus"
OUT_DIR.mkdir(exist_ok=True)

CONCEPTS = {
  "hajb": ["الحجب", "حجب الحرمان", "حجب النقصان", "محجوب", "يحجب"],
  "tasib": ["التعصيب", "العصبة", "عاصب", "باقي التركة", "الباقي"],
  "awl": ["العول", "عالت", "تعول"],
  "radd": ["الرد", "يرد", "رد الباقي"],
  "umarriyatan": ["العمرية", "العمريتان", "الغراوان", "ثلث الباقي"],
  "mushtaraka": ["المشتركة", "الحمارية", "اليمية"],
  "akdariya": ["الأكدرية", "اكدرية"],
  "munasakhat": ["المناسخات", "مناسخة", "مات بعده", "ثم مات"],
  "dhawu_arham": ["ذوو الأرحام", "ذوي الارحام", "الأرحام"],
  "mawani": ["موانع الإرث", "القتل", "اختلاف الدين", "الرق"],
  "rights": ["الحقوق المتعلقة بالتركة", "الديون", "الوصية", "تجهيز الميت", "الرهن"],
  "heirs_furud": ["أصحاب الفروض", "الفروض المقدرة", "النصف", "الربع", "الثمن", "السدس", "الثلث", "الثلثان"],
  "remote_agnates": ["العم", "ابن العم", "ابن الأخ", "العصبات"],
  "special_cases": ["الحمل", "المفقود", "الخنثى", "التخارج"],
}

SAFETY = {
  "requires_clarification": ["الأخ غير محدد الجهة", "الأخت غير محددة الجهة", "أولاد/عيال بلا عدد ذكور وإناث", "مال بلا عملة أو قيمة صافية"],
  "requires_madhhab_or_policy": ["الجد مع الإخوة", "ذوو الأرحام", "الرد على الزوجين", "بعض صور المناسخات", "الخنثى والمفقود والحمل"],
  "no_guessing": True,
  "runtime_policy": "احسب فقط ما تدعمه القواعد؛ وما نقصت بياناته يُطلب توضيحه؛ وما كان خلافيًا يُطلب فيه المذهب أو السياسة المعتمدة."
}

def build():
    files = sorted(ROOT.glob("المرحلة_*.txt"))
    index = {"schema": "v45_scholarly_rule_corpus", "concepts": {}, "safety_policy": SAFETY, "source_files": [p.name for p in files]}
    for key, terms in CONCEPTS.items():
        hits = []
        for p in files:
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            count = sum(len(re.findall(re.escape(t), txt)) for t in terms)
            if count:
                hits.append({"file": p.name, "hit_count": count})
        index["concepts"][key] = {"terms": terms, "source_hits": hits[:20], "supported_as": "rule_or_concept", "coverage_status": "needs_scholarly_review" if not hits else "indexed"}
    out = OUT_DIR / "v45_scholarly_rule_corpus.json"
    out.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out)

if __name__ == "__main__":
    print(build())
