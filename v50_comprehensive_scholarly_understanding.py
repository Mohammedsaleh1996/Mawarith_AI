# -*- coding: utf-8 -*-
"""
Mawareth AI v50 — Comprehensive Scholarly Understanding Engine

Goal
----
A non-RAG, non-fixed-answer, non-case-patch layer for Arabic inheritance terminology.
It understands questions about concepts by matching the semantic description of a concept
against a structured ontology of علم المواريث terms, rather than matching one observed
question or selecting a random keyword inside the question.

Key ideas
---------
- Comprehensive ontology: every concept has aliases, semantic signatures, rejection cues,
  relations, and a generated answer skeleton.
- Reverse definition support: questions like "ما المصطلح الذي يعبر عن ..." are matched by
  description, not by incidental words.
- Negation-aware scoring: "ليس له سهم مقدر" rejects الفرض and supports العاصب.
- Guard rails: calculation scenarios are passed to the inheritance engine; social chat is
  answered socially; ambiguous concepts request clarification.
- No RAG and no memorized Q/A pairs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple, Set
import re
import hashlib

try:
    from rapidfuzz import fuzz as _fuzz
except Exception:
    _fuzz = None

try:
    from pyarabic import araby as _araby
except Exception:
    _araby = None

# Reuse a few production helpers if present, without depending on them.
try:
    import v48_scholarly_intelligence_engine as _v48
except Exception:
    _v48 = None

TRANS = str.maketrans({
    "أ":"ا", "إ":"ا", "آ":"ا", "ٱ":"ا", "ى":"ي", "ة":"ه", "ؤ":"و", "ئ":"ي",
    "٠":"0", "١":"1", "٢":"2", "٣":"3", "٤":"4", "٥":"5", "٦":"6", "٧":"7", "٨":"8", "٩":"9",
    "۰":"0", "۱":"1", "۲":"2", "۳":"3", "۴":"4", "۵":"5", "۶":"6", "۷":"7", "۸":"8", "۹":"9",
})
DIAC = re.compile(r"[\u064b-\u0652\u0670\u0640]")
PUNCT = re.compile(r"[\u061f؟?!.,;:،؛\[\]{}()<>\"'`~|\\/]+")


def normalize(text: str) -> str:
    s = str(text or "")
    s = s.replace("\ufeff", "").replace("\u200f", "").replace("\u200e", "")
    if _araby:
        try:
            s = _araby.strip_tashkeel(s)
            s = _araby.strip_tatweel(s)
            s = _araby.normalize_hamza(s)
        except Exception:
            pass
    s = DIAC.sub("", s).translate(TRANS)
    s = PUNCT.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def stable_pick(options: List[str], seed: str) -> str:
    if not options:
        return ""
    h = int(hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
    return options[h % len(options)]


def tokens(text: str) -> List[str]:
    return normalize(text).split()


def word_hit(n: str, w: str) -> bool:
    w = normalize(w)
    if not w:
        return False
    if " " in w or len(w) > 4:
        return w in n
    return bool(re.search(r"(^|\s)(?:[وفبلك]?ال|[وفبلك])?" + re.escape(w) + r"($|\s)", n))


def phrase_hit(n: str, phrase: str) -> bool:
    p = normalize(phrase)
    return bool(p and p in n)


def fuzzy_score(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 100.0
    if _fuzz:
        try:
            return float(max(_fuzz.token_set_ratio(a, b), _fuzz.partial_ratio(a, b)))
        except Exception:
            pass
    at, bt = set(a.split()), set(b.split())
    return 100.0 * len(at & bt) / max(1, len(at | bt))


NEGATORS = ["ليس", "ليست", "بلا", "بدون", "لا", "غير", "عدم", "ما له", "ماله", "ما عنده", "ماعنده", "لا يوجد", "لا يملك"]


def negated_near(text: str, phrase: str, window: int = 6) -> bool:
    n = normalize(text)
    p = normalize(phrase)
    if not n or not p:
        return False
    words = n.split()
    pwords = p.split()
    if not pwords:
        return False
    for i in range(max(0, len(words) - len(pwords) + 1)):
        if words[i:i+len(pwords)] == pwords:
            before = " ".join(words[max(0, i-window):i])
            if any(normalize(x) in before for x in NEGATORS):
                return True
    return False


@dataclass
class Concept:
    id: str
    canonical: str
    family: str
    aliases: List[str]
    definition: str
    positive: List[str]
    negative: List[str] = field(default_factory=list)
    key_terms: List[str] = field(default_factory=list)
    points: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    contrasts: Dict[str, str] = field(default_factory=dict)
    answer_label: str = ""
    clarification: str = ""


CONCEPTS: Dict[str, Concept] = {}


def add(c: Concept) -> None:
    CONCEPTS[c.id] = c


# =====================================================
# Broad Scholarly Ontology — terms, concepts, and rules
# =====================================================

add(Concept(
    "fard", "الفَرْض", "shares",
    ["الفرض", "الفروض", "الفروض المقدرة", "النصيب المقدر", "السهم المقدر", "السهم المحدد", "الحصة المقدرة", "النصيب الشرعي", "النصيب المحدد", "السهم الشرعي", "ما فرضه الله"],
    "الفَرْض هو النصيب المقدّر شرعًا للوارث، كالنصف والربع والثمن والثلثين والثلث والسدس.",
    ["نصيب مقدر شرعا", "سهم مقدر شرعا", "حصة مقدرة شرعا", "النصيب المقدر للوارث", "السهم المحدد للوارث", "في كتاب الله", "فرضه الله", "لا يزيد الا بالرد", "لا ينقص الا بالعول", "النصف والربع والثمن", "الثلثان والثلث والسدس"],
    ["ليس له سهم مقدر", "ليس له نصيب مقدر", "بلا سهم مقدر", "ياخذ الباقي", "ما تبقى بعد اصحاب الفروض", "كل المال اذا انفرد", "منع شخص من ميراثه"],
    ["نصيب", "سهم", "مقدر", "شرعا", "فرض"],
    ["الفروض المقدرة ستة: النصف، الربع، الثمن، الثلثان، الثلث، السدس.", "الرد والعول يؤثران في مقدار الفرض، لكنهما ليسا اسم النصيب نفسه."],
    contrasts={"asib":"العاصب ليس له سهم مقدر، بل يأخذ الباقي.", "awl":"العول سبب نقص الفروض وليس اسم النصيب.", "radd":"الرد سبب زيادة بعض الأنصبة وليس اسم النصيب."},
    answer_label="الفَرْض"
))
add(Concept(
    "fixed_shares", "الفروض المقدّرة", "shares",
    ["الفروض المقدرة", "الفروض الستة", "عدد الفروض", "الأنصبة المقدرة", "انصبة مقدرة"],
    "الفروض المقدّرة هي الأنصبة المحددة شرعًا في كتاب الله: النصف، الربع، الثمن، الثلثان، الثلث، السدس.",
    ["عددها ستة", "ستة فروض", "النصف", "الربع", "الثمن", "الثلثان", "الثلث", "السدس", "انصبة محددة", "انصبة مقدرة"],
    ["ياخذ الباقي", "ليس له سهم مقدر"],
    ["فروض", "ستة", "النصف", "الربع", "الثمن", "الثلثان", "الثلث", "السدس"],
    ["هي: النصف، الربع، الثمن، الثلثان، الثلث، السدس."]
))
add(Concept(
    "ashab_furud", "أصحاب الفروض", "shares",
    ["اصحاب الفروض", "صاحب فرض", "الورثة بالفرض", "من لهم فروض", "اهل الفروض"],
    "أصحاب الفروض هم الورثة الذين لهم أنصبة مقدرة شرعًا في حالات معينة.",
    ["وارث له فرض", "له نصيب مقدر", "يرث بالفرض", "من يستحق نصيب مقدر", "اصحاب الانصبة المقدرة"],
    ["ليس له سهم مقدر", "ياخذ الباقي"],
    ["اصحاب", "فروض", "وارث", "نصيب", "مقدر"],
    ["منهم الزوجان، والأبوان، والبنات، وبنات الابن، والإخوة لأم، وغيرهم بحسب الشروط."]
))
add(Concept(
    "asib", "العاصِب", "residuary",
    ["العاصب", "العصبة", "وارث عاصب", "صاحب التعصيب", "الوارث بالتعصيب", "العصبات"],
    "العاصب هو الوارث الذي ليس له سهم مقدر، فيأخذ ما بقي بعد أصحاب الفروض، وقد يأخذ كل المال إذا انفرد.",
    ["ليس له سهم مقدر", "ليس له نصيب مقدر", "بلا سهم مقدر", "لا سهم مقدر له", "ياخذ ما تبقى", "ياخذ الباقي", "الباقي بعد اصحاب الفروض", "بعد اصحاب الفروض", "كل المال اذا انفرد", "كل التركة اذا انفرد", "وارث بلا فرض", "يرث بالتعصيب"],
    ["النصيب المقدر شرعا", "الفروض المقدرة", "النصف والربع والثمن", "منع شخص من ميراثه كله او بعضه"],
    ["عاصب", "عصبة", "باقي", "تعصيب"],
    ["العاصب يأخذ كل التركة عند عدم أصحاب الفروض.", "ويأخذ الباقي بعد أصحاب الفروض إن وجدوا.", "وقد لا يأخذ شيئًا إذا استغرقت الفروض التركة."],
    ["الأخ الشقيق مع بنت واحدة: البنت لها النصف، والأخ الشقيق يأخذ الباقي تعصيبًا."],
    contrasts={"fard":"الفرض سهم مقدر، أما العاصب فلا سهم مقدر له."},
    answer_label="العاصب"
))
add(Concept(
    "tasib", "التعصيب", "residuary",
    ["التعصيب", "تعصيب", "الإرث بالتعصيب", "ميراث العصبة", "ارث بلا فرض"],
    "التعصيب هو الإرث بلا سهم مقدر؛ فيأخذ العاصب ما بقي بعد أصحاب الفروض، أو يأخذ كل المال عند الانفراد.",
    ["الارث بلا سهم مقدر", "يرث بلا سهم مقدر", "يرث بالتعصيب", "ياخذ الباقي", "ما تبقى بعد اصحاب الفروض", "كل المال اذا انفرد", "عاصب بالنفس", "عاصب بالغير", "عاصب مع الغير"],
    ["النصيب المقدر شرعا", "الفرض", "الفروض الستة"],
    ["تعصيب", "باقي", "عصبة"],
    ["التعصيب يكون بالنفس أو بالغير أو مع الغير."]
))
add(Concept("asaba_binafs", "العاصب بالنفس", "residuary", ["العاصب بالنفس", "عاصب بنفسه", "ذكر يرث بقوته"], "العاصب بالنفس هو ذكر يرث بقوته هو، كالابن والأخ والعم عند تحقق الشروط.", ["ذكر يرث بقوته", "يرث بنفسه", "الابن", "الأخ الشقيق", "العم", "عاصب بالنفس"], ["انثى تصير عصبة بذكر"], ["بنفس", "ذكر", "عاصب"], ["هو قسم من أقسام العصبة."]))
add(Concept("asaba_bilghayr", "العاصب بالغير", "residuary", ["العاصب بالغير", "عاصبة بالغير", "البنت مع الابن", "الاخت مع الاخ"], "العاصب بالغير أنثى تصير عصبة بسبب ذكر معها في درجتها، مثل البنت مع الابن.", ["انثى تصير عصبة", "بسبب ذكر معها", "البنت مع الابن", "الاخت مع الاخ", "للذكر مثل حظ الانثيين"], ["ذكر يرث بقوته"], ["بالغير", "انثى", "ذكر"], ["مثاله: البنت مع الابن. "]))
add(Concept("asaba_maalghayr", "العاصب مع الغير", "residuary", ["العاصب مع الغير", "عاصبة مع الغير", "الأخت مع البنت", "اخت مع بنت"], "العاصب مع الغير أن تصير الأخت الشقيقة أو لأب عصبة مع فرع وارث أنثى.", ["الأخت مع البنت", "اخت شقيقة مع بنت", "اخت لاب مع بنت", "عصبة مع الغير", "فرع وارث انثى"], [], ["مع الغير", "اخت", "بنت"], ["مثاله: الأخت الشقيقة مع البنت. "]))
add(Concept(
    "hajb", "الحَجْب", "blocking",
    ["الحجب", "حجب", "منع الوارث", "محجوب", "يحجب", "الحاجب والمحجوب"],
    "الحجب هو منع وارث من ميراثه كله أو بعضه بسبب وجود وارث آخر أقرب منه أو أقوى منه.",
    ["منع وارث", "منع شخص من ميراثه", "منع من الميراث", "ميراثه كله او بعضه", "كله او بعضه", "وجود شخص اخر اقرب", "وجود وارث اقرب", "وارث اقرب", "وارث اقوى", "حجب حرمان", "حجب نقصان", "ينقص النصيب"],
    ["ياخذ الباقي", "ليس له سهم مقدر", "زيادة مجموع الفروض", "رجوع الباقي"],
    ["منع", "ميراث", "اقرب", "بعض", "كله", "حجب"],
    ["الحجب نوعان: حجب حرمان وحجب نقصان.", "حجب الحرمان يمنع الوارث من كل الميراث.", "حجب النقصان ينقص نصيب الوارث ولا يمنعه تمامًا."],
    contrasts={"radd":"الرد زيادة في نصيب بعض أصحاب الفروض، وليس منعًا من الميراث.", "awl":"العول نقص نسبي للفروض بسبب تزاحمها، وليس منعًا لشخص بسبب وارث أقرب."},
    answer_label="الحجب"
))
add(Concept("hajb_hirman", "حجب الحرمان", "blocking", ["حجب الحرمان", "منع كامل", "حرمان", "لا يرث نهائيا", "صفر ميراث"], "حجب الحرمان هو منع الوارث من الميراث كله بسبب وجود من هو أقرب أو أقوى منه.", ["لا يرث", "صفر ميراث", "منع كامل", "يحرم من كل الميراث", "منعه كله", "حجب كلي"], ["ينقص نصيبه فقط", "من الربع الى الثمن"], ["حرمان", "كامل", "لا يرث"], ["الأخ الشقيق يحجب بالابن أو الأب."]))
add(Concept("hajb_nuqsan", "حجب النقصان", "blocking", ["حجب النقصان", "نقص النصيب", "ينقص نصيبه", "حجب جزئي"], "حجب النقصان هو انتقال الوارث من نصيب أكبر إلى نصيب أقل بسبب وارث آخر.", ["ينقص النصيب", "من الربع الى الثمن", "من الثلث الى السدس", "يرث لكن اقل", "لا يمنع كليا", "نقصان"], ["لا يرث نهائيا", "منع كامل"], ["نقصان", "اقل", "ينقص"], ["الزوجة تنقص من الربع إلى الثمن بوجود الفرع الوارث."]))
add(Concept("awl", "العَوْل", "adjustment", ["العول", "عول", "تعول", "عالت", "زيادة الفروض", "زادت السهام"], "العول هو زيادة مجموع الفروض على التركة، فتُنقص أنصبة أصحاب الفروض بنسبة واحدة حتى تستوعب التركة.", ["زيادة مجموع الفروض", "الفروض اكثر من التركة", "نقص الانصبة", "تزاحم الفروض", "تخفض الانصبة", "تعول المسألة"], ["منع وارث", "ياخذ الباقي", "رجوع الباقي", "نصيب مقدر شرعا"], ["عول", "زيادة", "فروض", "نقص"], ["العول لا يلغي وارثًا، بل يخفض الأنصبة بنسبة واحدة."]))
add(Concept("radd", "الرَّد", "adjustment", ["الرد", "رد", "رد الباقي", "رجوع الباقي", "يرد الباقي"], "الرد هو رجوع الباقي إلى أصحاب الفروض غير الزوجين عند عدم وجود عاصب، بنسبة فروضهم في طريقة الحساب المعتمدة هنا.", ["رجوع الباقي", "عدم وجود عاصب", "يزيد النصيب", "يرد على اصحاب الفروض", "بقي جزء ولا عاصب"], ["عاصب موجود", "ياخذ الباقي", "زيادة مجموع الفروض"], ["رد", "باقي", "زيادة"], ["الرد لا يطبق عند وجود عاصب يأخذ الباقي."]))
add(Concept("taasil", "تأصيل المسألة", "math", ["تأصيل المسألة", "التأصيل", "اصل المسألة", "اصل المساله"], "تأصيل المسألة هو استخراج أصل عددي تُبنى عليه سهام الورثة بحسب مخارج الفروض.", ["استخراج اصل المسالة", "مخارج الفروض", "اصل عددي", "يبنى عليه السهام"], [], ["تأصيل", "اصل", "مخارج"], ["الأصل يكون من مخارج الفروض أو مما يؤول إليه بعد العول."]))
add(Concept("tashih", "تصحيح المسألة", "math", ["تصحيح المسألة", "التصحيح", "تصحيح الانكسار", "انكسار السهام"], "تصحيح المسألة هو معالجة انكسار السهام على رؤوس الورثة حتى تصح القسمة بعدد صحيح.", ["انكسار السهام", "لا تنقسم على الرؤوس", "تصحيح القسمة", "عدد صحيح"], [], ["تصحيح", "انكسار", "سهام"], []))
add(Concept("sahm", "السَّهْم", "math", ["السهم", "السهام", "اسهم المسألة", "سهم الوارث"], "السهم هو العدد الذي يمثل نصيب الوارث من أصل المسألة بعد التأصيل والتصحيح.", ["عدد يمثل نصيب", "من اصل المسالة", "سهم الوارث", "سهام الورثة"], [], ["سهم", "سهام", "اصل"], []))
add(Concept("tarka", "التَّرِكة", "estate", ["التركة", "تَرِكة", "الميراث المالي", "ما خلفه الميت", "مال الميت"], "التركة هي ما يتركه الميت من أموال وحقوق قابلة للإرث بعد إخراج الحقوق المقدمة.", ["ما يتركه الميت", "اموال وحقوق", "مال الميت", "بعد الحقوق"], [], ["تركة", "مال", "ميت"], []))
add(Concept("estate_rights", "الحقوق المتعلقة بالتركة", "estate", ["حقوق التركة", "الحقوق المتعلقة بالتركة", "ترتيب الحقوق", "قبل تقسيم التركة"], "هي الحقوق التي تقدم على قسمة الميراث: الحقوق المتعلقة بعين التركة، ثم تجهيز الميت، ثم الديون، ثم الوصية الصحيحة، ثم قسمة الباقي.", ["قبل تقسيم التركة", "تجهيز الميت", "قضاء الديون", "تنفيذ الوصية", "تقسيم الباقي", "حقوق عين التركة"], [], ["حقوق", "تركة", "ديون", "وصية"], ["لا تقسم التركة قبل إخراج الحقوق المقدمة."]))
add(Concept("wasiyya", "الوَصِيَّة", "estate", ["الوصية", "وصية", "اوصى", "ثلث التركة"], "الوصية تصرف مضاف إلى ما بعد الموت، وتنفذ في حدود الثلث ولغير وارث إلا إذا أجاز الورثة ما زاد أو كان لوارث.", ["تنفذ في حدود الثلث", "لغير وارث", "بعد الموت", "اوصى"], [], ["وصية", "ثلث", "وارث"], []))
add(Concept("dayn", "الدَّين", "estate", ["الدين", "الديون", "عليه دين", "سداد الدين", "قضاء الديون"], "الدين حق مقدم على قسمة الميراث، فيقضى من التركة قبل توزيع الباقي على الورثة.", ["يقضى قبل القسمة", "سداد الدين", "قضاء الديون", "مقدم على الورثة"], [], ["دين", "ديون", "سداد"], []))
add(Concept("sabab_irth", "أسباب الإرث", "rules", ["اسباب الارث", "سبب الارث", "بماذا يرث", "موجبات الارث"], "أسباب الإرث هي ما يثبت به استحقاق الميراث، وأشهرها: النسب، والنكاح، والولاء.", ["النسب", "النكاح", "الولاء", "ما يثبت به الميراث", "سبب استحقاق"], [], ["سبب", "ارث", "نسب", "نكاح"], []))
add(Concept("shurut_irth", "شروط الإرث", "rules", ["شروط الارث", "شروط الميراث", "متى يرث", "شرط الارث"], "شروط الإرث هي تحقق موت المورث، وحياة الوارث بعده، والعلم بجهة الإرث.", ["موت المورث", "حياة الوارث", "العلم بجهة الارث", "شرط الميراث"], [], ["شروط", "موت", "حياة"], []))
add(Concept("mawani_irth", "موانع الإرث", "rules", ["موانع الارث", "مانع الارث", "موانع الميراث", "ما يمنع الارث"], "موانع الإرث هي أوصاف تمنع من الميراث مع وجود سببه، مثل القتل واختلاف الدين والرق تاريخيًا.", ["يمنع من الميراث", "مع وجود سببه", "القتل", "اختلاف الدين", "الرق", "مانع"], [], ["مانع", "موانع", "قتل", "دين"], []))
add(Concept("qatl", "القتل المانع من الإرث", "rules", ["القتل", "قاتل مورثه", "القاتل لا يرث"], "القتل من موانع الإرث في الجملة؛ فلا يرث القاتل ممن قتله على التفصيل المعروف عند الفقهاء.", ["القاتل لا يرث", "قتل مورثه", "مانع من الارث"], [], ["قتل", "قاتل"], []))
add(Concept("ikhtilaf_deen", "اختلاف الدين", "rules", ["اختلاف الدين", "اختلاف الملة", "غير مسلم", "لا توارث بين ملتين"], "اختلاف الدين من موانع الإرث في الجملة على التفصيل المقرر في أبواب المواريث.", ["اختلاف الدين", "اختلاف الملة", "مانع من الارث"], [], ["دين", "ملة"], []))
add(Concept("far_warith", "الفَرْع الوارث", "heir_classes", ["الفرع الوارث", "فرع وارث", "الذرية الوارثة"], "الفرع الوارث هو نسل الميت الوارث، كالابن والبنت وابن الابن وبنت الابن عند تحقق الشروط.", ["نسل الميت", "ابن", "بنت", "ابن الابن", "بنت الابن", "ذرية"], [], ["فرع", "وارث", "ابن", "بنت"], []))
add(Concept("asl_warith", "الأصل الوارث", "heir_classes", ["الاصل الوارث", "أصل وارث", "أصول الميت"], "الأصل الوارث هو من يتصل به الميت من جهة الأصول، كالأب والأم والجد والجدة عند تحقق الشروط.", ["اب", "ام", "جد", "جدة", "اصول الميت"], [], ["اصل", "اب", "ام", "جد"], []))
add(Concept("kalala", "الكَلالة", "special", ["الكلالة", "كلالة"], "الكلالة تطلق على من مات ولا والد له ولا ولد، ولها أثر في ميراث الإخوة ونحوهم.", ["لا والد له ولا ولد", "لا اصل ولا فرع", "ميراث الاخوة"], [], ["كلالة", "والد", "ولد"], []))
add(Concept("umariyya", "العُمَرِيَّتان / الغَرَّاوَان", "special", ["العمرية", "العمريتان", "الغراوان", "الغراوين"], "العُمَرِيَّتان مسألتان فيهما زوج أو زوجة مع أم وأب، وتأخذ الأم ثلث الباقي لا ثلث التركة كلها.", ["زوج وام واب", "زوجة وام واب", "ثلث الباقي", "منسوبة لعمر"], [], ["عمرية", "غراوان", "ثلث الباقي"], []))
add(Concept("mushtaraka", "المُشْتَرَكة / الحِمَارِيَّة", "special", ["المشتركة", "الحمارية", "الحجرية", "اليمية"], "المشتركة مسألة مشهورة يجتمع فيها زوج وأم أو جدة وإخوة لأم وإخوة أشقاء، ولها تفصيل معروف في إشراك الأشقاء مع الإخوة لأم عند من يقول به.", ["زوج", "ام", "اخوة لام", "اخوة اشقاء", "يشرك الاشقاء"], [], ["مشتركة", "حمارية"], ["تحتاج بيان الصورة بدقة قبل الحساب."]))
add(Concept("akdariyya", "الأكدرية", "special", ["الأكدرية", "الاكدرية"], "الأكدرية مسألة مشهورة في باب الجد مع الإخوة، وصورتها على المشهور: زوج وأم وجد وأخت.", ["زوج", "ام", "جد", "اخت", "باب الجد مع الاخوة"], [], ["اكدرية", "جد", "اخت"], ["تحتاج اعتماد طريقة باب الجد مع الإخوة."]))
add(Concept("jad_ikhwa", "الجد مع الإخوة", "advanced", ["الجد مع الاخوة", "ميراث الجد مع الاخوة", "باب الجد والاخوة"], "باب الجد مع الإخوة من أبواب الفرائض الدقيقة، وفيه تفصيل وخلاف في بعض الطرق، فلا يحسب بالتخمين.", ["جد مع اخوة", "جد واخ", "جد واخت", "باب دقيق", "خلاف"], [], ["جد", "اخوة"], ["يحتاج تحديد الطريقة المعتمدة قبل الحساب التفصيلي."]))
add(Concept("dhawu_arham", "ذوو الأرحام", "advanced", ["ذوو الارحام", "ذوي الارحام", "ارحام", "خال", "خالة", "ابن بنت"], "ذوو الأرحام هم أقارب ليسوا من أصحاب الفروض ولا العصبات، وتوريثهم له تفصيل بحسب الطريقة المعتمدة.", ["ليسوا اصحاب فروض", "ليسوا عصبات", "اقارب غير وارثين بالفرض والتعصيب", "خال", "خالة"], [], ["ارحام", "خال", "خالة"], ["يحتاج الباب إلى طريقة توريث معتمدة قبل الحساب التفصيلي."]))
add(Concept("munasakhat", "المناسخات", "advanced", ["المناسخات", "مناسخة", "مات ثم مات", "بعده مات", "وفاة متتابعة"], "المناسخات هي مسائل وفاة متتابعة يموت فيها بعض الورثة قبل قسمة التركة أو قبل استلام نصيبه، فتحتاج تقسيمًا على مراحل.", ["وفاة متتابعة", "مات ثم مات", "بعده مات", "توزيع على مراحل", "نصيب وارث مات"], [], ["مناسخة", "مات", "بعده"], ["تحل بترتيب الوفيات وتحويل نصيب المتوفى اللاحق إلى تركة مستقلة."]))
add(Concept("takharuj", "التخارج", "advanced", ["التخارج", "تخارج", "خروج وارث", "تنازل وارث بعوض"], "التخارج هو تصالح بعض الورثة على خروج أحدهم من التركة مقابل عوض أو اتفاق معتبر.", ["خروج وارث", "تنازل بعوض", "صلح بين الورثة", "تصالح"], [], ["تخارج", "صلح", "تنازل"], []))
add(Concept("haml", "الحَمْل", "advanced", ["الحمل", "جنين", "حامل", "المولود"], "ميراث الحمل يتعلق بجنين في بطن أمه يحتمل أن يكون وارثًا، ويحتاج تحفظًا في القسمة حتى تتبين حاله.", ["جنين", "بطن امه", "حامل", "يحتمل ان يكون وارث"], [], ["حمل", "جنين"], []))
add(Concept("mafqud", "المفقود", "advanced", ["المفقود", "غائب", "لا يعرف حياته", "لا يعرف موته"], "المفقود من انقطع خبره فلم تعلم حياته ولا وفاته، وله أحكام خاصة في الإرث تحتاج حكمًا أو تقديرًا معتبرًا.", ["انقطع خبره", "لا تعلم حياته", "لا تعلم وفاته", "غائب"], [], ["مفقود", "غائب"], []))
add(Concept("khuntha", "الخنثى", "advanced", ["الخنثى", "خنثى", "غير واضح الذكورة والانثى"], "الخنثى في باب المواريث من اشتبه أمر ذكورته وأنوثته، وله أحكام خاصة في التقدير.", ["اشتباه الذكورة والانثى", "ذكر ام انثى", "خنثى"], [], ["خنثى"], []))
add(Concept("heir", "الوارث", "heirs", ["الوارث", "وريث", "الورثة"], "الوارث هو من ثبت له حق في تركة الميت بسبب من أسباب الإرث مع تحقق الشروط وانتفاء الموانع.", ["يثبت له حق في التركة", "من يستحق الميراث", "تحقق الشروط", "انتفاء الموانع"], [], ["وارث", "ورثة"], []))

SOCIAL_CUES = {
    "السلام عليكم", "وعليكم السلام", "ازيك", "ازايك", "كيف حالك", "كيف الحال", "عامل ايه", "اخبارك", "هلا", "اهلين", "اهلا", "مرحبا", "مساء الخير", "مساء الفل", "صباح الخير", "صباح الفل", "بخير", "الحمد لله", "تمام", "كويس", "مزيان", "لاباس", "شكرا", "تسلم", "جزاك الله"
}
FOLLOWUP_CUES = {"مش فاهم", "ما افهم", "ما فهمت", "مفهمتش", "مو واضح", "وضح", "وضحلي", "بسط", "بسطها", "اشرح ابسط", "سهلها", "مثال", "هات مثال", "بالارقام", "بالأرقام", "كيف حسبتها", "ازاي حسبتها", "ليه"}
DEATH_CUES = {"مات", "توفي", "توفيت", "ماتت", "هلك", "ترك", "تركت", "خلف", "خلّف", "ساب"}
HEIR_CUES = {"زوج", "زوجة", "ابن", "بنت", "ام", "اب", "اخ", "اخت", "جد", "جدة", "عم", "بنات", "اولاد", "عيال", "ابناء"}
REVERSE_CUES = {"ما هو المصطلح", "ما المصطلح", "ما اسم", "ماذا يسمى", "ماذا يسمي", "ماذا يطلق", "ما الذي يطلق", "المصطلح الذي", "الذي يعبر عن", "يعبر عن", "يطلق على", "وش يسمون", "ايش يسمون", "شنو يسمون", "ايه اسم", "اسم ايه", "يسمى ايه"}
DIRECT_CUES = {"ما معنى", "ما هو", "ما هي", "ما المقصود", "المقصود ب", "يعني ايه", "وش يعني", "شنو يعني", "عرف", "اشرح"}
DIFF_CUES = {"الفرق بين", "ما الفرق", "فرق بين", "ايه الفرق", "وش الفرق", "شنو الفرق"}
LIST_CUES = {"كم عدد", "اذكر", "عدد", "ما هي انواع", "ما انواع", "ما اقسام", "اقسام"}


def contains_any(n: str, cues: Set[str]) -> bool:
    return any(phrase_hit(n, c) for c in cues)


def domain_score(n: str) -> int:
    score = 0
    for c in list(DEATH_CUES) + list(HEIR_CUES):
        if word_hit(n, c):
            score += 3
    for k in ["ميراث", "مواريث", "فرائض", "تركة", "وارث", "ورثة", "نصيب", "سهم", "حصة", "فرض", "عاصب", "حجب", "عول", "رد"]:
        if word_hit(n, k):
            score += 2
    for c in CONCEPTS.values():
        if any(phrase_hit(n, a) or word_hit(n, a) for a in c.aliases[:5] + [c.canonical]):
            score += 2
    return score


def is_calculation_like(text: str) -> bool:
    n = normalize(text)
    return any(word_hit(n, c) for c in DEATH_CUES) and any(word_hit(n, h) for h in HEIR_CUES)


def question_type(text: str) -> str:
    n = normalize(text)
    if contains_any(n, FOLLOWUP_CUES): return "followup"
    if is_calculation_like(text): return "inheritance_calculation"
    if contains_any(n, DIFF_CUES): return "difference"
    if contains_any(n, REVERSE_CUES): return "reverse_definition"
    if contains_any(n, LIST_CUES): return "list"
    if contains_any(n, DIRECT_CUES) and domain_score(n) >= 2: return "definition"
    if domain_score(n) < 2 and (contains_any(n, SOCIAL_CUES) or len(n.split()) <= 4): return "social"
    if domain_score(n) >= 2: return "domain"
    return "unknown"


def split_target(text: str, typ: str) -> Tuple[str, str]:
    n = normalize(text)
    if typ != "reverse_definition":
        return n, ""
    # Strip leading question words and keep the description of the concept.
    n = re.sub(r"^(ما هو المصطلح|ما المصطلح|ما اسم|ماذا يسمى|ماذا يسمي|ماذا يطلق|ما الذي يطلق|وش يسمون|ايش يسمون|شنو يسمون|ايه اسم|اسم ايه|المصطلح الذي)\s+", "", n).strip()
    for pat in [r"(?:يطلق علي|يطلق على|يعبر عن|يسمى|يسمي)\s+(.+)", r"(?:الذي|التي)\s+(.+)"]:
        m = re.search(pat, n)
        if m:
            n = m.group(1).strip()
            break
    # Split descriptive target from secondary modifiers, but keep both available.
    parts = re.split(r"\b(والذي|والتي|او|أو)\b", n, maxsplit=1)
    if len(parts) >= 3 and parts[0].strip():
        return parts[0].strip(), " ".join(parts[1:]).strip()
    return n, ""


def semantic_phrase_score(segment: str, phrase: str) -> float:
    s = normalize(segment); p = normalize(phrase)
    if not s or not p: return 0.0
    # Avoid false substring hits for short single-word cues, e.g. "عم" inside "العمريتان" or "اب" inside "كتاب".
    if len(p.split()) == 1 and len(p) <= 4:
        return 1.0 if word_hit(s, p) else 0.0
    elif p in s:
        return 1.0
    pt, st = set(p.split()), set(s.split())
    if not pt: return 0.0
    overlap = len(pt & st) / len(pt)
    if overlap >= 0.75: return 0.80
    if overlap >= 0.55 and len(pt) <= 3: return 0.50
    fs = fuzzy_score(p, s)
    if fs >= 90: return 0.75
    if fs >= 82: return 0.48
    return 0.0


def score_concept(text: str, c: Concept, typ: Optional[str] = None) -> Tuple[float, List[str]]:
    typ = typ or question_type(text)
    n = normalize(text)
    target, modifiers = split_target(text, typ)
    score = 0.0
    reasons: List[str] = []
    reverse = typ == "reverse_definition"

    # Aliases: direct hits are strong, but in reverse-definition modifier words are weak.
    for a in c.aliases + [c.canonical]:
        an = normalize(a)
        if not an: continue
        hit_target = (an in target if (" " in an or len(an) > 4) else word_hit(target, an))
        hit_whole = (an in n if (" " in an or len(an) > 4) else word_hit(n, an))
        if hit_target:
            score += 12; reasons.append(f"alias_target:{a}")
        elif hit_whole and not reverse:
            score += 6; reasons.append(f"alias:{a}")
        elif hit_whole and reverse:
            score += 0.4; reasons.append(f"alias_modifier_weak:{a}")

    # Semantic features.
    for p in c.positive:
        if negated_near(target, p) or negated_near(n, p):
            score -= 5; reasons.append(f"positive_negated:{p[:24]}")
            continue
        mt = semantic_phrase_score(target, p)
        mw = semantic_phrase_score(n, p)
        if mt:
            score += 12 * mt; reasons.append(f"feature_target:{p[:24]}:{mt:.2f}")
        elif not reverse and mw:
            score += 8 * mw; reasons.append(f"feature:{p[:24]}:{mw:.2f}")
        elif reverse and mw >= 0.78:
            score += 1.2; reasons.append(f"feature_modifier_weak:{p[:24]}")

    for neg in c.negative:
        m = max(semantic_phrase_score(target, neg), semantic_phrase_score(n, neg) * (0.8 if reverse else 1.0))
        if m:
            score -= 14 * m; reasons.append(f"reject:{neg[:24]}:{m:.2f}")

    # Key terms: broad weak evidence.
    for kt in c.key_terms:
        if word_hit(target, kt):
            score += 1.5; reasons.append(f"term_target:{kt}")
        elif not reverse and word_hit(n, kt):
            score += 1.0; reasons.append(f"term:{kt}")

    # Generic class rules, not per-question patches.
    if reverse:
        has_prevent = any(x in target for x in ["منع", "يمنع", "يحرم", "اسقاط", "حجب"])
        has_all_some = any(x in target for x in ["كله او بعضه", "كل ميراثه او بعضه", "كله او جزء", "كله او من بعضه", "كله", "بعضه", "جزء"])
        has_nearer = any(x in target for x in ["اقرب", "اقوى", "شخص اخر", "وارث اخر", "واحد اقرب", "احد اقرب"])
        if c.id == "hajb" and has_prevent and (has_all_some or has_nearer):
            score += 30; reasons.append("generic_blocking_definition")
            # If the wording clearly asks the subtype (all vs some), let the subtype win over the parent concept.
            if (("كله" in target and "بعضه" not in n and "ينقص" not in n) or "لا يرث" in target):
                score -= 12; reasons.append("parent_hajb_demoted_for_total_subtype")
            if ("ينقص" in target or "اقل" in target or "أقل" in target) and "كله" not in target:
                score -= 12; reasons.append("parent_hajb_demoted_for_partial_subtype")
        # Blocking subtypes: total prevention vs partial reduction.
        if c.id == "hajb_hirman" and has_prevent and any(x in target for x in ["كله", "كل الميراث", "من الميراث كله", "لا يرث", "نهائيا"]) and not any(x in n for x in ["بعضه", "ينقص", "نقصان", "اقل", "أقل"]):
            score += 46; reasons.append("generic_total_blocking")
        if c.id == "hajb_nuqsan" and any(x in target for x in ["انتقال", "ينتقل", "نصيب اكبر", "نصيب أكبر", "نصيب اقل", "نصيب أقل", "ينقص نصيبه", "نقص نصيبه"]):
            score += 44; reasons.append("generic_partial_blocking")

        # Adjustment concepts.
        if c.id == "awl" and any(x in target for x in ["زياده مجموع الفروض", "زيادة مجموع الفروض", "الفروض اكثر من", "الفروض زادت", "تجاوزت الفروض"]):
            score += 30; reasons.append("generic_awl_definition")
        if c.id == "taasil" and any(x in target for x in ["زياده مجموع الفروض", "زيادة مجموع الفروض"]):
            score -= 20; reasons.append("taasil_rejected_by_awl_context")
        if c.id == "radd" and any(x in target for x in ["رجوع الباقي", "يرجع الباقي", "رد الباقي"]) and any(x in target for x in ["عدم العاصب", "لا عاصب", "بدون عاصب"]):
            score += 32; reasons.append("generic_radd_definition")
        if c.id == "asib" and any(x in target for x in ["عدم العاصب", "لا عاصب", "بدون عاصب"]):
            score -= 24; reasons.append("asib_rejected_by_absence_context")

        if c.id == "heir" and has_prevent:
            score -= 18; reasons.append("heir_rejected_by_blocking_context")

        share_words = any(word_hit(target, x) for x in ["نصيب", "سهم", "حصة", "حصه"])
        fixed_words = any(x in target for x in ["مقدر", "محد", "محدد", "شرع", "كتاب الله", "فرضه الله"])
        share_negated = any(x in target for x in ["ليس له سهم", "ليس له نصيب", "بلا سهم", "بدون سهم", "لا سهم مقدر", "لا نصيب مقدر"])
        residuary = any(x in target for x in ["ياخذ الباقي", "ياخذ ما تبقى", "ياخذ ما تبقي", "ما تبقى من التركه", "ما تبقي من التركه", "بعد اصحاب الفروض", "كل المال اذا انفرد", "كل التركه اذا انفرد"])
        if c.id == "fard" and share_words and fixed_words and not share_negated:
            score += 24; reasons.append("generic_defined_share")
        if c.id == "fard" and share_negated:
            score -= 28; reasons.append("fard_rejected_by_share_negation")
        if c.id in {"asib", "tasib"} and share_negated:
            score += 22; reasons.append("generic_no_fixed_share")
        if c.id in {"asib", "tasib"} and residuary:
            score += 24; reasons.append("generic_residuary")
        if c.id == "asib" and any(x in n for x in ["الوارث", "وارث", "شخص", "من هو"]):
            score += 4; reasons.append("heir_entity_asib")
        if c.id == "tasib" and any(x in n for x in ["طريقة", "نوع الارث", "الارث"]):
            score += 4; reasons.append("process_tasib")

    if typ == "list":
        if c.id == "fixed_shares" and any(x in n for x in ["الفروض", "النصف", "الربع", "الثمن", "عدد الفروض"]):
            score += 26; reasons.append("list_fixed_shares")
        if c.id in {"sabab_irth", "shurut_irth", "mawani_irth"} and any(word_hit(n, x) for x in c.key_terms):
            score += 14; reasons.append("list_rule_concept")

    return score, reasons


def rank(text: str, typ: Optional[str] = None) -> List[Tuple[str, float, List[str]]]:
    typ = typ or question_type(text)
    rows: List[Tuple[str, float, List[str]]] = []
    for cid, c in CONCEPTS.items():
        s, reasons = score_concept(text, c, typ)
        if s > 0:
            rows.append((cid, s, reasons))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows


def detect_dialect(text: str, context: Optional[dict] = None) -> str:
    if _v48:
        try:
            return _v48.detect_dialect(text, context)
        except Exception:
            pass
    n = normalize(text)
    if any(x in n for x in ["ازيك", "عامل ايه", "مش", "ايه"]): return "egyptian"
    if any(x in n for x in ["وش", "ابشر", "هلا", "شلون"]): return "gulf"
    if any(x in n for x in ["شو", "قديش", "مو"]): return "shami"
    return "standard"


def social_reply(text: str, context: Optional[dict] = None, name: str = "") -> str:
    if _v48:
        try:
            return _v48.social_reply(text, context, name)
        except Exception:
            pass
    n = normalize(text)
    if "السلام" in n:
        return "وعليكم السلام ورحمة الله وبركاته."
    if "كيف حال" in n or "ازيك" in n:
        return "الحمد لله بخير."
    if "شكرا" in n or "تسلم" in n:
        return "العفو."
    return "أهلًا بك."


def preamble(name: str, text: str) -> str:
    who = f" يا {name}" if name else ""
    opts = [
        f"بسم الله الرحمن الرحيم. بناءً على ما ورد في سؤالك{who}، فهذا بيان المسألة:",
        f"بسم الله، والصلاة والسلام على رسول الله. بعد فهم المقصود من السؤال{who}، فالجواب كالآتي:",
        f"بسم الله الرحمن الرحيم. هذا بيان موجز للمسألة التي سألت عنها{who}:",
    ]
    return stable_pick(opts, f"pre50:{text}:{name}")


def compose(c: Concept, typ: str, text: str, name: str = "") -> str:
    if typ == "reverse_definition":
        label = c.answer_label or c.canonical
        head = f"المصطلح المقصود هو: {label}."
    elif typ == "list" and c.id == "fixed_shares":
        head = "الفروض المقدّرة هي ستة."
    else:
        head = f"{c.canonical}:"
    parts = [preamble(name, text), head, c.definition]
    if c.points:
        parts.append("النقاط المهمة:\n" + "\n".join(f"- {p}" for p in c.points[:5]))
    # Show only relevant contrast if the misleading concept was mentioned.
    if typ == "reverse_definition" and c.contrasts:
        n = normalize(text)
        rel = []
        for oid, note in c.contrasts.items():
            oc = CONCEPTS.get(oid)
            if oc and any(phrase_hit(n, a) or word_hit(n, a) for a in oc.aliases + [oc.canonical]):
                rel.append(note)
        if rel:
            parts.append("تنبيه على الالتباس:\n" + "\n".join(f"- {x}" for x in rel[:4]))
    return "\n\n".join(p for p in parts if p)


def compose_difference(text: str, name: str = "") -> Optional[str]:
    n = normalize(text)
    direct = []
    for cid, c in CONCEPTS.items():
        if any(phrase_hit(n, a) or word_hit(n, a) for a in c.aliases + [c.canonical]):
            direct.append(cid)
    if len(direct) < 2:
        direct = [cid for cid, _, _ in rank(text, "difference")[:2]]
    seen = []
    for cid in direct:
        if cid not in seen:
            seen.append(cid)
    if len(seen) >= 2:
        c1, c2 = CONCEPTS[seen[0]], CONCEPTS[seen[1]]
        return "\n\n".join([
            preamble(name, text),
            f"الفرق باختصار بين {c1.canonical} و{c2.canonical}:",
            f"- {c1.canonical}: {c1.definition}",
            f"- {c2.canonical}: {c2.definition}",
        ])
    return None


@dataclass
class Route:
    action: str
    intent: str
    answer: str = ""
    concept_id: str = ""
    confidence: float = 0.0
    reason: str = ""
    dialect: str = "standard"


def route(text: str, context: Optional[dict] = None, name: str = "") -> Route:
    context = context or {}
    typ = question_type(text)
    dialect = detect_dialect(text, context)
    n = normalize(text)

    if typ == "inheritance_calculation":
        return Route("pass", typ, confidence=0.97, reason="calculation_guard", dialect=dialect)
    if typ == "social":
        return Route("answer", typ, social_reply(text, context, name), confidence=0.99, reason="social_guard", dialect=dialect)
    if typ == "followup":
        if _v48:
            try:
                return Route("answer", typ, _v48.followup_reply(text, context, name), concept_id=str(context.get("last_concept") or ""), confidence=0.82, dialect=dialect)
            except Exception:
                pass
        return Route("answer", typ, "قصدك تبسيط آخر نقطة؟ اكتب لي المصطلح أو المسألة وسأشرحها خطوة خطوة.", confidence=0.52, dialect=dialect)
    if typ == "difference":
        ans = compose_difference(text, name)
        if ans:
            return Route("answer", typ, ans, confidence=0.82, reason="difference_composer", dialect=dialect)

    if typ in {"reverse_definition", "definition", "list", "domain"}:
        rows = rank(text, typ)
        if rows:
            cid, score, reasons = rows[0]
            second_score = rows[1][1] if len(rows) > 1 else -999
            threshold = 22 if typ == "reverse_definition" else 12
            if score >= threshold and not (second_score >= score - 3 and typ not in {"reverse_definition", "list"}):
                c = CONCEPTS[cid]
                return Route("answer", typ, compose(c, typ, text, name), concept_id=cid, confidence=min(0.99, score / 62.0), reason=";".join(reasons[:10]), dialect=dialect)
            if score >= 10 and second_score >= score - 3:
                c1, c2 = CONCEPTS[cid], CONCEPTS[rows[1][0]]
                return Route("answer", "clarification", f"السؤال يحتمل أكثر من مصطلح: {c1.canonical} أو {c2.canonical}. حدّد المقصود حتى لا أجيب بتخمين.", confidence=0.55, dialect=dialect)
            return Route("review", typ, "السؤال يحتاج توضيحًا أدق قبل الجواب؛ لأن المصطلح المقصود غير ظاهر بدرجة كافية.", confidence=min(0.5, max(0, score) / 50.0), reason="low_confidence", dialect=dialect)

    if typ == "unknown" and domain_score(n) < 2:
        return Route("answer", typ, social_reply(text, context, name) if contains_any(n, SOCIAL_CUES) else "لم أفهم المطلوب بدقة. لو عندك سؤال في المواريث اكتبه، ولو تقصد شيئًا آخر وضّحه لي.", confidence=0.4, dialect=dialect)
    return Route("pass", typ, confidence=0.45, reason="fallback", dialect=dialect)


def answer(text: str, context: Optional[dict] = None, name: str = "") -> Optional[Dict[str, Any]]:
    r = route(text, context, name)
    if r.action in {"answer", "review"} and r.answer:
        return {"answer": r.answer, "intent": r.intent, "concept_id": r.concept_id, "confidence": r.confidence, "reason": r.reason, "dialect": r.dialect}
    return None


def detect_concept_key(text: str) -> str:
    rows = rank(text, question_type(text))
    return rows[0][0] if rows and rows[0][1] >= 18 else ""


def diagnose(text: str) -> Dict[str, Any]:
    typ = question_type(text)
    rows = rank(text, typ)[:8]
    return {
        "normalized": normalize(text),
        "qtype": typ,
        "target": split_target(text, typ)[0],
        "top": [{"concept_id": cid, "score": score, "reasons": reasons[:8]} for cid, score, reasons in rows]
    }
