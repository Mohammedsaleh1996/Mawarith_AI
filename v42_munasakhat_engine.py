# -*- coding: utf-8 -*-
"""Lightweight safe scenario layer for sequential-death inheritance cases.
No guessing, no RAG. Detects composite cases and either delegates supported simple cases
or asks for missing staged information.
"""
from __future__ import annotations
import re
from typing import Optional
try:
    from v42_full_intelligence import normalize, detect_dialect
except Exception:
    def normalize(x): return str(x or "").strip().lower()
    def detect_dialect(x, context=None): return "standard"

SEQ = ["ثم", "بعده", "بعدها", "وبعد", "وبعدين", "عقب", "لاحقا", "لاحقًا", "بعد ذلك", "بعد كده", "بعدها توفي", "بعده توفي"]
DEATH = ["مات", "ماتت", "توفي", "توفيت", "توفى", "توفت", "هلك", "هلكت"]


def looks_like_munasakhat(text: str) -> bool:
    n = normalize(text)
    death_terms = sorted({normalize(d) for d in DEATH if normalize(d)}, key=len, reverse=True)
    death_spans = []
    for d in death_terms:
        for m in re.finditer(r"(^|\s)" + re.escape(d) + r"($|\s)", n):
            # store only actual token span without surrounding spaces
            start = m.start() + (1 if m.group(1) else 0)
            end = m.end() - (1 if m.group(2) else 0)
            if not any(not (end <= a or start >= b) for a, b in death_spans):
                death_spans.append((start, end))
    death_count = len(death_spans)
    seq_present = any(re.search(r"(^|\s)" + re.escape(normalize(s)) + r"($|\s)", n) for s in SEQ)
    return death_count >= 2 or (death_count >= 1 and seq_present)


def safe_munasakhat_response(text: str, context: Optional[dict] = None) -> Optional[str]:
    if not looks_like_munasakhat(text):
        return None
    dialect = detect_dialect(text, context)
    openers = {
        "egyptian": "دي مسألة وفاة متتابعة / مناسخة، ومينفعش تتقسم كأنها قسمة واحدة؛ لازم نحلها مرحلة مرحلة.",
        "gulf": "هذه مسألة وفاة متتابعة / مناسخة، ولا يصح جمعها في قسمة واحدة؛ لازم تنحل على مراحل.",
        "shami": "هاي مسألة وفاة متتابعة / مناسخة، ولازم تنحل خطوة خطوة، مش قسمة واحدة.",
        "standard": "هذه مسألة وفاة متتابعة / مناسخة، ولا يصح حسابها بالتخمين؛ لأنها تُحل على مراحل، وقد يصبح نصيب أحد الورثة تركة مستقلة بعد وفاته.",
    }
    return (openers.get(dialect) or openers["standard"]) + "\n\n" + \
        "حتى أحسبها بدقة، اكتبها بهذا الترتيب:\n" + \
        "1) المتوفى الأول، وورثته الأحياء وقت وفاته.\n" + \
        "2) صافي تركته: الأموال، الأصول، الديون، الوصايا، والعملات.\n" + \
        "3) المتوفى الثاني: هل ورث من الأول؟ وكم كان نصيبه؟\n" + \
        "4) ورثة المتوفى الثاني الأحياء وقت وفاته.\n\n" + \
        "لو كانت البيانات كاملة سأقسم كل وفاة على حدة، ثم أدمج النتيجة النهائية دون تخمين."
