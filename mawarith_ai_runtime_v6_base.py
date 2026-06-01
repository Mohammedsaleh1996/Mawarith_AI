# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import re
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

# ============================================================
# مفتي المواريث الذكي - Runtime v6
# نطاق هذه النسخة:
# 1) فهم صيغ عربية وفصحى وعامية متعددة للسؤال الواحد.
# 2) عدم تثبيت إجابة لمسألة بعينها.
# 3) عدم استخدام RAG.
# 4) الحساب الفرائضي لا يُترك للنموذج اللغوي.
# 5) عند الغموض المؤثر فقهيًا: يسأل ولا يخمن.
# 6) توضيح العول/الرد بدون تناقض بين النصيب الأصلي والنهائي.
# 7) v5: دعم أقوى للهجات، ومنع إسقاط وارث بسبب التطبيع اللغوي.
# 8) v6: توسيع الإجابات الفقهية العامة للجمهور وإضافة بطارية اختبار ضغط.
# ============================================================

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

NUM_WORDS = {
    "واحد": 1, "واحدة": 1, "واحده": 1, "احد": 1, "احدى": 1, "احدي": 1,
    "وحيد": 1, "وحيده": 1, "وحيدة": 1,
    "اثنان": 2, "اثنين": 2, "اتنين": 2, "تنين": 2, "جوج": 2, "ثنتين": 2, "ثنتان": 2,
    "اثنتين": 2, "اثنتان": 2, "اثنا": 2,
    "ثلاث": 3, "ثلاثة": 3, "ثلاثه": 3, "تلات": 3, "تلاته": 3,
    "اربع": 4, "اربعة": 4, "اربعه": 4,
    "خمس": 5, "خمسة": 5, "خمسه": 5,
    "ست": 6, "ستة": 6, "سته": 6,
    "سبع": 7, "سبعة": 7, "سبعه": 7,
    "ثمان": 8, "ثمانية": 8, "ثمانيه": 8,
    "تسع": 9, "تسعة": 9, "تسعه": 9,
    "عشر": 10, "عشرة": 10, "عشره": 10,
}

COUNT_TOKEN = r"\d+|" + "|".join(sorted(map(re.escape, NUM_WORDS), key=len, reverse=True))

LABEL = {
    "husband": "الزوج",
    "wife": "الزوجة/الزوجات",
    "son": "الابن/الأبناء",
    "daughter": "البنت/البنات",
    "father": "الأب",
    "mother": "الأم",
    "full_brother": "الأخ الشقيق/الإخوة الأشقاء",
    "full_sister": "الأخت الشقيقة/الأخوات الشقيقات",
    "paternal_brother": "الأخ لأب/الإخوة لأب",
    "paternal_sister": "الأخت لأب/الأخوات لأب",
    "maternal_brother": "الأخ لأم/الإخوة لأم",
    "maternal_sister": "الأخت لأم/الأخوات لأم",
    "paternal_uncle": "العم/الأعمام",
}

@dataclass
class Heirs:
    husband: int = 0
    wife: int = 0
    son: int = 0
    daughter: int = 0
    father: int = 0
    mother: int = 0
    full_brother: int = 0
    full_sister: int = 0
    paternal_brother: int = 0
    paternal_sister: int = 0
    maternal_brother: int = 0
    maternal_sister: int = 0
    paternal_uncle: int = 0
    estate: Fraction | None = None
    warnings: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)

@dataclass
class CalcResult:
    shares: dict[str, Fraction]
    blocked: list[str] = field(default_factory=list)
    original_shares: dict[str, Fraction] = field(default_factory=dict)
    case_type: str | None = None  # awl / radd / residue-warning
    case_note: str | None = None

# -------------------------
# Normalization / Parsing
# -------------------------

def norm(s: str) -> str:
    s = (s or "").translate(AR_DIGITS)
    s = re.sub("[إأآٱ]", "ا", s)
    s = s.replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    s = re.sub("[ًٌٍَُِّْـٰ]", "", s)
    # قبل توحيد التاء المربوطة: نحمي ألفاظ البنت حتى لا تختلط بـ "ابنه" = ابنُه.
    # نعالج الكلمة ولو كانت مسبوقة بواو العطف: وابنة، وابنته...
    s = re.sub(r"\bو(?=ابنة\b)", "و", s)
    s = re.sub(r"\bابنة\b", "بنت", s)
    s = re.sub(r"\bوابنة\b", "وبنت", s)
    s = re.sub(r"\bابنتين\b", "بنتين", s)
    s = re.sub(r"\bوابنتين\b", "وبنتين", s)
    s = re.sub(r"\bابنتان\b", "بنتان", s)
    s = re.sub(r"\bوابنتان\b", "وبنتان", s)
    s = re.sub(r"\bابنتا\b", "بنتا", s)
    s = re.sub(r"\bوابنتا\b", "وبنتا", s)
    s = re.sub(r"\bابنته\b", "بنته", s)
    s = re.sub(r"\bوابنته\b", "وبنته", s)
    s = re.sub(r"\bابنتها\b", "بنتها", s)
    s = re.sub(r"\bوابنتها\b", "وبنتها", s)
    # Normalize ta marbuta after removing tashkeel.
    s = s.replace("ة", "ه")
    s = s.replace("؟", "?")
    s = re.sub(r"([,،؛:؛.؟?(){}\[\]])", r" \1 ", s)
    # common orthographic variants
    s = s.replace("للأب", "لاب").replace("للأم", "لام")
    s = s.replace("للاب", "لاب").replace("للام", "لام")
    s = re.sub(r"\bابو\b", "اب", s)
    return re.sub(r"\s+", " ", s).strip()

def spaced(t: str) -> str:
    return " " + norm(t) + " "

def nval(x: str | None, default: int = 1) -> int:
    if not x:
        return default
    x = norm(x)
    if x.isdigit():
        return int(x)
    return NUM_WORDS.get(x, default)

def consume(txt: str, m: re.Match) -> str:
    return txt[:m.start()] + (" " * (m.end() - m.start())) + txt[m.end():]

def add_count(h: Heirs, key: str, count: int) -> None:
    setattr(h, key, getattr(h, key) + max(1, int(count)))

