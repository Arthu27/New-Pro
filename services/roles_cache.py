# -*- coding: utf-8 -*-
"""SQLite-кэш ролей гильдии для панели (без Discord API на чтении)."""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from logger import get_logger

_log = get_logger('roles_cache')
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


def ensure_table(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    if own:
        conn = _conn()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS roles_cache (
                guild_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                name TEXT,
                color INTEGER DEFAULT 0,
                position INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, role_id)
            )
        ''')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_roles_pos '
            'ON roles_cache(guild_id, position DESC)')
        conn.commit()
    finally:
        if own:
            conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_role(guild_id: int, role) -> None:
    if role is None:
        return
    ensure_table()
    rid = int(getattr(role, 'id', 0) or 0)
    if not rid:
        return
    name = str(getattr(role, 'name', '') or '')
    color = int(getattr(getattr(role, 'color', None), 'value', 0) or 0)
    pos = int(getattr(role, 'position', 0) or 0)
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                '''INSERT INTO roles_cache
                   (guild_id, role_id, name, color, position, updated_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(guild_id, role_id) DO UPDATE SET
                     name=excluded.name, color=excluded.color,
                     position=excluded.position, updated_at=excluded.updated_at''',
                (int(guild_id), rid, name, color, pos, _now()),
            )
            conn.commit()
        finally:
            conn.close()


def delete_role(guild_id: int, role_id: int) -> None:
    ensure_table()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'DELETE FROM roles_cache WHERE guild_id=? AND role_id=?',
                (int(guild_id), int(role_id)),
            )
            conn.commit()
        finally:
            conn.close()


def sync_guild(guild) -> int:
    if guild is None:
        return 0
    ensure_table()
    rows = []
    for r in list(getattr(guild, 'roles', []) or []):
        rid = int(getattr(r, 'id', 0) or 0)
        if not rid:
            continue
        rows.append((
            int(guild.id), rid,
            str(getattr(r, 'name', '') or ''),
            int(getattr(getattr(r, 'color', None), 'value', 0) or 0),
            int(getattr(r, 'position', 0) or 0),
            _now(),
        ))
    with _LOCK:
        conn = _conn()
        try:
            conn.executemany(
                '''INSERT INTO roles_cache
                   (guild_id, role_id, name, color, position, updated_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(guild_id, role_id) DO UPDATE SET
                     name=excluded.name, color=excluded.color,
                     position=excluded.position, updated_at=excluded.updated_at''',
                rows,
            )
            # убрать удалённые
            keep = {r[1] for r in rows}
            existing = conn.execute(
                'SELECT role_id FROM roles_cache WHERE guild_id=?',
                (int(guild.id),),
            ).fetchall()
            for er in existing:
                if int(er['role_id']) not in keep:
                    conn.execute(
                        'DELETE FROM roles_cache WHERE guild_id=? AND role_id=?',
                        (int(guild.id), int(er['role_id'])),
                    )
            conn.commit()
            _log.info('roles_cache sync guild=%s n=%s', guild.id, len(rows))
            return len(rows)
        finally:
            conn.close()


def list_roles(guild_id: int) -> List[Dict[str, Any]]:
    ensure_table()
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                'SELECT * FROM roles_cache WHERE guild_id=? '
                'ORDER BY position DESC',
                (int(guild_id),),
            ).fetchall()
            return [{
                'id': str(r['role_id']),
                'name': r['name'] or '',
                'color': int(r['color'] or 0),
                'position': int(r['position'] or 0),
            } for r in rows]
        finally:
            conn.close()
