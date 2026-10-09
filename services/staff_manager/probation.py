# -*- coding: utf-8 -*-
"""Испытательный срок: старт/конец, пресеты, авто из ROLE_BUNDLES."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from logger import get_logger
from services.staff_manager.acl import get_staff_info, resolve_actor
from services.staff_manager.bundles import format_role_label, get_role_bundle
from services.staff_manager.config import get_config
from services.staff_manager.store import (
    active_probation_for, create_probation, due_probations,
    record_action, update_probation,
)

_log = get_logger('staff_manager.probation')


def _now() -> datetime:
    return datetime.now(timezone.utc)


def start_probation(
    *,
    guild_id: int,
    actor_member,
    target_member,
    days: int,
    reason: str = '',
    source: str = 'manual',
) -> Tuple[bool, str, Optional[dict]]:
    """Поставить испытательный. Роли не трогает — только статус/срок."""
    days = int(days or 0)
    if days < 1:
        return False, 'Укажите срок (дней)', None
    if days > 90:
        return False, 'Слишком длинный срок (макс. 90 дн.)', None

    info = get_staff_info(target_member)
    if not info.get('is_staff') or info.get('on_vacation'):
        return False, 'Человек не в стаффе или в отпуске', None

    existing = active_probation_for(guild_id, target_member.id)
    if existing:
        return False, 'Уже идёт испытательный срок', None

    actor = resolve_actor(
        actor_member.id,
        [r.id for r in getattr(actor_member, 'roles', []) or []],
    )
    start = _now()
    end = start + timedelta(days=days)
    row = create_probation(
        guild_id=guild_id,
        user_id=int(target_member.id),
        branch=info.get('primary_branch') or '',
        role_key=info.get('primary_key') or '',
        days=days,
        start_at=start.isoformat(),
        end_at=end.isoformat(),
        reason=reason or '',
        status='active',
        started_by=int(actor_member.id),
        started_by_role_key=actor.primary_key or '',
        source=source,
    )
    record_action(
        guild_id=guild_id,
        actor_id=int(actor_member.id),
        target_id=int(target_member.id),
        action='probation',
        branch=info.get('primary_branch') or '',
        old_key=info.get('primary_key') or '',
        new_key=info.get('primary_key') or '',
        reason=reason or f'{days} дн.',
        source=source,
        ok=True,
        actor_role_key=actor.primary_key or '',
        actor_branch=actor.primary_branch or '',
        meta={'days': days, 'end_at': end.isoformat(), 'probation_id': row.get('id')},
    )
    return True, 'ok', row


def end_probation(
    *,
    guild_id: int,
    actor_id: int,
    user_id: int,
    probation: dict | None = None,
    end_kind: str = 'early',
    reason: str = '',
) -> Tuple[bool, str]:
    row = probation or active_probation_for(guild_id, user_id)
    if not row:
        return False, 'Нет активного испытательного'
    update_probation(
        row['id'],
        status='ended',
        ended_by=int(actor_id),
        ended_at=_now().isoformat(),
        end_kind=end_kind,
    )
    record_action(
        guild_id=guild_id,
        actor_id=int(actor_id),
        target_id=int(user_id),
        action='probation',
        branch=row.get('branch') or '',
        old_key=row.get('role_key') or '',
        new_key=row.get('role_key') or '',
        reason=reason or f'end:{end_kind}',
        source='probation_end',
        ok=True,
        meta={'end_kind': end_kind, 'probation_id': row.get('id')},
    )
    return True, 'ok'


def maybe_start_after_promote(
    *,
    guild_id: int,
    actor_member,
    target_member,
    new_role_key: str,
    branch: str,
) -> Optional[dict]:
    """Если у новой роли probation_days > 0 — стартуем автоматически."""
    bundle = get_role_bundle(new_role_key, branch)
    days = int(bundle.get('probation_days') or 0)
    if days <= 0:
        return None
    ok, why, row = start_probation(
        guild_id=guild_id,
        actor_member=actor_member,
        target_member=target_member,
        days=days,
        reason=f'авто после назначения · {format_role_label(new_role_key, branch=branch)}',
        source='promote_auto',
    )
    if not ok:
        _log.info('probation auto skip: %s', why)
        return None
    return row


def process_due_probations() -> int:
    n = 0
    for row in due_probations():
        try:
            update_probation(
                row['id'],
                status='ended',
                ended_by=0,
                ended_at=_now().isoformat(),
                end_kind='auto',
            )
            n += 1
        except Exception as ex:
            _log.error('probation auto end %s: %s', row.get('id'), ex)
    return n


def probation_display(row: dict) -> dict:
    try:
        end = datetime.fromisoformat(row['end_at'])
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        left = max(0, int((end - _now()).total_seconds() // 86400))
    except Exception:
        left = 0
    return {
        'id': row.get('id'),
        'days': row.get('days'),
        'days_left': left,
        'end_at': row.get('end_at'),
        'start_at': row.get('start_at'),
        'role_key': row.get('role_key'),
        'branch': row.get('branch'),
        'reason': row.get('reason') or '',
        'status': row.get('status'),
    }
