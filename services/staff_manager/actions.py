# -*- coding: utf-8 -*-
"""Атомарная смена стафф-ролей + verify через fetch_member + откат."""
from __future__ import annotations

import asyncio
import traceback
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Set

from logger import get_logger
from services.staff_manager.acl import (
    can_manage_staff, resolve_actor, resolve_target, get_staff_info,
)
from services.staff_manager.bundles import (
    all_bundle_role_ids, compute_bundle_delta, get_role_bundle,
)
from services.staff_manager.config import get_config, get_index
from services.staff_manager.store import (
    claim_action_once, new_action_id, record_action, upsert_staff_profile,
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
    staff_info: dict = field(default_factory=dict)


def _role_id_for(branch: str, key: str) -> int:
    idx = get_index() or {}
    return int((idx.get('by_branch_key') or {}).get((branch, key), 0) or 0)


def _entry_id_for(branch: str) -> int:
    cfg = get_config() or {}
    b = (cfg.get('branches') or {}).get(branch) or {}
    return int(b.get('entry_role_id') or 0)


def _all_ladder_role_ids() -> Set[int]:
    idx = get_index() or {}
    return set((idx.get('by_role') or {}).keys())


def _all_entry_role_ids() -> Set[int]:
    idx = get_index() or {}
    return set((idx.get('by_entry') or {}).keys())


def _all_responsible_role_ids() -> Set[int]:
    idx = get_index() or {}
    return set((idx.get('responsible_of') or {}).keys())


def _never_strip_ids(cfg: dict) -> Set[int]:
    never = {int(x) for x in (cfg.get('never_strip_role_ids') or []) if int(x or 0)}
    # ☁️ и прочие manual_only — тоже не трогаем
    never |= {
        int(x) for x in (cfg.get('manual_only_role_ids') or []) if int(x or 0)
    }
    return never


def _norm_rank_key(key: str) -> str:
    key = (key or '').strip().lower()
    return 'assistant' if key == 'assistent' else key


def _rank_extra_role_ids(role_key: str, cfg: dict) -> Set[int]:
    """Доп. роли ступени: 🦋 только admin. Assistant/curator/master — пусто.

    При смене ступени чужие extras всё равно снимаются через
    _all_rank_extra_role_ids (бабочку с ассистента/куратора убираем).
    """
    never = _never_strip_ids(cfg)
    key = _norm_rank_key(role_key)
    # жёстко: ассистенту и куратору extras не выдаём, даже если в JSON остались
    if key in ('assistant', 'curator', 'master'):
        return set()
    mapping = cfg.get('rank_extra_roles') or {}
    out = {int(x) for x in (mapping.get(key) or []) if int(x or 0)}
    return out - never


def _all_rank_extra_role_ids(cfg: dict) -> Set[int]:
    """Все id из RANK_EXTRA_ROLES — чтобы снять чужие при смене ступени."""
    never = _never_strip_ids(cfg)
    out: Set[int] = set()
    for ids in (cfg.get('rank_extra_roles') or {}).values():
        for rid in ids or []:
            if int(rid or 0):
                out.add(int(rid))
    return out - never


def _apply_rank_extras(
    *,
    role_key: str,
    cfg: dict,
    current: Set[int],
    add_ids: List[int],
    remove_ids: List[int],
) -> None:
    """Выдать extras ступени, снять extras других ступеней. ☁️ не трогаем."""
    want = _rank_extra_role_ids(role_key, cfg)
    managed = _all_rank_extra_role_ids(cfg)
    for rid in managed:
        if rid in current and rid not in want:
            remove_ids.append(rid)
        if rid in want and rid not in current:
            add_ids.append(rid)
    # want может содержать id ещё не в managed (на всякий)
    for rid in want:
        if rid not in current and rid not in add_ids:
            add_ids.append(rid)


def _extra_strip_role_ids(cfg: dict) -> Set[int]:
    """Скрытые/rank-extras + legacy power + Staff Admin — снимать при remove.

    never_strip / manual_only (👑 🌺 ☁️) никогда не попадают в список.
    """
    never = _never_strip_ids(cfg)
    out = set(_all_rank_extra_role_ids(cfg))
    for rid in (cfg.get('hidden_admin_role_ids') or []):
        if int(rid or 0):
            out.add(int(rid))
    for rid in (cfg.get('staff_power_role_ids') or []):
        if int(rid or 0):
            out.add(int(rid))
    sa = int(cfg.get('staff_admin_role_id') or 0)
    if sa:
        out.add(sa)
    return out - never


def _hierarchy_block_reason(guild, role) -> Optional[str]:
    bot_member = guild.me
    if bot_member is None:
        return 'Бот не на сервере'
    if not bot_member.guild_permissions.manage_roles:
        return (
            'У бота нет права Manage Roles. '
            'Выдайте право «Управлять ролями» роли бота.'
        )
    if getattr(role, 'managed', False):
        return (
            f'Роль «{role.name}» управляемая (managed/бот/буст) — '
            f'Discord не позволяет её выдавать вручную.'
        )
    top = bot_member.top_role
    if role >= top:
        return (
            f'Роль бота ниже «{role.name}» (pos {role.position} ≥ '
            f'бот {top.position}). Поднимите роль бота выше в '
            f'Настройки сервера → Роли.'
        )
    return None


async def _safe_edit_roles(member, *, add, remove, reason: str):
    if remove:
        await member.remove_roles(*remove, reason=reason[:500])
    if add:
        await member.add_roles(*add, reason=reason[:500])


async def _rollback(member, *, added, removed, reason: str):
    """Откат: снять то что добавили, вернуть то что сняли."""
    try:
        if added:
            await member.remove_roles(*added, reason=f'rollback:{reason}'[:500])
        if removed:
            await member.add_roles(*removed, reason=f'rollback:{reason}'[:500])
    except Exception as ex:
        _log.error(
            'rollback failed target=%s: %s\n%s',
            getattr(member, 'id', '?'), ex, traceback.format_exc(),
        )


def _fail(
    *,
    guild_id, actor_id, target_id, action, branch, old_key, new_key,
    reason, source, aid, msg, meta=None, alert_multi=False,
    actor_role_key='', actor_branch='',
) -> StaffChangeResult:
    record_action(
        guild_id=guild_id, actor_id=actor_id, target_id=target_id,
        action=action, branch=branch or '', old_key=old_key, new_key=new_key,
        reason=reason, source=source, ok=False, action_id=aid,
        actor_role_key=actor_role_key, actor_branch=actor_branch,
        meta={**(meta or {}), 'error': msg},
    )
    return StaffChangeResult(False, msg, action_id=aid, alert_multi=alert_multi)


def _actor_snap(actor) -> tuple:
    return (actor.primary_key or '', actor.primary_branch or '')


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
    removal_kind: str | None = None,
    skip_acl: bool = False,
) -> StaffChangeResult:
    """Валидация → lock → Discord roles → fetch_member verify → history/cache.

    Успех ТОЛЬКО после проверки, что нужные роли реально на участнике.
    """
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

    alert_multi = False
    if not skip_acl:
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
    if action in ('assign', 'self_leave') and not branch:
        if len(actor.responsible_branches) == 1:
            branch = next(iter(actor.responsible_branches))
        elif new_branch:
            branch = new_branch

    add_ids: List[int] = []
    remove_ids: List[int] = []
    old_key = target.primary_key or ''
    new_key = new_role_key or ''
    current = {r.id for r in getattr(target_member, 'roles', []) or []}

    actor_rk, actor_br = _actor_snap(actor)

    if action in ('assign', 'promote', 'demote'):
        if not branch or not new_role_key:
            return _fail(
                guild_id=guild.id, actor_id=actor.user_id,
                target_id=target.user_id, action=action, branch=branch,
                old_key=old_key, new_key=new_key, reason=reason,
                source=source, aid=aid, msg='Нет ветки или роли',
                actor_role_key=actor_rk, actor_branch=actor_br,
            )
        new_rid = _role_id_for(branch, new_role_key)
        if not new_rid:
            return _fail(
                guild_id=guild.id, actor_id=actor.user_id,
                target_id=target.user_id, action=action, branch=branch,
                old_key=old_key, new_key=new_key, reason=reason,
                source=source, aid=aid,
                msg=f'role_id для {new_role_key}/{branch} не найден в конфиге',
                actor_role_key=actor_rk, actor_branch=actor_br,
            )
        # снять ВСЕ другие ladder-роли (общие)
        for rid in _all_ladder_role_ids():
            if rid in current and rid != new_rid:
                remove_ids.append(rid)
        if new_rid not in current:
            add_ids.append(new_rid)
        # entry роли: оставить только целевой ветки
        for rid in _all_entry_role_ids():
            if rid in current and rid != _entry_id_for(branch):
                remove_ids.append(rid)
        entry = _entry_id_for(branch)
        if entry and entry not in current:
            add_ids.append(entry)
        common = int(cfg.get('common_staff_role_id') or 0)
        if common and common not in current:
            add_ids.append(common)
        # ROLE_BUNDLES: доп. роли нового набора + снятие extras старого
        b_add, b_rem = compute_bundle_delta(
            old_key=old_key, new_key=new_role_key, branch=branch,
            current_role_ids=current, cfg=cfg,
        )
        add_ids.extend(b_add)
        remove_ids.extend(b_rem)
        # 🦋 только admin; assistant/curator — без extras (☁️ не трогаем)
        _apply_rank_extras(
            role_key=new_role_key, cfg=cfg, current=current,
            add_ids=add_ids, remove_ids=remove_ids)

    elif action in ('remove', 'self_leave'):
        branch = target.primary_branch or branch
        for rid in _all_ladder_role_ids():
            if rid in current:
                remove_ids.append(rid)
        for rid in _all_entry_role_ids():
            if rid in current:
                remove_ids.append(rid)
        # «Отвечаю за …» / «Отвечает за …»
        for rid in _all_responsible_role_ids():
            if rid in current:
                remove_ids.append(rid)
        # extras из любых бандлов
        for rid in all_bundle_role_ids(cfg):
            if rid in current:
                remove_ids.append(rid)
        # 4 скрытые админки + power-роли (🌂 ☁️) + Staff Admin
        for rid in _extra_strip_role_ids(cfg):
            if rid in current:
                remove_ids.append(rid)
        vac = int(cfg.get('vacation_role_id') or 0)
        if vac and vac in current:
            remove_ids.append(vac)
        common = int(cfg.get('common_staff_role_id') or 0)
        if common and common in current:
            remove_ids.append(common)
        new_key = ''
        action = 'remove' if action == 'self_leave' else action

    elif action == 'transfer':
        if not new_branch or not new_role_key:
            return _fail(
                guild_id=guild.id, actor_id=actor.user_id,
                target_id=target.user_id, action=action, branch=branch,
                old_key=old_key, new_key=new_key, reason=reason,
                source=source, aid=aid, msg='Нужны ветка и роль',
                actor_role_key=actor_rk, actor_branch=actor_br,
            )
        old_branch = target.primary_branch or branch
        for rid in _all_ladder_role_ids():
            if rid in current:
                remove_ids.append(rid)
        for rid in _all_entry_role_ids():
            if rid in current:
                remove_ids.append(rid)
        # при переводе «отвечаю за» старой ветки не оставляем
        for rid in _all_responsible_role_ids():
            if rid in current:
                remove_ids.append(rid)
        # снять extras старого бандла
        if old_key and old_branch:
            old_extras = get_role_bundle(old_key, old_branch, cfg).get('add_roles') or []
            for rid in old_extras:
                if int(rid) in current:
                    remove_ids.append(int(rid))
        new_rid = _role_id_for(new_branch, new_role_key)
        if not new_rid:
            return _fail(
                guild_id=guild.id, actor_id=actor.user_id,
                target_id=target.user_id, action=action, branch=new_branch,
                old_key=old_key, new_key=new_key, reason=reason,
                source=source, aid=aid, msg='role_id не найден',
                actor_role_key=actor_rk, actor_branch=actor_br,
            )
        add_ids.append(new_rid)
        entry = _entry_id_for(new_branch)
        if entry:
            add_ids.append(entry)
        common = int(cfg.get('common_staff_role_id') or 0)
        if common and common not in current:
            add_ids.append(common)
        b_add, b_rem = compute_bundle_delta(
            old_key='', new_key=new_role_key, branch=new_branch,
            current_role_ids=current, cfg=cfg,
        )
        add_ids.extend(b_add)
        remove_ids.extend(b_rem)
        _apply_rank_extras(
            role_key=new_role_key, cfg=cfg, current=current,
            add_ids=add_ids, remove_ids=remove_ids)
        branch = new_branch

    elif action == 'sync_bundle':
        # автосинк: довыдать недостающие роли текущего ROLE_BUNDLES
        key = target.primary_key or new_role_key or ''
        br = branch or target.primary_branch or ''
        if not key or not br:
            return _fail(
                guild_id=guild.id, actor_id=actor.user_id,
                target_id=target.user_id, action=action, branch=br,
                old_key=old_key, new_key=key, reason=reason,
                source=source, aid=aid, msg='Нет роли/ветки для синка',
                actor_role_key=actor_rk, actor_branch=actor_br,
            )
        new_key = key
        branch = br
        bundle = get_role_bundle(key, br, cfg)
        for rid in (bundle.get('add_roles') or []):
            rid = int(rid)
            if rid and rid not in current:
                add_ids.append(rid)
        # entry + common тоже, если вдруг нет
        entry = _entry_id_for(br)
        if entry and entry not in current:
            add_ids.append(entry)
        common = int(cfg.get('common_staff_role_id') or 0)
        if common and common not in current:
            add_ids.append(common)
        _apply_rank_extras(
            role_key=key, cfg=cfg, current=current,
            add_ids=add_ids, remove_ids=remove_ids)
        if not add_ids and not remove_ids:
            record_action(
                guild_id=guild.id, actor_id=actor.user_id,
                target_id=target.user_id, action=action, branch=br,
                old_key=old_key, new_key=key, reason=reason or 'already synced',
                source=source, ok=True, action_id=aid,
                actor_role_key=actor_rk, actor_branch=actor_br,
                meta={'note': 'nothing_to_add'},
            )
            return StaffChangeResult(True, '', action_id=aid, added=[], removed=[])

    elif action in ('probation', 'vacation', 'vacation_end', 'history', 'request'):
        if action == 'vacation':
            vac = int(cfg.get('vacation_role_id') or 0)
            # снять ВСЕ стафф-роли (роль отпуска опциональна — статус в БД)
            for rid in _all_ladder_role_ids():
                if rid in current:
                    remove_ids.append(rid)
            for rid in _all_entry_role_ids():
                if rid in current:
                    remove_ids.append(rid)
            for rid in _all_responsible_role_ids():
                if rid in current:
                    remove_ids.append(rid)
            for rid in all_bundle_role_ids(cfg):
                if rid in current:
                    remove_ids.append(rid)
            for rid in _extra_strip_role_ids(cfg):
                if rid in current:
                    remove_ids.append(rid)
            # common Staff — стафф-маркер, снимаем
            common = int(cfg.get('common_staff_role_id') or 0)
            if common and common in current:
                remove_ids.append(common)
            if vac and vac not in current:
                add_ids.append(vac)
            if not remove_ids and not add_ids:
                return _fail(
                    guild_id=guild.id, actor_id=actor.user_id,
                    target_id=target.user_id, action=action, branch=branch,
                    old_key=old_key, new_key=new_key, reason=reason,
                    source=source, aid=aid,
                    msg='Нечего снимать для отпуска',
                    actor_role_key=actor_rk, actor_branch=actor_br,
                )
        elif action == 'vacation_end':
            # снять роль отпуска; восстановление ladder — отдельный assign/promote
            vac = int(cfg.get('vacation_role_id') or 0)
            if vac and vac in current:
                remove_ids.append(vac)
            if not remove_ids and not add_ids:
                record_action(
                    guild_id=guild.id, actor_id=actor.user_id,
                    target_id=target.user_id, action=action, branch=branch or '',
                    old_key=old_key, new_key=new_key, reason=reason,
                    source=source, ok=True, action_id=aid,
                    actor_role_key=actor_rk, actor_branch=actor_br,
                    meta={'alert_multi': alert_multi},
                )
                return StaffChangeResult(True, '', action_id=aid, alert_multi=alert_multi)
        else:
            record_action(
                guild_id=guild.id, actor_id=actor.user_id,
                target_id=target.user_id, action=action, branch=branch or '',
                old_key=old_key, new_key=new_key, reason=reason,
                source=source, ok=True, action_id=aid,
                actor_role_key=actor_rk, actor_branch=actor_br,
                meta={'alert_multi': alert_multi, 'removal_kind': removal_kind},
            )
            return StaffChangeResult(True, '', action_id=aid, alert_multi=alert_multi)

    # dedupe preserve order
    def _uniq(xs):
        seen = set()
        out = []
        for x in xs:
            x = int(x)
            if x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    add_ids = _uniq(add_ids)
    never = {int(x) for x in (cfg.get('never_strip_role_ids') or []) if int(x or 0)}
    remove_ids = _uniq([
        r for r in remove_ids
        if r not in add_ids and int(r) not in never
    ])

    # hierarchy / managed / missing
    for rid in add_ids + remove_ids:
        role = guild.get_role(rid)
        if role is None:
            return _fail(
                guild_id=guild.id, actor_id=actor.user_id,
                target_id=target.user_id, action=action, branch=branch,
                old_key=old_key, new_key=new_key, reason=reason,
                source=source, aid=aid,
                msg=(
                    f'Роль {rid} не найдена на сервере (устаревший ID в конфиге). '
                    f'Обновите data/staff_manager.json.'
                ),
                actor_role_key=actor_rk, actor_branch=actor_br,
            )
        block = _hierarchy_block_reason(guild, role)
        if block:
            return _fail(
                guild_id=guild.id, actor_id=actor.user_id,
                target_id=target.user_id, action=action, branch=branch,
                old_key=old_key, new_key=new_key, reason=reason,
                source=source, aid=aid, msg=block,
                actor_role_key=actor_rk, actor_branch=actor_br,
            )

    lock = _target_lock(target_member.id)
    async with lock:
        added_roles = [guild.get_role(r) for r in add_ids]
        removed_roles = [guild.get_role(r) for r in remove_ids]
        if any(r is None for r in added_roles + removed_roles):
            return _fail(
                guild_id=guild.id, actor_id=actor.user_id,
                target_id=target.user_id, action=action, branch=branch,
                old_key=old_key, new_key=new_key, reason=reason,
                source=source, aid=aid, msg='Роль исчезла во время операции',
                actor_role_key=actor_rk, actor_branch=actor_br,
            )

        try:
            await _safe_edit_roles(
                target_member,
                add=added_roles,
                remove=removed_roles,
                reason=f'staff:{action} {reason}',
            )
        except Exception as ex:
            _log.error(
                'apply_staff_change discord target=%s action=%s: %s\n%s',
                target.user_id, action, ex, traceback.format_exc(),
            )
            msg = f'Discord отказал: {ex}'
            if '403' in str(ex) or 'Forbidden' in type(ex).__name__:
                msg = (
                    f'Discord Forbidden при смене ролей: {ex}. '
                    f'Проверьте иерархию и Manage Roles у бота.'
                )
            return _fail(
                guild_id=guild.id, actor_id=actor.user_id,
                target_id=target.user_id, action=action, branch=branch,
                old_key=old_key, new_key=new_key, reason=reason,
                source=source, aid=aid, msg=msg,
                meta={'traceback': traceback.format_exc()[-1500:]},
                actor_role_key=actor_rk, actor_branch=actor_br,
            )

        # VERIFY via fresh fetch
        try:
            fresh = await guild.fetch_member(target_member.id)
        except Exception as ex:
            _log.error(
                'fetch_member after change failed: %s\n%s',
                ex, traceback.format_exc(),
            )
            await _rollback(
                target_member, added=added_roles, removed=removed_roles,
                reason='verify_fetch_failed')
            return _fail(
                guild_id=guild.id, actor_id=actor.user_id,
                target_id=target.user_id, action=action, branch=branch,
                old_key=old_key, new_key=new_key, reason=reason,
                source=source, aid=aid,
                msg=f'Не удалось проверить роли после смены: {ex}',
                actor_role_key=actor_rk, actor_branch=actor_br,
            )

        have = {r.id for r in getattr(fresh, 'roles', []) or []}
        missing = [rid for rid in add_ids if rid not in have]
        leftover = [rid for rid in remove_ids if rid in have]

        # дабл-стафф: не больше одной ladder-роли и одной entry-роли
        # на отпуске ladder/entry сняты — не проверяем double
        if action not in ('vacation',):
            ladder_have = [rid for rid in _all_ladder_role_ids() if rid in have]
            entry_have = [rid for rid in _all_entry_role_ids() if rid in have]
            if len(ladder_have) > 1 or len(entry_have) > 1:
                await _rollback(
                    fresh, added=added_roles, removed=removed_roles,
                    reason='double_staff')
                msg = (
                    'Нельзя оставить две стафф-роли: после смены осталось '
                    f'{len(ladder_have)} ролей лестницы и {len(entry_have)} entry. '
                    'Откат выполнен.'
                )
                _log.error(
                    'double staff target=%s ladder=%s entry=%s',
                    target.user_id, ladder_have, entry_have,
                )
                return _fail(
                    guild_id=guild.id, actor_id=actor.user_id,
                    target_id=target.user_id, action=action, branch=branch,
                    old_key=old_key, new_key=new_key, reason=reason,
                    source=source, aid=aid, msg=msg,
                    meta={'ladder_have': ladder_have, 'entry_have': entry_have},
                    actor_role_key=actor_rk, actor_branch=actor_br,
                )

        if missing or leftover:
            await _rollback(
                fresh, added=added_roles, removed=removed_roles,
                reason='verify_mismatch')
            parts = []
            if missing:
                names = []
                for rid in missing:
                    r = guild.get_role(rid)
                    names.append(r.name if r else str(rid))
                parts.append('не выдались: ' + ', '.join(names))
            if leftover:
                names = []
                for rid in leftover:
                    r = guild.get_role(rid)
                    names.append(r.name if r else str(rid))
                parts.append('не снялись: ' + ', '.join(names))
            msg = (
                'Роли не применились по факту (' + '; '.join(parts) + '). '
                'Откат выполнен. Проверьте иерархию ролей бота.'
            )
            _log.error(
                'verify failed target=%s missing=%s leftover=%s',
                target.user_id, missing, leftover,
            )
            return _fail(
                guild_id=guild.id, actor_id=actor.user_id,
                target_id=target.user_id, action=action, branch=branch,
                old_key=old_key, new_key=new_key, reason=reason,
                source=source, aid=aid, msg=msg,
                meta={'missing': missing, 'leftover': leftover},
                actor_role_key=actor_rk, actor_branch=actor_br,
            )

        # SUCCESS — только теперь пишем БД / кэш / warn
        info = get_staff_info(fresh)
        status = 'removed' if action == 'remove' else (
            'vacation' if action == 'vacation' else 'active')
        record_action(
            guild_id=guild.id, actor_id=actor.user_id,
            target_id=target.user_id, action=action, branch=branch or '',
            old_key=old_key, new_key=new_key, reason=reason,
            source=source, ok=True, action_id=aid,
            actor_role_key=actor_rk, actor_branch=actor_br,
            meta={
                'alert_multi': alert_multi,
                'add': add_ids,
                'remove': remove_ids,
                'removal_kind': removal_kind,
                'staff_info': {
                    'primary_key': info.get('primary_key'),
                    'primary_branch': info.get('primary_branch'),
                },
            },
        )
        try:
            upsert_staff_profile(
                guild_id=guild.id,
                user_id=target.user_id,
                branch=info.get('primary_branch') or branch or '',
                role_key=info.get('primary_key') or (
                    old_key if action == 'vacation' else ''),
                status=status,
                assigned_by=actor.user_id,
            )
        except Exception as ex:
            _log.error('upsert_staff_profile: %s\n%s', ex, traceback.format_exc())

        try:
            from services import members_cache as MC
            MC.upsert_member(guild.id, fresh)
        except Exception as ex:
            _log.error('members_cache upsert: %s\n%s', ex, traceback.format_exc())

        try:
            from services.warn_role import sync_warn_role
            await sync_warn_role(fresh)
        except Exception as ex:
            _log.error('sync_warn_role: %s\n%s', ex, traceback.format_exc())

        return StaffChangeResult(
            True, '', action_id=aid,
            added=add_ids, removed=remove_ids, alert_multi=alert_multi,
            staff_info=info,
        )
