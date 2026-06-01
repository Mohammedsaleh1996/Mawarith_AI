# -*- coding: utf-8 -*-
"""
Mawareth AI Runtime v9 wrapper over locked v8.
- Keeps v8 locked; no direct edits to the baseline.
- Adds safer public NLU normalization and fiqh intent routing.
- Adds safety stops for incomplete/generic questions.
- Does not hardcode full answers for individual inheritance cases.
"""
from __future__ import annotations
import re, sys
from pathlib import Path
from fractions import Fraction
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

HERE = Path(__file__).resolve().parent
V8_PATH = HERE / "runtime_v8" / "mawarith_ai_final_v8"
sys.path.insert(0, str(V8_PATH))
import mawarith_ai_runtime as v8  # noqa
from fiqh_concept_engine import answer_concept, detect_concept_key, is_followup
try:
    from human_conversation_enhancer import (
        detect_human_message_kind as _v37_detect_human_kind,
        human_smalltalk_reply as _v37_human_smalltalk_reply,
        normalize_ar_human as _v37_norm_human,
        fuzzy_contains as _v37_fuzzy_contains,
    )
except Exception:
    _v37_detect_human_kind = None
    _v37_human_smalltalk_reply = None
    _v37_norm_human = None
    _v37_fuzzy_contains = None

normalize_ar = v8.normalize_ar
CALC_HEADERS = ["النتيجة الحسابية:", "القسمة كده:", "القسمة بتكون كذا:", "القسمة هيك:", "القسمة هكذا:"]


def _n(text: str) -> str:
    return v8.normalize_ar(text)


def _dialect(q: str):
    return v8.detect_dialect(q)


def _desired_header(q: str) -> str:
    n = _n(q)
    # Strong Shami markers first
    if any(w in n for w in ["قديش", "شو", "زلمة", "مرتو", "ابنو", "بنتو", "بيوخد", "بياخد", "مرة توفت", "مره توفت"]):
        return "القسمة هيك:"
    # Strong Egyptian markers before generic Gulf words like خلف
    if any(w in n for w in ["ازاي", "ايه", "راجل", "وساب", "اتوفى", "حرمته", "مراته", "نعمل ايه"]):
        return "القسمة كده:"
    if any(w in n for w in ["رجال", "خلّف", "خلف", "كيف القسمة", "كيف تتقسم", "كيف نحسبها"]):
        return "القسمة بتكون كذا:"
    return _dialect(q).calc_header()


def _safe_clarification(q: str, msg: str | None = None) -> str:
    dialect = _dialect(q)
    base = dialect.needs_clarification()
    return base + "\n\n- " + (msg or "لم أستخرج ورثة كافيين للحساب. اذكر الورثة بوضوح.")


def _advanced_stop(q: str, topic: str) -> str:
    # Use clear public language with the exact safety phrase too.
    dialect = _dialect(q)
    return dialect.unsupported_advanced() + f"\n\n- {topic}\n\nتنبيه: لا يصح حسابها بالتخمين."


def _replace_header(out: str, q: str) -> str:
    desired = _desired_header(q)
    for h in CALC_HEADERS:
        if out.startswith(h):
            return desired + out[len(h):]
    return out


def preprocess_question(q: str) -> str:
    t = " " + q + " "
    # Specific sibling forms first, before generic possessive replacements.
    phrase_repl = [
        ("وولده", " وابنه"), ("وولدو", " وابنه"), ("وابنو", " وابنه"),
        ("وبنته", " وبنت"), ("وبنتو", " وبنت"), ("وبنتها", " وبنت"),
        ("ومراته", " وزوجة"), ("ومرته", " وزوجة"), ("وحرمته", " وزوجة"),
        ("وزوجته", " وزوجة"), ("زوجته", "زوجة"),
        ("وزوجها", " وزوج"), ("وجوزها", " وزوج"),
        ("وأبوه", " وأب"), ("وابوه", " وأب"), ("وأبوها", " وأب"), ("وابوها", " وأب"), ("وأباه", " وأب"), ("واباه", " وأب"),
        ("وأمه", " وأم"), ("وامه", " وأم"), ("وأمها", " وأم"), ("وامها", " وأم"),
        ("واخوه الشقيق", " وأخ شقيق"), ("وأخوه الشقيق", " وأخ شقيق"),
        ("واخاه الشقيق", " وأخ شقيق"), ("وأخاه الشقيق", " وأخ شقيق"),
        ("وخوه الشقيق", " وأخ شقيق"), ("خوه الشقيق", "أخ شقيق"),
        ("اخوه الشقيق", "أخ شقيق"), ("أخوه الشقيق", "أخ شقيق"),
        ("اخاه الشقيق", "أخ شقيق"), ("أخاه الشقيق", "أخ شقيق"),
        ("أختين شقيقات", "أختين شقيقتين"), ("اختين شقيقات", "أختين شقيقتين"),
        ("أخوات شقيقات", "أخوات شقيقات"), ("اخوات شقيقات", "أخوات شقيقات"),
        ("أخوين من الأم", "أخوين لأم"), ("اخوين من الام", "أخوين لأم"),
        ("أخوين من امها", "أخوين لأم"), ("اخوين من امها", "أخوين لأم"),
        ("اتنين اخوة من الأم", "أخوين لأم"), ("اتنين اخوه من الام", "أخوين لأم"),
        ("اثنين اخوة من الأم", "أخوين لأم"),
        ("إخوة من الأم", "إخوة لأم"), ("اخوة من الأم", "إخوة لأم"), ("اخوه من الام", "إخوة لأم"),
        ("أخ من الأم", "أخ لأم"), ("اخ من الام", "أخ لأم"),
        ("أخت من الأم", "أخت لأم"), ("اخت من الام", "أخت لأم"),
        ("أخ من الأب والأم", "أخ شقيق"), ("اخ من الاب والام", "أخ شقيق"),
        ("أخت من الأب والأم", "أخت شقيقة"), ("اخت من الاب والام", "أخت شقيقة"),
        ("أختين من الأب والأم", "أختين شقيقتين"), ("اختين من الاب والام", "أختين شقيقتين"),
        ("أخ من الأب", "أخ لأب"), ("اخ من الاب", "أخ لأب"),
        ("أخت من الأب", "أخت لأب"), ("اخت من الاب", "أخت لأب"),
        ("أختين من الأب", "أختين لأب"), ("اختين من الاب", "أختين لأب"),
        ("ميت وراه", "مات وترك"),
    ]
    for a, b in phrase_repl:
        t = t.replace(a, b)
    # Remove casual tail phrases that confuse v8 classifier but do not change heirs.
    t = re.sub(r"القسمة\s+(إيه|ايه)", "القسمة", t, flags=re.IGNORECASE)
    t = re.sub(r"نعمل\s+(إيه|ايه)", "", t, flags=re.IGNORECASE)

    word_repl = [
        (r"(?<!\S)و?ولده(?!\S)|(?<!\S)و?ولدو(?!\S)|(?<!\S)و?ابنو(?!\S)|(?<!\S)و?ولدها(?!\S)", " وابنه"),
        (r"(?<!\S)و?بنتو(?!\S)|(?<!\S)و?بنته(?!\S)|(?<!\S)و?بنتها(?!\S)", " بنت"),
        (r"(?<!\S)و?مرتو(?!\S)|(?<!\S)و?مرته(?!\S)|(?<!\S)و?مراته(?!\S)|(?<!\S)و?حرمته(?!\S)", " زوجة"),
        (r"(?<!\S)و?مرتها(?!\S)|(?<!\S)و?جوزها(?!\S)|(?<!\S)و?زوجها(?!\S)", " زوج"),
        (r"(?<!\S)و?ابوه(?!\S)|(?<!\S)و?أبوه(?!\S)|(?<!\S)و?ابوها(?!\S)|(?<!\S)و?أبوها(?!\S)|(?<!\S)و?اباه(?!\S)|(?<!\S)و?أباه(?!\S)|(?<!\S)و?ابيه(?!\S)|(?<!\S)و?أبيه(?!\S)", " أب"),
        (r"(?<!\S)و?امه(?!\S)|(?<!\S)و?أمه(?!\S)|(?<!\S)و?امها(?!\S)|(?<!\S)و?أمها(?!\S)", " أم"),
    ]
    for pat, repl in word_repl:
        t = re.sub(pat, repl, t, flags=re.IGNORECASE)
    nt = _n(t)
    if "اب" in nt and ("اخوه" in nt or "اخو" in nt or "اخ " in nt):
        t = t.replace("وأخوه", "وأخ شقيق").replace("واخوه", "وأخ شقيق").replace("أخوه", "أخ شقيق").replace("اخوه", "أخ شقيق")
    return re.sub(r"\s+", " ", t).strip()



def _fixed_shares_answer(q: str) -> str:
    dialect = _dialect(q)
    n = _n(q)
    if dialect.name == 'egyptian':
        head = 'أيوه، ده سؤال فقهي في علم المواريث. الفروض المقدّرة ستة:'
    elif dialect.name in ('gulf', 'saudi'):
        head = 'نعم، هذا سؤال فقهي في علم المواريث. الفروض المقدّرة ستة:'
    elif dialect.name == 'shami':
        head = 'إيه، هذا سؤال فقهي بالمواريث. الفروض المقدّرة ستة:'
    else:
        head = 'هذا سؤال فقهي في علم المواريث. الفروض المقدّرة في القرآن الكريم ستة:'
    body = (
        f"{head}\n\n"
        "1) النصف: 1/2\n"
        "2) الربع: 1/4\n"
        "3) الثمن: 1/8\n"
        "4) الثلثان: 2/3\n"
        "5) الثلث: 1/3\n"
        "6) السدس: 1/6\n\n"
        "وتُسمّى فروضًا مقدّرة؛ لأنها أنصبة محددة بنصوص الشرع، تُعطى لأصحاب الفروض بحسب حالة الورثة والحجب.\n"
        "بعد إعطاء أصحاب الفروض فروضهم، يُنظر في الباقي: فإن وُجد عاصب أخذه، وإلا قد يقع الرد بحسب المسألة."
    )
    return body

