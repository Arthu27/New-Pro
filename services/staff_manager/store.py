# -*- coding: utf-8 -*-
"""SQLite: staff_actions + идемпотентность + состояние меню."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from logger import get_logger

_log = get_logger('staff_manager.store')
_LOCK = threading.RLock()


def _db_path() -> str:
    try:
        from config import Config
        return Config.DB_PATH
    except Exception:
        return os.path.join('data', 'bot.db')


def _conn() -> sqlite3.Connection:
    path = _db_path()
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=5000')
    except Exception:
        pass
    return conn


def ensure_tables() -> None:
    with _LOCK:
        conn = _conn()
        try:
            conn.executescript('''
            CREATE TABLE IF NOT EXISTS staff_actions (
                id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                actor_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                branch TEXT,
                old_key TEXT,
                new_key TEXT,
                reason TEXT,
                source TEXT NOT NULL DEFAULT 'bot',
                ok INTEGER NOT NULL DEFAULT 1,
                meta TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sa_target
                ON staff_actions(guild_id, target_id, created_at);
            CREATE TABLE IF NOT EXISTS staff_action_locks (
                guild_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                action_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, target_id, action_id)
            );
            CREATE TABLE IF NOT EXISTS staff_menu_state (
                token TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                actor_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                step TEXT,
                payload TEXT,
                updated_at TEXT NOT NULL
            );
            ''')
            conn.commit()
        finally:
            conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_action_id() -> str:
    return uuid.uuid4().hex


def claim_action_once(guild_id: int, target_id: int, action_id: str) -> bool:
    """True если впервые; False если дубль (двойной клик)."""
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            try:
                conn.execute(
                    'INSERT INTO staff_action_locks '
                    '(guild_id, target_id, action_id, created_at) VALUES (?,?,?,?)',
                    (int(guild_id), int(target_id), str(action_id), _now()),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
        finally:
            conn.close()


def record_action(
    *,
    guild_id: int,
    actor_id: int,
    target_id: int,
    action: str,
    branch: str = '',
    old_key: str = '',
    new_key: str = '',
    reason: str = '',
    source: str = 'bot',
    ok: bool = True,
    meta: dict | None = None,
    action_id: str | None = None,
) -> str:
    ensure_tables()
    aid = action_id or new_action_id()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'INSERT OR REPLACE INTO staff_actions '
                '(id, guild_id, actor_id, target_id, action, branch, old_key, '
                'new_key, reason, source, ok, meta, created_at) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    aid, int(guild_id), int(actor_id), int(target_id),
                    action, branch or '', old_key or '', new_key or '',
                    reason or '', source, 1 if ok else 0,
                    json.dumps(meta or {}, ensure_ascii=False), _now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    return aid


def list_actions(guild_id: int, target_id: int, *, limit: int = 30) -> List[dict]:
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                'SELECT * FROM staff_actions WHERE guild_id=? AND target_id=? '
                'ORDER BY created_at DESC LIMIT ?',
                (int(guild_id), int(target_id), int(limit)),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def save_menu_state(token: str, guild_id: int, actor_id: int, target_id: int,
                    step: str, payload: dict) -> None:
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'INSERT OR REPLACE INTO staff_menu_state '
                '(token, guild_id, actor_id, target_id, step, payload, updated_at) '
                'VALUES (?,?,?,?,?,?,?)',
                (token, int(guild_id), int(actor_id), int(target_id),
                 step, json.dumps(payload or {}, ensure_ascii=False), _now()),
            )
            conn.commit()
        finally:
            conn.close()


def load_menu_state(token: str) -> Optional[dict]:
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT * FROM staff_menu_state WHERE token=?', (token,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d['payload'] = json.loads(d.get('payload') or '{}')
            except Exception:
                d['payload'] = {}
            return d
        finally:
            conn.close()
