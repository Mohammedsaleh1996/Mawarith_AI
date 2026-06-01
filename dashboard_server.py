# -*- coding: utf-8 -*-
"""
Mawareth AI Dashboard Server
- Admin dashboard for runtime, reports, logs, chat, Telegram polling, and WaPilot webhook.
- Keeps inheritance runtime isolated; calls mawarith_ai_runtime_v9.answer().
- No RAG. No hardcoded per-question answers in dashboard.
"""
from __future__ import annotations

import json
import hashlib
import base64
import secrets
import shutil
import subprocess
import os
import queue
import re
import signal
import sqlite3
import threading
import time
import uuid
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import requests
import sqlserver_sync
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
LOG_DIR = HERE / "logs"
STATIC_DIR = HERE / "static"
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

# Persist user-owned assets outside the replaceable project folder.
# This keeps the logo/settings after the user replaces the project with a newer package.
def _persistent_base_dir() -> Path:
    root = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "MawarethAI" / "Dashboard"
    return DATA_DIR

PERSIST_DIR = _persistent_base_dir()
PERSIST_ASSETS_DIR = PERSIST_DIR / "assets"
PERSIST_DIR.mkdir(parents=True, exist_ok=True)
PERSIST_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "dashboard.sqlite3"
CONFIG_PATH = DATA_DIR / "dashboard_config.json"

from mawarith_ai_runtime_v9 import answer, normalize_ar, detect_concept_key  # noqa
from registry_config import (
    load_registry_config,
    save_registry_config,
    sanitize_config_for_file,
    registry_status,
    delete_registry_config,
)

from human_conversation_enhancer import (
    detect_human_message_kind,
    is_pure_social_message,
    human_smalltalk_reply,
    should_decorate_with_preamble,
    should_send_processing_notice,
    preamble_human,
    detect_dialect_human,
    answer_role,
)


DEFAULT_CONFIG = {
    "project_name": "مفتي المواريث الذكي",
    "dashboard_host": "0.0.0.0",
    "dashboard_port": 8088,
    "telegram": {
        "enabled": False,
        "bot_token": "",
        "poll_interval_seconds": 2,
        "last_update_id": 0
    },
    "wapilot": {
        "enabled": False,
        "instance_id": "instance3952",
        "webhook_path": "/webhook/wapilot",
        "public_webhook_url": "https://favorable-erased-hatbox.ngrok-free.dev/webhook/wapilot",
        "api_url_template": "https://api.wapilot.net/api/v2/{instance_id}/send-message",
        "api_token": "",
        "send_payload_style": "auto"
    },
    "runtime": {
        "same_dialect_reply": True,
        "safe_stop_on_advanced": True
    },
    "ui": {
        "logo_title": "مفتي المواريث",
        "logo_subtitle": "Dashboard",
        "logo_file": ""
    },
    "security": {
        "enabled": True,
        "session_hours": 12
    },
    "autostart": {
        "enabled": True,
        "telegram": True,
        "whatsapp": True,
        "ngrok": True
    },
    "ngrok": {
        "enabled": True,
        "path": "",
        "port": 8088,
        "public_url": "",
        "domain": "favorable-erased-hatbox.ngrok-free.dev",
        "strict_domain": True,
        "allow_random_fallback": False
    },
    "firewall": {
        "auto_open_port": True,
        "rule_name": "Mawareth AI Dashboard 8088"
    },
    "operational": {
        "reply_mode": "active",
        "review_large_amount_threshold": 1000000,
        "show_processing_notice": True,
        "daily_greeting_enabled": True,
        "answer_preamble_enabled": True
    },
    "sqlserver": {
        "enabled": False,
        "sync_enabled": True,
        "host": "",
        "port": "1433",
        "database": "MawarethAI",
        "auth_mode": "sql",
        "username": "",
        "password": "",
        "driver": "ODBC Driver 18 for SQL Server",
        "encrypt": True,
        "trust_server_certificate": True,
        "timeout_seconds": 5,
        "sync_interval_seconds": 30,
        "backup_dir": "C:\\MawarethAI_Backups"
    }
}


def shallow_merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = shallow_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_env_file() -> None:
    env_file = HERE / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)



def clean_telegram_token(value: str | None) -> str:
    """Normalize a Telegram BotFather token without guessing a different secret.
    Accepts raw token, bot<TOKEN>, or an API URL containing /bot<TOKEN>/...
    Removes spaces/quotes/invisible characters that commonly break Telegram getMe.
    """
    if value is None:
        return ""
    t = str(value)
    # remove common invisible characters and surrounding quotes/spaces
    t = t.replace("\ufeff", "").replace("\u200f", "").replace("\u200e", "")
    t = t.strip().strip('"').strip("'").strip()
    # If user pasted a Telegram API URL, extract what comes after /bot
    m = re.search(r"/bot([^/\s]+)", t)
    if m:
        t = m.group(1)
    # If user pasted bot123456:ABC, strip only the literal prefix
    if t.lower().startswith("bot") and ":" in t:
        t = t[3:]
    # BotFather tokens do not contain whitespace
    t = re.sub(r"\s+", "", t)
    return t


def telegram_token_format_status(value: str | None) -> dict:
    t = clean_telegram_token(value)
    has_colon = ":" in t
    prefix = t.split(":", 1)[0] if has_colon else t[:12]
    looks_like = bool(re.match(r"^\d{6,}:[A-Za-z0-9_-]{20,}$", t))
    return {
        "token_set": bool(t),
        "masked": mask_secret(t) if 'mask_secret' in globals() else (t[:4] + "…" + t[-4:] if len(t)>8 else "***"),
        "length": len(t),
        "has_colon": has_colon,
        "numeric_prefix": bool(prefix.isdigit()) if prefix else False,
        "looks_like_botfather_token": looks_like,
    }


def is_masked_secret_value(value: str | None) -> bool:
    """Return True when the browser submitted a masked display value, not a real secret.

    This prevents settings saves in one integration (e.g. WaPilot) from overwriting
    the other integration's token with values like VDGM...8763 or 8v6T***mEBH.
    """
    if value is None:
        return False
    v = str(value).strip()
    if not v:
        return False
    return ("…" in v) or ("..." in v) or ("***" in v) or (v.startswith("****"))


def _drop_blank_or_masked_secret(body: dict, section: str, key: str) -> None:
    """Mutate request body so blank/masked secrets mean KEEP EXISTING.

    This is intentionally section-level and does not touch the other service.
    """
    try:
        sec = body.get(section)
        if not isinstance(sec, dict) or key not in sec:
            return
        val = sec.get(key)
        if val is None or str(val).strip() == "" or is_masked_secret_value(str(val)):
            sec.pop(key, None)
    except Exception:
        return

def load_config() -> dict:
    """Load config with this priority:
    DEFAULT_CONFIG < project JSON < Windows Registry < .env/environment variables.

    Registry persistence is what keeps Telegram/WaPilot tokens after replacing project folders.
    """
    load_env_file()
    if CONFIG_PATH.exists():
        try:
            existing = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    else:
        existing = {}

    registry_cfg = load_registry_config()
    cfg = shallow_merge(DEFAULT_CONFIG, existing)
    cfg = shallow_merge(cfg, registry_cfg)

    # Environment variables override only when present.
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        cfg["telegram"]["bot_token"] = os.environ["TELEGRAM_BOT_TOKEN"]
    if os.environ.get("WAPILOT_INSTANCE_ID"):
        cfg["wapilot"]["instance_id"] = os.environ["WAPILOT_INSTANCE_ID"]
    if os.environ.get("WAPILOT_WEBHOOK_PATH"):
        cfg["wapilot"]["webhook_path"] = os.environ["WAPILOT_WEBHOOK_PATH"]
    if os.environ.get("WAPILOT_PUBLIC_WEBHOOK_URL"):
        cfg["wapilot"]["public_webhook_url"] = os.environ["WAPILOT_PUBLIC_WEBHOOK_URL"]
    if os.environ.get("WAPILOT_API_URL"):
        cfg["wapilot"]["api_url_template"] = os.environ["WAPILOT_API_URL"]
    if os.environ.get("WAPILOT_API_TOKEN"):
        cfg["wapilot"]["api_token"] = os.environ["WAPILOT_API_TOKEN"]
    if os.environ.get("SQLSERVER_ENABLED"):
        cfg.setdefault("sqlserver", {})["enabled"] = os.environ["SQLSERVER_ENABLED"].strip().lower() in {"1", "true", "yes", "on"}
    if os.environ.get("SQLSERVER_HOST"):
        cfg.setdefault("sqlserver", {})["host"] = os.environ["SQLSERVER_HOST"]
    if os.environ.get("SQLSERVER_PORT"):
        cfg.setdefault("sqlserver", {})["port"] = os.environ["SQLSERVER_PORT"]
    if os.environ.get("SQLSERVER_DATABASE"):
        cfg.setdefault("sqlserver", {})["database"] = os.environ["SQLSERVER_DATABASE"]
    if os.environ.get("SQLSERVER_USERNAME"):
        cfg.setdefault("sqlserver", {})["username"] = os.environ["SQLSERVER_USERNAME"]
    if os.environ.get("SQLSERVER_PASSWORD"):
        cfg.setdefault("sqlserver", {})["password"] = os.environ["SQLSERVER_PASSWORD"]
    if os.environ.get("SQLSERVER_AUTH_MODE"):
        cfg.setdefault("sqlserver", {})["auth_mode"] = os.environ["SQLSERVER_AUTH_MODE"]
    if os.environ.get("SQLSERVER_DRIVER"):
        cfg.setdefault("sqlserver", {})["driver"] = os.environ["SQLSERVER_DRIVER"]
    # Always normalize Telegram token read from Registry/.env/project config.
    cfg.setdefault("telegram", {})["bot_token"] = clean_telegram_token(cfg.get("telegram", {}).get("bot_token", ""))
    return cfg


def save_config(cfg: dict) -> None:
    # Persist tokens/integration settings in HKCU registry so future package replacements keep them.
    # v34 hard guard: any save path (not only /api/config) must preserve existing secrets
    # if the caller holds a blank/masked runtime copy. This prevents SQL/WaPilot settings saves
    # from corrupting Telegram token, and vice versa.
    cfg = dict(cfg or {})
    prev = load_registry_config()
    cfg.setdefault("telegram", {})
    cfg.setdefault("wapilot", {})
    cfg.setdefault("sqlserver", {})

    tg = clean_telegram_token(cfg.get("telegram", {}).get("bot_token", ""))
    if not tg or is_masked_secret_value(tg):
        tg = clean_telegram_token(prev.get("telegram", {}).get("bot_token", ""))
    cfg["telegram"]["bot_token"] = tg

    wa = str(cfg.get("wapilot", {}).get("api_token", "") or "").strip()
    if (not wa or is_masked_secret_value(wa)) and prev.get("wapilot", {}).get("api_token"):
        cfg["wapilot"]["api_token"] = prev.get("wapilot", {}).get("api_token", "")

    sp = str(cfg.get("sqlserver", {}).get("password", "") or "").strip()
    if (not sp or is_masked_secret_value(sp)) and prev.get("sqlserver", {}).get("password"):
        cfg["sqlserver"]["password"] = prev.get("sqlserver", {}).get("password", "")

    save_registry_config(cfg)
    # Keep project JSON portable and replaceable: do not write raw tokens into it.
    safe_cfg = sanitize_config_for_file(cfg)
    CONFIG_PATH.write_text(json.dumps(safe_cfg, ensure_ascii=False, indent=2), encoding="utf-8")


CONFIG = load_config()
if not CONFIG_PATH.exists():
    save_config(CONFIG)

# سياق محادثة بسيط لكل قناة/مستخدم لدعم: مش فاهم / بسط / مثال.
# لا يخزن ردودًا ثابتة، فقط آخر مفهوم/سؤال/إجابة داخل جلسة التشغيل.
SESSION_CONTEXTS: dict[str, dict] = {}
SESSION_LOCK = threading.RLock()

# v15: separate cookie name to invalidate old unaudited sessions after the security patch.
SESSION_COOKIE_NAME = "mawareth_session_v15"
LEGACY_SESSION_COOKIE_NAMES = ["mawareth_session"]


def _auth_is_enabled() -> bool:
    """Server-side auth is enforced by default for all dashboard/API routes.
    Set ALLOW_INSECURE_DASHBOARD=1 only for isolated local debugging.
    """
    if str(os.environ.get("ALLOW_INSECURE_DASHBOARD", "")).strip() == "1":
        return False
    return True


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return value[:4] + "…" + value[-4:]