def infer_count(term: str, explicit: str | None) -> int:
    if explicit:
        return nval(explicit, 1)
    term = norm(term)
    # clear dual forms
    if re.search(r"(تين|تان|وين|ين|ان)\b", term):
        return 2
    plural_terms = {
        "زوجات", "بنات", "ابناء", "اخوات", "اخوته", "اعمام", "اولاد", "عيال",
        "اشقاء", "شقيقات",
    }
    if term in plural_terms or re.search(r"(ات|اء)\b", term):
        return 2
    return 1

def extract_amount(t: str) -> Fraction | None:
    t = norm(t)
    m = re.search(r"(?:ترك|تركت|تركه|التركه|تركة|مبلغ|مال|قيمتها|قدرها)\s*(?:قدرها|قيمتها|مقدارها)?\s*([0-9]+(?:[.,][0-9]+)?)", t)
    if not m:
        return None
    raw = m.group(1).replace(",", ".")
    try:
        if "." in raw:
            return Fraction(str(float(raw)))
        return Fraction(int(raw), 1)
    except Exception:
        return None

COUNT_PREFIX = rf"(?:(?:عددهم|عددهن|عددها|عددهم\s*هو|عددهن\s*هو)?\s*({COUNT_TOKEN})\s+)?(?:و\s*)?"
COUNT_SUFFIX = rf"(?:\s+({COUNT_TOKEN}|واحده|واحدة|وحيده|وحيدة))?"
LOOKAHEAD = r"(?=\s|[,،.؛:؟?])"

def apply_pattern_loop(t: str, h: Heirs, key: str, pat: str) -> str:
    rg = re.compile(r"(?<=\s)" + COUNT_PREFIX + "(" + pat + ")" + COUNT_SUFFIX + LOOKAHEAD)
    while True:
        m = rg.search(t)
        if not m:
            break
        explicit_count = m.group(1) or m.group(3)
        term = m.group(2)
        add_count(h, key, infer_count(term, explicit_count))
        t = consume(t, m)
    return t

