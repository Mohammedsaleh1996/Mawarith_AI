# -*- coding: utf-8 -*-
"""
Production API wrapper for Mawareth AI Runtime v8.
- Does not modify v8 runtime.
- Adds request/response logging for auditing and future controlled improvements.
"""
from __future__ import annotations
import json, time, uuid, sys, os
from pathlib import Path
from fastapi import FastAPI
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
from mawarith_ai_runtime_v9 import answer, normalize_ar, detect_concept_key  # noqa

LOG_DIR = HERE / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "mawarith_requests.jsonl"

app = FastAPI(title="Mawareth AI Runtime Production API", version="1.1")
SESSION_CONTEXTS: dict[str, dict] = {}

class AskRequest(BaseModel):
    question: str
    user_id: str | None = None
    channel: str | None = "api"

class AskResponse(BaseModel):
    request_id: str
    answer: str
    elapsed_ms: int


def classify_output(text: str) -> str:
    n = normalize_ar(text)
    if "توضيح" in n or "لا يصح حسابها بالتخمين" in n:
        return "clarification_or_safe_stop"
    if "من التركة" in n and "مراجعة مجموع الانصبة" in n:
        return "calculation"
    return "fiqh_or_general"


def append_log(record: dict) -> None:
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

@app.get("/health")
def health():
    return {"ok": True, "runtime": "v8_locked_plus_v9_nlu_wrapper"}

@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    request_id = str(uuid.uuid4())
    t0 = time.time()
    session_key = f"{req.channel or 'api'}:{req.user_id or 'anonymous'}"
    context = SESSION_CONTEXTS.get(session_key, {})
    ans = answer(req.question, context=context)
    try:
        SESSION_CONTEXTS[session_key] = {
            "last_question": req.question,
            "last_answer": ans,
            "last_concept": detect_concept_key(req.question) or context.get("last_concept"),
        }
    except Exception:
        pass
    elapsed_ms = int((time.time() - t0) * 1000)
    append_log({
        "request_id": request_id,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "channel": req.channel,
        "user_id": req.user_id,
        "question": req.question,
        "answer": ans,
        "answer_type": classify_output(ans),
        "elapsed_ms": elapsed_ms,
    })
    return AskResponse(request_id=request_id, answer=ans, elapsed_ms=elapsed_ms)
