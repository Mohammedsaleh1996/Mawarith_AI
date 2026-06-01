# -*- coding: utf-8 -*-
from pathlib import Path
import json, re
from v47_full_understanding_engine import export_ontology, CONCEPTS
HERE = Path(__file__).resolve().parent
# Export curated ontology
export_ontology(HERE / "corpus" / "v47_full_scholarly_ontology.json")
# Build offline non-RAG reference coverage index from local text files if present.
patterns = {cid: c.aliases + c.features for cid, c in CONCEPTS.items()}
counts = {cid: 0 for cid in CONCEPTS}
examples = {cid: [] for cid in CONCEPTS}
for p in list(HERE.glob("*.txt")) + list(Path("/mnt/data").glob("المرحلة_*.txt")):
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    n = re.sub(r"\s+", " ", text[:2000000])
    for cid, pats in patterns.items():
        c = 0
        for pat in pats[:18]:
            if not pat or len(pat) < 3: continue
            c += len(re.findall(re.escape(pat), n, flags=re.I))
        if c:
            counts[cid] += c
            if len(examples[cid]) < 5:
                examples[cid].append(p.name)
idx = {cid: {"canonical": CONCEPTS[cid].canonical, "matches": counts[cid], "source_files_seen": examples[cid]} for cid in CONCEPTS}
(HERE / "corpus" / "v47_reference_coverage_index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
print("Built corpus/v47_full_scholarly_ontology.json")
print("Built corpus/v47_reference_coverage_index.json")
