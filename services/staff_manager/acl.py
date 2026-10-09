# -*- coding: utf-8 -*-
"""Единая матрица прав Staff Manager.

can_manage_staff(actor, target, action, new_role_key=None) -> (ok, reason)
get_allowed_actions(actor, target) -> dict
get_staff_info(member_or_roles) -> dict  — всегда из текущих ролей Discord.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from services.staff_manager.config import (
    get_config, get_index, ladder_by_key, is_enabled, role_emoji, branch_emoji,
)

Action = str


@dataclass
class ActorContext:
    user_id: int
    role_ids: Set[int] = field(default_factory=set)
    is_owner: bool = False
    is_staff_admin: bool = False
    responsible_branches: Set[str] = field(default_factory=set)
    placements: List[dict] = field(default_factory=list)
    max_rank: int = 0
    primary_branch: Optional[str] = None
    primary_key: Optional[str] = None


@dataclass
class TargetContext:
    user_id: int
    role_ids: Set[int] = field(default_factory=set)
    placements: List[dict] = field(default_factory=list)
    branches: Set[str] = field(default_factory=set)
    max_rank: int = 0
    primary_branch: Optional[str] = None
    primary_key: Optional[str] = None
    multi_branch: bool = False
    is_owner: bool = False
    is_staff_admin: bool = False
    entry_roles: Set[int] = field(default_factory=set)
    ladder_role_ids: Set[int] = field(default_factory=set)
    responsible_roles: Set[int] = field(default_factory=set)
    extra_staff_roles: Set[int] = field(default_factory=set)
    on_vacation: bool = False


def _placements_from_roles(role_ids: Set[int]) -> Tuple[List[dict], Set[int], Set[int]]:
    """Ветки якорятся entry_role; shared ladder цепляется к найденным веткам."""
    idx = get_index() or {}
    by_role = idx.get('by_role') or {}
    by_entry = idx.get('by_entry') or {}

    entry_rids: Set[int] = set()
    branches: Set[str] = set()
    for rid in role_ids:
        b = by_entry.get(int(rid))
        if b:
            entry_rids.add(int(rid))
            branches.add(b)

    ladder_hits: List[dict] = []
    ladder_rids: Set[int] = set()
    for rid in role_ids:
        info = by_role.get(int(rid))
        if not info:
            continue
        ladder_rids.add(int(rid))
        ladder_hits.append(dict(info))

    out: List[dict] = []
    for s in ladder_hits:
        attach = list(branches) if branches else list(s.get('branches') or [])
        if not attach:
            # ladder без entry — всё ещё staff, ветка неизвестна
            out.append({**s, 'branch': s.get('branch'), 'orphan': True})
            continue
        for b in attach:
            out.append({
                **s,
                'branch': b,
                'label': ((get_config() or {}).get('branches') or {})
                .get(b, {}).get('label') or b,
            })

    # entry без ladder — всё равно в ветке (ожидает назначения)
    for rid in entry_rids:
        b = by_entry[rid]
        if not any(p.get('branch') == b for p in out):
            out.append({
                'branch': b,
                'key': '',
                'rank': 0,
                'name': 'entry',
                'protected': False,
                'label': ((get_config() or {}).get('branches') or {})
                .get(b, {}).get('label') or b,
                'shared': False,
                'branches': [b],
                'is_entry': True,
            })

    seen = set()
    uniq = []
    for p in out:
        k = (p.get('branch'), p.get('key') or '')
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    return uniq, entry_rids, ladder_rids


def resolve_actor(user_id: int, role_ids) -> ActorContext:
    cfg = get_config() or {}
    rids = {int(x) for x in (role_ids or []) if int(x or 0)}
    owner_ids = {int(x) for x in (cfg.get('owner_ids') or [])}
    staff_admin = int(cfg.get('staff_admin_role_id') or 0)
    idx = get_index() or {}
    resp_of = idx.get('responsible_of') or {}

    is_owner = int(user_id) in owner_ids
    is_sa = bool(staff_admin and staff_admin in rids)
    placements, _, _ = _placements_from_roles(rids)
    # только настоящие ladder-placements для ранга
    ladder_pl = [p for p in placements if p.get('key')]
    responsible = {resp_of[rid] for rid in rids if rid in resp_of}
    max_rank = max((p['rank'] for p in ladder_pl), default=0)
    primary = max(ladder_pl, key=lambda p: p['rank']) if ladder_pl else None
    if primary is None and placements:
        primary = placements[0]
    return ActorContext(
        user_id=int(user_id),
        role_ids=rids,
        is_owner=is_owner,
        is_staff_admin=is_sa,
        responsible_branches=responsible,
        placements=ladder_pl or placements,
        max_rank=max_rank,
        primary_branch=(primary or {}).get('branch'),
        primary_key=(primary or {}).get('key') or None,
    )


def resolve_target(user_id: int, role_ids) -> TargetContext:
    cfg = get_config() or {}
    rids = {int(x) for x in (role_ids or []) if int(x or 0)}
    owner_ids = {int(x) for x in (cfg.get('owner_ids') or [])}
    staff_admin = int(cfg.get('staff_admin_role_id') or 0)
    vacation = int(cfg.get('vacation_role_id') or 0)
    placements, entry_rids, ladder_rids = _placements_from_roles(rids)
    idx = get_index() or {}
    resp_of = idx.get('responsible_of') or {}
    responsible = {rid for rid in rids if rid in resp_of}
    # если есть только «отвечаю за» — ветка из него
    for rid in responsible:
        b = resp_of.get(rid)
        if b:
            placements = placements or [{
                'branch': b, 'key': '', 'rank': 0, 'name': 'responsible',
                'protected': False, 'label': b, 'is_entry': False,
            }]
    extra = set()
    for rid in (cfg.get('hidden_admin_role_ids') or []):
        if int(rid or 0) in rids:
            extra.add(int(rid))
    for rid in (cfg.get('staff_power_role_ids') or []):
        if int(rid or 0) in rids:
            extra.add(int(rid))
    if staff_admin and staff_admin in rids:
        extra.add(staff_admin)
    ladder_pl = [p for p in placements if p.get('key')]
    branches = {p['branch'] for p in placements if p.get('branch')}
    # ветки из responsible
    for rid in responsible:
        b = resp_of.get(rid)
        if b:
            branches.add(b)
    max_rank = max((p['rank'] for p in ladder_pl), default=0)
    primary = max(ladder_pl, key=lambda p: p['rank']) if ladder_pl else None
    if primary is None and placements:
        primary = placements[0]
    if primary is None and responsible:
        rid0 = next(iter(responsible))
        b = resp_of.get(rid0)
        primary = {'branch': b, 'key': ''}
    return TargetContext(
        user_id=int(user_id),
        role_ids=rids,
        placements=ladder_pl or placements,
        branches=branches,
        max_rank=max_rank,
        primary_branch=(primary or {}).get('branch'),
        primary_key=(primary or {}).get('key') or None,
        multi_branch=len(branches) > 1,
        is_owner=int(user_id) in owner_ids,
        is_staff_admin=staff_admin in rids,
        entry_roles=entry_rids,
        ladder_role_ids=ladder_rids,
        responsible_roles=responsible,
        extra_staff_roles=extra,
        on_vacation=bool(vacation and vacation in rids),
    )


def get_staff_info(member_or_id, role_ids=None, *, guild_id: int | None = None) -> dict:
    """Стафф = роли лестницы/entry/responsible ИЛИ активный отпуск в БД."""
    if role_ids is None:
        if hasattr(member_or_id, 'roles'):
            uid = int(member_or_id.id)
            role_ids = [r.id for r in (member_or_id.roles or [])]
            if guild_id is None and hasattr(member_or_id, 'guild'):
                guild_id = getattr(member_or_id.guild, 'id', None)
        else:
            uid = int(member_or_id)
            role_ids = []
    else:
        uid = int(member_or_id.id) if hasattr(member_or_id, 'id') else int(member_or_id)
        if guild_id is None and hasattr(member_or_id, 'guild'):
            guild_id = getattr(member_or_id.guild, 'id', None)
    t = resolve_target(uid, role_ids)
    cfg = get_config() or {}

    vac_info = None
    prob_info = None
    on_vac = bool(t.on_vacation)
    on_prob = False
    if guild_id:
        try:
            from services.staff_manager.store import (
                active_vacation_for, active_probation_for,
            )
            vac_info = active_vacation_for(int(guild_id), uid)
            if vac_info:
                on_vac = True
            prob_info = active_probation_for(int(guild_id), uid)
            if prob_info:
                on_prob = True
        except Exception:
            vac_info = None
            prob_info = None

    primary_branch = t.primary_branch
    primary_key = t.primary_key
    max_rank = t.max_rank
    if on_vac and vac_info:
        snap = vac_info.get('role_snapshot') or {}
        if isinstance(snap, dict):
            primary_key = primary_key or snap.get('role_key') or ''
            max_rank = max_rank or int(snap.get('rank') or vac_info.get('rank_snapshot') or 0)
        primary_branch = primary_branch or vac_info.get('branch') or ''

    branch_label = ''
    if primary_branch:
        branch_label = ((cfg.get('branches') or {}).get(primary_branch) or {}).get(
            'label') or primary_branch
    role_label = ''
    if primary_key:
        item = ladder_by_key(primary_key, cfg)
        role_label = (item or {}).get('name') or primary_key
    # Скрытая админ-оболочка / power-роли сами по себе ≠ staff для ростера.
    # Staff Admin и лестница/entry/responsible/отпуск — да.
    is_staff = bool(
        t.ladder_role_ids or t.entry_roles or t.responsible_roles
        or t.is_staff_admin or on_vac)
    return {
        'user_id': t.user_id,
        'is_staff': is_staff,
        'primary_branch': primary_branch,
        'primary_key': primary_key,
        'branch_label': branch_label,
        'role_label': role_label or (
            'в отпуске' if on_vac else (
                'ответственный' if t.responsible_roles else (
                    'Staff Admin' if t.is_staff_admin else (
                        'скрытая оболочка' if t.extra_staff_roles else 'участник')))),
        'role_emoji': role_emoji(primary_key or '', branch=primary_branch),
        'branch_emoji': branch_emoji(primary_branch or ''),
        'branches': sorted(t.branches or ({primary_branch} if primary_branch else set())),
        'multi_branch': t.multi_branch,
        'max_rank': max_rank,
        'on_vacation': on_vac,
        'vacation': vac_info,
        'on_probation': on_prob,
        'probation': prob_info,
        'ladder_role_ids': sorted(t.ladder_role_ids),
        'entry_role_ids': sorted(t.entry_roles),
        'responsible_role_ids': sorted(t.responsible_roles),
        'extra_staff_role_ids': sorted(t.extra_staff_roles),
        'placements': t.placements,
    }


def _is_global(actor: ActorContext) -> bool:
    return bool(actor.is_owner or actor.is_staff_admin)


def _role_protected(key: str) -> bool:
    item = ladder_by_key(key)
    return bool(item and item.get('protected'))


def _role_rank(key: str) -> int:
    item = ladder_by_key(key)
    return int(item['rank']) if item else 0


def _actor_manage_keys(actor: ActorContext, branch: str) -> Set[str]:
    cfg = get_config() or {}
    if _is_global(actor):
        return {x['key'] for x in (cfg.get('ladder') or [])}

    keys: Set[str] = set()
    if branch in actor.responsible_branches:
        keys |= set(cfg.get('responsible_can_manage') or [])

    if (actor.primary_branch == branch and actor.primary_key == 'admin'):
        keys |= set(cfg.get('branch_admin_can_manage') or [])

    if (actor.primary_branch == branch and actor.primary_key == 'curator'):
        keys |= set(cfg.get('curator_can_manage') or [])

    return keys


def can_manage_staff(
    actor: ActorContext,
    target: TargetContext,
    action: str,
    new_role_key: str | None = None,
    *,
    new_branch: str | None = None,
) -> Tuple[bool, str]:
    if not is_enabled() and action not in ('history',):
        return False, 'Staff Manager не запущен (конфиг)'

    action = (action or '').strip().lower()
    if new_role_key == 'assistent':
        new_role_key = 'assistant'

    if int(actor.user_id) == int(target.user_id):
        if action not in ('history', 'self_leave', 'vacation'):
            return False, 'Нельзя изменить самого себя'

    if action == 'self_leave':
        if int(actor.user_id) != int(target.user_id):
            return False, 'self_leave только для себя'
        if not (target.ladder_role_ids or target.entry_roles or target.on_vacation):
            return False, 'Вы не в стаффе'
        return True, ''

    # отпуск: любой стафф себе; другому — по правам ниже
    if action == 'vacation' and int(actor.user_id) == int(target.user_id):
        if not (target.ladder_role_ids or target.entry_roles
                or target.responsible_roles or target.extra_staff_roles):
            return False, 'Вы не в стаффе'
        if target.on_vacation:
            return False, 'Вы уже в отпуске'
        return True, ''

    if action == 'history':
        if _is_global(actor):
            return True, ''
        if target.multi_branch:
            return False, 'У человека роли нескольких веток — только Стафф админ'
        if actor.responsible_branches and target.primary_branch in actor.responsible_branches:
            return True, ''
        if actor.primary_branch and target.primary_branch == actor.primary_branch:
            return True, ''
        return False, 'Нет доступа к истории'

    if action == 'request':
        cfg = get_config() or {}
        if not cfg.get('allow_promotion_requests', True):
            return False, 'Заявки выключены'
        if _is_global(actor) or actor.responsible_branches:
            return False, 'Вам доступно прямое управление'
        if not actor.placements:
            return False, 'Нет стафф-роли'
        return True, ''

    soft = action in ('probation', 'vacation')

    if target.is_owner and not actor.is_owner:
        return False, 'Владельца трогает только владелец'
    if target.is_staff_admin and not actor.is_owner:
        return False, 'Стафф админа трогает только владелец'

    if action == 'transfer':
        if not _is_global(actor):
            return False, 'Перевод между ветками — только Стафф админ'
        if not new_branch:
            return False, 'Не указана новая ветка'
        cfg = get_config() or {}
        if new_branch not in (cfg.get('branches') or {}):
            return False, 'Неизвестная ветка'
        if new_role_key and _role_protected(new_role_key) and not _is_global(actor):
            return False, 'Роль Admin выдаёт только Стафф админ'
        return True, ''

    alert_needed = False
    if target.multi_branch:
        if not _is_global(actor):
            return False, 'У человека роли нескольких веток — только Стафф админ'
        alert_needed = True

    branch = new_branch or target.primary_branch
    if action == 'assign' and not branch:
        if new_branch:
            branch = new_branch
        elif len(actor.responsible_branches) == 1:
            branch = next(iter(actor.responsible_branches))
        elif _is_global(actor) and new_branch:
            branch = new_branch
        else:
            return False, 'Укажите ветку для назначения'

    has_staff = bool(
        target.ladder_role_ids or target.entry_roles or target.placements
        or target.responsible_roles or target.extra_staff_roles
        or target.on_vacation
    )
    if action in ('promote', 'demote', 'remove', 'probation', 'vacation'):
        if not has_staff and action != 'assign':
            if action == 'remove':
                return False, 'У человека нет стафф-роли'
            return False, 'Человек не в стаффе'

    # в отпуске: promote/demote/transfer/снятие роли недоступны
    # (кроме Стафф админ/владельца; remove допустимо и завершает отпуск)
    if target.on_vacation and action in ('promote', 'demote', 'transfer', 'assign'):
        if not _is_global(actor):
            return False, 'Человек в отпуске — сначала верните из отпуска'
        # глобальным разрешаем с предупреждением (caller показывает warn)

    if _is_global(actor):
        if new_role_key:
            if not ladder_by_key(new_role_key):
                return False, 'Неизвестная роль'
        return True, ('' if not alert_needed else 'ALERT_MULTI_BRANCH')

    if not actor.responsible_branches and not soft:
        manage_keys = set()
        if actor.primary_branch:
            manage_keys = _actor_manage_keys(actor, actor.primary_branch)
        if not manage_keys:
            return False, 'Нет прав управлять ролями'

    own = actor.responsible_branches or (
        {actor.primary_branch} if actor.primary_branch else set())
    if not own:
        return False, 'Нет прав управлять ролями'

    if branch and branch not in own:
        return False, 'Это другая ветка'
    if target.primary_branch and target.primary_branch not in own:
        if has_staff:
            return False, 'Это другая ветка'

    if action == 'remove':
        if target.primary_key and _role_protected(target.primary_key):
            return False, 'Роль Admin выдаёт только Стафф админ'
        if target.max_rank and actor.max_rank and target.max_rank >= actor.max_rank:
            if branch not in actor.responsible_branches:
                return False, 'Нельзя изменить человека с рангом ≥ вашего'
        if branch in actor.responsible_branches:
            cfg = get_config() or {}
            allowed = set(cfg.get('responsible_can_manage') or [])
            if target.primary_key and target.primary_key not in allowed:
                if _role_protected(target.primary_key or ''):
                    return False, 'Роль Admin выдаёт только Стафф админ'
                return False, 'Нельзя снять эту роль'
            return True, ''
        return False, 'Нет прав управлять ролями'

    if soft:
        if branch not in own:
            return False, 'Это другая ветка'
        if target.primary_key and _role_protected(target.primary_key):
            if branch not in actor.responsible_branches and not _is_global(actor):
                return False, 'Роль Admin выдаёт только Стафф админ'
        return True, ''

    if action in ('assign', 'promote', 'demote'):
        if not new_role_key:
            return False, 'Не указана роль'
        if not ladder_by_key(new_role_key):
            return False, 'Неизвестная роль'
        if _role_protected(new_role_key):
            return False, 'Роль Admin выдаёт только Стафф админ'
        if target.primary_key and _role_protected(target.primary_key) and action in (
                'demote', 'promote'):
            return False, 'Роль Admin выдаёт только Стафф админ'

        allowed_keys = _actor_manage_keys(actor, branch or '')
        if new_role_key not in allowed_keys:
            return False, 'Нет прав на эту роль'

        new_rank = _role_rank(new_role_key)
        if actor.max_rank and branch == actor.primary_branch and branch not in actor.responsible_branches:
            if new_rank >= actor.max_rank:
                return False, 'Нельзя выдать роль выше или равную вашей'

        if target.max_rank and branch not in actor.responsible_branches:
            if target.max_rank >= actor.max_rank and actor.max_rank:
                return False, 'Нельзя изменить человека с рангом ≥ вашего'

        if action == 'promote' and target.max_rank and new_rank <= target.max_rank:
            return False, 'Новая роль не выше текущей'
        if action == 'demote' and target.max_rank and new_rank >= target.max_rank:
            return False, 'Новая роль не ниже текущей'
        if action == 'assign' and has_staff:
            if target.primary_branch == branch:
                return False, 'Уже в этой ветке — используйте повысить/понизить'
            return False, 'Это другая ветка'

        return True, ''

    return False, 'Неизвестное действие'


def get_allowed_actions(actor: ActorContext, target: TargetContext) -> Dict[str, Any]:
    cfg = get_config() or {}
    actions: List[str] = []
    roles: List[dict] = []
    branches: List[dict] = []

    for act in ('assign', 'promote', 'demote', 'remove', 'transfer',
                'probation', 'vacation', 'history', 'request', 'self_leave'):
        ok, _ = can_manage_staff(actor, target, act, new_role_key=None)
        if act in ('assign', 'promote', 'demote'):
            continue
        if act == 'transfer':
            if _is_global(actor):
                actions.append('transfer')
            continue
        if ok:
            actions.append(act)

    candidate_branches = []
    if _is_global(actor):
        candidate_branches = list((cfg.get('branches') or {}).keys())
    else:
        candidate_branches = list(actor.responsible_branches or [])
        if not candidate_branches and actor.primary_branch:
            candidate_branches = [actor.primary_branch]

    role_keys_ok: Set[str] = set()
    for b in candidate_branches:
        for item in cfg.get('ladder') or []:
            key = item['key']
            for probe in ('assign', 'promote', 'demote'):
                ok, _ = can_manage_staff(
                    actor, target, probe, new_role_key=key, new_branch=b)
                if ok:
                    role_keys_ok.add(key)
                    break

    has_staff = bool(
        target.ladder_role_ids or target.entry_roles or target.placements
        or target.responsible_roles or target.extra_staff_roles
    )
    if not has_staff:
        for b in candidate_branches:
            for key in role_keys_ok:
                ok, _ = can_manage_staff(
                    actor, target, 'assign', new_role_key=key, new_branch=b)
                if ok:
                    actions.append('assign')
                    break
            if 'assign' in actions:
                break
    else:
        for key in role_keys_ok:
            ok, _ = can_manage_staff(actor, target, 'promote', new_role_key=key)
            if ok:
                actions.append('promote')
                break
        for key in role_keys_ok:
            ok, _ = can_manage_staff(actor, target, 'demote', new_role_key=key)
            if ok:
                actions.append('demote')
                break
        ok, _ = can_manage_staff(actor, target, 'remove')
        if ok and 'remove' not in actions:
            actions.append('remove')

    for item in cfg.get('ladder') or []:
        if item['key'] in role_keys_ok:
            if item.get('protected') and not _is_global(actor):
                continue
            roles.append({
                'key': item['key'],
                'name': item['name'],
                'rank': item['rank'],
                'emoji': role_emoji(item['key']) or item.get('emoji') or '',
                'protected': bool(item.get('protected')),
            })

    if 'transfer' in actions or _is_global(actor):
        for bkey, b in (cfg.get('branches') or {}).items():
            branches.append({
                'key': bkey,
                'label': b.get('label') or bkey,
                'color': b.get('color'),
                'emoji': branch_emoji(bkey),
            })

    can_request = False
    ok, _ = can_manage_staff(actor, target, 'request')
    if ok:
        can_request = True

    seen = set()
    actions_u = []
    for a in actions:
        if a not in seen:
            seen.add(a)
            actions_u.append(a)

    return {
        'actions': actions_u,
        'roles': roles,
        'branches': branches,
        'can_request': can_request,
        'is_global': _is_global(actor),
        'manage_ui': bool(actions_u) and not (
            set(actions_u) <= {'history', 'request', 'self_leave'} and can_request
            and 'assign' not in actions_u and 'promote' not in actions_u
        ),
    }
