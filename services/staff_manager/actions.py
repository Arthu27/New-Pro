# -*- coding: utf-8 -*-
"""Атомарная смена стафф-ролей + синк кэша/варнов."""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Set

from logger import get_logger
from services.staff_manager.acl import (
    ActorContext, TargetContext, can_manage_staff, resolve_actor, resolve_target,
)
from services.staff_manager.config import get_config, get_index
from services.staff_manager.store import (
    claim_action_once, new_action_id, record_action,
)

_log = get_logger('staff_manager.actions')
_TARGET_LOCKS: dict[int, asyncio.Lock] = {}
_LOCK_GUARD = threading.Lock()


def _target_lock(target_id: int) -> asyncio.Lock:
    with _LOCK_GUARD:
        lock = _TARGET_LOCKS.get(int(target_id))
        if lock is None:
            lock = asyncio.Lock()
            _TARGET_LOCKS[int(target_id)] = lock
        return lock


@dataclass
class StaffChangeResult:
    ok: bool
    reason: str = ''
    action_id: str = ''
    added: List[int] = field(default_factory=list)
    removed: List[int] = field(default_factory=list)
    alert_multi: bool = False


def _role_id_for(branch: str, key: str) -> int:
    idx = get_index() or {}
    return int((idx.get('by_branch_key') or {}).get((branch, key), 0) or 0)


def _ladder_roles_in_branch(member_role_ids: Set[int], branch: str) -> List[int]:
    idx = get_index() or {}
    by_role = idx.get('by_role') or {}
    out = []
    for rid in member_role_ids:
        info = by_role.get(int(rid))
        if info and info.get('branch') == branch:
            out.append(int(rid))
    return out


