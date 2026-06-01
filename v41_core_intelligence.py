# -*- coding: utf-8 -*-
"""
Mawareth AI v41 — Core Intelligence Foundation

Purpose:
- Strong Arabic/dialect intent routing before the inheritance/fiqh engines.
- Natural small-talk handling without pushing users into a fatwa flow.
- Dynamic preamble policy: religious opener only for real fiqh/calculation answers.
- Follow-up intent layer: simplify/example/detail/why/amount based on prior context.
- Lightweight, local, no RAG, no fixed per-case inheritance answers.

This module does not calculate inheritance shares. It routes and shapes conversation safely
while preserving the deterministic inheritance engine already built in the project.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

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

DOMAIN_TERMS = [
    "ميراث", "مواريث", "فرائض", "فرايض", "فرض", "تركة", "تركه", "نصيب", "قسمة", "قسمه",
    "وارث", "ورثة", "ورثه", "يرث", "يرثون", "مات", "ماتت", "توفي", "توفى", "توفيت", "توفت", "هلك",
    "ترك", "تركت", "ساب", "خلف", "خلّف", "خلفت", "زوج", "زوجة", "زوجه", "ابن", "بنت", "بنات",
    "أب", "اب", "أم", "ام", "أخ", "اخ", "اخت", "أخت", "جد", "جدة", "جده", "عم", "عمة", "عمه",
    "حجب", "الحجب", "تعصيب", "عاصب", "عول", "العول", "رد", "الرد", "عمرية", "العمرية", "الغراوان",
    "كلالة", "وصية", "وصيه", "ديون", "دين", "تركات", "مناسخة", "مناسخات", "خنثى", "مفقود", "حمل",
    "ثلث", "نصف", "ربع", "ثمن", "سدس", "ثلثين", "الثلثان", "السدس", "النصف",
    "عالت", "عول", "اصحاب الفروض", "أصحاب الفروض", "نوع الاخ", "نوع الأخ", "الاخ الشقيق", "الأخ الشقيق",
]

# These are intentionally broad social phrases. They must never be routed into fatwa/calculation by themselves.
SOCIAL_GREETING = [
    "السلام عليكم", "سلام عليكم", "سلامو عليكم", "سلام", "هلا", "هلا والله", "يا هلا", "اهلا", "أهلا",
    "اهلين", "أهلين", "مرحبا", "مرحب", "مرحبتين", "صباح الخير", "صباح النور", "صباح الفل", "صباح الورد",
    "مساء الخير", "مساء النور", "مساء الفل", "مساء الورد", "هاي", "hello", "hi",
]
SOCIAL_WELLBEING = [
    "كيف حالك", "كيف الحال", "كيفك", "كيف حالك يا شيخ", "شلونك", "عامل ايه", "عامله ايه", "ازيك", "ازايك",
    "ايه اخبارك", "اخبارك", "وش اخبارك", "شخبارك", "طمني عليك", "كيف الامور", "عامل شنو", "لاباس", "لا باس",
]
SOCIAL_THANKS = [
    "شكرا", "شكرًا", "متشكر", "مشكور", "تسلم", "تسلمي", "تسلملي", "جزاك الله", "الله يجزاك خير",
    "بارك الله فيك", "يعطيك العافيه", "يعطيك العافية", "ربنا يبارك", "تمام شكرا", "جزاكم الله خيرا",
]
SOCIAL_ACK = ["تمام", "اوكي", "أوكي", "اوك", "ok", "حاضر", "تم", "ماشي", "طيب", "جميل", "واضح", "تمام كده", "تمام كدا"]

# V43: positive/negative replies to a previous wellbeing question, e.g.
# bot: "إنت عامل إيه؟" -> user: "بخير الحمد لله".
# These must stay in the social path and must never be routed to the fatwa/model path.
SOCIAL_STATUS_REPLY = [
    "بخير", "بخير الحمد لله", "الحمد لله بخير", "الحمدلله بخير", "انا بخير", "أنا بخير",
    "كويس", "كويس الحمد لله", "تمام الحمد لله", "تمام الحمدلله", "الحمد لله", "الحمدلله",
    "طيّب", "طيب", "طيبين", "طيبين الحمد لله", "تمام", "كلو تمام", "كله تمام",
    "بألف خير", "بالف خير", "الله يبارك فيك", "بخير دامك بخير", "بخير الله يسلمك",
    "لاباس", "لا باس", "لاباس الحمد لله", "مزيان", "مزيان الحمد لله", "الحمد لله لاباس",
]
IDENTITY = ["انت مين", "مين انت", "من انت", "ما اسمك", "اسمك ايه", "وش اسمك", "ايش اسمك", "ما وظيفتك"]

FOLLOWUP_SIMPLE = [
    "مش فاهم", "مش فاهمه", "مفهمتش", "مافهمتش", "ما فهمتش", "ما فهمت", "ما افهم", "ما أفهم", "لم افهم",
    "مو فاهم", "ماني فاهم", "مب فاهم", "مو واضح", "مش واضح", "ما واضح", "غير واضح", "مش مستوعب", "مو مستوعب",
    "وضح", "وضحلي", "وضح لي", "فهمني", "فهمني اكتر", "عيد الشرح", "اعد الشرح", "بسط", "بسطها", "بسطلي",
    "اشرح ابسط", "اشرحها ابسط", "اشرح ببساطة", "سهلها", "بالراحة", "واحدة واحدة", "خطوة خطوة", "شوي شوي",
    "وش يعني", "شنو يعني", "ايش يعني", "يعني ايه", "يعني شنو", "ايه المقصود", "ما المقصود", "ممكن تبسط", "ممكن توضح",
    "مش واصل", "ما وصلني", "ما دخلت دماغي", "مش داخلة دماغي", "لسه مش فاهم", "لسا مش فاهم",
]
FOLLOWUP_EXAMPLE = [
    "مثال", "هات مثال", "اديني مثال", "اعطني مثال", "وريني مثال", "مثال عملي", "مثال بالارقام", "مثال بالأرقام",
    "طبق", "طبقها", "طبقلي", "بالارقام", "بالأرقام", "مثال رقمي", "بفلوس", "بالفلوس", "احسبها بالمبلغ",
    "كم يطلع بالريال", "لو التركة", "على مبلغ", "علي مبلغ", "بمبلغ", "اعمل مثال",
]
FOLLOWUP_DETAIL = [
    "فصل", "فصّل", "بالتفصيل", "شرح كامل", "زود شرح", "الدليل", "اي الدليل", "وش الدليل", "ليه", "لماذا",
    "السبب", "سبب", "كيف طلعت", "ازاي طلعت", "كيف حسبتها", "ازاي حسبتها", "اشرح السبب", "منين جبتها",
]

QUESTIONISH = ["ما", "ماذا", "كم", "كيف", "متى", "هل", "من", "لماذا", "ليه", "وش", "شنو", "ايش", "ازاي", "ما معنى", "ما معني"]

@dataclass
class IntentResult:
    intent: str
    confidence: float
    dialect: str
    is_domain: bool
    needs_processing_notice: bool
    allow_preamble: bool
    reason: str = ""


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


def _contains_phrase(text_norm: str, phrases: List[str]) -> bool:
    return any(normalize(p) in text_norm for p in phrases if normalize(p))


def _fuzzy_contains(text: str, phrases: List[str], threshold: int = 88) -> bool:
    n = normalize(text)
    if _contains_phrase(n, phrases):
        return True
    if _fuzz is None or len(n.split()) > 16:
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
    token = normalize(token)
    if not token:
        return False
    return re.search(r"(^|\s)" + re.escape(token) + r"($|\s)", n) is not None


def is_domain_text(text: str) -> bool:
    n = normalize(text)
    # Avoid false positives such as "ام" inside "السلام" or "اب" inside unrelated words.
    short_tokens = {"ام", "اب", "اخ", "اخت", "عم", "جد", "رد", "دين"}
    for t in DOMAIN_TERMS:
        tn = normalize(t)
        if not tn:
            continue
        if tn in short_tokens:
            if _has_token(n, tn):
                return True
        elif tn in n:
            return True
    # Arabic inheritance questions often mention relatives + death verbs.
    has_death = any(x in n for x in ["مات", "ماتت", "توفي", "توفيت", "توفى", "توفت", "هلك", "ترك", "تركت", "ساب", "خلف"])
    has_relative = any(_has_token(n, x) or x in n for x in ["زوج", "زوجه", "زوجة", "ابن", "بنت", "بنات", "ام", "اب", "اخ", "اخت", "عم", "جد", "جده"])
    return bool(has_death and has_relative)


def detect_dialect(text: str, context: Optional[dict] = None) -> str:
    n = normalize(text)
    if any(x in n for x in ["ازاي", "ازيك", "ايه", "عايز", "عاوز", "مش", "مفهمتش", "بسطهالي", "مراته", "ساب", "مساء الفل", "صباح الفل"]):
        return "egyptian"
    if any(x in n for x in ["وش", "ايش", "شلون", "ابشر", "كذا", "رجال", "حياك", "عساك", "ماني", "مو", "هلا والله"]):
        return "gulf"
    if any(x in n for x in ["شو", "قديش", "هيك", "بدي", "كيفك", "مو", "عم "]):
        return "shami"
    if any(x in n for x in ["شنو", "واش", "فالميراث", "بزاف", "ديال", "نعاونك"]):
        return "moroccan"
    toks = set(n.split())
    if any(x in n for x in ["الزول", "عندو", "عامل شنو"]) or ("ليك" in toks and "عليك" not in toks):
        return "sudanese"
    if context and context.get("last_dialect"):
        return str(context.get("last_dialect"))
    return "standard"


def classify_intent(text: str, context: Optional[dict] = None) -> IntentResult:
    n = normalize(text)
    words = n.split()
    short = len(words) <= 14
    dialect = detect_dialect(text, context)
    domain = is_domain_text(text)

    if short and not domain and (_fuzzy_contains(text, SOCIAL_WELLBEING, 86) and _fuzzy_contains(text, SOCIAL_GREETING, 86)):
        return IntentResult("social_greeting_status", 0.98, dialect, False, False, False, "greeting+status")
    if short and not domain and _fuzzy_contains(text, SOCIAL_WELLBEING, 86):
        return IntentResult("social_status", 0.96, dialect, False, False, False, "status")
    if short and not domain and _fuzzy_contains(text, SOCIAL_GREETING, 86):
        return IntentResult("social_greeting", 0.96, dialect, False, False, False, "greeting")
    if short and not domain and _fuzzy_contains(text, SOCIAL_THANKS, 86):
        return IntentResult("social_thanks", 0.96, dialect, False, False, False, "thanks")
    # V43: a human status reply to the bot/user's previous wellbeing exchange.
    # Treat it as social even if it contains only "الحمد لله" or "بخير".
    if short and not domain and _fuzzy_contains(text, SOCIAL_STATUS_REPLY, 88):
        return IntentResult("social_status_reply", 0.96, dialect, False, False, False, "status reply")
    if short and not domain and _fuzzy_contains(text, SOCIAL_ACK, 90):
        return IntentResult("social_ack", 0.92, dialect, False, False, False, "ack")
    if short and not domain and _fuzzy_contains(text, IDENTITY, 86):
        return IntentResult("identity", 0.95, dialect, False, False, False, "identity")

    # Follow-up intents are only valid when the message is not a fresh domain scenario,
    # or when it clearly refers back to prior context without new heirs/death data.
    if not domain:
        if len(words) <= 20 and _fuzzy_contains(text, FOLLOWUP_EXAMPLE, 84):
            return IntentResult("followup_example", 0.90, dialect, domain, False, False, "follow-up example")
        if len(words) <= 24 and _fuzzy_contains(text, FOLLOWUP_SIMPLE, 82):
            return IntentResult("followup_simplify", 0.90, dialect, domain, False, False, "follow-up simplify")
        if len(words) <= 24 and _fuzzy_contains(text, FOLLOWUP_DETAIL, 84):
            return IntentResult("followup_detail", 0.88, dialect, domain, False, False, "follow-up detail")

    if domain:
        # Calculation if contains death/estate scenario; fiqh concept otherwise.
        calc_markers = ["مات", "ماتت", "توفي", "توفيت", "توفى", "توفت", "ترك", "تركت", "ساب", "خلف", "خلّف", "تركة", "تركه"]
        if any(x in n for x in calc_markers) and any(x in n for x in ["زوج", "زوجه", "زوجة", "ابن", "بنت", "ام", "اب", "اخ", "اخت", "عم", "جد", "جده", "ورثه", "ورثة"]):
            return IntentResult("inheritance_calculation", 0.92, dialect, True, True, True, "death+heirs")
        return IntentResult("fiqh_question", 0.90, dialect, True, True, True, "domain question")

    # Generic question but not domain: safe social/off-scope handling without fatwa preamble.
    if words and any(n.startswith(normalize(q)) for q in QUESTIONISH):
        return IntentResult("general_question", 0.62, dialect, False, False, False, "non-domain question")

    return IntentResult("unknown", 0.50, dialect, False, False, False, "unknown")


def _pick(options: List[str], seed: str) -> str:
    if not options:
        return ""
    h = int(hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
    return options[h % len(options)]


def social_reply(text: str, context: Optional[dict] = None, name: str = "") -> str:
    r = classify_intent(text, context)
    dialect = r.dialect
    n = normalize(text)
    nm = (name or "").strip()
    # Do not overuse names; natural chat uses name sparsely.
    name_part = f" يا {nm}" if nm and len(nm) <= 20 and random.random() < 0.15 else ""
    seed = f"v41:{r.intent}:{dialect}:{n}:{datetime.now().strftime('%Y-%m-%d-%H')}"

    if r.intent == "social_greeting_status":
        pools = {
            "egyptian": [f"وعليكم السلام ورحمة الله وبركاته{name_part}. الحمد لله بخير، إنت عامل إيه؟", f"وعليكم السلام ورحمة الله{name_part}. الحمد لله، طمني عليك."],
            "gulf": [f"وعليكم السلام ورحمة الله وبركاته{name_part}. الحمد لله بخير، عساك طيب.", f"وعليكم السلام ورحمة الله{name_part}. بخير ولله الحمد، وش أخبارك؟"],
            "shami": [f"وعليكم السلام ورحمة الله وبركاته{name_part}. الحمد لله بخير، كيفك إنت؟"],
            "moroccan": [f"وعليكم السلام ورحمة الله وبركاته{name_part}. الحمد لله، لاباس عليك؟"],
            "sudanese": [f"وعليكم السلام ورحمة الله وبركاته{name_part}. الحمد لله، إنت كيف؟"],
            "standard": [f"وعليكم السلام ورحمة الله وبركاته{name_part}. الحمد لله بخير، أسأل الله أن تكون بخير."]
        }
        return _pick(pools.get(dialect, pools["standard"]), seed)
    if r.intent == "social_status":
        pools = {
            "egyptian": ["الحمد لله بخير، إنت عامل إيه؟", "بخير الحمد لله، طمني عليك."],
            "gulf": ["بخير ولله الحمد، عساك بخير.", "الحمد لله، وش أخبارك؟"],
            "shami": ["الحمد لله بخير، كيفك إنت؟"],
            "moroccan": ["الحمد لله، لاباس. إنت لباس عليك؟"],
            "sudanese": ["الحمد لله بخير، إنت كيف؟"],
            "standard": ["الحمد لله بخير، أسأل الله أن تكون بخير.", "بخير ولله الحمد."]
        }
        return _pick(pools.get(dialect, pools["standard"]), seed)
    if r.intent == "social_greeting":
        if "مساء" in n:
            pools2 = {
                "egyptian": ["مساء النور.", "مساء الفل عليك."],
                "gulf": ["مساء النور، حياك الله.", "مساء الخير."],
                "standard": ["مساء النور.", "مساء الخير."]
            }
            return _pick(pools2.get(dialect, pools2["standard"]), seed)
        if "صباح" in n:
            pools2 = {
                "egyptian": ["صباح النور.", "صباح الفل عليك."],
                "gulf": ["صباح النور، حياك الله.", "صباح الخير."],
                "standard": ["صباح النور.", "صباح الخير."]
            }
            return _pick(pools2.get(dialect, pools2["standard"]), seed)
        pools = {
            "egyptian": ["أهلًا بيك.", "نورت."],
            "gulf": ["يا هلا.", "حياك الله.", "مرحبا مليون."],
            "shami": ["أهلين وسهلين.", "يا هلا فيك."],
            "moroccan": ["مرحبا، لاباس؟", "أهلا وسهلا."],
            "sudanese": ["مرحب، كيفك؟", "أهلًا بيك."],
            "standard": ["مرحبًا بك.", "أهلًا وسهلًا."]
        }
        return _pick(pools.get(dialect, pools["standard"]), seed)
    if r.intent == "social_thanks":
        pools = {
            "egyptian": ["العفو، تحت أمرك.", "ولا يهمك."],
            "gulf": ["العفو، حياك الله.", "تسلم، الله يحييك."],
            "standard": ["العفو، بارك الله فيك.", "حياك الله."]
        }
        return _pick(pools.get(dialect, pools["standard"]), seed)
    if r.intent == "social_status_reply":
        pools = {
            "egyptian": ["دايمًا بخير إن شاء الله.", "الحمد لله، ربنا يديم عليك الخير."],
            "gulf": ["عساك دايم بخير.", "الحمد لله، الله يديم عليك العافية."],
            "shami": ["دايمًا بخير إن شاء الله.", "الحمد لله، الله يديم عليك العافية."],
            "moroccan": ["الحمد لله، الله يديمها نعمة.", "ديما بخير إن شاء الله."],
            "sudanese": ["الحمد لله، ربنا يديم عليك العافية.", "دايمًا بخير إن شاء الله."],
            "standard": ["الحمد لله، أسأل الله أن يديم عليك الخير.", "دايمًا بخير إن شاء الله."]
        }
        return _pick(pools.get(dialect, pools["standard"]), seed)
    if r.intent == "social_ack":
        pools = {"egyptian": ["تمام.", "ماشي."], "gulf": ["تمام.", "أبشر."], "standard": ["حسنًا.", "تمام."]}
        return _pick(pools.get(dialect, pools["standard"]), seed)
    if r.intent == "identity":
        return "أنا مفتي المواريث الذكي؛ أساعد في فهم أحكام المواريث وحساب الأنصبة من غير تخمين. إذا كانت المسألة ناقصة أطلب توضيحًا بدل إعطاء نتيجة غير مأمونة."
    return ""


def is_pure_social(text: str, context: Optional[dict] = None) -> bool:
    return classify_intent(text, context).intent in {"social_greeting_status", "social_status", "social_status_reply", "social_greeting", "social_thanks", "social_ack", "identity"}


def is_followup(text: str, context: Optional[dict] = None) -> bool:
    return classify_intent(text, context).intent in {"followup_simplify", "followup_example", "followup_detail"}


def should_send_processing_notice(text: str, context: Optional[dict] = None) -> bool:
    return classify_intent(text, context).needs_processing_notice


def should_decorate_with_preamble(question: str, answer: str, context: Optional[dict] = None) -> bool:
    r = classify_intent(question, context)
    if r.intent in {"social_greeting_status", "social_status", "social_status_reply", "social_greeting", "social_thanks", "social_ack", "identity", "followup_simplify", "followup_example", "followup_detail"}:
        return False
    an = normalize(answer)
    if any(x in an for x in ["اكتب السؤال بصيغه اوضح", "يحتاج توضيح", "تحتاج تحديد", "لا يصح", "لا استطيع", "راجع"]):
        return False
    return r.intent in {"inheritance_calculation", "fiqh_question"}


def preamble(question: str, answer: str, name: str = "", dialect: str = "standard", seed: str = "") -> str:
    if not should_decorate_with_preamble(question, answer, None):
        return ""
    nm = (name or "").strip()
    add_name = f" يا {nm}" if nm and len(nm) <= 20 else ""
    pools = [
        f"بسم الله الرحمن الرحيم. بناءً على ما ورد في سؤالك{add_name}، فهذا بيان المسألة:",
        f"بسم الله، والصلاة والسلام على رسول الله. بعد فهم السؤال{add_name}، فالجواب كالآتي:",
        f"بسم الله الرحمن الرحيم. جوابًا على استفسارك{add_name}، أرتب لك المسألة كما يلي:",
        f"بسم الله. هذه خلاصة الحكم في المسألة التي سألت عنها{add_name}:",
    ]
    return _pick(pools, seed or question[:80])


def followup_instruction(text: str, context: Optional[dict] = None) -> str:
    r = classify_intent(text, context)
    if r.intent == "followup_example":
        return "example"
    if r.intent == "followup_detail":
        return "detail"
    if r.intent == "followup_simplify":
        return "simplify"
    return ""


def review_flags(question: str, answer: str, context: Optional[dict] = None) -> List[str]:
    flags: List[str] = []
    qn = normalize(question)
    an = normalize(answer)
    risky = ["جد مع اخ", "جد مع الاخوه", "مناسخه", "مناسخات", "خنثي", "مفقود", "حمل", "ذوي الارحام", "تخارج"]
    if any(x in qn for x in risky):
        flags.append("advanced_topic")
    if "اكتب السؤال بصيغه اوضح" in an:
        flags.append("clarification_prompt")
    if "من التركة" in an and "مراجعة مجموع الانصبة" not in an and "صافي التركة" not in an:
        flags.append("calculation_without_sum_review")
    if is_pure_social(question, context) and ("بسم الله" in answer or "المسألة" in an):
        flags.append("social_routed_to_fatwa")
    return flags


def as_debug_dict(text: str, context: Optional[dict] = None) -> Dict[str, Any]:
    return asdict(classify_intent(text, context))
