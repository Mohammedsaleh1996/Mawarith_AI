# -*- coding: utf-8 -*-
"""
Mawareth AI v44 — Dialogue State Machine

A general, non-RAG, non-per-case-patch conversation layer.
It separates social conversation, follow-up, fiqh questions and inheritance calculations
using scored intent routing + state-aware safeguards.

It does NOT calculate inheritance shares and does NOT store fixed answers for inheritance cases.
It only decides whether a message should enter the scholarly/calculation pipeline, and how
answers should be wrapped.
"""
from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    from pyarabic import araby as _araby  # type: ignore
except Exception:
    _araby = None

try:
    from rapidfuzz import fuzz as _fuzz  # type: ignore
except Exception:
    _fuzz = None

DIAC = re.compile(r"[\u064b-\u0652\u0670\u0640]")
PUNCT = re.compile(r"[\u061f؟?!.,;:،؛\[\]{}()<>\"'`~|\\/]+")


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
    trans = str.maketrans({
        "أ":"ا", "إ":"ا", "آ":"ا", "ٱ":"ا", "ى":"ي", "ئ":"ي", "ؤ":"و", "ة":"ه",
        "گ":"ك", "چ":"ج", "پ":"ب", "ڤ":"ف",
        "٠":"0", "١":"1", "٢":"2", "٣":"3", "٤":"4", "٥":"5", "٦":"6", "٧":"7", "٨":"8", "٩":"9",
        "۰":"0", "۱":"1", "۲":"2", "۳":"3", "۴":"4", "۵":"5", "۶":"6", "۷":"7", "۸":"8", "۹":"9",
    })
    s = s.translate(trans)
    s = PUNCT.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def tokens(text: str) -> List[str]:
    return normalize(text).split()


def _has_token(n: str, token: str) -> bool:
    t = normalize(token)
    return bool(t and re.search(r"(^|\s)" + re.escape(t) + r"($|\s)", n))


def _contains_phrase(n: str, phrases: List[str]) -> bool:
    return any(normalize(p) and normalize(p) in n for p in phrases)


def _fuzzy_phrase(n: str, phrases: List[str], threshold: int = 88, max_words: int = 12) -> bool:
    if _contains_phrase(n, phrases):
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


