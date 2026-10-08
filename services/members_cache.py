# -*- coding: utf-8 -*-
"""Кэш участников для живого поиска в панели (не для счётчиков варнов).

Таблица members_cache: синк при старте + member join/update/remove.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from logger import get_logger

_log = get_logger('members_cache')
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
            CREATE TABLE IF NOT EXISTS members_cache (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                display_name TEXT,
                avatar_url TEXT,
                top_role_id INTEGER,
                is_staff INTEGER NOT NULL DEFAULT 0,
                branch TEXT,
                in_guild INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        ''')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_mc_name '
            'ON members_cache(guild_id, display_name)')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_mc_user '
            'ON members_cache(guild_id, username)')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_mc_staff '
            'ON members_cache(guild_id, is_staff, in_guild)')
        conn.commit()
    finally:
        if own:
            conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(r: sqlite3.Row) -> Dict[str, Any]:
    return {
        'guild_id': int(r['guild_id']),
        'user_id': int(r['user_id']),
        'username': r['username'] or '',
        'display_name': r['display_name'] or '',
        'avatar_url': r['avatar_url'] or '',
        'top_role_id': int(r['top_role_id']) if r['top_role_id'] else None,
        'is_staff': int(r['is_staff'] or 0),
        'branch': r['branch'] or None,
        'in_guild': int(r['in_guild'] or 0),
        'updated_at': r['updated_at'] or '',
    }


_UPSERT_SQL = '''INSERT INTO members_cache
   (guild_id, user_id, username, display_name, avatar_url,
    top_role_id, is_staff, branch, in_guild, updated_at)
   VALUES (?,?,?,?,?,?,?,?,1,?)
   ON CONFLICT(guild_id, user_id) DO UPDATE SET
     username=excluded.username,
     display_name=excluded.display_name,
     avatar_url=excluded.avatar_url,
     top_role_id=excluded.top_role_id,
     is_staff=excluded.is_staff,
     branch=excluded.branch,
     in_guild=1,
     updated_at=excluded.updated_at'''


def _member_row(guild_id: int, member) -> Optional[tuple]:
    """Снимок участника для INSERT (без записи в БД).

    is_staff/branch — только из get_staff_info(member), не из варнов.
    """
    if member is None:
        return None
    from services.warn_config import member_rank_snapshot
    from services.warn_acl import get_staff_info

    uid = int(member.id)
    username = str(getattr(member, 'name', '') or '')
    display = str(
        getattr(member, 'display_name', None)
        or getattr(member, 'global_name', None)
        or username
        or uid
    )
    avatar = ''
    try:
        avatar = str(member.display_avatar.url)
    except Exception:
        pass
    _rank, top_rid, _name = member_rank_snapshot(member)
    is_staff_b, branch, _r = get_staff_info(member)
    return (
        int(guild_id), uid, username, display, avatar,
        top_rid, 1 if is_staff_b else 0, branch, _now(),
    )


def _bulk_upsert_rows(rows: List[tuple]) -> int:
    """Одна транзакция на пачку — не блокируем event-loop 20k commit'ами."""
    if not rows:
        return 0
    ensure_table()
    with _LOCK:
        conn = _conn()
        try:
            conn.executemany(_UPSERT_SQL, rows)
            conn.commit()
            return len(rows)
        finally:
            conn.close()


def upsert_member(guild_id: int, member) -> None:
    """Записать/обновить участника из discord.Member."""
    row = _member_row(guild_id, member)
    if row is None:
        return
    _bulk_upsert_rows([row])


def mark_left(guild_id: int, user_id: int) -> None:
    ensure_table()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'UPDATE members_cache SET in_guild=0, updated_at=? '
                'WHERE guild_id=? AND user_id=?',
                (_now(), int(guild_id), int(user_id)),
            )
            conn.commit()
        finally:
            conn.close()


def get_member(guild_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    ensure_table()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT * FROM members_cache WHERE guild_id=? AND user_id=?',
                (int(guild_id), int(user_id)),
            ).fetchone()
            return _row(row) if row else None
        finally:
            conn.close()