def parse_heirs(text: str) -> Heirs:
    h = Heirs()
    t = spaced(text)
    h.estate = extract_amount(t)

    # Specific relatives first.
    full_brother = (
        r"(?:اخ|اخا|اخو|اخوه|اخوان|اخوين|اخوته|خو|خوه|خوها|خويه|خويها|خوان|خوين)\s+(?:(?:ال)?شقيق|شقيقا|(?:ال)?اشقاء|شقيقين|شقيقان)"
        r"|(?:اخ|اخا|اخو|اخوه|اخوان|اخوين|اخوته|خو|خوه|خوها|خويه|خويها|خوان|خوين)\s+من\s+(?:ابوه|ابيه|اب|الاب|والده)\s*(?:و|و\s*من)?\s*(?:امه|ام|الام|والدته)"
        r"|(?:اخ|اخا|اخو|اخوه|اخوان|اخوين|اخوته|خو|خوه|خوها|خويه|خويها|خوان|خوين)\s+من\s+(?:امه|ام|الام|والدته)\s*(?:و|و\s*من)?\s*(?:ابوه|ابيه|اب|الاب|والده)"
        r"|(?:اخ|اخا|اخو|اخوه|اخوان|اخوين|اخوته|خو|خوه|خوها|خويه|خويها|خوان|خوين)\s+من\s+نفس\s+الاب\s+و\s*الام"
        r"|(?:اخ|اخا|اخو|اخوه|اخوان|اخوين|اخوته|خو|خوه|خوها|خويه|خويها|خوان|خوين)\s+لاب(?:وه|يه)?\s*و\s*ام(?:ه)?"
    )
    full_sister = (
        r"(?:اخت|اختا|اخوات|اختين|اختان|اخته|اختها|خت|خوات|خته|ختها)\s+(?:(?:ال)?شقيقه|(?:ال)?شقيقات|شقيقتين|شقيقتان)"
        r"|(?:اخت|اختا|اخوات|اختين|اختان|اخته|اختها|خت|خوات|خته|ختها)\s+من\s+(?:ابوها|ابيها|اب|الاب|والدها)\s*(?:و|و\s*من)?\s*(?:امها|ام|الام|والدتها)"
        r"|(?:اخت|اختا|اخوات|اختين|اختان|اخته|اختها|خت|خوات|خته|ختها)\s+من\s+(?:امها|ام|الام|والدتها)\s*(?:و|و\s*من)?\s*(?:ابوها|ابيها|اب|الاب|والدها)"
        r"|(?:اخت|اختا|اخوات|اختين|اختان|اخته|اختها|خت|خوات|خته|ختها)\s+من\s+نفس\s+الاب\s+و\s*الام"
        r"|(?:اخت|اختا|اخوات|اختين|اختان|اخته|اختها|خت|خوات|خته|ختها)\s+لاب(?:وها|يها)?\s*و\s*ام(?:ها)?"
    )
    paternal_brother = (
        r"(?:اخ|اخا|اخو|اخوه|اخوان|اخوين|اخوته|خو|خوه|خوها|خويه|خويها|خوان|خوين)\s+(?:لاب|من\s+الاب|من\s+ابيه|من\s+ابوه|لابيه|لابوه)\s*(?:فقط|بس)?"
        r"|(?:اخ|اخا|اخو|اخوه|اخوان|اخوين|اخوته|خو|خوه|خوها|خويه|خويها|خوان|خوين)\s+من\s+ابوه\s+بس"
    )
    paternal_sister = (
        r"(?:اخت|اختا|اخوات|اختين|اختان|اخته|اختها|خت|خوات|خته|ختها)\s+(?:لاب|من\s+الاب|من\s+ابيها|من\s+ابوها|لابيها|لابوها)\s*(?:فقط|بس)?"
        r"|(?:اخت|اختا|اخوات|اختين|اختان|اخته|اختها|خت|خوات|خته|ختها)\s+من\s+ابوها\s+بس"
    )
    maternal_brother = (
        r"(?:اخ|اخا|اخو|اخوه|اخوان|اخوين|اخوته|خو|خوه|خوها|خويه|خويها|خوان|خوين)\s+(?:لام|من\s+الام|من\s+امه|من\s+امها|لامه|لامها)\s*(?:فقط|بس)?"
        r"|(?:اخ|اخا|اخو|اخوه|اخوان|اخوين|اخوته|خو|خوه|خوها|خويه|خويها|خوان|خوين)\s+من\s+(?:امه|امها)\s+بس"
        r"|(?:اخ|اخا|اخو|اخوه|اخوان|اخوين|اخوته|خو|خوه|خوها|خويه|خويها|خوان|خوين)\s+من\s+نفس\s+الام"
    )
    maternal_sister = (
        r"(?:اخت|اختا|اخوات|اختين|اختان|اخته|اختها|خت|خوات|خته|ختها)\s+(?:لام|من\s+الام|من\s+امها|من\s+امه|لامها|لامه)\s*(?:فقط|بس)?"
        r"|(?:اخت|اختا|اخوات|اختين|اختان|اخته|اختها|خت|خوات|خته|ختها)\s+من\s+(?:امها|امه)\s+بس"
        r"|(?:اخت|اختا|اخوات|اختين|اختان|اخته|اختها|خت|خوات|خته|ختها)\s+من\s+نفس\s+الام"
    )

    specs = [
        ("full_brother", full_brother),
        ("full_sister", full_sister),
        ("paternal_brother", paternal_brother),
        ("paternal_sister", paternal_sister),
        ("maternal_brother", maternal_brother),
        ("maternal_sister", maternal_sister),
        ("wife", r"(?:زوجات|زوجتين|زوجتان|زوجه|زوجته|زوجتو|زوجة|مراته|مراتو|مرته|مرتو|حرمته|امرأته|امراته|ارملته|ارملتو)"),
        ("husband", r"(?:زوج|زوجا|زوجها|زوجھا|جوزها|جوز|راجلها|راجلھا|بعلها)"),
        ("daughter", r"(?:بنات|بنتين|بنتان|بنت|بنتا|بنته|بنتو|بنتها|بنيه|بنية)"),
        # Do not include ambiguous اولاد/عيال here.
        ("son", r"(?:ابناء\s+ذكور|ابنين|ابنان|ابن|ابنا|ابنه|ابنو|ابنها|ولده|ولدو|ولدها|ولد|ولدا|ولدين|ولدان)"),
        ("father", r"(?:اب|ابا|ابوه|ابوها|ابيها|ابو|ابيه|والد|والده|والدها)"),
        ("mother", r"(?:ام|اما|امه|امها|امو|والده|والدته|والدتها)"),
        ("paternal_uncle", r"(?:اعمام|عمين|عمان|عم|عما)"),
    ]

    for key, pat in specs:
        t = apply_pattern_loop(t, h, key, pat)

    # Ambiguity detection: public use must not guess.
    if re.search(r"(?<!\w)و?(?:اخ|اخا|اخو|اخوه|اخوان|اخوين|اخوته|خو|خوه|خوها|خويه|خويها|خوان|خوين)(?!\w)", t):
        h.ambiguities.append("ورد أخ/إخوة بدون تحديد الجهة. هل هو شقيق، أم لأب، أم لأم؟")
    if re.search(r"(?<!\w)و?(?:اخت|اختا|اخته|اختها|اخوات|اختين|اختان|خت|خوات|خته|ختها)(?!\w)", t):
        h.ambiguities.append("وردت أخت/أخوات بدون تحديد الجهة. هل هي شقيقة، أم لأب، أم لأم؟")
    if re.search(r"(?<!\w)و?(?:اولاد|اولاده|اولادها|عيال|عياله|عيالها|عيالو|ذريه|ذريته|ذريتها|ذرية|اطفال)(?!\w)", t):
        h.ambiguities.append("ورد لفظ عام مثل أولاد/عيال/ذرية. اذكر عدد الذكور وعدد الإناث: كم ابنًا وكم بنتًا؟")
    if h.husband and h.wife:
        h.ambiguities.append("ظهر في السؤال زوج وزوجة معًا؛ راجع جنس المتوفى والورثة لأن أحدهما غالبًا ليس وارثًا في نفس المسألة.")

    # dedupe preserving order
    seen = set()
    h.ambiguities = [x for x in h.ambiguities if not (x in seen or seen.add(x))]
    return h

def heirs_count(h: Heirs) -> int:
    return sum(getattr(h, k) for k in LABEL.keys())

def is_calc_question(q: str) -> bool:
    t = norm(q)
    death = bool(re.search(r"\b(توفي|توفى|توفيت|توفا|توفت|توفات|مات|ماتت|ميت|الميت|هالك|هلك|هلكت|ورثه|الورثه|ميراث|تركة|تركه|خلف|خلّف|خلّفت|ساب|سيب|ترك|تركت|وراه|وراها)\b", t))
    ask = bool(re.search(r"(نصيب|انصبه|تقسم|تتقسم|قسم|قسمة|قسمه|حصة|حصه|كم|ازاي|كيف|وش|ايه|شنو|شحال|قديش|اشقد|مين|ما نصيب|ميراث)", t))
    h = parse_heirs(q)
    extracted_or_ambiguous = heirs_count(h) > 0 or bool(h.ambiguities)
    concept = bool(re.search(r"(ما هو|ما معنى|عرف|اشرح|تعريف|المقصود)", t))
    return extracted_or_ambiguous and (death or ask) and not concept

# -------------------------
# Calculation
# -------------------------

def f(fr: Fraction) -> str:
    if fr.denominator == 1:
        return str(fr.numerator)
    return f"{fr.numerator}/{fr.denominator}"

def pct(fr: Fraction) -> str:
    return f"{float(fr * 100):.6g}%"

def money(fr: Fraction, estate: Fraction | None) -> str:
    if estate is None:
        return ""
    val = estate * fr
    return f" = {float(val):,.2f}" if val.denominator != 1 else f" = {val.numerator:,}"

def add(sh: dict[str, Fraction], key: str, frac: Fraction) -> None:
    if frac <= 0:
        return
    sh[key] = sh.get(key, Fraction(0)) + frac

