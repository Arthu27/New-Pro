from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DB_PATH = os.getenv("DATABASE_PATH", "data/database.sqlite")


def _resolve_db_path(path: Optional[str] = None) -> Path:
    db_path = Path(path or DEFAULT_DB_PATH)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def connect(path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(_resolve_db_path(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path: Optional[str] = None) -> None:
    with connect(path) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS module_configs (
                guild_id TEXT NOT NULL, module_id TEXT NOT NULL, config_json TEXT NOT NULL DEFAULT '{}', updated_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, module_id)
            );
            CREATE TABLE IF NOT EXISTS command_permissions (
                guild_id TEXT NOT NULL, command_name TEXT NOT NULL, target_type TEXT NOT NULL CHECK(target_type IN ('role','user')),
                target_id TEXT NOT NULL, effect TEXT NOT NULL CHECK(effect IN ('allow','deny')),
                visibility TEXT NOT NULL DEFAULT 'use' CHECK(visibility IN ('use','show','hide')), updated_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, command_name, target_type, target_id)
            );
            CREATE TABLE IF NOT EXISTS draft_configs (
                guild_id TEXT NOT NULL, user_id TEXT NOT NULL, scope TEXT NOT NULL, draft_json TEXT NOT NULL DEFAULT '{}', updated_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id, scope)
            );
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT NOT NULL, actor_id TEXT, action TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}', created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS log_channels (
                guild_id TEXT PRIMARY KEY, config_json TEXT NOT NULL DEFAULT '{}', updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings_sessions (
                guild_id TEXT NOT NULL, user_id TEXT NOT NULL, last_scope TEXT NOT NULL DEFAULT 'overview',
                draft_json TEXT NOT NULL DEFAULT '{}', updated_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS login_codes (
                guild_id TEXT NOT NULL, user_id TEXT NOT NULL, username TEXT NOT NULL, code TEXT NOT NULL,
                expires_at INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token TEXT PRIMARY KEY, guild_id TEXT NOT NULL, user_id TEXT NOT NULL, username TEXT NOT NULL,
                portal TEXT NOT NULL, expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS access_portals (
                guild_id TEXT PRIMARY KEY, config_json TEXT NOT NULL DEFAULT '{}', updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS guild_snapshots (
                guild_id TEXT PRIMARY KEY, snapshot_json TEXT NOT NULL DEFAULT '{}', updated_at INTEGER NOT NULL
            );
        """)


def now() -> int:
    return int(time.time())


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


# ── Module configs ──

def get_module_config(guild_id: str, module_id: str) -> Dict[str, Any]:
    init_db()
    with connect() as db:
        row = db.execute("SELECT config_json FROM module_configs WHERE guild_id=? AND module_id=?", (guild_id, module_id)).fetchone()
    return _loads(row["config_json"], {}) if row else {}


def set_module_config(guild_id: str, module_id: str, config: Dict[str, Any]) -> None:
    init_db()
    with connect() as db:
        db.execute("""INSERT INTO module_configs (guild_id, module_id, config_json, updated_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, module_id) DO UPDATE SET config_json=excluded.config_json, updated_at=excluded.updated_at""",
            (guild_id, module_id, json.dumps(config, ensure_ascii=False), now()))


def get_all_modules(guild_id: str) -> Dict[str, Dict[str, Any]]:
    init_db()
    with connect() as db:
        rows = db.execute("SELECT module_id, config_json FROM module_configs WHERE guild_id=?", (guild_id,)).fetchall()
    return {row["module_id"]: _loads(row["config_json"], {}) for row in rows}


# ── Permissions ──

def set_permission_rule(guild_id: str, command_name: str, target_type: str, target_id: str, effect: str, visibility: str = "use") -> None:
    init_db()
    with connect() as db:
        db.execute("""INSERT INTO command_permissions (guild_id, command_name, target_type, target_id, effect, visibility, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(guild_id, command_name, target_type, target_id)
            DO UPDATE SET effect=excluded.effect, visibility=excluded.visibility, updated_at=excluded.updated_at""",
            (guild_id, command_name, target_type, target_id, effect, visibility, now()))


def get_permission_rules(guild_id: str, command_name: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db()
    sql = "SELECT * FROM command_permissions WHERE guild_id=?"
    args: list[Any] = [guild_id]
    if command_name:
        sql += " AND command_name=?"
        args.append(command_name)
    with connect() as db:
        rows = db.execute(sql, args).fetchall()
    return [dict(row) for row in rows]


# ── Drafts ──

def set_draft(guild_id: str, user_id: str, scope: str, draft: Dict[str, Any]) -> None:
    init_db()
    with connect() as db:
        db.execute("""INSERT INTO draft_configs (guild_id, user_id, scope, draft_json, updated_at) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id, scope) DO UPDATE SET draft_json=excluded.draft_json, updated_at=excluded.updated_at""",
            (guild_id, user_id, scope, json.dumps(draft, ensure_ascii=False), now()))


def get_draft(guild_id: str, user_id: str, scope: str) -> Dict[str, Any]:
    init_db()
    with connect() as db:
        row = db.execute("SELECT draft_json FROM draft_configs WHERE guild_id=? AND user_id=? AND scope=?", (guild_id, user_id, scope)).fetchone()
    return _loads(row["draft_json"], {}) if row else {}


# ── Log channels ──

def save_log_channels(guild_id: str, config: Dict[str, Any]) -> None:
    init_db()
    with connect() as db:
        db.execute("""INSERT INTO log_channels (guild_id, config_json, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET config_json=excluded.config_json, updated_at=excluded.updated_at""",
            (guild_id, json.dumps(config, ensure_ascii=False), now()))


def get_log_channels(guild_id: str) -> Dict[str, Any]:
    init_db()
    with connect() as db:
        row = db.execute("SELECT config_json FROM log_channels WHERE guild_id=?", (guild_id,)).fetchone()
    return _loads(row["config_json"], {}) if row else {}


# ── Audit logs ──

def add_audit_log(guild_id: str, action: str, details: Dict[str, Any], actor_id: Optional[str] = None) -> None:
    init_db()
    with connect() as db:
        db.execute("INSERT INTO audit_logs (guild_id, actor_id, action, details_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, actor_id, action, json.dumps(details, ensure_ascii=False), now()))


def get_audit_logs(guild_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    init_db()
    with connect() as db:
        rows = db.execute("SELECT * FROM audit_logs WHERE guild_id=? ORDER BY id DESC LIMIT ?", (guild_id, limit)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["details"] = _loads(item.pop("details_json"), {})
        result.append(item)
    return result


# ── Auth / DM code login ──

def create_login_code(guild_id: str, user_id: str, username: str, code: str, expires_at: int) -> None:
    init_db()
    with connect() as db:
        db.execute("""INSERT INTO login_codes (guild_id, user_id, username, code, expires_at, used, created_at) VALUES (?, ?, ?, ?, ?, 0, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET username=excluded.username, code=excluded.code, expires_at=excluded.expires_at, used=0, created_at=excluded.created_at""",
            (guild_id, user_id, username, code, expires_at, now()))


def verify_login_code(guild_id: str, user_id: str, code: str) -> bool:
    init_db()
    with connect() as db:
        row = db.execute("SELECT code, expires_at, used FROM login_codes WHERE guild_id=? AND user_id=?", (guild_id, user_id)).fetchone()
        if not row or row["used"] or row["expires_at"] < now() or str(row["code"]) != str(code):
            return False
        db.execute("UPDATE login_codes SET used=1 WHERE guild_id=? AND user_id=?", (guild_id, user_id))
        return True


def create_auth_session(guild_id: str, user_id: str, username: str, portal: str, ttl_seconds: int = 60 * 60 * 24 * 7) -> str:
    init_db()
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute("INSERT INTO auth_sessions (token, guild_id, user_id, username, portal, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (token, guild_id, user_id, username, portal, now() + ttl_seconds, now()))
    return token


def get_auth_session(token: str) -> Optional[Dict[str, Any]]:
    init_db()
    with connect() as db:
        row = db.execute("SELECT * FROM auth_sessions WHERE token=?", (token,)).fetchone()
    if not row or row["expires_at"] < now():
        return None
    return dict(row)


# ── Access portals ──

def save_access_portals(guild_id: str, config: Dict[str, Any]) -> None:
    init_db()
    with connect() as db:
        db.execute("""INSERT INTO access_portals (guild_id, config_json, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET config_json=excluded.config_json, updated_at=excluded.updated_at""",
            (guild_id, json.dumps(config, ensure_ascii=False), now()))


def get_access_portals(guild_id: str) -> Dict[str, Any]:
    init_db()
    with connect() as db:
        row = db.execute("SELECT config_json FROM access_portals WHERE guild_id=?", (guild_id,)).fetchone()
    return _loads(row["config_json"], {}) if row else {}


# ── Guild snapshot ──

def save_guild_snapshot(guild_id: str, snapshot: Dict[str, Any]) -> None:
    init_db()
    with connect() as db:
        db.execute("""INSERT INTO guild_snapshots (guild_id, snapshot_json, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET snapshot_json=excluded.snapshot_json, updated_at=excluded.updated_at""",
            (guild_id, json.dumps(snapshot, ensure_ascii=False), now()))


def get_guild_snapshot(guild_id: str) -> Dict[str, Any]:
    init_db()
    with connect() as db:
        row = db.execute("SELECT snapshot_json, updated_at FROM guild_snapshots WHERE guild_id=?", (guild_id,)).fetchone()
    if not row:
        return {}
    data = _loads(row["snapshot_json"], {})
    data["snapshotUpdatedAt"] = row["updated_at"]
    return data


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {_resolve_db_path()}")
