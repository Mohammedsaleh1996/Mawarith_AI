# -*- coding: utf-8 -*-
"""
Windows Registry-backed settings for Mawareth AI Dashboard.

Purpose:
- Persist Telegram/WaPilot tokens and integration settings outside project folders.
- New dashboard packages can be replaced without re-entering tokens.
- Uses HKCU, so it does not require administrator privileges.

Registry path:
HKCU\\Software\\MawarethAI\\Dashboard
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict

REGISTRY_AVAILABLE = sys.platform.startswith("win")
REG_PATH = r"Software\MawarethAI\Dashboard"

# Map registry values to nested config paths.
VALUE_MAP = {
    "telegram_enabled": ("telegram", "enabled", "bool"),
    "telegram_bot_token": ("telegram", "bot_token", "str"),
    "telegram_poll_interval_seconds": ("telegram", "poll_interval_seconds", "int"),
    "telegram_last_update_id": ("telegram", "last_update_id", "int"),

    "wapilot_enabled": ("wapilot", "enabled", "bool"),
    "wapilot_instance_id": ("wapilot", "instance_id", "str"),
    "wapilot_webhook_path": ("wapilot", "webhook_path", "str"),
    "wapilot_public_webhook_url": ("wapilot", "public_webhook_url", "str"),
    "wapilot_api_url_template": ("wapilot", "api_url_template", "str"),
    "wapilot_api_token": ("wapilot", "api_token", "str"),
    "wapilot_send_payload_style": ("wapilot", "send_payload_style", "str"),

    # UI branding persists across replaced project folders.
    "ui_logo_title": ("ui", "logo_title", "str"),
    "ui_logo_subtitle": ("ui", "logo_subtitle", "str"),
    "ui_logo_file": ("ui", "logo_file", "str"),

    # Autostart / ngrok preferences also persist across replaced packages.
    "autostart_enabled": ("autostart", "enabled", "bool"),
    "autostart_telegram": ("autostart", "telegram", "bool"),
    "autostart_whatsapp": ("autostart", "whatsapp", "bool"),
    "autostart_ngrok": ("autostart", "ngrok", "bool"),
    "ngrok_path": ("ngrok", "path", "str"),
    "ngrok_public_url": ("ngrok", "public_url", "str"),
    "ngrok_domain": ("ngrok", "domain", "str"),
    "ngrok_strict_domain": ("ngrok", "strict_domain", "bool"),
    "ngrok_allow_random_fallback": ("ngrok", "allow_random_fallback", "bool"),
    "ngrok_enabled": ("ngrok", "enabled", "bool"),
    "operational_reply_mode": ("operational", "reply_mode", "str"),

    # SQL Server persistence / central mirror.
    "sqlserver_enabled": ("sqlserver", "enabled", "bool"),
    "sqlserver_sync_enabled": ("sqlserver", "sync_enabled", "bool"),
    "sqlserver_host": ("sqlserver", "host", "str"),
    "sqlserver_port": ("sqlserver", "port", "str"),
    "sqlserver_database": ("sqlserver", "database", "str"),
    "sqlserver_auth_mode": ("sqlserver", "auth_mode", "str"),
    "sqlserver_username": ("sqlserver", "username", "str"),
    "sqlserver_password": ("sqlserver", "password", "str"),
    "sqlserver_driver": ("sqlserver", "driver", "str"),
    "sqlserver_encrypt": ("sqlserver", "encrypt", "bool"),
    "sqlserver_trust_server_certificate": ("sqlserver", "trust_server_certificate", "bool"),
    "sqlserver_timeout_seconds": ("sqlserver", "timeout_seconds", "int"),
    "sqlserver_sync_interval_seconds": ("sqlserver", "sync_interval_seconds", "int"),
    "sqlserver_backup_dir": ("sqlserver", "backup_dir", "str"),
}

SECRET_KEYS = {"telegram_bot_token", "wapilot_api_token", "sqlserver_password"}


def _is_masked_secret(value: Any) -> bool:
    if value is None:
        return False
    v = str(value).strip()
    if not v:
        return False
    return ("…" in v) or ("..." in v) or ("***" in v) or v.startswith("****")


def _parse(value: Any, typ: str) -> Any:
    if typ == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}
    if typ == "int":
        try:
            return int(value)
        except Exception:
            return 0
    return "" if value is None else str(value)


def _to_registry_value(value: Any, typ: str) -> str:
    if typ == "bool":
        return "1" if bool(value) else "0"
    if typ == "int":
        return str(int(value or 0))
    return "" if value is None else str(value)


def _set_nested(cfg: Dict[str, Any], section: str, key: str, value: Any) -> None:
    cfg.setdefault(section, {})[key] = value


def _get_nested(cfg: Dict[str, Any], section: str, key: str, default: Any = None) -> Any:
    return cfg.get(section, {}).get(key, default)


def load_registry_config() -> Dict[str, Any]:
    """Return partial config loaded from Windows Registry. Empty on non-Windows."""
    if not REGISTRY_AVAILABLE:
        return {}
    try:
        import winreg  # type: ignore
    except Exception:
        return {}

    out: Dict[str, Any] = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ) as key:
            for reg_name, (section, cfg_key, typ) in VALUE_MAP.items():
                try:
                    raw, _ = winreg.QueryValueEx(key, reg_name)
                except FileNotFoundError:
                    continue
                value = _parse(raw, typ)
                # Do not let empty secret values overwrite existing config.
                if reg_name in SECRET_KEYS and not value:
                    continue
                # Do not let empty optional strings overwrite defaults.
                if typ == "str" and not value and reg_name not in SECRET_KEYS:
                    continue
                _set_nested(out, section, cfg_key, value)
    except FileNotFoundError:
        return {}
    except OSError:
        return {}
    return out


def save_registry_config(cfg: Dict[str, Any]) -> bool:
    """Persist integration config to Windows Registry. Returns True if written."""
    if not REGISTRY_AVAILABLE:
        return False
    try:
        import winreg  # type: ignore
    except Exception:
        return False

    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            for reg_name, (section, cfg_key, typ) in VALUE_MAP.items():
                value = _get_nested(cfg, section, cfg_key, None)
                # Preserve existing secret if submitted blank OR if the UI submitted a masked value.
                if reg_name in SECRET_KEYS and (not value or _is_masked_secret(value)):
                    continue
                reg_value = _to_registry_value(value, typ)
                winreg.SetValueEx(key, reg_name, 0, winreg.REG_SZ, reg_value)
        return True
    except OSError:
        return False


def sanitize_config_for_file(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return config safe for project JSON: no raw tokens in replaceable files."""
    safe = json.loads(json.dumps(cfg, ensure_ascii=False))
    safe.setdefault("telegram", {})["bot_token"] = ""
    safe.setdefault("wapilot", {})["api_token"] = ""
    safe.setdefault("sqlserver", {})["password"] = ""
    return safe


