# -*- coding: utf-8 -*-
"""
Mawareth AI v47 — Full Domain Understanding Engine

Purpose
-------
A stronger non-RAG, non-fixed-answer intelligence layer for Arabic inheritance
questions. It understands scholarly concepts through an ontology of aliases,
definition features, contrastive relations, and question type detection.

This layer is NOT a per-question answer map. It scores concepts from semantic
features and composes the answer from structured scholarly data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
import re, hashlib, math, json
from pathlib import Path

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
TRANS = str.maketrans({
    "أ":"ا","إ":"ا","آ":"ا","ٱ":"ا","ى":"ي","ئ":"ي","ؤ":"و","ة":"ه",
    "گ":"ك","چ":"ج","پ":"ب","ڤ":"ف",
    "٠":"0","١":"1","٢":"2","٣":"3","٤":"4","٥":"5","٦":"6","٧":"7","٨":"8","٩":"9",
    "۰":"0","۱":"1","۲":"2","۳":"3","۴":"4","۵":"5","۶":"6","۷":"7","۸":"8","۹":"9",
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
    s = DIAC.sub("", s).translate(TRANS)
    s = PUNCT.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def _tokens(text: str) -> set[str]:
    return set(normalize(text).split())


def _phrase(n: str, p: str) -> bool:
    p = normalize(p)
    return bool(p and (p in n))


def _word(n: str, w: str) -> bool:
    w = normalize(w)
    # Arabic conjunction/prepositions are often attached: والرد، فالعول، بالفرض.
    return bool(re.search(r"(^|\s)[وفبلك]?" + re.escape(w) + r"($|\s)", n))


def _alias(n: str, a: str) -> bool:
    a = normalize(a)
    if not a:
        return False
    if len(a) <= 4 and " " not in a:
        return _word(n, a)
    return a in n


def fuzzy(a: str, b: str) -> float:
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
    aw, bw = set(a.split()), set(b.split())
    return 100.0 * len(aw & bw) / max(1, len(aw | bw))


def stable_pick(options: List[str], seed: str) -> str:
    if not options:
        return ""
    h = int(hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
    return options[h % len(options)]


@dataclass
class Concept:
    id: str
    canonical: str
    family: str
    aliases: List[str]
    definition: str
    features: List[str]
    points: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    contrasts: Dict[str, str] = field(default_factory=dict)
    needs_clarification: bool = False
    clarification: str = ""


CONCEPTS: Dict[str, Concept] = {}


def add(c: Concept) -> None:
    CONCEPTS[c.id] = c

# Core: shares / furud
add(Concept("fard", "الفَرْض", "shares",
    ["الفرض", "الفروض", "نصيب مقدر", "النصيب المقدر", "السهم المقدر", "الحصه المقدره", "الحصة المقدرة", "النصيب الشرعي", "النصيب المحدد", "السهم الشرعي", "ما فرضه الله", "الانصبه المقدره"],
    "الفَرْض هو النصيب المقدّر شرعًا للوارث، كالنصف والربع والثمن والثلثين والثلث والسدس.",
    ["نصيب مقدر شرعا", "النصيب المقدر للوارث", "في كتاب الله", "لا يزيد الا بالرد", "لا ينقص الا بالعول", "حصة مقدرة", "سهم محدد", "فرضه الله للوارث", "النصف والربع والثمن والثلثان والثلث والسدس"],
    ["الفروض المقدرة ستة: النصف، الربع، الثمن، الثلثان، الثلث، السدس.", "الرد والعول يؤثران في مقدار الفرض، لكنهما ليسا اسم النصيب نفسه."],
    ["الزوج له النصف عند عدم الفرع الوارث، وهذا فرض.", "البنت الواحدة لها النصف عند عدم الابن، وهذا فرض."],
    {"awl":"العول سبب نقص الفرض، وليس اسم النصيب المقدر.", "radd":"الرد سبب زيادة بعض الأنصبة، وليس اسم النصيب نفسه."}))
add(Concept("fixed_shares", "الفروض المقدّرة", "shares",
    ["الفروض المقدرة", "عدد الفروض", "كم عدد الفروض", "انواع الفروض", "النصف والربع والثمن", "الفروض الستة"],
    "الفروض المقدّرة هي الأنصبة المحددة شرعًا في المواريث.",
    ["عددها ستة", "النصف", "الربع", "الثمن", "الثلثان", "الثلث", "السدس"],
    ["هي: النصف، الربع، الثمن، الثلثان، الثلث، السدس."], ["الثمن فرض الزوجة مع وجود الفرع الوارث."]))
add(Concept("ashab_furud", "أصحاب الفروض", "shares",
    ["اصحاب الفروض", "أصحاب الفروض", "صاحب فرض", "الورثة بالفرض", "من لهم فروض"],
    "أصحاب الفروض هم الورثة الذين لهم أنصبة مقدّرة شرعًا في حالات معينة.",
    ["وارث له فرض", "له نصيب مقدر", "يرث بالفرض", "من يستحق نصيب مقدر"],
    ["منهم الزوجان، الأبوان في بعض الأحوال، البنات، بنات الابن، الأخوات، الإخوة لأم، والجدات بحسب الشروط."]))
# Awl/Radd/Hajb/Tasib
add(Concept("awl", "العَوْل", "adjustment",
    ["العول", "عول", "تعول", "عالت", "زيادة الفروض", "زادت السهام"],
    "العول هو زيادة مجموع الفروض على التركة، فتُنقص أنصبة أصحاب الفروض بنسبة واحدة حتى تستوعب التركة.",
    ["زيادة مجموع الفروض", "مجموع الفروض اكثر من التركة", "نقص الانصبة", "تزاحم الفروض", "تخفض الانصبة"],
    ["العول لا يلغي وارثًا، بل يخفض الأنصبة كلها بنسبة واحدة."], ["زوج + أم + أختان شقيقتان من صور العول."], {"fard":"الفرض هو النصيب، أما العول فهو سبب نقصه."}))
add(Concept("radd", "الرَّد", "adjustment",
    ["الرد", "رد", "رد الباقي", "رجوع الباقي", "يرد الباقي"],
    "الرد هو رجوع الباقي إلى أصحاب الفروض غير الزوجين عند عدم وجود عاصب، بنسبة فروضهم في طريقة الحساب المعتمدة هنا.",
    ["رجوع الباقي", "عدم وجود عاصب", "يزيد النصيب", "يرد على اصحاب الفروض"],
    ["الرد لا يطبق عند وجود عاصب يأخذ الباقي."], ["بنت فقط: لها النصف فرضًا ويرد عليها الباقي عند عدم العاصب."], {"fard":"الفرض هو النصيب، أما الرد فهو سبب زيادة بعض الأنصبة."}))
add(Concept("hajb", "الحَجْب", "blocking",
    ["الحجب", "حجب", "منع الوارث", "محجوب", "يحجب"],
    "الحجب هو منع وارث من ميراثه كله أو من بعضه بسبب وجود وارث أقوى منه أو أقرب منه.",
    ["منع الوارث", "ينقص النصيب", "حجب حرمان", "حجب نقصان", "وجود وارث اقرب", "وجود وارث اقوى"],
    ["نوعاه: حجب حرمان وحجب نقصان."]))
add(Concept("hajb_hirman", "حجب الحرمان", "blocking", ["حجب الحرمان", "منع كامل", "لا يرث", "حرمان"], "حجب الحرمان هو منع الوارث من الميراث كله بسبب وجود من هو أقرب أو أقوى منه.", ["لا يرث", "صفر ميراث", "منع كامل"], ["الأخ الشقيق يُحجب بالابن أو الأب."]))
add(Concept("hajb_nuqsan", "حجب النقصان", "blocking", ["حجب النقصان", "نقص النصيب", "ينقص نصيبه"], "حجب النقصان هو انتقال الوارث من نصيب أكبر إلى نصيب أقل بسبب وارث آخر.", ["ينقص النصيب", "من الربع الى الثمن", "من الثلث الى السدس", "يرث لكن اقل"], ["الزوجة تنقص من الربع إلى الثمن بوجود الفرع الوارث."]))
add(Concept("tasib", "التعصيب", "residuary", ["التعصيب", "تعصيب", "عاصب", "العصبة", "ياخذ الباقي", "الباقي تعصيبا"], "التعصيب هو أن يرث الوارث بلا سهم مقدر، فيأخذ ما بقي بعد أصحاب الفروض، وقد يأخذ كل المال إذا لم يوجد صاحب فرض.", ["بلا سهم مقدر", "ياخذ الباقي", "بعد اصحاب الفروض", "عاصب بالنفس", "عاصب بالغير", "عاصب مع الغير"], ["أنواعه: عاصب بالنفس، عاصب بالغير، عاصب مع الغير."]))
for cid, canonical, definition, features in [
    ("asaba_binafs", "العاصب بالنفس", "العاصب بالنفس هو ذكر يرث بقوته هو، مثل الابن والأخ الشقيق عند عدم الحاجب.", ["ذكر يرث بقوته", "الابن", "اخ شقيق", "ياخذ الباقي"]),
    ("asaba_bilghayr", "العاصب بالغير", "العاصب بالغير أنثى تصير عصبة بسبب ذكر معها في درجتها، مثل البنت مع الابن.", ["انثى تصير عصبة", "البنت مع الابن", "للذكر مثل حظ الانثيين"]),
    ("asaba_maalghayr", "العاصب مع الغير", "العاصب مع الغير أن تصير الأخت الشقيقة أو لأب عصبة مع فرع وارث أنثى، مثل الأخت الشقيقة مع البنت.", ["الاخت مع البنت", "اخت شقيقة مع بنت", "عصبة مع الغير"]),
]:
    add(Concept(cid, canonical, "residuary", [canonical, canonical.replace("ال", "")], definition, features, [definition]))
# Famous problems and advanced chapters
for cid, canonical, aliases, definition, features, points in [
    ("umariyya", "العُمَرِيَّتان / الغَرَّاوَان", ["العمرية", "العمريتان", "الغراوان", "الغراوين", "زوج وام واب", "زوجة وام واب"], "العُمَرِيَّتان مسألتان فيهما زوج أو زوجة مع أم وأب، وتأخذ الأم ثلث الباقي لا ثلث التركة كلها.", ["زوج وام واب", "زوجة وام واب", "ثلث الباقي", "منسوبة لعمر"], ["في زوج + أم + أب: الزوج النصف، الأم ثلث الباقي، الأب الباقي.", "في زوجة + أم + أب: الزوجة الربع، الأم ثلث الباقي، الأب الباقي."]),
    ("mushtaraka", "المُشْتَرَكة / الحِمَارِيَّة", ["المشتركة", "الحمارية", "الحجريه", "اليمية", "زوج وام واخوة لام واخ شقيق"], "المشتركة مسألة مشهورة يجتمع فيها زوج وأم أو جدة وإخوة لأم وإخوة أشقاء، ولها تفصيل معروف في إشراك الأشقاء مع الإخوة لأم عند من يقول به.", ["زوج", "ام", "اخوة لام", "اخوة اشقاء", "يشرك الاشقاء"], ["هي من المسائل الخاصة التي تحتاج بيان الصورة بدقة قبل الحساب."]),
    ("akdariyya", "الأكدرية", ["الاكدرية", "الأكدرية", "زوج وام وجد واخت", "جد واخت"], "الأكدرية مسألة مشهورة في باب الجد مع الإخوة، وصورتها على المشهور: زوج وأم وجد وأخت.", ["زوج", "ام", "جد", "اخت", "باب الجد مع الاخوة"], ["تحتاج اعتماد طريقة الباب؛ لأنها من المسائل المتقدمة."]),
    ("jadd_with_siblings", "الجد مع الإخوة", ["الجد مع الاخوة", "جد واخوة", "جد واخ شقيق", "جد واخت"], "باب الجد مع الإخوة من أبواب الفرائض الدقيقة، وفيه تفصيل وخلاف في بعض الطرق.", ["جد", "اخوة", "مقاسمة", "ثلث الباقي", "السدس"], ["لا يصح الحساب فيه بالتخمين؛ يطلب النظام الطريقة أو المذهب المعتمد عند الحاجة."]),
    ("dhawu_arham", "ذوو الأرحام", ["ذوو الارحام", "ذوي الارحام", "ارحام", "خال", "خالة", "عمة من الام"], "ذوو الأرحام هم الأقارب الذين ليسوا من أصحاب الفروض ولا العصبات، ولتوريثهم تفصيل ومذاهب.", ["ليسوا اصحاب فروض", "ليسوا عصبات", "القريب غير الوارث بالفرض والتعصيب"], ["يحتاج الباب إلى طريقة توريث معتمدة قبل الحساب التفصيلي."]),
    ("munasakhat", "المناسخات", ["المناسخات", "مناسخة", "مات ثم مات", "بعده مات", "ثم توفي"], "المناسخات هي توالي وفاة وارث أو أكثر قبل قسمة التركة، فينتقل نصيب المتوفى اللاحق إلى ورثته.", ["وفاة متتابعة", "مات بعده", "قبل قسمة التركة", "نصيب وارث مات"], ["تحل على مراحل، ولا يصح دمجها كمسألة واحدة دون ترتيب الوفيات والورثة."]),
    ("takharuj", "التخارج", ["التخارج", "تخارج", "تنازل وارث", "تصالح الورثة"], "التخارج هو اتفاق بعض الورثة على الخروج من التركة مقابل عوض أو بدون عوض وفق ضوابطه.", ["اتفاق الورثة", "تنازل", "عوض", "خروج من التركة"], ["يحتاج تحديد من خرج، وعن ماذا، وبأي عوض، وموافقة الأطراف."]),
    ("kalala", "الكَلالة", ["الكلالة", "كلالة", "لا ولد ولا والد"], "الكلالة في باب المواريث تطلق على حالة من لا ولد له ولا والد، ولها أثر في ميراث الإخوة.", ["لا ولد", "لا والد", "ميراث الاخوة"], ["معنى الكلالة مهم في مسائل الإخوة لأم والإخوة الأشقاء أو لأب."]),
]:
    add(Concept(cid, canonical, "special", aliases, definition, features, points, [], needs_clarification=cid in {"jadd_with_siblings", "dhawu_arham", "akdariyya"}, clarification="هذه من المسائل المتقدمة؛ يلزم تحديد الصورة والمذهب أو الطريقة المعتمدة قبل الحساب التفصيلي."))
# Rights / causes / impediments / assets
for cid, canonical, aliases, definition, features, points in [
    ("estate_rights", "الحقوق المتعلقة بالتركة", ["حقوق التركة", "حقوق التركه", "الحقوق المتعلقة بالتركة", "الحقوق المتعلقه بالتركه", "ترتيب الحقوق", "قبل القسمة", "قبل القسمة", "قبل تقسيم التركة", "الديون قبل الميراث"], "هي الحقوق التي تخرج قبل توزيع التركة على الورثة.", ["حقوق متعلقة بعين التركة", "حقوق متعلقه بعين التركه", "الحقوق المتعلقه بالتركه", "تجهيز الميت", "قضاء الديون", "تنفيذ الوصية", "تقسيم الباقي"], ["الترتيب المختصر: الحقوق المتعلقة بعين التركة، تجهيز الميت، الديون، الوصية الصحيحة، ثم قسمة الباقي."]),
    ("will", "الوصية", ["الوصية", "وصيه", "اوصى", "ثلث التركة"], "الوصية تخرج قبل قسمة الميراث في حدود الثلث ولغير وارث إلا إذا أجاز الورثة.", ["في حدود الثلث", "لغير وارث", "اجازة الورثة"], ["ما زاد على الثلث أو كان لوارث يحتاج إجازة الورثة."]),
    ("debt", "الدَّين", ["الدين", "ديون", "عليه دين", "سداد الدين"], "الدين مقدم على قسمة الميراث، فيخرج من التركة قبل توزيعها.", ["قضاء الديون", "قبل الميراث", "لا تقسم قبل الدين"], ["لا يصح توزيع التركة قبل إخراج الديون الثابتة."]),
    ("causes", "أسباب الإرث", ["اسباب الارث", "سبب الارث", "بماذا يرث"], "أسباب الإرث المشهورة: النكاح، النسب، والولاء عند من يذكره في بابه.", ["النكاح", "النسب", "الولاء"], ["لا يكفي وجود القرابة إن وجد مانع من موانع الإرث."]),
    ("conditions", "شروط الإرث", ["شروط الارث", "متى يرث", "شروط الميراث"], "من شروط الإرث: تحقق موت المورث، وتحقق حياة الوارث بعده، والعلم بجهة الإرث، وانتفاء الموانع.", ["موت المورث", "حياة الوارث", "العلم بجهة الارث", "انتفاء الموانع"], ["إذا جهلت حياة الوارث أو جهة قرابته، لا يصح الحساب بالتخمين."]),
    ("impediments", "موانع الإرث", ["موانع الارث", "موانع الميراث", "لا يرث بسبب", "اختلاف الدين", "القتل"], "موانع الإرث هي أوصاف تمنع الوارث من الميراث مع وجود سبب الإرث، ومن أشهرها القتل واختلاف الدين والرق تاريخيًا.", ["قتل", "اختلاف الدين", "رق", "مانع من الارث"], ["وجود مانع يغير الحكم جذريًا ويجب التصريح به إن وجد."]),
    ("asl_masala", "تأصيل المسألة", ["تأصيل المسألة", "اصل المسألة", "اصل المساله"], "تأصيل المسألة هو إيجاد أصل عددي تُخرج منه فروض الورثة قبل التصحيح أو العول.", ["اصل عددي", "مخارج الفروض", "تخرج منه السهام"], ["يستخدم لتوحيد مخارج الفروض وحساب السهام."]),
    ("tashih", "تصحيح المسألة", ["تصحيح المسألة", "تصحيح المساله", "تصحيح السهام"], "تصحيح المسألة هو تعديل أصل المسألة أو السهام بحيث تنقسم على عدد المستحقين بلا كسر.", ["تنقسم السهام", "عدد الرؤوس", "لا كسر"], ["يظهر عند تعدد أفراد صنف واحد وعدم انقسام السهام عليهم."]),
    ("siham", "السِّهام", ["السهام", "سهم", "اسهم المسألة"], "السهام هي الأجزاء العددية التي يحصل عليها كل وارث من أصل المسألة.", ["اجزاء عددية", "اصل المسألة", "نصيب الوارث"], ["بعد معرفة السهام يمكن تحويلها إلى نسب أو مبالغ مالية."]),
]:
    add(Concept(cid, canonical, "rules", aliases, definition, features, points))
# Heir concepts
for cid, canonical, aliases, definition, features in [
    ("husband", "الزوج", ["الزوج", "زوجها", "جوزها"], "الزوج صاحب فرض؛ له النصف عند عدم الفرع الوارث، والربع مع وجوده.", ["النصف", "الربع", "فرع وارث"]),
    ("wife", "الزوجة", ["الزوجة", "زوجته", "مراته", "حرمته", "الزوجات"], "الزوجة أو الزوجات يشتركن في الربع عند عدم الفرع الوارث، وفي الثمن مع وجوده.", ["الربع", "الثمن", "فرع وارث", "يشتركن"]),
    ("father", "الأب", ["الاب", "أبوه", "والده"], "الأب يرث بحسب وجود الفرع الوارث: فرضًا فقط مع الابن، وفرضًا وتعصيبًا مع البنت، وتعصيبًا عند عدم الفرع.", ["السدس", "تعصيب", "فرع وارث"]),
    ("mother", "الأم", ["الأم", "ام", "امه", "والدته"], "الأم لها الثلث عند عدم الفرع الوارث وعدم جمع من الإخوة، ولها السدس مع الفرع الوارث أو جمع من الإخوة.", ["الثلث", "السدس", "فرع وارث", "جمع من الاخوة"]),
    ("son", "الابن", ["الابن", "ابنه", "ولده", "ولد"], "الابن عاصب بالنفس، ويأخذ الباقي ويعصب البنت معه للذكر مثل حظ الأنثيين.", ["عاصب بالنفس", "للذكر مثل حظ الانثيين"]),
    ("daughter", "البنت", ["البنت", "بنته", "بنية", "بنت"], "البنت لها النصف إن انفردت وعدم الابن، والثلثان للبنات عند التعدد، وتصير عصبة بالغير مع الابن.", ["النصف", "الثلثان", "عصبة بالغير"]),
    ("sons_son", "ابن الابن", ["ابن الابن", "ولد الابن", "حفيد"], "ابن الابن يقوم مقام الابن عند عدم الابن الأقرب، وله أحكام التعصيب والحجب بحسب الدرجة.", ["عاصب", "درجة", "عدم الابن"]),
    ("sons_daughter", "بنت الابن", ["بنت الابن", "حفيدة", "بنت ابن"], "بنت الابن ترث عند عدم من يحجبها، وقد تأخذ السدس تكملة للثلثين مع البنت الواحدة.", ["السدس تكملة الثلثين", "تحجب بالبنتين", "تعصب بابن الابن"]),
    ("full_brother", "الأخ الشقيق", ["اخ شقيق", "اخوه الشقيق", "اخ من الاب والام"], "الأخ الشقيق من العصبات، ويحجب بالأب وبالابن والفرع الوارث الذكر.", ["عاصب", "يحجب بالاب", "يحجب بالابن"]),
    ("paternal_brother", "الأخ لأب", ["اخ لاب", "اخ من الاب", "اخوه من ابوه"], "الأخ لأب عاصب عند عدم الأقوى منه كالأخ الشقيق والأب والفرع الوارث الذكر.", ["عاصب", "يحجبه الشقيق"]),
    ("maternal_sibling", "الأخ أو الأخت لأم", ["اخ لام", "اخت لام", "اخوين من امها", "اخوة لام"], "الإخوة لأم يرثون بالفرض، الواحد له السدس، والاثنان فأكثر لهم الثلث بالسوية، ويحجبون بالفرع الوارث والأصل الذكر.", ["السدس", "الثلث", "بالسوية", "يحجب بالفرع الوارث"]),
    ("uncle", "العَمّ", ["عم", "العم", "عم شقيق", "عم لاب", "اعمام"], "العم من العصبات بالنفس، يأخذ الباقي عند عدم عاصب أقرب منه.", ["عاصب", "ياخذ الباقي", "عصبة بعيدة"]),
    ("cousin", "ابن العم", ["ابن عم", "ابن العم", "اولاد العم"], "ابن العم من العصبات البعيدة، يأخذ الباقي عند عدم عاصب أقرب.", ["عاصب بعيد", "ياخذ الباقي"]),
    ("grandmother", "الجَدَّة", ["الجدة", "جدة", "ام الام", "ام الاب"], "الجدة الصحيحة لها السدس عند عدم الأم، وتشترك الجدات الصحيحات فيه بحسب التفصيل.", ["السدس", "عدم الام"]),
]:
    add(Concept(cid, canonical, "heirs", aliases, definition, features, [definition]))

SOCIAL_PATTERNS = [
    "السلام عليكم", "وعليكم السلام", "ازيك", "ازايك", "كيف حالك", "كيف الحال", "اخبارك", "عامل ايه", "عامله ايه", "هلا", "اهلين", "اهلا", "مرحبا", "مساء الخير", "مساء الفل", "صباح الخير", "صباح الفل", "بخير", "الحمد لله", "تمام", "كويس", "مزيان", "لاباس", "شكرا", "تسلم", "جزاك الله", "بارك الله"
]
DOMAIN_CUES = [
    "ميراث", "مواريث", "فرائض", "تركة", "ترك", "مات", "توفي", "توفيت", "هلك", "ورث", "وارث", "نصيب", "فرض", "عول", "العول", "رد", "الرد", "حجب", "الحجب", "تعصيب", "التعصيب", "زوج", "زوجة", "ابن", "بنت", "اخ", "اخت", "ام", "اب", "عم", "جد", "جدة", "ذوي الارحام", "وصية", "دين", "مناسخات", "مناسخة", "كلالة", "تخارج", "حقوق التركة", "موانع", "أسباب الإرث", "شروط الإرث", "العمرية", "العمريتان", "الغراوان", "المشتركة", "الحمارية", "الأكدرية", "الاكدرية"
]
FOLLOWUP_CUES = ["مش فاهم", "ما افهم", "ما فهمت", "مفهمتش", "مو واضح", "وضح", "وضحلي", "بسط", "بسطها", "اشرح", "مثال", "هات مثال", "بالارقام", "بالأرقام", "ازاي حسبتها", "كيف حسبتها", "ليه"]
REVERSE_CUES = ["ما هو المصطلح", "ما المصطلح", "ما اسم", "ماذا يسمى", "ماذا يطلق", "يطلق على", "وش يسمون", "ايش يسمون", "ايه اسم", "اسم ايه", "يسمى ايه", "ما الذي يطلق"]
DIRECT_DEF_CUES = ["ما معنى", "ما هو", "ما هي", "ما المقصود", "المقصود ب", "يعني ايه", "وش يعني", "شنو يعني", "اشرح", "عرف"]
DIFF_CUES = ["الفرق بين", "ما الفرق", "فرق بين", "ايه الفرق", "وش الفرق"]
LIST_CUES = ["كم عدد", "اذكر", "عدد", "ما هي انواع", "ما انواع", "ما اقسام"]


def detect_dialect(text: str, context: Optional[dict] = None) -> str:
    n = normalize(text)
    if any(x in n for x in ["ازيك", "ازاي", "عامل ايه", "مراتي", "جوزها", "مفهمتش", "مساء الفل"]): return "egyptian"
    if any(x in n for x in ["شلون", "وش", "ابشر", "حياك", "هلا", "ايش", "مو واضح"]): return "gulf"
    if any(x in n for x in ["شو", "قديش", "هيك", "مرتو", "بياخد"]): return "shami"
    if any(x in n for x in ["شنو", "مزيان", "واش", "بزاف", "ديال"]): return "maghrebi"
    if any(x in n for x in ["الزول", "عندو", "ليك"]): return "sudanese"
    if context and context.get("last_dialect"): return str(context.get("last_dialect"))
    return "standard"


def question_type(text: str, context: Optional[dict] = None) -> str:
    n = normalize(text)
    def _cue_hit(c):
        cn = normalize(c)
        return _word(n, cn) if len(cn) <= 3 and " " not in cn else _phrase(n, cn)
    has_domain = any(_cue_hit(c) for c in DOMAIN_CUES)
    if any(_phrase(n, c) for c in FOLLOWUP_CUES): return "followup"
    if any(_phrase(n, c) for c in DIFF_CUES): return "difference"
    if any(_phrase(n, c) for c in REVERSE_CUES): return "reverse_definition"
    if any(_phrase(n, c) for c in LIST_CUES): return "list"
    if any(_phrase(n, c) for c in DIRECT_DEF_CUES) and has_domain: return "definition"
    # social only if no strong domain cue
    if not has_domain and any(_phrase(n, c) for c in SOCIAL_PATTERNS): return "social"
    if not has_domain and len(n.split()) <= 4: return "small_unknown"
    return "domain" if has_domain else "unknown"


def social_reply(text: str, context: Optional[dict] = None, name: str = "") -> str:
    n = normalize(text)
    dialect = detect_dialect(text, context)
    if "السلام" in n:
        if any(x in n for x in ["كيف حالك", "كيف الحال", "ازيك", "اخبارك"]):
            pools = ["وعليكم السلام ورحمة الله وبركاته. الحمد لله بخير، أسأل الله أن تكون بخير.", "وعليكم السلام ورحمة الله وبركاته. بخير ولله الحمد، حياك الله."]
        else:
            pools = ["وعليكم السلام ورحمة الله وبركاته.", "وعليكم السلام ورحمة الله وبركاته، أهلًا وسهلًا."]
    elif any(x in n for x in ["كيف حالك", "كيف الحال", "ازيك", "اخبارك", "عامل ايه"]):
        pools = {
            "egyptian":["الحمد لله بخير، إنت عامل إيه؟", "بخير الحمد لله، ربنا يبارك فيك."],
            "gulf":["الحمد لله بخير، عساك طيب.", "بخير ولله الحمد، حياك الله."],
            "standard":["الحمد لله بخير، أسأل الله أن تكون بخير.", "بخير ولله الحمد."]
        }.get(dialect, ["الحمد لله بخير."])
    elif any(x in n for x in ["مساء الفل", "مساء الخير"]):
        pools = ["مساء النور، حيّاك الله.", "مساء الخير، أهلًا بك."]
    elif any(x in n for x in ["صباح الفل", "صباح الخير"]):
        pools = ["صباح النور، يومك طيب بإذن الله.", "صباح الخير، أهلًا بك."]
    elif any(x in n for x in ["بخير", "الحمد لله", "تمام", "كويس", "مزيان", "لاباس"]):
        pools = ["الحمد لله، ربنا يديم عليك العافية.", "تمام، ربنا يبارك فيك.", "الحمد لله، يسعدني سماع ذلك."]
    elif any(x in n for x in ["شكرا", "تسلم", "جزاك الله", "بارك الله"]):
        pools = ["العفو، بارك الله فيك.", "وإياكم، في خدمتك." ]
    else:
        pools = ["أهلًا بك.", "مرحبًا، حياك الله."]
    return stable_pick(pools, f"social:{text}:{name}:{context.get('last_seen_at','') if context else ''}")


def score_concept(text: str, concept: Concept, qtype: str) -> Tuple[float, List[str]]:
    n = normalize(text)
    score, reasons = 0.0, []
    # alias hit is strong in direct definition, weaker in reverse definition because mentioned terms can be constraints.
    for a in concept.aliases:
        if _alias(n, a):
            w = 9.0 if qtype != "reverse_definition" else 3.5
            score += w; reasons.append(f"alias:{a}")
    # features are essential for reverse definitions.
    for f in concept.features:
        fn = normalize(f)
        if fn and ((len(fn) <= 3 and " " not in fn and _word(n, fn)) or (len(fn) > 3 and fn in n)):
            score += 8.0; reasons.append(f"feature:{f}")
        else:
            fs = fuzzy(fn, n)
            if fs >= 92:
                score += 4.0; reasons.append(f"fuzzy_feature:{f}:{fs:.0f}")
            elif fs >= 84 and qtype == "reverse_definition":
                score += 2.0; reasons.append(f"weak_feature:{f}:{fs:.0f}")
    # reverse-definition clues should boost the defined thing, not the modifying terms.
    if qtype == "reverse_definition":
        if concept.id == "fard" and ("نصيب" in n or "سهم" in n or "حصه" in n or "حصة" in n) and ("مقدر" in n or "محد" in n or "شرع" in n or "كتاب الله" in n):
            score += 18; reasons.append("reverse_defined_share")
        if concept.id == "fard" and "رد" in n and "عول" in n and ("يزيد" in n or "ينقص" in n):
            score += 18; reasons.append("radd_awl_constraints_define_fard")
        if concept.id in {"awl", "radd"} and ("يزيد" in n or "ينقص" in n) and ("نصيب" in n or "سهم" in n):
            score -= 10; reasons.append("mentioned_as_constraint_not_target")
    # list/listing queries
    if qtype == "list" and concept.id == "fixed_shares" and any(x in n for x in ["فروض", "الفروض", "النصف", "الربع"]):
        score += 20; reasons.append("list_fixed_shares")
    return score, reasons


def rank_concepts(text: str, qtype: str) -> List[Tuple[str, float, List[str]]]:
    rows = []
    for cid, c in CONCEPTS.items():
        s, reasons = score_concept(text, c, qtype)
        if s > 0:
            rows.append((cid, s, reasons))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows


def detect_concept_key(text: str) -> str:
    qt = question_type(text)
    rows = rank_concepts(text, qt)
    return rows[0][0] if rows and rows[0][1] >= 8 else ""


def _concepts_mentioned(text: str) -> List[str]:
    n = normalize(text)
    out = []
    for cid, c in CONCEPTS.items():
        if any(_alias(n, a) for a in c.aliases):
            out.append(cid)
    # stable unique
    seen, res = set(), []
    for cid in out:
        if cid not in seen:
            seen.add(cid); res.append(cid)
    return res


def _preamble(name: str = "", seed: str = "") -> str:
    who = f" يا {name}" if name else ""
    options = [
        f"بسم الله الرحمن الرحيم. بناءً على ما ورد في سؤالك{who}، فهذا بيان المسألة:",
        f"بسم الله، والصلاة والسلام على رسول الله. بعد فهم السؤال{who}، فالجواب كالآتي:",
        f"بسم الله الرحمن الرحيم. المقصود من سؤالك{who} يحتاج بيانًا اصطلاحيًا، وبيانه كما يلي:",
    ]
    return stable_pick(options, f"pre:{seed}:{name}")


def compose_concept_answer(c: Concept, qtype: str, text: str, name: str = "", context: Optional[dict] = None, include_preamble: bool = True) -> str:
    pre = _preamble(name, text) + "\n\n" if include_preamble else ""
    if qtype == "reverse_definition":
        head = f"المصطلح المقصود هو: {c.canonical}."
    elif qtype == "list" and c.id == "fixed_shares":
        head = "الفروض المقدّرة في المواريث ستة."
    else:
        head = f"{c.canonical}:"
    body = [head, "", c.definition]
    if c.points:
        body += ["", "النقاط المهمة:"] + [f"- {p}" for p in c.points[:5]]
    # Contrast with distractors mentioned in question
    mentioned = [m for m in _concepts_mentioned(text) if m != c.id]
    contrasts = []
    for m in mentioned:
        if m in c.contrasts:
            contrasts.append(c.contrasts[m])
        elif c.id in CONCEPTS.get(m, c).contrasts:
            contrasts.append(CONCEPTS[m].contrasts[c.id])
    if contrasts:
        body += ["", "تنبيه على الالتباس:"] + [f"- {x}" for x in contrasts[:3]]
    if c.examples and any(k in normalize(text) for k in ["مثال", "وضح", "بسط", "مش فاهم", "ما افهم"]):
        body += ["", "مثال:", c.examples[0]]
    if c.needs_clarification:
        body += ["", "تنبيه:", c.clarification]
    return pre + "\n".join(body).strip()


def compose_difference(text: str, name: str = "") -> Optional[str]:
    mentioned = _concepts_mentioned(text)
    if len(mentioned) < 2:
        rows = rank_concepts(text, "difference")
        mentioned = [r[0] for r in rows[:2]]
    if len(mentioned) < 2:
        return None
    a, b = CONCEPTS[mentioned[0]], CONCEPTS[mentioned[1]]
    lines = [_preamble(name, text), "", f"الفرق بين {a.canonical} و{b.canonical}:", "", f"- {a.canonical}: {a.definition}", f"- {b.canonical}: {b.definition}"]
    if b.id in a.contrasts:
        lines.append(f"- الخلاصة: {a.contrasts[b.id]}")
    elif a.id in b.contrasts:
        lines.append(f"- الخلاصة: {b.contrasts[a.id]}")
    return "\n".join(lines)


def followup_reply(text: str, context: Optional[dict] = None, name: str = "") -> str:
    context = context or {}
    last = context.get("last_concept") or ""
    c = CONCEPTS.get(str(last))
    n = normalize(text)
    if c:
        if any(x in n for x in ["مثال", "بالارقام", "بالأرقام"]):
            ex = c.examples[0] if c.examples else "أحتاج مثالًا محددًا أو مسألة حتى أطبقه عليها بدقة."
            return f"تمام، مثال مبسّط على {c.canonical}:\n\n{ex}"
        return compose_concept_answer(c, "definition", text, name=name, context=context, include_preamble=False)
    return "وضح لي أي نقطة تريد تبسيطها من السؤال السابق، أو أعد ذكر المصطلح نفسه وسأشرحه لك خطوة بخطوة."


def answer(text: str, context: Optional[dict] = None, name: str = "") -> Optional[Dict[str, Any]]:
    qt = question_type(text, context)
    if qt == "social":
        return {"answer": social_reply(text, context, name), "intent": qt, "answer_kind": "social", "confidence": 1.0}
    if qt == "followup":
        return {"answer": followup_reply(text, context, name), "intent": qt, "answer_kind": "followup", "confidence": 0.9, "concept_id": (context or {}).get("last_concept")}
    if qt == "difference":
        ans = compose_difference(text, name)
        if ans:
            return {"answer": ans, "intent": qt, "answer_kind": "fiqh", "confidence": 0.84}
    if qt in {"definition", "reverse_definition", "list", "domain"}:
        rows = rank_concepts(text, qt)
        threshold = 8 if qt == "definition" else 12
        if rows and rows[0][1] >= threshold:
            top, score, reasons = rows[0]
            # If second is close, but top has explicit reverse constraints, still allow. Otherwise ask clarification.
            if len(rows) > 1 and rows[1][1] >= score - 2 and qt == "domain":
                c1, c2 = CONCEPTS[rows[0][0]], CONCEPTS[rows[1][0]]
                return {"answer": f"السؤال يحتمل أكثر من مصطلح: {c1.canonical} أو {c2.canonical}. حدّد أيهما تريد شرحه حتى لا أجيب بتخمين.", "intent": qt, "answer_kind": "clarification", "confidence": 0.45}
            c = CONCEPTS[top]
            return {"answer": compose_concept_answer(c, qt, text, name=name, context=context, include_preamble=True), "intent": qt, "answer_kind": "fiqh", "confidence": min(0.99, score / 35), "concept_id": top, "reasons": reasons}
    if qt in {"small_unknown", "unknown"}:
        return None
    return None


def export_ontology(path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {cid: {"canonical": c.canonical, "family": c.family, "aliases": c.aliases, "definition": c.definition, "features": c.features, "points": c.points, "examples": c.examples, "contrasts": c.contrasts, "needs_clarification": c.needs_clarification} for cid, c in CONCEPTS.items()}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
