# -*- coding: utf-8 -*-
"""
SQL Server sync layer for Mawareth AI Dashboard.

Design rules:
- SQLite remains the local-first operational store so the project never stops if SQL Server is down.
- SQL Server is a mirrored central store; sync is best-effort and retriable.
- No inheritance logic is changed here.
- Credentials are read from dashboard config/registry; password must never be written into project JSON.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import pyodbc  # type: ignore
except Exception:  # pragma: no cover
    pyodbc = None

TABLE_SPECS = {
    "conversations": {
        "pk": "id",
        "columns": ["id", "ts", "date", "channel", "user_id", "user_name", "direction", "question", "answer", "answer_type", "dialect", "elapsed_ms", "status", "raw_json"],
    },
    "service_events": {
        "pk": "id",
        "columns": ["id", "ts", "service", "action", "status", "message"],
    },
    "webhook_events": {
        "pk": "fingerprint",
        "columns": ["fingerprint", "ts", "channel", "sender", "text"],
    },
    "technical_events": {
        "pk": "id",
        "columns": ["id", "ts", "date", "level", "component", "event", "message", "raw_json"],
    },
    "users": {
        "pk": "username",
        "columns": ["username", "display_name", "password_hash", "role", "permissions", "active", "created_at", "updated_at", "force_password_change", "failed_login_count", "locked_until", "last_login"],
    },
    "sessions": {
        "pk": "token",
        "columns": ["token", "username", "created_at", "expires_at", "last_seen"],
    },
    "notifications": {
        "pk": "id",
        "columns": ["id", "ts", "level", "title", "message", "seen", "raw_json"],
    },
    "login_attempts": {
        "pk": "id",
        "columns": ["id", "ts", "username", "success", "ip", "message"],
    },
    "review_items": {
        "pk": "id",
        "columns": ["id", "ts", "conversation_id", "question", "answer", "reason", "status", "reviewer", "reviewed_at", "notes"],
    },
}

SYNC_META_TABLE = "sync_meta"
SYNC_ERROR_TABLE = "sync_errors"


def now_ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def mask_secret(v: str | None) -> str:
    if not v:
        return ""
    v = str(v)
    if len(v) <= 8:
        return "***"
    return v[:4] + "…" + v[-4:]


def _cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return cfg.get("sqlserver", {}) or {}


def sql_enabled(cfg: Dict[str, Any]) -> bool:
    s = _cfg(cfg)
    return bool(s.get("enabled") and s.get("sync_enabled", True))


def _available_drivers() -> List[str]:
    if pyodbc is None:
        return []
    try:
        return list(pyodbc.drivers())
    except Exception:
        return []


def _pick_driver(preferred: str | None = None) -> str:
    drivers = _available_drivers()
    if preferred and preferred in drivers:
        return preferred
    for d in ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server Native Client 11.0", "SQL Server"]:
        if d in drivers:
            return d
    return preferred or "ODBC Driver 18 for SQL Server"


def _clean_ident(name: str, default: str = "MawarethAI") -> str:
    name = str(name or default).strip()
    # Keep SQL Server identifiers safe. Do not allow injection through database/table names.
    name = re.sub(r"[^A-Za-z0-9_\-\u0600-\u06FF]", "_", name)
    return name[:120] or default


def _bracket_ident(name: str) -> str:
    return "[" + _clean_ident(name).replace("]", "") + "]"


def build_connection_string(cfg: Dict[str, Any], database: Optional[str] = None, use_master: bool = False) -> str:
    s = _cfg(cfg)
    driver = _pick_driver(s.get("driver") or "ODBC Driver 18 for SQL Server")
    host = str(s.get("host") or "").strip()
    port = str(s.get("port") or "").strip()
    server = host
    if port and "," not in server and "\\" not in server:
        server = f"{server},{port}"
    dbname = "master" if use_master else _clean_ident(database or s.get("database") or "MawarethAI")
    encrypt = "yes" if bool(s.get("encrypt", True)) else "no"
    trust = "yes" if bool(s.get("trust_server_certificate", True)) else "no"
    timeout = int(s.get("timeout_seconds") or 5)
    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={server}",
        f"DATABASE={dbname}",
        f"Encrypt={encrypt}",
        f"TrustServerCertificate={trust}",
        f"Connection Timeout={timeout}",
    ]
    auth = str(s.get("auth_mode") or "sql").lower()
    if auth in {"windows", "trusted", "integrated"}:
        parts.append("Trusted_Connection=yes")
    else:
        parts.append(f"UID={s.get('username') or ''}")
        parts.append(f"PWD={s.get('password') or ''}")
    return ";".join(parts)


def connect(cfg: Dict[str, Any], database: Optional[str] = None, use_master: bool = False, autocommit: bool = False):
    if pyodbc is None:
        raise RuntimeError("pyodbc غير مثبت. شغّل install_dashboard_requirements.bat أو pip install pyodbc، وتأكد من وجود ODBC Driver 17/18 for SQL Server.")
    conn_str = build_connection_string(cfg, database=database, use_master=use_master)
    return pyodbc.connect(conn_str, autocommit=autocommit)


def test_connection(cfg: Dict[str, Any]) -> Dict[str, Any]:
    s = _cfg(cfg)
    if pyodbc is None:
        return {"ok": False, "error": "pyodbc_not_installed", "message": "pyodbc غير مثبت", "drivers": []}
    try:
        with connect(cfg, use_master=True, autocommit=True) as conn:
            row = conn.cursor().execute("SELECT @@VERSION AS version").fetchone()
            drivers = _available_drivers()
            return {"ok": True, "version": str(row[0])[:500] if row else "", "driver_used": _pick_driver(s.get("driver")), "drivers": drivers}
    except Exception as e:
        return {"ok": False, "error": type(e).__name__, "message": str(e)[:1200], "driver_used": _pick_driver(s.get("driver")), "drivers": _available_drivers()}


def ensure_database(cfg: Dict[str, Any]) -> Dict[str, Any]:
    s = _cfg(cfg)
    dbname = _clean_ident(s.get("database") or "MawarethAI")
    try:
        with connect(cfg, use_master=True, autocommit=True) as conn:
            cur = conn.cursor()
            cur.execute("IF DB_ID(?) IS NULL EXEC('CREATE DATABASE ' + ?)", dbname, _bracket_ident(dbname))
        return {"ok": True, "database": dbname, "created_if_missing": True}
    except Exception as e:
        return {"ok": False, "database": dbname, "error": type(e).__name__, "message": str(e)[:1200]}


def _column_type(col: str, pk: str) -> str:
    if col == pk:
        return "NVARCHAR(220) NOT NULL"
    if col in {"elapsed_ms", "active", "force_password_change", "failed_login_count", "seen", "success"}:
        return "INT NULL"
    return "NVARCHAR(MAX) NULL"


def ensure_schema(cfg: Dict[str, Any]) -> Dict[str, Any]:
    created = []
    try:
        db_res = ensure_database(cfg)
        if not db_res.get("ok"):
            return db_res
        with connect(cfg, autocommit=True) as conn:
            cur = conn.cursor()
            for table, spec in TABLE_SPECS.items():
                pk = spec["pk"]
                cols = spec["columns"]
                col_defs = ",\n".join([f"{_bracket_ident(c)} {_column_type(c, pk)}" for c in cols])
                sql = f"""
                IF OBJECT_ID(N'dbo.{table}', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.{_bracket_ident(table)} (
                        {col_defs},
                        CONSTRAINT PK_{_clean_ident(table)} PRIMARY KEY ({_bracket_ident(pk)})
                    )
                END
                """
                cur.execute(sql)
                created.append(table)
            cur.execute(f"""
            IF OBJECT_ID(N'dbo.{SYNC_META_TABLE}', N'U') IS NULL
            BEGIN
                CREATE TABLE dbo.{_bracket_ident(SYNC_META_TABLE)} (
                    [key] NVARCHAR(220) NOT NULL PRIMARY KEY,
                    [value] NVARCHAR(MAX) NULL,
                    [updated_at] NVARCHAR(40) NULL
                )
            END
            """)
            cur.execute(f"""
            IF OBJECT_ID(N'dbo.{SYNC_ERROR_TABLE}', N'U') IS NULL
            BEGIN
                CREATE TABLE dbo.{_bracket_ident(SYNC_ERROR_TABLE)} (
                    [id] NVARCHAR(220) NOT NULL PRIMARY KEY,
                    [ts] NVARCHAR(40) NULL,
                    [level] NVARCHAR(40) NULL,
                    [message] NVARCHAR(MAX) NULL,
                    [raw_json] NVARCHAR(MAX) NULL
                )
            END
            """)
            _upsert_meta(cur, "schema_version", "v31_sqlserver_sync")
        return {"ok": True, "tables": created, "database": _clean_ident(_cfg(cfg).get("database") or "MawarethAI")}
    except Exception as e:
        return {"ok": False, "error": type(e).__name__, "message": str(e)[:1500]}


def _upsert_meta(cur, key: str, value: str) -> None:
    cur.execute(f"""
    MERGE dbo.{_bracket_ident(SYNC_META_TABLE)} AS target
    USING (SELECT ? AS [key], ? AS [value], ? AS [updated_at]) AS src
    ON target.[key] = src.[key]
    WHEN MATCHED THEN UPDATE SET [value]=src.[value], [updated_at]=src.[updated_at]
    WHEN NOT MATCHED THEN INSERT ([key], [value], [updated_at]) VALUES (src.[key], src.[value], src.[updated_at]);
    """, key, value, now_ts())


def _coerce_row_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    return str(v)


def _upsert_row(cur, table: str, spec: Dict[str, Any], row: Dict[str, Any]) -> None:
    pk = spec["pk"]
    cols = spec["columns"]
    values = [_coerce_row_value(row.get(c)) for c in cols]
    source_cols = ", ".join([f"? AS {_bracket_ident(c)}" for c in cols])
    update_cols = [c for c in cols if c != pk]
    update_sql = ", ".join([f"target.{_bracket_ident(c)} = src.{_bracket_ident(c)}" for c in update_cols])
    insert_cols = ", ".join([_bracket_ident(c) for c in cols])
    insert_vals = ", ".join([f"src.{_bracket_ident(c)}" for c in cols])
    sql = f"""
    MERGE dbo.{_bracket_ident(table)} AS target
    USING (SELECT {source_cols}) AS src
    ON target.{_bracket_ident(pk)} = src.{_bracket_ident(pk)}
    WHEN MATCHED THEN UPDATE SET {update_sql}
    WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals});
    """
    cur.execute(sql, *values)


def _sqlite_rows(sqlite_path: Path, table: str, cols: List[str]) -> List[Dict[str, Any]]:
    if not sqlite_path.exists():
        return []
    with sqlite3.connect(str(sqlite_path)) as conn:
        conn.row_factory = sqlite3.Row
        # only select columns that exist in local SQLite table
        pragma = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {r[1] for r in pragma}
        if not existing:
            return []
        selected = [c for c in cols if c in existing]
        if not selected:
            return []
        rows = conn.execute(f"SELECT {', '.join('['+c+']' for c in selected)} FROM [{table}]").fetchall()
        out = []
        for r in rows:
            d = {c: None for c in cols}
            for c in selected:
                d[c] = r[c]
            out.append(d)
        return out


def sync_sqlite_to_sqlserver(sqlite_path: Path | str, cfg: Dict[str, Any], tables: Optional[List[str]] = None, limit_per_table: Optional[int] = None) -> Dict[str, Any]:
    sqlite_path = Path(sqlite_path)
    if not sql_enabled(cfg):
        return {"ok": True, "enabled": False, "message": "SQL Server sync disabled"}
    schema = ensure_schema(cfg)
    if not schema.get("ok"):
        return {"ok": False, "stage": "ensure_schema", **schema}
    counts: Dict[str, int] = {}
    errors: List[Dict[str, str]] = []
    table_names = tables or list(TABLE_SPECS.keys())
    try:
        with connect(cfg, autocommit=False) as conn:
            cur = conn.cursor()
            try:
                cur.fast_executemany = False
            except Exception:
                pass
            for table in table_names:
                spec = TABLE_SPECS[table]
                rows = _sqlite_rows(sqlite_path, table, spec["columns"])
                if limit_per_table:
                    rows = rows[-int(limit_per_table):]
                n = 0
                for row in rows:
                    if not row.get(spec["pk"]):
                        continue
                    try:
                        _upsert_row(cur, table, spec, row)
                        n += 1
                    except Exception as e:
                        errors.append({"table": table, "pk": str(row.get(spec["pk"])), "error": type(e).__name__, "message": str(e)[:500]})
                counts[table] = n
            _upsert_meta(cur, "last_sync_at", now_ts())
            _upsert_meta(cur, "last_sync_counts", json.dumps(counts, ensure_ascii=False))
            conn.commit()
        return {"ok": not errors, "synced": counts, "errors": errors[:50], "error_count": len(errors), "sqlserver_enabled": True}
    except Exception as e:
        return {"ok": False, "stage": "sync", "error": type(e).__name__, "message": str(e)[:1500], "synced": counts, "errors": errors[:50]}


def _sqlite_table_count(sqlite_path: Path | str, table: str) -> int:
    try:
        with sqlite3.connect(str(sqlite_path)) as conn:
            exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if not exists:
                return 0
            return int(conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0])
    except Exception:
        return -1


def _sqlserver_table_count(cfg: Dict[str, Any], table: str) -> int:
    try:
        with connect(cfg, autocommit=True) as conn:
            cur = conn.cursor()
            cur.execute(f"IF OBJECT_ID(N'dbo.{table}', N'U') IS NULL SELECT CAST(-1 AS INT) ELSE SELECT COUNT(*) FROM dbo.{_bracket_ident(table)}")
            row = cur.fetchone()
            return int(row[0]) if row else -1
    except Exception:
        return -1


def mirror_counts(sqlite_path: Path | str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return lightweight parity counts for SQLite and SQL Server. No deletions, just visibility."""
    tables = list(TABLE_SPECS.keys())
    sqlite_counts = {t: _sqlite_table_count(sqlite_path, t) for t in tables}
    sql_counts = {}
    can_query_sql = False
    try:
        if sql_enabled(cfg):
            test = test_connection(cfg)
            can_query_sql = bool(test.get("ok"))
            if can_query_sql:
                # Ensure schema so count queries are meaningful. Failure still falls back gracefully.
                ensure_schema(cfg)
                sql_counts = {t: _sqlserver_table_count(cfg, t) for t in tables}
    except Exception:
        can_query_sql = False
    diffs = {}
    for t in tables:
        sc = sqlite_counts.get(t, -1)
        qc = sql_counts.get(t, -1)
        if qc >= 0 and sc >= 0 and sc != qc:
            diffs[t] = {"sqlite": sc, "sqlserver": qc}
    return {"sqlite": sqlite_counts, "sqlserver": sql_counts, "can_query_sql": can_query_sql, "diffs": diffs, "in_sync_by_counts": not bool(diffs) and bool(sql_counts)}