def search(
    guild_id: int,
    q: str,
    *,
    limit: int = 10,
    staff_only: bool | None = None,
) -> List[Dict[str, Any]]:
    """Поиск по display_name / username / user_id. max 10."""
    ensure_table()
    q = (q or '').strip()
    lim = max(1, min(10, int(limit or 10)))
    where = ['guild_id=?']
    params: list = [int(guild_id)]
    if staff_only is True:
        where.append('is_staff=1')
    elif staff_only is False:
        where.append('is_staff=0')
    if q:
        if q.isdigit() and len(q) >= 3:
            where.append(
                '(user_id LIKE ? OR username LIKE ? OR display_name LIKE ?)')
            like = f'%{q}%'
            params.extend([like, f'%{q}%', f'%{q}%'])
        else:
            where.append(
                '(LOWER(username) LIKE ? OR LOWER(display_name) LIKE ? '
                'OR CAST(user_id AS TEXT) LIKE ?)')
            like = f'%{q.lower()}%'
            params.extend([like, like, f'%{q}%'])
    wh = ' AND '.join(where)
    with _LOCK:
        conn = _conn()
        try:
            # берём с запасом и сортируем по качеству совпадения в питоне
            rows = conn.execute(
                f'''SELECT * FROM members_cache WHERE {wh}
                    ORDER BY in_guild DESC, display_name COLLATE NOCASE
                    LIMIT ?''',
                params + [max(lim * 8, 40)],
            ).fetchall()
            items = [_row(r) for r in rows]
        finally:
            conn.close()

    if not q:
        return items[:lim]

    ql = q.lower().lstrip('@')

    def _rank(h: Dict[str, Any]) -> tuple:
        un = (h.get('username') or '').lower()
        dn = (h.get('display_name') or '').lower()
        uid = str(h.get('user_id') or '')
        if uid == q:
            score = 0
        elif un == ql:
            score = 1
        elif dn == ql:
            score = 2
        elif un.startswith(ql):
            score = 3
        elif dn.startswith(ql):
            score = 4
        elif ql in un:
            score = 5
        elif ql in dn:
            score = 6
        else:
            score = 7
        return (0 if h.get('in_guild') else 1, score, dn)

    items.sort(key=_rank)
    return items[:lim]


async def sync_guild(guild) -> int:
    """Полная синхронизация участников гильдии.

    Снимки собираем в event-loop чанками (с yield), запись в SQLite —
    через executor одной/несколькими транзакциями. Раньше 20k sync
    commit'ов вешали цикл на минуты и рвали voice transport.
    """
    import asyncio

    if guild is None:
        return 0
    ensure_table()
    n = 0
    try:
        members = list(getattr(guild, 'members', []) or [])
        if not members:
            try:
                async for m in guild.fetch_members(limit=None):
                    members.append(m)
            except Exception as ex:
                _log.debug('fetch_members: %s', ex)

        gid = int(guild.id)
        batch: List[tuple] = []
        chunk = 200
        loop = asyncio.get_running_loop()

        async def _flush() -> None:
            nonlocal n, batch
            if not batch:
                return
            rows = batch
            batch = []
            written = await loop.run_in_executor(None, _bulk_upsert_rows, rows)
            n += int(written or 0)

        for i, m in enumerate(members):
            try:
                row = _member_row(gid, m)
                if row:
                    batch.append(row)
            except Exception as ex:
                _log.debug('snapshot %s: %s', getattr(m, 'id', '?'), ex)
            if len(batch) >= chunk:
                await _flush()
            # отдаём цикл раз в chunk — войс/gateway не голодают
            if (i + 1) % chunk == 0:
                await asyncio.sleep(0)

        await _flush()
        _log.info('members_cache sync guild=%s n=%s', guild.id, n)
    except Exception as ex:
        _log.warning('sync_guild: %s', ex)
    return n
