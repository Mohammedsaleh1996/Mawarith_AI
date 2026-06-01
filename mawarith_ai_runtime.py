# -*- coding: utf-8 -*-
"""
مفتي المواريث الذكي - Runtime Final v8

الفكرة الهندسية:
- لا RAG.
- لا تثبيت إجابات لمسائل بعينها.
- السؤال الحسابي يذهب إلى محرك فرائض حتمي.
- السؤال الفقهي الأساسي يذهب إلى طبقة مفاهيم مضبوطة.
- السؤال الفقهي المفتوح يذهب إلى نموذج Ollama المحلي إن وجد، مع فلتر مراجعة نهائي.
- الرد يحاول محاكاة لهجة السائل في الافتتاح، والتنبيه، وطلب التوضيح.

تنبيه فقهي/تقني:
المحرك يغطي أبوابًا عملية واسعة من مسائل الفرائض الشائعة. المسائل الخلافية أو التي تحتاج قضاءً/مذهبًا محددًا
لا يخمن فيها، بل يطلب توضيحًا أو يحيلها لمسار فقهي متخصص.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, List, Optional, Tuple

# -----------------------------
# Arabic normalization
# -----------------------------

ARABIC_DIACRITICS = re.compile(r"[\u064b-\u065f\u0670\u0640]")


def normalize_ar(text: str) -> str:
    t = text.strip()
    t = ARABIC_DIACRITICS.sub("", t)
    t = t.replace("إ", "ا").replace("أ", "ا").replace("آ", "ا")
    t = t.replace("ى", "ي")
    t = t.replace("ؤ", "و").replace("ئ", "ي")
    t = t.replace("ۀ", "ه")
    # keep ة; many heir words depend on it, but add normalized spaces/punct
    t = re.sub(r"[،,:؛;؟?!.()\[\]{}\"'ـ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    # افصل واو العطف الملتصقة بكلمات الورثة حتى لا تسقط: وامه، وابنه، وبنته، واخوه...
    t = re.sub(r"\bو(?=(زوج|مرات|مرت|حرم|ارملت|جوز|امه|امها|اما|ابوه|ابيه|ابا|ابنها|ابن|بنت|اخ|اخت|اب\b|ام\b|جد|جده))", "و ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def ar_num_to_int(token: str) -> Optional[int]:
    token = normalize_ar(token)
    mapping = {
        "واحد": 1, "واحدة": 1, "احد": 1, "احدة": 1, "فرد": 1,
        "اثنين": 2, "اتنين": 2, "اثنان": 2, "اثنتين": 2, "ثنتين": 2, "ثنين": 2, "تين": 2,
        "ثلاث": 3, "ثلاثة": 3, "تلات": 3, "تلاته": 3,
        "اربع": 4, "اربعة": 4, "خمسة": 5, "خمس": 5,
        "ستة": 6, "ست": 6, "سبعة": 7, "سبع": 7,
        "ثمانية": 8, "ثمان": 8, "تمنية": 8, "تمن": 8,
        "تسعة": 9, "تسع": 9, "عشرة": 10, "عشر": 10,
    }
    if token in mapping:
        return mapping[token]
    eastern = "٠١٢٣٤٥٦٧٨٩"
    western = "0123456789"
    trans = str.maketrans(eastern, western)
    s = token.translate(trans)
    if s.isdigit():
        return int(s)
    return None


# -----------------------------
# Dialect detection/rendering
# -----------------------------

@dataclass
class Dialect:
    name: str = "fusha"

    def calc_header(self) -> str:
        return {
            "egyptian": "القسمة كده:",
            "saudi": "القسمة بتكون كذا:",
            "gulf": "القسمة بتكون كذا:",
            "shami": "القسمة هيك:",
            "maghrebi": "القسمة هكذا:",
            "sudanese": "القسمة كده:",
            "fusha": "النتيجة الحسابية:",
        }.get(self.name, "النتيجة الحسابية:")

    def needs_clarification(self) -> str:
        return {
            "egyptian": "محتاج توضيح قبل ما أحسب؛ لأن التفاصيل دي بتغيّر الحكم:",
            "saudi": "نحتاج توضيح قبل الحساب؛ لأن هالتفاصيل تغيّر الحكم:",
            "gulf": "نحتاج توضيح قبل الحساب؛ لأن هالتفاصيل تغيّر الحكم:",
            "shami": "السؤال بدّه توضيح قبل الحساب؛ لأن هالتفاصيل بتغيّر الحكم:",
            "maghrebi": "خاص توضيح قبل الحساب؛ لأن هاد التفاصيل كتبدل الحكم:",
            "sudanese": "محتاجين توضيح قبل الحساب؛ لأن التفاصيل دي بتغيّر الحكم:",
            "fusha": "السؤال يحتاج توضيحًا قبل الحساب؛ لأن هذه المعلومات تغيّر الحكم:",
        }.get(self.name, "السؤال يحتاج توضيحًا قبل الحساب؛ لأن هذه المعلومات تغيّر الحكم:")

    def unsupported_advanced(self) -> str:
        return {
            "egyptian": "المسألة دي محتاجة تحديد فقهي أدق قبل الحكم، ومينفعش أحسبها بالتخمين.",
            "saudi": "المسألة هذي تحتاج تحديد فقهي أدق قبل الحكم، وما يصح أحسبها بالتخمين.",
            "gulf": "المسألة هذي تحتاج تحديد فقهي أدق قبل الحكم، وما يصح أحسبها بالتخمين.",
            "shami": "هالمسألة بدها تحديد فقهي أدق قبل الحكم، وما بصير أحسبها بالتخمين.",
            "maghrebi": "هاد المسألة خاصها تحديد فقهي أدق قبل الحكم، وما يصحش نحسبها بالتخمين.",
            "sudanese": "المسألة دي محتاجة تحديد فقهي أدق قبل الحكم، وما بنحسبها بالتخمين.",
            "fusha": "هذه المسألة تحتاج تحديدًا فقهيًا أدق قبل الحكم، ولا يصح حسابها بالتخمين.",
        }.get(self.name, "هذه المسألة تحتاج تحديدًا فقهيًا أدق قبل الحكم، ولا يصح حسابها بالتخمين.")


def detect_dialect(text: str) -> Dialect:
    t = normalize_ar(text)
    # Priority where specific markers are stronger
    if any(w in t for w in ["الزول", "زول", "عندو", "نسدد", "المات"]):
        return Dialect("sudanese")
    if any(w in t for w in ["واحد مات", "ساب", "مراته", "بنته", "ابنه", "ازاي", "ازاى", "عيال", "راجل", "كده"]):
        return Dialect("egyptian")
    if any(w in t for w in ["قديش", "بياخد", "بيورث", "توفت", "مره توفت", "مرة توفت", "هيك", "بدها", "تركت زوجها"]):
        return Dialect("shami")
    if any(w in t for w in ["شنو", "واش", "فالميراث", "كيقسم", "كتقسم", "خاص"]):
        if any(w in t for w in ["فالميراث", "واش", "كي", "كت", "خاص", "هاد"]):
            return Dialect("maghrebi")
        return Dialect("gulf")
    if any(w in t for w in ["رجال", "توفى", "خلف", "كيف", "هال", "ابوه", "وش"]):
        return Dialect("saudi")
    return Dialect("fusha")


# -----------------------------
# Heirs data
# -----------------------------

@dataclass
class Heirs:
    husband: int = 0
    wives: int = 0
    father: int = 0
    mother: int = 0
    son: int = 0
    daughter: int = 0
    grandson: int = 0       # ابن ابن
    granddaughter: int = 0  # بنت ابن
    full_brother: int = 0
    full_sister: int = 0
    paternal_brother: int = 0
    paternal_sister: int = 0
    maternal_sibling: int = 0  # إخوة لأم، ذكور/إناث بالسوية
    grandfather: int = 0
    grandmother: int = 0
    # meta flags
    ambiguous: List[str] = field(default_factory=list)
    advanced_flags: List[str] = field(default_factory=list)

    def any_descendant(self) -> bool:
        return self.son + self.daughter + self.grandson + self.granddaughter > 0

    def male_descendant(self) -> bool:
        return self.son + self.grandson > 0

    def siblings_count(self) -> int:
        return self.full_brother + self.full_sister + self.paternal_brother + self.paternal_sister + self.maternal_sibling


# -----------------------------
# Parser
# -----------------------------

COMPOSITE_PATTERNS = [
    # order matters: specific phrases before generic words
    ("maternal_sibling", [
        r"اخوين من ام(?:ه|ها|هم)?", r"اخوان من ام(?:ه|ها|هم)?", r"اتنين اخوه من الام", r"اثنين اخوه من الام",
        r"اخوه من الام", r"اخوة من الام", r"اخوان لام", r"اخوين لام", r"اختين لام", r"اختان لام",
        r"اخ لام", r"اخت لام", r"اخوه لام", r"اخوة لام", r"الاخوه لام", r"الاخوة لام",
    ]),
    ("full_brother", [
        r"اخوه الشقيق", r"اخو الشقيق", r"اخ شقيق", r"اخوه من ابوه وامه", r"اخوه من ابيه وامه",
        r"اخ من الاب والام", r"اخ من ابوه وامه", r"شقيقه الذكر",
    ]),
    ("full_sister", [
        r"اخت شقيقه", r"اخت شقيقة", r"اختان شقيقتان", r"اختين شقيقتين", r"اخوات شقيقات", r"اخواته الشقيقات",
        r"اخت من الاب والام", r"اخته من ابوه وامه",
    ]),
    ("paternal_brother", [
        r"اخ لاب", r"اخوه لاب", r"اخ من الاب", r"اخوه من ابوه بس", r"اخوه من ابيه فقط",
    ]),
    ("paternal_sister", [
        r"اخت لاب", r"اختين لاب", r"اختان لاب", r"اخوات لاب", r"اخت من الاب", r"اخت من ابوه بس",
    ]),
    ("granddaughter", [r"بنت ابن", r"بنت الابن", r"بنات ابن", r"بنات الابن"]),
    ("grandson", [r"ابن ابن", r"ابن الابن", r"اولاد ابن", r"ولد ابن"]),
]

GENERIC_PATTERNS = [
    ("husband", [r"زوجها", r"زوجا", r"زوج", r"جوزها", r"راجلها"]),
    ("wives", [r"زوجته", r"زوجة", r"زوجات", r"مراته", r"مرتو", r"مرته", r"حرمته", r"ارملته"]),
    ("father", [r"ابوه", r"ابيه", r"ابا", r"اب", r"والده", r"والد"]),
    ("mother", [r"امه", r"امها", r"اما", r"ام", r"والدته", r"والده"]),
    ("son", [r"ابنه", r"ابنها", r"ابنا", r"ابن", r"ولده", r"ولدو", r"ولد ذكر", r"ابناء", r"ابنين", r"ابنان", r"اولاد ذكور"]),
    ("daughter", [r"بنته", r"بنتها", r"بنتو", r"بنتا", r"بنت", r"بنتين", r"بنتان", r"بنات", r"بنيه", r"بنية"]),
    ("grandfather", [r"جده", r"جد"]),
    ("grandmother", [r"جدته", r"جدة"]),
]

ADVANCED_KEYWORDS = {
    "grandfather_with_siblings": ["جد واخ", "جد واخت", "جده واخ", "جده واخت"],
    "dhawu_arham": ["ذوي الارحام", "ذوو الارحام", "خال", "خاله", "عمة", "عمه", "ابن بنت", "بنت بنت"],
    "pregnancy": ["حامل", "حمل", "جنين"],
    "missing": ["مفقود", "غايب", "غائب"],
    "intersex": ["خنثى", "خنثي"],
    "killer": ["قتل", "قاتل", "الميراث والقتل"],
    "religion": ["اختلاف الدين", "غير مسلم", "كافر", "مسلم ومسيحي", "مسيحي"],
    "manasakhat": ["مناسخة", "مات قبل القسمة", "مات وارث قبل تقسيم"],
}


def _count_before(text: str, start: int) -> Optional[int]:
    before = text[max(0, start-30):start].strip().split()
    if not before:
        return None
    # last 3 tokens may include number word
    for tok in reversed(before[-4:]):
        n = ar_num_to_int(tok)
        if n is not None:
            return n
    return None


def _count_from_phrase(phrase: str, default: int = 1) -> int:
    p = normalize_ar(phrase)
    # في اللهجات: "اخوه الشقيق" غالبًا مفرد بمعنى أخوه، لا جمع إخوة
    if any(x in p for x in ["اخوه الشقيق", "اخوه من ابوه", "اخوه من ابيه", "اخوه لاب", "اخوه لام"]):
        return 1
    # dual markers
    if any(x in p for x in ["اثنين", "اتنين", "اخوين", "اخوان", "اختين", "اختان", "بنتين", "بنتان", "ابنين", "ابنان"]):
        return 2
    if any(x in p for x in ["ثلاث", "تلات"]):
        return 3
    # plural default for generic plurals is 2 unless explicit count before
    if any(x in p for x in ["بنات", "زوجات", "اخوات", "اخوه", "اخوة", "ابناء", "اولاد"]):
        return 2
    return default


def extract_heirs(question: str) -> Heirs:
    t = normalize_ar(question)
    h = Heirs()

    # Advanced markers/gates
    for flag, kws in ADVANCED_KEYWORDS.items():
        if any(kw in t for kw in kws):
            h.advanced_flags.append(flag)

    # Generic ambiguity checks before extraction
    if re.search(r"\b(عيال|اولاد|ذرية|ولاد)\b", t) and not re.search(r"(ابن|ابنه|بنت|بنته|بنتين|بنات|ولد ذكر|اولاد ذكور)", t):
        h.ambiguous.append("ورد لفظ عام مثل أولاد/عيال/ذرية. اذكر عدد الذكور وعدد الإناث: كم ابنًا وكم بنتًا؟")
    # generic brother mention without type
    if re.search(r"\b(اخوه|اخو|اخ|اخت|اخته|اخوات)\b", t) and not re.search(r"(شقيق|شقيقه|لاب|لام|لأب|لأم|من الاب|من الام|من ابوه وامه|من الأب والأم|من الاب والام)", t):
        h.ambiguous.append("ورد أخ/إخوة بدون تحديد الجهة. هل هو شقيق، أم لأب، أم لأم؟")

    # Remove already matched composite phrases to avoid double counting generic أخ/أخت
    consumed = []
    for heir, patterns in COMPOSITE_PATTERNS:
        for pat in patterns:
            for m in re.finditer(pat, t):
                phrase = m.group(0)
                cnt = _count_before(t, m.start()) or _count_from_phrase(phrase)
                setattr(h, heir, getattr(h, heir) + cnt)
                consumed.append((m.start(), m.end()))
    t2_chars = list(t)
    for a, b in consumed:
        for i in range(a, b):
            t2_chars[i] = " "
    t2 = "".join(t2_chars)

    # Specific family count patterns
    for heir, patterns in GENERIC_PATTERNS:
        for pat in patterns:
            for m in re.finditer(r"\b" + pat + r"\b", t2):
                phrase = m.group(0)
                cnt = _count_before(t2, m.start()) or _count_from_phrase(phrase)
                # special: زوج without possessive in male-decedent contexts could be spouse? still husband if question says امرأة/مرة ماتت
                if heir == "husband" and re.search(r"(رجل|راجل|واحد|الميت|مات وساب مراته)", t) and not re.search(r"(امرأة|امراه|مرة|زوجه ماتت|زوجها)", t):
                    # If user says زوجة/زوجته handled separately. Plain زوج in male question likely not a heir; rare skip.
                    pass
                setattr(h, heir, getattr(h, heir) + cnt)

    # Resolve duplicated "والده" maybe matched father/mother due normalization; keep only if explicit
    # Prevent "مرأة/مره توفت" as wife: only h.wives if possessive زوجة/مراته etc. Generic "مرة توفت" shouldn't add wife.
    if re.search(r"\bمره توفت\b|\bمرة توفت\b|\bمره ماتت\b|\bمرة ماتت\b", t):
        # our wife patterns don't include 'مرة', so no action
        pass

    # If grandfather with siblings, gate as advanced; if no siblings maybe can act as father substitute only later optionally
    if h.grandfather and h.siblings_count() > 0:
        h.advanced_flags.append("grandfather_with_siblings")

    # Normalize husband/wife impossible double? If both, keep; rare polygamy with female decedent impossible. Ask clarify.
    if h.husband and h.wives:
        h.ambiguous.append("ظهر في السؤال زوج وزوجة معًا بصياغة غير واضحة. حدّد هل الميت رجل أم امرأة، ومن الزوج/الزوجة الوارث؟")

    return h


# -----------------------------
# Fiqh intent layer
# -----------------------------

FIQH_INTENTS = {
    "radd": ["ما الرد", "يعني الرد", "شنو يعني الرد", "متى يصير الرد", "ايه الرد", "الرد في الميراث"],
    "awl": ["ما العول", "شنو العول", "يعني العول", "العول في الميراث"],
    "tasib": ["ما التعصيب", "معنى التعصيب", "التعصيب", "شنو التعصيب", "العاصب", "عصبة"],
    "hajb": ["ما الحجب", "معنى الحجب", "الحجب", "حجب", "حجب الحرمان", "حجب النقصان", "الحجب في المواريث"],
    "siblings_types": ["الاخ الشقيق", "الاخ لاب", "الاخ لام", "فرق بين الاخ", "انواع الاخوة", "شنو الفرق بين الاخ"],
    "estate_rights": ["ديون", "الدين", "نسدد الدين", "ترتيب الحقوق", "قبل تقسيم", "نقسم الورثة", "الوصية قبل", "تجهيز الميت"],
    "fixed_shares": ["اصحاب الفروض", "ما معنى اصحاب الفروض", "من هم اصحاب الفروض"],
    "descendant": ["الفرع الوارث", "معنى الفرع الوارث", "شنو الفرع الوارث"],
    "will": ["الوصية", "وصية لوارث", "ثلث التركة", "اوصى"],
    "mawani": ["موانع الارث", "القتل", "اختلاف الدين", "الرق"],
}


def classify(question: str, heirs: Heirs) -> str:
    t = normalize_ar(question)
    if heirs.advanced_flags:
        return "calculation"
    # الأسئلة التعريفية/الفقهية تُقدّم على الحساب حتى لو وردت فيها ألفاظ ورثة
    for intent, pats in FIQH_INTENTS.items():
        if any(p in t for p in pats):
            return "fiqh"
    if any(w in t for w in ["ما معنى", "يعني", "شنو", "ايه", "ما الفرق", "من هم", "متى", "لماذا"]):
        return "fiqh"
    # calculation if death/estate verbs and at least one extracted heir or ambiguity/advanced calculation marker
    death = any(w in t for w in ["مات", "توفي", "توفى", "توفت", "هلك", "ترك", "ساب", "خلف", "خلّف", "ورث", "ميراث", "تركة", "الميت"])
    if death and (sum(getattr(heirs, f) for f in ["husband","wives","father","mother","son","daughter","grandson","granddaughter","full_brother","full_sister","paternal_brother","paternal_sister","maternal_sibling","grandfather","grandmother"]) > 0 or heirs.ambiguous or heirs.advanced_flags):
        return "calculation"
    return "open"


def fiqh_answer(question: str, dialect: Dialect) -> Optional[str]:
    t = normalize_ar(question)
    def has(intent: str) -> bool:
        return any(p in t for p in FIQH_INTENTS[intent])

    if has("radd"):
        return "الرد هو رجوع الباقي من التركة إلى أصحاب الفروض غير الزوجين عند عدم وجود عاصب يأخذ الباقي، ويكون بنسبة فروضهم.\n\nمثال مبسط: لو مات شخص وترك بنتًا فقط، فلها النصف فرضًا، ولا يوجد عاصب، فيُرد عليها الباقي فتأخذ التركة كلها.\n\nتنبيه: في طريقة الحساب المعتمدة هنا، الزوج والزوجة لا يدخلان في الرد؛ يأخذان فرضهما فقط."
    if has("awl"):
        return "العول هو أن تزيد الفروض المقدّرة على مقدار التركة، فتُنقص أنصبة أصحاب الفروض بنسبة واحدة حتى يساوي المجموع التركة.\n\nمثال مختصر: زوج + أم + أختان شقيقتان؛ أصل الفروض يزيد على التركة، فتعول المسألة وتُخفض الأنصبة بنسبة واحدة."
    if has("siblings_types"):
        return "الفرق بين أنواع الإخوة في الميراث:\n\n- الأخ الشقيق: يشترك مع الميت في الأب والأم، وهو أقوى من الأخ لأب.\n- الأخ لأب: يشترك مع الميت في الأب فقط، وقد يحجبه الأخ الشقيق أو الابن أو الأب.\n- الأخ لأم: يشترك مع الميت في الأم فقط، ويرث بالفرض لا بالتعصيب، ويُحجب بالفرع الوارث أو الأصل الذكر.\n\nالخلاصة: الجهة مؤثرة جدًا؛ فلا يصح أن نقول فقط: أخ، بل يجب تحديده: شقيق أم لأب أم لأم."
    if has("estate_rights"):
        return "لا تُقسَّم التركة على الورثة قبل إخراج الحقوق السابقة.\n\nالترتيب المختصر: الحقوق المتعلقة بعين التركة إن وجدت، ثم تجهيز الميت بالمعروف، ثم قضاء الديون، ثم تنفيذ الوصية الصحيحة في حدود الثلث، ثم تقسيم الباقي على الورثة المستحقين.\n\nفالدين مقدَّم على قسمة الميراث، ولا يصح توزيع المال على الورثة قبل إخراجه."
    if has("tasib"):
        return "التعصيب في المواريث هو أن يرث الوارث بلا سهم مقدر ثابت؛ فيأخذ ما بقي بعد أصحاب الفروض، وقد يأخذ كل التركة إذا لم يوجد صاحب فرض، وقد لا يأخذ شيئًا إذا استغرقت الفروض التركة.\n\nأنواعه المشهورة:\n- عاصب بالنفس: مثل الابن والأخ الشقيق عند عدم من يحجبه.\n- عاصب بالغير: مثل البنت مع الابن، فيكون للذكر مثل حظ الأنثيين.\n- عاصب مع الغير: مثل الأخت الشقيقة مع البنت، فتأخذ الأخت الباقي تعصيبًا."
    if has("hajb"):
        return "الحجب في المواريث هو منع وارث من ميراثه كله أو من بعضه بسبب وجود وارث أقوى منه.\n\n- حجب حرمان: يمنع الوارث من الميراث بالكامل، مثل حجب الأخ الشقيق بالابن أو الأب.\n- حجب نقصان: لا يمنع الوارث بالكامل، لكنه ينقص نصيبه، مثل الزوجة تنقص من الربع إلى الثمن عند وجود الفرع الوارث، والأم تنقص من الثلث إلى السدس عند وجود الفرع الوارث أو جمع من الإخوة.\n\nالخلاصة: حجب الحرمان = لا يرث. حجب النقصان = يرث لكن أقل."
    if has("fixed_shares"):
        return "أصحاب الفروض هم الورثة الذين لهم أنصبة مقدّرة في الشرع، مثل: النصف، الربع، الثمن، الثلثان، الثلث، السدس.\n\nومن أمثلتهم بحسب الحالة: الزوج، الزوجة، الأب، الأم، البنت، بنت الابن، الأخت الشقيقة، الأخت لأب، والإخوة لأم.\n\nبعد إعطاء أصحاب الفروض فروضهم، يُعطى الباقي إلى العصبة إن وُجدوا."
    if has("descendant"):
        return "الفرع الوارث هو نسل الميت الذي يرث منه، مثل الابن والبنت وابن الابن وبنت الابن عند تحقق شروطهم.\n\nوجود الفرع الوارث يؤثر في أنصبة بعض الورثة؛ فالزوج ينتقل من النصف إلى الربع، والزوجة من الربع إلى الثمن، والأم غالبًا إلى السدس."
    if has("will"):
        return "الوصية تُنفذ بعد قضاء الديون وقبل تقسيم الباقي على الورثة، وتكون في حدود الثلث لغير وارث.\n\nأما الوصية لوارث فلا تُنفذ إلا إذا أجازها بقية الورثة المعتبرون بعد وفاة المورث."
    if has("mawani"):
        return "موانع الإرث هي أوصاف تمنع الشخص من الميراث مع وجود سبب القرابة أو الزوجية. من أشهرها: القتل، واختلاف الدين، والرق في كلام الفقهاء.\n\nهذه الأبواب تحتاج تحققًا من الوقائع، فلا يصح إسقاطها على حالة معينة بلا تفاصيل واضحة."
    return None


# -----------------------------
# Calculation engine
# -----------------------------

@dataclass
class Share:
    name: str
    amount: Fraction
    reason: str
    per_head: Optional[Fraction] = None
    original: Optional[Fraction] = None
    blocked: bool = False


def frac_str(f: Fraction) -> str:
    f = Fraction(f)
    if f.denominator == 1:
        return str(f.numerator)
    return f"{f.numerator}/{f.denominator}"


def pct_str(f: Fraction) -> str:
    val = float(f * 100)
    if abs(val - round(val)) < 1e-9:
        return f"{int(round(val))}%"
    return f"{val:.4f}".rstrip("0").rstrip(".") + "%"


def add_share(shares: Dict[str, Share], key: str, name: str, amount: Fraction, reason: str, per_head: Optional[Fraction]=None, original: Optional[Fraction]=None):
    if amount <= 0:
        return
    shares[key] = Share(name=name, amount=Fraction(amount), reason=reason, per_head=per_head, original=original)


def advanced_gate_message(h: Heirs, dialect: Dialect) -> Optional[str]:
    if not h.advanced_flags:
        return None
    flags = set(h.advanced_flags)
    if "grandfather_with_siblings" in flags:
        return dialect.unsupported_advanced() + "\n\n- ظهر في المسألة جد مع إخوة، وهذا باب له تفصيل وخلاف بين طرق الفرضيين. حدّد المذهب أو الطريقة القضائية المعتمدة قبل الحساب."
    if "manasakhat" in flags:
        return dialect.unsupported_advanced() + "\n\n- ظهرت مناسخة: وارث مات قبل قسمة التركة. اذكر الورثة في الوفاة الأولى، ثم ورثة الوارث الذي مات، ومقدار نصيبه إن عُرف."
    if "pregnancy" in flags:
        return dialect.unsupported_advanced() + "\n\n- وجود حمل/جنين يحتاج إيقاف نصيب محتمل حتى تتضح الولادة والجنس والعدد."
    if "missing" in flags:
        return dialect.unsupported_advanced() + "\n\n- المفقود يحتاج حكمًا قضائيًا أو مدة معتبرة قبل توزيع نهائي."
    if "intersex" in flags:
        return dialect.unsupported_advanced() + "\n\n- الخنثى يحتاج تحديد الحالة أو طريقة المعاملة الفقهية المعتمدة."
    if "killer" in flags or "religion" in flags:
        return dialect.unsupported_advanced() + "\n\n- ظهر مانع محتمل من موانع الإرث، ولا بد من تحقق الواقعة قبل الحكم."
    if "dhawu_arham" in flags:
        return dialect.unsupported_advanced() + "\n\n- ظهر وارث من ذوي الأرحام أو قرابة غير مباشرة، وهذا الباب لا يُحسب قبل التأكد من عدم أصحاب الفروض والعصبات وتحديد طريقة التوريث المعتمدة."
    return None


def calculate(heirs: Heirs, dialect: Dialect) -> str:
    if heirs.ambiguous:
        lines = [dialect.needs_clarification(), ""]
        lines += [f"- {x}" for x in heirs.ambiguous]
        lines += ["", "أعد كتابة الورثة بوضوح، مثل: زوجة، بنت، أخ شقيق / أخ لأب / أخ لأم، مع عدد الأبناء والبنات إن وجدوا."]
        return "\n".join(lines)

    gate = advanced_gate_message(heirs, dialect)
    if gate:
        return gate

    h = heirs
    shares: Dict[str, Share] = {}
    blocked_notes: List[str] = []
    hajb_notes: List[str] = []

    # Blocked heirs by close heirs
    # Father blocks siblings (except in advanced grandfather not here)
    father_like = h.father > 0
    male_desc = h.male_descendant()
    desc = h.any_descendant()

    # Spouses
    if h.husband:
        amt = Fraction(1, 4) if desc else Fraction(1, 2)
        reason = "للزوج الربع لوجود فرع وارث." if desc else "للزوج النصف لعدم وجود فرع وارث."
        add_share(shares, "husband", "الزوج", amt, reason)
        if desc:
            hajb_notes.append("الزوج حُجب حجب نقصان من النصف إلى الربع بسبب الفرع الوارث.")
    if h.wives:
        amt_total = Fraction(1, 8) if desc else Fraction(1, 4)
        reason = "للزوجة الثمن لوجود فرع وارث." if desc else "للزوجة الربع لعدم وجود فرع وارث."
        name = "الزوجة" if h.wives == 1 else "الزوجات"
        per = amt_total / h.wives if h.wives > 1 else None
        add_share(shares, "wives", name, amt_total, reason, per_head=per)
        if desc:
            hajb_notes.append("الزوجة حُجبت حجب نقصان من الربع إلى الثمن بسبب الفرع الوارث.")

    # Mother incl. Umariyat handling
    umariyat = False
    if h.mother:
        if desc or h.siblings_count() >= 2:
            amt = Fraction(1, 6)
            if desc:
                reason = "للأم السدس لوجود فرع وارث."
                hajb_notes.append("الأم حُجبت حجب نقصان من الثلث إلى السدس بسبب وجود فرع وارث.")
            else:
                reason = "للأم السدس لوجود جمع من الإخوة."
                hajb_notes.append("الأم حُجبت حجب نقصان من الثلث إلى السدس بسبب جمع من الإخوة.")
            add_share(shares, "mother", "الأم", amt, reason)
        else:
            # If father and spouse, mother gets 1/3 remainder (Umariyat)
            if h.father and (h.husband or h.wives) and not desc:
                # postpone until after spouse fixed known; mark as original calculated later
                umariyat = True
            else:
                add_share(shares, "mother", "الأم", Fraction(1, 3), "للأم الثلث لعدم وجود فرع وارث ولا جمع من الإخوة.")

    # Descendants: sons/daughters or grandsons/granddaughters
    # If son exists, children share residue after fixed shares. daughters do not fixed.
    # Grandchildren blocked by son.
    if h.son:
        if h.grandson or h.granddaughter:
            blocked_notes.append("أولاد الابن محجوبون بالابن.")
    else:
        # no son; grandsons may act as male descendants for lower line and block siblings if exist
        pass

    # Father fixed share
    father_gets_residue = False
    if h.father:
        if h.son or h.grandson:
            add_share(shares, "father", "الأب", Fraction(1, 6), "للأب السدس فرضًا فقط مع وجود فرع وارث ذكر.")
        elif desc:
            add_share(shares, "father", "الأب", Fraction(1, 6), "للأب السدس فرضًا مع الفرع الوارث الأنثى، ويأخذ الباقي تعصيبًا إن بقي بعد الفروض.")
            father_gets_residue = True
        else:
            father_gets_residue = True
    # Siblings blocked by father or male descendant
    siblings_blocked = father_like or h.son or h.grandson

    # Daughters/granddaughters fixed unless with male equal/lower
    child_residuary = False
    grandchild_residuary = False
    if h.son:
        child_residuary = True
    elif h.daughter:
        if h.daughter == 1:
            add_share(shares, "daughter", "البنت", Fraction(1, 2), "للبنت الواحدة النصف فرضًا عند عدم الابن المعصب.")
        else:
            add_share(shares, "daughter", "البنات", Fraction(2, 3), "للبنات الثلثان فرضًا عند التعدد وعدم وجود ابن معصب.", per_head=Fraction(2, 3)/h.daughter)

    # Granddaughters (son's daughters)
    if not h.son:
        if h.grandson:
            grandchild_residuary = True
        elif h.granddaughter:
            if h.daughter == 0:
                if h.granddaughter == 1:
                    add_share(shares, "granddaughter", "بنت الابن", Fraction(1, 2), "لبنت الابن النصف عند عدم الابن والبنت وابن الابن المعصب.")
                else:
                    add_share(shares, "granddaughter", "بنات الابن", Fraction(2, 3), "لبنات الابن الثلثان عند التعدد وعدم الابن والبنت وابن الابن المعصب.", per_head=Fraction(2, 3)/h.granddaughter)
            elif h.daughter == 1:
                add_share(shares, "granddaughter", "بنت الابن" if h.granddaughter == 1 else "بنات الابن", Fraction(1, 6), "لبنت الابن/بنات الابن السدس تكملةً للثلثين مع البنت الواحدة، عند عدم ابن ابن معصب.", per_head=(Fraction(1,6)/h.granddaughter if h.granddaughter>1 else None))
            else:
                blocked_notes.append("بنات الابن محجوبات بالبنتين فأكثر، ما لم يوجد ابن ابن يعصبهن.")

    # Maternal siblings fixed if not blocked
    if h.maternal_sibling:
        if desc or h.father or h.grandfather:
            blocked_notes.append("الإخوة لأم محجوبون بالفرع الوارث أو الأصل الذكر.")
        else:
            if h.maternal_sibling == 1:
                add_share(shares, "maternal_sibling", "الأخ/الأخت لأم", Fraction(1, 6), "للأخ أو الأخت لأم السدس عند الانفراد، مع عدم الفرع الوارث والأصل الذكر.")
            else:
                add_share(shares, "maternal_sibling", "الإخوة لأم مجتمعين", Fraction(1, 3), "الإخوة لأم يشتركون في الثلث بالسوية، ذكرهم وأنثاهم سواء، عند عدم الفرع الوارث والأصل الذكر.", per_head=Fraction(1,3)/h.maternal_sibling)

    # Full siblings
    full_sibs_residuary = False
    full_sister_asaba_with_daughters = False
    if h.full_brother or h.full_sister:
        if siblings_blocked:
            blocked_notes.append("الإخوة الأشقاء محجوبون بالأب أو الفرع الوارث الذكر.")
        else:
            if h.full_brother:
                full_sibs_residuary = True
            elif h.full_sister:
                # with daughters, full sisters become asaba with others
                if h.daughter or h.granddaughter:
                    full_sister_asaba_with_daughters = True
                else:
                    if h.full_sister == 1:
                        add_share(shares, "full_sister", "الأخت الشقيقة", Fraction(1, 2), "للأخت الشقيقة النصف فرضًا عند عدم الفرع الوارث والأصل الذكر والأخ الشقيق المعصب.")
                    else:
                        add_share(shares, "full_sister", "الأخوات الشقيقات", Fraction(2, 3), "للأخوات الشقيقات الثلثان فرضًا عند التعدد وعدم الفرع الوارث والأصل الذكر والأخ الشقيق المعصب.", per_head=Fraction(2,3)/h.full_sister)

    # Paternal siblings
    paternal_sibs_residuary = False
    if h.paternal_brother or h.paternal_sister:
        if h.father or h.son or h.grandson or h.full_brother:
            blocked_notes.append("الإخوة لأب محجوبون بالأب أو الفرع الوارث الذكر أو الأخ الشقيق.")
        else:
            if h.paternal_brother:
                paternal_sibs_residuary = True
            elif h.paternal_sister:
                if h.full_sister >= 2:
                    blocked_notes.append("الأخوات لأب محجوبات بالأختين الشقيقتين فأكثر، ما لم يوجد أخ لأب يعصبهن.")
                elif h.full_sister == 1:
                    add_share(shares, "paternal_sister", "الأخت لأب" if h.paternal_sister == 1 else "الأخوات لأب", Fraction(1, 6), "للأخت لأب/الأخوات لأب السدس تكملةً للثلثين مع الأخت الشقيقة الواحدة، عند عدم الأخ لأب المعصب.", per_head=(Fraction(1,6)/h.paternal_sister if h.paternal_sister>1 else None))
                elif h.daughter or h.granddaughter:
                    # sisters paternal can be asaba with daughters if no full sister? yes for sisters with daughters
                    paternal_sibs_residuary = True
                else:
                    if h.paternal_sister == 1:
                        add_share(shares, "paternal_sister", "الأخت لأب", Fraction(1, 2), "للأخت لأب النصف عند عدم الشقيقات والمعصب والحاجب.")
                    else:
                        add_share(shares, "paternal_sister", "الأخوات لأب", Fraction(2, 3), "للأخوات لأب الثلثان عند التعدد وعدم الشقيقات والمعصب والحاجب.", per_head=Fraction(2,3)/h.paternal_sister)

    # Umariyat mother as 1/3 remainder after spouse
    if umariyat:
        fixed_without_mother = sum(s.amount for k, s in shares.items() if k != "mother")
        mother_amt = (Fraction(1) - fixed_without_mother) / 3
        add_share(shares, "mother", "الأم", mother_amt, "هذه من العمريتين: للأم ثلث الباقي بعد فرض الزوج/الزوجة مع وجود الأب وعدم الفرع الوارث.")

    # Sum fixed shares and apply awl if > 1 before residue
    fixed_sum = sum(s.amount for s in shares.values())
    awl = False
    awl_original_sum = fixed_sum
    if fixed_sum > 1:
        awl = True
        # reduce each fixed share proportionally: new = old / fixed_sum
        for s in shares.values():
            s.original = s.amount
            s.amount = s.amount / fixed_sum
            if s.per_head is not None:
                s.per_head = s.per_head / fixed_sum
            s.reason = f"الحكم الأصلي قبل العول: {s.reason.replace('فرضًا ', 'فرضًا ')} وكان نصيبه الأصلي {frac_str(s.original)}، ثم صار نصيبه النهائي بعد العول {frac_str(s.amount)}."
        fixed_sum = Fraction(1)

    residue = Fraction(1) - fixed_sum

    # Residuary distributions (no awl if residue)
    if not awl and residue > 0:
        # father residue first if father present (after daughters etc)
        if father_gets_residue and h.father:
            existing = shares.get("father")
            if existing:
                existing.amount += residue
                existing.reason = existing.reason.replace("ويأخذ الباقي تعصيبًا إن بقي بعد الفروض.", "وأخذ الباقي تعصيبًا بعد أصحاب الفروض.")
            else:
                add_share(shares, "father", "الأب", residue, "الأب يأخذ الباقي تعصيبًا عند عدم الفرع الوارث.")
            residue = Fraction(0)
        elif child_residuary:
            units = h.son * 2 + h.daughter
            if units:
                if h.son:
                    add_share(shares, "son", "الابن" if h.son == 1 else "الأبناء", residue * h.son * 2 / units, "الابن عصبة بالنفس، ويعصب البنت معه؛ فيُقسم الباقي بين الأولاد للذكر مثل حظ الأنثيين.", per_head=(residue * 2 / units if h.son > 1 else None))
                if h.daughter:
                    add_share(shares, "daughter", "البنت" if h.daughter == 1 else "البنات", residue * h.daughter / units, "البنت صارت عصبة بالغير مع الابن، ويُقسم الباقي بينهما للذكر مثل حظ الأنثيين.", per_head=(residue / units if h.daughter > 1 else None))
                residue = Fraction(0)
        elif grandchild_residuary:
            units = h.grandson * 2 + h.granddaughter
            if units:
                if h.grandson:
                    add_share(shares, "grandson", "ابن الابن" if h.grandson == 1 else "أبناء الابن", residue * h.grandson * 2 / units, "ابن الابن عصبة عند عدم الابن، ويعصب بنت الابن معه؛ للذكر مثل حظ الأنثيين.", per_head=(residue * 2 / units if h.grandson > 1 else None))
                if h.granddaughter:
                    # if already fixed share exists for granddaughter and also grandson? normally no fixed, but combine if exists
                    add_share(shares, "granddaughter", "بنت الابن" if h.granddaughter == 1 else "بنات الابن", residue * h.granddaughter / units, "بنت الابن صارت عصبة بالغير مع ابن الابن؛ للذكر مثل حظ الأنثيين.", per_head=(residue / units if h.granddaughter > 1 else None))
                residue = Fraction(0)
        elif full_sibs_residuary:
            units = h.full_brother * 2 + h.full_sister
            if units:
                if h.full_brother:
                    add_share(shares, "full_brother", "الأخ الشقيق" if h.full_brother == 1 else "الإخوة الأشقاء", residue * h.full_brother * 2 / units, "الإخوة الأشقاء عصبة عند عدم الأب والفرع الوارث الذكر؛ للذكر مثل حظ الأنثيين.", per_head=(residue * 2 / units if h.full_brother > 1 else None))
                if h.full_sister:
                    add_share(shares, "full_sister", "الأخت الشقيقة" if h.full_sister == 1 else "الأخوات الشقيقات", residue * h.full_sister / units, "الأخت الشقيقة صارت عصبة بالغير مع الأخ الشقيق؛ للذكر مثل حظ الأنثيين.", per_head=(residue / units if h.full_sister > 1 else None))
                residue = Fraction(0)
        elif full_sister_asaba_with_daughters:
            add_share(shares, "full_sister", "الأخت الشقيقة" if h.full_sister == 1 else "الأخوات الشقيقات", residue, "الأخت الشقيقة/الأخوات الشقيقات يأخذن الباقي تعصيبًا مع الغير لوجود فرع وارث أنثى وعدم وجود حاجب.", per_head=(residue/h.full_sister if h.full_sister>1 else None))
            residue = Fraction(0)
        elif paternal_sibs_residuary:
            units = h.paternal_brother * 2 + h.paternal_sister
            if units:
                if h.paternal_brother:
                    add_share(shares, "paternal_brother", "الأخ لأب" if h.paternal_brother == 1 else "الإخوة لأب", residue * h.paternal_brother * 2 / units, "الأخ لأب يأخذ الباقي تعصيبًا عند عدم الأب والفرع الوارث الذكر والأخ الشقيق.", per_head=(residue*2/units if h.paternal_brother>1 else None))
                if h.paternal_sister:
                    add_share(shares, "paternal_sister", "الأخت لأب" if h.paternal_sister == 1 else "الأخوات لأب", residue * h.paternal_sister / units, "الأخت لأب صارت عصبة بالغير مع الأخ لأب أو مع الغير عند وجود فرع وارث أنثى، بحسب صورة المسألة.", per_head=(residue/units if h.paternal_sister>1 else None))
                residue = Fraction(0)

    # Radd if residue remains and no residuary: to fixed heirs excluding spouses
    if not awl and residue > 0:
        radd_keys = [k for k in shares.keys() if k not in ("husband", "wives")]
        radd_base = sum(shares[k].amount for k in radd_keys)
        if radd_keys and radd_base > 0:
            for k in radd_keys:
                s = shares[k]
                old = s.amount
                inc = residue * old / radd_base
                s.original = old
                s.amount = old + inc
                if s.per_head is not None:
                    # scale per head by new/old
                    s.per_head = s.per_head * s.amount / old
                s.reason = f"الحكم الأصلي قبل الرد: {s.reason} وكان نصيبه الأصلي {frac_str(old)}، ثم زاد نصيبه بالرد إلى {frac_str(s.amount)} لعدم وجود عاصب."
            residue = Fraction(0)
        # If only spouse and residue, it remains? In practice may go to بيت المال/ذوي الأرحام depending. Ask? We'll note.

    # If father fixed and no residue, adjust reason phrase
    if "father" in shares and "ويأخذ الباقي تعصيبًا إن بقي" in shares["father"].reason and residue == 0:
        shares["father"].reason = "للأب السدس فرضًا مع الفرع الوارث الأنثى، ولم يبق له شيء تعصيبًا لاستغراق الفروض التركة."

    return render_calculation(shares, awl, awl_original_sum, hajb_notes, blocked_notes, dialect, residue)


def render_calculation(shares: Dict[str, Share], awl: bool, awl_original_sum: Fraction, hajb_notes: List[str], blocked_notes: List[str], dialect: Dialect, residue: Fraction) -> str:
    if not shares and not blocked_notes:
        return dialect.needs_clarification() + "\n\n- لم أستخرج ورثة كافيين للحساب. اذكر الورثة بوضوح."
    # Sort by Islamic/common priority? Descendants, spouses, parents, siblings
    order = ["son", "daughter", "grandson", "granddaughter", "husband", "wives", "father", "mother", "full_brother", "full_sister", "paternal_brother", "paternal_sister", "maternal_sibling"]
    lines = [dialect.calc_header(), ""]
    for k in order:
        if k not in shares:
            continue
        s = shares[k]
        lines.append(f"- {s.name}: {frac_str(s.amount)} من التركة ({pct_str(s.amount)})")
        if s.per_head is not None:
            lines.append(f"  نصيب الفرد الواحد: {frac_str(s.per_head)} من التركة ({pct_str(s.per_head)})")
        lines.append(f"  السبب: {s.reason}")
    if awl:
        lines += ["", f"تنبيه: عالت المسألة لأن مجموع الفروض قبل العول بلغ {frac_str(awl_original_sum)} من التركة، فخُفِّضت الأنصبة بنسبة واحدة حتى صار المجموع 1."]
    # Radd detection
    if any(s.original is not None and s.amount > s.original for s in shares.values()):
        lines += ["", "تنبيه: بقي جزء من التركة ولا توجد عصبة، فرُدَّ الباقي على أصحاب الفروض غير الزوجين بنسبة فروضهم."]
    if hajb_notes:
        lines += ["", "الحجب:"] + [f"- {n}" for n in dict.fromkeys(hajb_notes)]
    if blocked_notes:
        lines += ["", "ورثة محجوبون:"] + [f"- {n}" for n in dict.fromkeys(blocked_notes)]
    total = sum(s.amount for s in shares.values())
    if residue > 0:
        lines += ["", f"تنبيه: بقي {frac_str(residue)} من التركة، ولم أجد عاصبًا واضحًا في السؤال. قد يحتاج الأمر إلى تحديد ذوي الأرحام أو جهة قضائية/مذهب معتمد."]
        total += residue
    lines += ["", f"مراجعة مجموع الأنصبة: {frac_str(sum(s.amount for s in shares.values()))} من التركة."]
    return "\n".join(lines)


# -----------------------------
# Local model fallback with review filter
# -----------------------------

BAD_PATTERNS = [
    r"زوجة\s+النصف", r"الزوجة\s+النصف", r"البنت\s+الثلث\b", r"ولد الزنا", r"ابن الخنثى",
    r"الله:\s*1", r"اضف هذا الباب", r"sft", r"rag", r"نموذج محلي غير مستقر",
]


def call_ollama(question: str, model: str = "mawarith_ai", timeout: int = 25) -> Optional[str]:
    url = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
    model = os.environ.get("OLLAMA_MODEL", model)
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": "أنت مساعد متخصص في علم المواريث. أجب بدقة، ولا تخمن. إذا كانت المسألة حسابية أو ناقصة فاطلب البيانات اللازمة. لا تذكر أدوات أو تدريب أو RAG."},
            {"role": "user", "content": question},
        ],
        "options": {"temperature": 0.1, "top_p": 0.9}
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("message", {}).get("content") or data.get("response")
    except Exception:
        return None


def review_model_answer(ans: Optional[str]) -> Optional[str]:
    if not ans:
        return None
    a = ans.strip()
    if len(a) < 8:
        return None
    if len(a) > 2500:
        a = a[:2500].rsplit(" ", 1)[0] + "..."
    na = normalize_ar(a)
    for pat in BAD_PATTERNS:
        if re.search(pat, na):
            return None
    # repeated fragments heuristic
    words = na.split()
    if len(words) > 80:
        chunks = [" ".join(words[i:i+8]) for i in range(0, len(words)-8, 8)]
        if len(chunks) != len(set(chunks)) and len(chunks) - len(set(chunks)) > 2:
            return None
    return a


# -----------------------------
# Main answering
# -----------------------------


def answer(question: str) -> str:
    dialect = detect_dialect(question)
    heirs = extract_heirs(question)
    kind = classify(question, heirs)
    if kind == "calculation":
        return calculate(heirs, dialect)
    if kind == "fiqh":
        fa = fiqh_answer(question, dialect)
        if fa:
            return fa
        ans = review_model_answer(call_ollama(question))
        if ans:
            return ans
        return dialect.unsupported_advanced() + "\n\nاكتب السؤال بتفاصيل أكثر أو حدّد الباب الفقهي المقصود، وسأجيب بدون تخمين."
    # open fallback
    ans = review_model_answer(call_ollama(question))
    if ans:
        return ans
    return "اكتب السؤال بصيغة أوضح: هل تريد حساب مسألة ميراث، أم شرح حكم فقهي في المواريث؟"


def cli():
    print("مفتي المواريث الذكي - اكتب السؤال، أو exit للخروج.\n")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q.lower() in {"exit", "quit", "خروج"}:
            break
        print(answer(q))
        print()


if __name__ == "__main__":
    cli()
