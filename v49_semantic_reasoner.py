# -*- coding: utf-8 -*-
"""
Mawareth AI v49 — Scholarly Semantic Reasoner

Purpose
-------
A non-RAG, non-fixed-answer, non-patch semantic layer for inheritance terminology.
It solves the class of errors where the system selects a mentioned concept (e.g. العول)
instead of the concept described by the full definition (e.g. الفرض), and where negated
features (e.g. ليس له سهم مقدر) must actively reject the opposite concept and select
العاصب/التعصيب.

Design
------
- Ontology-driven: concepts have aliases, positive semantic signatures, negative/contrast
  cues, and explanation parts.
- Description matching: reverse-definition questions are matched against the described
  target clause, not incidental modifier words.
- Negation-aware: phrases such as "ليس له سهم مقدر" penalize الفرض and reward العاصب.
- Calculation guard: inheritance calculation scenarios are passed to the runtime engine.
- Social guard: non-domain chat is answered socially and never sent to the fatwa engine.

This is not a dictionary of question/answer pairs. It is a semantic scoring engine over
structured scholarly concepts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
import re, hashlib

try:
    from rapidfuzz import fuzz as _fuzz
except Exception:  # pragma: no cover
    _fuzz = None

try:
    import v48_scholarly_intelligence_engine as v48
except Exception:  # pragma: no cover
    v48 = None

try:
    import v47_full_understanding_engine as v47
except Exception:  # pragma: no cover
    v47 = None

TRANS = str.maketrans({
    "أ":"ا", "إ":"ا", "آ":"ا", "ٱ":"ا", "ى":"ي", "ة":"ه", "ؤ":"و", "ئ":"ي",
    "٠":"0", "١":"1", "٢":"2", "٣":"3", "٤":"4", "٥":"5", "٦":"6", "٧":"7", "٨":"8", "٩":"9",
    "۰":"0", "۱":"1", "۲":"2", "۳":"3", "۴":"4", "۵":"5", "۶":"6", "۷":"7", "۸":"8", "۹":"9",
})
DIAC = re.compile(r"[\u064b-\u0652\u0670\u0640]")
PUNCT = re.compile(r"[\u061f؟?!.,;:،؛\[\]{}()<>\"'`~|\\/]+")


def normalize(text: str) -> str:
    if v48 is not None:
        try:
            return v48.normalize(text)
        except Exception:
            pass
    s = str(text or "")
    s = s.replace("\ufeff", "").replace("\u200f", "").replace("\u200e", "")
    s = DIAC.sub("", s).translate(TRANS)
    s = PUNCT.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def stable_pick(options: List[str], seed: str) -> str:
    if not options:
        return ""
    h = int(hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
    return options[h % len(options)]


def word_hit(n: str, w: str) -> bool:
    w = normalize(w)
    if not w:
        return False
    if " " in w or len(w) > 4:
        return w in n
    return bool(re.search(r"(^|\s)(?:[وفبلك]?ال|[وفبلك])?" + re.escape(w) + r"($|\s)", n))


def phrase_hit(n: str, p: str) -> bool:
    p = normalize(p)
    return bool(p and p in n)


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


@dataclass
class SemanticConcept:
    id: str
    canonical: str
    family: str
    aliases: List[str]
    definition: str
    positive: List[str]
    negative: List[str] = field(default_factory=list)  # cues that reject this concept
    points: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    contrasts: Dict[str, str] = field(default_factory=dict)
    answer_labels: List[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification: str = ""


CONCEPTS: Dict[str, SemanticConcept] = {}


def add(c: SemanticConcept) -> None:
    CONCEPTS[c.id] = c


# Core concepts: structured semantic signatures.
add(SemanticConcept(
    id="fard", canonical="الفَرْض", family="shares",
    aliases=["الفرض", "الفروض", "الفروض المقدرة", "النصيب المقدر", "السهم المقدر", "الحصة المقدرة", "النصيب الشرعي", "النصيب المحدد", "السهم الشرعي", "ما فرضه الله"],
    definition="الفَرْض هو النصيب المقدّر شرعًا للوارث، كالنصف والربع والثمن والثلثين والثلث والسدس.",
    positive=["نصيب مقدر شرعا", "سهم مقدر شرعا", "حصة مقدرة", "النصيب المقدر للوارث", "في كتاب الله", "فرضه الله", "لا يزيد الا بالرد", "لا ينقص الا بالعول", "النصف والربع والثمن والثلثان والثلث والسدس"],
    negative=["ليس له سهم مقدر", "ليس له نصيب مقدر", "بلا سهم مقدر", "لا سهم مقدر له", "ياخذ الباقي", "ما تبقى بعد اصحاب الفروض", "كل المال اذا انفرد"],
    points=["الفروض المقدرة ستة: النصف، الربع، الثمن، الثلثان، الثلث، السدس.", "العول والرد يؤثران في مقدار الفرض، لكنهما ليسا اسم النصيب نفسه."],
    contrasts={"asib":"العاصب لا يكون له سهم مقدر، بل يأخذ الباقي.", "awl":"العول سبب نقص الفرض، وليس اسم النصيب.", "radd":"الرد سبب زيادة بعض الأنصبة، وليس اسم النصيب."},
    answer_labels=["الفَرْض"]
))
add(SemanticConcept(
    id="asib", canonical="العاصِب", family="residuary",
    aliases=["العاصب", "العصبة", "وارث عاصب", "العاصب بنفسه", "صاحب التعصيب"],
    definition="العاصب هو الوارث الذي ليس له سهم مقدر، فيأخذ ما بقي بعد أصحاب الفروض، وقد يأخذ كل المال إذا انفرد.",
    positive=["ليس له سهم مقدر", "ليس له نصيب مقدر", "بلا سهم مقدر", "لا سهم مقدر له", "ياخذ ما تبقى", "ياخذ الباقي", "الباقي بعد اصحاب الفروض", "بعد اصحاب الفروض", "كل المال اذا انفرد", "كل التركة اذا انفرد", "وارث بلا فرض", "يرث بالتعصيب", "ما بقي فهو لاولى رجل ذكر"],
    negative=["النصيب المقدر شرعا", "الفروض المقدرة", "النصف والربع والثمن", "لا يزيد الا بالرد", "لا ينقص الا بالعول"],
    points=["العاصب يأخذ كل التركة عند عدم أصحاب الفروض.", "ويأخذ الباقي بعد أصحاب الفروض إن وجدوا.", "وقد لا يأخذ شيئًا إذا استغرقت الفروض التركة."],
    examples=["الأخ الشقيق مع بنت واحدة: البنت لها النصف، والأخ الشقيق يأخذ الباقي تعصيبًا."],
    contrasts={"fard":"الفرض سهم مقدر، أما العاصب فلا سهم مقدر له."},
    answer_labels=["العاصب", "العَصَبَة"]
))
add(SemanticConcept(
    id="tasib", canonical="التعصيب", family="residuary",
    aliases=["التعصيب", "تعصيب", "الإرث بالتعصيب", "ميراث العصبة"],
    definition="التعصيب هو الإرث بلا سهم مقدر؛ فيأخذ العاصب ما بقي بعد أصحاب الفروض، أو يأخذ كل المال عند الانفراد.",
    positive=["الارث بلا سهم مقدر", "يرث بلا سهم مقدر", "يرث بالتعصيب", "ياخذ الباقي", "ما تبقى بعد اصحاب الفروض", "كل المال اذا انفرد", "عاصب بالنفس", "عاصب بالغير", "عاصب مع الغير"],
    negative=["النصيب المقدر شرعا", "الفرض", "الفروض الستة"],
    points=["التعصيب يكون بالنفس أو بالغير أو مع الغير."],
    examples=["الابن عاصب بالنفس؛ يأخذ الباقي، ويقسم مع البنت للذكر مثل حظ الأنثيين."],
    answer_labels=["التعصيب"]
))
add(SemanticConcept("asaba_binafs", "العاصب بالنفس", "residuary", ["العاصب بالنفس", "عاصب بنفسه", "ذكر يرث بقوته"], "العاصب بالنفس هو ذكر يرث بقوته هو، كالابن والأخ والعم عند تحقق الشروط.", ["ذكر يرث بقوته", "يرث بنفسه", "الابن", "الأخ الشقيق", "العم", "عاصب بالنفس"], ["انثى تصير عصبة بذكر"], ["هو قسم من أقسام العصبة."]))
add(SemanticConcept("asaba_bilghayr", "العاصب بالغير", "residuary", ["العاصب بالغير", "عاصبة بالغير", "البنت مع الابن"], "العاصب بالغير أنثى تصير عصبة بسبب ذكر معها في درجتها، مثل البنت مع الابن.", ["انثى تصير عصبة", "بسبب ذكر معها", "البنت مع الابن", "للذكر مثل حظ الانثيين"], ["ذكر يرث بقوته"], ["مثاله: البنت مع الابن."]))
add(SemanticConcept("asaba_maalghayr", "العاصب مع الغير", "residuary", ["العاصب مع الغير", "عاصبة مع الغير", "الأخت مع البنت"], "العاصب مع الغير أن تصير الأخت الشقيقة أو لأب عصبة مع فرع وارث أنثى.", ["الأخت مع البنت", "اخت شقيقة مع بنت", "عصبة مع الغير", "فرع وارث انثى"], [], ["مثاله: الأخت الشقيقة مع البنت."]))
add(SemanticConcept("awl", "العَوْل", "adjustment", ["العول", "عول", "تعول", "عالت", "زيادة الفروض", "زادت السهام"], "العول هو زيادة مجموع الفروض على التركة، فتُنقص أنصبة أصحاب الفروض بنسبة واحدة حتى تستوعب التركة.", ["زيادة مجموع الفروض", "الفروض اكثر من التركة", "نقص الانصبة", "تزاحم الفروض", "تخفض الانصبة"], ["نصيب مقدر شرعا", "ياخذ الباقي"], ["العول لا يلغي وارثًا، بل يخفض الأنصبة بنسبة واحدة."]))
add(SemanticConcept("radd", "الرَّد", "adjustment", ["الرد", "رد", "رد الباقي", "رجوع الباقي"], "الرد هو رجوع الباقي إلى أصحاب الفروض غير الزوجين عند عدم وجود عاصب، بنسبة فروضهم في الطريقة المعتمدة هنا.", ["رجوع الباقي", "عدم وجود عاصب", "يزيد النصيب", "يرد على اصحاب الفروض"], ["عاصب موجود", "ياخذ الباقي"], ["الرد لا يطبق عند وجود عاصب يأخذ الباقي."]))
add(SemanticConcept("hajb", "الحَجْب", "blocking", ["الحجب", "حجب", "منع الوارث", "محجوب"], "الحجب هو منع وارث من ميراثه كله أو من بعضه بسبب وجود وارث أقوى منه أو أقرب منه.", ["منع وارث", "منع من الميراث", "ينقص النصيب", "حجب حرمان", "حجب نقصان", "وارث اقرب", "وارث اقوى"], [], ["نوعاه: حجب حرمان وحجب نقصان."]))
add(SemanticConcept("hajb_hirman", "حجب الحرمان", "blocking", ["حجب الحرمان", "منع كامل", "لا يرث", "حرمان"], "حجب الحرمان هو منع الوارث من الميراث كله بسبب وجود من هو أقرب أو أقوى منه.", ["لا يرث", "صفر ميراث", "منع كامل", "يحرم من كل الميراث"], [], ["الأخ الشقيق يحجب بالابن أو الأب."]))
add(SemanticConcept("hajb_nuqsan", "حجب النقصان", "blocking", ["حجب النقصان", "نقص النصيب", "ينقص نصيبه"], "حجب النقصان هو انتقال الوارث من نصيب أكبر إلى نصيب أقل بسبب وارث آخر.", ["ينقص النصيب", "من الربع الى الثمن", "من الثلث الى السدس", "يرث لكن اقل"], [], ["الزوجة تنقص من الربع إلى الثمن بوجود الفرع الوارث."]))
add(SemanticConcept("fixed_shares", "الفروض المقدّرة", "shares", ["الفروض المقدرة", "عدد الفروض", "الفروض الستة"], "الفروض المقدرة هي الأنصبة المحددة شرعًا: النصف، الربع، الثمن، الثلثان، الثلث، السدس.", ["عددها ستة", "النصف", "الربع", "الثمن", "الثلثان", "الثلث", "السدس"], [], ["هي: النصف، الربع، الثمن، الثلثان، الثلث، السدس."]))
add(SemanticConcept("ashab_furud", "أصحاب الفروض", "shares", ["اصحاب الفروض", "صاحب فرض", "الورثة بالفرض"], "أصحاب الفروض هم الورثة الذين لهم أنصبة مقدرة شرعًا في حالات معينة.", ["وارث له فرض", "له نصيب مقدر", "يرث بالفرض", "من يستحق نصيب مقدر"], ["ليس له سهم مقدر"], ["منهم الزوجان والأبوان والبنات وبنات الابن والإخوة لأم وغيرهم بحسب الشروط."]))
add(SemanticConcept("estate_rights", "الحقوق المتعلقة بالتركة", "estate", ["حقوق التركة", "الحقوق المتعلقة بالتركة", "ترتيب الحقوق", "قبل تقسيم التركة"], "هي الحقوق التي تقدم على قسمة الميراث: الحقوق المتعلقة بعين التركة، ثم تجهيز الميت، ثم الديون، ثم الوصية الصحيحة، ثم قسمة الباقي.", ["قبل تقسيم التركة", "تجهيز الميت", "قضاء الديون", "تنفيذ الوصية", "تقسيم الباقي"], [], ["لا تقسم التركة قبل إخراج الحقوق المقدمة."]))
add(SemanticConcept("umariyya", "العُمَرِيَّتان / الغَرَّاوَان", "special", ["العمرية", "العمريتان", "الغراوان", "الغراوين"], "العُمَرِيَّتان مسألتان فيهما زوج أو زوجة مع أم وأب، وتأخذ الأم ثلث الباقي لا ثلث التركة كلها.", ["زوج وام واب", "زوجة وام واب", "ثلث الباقي", "منسوبة لعمر"], [], ["فيهما تأخذ الأم ثلث الباقي بعد نصيب الزوج أو الزوجة."]))
add(SemanticConcept("mushtaraka", "المُشْتَرَكة / الحِمَارِيَّة", "special", ["المشتركة", "الحمارية", "الحجرية", "اليمية"], "المشتركة مسألة مشهورة يجتمع فيها زوج وأم أو جدة وإخوة لأم وإخوة أشقاء، ولها تفصيل معروف في إشراك الأشقاء مع الإخوة لأم عند من يقول به.", ["زوج", "ام", "اخوة لام", "اخوة اشقاء", "يشرك الاشقاء"], [], ["تحتاج بيان الصورة بدقة قبل الحساب."]))
add(SemanticConcept("akdariyya", "الأكدرية", "special", ["الأكدرية", "الاكدرية"], "الأكدرية مسألة مشهورة في باب الجد مع الإخوة، وصورتها على المشهور: زوج وأم وجد وأخت.", ["زوج", "ام", "جد", "اخت", "باب الجد مع الاخوة"], [], ["تحتاج اعتماد طريقة باب الجد مع الإخوة."]))
add(SemanticConcept("munasakhat", "المناسخات", "advanced", ["المناسخات", "مناسخة", "مات ثم مات", "بعده مات"], "المناسخات هي مسائل وفاة متتابعة يموت فيها بعض الورثة قبل قسمة التركة أو قبل استلام نصيبه، فتحتاج تقسيمًا على مراحل.", ["وفاة متتابعة", "مات ثم مات", "توزيع على مراحل", "نصيب وارث مات"], [], ["تحل بترتيب الوفيات وتحويل نصيب المتوفى اللاحق إلى تركة مستقلة."]))
add(SemanticConcept("dhawu_arham", "ذوو الأرحام", "advanced", ["ذوو الارحام", "ذوي الارحام", "ارحام", "خال", "خالة"], "ذوو الأرحام هم أقارب ليسوا من أصحاب الفروض ولا العصبات، وتوريثهم له تفصيل بحسب الطريقة المعتمدة.", ["ليسوا اصحاب فروض", "ليسوا عصبات", "اقارب غير وارثين بالفرض والتعصيب"], [], ["يحتاج الباب إلى طريقة توريث معتمدة قبل الحساب التفصيلي."]))

# General routing cues.
SOCIAL_CUES = {"السلام عليكم", "وعليكم السلام", "ازيك", "ازايك", "كيف حالك", "كيف الحال", "عامل ايه", "اخبارك", "هلا", "اهلين", "اهلا", "مرحبا", "مساء الخير", "مساء الفل", "صباح الخير", "صباح الفل", "بخير", "الحمد لله", "تمام", "كويس", "مزيان", "لاباس", "شكرا", "تسلم", "جزاك الله"}
FOLLOWUP_CUES = {"مش فاهم", "ما افهم", "ما فهمت", "مفهمتش", "مو واضح", "وضح", "وضحلي", "بسط", "بسطها", "اشرح ابسط", "سهلها", "مثال", "هات مثال", "بالارقام", "بالأرقام", "كيف حسبتها", "ازاي حسبتها", "ليه"}
DEATH_CUES = {"مات", "توفي", "توفيت", "ماتت", "هلك", "ترك", "تركت", "خلف", "خلّف", "ساب"}
HEIR_CUES = {"زوج", "زوجة", "ابن", "بنت", "ام", "اب", "اخ", "اخت", "جد", "جدة", "عم", "بنات", "اولاد", "عيال", "ابناء"}
REVERSE_CUES = {"ما هو المصطلح", "ما المصطلح", "ما اسم", "ماذا يسمى", "ماذا يسمي", "ماذا يطلق", "يطلق على", "وش يسمون", "ايش يسمون", "شنو يسمون", "ايه اسم", "اسم ايه", "يسمى ايه", "ما الذي يطلق"}
DIRECT_DEF_CUES = {"ما معنى", "ما هو", "ما هي", "ما المقصود", "المقصود ب", "يعني ايه", "وش يعني", "شنو يعني", "عرف", "اشرح"}
DIFF_CUES = {"الفرق بين", "ما الفرق", "فرق بين", "ايه الفرق", "وش الفرق", "شنو الفرق"}
LIST_CUES = {"كم عدد", "اذكر", "عدد", "ما هي انواع", "ما انواع", "ما اقسام", "اقسام"}


def contains_any(n: str, cues) -> bool:
    return any(phrase_hit(n, c) for c in cues)


def domain_score(n: str) -> int:
    score = 0
    for c in list(DEATH_CUES) + list(HEIR_CUES):
        if word_hit(n, c):
            score += 3
    for c in CONCEPTS.values():
        for a in c.aliases[:4] + [c.canonical]:
            an = normalize(a)
            if an and (an in n if len(an) > 4 or " " in an else word_hit(n, an)):
                score += 2
                break
    for k in ["ميراث", "مواريث", "فرائض", "تركة", "وارث", "ورثة", "نصيب", "سهم", "حصة"]:
        if word_hit(n, k):
            score += 2
    return score


def is_calculation_like(text: str) -> bool:
    n = normalize(text)
    return any(word_hit(n, c) for c in DEATH_CUES) and any(word_hit(n, h) for h in HEIR_CUES)


def qtype(text: str) -> str:
    n = normalize(text)
    if contains_any(n, FOLLOWUP_CUES): return "followup"
    if contains_any(n, DIFF_CUES): return "difference"
    if contains_any(n, REVERSE_CUES): return "reverse_definition"
    if contains_any(n, LIST_CUES): return "list"
    if is_calculation_like(text): return "inheritance_calculation"
    if contains_any(n, DIRECT_DEF_CUES) and domain_score(n) >= 2: return "definition"
    if domain_score(n) < 2 and (contains_any(n, SOCIAL_CUES) or len(n.split()) <= 4): return "social"
    if domain_score(n) >= 2: return "domain"
    return "unknown"


def split_target_modifiers(text: str, typ: str) -> Tuple[str, str]:
    n = normalize(text)
    if typ != "reverse_definition":
        return n, ""
    # Remove lead phrases and keep the described entity. This is generic, not per-question.
    n = re.sub(r"^(ما هو المصطلح|ما المصطلح|ما اسم|ماذا يسمى|ماذا يسمي|ماذا يطلق|ما الذي يطلق|وش يسمون|ايش يسمون|ايه اسم|اسم ايه)\s+", "", n).strip()
    m = re.search(r"(?:يطلق علي|يطلق على|يسمى|يسمي)\s+(.+)", n)
    if m:
        n = m.group(1).strip()
    parts = re.split(r"\b(والذي|والتي)\b", n, maxsplit=1)
    if len(parts) >= 3 and parts[0].strip():
        return parts[0].strip(), " ".join(parts[1:]).strip()
    return n, ""


NEGATORS = ["ليس", "ليست", "بلا", "بدون", "لا", "غير", "ما له", "ماله", "لا يوجد", "لا يملك"]


def negated_near(text: str, phrase: str, window: int = 5) -> bool:
    n = normalize(text)
    phrase = normalize(phrase)
    if not phrase:
        return False
    words = n.split()
    pwords = phrase.split()
    if not pwords:
        return False
    for i in range(len(words)):
        if words[i:i+len(pwords)] == pwords:
            start = max(0, i-window)
            before = " ".join(words[start:i])
            if any(normalize(neg) in before for neg in NEGATORS):
                return True
    return False


def semantic_phrase_score(segment: str, phrase: str) -> float:
    s = normalize(segment); p = normalize(phrase)
    if not s or not p: return 0.0
    if p in s: return 1.0
    # token evidence: requiring important words to overlap.
    ptoks = set(p.split()); stoks = set(s.split())
    overlap = len(ptoks & stoks) / max(1, len(ptoks))
    if overlap >= 0.72: return 0.75
    sim = fuzzy(p, s)
    if sim >= 88: return 0.70
    if sim >= 80: return 0.45
    return 0.0


def score_concept(text: str, c: SemanticConcept, typ: str) -> Tuple[float, List[str]]:
    n = normalize(text)
    target, modifiers = split_target_modifiers(text, typ)
    whole_weight = 0.75 if typ == "reverse_definition" else 1.0
    score = 0.0; reasons: List[str] = []

    # Alias evidence. In reverse definitions, target evidence matters more than modifier words.
    for a in c.aliases + [c.canonical]:
        an = normalize(a)
        if not an: continue
        hit_target = (an in target if len(an) > 4 or " " in an else word_hit(target, an))
        hit_whole = (an in n if len(an) > 4 or " " in an else word_hit(n, an))
        if hit_target:
            score += 6; reasons.append(f"alias_target:{a}")
        elif hit_whole and typ != "reverse_definition":
            score += 5; reasons.append(f"alias:{a}")
        elif hit_whole:
            score += 0.5; reasons.append(f"alias_modifier:{a}")

    # Positive signatures.
    for p in c.positive:
        # if positive is explicitly negated, it should not count as positive evidence.
        if negated_near(target, p) or negated_near(n, p):
            score -= 3; reasons.append(f"positive_negated:{p[:28]}")
            continue
        mt = semantic_phrase_score(target, p)
        mw = semantic_phrase_score(n, p) * whole_weight
        if mt:
            score += 10 * mt; reasons.append(f"positive_target:{p[:28]}:{mt:.2f}")
        elif typ != "reverse_definition" and mw:
            score += 7 * mw; reasons.append(f"positive:{p[:28]}:{mw:.2f}")
        elif typ == "reverse_definition" and mw >= 0.70:
            # modifier-only positives are weak evidence.
            score += 1.5; reasons.append(f"positive_modifier_weak:{p[:28]}")

    # Negative/contrast signatures actively reject concepts.
    for neg in c.negative:
        mn = max(semantic_phrase_score(target, neg), semantic_phrase_score(n, neg) * whole_weight)
        if mn:
            score -= 12 * mn; reasons.append(f"negative:{neg[:28]}:{mn:.2f}")

    # Generic semantic class rules, not tied to a particular question.
    if typ == "reverse_definition":
        # Defined share: require non-negated "share" + "defined/legally fixed" cues.
        has_share = any(word_hit(target, x) for x in ["نصيب", "سهم", "حصة", "حصه"])
        has_fixed = any(x in target for x in ["مقدر", "محد", "محدد", "شرع", "كتاب الله", "فرضه الله"])
        share_negated = any(x in target for x in ["ليس له سهم", "ليس له نصيب", "بلا سهم", "بدون سهم", "لا سهم مقدر", "لا نصيب مقدر"])
        if c.id == "fard" and has_share and has_fixed and not share_negated:
            score += 20; reasons.append("defined_share_semantic")
        if c.id in {"asib", "tasib"} and share_negated:
            score += 22; reasons.append("negated_fixed_share_semantic")
        if c.id in {"asib", "tasib"} and any(x in target for x in ["ياخذ ما تبقي", "ياخذ ما تبقى", "ياخذ الباقي", "ما تبقي من التركه", "ما تبقى من التركه", "بعد اصحاب الفروض", "كل المال اذا انفرد", "كل التركه اذا انفرد"]):
            score += 20; reasons.append("residuary_semantic")
        if c.id == "tasib" and any(x in n for x in ["الارث", "طريقة", "نوع الارث"]):
            score += 6; reasons.append("process_word_tasib")
        if c.id == "asib" and any(x in n for x in ["الوارث", "وارث", "الشخص", "من هو"]):
            score += 7; reasons.append("heir_word_asib")
        if c.id == "fard" and share_negated:
            score -= 25; reasons.append("fard_rejected_by_negation")

    if typ == "list" and c.id == "fixed_shares" and any(x in n for x in ["الفروض", "النصف", "الربع", "الثمن", "عدد الفروض"]):
        score += 20; reasons.append("list_fixed_shares")

    return score, reasons


def rank(text: str, typ: Optional[str] = None) -> List[Tuple[str, float, List[str]]]:
    typ = typ or qtype(text)
    rows = []
    for cid, c in CONCEPTS.items():
        s, r = score_concept(text, c, typ)
        if s > 0:
            rows.append((cid, s, r))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows


def detect_dialect(text: str, context: Optional[dict] = None) -> str:
    if v48 is not None:
        try:
            return v48.detect_dialect(text, context)
        except Exception:
            pass
    return "standard"


def social_reply(text: str, context: Optional[dict] = None, name: str = "") -> str:
    if v48 is not None:
        try:
            return v48.social_reply(text, context, name)
        except Exception:
            pass
    return "أهلًا بك."


def preamble(name: str, text: str) -> str:
    who = f" يا {name}" if name else ""
    opts = [
        f"بسم الله الرحمن الرحيم. بناءً على ما ورد في سؤالك{who}، فهذا بيان المسألة:",
        f"بسم الله، والصلاة والسلام على رسول الله. بعد فهم المقصود من السؤال{who}، فالجواب كالآتي:",
        f"بسم الله الرحمن الرحيم. هذا بيان موجز للمسألة التي سألت عنها{who}:",
    ]
    return stable_pick(opts, f"pre49:{text}:{name}")


def compose(c: SemanticConcept, typ: str, text: str, name: str = "") -> str:
    if typ == "reverse_definition":
        label = c.answer_labels[0] if c.answer_labels else c.canonical
        head = f"المصطلح المقصود هو: {label}."
    elif typ == "list" and c.id == "fixed_shares":
        head = "الفروض المقدّرة هي ستة."
    else:
        head = f"{c.canonical}:"
    parts = [preamble(name, text), head, c.definition]
    if c.points:
        parts.append("النقاط المهمة:\n" + "\n".join(f"- {p}" for p in c.points[:4]))
    if typ == "reverse_definition" and c.contrasts:
        # Only show relevant contrasts if mentioned in question.
        n = normalize(text)
        rel = []
        for other, note in c.contrasts.items():
            other_concept = CONCEPTS.get(other)
            if other_concept and any(phrase_hit(n, a) for a in other_concept.aliases + [other_concept.canonical]):
                rel.append(note)
        if rel:
            parts.append("تنبيه على الالتباس:\n" + "\n".join(f"- {x}" for x in rel[:3]))
    return "\n\n".join([p for p in parts if p])


def compose_difference(text: str, name: str = "") -> Optional[str]:
    n = normalize(text)
    hits = []
    for cid, c in CONCEPTS.items():
        if any(phrase_hit(n, a) for a in c.aliases + [c.canonical]):
            hits.append(cid)
    # if concepts not directly named, use rank as fallback.
    if len(hits) < 2:
        hits = [cid for cid, _, _ in rank(text, "difference")[:2]]
    if len(hits) >= 2:
        c1, c2 = CONCEPTS[hits[0]], CONCEPTS[hits[1]]
        return "\n\n".join([
            preamble(name, text),
            f"الفرق باختصار بين {c1.canonical} و{c2.canonical}:",
            f"- {c1.canonical}: {c1.definition}",
            f"- {c2.canonical}: {c2.definition}",
        ])
    return None


@dataclass
class RouteResult:
    action: str  # answer | pass | review
    intent: str
    answer: str = ""
    concept_id: str = ""
    confidence: float = 0.0
    reason: str = ""
    dialect: str = "standard"


def route(text: str, context: Optional[dict] = None, name: str = "") -> RouteResult:
    context = context or {}
    typ = qtype(text)
    dialect = detect_dialect(text, context)
    n = normalize(text)

    if typ == "inheritance_calculation":
        return RouteResult("pass", typ, confidence=0.96, reason="calculation_guard", dialect=dialect)
    if typ == "social":
        return RouteResult("answer", typ, social_reply(text, context, name), confidence=0.99, dialect=dialect)
    if typ == "followup":
        # Delegate rich context followup to v48/v47 if possible.
        if v48 is not None:
            try:
                return RouteResult("answer", typ, v48.followup_reply(text, context, name), concept_id=str(context.get("last_concept") or ""), confidence=0.84, dialect=dialect)
            except Exception:
                pass
        return RouteResult("answer", typ, "قصدك تبسيط آخر نقطة؟ اكتب المصطلح أو المسألة وسأشرحها خطوة خطوة.", confidence=0.5, dialect=dialect)
    if typ == "difference":
        ans = compose_difference(text, name)
        if ans:
            return RouteResult("answer", typ, ans, confidence=0.82, dialect=dialect)

    if typ in {"reverse_definition", "definition", "list", "domain"}:
        rows = rank(text, typ)
        if rows:
            cid, score, reasons = rows[0]
            second = rows[1][1] if len(rows) > 1 else -999
            # Strong thresholds. Do not answer if ambiguous.
            threshold = 20 if typ == "reverse_definition" else 12
            if score < threshold:
                return RouteResult("review", typ, "السؤال يحتاج توضيحًا أدق قبل الجواب؛ لأن المصطلح المقصود غير ظاهر بدرجة كافية.", confidence=min(0.5, score/40), dialect=dialect)
            if second >= score - 4 and typ not in {"reverse_definition", "list"}:
                c1, c2 = CONCEPTS[cid], CONCEPTS[rows[1][0]]
                return RouteResult("answer", "clarification", f"السؤال يحتمل أكثر من مصطلح: {c1.canonical} أو {c2.canonical}. حدّد أيهما تريد حتى لا أجيب بتخمين.", confidence=0.55, dialect=dialect)
            c = CONCEPTS[cid]
            return RouteResult("answer", typ, compose(c, typ, text, name), concept_id=cid, confidence=min(0.99, score/55), reason=";".join(reasons[:8]), dialect=dialect)

    # If no domain evidence, do not pass to fatwa engines.
    if typ == "unknown" and domain_score(n) < 2:
        return RouteResult("answer", typ, "لم أفهم المطلوب بدقة. لو عندك سؤال في المواريث اكتبه، ولو تقصد شيئًا آخر وضّحه لي.", confidence=0.4, dialect=dialect)
    return RouteResult("pass", typ, confidence=0.45, reason="fallback", dialect=dialect)


def answer(text: str, context: Optional[dict] = None, name: str = "") -> Optional[Dict[str, Any]]:
    r = route(text, context, name)
    if r.action in {"answer", "review"} and r.answer:
        return {"answer": r.answer, "intent": r.intent, "concept_id": r.concept_id, "confidence": r.confidence, "reason": r.reason, "dialect": r.dialect}
    return None


def detect_concept_key(text: str) -> str:
    rows = rank(text, qtype(text))
    return rows[0][0] if rows and rows[0][1] >= 18 else ""
