# -*- coding: utf-8 -*-
"""
Mawareth AI v45 — Full Scholarly Production Architecture

Purpose
-------
A lightweight, deterministic intelligence layer for Arabic dialogue, dialects,
fiqh/inheritance routing, follow-up understanding, and safe production behavior.

Constraints preserved:
- No RAG.
- No fixed answer per user question.
- No inheritance calculation inside this layer.
- Does not replace the inheritance engine; it protects and routes into it.

This module is intentionally small enough for Python 3.11 on a normal Windows machine.
It uses optional PyArabic/RapidFuzz/Babel/dateparser when installed, and degrades safely.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from pyarabic import araby as _araby  # type: ignore
except Exception:
    _araby = None

try:
    from rapidfuzz import fuzz as _fuzz  # type: ignore
except Exception:
    _fuzz = None

try:
    from babel.numbers import format_decimal  # type: ignore
except Exception:
    format_decimal = None

DIAC = re.compile(r"[\u064b-\u0652\u0670\u0640]")
PUNCT = re.compile(r"[\u061f؟?!.,;:،؛\[\]{}()<>\"'`~|\\/]+")

_ARABIC_DIGITS = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه",
    "گ": "ك", "چ": "ج", "پ": "ب", "ڤ": "ف",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
})


def normalize(text: str) -> str:
    s = str(text or "")
    s = s.replace("\ufeff", "").replace("\u200f", "").replace("\u200e", "")
    if _araby is not None:
        try:
            s = _araby.strip_tashkeel(s)
            s = _araby.strip_tatweel(s)
            s = _araby.normalize_hamza(s)
        except Exception:
            pass
    s = DIAC.sub("", s)
    s = s.translate(_ARABIC_DIGITS)
    s = PUNCT.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def words(text: str) -> List[str]:
    return normalize(text).split()


def contains_word(n: str, w: str) -> bool:
    ww = normalize(w)
    return bool(ww and re.search(r"(^|\s)" + re.escape(ww) + r"($|\s)", n))


def contains_any(n: str, phrases: List[str]) -> bool:
    return any(normalize(p) and normalize(p) in n for p in phrases)


def fuzzy_any(n: str, phrases: List[str], threshold: int = 88, max_words: int = 16) -> bool:
    if contains_any(n, phrases):
        return True
    if _fuzz is None or len(n.split()) > max_words:
        return False
    for p in phrases:
        pn = normalize(p)
        if not pn:
            continue
        try:
            if _fuzz.partial_ratio(pn, n) >= threshold:
                return True
        except Exception:
            continue
    return False


def stable_pick(options: List[str], seed: str) -> str:
    if not options:
        return ""
    h = int(hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
    return options[h % len(options)]

# Dialogue acts: broad categories, not single-case patches.
SOCIAL_GREETING = [
    "السلام عليكم", "سلام عليكم", "السلام عليكم ورحمه الله", "السلام عليكم ورحمة الله", "سلام", "سلامو عليكم",
    "اهلا", "اهلين", "اهلا وسهلا", "اهلين وسهلين", "هلا", "هلا والله", "يا هلا", "مرحبا", "مرحب", "مرحبتين",
    "صباح الخير", "صباح النور", "صباح الفل", "صباح الورد", "مسا الخير", "مساء الخير", "مساء النور", "مساء الفل", "مساء الورد",
    "هاي", "hi", "hello", "الو", "الوو", "ألو",
]
SOCIAL_STATUS_ASK = [
    "كيف حالك", "كيف الحال", "كيفك", "اخبارك", "وش اخبارك", "ايه اخبارك", "ازيك", "ازايك", "عامل ايه", "عامله ايه",
    "طمني عليك", "كيف الامور", "كيف صحتك", "شلونك", "شخبارك", "علومك", "عساك طيب", "واش خبارك", "شنو اخبارك",
    "كيف انت", "انت كيف", "كيفك انت", "اخبار الدنيا", "ايه الدنيا", "كل شي تمام",
]
SOCIAL_STATUS_REPLY = [
    "بخير", "انا بخير", "الحمد لله", "الحمدلله", "الحمد لله بخير", "بخير الحمد لله", "تمام", "تمام الحمد لله", "كويس", "كويس الحمد لله",
    "طيب", "طيبين", "طيبين الحمد لله", "بالف خير", "بألف خير", "كله تمام", "كلو تمام", "ماشي الحال", "زي الفل", "عال العال",
    "مزيان", "مزيان الحمد لله", "لاباس", "لا باس", "بخير الله يسلمك", "بخير دامك بخير", "تمام يا غالي", "الحمد لله على كل حال",
]
SOCIAL_THANKS = [
    "شكرا", "شكرًا", "متشكر", "مشكور", "تسلم", "تسلمي", "جزاك الله", "جزاكم الله", "بارك الله فيك", "يعطيك العافيه",
    "يعطيك العافية", "الله يجزاك خير", "ربنا يبارك", "الف شكر", "ألف شكر", "تمام شكرا",
]
SOCIAL_ACK = ["تمام", "اوكي", "اوك", "ok", "حاضر", "تم", "ماشي", "طيب", "جميل", "واضح", "حلو", "اتفقنا"]
IDENTITY = ["انت مين", "مين انت", "من انت", "ما اسمك", "اسمك ايه", "وش اسمك", "ايش اسمك", "ما وظيفتك", "مين حضرتك"]

FOLLOWUP_SIMPLIFY = [
    "مش فاهم", "مش فاهمه", "مفهمتش", "مافهمتش", "ما فهمتش", "ما فهمت", "ما افهم", "ما أفهم", "لم افهم", "لم أفهم",
    "مو فاهم", "ماني فاهم", "مب فاهم", "مش مستوعب", "مو مستوعب", "ما استوعبت", "مش واضح", "مو واضح", "ما واضح", "غير واضح",
    "وضح", "وضحلي", "وضح لي", "وضحهالي", "فهمني", "فهمني اكتر", "عيد الشرح", "اعد الشرح", "بسط", "بسطها", "بسطلي",
    "اشرح ابسط", "اشرحها ابسط", "اشرح ببساطة", "سهلها", "بالراحة", "واحدة واحدة", "خطوة خطوة", "شوي شوي", "مش واصل", "ما وصلني",
    "وش يعني", "شنو يعني", "ايش يعني", "يعني شنو", "يعني ايه", "ايه المقصود", "لسه مش فاهم",
]
FOLLOWUP_EXAMPLE = [
    "مثال", "هات مثال", "اديني مثال", "اعطني مثال", "وريني مثال", "مثال عملي", "مثال بالارقام", "مثال بالأرقام", "طبق", "طبقها",
    "طبقلي", "بالارقام", "بالأرقام", "مثال رقمي", "بفلوس", "بالفلوس", "احسبها بالمبلغ", "كم يطلع بالريال", "لو التركة", "على مبلغ", "بمبلغ",
]
FOLLOWUP_DETAIL = ["فصل", "فصّل", "بالتفصيل", "شرح كامل", "زود شرح", "الدليل", "اي الدليل", "وش الدليل", "ليه", "لماذا", "سبب", "السبب", "كيف طلعت", "ازاي طلعت", "كيف حسبتها", "ازاي حسبتها"]

DEATH_TERMS = ["مات", "ماتت", "توفي", "توفيت", "توفى", "توفت", "هلك", "هلكت", "ماتوا", "توفوا", "وفاة", "وفاه"]
LEAVE_TERMS = ["ترك", "تركت", "ساب", "سابت", "خلف", "خلفت", "خلّف", "خلّفت", "وراه", "ورثه", "ورثة", "تركة", "تركه"]
RELATIVES = [
    "زوج", "زوجة", "زوجه", "زوجته", "زوجها", "مراته", "مرتو", "حرمته", "ابن", "ابنه", "بنته", "بنت", "بنات", "اولاد", "عيال", "ذرية",
    "اب", "أب", "ابوه", "أبوه", "ام", "أم", "امه", "أمه", "اخ", "أخ", "اخت", "أخت", "اخوه", "اختها", "جد", "جده", "جدة", "عم", "عمه", "عمة", "خال", "خاله", "خالة",
]
FIQH = [
    "ميراث", "مواريث", "فرائض", "فرايض", "فريضه", "فريضة", "تركة", "تركه", "نصيب", "قسمة", "قسمه", "وارث", "يرث", "الورثة", "الورثه",
    "حجب", "الحجب", "تعصيب", "عاصب", "العصبة", "العصبه", "عول", "العول", "رد", "الرد", "عمرية", "العمرية", "عمريتان", "الغراوان", "الغراوين",
    "كلالة", "الكلالة", "وصية", "وصيه", "ديون", "دين", "مناسخة", "مناسخات", "خنثى", "مفقود", "حمل", "اصحاب الفروض", "أصحاب الفروض",
    "نصف", "ثلث", "ربع", "ثمن", "سدس", "ثلثين", "الفروض المقدرة", "الفروض المقدره", "الأكدرية", "اكدرية", "الحمارية", "المشتركة", "ذوي الارحام", "ذوو الارحام", "التخارج",
]
MONEY_HINTS = ["ريال", "جنيه", "دولار", "درهم", "دينار", "يورو", "فرنك", "ليره", "ليرة", "روبيه", "روبية", "مليون", "الف", "ألف", "نص مليون", "نصف مليون", "100k", "m ", "k "]
QUESTION_WORDS = ["ما", "ماذا", "كم", "كيف", "متى", "هل", "من", "لماذا", "ليه", "وش", "شنو", "ايش", "ازاي", "معنى", "معني", "حكم", "الفرق"]
ADVANCED = ["جد مع الاخوة", "جد مع اخوة", "اكدرية", "الأكدرية", "مشتركة", "حمارية", "ذوي الارحام", "ذوو الارحام", "خنثى", "مفقود", "حمل", "مناسخة", "مناسخات", "ثم مات", "بعده مات", "بعدها مات", "وبعده مات", "وبعدها مات", "تخارج"]

DIALECT_MARKERS = {
    "egyptian": ["ازيك", "ازايك", "ايه", "عايز", "عاوز", "مش", "مفهمتش", "مراته", "ساب", "مساء الفل", "صباح الفل", "عامل ايه", "زي الفل", "يا باشا"],
    "gulf": ["وش", "ايش", "شلون", "ابشر", "كذا", "رجال", "حياك", "عساك", "ماني", "مو", "هلا والله", "يعطيك العافيه", "علومك"],
    "shami": ["شو", "قديش", "هيك", "بدي", "كيفك", "عم ", "مو "],
    "moroccan": ["شنو", "واش", "فالميراث", "بزاف", "ديال", "نعاونك", "مزيان"],
    "sudanese": ["الزول", "عندو", "عامل شنو"],
    "iraqi": ["شلون", "شكو", "اكو"],
}


def detect_dialect(text: str, context: Optional[dict] = None) -> str:
    n = normalize(text)
    scores = {k: sum(1 for m in vals if normalize(m) in n) for k, vals in DIALECT_MARKERS.items()}
    best = max(scores, key=lambda k: scores[k]) if scores else "standard"
    if scores.get(best, 0) > 0:
        return best
    if context and context.get("last_dialect"):
        return str(context.get("last_dialect"))
    return "standard"


def _score_domain(n: str) -> int:
    score = 0
    has_death = contains_any(n, DEATH_TERMS)
    has_leave = contains_any(n, LEAVE_TERMS)
    has_relative = any(contains_word(n, r) or normalize(r) in n for r in RELATIVES)
    has_fiqh = contains_any(n, FIQH)
    has_money = contains_any(n, MONEY_HINTS) or bool(re.search(r"\b\d+[\d,\.]*\b", n))
    has_q = any(contains_word(n, q) or n.startswith(normalize(q) + " ") for q in QUESTION_WORDS)
    if has_death: score += 4
    if has_leave: score += 3
    if has_relative: score += 3
    if has_fiqh: score += 4
    if has_money and (has_death or has_leave or has_relative or has_fiqh): score += 2
    if has_q and has_fiqh: score += 2
    if has_death and has_relative: score += 4
    if has_leave and has_relative: score += 3
    return score


def _score_social(n: str, context: Optional[dict]) -> Tuple[int, str]:
    if len(n.split()) > 20:
        return 0, ""
    score = 0
    intent = ""
    if fuzzy_any(n, SOCIAL_GREETING, 86, 16):
        score += 6; intent = "social_greeting"
    if fuzzy_any(n, SOCIAL_STATUS_ASK, 84, 16):
        score += 7; intent = "social_status" if not intent else "social_greeting_status"
    if fuzzy_any(n, SOCIAL_STATUS_REPLY, 84, 12):
        score += 7; intent = "social_status_reply"
        last = normalize(str((context or {}).get("last_answer", "")))
        if any(x in last for x in ["عامل ايه", "طمني", "عساك", "اخبارك", "كيفك", "تكون بخير", "انت كيف", "كيف الحال"]):
            score += 2
    if fuzzy_any(n, SOCIAL_THANKS, 86, 12):
        score += 6; intent = "social_thanks"
    if fuzzy_any(n, SOCIAL_ACK, 92, 7):
        score += 4; intent = intent or "social_ack"
    if fuzzy_any(n, IDENTITY, 86, 10):
        score += 6; intent = "identity"
    return score, intent


def _followup(n: str) -> str:
    if len(n.split()) > 26:
        return ""
    if fuzzy_any(n, FOLLOWUP_EXAMPLE, 82, 22): return "followup_example"
    if fuzzy_any(n, FOLLOWUP_SIMPLIFY, 80, 24): return "followup_simplify"
    if fuzzy_any(n, FOLLOWUP_DETAIL, 82, 22): return "followup_detail"
    return ""


@dataclass
class Route:
    intent: str
    confidence: float
    dialect: str
    domain: bool
    social: bool
    followup: bool
    allow_preamble: bool
    processing_notice: bool
    review_required: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def route(text: str, context: Optional[dict] = None) -> Route:
    n = normalize(text)
    dialect = detect_dialect(text, context)
    if not n:
        return Route("empty", 1, dialect, False, True, False, False, False, False, "empty")
    dscore = _score_domain(n)
    sscore, sintent = _score_social(n, context)
    fup = _followup(n)
    # Strong domain must win over social phrases inside a real inheritance question.
    if dscore >= 6:
        if contains_any(n, ADVANCED):
            return Route("advanced_or_composite", .90, dialect, True, False, False, True, True, True, f"domain={dscore};advanced")
        if contains_any(n, DEATH_TERMS) or contains_any(n, LEAVE_TERMS) or any(w in n for w in ["نصيب", "قسمة", "قسمه", "تركة", "تركه"]):
            return Route("inheritance_calculation", .94, dialect, True, False, False, True, True, False, f"domain={dscore};calc")
        return Route("fiqh_question", .91, dialect, True, False, False, True, True, False, f"domain={dscore};fiqh")
    if fup:
        has_ctx = bool((context or {}).get("last_answer") or (context or {}).get("last_concept") or (context or {}).get("last_question"))
        return Route(fup, .90 if has_ctx else .70, dialect, False, False, True, False, False, not has_ctx, f"followup={fup};has_ctx={has_ctx}")
    # Social wins when no real domain signal.
    if sscore >= 4 and dscore < 6:
        return Route(sintent or "social", min(.99, .60 + sscore/20), dialect, False, True, False, False, False, False, f"social={sscore};domain={dscore}")
    # Non-domain question should not leak to fiqh/model path.
    if any(contains_word(n, q) or n.startswith(normalize(q) + " ") for q in QUESTION_WORDS):
        return Route("general_non_domain", .65, dialect, False, False, False, False, False, False, "question_no_domain")
    if len(n.split()) <= 9:
        return Route("small_unknown", .55, dialect, False, False, False, False, False, False, "short_unknown")
    return Route("unknown", .50, dialect, False, False, False, False, False, True, "unknown")


def is_social(text: str, context: Optional[dict] = None) -> bool:
    return route(text, context).social


def is_followup(text: str, context: Optional[dict] = None) -> bool:
    return route(text, context).followup


def should_send_processing_notice(text: str, context: Optional[dict] = None) -> bool:
    return route(text, context).processing_notice


def should_use_fatwa_preamble(question: str, answer: str, context: Optional[dict] = None) -> bool:
    r = route(question, context)
    if not r.allow_preamble:
        return False
    an = normalize(answer)
    blocked = ["اكتب السؤال بصيغه اوضح", "اكتب السؤال بصيغة اوضح", "يحتاج توضيح", "تحتاج تحديد", "لا يصح حسابها بالتخمين", "غير واضح"]
    if any(x in an for x in blocked):
        return False
    return r.intent in {"fiqh_question", "inheritance_calculation", "advanced_or_composite"}


def social_reply(text: str, context: Optional[dict] = None, name: str = "") -> str:
    r = route(text, context)
    dialect = r.dialect
    n = normalize(text)
    seed = f"v45social:{r.intent}:{dialect}:{n}:{datetime.now().strftime('%Y-%m-%d-%H')}"
    if r.intent == "social_greeting_status":
        pools = {
            "egyptian": ["وعليكم السلام ورحمة الله وبركاته. الحمد لله بخير، إنت عامل إيه؟", "وعليكم السلام. الحمد لله تمام، طمني عليك."],
            "gulf": ["وعليكم السلام ورحمة الله وبركاته. الحمد لله بخير، عساك طيب.", "وعليكم السلام. بخير ولله الحمد، وش أخبارك؟"],
            "shami": ["وعليكم السلام ورحمة الله. الحمد لله بخير، كيفك إنت؟"],
            "moroccan": ["وعليكم السلام ورحمة الله. الحمد لله، لاباس عليك؟"],
            "sudanese": ["وعليكم السلام ورحمة الله. الحمد لله، إنت كيف؟"],
            "standard": ["وعليكم السلام ورحمة الله وبركاته. الحمد لله بخير، أسأل الله أن تكون بخير."],
        }
        return stable_pick(pools.get(dialect, pools["standard"]), seed)
    if r.intent == "social_status":
        pools = {"egyptian":["الحمد لله بخير، إنت عامل إيه؟", "تمام الحمد لله، طمني عليك."], "gulf":["بخير ولله الحمد، عساك بخير.", "الحمد لله، وش أخبارك؟"], "standard":["الحمد لله بخير، أسأل الله أن تكون بخير.", "بخير ولله الحمد."]}
        return stable_pick(pools.get(dialect, pools["standard"]), seed)
    if r.intent == "social_status_reply":
        pools = {"egyptian":["دايمًا بخير إن شاء الله.", "الحمد لله، ربنا يديم عليك الخير."], "gulf":["عساك دايم بخير.", "الحمد لله، الله يديم عليك العافية."], "standard":["الحمد لله، أسأل الله أن يديم عليك الخير.", "دايمًا بخير إن شاء الله."]}
        return stable_pick(pools.get(dialect, pools["standard"]), seed)
    if r.intent == "social_greeting":
        if "مساء" in n:
            return stable_pick({"egyptian":["مساء الفل عليك.", "مساء النور."], "gulf":["مساء النور، حياك الله.", "مساء الخير."], "standard":["مساء النور.", "مساء الخير."]}.get(dialect, ["مساء النور."]), seed)
        if "صباح" in n:
            return stable_pick({"egyptian":["صباح الفل.", "صباح النور."], "gulf":["صباح النور، حياك الله.", "صباح الخير."], "standard":["صباح النور.", "صباح الخير."]}.get(dialect, ["صباح النور."]), seed)
        if "السلام" in n or "سلام عليكم" in n:
            return stable_pick({"gulf":["وعليكم السلام ورحمة الله وبركاته.", "وعليكم السلام، يا هلا."], "standard":["وعليكم السلام ورحمة الله وبركاته."]}.get(dialect, ["وعليكم السلام ورحمة الله وبركاته."]), seed)
        return stable_pick({"egyptian":["أهلًا بيك.", "نورت."], "gulf":["يا هلا.", "هلا والله."], "shami":["أهلين وسهلين.", "يا هلا."], "standard":["مرحبًا بك.", "أهلًا وسهلًا."]}.get(dialect, ["مرحبًا بك."]), seed)
    if r.intent == "social_thanks":
        return stable_pick({"egyptian":["العفو، تحت أمرك.", "ولا يهمك."], "gulf":["العفو، حياك الله.", "تسلم، الله يحييك."], "standard":["العفو، بارك الله فيك.", "حياك الله."]}.get(dialect, ["العفو."]), seed)
    if r.intent == "social_ack":
        return stable_pick({"egyptian":["تمام.", "ماشي."], "gulf":["تمام.", "أبشر."], "standard":["حسنًا.", "تمام."]}.get(dialect, ["تمام."]), seed)
    if r.intent == "identity":
        return "أنا مفتي المواريث الذكي؛ أساعد في فهم أحكام المواريث وحساب الأنصبة، وإذا كانت البيانات ناقصة أطلب توضيحًا بدل التخمين."
    if r.intent == "general_non_domain":
        return "أنا مخصص لمسائل المواريث والفرائض. لو سؤالك في الميراث اكتب تفاصيل الورثة أو الحكم الذي تريد فهمه."
    return "أنا معك."


def followup_reply(text: str, context: Optional[dict] = None) -> str:
    context = context or {}
    r = route(text, context)
    last_answer = str(context.get("last_answer") or "").strip()
    last_q = str(context.get("last_question") or "").strip()
    dialect = r.dialect
    if not last_answer and not last_q:
        return "وضح لي المسألة أو الحكم الذي تريد تبسيطه، وسأشرحه لك خطوة خطوة."
    seed = f"v45fup:{r.intent}:{dialect}:{last_q[:50]}:{datetime.now().strftime('%Y-%m-%d-%H')}"
    if r.intent == "followup_example":
        return stable_pick([
            "تمام، خلّينا ناخدها بمثال بسيط من نفس الفكرة: لو عندنا وارث يتغير نصيبه بسبب وجود وارث أقرب منه، فهذا هو موضع التأثير. اكتب لي قيمة التركة أو الورثة إن كنت تريد مثالًا رقميًا كاملًا.",
            "أعطيك مثالًا مبسطًا: الفكرة لا تكون في الاسم فقط، بل في وجود وارث يغيّر نصيب غيره. لو أردت تطبيقًا بالأرقام، اكتب قيمة التركة والورثة.",
        ], seed)
    if r.intent == "followup_detail":
        return "أفصّلها لك: الحكم لا يُبنى على وجود الوارث فقط، بل على درجته وصلته بالميت وهل يوجد من يحجبه أو ينقص نصيبه. لذلك نرتّب المسألة أولًا: الورثة، ثم الحجب، ثم الفروض، ثم الباقي للعصبة إن وُجدت."
    # simplify
    return stable_pick([
        "أبسطها لك: الفكرة الأساسية أن الميراث لا يُقسم عشوائيًا؛ نحدد الورثة أولًا، ثم نعرف من له فرض محدد، ثم نعطي الباقي للعصبة إن وُجدوا. لو تحب، اكتب لي المسألة نفسها وأمشي معك خطوة خطوة.",
        "خلّيها ببساطة: نبدأ بمن يرث فعلًا، ثم نستبعد المحجوبين، ثم نحسب نصيب كل وارث. اكتب لي أسماء الورثة لو تريد تطبيقًا مباشرًا.",
    ], seed)


def preamble(question: str, answer: str, name: str = "", dialect: str = "standard", seed: str = "") -> str:
    if not should_use_fatwa_preamble(question, answer, None):
        return ""
    nm = (name or "").strip()
    add_name = f" يا {nm}" if nm and len(nm) <= 20 else ""
    pools = [
        f"بسم الله الرحمن الرحيم. بناءً على ما ورد في سؤالك{add_name}، فهذا بيان المسألة:",
        f"بسم الله، والصلاة والسلام على رسول الله. بعد فهم السؤال{add_name}، فالجواب كالآتي:",
        f"بسم الله الرحمن الرحيم. جوابًا على استفسارك{add_name}، أوضح المسألة بهذا التفصيل:",
        f"بسم الله. بعد ترتيب المعطيات المذكورة في السؤال{add_name}، يكون البيان كالآتي:",
    ]
    return stable_pick(pools, seed or f"v45pre:{question[:80]}:{datetime.now().strftime('%Y-%m-%d')}")


def format_money(value: float, currency: str = "") -> str:
    try:
        if format_decimal:
            val = format_decimal(value, locale="ar")
        else:
            val = f"{value:,.2f}"
    except Exception:
        val = f"{value:,.2f}"
    return (val + (" " + currency if currency else "")).strip()
