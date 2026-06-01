# -*- coding: utf-8 -*-
"""
Human Conversation Enhancer v37
- Optional NLP dependencies: PyArabic, RapidFuzz, Babel, dateparser.
- No RAG, no fixed per-case inheritance answers.
- Purpose: robust Arabic/dialect conversation routing and answer decoration policy.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

try:
    from pyarabic import araby as _araby  # type: ignore
except Exception:  # optional dependency
    _araby = None

try:
    from rapidfuzz import fuzz as _rf_fuzz  # type: ignore
except Exception:  # optional dependency
    _rf_fuzz = None

try:
    from babel.numbers import format_decimal as _babel_format_decimal  # type: ignore
except Exception:
    _babel_format_decimal = None


AR_DIACRITICS_RE = re.compile(r"[\u064b-\u0652\u0670\u0640]")
PUNCT_RE = re.compile(r"[\u061f؟?!.,;:،؛\[\]{}()<>\"'`~|\\/]+")


def normalize_ar_human(text: str) -> str:
    """Strong Arabic normalization for intent detection only.
    It does not alter the original user text used for records or display.
    """
    s = str(text or "")
    s = s.replace("\ufeff", "").replace("\u200f", "").replace("\u200e", "")
    if _araby is not None:
        try:
            s = _araby.strip_tashkeel(s)
            s = _araby.strip_tatweel(s)
            s = _araby.normalize_hamza(s)
        except Exception:
            pass
    s = AR_DIACRITICS_RE.sub("", s)
    # practical intent-level normalization
    trans = str.maketrans({
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه",
        "گ": "ك", "چ": "ج", "پ": "ب",
        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
        "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    })
    s = s.translate(trans)
    s = PUNCT_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def _pick(options: list[str], seed: str) -> str:
    if not options:
        return ""
    h = int(hashlib.sha256(str(seed).encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
    return options[h % len(options)]


def fuzzy_contains(text: str, phrases: list[str], threshold: int = 86) -> bool:
    n = normalize_ar_human(text)
    if not n:
        return False
    if any(normalize_ar_human(p) in n for p in phrases):
        return True
    if _rf_fuzz is None:
        return False
    # Fuzzy only for short conversational messages to avoid false positives in long fatwa questions.
    if len(n.split()) > 18:
        return False
    for p in phrases:
        pn = normalize_ar_human(p)
        if not pn:
            continue
        try:
            if _rf_fuzz.partial_ratio(pn, n) >= threshold:
                return True
        except Exception:
            continue
    return False


SUBSTANTIVE_MARKERS = [
    "ميراث", "مواريث", "فرائض", "فرايض", "تركة", "تركه", "نصيب", "قسمة", "قسمه",
    "مات", "ماتت", "توفي", "توفى", "توفت", "توفيت", "هلك", "ترك", "تركت", "ساب", "خلف", "ورث",
    "الحجب", "تعصيب", "العول", "الرد", "العمرية", "العمرية", "الغراوان", "الكلالة", "وصية", "ديون",
]

GREETING_PHRASES = [
    "السلام عليكم", "سلام عليكم", "السلام عليكم ورحمة الله", "السلام عليكم ورحمه الله", "وعليكم السلام",
    "مرحبا", "مرحب", "اهلا", "اهلين", "اهلا وسهلا", "هلا", "يا هلا", "صباح الخير", "مساء الخير",
    "عامل ايه", "ازيك", "كيف الحال", "شلونك", "كيفك", "كيف حالك", "شنو اخبارك", "اخبارك",
]

WELLBEING_PHRASES = [
    "كيف حالك", "كيف الحال", "كيفك", "شلونك", "عامل ايه", "عامله ايه", "ازيك", "ازايك",
    "اخبارك", "شنو اخبارك", "وش اخبارك", "ايه الاخبار", "كيف صحتك", "عامل شنو", "كيف الامور",
]

THANKS_PHRASES = [
    "شكرا", "شكرًا", "متشكر", "مشكور", "تسلم", "تسلمي", "تسلملي", "جزاك الله", "بارك الله فيك",
    "يعطيك العافيه", "يعطيك العافية", "الله يجزاك خير", "ربنا يبارك", "تمام شكرا",
]
ACK_PHRASES = ["تمام", "اوكي", "اوك", "ok", "حاضر", "تم", "ماشي", "طيب", "جميل", "واضح كده", "تمام كده"]
IDENTITY_PHRASES = ["انت مين", "مين انت", "من انت", "ما اسمك", "اسمك ايه", "وش اسمك", "من تكون"]

FOLLOWUP_SIMPLE = [
    "مش فاهم", "مش فاهمه", "مش فاهمة", "مش فاهما", "مفهمتش", "مفهمت", "مافهمتش", "ما فهمتش",
    "ما فهمت", "ما افهم", "ما أفهم", "ما فهمت عليك", "لم افهم", "لم أفهم", "مو فاهم", "ماني فاهم",
    "مب فاهم", "مش مستوعب", "مو مستوعب", "ما استوعبت", "مش واضح", "مو واضح", "ما واضح", "غير واضح",
    "وضح", "وضحلي", "وضح لي", "وضحهالي", "فهمني", "فهمنى", "فهمني اكتر", "فهمني أكثر", "عيد الشرح",
    "اعد الشرح", "بسط", "بسطها", "بسطلي", "بسطهالي", "سهلها", "اشرح ببساطة", "اشرح ابسط",
    "اشرحها ابسط", "بالراحة", "واحدة واحدة", "خطوة خطوة", "شوي شوي", "شنو يعني", "وش يعني", "ايش يعني",
    "يعني شنو", "يعني ايه", "يعني اي", "اي المقصود", "ايه المقصود", "ممكن تبسط", "ممكن توضح",
    "مش داخله دماغي", "مش داخلة دماغي", "مش فاهم النقطه", "مش فاهم النقطة", "لسه مش فاهم", "لسا مش فاهم",
    "مش واصل", "ما وصلني", "مو واصل", "ممكن تشرح بالعامي", "اشرح بالعاميه", "اشرح باللهجه",
]
FOLLOWUP_EXAMPLE = [
    "مثال", "هات مثال", "اديني مثال", "اعطني مثال", "وريني مثال", "وريني", "مثال عملي", "مثال بالارقام",
    "مثال بالأرقام", "طبق", "طبقها", "طبقلي", "بالارقام", "بالأرقام", "احسبها بالمبلغ", "لو التركة",
    "على مبلغ", "علي مبلغ", "بمبلغ", "اعمل مثال", "مثال رقمي", "بفلوس", "بالفلوس", "كم يطلع بالريال",
]
FOLLOWUP_DETAIL = [
    "فصل", "فصّل", "بالتفصيل", "شرح كامل", "زود شرح", "الدليل", "اي الدليل", "وش الدليل",
    "ليه", "لماذا", "سبب", "السبب", "كيف طلعت", "ازاي طلعت", "كيف حسبتها", "ازاي حسبتها", "اشرح السبب",
]


def has_substantive_marker(text: str) -> bool:
    n = normalize_ar_human(text)
    return any(normalize_ar_human(x) in n for x in SUBSTANTIVE_MARKERS)


def detect_human_message_kind(text: str, context: dict | None = None) -> str | None:
    n = normalize_ar_human(text)
    words = n.split()
    short = len(words) <= 12
    if short and fuzzy_contains(text, GREETING_PHRASES, 88) and not has_substantive_marker(text):
        # التحية التي معها "كيف الحال" تظل محادثة اجتماعية لا سؤال مواريث.
        return "greeting"
    if short and fuzzy_contains(text, WELLBEING_PHRASES, 88) and not has_substantive_marker(text):
        return "wellbeing"
    if short and fuzzy_contains(text, THANKS_PHRASES, 88):
        return "thanks"
    if short and fuzzy_contains(text, ACK_PHRASES, 92) and not has_substantive_marker(text):
        return "ack"
    if fuzzy_contains(text, FOLLOWUP_EXAMPLE, 88):
        return "followup_example"
    if len(words) <= 22 and fuzzy_contains(text, FOLLOWUP_SIMPLE, 82):
        return "followup_simple"
    if len(words) <= 22 and fuzzy_contains(text, FOLLOWUP_DETAIL, 86):
        return "followup_detail"
    if fuzzy_contains(text, IDENTITY_PHRASES, 88):
        return "identity"
    return None


def detect_dialect_human(text: str, context: dict | None = None) -> str:
    n = normalize_ar_human(text)
    if any(x in n for x in ["ازاي", "ايه", "عايز", "عاوز", "مش", "مفهمتش", "بسطهالي", "مراته", "ساب", "متشكر"]):
        return "egyptian"
    if any(x in n for x in ["وش", "ايش", "شلون", "ابشر", "كذا", "رجال", "حياك", "عقب", "مو", "ماني", "يعطيك"]):
        return "gulf"
    if any(x in n for x in ["شو", "قديش", "هيك", "بدي", "مو", "عم", "كيفك"]):
        return "shami"
    if any(x in n for x in ["شنو", "واش", "فالميراث", "بزاف", "نعاونك", "ديال"]):
        return "moroccan"
    toks = set(n.split())
    if any(x in n for x in ["الزول", "عندو"]) or ("ليك" in toks) or ("كده" in toks):
        return "sudanese"
    if context and context.get("last_dialect"):
        return str(context.get("last_dialect"))
    return "standard"


def answer_role(question: str, answer_text: str, context: dict | None = None) -> str:
    kind = detect_human_message_kind(question, context)
    if kind in {"greeting", "wellbeing", "thanks", "ack", "identity"}:
        return "smalltalk"
    if kind in {"followup_simple", "followup_example", "followup_detail"}:
        return "followup"
    nans = normalize_ar_human(answer_text)
    if any(x in nans for x in ["يحتاج توضيح", "تحتاج تحديد", "لا يصح حسابها بالتخمين", "اكتب السؤال بصيغه اوضح"]):
        return "clarification"
    if "من التركة" in nans or "مراجعة مجموع الانصبة" in nans or "القسمة النقدية" in nans:
        return "calculation"
    if has_substantive_marker(question) or any(x in nans for x in ["هو", "هي", "معنى", "الحكم", "المقصود", "مثال", "الفرق"]):
        return "fiqh"
    return "general"


def should_decorate_with_preamble(question: str, answer_text: str, context: dict | None = None) -> bool:
    return answer_role(question, answer_text, context) in {"calculation", "fiqh"}


def should_send_processing_notice(question: str, context: dict | None = None) -> bool:
    # Do not send processing notices for human smalltalk/follow-ups; they make conversation unnatural.
    kind = detect_human_message_kind(question, context)
    if kind in {"greeting", "wellbeing", "thanks", "ack", "identity", "followup_simple", "followup_example", "followup_detail"}:
        return False
    return has_substantive_marker(question) or len(normalize_ar_human(question).split()) >= 6



def is_pure_social_message(text: str, context: dict | None = None) -> bool:
    """True for greetings/thanks/status chat that must not trigger processing notices or fatwa preambles."""
    return detect_human_message_kind(text, context) in {"greeting", "wellbeing", "thanks", "ack", "identity"}


def _has_wellbeing(text: str) -> bool:
    return fuzzy_contains(text, WELLBEING_PHRASES, 88)

def human_smalltalk_reply(question: str, context: dict | None = None, name: str = "") -> str:
    kind = detect_human_message_kind(question, context) or "greeting"
    dialect = detect_dialect_human(question, context)
    who = f" يا {name.strip()}" if name else ""
    seed = f"v38:{kind}:{dialect}:{normalize_ar_human(question)}:{datetime.now().strftime('%Y-%m-%d-%H')}"
    has_salam = any(x in normalize_ar_human(question) for x in ["السلام عليكم", "سلام عليكم"])
    has_wellbeing = _has_wellbeing(question)

    # تحية + سؤال حال: رد اجتماعي طبيعي، لا تحويل مباشر لمسألة ولا مقدمة فتوى.
    greeting_wellbeing = {
        "egyptian": [
            f"وعليكم السلام ورحمة الله وبركاته{who}. الحمد لله، بخير. إنت عامل إيه؟ لو عندك مسألة ميراث ابعتهالي وأنا أرتبها معاك.",
            f"وعليكم السلام{who}. الحمد لله تمام. اتفضل، لما تحب ابعت سؤالك في المواريث.",
        ],
        "gulf": [
            f"وعليكم السلام ورحمة الله وبركاته{who}. الحمد لله بخير، عساك بخير. تفضل متى ما عندك سؤال في المواريث.",
            f"وعليكم السلام{who}. الله يحييك، أنا بخير. أرسل مسألتك وقت ما تحب.",
        ],
        "shami": [
            f"وعليكم السلام ورحمة الله{who}. الحمد لله، منيح. إنت كيفك؟ ابعت سؤالك وقت ما تحب.",
            f"وعليكم السلام{who}. الحمد لله تمام. احكيلي المسألة لما تكون جاهز.",
        ],
        "moroccan": [
            f"وعليكم السلام ورحمة الله{who}. الحمد لله بخير. تفضل، إلا عندك سؤال فالميراث صيفطو لي.",
        ],
        "sudanese": [
            f"وعليكم السلام ورحمة الله{who}. الحمد لله تمام. أرسل المسألة وأنا أوضحها ليك.",
        ],
        "standard": [
            f"وعليكم السلام ورحمة الله وبركاته{who}. الحمد لله بخير. تفضل متى أردت، أرسل سؤالك في المواريث وسأساعدك في ترتيبه.",
            f"وعليكم السلام ورحمة الله وبركاته{who}. حياك الله، أنا جاهز لمساعدتك في مسائل المواريث متى أرسلتها.",
        ],
    }

    pools = {
        "greeting": {
            "egyptian": [
                f"وعليكم السلام ورحمة الله وبركاته{who}. اتفضل، أنا معاك.",
                f"أهلاً بيك{who}. تحت أمرك، ابعت اللي محتاجه في المواريث.",
            ],
            "gulf": [
                f"وعليكم السلام ورحمة الله وبركاته{who}. حيّاك الله، تفضل.",
                f"مرحبًا{who}. تفضل بسؤالك وقت ما تحب.",
            ],
            "shami": [
                f"وعليكم السلام ورحمة الله{who}. أهلاً وسهلاً، تفضل.",
                f"أهلاً فيك{who}. احكيلي شو سؤالك.",
            ],
            "moroccan": [f"وعليكم السلام ورحمة الله{who}. مرحبا، تفضل."],
            "sudanese": [f"وعليكم السلام ورحمة الله{who}. اتفضل، أنا معاك."],
            "standard": [
                f"وعليكم السلام ورحمة الله وبركاته{who}. تفضل، أنا معك.",
                f"مرحبًا{who}. يسعدني مساعدتك في المواريث.",
            ],
        },
        "wellbeing": {
            "egyptian": [f"الحمد لله بخير. إنت عامل إيه؟", f"الحمد لله تمام. طمني عليك."],
            "gulf": [f"الحمد لله بخير، عساك بخير.", f"بخير ولله الحمد. الله يحييك."],
            "shami": [f"الحمد لله منيح. إنت كيفك؟", f"تمام الحمد لله. شو أخبارك؟"],
            "moroccan": [f"الحمد لله بخير، نتمنى تكون بخير."],
            "sudanese": [f"الحمد لله تمام. كيفك إنت؟"],
            "standard": [f"الحمد لله بخير. أسأل الله أن تكون بخير أيضًا.", f"بخير ولله الحمد. تفضل، أنا معك."],
        },
        "thanks": {
            "egyptian": ["العفو، تحت أمرك.", "ربنا يبارك فيك، موجود لو احتجت حاجة تانية."],
            "gulf": ["العفو، حياك الله.", "الله يعافيك، تفضل بأي وقت."],
            "shami": ["العفو، أهلًا فيك.", "تكرم، ابعت أي سؤال تاني."],
            "standard": ["العفو، يسعدني خدمتك.", "بارك الله فيك، تفضل بأي سؤال آخر."],
        },
        "ack": {
            "egyptian": ["تمام، أنا معاك.", "ماشي، لما تحب ابعت السؤال."],
            "gulf": ["تمام، أبشر.", "حاضر، تفضل متى احتجت."],
            "standard": ["تمام، أنا معك.", "حسنًا، تفضل متى احتجت."],
        },
        "identity": {
            "standard": ["أنا مفتي المواريث الذكي؛ أساعدك في شرح أحكام المواريث وحساب الأنصبة، وإذا كانت البيانات ناقصة أطلب توضيحًا بدل التخمين."],
            "egyptian": ["أنا مفتي المواريث الذكي؛ أساعدك تفهم مسائل المواريث وأحسب الأنصبة، ولو البيانات ناقصة هسألك بدل ما أخمّن."],
            "gulf": ["أنا مفتي المواريث الذكي؛ أساعدك في حساب الإرث وشرح أحكام الفرائض، وإذا نقصت البيانات أطلب توضيحًا."],
        },
    }

    if kind == "greeting" and has_wellbeing:
        opts = greeting_wellbeing.get(dialect) or greeting_wellbeing["standard"]
    else:
        group = pools.get(kind, pools["greeting"])
        opts = group.get(dialect) or group.get("standard") or ["تفضل، أنا معك."]
        if kind == "greeting" and has_salam:
            wa_opts = [o for o in opts if "وعليكم" in o]
            if wa_opts:
                opts = wa_opts
    return _pick(opts, seed)

def preamble_human(question: str, answer_text: str, name: str, dialect: str, seed: str) -> str:
    """Variable formal opener only for real fiqh/calculation answers."""
    who = f" يا {name.strip()}" if name else ""
    pools = {
        "egyptian": [
            f"بسم الله الرحمن الرحيم. بناءً على اللي ورد في سؤالك{who}، فهذا بيان المسألة:",
            f"بسم الله، والصلاة والسلام على رسول الله. بعد فهم السؤال{who}، أوضح لك الجواب كالتالي:",
        ],
        "gulf": [
            f"بسم الله الرحمن الرحيم. بناءً على ما ورد في سؤالك{who}، يكون البيان كالآتي:",
            f"بسم الله، والصلاة والسلام على رسول الله. جوابًا على استفسارك{who}، فالتفصيل كالتالي:",
        ],
        "shami": [
            f"بسم الله الرحمن الرحيم. بناءً على سؤالك{who}، التوضيح يكون كالتالي:",
            f"بسم الله، والصلاة والسلام على رسول الله. بعد ما اتضح السؤال{who}، هذا بيان المسألة:",
        ],
        "moroccan": [
            f"بسم الله الرحمن الرحيم. بناءً على السؤال ديالك{who}، فهذا بيان المسألة:",
        ],
        "sudanese": [
            f"بسم الله الرحمن الرحيم. بناءً على سؤالك{who}، أوضح ليك الحكم كالآتي:",
        ],
        "standard": [
            f"بسم الله الرحمن الرحيم، والصلاة والسلام على خاتم الأنبياء والمرسلين. بناءً على ما ورد في سؤالك{who}، فهذا بيان المسألة:",
            f"بسم الله، والحمد لله، والصلاة والسلام على رسول الله. بعد فهم السؤال{who}، فالجواب كالآتي:",
            f"بسم الله الرحمن الرحيم. ردًا على استفسارك{who}، أوضح الحكم والتوزيع كما يلي:",
        ],
    }
    return _pick(pools.get(dialect) or pools["standard"], seed)


def format_money_optional(value: Any, currency: str = "", locale: str = "ar_EG") -> str:
    try:
        if _babel_format_decimal is not None:
            return _babel_format_decimal(value, locale=locale) + (f" {currency}" if currency else "")
    except Exception:
        pass
    return f"{value:,.2f}" + (f" {currency}" if currency else "")


# ---------------------------------------------------------------------------
# V39 Natural Small Talk Override
# هدفها: أي تحية/سؤال حال/شكر يرد برد بشري قصير فقط، بدون دعوة آلية متكررة
# إلى "اكتب مسألتك"، وبدون مقدمة فتوى، وبدون تحويل الكلام العادي لمسألة.
# ---------------------------------------------------------------------------
PURE_DOMAIN_HINTS_V39 = [
    "ميراث", "مواريث", "فرائض", "تركة", "التركة", "ورث", "يرث", "نصيب", "قسمة", "تقسيم",
    "مات", "توفي", "توفى", "توفيت", "ماتت", "هلك", "زوج", "زوجة", "ابن", "بنت", "أب", "ام", "أم",
    "اخ", "أخ", "اخت", "أخت", "عم", "جد", "جدة", "وصية", "دين", "عول", "رد", "حجب", "تعصيب"
]

PURE_WELLBEING_V39 = [
    "كيف حالك", "كيفك", "كيف الحال", "شلونك", "شخبارك", "اخبارك", "عامل ايه", "عامله ايه", "ازيك", "ازايك",
    "كيف امورك", "علومك", "طمني عليك", "عامل اي", "كيف انت", "كيف أنت", "اشلونك", "شنو اخبارك"
]

PURE_GREETING_V39 = [
    "السلام عليكم", "سلام عليكم", "السلام عليكم ورحمة الله", "هلا", "هلا والله", "يا هلا", "مرحبا", "مرحباً",
    "اهلا", "أهلا", "اهلين", "أهلين", "صباح الخير", "مساء الخير", "حي الله", "حياك", "سلام"
]

THANKS_V39 = ["شكرا", "شكرًا", "تسلم", "جزاك الله", "بارك الله فيك", "الله يجزيك", "يعطيك العافيه", "يعطيك العافية", "مشكور"]
ACK_V39 = ["تمام", "اوكي", "أوكي", "ok", "اوك", "حاضر", "تم", "ماشي", "طيب", "جميل"]

def _v39_has_domain_hint(text: str) -> bool:
    n = normalize_ar_human(text)
    return any(normalize_ar_human(x) in n for x in PURE_DOMAIN_HINTS_V39)

def _v39_has_any(text: str, phrases: list[str]) -> bool:
    n = normalize_ar_human(text)
    return any(normalize_ar_human(p) in n for p in phrases)

def _v39_short_social(text: str) -> bool:
    n = normalize_ar_human(text)
    return len(n.split()) <= 10 and not _v39_has_domain_hint(n)

# Override previous detector with stricter natural chat handling.
def detect_human_message_kind(text: str, context: dict | None = None) -> str | None:  # type: ignore[override]
    n = normalize_ar_human(text)
    if not n:
        return None
    short_social = _v39_short_social(n)
    if short_social and _v39_has_any(n, THANKS_V39):
        return "thanks"
    if short_social and _v39_has_any(n, PURE_WELLBEING_V39):
        # لو فيها سلام + كيف حالك؛ النوع wellbeing عشان الرد يجمع السلام والحال.
        return "wellbeing"
    if short_social and _v39_has_any(n, PURE_GREETING_V39):
        return "greeting"
    if short_social and _v39_has_any(n, ACK_V39):
        return "ack"
    if any(x in n for x in ["انت مين", "من انت", "مين انت", "ما اسمك", "اسمك ايه", "وش اسمك"]):
        return "identity"
    # Follow-up intents remain broad, but only if no domain question is being asked now.
    if len(n.split()) <= 18:
        if _v39_has_any(n, ["مش فاهم", "ما افهم", "ما فهمت", "ماني فاهم", "مفهمتش", "مش مستوعب", "مو واضح", "مش واضح", "بسط", "بسطها", "وضح", "وضحلي", "اشرح ابسط", "اشرحها ابسط", "فهمني"]):
            return "followup_simple"
        if _v39_has_any(n, ["مثال", "هات مثال", "بالارقام", "بالأرقام", "رقميا", "تطبيق"]):
            return "followup_example"
        if _v39_has_any(n, ["بالتفصيل", "فصل", "فصّل", "الدليل", "ليه", "لماذا", "ازاي حسبتها", "كيف حسبتها"]):
            return "followup_detail"
    return None

def is_pure_social_message(text: str, context: dict | None = None) -> bool:  # type: ignore[override]
    return detect_human_message_kind(text, context) in {"greeting", "wellbeing", "thanks", "ack", "identity"}

def should_send_processing_notice(text: str, context: dict | None = None) -> bool:  # type: ignore[override]
    # لا تظهر حالة "تحليل المسألة" مع أي كلام اجتماعي أو متابعة قصيرة.
    kind = detect_human_message_kind(text, context)
    if kind in {"greeting", "wellbeing", "thanks", "ack", "identity", "followup_simple", "followup_example", "followup_detail"}:
        return False
    # تظهر فقط إذا فيه مؤشرات فتوى/حساب حقيقية.
    return _v39_has_domain_hint(text)

def human_smalltalk_reply(question: str, context: dict | None = None, name: str = "") -> str:  # type: ignore[override]
    kind = detect_human_message_kind(question, context) or "greeting"
    dialect = detect_dialect_human(question, context)
    who = f" يا {name.strip()}" if name else ""
    seed = f"v39:{kind}:{dialect}:{normalize_ar_human(question)}:{datetime.now().strftime('%Y-%m-%d-%H')}"
    n = normalize_ar_human(question)
    has_salam = _v39_has_any(n, ["السلام عليكم", "سلام عليكم"])
    has_wellbeing = _v39_has_any(n, PURE_WELLBEING_V39)

    # ردود اجتماعية فقط، لا دعوة متكررة للمسألة، لا مقدمة شرعية.
    if has_salam and has_wellbeing:
        pools = {
            "egyptian": [f"وعليكم السلام ورحمة الله وبركاته{who}. الحمد لله، بخير. إنت عامل إيه؟", f"وعليكم السلام{who}. الحمد لله تمام، ربنا يكرمك. أخبارك إيه؟"],
            "gulf": [f"وعليكم السلام ورحمة الله وبركاته{who}. الحمد لله بخير، عساك بخير.", f"وعليكم السلام{who}. بخير ولله الحمد، الله يحييك."],
            "shami": [f"وعليكم السلام ورحمة الله{who}. الحمد لله منيح. إنت كيفك؟"],
            "moroccan": [f"وعليكم السلام ورحمة الله{who}. الحمد لله بخير، نتمنى تكون بخير."],
            "sudanese": [f"وعليكم السلام ورحمة الله{who}. الحمد لله تمام. كيفك إنت؟"],
            "standard": [f"وعليكم السلام ورحمة الله وبركاته{who}. الحمد لله بخير، أسأل الله أن تكون بخير.", f"وعليكم السلام ورحمة الله وبركاته{who}. بخير ولله الحمد."],
        }
        return _pick(pools.get(dialect) or pools["standard"], seed)

    if kind == "wellbeing":
        pools = {
            "egyptian": ["الحمد لله بخير. إنت عامل إيه؟", "تمام الحمد لله. طمني عليك."],
            "gulf": ["بخير ولله الحمد، عساك بخير.", "الحمد لله بخير. الله يحييك."],
            "shami": ["الحمد لله منيح. إنت كيفك؟", "تمام الحمد لله. شو أخبارك؟"],
            "moroccan": ["الحمد لله بخير، نتمنى تكون بخير."],
            "sudanese": ["الحمد لله تمام. كيفك إنت؟"],
            "standard": ["بخير ولله الحمد. أسأل الله أن تكون بخير.", "الحمد لله بخير."],
        }
        return _pick(pools.get(dialect) or pools["standard"], seed)

    if kind == "greeting":
        pools = {
            "egyptian": [f"وعليكم السلام ورحمة الله وبركاته{who}. أهلاً بيك.", f"أهلاً{who}. نورت."],
            "gulf": [f"وعليكم السلام ورحمة الله وبركاته{who}. حيّاك الله.", f"هلا والله{who}. حيّاك."],
            "shami": [f"وعليكم السلام ورحمة الله{who}. أهلاً وسهلاً.", f"أهلاً فيك{who}."],
            "moroccan": [f"وعليكم السلام ورحمة الله{who}. مرحبا."],
            "sudanese": [f"وعليكم السلام ورحمة الله{who}. مرحب بيك."],
            "standard": [f"وعليكم السلام ورحمة الله وبركاته{who}. أهلاً بك.", f"مرحبًا{who}."],
        }
        if has_salam:
            opts = [o for o in (pools.get(dialect) or pools["standard"]) if "وعليكم" in o] or (pools.get(dialect) or pools["standard"])
            return _pick(opts, seed)
        return _pick(pools.get(dialect) or pools["standard"], seed)

    if kind == "thanks":
        pools = {
            "egyptian": ["العفو، تحت أمرك.", "ربنا يبارك فيك."],
            "gulf": ["العفو، حياك الله.", "الله يعافيك."],
            "shami": ["العفو، أهلًا فيك."],
            "standard": ["العفو، بارك الله فيك.", "يسعدني خدمتك."],
        }
        return _pick(pools.get(dialect) or pools["standard"], seed)

    if kind == "ack":
        pools = {
            "egyptian": ["تمام، أنا معاك.", "ماشي."],
            "gulf": ["تمام، أبشر.", "حاضر."],
            "standard": ["تمام.", "حسنًا."],
        }
        return _pick(pools.get(dialect) or pools["standard"], seed)

    if kind == "identity":
        pools = {
            "egyptian": ["أنا مفتي المواريث الذكي؛ أساعدك تفهم مسائل المواريث وأحسب الأنصبة، ولو البيانات ناقصة بسألك بدل ما أخمّن."],
            "gulf": ["أنا مفتي المواريث الذكي؛ أساعدك في حساب الإرث وشرح أحكام الفرائض، وإذا نقصت البيانات أطلب توضيحًا."],
            "standard": ["أنا مفتي المواريث الذكي؛ أساعدك في شرح أحكام المواريث وحساب الأنصبة، وأطلب التوضيح عند نقص البيانات."],
        }
        return _pick(pools.get(dialect) or pools["standard"], seed)

    return "أنا معك."

# V39 dialect override: short Gulf greetings مثل "هلا" لا تُعامل كفصحى.
def detect_dialect_human(text: str, context: dict | None = None) -> str:  # type: ignore[override]
    n = normalize_ar_human(text)
    if any(x in n for x in ["ازاي", "ايه", "عايز", "عاوز", "مش", "مفهمتش", "بسطهالي", "مراته", "ساب", "متشكر", "عامل ايه", "ازيك", "ازايك"]):
        return "egyptian"
    if any(x in n for x in ["هلا", "يا هلا", "وش", "ايش", "شلون", "ابشر", "كذا", "رجال", "حياك", "عقب", "مو", "ماني", "يعطيك", "عساك"]):
        return "gulf"
    if any(x in n for x in ["شو", "قديش", "هيك", "بدي", "بدّي", "عم", "كيفك"]):
        return "shami"
    if any(x in n for x in ["شنو", "واش", "فالميراث", "بزاف", "نعاونك", "ديال"]):
        return "moroccan"
    toks = set(n.split())
    if any(x in n for x in ["الزول", "عندو"]) or ("ليك" in toks) or ("كده" in toks):
        return "sudanese"
    if context and context.get("last_dialect"):
        return str(context.get("last_dialect"))
    return "standard"

# V39.1 final natural smalltalk override: no "وعليكم السلام" unless user actually said السلام.
def human_smalltalk_reply(question: str, context: dict | None = None, name: str = "") -> str:  # type: ignore[override]
    kind = detect_human_message_kind(question, context) or "greeting"
    dialect = detect_dialect_human(question, context)
    who = f" يا {name.strip()}" if name else ""
    seed = f"v39.1:{kind}:{dialect}:{normalize_ar_human(question)}:{datetime.now().strftime('%Y-%m-%d-%H')}"
    n = normalize_ar_human(question)
    has_salam = _v39_has_any(n, ["السلام عليكم", "سلام عليكم"])
    has_wellbeing = _v39_has_any(n, PURE_WELLBEING_V39)

    if has_salam and has_wellbeing:
        pools = {
            "egyptian": [f"وعليكم السلام ورحمة الله وبركاته{who}. الحمد لله، بخير. إنت عامل إيه؟", f"وعليكم السلام{who}. الحمد لله تمام، ربنا يكرمك. أخبارك إيه؟"],
            "gulf": [f"وعليكم السلام ورحمة الله وبركاته{who}. الحمد لله بخير، عساك بخير.", f"وعليكم السلام{who}. بخير ولله الحمد، الله يحييك."],
            "shami": [f"وعليكم السلام ورحمة الله{who}. الحمد لله منيح. إنت كيفك؟"],
            "moroccan": [f"وعليكم السلام ورحمة الله{who}. الحمد لله بخير، نتمنى تكون بخير."],
            "sudanese": [f"وعليكم السلام ورحمة الله{who}. الحمد لله تمام. كيفك إنت؟"],
            "standard": [f"وعليكم السلام ورحمة الله وبركاته{who}. الحمد لله بخير، أسأل الله أن تكون بخير.", f"وعليكم السلام ورحمة الله وبركاته{who}. بخير ولله الحمد."],
        }
        return _pick(pools.get(dialect) or pools["standard"], seed)
    if kind == "wellbeing":
        pools = {
            "egyptian": ["الحمد لله بخير. إنت عامل إيه؟", "تمام الحمد لله. طمني عليك."],
            "gulf": ["بخير ولله الحمد، عساك بخير.", "الحمد لله بخير. الله يحييك."],
            "shami": ["الحمد لله منيح. إنت كيفك؟", "تمام الحمد لله. شو أخبارك؟"],
            "moroccan": ["الحمد لله بخير، نتمنى تكون بخير."],
            "sudanese": ["الحمد لله تمام. كيفك إنت؟"],
            "standard": ["بخير ولله الحمد. أسأل الله أن تكون بخير.", "الحمد لله بخير."],
        }
        return _pick(pools.get(dialect) or pools["standard"], seed)
    if kind == "greeting":
        pools = {
            "egyptian": [f"وعليكم السلام ورحمة الله وبركاته{who}. أهلاً بيك.", f"أهلاً{who}. نورت."],
            "gulf": [f"وعليكم السلام ورحمة الله وبركاته{who}. حيّاك الله.", f"هلا والله{who}. حيّاك.", f"يا هلا{who}."],
            "shami": [f"وعليكم السلام ورحمة الله{who}. أهلاً وسهلاً.", f"أهلاً فيك{who}."],
            "moroccan": [f"وعليكم السلام ورحمة الله{who}. مرحبا.", f"مرحبا{who}."],
            "sudanese": [f"وعليكم السلام ورحمة الله{who}. مرحب بيك.", f"مرحب{who}."],
            "standard": [f"وعليكم السلام ورحمة الله وبركاته{who}. أهلاً بك.", f"مرحبًا{who}."],
        }
        opts = pools.get(dialect) or pools["standard"]
        if has_salam:
            opts = [o for o in opts if "وعليكم" in o] or opts
        else:
            opts = [o for o in opts if "وعليكم" not in o] or opts
        return _pick(opts, seed)
    if kind == "thanks":
        pools = {"egyptian":["العفو، تحت أمرك.", "ربنا يبارك فيك."], "gulf":["العفو، حياك الله.", "الله يعافيك."], "shami":["العفو، أهلًا فيك."], "standard":["العفو، بارك الله فيك.", "يسعدني خدمتك."]}
        return _pick(pools.get(dialect) or pools["standard"], seed)
    if kind == "ack":
        pools = {"egyptian":["تمام، أنا معاك.", "ماشي."], "gulf":["تمام، أبشر.", "حاضر."], "standard":["تمام.", "حسنًا."]}
        return _pick(pools.get(dialect) or pools["standard"], seed)
    if kind == "identity":
        pools = {"egyptian":["أنا مفتي المواريث الذكي؛ أساعدك تفهم مسائل المواريث وأحسب الأنصبة، ولو البيانات ناقصة بسألك بدل ما أخمّن."], "gulf":["أنا مفتي المواريث الذكي؛ أساعدك في حساب الإرث وشرح أحكام الفرائض، وإذا نقصت البيانات أطلب توضيحًا."], "standard":["أنا مفتي المواريث الذكي؛ أساعدك في شرح أحكام المواريث وحساب الأنصبة، وأطلب التوضيح عند نقص البيانات."]}
        return _pick(pools.get(dialect) or pools["standard"], seed)
    return "أنا معك."

# ---------------------------------------------------------------------------
# V40 True Human Social Router
# الهدف: التعامل مع الكلام الاجتماعي ككلام اجتماعي طبيعي، لا كمدخل لمسألة.
# لا يذكر المواريث ولا يطلب السؤال إلا إذا المستخدم سأل فعلًا في المجال.
# يعتمد على تطبيع عربي + قواعد نية عامة + RapidFuzz عند توفره.
# ---------------------------------------------------------------------------

V40_DOMAIN_TERMS = [
    "ميراث", "مواريث", "فرائض", "فرايض", "تركة", "تركه", "ورث", "يرث", "وارث", "نصيب", "قسمة", "قسمه", "توزيع",
    "مات", "ماتت", "توفي", "توفى", "توفت", "توفيت", "هلك", "ترك", "تركت", "ساب", "خلف", "خلّف",
    "حجب", "الحجب", "تعصيب", "العول", "الرد", "العمرية", "الغراوان", "الكلالة", "وصية", "وصيه", "دين", "ديون",
    "زوج", "زوجة", "زوجه", "ابن", "بنت", "ام", "أم", "اب", "أب", "اخ", "أخ", "اخت", "أخت", "جد", "جدة", "عم",
]

V40_GREETING_PATTERNS = [
    "السلام عليكم", "سلام عليكم", "وعليكم السلام", "السلام", "سلام",
    "هلا", "هلا والله", "يا هلا", "اهلا", "أهلا", "اهلين", "أهلين", "اهلا وسهلا", "أهلا وسهلا",
    "مرحبا", "مرحباً", "مرحبتين", "حياك", "حي الله", "يا مرحبا", "الو", "هاي", "hello", "hi",
    "صباح الخير", "صباح النور", "صباح الفل", "صباح الورد", "صباحك", "صباحو",
    "مساء الخير", "مساء النور", "مساء الفل", "مساء الورد", "مساءك", "مسا الخير", "مسا النور",
]

V40_WELLBEING_PATTERNS = [
    "كيف حالك", "كيف الحال", "كيفك", "شلونك", "اشلونك", "شخبارك", "وش اخبارك", "اخبارك", "شنو اخبارك",
    "عامل ايه", "عامل اي", "عامله ايه", "عاملة ايه", "ازيك", "ازايك", "كيف الامور", "كيف امورك",
    "طمني عليك", "علومك", "كيف انت", "كيف أنت", "لاباس", "لاباس عليك", "كيف الصحة", "كيف صحتك",
]

V40_THANKS_PATTERNS = [
    "شكرا", "شكرًا", "متشكر", "مشكور", "تسلم", "تسلمي", "جزاك الله", "بارك الله فيك", "يعطيك العافيه", "يعطيك العافية", "الله يجزاك خير",
]

V40_ACK_PATTERNS = ["تمام", "اوك", "أوك", "اوكي", "أوكي", "ok", "حاضر", "تم", "ماشي", "طيب", "جميل", "واضح"]

V40_FOLLOWUP_PATTERNS = [
    "مش فاهم", "ما افهم", "ما فهمت", "مفهمتش", "مش مستوعب", "مو واضح", "مش واضح", "وضح", "وضحلي", "بسط", "بسطها", "فهمني", "اشرح ابسط", "هات مثال", "مثال", "بالارقام", "بالأرقام", "ازاي حسبتها", "كيف حسبتها",
]

def _v40_domain_score(text: str) -> int:
    n = normalize_ar_human(text)
    if not n:
        return 0
    score = 0
    for term in V40_DOMAIN_TERMS:
        tn = normalize_ar_human(term)
        if tn and re.search(rf"(^|\s){re.escape(tn)}($|\s)", n):
            score += 2
    # المبالغ وحدها ليست سؤال مواريث، لكنها تقوّي المجال لو معها ترك/مات/تركة.
    if re.search(r"\b\d+[\d,\.]*\b", n) and any(x in n for x in ["ريال", "جنيه", "دولار", "درهم", "مبلغ", "تركة", "تركه"]):
        score += 1
    return score

def _v40_short(text: str, max_words: int = 10) -> bool:
    return len(normalize_ar_human(text).split()) <= max_words

def _v40_has_exact_or_fuzzy(text: str, phrases: list[str], threshold: int = 88) -> bool:
    n = normalize_ar_human(text)
    if not n:
        return False
    # expressions like "مساء الفل" should match by prefix/category too
    for p in phrases:
        pn = normalize_ar_human(p)
        if pn and (pn in n or n in pn):
            return True
    # Heuristic buckets for open-ended greetings, not just fixed phrases
    if re.search(r"(^|\s)(مساء|مسا|صباح)(\s+\w+)?($|\s)", n):
        return True
    if re.search(r"(^|\s)(هلا|اهلا|اهلين|مرحبا|مرحب|سلام|هاي|الو)(\s|$)", n):
        return True
    if _rf_fuzz is not None and len(n.split()) <= 8:
        for p in phrases:
            pn = normalize_ar_human(p)
            if pn:
                try:
                    if _rf_fuzz.partial_ratio(pn, n) >= threshold:
                        return True
                except Exception:
                    pass
    return False

def _v40_has_wellbeing(text: str) -> bool:
    n = normalize_ar_human(text)
    if not n:
        return False
    if _v40_has_exact_or_fuzzy(n, V40_WELLBEING_PATTERNS, 88):
        return True
    return bool(re.search(r"(^|\s)(كيف|شلون|اشلون|ازيك|اخبارك|شخبارك|عامل|عامله|عاملة|طمني|علومك)(\s|$)", n))

def _v40_has_greeting(text: str) -> bool:
    return _v40_has_exact_or_fuzzy(text, V40_GREETING_PATTERNS, 87)

def detect_human_message_kind(text: str, context: dict | None = None) -> str | None:  # type: ignore[override]
    n = normalize_ar_human(text)
    if not n:
        return None
    words = n.split()
    short = len(words) <= 14
    domain_score = _v40_domain_score(n)

    # Short social messages must be captured before any domain fallback.
    if short and domain_score == 0:
        if _v40_has_exact_or_fuzzy(n, V40_THANKS_PATTERNS, 88):
            return "thanks"
        if _v40_has_wellbeing(n):
            return "wellbeing"
        if _v40_has_greeting(n):
            return "greeting"
        if _v40_has_exact_or_fuzzy(n, V40_ACK_PATTERNS, 92):
            return "ack"
        if any(x in n for x in ["انت مين", "مين انت", "من انت", "اسمك ايه", "ما اسمك", "وش اسمك"]):
            return "identity"

    # Follow-up can be social-like but requires previous context.
    if len(words) <= 18 and _v40_has_exact_or_fuzzy(n, V40_FOLLOWUP_PATTERNS, 84):
        if any(x in n for x in ["مثال", "بالارقام", "بالأرقام"]):
            return "followup_example"
        return "followup_simple"
    if len(words) <= 18 and any(x in n for x in ["بالتفصيل", "الدليل", "ليه", "لماذا", "ازاي حسبتها", "كيف حسبتها"]):
        return "followup_detail"
    return None

def is_pure_social_message(text: str, context: dict | None = None) -> bool:  # type: ignore[override]
    return detect_human_message_kind(text, context) in {"greeting", "wellbeing", "thanks", "ack", "identity"}

def should_send_processing_notice(text: str, context: dict | None = None) -> bool:  # type: ignore[override]
    kind = detect_human_message_kind(text, context)
    if kind in {"greeting", "wellbeing", "thanks", "ack", "identity", "followup_simple", "followup_example", "followup_detail"}:
        return False
    return _v40_domain_score(text) > 0

def human_smalltalk_reply(question: str, context: dict | None = None, name: str = "") -> str:  # type: ignore[override]
    kind = detect_human_message_kind(question, context) or "greeting"
    dialect = detect_dialect_human(question, context)
    seed = f"v40:{kind}:{dialect}:{normalize_ar_human(question)}:{datetime.now().strftime('%Y-%m-%d-%H')}"
    n = normalize_ar_human(question)
    has_salam = any(x in n for x in ["السلام عليكم", "سلام عليكم"])
    has_evening = bool(re.search(r"(^|\s)(مساء|مسا)(\s|$)", n))
    has_morning = bool(re.search(r"(^|\s)(صباح)(\s|$)", n))
    has_hala = bool(re.search(r"(^|\s)(هلا|يا هلا|اهلين|اهلا)(\s|$)", n))
    has_well = _v40_has_wellbeing(n)
    who = f" يا {name.strip()}" if name else ""

    # Combined greeting + wellbeing.
    if has_salam and has_well:
        pools = {
            "egyptian": [f"وعليكم السلام ورحمة الله وبركاته{who}. الحمد لله بخير، إنت عامل إيه؟", f"وعليكم السلام{who}. تمام الحمد لله، أخبارك إيه؟"],
            "gulf": [f"وعليكم السلام ورحمة الله وبركاته{who}. الحمد لله بخير، عساك بخير.", f"وعليكم السلام{who}. بخير ولله الحمد، الله يحييك."],
            "shami": [f"وعليكم السلام ورحمة الله{who}. الحمد لله منيح، إنت كيفك؟"],
            "sudanese": [f"وعليكم السلام ورحمة الله{who}. الحمد لله تمام، كيفك إنت؟"],
            "standard": [f"وعليكم السلام ورحمة الله وبركاته{who}. الحمد لله بخير، أسأل الله أن تكون بخير."],
        }
        return _pick(pools.get(dialect) or pools["standard"], seed)

    if kind == "wellbeing":
        pools = {
            "egyptian": ["الحمد لله بخير، إنت عامل إيه؟", "تمام الحمد لله، طمني عليك."],
            "gulf": ["بخير ولله الحمد، عساك بخير.", "الحمد لله بخير، الله يحييك."],
            "shami": ["الحمد لله منيح، إنت كيفك؟", "تمام الحمد لله، شو أخبارك؟"],
            "moroccan": ["الحمد لله بخير، نتمنى تكون بخير."],
            "sudanese": ["الحمد لله تمام، كيفك إنت؟"],
            "standard": ["الحمد لله بخير.", "بخير ولله الحمد."],
        }
        return _pick(pools.get(dialect) or pools["standard"], seed)

    if kind == "greeting":
        if has_salam:
            pools = {
                "egyptian": [f"وعليكم السلام ورحمة الله وبركاته{who}. أهلاً بيك.", f"وعليكم السلام{who}. نورت."],
                "gulf": [f"وعليكم السلام ورحمة الله وبركاته{who}. حيّاك الله.", f"وعليكم السلام{who}. يا هلا."],
                "standard": [f"وعليكم السلام ورحمة الله وبركاته{who}.", f"وعليكم السلام ورحمة الله وبركاته{who}."],
            }
            return _pick(pools.get(dialect) or pools["standard"], seed)
        if has_evening:
            pools = {
                "egyptian": ["مساء النور والفل.", "مساء الفل عليك."],
                "gulf": ["مساء النور، حيّاك الله.", "مساء الخير."],
                "shami": ["مسا النور.", "مسا الخير."],
                "standard": ["مساء النور.", "مساء الخير."],
            }
            return _pick(pools.get(dialect) or pools["standard"], seed)
        if has_morning:
            pools = {
                "egyptian": ["صباح النور.", "صباح الفل."],
                "gulf": ["صباح النور، حيّاك الله.", "صباح الخير."],
                "standard": ["صباح النور.", "صباح الخير."],
            }
            return _pick(pools.get(dialect) or pools["standard"], seed)
        if has_hala:
            pools = {
                "egyptian": ["أهلًا بيك.", "نورت."],
                "gulf": ["يا هلا.", "هلا والله."],
                "shami": ["أهلين.", "يا هلا."],
                "standard": ["مرحبًا.", "أهلًا بك."],
            }
            return _pick(pools.get(dialect) or pools["standard"], seed)
        return _pick(["مرحبًا.", "أهلًا بك."], seed)

    if kind == "thanks":
        pools = {
            "egyptian": ["العفو.", "تحت أمرك."],
            "gulf": ["العفو، الله يحييك.", "حياك الله."],
            "standard": ["العفو.", "بارك الله فيك."],
        }
        return _pick(pools.get(dialect) or pools["standard"], seed)

    if kind == "ack":
        pools = {"egyptian": ["تمام.", "ماشي."], "gulf": ["تمام.", "أبشر."], "standard": ["تمام.", "حسنًا."]}
        return _pick(pools.get(dialect) or pools["standard"], seed)

    if kind == "identity":
        pools = {
            "egyptian": ["أنا مفتي المواريث الذكي؛ أساعدك في حساب مسائل الميراث وشرح أحكامها، ولو البيانات ناقصة بسألك بدل ما أخمّن."],
            "gulf": ["أنا مفتي المواريث الذكي؛ أساعدك في حساب الإرث وشرح أحكام الفرائض، وإذا نقصت البيانات أطلب توضيحًا."],
            "standard": ["أنا مفتي المواريث الذكي؛ أساعدك في شرح أحكام المواريث وحساب الأنصبة، وأطلب التوضيح عند نقص البيانات."],
        }
        return _pick(pools.get(dialect) or pools["standard"], seed)

    return "أنا معك."

def answer_role(question: str, answer_text: str, context: dict | None = None) -> str:  # type: ignore[override]
    kind = detect_human_message_kind(question, context)
    if kind in {"greeting", "wellbeing", "thanks", "ack", "identity"}:
        return "smalltalk"
    if kind in {"followup_simple", "followup_example", "followup_detail"}:
        return "followup"
    q_domain = _v40_domain_score(question)
    nans = normalize_ar_human(answer_text)
    if any(x in nans for x in ["يحتاج توضيح", "تحتاج تحديد", "لا يصح حسابها بالتخمين", "اكتب السؤال بصيغه اوضح", "اكتب السؤال بصيغة اوضح"]):
        return "clarification"
    if "من التركه" in nans or "مراجعه مجموع الانصبه" in nans or "القسمه النقديه" in nans:
        return "calculation"
    if q_domain > 0 or any(x in nans for x in ["الحكم", "المقصود", "التعريف"]):
        return "fiqh"
    return "general"

def should_decorate_with_preamble(question: str, answer_text: str, context: dict | None = None) -> bool:  # type: ignore[override]
    return answer_role(question, answer_text, context) in {"calculation", "fiqh"}

# V40.1: fix social matching so greeting heuristics do not leak into thanks/ack/follow-up.
def _v401_phrase_only(text: str, phrases: list[str], threshold: int = 88) -> bool:
    n = normalize_ar_human(text)
    if not n:
        return False
    for p in phrases:
        pn = normalize_ar_human(p)
        if pn and (pn in n or n in pn):
            return True
    if _rf_fuzz is not None and len(n.split()) <= 8:
        for p in phrases:
            pn = normalize_ar_human(p)
            if pn:
                try:
                    if _rf_fuzz.partial_ratio(pn, n) >= threshold:
                        return True
                except Exception:
                    pass
    return False

def detect_human_message_kind(text: str, context: dict | None = None) -> str | None:  # type: ignore[override]
    n = normalize_ar_human(text)
    if not n:
        return None
    words = n.split()
    short = len(words) <= 14
    domain_score = _v40_domain_score(n)
    if short and domain_score == 0:
        if _v401_phrase_only(n, V40_THANKS_PATTERNS, 90):
            return "thanks"
        if _v40_has_wellbeing(n):
            return "wellbeing"
        if _v40_has_greeting(n):
            return "greeting"
        if _v401_phrase_only(n, V40_ACK_PATTERNS, 94):
            return "ack"
        if any(x in n for x in ["انت مين", "مين انت", "من انت", "اسمك ايه", "ما اسمك", "وش اسمك"]):
            return "identity"
    if len(words) <= 18 and _v401_phrase_only(n, V40_FOLLOWUP_PATTERNS, 84):
        if any(x in n for x in ["مثال", "بالارقام", "بالأرقام"]):
            return "followup_example"
        return "followup_simple"
    if len(words) <= 18 and any(x in n for x in ["بالتفصيل", "الدليل", "ليه", "لماذا", "ازاي حسبتها", "كيف حسبتها"]):
        return "followup_detail"
    return None

# V40.2: wellbeing must not match open greetings like هلا/مساء.
def _v40_has_wellbeing(text: str) -> bool:  # type: ignore[override]
    n = normalize_ar_human(text)
    if not n:
        return False
    if _v401_phrase_only(n, V40_WELLBEING_PATTERNS, 88):
        return True
    return bool(re.search(r"(^|\s)(كيف|شلون|اشلون|ازيك|ازايك|اخبارك|شخبارك|عامل|عامله|عاملة|طمني|علومك)(\s|$)", n))

# ---------------------------------------------------------------------------
# V41 Core Intelligence Foundation override
# This final block intentionally overrides earlier v37-v40 functions.
# It is not a per-question fixed-answer layer; it is a general intent/context layer.
# ---------------------------------------------------------------------------
try:
    import v41_core_intelligence as _v41
except Exception:  # keep the project alive if optional module is missing
    _v41 = None

if _v41 is not None:
    def normalize_ar_human(text: str) -> str:  # type: ignore[override]
        return _v41.normalize(text)

    def detect_dialect_human(text: str, context: dict | None = None) -> str:  # type: ignore[override]
        return _v41.detect_dialect(text, context)

    def detect_human_message_kind(text: str, context: dict | None = None) -> str | None:  # type: ignore[override]
        r = _v41.classify_intent(text, context)
        mapping = {
            "social_greeting_status": "greeting",
            "social_status": "wellbeing",
            "social_status_reply": "ack",
            "social_greeting": "greeting",
            "social_thanks": "thanks",
            "social_ack": "ack",
            "identity": "identity",
            "followup_simplify": "followup_simple",
            "followup_example": "followup_example",
            "followup_detail": "followup_detail",
        }
        return mapping.get(r.intent)

    def is_pure_social_message(text: str, context: dict | None = None) -> bool:  # type: ignore[override]
        return _v41.is_pure_social(text, context)

    def should_send_processing_notice(question: str, context: dict | None = None) -> bool:  # type: ignore[override]
        return _v41.should_send_processing_notice(question, context)

    def should_decorate_with_preamble(question: str, answer_text: str, context: dict | None = None) -> bool:  # type: ignore[override]
        return _v41.should_decorate_with_preamble(question, answer_text, context)

    def preamble_human(question: str, answer_text: str, name: str = "", dialect: str = "standard", seed: str = "") -> str:  # type: ignore[override]
        return _v41.preamble(question, answer_text, name=name, dialect=dialect, seed=seed)

    def human_smalltalk_reply(question: str, context: dict | None = None, name: str = "") -> str:  # type: ignore[override]
        return _v41.social_reply(question, context=context, name=name)

    def answer_role(question: str, answer_text: str, context: dict | None = None) -> str:  # type: ignore[override]
        r = _v41.classify_intent(question, context)
        if r.intent.startswith("social_") or r.intent == "identity":
            return "smalltalk"
        if r.intent.startswith("followup_"):
            return "followup"
        if not _v41.should_decorate_with_preamble(question, answer_text, context):
            an = _v41.normalize(answer_text)
            if "يحتاج توضيح" in an or "اكتب السؤال" in an:
                return "clarification"
            return "general"
        return "calculation" if r.intent == "inheritance_calculation" else "fiqh"

# ---------------------------------------------------------------------------
# V44 Dialogue State Machine override
# General social/domain/follow-up routing. This is a state machine layer, not a
# per-case patch. It prevents all high-confidence social dialogue from leaking
# into the fatwa/runtime path.
# ---------------------------------------------------------------------------
try:
    import v44_dialogue_state_machine as _v44
except Exception:
    _v44 = None

if _v44 is not None:
    def normalize_ar_human(text: str) -> str:  # type: ignore[override]
        return _v44.normalize(text)

    def detect_dialect_human(text: str, context: dict | None = None) -> str:  # type: ignore[override]
        return _v44.detect_dialect(text, context)

    def detect_human_message_kind(text: str, context: dict | None = None) -> str | None:  # type: ignore[override]
        r = _v44.classify(text, context)
        if r.social:
            mapping = {
                "social_greeting_status": "greeting",
                "social_status": "wellbeing",
                "social_status_reply": "ack",
                "social_greeting": "greeting",
                "social_thanks": "thanks",
                "social_ack": "ack",
                "identity": "identity",
            }
            return mapping.get(r.intent, "greeting")
        if r.followup:
            return {
                "followup_simplify": "followup_simple",
                "followup_example": "followup_example",
                "followup_detail": "followup_detail",
            }.get(r.intent, "followup_simple")
        return None

    def is_pure_social_message(text: str, context: dict | None = None) -> bool:  # type: ignore[override]
        return _v44.is_social(text, context)

    def should_send_processing_notice(question: str, context: dict | None = None) -> bool:  # type: ignore[override]
        return _v44.should_send_processing_notice(question, context)

    def should_decorate_with_preamble(question: str, answer_text: str, context: dict | None = None) -> bool:  # type: ignore[override]
        return _v44.should_use_fatwa_preamble(question, answer_text, context)

    def preamble_human(question: str, answer_text: str, name: str = "", dialect: str = "standard", seed: str = "") -> str:  # type: ignore[override]
        return _v44.preamble(question, answer_text, name=name, dialect=dialect, seed=seed)

    def human_smalltalk_reply(question: str, context: dict | None = None, name: str = "") -> str:  # type: ignore[override]
        return _v44.social_reply(question, context=context, name=name)

    def answer_role(question: str, answer_text: str, context: dict | None = None) -> str:  # type: ignore[override]
        r = _v44.classify(question, context)
        if r.social:
            return "smalltalk"
        if r.followup:
            return "followup"
        if not _v44.should_use_fatwa_preamble(question, answer_text, context):
            an = _v44.normalize(answer_text)
            if "يحتاج توضيح" in an or "اكتب السؤال" in an:
                return "clarification"
            return "general"
        return "calculation" if r.intent == "inheritance_calculation" else "fiqh"