def solve(h: Heirs) -> CalcResult:
    sh: dict[str, Fraction] = {}
    blocked: list[str] = []
    resid: list[tuple[str, int]] = []

    has_male_desc = h.son > 0
    has_desc = (h.son + h.daughter) > 0
    siblings_total = h.full_brother + h.full_sister + h.paternal_brother + h.paternal_sister + h.maternal_brother + h.maternal_sister

    if h.husband:
        add(sh, "husband", Fraction(1, 4) if has_desc else Fraction(1, 2))
    if h.wife:
        add(sh, "wife", Fraction(1, 8) if has_desc else Fraction(1, 4))

    if h.mother:
        if has_desc or siblings_total >= 2:
            add(sh, "mother", Fraction(1, 6))
        elif (h.husband or h.wife) and h.father and not has_desc and siblings_total == 0:
            spouse = sh.get("husband", Fraction(0)) + sh.get("wife", Fraction(0))
            add(sh, "mother", (Fraction(1) - spouse) / 3)
        else:
            add(sh, "mother", Fraction(1, 3))

    if h.father:
        if has_male_desc:
            add(sh, "father", Fraction(1, 6))
        elif h.daughter > 0:
            add(sh, "father", Fraction(1, 6))
            resid.append(("father", h.father))
        else:
            resid.append(("father", h.father))

    if h.son > 0:
        resid.append(("children", h.son * 2 + h.daughter))
    elif h.daughter > 0:
        add(sh, "daughter", Fraction(1, 2) if h.daughter == 1 else Fraction(2, 3))

    if h.maternal_brother + h.maternal_sister:
        if has_desc or h.father:
            blocked.append("الإخوة لأم محجوبون بالفرع الوارث أو الأب.")
        else:
            n = h.maternal_brother + h.maternal_sister
            add(sh, "maternal_siblings", Fraction(1, 6) if n == 1 else Fraction(1, 3))

    if h.full_brother + h.full_sister:
        if has_male_desc or h.father:
            blocked.append("الإخوة الأشقاء محجوبون بالابن أو الأب.")
        elif h.full_brother:
            resid.append(("full_siblings", h.full_brother * 2 + h.full_sister))
        elif h.daughter > 0:
            resid.append(("full_sister_with_daughters", h.full_sister))
        else:
            add(sh, "full_sister", Fraction(1, 2) if h.full_sister == 1 else Fraction(2, 3))

    if h.paternal_brother + h.paternal_sister:
        if has_male_desc or h.father or h.full_brother or (h.full_sister and h.daughter):
            blocked.append("الإخوة لأب محجوبون بمن هو أقرب منهم في العصوبة.")
        elif h.paternal_brother:
            resid.append(("paternal_siblings", h.paternal_brother * 2 + h.paternal_sister))
        elif h.daughter > 0:
            resid.append(("paternal_sister_with_daughters", h.paternal_sister))
        elif h.full_sister == 1:
            add(sh, "paternal_sister", Fraction(1, 6))
        elif h.full_sister >= 2:
            blocked.append("الأخت/الأخوات لأب محجوبات باستكمال الشقيقات الثلثين ما لم يوجد أخ لأب يعصبهن.")
        else:
            add(sh, "paternal_sister", Fraction(1, 2) if h.paternal_sister == 1 else Fraction(2, 3))

    if h.paternal_uncle:
        if has_male_desc or h.father or h.full_brother or h.paternal_brother:
            blocked.append("العم محجوب بمن هو أقرب منه في العصوبة.")
        else:
            resid.append(("paternal_uncle", h.paternal_uncle))

    fixed_total = sum(sh.values(), Fraction(0))

    if fixed_total > 1:
        original = dict(sh)
        factor = Fraction(1, 1) / fixed_total
        sh = {k: v * factor for k, v in sh.items()}
        return CalcResult(
            shares=sh,
            blocked=blocked,
            original_shares=original,
            case_type="awl",
            case_note=f"عالت المسألة لأن مجموع الفروض قبل العول بلغ {f(fixed_total)} من التركة، فخُفِّضت الأنصبة بنسبة واحدة حتى صار المجموع 1.",
        )

    residue = Fraction(1) - fixed_total
    original_before_residue = dict(sh)

    if residue > 0 and resid:
        name, units = resid[0]
        if name == "children":
            if h.son:
                sh["son"] = sh.get("son", Fraction(0)) + residue * Fraction(h.son * 2, units)
            if h.daughter:
                sh["daughter"] = sh.get("daughter", Fraction(0)) + residue * Fraction(h.daughter, units)
        elif name == "full_siblings":
            if h.full_brother:
                sh["full_brother"] = sh.get("full_brother", Fraction(0)) + residue * Fraction(h.full_brother * 2, units)
            if h.full_sister:
                sh["full_sister"] = sh.get("full_sister", Fraction(0)) + residue * Fraction(h.full_sister, units)
        elif name == "paternal_siblings":
            if h.paternal_brother:
                sh["paternal_brother"] = sh.get("paternal_brother", Fraction(0)) + residue * Fraction(h.paternal_brother * 2, units)
            if h.paternal_sister:
                sh["paternal_sister"] = sh.get("paternal_sister", Fraction(0)) + residue * Fraction(h.paternal_sister, units)
        elif name == "full_sister_with_daughters":
            sh["full_sister"] = sh.get("full_sister", Fraction(0)) + residue
        elif name == "paternal_sister_with_daughters":
            sh["paternal_sister"] = sh.get("paternal_sister", Fraction(0)) + residue
        else:
            sh[name] = sh.get(name, Fraction(0)) + residue
        return CalcResult(shares=sh, blocked=blocked, original_shares=original_before_residue)

    if residue > 0:
        radd_keys = [k for k in sh if k not in ("husband", "wife")]
        base = sum(sh[k] for k in radd_keys)
        if radd_keys and base > 0:
            original = dict(sh)
            for k in radd_keys:
                sh[k] += residue * sh[k] / base
            return CalcResult(
                shares=sh,
                blocked=blocked,
                original_shares=original,
                case_type="radd",
                case_note="بقي جزء من التركة ولا توجد عصبة، فرُدَّ الباقي على أصحاب الفروض غير الزوجين بنسبة فروضهم.",
            )
        return CalcResult(
            shares=sh,
            blocked=blocked,
            original_shares=original_before_residue,
            case_type="residue-warning",
            case_note="بقي جزء من التركة ولم يظهر في السؤال عاصب ولا مستحق رد؛ راجع الورثة.",
        )

    return CalcResult(shares=sh, blocked=blocked, original_shares=original_before_residue)