def fiqh_route(q: str):
    n = _n(q)
    definitional_top = any(x in n for x in ["ما هو", "ما هي", "ما معنى", "ما معني", "معنى", "معني", "يعني", "اشرح", "شنو يعني", "وش معنى", "وش معني", "ما الفرق", "كم عدد", "متى", "كيف يكون", "حكم", "فرق بين", "الفرق بين", "انواع"])
    # Advanced/safety topics before general estate-rights because "اختلاف الدين" contains "الدين".
    if (not definitional_top) and ("مناسخة" in n or "مات احد الورثة" in n or "مات احد الورثه" in n or "ثم مات" in n):
        return ("advanced", "ظهر في السؤال باب المناسخات/مناسخة، وهو يحتاج ترتيب وفيات وأنصبة مستقلة.")
    if (not definitional_top) and "خنثى" in n:
        return ("advanced", "الخنثى يحتاج تحديد الحالة أو طريقة المعاملة الفقهية المعتمدة.")
    if (not definitional_top) and "حمل" in n:
        return ("advanced", "الحمل في الميراث يحتاج تحققًا من وجوده وولادته وحالته قبل الحكم.")
    if (not definitional_top) and "مفقود" in n:
        return ("advanced", "المفقود يحتاج حكمًا قضائيًا أو طريقة معتمدة قبل توزيع التركة.")
    if (not definitional_top) and ("ذوي الارحام" in n or "ذوي ارحام" in n or "ذوو الارحام" in n or "خال" in n or "عمة" in n or "ابن خال" in n):
        return ("advanced", "ذوي الأرحام / ذوو الأرحام باب يحتاج ترتيبًا فقهيًا خاصًا أو مذهبًا معتمدًا.")
    if "قاتل" in n or "قتل" in n or "اختلاف الدين" in n or "اختلاف دين" in n or "الرق" in n or "غير مسلم" in n or "مسيحي" in n:
        return ("mawani", None)

    death_calc = bool(re.search(r"(^|\s)(مات|توفي|توفى|توفت|ماتت|ترك|تركت|ساب|خلف|خلّف|ورث|الميت عنده)(\s|$)", n))
    definitional = any(x in n for x in ["ما هو", "ما هي", "ما معنى", "ما معني", "ما اسباب", "ما أسباب", "ما شروط", "معنى", "معني", "يعني", "اشرح", "شنو يعني", "وش معنى", "ما الفرق", "كم عدد", "متى", "كيف يكون", "حكم", "فرق بين", "الفرق بين", "انواع"])
    # لا نوجه السؤال إلى مفهوم فقهي إذا كان سؤالًا حسابيًا واضحًا بصيغة "ما نصيب..." مع وفاة/تركة.
    # هذا يمنع خلط أسئلة الحساب بمفاهيم مثل: الأخ لأب.
    if (not death_calc) and definitional:
        concept_key = detect_concept_key(q)
        if concept_key:
            return ("concept", concept_key)

    if "عاصب" in n or "تعصيب" in n:
        return ("canonical", "ما معنى التعصيب في علم المواريث؟")
    if "حجب" in n:
        return ("canonical", "ما الفرق بين حجب الحرمان وحجب النقصان؟")
    if "رد" in n and ("ميراث" in n or "فرائض" in n or "فرايض" in n or "الباقي" in n or "متى" in n or "امتى" in n or "يصير" in n or "يحصل" in n or "حكم" in n or "كيف" in n or "اشرح" in n):
        return ("canonical", "شنو يعني الرد في الميراث؟ ومتى يصير؟")
    if "عول" in n or "عالت" in n:
        return ("canonical", "شنو العول؟")
    if ("الفروض المقدره" in n or "الفروض المقدرة" in n or "الفروض المقدر" in n or
        "عدد الفروض" in n or "كم فرض" in n or "كم عدد الفروض" in n or
        "انصبة مقدرة" in n or "الانصبة المقدرة" in n or
        ("ما هي الفروض" in n and "قران" in n) or ("ما هي الفروض" in n and "مواريث" in n)):
        return ("fixed_shares", None)
    if "اصحاب الفروض" in n or "صاحب فرض" in n:
        return ("canonical", "ما معنى أصحاب الفروض؟")
    if "ديون" in n or "الدين قبل" in n or "نسدد الدين" in n or "قضاء الدين" in n or "ترتيب الحقوق" in n or "ترتيب التركة" in n or "قبل القس" in n or "تجهيز الميت" in n or "يخرج من التركة" in n:
        return ("canonical", "ما ترتيب الحقوق المتعلقة بالتركة قبل تقسيمها على الورثة؟")
    if (not death_calc) and ("وصية" in n or "اوصى" in n or "اوصي" in n or "الثلث" in n or "فوق الثلث" in n or "حد الوصية" in n):
        return ("canonical", "ما حكم الوصية لوارث؟")
    if "موانع" in n or "يمنع" in n and "ميراث" in n or "لا يرث القريب" in n:
        return ("mawani", None)
    if "الفرع الوارث" in n or "فرع وارث" in n:
        return ("canonical", "وش معنى الفرع الوارث؟")
    if "فرق بين الاخ" in n or "الفرق بين الاخ" in n or "انواع الاخوة" in n or "نوع الاخ" in n or "الاخوة في الميراث" in n or "لماذا لازم احدد نوع الاخ" in n:
        return ("canonical", "شنو الفرق بين الأخ الشقيق والأخ لأب والأخ لأم فالميراث؟")
    return None



# -----------------------------
# Extended agnatic heirs layer
# -----------------------------
# هذه الطبقة لا تضيف إجابات محفوظة لمسائل بعينها.
# وظيفتها استخراج طبقة العصبات البعيدة التي لا يدعمها v8 مباشرةً، ثم تمريرها لمحرك الحساب كعاصب بديل،
# وبعد الحساب تعيد تسمية العاصب وسبب الإرث إلى الوارث الحقيقي.

EXT_AGNATE_ORDER = [
    ("full_nephew", 70, "ابن الأخ الشقيق", "أبناء الأخ الشقيق", "ابن الأخ الشقيق/أبناء الأخ الشقيق يأخذ الباقي تعصيبًا إذا لم يوجد عاصب أقرب منه."),
    ("paternal_nephew", 80, "ابن الأخ لأب", "أبناء الأخ لأب", "ابن الأخ لأب/أبناء الأخ لأب يأخذ الباقي تعصيبًا إذا لم يوجد عاصب أقرب منه."),
    ("full_uncle", 90, "العم الشقيق", "الأعمام الأشقاء", "العم الشقيق/الأعمام الأشقاء يأخذ الباقي تعصيبًا بعد أصحاب الفروض إذا لم يوجد عاصب أقرب منه."),
    ("paternal_uncle", 100, "العم لأب", "الأعمام لأب", "العم لأب/الأعمام لأب يأخذ الباقي تعصيبًا إذا لم يوجد عاصب أقرب منه."),
    ("uncle", 105, "العم", "الأعمام", "العم/الأعمام من العصبات بالنفس؛ يأخذون الباقي بعد أصحاب الفروض إذا لم يوجد عاصب أقرب منهم."),
    ("full_cousin", 110, "ابن العم الشقيق", "أبناء العم الشقيق", "ابن العم الشقيق/أبناء العم الشقيق يأخذ الباقي تعصيبًا إذا لم يوجد عاصب أقرب منه."),
    ("paternal_cousin", 120, "ابن العم لأب", "أبناء العم لأب", "ابن العم لأب/أبناء العم لأب يأخذ الباقي تعصيبًا إذا لم يوجد عاصب أقرب منه."),
    ("cousin", 125, "ابن العم", "أبناء العم", "ابن العم/أبناء العم من العصبات بالنفس؛ يأخذون الباقي إذا لم يوجد عاصب أقرب منهم."),
]
EXT_AGNATE_INFO = {k: (rank, singular, plural, reason) for k, rank, singular, plural, reason in EXT_AGNATE_ORDER}


def _num_before(text: str, start: int):
    """Read explicit count only when it is directly attached to this heir phrase.

    Avoid stealing numbers from previous heirs, e.g. "3 بنات وأم وعم" must not make العم = 3.
    """
    before = text[:start].strip().split()
    if not before:
        return None
    # Direct previous token only, or previous token after a standalone conjunction.
    candidates = []
    if before:
        candidates.append(before[-1])
    if before and before[-1] in {"و", "ثم"} and len(before) >= 2:
        candidates.append(before[-2])
    for tok in candidates:
        variants = [tok]
        if tok.startswith("و") and len(tok) > 1:
            variants.append(tok[1:])
        for v in variants:
            try:
                n = v8.ar_num_to_int(v)
            except Exception:
                n = None
            if n is not None:
                return n
    return None


def _phrase_count(phrase: str, default: int = 1) -> int:
    p = _n(phrase)
    if any(x in p for x in ["عمين", "عمان", "اثنين", "اتنين", "ابنين", "ابنان"]):
        return 2
    if any(x in p for x in ["ثلاث", "تلات"]):
        return 3
    if any(x in p for x in ["اعمام", "ابناء", "اولاد"]):
        return 2
    return default


def _detect_extended_agnates(q: str):
    """Return (found, masked_question) for agnatic heirs not natively handled by v8.

    masked_question removes phrases like "ابن عم" before v8 extraction so they are not mistaken for "ابن".
    """
    t = _n(q)
    found = {}
    consumed = []

    # Specific patterns first; consumed spans prevent "ابن عم" from also becoming "عم".
    # Allow attached Arabic conjunction waw: وعم، وابن عم، وأعمام...
    patterns = [
        ("full_nephew", [r"(?:و)?ابن الاخ الشقيق", r"(?:و)?ابن اخ شقيق", r"(?:و)?ابناء الاخ الشقيق", r"(?:و)?ابناء اخ شقيق", r"(?:و)?اولاد الاخ الشقيق", r"(?:و)?اولاد اخ شقيق", r"(?:و)?ولد الاخ الشقيق", r"(?:و)?ولد اخ شقيق"]),
        ("paternal_nephew", [r"(?:و)?ابن الاخ لاب", r"(?:و)?ابن اخ لاب", r"(?:و)?ابناء الاخ لاب", r"(?:و)?ابناء اخ لاب", r"(?:و)?اولاد الاخ لاب", r"(?:و)?اولاد اخ لاب", r"(?:و)?ولد الاخ لاب", r"(?:و)?ولد اخ لاب", r"(?:و)?ابن الاخ من الاب"]),
        ("full_uncle", [r"(?:و)?العم الشقيق", r"(?:و)?عم شقيق", r"(?:و)?اعمام اشقاء", r"(?:و)?اعمام شقيق"]),
        ("paternal_uncle", [r"(?:و)?العم لاب", r"(?:و)?عم لاب", r"(?:و)?اعمام لاب", r"(?:و)?عم من الاب", r"(?:و)?العم من الاب"]),
        ("full_cousin", [r"(?:و)?ابن العم الشقيق", r"(?:و)?ابناء العم الشقيق", r"(?:و)?اولاد العم الشقيق", r"(?:و)?ولد العم الشقيق"]),
        ("paternal_cousin", [r"(?:و)?ابن العم لاب", r"(?:و)?ابناء العم لاب", r"(?:و)?اولاد العم لاب", r"(?:و)?ابن العم من الاب"]),
        ("cousin", [r"(?:و)?ابن عم", r"(?:و)?ابن العم", r"(?:و)?ابناء عم", r"(?:و)?ابناء العم", r"(?:و)?اولاد عم", r"(?:و)?اولاد العم"]),
        ("uncle", [r"(?:و)?عمين", r"(?:و)?عمان", r"(?:و)?اعمام", r"(?:و)?العم", r"(?:و)?عم", r"(?:و)?عمه"]),
    ]
    for kind, pats in patterns:
        for pat in pats:
            for m in re.finditer(r"(?<![\wء-ي])" + pat + r"(?![\wء-ي])", t):
                if any(not (m.end() <= a or m.start() >= b) for a, b in consumed):
                    continue
                phrase = m.group(0)
                # Do not treat feminine relatives as agnatic male heirs.
                if _n(phrase) in {"عمه", "وعمه"}:
                    # "عمه" in common Arabic often means his uncle; keep it. "عمة" is not normalized to عمه.
                    pass
                cnt = _num_before(t, m.start()) or _phrase_count(phrase)
                found[kind] = found.get(kind, 0) + cnt
                consumed.append((m.start(), m.end()))
    # Mask consumed spans so v8 does not read "ابن عم" as "ابن" or "ابن أخ" as a direct son.
    chars = list(t)
    for a, b in consumed:
        for i in range(a, b):
            chars[i] = " "
    masked = re.sub(r"\s+", " ", "".join(chars)).strip()
    return found, masked


def _closest_extended_agnate(found: dict):
    if not found:
        return None
    kinds = sorted(found.keys(), key=lambda k: EXT_AGNATE_INFO[k][0])
    return kinds[0]


def _native_closer_residuary_exists(h) -> str | None:
    """Return reason if a closer native residuary blocks extended agnates."""
    if h.son or h.grandson:
        return "محجوب بفرع وارث ذكر أقرب منه."
    if h.father:
        return "محجوب بالأب لأنه أقرب منه في العصوبة."
    if h.grandfather:
        return "ظهر جد مع عصبة أبعد، وهذه صورة تحتاج ضبط طريقة معاملة الجد قبل الحساب."
    if h.full_brother:
        return "محجوب بالأخ الشقيق لأنه أقرب منه في جهة العصوبة."
    if h.paternal_brother:
        return "محجوب بالأخ لأب لأنه أقرب منه في جهة العصوبة."
    if (h.daughter or h.granddaughter) and h.full_sister:
        return "محجوب بالأخت الشقيقة إذا صارت عصبة مع الغير لوجود فرع وارث أنثى."
    if (h.daughter or h.granddaughter) and h.paternal_sister and not h.full_sister:
        return "محجوب بالأخت لأب إذا صارت عصبة مع الغير لوجود فرع وارث أنثى."
    return None


def _name_for_kind(kind: str, count: int) -> str:
    rank, singular, plural, reason = EXT_AGNATE_INFO[kind]
    return singular if count == 1 else plural


def _blocked_note_for_kind(kind: str, count: int, reason: str) -> str:
    name = _name_for_kind(kind, count)
    return f"{name} لا يأخذ شيئًا هنا؛ لأنه {reason}"


def _surrogate_phrase(count: int) -> str:
    # spaces around number are intentional so v8 count parser reads it.
    return f" و {count} أخ لأب"


def _replace_surrogate_output(out: str, kind: str, count: int, lower_blocked: list[str] | None = None) -> str:
    rank, singular, plural, reason = EXT_AGNATE_INFO[kind]
    label = singular if count == 1 else plural
    # Replace reason while the surrogate names are still present.
    out = re.sub(r"السبب:\s*[^\n]*(?:الأخ لأب|الإخوة لأب)[^\n]*", f"السبب: {reason}", out)
    # label replacement
    out = out.replace("الإخوة لأب", label)
    out = out.replace("الأخ لأب", label)
    out = out.replace("الأخت لأب", label)
    out = out.replace("الأخوات لأب", label)
    out = out.replace("محجوبون", "محجوب") if count == 1 else out
    # If the surrogate did not appear because no residue remained, append clear note.
    nout = _n(out)
    if _n(label) not in nout:
        out += f"\n\nتنبيه: {label} من العصبات، لكن لم يبق له شيء بعد الفروض في هذه الصورة."
    if lower_blocked:
        out += "\n\nحجب العصبات الأبعد:\n" + "\n".join(f"- {x}" for x in lower_blocked)
    return out