DB_LOCK = threading.RLock()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with DB_LOCK, db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            ts TEXT NOT NULL,
            date TEXT NOT NULL,
            channel TEXT NOT NULL,
            user_id TEXT,
            user_name TEXT,
            direction TEXT NOT NULL,
            question TEXT,
            answer TEXT,
            answer_type TEXT,
            dialect TEXT,
            elapsed_ms INTEGER DEFAULT 0,
            status TEXT DEFAULT 'ok',
            raw_json TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS service_events (
            id TEXT PRIMARY KEY,
            ts TEXT NOT NULL,
            service TEXT NOT NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS webhook_events (
            fingerprint TEXT PRIMARY KEY,
            ts TEXT NOT NULL,
            channel TEXT NOT NULL,
            sender TEXT,
            text TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS technical_events (
            id TEXT PRIMARY KEY,
            ts TEXT NOT NULL,
            date TEXT NOT NULL,
            level TEXT NOT NULL,
            component TEXT NOT NULL,
            event TEXT NOT NULL,
            message TEXT,
            raw_json TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            display_name TEXT,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            permissions TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_seen TEXT NOT NULL
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            ts TEXT NOT NULL,
            level TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT,
            seen INTEGER NOT NULL DEFAULT 0,
            raw_json TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS login_attempts (
            id TEXT PRIMARY KEY,
            ts TEXT NOT NULL,
            username TEXT,
            success INTEGER NOT NULL,
            ip TEXT,
            message TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS review_items (
            id TEXT PRIMARY KEY,
            ts TEXT NOT NULL,
            conversation_id TEXT,
            question TEXT,
            answer TEXT,
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            reviewer TEXT,
            reviewed_at TEXT,
            notes TEXT
        )
        """)
        # Lightweight schema migrations for older package DB files.
        for sql in [
            "ALTER TABLE users ADD COLUMN force_password_change INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN failed_login_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN locked_until TEXT",
            "ALTER TABLE users ADD COLUMN last_login TEXT",
        ]:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass
        conn.commit()


init_db()

SQLSYNC_WORKER = sqlserver_sync.SqlServerSyncWorker(DB_PATH, load_config, logger=lambda level, component, event, message, raw=None: log_event(level, component, event, message, raw) if 'log_event' in globals() else None)

SQL_SYNC_KICK_LOCK = threading.RLock()
SQL_SYNC_LAST_KICK = 0.0
SQL_SYNC_IN_FLIGHT = False

def kick_sql_sync(reason: str = "change", min_interval: float = 2.5) -> None:
    """Best-effort immediate bidirectional sync after local writes.

    SQLite stays the source of availability. If SQL Server is down, the operation
    is logged and retried later by the background worker; the user request never fails.
    """
    global SQL_SYNC_LAST_KICK, SQL_SYNC_IN_FLIGHT
    try:
        cfg = load_config()
        if not (cfg.get("sqlserver", {}).get("enabled") and cfg.get("sqlserver", {}).get("sync_enabled", True)):
            return
        now = time.time()
        with SQL_SYNC_KICK_LOCK:
            if SQL_SYNC_IN_FLIGHT or (now - SQL_SYNC_LAST_KICK) < min_interval:
                return
            SQL_SYNC_IN_FLIGHT = True
            SQL_SYNC_LAST_KICK = now
        def _run():
            global SQL_SYNC_IN_FLIGHT
            try:
                res = SQLSYNC_WORKER.run_once()
                # Do not call log_event here to avoid recursive sync storms.
                if not res.get("ok"):
                    try:
                        with DB_LOCK, db() as conn:
                            conn.execute("""
                            INSERT INTO technical_events (id, ts, date, level, component, event, message, raw_json)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (str(uuid.uuid4()), now_ts(), today_str(), "warning", "sqlserver", "sync_kick_failed", "تعذرت مزامنة SQL Server؛ المشروع مستمر على SQLite", json.dumps(res, ensure_ascii=False)[:12000]))
                            conn.commit()
                    except Exception:
                        pass
            finally:
                with SQL_SYNC_KICK_LOCK:
                    SQL_SYNC_IN_FLIGHT = False
        threading.Thread(target=_run, name="SqlServerSyncKick", daemon=True).start()
    except Exception:
        return

ALL_PERMISSIONS = [
    "dashboard", "chat", "services", "logs", "events", "errors",
    "remote", "settings", "users", "notifications",
    "health", "tests", "backup", "conversations", "review", "security"
]
ROLE_PERMISSIONS = {
    "admin": ALL_PERMISSIONS,
    "operator": ["dashboard", "chat", "services", "logs", "events", "errors", "remote", "notifications", "health", "tests", "conversations", "review"],
    "viewer": ["dashboard", "logs", "notifications", "health"],
}


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt, digest = stored.split("$", 2)
        if algo != "pbkdf2_sha256":
            return False
        return secrets.compare_digest(_hash_password(password, salt), stored)
    except Exception:
        return False


def _parse_permissions(value: str | list | None) -> list[str]:
    if isinstance(value, list):
        return [p for p in value if p in ALL_PERMISSIONS]
    if not value:
        return []
    return [p.strip() for p in str(value).split(",") if p.strip() in ALL_PERMISSIONS]


def _permissions_string(perms: list[str]) -> str:
    return ",".join([p for p in ALL_PERMISSIONS if p in set(perms)])


def ensure_default_admin() -> None:
    with DB_LOCK, db() as conn:
        count = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        if count == 0:
            ts = now_ts_raw()
            conn.execute("""
            INSERT INTO users (username, display_name, password_hash, role, permissions, active, created_at, updated_at, force_password_change)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?, 1)
            """, (
                "admin", "مدير النظام", _hash_password("admin123"), "admin",
                _permissions_string(ALL_PERMISSIONS), ts, ts
            ))
            conn.commit()


def ensure_permission_upgrade() -> None:
    """Keep existing admin accounts compatible with new dashboard modules."""
    try:
        with DB_LOCK, db() as conn:
            conn.execute("UPDATE users SET permissions=? WHERE role='admin'", (_permissions_string(ALL_PERMISSIONS),))
            conn.commit()
        kick_sql_sync("notification")
    except Exception:
        pass


def add_notification(level: str, title: str, message: str = "", raw: Any = None) -> None:
    try:
        with DB_LOCK, db() as conn:
            conn.execute("""
            INSERT INTO notifications (id, ts, level, title, message, seen, raw_json)
            VALUES (?, ?, ?, ?, ?, 0, ?)
            """, (
                str(uuid.uuid4()), now_ts_raw(), level or "info", str(title or "")[:250],
                str(message or "")[:1000],
                json.dumps(raw, ensure_ascii=False)[:5000] if raw is not None else None,
            ))
            conn.commit()
        kick_sql_sync("notification")
    except Exception:
        pass


def now_ts_raw() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

ensure_default_admin()
ensure_permission_upgrade()


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def detect_answer_type(text: str) -> str:
    n = normalize_ar(text)
    if "توضيح" in n or "لا يصح حسابها بالتخمين" in n or "تحتاج تحديد" in n:
        return "clarification_or_safe_stop"
    if "من التركة" in n and "مراجعة مجموع الانصبة" in n:
        return "calculation"
    return "fiqh_or_general"


def detect_dialect_label(question: str) -> str:
    n = normalize_ar(question)
    if any(w in n for w in ["ازاي", "ايه", "راجل", "وساب", "مراته"]):
        return "egyptian"
    if any(w in n for w in ["رجال", "شلون", "شنو", "كيف", "خلّف", "خلف"]):
        return "gulf_saudi"
    if any(w in n for w in ["قديش", "هيك", "شو", "مرتو", "توفّت", "توف ت", "بياخد"]):
        return "shami"
    if any(w in n for w in ["شنو", "فالميراث", "ديال", "واش"]):
        return "maghrebi"
    if any(w in n for w in ["الزول", "عندو", "المات"]):
        return "sudanese"
    return "arabic"




# ---------------- WhatsApp display identity helpers ----------------
def _normalize_digits_for_display(value: Any) -> str:
    """Return digits only. Arabic/Eastern digits are normalized by str.translate first."""
    if value is None:
        return ""
    txt = str(value).strip()
    trans = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
    txt = txt.translate(trans)
    return re.sub(r"\D", "", txt)


def _phone_from_raw_json(raw_json: Any) -> dict:
    """Extract phone-like identifier from WaPilot/Telegram raw payload if available.

    Important: WaPilot may send LID chat ids such as 1495...@lid. A LID is not a real
    phone number, so we display it as chat id and only show a phone when the payload
    contains a phone-style field such as senderPn/cleanedSenderPn/phone/number/wa_id
    or a @c.us/@s.whatsapp.net JID.
    """
    data = None
    if isinstance(raw_json, str) and raw_json.strip():
        try:
            data = json.loads(raw_json)
        except Exception:
            data = None
    elif isinstance(raw_json, dict):
        data = raw_json
    result = {"phone": "", "country_code": "", "chat_id": "", "source": ""}
    if not data:
        return result

    phone_keys = {
        "phone", "mobile", "number", "msisdn", "wa_id", "waid",
        "senderpn", "cleanedsenderpn", "recipient_id", "senderphone", "fromphone"
    }
    chat_keys = {"chat_id", "chatid", "from", "sender", "remotejid", "id"}

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                lk = str(k).lower()
                if isinstance(v, (str, int, float)):
                    sv = str(v).strip()
                    # Preserve the best chat id for display.
                    if not result["chat_id"] and lk in chat_keys and sv:
                        result["chat_id"] = sv
                    # Phone-specific fields are trusted more than generic ids.
                    if lk in phone_keys and sv:
                        digits = _normalize_digits_for_display(sv)
                        if len(digits) >= 8:
                            result["phone"] = digits
                            result["source"] = str(k)
                    # WhatsApp JIDs can contain the real phone number.
                    if not result["phone"] and re.search(r"@(c\.us|s\.whatsapp\.net)$", sv, re.I):
                        digits = _normalize_digits_for_display(sv.split("@", 1)[0])
                        if len(digits) >= 8:
                            result["phone"] = digits
                            result["source"] = str(k)
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)
    walk(data)

    phone = result.get("phone") or ""
    if phone:
        # Lightweight country-code extraction without assuming a complete libphonenumber install.
        # Prefer common Arab-region codes first, then use first 1-3 digits as a safe fallback.
        known = ["966","971","965","974","973","968","20","249","212","213","216","218","962","963","964","970","972","961","967","1","44","33","49","39","34","90","91","92"]
        for code in known:
            if phone.startswith(code) and len(phone) > len(code) + 5:
                result["country_code"] = "+" + code
                break
        if not result["country_code"]:
            result["country_code"] = "+" + phone[:3] if len(phone) >= 11 else ""
    return result


def _thread_identity_from_row(row: dict) -> dict:
    raw = row.get("raw_json") or ""
    extracted = _phone_from_raw_json(raw)
    user_id = str(row.get("thread_id") or row.get("user_id") or "")
    if user_id and not extracted.get("chat_id"):
        extracted["chat_id"] = user_id
    # Try user_id as a source only if it is not a LID. LID is not the phone number.
    if not extracted.get("phone") and user_id and "@lid" not in user_id.lower():
        if re.search(r"@(c\.us|s\.whatsapp\.net)$", user_id, re.I):
            digits = _normalize_digits_for_display(user_id.split("@", 1)[0])
        else:
            digits = _normalize_digits_for_display(user_id)
        if len(digits) >= 8:
            extracted["phone"] = digits
            extracted["source"] = "user_id"
            if not extracted.get("country_code"):
                known = ["966","971","965","974","973","968","20","249","212","213","216","218","962","963","964","970","972","961","967","1","44","33","49","39","34","90","91","92"]
                for code in known:
                    if digits.startswith(code) and len(digits) > len(code) + 5:
                        extracted["country_code"] = "+" + code
                        break
    extracted["display_phone"] = (extracted.get("country_code", "") + " " + extracted.get("phone", "")).strip() if extracted.get("phone") else "غير متاح"
    extracted["display_chat_id"] = extracted.get("chat_id") or user_id or "local"
    return extracted


def insert_conversation(record: dict) -> None:
    with DB_LOCK, db() as conn:
        conn.execute("""
        INSERT INTO conversations (id, ts, date, channel, user_id, user_name, direction,
                                   question, answer, answer_type, dialect, elapsed_ms, status, raw_json)
        VALUES (:id, :ts, :date, :channel, :user_id, :user_name, :direction,
                :question, :answer, :answer_type, :dialect, :elapsed_ms, :status, :raw_json)
        """, record)
        conn.commit()
    kick_sql_sync("conversation")


def log_service(service: str, action: str, status: str, message: str = "") -> None:
    with DB_LOCK, db() as conn:
        conn.execute("""
        INSERT INTO service_events (id, ts, service, action, status, message)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (str(uuid.uuid4()), now_ts(), service, action, status, message))
        conn.commit()
    kick_sql_sync("service_event")
    # UI notification: show clean human event, keep technical details in logs only.
    title_map = {
        "start": "تم التشغيل", "stop": "تم الإيقاف", "config_save": "تم حفظ الإعدادات",
        "send_error": "فشل إرسال رسالة", "loop_error": "خطأ في خدمة"
    }
    clean_title = title_map.get(action, f"حدث: {action}")
    if status in {"ok", "error", "warning"}:
        add_notification("error" if status == "error" else "info", clean_title, f"{service}: {message}")


def log_event(level: str, component: str, event: str, message: str = "", raw: Any = None) -> None:
    """Technical event log for dashboard, webhook, WaPilot send, errors, and diagnostics."""
    try:
        with DB_LOCK, db() as conn:
            conn.execute("""
            INSERT INTO technical_events (id, ts, date, level, component, event, message, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()), now_ts(), today_str(),
                str(level or "info"), str(component or "system"), str(event or "event"),
                str(message or "")[:4000],
                json.dumps(raw, ensure_ascii=False)[:12000] if raw is not None else None,
            ))
            conn.commit()
        if str(component) != "sqlserver":
            kick_sql_sync("technical_event")
        # Only notify relevant events; raw JSON remains in technical log, not in UI bubbles.
        if str(level).lower() in {"error", "critical", "warning"}:
            add_notification(str(level), f"{component}: {event}", str(message or "")[:300], raw)
        elif str(component) in {"wapilot", "telegram", "dashboard", "ngrok"} and str(event) in {"webhook_received", "send_ok", "send_failed", "ngrok_started", "ngrok_failed", "autostart_done"}:
            human = {
                "webhook_received": "وصلت رسالة واتساب",
                "send_ok": "تم إرسال رد واتساب",
                "send_failed": "فشل إرسال رد واتساب",
                "ngrok_started": "تم تشغيل ngrok",
                "ngrok_failed": "تعذر تشغيل ngrok",
                "autostart_done": "اكتمل التشغيل التلقائي",
            }.get(str(event), str(event))
            add_notification("info", human, str(message or "")[:300])
    except Exception:
        pass


def maybe_create_review_item(conversation_id: str, question: str, answer_text: str, answer_type: str, status: str) -> None:
    reasons: list[str] = []
    n = normalize_ar(question + " " + (answer_text or ""))
    if answer_type == "clarification_or_safe_stop":
        reasons.append("توضيح/إيقاف آمن")
    if any(w in n for w in ["جد مع اخ", "الاكدرية", "المشتركة", "الخنثى", "المفقود", "الحمل", "ذوي الارحام"]):
        reasons.append("باب متقدم أو خلافي")
    if "مش فاهم" in n or "بسط" in n or "مش واضح" in n:
        reasons.append("المستخدم طلب تبسيطًا")
    if status != "ok":
        reasons.append("خطأ معالجة")
    if not reasons:
        return
    with DB_LOCK, db() as conn:
        exists = conn.execute("SELECT id FROM review_items WHERE conversation_id=?", (conversation_id,)).fetchone()
        if exists:
            return
        conn.execute("""INSERT INTO review_items
            (id, ts, conversation_id, question, answer, reason, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            (str(uuid.uuid4()), now_ts(), conversation_id, question, answer_text, "، ".join(reasons)))
        conn.commit()



def _norm_runtime_text_v35(text: str) -> str:
    try:
        return normalize_ar(text or "")
    except Exception:
        s = re.sub(r"[\u064b-\u0652\u0670]", "", str(text or ""))
        return s.replace("أ","ا").replace("إ","ا").replace("آ","ا").replace("ة","ه").lower()


def _is_clarification_answer_v35(ans: str) -> bool:
    n = _norm_runtime_text_v35(ans)
    return any(x in n for x in ["يحتاج توضيح", "اكتب السؤال بصيغه اوضح", "لا يصح حسابها بالتخمين", "حدّد المذهب", "حدد المذهب", "هذه المساله تحتاج"])


def _extract_display_name_v35(raw: Any, fallback: str | None = None) -> str:
    """Extract a human display name from Telegram/WaPilot/dashboard payloads when available."""
    if fallback:
        return str(fallback).strip()
    names: list[str] = []
    def walk(x: Any):
        if isinstance(x, dict):
            for k, v in x.items():
                lk = str(k).lower()
                if isinstance(v, str) and lk in {"pushname", "push_name", "notifyname", "notify_name", "sendername", "sender_name", "name", "displayname", "display_name", "username", "first_name", "firstname"}:
                    vv = v.strip()
                    if vv and not re.search(r"@|\d{5,}", vv):
                        names.append(vv)
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)
    try:
        walk(raw)
    except Exception:
        pass
    return names[0] if names else ""


def _last_conversation_ts_v35(channel: str, user_id: str | None) -> str | None:
    if not user_id:
        return None
    try:
        with DB_LOCK, db() as conn:
            row = conn.execute("""
                SELECT ts FROM conversations
                WHERE channel=? AND user_id=?
                ORDER BY ts DESC LIMIT 1
            """, (channel, user_id)).fetchone()
            return row["ts"] if row else None
    except Exception:
        return None


def _should_daily_greet_v35(channel: str, user_id: str | None, cfg: dict) -> bool:
    if not cfg.get("operational", {}).get("daily_greeting_enabled", True):
        return False
    last_ts = _last_conversation_ts_v35(channel, user_id)
    if not last_ts:
        return True
    try:
        last = datetime.strptime(last_ts[:19], "%Y-%m-%dT%H:%M:%S")
        return (datetime.now() - last) >= timedelta(hours=20) or last.date() != datetime.now().date()
    except Exception:
        return True


def _detect_dialect_name_v35(q: str, context: dict | None = None) -> str:
    n = _norm_runtime_text_v35(q)
    if any(w in n for w in ["ازاي", "ايه", "مش", "مراته", "وساب", "عاوز", "مفهمتش"]):
        return "egyptian"
    if any(w in n for w in ["وش", "شلون", "ابشر", "كذا", "رجال", "خلّف", "خلف"]):
        return "gulf"
    if any(w in n for w in ["شو", "قديش", "هيك", "بدّي", "بدي", "مرة توفت"]):
        return "shami"
    if any(w in n for w in ["شنو", "بزاف", "واش", "فالميراث"]):
        return "moroccan"
    toks = set(n.split())
    if any(w in n for w in ["الزول", "عندو"]) or ("ليك" in toks) or ("كده" in toks):
        return "sudanese"
    if context and context.get("last_dialect"):
        return str(context.get("last_dialect"))
    return "standard"


def _pick_variant_v35(options: list[str], seed: str) -> str:
    if not options:
        return ""
    h = int(hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
    return options[h % len(options)]


def _greeting_v35(name: str, dialect: str, seed: str) -> str:
    safe_name = (name or "").strip()
    who = f" يا {safe_name}" if safe_name else ""
    pools = {
        "egyptian": [f"أهلًا{who}، نورت مفتي المواريث الذكي.", f"مرحبًا{who}، جاهز أساعدك في مسألة المواريث."],
        "gulf": [f"حياك الله{who}، تفضل بسؤالك في المواريث.", f"مرحبًا{who}، أبشر أساعدك في مسألة الفرائض."],
        "shami": [f"أهلًا وسهلًا{who}، احكيلي مسألتك بالمواريث.", f"مرحبًا{who}، جاهز أساعدك بالمسألة."],
        "moroccan": [f"مرحبا{who}، تفضل بسؤالك في المواريث.", f"أهلًا{who}، نعاونك في مسألة الإرث."],
        "sudanese": [f"مرحب{who}، أرسل مسألتك ونرتبها ليك.", f"أهلًا{who}، جاهز أساعدك في قسمة الميراث."],
        "standard": [f"مرحبًا{who}، تفضل بسؤالك في المواريث.", f"أهلًا{who}، يسعدني مساعدتك في مسألة الفرائض."]
    }
    return _pick_variant_v35(pools.get(dialect, pools["standard"]), seed)


def _preamble_v35(question: str, answer_text: str, name: str, dialect: str, seed: str) -> str:
    # V37: formal religious preamble only for a real fiqh/calculation answer.
    # It must NOT appear after greetings/thanks/ack/follow-up simplification.
    if _is_clarification_answer_v35(answer_text):
        return ""
    try:
        if not should_decorate_with_preamble(question, answer_text, None):
            return ""
        return preamble_human(question, answer_text, name, dialect, seed)
    except Exception:
        pass
    safe_name = (name or "").strip()
    name_part = f" يا {safe_name}" if safe_name else ""
    return f"بسم الله الرحمن الرحيم. بناءً على ما ورد في سؤالك{name_part}، فهذا بيان المسألة:"


def _decorate_answer_v35(question: str, ans: str, channel: str, user_id: str | None, user_name: str | None, raw: Any, context: dict, cfg: dict) -> tuple[str, str, str]:
    # V40 hard guard: لو الرسالة اجتماعية بحتة، لا نسمح بأي رد افتراضي آلي
    # مثل "اكتب السؤال بصيغة أوضح" ولا بأي مقدمة فتوى.
    try:
        if is_pure_social_message(question, context):
            display_name0 = _extract_display_name_v35(raw, user_name) or ("مدير النظام" if channel == "dashboard" else "")
            dialect0 = _detect_dialect_name_v35(question, context)
            try:
                d0 = detect_dialect_human(question, context)
                if d0 and d0 != "standard":
                    dialect0 = d0
            except Exception:
                pass
            return human_smalltalk_reply(question, context=context, name=display_name0), display_name0, dialect0
    except Exception:
        pass
    dialect = _detect_dialect_name_v35(question, context)
    try:
        # Prefer the stronger v37 dialect detector when it recognizes a dialect.
        d2 = detect_dialect_human(question, context)
        if d2 and d2 != "standard":
            dialect = d2
    except Exception:
        pass
    display_name = _extract_display_name_v35(raw, user_name) or ("مدير النظام" if channel == "dashboard" else "")
    parts = []
    try:
        role = answer_role(question, ans, context)
    except Exception:
        role = "general"
    # Daily greeting is only for the first substantive interaction of the day.
    # Do not prepend it to pure greetings/thanks/ack/follow-up, otherwise the chat becomes robotic.
    if role in {"calculation", "fiqh", "general"} and _should_daily_greet_v35(channel, user_id, cfg):
        parts.append(_greeting_v35(display_name, dialect, f"greet:{channel}:{user_id}:{today_str()}"))
    # Formal opener only for actual fatwa/explanation/calculation, not smalltalk or follow-up simplification.
    if cfg.get("operational", {}).get("answer_preamble_enabled", True) and role in {"calculation", "fiqh"}:
        pre = _preamble_v35(question, ans, display_name, dialect, f"pre:{channel}:{user_id}:{question[:80]}:{today_str()}")
        if pre:
            parts.append(pre)
    if parts:
        ans = "\n\n".join(parts + [ans])
    return ans, display_name, dialect

def _processing_notice_v35(question: str, channel: str = "whatsapp") -> str:
    try:
        # Social messages like السلام عليكم / كيف حالك must never receive "جارٍ تحليل المسألة".
        if is_pure_social_message(question, None):
            return ""
        if not should_send_processing_notice(question, None):
            return ""
    except Exception:
        pass
    dialect = _detect_dialect_name_v35(question, None)
    pools = {
        "egyptian": ["⏳ جارٍ فهم المسألة وتجهيز الرد...", "⏳ لحظة، براجع السؤال وبحضّر الإجابة..."],
        "gulf": ["⏳ جارٍ دراسة المسألة وتجهيز الرد...", "⏳ أبشر، يتم الآن تجهيز الجواب..."],
        "shami": ["⏳ لحظة، عم راجع المسألة وبجهّز الجواب..."],
        "standard": ["⏳ جارٍ فهم السؤال وتجهيز الإجابة...", "⏳ يتم الآن تحليل المسألة وإعداد الرد..."]
    }
    return _pick_variant_v35(pools.get(dialect, pools["standard"]), f"proc:{channel}:{question[:80]}:{now_ts_raw()[:13]}")


def ask_runtime(question: str, channel: str = "dashboard", user_id: str | None = None, user_name: str | None = None, raw: Any = None) -> dict:
    rid = str(uuid.uuid4())
    t0 = time.time()
    cfg = load_config()
    session_key = f"{channel}:{user_id or 'local'}"
    with SESSION_LOCK:
        context = dict(SESSION_CONTEXTS.get(session_key, {}))
    display_name = _extract_display_name_v35(raw, user_name) or ("مدير النظام" if channel == "dashboard" else "")

    # V50 Comprehensive Scholarly Understanding Engine: broad ontology + semantic reasoning.
    # It runs before all older semantic layers. It is not a fixed Q/A patch; it scores
    # descriptions against a structured ontology of inheritance concepts.
    pre_routed_v50 = False
    skip_legacy_semantic_v50 = False
    pre_routed_v49 = False
    skip_legacy_semantic_v49 = False
    try:
        import v50_comprehensive_scholarly_understanding as _v50brain
        v50_route = _v50brain.route(question, context=context, name=display_name)
        if v50_route.action == "answer" and v50_route.answer:
            ans = v50_route.answer
            dialect = v50_route.dialect
            status = f"ok:v50:{v50_route.intent}"
            pre_routed_v50 = True
            skip_legacy_semantic_v50 = True
            skip_legacy_semantic_v49 = True
            if v50_route.concept_id:
                context["last_concept"] = v50_route.concept_id
            try:
                log_event("info", "runtime", "v50_answer", status, {"question": question, "intent": v50_route.intent, "concept_id": v50_route.concept_id, "confidence": v50_route.confidence, "reason": v50_route.reason})
            except Exception:
                pass
        elif v50_route.action == "pass" and v50_route.intent in {"inheritance_calculation"}:
            skip_legacy_semantic_v50 = True
            skip_legacy_semantic_v49 = True
            try:
                log_event("info", "runtime", "v50_pass_to_inheritance", v50_route.intent, {"question": question})
            except Exception:
                pass
    except Exception as e:
        pre_routed_v50 = False
        skip_legacy_semantic_v50 = False
        try:
            log_event("warning", "runtime", "v50_failed", str(e), {"question": question})
        except Exception:
            pass

    # v49 Scholarly Semantic Reasoner: legacy semantic layer.
    if not pre_routed_v50:
        try:
            import v49_semantic_reasoner as _v49brain
            v49_route = _v49brain.route(question, context=context, name=display_name)
            if v49_route.action == "answer" and v49_route.answer:
                ans = v49_route.answer
                dialect = v49_route.dialect
                status = f"ok:v49:{v49_route.intent}"
                pre_routed_v49 = True
                skip_legacy_semantic_v49 = True
                if v49_route.concept_id:
                    context["last_concept"] = v49_route.concept_id
                try:
                    log_event("info", "runtime", "v49_answer", status, {"question": question, "intent": v49_route.intent, "concept_id": v49_route.concept_id, "confidence": v49_route.confidence, "reason": v49_route.reason})
                except Exception:
                    pass
            elif v49_route.action == "pass" and v49_route.intent in {"inheritance_calculation"}:
                skip_legacy_semantic_v49 = True
                try:
                    log_event("info", "runtime", "v49_pass_to_inheritance", v49_route.intent, {"question": question})
                except Exception:
                    pass
        except Exception as e:
            pre_routed_v49 = False
            skip_legacy_semantic_v49 = skip_legacy_semantic_v50
            try:
                log_event("warning", "runtime", "v49_failed", str(e), {"question": question})
            except Exception:
                pass

    # Runs before v47/v45/v46. It separates social chat, calculation pass-through,
    # and semantic concept understanding using ontology scoring, not fixed answers.
    pre_routed_v48 = False
    skip_legacy_semantic = False
    try:
        import v48_scholarly_intelligence_engine as _v48brain
        display_name = _extract_display_name_v35(raw, user_name) or ("مدير النظام" if channel == "dashboard" else "")
        v48_route = _v48brain.route(question, context=context, name=display_name)
        if v48_route.action == "answer" and v48_route.answer:
            ans = v48_route.answer
            dialect = v48_route.dialect
            status = f"ok:v48:{v48_route.intent}"
            pre_routed_v48 = True
            skip_legacy_semantic = True
            if v48_route.concept_id:
                context["last_concept"] = v48_route.concept_id
            try:
                log_event("info", "runtime", "v48_answer", status, {"question": question, "intent": v48_route.intent, "concept_id": v48_route.concept_id, "confidence": v48_route.confidence, "reason": v48_route.reason})
            except Exception:
                pass
        elif v48_route.action == "pass" and v48_route.intent in {"inheritance_calculation"}:
            # Prevent older concept layers from consuming calculation questions as concept definitions.
            skip_legacy_semantic = True
            try:
                log_event("info", "runtime", "v48_pass_to_inheritance", v48_route.intent, {"question": question})
            except Exception:
                pass
    except Exception as e:
        if str(e) == "v49_already_answered":
            pre_routed_v48 = False
        else:
            pre_routed_v48 = False
            skip_legacy_semantic = skip_legacy_semantic_v49
            try:
                log_event("warning", "runtime", "v48_failed", str(e), {"question": question})
            except Exception:
                pass

    # V47: comprehensive semantic/dialogue understanding engine.
    # It runs before v45/v46 and handles: social chat, reverse definitions,
    # concept disambiguation, differences, lists, and contextual follow-up.
    pre_routed_v47 = False
    try:
        import v47_full_understanding_engine as _v47brain
        display_name = _extract_display_name_v35(raw, user_name) or ("مدير النظام" if channel == "dashboard" else "")
        v47_out = _v47brain.answer(question, context=context, name=display_name)
        if (not skip_legacy_semantic) and v47_out and v47_out.get("answer"):
            ans = v47_out["answer"]
            dialect = _v47brain.detect_dialect(question, context)
            status = f"ok:v47:{v47_out.get('intent','semantic')}"
            pre_routed_v47 = True
            if v47_out.get("concept_id"):
                context["last_concept"] = v47_out.get("concept_id")
            try:
                log_event("info", "runtime", "v47_answer", status, {"question": question, "intent": v47_out.get("intent"), "concept_id": v47_out.get("concept_id"), "confidence": v47_out.get("confidence")})
            except Exception:
                pass
    except Exception as e:
        pre_routed_v47 = False
        try:
            log_event("warning", "runtime", "v47_failed", str(e), {"question": question})
        except Exception:
            pass

    # V45: production dialogue router before any inheritance/model path.
    # This prevents social/status/unknown non-domain messages from leaking into the fatwa engine,
    # and handles follow-ups from the saved session context.
    pre_routed_v45 = False
    try:
        if not pre_routed_v47:
            import v45_full_scholarly_production as _v45route
            v45_route = _v45route.route(question, context)
            if v45_route.social or v45_route.intent in {"general_non_domain", "small_unknown", "identity"}:
                display_name = _extract_display_name_v35(raw, user_name) or ("مدير النظام" if channel == "dashboard" else "")
                dialect = v45_route.dialect
                ans = _v45route.social_reply(question, context=context, name=display_name)
                status = f"ok:v45:{v45_route.intent}"
                pre_routed_v45 = True
            elif v45_route.followup:
                display_name = _extract_display_name_v35(raw, user_name) or ("مدير النظام" if channel == "dashboard" else "")
                dialect = v45_route.dialect
                ans = _v45route.followup_reply(question, context=context)
                status = f"ok:v45:{v45_route.intent}"
                pre_routed_v45 = True
            elif v45_route.review_required and not v45_route.domain:
                display_name = _extract_display_name_v35(raw, user_name) or ("مدير النظام" if channel == "dashboard" else "")
                dialect = v45_route.dialect
                ans = "هذه الرسالة تحتاج توضيحًا قبل أن أتعامل معها كمسألة مواريث. اكتب الورثة أو الحكم الذي تريد بيانه بوضوح."
                status = f"review:v45:{v45_route.intent}"
                pre_routed_v45 = True
    except Exception as e:
        pre_routed_v45 = False
        try:
            log_event("warning", "runtime", "v45_preroute_failed", str(e), {"question": question})
        except Exception:
            pass
    # V43: route pure human small-talk before calling the inheritance/fiqh runtime.
    # This prevents harmless messages like "بخير الحمد لله" from leaking into
    # the model/runtime path and returning unrelated scholarly fragments.
    pre_routed_social = False
    try:
        if is_pure_social_message(question, context):
            display_name = _extract_display_name_v35(raw, user_name) or ("مدير النظام" if channel == "dashboard" else "")
            dialect = _detect_dialect_name_v35(question, context)
            try:
                d0 = detect_dialect_human(question, context)
                if d0 and d0 != "standard":
                    dialect = d0
            except Exception:
                pass
            ans = human_smalltalk_reply(question, context=context, name=display_name)
            status = "ok:social"
            pre_routed_social = True
    except Exception as e:
        pre_routed_social = False
        log_event("warning", "runtime", "social_preroute_failed", str(e), {"question": question})

    if pre_routed_v50:
        pre_routed_social = True
    if pre_routed_v48:
        pre_routed_social = True
    if pre_routed_v47:
        pre_routed_social = True
    if pre_routed_v45:
        pre_routed_social = True

    # V46: Scholarly Semantic Concept Engine.
    # This is the non-RAG/non-fixed-answer layer that understands reverse definitions
    # and disambiguates concepts like: الفرض vs العول/الرد when those are only constraints.
    pre_routed_v46 = False
    if (not pre_routed_social) and (not skip_legacy_semantic):
        try:
            import v46_semantic_concept_engine as _v46sem
            display_name = _extract_display_name_v35(raw, user_name) or ("مدير النظام" if channel == "dashboard" else "")
            sem = _v46sem.answer(question, context=context, name=display_name)
            if sem and sem.get("answer"):
                ans = sem["answer"]
                status = f"ok:v46_semantic:{sem.get('concept_id','concept')}"
                dialect = _v46sem.detect_dialect(question, context)
                context["last_concept"] = sem.get("concept_id") or context.get("last_concept")
                pre_routed_v46 = True
                pre_routed_social = True
                try:
                    log_event("info", "runtime", "v46_semantic_answer", status, {"question": question, "concept_id": sem.get("concept_id"), "confidence": sem.get("confidence"), "qtype": sem.get("qtype")})
                except Exception:
                    pass
        except Exception as e:
            try:
                log_event("warning", "runtime", "v46_semantic_failed", str(e), {"question": question})
            except Exception:
                pass

    if not pre_routed_social:
        try:
            ans = answer(question, context=context)
            status = "ok"
        except Exception as e:
            ans = "حدث خطأ داخلي أثناء معالجة السؤال. راجع السجل الفني قبل الاعتماد على أي نتيجة."
            status = f"error:{type(e).__name__}"
            log_event("error", "runtime", "ask_failed", status, {"question": question, "exception": str(e)})
        ans, display_name, dialect = _decorate_answer_v35(question, ans, channel, user_id, user_name, raw, context, cfg)
    elapsed = int((time.time() - t0) * 1000)
    rec = {
        "id": rid,
        "ts": now_ts(),
        "date": today_str(),
        "channel": channel,
        "user_id": user_id,
        "user_name": display_name or user_name,
        "direction": "inout",
        "question": question,
        "answer": ans,
        "answer_type": detect_answer_type(ans),
        "dialect": dialect,
        "elapsed_ms": elapsed,
        "status": status,
        "raw_json": json.dumps(raw, ensure_ascii=False) if raw is not None else None,
    }
    insert_conversation(rec)
    try:
        maybe_create_review_item(rid, question, ans, rec["answer_type"], status)
    except Exception:
        pass
    try:
        try:
            import v50_comprehensive_scholarly_understanding as _v50ctx
            last_concept = _v50ctx.detect_concept_key(question) or context.get("last_concept")
            if not last_concept:
                import v49_semantic_reasoner as _v49ctx
                last_concept = _v49ctx.detect_concept_key(question) or context.get("last_concept")
            if not last_concept:
                import v48_scholarly_intelligence_engine as _v48ctx
                last_concept = _v48ctx.detect_concept_key(question) or context.get("last_concept")
        except Exception:
            try:
                import v46_semantic_concept_engine as _v46ctx
                last_concept = _v46ctx.detect_concept_key(question) or detect_concept_key(question) or context.get("last_concept")
            except Exception:
                last_concept = detect_concept_key(question) or context.get("last_concept")
        with SESSION_LOCK:
            SESSION_CONTEXTS[session_key] = {
                "last_question": question,
                "last_answer": ans,
                "last_concept": last_concept,
                "last_dialect": dialect,
                "last_user_name": display_name or user_name or context.get("last_user_name", ""),
                "last_seen_at": now_ts_raw(),
            }
    except Exception:
        pass
    return {"request_id": rid, "answer": ans, "elapsed_ms": elapsed, "answer_type": rec["answer_type"]}


class TelegramWorker:
    def __init__(self):
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.running = False
        self.last_error = ""
        self.bot_username = ""

    def _base_url(self, token: str) -> str:
        return f"https://api.telegram.org/bot{token}"

    def validate_token(self, token: str) -> tuple[bool, str, dict]:
        """Validate Telegram token before starting the polling loop.
        This prevents showing 'شغال' while Telegram is actually returning 404 Not Found.
        """
        token = clean_telegram_token(token)
        fmt = telegram_token_format_status(token)
        diag = {"format": fmt, "endpoint": "getMe"}
        if not token:
            return False, "توكن تليجرام غير موجود. ضعه من صفحة الإعدادات أولًا.", diag
        if not fmt.get("looks_like_botfather_token"):
            return False, "صيغة توكن تليجرام غير صحيحة. توكن BotFather يكون مثل: 1234567890:AA... وليس API ID أو API Hash.", diag
        try:
            url = self._base_url(token) + "/getMe"
            resp = requests.get(url, timeout=12)
            diag.update({
                "url": url.replace(token, mask_secret(token)),
                "status_code": resp.status_code,
                "response_preview": resp.text[:1000],
            })
            if resp.status_code == 404:
                return False, "توكن تليجرام غير صحيح أو البوت غير موجود (HTTP 404). انسخ التوكن كاملًا من BotFather مرة أخرى.", diag
            data = resp.json()
            diag["telegram_response"] = data
            if not data.get("ok"):
                return False, f"فشل التحقق من توكن تليجرام: {str(data)[:220]}", diag
            username = (data.get("result") or {}).get("username") or ""
            self.bot_username = username
            return True, ("تم التحقق من تليجرام" + (f" @{username}" if username else "")), diag
        except Exception as e:
            diag["exception"] = f"{type(e).__name__}: {e}"
            return False, f"تعذر الاتصال بتليجرام للتحقق من التوكن: {type(e).__name__}: {e}", diag

    def start(self) -> tuple[bool, str]:
        global CONFIG
        cfg = refresh_runtime_config()
        token = clean_telegram_token(cfg.get("telegram", {}).get("bot_token", ""))
        CONFIG.setdefault("telegram", {})["bot_token"] = token
        if self.running:
            return True, "Telegram يعمل بالفعل."
        ok, msg, diag = self.validate_token(token)
        if not ok:
            self.last_error = msg
            self.running = False
            log_service("telegram", "start", "error", msg)
            log_event("error", "telegram", "start_failed", msg, raw=diag)
            return False, msg
        self.last_error = ""
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.running = True
        log_service("telegram", "start", "ok", msg)
        return True, msg

    def stop(self) -> tuple[bool, str]:
        self.stop_event.set()
        self.running = False
        log_service("telegram", "stop", "ok", "stopped")
        return True, "Telegram stopped"

    def _loop(self) -> None:
        global CONFIG
        cfg = refresh_runtime_config()
        token = clean_telegram_token(cfg.get("telegram", {}).get("bot_token", ""))
        CONFIG.setdefault("telegram", {})["bot_token"] = token
        base = f"https://api.telegram.org/bot{token}"
        last_update_id = int(CONFIG.get("telegram", {}).get("last_update_id", 0) or 0)
        while not self.stop_event.is_set():
            try:
                resp = requests.get(base + "/getUpdates", params={"offset": last_update_id + 1, "timeout": 15}, timeout=25)
                if resp.status_code == 404:
                    self.last_error = "توكن تليجرام غير صحيح أو البوت غير موجود (HTTP 404)."
                    self.running = False
                    log_event("error", "telegram", "polling_failed", self.last_error, raw={"status_code": resp.status_code, "response_preview": resp.text[:1000]})
                    break
                data = resp.json()
                if not data.get("ok"):
                    self.last_error = str(data)[:500]
                    log_event("warning", "telegram", "polling_warning", self.last_error, raw={"response_preview": str(data)[:1000]})
                    time.sleep(3)
                    continue
                for upd in data.get("result", []):
                    last_update_id = max(last_update_id, int(upd.get("update_id", 0)))
                    CONFIG["telegram"]["last_update_id"] = last_update_id
                    save_config(CONFIG)
                    msg = upd.get("message") or upd.get("edited_message") or {}
                    chat = msg.get("chat") or {}
                    chat_id = chat.get("id")
                    text = msg.get("text") or ""
                    if not chat_id or not text:
                        continue
                    if text.strip().lower() in ["/start", "start"]:
                        ans = "أرسل مسألة ميراث أو سؤالًا فقهيًا. لو السؤال ناقص سأطلب توضيحًا بدل التخمين."
                    else:
                        try:
                            requests.post(base + "/sendChatAction", json={"chat_id": chat_id, "action": "typing"}, timeout=8)
                        except Exception:
                            pass
                        out = ask_runtime(text, channel="telegram", user_id=str(chat_id), user_name=chat.get("username") or chat.get("first_name"), raw=upd)
                        ans = out["answer"]
                    for i in range(0, len(ans), 3900):
                        requests.post(base + "/sendMessage", json={"chat_id": chat_id, "text": ans[i:i+3900]}, timeout=15)
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
                log_service("telegram", "loop_error", "error", self.last_error)
                time.sleep(5)
        self.running = False


TELEGRAM = TelegramWorker()


WHATSAPP_STATUS = {
    "enabled": bool(CONFIG.get("wapilot", {}).get("enabled", False)),
    "last_error": "",
    "sent": 0,
    "received": 0,
    "last_webhook_at": "",
    "last_webhook_sender": "",
    "last_webhook_text": "",
    "last_send_response": "",
}


def refresh_runtime_config() -> dict:
    """Reload Registry/.env/project config into the live process.

    This prevents a common replacement-package bug: Settings/Telegram check read
    the token from Registry correctly, while the already-loaded service worker
    still uses an old in-memory CONFIG. All service starts and webhooks must call
    this before making decisions.
    """
    global CONFIG, WHATSAPP_STATUS
    cfg = load_config()
    cfg.setdefault("telegram", {})["bot_token"] = clean_telegram_token(cfg.get("telegram", {}).get("bot_token", ""))
    CONFIG = cfg
    WHATSAPP_STATUS["enabled"] = bool(cfg.get("wapilot", {}).get("enabled", False))
    return cfg


def extract_first_text_and_sender(payload: Any) -> tuple[str | None, str | None, dict]:
    """Robust extractor for WaPilot/WhatsApp-like payloads. It deliberately avoids hard failure on unknown JSON shapes."""
    candidates_text_keys = {"text", "message", "body", "content", "caption", "conversation"}
    candidates_sender_keys = {"chat_id", "chatId", "from", "sender", "phone", "mobile", "number", "wa_id", "remoteJid", "senderPn", "cleanedSenderPn", "recipient_id"}
    found_text = None
    found_sender = None
    meta: dict[str, Any] = {}

    def walk(x: Any, path: str = ""):
        nonlocal found_text, found_sender
        if isinstance(x, dict):
            # Meta WhatsApp nested text object: {text: {body: ...}}
            if isinstance(x.get("text"), dict) and isinstance(x["text"].get("body"), str):
                found_text = found_text or x["text"]["body"]
            if isinstance(x.get("message"), dict) and isinstance(x["message"].get("text"), str):
                found_text = found_text or x["message"]["text"]
            for k, v in x.items():
                lk = str(k).lower()
                if found_text is None and lk in candidates_text_keys and isinstance(v, str) and len(v.strip()) > 0:
                    # avoid picking status words as message text
                    if v.strip().lower() not in {"sent", "delivered", "read", "message", "messages"}:
                        found_text = v.strip()
                if found_sender is None and lk in {s.lower() for s in candidates_sender_keys} and isinstance(v, (str, int)):
                    raw_sender = str(v).strip()

                    # IMPORTANT for WaPilot:
                    # The send-message endpoint requires chat_id. When webhook payload contains
                    # WhatsApp/LID chat ids such as "149581346173069@lid", "2010...@c.us",
                    # "...@s.whatsapp.net", or group ids "...@g.us", we must preserve the exact
                    # chat id. Stripping it to digits can make WaPilot queue the message but the
                    # worker cannot deliver it to the original chat.
                    if raw_sender and re.search(r"@(lid|c\.us|s\.whatsapp\.net|g\.us)$", raw_sender, re.I):
                        found_sender = raw_sender
                    elif lk in {"chat_id", "chatid"} and raw_sender:
                        found_sender = raw_sender
                    else:
                        # Last-resort support for payloads that only include a bare phone/number.
                        sv = raw_sender.replace("@s.whatsapp.net", "").replace("@c.us", "")
                        if re.search(r"\d{6,}", sv):
                            found_sender = re.sub(r"\D", "", sv)
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(x, list):
            for i, item in enumerate(x):
                walk(item, f"{path}[{i}]")

    walk(payload)
    meta["text_found"] = found_text is not None
    meta["sender_found"] = found_sender is not None
    return found_text, found_sender, meta


def _mask_header_value(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 10:
        return "***"
    return value[:4] + "***" + value[-4:]


def _write_wapilot_send_attempt(record: dict) -> None:
    """Append outbound send diagnostics without exposing full secrets."""
    try:
        path = LOG_DIR / "wapilot_send_attempts.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _recipient_variants(to_number: str) -> list[str]:
    raw = str(to_number or "").strip()
    digits = re.sub(r"\D", "", raw)
    variants: list[str] = []
    for v in [raw, digits, ("+" + digits if digits else "")]:
        if v and v not in variants:
            variants.append(v)
    return variants


def wapilot_send(to_number: str, message: str) -> tuple[bool, str]:
    """
    Send a WhatsApp reply through WaPilot API v2 using the documented contract:
    POST /api/v2/{instance_id}/send-message
    Headers: token, Content-Type: application/json
    Body: {"chat_id": ..., "text": ...}
    Optional: priority, send_at.
    """
    global CONFIG, WHATSAPP_STATUS
    wcfg = refresh_runtime_config().get("wapilot", {})
    token = str(wcfg.get("api_token", "") or "").strip()
    instance_id = str(wcfg.get("instance_id", "") or "").strip()
    if not token:
        msg = "WAPILOT_API_TOKEN غير موجود. ضعه من Settings."
        log_event("error", "wapilot", "send_config_missing", msg)
        return False, msg
    if not instance_id:
        msg = "WAPILOT_INSTANCE_ID غير موجود."
        log_event("error", "wapilot", "send_config_missing", msg)
        return False, msg

    api_template = wcfg.get("api_url_template", DEFAULT_CONFIG["wapilot"]["api_url_template"])
    url = api_template.format(instance_id=instance_id).strip()
    chat_id = str(to_number or "").strip()
    if not chat_id:
        msg = "لم أستطع استخراج chat_id للرد عليه. راجع logs/wapilot_last_payload.json."
        log_event("error", "wapilot", "send_no_chat_id", msg)
        return False, msg

    headers = {"token": token, "Content-Type": "application/json", "Accept": "application/json"}
    payload = {"chat_id": chat_id, "text": message}
    if wcfg.get("send_priority") not in [None, "", False]:
        try:
            payload["priority"] = int(wcfg.get("send_priority"))
        except Exception:
            payload["priority"] = wcfg.get("send_priority")

    started = time.time()
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        elapsed_ms = int((time.time() - started) * 1000)
        body = r.text[:3000]
        rec = {
            "ts": now_ts(),
            "url": url,
            "chat_id": chat_id,
            "chat_id_type": ("lid" if chat_id.endswith("@lid") else "c.us" if chat_id.endswith("@c.us") else "s.whatsapp.net" if chat_id.endswith("@s.whatsapp.net") else "group" if chat_id.endswith("@g.us") else "bare"),
            "payload_keys": list(payload.keys()),
            "payload_preview": {"chat_id": chat_id, "text": f"<message {len(message)} chars>"},
            "headers": {"token": _mask_header_value(token), "Content-Type": "application/json"},
            "status_code": r.status_code,
            "elapsed_ms": elapsed_ms,
            "response": body,
        }
        _write_wapilot_send_attempt(rec)
        log_event("info" if 200 <= r.status_code < 300 else "error", "wapilot", "send_message", f"HTTP {r.status_code}: {body[:800]}", rec)
        if 200 <= r.status_code < 300:
            WHATSAPP_STATUS["sent"] += 1
            return True, f"HTTP {r.status_code}: {body[:800]}"
        final = f"فشل إرسال WaPilot. HTTP {r.status_code}: {body[:800]}"
        WHATSAPP_STATUS["last_error"] = final[:800]
        log_service("whatsapp", "send_error", "error", final[:800])
        return False, final
    except Exception as e:
        elapsed_ms = int((time.time() - started) * 1000)
        msg = f"{type(e).__name__}: {e}"
        rec = {
            "ts": now_ts(), "url": url, "chat_id": chat_id,
            "payload_keys": list(payload.keys()),
            "headers": {"token": _mask_header_value(token), "Content-Type": "application/json"},
            "status_code": None, "elapsed_ms": elapsed_ms, "exception": msg,
        }
        _write_wapilot_send_attempt(rec)
        log_event("error", "wapilot", "send_exception", msg, rec)
        WHATSAPP_STATUS["last_error"] = msg[:800]
        return False, msg


app = FastAPI(title="Mawareth AI Admin Dashboard", version="1.0")

# v15 security rule:
# Everything is protected server-side except login/static/health and WaPilot webhook.
# The webhook must remain public so WaPilot can deliver inbound WhatsApp events.
AUTH_WHITELIST_PREFIXES = (
    "/static/",
    "/assets/",
    "/api/login",
    "/health",
    "/webhook/wapilot",
)
AUTH_EXACT_WHITELIST = {"/login", "/favicon.ico"}


def _get_session_user_from_token(token: str | None) -> dict | None:
    if not token:
        return None
    with DB_LOCK, db() as conn:
        row = conn.execute("""
        SELECT s.token, s.username, s.expires_at, u.display_name, u.role, u.permissions, u.active
        FROM sessions s JOIN users u ON u.username=s.username
        WHERE s.token=?
        """, (token,)).fetchone()
        if not row or not row["active"]:
            return None
        if row["expires_at"] < now_ts():
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            conn.commit()
            return None
        conn.execute("UPDATE sessions SET last_seen=? WHERE token=?", (now_ts(), token))
        conn.commit()
    perms = _parse_permissions(row["permissions"])
    return {"username": row["username"], "display_name": row["display_name"], "role": row["role"], "permissions": perms}


def _required_permission_for_path(path: str, method: str) -> str | None:
    if path in {"/", "/api/me", "/api/notifications", "/api/notifications/read"}:
        return None
    if path.startswith("/api/users"):
        return "users"
    if path.startswith("/api/health"):
        return "health"
    if path.startswith("/api/system-test"):
        return "tests"
    if path.startswith("/api/backup"):
        return "backup"
    if path.startswith("/api/conversations"):
        return "conversations"
    if path.startswith("/api/review"):
        return "review"
    if path.startswith("/api/login-attempts"):
        return "security"
    if path.startswith("/api/operational"):
        return "services"
    if path.startswith("/api/config") or path.startswith("/api/logo") or path.startswith("/api/registry") or path.startswith("/api/sqlserver"):
        return "settings"
    if path.startswith("/api/services") or path.startswith("/api/wapilot/test-send"):
        return "services"
    if path.startswith("/api/events") or path.startswith("/api/export/events"):
        return "events"
    if path.startswith("/api/errors") or path.startswith("/api/export/errors"):
        return "errors"
    if path.startswith("/api/logs") or path.startswith("/api/export/logs"):
        return "logs"
    if path.startswith("/api/remote") or path.startswith("/api/ngrok"):
        return "remote"
    if path.startswith("/api/security"):
        return "settings"
    if path.startswith("/api/ask"):
        return "chat"
    if path.startswith("/api/stats"):
        return "dashboard"
    return None


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path in AUTH_EXACT_WHITELIST or any(path.startswith(p) for p in AUTH_WHITELIST_PREFIXES):
        return await call_next(request)
    if not _auth_is_enabled():
        return await call_next(request)
    # Do not accept legacy cookie names here; v15 intentionally forces a fresh login
    # after the server-side security patch.
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = _get_session_user_from_token(token)
    if not user:
        if path.startswith("/api/"):
            return JSONResponse(status_code=401, content={"ok": False, "error": "login_required"})
        resp = FileResponse(STATIC_DIR / "login.html")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return resp
    request.state.user = user
    required = _required_permission_for_path(path, request.method)
    if required and required not in user.get("permissions", []):
        if path.startswith("/api/"):
            return JSONResponse(status_code=403, content={"ok": False, "error": "forbidden", "required": required})
        return FileResponse(STATIC_DIR / "index.html")
    return await call_next(request)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    msg = f"{type(exc).__name__}: {exc}"
    log_event("error", "dashboard", "unhandled_exception", msg, {"path": str(request.url), "method": request.method})
    return JSONResponse(status_code=500, content={"ok": False, "error": "Internal Server Error", "detail": msg[:800]})

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class AskReq(BaseModel):
    question: str
    channel: str = "dashboard"
    user_id: str | None = None


class LoginReq(BaseModel):
    username: str
    password: str
    remember: bool = False


@app.get("/login", response_class=HTMLResponse)
def login_page():
    resp = FileResponse(STATIC_DIR / "login.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.post("/api/login")
def api_login(req: LoginReq, request: Request):
    username = req.username.strip()
    ip = request.client.host if request.client else ""
    cfg = load_config()
    max_failed = int(cfg.get("security", {}).get("max_failed_login", 5) or 5)
    lock_minutes = int(cfg.get("security", {}).get("lockout_minutes", 15) or 15)
    with DB_LOCK, db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
        locked = False
        if row and row["locked_until"] if "locked_until" in row.keys() else None:
            locked = str(row["locked_until"]) > now_ts()
        if locked:
            conn.execute("INSERT INTO login_attempts (id, ts, username, success, ip, message) VALUES (?, ?, ?, 0, ?, ?)",
                         (str(uuid.uuid4()), now_ts(), username, ip, "locked"))
            conn.commit()
            return JSONResponse(status_code=423, content={"ok": False, "error": "الحساب مقفول مؤقتًا بسبب محاولات دخول فاشلة. حاول لاحقًا."})
        if not row or not _verify_password(req.password, row["password_hash"]):
            if row:
                failed = int(row["failed_login_count"] if "failed_login_count" in row.keys() else 0 or 0) + 1
                locked_until = None
                if failed >= max_failed:
                    locked_until = (datetime.now() + timedelta(minutes=lock_minutes)).strftime("%Y-%m-%dT%H:%M:%S")
                conn.execute("UPDATE users SET failed_login_count=?, locked_until=? WHERE username=?", (failed, locked_until, username))
            conn.execute("INSERT INTO login_attempts (id, ts, username, success, ip, message) VALUES (?, ?, ?, 0, ?, ?)",
                         (str(uuid.uuid4()), now_ts(), username, ip, "bad credentials"))
            conn.commit()
            add_notification("warning", "محاولة دخول فاشلة", f"username={username[:40]}")
            return JSONResponse(status_code=401, content={"ok": False, "error": "بيانات الدخول غير صحيحة"})
        token = secrets.token_urlsafe(32)
        base_hours = int(cfg.get("security", {}).get("session_hours", 12) or 12)
        hours = max(base_hours, 24 * 30) if bool(req.remember) else base_hours
        expires = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")
        conn.execute("INSERT INTO sessions (token, username, created_at, expires_at, last_seen) VALUES (?, ?, ?, ?, ?)",
                     (token, row["username"], now_ts(), expires, now_ts()))
        conn.execute("UPDATE users SET failed_login_count=0, locked_until=NULL, last_login=? WHERE username=?", (now_ts(), row["username"]))
        conn.execute("INSERT INTO login_attempts (id, ts, username, success, ip, message) VALUES (?, ?, ?, 1, ?, ?)",
                     (str(uuid.uuid4()), now_ts(), username, ip, "ok"))
        conn.commit()
    resp = JSONResponse(content={"ok": True, "must_change_password": bool(row["force_password_change"] if "force_password_change" in row.keys() else 0)})
    resp.set_cookie(SESSION_COOKIE_NAME, token, httponly=True, samesite="lax", max_age=hours*3600, path="/")
    for legacy_name in LEGACY_SESSION_COOKIE_NAMES:
        if legacy_name != SESSION_COOKIE_NAME:
            resp.delete_cookie(legacy_name, path="/")
    add_notification("info", "تسجيل دخول", f"دخل المستخدم {row['username']}")
    return resp

@app.post("/api/logout")
def api_logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME) or request.cookies.get("mawareth_session")
    if token:
        with DB_LOCK, db() as conn:
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            conn.commit()
    resp = JSONResponse(content={"ok": True})
    resp.delete_cookie(SESSION_COOKIE_NAME)
    resp.delete_cookie("mawareth_session")
    return resp


@app.get("/api/me")
def api_me(request: Request):
    user = getattr(request.state, "user", None) or _get_session_user_from_token(request.cookies.get(SESSION_COOKIE_NAME))
    return {"ok": True, "user": user, "permissions": user.get("permissions", []) if user else []}


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"ok": True, "project": CONFIG.get("project_name"), "version": "dashboard_v22_ops_hardening"}


@app.get("/api/security/status")
def api_security_status(request: Request):
    user = getattr(request.state, "user", None)
    return {
        "ok": True,
        "auth_enforced": _auth_is_enabled(),
        "session_cookie": SESSION_COOKIE_NAME,
        "user": user,
        "public_exceptions": ["/login", "/api/login", "/health", "/webhook/wapilot", "/static/*", "/assets/*"],
    }


@app.get("/api/ngrok/detect")
def api_ngrok_detect():
    candidate = _candidate_ngrok_path()
    running_url = ""
    try:
        r = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=2)
        if r.ok:
            for t in r.json().get("tunnels", []):
                if str(t.get("proto")) == "https":
                    running_url = t.get("public_url", "")
                    break
    except Exception:
        pass
    return {"ok": True, "ngrok_command": candidate or "", "running_public_url": running_url}


@app.post("/api/ask")
def api_ask(req: AskReq):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is empty")
    return ask_runtime(req.question, channel=req.channel, user_id=req.user_id)


@app.get("/api/config")
def api_config(mask: bool = True):
    cfg = load_config()
    if mask:
        cfg = json.loads(json.dumps(cfg, ensure_ascii=False))
        cfg["telegram"]["bot_token_masked"] = mask_secret(cfg["telegram"].get("bot_token"))
        cfg["telegram"]["bot_token"] = ""
        cfg["wapilot"]["api_token_masked"] = mask_secret(cfg["wapilot"].get("api_token"))
        cfg["wapilot"]["api_token"] = ""
        cfg.setdefault("sqlserver", {})["password_masked"] = mask_secret(cfg.get("sqlserver", {}).get("password"))
        cfg["sqlserver"]["password"] = ""
    return cfg


@app.get("/api/registry/status")
def api_registry_status():
    return registry_status(mask=True)


@app.post("/api/registry/clear")
def api_registry_clear():
    ok = delete_registry_config()
    log_service("dashboard", "registry_clear", "ok" if ok else "error", "registry config cleared" if ok else "failed to clear registry")
    return {"ok": ok}


@app.post("/api/config")
async def api_save_config(request: Request):
    global CONFIG, WHATSAPP_STATUS
    body = await request.json()
    if not isinstance(body, dict):
        body = {}

    # Critical v29 rule:
    # A blank field or masked token shown in the UI means KEEP EXISTING, not overwrite.
    # This fixes the bug where saving WaPilot settings could break Telegram, and vice versa.
    _drop_blank_or_masked_secret(body, "telegram", "bot_token")
    _drop_blank_or_masked_secret(body, "wapilot", "api_token")
    _drop_blank_or_masked_secret(body, "sqlserver", "password")

    before = load_config()
    before_tg_token_set = bool(before.get("telegram", {}).get("bot_token"))
    before_wa_token_set = bool(before.get("wapilot", {}).get("api_token"))
    before_tg_enabled = bool(before.get("telegram", {}).get("enabled", False))
    before_wa_enabled = bool(before.get("wapilot", {}).get("enabled", False))

    cfg = shallow_merge(before, body)

    # Final defensive preservation in case another frontend sends an empty/masked secret.
    if not cfg.get("telegram", {}).get("bot_token") or is_masked_secret_value(cfg.get("telegram", {}).get("bot_token")):
        cfg.setdefault("telegram", {})["bot_token"] = before.get("telegram", {}).get("bot_token", "")
    if not cfg.get("wapilot", {}).get("api_token") or is_masked_secret_value(cfg.get("wapilot", {}).get("api_token")):
        cfg.setdefault("wapilot", {})["api_token"] = before.get("wapilot", {}).get("api_token", "")

    save_config(cfg)
    CONFIG = load_config()
    # Keep running services in sync with freshly saved registry-backed settings.
    WHATSAPP_STATUS["enabled"] = bool(CONFIG.get("wapilot", {}).get("enabled", False))
    if before_tg_enabled and CONFIG.get("telegram", {}).get("bot_token") and not TELEGRAM.running:
        try:
            TELEGRAM.start()
        except Exception:
            pass
    try:
        if CONFIG.get("sqlserver", {}).get("enabled") and CONFIG.get("sqlserver", {}).get("sync_enabled", True):
            SQLSYNC_WORKER.start()
        else:
            SQLSYNC_WORKER.stop()
    except Exception:
        pass

    log_service("dashboard", "config_save", "ok", "config updated with secret-preserve guard")
    log_event("info", "dashboard", "settings_secret_guard",
              "settings saved without overwriting blank/masked Telegram/WaPilot secrets",
              {
                  "telegram_token_before": before_tg_token_set,
                  "telegram_token_after": bool(CONFIG.get("telegram", {}).get("bot_token")),
                  "wapilot_token_before": before_wa_token_set,
                  "wapilot_token_after": bool(CONFIG.get("wapilot", {}).get("api_token")),
                  "telegram_enabled_before": before_tg_enabled,
                  "telegram_enabled_after": bool(CONFIG.get("telegram", {}).get("enabled", False)),
                  "wapilot_enabled_before": before_wa_enabled,
                  "wapilot_enabled_after": bool(CONFIG.get("wapilot", {}).get("enabled", False)),
              })
    return {
        "ok": True,
        "telegram_token_set": bool(CONFIG.get("telegram", {}).get("bot_token")),
        "wapilot_token_set": bool(CONFIG.get("wapilot", {}).get("api_token")),
        "telegram_enabled": bool(CONFIG.get("telegram", {}).get("enabled", False)),
        "wapilot_enabled": bool(CONFIG.get("wapilot", {}).get("enabled", False)),
    }




@app.post("/api/config/reload-runtime")
def api_config_reload_runtime():
    cfg = refresh_runtime_config()
    return {
        "ok": True,
        "telegram_token_set": bool(cfg.get("telegram", {}).get("bot_token")),
        "telegram_enabled": bool(cfg.get("telegram", {}).get("enabled", False)),
        "wapilot_token_set": bool(cfg.get("wapilot", {}).get("api_token")),
        "wapilot_enabled": bool(cfg.get("wapilot", {}).get("enabled", False)),
        "wapilot_public_webhook_url": cfg.get("wapilot", {}).get("public_webhook_url", ""),
    }

@app.get("/api/services/status")
def services_status():
    cfg = refresh_runtime_config()
    sql_status = {}
    try:
        sql_status = sqlserver_sync.get_status(DB_PATH, cfg)
        sql_status["worker_last_result"] = getattr(SQLSYNC_WORKER, "last_result", {})
    except Exception as e:
        sql_status = {"ok": False, "enabled": bool(cfg.get("sqlserver", {}).get("enabled")), "message": str(e)[:500]}
    return {
        "project": {"running": True, "message": "Dashboard/API running"},
        "telegram": {"running": TELEGRAM.running, "last_error": TELEGRAM.last_error, "token_set": bool(load_config()["telegram"].get("bot_token")), "bot_username": TELEGRAM.bot_username},
        "whatsapp": {"running": WHATSAPP_STATUS["enabled"], "last_error": WHATSAPP_STATUS["last_error"], "sent": WHATSAPP_STATUS["sent"], "received": WHATSAPP_STATUS["received"], "token_set": bool(load_config()["wapilot"].get("api_token"))},
        "sqlserver": sql_status,
    }


@app.get("/api/telegram/check")
def api_telegram_check():
    cfg = load_config()
    token = clean_telegram_token(cfg.get("telegram", {}).get("bot_token", ""))
    ok, msg, diag = TELEGRAM.validate_token(token)
    level = "info" if ok else "error"
    log_event(level, "telegram", "token_check", msg, raw=diag)
    return {"ok": ok, "message": msg, "diagnostics": diag}


@app.post("/api/services/{service}/{action}")
def service_action(service: str, action: str):
    global WHATSAPP_STATUS, CONFIG
    refresh_runtime_config()
    service = service.lower()
    action = action.lower()
    if service == "all":
        if action == "start":
            tok, tmsg = TELEGRAM.start()
            CONFIG["wapilot"]["enabled"] = True
            CONFIG["telegram"]["enabled"] = bool(tok)
            save_config(CONFIG)
            WHATSAPP_STATUS["enabled"] = True
            log_service("all", "start", "ok", "all start requested")
            return {"ok": True, "telegram": tmsg, "whatsapp": "enabled"}
        if action == "stop":
            TELEGRAM.stop()
            CONFIG["wapilot"]["enabled"] = False
            CONFIG["telegram"]["enabled"] = False
            save_config(CONFIG)
            WHATSAPP_STATUS["enabled"] = False
            log_service("all", "stop", "ok", "all stop requested")
            return {"ok": True}
    if service == "telegram":
        if action == "start":
            ok, msg = TELEGRAM.start()
            CONFIG["telegram"]["enabled"] = ok
            save_config(CONFIG)
            return {"ok": ok, "message": msg}
        if action == "stop":
            ok, msg = TELEGRAM.stop()
            CONFIG["telegram"]["enabled"] = False
            save_config(CONFIG)
            return {"ok": ok, "message": msg}
    if service == "whatsapp":
        if action == "start":
            WHATSAPP_STATUS["enabled"] = True
            CONFIG["wapilot"]["enabled"] = True
            save_config(CONFIG)
            log_service("whatsapp", "start", "ok", "webhook enabled")
            return {"ok": True, "message": "WhatsApp webhook enabled"}
        if action == "stop":
            WHATSAPP_STATUS["enabled"] = False
            CONFIG["wapilot"]["enabled"] = False
            save_config(CONFIG)
            log_service("whatsapp", "stop", "ok", "webhook disabled")
            return {"ok": True, "message": "WhatsApp webhook disabled"}
    raise HTTPException(status_code=400, detail="unknown service/action")


@app.get("/api/notifications")
def api_notifications(limit: int = 30):
    limit = min(max(limit, 1), 100)
    with DB_LOCK, db() as conn:
        unread = conn.execute("SELECT COUNT(*) c FROM notifications WHERE seen=0").fetchone()["c"]
        rows = [dict(r) for r in conn.execute("SELECT id, ts, level, title, message, seen FROM notifications ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()]
    return {"ok": True, "unread": unread, "rows": rows}


@app.post("/api/notifications/read")
def api_notifications_read():
    with DB_LOCK, db() as conn:
        conn.execute("UPDATE notifications SET seen=1 WHERE seen=0")
        conn.commit()
    return {"ok": True}


@app.get("/api/users")
def api_users():
    with DB_LOCK, db() as conn:
        rows = [dict(r) for r in conn.execute("SELECT username, display_name, role, permissions, active, created_at, updated_at FROM users ORDER BY username").fetchall()]
    for r in rows:
        r["permissions"] = _parse_permissions(r.get("permissions"))
        r["active"] = bool(r.get("active"))
    return {"ok": True, "roles": ROLE_PERMISSIONS, "permissions": ALL_PERMISSIONS, "rows": rows}


@app.post("/api/users")
async def api_users_save(request: Request):
    body = await request.json()
    username = str(body.get("username", "")).strip()
    if not re.match(r"^[A-Za-z0-9_.-]{3,40}$", username):
        raise HTTPException(status_code=400, detail="اسم المستخدم يجب أن يكون 3-40 حرفًا إنجليزيًا/أرقامًا/._-")
    display_name = str(body.get("display_name") or username).strip()[:80]
    role = str(body.get("role") or "viewer").strip()
    if role not in ROLE_PERMISSIONS:
        role = "viewer"
    perms = _parse_permissions(body.get("permissions") or ROLE_PERMISSIONS.get(role, []))
    active = 1 if body.get("active", True) else 0
    password = str(body.get("password") or "")
    ts = now_ts()
    with DB_LOCK, db() as conn:
        exists = conn.execute("SELECT username FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            if password:
                conn.execute("UPDATE users SET display_name=?, role=?, permissions=?, active=?, password_hash=?, updated_at=? WHERE username=?",
                             (display_name, role, _permissions_string(perms), active, _hash_password(password), ts, username))
            else:
                conn.execute("UPDATE users SET display_name=?, role=?, permissions=?, active=?, updated_at=? WHERE username=?",
                             (display_name, role, _permissions_string(perms), active, ts, username))
        else:
            if not password:
                raise HTTPException(status_code=400, detail="كلمة المرور مطلوبة للمستخدم الجديد")
            conn.execute("INSERT INTO users (username, display_name, password_hash, role, permissions, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (username, display_name, _hash_password(password), role, _permissions_string(perms), active, ts, ts))
        conn.commit()
    log_service("dashboard", "users_save", "ok", f"user={username}")
    return {"ok": True}


@app.post("/api/users/{username}/delete")
def api_users_delete(username: str):
    if username == "admin":
        raise HTTPException(status_code=400, detail="لا يمكن حذف admin الأساسي")
    with DB_LOCK, db() as conn:
        conn.execute("DELETE FROM users WHERE username=?", (username,))
        conn.execute("DELETE FROM sessions WHERE username=?", (username,))
        conn.commit()
    log_service("dashboard", "users_delete", "ok", f"user={username}")
    return {"ok": True}


def _logo_candidates_from_config(cfg: dict) -> list[Path]:
    logo = (cfg.get("ui", {}) or {}).get("logo_file") or ""
    candidates: list[Path] = []
    if logo:
        p = Path(str(logo))
        candidates.append(p if p.is_absolute() else DATA_DIR / p)
        candidates.append(PERSIST_ASSETS_DIR / p.name)
    # Fallback to the newest persisted logo if config was reset by a replaced package.
    for ext in ("png", "jpg", "jpeg", "webp", "svg"):
        candidates.append(PERSIST_ASSETS_DIR / f"custom_logo.{ext}")
    return candidates


@app.get("/assets/logo")
def serve_logo():
    cfg = load_config()
    for p in _logo_candidates_from_config(cfg):
        try:
            if p.exists() and p.is_file():
                return FileResponse(p)
        except Exception:
            continue
    # Simple SVG fallback; not raw data in UI code.
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96"><rect rx="22" width="96" height="96" fill="#8bc75a"/><text x="48" y="61" text-anchor="middle" font-size="44" font-family="Arial" fill="#17340b" font-weight="700">م</text></svg>'
    return PlainTextResponse(svg, media_type="image/svg+xml")


@app.post("/api/logo")
async def api_logo_upload(request: Request):
    body = await request.json()
    data_url = str(body.get("data_url") or "")
    if not data_url.startswith("data:image/") or ";base64," not in data_url:
        raise HTTPException(status_code=400, detail="صيغة الصورة غير صحيحة")
    header, b64 = data_url.split(",", 1)
    mime = header.split(";")[0].split(":",1)[1]
    ext = {"image/png":"png", "image/jpeg":"jpg", "image/jpg":"jpg", "image/webp":"webp", "image/svg+xml":"svg"}.get(mime)
    if not ext:
        raise HTTPException(status_code=400, detail="الأنواع المدعومة: png, jpg, webp, svg")
    raw = base64.b64decode(b64)
    if len(raw) > 2_500_000:
        raise HTTPException(status_code=400, detail="الصورة كبيرة جدًا. الحد 2.5MB")
    fn = f"custom_logo.{ext}"
    persistent_path = PERSIST_ASSETS_DIR / fn
    persistent_path.write_bytes(raw)
    # Also keep a project-local copy for manual portability, but AppData/Registry is the source of persistence.
    try:
        (DATA_DIR / fn).write_bytes(raw)
    except Exception:
        pass
    cfg = load_config()
    cfg.setdefault("ui", {})["logo_file"] = str(persistent_path)
    save_config(cfg)
    log_service("dashboard", "logo_upload", "ok", str(persistent_path))
    return {"ok": True, "logo_url": f"/assets/logo?ts={int(time.time())}"}


# Compatibility aliases for older/newer front-end builds.
@app.post("/api/settings")
async def api_save_settings_alias(request: Request):
    return await api_save_config(request)

@app.post("/api/upload-logo")
async def api_logo_upload_alias(request: Request):
    return await api_logo_upload(request)

@app.post("/api/branding/logo")
async def api_branding_logo_upload_alias(request: Request):
    return await api_logo_upload(request)

@app.get("/api/logo")
def api_logo_get_alias():
    # Some browsers/front-end versions may request /api/logo as an image URL.
    return serve_logo()


NGROK_PROCESS: subprocess.Popen | None = None


def _validate_ngrok_candidate(candidate: str) -> str | None:
    """Return a usable ngrok command/path, including Microsoft Store App Execution Alias."""
    if not candidate:
        return None
    candidate = str(candidate).strip().strip('"')
    if not candidate:
        return None
    # Existing exe path.
    try:
        if Path(candidate).exists():
            return candidate
    except Exception:
        pass
    # Command available from PATH/App Execution Alias.
    try:
        r = subprocess.run([candidate, "version"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 or "ngrok" in ((r.stdout or "") + (r.stderr or "")).lower():
            return candidate
    except Exception:
        return None
    return None


def _candidate_ngrok_path() -> str | None:
    cfg_path = str(load_config().get("ngrok", {}).get("path") or "").strip()
    if cfg_path:
        ok = _validate_ngrok_candidate(cfg_path)
        if ok:
            return ok

    # Works for normal exe installs and many Windows Store app aliases.
    found = shutil.which("ngrok") or shutil.which("ngrok.exe")
    if found:
        ok = _validate_ngrok_candidate(found)
        if ok:
            return ok

    # Windows native lookup. Useful when Python's shutil.which misses App Execution Alias.
    for cmd in (["where.exe", "ngrok"], ["where.exe", "ngrok.exe"]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                for line in (r.stdout or "").splitlines():
                    ok = _validate_ngrok_candidate(line)
                    if ok:
                        return ok
        except Exception:
            pass

    # PowerShell lookup. This catches Store/AppExecutionAlias installations more reliably.
    ps = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        "(Get-Command ngrok -ErrorAction SilentlyContinue).Source"
    ]
    try:
        r = subprocess.run(ps, capture_output=True, text=True, timeout=8)
        if r.returncode == 0:
            for line in (r.stdout or "").splitlines():
                ok = _validate_ngrok_candidate(line)
                if ok:
                    return ok
    except Exception:
        pass

    # Common manual installs + WindowsApps alias path.
    localapp = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        r"C:\ngrok\ngrok.exe",
        r"C:\Program Files\ngrok\ngrok.exe",
        r"C:\Program Files (x86)\ngrok\ngrok.exe",
    ]
    if localapp:
        candidates.append(str(Path(localapp) / "Microsoft" / "WindowsApps" / "ngrok.exe"))
    for cand in candidates:
        ok = _validate_ngrok_candidate(cand)
        if ok:
            return ok

    # Final safe fallback: try command name directly. If Windows Store alias exists, this may work.
    return _validate_ngrok_candidate("ngrok")

def _get_ngrok_public_url(port: int | None = None, preferred_domain: str = "", require_domain: bool = False) -> str:
    """Read the running ngrok public HTTPS URL from the local ngrok API.

    v27 rule: when a fixed domain is configured for WaPilot, do not silently accept a
    random ngrok URL. A random URL may open the dashboard but WaPilot will continue
    posting to the old configured webhook and inbound WhatsApp will look dead.
    """
    preferred_domain = (preferred_domain or "").replace("https://", "").replace("http://", "").split("/", 1)[0].strip().lower()
    try:
        r = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=3)
        if not r.ok:
            return ""
        tunnels = r.json().get("tunnels", []) or []
        wanted = str(port) if port else ""
        candidates = []
        for t in tunnels:
            if str(t.get("proto")) != "https":
                continue
            cfg = t.get("config") or {}
            addr = str(cfg.get("addr") or "")
            if wanted and wanted not in addr:
                continue
            url = str(t.get("public_url") or "")
            if not url:
                continue
            candidates.append(url)
        if not candidates:
            for t in tunnels:
                if str(t.get("proto")) == "https":
                    url = str(t.get("public_url") or "")
                    if url:
                        candidates.append(url)
        if preferred_domain:
            for url in candidates:
                if preferred_domain in url.lower():
                    return url
            if require_domain:
                return ""
        return candidates[0] if candidates else ""
    except Exception:
        return ""
    return ""


def _sync_public_url(public_url: str, update_wapilot: bool = True) -> None:
    """Persist ngrok public URL and, only when safe, derived WaPilot webhook URL."""
    global CONFIG
    if not public_url:
        return
    cfg = load_config()
    cfg.setdefault("ngrok", {})["public_url"] = public_url
    if update_wapilot:
        cfg.setdefault("wapilot", {})["public_webhook_url"] = public_url.rstrip("/") + cfg.get("wapilot", {}).get("webhook_path", "/webhook/wapilot")
    CONFIG = cfg
    save_config(cfg)


def _extract_ngrok_domain(cfg: dict) -> str:
    """Resolve preferred static ngrok domain from config or current public webhook URL."""
    domain = str(cfg.get("ngrok", {}).get("domain") or "").strip()
    if domain:
        return domain.replace("https://", "").replace("http://", "").split("/", 1)[0]
    wh = str(cfg.get("wapilot", {}).get("public_webhook_url") or "").strip()
    m = re.search(r"https?://([^/]+\.ngrok[^/]+)", wh)
    if m:
        return m.group(1)
    return ""


def _spawn_ngrok(exe: str, args: list[str], label: str) -> tuple[Optional[subprocess.Popen], str]:
    """Start ngrok and write stdout/stderr to logs, then return process and log path."""
    log_path = LOG_DIR / f"ngrok_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{label}.log"
    fh = open(log_path, "ab", buffering=0)
    try:
        p = subprocess.Popen([exe] + args, stdout=fh, stderr=fh, cwd=str(HERE))
        return p, str(log_path)
    except Exception:
        fh.close()
        raise


def start_ngrok_if_configured() -> tuple[bool, str]:
    """Start ngrok automatically and sync the public webhook URL safely.

    v27 WhatsApp recovery rule:
    - If a fixed ngrok domain is configured, use it strictly by default.
    - Do not replace WAPILOT_PUBLIC_WEBHOOK_URL with a random ngrok URL unless
      ngrok.allow_random_fallback=true. Replacing it silently breaks WaPilot inbound
      because WaPilot keeps posting to the webhook saved in its own dashboard.
    """
    global NGROK_PROCESS, CONFIG
    cfg = load_config()
    if not cfg.get("autostart", {}).get("ngrok", True):
        return False, "ngrok autostart disabled"
    port = int(cfg.get("dashboard_port") or cfg.get("ngrok", {}).get("port") or 8088)
    domain = _extract_ngrok_domain(cfg)
    strict_domain = bool(cfg.get("ngrok", {}).get("strict_domain", True))
    allow_random_fallback = bool(cfg.get("ngrok", {}).get("allow_random_fallback", False))

    # Reuse existing tunnel only if it matches the fixed domain when strict mode is on.
    running_url = _get_ngrok_public_url(port, preferred_domain=domain, require_domain=bool(domain and strict_domain))
    if running_url:
        _sync_public_url(running_url, update_wapilot=True)
        log_event("info", "ngrok", "ngrok_started", f"existing tunnel: {running_url}", {"strict_domain": strict_domain, "domain": domain})
        return True, running_url

    # Detect a wrong/random tunnel that points to this port. Log it, but do not sync WaPilot to it.
    wrong_url = _get_ngrok_public_url(port, preferred_domain="", require_domain=False)
    if domain and strict_domain and wrong_url and domain not in wrong_url.lower():
        log_event("warning", "ngrok", "ngrok_wrong_tunnel_domain",
                  f"ngrok يعمل على رابط مختلف عن رابط WaPilot الثابت: {wrong_url}. لن أغيّر Webhook WaPilot تلقائيًا.",
                  {"wanted_domain": domain, "running_url": wrong_url})

    if NGROK_PROCESS and NGROK_PROCESS.poll() is None:
        # Process exists but URL not ready yet; wait briefly.
        for _ in range(12):
            time.sleep(0.5)
            running_url = _get_ngrok_public_url(port, preferred_domain=domain, require_domain=bool(domain and strict_domain))
            if running_url:
                _sync_public_url(running_url, update_wapilot=True)
                return True, running_url
        return True, "ngrok process running, public URL not ready"

    exe = _candidate_ngrok_path()
    if not exe:
        msg = "ngrok غير موجود. ضع ngrok.exe في C:\\ngrok أو أضفه إلى PATH أو اكتب مساره في الإعدادات."
        log_event("warning", "ngrok", "ngrok_failed", msg)
        return False, msg

    upstream = f"http://127.0.0.1:{port}"
    attempts: list[tuple[str, list[str]]] = []
    if domain:
        # ngrok v3 generally supports --domain for reserved/static domains; some setups use --url.
        attempts.append(("static_domain", ["http", f"--domain={domain}", upstream]))
        attempts.append(("static_url", ["http", f"--url={domain}", upstream]))
    if (not domain) or allow_random_fallback:
        attempts.append(("random", ["http", upstream]))

    errors = []
    for label, args in attempts:
        try:
            NGROK_PROCESS, log_path = _spawn_ngrok(exe, args, label)
            for _ in range(18):
                time.sleep(0.5)
                public_url = _get_ngrok_public_url(port, preferred_domain=domain, require_domain=bool(domain and strict_domain and label != "random"))
                if public_url:
                    if domain and strict_domain and domain not in public_url.lower():
                        # Safety: never sync WaPilot to a random URL in strict domain mode.
                        _sync_public_url(public_url, update_wapilot=False)
                        log_event("warning", "ngrok", "ngrok_random_not_synced_to_wapilot",
                                  f"ngrok أعطى رابطًا عشوائيًا: {public_url}. لم أغيّر Webhook WaPilot لأن strict_domain مفعل.",
                                  {"public_url": public_url, "wanted_domain": domain, "args": args, "log": log_path})
                        return False, public_url
                    _sync_public_url(public_url, update_wapilot=True)
                    log_event("info", "ngrok", "ngrok_started", public_url, {"args": args, "log": log_path})
                    return True, public_url
                if NGROK_PROCESS.poll() is not None:
                    break
            if NGROK_PROCESS and NGROK_PROCESS.poll() is None:
                try:
                    NGROK_PROCESS.terminate()
                except Exception:
                    pass
            errors.append({"label": label, "args": args, "log": log_path, "returncode": NGROK_PROCESS.poll() if NGROK_PROCESS else None})
        except Exception as e:
            errors.append({"label": label, "args": args, "error": f"{type(e).__name__}: {e}"})

    msg = "تعذر تشغيل ngrok على الدومين/البورت المطلوب. راجع صفحة الأحداث أو سجلات ngrok داخل logs."
    log_event("warning", "ngrok", "ngrok_failed", msg, {"attempts": errors, "wanted_domain": domain, "allow_random_fallback": allow_random_fallback})
    return False, msg


def _is_admin_windows() -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def ensure_dashboard_firewall_rule() -> tuple[bool, str]:
    """Open inbound Windows Firewall port for LAN/mobile access when possible.
    ngrok itself does not need this, but LAN phone access does.
    """
    if os.name != "nt":
        return False, "not windows"
    cfg = load_config()
    if not cfg.get("firewall", {}).get("auto_open_port", True):
        return False, "firewall auto open disabled"
    port = int(cfg.get("dashboard_port") or 8088)
    rule = str(cfg.get("firewall", {}).get("rule_name") or f"Mawareth AI Dashboard {port}")
    try:
        show = subprocess.run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule}"], capture_output=True, text=True, timeout=8)
        if show.returncode == 0 and "No rules match" not in (show.stdout + show.stderr):
            return True, "rule already exists"
        if not _is_admin_windows():
            msg = "لم يتم فتح Firewall تلقائيًا لأن التشغيل ليس كمسؤول. ngrok لا يحتاج Firewall، لكن فتح الداشبورد من نفس Wi‑Fi قد يحتاج ذلك."
            log_event("warning", "dashboard", "firewall_skipped", msg, {"port": port, "rule": rule})
            return False, msg
        add = subprocess.run([
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={rule}", "dir=in", "action=allow", "protocol=TCP", f"localport={port}"
        ], capture_output=True, text=True, timeout=10)
        if add.returncode == 0:
            msg = f"تم فتح بورت {port} في Windows Firewall."
            log_event("info", "dashboard", "firewall_opened", msg, {"port": port, "rule": rule})
            return True, msg
        msg = (add.stdout or add.stderr or "netsh failed").strip()
        log_event("warning", "dashboard", "firewall_failed", msg, {"port": port, "rule": rule})
        return False, msg
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        log_event("warning", "dashboard", "firewall_failed", msg, {"port": port, "rule": rule})
        return False, msg


@app.on_event("startup")
def startup_autostart():
    global CONFIG, WHATSAPP_STATUS
    cfg = load_config()
    CONFIG = cfg
    if cfg.get("autostart", {}).get("enabled", True):
        if cfg.get("autostart", {}).get("whatsapp", True):
            cfg.setdefault("wapilot", {})["enabled"] = True
            WHATSAPP_STATUS["enabled"] = True
        if cfg.get("autostart", {}).get("telegram", True):
            if cfg.get("telegram", {}).get("bot_token"):
                ok, _msg = TELEGRAM.start()
                cfg.setdefault("telegram", {})["enabled"] = bool(ok)
            else:
                cfg.setdefault("telegram", {})["enabled"] = False
        save_config(cfg)
        ensure_dashboard_firewall_rule()
        start_ngrok_if_configured()
        try:
            if cfg.get("sqlserver", {}).get("enabled") and cfg.get("sqlserver", {}).get("sync_enabled", True):
                SQLSYNC_WORKER.start()
                log_event("info", "sqlserver", "sync_worker_started", "تم تشغيل مزامنة SQL Server بالخلفية")
        except Exception as e:
            log_event("warning", "sqlserver", "sync_worker_start_failed", str(e))
        log_event("info", "dashboard", "autostart_done", "تم تشغيل الخدمات حسب إعدادات التشغيل التلقائي")


@app.get("/api/stats")
def api_stats(days: int = 7):
    since = (datetime.now() - timedelta(days=max(days - 1, 0))).strftime("%Y-%m-%d")
    with DB_LOCK, db() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM conversations").fetchone()["c"]
        today = conn.execute("SELECT COUNT(*) c FROM conversations WHERE date=?", (today_str(),)).fetchone()["c"]
        by_channel = {r["channel"]: r["c"] for r in conn.execute("SELECT channel, COUNT(*) c FROM conversations GROUP BY channel")}
        by_type = {r["answer_type"]: r["c"] for r in conn.execute("SELECT answer_type, COUNT(*) c FROM conversations GROUP BY answer_type")}
        avg = conn.execute("SELECT AVG(elapsed_ms) a FROM conversations").fetchone()["a"] or 0
        rows = conn.execute("SELECT date, COUNT(*) c FROM conversations WHERE date>=? GROUP BY date ORDER BY date", (since,)).fetchall()
        series_map = {r["date"]: r["c"] for r in rows}
    labels = []
    values = []
    for i in range(days):
        d = (datetime.now() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        labels.append(d)
        values.append(series_map.get(d, 0))
    return {
        "total": total,
        "today": today,
        "telegram": by_channel.get("telegram", 0),
        "whatsapp": by_channel.get("whatsapp", 0),
        "dashboard": by_channel.get("dashboard", 0),
        "api": by_channel.get("api", 0),
        "calculation": by_type.get("calculation", 0),
        "fiqh": by_type.get("fiqh_or_general", 0),
        "clarification": by_type.get("clarification_or_safe_stop", 0),
        "avg_ms": round(avg, 1),
        "series": {"labels": labels, "values": values},
    }


@app.get("/api/logs")
def api_logs(limit: int = 100, channel: str | None = None, date: str | None = None):
    limit = min(max(limit, 1), 1000)
    sql = "SELECT * FROM conversations WHERE 1=1"
    params = []
    if channel:
        sql += " AND channel=?"
        params.append(channel)
    if date:
        sql += " AND date=?"
        params.append(date)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    with DB_LOCK, db() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    return {"rows": rows}


@app.get("/api/export/logs.csv")
def export_logs_csv():
    import csv
    export_path = LOG_DIR / f"conversation_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with DB_LOCK, db() as conn, export_path.open("w", encoding="utf-8-sig", newline="") as f:
        rows = conn.execute("SELECT ts, channel, user_id, user_name, question, answer, answer_type, dialect, elapsed_ms, status FROM conversations ORDER BY ts DESC").fetchall()
        w = csv.writer(f)
        w.writerow(["ts", "channel", "user_id", "user_name", "question", "answer", "answer_type", "dialect", "elapsed_ms", "status"])
        for r in rows:
            w.writerow([r[x] for x in r.keys()])
    return FileResponse(export_path, filename=export_path.name, media_type="text/csv")


@app.post("/api/wapilot/test-send")
async def wapilot_test_send(request: Request):
    body = await request.json()
    to = str(body.get("to") or "").strip()
    message = str(body.get("message") or "اختبار من مفتي المواريث الذكي").strip()
    if not to:
        raise HTTPException(status_code=400, detail="to is required")
    ok, msg = wapilot_send(to, message)
    return {"ok": ok, "response": msg}




def _stable_json_for_hash(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        return str(obj)


def _webhook_fingerprint(payload: Any, sender: str | None, text: str | None) -> str:
    """Create an idempotency key for WaPilot webhook retries.

    Prefer provider ids if present; otherwise hash the full payload. This prevents duplicate replies
    when the webhook provider retries the same event.
    """
    ids = []
    def walk(x: Any):
        if isinstance(x, dict):
            for k, v in x.items():
                lk = str(k).lower()
                if lk in {"id", "messageid", "message_id", "wamid", "update_id", "event_id", "key", "msgid"} and isinstance(v, (str, int)):
                    ids.append(f"{lk}:{v}")
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)
    walk(payload)
    seed = "|".join(sorted(ids[:10])) if ids else _stable_json_for_hash(payload)
    seed = f"wapilot|{sender or ''}|{text or ''}|{seed}"
    return hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()


def _mark_webhook_event_once(fingerprint: str, sender: str | None, text: str | None) -> bool:
    """Return True if first time, False if duplicate."""
    try:
        with DB_LOCK, db() as conn:
            conn.execute("INSERT INTO webhook_events (fingerprint, ts, channel, sender, text) VALUES (?, ?, ?, ?, ?)",
                         (fingerprint, now_ts(), "wapilot", sender, text))
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False



def save_last_wapilot_payload(payload: Any) -> None:
    """Persist the last webhook payload for debugging without changing inheritance logic."""
    try:
        (LOG_DIR / "wapilot_last_payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


@app.get("/api/wapilot/diagnostics")
def wapilot_diagnostics():
    """Operational diagnostics: tells whether the dashboard is ready to receive WAPilot webhooks."""
    cfg = refresh_runtime_config()
    wcfg = cfg.get("wapilot", {})
    expected_local = f"http://127.0.0.1:{cfg.get('dashboard_port', 8088)}{wcfg.get('webhook_path', '/webhook/wapilot')}"
    return {
        "ok": True,
        "enabled": bool(WHATSAPP_STATUS.get("enabled")),
        "expected_local_webhook": expected_local,
        "configured_public_webhook_url": wcfg.get("public_webhook_url"),
        "configured_webhook_path": wcfg.get("webhook_path"),
        "instance_id": wcfg.get("instance_id"),
        "api_url_template": wcfg.get("api_url_template"),
        "token_set": bool(wcfg.get("api_token")),
        "last_webhook_at": WHATSAPP_STATUS.get("last_webhook_at"),
        "last_webhook_sender": WHATSAPP_STATUS.get("last_webhook_sender"),
        "last_webhook_text": WHATSAPP_STATUS.get("last_webhook_text"),
        "last_send_response": WHATSAPP_STATUS.get("last_send_response"),
        "last_error": WHATSAPP_STATUS.get("last_error"),
        "received_count": WHATSAPP_STATUS.get("received"),
        "sent_count": WHATSAPP_STATUS.get("sent"),
        "debug_last_payload_file": str(LOG_DIR / "wapilot_last_payload.json"),
        "debug_send_attempts_file": str(LOG_DIR / "wapilot_send_attempts.jsonl"),
        "send_payload_style": wcfg.get("send_payload_style", "auto"),
        "notes": [
            "افتح configured_public_webhook_url في المتصفح. يجب أن يرجع JSON فيه ok=true.",
            "لازم ngrok يكون شغال على نفس بورت الداشبورد: ngrok http 8088.",
            "لازم تضع نفس configured_public_webhook_url داخل إعدادات Webhook في WAPilot للـ instance الصحيح.",
            "لازم WhatsApp service enabled من الداشبورد كي يرد النظام على الرسائل؛ أما التشخيص فيسجل الوصول حتى لو كان متوقفًا.",
        ],
    }


@app.get("/api/wapilot/recovery-check")
def wapilot_recovery_check():
    refresh_runtime_config()
    """End-to-end readiness report for WhatsApp/WaPilot after package replacement.
    It does not send a real WhatsApp message; it checks config, ngrok, local/public webhook reachability,
    and tells exactly why inbound/outbound is likely failing.
    """
    cfg = load_config()
    wcfg = cfg.get("wapilot", {})
    ncfg = cfg.get("ngrok", {})
    port = int(cfg.get("dashboard_port") or 8088)
    path = str(wcfg.get("webhook_path") or "/webhook/wapilot")
    configured_public = str(wcfg.get("public_webhook_url") or "")
    domain = _extract_ngrok_domain(cfg)
    current_ngrok = _get_ngrok_public_url(port, preferred_domain=domain, require_domain=False)
    expected_static = f"https://{domain}{path}" if domain else ""
    checks = []
    actions = []

    def add_check(name, ok, message, details=None):
        checks.append({"name": name, "ok": bool(ok), "message": message, "details": details or {}})
        return ok

    add_check("whatsapp_enabled", WHATSAPP_STATUS.get("enabled"), "WhatsApp/WaPilot service enabled" if WHATSAPP_STATUS.get("enabled") else "WhatsApp/WaPilot service is disabled")
    if not WHATSAPP_STATUS.get("enabled"):
        actions.append("فعّل WhatsApp من صفحة التشغيل أو تأكد أن autostart.whatsapp=true.")
    add_check("token_set", bool(wcfg.get("api_token")), "WaPilot token exists" if wcfg.get("api_token") else "WaPilot token is missing")
    if not wcfg.get("api_token"):
        actions.append("ضع WAPILOT_API_TOKEN من Settings؛ سيتم حفظه في Registry.")
    add_check("instance_id_set", bool(wcfg.get("instance_id")), "Instance ID exists" if wcfg.get("instance_id") else "Instance ID missing")

    if domain:
        ok_domain = bool(configured_public.lower().startswith(f"https://{domain}"))
        add_check("configured_webhook_uses_static_domain", ok_domain, "Configured webhook matches fixed ngrok domain" if ok_domain else "Configured webhook does not match fixed ngrok domain", {"configured_public_webhook_url": configured_public, "expected": expected_static})
        if not ok_domain:
            actions.append(f"اجعل WAPILOT_PUBLIC_WEBHOOK_URL = {expected_static} في Settings وداخل WaPilot نفسه.")
    else:
        add_check("ngrok_domain_configured", False, "No fixed ngrok domain configured", {})
        actions.append("ضع ngrok domain الثابت في Settings لتجنب تغيّر رابط WaPilot كل مرة.")

    if current_ngrok:
        add_check("ngrok_running", True, "ngrok tunnel is running", {"current_ngrok_public_url": current_ngrok})
        if domain and domain not in current_ngrok.lower():
            add_check("ngrok_matches_domain", False, "ngrok is running but not on the configured fixed domain", {"current_ngrok_public_url": current_ngrok, "wanted_domain": domain})
            actions.append("اقفل ngrok الحالي وشغّل run_dashboard_full_auto.bat؛ يجب أن يعمل على الدومين الثابت لا رابط عشوائي.")
        else:
            add_check("ngrok_matches_domain", True, "ngrok matches configured domain" if domain else "ngrok is running")
    else:
        add_check("ngrok_running", False, "No ngrok tunnel found on 127.0.0.1:4040", {})
        actions.append("تأكد أن ngrok.exe موجود ثم شغّل run_dashboard_full_auto.bat.")

    # Local health test
    local_url = f"http://127.0.0.1:{port}{path}"
    try:
        r = requests.get(local_url, timeout=4)
        add_check("local_webhook_get", r.status_code == 200, f"local GET {r.status_code}", {"url": local_url, "body": r.text[:500]})
    except Exception as e:
        add_check("local_webhook_get", False, f"local GET failed: {type(e).__name__}: {e}", {"url": local_url})
        actions.append("لو local webhook فشل، السيرفر نفسه غير سليم أو المسار غير صحيح.")

    # Public health test. Use ngrok header to skip browser warning.
    if configured_public:
        try:
            r = requests.get(configured_public, headers={"ngrok-skip-browser-warning": "true"}, timeout=8)
            add_check("public_webhook_get", r.status_code == 200, f"public GET {r.status_code}", {"url": configured_public, "body": r.text[:500]})
        except Exception as e:
            add_check("public_webhook_get", False, f"public GET failed: {type(e).__name__}: {e}", {"url": configured_public})
            actions.append("لو public webhook فشل، WaPilot لن يستطيع إرسال رسائل. راجع ngrok والدومين.")

    ok = all(c["ok"] for c in checks if c["name"] not in {"configured_webhook_uses_static_domain"}) and bool(configured_public)
    return {
        "ok": bool(ok),
        "configured_public_webhook_url": configured_public,
        "expected_static_webhook_url": expected_static,
        "current_ngrok_public_url": current_ngrok,
        "whatsapp_status": WHATSAPP_STATUS,
        "checks": checks,
        "actions": actions,
    }


@app.post("/api/wapilot/simulate-incoming")
async def wapilot_simulate_incoming(request: Request):
    """Local-only simulation of an incoming WhatsApp message without calling WAPilot send API."""
    body = await request.json()
    text = str(body.get("text") or body.get("message") or "").strip()
    sender = str(body.get("sender") or body.get("from") or "dashboard-test").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text/message is required")
    out = ask_runtime(text, channel="whatsapp-sim", user_id=sender, raw={"simulated": True, **body})
    return {"ok": True, "simulated": True, "sender": sender, "answer": out.get("answer"), "request_id": out.get("request_id")}

@app.post("/webhook/wapilot")
async def wapilot_webhook(request: Request):
    global WHATSAPP_STATUS
    refresh_runtime_config()
    try:
        payload = await request.json()
    except Exception:
        raw = await request.body()
        payload = {"raw": raw.decode("utf-8", errors="ignore")}
    WHATSAPP_STATUS["received"] += 1
    WHATSAPP_STATUS["last_webhook_at"] = now_ts()
    save_last_wapilot_payload(payload)
    text, sender, meta = extract_first_text_and_sender(payload)
    WHATSAPP_STATUS["last_webhook_sender"] = sender or ""
    WHATSAPP_STATUS["last_webhook_text"] = (text or "")[:300]
    log_service("whatsapp", "webhook_received", "ok", f"sender={sender or 'unknown'} text_found={bool(text)}")
    log_event("info", "wapilot", "webhook_received", f"sender={sender or 'unknown'} text_found={bool(text)}", payload)
    if sender and "@" in sender:
        log_event("info", "wapilot", "webhook_chat_id_preserved", f"using exact chat_id for reply: {sender}", {"sender": sender})
    if not WHATSAPP_STATUS.get("enabled"):
        log_service("whatsapp", "webhook_ignored", "disabled", "received while disabled")
        log_event("warning", "wapilot", "webhook_ignored_disabled", "received while disabled", payload)
        return {"ok": True, "ignored": "whatsapp disabled", "text_found": bool(text), "sender_found": bool(sender)}
    if not text:
        insert_conversation({
            "id": str(uuid.uuid4()), "ts": now_ts(), "date": today_str(), "channel": "whatsapp",
            "user_id": sender, "user_name": None, "direction": "incoming", "question": None, "answer": None,
            "answer_type": "ignored_non_text", "dialect": None, "elapsed_ms": 0, "status": "ignored", "raw_json": json.dumps(payload, ensure_ascii=False),
        })
        return {"ok": True, "ignored": "no text found", "meta": meta}
    fp = _webhook_fingerprint(payload, sender, text)
    if not _mark_webhook_event_once(fp, sender, text):
        log_service("whatsapp", "webhook_duplicate", "ignored", fp)
        return {"ok": True, "ignored": "duplicate webhook", "fingerprint": fp}
    cfg_now = load_config()
    reply_mode = str(cfg_now.get("operational", {}).get("reply_mode", "active") or "active")
    if sender and reply_mode == "active" and cfg_now.get("operational", {}).get("show_processing_notice", True):
        try:
            _notice = _processing_notice_v35(text, "whatsapp")
            if _notice:
                wapilot_send(sender, _notice)
        except Exception as _e:
            log_event("warning", "wapilot", "processing_notice_failed", str(_e), {"sender": sender})
    out = ask_runtime(text, channel="whatsapp", user_id=sender, raw=payload)
    reply_mode = str(load_config().get("operational", {}).get("reply_mode", "active") or "active")
    if reply_mode == "monitor":
        log_event("info", "wapilot", "monitor_mode_no_send", "تم تسجيل الرسالة دون إرسال رد لأن وضع المراقبة مفعّل", {"sender": sender, "request_id": out.get("request_id")})
        return {"ok": True, "answered": True, "sent": False, "mode": "monitor", "request_id": out["request_id"]}
    send_ok = False
    send_resp = "no sender"
    if sender:
        send_ok, send_resp = wapilot_send(sender, out["answer"])
    WHATSAPP_STATUS["last_send_response"] = str(send_resp)[:800]
    if not send_ok:
        WHATSAPP_STATUS["last_error"] = str(send_resp)[:800]
        log_service("whatsapp", "send_failed", "error", str(send_resp)[:800])
        log_event("error", "wapilot", "send_failed", str(send_resp)[:800], {"sender": sender, "request_id": out.get("request_id")})
    else:
        log_service("whatsapp", "send_ok", "ok", str(send_resp)[:300])
        log_event("info", "wapilot", "send_ok", str(send_resp)[:300], {"sender": sender, "request_id": out.get("request_id")})
    return {"ok": True, "answered": True, "sent": send_ok, "send_response": send_resp, "request_id": out["request_id"]}


@app.get("/api/events")
def api_events(limit: int = 200, level: str | None = None, component: str | None = None, date: str | None = None):
    limit = min(max(limit, 1), 2000)
    sql = "SELECT * FROM technical_events WHERE 1=1"
    params: list[Any] = []
    if level:
        sql += " AND level=?"
        params.append(level)
    if component:
        sql += " AND component=?"
        params.append(component)
    if date:
        sql += " AND date=?"
        params.append(date)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    with DB_LOCK, db() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    return {"rows": rows}


@app.get("/api/errors")
def api_errors(limit: int = 200, date: str | None = None):
    limit = min(max(limit, 1), 2000)
    sql = "SELECT * FROM technical_events WHERE level IN ('error','critical')"
    params: list[Any] = []
    if date:
        sql += " AND date=?"
        params.append(date)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    with DB_LOCK, db() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    return {"rows": rows}


@app.get("/api/export/events.csv")
def export_events_csv():
    import csv
    export_path = LOG_DIR / f"events_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with DB_LOCK, db() as conn, export_path.open("w", encoding="utf-8-sig", newline="") as f:
        rows = conn.execute("SELECT ts, level, component, event, message, raw_json FROM technical_events ORDER BY ts DESC").fetchall()
        w = csv.writer(f)
        w.writerow(["ts", "level", "component", "event", "message", "raw_json"])
        for r in rows:
            w.writerow([r[x] for x in r.keys()])
    return FileResponse(export_path, filename=export_path.name, media_type="text/csv")


@app.get("/api/export/errors.csv")
def export_errors_csv():
    import csv
    export_path = LOG_DIR / f"errors_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with DB_LOCK, db() as conn, export_path.open("w", encoding="utf-8-sig", newline="") as f:
        rows = conn.execute("SELECT ts, level, component, event, message, raw_json FROM technical_events WHERE level IN ('error','critical') ORDER BY ts DESC").fetchall()
        w = csv.writer(f)
        w.writerow(["ts", "level", "component", "event", "message", "raw_json"])
        for r in rows:
            w.writerow([r[x] for x in r.keys()])
    return FileResponse(export_path, filename=export_path.name, media_type="text/csv")


@app.get("/api/remote/access")
def api_remote_access():
    cfg = load_config()
    port = int(cfg.get("dashboard_port", 8088))
    public_url = cfg.get("wapilot", {}).get("public_webhook_url", "")
    return {
        "ok": True,
        "local_dashboard": f"http://127.0.0.1:{port}",
        "local_webhook": f"http://127.0.0.1:{port}/webhook/wapilot",
        "configured_public_webhook_url": public_url,
        "free_options": [
            {"name": "ngrok", "command": f"ngrok http {port}", "notes": "سهل للتجربة. الرابط المجاني قد يتغير عند إعادة التشغيل."},
            {"name": "Cloudflare Quick Tunnel", "command": f"cloudflared tunnel --url http://localhost:{port}", "notes": "مجاني للتجربة بدون شراء استضافة. الرابط قد يتغير مع Quick Tunnel."},
        ],
        "mobile_ui": "مدعوم بتصميم responsive؛ افتح رابط النفق من متصفح الهاتف.",
    }


# Optional: WaPilot/ngrok may call GET/HEAD/OPTIONS for verification/probing. Keep it harmless.
@app.api_route("/webhook/wapilot", methods=["GET", "HEAD", "OPTIONS"])
def wapilot_probe():
    refresh_runtime_config()
    return {
        "ok": True,
        "webhook": "wapilot",
        "enabled": WHATSAPP_STATUS.get("enabled"),
        "received_count": WHATSAPP_STATUS.get("received"),
        "last_webhook_at": WHATSAPP_STATUS.get("last_webhook_at"),
    }


# ---------------- v22 operational hardening endpoints ----------------

def _service_health_summary() -> dict:
    cfg = load_config()
    ngrok_url = ""
    try:
        r = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=2)
        if r.ok:
            for t in r.json().get("tunnels", []):
                if str(t.get("proto")) == "https":
                    ngrok_url = t.get("public_url", "")
                    break
    except Exception:
        pass
    with DB_LOCK, db() as conn:
        last_in = conn.execute("SELECT ts, channel, question FROM conversations ORDER BY ts DESC LIMIT 1").fetchone()
        last_err = conn.execute("SELECT ts, component, event, message FROM technical_events WHERE level IN ('error','critical') ORDER BY ts DESC LIMIT 1").fetchone()
    return {
        "dashboard": {"ok": True, "port": cfg.get("dashboard_port", 8088)},
        "runtime": {"ok": callable(answer)},
        "database": {"ok": DB_PATH.exists(), "path": str(DB_PATH)},
        "telegram": {"running": TELEGRAM.running, "token_set": bool(cfg.get("telegram", {}).get("bot_token")), "last_error": TELEGRAM.last_error},
        "whatsapp": {"enabled": bool(WHATSAPP_STATUS.get("enabled")), "token_set": bool(cfg.get("wapilot", {}).get("api_token")), "received": WHATSAPP_STATUS.get("received"), "sent": WHATSAPP_STATUS.get("sent"), "last_error": WHATSAPP_STATUS.get("last_error")},
        "ngrok": {"running": bool(ngrok_url), "public_url": ngrok_url or cfg.get("ngrok", {}).get("public_url", "")},
        "last_message": dict(last_in) if last_in else None,
        "last_error": dict(last_err) if last_err else None,
        "mode": cfg.get("operational", {}).get("reply_mode", "active"),
    }


@app.get("/api/health/full")
def api_health_full():
    return {"ok": True, "ts": now_ts(), "health": _service_health_summary()}


@app.get("/api/operational/mode")
def api_operational_mode():
    return {"ok": True, "mode": load_config().get("operational", {}).get("reply_mode", "active")}


@app.post("/api/operational/mode")
async def api_operational_mode_set(request: Request):
    global CONFIG
    body = await request.json()
    mode = str(body.get("mode") or "active").strip().lower()
    if mode not in {"active", "monitor"}:
        raise HTTPException(status_code=400, detail="mode must be active or monitor")
    cfg = load_config()
    cfg.setdefault("operational", {})["reply_mode"] = mode
    save_config(cfg)
    CONFIG = cfg
    log_service("dashboard", "mode_change", "ok", f"reply_mode={mode}")
    return {"ok": True, "mode": mode}


@app.post("/api/system-test/run")
def api_system_test_run():
    results = []
    def add(name, ok, message=""):
        results.append({"name": name, "ok": bool(ok), "message": str(message or "")})
    try:
        sample = answer("ما هي الفروض المقدرة في القرآن الكريم؟")
        add("Runtime", bool(sample and "النصف" in sample), "محرك مفتي المواريث يعمل")
    except Exception as e:
        add("Runtime", False, f"{type(e).__name__}: {e}")
    add("Database", DB_PATH.exists(), str(DB_PATH))
    cfg = load_config()
    add("Telegram token", bool(cfg.get("telegram", {}).get("bot_token")), "موجود" if cfg.get("telegram", {}).get("bot_token") else "غير موجود")
    add("WaPilot token", bool(cfg.get("wapilot", {}).get("api_token")), "موجود" if cfg.get("wapilot", {}).get("api_token") else "غير موجود")
    diag = _service_health_summary()
    add("ngrok", bool(diag["ngrok"].get("running")), diag["ngrok"].get("public_url") or "غير شغال")
    ok_all = all(r["ok"] for r in results if r["name"] in {"Runtime", "Database"})
    log_event("info", "dashboard", "system_test", "تم تشغيل اختبار النظام", {"results": results})
    return {"ok": ok_all, "results": results}


@app.get("/api/conversations/threads")
def api_conversation_threads(limit: int = 200, channel: str | None = None, search: str | None = None):
    # Return one row per thread, plus best-effort phone/country-code extraction for WhatsApp.
    sql = """
    SELECT COALESCE(c.user_id,'local') AS thread_id, c.channel, MAX(c.ts) AS last_ts, COUNT(*) AS count,
           (SELECT c2.question FROM conversations c2
            WHERE COALESCE(c2.user_id,'local')=COALESCE(c.user_id,'local') AND c2.channel=c.channel
            ORDER BY c2.ts DESC LIMIT 1) AS last_question,
           (SELECT c3.raw_json FROM conversations c3
            WHERE COALESCE(c3.user_id,'local')=COALESCE(c.user_id,'local') AND c3.channel=c.channel AND COALESCE(c3.raw_json,'')<>''
            ORDER BY c3.ts DESC LIMIT 1) AS raw_json
    FROM conversations c WHERE 1=1
    """
    params=[]
    if channel:
        sql += " AND c.channel=?"; params.append(channel)
    if search:
        sql += " AND (c.question LIKE ? OR c.answer LIKE ? OR c.user_id LIKE ? OR c.raw_json LIKE ?)"; params += [f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"]
    sql += " GROUP BY COALESCE(c.user_id,'local'), c.channel ORDER BY last_ts DESC LIMIT ?"; params.append(min(max(limit,1),1000))
    with DB_LOCK, db() as conn:
        rows=[]
        for r in conn.execute(sql, params).fetchall():
            row=dict(r)
            ident=_thread_identity_from_row(row)
            row.update({
                "phone": ident.get("phone", ""),
                "country_code": ident.get("country_code", ""),
                "display_phone": ident.get("display_phone", "غير متاح"),
                "display_chat_id": ident.get("display_chat_id", row.get("thread_id", "")),
                "phone_source": ident.get("source", ""),
            })
            row.pop("raw_json", None)
            rows.append(row)
    return {"ok": True, "rows": rows}


@app.get("/api/conversations/thread/{thread_id}")
def api_conversation_thread(thread_id: str, channel: str | None = None, limit: int = 200):
    sql="SELECT * FROM conversations WHERE COALESCE(user_id,'local')=?"
    params=[thread_id]
    if channel:
        sql += " AND channel=?"; params.append(channel)
    sql += " ORDER BY ts DESC LIMIT ?"; params.append(min(max(limit,1),1000))
    with DB_LOCK, db() as conn:
        rows=[dict(r) for r in conn.execute(sql, params).fetchall()]
    ident={}
    for row in rows:
        if row.get("raw_json"):
            ident=_thread_identity_from_row({"thread_id": thread_id, "user_id": thread_id, "raw_json": row.get("raw_json")})
            break
    if not ident:
        ident=_thread_identity_from_row({"thread_id": thread_id, "user_id": thread_id, "raw_json": ""})
    return {"ok": True, "identity": ident, "rows": rows}


@app.get("/api/review/items")
def api_review_items(status: str | None = None, limit: int = 200):
    sql="SELECT * FROM review_items WHERE 1=1"; params=[]
    if status:
        sql += " AND status=?"; params.append(status)
    sql += " ORDER BY ts DESC LIMIT ?"; params.append(min(max(limit,1),1000))
    with DB_LOCK, db() as conn:
        rows=[dict(r) for r in conn.execute(sql, params).fetchall()]
    return {"ok": True, "rows": rows}


@app.post("/api/review/{item_id}/mark")
async def api_review_mark(item_id: str, request: Request):
    body=await request.json()
    status=str(body.get("status") or "reviewed").strip()
    if status not in {"pending", "correct", "needs_fix", "wrong", "reviewed"}:
        raise HTTPException(status_code=400, detail="invalid status")
    notes=str(body.get("notes") or "")[:1000]
    user=getattr(request.state, "user", {}) or {}
    with DB_LOCK, db() as conn:
        conn.execute("UPDATE review_items SET status=?, reviewer=?, reviewed_at=?, notes=? WHERE id=?", (status, user.get("username"), now_ts(), notes, item_id))
        conn.commit()
    return {"ok": True}


@app.get("/api/login-attempts")
def api_login_attempts(limit: int = 200):
    with DB_LOCK, db() as conn:
        rows=[dict(r) for r in conn.execute("SELECT * FROM login_attempts ORDER BY ts DESC LIMIT ?", (min(max(limit,1),1000),)).fetchall()]
    return {"ok": True, "rows": rows}


@app.post("/api/users/change-password")
async def api_change_password(request: Request):
    body=await request.json()
    current=str(body.get("current_password") or "")
    newpass=str(body.get("new_password") or "")
    if len(newpass) < 8:
        raise HTTPException(status_code=400, detail="كلمة المرور الجديدة يجب ألا تقل عن 8 أحرف")
    user=getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="login required")
    with DB_LOCK, db() as conn:
        row=conn.execute("SELECT * FROM users WHERE username=?", (user["username"],)).fetchone()
        if not row or not _verify_password(current, row["password_hash"]):
            raise HTTPException(status_code=400, detail="كلمة المرور الحالية غير صحيحة")
        conn.execute("UPDATE users SET password_hash=?, force_password_change=0, updated_at=? WHERE username=?", (_hash_password(newpass), now_ts(), user["username"]))
        conn.commit()
    return {"ok": True}


def _collect_backup(include_secrets: bool=False) -> dict:
    cfg = load_config()
    if not include_secrets:
        cfg = json.loads(json.dumps(cfg, ensure_ascii=False))
        cfg.get("telegram", {})["bot_token"] = ""
        cfg.get("wapilot", {})["api_token"] = ""
    data = {"version": "v22", "created_at": now_ts(), "config": cfg, "users": [], "logo_present": False, "logo_data_url": ""}
    with DB_LOCK, db() as conn:
        rows=conn.execute("SELECT username, display_name, password_hash, role, permissions, active, force_password_change, created_at, updated_at FROM users").fetchall()
        data["users"]=[dict(r) for r in rows]
    # Optional logo export as base64 for portability.
    try:
        for p in _logo_candidates_from_config(load_config()):
            if p.exists() and p.is_file():
                ext=p.suffix.lower().lstrip('.') or 'png'
                mime='image/svg+xml' if ext=='svg' else f'image/{"jpeg" if ext in {"jpg","jpeg"} else ext}'
                data["logo_data_url"] = "data:%s;base64,%s" % (mime, base64.b64encode(p.read_bytes()).decode('ascii'))
                data["logo_present"] = True
                break
    except Exception:
        pass
    return data


@app.get("/api/backup/export")
def api_backup_export(include_secrets: bool = False):
    payload=_collect_backup(include_secrets=include_secrets)
    path=LOG_DIR / f"mawareth_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log_event("info", "dashboard", "backup_export", "تم إنشاء نسخة احتياطية", {"include_secrets": include_secrets})
    return FileResponse(path, filename=path.name, media_type="application/json")


@app.post("/api/backup/import")
async def api_backup_import(request: Request):
    body=await request.json()
    payload=body.get("payload") or body
    if not isinstance(payload, dict) or "config" not in payload:
        raise HTTPException(status_code=400, detail="ملف النسخة الاحتياطية غير صحيح")
    cfg=payload.get("config") or {}
    save_config(shallow_merge(load_config(), cfg))
    # Restore users if present; keep passwords hashed as stored in backup.
    users=payload.get("users") or []
    with DB_LOCK, db() as conn:
        for u in users:
            if not u.get("username") or not u.get("password_hash"):
                continue
            conn.execute("""INSERT OR REPLACE INTO users
                (username, display_name, password_hash, role, permissions, active, created_at, updated_at, force_password_change)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (u.get("username"), u.get("display_name"), u.get("password_hash"), u.get("role","viewer"), u.get("permissions",""), int(u.get("active",1)), u.get("created_at") or now_ts(), now_ts(), int(u.get("force_password_change",0))))
        conn.commit()
    if payload.get("logo_data_url"):
        class _Req:
            async def json(self): return {"data_url": payload.get("logo_data_url")}
        await api_logo_upload(_Req())
    log_event("info", "dashboard", "backup_import", "تم استيراد نسخة احتياطية")
    return {"ok": True}



async def _sql_cfg_from_request(request: Request) -> dict:
    """Use current form SQL settings when posted, without forcing the user to save first."""
    cfg = load_config()
    try:
        body = await request.json()
    except Exception:
        body = {}
    if isinstance(body, dict) and isinstance(body.get("sqlserver"), dict):
        _drop_blank_or_masked_secret(body, "sqlserver", "password")
        cfg = shallow_merge(cfg, {"sqlserver": body.get("sqlserver", {})})
        # If password was blank in the form, keep the saved/registry password.
        if not cfg.get("sqlserver", {}).get("password"):
            saved = load_config()
            cfg.setdefault("sqlserver", {})["password"] = saved.get("sqlserver", {}).get("password", "")
    return cfg


@app.get("/api/sqlserver/status")
def api_sqlserver_status():
    cfg = load_config()
    status = sqlserver_sync.get_status(DB_PATH, cfg)
    status["worker_last_result"] = getattr(SQLSYNC_WORKER, "last_result", {})
    return status


@app.post("/api/sqlserver/test")
async def api_sqlserver_test(request: Request):
    cfg = await _sql_cfg_from_request(request)
    res = sqlserver_sync.test_connection(cfg)
    log_event("info" if res.get("ok") else "error", "sqlserver", "connection_test", "تم فحص الاتصال بـ SQL Server" if res.get("ok") else "فشل الاتصال بـ SQL Server", res)
    return res


@app.post("/api/sqlserver/init")
async def api_sqlserver_init(request: Request):
    cfg = await _sql_cfg_from_request(request)
    res = sqlserver_sync.ensure_schema(cfg)
    log_event("info" if res.get("ok") else "error", "sqlserver", "ensure_schema", "تم إنشاء/تحديث قاعدة SQL Server والجداول" if res.get("ok") else "فشل إنشاء/تحديث SQL Server", res)
    return res


@app.post("/api/sqlserver/sync-now")
async def api_sqlserver_sync_now(request: Request):
    cfg = await _sql_cfg_from_request(request)
    res = sqlserver_sync.sync_bidirectional(DB_PATH, cfg)
    log_event("info" if res.get("ok") else "warning", "sqlserver", "sync_now", "تمت المزامنة بين SQLite و SQL Server" if res.get("ok") else "تعذرت المزامنة؛ المشروع مستمر على SQLite", res)
    return res


@app.post("/api/sqlserver/backup")
async def api_sqlserver_backup(request: Request):
    cfg = await _sql_cfg_from_request(request)
    sqlite_res = sqlserver_sync.sqlite_backup_zip(DB_PATH, CONFIG_PATH, LOG_DIR, LOG_DIR)
    sql_res = sqlserver_sync.sqlserver_backup(cfg) if cfg.get("sqlserver", {}).get("enabled") else {"ok": False, "message": "SQL Server disabled"}
    res = {"ok": bool(sqlite_res.get("ok")), "sqlite_backup": sqlite_res, "sqlserver_backup": sql_res}
    log_event("info" if res.get("ok") else "warning", "sqlserver", "backup", "تم إنشاء نسخة احتياطية" if res.get("ok") else "تعذر إنشاء نسخة احتياطية كاملة", res)
    return res


@app.get("/api/sqlserver/download-sqlite-backup")
def api_sqlserver_download_sqlite_backup():
    res = sqlserver_sync.sqlite_backup_zip(DB_PATH, CONFIG_PATH, LOG_DIR, LOG_DIR)
    if not res.get("ok"):
        raise HTTPException(status_code=500, detail="backup failed")
    return FileResponse(res["path"], filename=Path(res["path"]).name, media_type="application/zip")

if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    host = cfg.get("dashboard_host", "0.0.0.0")
    # In full-auto mode, bind to all interfaces so phone/LAN access works too.
    if str(os.environ.get("MAWARETH_FULL_AUTO", "")).strip() == "1":
        host = "0.0.0.0"
    uvicorn.run("dashboard_server:app", host=host, port=int(cfg.get("dashboard_port", 8088)), reload=False)

# ---------------------------------------------------------------------------
# V42 dashboard bridge — use full intelligence layer for notices and preambles.
# This preserves existing dashboard/services while preventing social chat from
# receiving fatwa preambles or processing notices.
# ---------------------------------------------------------------------------
try:
    import v42_full_intelligence as _v42dash
except Exception:
    _v42dash = None

_DECORATE_ANSWER_BEFORE_V42 = _decorate_answer_v35
_PROCESSING_NOTICE_BEFORE_V42 = _processing_notice_v35

if _v42dash is not None:
    def _processing_notice_v35(question: str, channel: str = "whatsapp") -> str:  # type: ignore[override]
        try:
            if not _v42dash.should_send_processing_notice(question, None):
                return ""
        except Exception:
            return ""
        try:
            dialect = _v42dash.detect_dialect(question, None)
        except Exception:
            dialect = "standard"
        pools = {
            "egyptian": ["⏳ لحظة، براجع المسألة وبحضّر الإجابة...", "⏳ جارٍ فهم المسألة وتجهيز الرد..."],
            "gulf": ["⏳ أبشر، أرتّب المسألة الآن...", "⏳ جارٍ دراسة المسألة وتجهيز الرد..."],
            "shami": ["⏳ لحظة، عم رتّب المسألة وبجهّز الجواب..."],
            "standard": ["⏳ جارٍ فهم السؤال وتجهيز الإجابة...", "⏳ يتم الآن ترتيب المسألة وإعداد الرد..."]
        }
        return _pick_variant_v35(pools.get(dialect, pools["standard"]), f"v42proc:{channel}:{question[:80]}:{now_ts_raw()[:13]}")

    def _decorate_answer_v35(question: str, ans: str, channel: str, user_id: str | None, user_name: str | None, raw: Any, context: dict, cfg: dict) -> tuple[str, str, str]:  # type: ignore[override]
        try:
            display_name = _extract_display_name_v35(raw, user_name) or ("مدير النظام" if channel == "dashboard" else "")
        except Exception:
            display_name = user_name or ""
        try:
            dialect = _v42dash.detect_dialect(question, context)
        except Exception:
            dialect = _detect_dialect_name_v35(question, context)
        try:
            # Social and follow-up must not receive daily greeting or religious preamble.
            if _v42dash.is_social(question, context) or _v42dash.is_followup(question, context):
                return ans, display_name, dialect
            if cfg.get("operational", {}).get("answer_preamble_enabled", True) and _v42dash.should_use_fatwa_preamble(question, ans, context):
                pre = _v42dash.preamble(question, ans, display_name, dialect, f"v42pre:{channel}:{user_id}:{question[:80]}:{today_str()}")
                if pre and not str(ans).lstrip().startswith("بسم الله"):
                    ans = pre + "\n\n" + ans
            # Daily greeting only for first substantive domain interaction, never for social/follow-up.
            if _should_daily_greet_v35(channel, user_id, cfg) and not str(ans).startswith("مرحب"):
                try:
                    greet = _greeting_v35(display_name, dialect, f"v42greet:{channel}:{user_id}:{today_str()}")
                    if greet and not _v42dash.is_social(question, context):
                        ans = greet + "\n\n" + ans
                except Exception:
                    pass
            return ans, display_name, dialect
        except Exception:
            return _DECORATE_ANSWER_BEFORE_V42(question, ans, channel, user_id, user_name, raw, context, cfg)

# ---------------------------------------------------------------------------
# V44 Dashboard Bridge — state-machine-driven routing for notices/preambles.
# This override comes after older bridges and therefore takes precedence.
# ---------------------------------------------------------------------------
try:
    import v44_dialogue_state_machine as _v44dash
except Exception:
    _v44dash = None

if _v44dash is not None:
    def _processing_notice_v35(question: str, channel: str = "whatsapp") -> str:  # type: ignore[override]
        try:
            if not _v44dash.should_send_processing_notice(question, None):
                return ""
        except Exception:
            return ""
        try:
            dialect = _v44dash.detect_dialect(question, None)
        except Exception:
            dialect = "standard"
        pools = {
            "egyptian": ["⏳ لحظة، براجع المسألة وبحضّر الإجابة...", "⏳ جارٍ فهم المسألة وتجهيز الرد..."],
            "gulf": ["⏳ أبشر، أرتّب المسألة الآن...", "⏳ جارٍ دراسة المسألة وتجهيز الرد..."],
            "shami": ["⏳ لحظة، عم رتّب المسألة وبجهّز الجواب..."],
            "standard": ["⏳ جارٍ فهم السؤال وتجهيز الإجابة...", "⏳ يتم الآن ترتيب المسألة وإعداد الرد..."]
        }
        return _pick_variant_v35(pools.get(dialect, pools["standard"]), f"v44proc:{channel}:{question[:80]}:{now_ts_raw()[:13]}")

    def _decorate_answer_v35(question: str, ans: str, channel: str, user_id: str | None, user_name: str | None, raw: Any, context: dict, cfg: dict) -> tuple[str, str, str]:  # type: ignore[override]
        try:
            display_name = _extract_display_name_v35(raw, user_name) or ("مدير النظام" if channel == "dashboard" else "")
        except Exception:
            display_name = user_name or ""
        try:
            dialect = _v44dash.detect_dialect(question, context)
        except Exception:
            dialect = _detect_dialect_name_v35(question, context)
        try:
            if _v44dash.is_social(question, context) or _v44dash.is_followup(question, context):
                return ans, display_name, dialect
            if cfg.get("operational", {}).get("answer_preamble_enabled", True) and _v44dash.should_use_fatwa_preamble(question, ans, context):
                pre = _v44dash.preamble(question, ans, display_name, dialect, f"v44pre:{channel}:{user_id}:{question[:80]}:{today_str()}")
                if pre and not str(ans).lstrip().startswith("بسم الله"):
                    ans = pre + "\n\n" + ans
            if _should_daily_greet_v35(channel, user_id, cfg) and not str(ans).startswith("مرحب"):
                try:
                    greet = _greeting_v35(display_name, dialect, f"v44greet:{channel}:{user_id}:{today_str()}")
                    if greet and not _v44dash.is_social(question, context):
                        ans = greet + "\n\n" + ans
                except Exception:
                    pass
            return ans, display_name, dialect
        except Exception:
            return _DECORATE_ANSWER_BEFORE_V42(question, ans, channel, user_id, user_name, raw, context, cfg)

# ---------------------------------------------------------------------------
# V45 Dashboard Bridge — production dialogue router + scholarly guard.
# Takes precedence over v42/v44 decoration. This is not a per-case patch:
# it uses route scoring and conversation state before adding notices/preambles.
# ---------------------------------------------------------------------------
try:
    import v45_full_scholarly_production as _v45dash
except Exception:
    _v45dash = None

if _v45dash is not None:
    def _processing_notice_v35(question: str, channel: str = "whatsapp") -> str:  # type: ignore[override]
        try:
            if not _v45dash.should_send_processing_notice(question, None):
                return ""
            dialect = _v45dash.detect_dialect(question, None)
        except Exception:
            return ""
        pools = {
            "egyptian": ["⏳ لحظة، براجع المسألة وبحضّر الإجابة...", "⏳ جارٍ فهم المسألة وتجهيز الرد..."],
            "gulf": ["⏳ أبشر، أرتّب المسألة الآن...", "⏳ جارٍ دراسة المسألة وتجهيز الرد..."],
            "shami": ["⏳ لحظة، عم رتّب المسألة وبجهّز الجواب..."],
            "standard": ["⏳ جارٍ فهم السؤال وتجهيز الإجابة...", "⏳ يتم الآن ترتيب المسألة وإعداد الرد..."]
        }
        return _pick_variant_v35(pools.get(dialect, pools["standard"]), f"v45proc:{channel}:{question[:80]}:{now_ts_raw()[:13]}")

    def _decorate_answer_v35(question: str, ans: str, channel: str, user_id: str | None, user_name: str | None, raw: Any, context: dict, cfg: dict) -> tuple[str, str, str]:  # type: ignore[override]
        try:
            display_name = _extract_display_name_v35(raw, user_name) or ("مدير النظام" if channel == "dashboard" else "")
        except Exception:
            display_name = user_name or ""
        try:
            r = _v45dash.route(question, context)
            dialect = r.dialect
            if r.social or r.followup or r.intent in {"general_non_domain", "small_unknown", "identity"}:
                return ans, display_name, dialect
            if cfg.get("operational", {}).get("answer_preamble_enabled", True) and _v45dash.should_use_fatwa_preamble(question, ans, context):
                pre = _v45dash.preamble(question, ans, display_name, dialect, f"v45pre:{channel}:{user_id}:{question[:80]}:{today_str()}")
                if pre and not str(ans).lstrip().startswith("بسم الله"):
                    ans = pre + "\n\n" + ans
            if _should_daily_greet_v35(channel, user_id, cfg) and not str(ans).startswith("مرحب") and r.domain:
                try:
                    greet = _greeting_v35(display_name, dialect, f"v45greet:{channel}:{user_id}:{today_str()}")
                    if greet:
                        ans = greet + "\n\n" + ans
                except Exception:
                    pass
            return ans, display_name, dialect
        except Exception:
            return _DECORATE_ANSWER_BEFORE_V42(question, ans, channel, user_id, user_name, raw, context, cfg)