def delete_registry_config() -> bool:
    """Delete dashboard registry key. Used only when user intentionally clears settings."""
    if not REGISTRY_AVAILABLE:
        return False
    try:
        import winreg  # type: ignore
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_PATH)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return value[:4] + "…" + value[-4:]


def registry_status(mask: bool = True) -> Dict[str, Any]:
    cfg = load_registry_config()
    status = {
        "available": REGISTRY_AVAILABLE,
        "path": r"HKCU\\" + REG_PATH,
        "telegram_token_set": bool(cfg.get("telegram", {}).get("bot_token")),
        "wapilot_token_set": bool(cfg.get("wapilot", {}).get("api_token")),
        "telegram_enabled": cfg.get("telegram", {}).get("enabled", False),
        "wapilot_enabled": cfg.get("wapilot", {}).get("enabled", False),
        "wapilot_instance_id": cfg.get("wapilot", {}).get("instance_id", ""),
        "wapilot_public_webhook_url": cfg.get("wapilot", {}).get("public_webhook_url", ""),
        "sqlserver_enabled": cfg.get("sqlserver", {}).get("enabled", False),
        "sqlserver_host": cfg.get("sqlserver", {}).get("host", ""),
        "sqlserver_database": cfg.get("sqlserver", {}).get("database", ""),
        "sqlserver_password_set": bool(cfg.get("sqlserver", {}).get("password")),
        "keys_loaded": sorted([s + "." + k for s, vals in cfg.items() if isinstance(vals, dict) for k in vals.keys()]),
    }
    if mask:
        status["telegram_token_masked"] = mask_secret(cfg.get("telegram", {}).get("bot_token"))
        status["wapilot_token_masked"] = mask_secret(cfg.get("wapilot", {}).get("api_token"))
        status["sqlserver_password_masked"] = mask_secret(cfg.get("sqlserver", {}).get("password"))
    return status


if __name__ == "__main__":
    print(json.dumps(registry_status(mask=True), ensure_ascii=False, indent=2))