def _answer_with_extended_agnates(original_question: str, preprocessed_question: str, found: dict) -> str | None:
    if not found:
        return None
    h = v8.extract_heirs(preprocessed_question)
    # If a native closer residuary exists, calculate normally and append safe blocked note.
    closer_reason = _native_closer_residuary_exists(h)
    if closer_reason:
        # grandfather cases are safer as explicit advanced stop because v8 does not fully model all grandfather paths.
        if h.grandfather:
            return _advanced_stop(original_question, "ظهر جد مع عصبة أبعد، وهذا يحتاج تحديد طريقة معاملة الجد قبل الحساب.")
        out = v8.answer(preprocessed_question)
        out = _replace_header(out, original_question)
        notes = [_blocked_note_for_kind(k, c, closer_reason) for k, c in sorted(found.items(), key=lambda x: EXT_AGNATE_INFO[x[0]][0])]
        return out + "\n\nحجب العصبات الأبعد:\n" + "\n".join(f"- {n}" for n in notes)

    chosen = _closest_extended_agnate(found)
    if not chosen:
        return None
    chosen_rank = EXT_AGNATE_INFO[chosen][0]
    chosen_count = found[chosen]
    lower = []
    for k, c in sorted(found.items(), key=lambda x: EXT_AGNATE_INFO[x[0]][0]):
        if k == chosen:
            continue
        if EXT_AGNATE_INFO[k][0] > chosen_rank:
            lower.append(_blocked_note_for_kind(k, c, f"محجوب بـ{_name_for_kind(chosen, chosen_count)} لأنه أقرب منه في جهة العصوبة."))
    q_calc = preprocessed_question + _surrogate_phrase(chosen_count)
    out = v8.answer(q_calc)
    out = _replace_header(out, original_question)
    return _replace_surrogate_output(out, chosen, chosen_count, lower)


def early_ambiguity(q: str):
    n = _n(q)
    if detect_concept_key(q) and any(x in n for x in ["ما هو", "ما هي", "ما معنى", "معنى", "معني", "يعني", "اشرح", "شنو يعني", "وش معنى", "متى", "كم عدد"]):
        return None
    if any(x in n for x in ["فرق بين", "الفرق بين", "انواع", "اشرح"]):
        return None
    if n.strip() == "مات شخص":
        return _safe_clarification(q)
    if "جد" in n and ("اخ" in n or "اخت" in n):
        return _advanced_stop(q, "ظهر في المسألة جد مع إخوة، وهذا باب له تفصيل وخلاف بين طرق الفرضيين. حدّد المذهب أو الطريقة القضائية المعتمدة قبل الحساب.")
    if any(x in n for x in ["ذرية", "اولاد وبنات", "عنده اولاد", "عنده عيال", "زوجة وعيال", "زوجها واولاد"]):
        return _safe_clarification(q, "ورد لفظ عام مثل أولاد/عيال/ذرية. اذكر عدد الذكور وعدد الإناث: كم ابنًا وكم بنتًا؟")
    if any(x in n for x in ["اخوها", "اخته", "اخوات", "اخوته", "اخوة", "اخوة من غير تحديد", "اخوان", "اخوه"]):
        if not any(y in n for y in ["شقيق", "لاب", "لام", "من الاب", "من الام"]):
            if "اب" not in n:
                return _safe_clarification(q, "ورد أخ/إخوة بدون تحديد الجهة. هل هو شقيق، أم لأب، أم لأم؟")
    if any(x in n for x in ["ورثة كتير", "احسب الميراث", "تقسيم ميراث لاهلي", "اهلي", "ناس كتير", "ورثة ناقصين", "واحد مات وترك ورثة"]):
        return _safe_clarification(q)
    if "زوجات" in n and not any(x in n for x in ["ابن", "بنت", "اب", "ام", "اخ", "اخت"]):
        return _safe_clarification(q)
    if "احفاد" in n or "بنات اولاده" in n:
        return _safe_clarification(q, "ورد أحفاد/بنات أولاد بلفظ عام. حدّد: ابن ابن، بنت ابن، وعدد كل وارث.")
    return None



# -----------------------------
# Monetary estate value layer
# -----------------------------
# هذه الطبقة لا تغيّر حكم الميراث ولا تضيف ردًا محفوظًا لمسألة بعينها.
# وظيفتها فقط: إذا ذكر المستخدم قيمة التركة وعملتها، تضرب الأنصبة المحسوبة في القيمة النقدية.
# الحساب الشرعي يبقى من محرك الفرائض، وهذه الطبقة تضيف المبالغ فقط.

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

_CURRENCY_PATTERNS = [
    r"ريال\s*سعودي", r"ر\.\s*س", r"ريال", r"SAR",
    r"جنيه\s*مصري", r"ج\.\s*م", r"جنيه", r"EGP",
    r"دولار\s*امريكي", r"دولار", r"USD", r"\$",
    r"درهم\s*اماراتي", r"درهم", r"AED",
    r"دينار\s*كويتي", r"دينار\s*بحريني", r"دينار\s*اردني", r"دينار", r"KWD", r"BHD", r"JOD",
    r"يورو", r"EUR", r"€",
    r"ريال\s*قطري", r"ريال\s*عماني", r"QAR", r"OMR",
    r"ليرة", r"ليره", r"TRY", r"جنيه\s*استرليني", r"GBP", r"£",
    r"درهم\s*مغربي", r"MAD", r"جنيه\s*سوداني", r"SDG",
    r"فرنك\s*سويسري", r"فرنك", r"CHF", r"روبية", r"روبيه", r"INR", r"PKR",
    r"شيكل", r"ILS", r"يوان", r"CNY", r"ين", r"JPY", r"روبل", r"RUB",
    r"كرونة", r"كرونا", r"NOK", r"SEK", r"DKK", r"بيزو", r"MXN",
]
_CURRENCY_RE = r"(?P<currency>" + r"|".join(_CURRENCY_PATTERNS) + r")"
_SCALE_WORDS = {
    "الف": Decimal("1000"), "ألف": Decimal("1000"), "آلاف": Decimal("1000"), "الاف": Decimal("1000"),
    "مليون": Decimal("1000000"), "ملايين": Decimal("1000000"),
    "مليار": Decimal("1000000000"), "بليون": Decimal("1000000000"),
}
_BAD_GENERIC_CURRENCY_WORDS = {
    "بنات", "بنت", "ابن", "ابناء", "ام", "اب", "زوج", "زوجة", "اخ", "اخت", "اخوة", "اخوات",
    "عم", "اعمام", "جد", "جدة", "ورثة", "وارث", "وارثة", "ريال؟", "؟"
}
_WORD_NUMBERS = {
    "واحد": Decimal(1), "واحدة": Decimal(1), "احد": Decimal(1), "إحدى": Decimal(1), "احدى": Decimal(1),
    "اثنين": Decimal(2), "اتنين": Decimal(2), "اثنتين": Decimal(2), "ثلاث": Decimal(3), "ثلاثة": Decimal(3), "تلات": Decimal(3), "تلاتة": Decimal(3),
    "اربع": Decimal(4), "أربع": Decimal(4), "اربعة": Decimal(4), "أربعة": Decimal(4), "خمس": Decimal(5), "خمسة": Decimal(5),
    "ست": Decimal(6), "ستة": Decimal(6), "سبع": Decimal(7), "سبعة": Decimal(7), "ثمان": Decimal(8), "ثمانية": Decimal(8),
    "تسع": Decimal(9), "تسعة": Decimal(9), "عشر": Decimal(10), "عشرة": Decimal(10),
    "مئة": Decimal(100), "مائه": Decimal(100), "مائة": Decimal(100), "مية": Decimal(100), "ميه": Decimal(100),
    "نصف": Decimal("0.5"),
}


def _to_latin_digits(text: str) -> str:
    return (text or "").translate(_AR_DIGITS)


