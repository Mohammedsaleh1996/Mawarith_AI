# -*- coding: utf-8 -*-
"""
Mawareth AI v42 — Full Scholarly Intelligence Layer

Local, lightweight, non-RAG orchestration layer.
Goals:
- Stop social chat from entering fatwa/calculation flow.
- Strong Arabic/dialect intent detection using PyArabic + RapidFuzz when available.
- Context-aware follow-up handling.
- Dynamic, non-fixed answer shaping/preamble policy.
- Safe routing for advanced/ambiguous inheritance cases.

This layer never stores fixed answers for individual inheritance scenarios.
It classifies intent and composes social/follow-up scaffolding, while the deterministic
inheritance engine remains responsible for shares/calculations.
"""
from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from pyarabic import araby as _araby  # type: ignore
except Exception:  # pragma: no cover
    _araby = None

try:
    from rapidfuzz import fuzz as _fuzz, process as _process  # type: ignore
except Exception:  # pragma: no cover
    _fuzz = None
    _process = None

DIAC_RE = re.compile(r"[\u064b-\u0652\u0670\u0640]")
PUNCT_RE = re.compile(r"[\u061f؟?!.,;:،؛\[\]{}()<>\"'`~|\\/]+")

# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

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
    s = DIAC_RE.sub("", s)
    trans = str.maketrans({
        "أ":"ا", "إ":"ا", "آ":"ا", "ٱ":"ا", "ى":"ي", "ئ":"ي", "ؤ":"و", "ة":"ه",
        "گ":"ك", "چ":"ج", "پ":"ب", "ڤ":"ف",
        "٠":"0", "١":"1", "٢":"2", "٣":"3", "٤":"4", "٥":"5", "٦":"6", "٧":"7", "٨":"8", "٩":"9",
        "۰":"0", "۱":"1", "۲":"2", "۳":"3", "۴":"4", "۵":"5", "۶":"6", "۷":"7", "۸":"8", "۹":"9",
    })
    s = s.translate(trans)
    s = PUNCT_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def _seed_pick(options: List[str], seed: str) -> str:
    if not options:
        return ""
    h = int(hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
    return options[h % len(options)]


def _contains_any(n: str, phrases: List[str]) -> bool:
    return any(normalize(p) in n for p in phrases if normalize(p))


def fuzzy_any(text: str, phrases: List[str], threshold: int = 88, max_words: int = 20) -> bool:
    n = normalize(text)
    if not n:
        return False
    if _contains_any(n, phrases):
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
            pass
    return False


def _has_token(n: str, token: str) -> bool:
    t = normalize(token)
    if not t:
        return False
    return re.search(r"(^|\s)" + re.escape(t) + r"($|\s)", n) is not None

# ---------------------------------------------------------------------------
# Lexicons — broad but safe. Social phrases must not trigger the fatwa engine.
# ---------------------------------------------------------------------------
SOCIAL_GREETING = [
    "السلام عليكم", "سلام عليكم", "السلام عليكم ورحمه الله", "السلام عليكم ورحمة الله", "سلام", "سلامو عليكم",
    "هلا", "هلا والله", "يا هلا", "اهلا", "أهلا", "اهلين", "أهلين", "مرحبا", "مرحب", "مرحبتين",
    "صباح الخير", "صباح النور", "صباح الفل", "صباح الورد", "مساء الخير", "مساء النور", "مساء الفل", "مساء الورد",
    "هاي", "hi", "hello", ]
WELLBEING = [
    "كيف حالك", "كيف الحال", "كيفك", "شلونك", "ازيك", "ازايك", "عامل ايه", "عامله ايه", "عامل شنو",
    "اخبارك", "ايه اخبارك", "وش اخبارك", "شخبارك", "طمني عليك", "كيف الامور", "كيف صحتك", "لاباس", "لا باس",
]
THANKS = [
    "شكرا", "شكرًا", "متشكر", "مشكور", "تسلم", "تسلمي", "تسلملي", "جزاك الله", "جزاكم الله", "بارك الله فيك",
    "يعطيك العافيه", "يعطيك العافية", "الله يجزاك خير", "ربنا يبارك", "الف شكر", "تمام شكرا",
]
ACK = ["تمام", "اوكي", "اوك", "ok", "حاضر", "تم", "ماشي", "طيب", "جميل", "واضح", "تمام كده", "تمام كدا", "حلو"]
IDENTITY = ["انت مين", "مين انت", "من انت", "ما اسمك", "اسمك ايه", "وش اسمك", "ايش اسمك", "مين حضرتك"]

FOLLOWUP_SIMPLE = [
    "مش فاهم", "مش فاهمه", "مش فاهمة", "مفهمتش", "مفهمت", "مافهمتش", "ما فهمتش", "ما فهمت", "ما افهم", "ما أفهم",
    "لم افهم", "لم أفهم", "مو فاهم", "ماني فاهم", "مب فاهم", "مش مستوعب", "مو مستوعب", "ما استوعبت", "مش واضح", "مو واضح",
    "ما واضح", "غير واضح", "وضح", "وضحلي", "وضح لي", "وضحهالي", "فهمني", "فهمني اكتر", "فهمني أكثر", "عيد الشرح",
    "اعد الشرح", "بسط", "بسطها", "بسطلي", "بسطهالي", "سهلها", "اشرح ببساطه", "اشرح ببساطة", "اشرح ابسط", "اشرحها ابسط",
    "بالراحة", "واحدة واحدة", "خطوة خطوة", "شوي شوي", "شنو يعني", "وش يعني", "ايش يعني", "يعني شنو", "يعني ايه", "يعني اي",
    "اي المقصود", "ايه المقصود", "ممكن تبسط", "ممكن توضح", "مش داخله دماغي", "مش داخلة دماغي", "مش فاهم النقطه",
    "لسه مش فاهم", "لسا مش فاهم", "مش واصل", "ما وصلني", "مو واصل", "اشرح بالعاميه", "اشرح باللهجه",
]
FOLLOWUP_EXAMPLE = [
    "مثال", "هات مثال", "اديني مثال", "اعطني مثال", "وريني مثال", "وريني", "مثال عملي", "مثال بالارقام", "مثال بالأرقام",
    "طبق", "طبقها", "طبقلي", "بالارقام", "بالأرقام", "احسبها بالمبلغ", "لو التركة", "على مبلغ", "علي مبلغ", "بمبلغ",
    "اعمل مثال", "مثال رقمي", "بفلوس", "بالفلوس", "كم يطلع بالريال", "لو فيه مليون", "لو مبلغه",
]
FOLLOWUP_DETAIL = [
    "فصل", "فصّل", "بالتفصيل", "شرح كامل", "زود شرح", "الدليل", "اي الدليل", "وش الدليل", "ليه", "لماذا", "سبب", "السبب",
    "كيف طلعت", "ازاي طلعت", "كيف حسبتها", "ازاي حسبتها", "اشرح السبب", "منين جبتها", "على اي اساس", "علي اي اساس",
]

DOMAIN_TERMS = [
    "ميراث", "مواريث", "فرائض", "فرايض", "تركة", "تركه", "نصيب", "قسمة", "قسمه", "وارث", "ورثة", "ورثه", "يرث", "يرثون",
    "مات", "ماتت", "توفي", "توفى", "توفيت", "توفت", "هلك", "ترك", "تركت", "ساب", "خلف", "خلّف", "خلفت",
    "زوج", "زوجة", "زوجه", "زوجته", "ابن", "ابنه", "بنت", "بنته", "بنات", "اولاد", "عيال", "أب", "اب", "أم", "ام", "أخ", "اخ", "الأخ", "الاخ", "اخت", "أخت", "الأخت", "الاخت", "جد", "جدة", "جده", "عم", "عمه", "عمة",
    "حجب", "الحجب", "تعصيب", "عاصب", "عول", "العول", "رد", "الرد", "عمرية", "العمرية", "الغراوان", "كلالة", "عالت", "عالت المساله", "صاحب فرض", "صاحب الفرض", "وصية", "وصيه", "ديون", "دين", "مناسخة", "مناسخات", "خنثى", "مفقود", "حمل", "ثلث", "نصف", "ربع", "ثمن", "سدس", "أصحاب الفروض", "اصحاب الفروض",
]
QUESTION_MARKERS = ["ما", "ماذا", "كم", "كيف", "متى", "هل", "من", "لماذا", "ليه", "وش", "شنو", "ايش", "ازاي", "معنى", "معني", "حكم", "ما الفرق", "الفرق"]
ADVANCED_HINTS = ["جد مع الاخوة", "جد مع اخوة", "اكدرية", "الأكدرية", "مشتركة", "حمارية", "ذوي الارحام", "ذوو الارحام", "خنثى", "مفقود", "حمل", "مناسخة", "مناسخات", "ثم مات", "بعده مات", "بعدها مات", "تخارج"]

@dataclass
class Intent:
    name: str
    confidence: float
    dialect: str
    domain: bool
    allow_preamble: bool
    processing_notice: bool
    reason: str = ""


def detect_dialect(text: str, context: Optional[dict] = None) -> str:
    n = normalize(text)
    toks = set(n.split())
    if any(x in n for x in ["ازاي", "ازيك", "ايه", "عايز", "عاوز", "مش", "مفهمتش", "بسطهالي", "مراته", "ساب", "مساء الفل", "صباح الفل", "عامل ايه"]):
        return "egyptian"
    if any(x in n for x in ["وش", "ايش", "شلون", "ابشر", "كذا", "رجال", "حياك", "عساك", "ماني", "مو", "هلا والله", "يعطيك العافيه"]):
        return "gulf"
    if any(x in n for x in ["شو", "قديش", "هيك", "بدي", "كيفك", "مو ", "عم "]):
        return "shami"
    if any(x in n for x in ["شنو", "واش", "فالميراث", "بزاف", "ديال", "نعاونك"]):
        return "moroccan"
    if any(x in n for x in ["الزول", "عندو", "عامل شنو"]) or "ليك" in toks:
        return "sudanese"
    if any(x in n for x in ["شلون", "شكو", "اكو"]):
        return "iraqi"
    if context and context.get("last_dialect"):
        return str(context.get("last_dialect"))
    return "standard"


def is_domain_text(text: str) -> bool:
    n = normalize(text)
    # short social words like "سلام" must not match inside domain words; short relatives checked by token.
    short = {"ام", "اب", "اخ", "اخت", "عم", "جد", "رد", "دين"}
    for term in DOMAIN_TERMS:
        tn = normalize(term)
        if not tn:
            continue
        if tn in short:
            if _has_token(n, tn):
                return True
        elif tn in n:
            return True
    has_death = any(x in n for x in ["مات", "ماتت", "توفي", "توفيت", "توفى", "توفت", "ترك", "تركت", "ساب", "خلف", "خلّف"])
    has_relative = any(_has_token(n, x) or x in n for x in ["زوج", "زوجه", "زوجة", "ابن", "بنت", "بنات", "ام", "اب", "اخ", "اخت", "عم", "جد"])
    return bool(has_death and has_relative)


def classify(text: str, context: Optional[dict] = None) -> Intent:
    n = normalize(text)
    words = n.split()
    short = len(words) <= 16
    dialect = detect_dialect(text, context)
    domain = is_domain_text(text)

    # Social first. Social + no domain must never enter fiqh.
    if short and not domain and fuzzy_any(text, WELLBEING, 86) and fuzzy_any(text, SOCIAL_GREETING, 86):
        return Intent("social_greeting_status", 0.99, dialect, False, False, False, "greeting+status")
    if short and not domain and fuzzy_any(text, WELLBEING, 86):
        return Intent("social_status", 0.97, dialect, False, False, False, "status")
    if short and not domain and fuzzy_any(text, SOCIAL_GREETING, 86):
        return Intent("social_greeting", 0.97, dialect, False, False, False, "greeting")
    if short and not domain and fuzzy_any(text, THANKS, 86):
        return Intent("social_thanks", 0.96, dialect, False, False, False, "thanks")
    if short and not domain and fuzzy_any(text, ACK, 91):
        return Intent("social_ack", 0.92, dialect, False, False, False, "ack")
    if short and not domain and fuzzy_any(text, IDENTITY, 86):
        return Intent("identity", 0.95, dialect, False, False, False, "identity")

    # Follow-up requires no new inheritance scenario.
    if not domain and len(words) <= 24:
        if fuzzy_any(text, FOLLOWUP_EXAMPLE, 83):
            return Intent("followup_example", 0.92, dialect, False, False, False, "example")
        if fuzzy_any(text, FOLLOWUP_SIMPLE, 80):
            return Intent("followup_simplify", 0.92, dialect, False, False, False, "simplify")
        if fuzzy_any(text, FOLLOWUP_DETAIL, 83):
            return Intent("followup_detail", 0.90, dialect, False, False, False, "detail")

    if any(normalize(x) in n for x in ADVANCED_HINTS):
        return Intent("advanced_or_composite", 0.86, dialect, True, True, True, "advanced")

    if domain:
        # calculation if death/estate/heirs, otherwise fiqh concept.
        has_calc = any(x in n for x in ["مات", "ماتت", "توفي", "توفيت", "توفى", "توفت", "ترك", "تركت", "ساب", "خلف", "خلّف", "تركة", "تركه", "نصيب", "قسمة", "قسمه"])
        if has_calc:
            return Intent("calculation", 0.90, dialect, True, True, True, "domain calculation")
        return Intent("fiqh_question", 0.88, dialect, True, True, True, "domain fiqh")

    if any(normalize(q) in n for q in QUESTION_MARKERS):
        return Intent("unclear_question", 0.55, dialect, False, False, False, "non-domain question")
    return Intent("unknown", 0.40, dialect, False, False, False, "unknown")

# ---------------------------------------------------------------------------
# Social reply generation — dynamic with deterministic variety, not fixed by case.
# ---------------------------------------------------------------------------

def social_reply(text: str, context: Optional[dict] = None, name: str = "") -> str:
    r = classify(text, context)
    dialect = r.dialect
    n = normalize(text)
    who = f" يا {name.strip()}" if name else ""
    seed = f"v42:{r.name}:{dialect}:{n}:{datetime.now().strftime('%Y-%m-%d-%H')}"
    has_salam = "السلام عليكم" in n or "سلام عليكم" in n
    has_well = fuzzy_any(text, WELLBEING, 86)

    if r.name == "social_greeting_status" or (has_salam and has_well):
        pools = {
            "egyptian": [f"وعليكم السلام ورحمة الله وبركاته{who}. الحمد لله بخير، إنت عامل إيه؟", f"وعليكم السلام{who}. الحمد لله تمام، ربنا يطمّنك."],
            "gulf": [f"وعليكم السلام ورحمة الله وبركاته{who}. الحمد لله بخير، عساك طيب.", f"وعليكم السلام{who}. الله يحييك، بخير ولله الحمد."],
            "shami": [f"وعليكم السلام ورحمة الله{who}. الحمد لله منيح، إنت كيفك؟"],
            "moroccan": [f"وعليكم السلام ورحمة الله{who}. الحمد لله بخير، نتمنى تكون بخير."],
            "sudanese": [f"وعليكم السلام ورحمة الله{who}. الحمد لله تمام، إنت كيفك؟"],
            "standard": [f"وعليكم السلام ورحمة الله وبركاته{who}. الحمد لله بخير، أسأل الله أن تكون بخير.", f"وعليكم السلام ورحمة الله{who}. بخير ولله الحمد."],
        }
        return _seed_pick(pools.get(dialect, pools["standard"]), seed)

    if r.name == "social_status":
        pools = {
            "egyptian": ["الحمد لله بخير، إنت عامل إيه؟", "تمام الحمد لله، طمني عليك."],
            "gulf": ["بخير ولله الحمد، عساك بخير.", "الحمد لله بخير، الله يحييك."],
            "shami": ["الحمد لله منيح، إنت كيفك؟"],
            "moroccan": ["الحمد لله بخير، وانت؟"],
            "sudanese": ["الحمد لله تمام، إنت كيفك؟"],
            "standard": ["الحمد لله بخير.", "بخير ولله الحمد، أسأل الله لك العافية."],
        }
        return _seed_pick(pools.get(dialect, pools["standard"]), seed)

    if r.name == "social_greeting":
        if has_salam:
            pools = {
                "egyptian": [f"وعليكم السلام ورحمة الله وبركاته{who}. أهلاً بيك.", f"وعليكم السلام{who}. نورت."],
                "gulf": [f"وعليكم السلام ورحمة الله وبركاته{who}. حيّاك الله.", f"وعليكم السلام{who}. هلا والله."],
                "standard": [f"وعليكم السلام ورحمة الله وبركاته{who}. أهلاً بك.", f"وعليكم السلام ورحمة الله{who}. حياك الله."],
            }
            return _seed_pick(pools.get(dialect, pools["standard"]), seed)
        pools = {
            "egyptian": ["أهلاً بيك.", "مساء النور." if "مساء" in n else "نورت."],
            "gulf": ["يا هلا.", "الله يحييك."],
            "shami": ["أهلاً وسهلاً.", "يا هلا."],
            "moroccan": ["مرحبا بيك.", "أهلا وسهلا."],
            "standard": ["مرحبًا.", "أهلاً بك."],
        }
        if "مساء" in n:
            pools["standard"] = ["مساء النور.", "مساء الخير، أهلاً بك."]
        if "صباح" in n:
            pools["standard"] = ["صباح النور.", "صباح الخير، أهلاً بك."]
        return _seed_pick(pools.get(dialect, pools["standard"]), seed)

    if r.name == "social_thanks":
        return _seed_pick(["العفو، بارك الله فيك.", "حياك الله، في خدمتك.", "تسلم، ربنا يبارك فيك."], seed)
    if r.name == "social_ack":
        return _seed_pick(["تمام.", "حسنًا.", "على بركة الله."], seed)
    if r.name == "identity":
        return "أنا مفتي المواريث الذكي؛ أساعدك في شرح أحكام المواريث وحساب الأنصبة، وأطلب التوضيح عند نقص البيانات بدل التخمين."
    return "أنا معك."


def is_social(text: str, context: Optional[dict] = None) -> bool:
    return classify(text, context).name in {"social_greeting_status", "social_status", "social_greeting", "social_thanks", "social_ack", "identity"}


def is_followup(text: str, context: Optional[dict] = None) -> bool:
    return classify(text, context).name in {"followup_simplify", "followup_example", "followup_detail"}


def should_send_processing_notice(text: str, context: Optional[dict] = None) -> bool:
    return classify(text, context).processing_notice and not is_social(text, context) and not is_followup(text, context)


def should_use_fatwa_preamble(question: str, answer_text: str, context: Optional[dict] = None) -> bool:
    r = classify(question, context)
    if r.name in {"social_greeting_status", "social_status", "social_greeting", "social_thanks", "social_ack", "identity", "followup_simplify", "followup_example", "followup_detail", "unclear_question", "unknown"}:
        return False
    ans = normalize(answer_text)
    if any(x in ans for x in ["يحتاج توضيح", "تحتاج تحديد", "لا يصح حسابها بالتخمين", "اكتب السؤال بصيغه اوضح", "اكتب السؤال بصيغة اوضح"]):
        return False
    return r.name in {"fiqh_question", "calculation", "advanced_or_composite"}


def preamble(question: str, answer_text: str, name: str = "", dialect: str = "standard", seed: str = "") -> str:
    if not should_use_fatwa_preamble(question, answer_text):
        return ""
    who = f" يا {name.strip()}" if name else ""
    pools = {
        "egyptian": [
            f"بسم الله الرحمن الرحيم. بناءً على سؤالك{who}، أوضح لك المسألة كالتالي:",
            f"بسم الله، والصلاة والسلام على رسول الله. بعد فهم السؤال{who}، فالبيان كالتالي:",
        ],
        "gulf": [
            f"بسم الله الرحمن الرحيم. بناءً على استفسارك{who}، فهذا بيان المسألة:",
            f"بسم الله، والصلاة والسلام على رسول الله. الجواب بعد ترتيب المسألة{who} كالتالي:",
        ],
        "standard": [
            f"بسم الله الرحمن الرحيم، والصلاة والسلام على خاتم الأنبياء والمرسلين. بناءً على ما ورد في سؤالك{who}، فهذا بيان المسألة:",
            f"بسم الله الرحمن الرحيم. بعد فهم السؤال وترتيب محلّه{who}، فالجواب كالتالي:",
            f"بسم الله، والصلاة والسلام على رسول الله. هذا بيان المسألة على قدر المعطيات المذكورة{who}:",
        ]
    }
    return _seed_pick(pools.get(dialect, pools["standard"]), seed or question)


def followup_response(text: str, context: Optional[dict] = None) -> Optional[str]:
    r = classify(text, context)
    if r.name not in {"followup_simplify", "followup_example", "followup_detail"}:
        return None
    ctx = context or {}
    last_answer = str(ctx.get("last_answer") or "").strip()
    last_question = str(ctx.get("last_question") or "").strip()
    if not last_answer:
        return "أحتاج أعرف أي جزء تريد تبسيطه؛ اكتب السؤال أو المسألة أولًا، ثم قل لي: بسّط أو هات مثال."
    lines = [ln.strip() for ln in last_answer.splitlines() if ln.strip()]
    # remove formal preambles and technical review lines
    bad = ["بسم الله", "الصلاة والسلام", "بناءً على", "مراجعة مجموع", "تنبيه:"]
    keep = [ln for ln in lines if not any(b in ln for b in bad)]
    if not keep:
        keep = lines
    seed = f"follow:{r.name}:{last_question}:{datetime.now().strftime('%Y-%m-%d-%H')}"
    if r.name == "followup_example":
        head = _seed_pick(["خلينا ناخدها بمثال بسيط:", "تمام، نمشيها بمثال واضح:", "أبسطها لك بمثال:"], seed)
        tail = "\n\nلو تريد مثالًا على مبلغ معيّن، اكتب قيمة التركة والعملة، مثل: التركة 100000 ريال."
        return head + "\n\n" + "\n".join(keep[:10]) + tail
    if r.name == "followup_detail":
        head = _seed_pick(["أوضحها بتفصيل أكثر:", "خليني أفصلها خطوة خطوة:", "البيان بتفصيل أوضح:"], seed)
        return head + "\n\n" + "\n".join(keep[:16])
    head = _seed_pick(["تمام، أبسطها لك:", "خليني أقولها بطريقة أسهل:", "ببساطة:"], seed)
    simplified = []
    for ln in keep[:8]:
        ln = re.sub(r"\s+", " ", ln)
        simplified.append(ln)
    return head + "\n\n" + "\n".join(simplified)