def count_for_key(h: Heirs, key: str) -> int:
    if key == "maternal_siblings":
        return h.maternal_brother + h.maternal_sister
    return getattr(h, key, 1)

# -------------------------
# Explanation Engine v4
# -------------------------

def _has_desc(h: Heirs) -> bool:
    return (h.son + h.daughter) > 0

def _has_male_desc(h: Heirs) -> bool:
    return h.son > 0

def _siblings_total(h: Heirs) -> int:
    return h.full_brother + h.full_sister + h.paternal_brother + h.paternal_sister + h.maternal_brother + h.maternal_sister

def base_explain_share(h: Heirs, key: str) -> str:
    has_desc = _has_desc(h)
    has_male_desc = _has_male_desc(h)
    sibs = _siblings_total(h)

    if key == "wife":
        base = "تشترك الزوجات في" if h.wife > 1 else "للزوجة"
        return (f"{base} الثمن لوجود فرع وارث." if has_desc else f"{base} الربع لعدم وجود فرع وارث.")
    if key == "husband":
        return "للزوج الربع لوجود فرع وارث." if has_desc else "للزوج النصف لعدم وجود فرع وارث."
    if key == "mother":
        if has_desc and sibs >= 2:
            return "للأم السدس لاجتماع سببين: وجود فرع وارث ووجود جمع من الإخوة."
        if has_desc:
            return "للأم السدس لوجود فرع وارث."
        if sibs >= 2:
            return "للأم السدس لوجود جمع من الإخوة."
        if (h.husband or h.wife) and h.father:
            return "للأم ثلث الباقي في المسألة العمرية بعد فرض الزوج أو الزوجة."
        return "للأم الثلث لعدم وجود فرع وارث وعدم وجود جمع من الإخوة."
    if key == "father":
        if has_male_desc:
            return "للأب السدس فرضًا فقط مع وجود فرع وارث ذكر."
        if h.daughter:
            return "للأب السدس فرضًا مع الفرع الوارث الأنثى، ويأخذ الباقي تعصيبًا إن بقي بعد الفروض."
        return "الأب عصبة بالنفس؛ يأخذ الباقي بعد أصحاب الفروض، وقد يأخذ التركة كلها عند عدم صاحب فرض."
    if key == "son":
        if h.daughter:
            return "الابن عصبة بالنفس، ويعصب البنت معه؛ فيُقسم الباقي بين الأولاد للذكر مثل حظ الأنثيين."
        return "الابن عصبة بالنفس؛ يأخذ الباقي بعد أصحاب الفروض، ويحجب من دونه من العصبات."
    if key == "daughter":
        if h.son:
            return "البنت صارت عصبة بالغير مع الابن، ويُقسم الباقي بينهما للذكر مثل حظ الأنثيين."
        if h.daughter == 1:
            return "للبنت الواحدة النصف فرضًا عند عدم الابن المعصب."
        return "للبنات الثلثان فرضًا عند التعدد وعدم وجود ابن معصب."
    if key == "full_brother":
        if h.full_sister:
            return "الإخوة الأشقاء يعصبون الأخوات الشقيقات؛ فيأخذون الباقي بعد الفروض للذكر مثل حظ الأنثيين."
        return "الأخ الشقيق يأخذ الباقي تعصيبًا بعد أصحاب الفروض؛ لعدم وجود أب أو فرع وارث ذكر يحجبه."
    if key == "full_sister":
        if h.full_brother:
            return "الأخت الشقيقة صارت عصبة بالغير مع الأخ الشقيق؛ فيُقسم الباقي للذكر مثل حظ الأنثيين."
        if h.daughter:
            return "الأخت الشقيقة صارت عصبة مع الغير بوجود البنت أو البنات، فتأخذ الباقي بعد أصحاب الفروض."
        if h.full_sister == 1:
            return "للأخت الشقيقة النصف فرضًا عند عدم الفرع الوارث والأصل الذكر والأخ الشقيق المعصب."
        return "للأخوات الشقيقات الثلثان فرضًا عند التعدد وعدم الفرع الوارث والأصل الذكر والأخ الشقيق المعصب."
    if key == "paternal_brother":
        if h.paternal_sister:
            return "الأخ لأب يعصب الأخت لأب؛ فيأخذان الباقي بعد الفروض للذكر مثل حظ الأنثيين، عند عدم من يحجبهما."
        if h.full_sister:
            return "الأخ لأب يأخذ الباقي تعصيبًا بعد فرض الأخت الشقيقة/الأخوات الشقيقات؛ لأنه لا يوجد أب ولا فرع وارث ذكر ولا أخ شقيق يحجبه."
        return "الأخ لأب يأخذ الباقي تعصيبًا بعد أصحاب الفروض، عند عدم الأب والفرع الوارث الذكر والأخ الشقيق."
    if key == "paternal_sister":
        if h.paternal_brother:
            return "الأخت لأب صارت عصبة بالغير مع الأخ لأب؛ فيُقسم الباقي للذكر مثل حظ الأنثيين."
        if h.daughter:
            return "الأخت لأب صارت عصبة مع الغير مع البنت أو البنات عند عدم الشقيقة المعصبة ومن يحجبها."
        if h.full_sister == 1:
            return "الأخت لأب تأخذ السدس تكملة للثلثين مع الأخت الشقيقة الواحدة، عند عدم المعصب والحاجب."
        if h.paternal_sister == 1:
            return "للأخت لأب النصف فرضًا عند عدم الشقيقات وعدم المعصب والحاجب."
        return "للأخوات لأب الثلثان فرضًا عند التعدد وعدم الشقيقات وعدم المعصب والحاجب."
    if key == "maternal_siblings":
        n = h.maternal_brother + h.maternal_sister
        if n == 1:
            return "للأخ أو الأخت لأم السدس فرضًا عند عدم الفرع الوارث والأصل الذكر."
        return "الإخوة لأم يشتركون في الثلث بالسوية، ذكرهم وأنثاهم سواء، عند عدم الفرع الوارث والأصل الذكر."
    if key == "paternal_uncle":
        return "العم عصبة بالنفس؛ يأخذ الباقي عند عدم العصبات الأقرب منه كالأب والابن والأخ."
    return "استحق هذا الوارث نصيبه بحسب القواعد المستخرجة من الورثة المذكورين في السؤال."

