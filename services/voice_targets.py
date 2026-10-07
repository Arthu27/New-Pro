# -*- coding: utf-8 -*-
"""Постоянное хранилище целевых голосовых каналов (voice stay).

Таблица voice_targets(bot_id, guild_id, channel_id):
  bot_id — стабильный ключ бота ('main' / 'event' / snowflake).
  Запись есть → бот ОБЯЗАН сидеть в канале и возвращаться при кике.
  Записи нет → намеренный leave (/leave), вотчдог не возвращает.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import List, Optional, Tuple

from logger import get_logger

_log = get_logger('voice_targets')
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


def ensure_table() -> None:
    with _LOCK:
        conn = _conn()
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS voice_targets (
                    bot_id TEXT NOT NULL,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (bot_id, guild_id)
                )
            ''')
            conn.commit()
        finally:
            conn.close()


def set_target(bot_id: str, guild_id: int, channel_id: int) -> None:
    """Запомнить, где бот должен сидеть (после /join или конфига).

    guild_id=0 — pending seed из env/json до resolve канала в on_ready.
    """
    ensure_table()
    bid = str(bot_id or '').strip()
    cid = int(channel_id or 0)
    if not bid or not cid:
        return
    gid = int(guild_id or 0)
    # guild_id=0 разрешён как pending; отрицательные — нет
    if gid < 0:
        return
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                '''INSERT INTO voice_targets (bot_id, guild_id, channel_id, updated_at)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(bot_id, guild_id) DO UPDATE SET
                     channel_id=excluded.channel_id,
                     updated_at=CURRENT_TIMESTAMP''',
                (bid, gid, cid),
            )
            conn.commit()
            _log.info('voice_targets set %s guild=%s → channel=%s',
                      bid, gid, cid)
        finally:
            conn.close()


def clear_target(bot_id: str, guild_id: int) -> None:
    """Намеренный leave — вотчдог больше не возвращает."""
    ensure_table()
    bid = str(bot_id or '').strip()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'DELETE FROM voice_targets WHERE bot_id=? AND guild_id=?',
                (bid, int(guild_id)),
            )
            conn.commit()
            _log.info('voice_targets clear %s guild=%s (intentional leave)',
                      bid, guild_id)
        finally:
            conn.close()


def get_target(bot_id: str, guild_id: int) -> Optional[int]:
    ensure_table()
    bid = str(bot_id or '').strip()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT channel_id FROM voice_targets '
                'WHERE bot_id=? AND guild_id=?',
                (bid, int(guild_id)),
            ).fetchone()
            return int(row['channel_id']) if row else None
        finally:
            conn.close()


def list_targets(bot_id: str) -> List[Tuple[int, int]]:
    """[(guild_id, channel_id), ...] для бота."""
    ensure_table()
    bid = str(bot_id or '').strip()
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                'SELECT guild_id, channel_id FROM voice_targets WHERE bot_id=?',
                (bid,),
            ).fetchall()
            return [(int(r['guild_id']), int(r['channel_id'])) for r in rows]
        finally:
            conn.close()


def has_any(bot_id: str) -> bool:
    return bool(list_targets(bot_id))
