# -*- coding: utf-8 -*-
"""
Mawareth AI v48 — Scholarly Intelligence Reinforcement Layer

Non-RAG, non-fixed-answer layer. It does NOT store question/answer pairs.
It adds a general semantic decision layer before older engines:
  - social/domain gate
  - calculation pass-through gate
  - reverse-definition understanding
  - concept disambiguation by meaning, not by mentioned words
  - review-safe clarification instead of guessing

It reuses the structured v47 ontology and adds scoring rules that treat
mentioned concepts in constraint clauses (e.g. "لا يزيد إلا بالرد ولا ينقص إلا بالعول")
as modifiers, not necessarily the target concept.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple, Set
import re, json, hashlib
from pathlib import Path

try:
    import v47_full_understanding_engine as base
except Exception:  # pragma: no cover
    base = None

try:
    from rapidfuzz import fuzz as _fuzz
except Exception:
    _fuzz = None

# Reuse v47 normalizer if available.
def normalize(text: str) -> str:
    if base is not None:
        try:
            return base.normalize(text)
        except Exception:
            pass
    s = str(text or "")
    trans = str.maketrans({"أ":"ا","إ":"ا","آ":"ا","ى":"ي","ة":"ه","ؤ":"و","ئ":"ي"})
    s = re.sub(r"[\u064b-\u0652\u0670\u0640]", "", s).translate(trans)
    s = re.sub(r"[؟?!.,;:،؛\[\]{}()<>\"'`~|\\/]+", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def stable_pick(options: List[str], seed: str) -> str:
    if not options: return ""
    h = int(hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
    return options[h % len(options)]


def fuzzy(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)
    if not a or not b: return 0.0
    if a in b or b in a: return 100.0
    if _fuzz:
        return float(max(_fuzz.token_set_ratio(a, b), _fuzz.partial_ratio(a, b)))
    aw, bw = set(a.split()), set(b.split())
    return 100.0 * len(aw & bw) / max(1, len(aw | bw))


def word_hit(n: str, w: str) -> bool:
    w = normalize(w)
    if not w: return False
    if " " in w or len(w) > 4:
        return w in n
    return bool(re.search(r"(^|\s)(?:[وفبلك]?ال|[وفبلك])?" + re.escape(w) + r"($|\s)", n))


# ---------- Dialogue and routing -------------------------------------------------
SOCIAL_CUES = {
    "السلام عليكم", "وعليكم السلام", "ازيك", "ازايك", "كيف حالك", "كيف الحال", "عامل ايه", "اخبارك", "هلا", "اهلين", "اهلا", "مرحبا", "مساء الخير", "مساء الفل", "صباح الخير", "صباح الفل", "بخير", "الحمد لله", "تمام", "كويس", "مزيان", "لاباس", "شكرا", "تسلم", "بارك الله", "جزاك الله", "طيبين", "الحمدلله"
}
DOMAIN_CUES = {
    "ميراث", "مواريث", "فرائض", "فرائض", "تركة", "التركة", "ورث", "وارث", "وارثين", "نصيب", "حصة", "سهم", "فرض", "فروض", "عول", "العول", "رد", "الرد", "حجب", "الحجب", "تعصيب", "العصبة", "عاصب", "زوج", "زوجة", "ابن", "بنت", "اخ", "اخت", "ام", "اب", "جد", "جدة", "عم", "خال", "وصية", "وصيه", "دين", "ديون", "كلالة", "مناسخة", "مناسخات", "العمرية", "الغراوان", "المشتركة", "الحمارية", "الأكدرية", "الاكدرية", "ذوو الارحام", "موانع الارث", "أسباب الإرث", "شروط الإرث"
}
DEATH_CUES = {"مات", "توفي", "توفيت", "هلك", "ماتت", "ماتوا", "ترك", "تركت", "خلف", "خلّف", "ساب", "سيب"}
HEIR_CUES = {"زوج", "زوجة", "زوجته", "مراته", "ابن", "ابنه", "بنت", "بنته", "ام", "امه", "اب", "ابوه", "اخ", "اخت", "عم", "جدة", "جد", "بنات", "اولاد", "عيال", "ابناء", "اخوة", "اخوين"}
FOLLOWUP_CUES = {"مش فاهم", "ما افهم", "ما فهمت", "مفهمتش", "مو واضح", "وضح", "وضحلي", "بسط", "بسطها", "اشرح ابسط", "سهلها", "مثال", "هات مثال", "بالارقام", "بالأرقام", "كيف حسبتها", "ازاي حسبتها", "ليه"}
REVERSE_CUES = {"ما هو المصطلح", "ما المصطلح", "ما اسم", "ماذا يسمى", "ماذا يطلق", "يطلق على", "وش يسمون", "ايش يسمون", "ايه اسم", "اسم ايه", "يسمى ايه", "ما الذي يطلق", "ما المراد بالمصطلح"}
DIRECT_DEF_CUES = {"ما معنى", "ما هو", "ما هي", "ما المقصود", "المقصود ب", "يعني ايه", "وش يعني", "شنو يعني", "عرف", "اشرح"}
DIFF_CUES = {"الفرق بين", "ما الفرق", "فرق بين", "ايه الفرق", "وش الفرق", "شنو الفرق"}
LIST_CUES = {"كم عدد", "اذكر", "عدد", "ما هي انواع", "ما انواع", "ما اقسام", "اقسام"}


def contains_any(n: str, cues: Set[str]) -> bool:
    return any(normalize(c) in n for c in cues)


def social_score(n: str) -> int:
    score = 0
    for c in SOCIAL_CUES:
        if normalize(c) in n:
            score += 3 if len(c.split()) > 1 else 2
    # short non-domain utterances are usually chat acknowledgements.
    if len(n.split()) <= 4 and not contains_any(n, DOMAIN_CUES):
        score += 2
    return score


def domain_score(n: str) -> int:
    score = 0
    for c in DOMAIN_CUES:
        cn = normalize(c)
        if not cn:
            continue
        # Short Arabic domain cues مثل خال/عم/اب must match as whole words
        # to avoid false positives like: حالك -> خال.
        if (len(cn) <= 4 and " " not in cn):
            if word_hit(n, cn): score += 2
        elif cn in n:
            score += 2
    for c in DEATH_CUES:
        if word_hit(n, c): score += 3
    for c in HEIR_CUES:
        if word_hit(n, c): score += 1
    return score


def is_calculation_like(text: str) -> bool:
    n = normalize(text)
    return any(normalize(c) in n for c in DEATH_CUES) and any(word_hit(n, h) for h in HEIR_CUES)


def qtype(text: str) -> str:
    n = normalize(text)
    if any(normalize(c) in n for c in FOLLOWUP_CUES): return "followup"
    if any(normalize(c) in n for c in DIFF_CUES): return "difference"
    if any(normalize(c) in n for c in REVERSE_CUES): return "reverse_definition"
    if any(normalize(c) in n for c in LIST_CUES): return "list"
    if any(normalize(c) in n for c in DIRECT_DEF_CUES) and domain_score(n) >= 2: return "definition"
    if is_calculation_like(text): return "inheritance_calculation"
    ss, ds = social_score(n), domain_score(n)
    if ss >= 2 and ds < 2: return "social"
    if ds >= 2: return "domain"
    return "unknown"


def detect_dialect(text: str, context: Optional[dict] = None) -> str:
    if base is not None:
        try:
            return base.detect_dialect(text, context)
        except Exception:
            pass
    n = normalize(text)
    if any(x in n for x in ["ازيك", "ازاي", "عامل ايه", "مراتي", "جوزها", "مفهمتش", "مساء الفل"]): return "egyptian"
    if any(x in n for x in ["شلون", "وش", "ابشر", "حياك", "هلا", "ايش", "مو واضح"]): return "gulf"
    if any(x in n for x in ["شو", "قديش", "هيك", "مرتو", "بياخد"]): return "shami"
    if context and context.get("last_dialect"): return str(context.get("last_dialect"))
    return "standard"


def social_reply(text: str, context: Optional[dict] = None, name: str = "") -> str:
    n = normalize(text)
    dialect = detect_dialect(text, context)
    if "السلام" in n:
        if any(x in n for x in ["كيف حالك", "كيف الحال", "ازيك", "اخبارك"]):
            opts = ["وعليكم السلام ورحمة الله وبركاته. الحمد لله بخير، أسأل الله أن تكون بخير.", "وعليكم السلام ورحمة الله وبركاته. بخير ولله الحمد، حياك الله."]
        else:
            opts = ["وعليكم السلام ورحمة الله وبركاته.", "وعليكم السلام ورحمة الله وبركاته، أهلًا وسهلًا."]
    elif any(x in n for x in ["ازيك", "عامل ايه"]):
        opts = ["الحمد لله بخير، إنت عامل إيه؟", "بخير الحمد لله، ربنا يكرمك."]
    elif any(x in n for x in ["كيف حالك", "كيف الحال", "شلونك"]):
        opts = ["الحمد لله بخير.", "بخير ولله الحمد."]
    elif any(x in n for x in ["مساء الفل", "مساء الخير"]):
        opts = ["مساء النور.", "مساء الخير، حياك الله."]
    elif any(x in n for x in ["صباح الفل", "صباح الخير"]):
        opts = ["صباح النور.", "صباح الخير، يومك طيب."]
    elif any(x in n for x in ["هلا", "اهلين", "اهلا", "مرحبا"]):
        opts = ["يا هلا.", "أهلًا وسهلًا.", "مرحبًا بك."]
    elif any(x in n for x in ["بخير", "الحمد لله", "تمام", "كويس", "لاباس", "مزيان"]):
        opts = ["الحمد لله، يديم عليك الخير.", "تمام، الحمد لله.", "ربنا يديم عليك العافية."]
    elif any(x in n for x in ["شكرا", "تسلم", "جزاك"]):
        opts = ["العفو، بارك الله فيك.", "تحت أمرك."]
    else:
        opts = ["أهلًا بك.", "مرحبًا."]
    return stable_pick(opts, f"social:{dialect}:{text}:{name}")


# ---------- Concept scoring ------------------------------------------------------

def concepts() -> Dict[str, Any]:
    if base is None: return {}
    return getattr(base, "CONCEPTS", {})


def split_target_and_modifiers(text: str) -> Tuple[str, str]:
    """Separate the described target from constraint/modifier clauses.

    Works for generic reverse definitions such as:
    - ما اسم النصيب المقدر شرعا ...؟
    - ما المصطلح الذي يطلق على النصيب المقدر ... والذي لا يزيد إلا بالرد؟

    The target is the described object; modifiers are later clauses that may mention
    related concepts but are not necessarily the answer.
    """
    n = normalize(text)
    # Extract text after reverse-definition lead patterns.
    m = re.search(r"(?:يطلق علي|يطلق على|يسمي|يسمى)\s+(.+)", n)
    if m:
        n = m.group(1).strip()
    else:
        n = re.sub(r"^(ما هو المصطلح|ما المصطلح|ما اسم|ماذا يسمى|ماذا يسمي|ماذا يطلق|ايه اسم|وش يسمون|ايش يسمون)\s+", "", n).strip()
    # Split at modifier/relative clauses, but do not allow empty target.
    parts = re.split(r"\b(والذي|والتي|الذي|التي|ولا|الا|إلا)\b", n, maxsplit=1)
    if len(parts) >= 3 and parts[0].strip():
        return parts[0].strip(), " ".join(parts[1:]).strip()
    return n, ""


def mentioned_concepts(segment: str) -> Set[str]:
    n = normalize(segment)
    out = set()
    for cid, c in concepts().items():
        for a in getattr(c, "aliases", []):
            an = normalize(a)
            if an and ((len(an) <= 4 and " " not in an and word_hit(n, an)) or (len(an) > 4 and an in n)):
                out.add(cid); break
    return out


def score_concept(text: str, concept: Any, typ: str) -> Tuple[float, List[str]]:
    n = normalize(text)
    target, modifiers = split_target_and_modifiers(text) if typ == "reverse_definition" else (n, "")
    mod_mentions = mentioned_concepts(modifiers)
    score, reasons = 0.0, []
    aliases = list(getattr(concept, "aliases", []) or []) + [getattr(concept, "canonical", "")]
    features = list(getattr(concept, "features", []) or []) + [getattr(concept, "definition", "")]

    # direct alias hit. In reverse definitions, alias in modifier is a distractor, not target.
    for a in aliases:
        an = normalize(a)
        if not an: continue
        hit_all = an in n if len(an) > 4 or " " in an else word_hit(n, an)
        hit_target = an in target if len(an) > 4 or " " in an else word_hit(target, an)
        if hit_target:
            w = 8.0 if typ != "reverse_definition" else 4.0
            score += w; reasons.append(f"alias_target:{a}")
        elif hit_all:
            w = 5.0 if typ != "reverse_definition" else 0.75
            score += w; reasons.append(f"alias_modifier_or_mentioned:{a}")

    # feature matching. Target clause gets highest weight in reverse definitions.
    for f in features:
        fn = normalize(f)
        if not fn: continue
        if fn in target:
            score += 10.0; reasons.append(f"feature_target:{f[:35]}")
        elif typ != "reverse_definition" and fn in n:
            score += 7.0; reasons.append(f"feature_all:{f[:35]}")
        else:
            sim_target = fuzzy(fn, target)
            sim_all = fuzzy(fn, n)
            if sim_target >= 86:
                score += 5.0; reasons.append(f"fuzzy_target:{f[:25]}:{sim_target:.0f}")
            elif typ != "reverse_definition" and sim_all >= 88:
                score += 3.0; reasons.append(f"fuzzy_all:{f[:25]}:{sim_all:.0f}")

    cid = getattr(concept, "id", "")
    # Generic reverse-definition rule: if concept is mentioned only in modifier and has no target evidence, penalize.
    if typ == "reverse_definition" and cid in mod_mentions:
        target_evidence = sum(1 for r in reasons if "target" in r)
        if target_evidence == 0:
            score -= 12.0; reasons.append("modifier_only_penalty")
        else:
            score -= 4.0; reasons.append("modifier_mention_penalty")

    # Generic defined-share cues, not a fixed question. They describe fard.
    if typ == "reverse_definition":
        if cid == "fard" and any(x in target for x in ["نصيب", "سهم", "حصه", "حصة"]) and any(x in target for x in ["مقدر", "محد", "شرع", "كتاب الله", "فرضه الله"]):
            score += 22; reasons.append("generic_defined_share_cue")
        if cid == "fixed_shares" and any(x in n for x in ["النصف", "الربع", "الثمن", "الثلثين", "الثلثان", "السدس"]):
            score += 13; reasons.append("listed_share_terms")

    if typ == "list" and cid == "fixed_shares" and any(x in n for x in ["فروض", "الفروض", "عدد الفروض", "النصف", "الربع"]):
        score += 22; reasons.append("list_fixed_shares")
    return score, reasons


def rank(text: str, typ: str) -> List[Tuple[str,float,List[str]]]:
    rows = []
    for cid, c in concepts().items():
        s, r = score_concept(text, c, typ)
        if s > 0:
            rows.append((cid, s, r))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows


def preamble(name: str, text: str) -> str:
    who = f" يا {name}" if name else ""
    opts = [
        f"بسم الله الرحمن الرحيم. بناءً على ما ورد في سؤالك{who}، فهذا بيان المسألة:",
        f"بسم الله، والصلاة والسلام على رسول الله. بعد فهم المقصود من السؤال{who}، فالجواب كالآتي:",
        f"بسم الله الرحمن الرحيم. هذا بيان موجز للمسألة التي سألت عنها{who}:",
    ]
    return stable_pick(opts, f"pre48:{text}:{name}")


def compose_concept(c: Any, typ: str, text: str, name: str = "") -> str:
    if base is not None:
        # Use v47 composer for consistency, with our qtype.
        try:
            return base.compose_concept_answer(c, typ, text, name=name, context=None, include_preamble=True)
        except Exception:
            pass
    head = f"المصطلح المقصود هو: {getattr(c,'canonical','المفهوم')}." if typ == "reverse_definition" else f"{getattr(c,'canonical','المفهوم')}:"
    return preamble(name, text) + "\n\n" + head + "\n\n" + getattr(c, "definition", "")


def compose_difference(text: str, name: str = "") -> Optional[str]:
    if base is not None:
        try:
            return base.compose_difference(text, name=name)
        except Exception:
            pass
    return None


def followup_reply(text: str, context: Optional[dict] = None, name: str = "") -> str:
    context = context or {}
    cid = context.get("last_concept") or ""
    c = concepts().get(str(cid))
    if c:
        if any(x in normalize(text) for x in ["مثال", "بالارقام", "بالأرقام"]):
            exs = getattr(c, "examples", []) or []
            return f"تمام، مثال مبسّط على {getattr(c,'canonical','هذا المفهوم')}:\n\n" + (exs[0] if exs else "أحتاج مسألة محددة لأطبق المثال بدقة.")
        return compose_concept(c, "definition", text, name="")
    return "قصدك تبسيط آخر نقطة اتكلمنا عنها؟ اذكر المصطلح أو المسألة وسأشرحها خطوة خطوة."


@dataclass
class RouteResult:
    action: str             # answer | pass | review
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

    # Calculation-like messages must never be consumed by concept engines.
    if typ == "inheritance_calculation":
        return RouteResult("pass", typ, confidence=0.95, reason="inheritance_calculation", dialect=dialect)

    if typ == "social":
        return RouteResult("answer", typ, social_reply(text, context, name), confidence=0.99, dialect=dialect)

    if typ == "followup":
        return RouteResult("answer", typ, followup_reply(text, context, name), concept_id=str(context.get("last_concept") or ""), confidence=0.85, dialect=dialect)

    if typ == "difference":
        ans = compose_difference(text, name)
        if ans:
            return RouteResult("answer", typ, ans, confidence=0.82, dialect=dialect)

    if typ in {"definition", "reverse_definition", "list", "domain"}:
        rows = rank(text, typ)
        if rows:
            top, score, reasons = rows[0]
            second_score = rows[1][1] if len(rows) > 1 else -999
            # strict ambiguity: if close and no strong reverse target evidence, ask.
            strong = score >= (18 if typ == "reverse_definition" else 12)
            close = second_score >= score - 3
            if not strong:
                return RouteResult("review", typ, "السؤال يحتاج توضيحًا أدق قبل الجواب؛ لأن المصطلح المقصود غير ظاهر بدرجة كافية.", confidence=min(0.5, score/30), dialect=dialect)
            if close and typ not in {"reverse_definition", "list"}:
                c1, c2 = concepts()[top], concepts()[rows[1][0]]
                return RouteResult("answer", "clarification", f"السؤال يحتمل أكثر من مصطلح: {c1.canonical} أو {c2.canonical}. حدّد أيهما تريد شرحه حتى لا أجيب بتخمين.", confidence=0.55, dialect=dialect)
            c = concepts()[top]
            return RouteResult("answer", typ, compose_concept(c, typ, text, name), concept_id=top, confidence=min(0.99, score/40), reason=";".join(reasons[:6]), dialect=dialect)

    if typ == "unknown":
        # If not domain, do not feed into fatwa. Give harmless clarification only for dashboard? pass to older social maybe not.
        if domain_score(n) < 2:
            return RouteResult("answer", typ, "لم أفهم هل تقصد سؤالًا في المواريث أم محادثة عادية. اكتب سؤالك في المواريث أو وضّح المطلوب.", confidence=0.4, dialect=dialect)
    return RouteResult("pass", typ, confidence=0.5, reason="fallback", dialect=dialect)


def answer(text: str, context: Optional[dict] = None, name: str = "") -> Optional[Dict[str, Any]]:
    r = route(text, context, name)
    if r.action == "answer":
        return {"answer": r.answer, "intent": r.intent, "concept_id": r.concept_id, "confidence": r.confidence, "reason": r.reason, "dialect": r.dialect}
    if r.action == "review" and r.answer:
        return {"answer": r.answer, "intent": r.intent, "answer_kind": "clarification", "confidence": r.confidence, "dialect": r.dialect}
    return None


def detect_concept_key(text: str) -> str:
    typ = qtype(text)
    rows = rank(text, typ)
    return rows[0][0] if rows and rows[0][1] >= 14 else ""


def export_ontology(path: str | Path) -> None:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    for cid, c in concepts().items():
        data[cid] = {
            "canonical": getattr(c,"canonical", ""),
            "family": getattr(c,"family", ""),
            "aliases": getattr(c,"aliases", []),
            "definition": getattr(c,"definition", ""),
            "features": getattr(c,"features", []),
            "points": getattr(c,"points", []),
            "examples": getattr(c,"examples", []),
            "contrasts": getattr(c,"contrasts", {}),
        }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
