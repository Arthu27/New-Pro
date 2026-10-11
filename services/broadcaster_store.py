# -*- coding: utf-8 -*-
"""SQLite Broadcaster: трибуны, слоты пожеланий, лав-румы."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

_LOCK = threading.RLock()
_PATH: Optional[str] = None


def set_db_path(path: str | None) -> None:
    global _PATH
    _PATH = path


def db_path() -> str:
    if _PATH:
        return _PATH
    override = (os.environ.get('BROADCASTER_DB') or '').strip()
    if override:
        return override
    return os.path.join('data', 'broadcaster.db')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    path = db_path()
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=5000')
    except Exception:
        pass
    return conn


def ensure() -> None:
    with _LOCK:
        conn = _conn()
        try:
            conn.executescript(
                '''
                CREATE TABLE IF NOT EXISTS tribunes (
                    id TEXT PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    owner_id INTEGER NOT NULL,
                    catalog_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    starts_at TEXT NOT NULL,
                    channel_id INTEGER,
                    event_id INTEGER,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    opened_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_tribunes_guild
                    ON tribunes(guild_id, status, starts_at);
                CREATE TABLE IF NOT EXISTS wish_slots (
                    slot_key TEXT PRIMARY KEY,
                    sent_at TEXT NOT NULL,
                    message_id INTEGER,
                    channel_id INTEGER
                );
                CREATE TABLE IF NOT EXISTS wish_deck (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    deck_json TEXT NOT NULL,
                    last_text TEXT
                );
                CREATE TABLE IF NOT EXISTS wish_deletes (
                    message_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    delete_at TEXT NOT NULL,
                    done INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS love_rooms (
                    channel_id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    owner_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                '''
            )
            conn.commit()
        finally:
            conn.close()


def _row(row) -> Optional[dict]:
    return dict(row) if row else None


def insert_tribune(
    *,
    guild_id: int,
    owner_id: int,
    catalog_key: str,
    title: str,
    starts_at: str,
    channel_id: int,
    event_id: int,
) -> dict:
    ensure()
    tid = uuid.uuid4().hex
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'INSERT INTO tribunes (id, guild_id, owner_id, catalog_key, title, '
                'starts_at, channel_id, event_id, status, created_at) '
                'VALUES (?,?,?,?,?,?,?,?,?,?)',
                (
                    tid, int(guild_id), int(owner_id), catalog_key, title,
                    starts_at, int(channel_id or 0), int(event_id or 0),
                    'scheduled', _now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    return get_tribune(tid)


def get_tribune(tid: str) -> Optional[dict]:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            return _row(conn.execute(
                'SELECT * FROM tribunes WHERE id=?', (tid,)
            ).fetchone())
        finally:
            conn.close()


def list_live(guild_id: int) -> list:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                'SELECT * FROM tribunes WHERE guild_id=? AND status IN '
                "('scheduled','opening','opened') ORDER BY starts_at ASC",
                (int(guild_id),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def due_tribunes(now_iso: str) -> list:
    """Сравнение по мгновению, не по строке: +03:00 и Z — одно и то же время."""
    from datetime import datetime

    from services.broadcaster_logic import tribune_is_due
    ensure()
    try:
        now = datetime.fromisoformat(now_iso)
    except Exception:
        return []
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT * FROM tribunes WHERE status='scheduled' ORDER BY starts_at ASC"
            ).fetchall()
        finally:
            conn.close()
    return [dict(r) for r in rows if tribune_is_due(r['starts_at'], now, r['status'])]


def claim_open(tid: str) -> bool:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            cur = conn.execute(
                "UPDATE tribunes SET status='opening' WHERE id=? AND status='scheduled'",
                (tid,),
            )
            conn.commit()
            return cur.rowcount == 1
        finally:
            conn.close()


def release_open(tid: str) -> None:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                "UPDATE tribunes SET status='scheduled' WHERE id=? AND status='opening'",
                (tid,),
            )
            conn.commit()
        finally:
            conn.close()


def mark_opened(tid: str) -> None:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                "UPDATE tribunes SET status='opened', opened_at=? WHERE id=?",
                (_now(), tid),
            )
            conn.commit()
        finally:
            conn.close()


def mark_deleted(tid: str) -> None:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                "UPDATE tribunes SET status='deleted' WHERE id=?", (tid,)
            )
            conn.commit()
        finally:
            conn.close()


def update_tribune(tid: str, **fields) -> Optional[dict]:
    ensure()
    allowed = {'catalog_key', 'title', 'starts_at', 'channel_id', 'event_id', 'status'}
    sets = []
    args = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        sets.append(f'{key}=?')
        args.append(value)
    if not sets:
        return get_tribune(tid)
    args.append(tid)
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                f'UPDATE tribunes SET {", ".join(sets)} WHERE id=?', args
            )
            conn.commit()
        finally:
            conn.close()
    return get_tribune(tid)


def claim_wish_slot(slot_key: str) -> bool:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'INSERT INTO wish_slots (slot_key, sent_at) VALUES (?,?)',
                (slot_key, _now()),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()


def release_wish_slot(slot_key: str) -> None:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute('DELETE FROM wish_slots WHERE slot_key=?', (slot_key,))
            conn.commit()
        finally:
            conn.close()


def sent_wish_slots() -> set:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute('SELECT slot_key FROM wish_slots').fetchall()
            return {r['slot_key'] for r in rows}
        finally:
            conn.close()


def wish_memory() -> tuple[list, str]:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT deck_json, last_text FROM wish_deck WHERE id=1'
            ).fetchone()
            if not row:
                return [], ''
            try:
                deck = json.loads(row['deck_json'] or '[]')
            except Exception:
                deck = []
            return list(deck or []), row['last_text'] or ''
        finally:
            conn.close()


def save_wish_memory(deck: list, last: str) -> None:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'INSERT INTO wish_deck (id, deck_json, last_text) VALUES (1,?,?) '
                'ON CONFLICT(id) DO UPDATE SET deck_json=excluded.deck_json, '
                'last_text=excluded.last_text',
                (json.dumps(deck, ensure_ascii=False), last or ''),
            )
            conn.commit()
        finally:
            conn.close()


def schedule_wish_delete(message_id: int, channel_id: int, delete_at: str) -> None:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'INSERT OR REPLACE INTO wish_deletes '
                '(message_id, channel_id, delete_at, done) VALUES (?,?,?,0)',
                (int(message_id), int(channel_id), delete_at),
            )
            conn.commit()
        finally:
            conn.close()


def due_wish_deletes(now_iso: str) -> list:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                'SELECT * FROM wish_deletes WHERE done=0 AND delete_at<=?',
                (now_iso,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def finish_wish_delete(message_id: int) -> None:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'UPDATE wish_deletes SET done=1 WHERE message_id=?',
                (int(message_id),),
            )
            conn.commit()
        finally:
            conn.close()


def add_love(channel_id: int, guild_id: int, owner_id: int) -> None:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'INSERT OR REPLACE INTO love_rooms '
                '(channel_id, guild_id, owner_id, created_at) VALUES (?,?,?,?)',
                (int(channel_id), int(guild_id), int(owner_id), _now()),
            )
            conn.commit()
        finally:
            conn.close()


def is_love(channel_id: int) -> bool:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT 1 FROM love_rooms WHERE channel_id=?',
                (int(channel_id),),
            ).fetchone()
            return row is not None
        finally:
            conn.close()


def remove_love(channel_id: int) -> None:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'DELETE FROM love_rooms WHERE channel_id=?', (int(channel_id),)
            )
            conn.commit()
        finally:
            conn.close()


def list_love(guild_id: int) -> list:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                'SELECT * FROM love_rooms WHERE guild_id=?', (int(guild_id),)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def meta_get(key: str, default: str = '') -> str:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT value FROM meta WHERE key=?', (key,)
            ).fetchone()
            return row['value'] if row else default
        finally:
            conn.close()


def meta_set(key: str, value: str) -> None:
    ensure()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'INSERT INTO meta (key, value) VALUES (?,?) '
                'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()