def explain_share(h: Heirs, key: str, final_share: Fraction, result: CalcResult) -> str:
    base = base_explain_share(h, key)
    original = result.original_shares.get(key)
    if result.case_type == "awl" and original and original != final_share:
        return f"الحكم الأصلي قبل العول: {base} وكان نصيبه الأصلي {f(original)}، ثم صار نصيبه النهائي بعد العول {f(final_share)}."
    if result.case_type == "radd" and original and original != final_share:
        return f"الحكم الأصلي قبل الرد: {base} وكان نصيبه الأصلي {f(original)}، ثم زاد نصيبه بالرد إلى {f(final_share)} لعدم وجود عاصب."
    if key == "father" and h.daughter and final_share == Fraction(1, 6) and sum(result.shares.values(), Fraction(0)) == 1:
        return "للأب السدس فرضًا مع الفرع الوارث الأنثى، ولم يبق له شيء تعصيبًا لاستغراق الفروض التركة."
    return base

def display_label(h: Heirs, key: str) -> str:
    c = count_for_key(h, key)
    if key == "wife": return "الزوجة" if c == 1 else "الزوجات"
    if key == "daughter": return "البنت" if c == 1 else "البنات"
    if key == "son": return "الابن" if c == 1 else "الأبناء"
    if key == "full_brother": return "الأخ الشقيق" if c == 1 else "الإخوة الأشقاء"
    if key == "full_sister": return "الأخت الشقيقة" if c == 1 else "الأخوات الشقيقات"
    if key == "paternal_brother": return "الأخ لأب" if c == 1 else "الإخوة لأب"
    if key == "paternal_sister": return "الأخت لأب" if c == 1 else "الأخوات لأب"
    if key == "maternal_siblings": return "الإخوة لأم مجتمعين"
    if key == "paternal_uncle": return "العم" if c == 1 else "الأعمام"
    return LABEL.get(key, key)

def render_calc(question: str) -> str:
    h = parse_heirs(question)
    if h.ambiguities:
        out = ["السؤال يحتاج توضيحًا قبل الحساب؛ لأن هذه المعلومات تغيّر الحكم:", ""]
        out += ["- " + x for x in h.ambiguities]
        out += ["", "أعد كتابة الورثة مثل: زوجة، بنت، أخ شقيق / أخ لأب / أخ لأم، مع عدد الأبناء والبنات إن وجدوا."]
        return "\n".join(out)

    if heirs_count(h) == 0:
        return "لم أستطع استخراج الورثة من السؤال بدقة. اكتبها مثل: توفي عن زوجة وبنت وأخ شقيق."

    result = solve(h)
    sh = result.shares
    if not sh:
        return "استخرجت الورثة، لكن المسألة خارج نطاق محرك الحساب الحالي أو ناقصة. اذكر الورثة كاملين بدون اختصار."

    out = ["النتيجة الحسابية:", ""]
    for k, v in sorted(sh.items(), key=lambda x: float(x[1]), reverse=True):
        label = display_label(h, k)
        c = count_for_key(h, k)
        out.append(f"- {label}: {f(v)} من التركة ({pct(v)}){money(v, h.estate)}")
        if c and c > 1:
            out.append(f"  نصيب الفرد الواحد: {f(v / c)} من التركة ({pct(v / c)}){money(v / c, h.estate)}")
        out.append(f"  السبب: {explain_share(h, k, v, result)}")

    if result.case_note:
        out += ["", "تنبيه: " + result.case_note]

    hajb_notes = []
    if h.mother and (h.son + h.daughter > 0):
        hajb_notes.append("الأم حُجبت حجب نقصان من الثلث إلى السدس بسبب وجود فرع وارث.")
    elif h.mother and _siblings_total(h) >= 2:
        hajb_notes.append("الأم حُجبت حجب نقصان من الثلث إلى السدس بسبب جمع من الإخوة.")
    if h.wife and (h.son + h.daughter > 0):
        hajb_notes.append("الزوجة حُجبت حجب نقصان من الربع إلى الثمن بسبب الفرع الوارث.")
    if h.husband and (h.son + h.daughter > 0):
        hajb_notes.append("الزوج حُجب حجب نقصان من النصف إلى الربع بسبب الفرع الوارث.")

    if result.blocked or hajb_notes:
        out += ["", "الحجب:"]
        out += ["- " + b for b in result.blocked]
        out += ["- " + n for n in hajb_notes]

    if h.warnings:
        out += ["", "تنبيهات إدخال:", *["- " + w for w in h.warnings]]

    total = sum(sh.values(), Fraction(0))
    out += ["", "مراجعة مجموع الأنصبة: " + f(total) + " من التركة."]
    return "\n".join(out)

# -------------------------
# Fiqh concept engine / model fallback
# -------------------------

def is_simplify_request(q: str) -> bool:
    t = norm(q)
    return bool(re.search(r"\b(مش فاهم|مش فاهمه|ما فهمت|مفهمتش|مش واضح|وضح|وضحي|بسط|بسطها|ببساطه|ببساطة|اشرح تاني|فهمني)\b", t))

def simplify_previous(last_answer: str | None) -> str | None:
    if not last_answer:
        return None
    lines = [l.strip() for l in last_answer.splitlines() if l.strip()]
    share_lines = [l for l in lines if l.startswith("- ") and "من التركة" in l]
    if share_lines:
        out = ["ببساطة:"]
        for l in share_lines:
            out.append(l)
        out.append("يعني نقسم التركة على هذه النسب، ومجموعها لازم يساوي التركة كلها.")
        return "\n".join(out)
    return "ببساطة: " + " ".join(lines[:4])

