# -*- coding: utf-8 -*-
"""Отпуск: снимок ролей, старт/конец, лимиты, автовозврат."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from logger import get_logger
from services.staff_manager.acl import get_staff_info, resolve_actor, resolve_target
from services.staff_manager.bundles import all_bundle_role_ids, format_role_label
from services.staff_manager.config import get_config, get_index
from services.staff_manager.store import (
    active_vacation_for, create_vacation, due_vacations, new_action_id,
    pending_vacation_for, update_vacation, vacation_days_used_year,
)

_log = get_logger('staff_manager.vacation')


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_role_snapshot(member) -> Tuple[List[dict], int, str, str]:
    """Список снятых стафф-ролей + rank/branch/key."""
    cfg = get_config() or {}
    idx = get_index() or {}
    info = get_staff_info(member)
    rids = {r.id for r in getattr(member, 'roles', []) or []}
    staff_ids = set()
    staff_ids |= set((idx.get('by_role') or {}).keys())
    staff_ids |= set((idx.get('by_entry') or {}).keys())
    staff_ids |= set((idx.get('responsible_of') or {}).keys())
    staff_ids |= all_bundle_role_ids(cfg)
    for rid in (cfg.get('hidden_admin_role_ids') or []):
        if int(rid or 0):
            staff_ids.add(int(rid))
    for rid in (cfg.get('staff_power_role_ids') or []):
        if int(rid or 0):
            staff_ids.add(int(rid))
    for ids in (cfg.get('rank_extra_roles') or {}).values():
        for rid in ids or []:
            if int(rid or 0):
                staff_ids.add(int(rid))
    common = int(cfg.get('common_staff_role_id') or 0)
    if common:
        staff_ids.add(common)
    never = {int(x) for x in (cfg.get('never_strip_role_ids') or []) if int(x or 0)}
    never |= {
        int(x) for x in (cfg.get('manual_only_role_ids') or []) if int(x or 0)
    }
    snap = []
    by_role = idx.get('by_role') or {}
    for rid in sorted(staff_ids & rids - never):
        meta = by_role.get(rid) or {}
        snap.append({
            'id': rid,
            'key': meta.get('key') or '',
            'branch': meta.get('branch') or info.get('primary_branch') or '',
        })
    return (
        snap,
        int(info.get('max_rank') or 0),
        info.get('primary_branch') or '',
        info.get('primary_key') or '',
    )


def check_vacation_limits(
    *,
    guild_id: int,
    user_id: int,
    days: int,
    for_self: bool,
    is_admin: bool,
) -> Tuple[bool, List[str]]:
    cfg = get_config() or {}
    missing: List[str] = []
    max_self = int(cfg.get('vacation_max_days_self') or 30)
    max_admin = int(cfg.get('vacation_max_days_by_admin') or 90)
    max_year = int(cfg.get('vacation_max_days_per_year') or 60)
    cooldown = int(cfg.get('vacation_cooldown_days') or 14)

    if for_self and days > max_self:
        missing.append(f'Слишком длинный отпуск для себя (макс. {max_self} дн.)')
    if not for_self and days > max_admin:
        missing.append(f'Слишком длинный отпуск (макс. {max_admin} дн.)')
    if not is_admin and for_self and days > max_self:
        pass  # already

    used = vacation_days_used_year(guild_id, user_id)
    if used + days > max_year:
        missing.append(
            f'Годовой лимит отпуска: осталось {max(0, max_year - used)} дн.')

    active = active_vacation_for(guild_id, user_id)
    if active:
        missing.append('Уже в отпуске')
    pending = pending_vacation_for(guild_id, user_id)
    if pending:
        missing.append('Уже есть заявка на отпуск')

    # cooldown: last ended vacation
    from services.staff_manager.store import list_vacations
    past = list_vacations(guild_id, status='ended', limit=5)
    mine = [v for v in past if int(v.get('user_id') or 0) == int(user_id)]
    if mine and cooldown > 0 and not is_admin:
        try:
            ended = datetime.fromisoformat(
                mine[0].get('ended_at') or mine[0].get('end_at'))
            if ended.tzinfo is None:
                ended = ended.replace(tzinfo=timezone.utc)
            left = cooldown - int((_now() - ended).total_seconds() // 86400)
            if left > 0:
                missing.append(f'Кулдаун после отпуска: осталось {left} дн.')
        except Exception:
            pass

    return (not missing), missing


def needs_approval(days: int, for_self: bool) -> bool:
    cfg = get_config() or {}
    auto = int(cfg.get('vacation_auto_approve_up_to_days') or 7)
    return bool(for_self and days > auto)


async def start_vacation(
    *,
    guild,
    actor_member,
    target_member,
    days: int,
    reason: str = '',
    force_approve: bool = False,
    source: str = 'bot',
) -> Tuple[bool, str, Optional[dict]]:
    """Старт отпуска через apply_staff_change(action=vacation)."""
    from services.staff_manager.actions import apply_staff_change

    cfg = get_config() or {}
    # vacation_role_id опционален: статус в БД; роль — визуальный маркер

    for_self = int(actor_member.id) == int(target_member.id)
    actor = resolve_actor(
        actor_member.id, [r.id for r in actor_member.roles or []])
    is_admin = bool(actor.is_owner or actor.is_staff_admin)

    ok, missing = check_vacation_limits(
        guild_id=guild.id, user_id=target_member.id, days=days,
        for_self=for_self, is_admin=is_admin,
    )
    if not ok:
        return False, '; '.join(missing), None

    snap, rank, branch, key = build_role_snapshot(target_member)
    start = _now()
    end = start + timedelta(days=int(days))
    approve_now = force_approve or not needs_approval(days, for_self) or is_admin

    if not approve_now:
        vac = create_vacation(
            guild_id=guild.id, user_id=target_member.id, branch=branch,
            role_snapshot={
                'roles': snap, 'role_key': key, 'rank': rank,
            },
            rank_snapshot=rank,
            start_at=start.isoformat(), end_at=end.isoformat(),
            reason=reason, status='pending',
            requested_by=actor_member.id,
        )
        return True, 'pending', vac

    result = await apply_staff_change(
        guild=guild, actor_member=actor_member, target_member=target_member,
        action='vacation', reason=reason, source=source,
        skip_acl=for_self or is_admin,
        new_branch=branch, new_role_key=key,
    )
    if not result.ok:
        return False, result.reason, None

    vac = create_vacation(
        guild_id=guild.id, user_id=target_member.id, branch=branch,
        role_snapshot={
            'roles': snap, 'role_key': key, 'rank': rank,
            'removed_ids': result.removed,
        },
        rank_snapshot=rank,
        start_at=start.isoformat(), end_at=end.isoformat(),
        reason=reason, status='active',
        requested_by=actor_member.id,
        approved_by=actor_member.id,
        approved_by_role_key=actor.primary_key or '',
    )
    return True, 'active', vac


async def end_vacation(
    *,
    guild,
    actor_member,
    target_member,
    vacation: dict | None = None,
    end_kind: str = 'early',
    reason: str = '',
    source: str = 'bot',
) -> Tuple[bool, str, List[str]]:
    """Завершить отпуск: снять vacation + восстановить из снимка."""
    from services.staff_manager.actions import apply_staff_change

    vac = vacation or active_vacation_for(guild.id, target_member.id)
    if not vac:
        return False, 'Нет активного отпуска', []

    snap = vac.get('role_snapshot') or {}
    if isinstance(snap, list):
        roles = snap
        role_key = ''
        branch = vac.get('branch') or ''
    else:
        roles = snap.get('roles') or []
        role_key = snap.get('role_key') or ''
        branch = vac.get('branch') or snap.get('branch') or ''

    # 1) снять роль отпуска
    r1 = await apply_staff_change(
        guild=guild, actor_member=actor_member, target_member=target_member,
        action='vacation_end', reason=reason or f'end:{end_kind}',
        source=source, skip_acl=True,
        new_branch=branch, new_role_key=role_key,
    )
    if not r1.ok:
        update_vacation(vac['id'], status='failed')
        return False, r1.reason, []

    alerts: List[str] = []
    # 2) восстановить основную роль через assign (атомарно с бандлом)
    if role_key and branch:
        try:
            fresh = await guild.fetch_member(target_member.id)
        except Exception:
            fresh = target_member
        r2 = await apply_staff_change(
            guild=guild, actor_member=actor_member, target_member=fresh,
            action='assign', new_role_key=role_key, new_branch=branch,
            reason=reason or f'vacation_restore:{end_kind}',
            source=source, skip_acl=True,
        )
        if not r2.ok:
            alerts.append(r2.reason)
            update_vacation(
                vac['id'], status='failed', end_kind=end_kind,
                ended_by=actor_member.id, ended_at=_now().isoformat())
            return False, r2.reason, alerts
    else:
        # частичное: роли из снимка по id
        missing = []
        for item in roles:
            rid = int(item.get('id') or 0)
            if not rid or guild.get_role(rid) is None:
                missing.append(str(rid))
        if missing:
            alerts.append('Роли из снимка недоступны: ' + ', '.join(missing))
        update_vacation(
            vac['id'],
            status='failed' if missing else 'ended',
            end_kind=end_kind,
            ended_by=actor_member.id,
            ended_at=_now().isoformat(),
        )
        return (not missing), (
            'partial' if missing else 'ok'), alerts

    update_vacation(
        vac['id'], status='ended', end_kind=end_kind,
        ended_by=actor_member.id, ended_at=_now().isoformat(),
    )
    return True, 'ok', alerts


async def process_due_vacations(bot) -> int:
    """БД-задача: завершить просроченные отпуска."""
    due = due_vacations()
    n = 0
    for vac in due:
        guild = bot.get_guild(int(vac['guild_id']))
        if not guild:
            continue
        try:
            member = await guild.fetch_member(int(vac['user_id']))
        except Exception:
            # человек не на сервере — статус сохраняем, пометим при join
            continue
        me = guild.me
        if me is None:
            continue
        ok, why, alerts = await end_vacation(
            guild=guild, actor_member=me, target_member=member,
            vacation=vac, end_kind='auto', reason='auto_end',
        )
        if alerts:
            _log.warning('vacation end alerts %s: %s', vac.get('id'), alerts)
        if ok:
            n += 1
        else:
            _log.error('vacation auto end failed %s: %s', vac.get('id'), why)
    return n


def vacation_display(vac: dict, cfg: dict | None = None) -> dict:
    cfg = cfg or get_config() or {}
    snap = vac.get('role_snapshot') or {}
    if isinstance(snap, list):
        role_key = ''
    else:
        role_key = snap.get('role_key') or ''
    branch = vac.get('branch') or ''
    b = (cfg.get('branches') or {}).get(branch) or {}
    try:
        end = datetime.fromisoformat(vac.get('end_at'))
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        left = max(0, int((end - _now()).total_seconds() // 86400))
    except Exception:
        left = 0
    return {
        'id': vac.get('id'),
        'status': vac.get('status'),
        'branch': branch,
        'branch_label': b.get('label') or branch,
        'role_key': role_key,
        'role_label': format_role_label(role_key) if role_key else '—',
        'start_at': vac.get('start_at'),
        'end_at': vac.get('end_at'),
        'days_left': left,
        'reason': vac.get('reason') or '',
    }