def _pick(options: List[str], seed: str) -> str:
    if not options:
        return ""
    h = int(hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
    return options[h % len(options)]

# ---------------------------------------------------------------------------
# General lexicons, not one-case patches. These represent dialogue acts.
# ---------------------------------------------------------------------------

GREETING_OPENERS = [
    "السلام عليكم", "سلام عليكم", "السلام عليكم ورحمة الله", "السلام عليكم ورحمه الله", "سلام", "سلامو عليكم",
    "هلا", "هلا والله", "يا هلا", "اهلا", "اهلين", "أهلين", "أهلا", "اهلا وسهلا", "مرحبا", "مرحب", "مرحبتين",
    "صباح الخير", "صباح النور", "صباح الفل", "صباح الورد", "مساء الخير", "مساء النور", "مساء الفل", "مساء الورد",
    "هاي", "hi", "hello", "الو", "ألو",
]

WELLBEING_ASK = [
    "كيف حالك", "كيف الحال", "كيفك", "شلونك", "شخبارك", "وش اخبارك", "ايه اخبارك", "اخبارك", "طمني عليك",
    "ازيك", "ازايك", "عامل ايه", "عامله ايه", "عاملة ايه", "عامل شنو", "كيف الامور", "كيف صحتك", "لاباس", "لا باس",
    "واش خبارك", "شنو اخبارك", "عساك طيب", "علومك", "اخبار الدنيا", "ايه الدنيا",
]

STATUS_REPLY_MARKERS = [
    "بخير", "انا بخير", "الحمد لله", "الحمدلله", "الحمد لله بخير", "تمام", "تمام الحمد لله", "كويس", "كويس الحمد لله",
    "طيب", "طيبين", "طيبين الحمد لله", "بالف خير", "بألف خير", "كلو تمام", "كله تمام", "ماشي الحال", "زي الفل",
    "الله يسلمك", "ربنا يخليك", "تسلم", "تسلملي", "الله يبارك فيك", "مزيان", "مزيان الحمد لله", "لاباس", "لا باس",
    "بخير دامك بخير", "بخير الله يسلمك", "تمام يا غالي", "تمام يا باشا", "عال العال", "الحمد لله على كل حال",
]

THANKS = [
    "شكرا", "شكرًا", "متشكر", "مشكور", "تسلم", "تسلمي", "تسلملي", "جزاك الله", "جزاكم الله", "بارك الله فيك",
    "يعطيك العافيه", "يعطيك العافية", "الله يجزاك خير", "ربنا يبارك", "الف شكر", "ألف شكر", "تمام شكرا",
]

ACK = ["تمام", "اوكي", "اوك", "ok", "حاضر", "تم", "ماشي", "طيب", "جميل", "واضح", "حلو", "اتفقنا", "تمام كده", "تمام كدا"]

IDENTITY = ["انت مين", "مين انت", "من انت", "ما اسمك", "اسمك ايه", "وش اسمك", "ايش اسمك", "ما وظيفتك", "مين حضرتك"]

FOLLOWUP_SIMPLE = [
    "مش فاهم", "مش فاهمه", "مفهمتش", "مافهمتش", "ما فهمتش", "ما فهمت", "ما افهم", "ما أفهم", "لم افهم",
    "مو فاهم", "ماني فاهم", "مب فاهم", "مش مستوعب", "مو مستوعب", "ما استوعبت", "مش واضح", "مو واضح", "ما واضح",
    "غير واضح", "وضح", "وضحلي", "وضح لي", "وضحهالي", "فهمني", "فهمني اكتر", "عيد الشرح", "اعد الشرح",
    "بسط", "بسطها", "بسطلي", "اشرح ابسط", "اشرحها ابسط", "اشرح ببساطة", "سهلها", "بالراحة", "واحدة واحدة",
    "خطوة خطوة", "شوي شوي", "وش يعني", "شنو يعني", "ايش يعني", "يعني شنو", "يعني ايه", "يعني اي", "ايه المقصود",
    "ممكن تبسط", "ممكن توضح", "مش واصل", "ما وصلني", "مش داخلة دماغي", "ما دخلت دماغي", "لسه مش فاهم",
]
FOLLOWUP_EXAMPLE = [
    "مثال", "هات مثال", "اديني مثال", "اعطني مثال", "وريني مثال", "مثال عملي", "مثال بالارقام", "مثال بالأرقام",
    "طبق", "طبقها", "طبقلي", "بالارقام", "بالأرقام", "مثال رقمي", "بفلوس", "بالفلوس", "احسبها بالمبلغ",
    "كم يطلع بالريال", "لو التركة", "على مبلغ", "علي مبلغ", "بمبلغ", "اعمل مثال",
]
FOLLOWUP_DETAIL = [
    "فصل", "فصّل", "بالتفصيل", "شرح كامل", "زود شرح", "الدليل", "اي الدليل", "وش الدليل", "ليه", "لماذا",
    "سبب", "السبب", "كيف طلعت", "ازاي طلعت", "كيف حسبتها", "ازاي حسبتها", "اشرح السبب", "منين جبتها",
]

# Domain lexicon separated into strong and weak terms to avoid false positives.
DEATH_TERMS = ["مات", "ماتت", "توفي", "توفيت", "توفى", "توفت", "هلك", "هلكت", "ماتوا", "توفوا"]
LEAVE_TERMS = ["ترك", "تركت", "ساب", "سابت", "خلف", "خلفت", "خلّف", "خلّفت", "وراه", "ورثه", "ورثة"]
RELATIVE_TERMS = [
    "زوج", "زوجة", "زوجه", "زوجته", "زوجها", "مراته", "مرتو", "ابن", "ابنه", "بنته", "بنت", "بنات", "اولاد", "عيال",
    "اب", "أب", "ابوه", "أبوه", "ام", "أم", "امه", "أمه", "اخ", "أخ", "اخت", "أخت", "جد", "جده", "جدة", "عم", "عمه", "عمة",
]
FIQH_CONCEPT_TERMS = [
    "ميراث", "مواريث", "فرائض", "فرايض", "تركة", "تركه", "نصيب", "قسمة", "قسمه", "وارث", "يرث",
    "حجب", "الحجب", "تعصيب", "عاصب", "العصبة", "عول", "العول", "رد", "الرد", "عمرية", "العمرية", "الغراوان",
    "كلالة", "الكلالة", "وصية", "وصيه", "ديون", "دين", "مناسخة", "مناسخات", "خنثى", "مفقود", "حمل", "اصحاب الفروض", "أصحاب الفروض",
    "نصف", "ثلث", "ربع", "ثمن", "سدس", "ثلثين", "الفروض المقدرة", "الأكدرية", "الحمارية", "المشتركة", "ذوي الارحام", "ذوو الارحام",
]
QUESTION_WORDS = ["ما", "ماذا", "كم", "كيف", "متى", "هل", "من", "لماذا", "ليه", "وش", "شنو", "ايش", "ازاي", "معنى", "معني", "حكم", "الفرق"]

ADVANCED_TERMS = ["جد مع الاخوة", "جد مع اخوة", "اكدرية", "الأكدرية", "مشتركة", "حمارية", "ذوي الارحام", "ذوو الارحام", "خنثى", "مفقود", "حمل", "مناسخة", "مناسخات", "ثم مات", "بعده مات", "بعدها مات", "تخارج"]


def detect_dialect(text: str, context: Optional[dict] = None) -> str:
    n = normalize(text)
    if any(x in n for x in ["ازاي", "ازيك", "ايه", "عايز", "عاوز", "مش", "مفهمتش", "مراته", "ساب", "مساء الفل", "صباح الفل", "عامل ايه", "زي الفل"]):
        return "egyptian"
    if any(x in n for x in ["وش", "ايش", "شلون", "ابشر", "كذا", "رجال", "حياك", "عساك", "ماني", "مو", "هلا والله", "يعطيك العافيه"]):
        return "gulf"
    if any(x in n for x in ["شو", "قديش", "هيك", "بدي", "كيفك", "مو ", "عم "]):
        return "shami"
    if any(x in n for x in ["شنو", "واش", "فالميراث", "بزاف", "ديال", "نعاونك", "مزيان"]):
        return "moroccan"
    toks = set(n.split())
    if any(x in n for x in ["الزول", "عندو", "عامل شنو"]) or ("ليك" in toks and "عليك" not in toks):
        return "sudanese"
    if any(x in n for x in ["شلون", "شكو", "اكو"]):
        return "iraqi"
    if context and context.get("last_dialect"):
        return str(context.get("last_dialect"))
    return "standard"


def domain_score(text: str) -> int:
    n = normalize(text)
    score = 0
    has_death = _contains_phrase(n, DEATH_TERMS)
    has_leave = _contains_phrase(n, LEAVE_TERMS)
    has_relative = any(_has_token(n, t) or normalize(t) in n for t in RELATIVE_TERMS)
    has_fiqh = _contains_phrase(n, FIQH_CONCEPT_TERMS)
    has_question = any(_has_token(n, q) or normalize(q) in n for q in QUESTION_WORDS)
    if has_death: score += 3
    if has_leave: score += 2
    if has_relative: score += 3
    if has_fiqh: score += 3
    if has_question and has_fiqh: score += 2
    if has_death and has_relative: score += 4
    if has_leave and has_relative: score += 3
    if re.search(r"\b\d+[\d,\.]*\b", n) and (has_death or has_leave or has_relative or has_fiqh):
        score += 1
    return score


def social_score(text: str, context: Optional[dict] = None) -> Tuple[int, str]:
    n = normalize(text)
    words = n.split()
    if len(words) > 18:
        return 0, ""
    score = 0
    intent = ""
    if _fuzzy_phrase(n, GREETING_OPENERS, 88, 12):
        score += 5; intent = "social_greeting"
    if _fuzzy_phrase(n, WELLBEING_ASK, 86, 12):
        score += 6; intent = "social_status" if not intent else "social_greeting_status"
    if _fuzzy_phrase(n, THANKS, 88, 10):
        score += 5; intent = "social_thanks"
    if _fuzzy_phrase(n, IDENTITY, 88, 10):
        score += 5; intent = "identity"
    if _fuzzy_phrase(n, STATUS_REPLY_MARKERS, 86, 10):
        # Stronger when previous bot answer was a status question, but still general.
        score += 6; intent = "social_status_reply"
        if context and str(context.get("last_answer", "")):
            last = normalize(str(context.get("last_answer", "")))
            if any(x in last for x in ["عامل ايه", "طمني", "عساك", "اخبارك", "كيفك", "تكون بخير", "انت كيف"]):
                score += 2
    # ACK after another social turn is social; ACK alone can also be social if no domain.
    if _fuzzy_phrase(n, ACK, 92, 6):
        score += 4; intent = intent or "social_ack"
    return score, intent


def followup_intent(text: str, context: Optional[dict] = None) -> str:
    n = normalize(text)
    if len(n.split()) > 24:
        return ""
    if _fuzzy_phrase(n, FOLLOWUP_EXAMPLE, 84, 20):
        return "followup_example"
    if _fuzzy_phrase(n, FOLLOWUP_SIMPLE, 82, 22):
        return "followup_simplify"
    if _fuzzy_phrase(n, FOLLOWUP_DETAIL, 84, 22):
        return "followup_detail"
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
    reason: str


def classify(text: str, context: Optional[dict] = None) -> Route:
    n = normalize(text)
    if not n:
        return Route("empty", 1.0, detect_dialect(text, context), False, True, False, False, False, "empty")
    dscore = domain_score(text)
    sscore, sintent = social_score(text, context)
    dialect = detect_dialect(text, context)
    fup = followup_intent(text, context)

    # Domain wins if it is a real inheritance/fiqh question/scenario.
    if dscore >= 5:
        if _contains_phrase(n, ADVANCED_TERMS):
            return Route("advanced_or_composite", .88, dialect, True, False, False, True, True, f"domain={dscore};advanced")
        if any(x in n for x in ["مات", "ماتت", "توفي", "توفيت", "توفى", "توفت", "ترك", "تركت", "ساب", "خلف", "خلّف", "تركة", "تركه", "نصيب", "قسمة", "قسمه"]):
            return Route("inheritance_calculation", .92, dialect, True, False, False, True, True, f"domain={dscore};calc")
        return Route("fiqh_question", .90, dialect, True, False, False, True, True, f"domain={dscore};fiqh")

    # Follow-ups are not social, but must not receive preamble/processing.
    if fup:
        return Route(fup, .90, dialect, False, False, True, False, False, f"followup={fup}")

    # Social channel: broad dialogue acts with no domain evidence.
    if sscore >= 4 and dscore < 5:
        return Route(sintent or "social", min(.99, .60 + sscore/20), dialect, False, True, False, False, False, f"social={sscore};domain_noise={dscore}")

    # Low-domain off-topic question: do not send to fatwa path, and do not preamble.
    if any(_has_token(n, q) or n.startswith(normalize(q) + " ") for q in QUESTION_WORDS):
        return Route("general_non_domain", .65, dialect, False, False, False, False, False, "non-domain question")

    # Short unknown messages stay out of fatwa to avoid hallucinated fragments.
    if len(n.split()) <= 8:
        return Route("small_unknown", .55, dialect, False, False, False, False, False, "short unknown")

    return Route("unknown", .50, dialect, False, False, False, False, False, "unknown")


def is_social(text: str, context: Optional[dict] = None) -> bool:
    return classify(text, context).social


def is_followup(text: str, context: Optional[dict] = None) -> bool:
    return classify(text, context).followup


def should_send_processing_notice(text: str, context: Optional[dict] = None) -> bool:
    return classify(text, context).processing_notice


def should_use_fatwa_preamble(question: str, answer: str, context: Optional[dict] = None) -> bool:
    r = classify(question, context)
    if not r.allow_preamble:
        return False
    an = normalize(answer)
    if any(x in an for x in ["اكتب السؤال بصيغه اوضح", "اكتب السؤال بصيغة اوضح", "يحتاج توضيح", "تحتاج تحديد", "لا يصح حسابها بالتخمين", "لا يصح", "راجع"]):
        return False
    return r.intent in {"fiqh_question", "inheritance_calculation", "advanced_or_composite"}


def social_reply(text: str, context: Optional[dict] = None, name: str = "") -> str:
    r = classify(text, context)
    dialect = r.dialect
    n = normalize(text)
    nm = (name or "").strip()
    # Use names sparingly to feel natural.
    name_part = f" يا {nm}" if nm and len(nm) <= 20 and random.random() < 0.12 else ""
    seed = f"v44:{r.intent}:{dialect}:{n}:{datetime.now().strftime('%Y-%m-%d-%H')}"

    if r.intent == "social_greeting_status":
        pools = {
            "egyptian": [f"وعليكم السلام ورحمة الله وبركاته{name_part}. الحمد لله بخير، إنت عامل إيه؟", f"وعليكم السلام{name_part}. الحمد لله تمام، طمني عليك."],
            "gulf": [f"وعليكم السلام ورحمة الله وبركاته{name_part}. الحمد لله بخير، عساك طيب.", f"وعليكم السلام{name_part}. بخير ولله الحمد، وش أخبارك؟"],
            "shami": [f"وعليكم السلام ورحمة الله{name_part}. الحمد لله بخير، كيفك إنت؟"],
            "moroccan": [f"وعليكم السلام ورحمة الله{name_part}. الحمد لله، لاباس عليك؟"],
            "sudanese": [f"وعليكم السلام ورحمة الله{name_part}. الحمد لله، إنت كيف؟"],
            "standard": [f"وعليكم السلام ورحمة الله وبركاته{name_part}. الحمد لله بخير، أسأل الله أن تكون بخير."],
        }
        return _pick(pools.get(dialect, pools["standard"]), seed)
    if r.intent == "social_status":
        pools = {
            "egyptian": ["الحمد لله بخير، إنت عامل إيه؟", "تمام الحمد لله، طمني عليك."],
            "gulf": ["بخير ولله الحمد، عساك بخير.", "الحمد لله، وش أخبارك؟"],
            "shami": ["الحمد لله بخير، كيفك إنت؟"],
            "moroccan": ["الحمد لله، لاباس. إنت لباس عليك؟"],
            "sudanese": ["الحمد لله بخير، إنت كيف؟"],
            "standard": ["الحمد لله بخير، أسأل الله أن تكون بخير.", "بخير ولله الحمد."],
        }
        return _pick(pools.get(dialect, pools["standard"]), seed)
    if r.intent == "social_status_reply":
        pools = {
            "egyptian": ["دايمًا بخير إن شاء الله.", "الحمد لله، ربنا يديم عليك الخير."],
            "gulf": ["عساك دايم بخير.", "الحمد لله، الله يديم عليك العافية."],
            "shami": ["دايمًا بخير إن شاء الله.", "الحمد لله، الله يديم عليك العافية."],
            "moroccan": ["الحمد لله، الله يديمها نعمة.", "ديما بخير إن شاء الله."],
            "sudanese": ["الحمد لله، ربنا يديم عليك العافية.", "دايمًا بخير إن شاء الله."],
            "standard": ["الحمد لله، أسأل الله أن يديم عليك الخير.", "دايمًا بخير إن شاء الله."],
        }
        return _pick(pools.get(dialect, pools["standard"]), seed)
    if r.intent == "social_greeting":
        if "مساء" in n:
            pools = {"egyptian": ["مساء الفل عليك.", "مساء النور."], "gulf": ["مساء النور، حياك الله.", "مساء الخير."], "standard": ["مساء النور.", "مساء الخير."]}
            return _pick(pools.get(dialect, pools["standard"]), seed)
        if "صباح" in n:
            pools = {"egyptian": ["صباح الفل.", "صباح النور."], "gulf": ["صباح النور، حياك الله.", "صباح الخير."], "standard": ["صباح النور.", "صباح الخير."]}
            return _pick(pools.get(dialect, pools["standard"]), seed)
        if "السلام" in n or "سلام عليكم" in n:
            pools = {"egyptian": ["وعليكم السلام ورحمة الله وبركاته.", "وعليكم السلام."], "gulf": ["وعليكم السلام ورحمة الله وبركاته.", "وعليكم السلام، يا هلا."], "standard": ["وعليكم السلام ورحمة الله وبركاته."]}
            return _pick(pools.get(dialect, pools["standard"]), seed)
        pools = {"egyptian": ["أهلًا بيك.", "نورت."], "gulf": ["يا هلا.", "هلا والله."], "shami": ["أهلين وسهلين.", "يا هلا."], "standard": ["مرحبًا بك.", "أهلًا وسهلًا."]}
        return _pick(pools.get(dialect, pools["standard"]), seed)
    if r.intent == "social_thanks":
        pools = {"egyptian": ["العفو، تحت أمرك.", "ولا يهمك."], "gulf": ["العفو، حياك الله.", "تسلم، الله يحييك."], "standard": ["العفو، بارك الله فيك.", "حياك الله."]}
        return _pick(pools.get(dialect, pools["standard"]), seed)
    if r.intent == "social_ack":
        pools = {"egyptian": ["تمام.", "ماشي."], "gulf": ["تمام.", "أبشر."], "standard": ["حسنًا.", "تمام."]}
        return _pick(pools.get(dialect, pools["standard"]), seed)
    if r.intent == "identity":
        return "أنا مفتي المواريث الذكي؛ أساعد في فهم أحكام المواريث وحساب الأنصبة. وإذا كانت البيانات ناقصة أطلب توضيحًا بدل التخمين."
    if r.intent == "general_non_domain":
        return "أنا مخصص لمسائل المواريث والفرائض. لو سؤالك عن الميراث اكتب تفاصيل الورثة أو الحكم الذي تريد فهمه."
    return "أنا معك."


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
    return _pick(pools, seed or f"v44pre:{question[:80]}:{datetime.now().strftime('%Y-%m-%d')}")