def answer_fiqh_concept(q: str) -> str | None:
    t = norm(q)
    if "تعصيب" in t or "عاصب" in t or "العصبه" in t or "العصبة" in q:
        return (
            "التعصيب هو إرث بلا سهم مقدر؛ فيأخذ العاصب ما بقي بعد أصحاب الفروض، وقد يأخذ كل التركة إذا لم يوجد صاحب فرض، وقد لا يأخذ شيئًا إذا استغرقت الفروض التركة.\n\n"
            "أنواعه المختصرة:\n"
            "- عاصب بالنفس: يرث بقوته، مثل الابن والأخ الشقيق عند عدم من يحجبه.\n"
            "- عاصب بالغير: أنثى صارت عصبة بذكر في درجتها، مثل البنت مع الابن.\n"
            "- عاصب مع الغير: مثل الأخت الشقيقة مع البنت، فتأخذ الأخت الباقي بعد فرض البنت."
        )
    if "حجب" in t or "محجوب" in t or "حرمان" in t or "نقصان" in t:
        return (
            "الحجب هو منع وارث من الميراث كله أو من بعضه بسبب وجود وارث أقوى منه.\n\n"
            "- حجب حرمان: يمنع الوارث من الميراث بالكامل، مثل حجب الأخ الشقيق بالابن أو الأب.\n"
            "- حجب نقصان: لا يمنع الوارث بالكامل، لكنه ينقص نصيبه، مثل الزوجة من الربع إلى الثمن عند وجود الفرع الوارث، والأم من الثلث إلى السدس عند وجود فرع وارث أو جمع من الإخوة."
        )
    if ("ترتيب" in t and ("حقوق" in t or "التركة" in t or "تركه" in t)) or "قبل تقسيم" in t:
        return (
            "ترتيب الحقوق المتعلقة بالتركة قبل التوزيع:\n\n"
            "1) الحقوق المتعلقة بعين التركة إن وجدت، مثل الرهن أو مال تعلّق به حق خاص.\n"
            "2) تجهيز الميت بالمعروف بلا إسراف.\n"
            "3) قضاء الديون.\n"
            "4) تنفيذ الوصية الصحيحة في حدود الثلث ولغير وارث إلا إذا أجاز الورثة.\n"
            "5) تقسيم الباقي على الورثة المستحقين.\n\n"
            "تنبيه: لا يبدأ حساب أنصبة الورثة إلا بعد إخراج هذه الحقوق من التركة."
        )
    if "اصحاب الفروض" in t or "أصحاب الفروض" in q or ("فرض" in t and "مين" in t):
        return (
            "أصحاب الفروض هم الورثة الذين لهم أنصبة مقدّرة في الشرع، مثل النصف والربع والثمن والثلثين والثلث والسدس.\n\n"
            "ومن أمثلتهم بحسب الحالة: الزوج، الزوجة، الأب، الأم، البنت، بنت الابن، الأخت الشقيقة، الأخت لأب، والإخوة لأم.\n\n"
            "بعد إعطاء أصحاب الفروض فروضهم، يُعطى الباقي إلى العصبة إن وُجدوا."
        )
    if "عول" in t:
        return "العول هو زيادة مجموع الفروض على التركة، فتنقص أنصبة أصحاب الفروض بنسبة واحدة حتى يساوي المجموع التركة."
    if "رد" in t and ("ميراث" in t or "الميراث" in t or "ورث" in t or "تركة" in q or "تركه" in t):
        return (
            "الرد هو رجوع الباقي من التركة إلى أصحاب الفروض غير الزوجين عند عدم وجود عاصب يأخذ الباقي، ويكون بنسبة فروضهم.\n\n"
            "مثال مبسط: لو مات شخص وترك بنتًا فقط، فلها النصف فرضًا، ولا يوجد عاصب، فيُرد عليها الباقي فتأخذ التركة كلها.\n\n"
            "تنبيه: الزوج والزوجة لا يدخلان في الرد في المعتمد الذي يعمل به هذا المحرك؛ فيأخذان فرضهما فقط."
        )
    if "كلاله" in t or "كلالة" in q:
        return "الكلالة هي حالة من مات وليس له ولد ولا والد وارث، وتظهر أحكامها في ميراث الإخوة والأخوات."
    if "فرع وارث" in t or "الفرع الوارث" in t:
        return "الفرع الوارث هو نسل الميت الذي يرث منه، مثل الابن والبنت وابن الابن عند تحقق شروطه، ووجوده يؤثر في أنصبة الزوجين والأم وغيرهم."
    if ("اخ" in t or "اخت" in t) and ("شقيق" in t or "لاب" in t or "لام" in t or "الام" in t or "الاب" in t) and ("فرق" in t or "شنو" in t or "ما الفرق" in t or "ايه الفرق" in t):
        return (
            "الفرق بين أنواع الإخوة في الميراث:\n\n"
            "- الأخ الشقيق: يشترك مع الميت في الأب والأم، وهو أقوى من الأخ لأب.\n"
            "- الأخ لأب: يشترك مع الميت في الأب فقط، وقد يحجبه الأخ الشقيق أو الابن أو الأب.\n"
            "- الأخ لأم: يشترك مع الميت في الأم فقط، ويرث بالفرض لا بالتعصيب، ويُحجب بالفرع الوارث أو الأصل الذكر.\n\n"
            "الخلاصة: الجهة مؤثرة جدًا؛ فلا يصح أن نقول فقط: أخ، بل يجب تحديده: شقيق أم لأب أم لأم."
        )
    if "دين" in t or "ديون" in t or "نسدد" in t or "سداد" in t or "قضاء" in t:
        if ("ترك" in t or "تركة" in q or "تركه" in t or "ورث" in t or "نقسم" in t or "تقسيم" in t or "الميراث" in t or "الورثة" in q or "الورثه" in t or "وصيه" in t or "وصية" in q or "بعدها" in t or "قبل" in t):
            return (
                "لا تُقسَّم التركة على الورثة قبل سداد الديون.\n\n"
                "الترتيب المختصر: الحقوق المتعلقة بعين التركة إن وجدت، ثم تجهيز الميت بالمعروف، ثم قضاء الديون، ثم تنفيذ الوصية الصحيحة في حدود الثلث، ثم تقسيم الباقي على الورثة المستحقين.\n\n"
                "فالدين مقدَّم على قسمة الميراث، ولا يصح توزيع المال على الورثة قبل إخراجه."
            )
    if ("اخوه لام" in t or "اخوة لام" in t or "الإخوة لأم" in q or "اخ لام" in t or "اخت لام" in t) and ("سويه" in t or "بالسويه" in t or "سواء" in t):
        return "معنى أن الإخوة لأم يرثون بالسوية: أن ذكرهم وأنثاهم سواء في القسمة؛ فإذا تعددوا اشتركوا في الثلث بالتساوي عند تحقق شروط إرثهم."
    if ("تجهيز الميت" in t or "تجهيز" in t) and ("ميراث" in t or "نقسم" in t or "قبل" in t):
        return "لا يُبدأ بتقسيم الميراث قبل تجهيز الميت بالمعروف؛ لأن تجهيز الميت من الحقوق المقدمة على قسمة التركة، ثم تُقضى الديون، ثم تنفذ الوصية الصحيحة، ثم يقسم الباقي، ولذلك يكون التجهيز قبل التوزيع."
    return None

