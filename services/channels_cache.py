# -*- coding: utf-8 -*-
"""SQLite-кэш каналов гильдии для панели (без Discord API на чтении)."""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List

from logger import get_logger

_log = get_logger('channels_cache')
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
            CREATE TABLE IF NOT EXISTS channels_cache (
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                name TEXT,
                type INTEGER DEFAULT 0,
                category_id INTEGER,
                position INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, channel_id)
            )
        ''')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_chan_pos '
            'ON channels_cache(guild_id, position)')
        conn.commit()
    finally:
        if own:
            conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ch_type(ch) -> int:
    try:
        t = getattr(ch, 'type', None)
        return int(getattr(t, 'value', t) or 0)
    except Exception:
        return 0


def upsert_channel(guild_id: int, channel) -> None:
    if channel is None:
        return
    ensure_table()
    cid = int(getattr(channel, 'id', 0) or 0)
    if not cid:
        return
    cat = getattr(channel, 'category_id', None)
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                '''INSERT INTO channels_cache
                   (guild_id, channel_id, name, type, category_id,
                    position, updated_at)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(guild_id, channel_id) DO UPDATE SET
                     name=excluded.name, type=excluded.type,
                     category_id=excluded.category_id,
                     position=excluded.position,
                     updated_at=excluded.updated_at''',
                (
                    int(guild_id), cid,
                    str(getattr(channel, 'name', '') or ''),
                    _ch_type(channel),
                    int(cat) if cat else None,
                    int(getattr(channel, 'position', 0) or 0),
                    _now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def delete_channel(guild_id: int, channel_id: int) -> None:
    ensure_table()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'DELETE FROM channels_cache WHERE guild_id=? AND channel_id=?',
                (int(guild_id), int(channel_id)),
            )
            conn.commit()
        finally:
            conn.close()


def sync_guild(guild) -> int:
    if guild is None:
        return 0
    ensure_table()
    rows = []
    for ch in list(getattr(guild, 'channels', []) or []):
        cid = int(getattr(ch, 'id', 0) or 0)
        if not cid:
            continue
        cat = getattr(ch, 'category_id', None)
        rows.append((
            int(guild.id), cid,
            str(getattr(ch, 'name', '') or ''),
            _ch_type(ch),
            int(cat) if cat else None,
            int(getattr(ch, 'position', 0) or 0),
            _now(),
        ))
    with _LOCK:
        conn = _conn()
        try:
            conn.executemany(
                '''INSERT INTO channels_cache
                   (guild_id, channel_id, name, type, category_id,
                    position, updated_at)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(guild_id, channel_id) DO UPDATE SET
                     name=excluded.name, type=excluded.type,
                     category_id=excluded.category_id,
                     position=excluded.position,
                     updated_at=excluded.updated_at''',
                rows,
            )
            keep = {r[1] for r in rows}
            existing = conn.execute(
                'SELECT channel_id FROM channels_cache WHERE guild_id=?',
                (int(guild.id),),
            ).fetchall()
            for er in existing:
                if int(er['channel_id']) not in keep:
                    conn.execute(
                        'DELETE FROM channels_cache '
                        'WHERE guild_id=? AND channel_id=?',
                        (int(guild.id), int(er['channel_id'])),
                    )
            conn.commit()
            _log.info('channels_cache sync guild=%s n=%s', guild.id, len(rows))
            return len(rows)
        finally:
            conn.close()


def list_channels(guild_id: int) -> List[Dict[str, Any]]:
    ensure_table()
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                'SELECT * FROM channels_cache WHERE guild_id=? '
                'ORDER BY position ASC',
                (int(guild_id),),
            ).fetchall()
            return [{
                'id': str(r['channel_id']),
                'name': r['name'] or '',
                'type': int(r['type'] or 0),
                'category_id': (
                    str(r['category_id']) if r['category_id'] else ''),
                'position': int(r['position'] or 0),
            } for r in rows]
        finally:
            conn.close()
