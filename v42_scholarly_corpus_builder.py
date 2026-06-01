# -*- coding: utf-8 -*-
"""Builds a structured non-RAG corpus index from local Sheikh/reference text files.
It stores topic coverage and source hits; the runtime uses concept keys/rules, not retrieval snippets.
"""
from __future__ import annotations
import json, re
from pathlib import Path
from typing import Dict, List
try:
    from v42_full_intelligence import normalize
except Exception:
    def normalize(x): return str(x or "").strip().lower()

CONCEPTS = {
    "hajb": ["حجب", "حجب الحرمان", "حجب النقصان"],
    "tasib": ["تعصيب", "عاصب", "عصبة", "للذكر مثل حظ الانثيين"],
    "awl": ["عول", "عالت", "العول"],
    "radd": ["رد", "الرد", "يرد", "يرد الباقي"],
    "umariyat": ["العمرية", "العمريتان", "الغراوان", "ثلث الباقي"],
    "musharaka": ["المشتركة", "الحمارية", "اليمية"],
    "akdariya": ["الأكدرية", "اكدرية"],
    "munasakhat": ["مناسخة", "مناسخات", "ثم مات", "بعده مات"],
    "dhawu_arham": ["ذوي الأرحام", "ذوو الأرحام", "الارحام"],
    "mawani": ["موانع الإرث", "القتل", "اختلاف الدين", "الرق"],
    "estate_rights": ["الحقوق المتعلقة بالتركة", "تجهيز الميت", "الديون", "الوصية"],
    "heirs": ["أصحاب الفروض", "الزوج", "الزوجة", "الأب", "الأم", "البنت", "بنت الابن", "الأخ"],
}


def scan_sources(root: str | Path) -> Dict[str, dict]:
    root = Path(root)
    files = list(root.glob("المرحلة_*.txt")) + list((root / "sources").glob("*.txt")) if (root / "sources").exists() else list(root.glob("المرحلة_*.txt"))
    out: Dict[str, dict] = {}
    for key, terms in CONCEPTS.items():
        hits = []
        total = 0
        for fp in files:
            try:
                txt = fp.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            n = normalize(txt)
            count = sum(n.count(normalize(t)) for t in terms)
            if count:
                total += count
                hits.append({"file": fp.name, "hits": int(count)})
        out[key] = {"terms": terms, "total_hits": total, "sources": sorted(hits, key=lambda x: -x["hits"])[:12]}
    return out


def build(root: str | Path, out_file: str | Path) -> None:
    data = {
        "version": "v42",
        "description": "Structured non-RAG topic index built from local mawarith references.",
        "concepts": scan_sources(root),
    }
    Path(out_file).parent.mkdir(parents=True, exist_ok=True)
    Path(out_file).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    build(here, here / "corpus" / "scholarly_corpus_index_v42.json")
    print("built", here / "corpus" / "scholarly_corpus_index_v42.json")
