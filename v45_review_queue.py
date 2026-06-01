# -*- coding: utf-8 -*-
"""Review queue helper for uncertain/high-risk inheritance questions."""
from __future__ import annotations
import json, sqlite3, uuid
from datetime import datetime
from pathlib import Path
from typing import Any


def ensure_review_schema(db_path: Path):
    con = sqlite3.connect(str(db_path)); cur = con.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS review_queue (
        id TEXT PRIMARY KEY,
        ts TEXT,
        channel TEXT,
        user_id TEXT,
        question TEXT,
        reason TEXT,
        status TEXT DEFAULT 'open',
        raw_json TEXT
    )''')
    con.commit(); con.close()


def add_review_item(db_path: Path, channel: str, user_id: str, question: str, reason: str, raw: Any = None) -> str:
    ensure_review_schema(db_path)
    rid = str(uuid.uuid4())
    con = sqlite3.connect(str(db_path)); cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO review_queue(id,ts,channel,user_id,question,reason,status,raw_json) VALUES(?,?,?,?,?,?,?,?)",
                (rid, datetime.now().isoformat(timespec="seconds"), channel, user_id, question, reason, "open", json.dumps(raw, ensure_ascii=False) if raw is not None else None))
    con.commit(); con.close()
    return rid