def get_status(sqlite_path: Path | str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    s = _cfg(cfg)
    status = {
        "configured": bool(s.get("host") and s.get("database")),
        "enabled": bool(s.get("enabled")),
        "sync_enabled": bool(s.get("sync_enabled", True)),
        "host": s.get("host", ""),
        "port": s.get("port", ""),
        "database": s.get("database", ""),
        "username": s.get("username", ""),
        "password_set": bool(s.get("password")),
        "password_masked": mask_secret(s.get("password")),
        "driver": s.get("driver") or _pick_driver(None),
        "drivers_available": _available_drivers(),
        "pyodbc_installed": pyodbc is not None,
    }
    if pyodbc is None:
        status.update({"ok": False, "message": "pyodbc غير مثبت"})
        return status
    test = test_connection(cfg)
    status.update({"connection": test, "ok": bool(test.get("ok"))})
    try:
        status["mirror_counts"] = mirror_counts(sqlite_path, cfg) if bool(test.get("ok")) else {"sqlite": {t: _sqlite_table_count(sqlite_path, t) for t in TABLE_SPECS.keys()}, "sqlserver": {}, "can_query_sql": False, "diffs": {}, "in_sync_by_counts": False}
    except Exception as e:
        status["mirror_counts"] = {"error": type(e).__name__, "message": str(e)[:500]}
    return status


def sqlite_backup_zip(sqlite_path: Path | str, config_path: Path | str, logs_dir: Path | str, output_dir: Path | str) -> Dict[str, Any]:
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    name = f"mawareth_sqlite_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    out = outdir / name
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        sp = Path(sqlite_path)
        cp = Path(config_path)
        if sp.exists():
            z.write(sp, "data/dashboard.sqlite3")
        if cp.exists():
            z.write(cp, "data/dashboard_config.json")
        logs = Path(logs_dir)
        if logs.exists():
            for p in logs.glob("*.jsonl"):
                z.write(p, f"logs/{p.name}")
            for p in logs.glob("*.csv"):
                z.write(p, f"logs/{p.name}")
    return {"ok": True, "path": str(out), "filename": name}


def sqlserver_backup(cfg: Dict[str, Any]) -> Dict[str, Any]:
    s = _cfg(cfg)
    dbname = _clean_ident(s.get("database") or "MawarethAI")
    backup_dir = str(s.get("backup_dir") or "").strip() or r"C:\MawarethAI_Backups"
    # Path is on SQL Server machine, not necessarily local dashboard machine.
    safe_filename = f"{dbname}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
    disk = os.path.join(backup_dir, safe_filename)
    try:
        with connect(cfg, use_master=True, autocommit=True) as conn:
            cur = conn.cursor()
            sql = f"BACKUP DATABASE {_bracket_ident(dbname)} TO DISK = ? WITH INIT, NAME = ?"
            cur.execute(sql, disk, f"MawarethAI backup {now_ts()}")
        return {"ok": True, "backup_path_on_sql_server": disk, "note": "المسار يخص جهاز SQL Server نفسه"}
    except Exception as e:
        return {"ok": False, "error": type(e).__name__, "message": str(e)[:1500], "backup_path_on_sql_server": disk}


class SqlServerSyncWorker:
    def __init__(self, sqlite_path: Path, config_provider, logger=None):
        self.sqlite_path = Path(sqlite_path)
        self.config_provider = config_provider
        self.logger = logger
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_result: Dict[str, Any] = {"ok": None, "message": "not started"}

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="SqlServerSyncWorker", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def run_once(self) -> Dict[str, Any]:
        cfg = self.config_provider()
        result = sync_bidirectional(self.sqlite_path, cfg)
        self.last_result = result
        return result

    def _emit(self, level: str, message: str, raw: Any = None):
        if self.logger:
            try:
                self.logger(level, "sqlserver", "sync_worker", message, raw)
            except Exception:
                pass

    def _loop(self):
        while not self._stop.is_set():
            cfg = self.config_provider()
            s = _cfg(cfg)
            interval = int(s.get("sync_interval_seconds") or 30)
            interval = min(max(interval, 10), 3600)
            if sql_enabled(cfg):
                result = sync_bidirectional(self.sqlite_path, cfg)
                self.last_result = result
                if result.get("ok"):
                    self._emit("info", "تمت المزامنة الثنائية بين SQLite و SQL Server", result)
                else:
                    self._emit("warning", "تعذرت مزامنة SQL Server؛ سيستمر المشروع على SQLite ويحاول لاحقًا", result)
            self._stop.wait(interval)


def _sqlserver_rows(cfg: Dict[str, Any], table: str, cols: List[str]) -> List[Dict[str, Any]]:
    with connect(cfg, autocommit=True) as conn:
        cur = conn.cursor()
        col_sql = ", ".join([_bracket_ident(c) for c in cols])
        cur.execute(f"SELECT {col_sql} FROM dbo.{_bracket_ident(table)}")
        desc = [d[0] for d in cur.description]
        rows = []
        for r in cur.fetchall():
            rows.append({desc[i]: r[i] for i in range(len(desc))})
        return rows


def sync_sqlserver_to_sqlite(sqlite_path: Path | str, cfg: Dict[str, Any], tables: Optional[List[str]] = None, limit_per_table: Optional[int] = None) -> Dict[str, Any]:
    """Pull data from SQL Server into local SQLite without deleting local-only rows.

    This is a safety mirror, not a replacement for local-first operation. It is useful if
    the central SQL Server already contains rows from another machine or an earlier package.
    """
    sqlite_path = Path(sqlite_path)
    if not sql_enabled(cfg):
        return {"ok": True, "enabled": False, "message": "SQL Server sync disabled"}
    schema = ensure_schema(cfg)
    if not schema.get("ok"):
        return {"ok": False, "stage": "ensure_schema", **schema}
    counts: Dict[str, int] = {}
    errors: List[Dict[str, str]] = []
    table_names = tables or list(TABLE_SPECS.keys())
    try:
        with sqlite3.connect(str(sqlite_path)) as sq:
            for table in table_names:
                spec = TABLE_SPECS[table]
                rows = _sqlserver_rows(cfg, table, spec["columns"])
                if limit_per_table:
                    rows = rows[-int(limit_per_table):]
                pragma = sq.execute(f"PRAGMA table_info({table})").fetchall()
                existing = {r[1] for r in pragma}
                if not existing:
                    counts[table] = 0
                    continue
                cols = [c for c in spec["columns"] if c in existing]
                if not cols:
                    counts[table] = 0
                    continue
                placeholders = ", ".join(["?" for _ in cols])
                col_sql = ", ".join(["["+c+"]" for c in cols])
                sql = f"INSERT OR REPLACE INTO [{table}] ({col_sql}) VALUES ({placeholders})"
                n = 0
                for row in rows:
                    try:
                        sq.execute(sql, [row.get(c) for c in cols])
                        n += 1
                    except Exception as e:
                        errors.append({"table": table, "pk": str(row.get(spec["pk"])), "error": type(e).__name__, "message": str(e)[:500]})
                counts[table] = n
            sq.commit()
        return {"ok": not errors, "pulled": counts, "errors": errors[:50], "error_count": len(errors), "sqlserver_enabled": True}
    except Exception as e:
        return {"ok": False, "stage": "pull", "error": type(e).__name__, "message": str(e)[:1500], "pulled": counts, "errors": errors[:50]}


def sync_bidirectional(sqlite_path: Path | str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronize both directions without making SQL Server a point of failure.

    We always try push and pull independently. A failure in one direction does not
    prevent the other direction from running, so a temporary row-level issue or
    connection interruption does not block the local SQLite-first workflow.
    """
    push = sync_sqlite_to_sqlserver(sqlite_path, cfg)
    pull = None
    try:
        pull = sync_sqlserver_to_sqlite(sqlite_path, cfg)
    except Exception as e:
        pull = {"ok": False, "stage": "pull_exception", "error": type(e).__name__, "message": str(e)[:1500]}
    ok = bool(push.get("ok") and pull and pull.get("ok"))
    return {"ok": ok, "push": push, "pull": pull, "mode": "bidirectional_union_no_delete"}