SYSTEM_PROMPT = """أنت مفتي مواريث ذكي متخصص في الفرائض والوصايا.
التزم بالآتي:
- لا تحسب مسائل التركات من نفسك؛ الحساب يكون من المحرك الحتمي.
- في السؤال الفقهي أجب بضبط واختصار.
- لا تخترع آثارًا أو قصصًا أو أسماء مسائل.
- إن نقصت معلومة مؤثرة فاسأل عنها.
"""

def looks_bad_model_output(s: str) -> bool:
    if not s or len(s.strip()) < 3:
        return True
    ns = norm(s)
    bad_patterns = [
        r"الله\s*:\s*\d",
        r"ولد الزنا.*ابن الخنثى",
        r"زوجات لزوج ولهما فيه حق الولاء",
        r"(سَوَاءٌ.*){3,}",
        r"(\b\w+\b(?:\s+\b\w+\b){0,5}).*\1.*\1.*\1",
    ]
    return any(re.search(p, ns) for p in bad_patterns)

def ollama_chat(prompt: str, model: str = "mawarith_ai", host: str = "http://localhost:11434", timeout: int = 60) -> str:
    data = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "top_p": 0.1,
            "repeat_penalty": 1.25,
            "num_predict": 384,
            "stop": ["<|im_end|>", "<|im_start|>", "***", "مسألة:", "القول الأول", "ثانيا:", ">>>"],
        },
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(host.rstrip("/") + "/api/chat", data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            obj = json.loads(r.read().decode("utf-8"))
            ans = (obj.get("message") or {}).get("content", "").strip()
            if looks_bad_model_output(ans):
                return "لم أستطع تقديم جواب مضبوط لهذا السؤال من الطبقة الحالية بدون مخاطرة بالخطأ. أعد صياغة السؤال بتحديد الورثة أو نوع المسألة بدقة أكثر."
            return ans
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        return "تعذر الاتصال بنموذج Ollama المحلي. شغّل النموذج أولًا ثم أعد المحاولة.\nتفاصيل الخطأ: " + str(e)

def ask(q: str, model: str = "mawarith_ai", host: str = "http://localhost:11434", last_answer: str | None = None) -> str:
    if is_simplify_request(q):
        simp = simplify_previous(last_answer)
        if simp:
            return simp
    if is_calc_question(q):
        return render_calc(q)
    concept = answer_fiqh_concept(q)
    if concept:
        return concept
    return ollama_chat(q, model=model, host=host)

# -------------------------
# Self-test / API / CLI
# -------------------------

TESTS = [
    "واحد مات وساب مراته وأمه وابنه وبنته، القسمة تبقى إزاي؟",
    "رجال توفى وخلّف أبوه وأمه وبنتين، كيف تتقسم التركة؟",
    "مرة توفّت وتركت زوجها وأخوين من أمها وأخت شقيقة، مين بياخد قديش؟",
    "شنو يعني الرد في الميراث؟ ومتى يصير؟",
    "شنو الفرق بين الأخ الشقيق والأخ لأب والأخ لأم فالميراث؟",
    "لو الزول المات عندو ديون، نقسم الورثة الأول ولا نسدد الدين؟",
    "مات واحد وترك اخوه، كم نصيبه؟",
    "واحد مات وعنده عيال، كيف القسمة؟",
    "امرأة ماتت وخلفت زوج وبنت، كم لكل واحد؟",
    "راجل توفى وساب أب وأم وزوجة وبنت، التركة تتقسم إزاي؟",
    "ما معنى أصحاب الفروض؟",
    "شنو العول؟",
]

def self_test() -> str:
    out = []
    for q in TESTS:
        out.append("> " + q)
        out.append(ask(q))
        out.append("-" * 60)
    return "\n".join(out)

class Handler(BaseHTTPRequestHandler):
    model = "mawarith_ai"
    host = "http://localhost:11434"

    def do_POST(self):
        if self.path != "/ask":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length", "0") or "0")
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            q = body.get("question") or body.get("q") or ""
            last = body.get("last_answer")
            ans = ask(q, self.model, self.host, last_answer=last)
            payload = json.dumps({"answer": ans}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as e:
            self.send_error(500, str(e))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ask", "-a")
    ap.add_argument("--model", default="mawarith_ai")
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    if args.self_test:
        print(self_test())
        return
    if args.api:
        Handler.model = args.model
        Handler.host = args.host
        print(f"API: http://127.0.0.1:{args.port}/ask")
        HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
        return
    if args.ask:
        print(ask(args.ask, args.model, args.host))
        return

    print("مفتي المواريث الذكي - اكتب السؤال، أو exit للخروج.")
    last_answer = None
    while True:
        try:
            q = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in ("exit", "quit", "خروج"):
            break
        if q:
            ans = ask(q, args.model, args.host, last_answer=last_answer)
            print(ans)
            last_answer = ans

if __name__ == "__main__":
    main()
