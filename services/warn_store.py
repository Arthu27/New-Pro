# -*- coding: utf-8 -*-
"""Постоянное хранилище варнов (SQLite).

Счётчик = COUNT(*) WHERE active = 1. Отдельного числового счётчика нет,
чтобы он не расходился с историей. Снятие = active=0 + removed_by/at,
запись истории не удаляется.

Миграция: старые списки из GuildData(namespace=warnings) и
data/warnings.json переносятся один раз при первом обращении к гильдии.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from logger import get_logger

_log = get_logger('warn_store')

_LOCK = threading.RLock()
_MIGRATED: set = set()


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
        conn.execute('PRAGMA synchronous=NORMAL')
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
            CREATE TABLE IF NOT EXISTS warns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_staff_target INTEGER NOT NULL DEFAULT 0,
                branch TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                removed_by INTEGER,
                removed_at TEXT
            )
        ''')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_warns_user_active '
            'ON warns(guild_id, user_id, active)')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_warns_guild '
            'ON warns(guild_id)')
        conn.commit()
    finally:
        if own:
            conn.close()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        'id': int(row['id']),
        'guild_id': int(row['guild_id']),
        'user_id': int(row['user_id']),
        'moderator_id': int(row['moderator_id']),
        'reason': row['reason'] or 'Не указана',
        'created_at': row['created_at'] or '',
        'is_staff_target': int(row['is_staff_target'] or 0),
        'branch': row['branch'] or None,
        'active': int(row['active'] or 0),
        'removed_by': int(row['removed_by']) if row['removed_by'] else None,
        'removed_at': row['removed_at'] or None,
        # совместимость со старым форматом (панель / досье)
        'mod_id': str(row['moderator_id']),
        'mod': str(row['moderator_id']),
        'timestamp': row['created_at'] or '',
    }


def count_active(guild_id: int, user_id: int) -> int:
    ensure_table()
    migrate_guild(guild_id)
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT COUNT(*) AS c FROM warns '
                'WHERE guild_id=? AND user_id=? AND active=1',
                (int(guild_id), int(user_id)),
            ).fetchone()
            return int(row['c'] if row else 0)
        finally:
            conn.close()


def list_warns(
    guild_id: int,
    user_id: int,
    *,
    active_only: bool = False,
    limit: int = 0,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """История варнов (новые сверху)."""
    ensure_table()
    migrate_guild(guild_id)
    sql = (
        'SELECT * FROM warns WHERE guild_id=? AND user_id=?'
        + (' AND active=1' if active_only else '')
        + ' ORDER BY id DESC'
    )
    params: list = [int(guild_id), int(user_id)]
    if limit and limit > 0:
        sql += ' LIMIT ? OFFSET ?'
        params.extend([int(limit), int(offset or 0)])
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()


def list_active_user_ids(guild_id: int) -> List[int]:
    """Все user_id с active-варнами на сервере (для sync при старте)."""
    ensure_table()
    migrate_guild(guild_id)
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                'SELECT DISTINCT user_id FROM warns '
                'WHERE guild_id=? AND active=1',
                (int(guild_id),),
            ).fetchall()
            return [int(r['user_id']) for r in rows]
        finally:
            conn.close()


def add_warn(
    guild_id: int,
    user_id: int,
    moderator_id: int,
    reason: str,
    *,
    is_staff_target: bool = False,
    branch: str | None = None,
    created_at: str | None = None,
) -> Dict[str, Any]:
    """Добавить активный варн. Возвращает запись."""
    ensure_table()
    migrate_guild(guild_id)
    ts = created_at or datetime.now(timezone.utc).isoformat()
    reason = (reason or 'Не указана').strip() or 'Не указана'
    with _LOCK:
        conn = _conn()
        try:
            cur = conn.execute(
                '''INSERT INTO warns
                   (guild_id, user_id, moderator_id, reason, created_at,
                    is_staff_target, branch, active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1)''',
                (
                    int(guild_id), int(user_id), int(moderator_id),
                    reason, ts,
                    1 if is_staff_target else 0,
                    branch or None,
                ),
            )
            conn.commit()
            wid = int(cur.lastrowid)
            row = conn.execute(
                'SELECT * FROM warns WHERE id=?', (wid,)
            ).fetchone()
            return _row_to_dict(row)
        finally:
            conn.close()


def deactivate_warn(
    warn_id: int,
    removed_by: int,
    *,
    removed_at: str | None = None,
) -> Optional[Dict[str, Any]]:
    """Снять варн (soft): active=0. Возвращает запись или None."""
    ensure_table()
    ts = removed_at or datetime.now(timezone.utc).isoformat()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT * FROM warns WHERE id=? AND active=1',
                (int(warn_id),),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                'UPDATE warns SET active=0, removed_by=?, removed_at=? '
                'WHERE id=?',
                (int(removed_by), ts, int(warn_id)),
            )
            conn.commit()
            row2 = conn.execute(
                'SELECT * FROM warns WHERE id=?', (int(warn_id),)
            ).fetchone()
            return _row_to_dict(row2) if row2 else None
        finally:
            conn.close()


def deactivate_last_active(
    guild_id: int, user_id: int, removed_by: int,
) -> Optional[Dict[str, Any]]:
    """Снять самый свежий активный варн пользователя."""
    active = list_warns(guild_id, user_id, active_only=True, limit=1)
    if not active:
        return None
    return deactivate_warn(active[0]['id'], removed_by)


def mirror_json(guild_id: int, user_id: int) -> None:
    """Зеркало data/warnings.json для веб-панели (только active)."""
    try:
        warns = list_warns(guild_id, user_id, active_only=True)
        path = 'data/warnings.json'
        os.makedirs('data', exist_ok=True)
        data: dict = {}
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
        if not isinstance(data, dict):
            data = {}
        gid, uid = str(guild_id), str(user_id)
        payload = []
        for w in reversed(warns[-25:]):  # хронологический порядок в JSON
            payload.append({
                'id': w['id'],
                'reason': w['reason'],
                'mod': w.get('mod') or str(w.get('moderator_id')),
                'mod_id': str(w.get('moderator_id')),
                'timestamp': w.get('created_at') or w.get('timestamp') or '',
                'branch': w.get('branch'),
                'is_staff_target': w.get('is_staff_target', 0),
            })
        if payload:
            if not isinstance(data.get(gid), dict):
                data[gid] = {}
            data[gid][uid] = payload
        else:
            if isinstance(data.get(gid), dict):
                data[gid].pop(uid, None)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        _log.error('mirror_json: %s', e)


# ── миграция со старого GuildData / JSON ──────────────────────────────

def _legacy_marker(guild_id: int) -> str:
    return f'data/.warns_migrated_{int(guild_id)}'


def migrate_guild(guild_id: int) -> None:
    """Одноразовая миграция старых варнов гильдии в таблицу warns."""
    gid = int(guild_id)
    if gid in _MIGRATED:
        return
    marker = _legacy_marker(gid)
    if os.path.exists(marker):
        _MIGRATED.add(gid)
        return
    with _LOCK:
        if gid in _MIGRATED:
            return
        ensure_table()
        conn = _conn()
        try:
            # уже есть строки — считаем мигрированным (не дублируем)
            existing = conn.execute(
                'SELECT COUNT(*) AS c FROM warns WHERE guild_id=?',
                (gid,),
            ).fetchone()
            if existing and int(existing['c'] or 0) > 0:
                _touch_marker(marker)
                _MIGRATED.add(gid)
                return

            imported = 0
            # 1) GuildData namespace=warnings
            try:
                from db import GuildData
                gd = GuildData('warnings')
                all_data = gd.get_all(gid) or {}
                for uid_s, wlist in all_data.items():
                    imported += _import_list(conn, gid, uid_s, wlist)
            except Exception as _ex:
                _log.debug('migrate GuildData: %s', _ex)

            # 2) data/warnings.json (если GuildData пуст / дополнение)
            try:
                path = 'data/warnings.json'
                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    users = (data or {}).get(str(gid)) or {}
                    if isinstance(users, dict):
                        for uid_s, wlist in users.items():
                            # не дублировать если уже импортировали из GD
                            has = conn.execute(
                                'SELECT 1 FROM warns WHERE guild_id=? '
                                'AND user_id=? LIMIT 1',
                                (gid, int(uid_s)),
                            ).fetchone()
                            if has:
                                continue
                            imported += _import_list(conn, gid, uid_s, wlist)
            except Exception as _ex:
                _log.debug('migrate warnings.json: %s', _ex)

            conn.commit()
            _touch_marker(marker)
            _MIGRATED.add(gid)
            if imported:
                _log.info(
                    'warn_store: мигрировано %s варнов для guild=%s',
                    imported, gid)
        except Exception as e:
            _log.warning('migrate_guild(%s): %s', gid, e)
        finally:
            conn.close()


def _touch_marker(path: str) -> None:
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write('1')
    except Exception:
        pass


def _import_list(conn, guild_id, uid_s, wlist) -> int:
    try:
        uid = int(uid_s)
    except (TypeError, ValueError):
        return 0
    if not isinstance(wlist, list):
        return 0
    n = 0
    for w in wlist:
        if not isinstance(w, dict):
            continue
        reason = str(w.get('reason') or 'Не указана')
        try:
            mod_id = int(w.get('mod_id') or 0)
        except (TypeError, ValueError):
            mod_id = 0
        ts = str(w.get('timestamp') or w.get('created_at') or '')
        if not ts:
            ts = datetime.now(timezone.utc).isoformat()
        active = 1
        if w.get('active') in (0, '0', False):
            active = 0
        branch = w.get('branch')
        is_staff = 1 if w.get('is_staff_target') else 0
        conn.execute(
            '''INSERT INTO warns
               (guild_id, user_id, moderator_id, reason, created_at,
                is_staff_target, branch, active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (int(guild_id), uid, mod_id, reason, ts,
             is_staff, branch, active),
        )
        n += 1
    return n