async def apply_staff_change(
    *,
    guild,
    actor_member,
    target_member,
    action: str,
    new_role_key: str | None = None,
    new_branch: str | None = None,
    reason: str = '',
    action_id: str | None = None,
    source: str = 'bot',
) -> StaffChangeResult:
    """Валидация → lock → Discord roles → verify → history → cache → warn sync."""
    cfg = get_config()
    if not cfg:
        return StaffChangeResult(False, 'Staff Manager не запущен (конфиг)')

    actor = resolve_actor(
        actor_member.id,
        [r.id for r in getattr(actor_member, 'roles', []) or []],
    )
    target = resolve_target(
        target_member.id,
        [r.id for r in getattr(target_member, 'roles', []) or []],
    )

    ok, why = can_manage_staff(
        actor, target, action,
        new_role_key=new_role_key,
        new_branch=new_branch,
    )
    alert_multi = why == 'ALERT_MULTI_BRANCH'
    if not ok:
        return StaffChangeResult(False, why)

    aid = action_id or new_action_id()
    if not claim_action_once(guild.id, target_member.id, aid):
        return StaffChangeResult(False, 'Действие уже выполняется (двойной клик)')

    branch = new_branch or target.primary_branch
    if action == 'assign' and not branch:
        if len(actor.responsible_branches) == 1:
            branch = next(iter(actor.responsible_branches))
        elif new_branch:
            branch = new_branch

    add_ids: List[int] = []
    remove_ids: List[int] = []
    old_key = target.primary_key or ''
    new_key = new_role_key or ''

    if action in ('assign', 'promote', 'demote'):
        if not branch or not new_role_key:
            return StaffChangeResult(False, 'Нет ветки или роли')
        new_rid = _role_id_for(branch, new_role_key)
        if not new_rid:
            return StaffChangeResult(False, 'role_id не найден в конфиге')
        # снять старые роли лестницы этой ветки
        current = {r.id for r in getattr(target_member, 'roles', []) or []}
        for rid in _ladder_roles_in_branch(current, branch):
            if rid != new_rid:
                remove_ids.append(rid)
        if new_rid not in current:
            add_ids.append(new_rid)
        # common staff role
        common = int(cfg.get('common_staff_role_id') or 0)
        if common and common not in current:
            add_ids.append(common)

    elif action == 'remove':
        branch = target.primary_branch
        current = {r.id for r in getattr(target_member, 'roles', []) or []}
        if branch:
            remove_ids.extend(_ladder_roles_in_branch(current, branch))
        # если больше нет лестничных ролей — снять common staff
        idx = get_index() or {}
        by_role = idx.get('by_role') or {}
        still = [
            rid for rid in current
            if rid in by_role and rid not in remove_ids
        ]
        common = int(cfg.get('common_staff_role_id') or 0)
        if common and not still and common in current:
            remove_ids.append(common)
        new_key = ''

    elif action == 'transfer':
        if not new_branch or not new_role_key:
            return StaffChangeResult(False, 'Нужны ветка и роль')
        current = {r.id for r in getattr(target_member, 'roles', []) or []}
        # снять ВСЕ лестничные роли всех веток
        idx = get_index() or {}
        by_role = idx.get('by_role') or {}
        for rid in list(current):
            if rid in by_role:
                remove_ids.append(rid)
        new_rid = _role_id_for(new_branch, new_role_key)
        if not new_rid:
            return StaffChangeResult(False, 'role_id не найден')
        add_ids.append(new_rid)
        common = int(cfg.get('common_staff_role_id') or 0)
        if common and common not in current:
            add_ids.append(common)
        branch = new_branch

    elif action in ('probation', 'vacation', 'history', 'request'):
        # без смены Discord-ролей — только запись
        record_action(
            guild_id=guild.id, actor_id=actor.user_id,
            target_id=target.user_id, action=action, branch=branch or '',
            old_key=old_key, new_key=new_key, reason=reason,
            source=source, ok=True, action_id=aid,
            meta={'alert_multi': alert_multi},
        )
        return StaffChangeResult(True, '', action_id=aid, alert_multi=alert_multi)

    # Discord hierarchy check
    bot_member = guild.me
    if bot_member is None:
        return StaffChangeResult(False, 'Бот не на сервере')
    top = bot_member.top_role
    for rid in add_ids + remove_ids:
        role = guild.get_role(rid)
        if role is None:
            return StaffChangeResult(False, f'Роль {rid} не найдена на сервере')
        if role >= top:
            return StaffChangeResult(
                False,
                f'Роль бота ниже «{role.name}» — подними роль бота в настройках')

    lock = _target_lock(target_member.id)
    async with lock:
        added_roles = [guild.get_role(r) for r in add_ids if guild.get_role(r)]
        removed_roles = [guild.get_role(r) for r in remove_ids if guild.get_role(r)]
        try:
            if removed_roles:
                await target_member.remove_roles(
                    *removed_roles, reason=f'staff:{action} {reason}'[:500])
            if added_roles:
                await target_member.add_roles(
                    *added_roles, reason=f'staff:{action} {reason}'[:500])
        except Exception as ex:
            _log.warning('apply_staff_change discord: %s', ex)
            record_action(
                guild_id=guild.id, actor_id=actor.user_id,
                target_id=target.user_id, action=action, branch=branch or '',
                old_key=old_key, new_key=new_key, reason=reason,
                source=source, ok=False, action_id=aid,
                meta={'error': str(ex)},
            )
            return StaffChangeResult(False, f'Discord: {ex}', action_id=aid)

        # verify
        try:
            fresh = await guild.fetch_member(target_member.id)
        except Exception:
            fresh = guild.get_member(target_member.id) or target_member
        have = {r.id for r in getattr(fresh, 'roles', []) or []}
        for rid in add_ids:
            if rid not in have:
                record_action(
                    guild_id=guild.id, actor_id=actor.user_id,
                    target_id=target.user_id, action=action, branch=branch or '',
                    old_key=old_key, new_key=new_key, reason=reason,
                    source=source, ok=False, action_id=aid,
                    meta={'error': 'not_applied', 'role': rid},
                )
                return StaffChangeResult(
                    False, 'Роль не применилась (права/иерархия)', action_id=aid)

        record_action(
            guild_id=guild.id, actor_id=actor.user_id,
            target_id=target.user_id, action=action, branch=branch or '',
            old_key=old_key, new_key=new_key, reason=reason,
            source=source, ok=True, action_id=aid,
            meta={'alert_multi': alert_multi, 'add': add_ids, 'remove': remove_ids},
        )

        # members_cache + warn role sync (non-blocking best-effort)
        try:
            from services import members_cache as MC
            MC.upsert_member(fresh)
        except Exception as ex:
            _log.debug('members_cache upsert: %s', ex)
        try:
            from services.warn_role import sync_warn_role
            await sync_warn_role(fresh)
        except Exception as ex:
            _log.debug('sync_warn_role: %s', ex)

        return StaffChangeResult(
            True, '', action_id=aid,
            added=add_ids, removed=remove_ids, alert_multi=alert_multi,
        )