def _parse_decimal_token(raw: str) -> Decimal | None:
    if not raw:
        return None
    s = _to_latin_digits(raw).strip()
    # Remove thousands separators and Arabic comma. Preserve decimal point.
    s = s.replace(",", "").replace("٬", "").replace(" ", "")
    s = s.replace("٫", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _normalize_currency_label(cur: str) -> str:
    c = (cur or "").strip()
    if not c:
        return "وحدة نقدية"
    nc = _n(c)
    if nc in {"ر س", "sar", "ريال", "ريال سعودي"}:
        return "ريال"
    if nc in {"ج م", "egp", "جنيه", "جنيه مصري"}:
        return "جنيه"
    if nc in {"usd", "دولار", "$", "دولار امريكي"}:
        return "دولار"
    if nc in {"aed", "درهم", "درهم اماراتي"}:
        return "درهم"
    if nc in {"eur", "يورو", "€"}:
        return "يورو"
    return c


def _extract_money_amount(question: str) -> tuple[Decimal, str] | None:
    """Extract estate amount + currency only when clearly money, not heir counts."""
    q = _to_latin_digits(question or "")
    # 1) numeric + optional scale + known currency. This avoids confusing "3 بنات" with money.
    num = r"(?P<num>\d+(?:[\s,٬]\d{3})*(?:[\.٫]\d+)?|\d+(?:[\.٫]\d+)?)"
    scale = r"(?P<scale>الف|ألف|آلاف|الاف|مليون|ملايين|مليار|بليون)?"
    pat1 = re.compile(num + r"\s*" + scale + r"\s*" + _CURRENCY_RE, re.IGNORECASE)
    matches = list(pat1.finditer(q))
    if matches:
        m = matches[-1]
        amount = _parse_decimal_token(m.group("num"))
        if amount is not None:
            sc = m.group("scale")
            if sc:
                amount *= _SCALE_WORDS.get(sc, Decimal(1))
            return amount, _normalize_currency_label(m.group("currency"))

    # 2) known currency + numeric, e.g. ريال 100000
    pat2 = re.compile(_CURRENCY_RE + r"\s*" + num + r"\s*" + scale, re.IGNORECASE)
    matches = list(pat2.finditer(q))
    if matches:
        m = matches[-1]
        amount = _parse_decimal_token(m.group("num"))
        if amount is not None:
            sc = m.group("scale")
            if sc:
                amount *= _SCALE_WORDS.get(sc, Decimal(1))
            return amount, _normalize_currency_label(m.group("currency"))

    # 3) word number + scale + currency: مائة ألف ريال، نصف مليون جنيه، ثلاثة ملايين دولار
    word_group = r"(?P<word>" + "|".join(sorted(map(re.escape, _WORD_NUMBERS.keys()), key=len, reverse=True)) + r")"
    scale_words = r"(?P<scale_word>" + "|".join(sorted(map(re.escape, _SCALE_WORDS.keys()), key=len, reverse=True)) + r")"
    pat3 = re.compile(word_group + r"\s+" + scale_words + r"\s*" + _CURRENCY_RE, re.IGNORECASE)
    matches = list(pat3.finditer(q))
    if matches:
        m = matches[-1]
        amount = _WORD_NUMBERS.get(m.group("word"), Decimal(0)) * _SCALE_WORDS.get(m.group("scale_word"), Decimal(1))
        return amount, _normalize_currency_label(m.group("currency"))

    # 4) generic currency label after money context, e.g. "مبلغ 100000 فرنك محلي".
    # Kept after known currencies to avoid over-detecting heir counts like "3 بنات".
    pat_generic = re.compile(
        r"(?:مبلغ|قيمتها|قيمة\s+التركة|التركة|ترك\s+مبلغ|مال\s+قدره)\s*[:：]?\s*"
        + num + r"\s*" + scale + r"\s*(?P<generic_currency>[A-Za-zء-ي]{2,}(?:\s+[A-Za-zء-ي]{2,}){0,2})",
        re.IGNORECASE,
    )
    matches = list(pat_generic.finditer(q))
    if matches:
        m = matches[-1]
        amount = _parse_decimal_token(m.group("num"))
        if amount is not None:
            sc = m.group("scale")
            if sc:
                amount *= _SCALE_WORDS.get(sc, Decimal(1))
            cur = (m.group("generic_currency") or "").strip().split()[0]
            if _n(cur) not in _BAD_GENERIC_CURRENCY_WORDS:
                return amount, _normalize_currency_label(cur)

    # 5) amount without currency only if it is explicitly called تركة/مبلغ/مال/قيمتها.
    pat4 = re.compile(r"(?:مبلغ|قيمتها|قيمة\s+التركة|التركة|ترك\s+مبلغ|مال\s+قدره)\s*[:：]?\s*" + num + r"\s*" + scale, re.IGNORECASE)
    matches = list(pat4.finditer(q))
    if matches:
        m = matches[-1]
        amount = _parse_decimal_token(m.group("num"))
        if amount is not None:
            sc = m.group("scale")
            if sc:
                amount *= _SCALE_WORDS.get(sc, Decimal(1))
            return amount, "وحدة نقدية"
    return None


def _fraction_to_decimal(frac: str) -> Decimal | None:
    try:
        f = Fraction(frac.strip())
        return Decimal(f.numerator) / Decimal(f.denominator)
    except Exception:
        return None


def _format_money(value: Decimal, currency: str) -> str:
    q = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    # If whole number, omit .00 for cleaner public output.
    if q == q.to_integral_value():
        s = f"{int(q):,}"
    else:
        s = f"{q:,.2f}"
    return f"{s} {currency}"


def _extract_share_entries(answer_text: str):
    entries = []
    current = None
    bullet_re = re.compile(r"^\s*-\s*(?P<label>[^:\n]+):\s*(?P<frac>\d+\s*/\s*\d+)\s+من\s+التركة", re.MULTILINE)
    individual_re = re.compile(r"نصيب\s+الفرد\s+الواحد:\s*(?P<frac>\d+\s*/\s*\d+)\s+من\s+التركة")
    lines = answer_text.splitlines()
    for line in lines:
        m = re.match(r"\s*-\s*(?P<label>[^:\n]+):\s*(?P<frac>\d+\s*/\s*\d+)\s+من\s+التركة", line)
        if m:
            current = {"label": m.group("label").strip(), "frac": m.group("frac").replace(" ", ""), "individual": None}
            entries.append(current)
            continue
        if current:
            im = individual_re.search(line)
            if im:
                current["individual"] = im.group("frac").replace(" ", "")
    return entries


def _append_monetary_distribution(answer_text: str, question: str) -> str:
    money = _extract_money_amount(question)
    if not money:
        return answer_text
    amount, currency = money
    if amount <= 0:
        return answer_text
    if "من التركة" not in answer_text:
        return answer_text
    entries = _extract_share_entries(answer_text)
    if not entries:
        return answer_text
    lines = ["", "القسمة النقدية حسب قيمة التركة المذكورة:", f"- إجمالي التركة: {_format_money(amount, currency)}"]
    for e in entries:
        dec = _fraction_to_decimal(e["frac"])
        if dec is None:
            continue
        share_value = amount * dec
        lines.append(f"- {e['label']}: {_format_money(share_value, currency)}")
        if e.get("individual"):
            idec = _fraction_to_decimal(e["individual"])
            if idec is not None:
                lines.append(f"  نصيب الفرد الواحد: {_format_money(amount * idec, currency)}")
    lines.append("تنبيه: قد تظهر فروق بسيطة جدًا بسبب تقريب الكسور النقدية إلى منزلتين عشريتين.")
    return answer_text.rstrip() + "\n" + "\n".join(lines)

def answer(question: str, context: dict | None = None) -> str:
    if context and is_followup(question):
        ca = answer_concept(question, _dialect(context.get("last_question") or question), context=context)
        if ca:
            return ca
    amb = early_ambiguity(question)
    if amb:
        return amb

    route = fiqh_route(question)
    if route:
        kind, payload = route
        if kind == "concept":
            ca = answer_concept(question, _dialect(question), context=context)
            if ca:
                return ca
        if kind == "canonical":
            ca = answer_concept(payload, _dialect(question), context=context)
            return ca or v8.answer(payload)
        if kind == "fixed_shares":
            ca = answer_concept("الفروض المقدرة", _dialect(question), context=context)
            return ca or _fixed_shares_answer(question)
        if kind == "mawani":
            return v8.answer("ما موانع الإرث؟") + "\n\nتنبيه: إذا كان السؤال عن حالة بعينها فهذا مانع محتمل، ولا بد من تحقق الواقعة قبل الحكم."
        if kind == "advanced":
            return _advanced_stop(question, payload)

    q2 = preprocess_question(question)
    ext_agnates, q2_masked = _detect_extended_agnates(q2)
    if ext_agnates:
        ext_out = _answer_with_extended_agnates(question, q2_masked, ext_agnates)
        if ext_out:
            return _append_monetary_distribution(ext_out, question)
    out = v8.answer(q2)
    out = _replace_header(out, question)
    nout = _n(out)
    nq = _n(question)
    if ("اكتب السؤال بصيغة اوضح" in nout) and any(w in nq for w in ["ورثة", "ناس كتير", "اهلي", "قسيم ميراث", "تقسيم ميراث"]):
        return _safe_clarification(question)
    if "ما يصح" in out and "بالتخمين" in out and "لا يصح" not in out:
        out += "\n\nتنبيه: لا يصح حسابها بالتخمين."
    return _append_monetary_distribution(out, question)


# ==========================================================
# HARDENING V7: Net Estate + Multi Asset + Text Money Layer
# ==========================================================
# هذه الطبقة تعيد تعريف دالة _append_monetary_distribution فقط.
# لا تغير محرك الفرائض ولا تثبت إجابات مسائل بعينها.
# الهدف: استخراج إجمالي المال/الأصول والديون/الوصايا/التجهيز، ثم توزيع الصافي على الأنصبة المحسوبة.

_TENS_WORDS_V7 = {
    "عشرون": Decimal(20), "عشرين": Decimal(20), "تلاتين": Decimal(30), "ثلاثين": Decimal(30),
    "اربعين": Decimal(40), "أربعين": Decimal(40), "خمسين": Decimal(50), "ستين": Decimal(60),
    "سبعين": Decimal(70), "ثمانين": Decimal(80), "تسعين": Decimal(90),
}
_ONES_WORDS_V7 = dict(_WORD_NUMBERS)
_ONES_WORDS_V7.update({"مايه": Decimal(100), "ماية": Decimal(100), "ماة": Decimal(100)})

_ONES_WORDS_V7.update({
    "اثنا": Decimal(2), "اثني": Decimal(2), "اثنتا": Decimal(2), "اثنتي": Decimal(2),
    "الفين": Decimal(2000), "ألفين": Decimal(2000), "مليونين": Decimal(2000000), "مليونان": Decimal(2000000),
    "مليوني": Decimal(2000000), "مليارين": Decimal(2000000000),
    "نص": Decimal("0.5"), "نصف": Decimal("0.5"),
})

_ASSET_CONTEXT_V7 = [
    "ترك", "تركت", "ساب", "خلف", "خلّف", "التركة", "تركه", "تاركا", "مبلغ", "مال", "اموال",
    "رصيد", "حساب", "محفظة", "قيمة", "قيمتها", "يساوي", "تساوي", "بيت", "منزل", "شقة", "شقه",
    "ارض", "أرض", "عقار", "سيارة", "سياره", "ذهب", "اسهم", "أسهم", "عملة", "عملات"
]
_DEBT_CONTEXT_V7 = ["دين", "ديون", "مديون", "قرض", "قروض", "عليه", "عليها", "مستحق", "سلفة", "سلفه", "مطالبة", "مطالبات"]
_WILL_CONTEXT_V7 = ["وصية", "وصيه", "اوصى", "أوصى", "اوصت", "أوصت", "موصي", "موصى"]
_EXPENSE_CONTEXT_V7 = ["تجهيز", "دفن", "كفن", "جنازة", "جنازه", "مصاريف", "تكاليف", "غسل", "قبر"]
_RIGHT_CONTEXT_V7 = ["رهن", "مرهون", "حق متعلق", "حقوق متعلقة", "عين التركة", "عين التركه"]
_DEDUCTION_CONTEXT_V7 = _DEBT_CONTEXT_V7 + _WILL_CONTEXT_V7 + _EXPENSE_CONTEXT_V7 + _RIGHT_CONTEXT_V7

_CURRENCY_EXTRA_V7 = {
    "سعودي": "ريال", "ر س": "ريال", "ر.س": "ريال", "ريالات": "ريال",
    "مصري": "جنيه", "جنيهات": "جنيه", "ج.م": "جنيه",
    "اماراتي": "درهم", "إماراتي": "درهم", "دراهم": "درهم",
    "كويتي": "دينار", "اردني": "دينار", "أردني": "دينار", "بحريني": "دينار", "دنانير": "دينار",
    "سترليني": "جنيه استرليني", "استرليني": "جنيه استرليني",
    "ليرة": "ليرة", "ليره": "ليرة", "ليرات": "ليرة",
    "يورو": "يورو", "دولار": "دولار", "دولارات": "دولار",
}

def _normalize_currency_label_v7(cur: str | None, fallback: str | None = None) -> str:
    if not cur:
        return fallback or "وحدة نقدية"
    c = (cur or "").strip().strip(".،,:؛")
    nc = _n(c)
    base = _normalize_currency_label(c)
    if base != c or nc in {"sar", "egp", "usd", "eur", "aed"}:
        return base
    if nc in _CURRENCY_EXTRA_V7:
        return _CURRENCY_EXTRA_V7[nc]
    if nc in _BAD_GENERIC_CURRENCY_WORDS:
        return fallback or "وحدة نقدية"
    return c

_NUMERIC_TOKEN_V7 = r"\d+(?:[\s,٬]\d{3})*(?:[\.٫]\d+)?|\d+(?:[\.٫]\d+)?|\d+(?:[kKmM])"
_CURRENCY_WORD_RE_V7 = r"(?<![\wء-ي])(?:" + r"|".join(_CURRENCY_PATTERNS + [r"سعودي", r"مصري", r"اماراتي", r"إماراتي", r"كويتي", r"اردني", r"بحريني", r"استرليني", r"ريالات", r"جنيهات", r"دراهم", r"دولارات", r"دنانير"]) + r")(?![\wء-ي])"


def _parse_numeric_token_v7(raw: str) -> Decimal | None:
    if not raw:
        return None
    s = _to_latin_digits(raw).strip()
    mult = Decimal(1)
    if s[-1:].lower() == "k":
        mult = Decimal(1000); s = s[:-1]
    elif s[-1:].lower() == "m":
        mult = Decimal(1000000); s = s[:-1]
    # If comma between 1 and 2 digits at end, it may be decimal comma; otherwise thousands.
    s = s.replace("٬", ",").replace("٫", ".")
    if "," in s and "." not in s:
        parts = s.split(",")
        if len(parts[-1]) in (1,2) and len(parts) == 2 and len(parts[0]) <= 3:
            s = parts[0] + "." + parts[1]
        else:
            s = "".join(parts)
    else:
        s = s.replace(",", "")
    s = s.replace(" ", "")
    try:
        return Decimal(s) * mult
    except InvalidOperation:
        return None


def _parse_word_number_v7(text: str) -> Decimal | None:
    """Parse common Arabic/Egyptian amount words used with money. Not a full NLP number parser."""
    if not text:
        return None
    t = _n(text).replace(" و ", " ").replace("ونص", " ونص").strip()
    t = re.sub(r"\s+", " ", t)
    # million and half forms
    if re.search(r"نص\s+مليون|نصف\s+مليون", t):
        return Decimal("500000")
    if re.search(r"مليون\s+(?:و)?\s*(?:نص|نصف)", t):
        return Decimal("1500000")
    if re.search(r"مليار\s+(?:و)?\s*(?:نص|نصف)", t):
        return Decimal("1500000000")
    if t in {"مليون", "مليون واحد"}:
        return Decimal(1000000)
    if t in {"مليار", "مليار واحد"}:
        return Decimal(1000000000)
    if t in {"الف", "ألف", "الاف", "آلاف"}:
        return Decimal(1000)
    if t in {"الفين", "ألفين"}:
        return Decimal(2000)
    if t in {"مليونين", "مليونان"}:
        return Decimal(2000000)
    # "مية الف", "مائة ألف", "خمسين الف", "ثلاثة ملايين"
    toks = t.split()
    total = Decimal(0)
    # direct: [number] [scale]
    if len(toks) >= 2:
        first = toks[0]
        second = toks[1]
        n = _ONES_WORDS_V7.get(first) or _TENS_WORDS_V7.get(first)
        if n is not None and second in _SCALE_WORDS:
            return n * _SCALE_WORDS[second]
        if first in {"مئة", "مائه", "مائة", "مية", "ميه"} and second in {"الف", "ألف", "الاف", "آلاف"}:
            return Decimal(100000)
        if second in {"مليون", "ملايين"} and n is not None:
            return n * Decimal(1000000)
        if second in {"مليار", "بليون"} and n is not None:
            return n * Decimal(1000000000)
    # compound up to 999 then scale: "مئة وخمسين الف" normalized into tokens
    number = Decimal(0)
    scale_val = None
    for tok in toks:
        if tok in _SCALE_WORDS:
            scale_val = _SCALE_WORDS[tok]
            break
        if tok in _ONES_WORDS_V7:
            number += _ONES_WORDS_V7[tok]
        elif tok in _TENS_WORDS_V7:
            number += _TENS_WORDS_V7[tok]
    if number > 0 and scale_val:
        return number * scale_val
    return None


def _context_category_v7(window_norm: str) -> str:
    if any(x in window_norm for x in _WILL_CONTEXT_V7):
        return "will"
    if any(x in window_norm for x in _EXPENSE_CONTEXT_V7):
        return "expense"
    if any(x in window_norm for x in _RIGHT_CONTEXT_V7):
        return "right"
    if any(x in window_norm for x in _DEBT_CONTEXT_V7):
        return "debt"
    return "asset"


def _add_mention_v7(items, text, start, end, amount, currency, category, raw):
    if amount is None or amount <= 0:
        return
    # avoid duplicate overlapping matches
    for it in items:
        if not (end <= it["start"] or start >= it["end"]):
            # keep the one with currency over generic/no currency
            if it.get("currency") == "وحدة نقدية" and currency != "وحدة نقدية":
                it.update({"amount": amount, "currency": currency, "category": category, "raw": raw, "start": start, "end": end})
            return
    items.append({"start": start, "end": end, "amount": amount, "currency": currency, "category": category, "raw": raw})


def _extract_financial_mentions_v7(question: str):
    q = _to_latin_digits(question or "")
    q_norm = _n(q)
    mentions = []
    # Numeric + optional scale + currency
    scale = r"(?P<scale>الف|ألف|آلاف|الاف|مليون|ملايين|مليار|بليون)?"
    pat_num_cur = re.compile(r"(?P<num>" + _NUMERIC_TOKEN_V7 + r")\s*" + scale + r"\s*(?P<cur>" + _CURRENCY_WORD_RE_V7 + r")", re.IGNORECASE)
    for m in pat_num_cur.finditer(q):
        amount = _parse_numeric_token_v7(m.group("num"))
        if amount is None: continue
        sc = m.group("scale")
        if sc: amount *= _SCALE_WORDS.get(sc, Decimal(1))
        a,b = m.span()
        win = _n(q[max(0,a-70):b])
        _add_mention_v7(mentions, q, a,b,amount,_normalize_currency_label_v7(m.group("cur")),_context_category_v7(win),m.group(0))
    # Currency + numeric
    pat_cur_num = re.compile(r"(?P<cur>" + _CURRENCY_WORD_RE_V7 + r")\s*(?P<num>" + _NUMERIC_TOKEN_V7 + r")\s*" + scale, re.IGNORECASE)
    for m in pat_cur_num.finditer(q):
        amount = _parse_numeric_token_v7(m.group("num"))
        if amount is None: continue
        sc = m.group("scale")
        if sc: amount *= _SCALE_WORDS.get(sc, Decimal(1))
        a,b = m.span(); win = _n(q[max(0,a-70):b])
        _add_mention_v7(mentions, q, a,b,amount,_normalize_currency_label_v7(m.group("cur")),_context_category_v7(win),m.group(0))
    # Word amount + currency; allow 1-5 words before currency.
    word_amount_pat = r"(?P<words>(?:(?:نصف|نص|مليون(?:ين|ان)?|مليار(?:ين)?|الفين|ألفين|الف|ألف|الاف|آلاف|مئة|مائه|مائة|مية|ميه|واحد|واحدة|اثنين|اتنين|اثنتين|ثلاثة|ثلاث|تلاتة|تلات|اربعة|أربعة|اربع|أربع|خمسة|خمس|ستة|ست|سبعة|سبع|ثمانية|ثمان|تسعة|تسع|عشرة|عشر|عشرين|عشرون|ثلاثين|تلاتين|اربعين|أربعين|خمسين|ستين|سبعين|ثمانين|تسعين|و)\s*){1,7})"
    pat_words_cur = re.compile(word_amount_pat + r"\s*(?P<cur>" + _CURRENCY_WORD_RE_V7 + r")", re.IGNORECASE)
    for m in pat_words_cur.finditer(q):
        amount = _parse_word_number_v7(m.group("words"))
        if amount is None: continue
        a,b = m.span(); win = _n(q[max(0,a-70):b])
        _add_mention_v7(mentions, q, a,b,amount,_normalize_currency_label_v7(m.group("cur")),_context_category_v7(win),m.group(0))
    # Context + numeric/word without currency, to be resolved later if one asset currency exists.
    ctx_words = r"(?:مبلغ|قيمتها|قيمة\s+التركة|التركة|ترك\s+مبلغ|مال\s+قدره|دين|ديون|عليه|عليها|وصية|وصيه|مصاريف|تجهيز|دفن|رهن)"
    pat_ctx_num = re.compile(ctx_words + r"\s*[:：]?\s*(?P<num>" + _NUMERIC_TOKEN_V7 + r")\s*" + scale, re.IGNORECASE)
    for m in pat_ctx_num.finditer(q):
        amount = _parse_numeric_token_v7(m.group("num"))
        if amount is None: continue
        sc = m.group("scale")
        if sc: amount *= _SCALE_WORDS.get(sc, Decimal(1))
        a,b=m.span(); win=_n(q[max(0,a-70):b])
        _add_mention_v7(mentions,q,a,b,amount,"وحدة نقدية",_context_category_v7(win),m.group(0))
    pat_ctx_words = re.compile(ctx_words + r"\s*[:：]?\s*" + word_amount_pat, re.IGNORECASE)
    for m in pat_ctx_words.finditer(q):
        amount = _parse_word_number_v7(m.group("words"))
        if amount is None: continue
        a,b=m.span(); win=_n(q[max(0,a-70):b])
        _add_mention_v7(mentions,q,a,b,amount,"وحدة نقدية",_context_category_v7(win),m.group(0))
    # Resolve generic currency when possible.
    asset_curs = {x["currency"] for x in mentions if x["category"] == "asset" and x["currency"] != "وحدة نقدية"}
    if len(asset_curs) == 1:
        cur = next(iter(asset_curs))
        for x in mentions:
            if x["currency"] == "وحدة نقدية":
                x["currency"] = cur
    return mentions


def _summarize_financials_v7(question: str):
    mentions = _extract_financial_mentions_v7(question)
    if not mentions:
        return None
    by_cur = {}
    for m in mentions:
        cur = m["currency"]
        by_cur.setdefault(cur, {"asset": Decimal(0), "debt": Decimal(0), "expense": Decimal(0), "right": Decimal(0), "will": Decimal(0), "items": []})
        by_cur[cur][m["category"]] += m["amount"]
        by_cur[cur]["items"].append(m)
    # Drop currencies with no assets; they cannot be distributed. Keep warning in summary.
    return by_cur


def _format_money_v7(value: Decimal, currency: str) -> str:
    return _format_money(value, currency)


def _append_monetary_distribution(answer_text: str, question: str) -> str:
    """Enhanced monetary distribution: gross assets minus rights/expenses/debts/valid will, then distribute net.

    Handles numeric and common Arabic textual amounts, single/multiple assets, many currencies, and safe non-conversion.
    """
    if "من التركة" not in answer_text:
        return answer_text
    entries = _extract_share_entries(answer_text)
    if not entries:
        return answer_text
    fin = _summarize_financials_v7(question)
    if not fin:
        return answer_text
    blocks = []
    any_distribution = False
    for cur, sums in fin.items():
        gross = sums["asset"]
        if gross <= 0:
            continue
        pre_will_deductions = sums["right"] + sums["expense"] + sums["debt"]
        after_pre = gross - pre_will_deductions
        if after_pre < 0:
            blocks.append("\nتنبيه مالي: الخصومات المذكورة أكبر من قيمة الأصول بعملة " + cur + "؛ لا يمكن قسمة تركة سالبة. راجع مبالغ الديون والحقوق.")
            continue
        will_requested = sums["will"]
        will_allowed = Decimal(0)
        will_note = ""
        if will_requested > 0:
            max_will = after_pre / Decimal(3)
            will_allowed = will_requested if will_requested <= max_will else max_will
            if will_requested > max_will:
                will_note = f"- الوصية المذكورة: {_format_money_v7(will_requested, cur)}، والمحتسب هنا في حدود الثلث فقط: {_format_money_v7(will_allowed, cur)}، وما زاد يحتاج إجازة الورثة."
            else:
                will_note = f"- الوصية المحتسبة: {_format_money_v7(will_allowed, cur)}."
        net = after_pre - will_allowed
        if net <= 0:
            blocks.append("\nتنبيه مالي: لا يوجد صافي تركة قابل للقسمة بعملة " + cur + " بعد الحقوق والخصومات المذكورة.")
            continue
        lines = ["", "القسمة النقدية/المالية حسب صافي التركة المذكورة:"]
        lines.append(f"- إجمالي التركة: {_format_money_v7(gross, cur)}")
        lines.append(f"- إجمالي الأصول: {_format_money_v7(gross, cur)}")
        if pre_will_deductions > 0 or will_allowed > 0:
            lines.append("- الخصومات قبل القسمة:")
            if sums["right"] > 0:
                lines.append(f"  - الحقوق المتعلقة بعين التركة/الرهن: {_format_money_v7(sums['right'], cur)}")
            if sums["expense"] > 0:
                lines.append(f"  - تجهيز/مصاريف الميت: {_format_money_v7(sums['expense'], cur)}")
            if sums["debt"] > 0:
                lines.append(f"  - الديون: {_format_money_v7(sums['debt'], cur)}")
            if will_note:
                lines.append("  " + will_note)
        lines.append(f"- صافي التركة المقسومة: {_format_money_v7(net, cur)}")
        for e in entries:
            dec = _fraction_to_decimal(e["frac"])
            if dec is None: continue
            lines.append(f"- {e['label']}: {_format_money_v7(net * dec, cur)}")
            if e.get("individual"):
                idec = _fraction_to_decimal(e["individual"])
                if idec is not None:
                    lines.append(f"  نصيب الفرد الواحد: {_format_money_v7(net * idec, cur)}")
        lines.append("تنبيه: الحساب المالي مبني على المبالغ التي كتبها المستخدم، وقد تظهر فروق بسيطة بسبب التقريب إلى منزلتين عشريتين.")
        blocks.append("\n".join(lines))
        any_distribution = True
    # Warnings for unsupported multiple currency conversion or deductions without assets.
    asset_currencies = [cur for cur, sums in fin.items() if sums["asset"] > 0]
    if len(asset_currencies) > 1:
        blocks.append("\nتنبيه: ظهرت أكثر من عملة في السؤال، لذلك لم أحوّل العملات بين بعضها؛ تم حساب كل عملة على حدة. للتحويل إلى عملة واحدة اكتب سعر الصرف أو قيمة جميع الأصول بعملة واحدة.")
    orphan_deductions = []
    for cur, sums in fin.items():
        if sums["asset"] <= 0 and (sums["debt"] + sums["expense"] + sums["right"] + sums["will"]) > 0:
            orphan_deductions.append(cur)
    if orphan_deductions:
        blocks.append("\nتنبيه: وُجدت خصومات بعملة لا تقابلها أصول بنفس العملة، فلم أخصمها تلقائيًا: " + ", ".join(orphan_deductions))
    if not any_distribution:
        return answer_text
    return answer_text.rstrip() + "\n" + "\n".join(blocks)


# ==========================================================
# V35: Universal Follow-up + Simple Multi-Death/Munasakhat Layer
# ==========================================================
# هذه الطبقة لا تثبت إجابات نصية لأسئلة بعينها.
# وظيفتها: فهم المتابعة السياقية باللهجات، ومعالجة نموذج مبدئي آمن للمناسخات البسيطة.

_BASE_ANSWER_BEFORE_V35 = answer

_UNIVERSAL_SIMPLIFY_V35 = [
    "مش فاهم", "مش فاهمه", "مش فاهما", "ما فهمت", "ما افهم", "مافهمت", "مفهمتش", "مفهمت", "مو فاهم",
    "ماني فاهم", "ما استوعبت", "مش مستوعب", "مش واضح", "غير واضح", "وضح", "وضحلي", "وضحهالي",
    "فهمني", "بسط", "بسطها", "بسطلي", "اختصر", "اشرح ابسط", "اشرحها ابسط", "ممكن تبسط",
    "ما فهمتش", "مافهمتش", "مش داخله دماغي", "بالراحة", "واحدة واحدة", "اشرح خطوة خطوة",
    "شنو يعني", "وش يعني", "يعني شنو", "يعني ايه", "يعني اي", "اي المقصود", "إيه المقصود"
]
_UNIVERSAL_EXAMPLE_V35 = [
    "مثال", "هات مثال", "اديني مثال", "مثال بالارقام", "مثال بالأرقام", "طبقها", "طبق", "بالارقام", "بالأرقام",
    "احسبها بالمبلغ", "على مبلغ", "بمبلغ", "لو التركة", "وريني مثال", "اعمل مثال"
]
_UNIVERSAL_DETAIL_V35 = [
    "فصل", "فصّل", "بالتفصيل", "شرح كامل", "زود شرح", "الدليل", "ليه", "لماذا", "سبب", "السبب"
]

def _is_universal_followup_v35(q: str) -> bool:
    n = _n(q)
    if len(n.split()) > 12 and not any(x in n for x in ["مثال", "بالارقام", "بالأرقام", "اشرح"]):
        return False
    return any(_n(x) in n for x in (_UNIVERSAL_SIMPLIFY_V35 + _UNIVERSAL_EXAMPLE_V35 + _UNIVERSAL_DETAIL_V35))

def _followup_level_v35(q: str) -> str:
    n = _n(q)
    if any(_n(x) in n for x in _UNIVERSAL_EXAMPLE_V35):
        return "example"
    if any(_n(x) in n for x in _UNIVERSAL_DETAIL_V35):
        return "detailed"
    return "simple"

def _simplify_previous_answer_v35(q: str, context: dict) -> str | None:
    last_answer = (context or {}).get("last_answer") or ""
    if not last_answer:
        return None
    level = _followup_level_v35(q)
    dialect = _dialect((context or {}).get("last_question") or q)
    prefix = {
        "egyptian": "تمام، أبسطهالك واحدة واحدة:",
        "gulf": "أبشر، أوضحها لك بشكل أبسط:",
        "saudi": "أبشر، أوضحها لك بشكل أبسط:",
        "shami": "تمام، خليني أبسطها لك:",
        "moroccan": "حاضر، نشرحها ببساطة:",
        "sudanese": "تمام، أبسطها ليك كده:",
    }.get(getattr(dialect, 'name', 'standard'), "تمام، أوضحها بصورة أبسط:")
    # لا نعيد الرد كاملًا كما هو؛ نلخص أهم الأسطر حتى لا يكون ردًا ثابتًا ولا تكرارًا حرفيًا.
    lines = [x.strip() for x in last_answer.splitlines() if x.strip()]
    useful = []
    for x in lines:
        if x.startswith("-") or "السبب:" in x or "تنبيه" in x or "مراجعة مجموع" in x:
            useful.append(x)
    if not useful:
        useful = lines[:6]
    if level == "example":
        return prefix + "\n\n" + "\n".join(useful[:10]) + "\n\nلو تحب مثالًا رقميًا، اكتب قيمة التركة أو مبلغها وسأقسمه على نفس الأنصبة."
    if level == "detailed":
        return prefix + "\n\n" + "\n".join(useful[:14]) + "\n\nالخلاصة: أنا لم أغيّر الحكم؛ فقط أعدت ترتيب الشرح من آخر مسألة/مفهوم سألته."
    return prefix + "\n\n" + "\n".join(useful[:8])

def _detect_daughters_count_v35(q: str) -> int | None:
    n = _n(q)
    pats = [r"(\d+)\s+بنات", r"(\d+)\s+بنت", r"(واحده|واحدة|بنت واحده|بنت واحدة)\s+", r"(اربع|اربعه|أربع|أربعة|اربعة|اربع)\s+بنات", r"(ثلاث|ثلاثه|تلات|تلاته)\s+بنات", r"(بنتين|ابنتين)" ]
    for pat in pats:
        m = re.search(pat, n)
        if not m:
            continue
        token = m.group(1) if m.groups() else m.group(0)
        if token in {"بنتين", "ابنتين"}:
            return 2
        if "اربع" in token:
            return 4
        if any(x in token for x in ["ثلاث", "تلات"]):
            return 3
        try:
            return int(token)
        except Exception:
            try:
                return v8.ar_num_to_int(token)
            except Exception:
                pass
    return None

def _is_simple_spouse_munasakhat_v35(q: str) -> bool:
    n = _n(q)
    return (
        any(x in n for x in ["بعده ماتت زوجته", "ثم ماتت زوجته", "بعدها ماتت زوجته", "وبعده ماتت زوجته", "ماتت زوجته بعده"])
        and any(x in n for x in ["اخ", "اخوها", "اخ لها", "اخو الزوجة", "اخ الزوجة"])
        and any(x in n for x in ["بنات", "بنتين", "بنت"])
    )

def _answer_simple_spouse_munasakhat_v35(q: str) -> str | None:
    if not _is_simple_spouse_munasakhat_v35(q):
        return None
    daughters = _detect_daughters_count_v35(q) or 0
    if daughters <= 0:
        return _safe_clarification(q, "المناسخة مفهومة مبدئيًا، لكن لم أحدد عدد البنات. اذكر عدد البنات بدقة.")
    amount = None; currency = "وحدة نقدية"
    try:
        fin = _summarize_financials_v7(re.sub(r"(?<!\S)و(?=(?:مليون|ملايين|نص|نصف|مية|ميه|مائة|الف|ألف|\d))", "", q))
        if fin:
            # حساب الصافي بنفس منطق طبقة المال: أصول - حقوق/تجهيز/ديون - وصية بحد الثلث.
            for cur, sums in fin.items():
                gross = sums.get("asset", Decimal(0))
                if gross <= 0:
                    continue
                pre = sums.get("right", Decimal(0)) + sums.get("expense", Decimal(0)) + sums.get("debt", Decimal(0))
                after_pre = gross - pre
                if after_pre <= 0:
                    continue
                will_req = sums.get("will", Decimal(0))
                will_allowed = Decimal(0)
                if will_req > 0:
                    max_will = after_pre / Decimal(3)
                    will_allowed = will_req if will_req <= max_will else max_will
                amount = after_pre - will_allowed
                currency = cur
                break
    except Exception:
        pass
    if amount is None:
        simple_money = _extract_money_amount(q)
        if simple_money:
            amount, currency = simple_money
    # الحالة المدعومة: الزوج مات وترك زوجة وبنات، ثم ماتت الزوجة، وورثتها البنات + أخها.
    # في الوفاة الأولى: الزوجة 1/8 لوجود الفرع الوارث، والبنات 7/8 بعد الرد لعدم وجود عاصب مذكور.
    wife_first = Fraction(1, 8)
    daughters_first_total = Fraction(7, 8)
    # في وفاة الزوجة: بناتها 2/3، وأخوها الباقي 1/3، من نصيبها الذي ورثته أولًا.
    daughters_from_mother_total = wife_first * Fraction(2, 3)
    brother_from_mother = wife_first * Fraction(1, 3)
    daughters_final_total = daughters_first_total + daughters_from_mother_total
    per_daughter = daughters_final_total / daughters
    header = _desired_header(q)
    out = [header,
           "",
           "هذه مسألة فيها وفاة متتابعة، لذلك تُحل على مرحلتين، لا كمسألة واحدة:",
           "",
           "المرحلة الأولى: وفاة الزوج.",
           f"- الزوجة: 1/8 من التركة الأولى؛ لوجود فرع وارث.",
           f"- البنات: 7/8 من التركة الأولى بعد الرد عليهن؛ لعدم ذكر عاصب في تركة الزوج.",
           "",
           "المرحلة الثانية: وفاة الزوجة بعده.",
           "- نصيب الزوجة الذي ورثته من زوجها صار تركة مستقلة لها.",
           "- بناتها يأخذن من تركة أمهن 2/3.",
           "- أخو الزوجة يأخذ الباقي 1/3 تعصيبًا، إذا لم يوجد وارث أقرب يحجبه.",
           "",
           "الناتج النهائي من التركة الأصلية:",
           f"- البنات مجتمعات: {daughters_final_total} من التركة الأصلية.",
           f"  نصيب كل بنت: {per_daughter} من التركة الأصلية.",
           f"- أخو الزوجة: {brother_from_mother} من التركة الأصلية.",
           "",
           "تنبيه: هذا الحساب مبني على أن البنات هن بنات الزوجة أيضًا، وأنه لا يوجد للزوجة وارث آخر كأب أو أم أو ابن، ولا يوجد للزوج عاصب آخر. لو وُجد وارث إضافي تتغير المسألة."]
    if amount is not None and amount > 0:
        try:
            amountD = Decimal(amount)
            out += ["", "القسمة النقدية حسب صافي التركة المذكور:", f"- إجمالي/صافي التركة المعتمد: {_format_money(amountD, currency)}"]
            out.append(f"- البنات مجتمعات: {_format_money(amountD * (Decimal(daughters_final_total.numerator)/Decimal(daughters_final_total.denominator)), currency)}")
            out.append(f"  نصيب كل بنت: {_format_money(amountD * (Decimal(per_daughter.numerator)/Decimal(per_daughter.denominator)), currency)}")
            out.append(f"- أخو الزوجة: {_format_money(amountD * (Decimal(brother_from_mother.numerator)/Decimal(brother_from_mother.denominator)), currency)}")
            out.append("تنبيه: قد توجد فروق هللات/قروش بسيطة بسبب التقريب النقدي.")
        except Exception:
            pass
    return "\n".join(out).strip()

def answer(question: str, context: dict | None = None) -> str:
    # 1) متابعة سياقية عامة بكل اللهجات: مش فاهم/ما افهم/بسط/مثال/ليه...
    if context and _is_universal_followup_v35(question):
        ca = answer_concept(question, _dialect(context.get("last_question") or question), context=context)
        if ca:
            return ca
        simplified = _simplify_previous_answer_v35(question, context)
        if simplified:
            return simplified
    # 2) مناسخات بسيطة آمنة: زوجة ترث ثم تموت، مع بنات وأخ للزوجة.
    mun = _answer_simple_spouse_munasakhat_v35(question)
    if mun:
        return mun
    # 3) باقي النظام كما هو، دون المساس بالأساس.
    return _BASE_ANSWER_BEFORE_V35(question, context=context)


# ==========================================================
# V36: Human Conversation Orchestrator + Broader Context Layer
# ==========================================================
# الهدف: جعل المحادثة أقرب لطريقة المفتي البشري دون ردود محفوظة لمسألة بعينها.
# الطبقة تعمل كمنسق نوايا وسياق: تحية، شكر، متابعة، تبسيط، مثال، لهجة، ومناسخات آمنة.

_BASE_ANSWER_BEFORE_V36 = answer

_V36_FOLLOWUP_SIMPLIFY = [
    "مش فاهم", "مش فاهمة", "مش فاهما", "مفهمتش", "مفهمت", "مافهمتش", "ما فهمتش", "ما فهمت", "ما افهم", "ما أفهم",
    "مو فاهم", "ماني فاهم", "مب فاهم", "ما استوعبت", "مش مستوعب", "مو مستوعب", "مش واضح", "مو واضح", "ما واضح",
    "وضح", "وضحلي", "وضح لي", "وضحهالي", "فهمني", "فهمنى", "فهمني اكتر", "فهمني أكثر", "عيد الشرح", "اعد الشرح",
    "بسط", "بسطها", "بسطلي", "بسطهالي", "اشرح ببساطة", "اشرح ابسط", "اشرحها ابسط", "بالراحة", "واحدة واحدة", "خطوة خطوة",
    "شنو يعني", "وش يعني", "ايش يعني", "يعني شنو", "يعني ايه", "يعني اي", "إيه المقصود", "اي المقصود", "ممكن تبسط", "ممكن توضح",
    "ما دخلت دماغي", "مش داخلة دماغي", "مش فاهم النقطة", "لسه مش فاهم", "لسا مش فاهم", "مش واصل", "ما وصلني"
]
_V36_FOLLOWUP_EXAMPLE = [
    "مثال", "هات مثال", "اديني مثال", "اعطني مثال", "وريني مثال", "وريني", "مثال عملي", "مثال بالارقام", "مثال بالأرقام", "طبق", "طبقها", "طبقلي", "بالارقام", "بالأرقام", "احسبها بالمبلغ", "لو التركة", "على مبلغ", "علي مبلغ", "بمبلغ", "اعمل مثال", "مثال رقمي", "بفلوس", "بالفلوس", "كم يطلع بالريال"
]
_V36_FOLLOWUP_DETAIL = [
    "فصل", "فصّل", "بالتفصيل", "شرح كامل", "زود شرح", "الدليل", "اي الدليل", "وش الدليل", "ليه", "لماذا", "سبب", "السبب", "كيف طلعت", "ازاي طلعت", "كيف حسبتها", "ازاي حسبتها"
]
_V36_GREETING_ONLY = [
    "السلام عليكم", "سلام عليكم", "وعليكم السلام", "مرحبا", "مرحباً", "اهلا", "أهلا", "اهلين", "هلا", "يا هلا", "صباح الخير", "مساء الخير", "عامل ايه", "كيف الحال", "شلونك", "ازيك", "اخبارك"
]
_V36_THANKS = ["شكرا", "شكرًا", "تسلم", "تسلملي", "جزاك الله", "بارك الله", "يعطيك العافية", "الله يجزاك", "تمام شكرا", "مشكور"]
_V36_ACK = ["تمام", "اوكي", "أوكي", "ok", "اوك", "حاضر", "تم", "جميل", "طيب", "ماشي"]


def _v36_norm(q: str) -> str:
    try:
        s = _n(q)
    except Exception:
        s = str(q or "")
        s = re.sub(r"[\u064b-\u0652\u0670]", "", s).replace("أ","ا").replace("إ","ا").replace("آ","ا").replace("ى","ي").replace("ة","ه").lower()
    s = re.sub(r"[\u061f؟?!.,;:،؛\[\]{}()<>\"'`~]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _v36_contains_any(q: str, arr: list[str]) -> bool:
    n = _v36_norm(q)
    return any(_v36_norm(x) in n for x in arr)


def _v36_message_kind(q: str, context: dict | None = None) -> str | None:
    # V37 optional smart classifier (PyArabic/RapidFuzz if installed).
    try:
        if _v37_detect_human_kind is not None:
            k = _v37_detect_human_kind(q, context)
            if k:
                return k
    except Exception:
        pass
    n = _v36_norm(q)
    words = n.split()
    short = len(words) <= 8
    if short and _v36_contains_any(q, _V36_GREETING_ONLY):
        # لو معها سؤال مواريث لا نعاملها كتحية فقط.
        if not any(x in n for x in ["ميراث", "مواريث", "فرائض", "تركة", "مات", "توفي", "ورث", "نصيب", "قسمة"]):
            return "greeting"
    if short and _v36_contains_any(q, _V36_THANKS):
        return "thanks"
    if short and _v36_contains_any(q, _V36_ACK):
        return "ack"
    if _v36_contains_any(q, _V36_FOLLOWUP_EXAMPLE):
        return "followup_example"
    # في المتابعة نسمح بعبارات أطول مثل: ممكن تبسط لي الكلام ده شوية.
    if len(words) <= 18 and _v36_contains_any(q, _V36_FOLLOWUP_SIMPLIFY):
        return "followup_simple"
    if len(words) <= 18 and _v36_contains_any(q, _V36_FOLLOWUP_DETAIL):
        return "followup_detail"
    if any(x in n for x in ["انت مين", "من انت", "مين انت", "ما اسمك", "اسمك ايه", "وش اسمك"]):
        return "identity"
    return None


def _v36_dialect_name(q: str, context: dict | None = None) -> str:
    try:
        d = _dialect(q)
        name = getattr(d, 'name', None)
        if name:
            return name
    except Exception:
        pass
    n = _v36_norm(q)
    if any(x in n for x in ["ازاي", "ايه", "عايز", "عاوز", "مش", "مفهمتش", "بسطهالي", "مراته", "ساب"]):
        return "egyptian"
    if any(x in n for x in ["وش", "ايش", "شلون", "ابشر", "كذا", "رجال", "حياك", "عقب"]):
        return "gulf"
    if any(x in n for x in ["شو", "قديش", "هيك", "بدي", "بدّي", "مو", "عم"]):
        return "shami"
    if any(x in n for x in ["شنو", "واش", "فالميراث", "بزاف", "نعاونك"]):
        return "moroccan"
    toks = set(n.split())
    if any(x in n for x in ["الزول", "عندو"]) or ("ليك" in toks) or ("كده" in toks):
        return "sudanese"
    if context and context.get("last_dialect"):
        return str(context.get("last_dialect"))
    return "standard"


def _v36_pick(options: list[str], seed: str) -> str:
    try:
        return _pick_variant_v35(options, seed)
    except Exception:
        if not options:
            return ""
        return options[abs(hash(seed)) % len(options)]


def _v36_smalltalk(q: str, context: dict | None, kind: str) -> str:
    try:
        if _v37_human_smalltalk_reply is not None:
            return _v37_human_smalltalk_reply(q, context=context, name=str((context or {}).get("last_user_name", "") or ""))
    except Exception:
        pass
    dialect = _v36_dialect_name(q, context)
    seed = f"v36:{kind}:{q}:{(context or {}).get('last_seen_at','')}"
    pools = {
        "greeting": {
            "egyptian": ["وعليكم السلام ورحمة الله، أهلاً بيك. ابعت مسألة المواريث أو السؤال الفقهي وأنا أرتبه معاك.", "أهلاً وسهلاً، تحت أمرك. اكتب الورثة أو سؤالك في المواريث."],
            "gulf": ["وعليكم السلام ورحمة الله، حياك الله. اكتب مسألتك أو سؤالك في الفرائض.", "مرحبا، تفضل بسؤالك في المواريث وأرتبه لك."],
            "shami": ["وعليكم السلام ورحمة الله، أهلاً وسهلاً. اكتبلي مسألتك بالمواريث.", "أهلاً فيك، ابعت السؤال وأنا أوضح لك."],
            "standard": ["وعليكم السلام ورحمة الله وبركاته. تفضل بسؤالك في المواريث أو اذكر الورثة وقيمة التركة إن وجدت.", "مرحبًا بك. اكتب مسألة ميراث أو سؤالًا فقهيًا، وإذا كان السؤال ناقصًا سأطلب توضيحًا بدل التخمين."]
        },
        "thanks": {
            "egyptian": ["العفو، تحت أمرك. لو حابب أبسط نقطة أو أحسب مبلغ معيّن ابعتهولي.", "ربنا يبارك فيك، أي مسألة تانية ابعتها وأنا أرتبها."],
            "gulf": ["العفو، حياك الله. لو تحتاج تبسيط أو مثال أرسله.", "الله يعافيك، تفضل بأي مسألة ثانية."],
            "standard": ["العفو، يسعدني خدمتك. إن احتجت تبسيطًا أو مثالًا رقميًا فأرسل طلبك.", "بارك الله فيك، تفضل بأي سؤال آخر في المواريث."]
        },
        "ack": {
            "egyptian": ["تمام، لو احتجت أحسب مسألة أو أبسط حاجة ابعتلي.", "ماشي، جاهز لأي سؤال مواريث تاني."],
            "gulf": ["تمام، أبشر بأي سؤال ثاني.", "حاضر، أرسل المسألة متى ما احتجت."],
            "standard": ["تمام، أنا جاهز لأي مسألة أو سؤال فقهي آخر.", "حسنًا، أرسل ما تريد حسابه أو توضيحه في المواريث."]
        },
        "identity": {
            "egyptian": ["أنا مفتي المواريث الذكي؛ أساعدك في فهم مسائل الفرائض وحساب الأنصبة بأمان، ولو السؤال ناقص بطلب توضيح بدل التخمين."],
            "gulf": ["أنا مفتي المواريث الذكي؛ أساعدك في حساب مسائل الإرث وشرح أحكام الفرائض، وأطلب التوضيح إذا كانت المسألة ناقصة."],
            "standard": ["أنا مفتي المواريث الذكي؛ نظام مخصص لشرح أحكام المواريث وحساب الأنصبة وفق البيانات التي تذكرها، مع تجنب التخمين عند الغموض."]
        }
    }
    group = pools.get(kind, {})
    opts = group.get(dialect) or group.get("standard") or ["تفضل بسؤالك في المواريث."]
    return _v36_pick(opts, seed)


def _v36_followup_answer(q: str, context: dict | None, kind: str) -> str | None:
    if not context:
        return None
    last_answer = context.get("last_answer") or ""
    last_question = context.get("last_question") or ""
    if not last_answer and not last_question:
        return None
    # أولًا: لو آخر موضوع فقهي معروف، استخدم محرك المفاهيم نفسه بمستوى جديد.
    try:
        dialect = _dialect(last_question or q)
        fq = ""
        if kind == "followup_example":
            fq = "هات مثال بالأرقام " + (context.get("last_concept") or last_question)
        elif kind == "followup_detail":
            fq = "اشرح بالتفصيل " + (context.get("last_concept") or last_question)
        else:
            fq = "اشرح ببساطة " + (context.get("last_concept") or last_question)
        ca = answer_concept(fq, dialect, context=context)
        if ca:
            return ca
    except Exception:
        pass
    # ثانيًا: تبسيط آخر إجابة حسابية أو فقهية بدون نسخ حرفي كامل.
    return _v36_rephrase_last_answer(q, context, kind)


def _v36_rephrase_last_answer(q: str, context: dict, kind: str) -> str | None:
    last_answer = context.get("last_answer") or ""
    if not last_answer:
        return None
    # إزالة مقدمات/تحيات طويلة حتى لا تتكرر عند التبسيط.
    lines = [x.strip() for x in last_answer.splitlines() if x.strip()]
    keep = []
    for x in lines:
        nx = _v36_norm(x)
        if nx.startswith("بسم الله") or "ردا على" in nx or "رد ا على" in nx or "اهلا" in nx or "مرحبا" in nx:
            continue
        if x.startswith("-") or "نصيب" in x or "السبب" in x or "تنبيه" in x or "مجموع" in x or ":" in x:
            keep.append(x)
    if not keep:
        keep = lines[:8]
    dialect = _v36_dialect_name(q, context)
    prefixes = {
        "egyptian": {
            "followup_simple": "حاضر، خليني أبسطهالك من غير تعقيد:",
            "followup_example": "تمام، ناخدها كمثال عملي:",
            "followup_detail": "ماشي، أوضحها بتفصيل أكتر:",
        },
        "gulf": {
            "followup_simple": "أبشر، أوضحها لك ببساطة:",
            "followup_example": "خلّنا نأخذها كمثال:",
            "followup_detail": "أبشر، هذا التفصيل:",
        },
        "shami": {
            "followup_simple": "تمام، خليني أبسطها لك:",
            "followup_example": "طيب، ناخدها بمثال:",
            "followup_detail": "خليني أوضحها بتفصيل أكثر:",
        },
        "standard": {
            "followup_simple": "حسنًا، أوضحها بصورة أبسط:",
            "followup_example": "لنطبّقها بمثال واضح:",
            "followup_detail": "إليك التفصيل بصورة أوسع:",
        }
    }
    pre = (prefixes.get(dialect) or prefixes["standard"]).get(kind, prefixes["standard"]["followup_simple"])
    limit = 8 if kind == "followup_simple" else 14
    tail = ""
    if kind == "followup_example" and not any(x in _v36_norm(last_answer) for x in ["ريال", "جنيه", "دولار", "درهم", "دينار"]):
        tail = "\n\nلو تريد مثالًا بمبلغ محدد، اكتب قيمة التركة والعملة، مثل: التركة 100000 ريال."
    return pre + "\n\n" + "\n".join(keep[:limit]) + tail


def _v36_is_extended_death_case(q: str) -> bool:
    n = _v36_norm(q)
    death_markers = ["مات", "توفي", "توفى", "هلك", "ماتت", "توفت", "توفيت"]
    seq_markers = ["بعده", "بعدها", "ثم", "وبعد", "وبعدين", "عقب", "لاحقا", "بعد ذلك"]
    return sum(1 for x in death_markers if x in n) >= 2 or (any(x in n for x in death_markers) and any(x in n for x in seq_markers))


def _v36_safe_munasakhat_router(q: str) -> str | None:
    # اترك الحالة المدعومة في V35 تعمل أولًا.
    try:
        ans = _answer_simple_spouse_munasakhat_v35(q)
        if ans:
            return ans
    except Exception:
        pass
    if not _v36_is_extended_death_case(q):
        return None
    dialect = _v36_dialect_name(q, None)
    openers = {
        "egyptian": "المسألة دي مناسخة / وفاة متتابعة، ولا يصح حسابها بالتخمين؛ فلازم تتحل مرحلة مرحلة ومينفعش أخلط الورثة في قسمة واحدة.",
        "gulf": "هذه مسألة مناسخة / وفاة متتابعة، ولا يصح حسابها بالتخمين؛ ولازم تنحل على مراحل ولا يصح جمع الورثة كلهم في قسمة واحدة.",
        "shami": "هاي مسألة مناسخة / وفاة متتابعة، ولا يصح حسابها بالتخمين؛ ولازم تنحل خطوة خطوة، مش قسمة واحدة.",
        "standard": "هذه مسألة مناسخة / وفاة متتابعة، ولا يصح حسابها بالتخمين، وتُحل على مراحل؛ لأن نصيب كل متوفى قد يصبح تركة مستقلة لورثته."
    }
    return (openers.get(dialect) or openers["standard"]) + "\n\n" + \
        "حتى أحسبها بدقة أحتاج هذه البيانات لكل وفاة:\n" + \
        "1. من هو المتوفى الأول؟ ومن ورثته الأحياء وقت وفاته؟\n" + \
        "2. كم كانت التركة الصافية للمتوفى الأول، مع العملة والأصول والديون والوصايا إن وجدت؟\n" + \
        "3. من هو المتوفى الثاني؟ وما نصيبه الذي ورثه من الأول؟\n" + \
        "4. من ورثة المتوفى الثاني الأحياء وقت وفاته؟\n\n" + \
        "لو كتبتها بهذا الشكل سأقسمها دون تخمين: مات فلان وترك كذا، ثم مات فلان وترك كذا."


def answer(question: str, context: dict | None = None) -> str:
    kind = _v36_message_kind(question, context)
    if kind in {"greeting", "wellbeing", "thanks", "ack", "identity"}:
        return _v36_smalltalk(question, context, kind)
    if kind in {"followup_simple", "followup_example", "followup_detail"}:
        fu = _v36_followup_answer(question, context, kind)
        if fu:
            return fu
        # لو لا يوجد سياق، لا نخمن موضوعًا.
        return _v36_smalltalk("", context, "greeting") + "\n\nاكتب السؤال أو المسألة التي تريد تبسيطها أولًا."
    # مناسخات موسعة: احسب المدعوم، وأوقف بأمان غير المكتمل.
    mun = _v36_safe_munasakhat_router(question)
    if mun:
        return mun
    return _BASE_ANSWER_BEFORE_V36(question, context=context)


# ---------------------------------------------------------------------------
# V39 fallback natural chat override inside runtime.
# حتى لو فشل استيراد human_conversation_enhancer، لا نرجع لعبارات آلية مثل "تفضل بسؤالك" في الكلام الاجتماعي.
# ---------------------------------------------------------------------------
def _v39_runtime_norm(q: str) -> str:
    try:
        return _v36_norm(q)
    except Exception:
        return str(q or "").strip().lower()

def _v39_runtime_has(q: str, arr: list[str]) -> bool:
    n = _v39_runtime_norm(q)
    return any(_v39_runtime_norm(x) in n for x in arr)

_V39_DOMAIN_HINTS_RUNTIME = ["ميراث", "مواريث", "فرائض", "تركة", "مات", "توفي", "توفى", "توفيت", "ورث", "نصيب", "قسمة", "حجب", "تعصيب", "عول", "رد", "زوج", "زوجة", "ابن", "بنت", "اخ", "اخت", "أخ", "أخت", "عم", "جد", "وصية", "دين"]
_V39_WELLBEING_RUNTIME = ["كيف حالك", "كيف الحال", "كيفك", "شلونك", "ازيك", "ازايك", "عامل ايه", "اخبارك", "شخبارك", "طمني عليك"]
_V39_GREETING_RUNTIME = ["السلام عليكم", "سلام عليكم", "هلا", "هلا والله", "يا هلا", "مرحبا", "اهلا", "اهلين", "صباح الخير", "مساء الخير", "سلام"]

def _v36_message_kind(q: str, context: dict | None = None) -> str | None:  # type: ignore[override]
    try:
        if _v37_detect_human_kind is not None:
            k = _v37_detect_human_kind(q, context)
            if k:
                return k
    except Exception:
        pass
    n = _v39_runtime_norm(q)
    words = n.split()
    short = len(words) <= 10
    has_domain = any(_v39_runtime_norm(x) in n for x in _V39_DOMAIN_HINTS_RUNTIME)
    if short and not has_domain and _v39_runtime_has(q, _V39_WELLBEING_RUNTIME):
        return "wellbeing"
    if short and not has_domain and _v39_runtime_has(q, _V39_GREETING_RUNTIME):
        return "greeting"
    if short and _v36_contains_any(q, _V36_THANKS):
        return "thanks"
    if short and _v36_contains_any(q, _V36_ACK):
        return "ack"
    if _v36_contains_any(q, _V36_FOLLOWUP_EXAMPLE):
        return "followup_example"
    if len(words) <= 18 and _v36_contains_any(q, _V36_FOLLOWUP_SIMPLIFY):
        return "followup_simple"
    if len(words) <= 18 and _v36_contains_any(q, _V36_FOLLOWUP_DETAIL):
        return "followup_detail"
    if any(x in n for x in ["انت مين", "من انت", "مين انت", "ما اسمك", "اسمك ايه", "وش اسمك"]):
        return "identity"
    return None

def _v36_smalltalk(q: str, context: dict | None, kind: str) -> str:  # type: ignore[override]
    try:
        if _v37_human_smalltalk_reply is not None:
            return _v37_human_smalltalk_reply(q, context=context, name=str((context or {}).get("last_user_name", "") or ""))
    except Exception:
        pass
    dialect = _v36_dialect_name(q, context)
    seed = f"v39-runtime:{kind}:{q}:{(context or {}).get('last_seen_at','')}"
    n = _v39_runtime_norm(q)
    has_salam = "السلام عليكم" in n or "سلام عليكم" in n
    has_wellbeing = _v39_runtime_has(q, _V39_WELLBEING_RUNTIME)
    if has_salam and has_wellbeing:
        pools = {
            "egyptian": ["وعليكم السلام ورحمة الله وبركاته. الحمد لله بخير. إنت عامل إيه؟"],
            "gulf": ["وعليكم السلام ورحمة الله وبركاته. الحمد لله بخير، عساك بخير."],
            "standard": ["وعليكم السلام ورحمة الله وبركاته. الحمد لله بخير، أسأل الله أن تكون بخير."]
        }
        return _v36_pick(pools.get(dialect) or pools["standard"], seed)
    if kind == "wellbeing":
        pools = {
            "egyptian": ["الحمد لله بخير. إنت عامل إيه؟", "تمام الحمد لله. طمني عليك."],
            "gulf": ["بخير ولله الحمد، عساك بخير.", "الحمد لله بخير. الله يحييك."],
            "standard": ["الحمد لله بخير.", "بخير ولله الحمد."]
        }
        return _v36_pick(pools.get(dialect) or pools["standard"], seed)
    if kind == "greeting":
        pools = {
            "egyptian": ["وعليكم السلام ورحمة الله وبركاته. أهلاً بيك.", "أهلاً، نورت."],
            "gulf": ["وعليكم السلام ورحمة الله وبركاته. حيّاك الله.", "هلا والله، حيّاك."],
            "standard": ["وعليكم السلام ورحمة الله وبركاته. أهلاً بك.", "مرحبًا."]
        }
        opts = pools.get(dialect) or pools["standard"]
        if has_salam:
            opts = [x for x in opts if "وعليكم" in x] or opts
        return _v36_pick(opts, seed)
    if kind == "thanks":
        return _v36_pick(["العفو، بارك الله فيك.", "يسعدني خدمتك."], seed)
    if kind == "ack":
        return _v36_pick(["تمام.", "حسنًا."], seed)
    if kind == "identity":
        return "أنا مفتي المواريث الذكي؛ أساعدك في شرح أحكام المواريث وحساب الأنصبة، وأطلب التوضيح عند نقص البيانات."
    return "أنا معك."

# ---------------------------------------------------------------------------
# V41 Core Intelligence Foundation — final runtime override
# General Arabic/dialect conversation routing, no RAG, no fixed case answers.
# ---------------------------------------------------------------------------
try:
    import v41_core_intelligence as _v41core
except Exception:
    _v41core = None

_BASE_ANSWER_BEFORE_V41 = answer

if _v41core is not None:
    def _v36_message_kind(q: str, context: dict | None = None) -> str | None:  # type: ignore[override]
        r = _v41core.classify_intent(q, context)
        mapping = {
            "social_greeting_status": "greeting",
            "social_status": "wellbeing",
            "social_greeting": "greeting",
            "social_thanks": "thanks",
            "social_ack": "ack",
            "identity": "identity",
            "followup_simplify": "followup_simple",
            "followup_example": "followup_example",
            "followup_detail": "followup_detail",
        }
        return mapping.get(r.intent)

    def _v36_smalltalk(q: str, context: dict | None, kind: str) -> str:  # type: ignore[override]
        return _v41core.social_reply(q, context=context, name=str((context or {}).get("last_user_name", "") or "")) or "أنا معك."

    def answer(question: str, context: dict | None = None) -> str:  # type: ignore[override]
        r = _v41core.classify_intent(question, context)
        if r.intent in {"social_greeting_status", "social_status", "social_greeting", "social_thanks", "social_ack", "identity"}:
            return _v41core.social_reply(question, context=context, name=str((context or {}).get("last_user_name", "") or ""))
        if r.intent in {"followup_simplify", "followup_example", "followup_detail"}:
            # Keep the existing project follow-up logic, but never allow social/follow-up to become a fatwa preamble.
            kind = _v36_message_kind(question, context)
            fu = _v36_followup_answer(question, context, kind or "followup_simple")
            if fu:
                return fu
            return "أحتاج أعرف أي جزء تريد تبسيطه؛ اكتب السؤال أو المسألة أولًا ثم قل لي: بسّط أو هات مثال."
        # Supported/unsafe munasakhat routing remains before the base engine,
        # but only when the text clearly contains sequential deaths.
        try:
            nq = _v41core.normalize(question)
            seq = any(x in nq for x in ["بعده", "بعدها", "ثم", "وبعد", "وبعدين", "عقب", "بعد ذلك", "بعد كده"])
            # count death verbs as tokens/phrases, not substrings, so "توفيت" is one death not two.
            death_hits = 0
            for pat in [r"(^|\s)مات($|\s)", r"(^|\s)ماتت($|\s)", r"(^|\s)توفي($|\s)", r"(^|\s)توفيت($|\s)", r"(^|\s)توفى($|\s)", r"(^|\s)توفت($|\s)"]:
                if re.search(pat, nq):
                    death_hits += 1
            if seq or death_hits >= 2:
                mun = _v36_safe_munasakhat_router(question)
                if mun:
                    return mun
        except Exception:
            pass
        return _BASE_ANSWER_BEFORE_V36(question, context=context)

# ---------------------------------------------------------------------------
# V42 Full Scholarly Intelligence Build — final override
# Stronger human conversation, follow-up context, and safe composite-case routing.
# ---------------------------------------------------------------------------
try:
    import v42_full_intelligence as _v42ai
except Exception:
    _v42ai = None
try:
    import v42_munasakhat_engine as _v42mun
except Exception:
    _v42mun = None

_BASE_ANSWER_BEFORE_V42 = answer

if _v42ai is not None:
    def answer(question: str, context: dict | None = None) -> str:  # type: ignore[override]
        ctx = context or {}
        intent = _v42ai.classify(question, ctx)
        if intent.name in {"social_greeting_status", "social_status", "social_greeting", "social_thanks", "social_ack", "identity"}:
            return _v42ai.social_reply(question, context=ctx, name=str(ctx.get("last_user_name") or ""))
        if intent.name in {"followup_simplify", "followup_example", "followup_detail"}:
            fu = _v42ai.followup_response(question, ctx)
            if fu:
                return fu
            # fallback to old follow-up logic if it has richer context
            try:
                kind_map = {"followup_simplify":"followup_simple", "followup_example":"followup_example", "followup_detail":"followup_detail"}
                fu2 = _v36_followup_answer(question, ctx, kind_map.get(intent.name, "followup_simple"))
                if fu2:
                    return fu2
            except Exception:
                pass
            return "أحتاج أعرف أي جزء تريد تبسيطه؛ اكتب السؤال أو المسألة أولًا، ثم قل لي: بسّط أو هات مثال."
        # Composite sequential deaths are handled by a safe scenario layer before normal calculation.
        if _v42mun is not None:
            try:
                mr = _v42mun.safe_munasakhat_response(question, ctx)
                if mr:
                    # If an earlier simple scenario handler can compute it, keep it; otherwise safe prompt.
                    try:
                        simple = _answer_simple_spouse_munasakhat_v35(question)
                        if simple:
                            return simple
                    except Exception:
                        pass
                    return mr
            except Exception:
                pass
        return _BASE_ANSWER_BEFORE_V42(question, context=ctx)
