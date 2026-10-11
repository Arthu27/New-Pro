# -*- coding: utf-8 -*-
"""Перевод между ветками: решение целевой ветки + согласие человека.

Стафф админ / владелец: только согласие человека (без шага ветки).
Остальные: pending_branch → pending_target → apply.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from services.staff_manager.acl import (
    ActorContext, TargetContext, _is_global, resolve_actor, resolve_target,
)
from services.staff_manager.config import get_config, get_index, ladder_by_key
from services.staff_manager.store import (
    ensure_tables, new_action_id, _conn, _LOCK, _now, get_consent,
    create_consent,
)


def can_decide_branch_transfer(
    actor: ActorContext,
    *,
    to_branch: str,
    requested_role_key: str,
) -> Tuple[bool, str]:
    """Симметрия по rank: same_or_higher в ЦЕЛЕВОЙ ветке, либо ответственный/глобальный."""
    if _is_global(actor):
        return True, ''
    if to_branch in actor.responsible_branches:
        return True, ''
    need = ladder_by_key(requested_role_key)
    if not need:
        return False, 'Неизвестная роль'
    need_rank = int(need['rank'])
    # актёр должен быть в целевой ветке с rank >= requested
    for p in actor.placements:
        if p.get('branch') == to_branch and int(p.get('rank') or 0) >= need_rank:
            return True, ''
    return False, 'Принять может только тот же уровень или выше в целевой ветке'


def create_transfer_request(
    *,
    guild_id: int,
    target_id: int,
    initiator_id: int,
    initiator_branch: str = '',
    initiator_level: str = '',
    from_branch: str = '',
    from_role_id: int = 0,
    to_branch: str = '',
    to_role_id: int = 0,
    to_role_key: str = '',
    reason: str = '',
    status: str = 'pending_branch',
    expire_hours: int = 72,
) -> Optional[dict]:
    ensure_tables()
    # один активный перевод на человека
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT id FROM staff_transfer_requests '
                'WHERE guild_id=? AND target_id=? AND status IN (?,?)',
                (int(guild_id), int(target_id),
                 'pending_branch', 'pending_target'),
            ).fetchone()
            if row:
                return None
            tid = new_action_id()
            now = datetime.now(timezone.utc)
            exp = now + timedelta(hours=max(1, int(expire_hours)))
            conn.execute(
                'INSERT INTO staff_transfer_requests '
                '(id, guild_id, target_id, initiator_id, initiator_branch, '
                'initiator_level, from_branch, from_role_id, to_branch, '
                'to_role_id, to_role_key, reason, status, created_at, expires_at) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    tid, int(guild_id), int(target_id), int(initiator_id),
                    initiator_branch or '', initiator_level or '',
                    from_branch or '', int(from_role_id or 0),
                    to_branch or '', int(to_role_id or 0), to_role_key or '',
                    reason or '', status, now.isoformat(), exp.isoformat(),
                ),
            )
            conn.commit()
            return get_transfer_request(tid)
        finally:
            conn.close()


def get_transfer_request(req_id: str) -> Optional[dict]:
    ensure_tables()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                'SELECT * FROM staff_transfer_requests WHERE id=?', (req_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def claim_transfer_status(req_id: str, from_status: str, to_status: str,
                          **fields) -> Optional[dict]:
    ensure_tables()
    allowed = {
        'branch_decided_by', 'branch_decided_at', 'branch_decision_reason',
        'target_decided_at', 'branch_message_id', 'dm_message_id',
        'channel_message_id', 'meta',
    }
    sets = ['status=?']
    vals: list = [to_status]
    for k, v in fields.items():
        if k not in allowed:
            continue
        sets.append(f'{k}=?')
        vals.append(v)
    vals.extend([req_id, from_status])
    with _LOCK:
        conn = _conn()
        try:
            cur = conn.execute(
                f'UPDATE staff_transfer_requests SET {", ".join(sets)} '
                f'WHERE id=? AND status=?',
                vals,
            )
            conn.commit()
            if cur.rowcount != 1:
                return None
        finally:
            conn.close()
    return get_transfer_request(req_id)


def expire_due_transfers() -> list:
    ensure_tables()
    now = _now()
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                'SELECT * FROM staff_transfer_requests '
                'WHERE status IN (?,?) AND expires_at<=?',
                ('pending_branch', 'pending_target', now),
            ).fetchall()
            for r in rows:
                conn.execute(
                    'UPDATE staff_transfer_requests SET status=? WHERE id=?',
                    ('expired', r['id']),
                )
            conn.commit()
            return [dict(r) for r in rows]
        finally:
            conn.close()
