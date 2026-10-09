# -*- coding: utf-8 -*-
"""SQLite: staff_actions, staff_consents, staff_profiles, emoji cache, меню."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
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

            CREATE TABLE IF NOT EXISTS staff_consents (
                id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                initiator_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                from_branch TEXT,
                from_role_id INTEGER,
                to_branch TEXT,
                to_role_id INTEGER,
                to_role_key TEXT,
                reason TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                decided_at TEXT,
                dm_message_id INTEGER,
                channel_message_id INTEGER,
                decline_reason TEXT,
                meta TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sc_target_status
                ON staff_consents(guild_id, target_id, status);
            CREATE INDEX IF NOT EXISTS idx_sc_status_exp
                ON staff_consents(status, expires_at);

            CREATE TABLE IF NOT EXISTS staff_profiles (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                branch TEXT,
                role_key TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                assigned_by INTEGER,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS staff_emoji_cache (
                guild_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                key TEXT NOT NULL,
                emoji TEXT NOT NULL,
                source TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, kind, key)
            );

            CREATE TABLE IF NOT EXISTS staff_vacations (
                id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                branch TEXT,
                role_snapshot TEXT,
                rank_snapshot INTEGER,
                start_at TEXT NOT NULL,
                end_at TEXT NOT NULL,
                original_end_at TEXT,
                reason TEXT,
                status TEXT NOT NULL,
                requested_by INTEGER,
                approved_by INTEGER,
                approved_by_role_key TEXT,
                ended_by INTEGER,
                ended_at TEXT,
                end_kind TEXT,
                extensions_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sv_user_status
                ON staff_vacations(guild_id, user_id, status);
            CREATE INDEX IF NOT EXISTS idx_sv_end
                ON staff_vacations(status, end_at);

            CREATE TABLE IF NOT EXISTS staff_probations (
                id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                branch TEXT,
                role_key TEXT,
                days INTEGER NOT NULL,
                start_at TEXT NOT NULL,
                end_at TEXT NOT NULL,
                reason TEXT,
                status TEXT NOT NULL,
                started_by INTEGER,
                started_by_role_key TEXT,
                ended_by INTEGER,
                ended_at TEXT,
                end_kind TEXT,
                source TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sp_user_status
                ON staff_probations(guild_id, user_id, status);
            CREATE INDEX IF NOT EXISTS idx_sp_end
                ON staff_probations(status, end_at);

            CREATE TABLE IF NOT EXISTS staff_requests (
                id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                requester_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                branch TEXT,
                role_key TEXT,
                reason TEXT,
                status TEXT NOT NULL,
                decided_by INTEGER,
                decided_by_role_key TEXT,
                decided_at TEXT,
                actor_role_key TEXT,
                actor_branch TEXT,
                created_at TEXT NOT NULL,
                meta TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sreq_status
                ON staff_requests(guild_id, status);

            CREATE TABLE IF NOT EXISTS staff_transfer_requests (
                id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                initiator_id INTEGER NOT NULL,
                initiator_branch TEXT,
                initiator_level TEXT,
                from_branch TEXT,
                from_role_id INTEGER,
                to_branch TEXT,
                to_role_id INTEGER,
                to_role_key TEXT,
                reason TEXT,
                status TEXT NOT NULL,
                branch_decided_by INTEGER,
                branch_decided_at TEXT,
                branch_decision_reason TEXT,
                target_decided_at TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                branch_message_id INTEGER,
                dm_message_id INTEGER,
                channel_message_id INTEGER,
                meta TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_str_target_status
                ON staff_transfer_requests(guild_id, target_id, status);
            CREATE INDEX IF NOT EXISTS idx_str_status_exp
                ON staff_transfer_requests(status, expires_at);
            ''')
            # безопасные миграции снимка исполнителя
            for table, cols in (
                ('staff_actions', (
                    ('actor_role_key', 'TEXT'),
                    ('actor_branch', 'TEXT'),
                )),
                ('staff_transfer_requests', (
                    ('actor_role_key', 'TEXT'),
                    ('actor_branch', 'TEXT'),
                    ('branch_decided_by_role_key', 'TEXT'),
                    ('target_decided_by_role_key', 'TEXT'),
                )),
                ('staff_consents', (
                    ('actor_role_key', 'TEXT'),
                    ('actor_branch', 'TEXT'),
                )),
            ):
                existing = {
                    r[1] for r in conn.execute(f'PRAGMA table_info({table})')
                }
                for col, typ in cols:
                    if col not in existing:
                        try:
                            conn.execute(
                                f'ALTER TABLE {table} ADD COLUMN {col} {typ}')
                        except Exception:
                            pass
            conn.commit()
        finally:
            conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.now(timezone.utc)


def new_action_id() -> str:
    return uuid.uuid4().hex


def claim_action_once(guild_id: int, target_id: int, action_id: str) -> bool:
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
    actor_role_key: str = '',
    actor_branch: str = '',
) -> str:
    ensure_tables()
    aid = action_id or new_action_id()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'INSERT OR REPLACE INTO staff_actions '
                '(id, guild_id, actor_id, target_id, action, branch, old_key, '
                'new_key, reason, source, ok, meta, created_at, '
                'actor_role_key, actor_branch) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    aid, int(guild_id), int(actor_id), int(target_id),
                    action, branch or '', old_key or '', new_key or '',
                    reason or '', source, 1 if ok else 0,
                    json.dumps(meta or {}, ensure_ascii=False), _now(),
                    actor_role_key or '', actor_branch or '',
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


def upsert_staff_profile(
    *,
    guild_id: int,
    user_id: int,
    branch: str = '',
    role_key: str = '',
    status: str = 'active',
    assigned_by: int | None = None,
) -> None:
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'INSERT INTO staff_profiles '
                '(guild_id, user_id, branch, role_key, status, assigned_by, updated_at) '
                'VALUES (?,?,?,?,?,?,?) '
                'ON CONFLICT(guild_id, user_id) DO UPDATE SET '
                'branch=excluded.branch, role_key=excluded.role_key, '
                'status=excluded.status, assigned_by=excluded.assigned_by, '
                'updated_at=excluded.updated_at',
                (
                    int(guild_id), int(user_id), branch or '', role_key or '',
                    status or 'active',
                    int(assigned_by) if assigned_by else None, _now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def get_staff_profile(guild_id: int, user_id: int) -> Optional[dict]:
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT * FROM staff_profiles WHERE guild_id=? AND user_id=?',
                (int(guild_id), int(user_id)),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def save_emoji_cache(guild_id: int, kind: str, key: str, emoji: str,
                     source: str = '') -> None:
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'INSERT OR REPLACE INTO staff_emoji_cache '
                '(guild_id, kind, key, emoji, source, updated_at) '
                'VALUES (?,?,?,?,?,?)',
                (int(guild_id), kind, key, emoji or '', source or '', _now()),
            )
            conn.commit()
        finally:
            conn.close()


def get_emoji_cache(guild_id: int, kind: str, key: str) -> Optional[str]:
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT emoji FROM staff_emoji_cache '
                'WHERE guild_id=? AND kind=? AND key=?',
                (int(guild_id), kind, key),
            ).fetchone()
            return row['emoji'] if row else None
        finally:
            conn.close()


# ── consents ──────────────────────────────────────────────────────────

def create_consent(
    *,
    guild_id: int,
    target_id: int,
    initiator_id: int,
    action: str,
    from_branch: str = '',
    from_role_id: int = 0,
    to_branch: str = '',
    to_role_id: int = 0,
    to_role_key: str = '',
    reason: str = '',
    expire_hours: int = 48,
    meta: dict | None = None,
) -> Optional[dict]:
    """Создаёт pending-согласие. Одновременно у target только один pending."""
    ensure_tables()
    cid = new_action_id()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=max(1, int(expire_hours)))
    with _LOCK:
        conn = _conn()
        try:
            pending = conn.execute(
                'SELECT id FROM staff_consents '
                'WHERE guild_id=? AND target_id=? AND status=?',
                (int(guild_id), int(target_id), 'pending'),
            ).fetchone()
            if pending:
                return None
            conn.execute(
                'INSERT INTO staff_consents '
                '(id, guild_id, target_id, initiator_id, action, from_branch, '
                'from_role_id, to_branch, to_role_id, to_role_key, reason, status, '
                'created_at, expires_at, decided_at, dm_message_id, '
                'channel_message_id, decline_reason, meta) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,?)',
                (
                    cid, int(guild_id), int(target_id), int(initiator_id),
                    action, from_branch or '', int(from_role_id or 0),
                    to_branch or '', int(to_role_id or 0), to_role_key or '',
                    reason or '', 'pending', now.isoformat(),
                    expires.isoformat(),
                    json.dumps(meta or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
            return get_consent(cid)
        finally:
            conn.close()


def get_consent(consent_id: str) -> Optional[dict]:
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT * FROM staff_consents WHERE id=?', (consent_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d['meta'] = json.loads(d.get('meta') or '{}')
            except Exception:
                d['meta'] = {}
            return d
        finally:
            conn.close()


def update_consent(consent_id: str, **fields) -> Optional[dict]:
    ensure_tables()
    allowed = {
        'status', 'decided_at', 'dm_message_id', 'channel_message_id',
        'decline_reason', 'meta',
    }
    sets = []
    vals = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == 'meta' and isinstance(v, dict):
            v = json.dumps(v, ensure_ascii=False)
        sets.append(f'{k}=?')
        vals.append(v)
    if not sets:
        return get_consent(consent_id)
    vals.append(consent_id)
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                f'UPDATE staff_consents SET {", ".join(sets)} WHERE id=?',
                vals,
            )
            conn.commit()
        finally:
            conn.close()
    return get_consent(consent_id)


def claim_consent_decision(consent_id: str, new_status: str) -> Optional[dict]:
    """Атомарно: только из pending → new_status. Иначе None."""
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            cur = conn.execute(
                'UPDATE staff_consents SET status=?, decided_at=? '
                'WHERE id=? AND status=?',
                (new_status, _now(), consent_id, 'pending'),
            )
            conn.commit()
            if cur.rowcount != 1:
                return None
        finally:
            conn.close()
    return get_consent(consent_id)


def list_consents(
    guild_id: int,
    *,
    status: str | None = None,
    limit: int = 50,
) -> List[dict]:
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            if status:
                rows = conn.execute(
                    'SELECT * FROM staff_consents WHERE guild_id=? AND status=? '
                    'ORDER BY created_at DESC LIMIT ?',
                    (int(guild_id), status, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT * FROM staff_consents WHERE guild_id=? '
                    'ORDER BY created_at DESC LIMIT ?',
                    (int(guild_id), int(limit)),
                ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                try:
                    d['meta'] = json.loads(d.get('meta') or '{}')
                except Exception:
                    d['meta'] = {}
                out.append(d)
            return out
        finally:
            conn.close()


def expire_due_consents() -> List[dict]:
    """Пометить просроченные pending → expired. Вернуть затронутые."""
    ensure_tables()
    now = _now()
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                'SELECT * FROM staff_consents '
                'WHERE status=? AND expires_at<=?',
                ('pending', now),
            ).fetchall()
            ids = [r['id'] for r in rows]
            if ids:
                conn.executemany(
                    'UPDATE staff_consents SET status=?, decided_at=? WHERE id=?',
                    [('expired', now, i) for i in ids],
                )
                conn.commit()
            out = []
            for r in rows:
                d = dict(r)
                d['status'] = 'expired'
                d['decided_at'] = now
                out.append(d)
            return out
        finally:
            conn.close()


def pending_consent_for(guild_id: int, target_id: int) -> Optional[dict]:
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT * FROM staff_consents '
                'WHERE guild_id=? AND target_id=? AND status=? '
                'ORDER BY created_at DESC LIMIT 1',
                (int(guild_id), int(target_id), 'pending'),
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d['meta'] = json.loads(d.get('meta') or '{}')
            except Exception:
                d['meta'] = {}
            return d
        finally:
            conn.close()


# ── vacations ─────────────────────────────────────────────────────────

def create_vacation(
    *,
    guild_id: int,
    user_id: int,
    branch: str,
    role_snapshot: list | dict,
    rank_snapshot: int = 0,
    start_at: str,
    end_at: str,
    reason: str = '',
    status: str = 'active',
    requested_by: int = 0,
    approved_by: int = 0,
    approved_by_role_key: str = '',
) -> dict:
    ensure_tables()
    vid = new_action_id()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'INSERT INTO staff_vacations '
                '(id, guild_id, user_id, branch, role_snapshot, rank_snapshot, '
                'start_at, end_at, original_end_at, reason, status, '
                'requested_by, approved_by, approved_by_role_key, '
                'ended_by, ended_at, end_kind, extensions_count, created_at) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    vid, int(guild_id), int(user_id), branch or '',
                    json.dumps(role_snapshot or [], ensure_ascii=False),
                    int(rank_snapshot or 0), start_at, end_at, end_at,
                    reason or '', status,
                    int(requested_by or 0) or None,
                    int(approved_by or 0) or None,
                    approved_by_role_key or '',
                    None, None, None, 0, _now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    return get_vacation(vid) or {'id': vid}


def get_vacation(vacation_id: str) -> Optional[dict]:
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT * FROM staff_vacations WHERE id=?', (vacation_id,)
            ).fetchone()
            return _vac_row(row) if row else None
        finally:
            conn.close()


def _vac_row(row) -> dict:
    d = dict(row)
    try:
        d['role_snapshot'] = json.loads(d.get('role_snapshot') or '[]')
    except Exception:
        d['role_snapshot'] = []
    return d


def active_vacation_for(guild_id: int, user_id: int) -> Optional[dict]:
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT * FROM staff_vacations '
                'WHERE guild_id=? AND user_id=? AND status=? '
                'ORDER BY start_at DESC LIMIT 1',
                (int(guild_id), int(user_id), 'active'),
            ).fetchone()
            return _vac_row(row) if row else None
        finally:
            conn.close()


def pending_vacation_for(guild_id: int, user_id: int) -> Optional[dict]:
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT * FROM staff_vacations '
                'WHERE guild_id=? AND user_id=? AND status=? '
                'ORDER BY created_at DESC LIMIT 1',
                (int(guild_id), int(user_id), 'pending'),
            ).fetchone()
            return _vac_row(row) if row else None
        finally:
            conn.close()


def list_vacations(
    guild_id: int,
    *,
    status: str | None = None,
    limit: int = 50,
) -> List[dict]:
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            if status:
                rows = conn.execute(
                    'SELECT * FROM staff_vacations WHERE guild_id=? AND status=? '
                    'ORDER BY created_at DESC LIMIT ?',
                    (int(guild_id), status, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT * FROM staff_vacations WHERE guild_id=? '
                    'ORDER BY created_at DESC LIMIT ?',
                    (int(guild_id), int(limit)),
                ).fetchall()
            return [_vac_row(r) for r in rows]
        finally:
            conn.close()


def due_vacations(now_iso: str | None = None) -> List[dict]:
    ensure_tables()
    now = now_iso or _now()
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                'SELECT * FROM staff_vacations '
                'WHERE status=? AND end_at<=?',
                ('active', now),
            ).fetchall()
            return [_vac_row(r) for r in rows]
        finally:
            conn.close()


def update_vacation(vacation_id: str, **fields) -> Optional[dict]:
    ensure_tables()
    allowed = {
        'status', 'end_at', 'ended_by', 'ended_at', 'end_kind',
        'extensions_count', 'approved_by', 'approved_by_role_key',
        'reason', 'role_snapshot',
    }
    sets = []
    vals = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == 'role_snapshot' and not isinstance(v, str):
            v = json.dumps(v or [], ensure_ascii=False)
        sets.append(f'{k}=?')
        vals.append(v)
    if not sets:
        return get_vacation(vacation_id)
    vals.append(vacation_id)
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                f'UPDATE staff_vacations SET {", ".join(sets)} WHERE id=?',
                vals,
            )
            conn.commit()
        finally:
            conn.close()
    return get_vacation(vacation_id)


def vacation_days_used_year(guild_id: int, user_id: int,
                            year: int | None = None) -> int:
    """Сумма дней активных/завершённых отпусков в календарном году."""
    ensure_tables()
    y = year or datetime.now(timezone.utc).year
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                'SELECT start_at, end_at, original_end_at, status '
                'FROM staff_vacations '
                'WHERE guild_id=? AND user_id=? AND status IN (?,?,?)',
                (int(guild_id), int(user_id), 'active', 'ended', 'cancelled'),
            ).fetchall()
        finally:
            conn.close()
    total = 0
    for r in rows:
        try:
            s = datetime.fromisoformat(r['start_at'])
            e = datetime.fromisoformat(r['end_at'] or r['original_end_at'])
            if s.year != y and e.year != y:
                continue
            days = max(0, int((e - s).total_seconds() // 86400))
            total += days
        except Exception:
            continue
    return total


def list_actions_filtered(
    guild_id: int,
    *,
    target_id: int | None = None,
    action: str | None = None,
    branch: str | None = None,
    status_ok: bool | None = None,
    since_iso: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> List[dict]:
    ensure_tables()
    clauses = ['guild_id=?']
    args: list = [int(guild_id)]
    if target_id:
        clauses.append('target_id=?')
        args.append(int(target_id))
    if action:
        clauses.append('action=?')
        args.append(action)
    if branch:
        clauses.append('branch=?')
        args.append(branch)
    if status_ok is not None:
        clauses.append('ok=?')
        args.append(1 if status_ok else 0)
    if since_iso:
        clauses.append('created_at>=?')
        args.append(since_iso)
    args.extend([int(limit), int(offset)])
    sql = (
        'SELECT * FROM staff_actions WHERE ' + ' AND '.join(clauses)
        + ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    )
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(sql, args).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── probations ────────────────────────────────────────────────────────

def create_probation(
    *,
    guild_id: int,
    user_id: int,
    branch: str = '',
    role_key: str = '',
    days: int = 0,
    start_at: str,
    end_at: str,
    reason: str = '',
    status: str = 'active',
    started_by: int = 0,
    started_by_role_key: str = '',
    source: str = 'manual',
) -> dict:
    ensure_tables()
    pid = new_action_id()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                'INSERT INTO staff_probations '
                '(id, guild_id, user_id, branch, role_key, days, start_at, end_at, '
                'reason, status, started_by, started_by_role_key, ended_by, '
                'ended_at, end_kind, source, created_at) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    pid, int(guild_id), int(user_id), branch or '', role_key or '',
                    int(days), start_at, end_at, reason or '', status,
                    int(started_by or 0) or None, started_by_role_key or '',
                    None, None, None, source or 'manual', _now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    return get_probation(pid) or {'id': pid}


def get_probation(probation_id: str) -> Optional[dict]:
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT * FROM staff_probations WHERE id=?', (probation_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def active_probation_for(guild_id: int, user_id: int) -> Optional[dict]:
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT * FROM staff_probations '
                'WHERE guild_id=? AND user_id=? AND status=? '
                'ORDER BY start_at DESC LIMIT 1',
                (int(guild_id), int(user_id), 'active'),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def due_probations(now_iso: str | None = None) -> List[dict]:
    ensure_tables()
    now = now_iso or _now()
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                'SELECT * FROM staff_probations '
                'WHERE status=? AND end_at<=?',
                ('active', now),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def update_probation(probation_id: str, **fields) -> Optional[dict]:
    ensure_tables()
    allowed = {
        'status', 'end_at', 'ended_by', 'ended_at', 'end_kind', 'reason', 'days',
    }
    sets, vals = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        sets.append(f'{k}=?')
        vals.append(v)
    if not sets:
        return get_probation(probation_id)
    vals.append(probation_id)
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                f'UPDATE staff_probations SET {", ".join(sets)} WHERE id=?',
                vals,
            )
            conn.commit()
        finally:
            conn.close()
    return get_probation(probation_id)
