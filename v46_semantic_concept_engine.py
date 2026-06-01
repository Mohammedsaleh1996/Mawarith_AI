# -*- coding: utf-8 -*-
"""
Mawareth AI v46 — Scholarly Semantic Concept Engine

Goal
----
A domain semantic layer for inheritance/fiqh concepts that understands
reverse definitions, disambiguates mentioned concepts from the requested concept,
and renders answers from structured scholarly data.

Constraints
-----------
- No RAG: no retrieval at answer time.
- No per-question fixed answers: matching is based on concept features, aliases,
  contrastive relations, and question type.
- Lightweight: works on Python 3.11 and uses optional PyArabic/RapidFuzz only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import re
import math
import hashlib

try:
    from pyarabic import araby as _araby  # type: ignore
except Exception:
    _araby = None

try:
    from rapidfuzz import fuzz as _fuzz  # type: ignore
except Exception:
    _fuzz = None

try:
    import fiqh_concept_engine as _legacy_concepts
except Exception:
    _legacy_concepts = None

DIAC = re.compile(r"[\u064b-\u0652\u0670\u0640]")
PUNCT = re.compile(r"[\u061f؟?!.,;:،؛\[\]{}()<>\"'`~|\\/]+")
TRANS = str.maketrans({
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
    s = s.translate(TRANS)
    s = PUNCT.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def toks(text: str) -> List[str]:
    return [t for t in normalize(text).split() if t]


def contains_phrase(n: str, phrase: str) -> bool:
    p = normalize(phrase)
    return bool(p and (p in n))


def alias_match(n: str, alias: str) -> bool:
    a = normalize(alias)
    if not a:
        return False
    # Very short aliases like "عم" must be standalone tokens, not part of "العمرية".
    if len(a) <= 5 and " " not in a:
        return bool(re.search(r"(^|\s)" + re.escape(a) + r"($|\s)", n))
    return a in n


def fuzzy_score(a: str, b: str) -> float:
    an, bn = normalize(a), normalize(b)
    if not an or not bn:
        return 0.0
    if an in bn or bn in an:
        return 100.0
    if _fuzz is None:
        aw, bw = set(an.split()), set(bn.split())
        if not aw or not bw:
            return 0.0
        return 100.0 * len(aw & bw) / max(len(aw), len(bw))
    try:
        return max(float(_fuzz.partial_ratio(an, bn)), float(_fuzz.token_set_ratio(an, bn)))
    except Exception:
        return 0.0


def stable_pick(options: List[str], seed: str) -> str:
    if not options:
        return ""
    h = int(hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
    return options[h % len(options)]


@dataclass
class Concept:
    id: str
    canonical: str
    aliases: List[str]
    definition: str
    features: List[str]
    points: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    related: List[str] = field(default_factory=list)
    contrast: Dict[str, str] = field(default_factory=dict)  # concept_id -> why not same
    category: str = "concept"
    advanced: bool = False
    caution: str = ""


CONCEPTS: Dict[str, Concept] = {}


def add(c: Concept) -> None:
    CONCEPTS[c.id] = c

# ------------------------
# Core ontology
# ------------------------
add(Concept(
    id="fard",
    canonical="الفَرْض",
    aliases=["الفرض", "الفروض", "الفروض المقدره", "الفروض المقدرة", "السهم المقدر", "النصيب المقدر", "النصيب الشرعي المقدر", "الحصة المقدرة", "الحصه المقدره", "النصيب المحدد", "الانصبة المقدرة", "الانصبه المقدره", "ما فرضه الله", "سهم مقدر"],
    definition="الفَرْض هو النصيب المقدّر شرعًا للوارث، مثل النصف والربع والثمن والثلثين والثلث والسدس.",
    features=["نصيب مقدر شرعا", "نصيب مقدر شرعي", "النصيب المقدر للوارث", "نصيب مقدر في كتاب الله", "في كتاب الله", "السهم المقدر", "الحصة المحددة للوارث", "لا يزيد الا بالرد", "لا ينقص الا بالعول", "النصف والربع والثمن والثلثان والثلث والسدس", "اصحاب الفروض", "فرضه الله للوارث"],
    points=["الفروض المقدرة المشهورة ستة: النصف، الربع، الثمن، الثلثان، الثلث، السدس.", "يزيد الفرض في بعض الصور بالرد، وينقص بالعول إذا زادت الفروض على التركة.", "العول والرد يؤثران في الفرض، لكنهما ليسا اسم النصيب نفسه."],
    examples=["الزوج له النصف عند عدم الفرع الوارث، وهذا فرض مقدّر.", "البنت الواحدة لها النصف عند عدم الابن، وهذا فرض."],
    related=["fixed_shares", "awl", "radd", "ashab_furud"],
    contrast={"awl": "العول سبب نقص الأنصبة عند زيادة الفروض على التركة، وليس اسم النصيب المقدر.", "radd": "الرد سبب زيادة بعض الأنصبة عند عدم العاصب، وليس اسم النصيب المقدر."}
))
add(Concept(
    id="fixed_shares",
    canonical="الفروض المقدّرة",
    aliases=["الفروض المقدرة", "الفروض المقدره", "عدد الفروض", "كم عدد الفروض", "انواع الفروض", "النصف والربع والثمن", "الأنصبة المقدرة"],
    definition="الفروض المقدّرة هي الأنصبة المحددة شرعًا في المواريث.",
    features=["عددها ستة", "النصف", "الربع", "الثمن", "الثلثان", "الثلث", "السدس", "انصبة مقدرة"],
    points=["هي: النصف، الربع، الثمن، الثلثان، الثلث، السدس.", "ترتبط بأصحاب الفروض، وقد تتغير بالعول أو الرد بحسب المسألة."],
    examples=["نصيب الزوجة مع وجود الفرع الوارث هو الثمن، وهو من الفروض المقدرة."],
    related=["fard", "ashab_furud"]
))
add(Concept(
    id="ashab_furud",
    canonical="أصحاب الفروض",
    aliases=["اصحاب الفروض", "أصحاب الفروض", "صاحب فرض", "من هم اصحاب الفروض", "الورثة بالفرض"],
    definition="أصحاب الفروض هم الورثة الذين لهم أنصبة مقدّرة شرعًا في حالات معينة.",
    features=["وارث له فرض", "له نصيب مقدر", "يرث بالفرض", "زوج زوجة ام اب بنت"],
    points=["منهم الزوج والزوجة والأم والأب في بعض أحواله والبنت وبنت الابن والأخت وغيرهم بحسب الشروط.", "قد يأخذ صاحب الفرض فرضه فقط، وقد يجمع بعض الورثة بين الفرض والتعصيب مثل الأب في بعض الصور."],
    related=["fard", "fixed_shares"]
))
add(Concept(
    id="awl",
    canonical="العَوْل",
    aliases=["العول", "عول", "عالت", "تعول المسألة", "زيادة الفروض", "زادت السهام"],
    definition="العول هو زيادة مجموع الفروض على التركة، فتُنقص أنصبة أصحاب الفروض بنسبة واحدة حتى تستوعب التركة.",
    features=["زيادة مجموع الفروض", "نقص الانصبة", "تنقص الفروض", "مجموع الفروض اكثر من التركة", "تخفض الانصبة", "تزاحم الفروض"],
    points=["العول لا يمنع وارثًا من أصل الميراث، بل يخفض الأنصبة بنسبة واحدة.", "العول سبب نقص الفرض، وليس هو الفرض نفسه."],
    examples=["زوج + أم + أختان شقيقتان: مجموع الفروض قبل العول أكبر من التركة، فتُعال المسألة."],
    related=["fard", "fixed_shares"],
    contrast={"fard": "الفرض هو النصيب المقدر، أما العول فهو الحالة التي ينقص فيها ذلك النصيب."}
))
add(Concept(
    id="radd",
    canonical="الرَّد",
    aliases=["الرد", "رد", "يرد الباقي", "رجوع الباقي", "باقي التركة", "رد الباقي"],
    definition="الرد هو رجوع الباقي إلى أصحاب الفروض غير الزوجين عند عدم وجود عاصب، بنسبة فروضهم في طريقة الحساب المعتمدة هنا.",
    features=["رجوع الباقي", "عدم وجود عاصب", "يزيد النصيب", "زيادة الفروض", "لا يوجد عاصب", "يرد على اصحاب الفروض"],
    points=["يكون عند بقاء جزء من التركة بعد أصحاب الفروض وعدم وجود عاصب يأخذه.", "الرد سبب زيادة بعض الأنصبة، وليس اسم النصيب المقدر نفسه."],
    examples=["من مات وترك بنتًا فقط، فلها النصف فرضًا ويرد عليها الباقي عند عدم العاصب فتأخذ التركة كلها في هذه الطريقة."],
    related=["fard", "ashab_furud"],
    contrast={"fard": "الفرض هو النصيب المقدر، أما الرد فهو سبب زيادة بعض الأنصبة عند عدم العاصب."}
))
add(Concept(
    id="hajb",
    canonical="الحَجْب",
    aliases=["الحجب", "حجب", "محجوب", "منع الوارث", "حجب الحرمان", "حجب النقصان"],
    definition="الحجب هو منع وارث من ميراثه كله أو من بعضه بسبب وجود وارث أقوى منه أو أقرب منه.",
    features=["منع الوارث", "منع من الميراث", "نقص النصيب", "وجود وارث اقوى", "حجب حرمان", "حجب نقصان"],
    points=["حجب الحرمان: يمنع الوارث من الميراث كله.", "حجب النقصان: لا يمنعه تمامًا، لكنه ينقص نصيبه.", "لا يصح الحكم بالحجب إلا بعد معرفة كل الورثة."],
    examples=["الأخ الشقيق يُحجب بالابن أو الأب، والزوجة تنقص من الربع إلى الثمن بوجود الفرع الوارث."],
    related=["hajb_hirman", "hajb_nuqsan"]
))
add(Concept(
    id="hajb_hirman",
    canonical="حجب الحرمان",
    aliases=["حجب الحرمان", "حرمان", "لا يرث", "منع كامل"],
    definition="حجب الحرمان هو منع الوارث من الميراث كله بسبب وجود من هو أقرب أو أقوى منه.",
    features=["منع كامل", "لا يرث", "يحرم من الميراث", "صفر ميراث"],
    points=["مثل حجب الأخ الشقيق بالابن أو بالأب.", "لا يطبق إلا بعد التأكد من نوع الوارث والحاجب."],
    related=["hajb"]
))
add(Concept(
    id="hajb_nuqsan",
    canonical="حجب النقصان",
    aliases=["حجب النقصان", "نقصان", "نقص النصيب", "ينقص نصيبه"],
    definition="حجب النقصان هو انتقال الوارث من نصيب أكبر إلى نصيب أقل بسبب وجود وارث آخر.",
    features=["ينقص النصيب", "ينتقل من الربع للثمن", "من الثلث للسدس", "يرث لكن اقل"],
    points=["مثل انتقال الزوجة من الربع إلى الثمن بوجود الفرع الوارث.", "ومثل انتقال الأم من الثلث إلى السدس بوجود فرع وارث أو جمع من الإخوة."],
    related=["hajb"]
))
add(Concept(
    id="tasib",
    canonical="التعصيب",
    aliases=["التعصيب", "تعصيب", "عاصب", "العصبة", "العصبه", "الباقي تعصيبا", "يرث بالتعصيب"],
    definition="التعصيب هو أن يرث الوارث بلا سهم مقدر ثابت، فيأخذ ما بقي بعد أصحاب الفروض، وقد يأخذ كل التركة عند عدم صاحب فرض، وقد لا يأخذ شيئًا إذا استغرقت الفروض التركة.",
    features=["بلا سهم مقدر", "ياخذ الباقي", "بعد اصحاب الفروض", "عاصب بالنفس", "عاصب بالغير", "عاصب مع الغير"],
    points=["أنواعه المشهورة: عاصب بالنفس، وعاصب بالغير، وعاصب مع الغير.", "العصبة لا يأخذون شيئًا إذا استغرقت الفروض التركة."],
    examples=["الأخ الشقيق مع البنت يأخذ الباقي تعصيبًا إذا لم يوجد من يحجبه."],
    related=["asaba_binafs", "asaba_bilghayr", "asaba_maalghayr"]
))
for cid, name, desc, feat in [
    ("asaba_binafs", "العاصب بالنفس", "العاصب بالنفس هو ذكر يرث بقوته هو دون أن يحتاج لمن يعصبه، مثل الابن والأخ الشقيق عند عدم الحاجب.", ["ذكر يرث بقوته", "ابن", "اخ شقيق", "ياخذ الباقي"]),
    ("asaba_bilghayr", "العاصب بالغير", "العاصب بالغير هو أنثى تصير عصبة بسبب ذكر معها في درجتها، مثل البنت مع الابن.", ["انثى تصير عصبه", "البنت مع الابن", "للذكر مثل حظ الانثيين"]),
    ("asaba_maalghayr", "العاصب مع الغير", "العاصب مع الغير هو أن تصير الأخت الشقيقة أو لأب عصبة مع وجود فرع وارث أنثى، مثل الأخت الشقيقة مع البنت.", ["الاخت مع البنت", "اخت شقيقه مع بنت", "عصبه مع الغير"]),
]:
    add(Concept(id=cid, canonical=name, aliases=[name, name.replace("ال", ""), desc[:30]], definition=desc, features=feat, related=["tasib"]))
add(Concept(
    id="estate_rights",
    canonical="الحقوق المتعلقة بالتركة",
    aliases=["ترتيب الحقوق", "حقوق التركة", "حقوق التركه", "قبل تقسيم التركة", "قبل القسمة", "الديون قبل الميراث", "تجهيز الميت", "مؤنة التجهيز"],
    definition="الحقوق المتعلقة بالتركة هي ما يخرج من التركة قبل توزيعها على الورثة.",
    features=["قبل تقسيم التركة", "تجهيز الميت", "قضاء الديون", "تنفيذ الوصية", "حقوق متعلقة بعين التركة"],
    points=["تبدأ بالحقوق المتعلقة بعين التركة إن وجدت.", "ثم تجهيز الميت بالمعروف.", "ثم قضاء الديون.", "ثم تنفيذ الوصية الصحيحة في حدود الثلث ولغير وارث إلا بإجازة الورثة.", "ثم تقسيم الباقي على الورثة."],
    related=["will", "debt"]
))
add(Concept(
    id="will",
    canonical="الوصية",
    aliases=["الوصية", "وصية", "وصيه", "اوصى", "أوصى", "ثلث التركة"],
    definition="الوصية تصرف مضاف إلى ما بعد الموت، وتنفذ من التركة بعد الديون وقبل قسمة الميراث، في حدود الثلث ولغير وارث إلا إذا أجاز الورثة.",
    features=["بعد الموت", "حد الثلث", "لغير وارث", "اجازة الورثة", "قبل قسمة الميراث"],
    points=["لا تنفذ الوصية الزائدة على الثلث إلا بإجازة الورثة.", "الوصية للوارث تحتاج إجازة الورثة بحسب القواعد المعتمدة."],
    related=["estate_rights"]
))
add(Concept(
    id="kalala",
    canonical="الكَلالة",
    aliases=["الكلالة", "كلالة", "كلاله", "لا والد ولا ولد"],
    definition="الكلالة في باب المواريث تدور على من لا والد له ولا ولد، ولها أحكام في ميراث الإخوة ونحوهم.",
    features=["لا والد", "لا ولد", "لا اصل ولا فرع", "ميراث الاخوة"],
    points=["لا يكفي لفظ الكلالة وحده لحساب مسألة؛ يجب معرفة الورثة الموجودين.", "تظهر أهميتها في مسائل الإخوة."],
    related=["siblings_types"]
))
add(Concept(
    id="umariyyat",
    canonical="العُمَرِيَّتان / الغَرَّاوَان",
    aliases=["العمرية", "العُمَرية", "العمريه", "العمريتان", "الغراوان", "الغراوين", "ثلث الباقي للام", "ثلث الباقي للأم"],
    definition="العُمَرِيَّتان مسألتان مشهورتان يجتمع فيهما الأب والأم مع أحد الزوجين، وتأخذ فيهما الأم ثلث الباقي بعد نصيب الزوج أو الزوجة، لا ثلث التركة كلها.",
    features=["اب وام وزوج", "اب وام وزوجة", "ثلث الباقي", "الام ثلث الباقي", "الغراوان"],
    points=["الصورة الأولى: زوج + أم + أب.", "الصورة الثانية: زوجة + أم + أب.", "سميت بالعمرية نسبة إلى عمر بن الخطاب رضي الله عنه."],
    examples=["زوج + أم + أب: الزوج النصف، يبقى النصف؛ الأم ثلث الباقي = السدس، والأب الباقي."],
    related=["mother", "father"]
))
add(Concept(
    id="munasakhat",
    canonical="المناسخات",
    aliases=["المناسخات", "مناسخة", "مات ثم مات", "مات بعده", "بعده مات", "وفاة متتابعة", "توفي ثم توفي"],
    definition="المناسخات هي مسائل تتعدد فيها الوفيات قبل قسمة التركة، فينتقل نصيب وارث مات بعد المورث إلى ورثته هو.",
    features=["تعدد الوفيات", "مات ثم مات", "قبل قسمة التركة", "نصيب وارث متوفى", "تركة ثانية"],
    points=["تحل على مراحل: وفاة أولى ثم تحديد نصيب من مات لاحقًا، ثم تقسيم نصيبه على ورثته.", "لا تحسب بالتخمين إذا نقص ترتيب الوفيات أو الورثة."],
    advanced=True,
    caution="هذا باب مركب؛ يلزم ترتيب الوفيات والورثة وقيمة التركة بوضوح."
))
add(Concept(
    id="mawani",
    canonical="موانع الإرث",
    aliases=["موانع الإرث", "موانع الميراث", "مانع من الارث", "القتل", "اختلاف الدين", "الرق"],
    definition="موانع الإرث هي أوصاف تمنع الشخص من الميراث رغم وجود سبب الإرث، ومن أشهرها القتل واختلاف الدين والرق تاريخيًا.",
    features=["يمنع من الميراث", "القتل", "اختلاف الدين", "الرق", "مانع"],
    points=["وجود قرابة أو زوجية لا يكفي إذا وجد مانع معتبر.", "النوازل والتطبيقات القضائية تحتاج تحققًا من الوقائع والنظام المعتمد."],
    advanced=True
))
add(Concept(
    id="dhawi_arham",
    canonical="ذوو الأرحام",
    aliases=["ذوي الارحام", "ذوو الارحام", "ذوو الأرحام", "الارحام", "الخاله", "الخالة", "العمة", "ابن البنت"],
    definition="ذوو الأرحام هم الأقارب الذين ليسوا من أصحاب الفروض ولا من العصبات في ترتيب الفرائض المشهور.",
    features=["ليسوا اصحاب فروض", "ليسوا عصبه", "الخاله", "العمه", "ابن البنت"],
    points=["توريثهم له تفصيل بين أهل العلم والأنظمة القضائية.", "لا ينتقل إليهم غالبًا مع وجود صاحب فرض أو عصبة مستحق بحسب الطريقة المعتمدة."],
    advanced=True
))
# Add many heir concepts as light concepts.
for cid, canon, aliases, definition in [
    ("husband", "الزوج", ["الزوج", "زوجها", "جوزها"], "الزوج من أصحاب الفروض؛ له النصف عند عدم الفرع الوارث، والربع مع وجوده."),
    ("wife", "الزوجة", ["الزوجة", "زوجته", "مراته", "حرمته", "زوجات"], "الزوجة من أصحاب الفروض؛ لها الربع عند عدم الفرع الوارث، والثمن مع وجوده، والزوجات يشتركن في هذا النصيب."),
    ("father", "الأب", ["الاب", "الأب", "ابوه", "والده"], "الأب وارث قوي؛ قد يرث بالفرض أو بالتعصيب أو بهما بحسب وجود الفرع الوارث."),
    ("mother", "الأم", ["الام", "الأم", "امه", "والدته"], "الأم من أصحاب الفروض؛ لها الثلث في بعض الصور، والسدس مع الفرع الوارث أو جمع من الإخوة، وثلث الباقي في العمريتين."),
    ("son", "الابن", ["الابن", "ابن", "ابنه", "ولده"], "الابن عاصب بالنفس، يأخذ الباقي بعد أصحاب الفروض ويعصب البنت معه للذكر مثل حظ الأنثيين."),
    ("daughter", "البنت", ["البنت", "بنت", "بنته", "ابنته"], "البنت ترث النصف إذا انفردت بلا ابن، والثلثين للبنات عند التعدد بلا ابن، وتتعصب مع الابن."),
    ("full_brother", "الأخ الشقيق", ["الاخ الشقيق", "أخ شقيق", "اخوه الشقيق", "اخ من الاب والام"], "الأخ الشقيق عاصب بالنفس عند عدم من يحجبه، وهو أقوى من الأخ لأب."),
    ("maternal_sibling", "الأخ أو الأخت لأم", ["اخ لام", "الأخ لأم", "اخت لام", "اخوة لام", "اخوين لام"], "الإخوة لأم يرثون بالفرض لا بالتعصيب، ويستوي ذكرهم وأنثاهم، ويحجبون بالفرع الوارث والأصل الذكر."),
    ("uncle", "العم", ["العم", "عم", "اعمام", "عم شقيق", "عم لأب"], "العم من العصبات بالنفس، يأخذ الباقي إذا لم يوجد عاصب أقرب منه."),
]:
    add(Concept(id=cid, canonical=canon, aliases=aliases, definition=definition, features=aliases + [definition], points=[], examples=[]))

# ------------------------
# Question-type detection
# ------------------------
REVERSE_PATTERNS = [
    "ما هو المصطلح", "ما المصطلح", "ما اسم", "ماذا يسمى", "ماذا نسمي", "ما الذي يطلق", "يطلق على", "يسمى", "تسمى", "وش يسمون", "ايش يسمون", "شنو يسمون", "ما المقصود بالمصطلح الذي", "مصطلح يطلق على", "اسم الشيء", "اسم النصيب", "اسم الحصة", "اسم السهم",
]
DIRECT_PATTERNS = ["ما هو", "ما هي", "ما معنى", "معنى", "عرف", "عرّف", "اشرح", "وش يعني", "ايش يعني", "شنو يعني", "يعني ايه", "يعني شنو"]
COMPARE_PATTERNS = ["الفرق بين", "ما الفرق", "قارن", "فرق بين"]
COUNT_PATTERNS = ["كم عدد", "عدد", "ما هي", "اذكر", "ما الفروض"]

DOMAIN_WORDS = ["ميراث", "مواريث", "فرائض", "فرايض", "تركة", "وارث", "الفروض", "النصيب", "العول", "الرد", "الحجب", "التعصيب", "الفرض", "الوارث", "شرعا", "شرعي"]


def question_type(question: str) -> str:
    n = normalize(question)
    if any(normalize(p) in n for p in COMPARE_PATTERNS):
        return "compare"
    if any(normalize(p) in n for p in REVERSE_PATTERNS):
        return "reverse_definition"
    # reverse definitions may not include explicit "مصطلح" but describe a concept.
    if ("النصيب" in n or "السهم" in n or "الحصه" in n or "الحصة" in n) and any(x in n for x in ["مقدر", "المقدر", "شرعا", "شرعي", "كتاب الله"]):
        return "reverse_definition"
    if any(normalize(p) in n for p in COUNT_PATTERNS) and any(x in n for x in ["فروض", "انصبه", "انصبة", "انصبه", "النصف", "الربع"]):
        return "count_or_list"
    if any(normalize(p) in n for p in DIRECT_PATTERNS):
        return "direct_definition"
    return "unknown"


def is_domain_question(question: str) -> bool:
    n = normalize(question)
    return any(normalize(w) in n for w in DOMAIN_WORDS) or question_type(question) in {"reverse_definition", "count_or_list", "compare", "direct_definition"}

# ------------------------
# Semantic scoring
# ------------------------
STOP_HINTS = {"ما", "هو", "هي", "الذي", "التي", "يطلق", "على", "اسم", "مصطلح", "يسمى", "تسمى", "في", "من", "الى", "إلى", "كتاب", "الله", "شرعا", "شرعي", "للوارث", "للوارثين"}


def _mentioned_concepts(n: str) -> List[str]:
    mentioned = []
    for cid, c in CONCEPTS.items():
        for a in [c.canonical] + c.aliases:
            an = normalize(a)
            if an and alias_match(n, an) and cid not in mentioned:
                mentioned.append(cid)
                break
    return mentioned


def _candidate_score(question: str, concept: Concept, qtype: str) -> Tuple[float, List[str]]:
    n = normalize(question)
    reasons: List[str] = []
    score = 0.0

    # direct alias match useful for direct questions, less for reverse definitions.
    alias_best = 0.0
    for a in [concept.canonical] + concept.aliases:
        an = normalize(a)
        if not an:
            continue
        if alias_match(n, an):
            alias_best = max(alias_best, 100.0)
        else:
            # Avoid fuzzy false positives from very short aliases like عم.
            if len(an) <= 5 and " " not in an:
                continue
            alias_best = max(alias_best, fuzzy_score(an, n))
    if qtype == "direct_definition":
        score += min(alias_best, 100) * 0.45
        if alias_best >= 88:
            reasons.append(f"تطابق اسم المفهوم أو أحد أسمائه: {concept.canonical}")
    elif qtype == "reverse_definition":
        # Alias presence may just be a contrast word (like العول/الرد), so reduce weight.
        score += min(alias_best, 100) * 0.08
    else:
        score += min(alias_best, 100) * 0.20

    feature_hits = 0
    for f in concept.features:
        fn = normalize(f)
        if not fn:
            continue
        if alias_match(n, fn):
            feature_hits += 1
            score += 26
            reasons.append(f"تطابق دلالة: {f}")
        else:
            # Avoid semantic false positives from short fragments.
            if len(fn) <= 5 and " " not in fn:
                continue
            fs = fuzzy_score(fn, n)
            if fs >= 86:
                feature_hits += 1
                score += 16
                reasons.append(f"تقارب دلالي: {f}")
    if feature_hits >= 2:
        score += 18
    if feature_hits >= 3:
        score += 14

    # Weighted token overlap for definitions/features.
    n_tokens = set(toks(question)) - STOP_HINTS
    c_tokens = set()
    for part in [concept.definition] + concept.features + concept.aliases:
        c_tokens.update(toks(part))
    c_tokens -= STOP_HINTS
    if n_tokens and c_tokens:
        overlap = len(n_tokens & c_tokens)
        if overlap:
            score += 4.5 * overlap
            if overlap >= 3:
                reasons.append("اشتراك ألفاظ دلالية مع تعريف المفهوم")

    # Special semantic relations: reverse definitions with contrast words.
    if qtype == "reverse_definition":
        share_words = any(x in n for x in ["النصيب", "نصيب", "السهم", "سهم", "الحصه", "الحصة", "حصة", "حصة", "حظ"])
        determiners = any(x in n for x in ["مقدر", "المقدر", "محدّد", "محدد", "المحدد", "شرعا", "شرعي", "كتاب الله", "القران", "القرآن", "فرضه الله", "للوارث", "للوريث"])
        if concept.id == "fard" and share_words and determiners:
            score += 70
            reasons.append("الوصف يطلب اسم النصيب/السهم المقدر شرعًا للوارث")
        if concept.id == "fard" and any(x in n for x in ["لا يزيد الا بالرد", "يزيد الا بالرد", "لا ينقص الا بالعول", "ينقص الا بالعول", "بالرد", "بالعول"]):
            score += 55
            reasons.append("الوصف يذكر قاعدة الفرض: لا يزيد إلا بالرد ولا ينقص إلا بالعول")
        if concept.id in {"awl", "radd"} and any(x in n for x in ["يطلق على", "ما المصطلح", "ما هو المصطلح", "ما اسم", "النصيب", "السهم", "الحصه", "الحصة"]):
            # If asking for the name of the share, awl/radd are probably modifiers, not target.
            score -= 38
            reasons.append("ذُكر المفهوم كقيد مؤثر لا كاسم النصيب المطلوب")

    # Count/list fixed shares.
    if qtype == "count_or_list" and concept.id in {"fixed_shares", "fard"}:
        score += 45
        reasons.append("السؤال يطلب تعداد الفروض المقدرة")

    # Compare common subtypes under a parent concept.
    if qtype == "compare" and concept.id == "hajb" and "حرمان" in n and "نقصان" in n:
        score += 55
        reasons.append("السؤال يقارن بين نوعي الحجب: الحرمان والنقصان")

    return score, reasons


def rank_concepts(question: str, limit: int = 5) -> List[Tuple[str, float, List[str]]]:
    qtype = question_type(question)
    ranked: List[Tuple[str, float, List[str]]] = []
    for cid, c in CONCEPTS.items():
        sc, rs = _candidate_score(question, c, qtype)
        if sc > 0:
            ranked.append((cid, sc, rs))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked[:limit]


@dataclass
class SemanticDecision:
    should_answer: bool
    concept_id: Optional[str]
    confidence: float
    qtype: str
    reasons: List[str]
    alternatives: List[Tuple[str, float]]
    review_required: bool = False


def decide(question: str, context: Optional[dict] = None) -> SemanticDecision:
    qtype = question_type(question)
    n = normalize(question)
    if qtype == "unknown" and not any(normalize(w) in n for w in DOMAIN_WORDS):
        return SemanticDecision(False, None, 0.0, qtype, [], [], False)
    ranked = rank_concepts(question, 5)
    if not ranked:
        return SemanticDecision(False, None, 0.0, qtype, [], [], qtype != "unknown")
    top_id, top_score, reasons = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    # confidence based on absolute score and margin.
    conf = min(0.99, max(0.0, top_score / 160.0))
    if top_score > 0:
        margin = max(0.0, (top_score - second) / max(top_score, 1.0))
        conf = min(0.99, 0.65 * conf + 0.35 * margin)
    # thresholds: direct definitions can be lower; reverse needs enough semantic evidence.
    threshold = 0.52 if qtype in {"direct_definition", "count_or_list"} else 0.58
    # If top score is clearly above second and above baseline, answer.
    should = (conf >= threshold and top_score >= 55) or (qtype == "reverse_definition" and top_id == "fard" and top_score >= 75) or (qtype == "count_or_list" and top_id in {"fixed_shares", "fard"} and top_score >= 70) or (qtype == "direct_definition" and top_score >= 48) or (qtype == "compare" and top_score >= 55)
    review = False
    if not should and qtype in {"reverse_definition", "direct_definition", "compare", "count_or_list"}:
        review = True
    return SemanticDecision(should, top_id if should else None, conf, qtype, reasons, [(cid, sc) for cid, sc, _ in ranked], review)

# ------------------------
# Answer rendering
# ------------------------
PREAMBLES = {
    "standard": [
        "بسم الله الرحمن الرحيم. بناءً على ما ورد في سؤالك، فهذا بيان المسألة:",
        "بسم الله، والصلاة والسلام على رسول الله. الجواب عن سؤالك كالآتي:",
        "بسم الله الرحمن الرحيم. بعد فهم صيغة السؤال، فالبيان المختصر هو:",
    ],
    "egyptian": [
        "بسم الله الرحمن الرحيم. بناءً على سؤالك، التوضيح كالتالي:",
        "بسم الله، خلّيني أوضح لك المسألة بدقة:",
    ],
    "gulf": [
        "بسم الله الرحمن الرحيم. بناءً على سؤالك، فالجواب كالتالي:",
        "بسم الله، أبشر؛ هذا بيان المسألة:",
    ],
}


def detect_dialect(question: str, context: Optional[dict] = None) -> str:
    try:
        import v45_full_scholarly_production as v45
        return v45.detect_dialect(question, context)
    except Exception:
        if context and context.get("last_dialect"):
            return str(context.get("last_dialect"))
        n = normalize(question)
        if any(x in n for x in ["ازيك", "ايه", "مش", "عاوز"]):
            return "egyptian"
        if any(x in n for x in ["وش", "ايش", "هلا", "مو"]):
            return "gulf"
        return "standard"


def _preamble(question: str, dialect: str, name: str = "") -> str:
    pool = PREAMBLES.get(dialect, PREAMBLES["standard"])
    s = stable_pick(pool, "v46pre:" + question + ":" + dialect)
    if name:
        # Mention dashboard/admin name lightly, not in every social reply.
        if "سؤالك" in s:
            s = s.replace("سؤالك", f"سؤالك يا {name}", 1)
        elif "المسألة" in s:
            s = s.replace("المسألة", f"المسألة يا {name}", 1)
    return s


def render_concept(concept_id: str, question: str, context: Optional[dict] = None, name: str = "") -> str:
    c = CONCEPTS[concept_id]
    qtype = question_type(question)
    dialect = detect_dialect(question, context)
    lines: List[str] = []
    lines.append(_preamble(question, dialect, name))
    lines.append("")

    if qtype == "reverse_definition":
        lines.append(f"المصطلح المقصود هو: **{c.canonical}**.")
        lines.append("")
        lines.append(c.definition)
    elif qtype == "count_or_list" and concept_id in {"fixed_shares", "fard"}:
        lines.append("الفروض المقدّرة في المواريث ستة:")
        lines.extend(["- النصف", "- الربع", "- الثمن", "- الثلثان", "- الثلث", "- السدس"])
        lines.append("")
        lines.append("وتسمى هذه الأنصبة فروضًا؛ لأنها أنصبة مقدّرة شرعًا للورثة في حالات محددة.")
    else:
        lines.append(f"**{c.canonical}:**")
        lines.append("")
        lines.append(c.definition)

    if c.points:
        lines.append("")
        lines.append("النقاط المهمة:")
        for p in c.points[:5]:
            lines.append(f"- {p}")

    # Contrast: if related words are in the question, clarify they are not the answer.
    n = normalize(question)
    contrast_lines = []
    for other_id, why in c.contrast.items():
        other = CONCEPTS.get(other_id)
        if not other:
            continue
        if any(alias_match(n, normalize(a)) for a in [other.canonical] + other.aliases):
            contrast_lines.append(f"- {other.canonical}: {why}")
    if contrast_lines:
        lines.append("")
        lines.append("تنبيه على الألفاظ المذكورة في السؤال:")
        lines.extend(contrast_lines)

    if c.examples:
        lines.append("")
        lines.append("مثال:")
        lines.append(c.examples[0])

    if c.advanced or c.caution:
        lines.append("")
        lines.append("تنبيه:")
        lines.append(c.caution or "هذا باب متقدم؛ لا يُحسب بالتخمين عند نقص البيانات.")

    return "\n".join(lines).strip()


def answer(question: str, context: Optional[dict] = None, name: str = "") -> Optional[Dict[str, Any]]:
    d = decide(question, context)
    if not d.should_answer or not d.concept_id:
        return None
    text = render_concept(d.concept_id, question, context, name)
    return {
        "answer": text,
        "concept_id": d.concept_id,
        "confidence": d.confidence,
        "qtype": d.qtype,
        "reasons": d.reasons,
        "alternatives": d.alternatives,
    }


def detect_concept_key(question: str) -> Optional[str]:
    d = decide(question, None)
    return d.concept_id
