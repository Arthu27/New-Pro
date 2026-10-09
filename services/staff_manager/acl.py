# -*- coding: utf-8 -*-
"""Единая матрица прав Staff Manager.

can_manage_staff(actor, target, action, new_role_key=None) -> (ok, reason)
get_allowed_actions(actor, target) -> dict

Жёсткие инварианты (не из конфига):
  - protected (Admin) — только owner / staff_admin
  - изоляция веток для ответственных
  - ранг: нельзя выдавать/трогать >= своего ранга (кроме глобальных)
  - себе нельзя
  - мульти-ветка у цели → только staff_admin/owner + алерт-флаг
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from services.staff_manager.config import (
    get_config, get_index, ladder_by_key, is_enabled,
)

Action = str  # assign|promote|demote|remove|transfer|probation|vacation|history|request


@dataclass
class ActorContext:
    user_id: int
    role_ids: Set[int] = field(default_factory=set)
    is_owner: bool = False
    is_staff_admin: bool = False
    # responsible branches (keys)
    responsible_branches: Set[str] = field(default_factory=set)
    # ladder placement(s) — обычно одна
    placements: List[dict] = field(default_factory=list)  # {branch,key,rank,...}
    # highest rank among placements (0 if none)
    max_rank: int = 0
    # branch ladder key of highest placement
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


def _placements_from_roles(role_ids: Set[int]) -> List[dict]:
    """Уникальные роли ветки якорят ветку; общие (Master/Curator/Admin) —
    цепляются только к уже найденным веткам, иначе ко всем своим branches."""
    idx = get_index() or {}
    by_role = idx.get('by_role') or {}
    unique: List[dict] = []
    shared: List[dict] = []
    for rid in role_ids:
        info = by_role.get(int(rid))
        if not info:
            continue
        if info.get('shared'):
            shared.append(dict(info))
        else:
            unique.append(dict(info))
    branches = {p['branch'] for p in unique}
    out: List[dict] = list(unique)
    for s in shared:
        attach = list(branches) if branches else list(s.get('branches') or [])
        for b in attach:
            out.append({
                **s,
                'branch': b,
                'label': s.get('label') or b,
            })
    seen = set()
    uniq = []
    for p in out:
        k = (p['branch'], p['key'])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    return uniq


def resolve_actor(user_id: int, role_ids) -> ActorContext:
    cfg = get_config() or {}
    rids = {int(x) for x in (role_ids or []) if int(x or 0)}
    owner_ids = {int(x) for x in (cfg.get('owner_ids') or [])}
    staff_admin = int(cfg.get('staff_admin_role_id') or 0)
    idx = get_index() or {}
    resp_of = idx.get('responsible_of') or {}

    is_owner = int(user_id) in owner_ids
    is_sa = bool(staff_admin and staff_admin in rids)
    placements = _placements_from_roles(rids)
    responsible = {resp_of[rid] for rid in rids if rid in resp_of}
    max_rank = max((p['rank'] for p in placements), default=0)
    primary = max(placements, key=lambda p: p['rank']) if placements else None
    return ActorContext(
        user_id=int(user_id),
        role_ids=rids,
        is_owner=is_owner,
        is_staff_admin=is_sa,
        responsible_branches=responsible,
        placements=placements,
        max_rank=max_rank,
        primary_branch=(primary or {}).get('branch'),
        primary_key=(primary or {}).get('key'),
    )


def resolve_target(user_id: int, role_ids) -> TargetContext:
    cfg = get_config() or {}
    rids = {int(x) for x in (role_ids or []) if int(x or 0)}
    owner_ids = {int(x) for x in (cfg.get('owner_ids') or [])}
    staff_admin = int(cfg.get('staff_admin_role_id') or 0)
    placements = _placements_from_roles(rids)
    branches = {p['branch'] for p in placements}
    max_rank = max((p['rank'] for p in placements), default=0)
    primary = max(placements, key=lambda p: p['rank']) if placements else None
    return TargetContext(
        user_id=int(user_id),
        role_ids=rids,
        placements=placements,
        branches=branches,
        max_rank=max_rank,
        primary_branch=(primary or {}).get('branch'),
        primary_key=(primary or {}).get('key'),
        multi_branch=len(branches) > 1,
        is_owner=int(user_id) in owner_ids,
        is_staff_admin=staff_admin in rids,
    )


def _is_global(actor: ActorContext) -> bool:
    return bool(actor.is_owner or actor.is_staff_admin)


def _role_protected(key: str) -> bool:
    item = ladder_by_key(key)
    return bool(item and item.get('protected'))


def _role_rank(key: str) -> int:
    item = ladder_by_key(key)
    return int(item['rank']) if item else 0


def _actor_manage_keys(actor: ActorContext, branch: str) -> Set[str]:
    """Какие ключи лестницы актёр может ставить в ветке (без protected-инварианта)."""
    cfg = get_config() or {}
    if _is_global(actor):
        return {x['key'] for x in (cfg.get('ladder') or [])}

    keys: Set[str] = set()
    if branch in actor.responsible_branches:
        keys |= set(cfg.get('responsible_can_manage') or [])

    # branch Admin optional rights
    if (actor.primary_branch == branch and actor.primary_key == 'admin'):
        keys |= set(cfg.get('branch_admin_can_manage') or [])

    # curator optional (default empty)
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
    """Единая проверка. action: assign|promote|demote|remove|transfer|
    probation|vacation|history|request.
    """
    if not is_enabled() and action not in ('history',):
        # history can be read-only even if misconfigured? No — require enabled
        return False, 'Staff Manager не запущен (конфиг)'

    action = (action or '').strip().lower()
    if new_role_key == 'assistent':
        new_role_key = 'assistant'

    # 5. себе нельзя
    if int(actor.user_id) == int(target.user_id):
        if action != 'history':
            return False, 'Нельзя изменить самого себя'

    # history — почти всем, кто видит цель в своей зоне
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

    # request (заявка) — куратор/ассистент/мастер без manage-прав
    if action == 'request':
        cfg = get_config() or {}
        if not cfg.get('allow_promotion_requests', True):
            return False, 'Заявки выключены'
        if _is_global(actor) or actor.responsible_branches:
            return False, 'Вам доступно прямое управление'
        if not actor.placements:
            return False, 'Нет стафф-роли'
        return True, ''

    # probation / vacation — как manage в своей зоне, без смены ранга
    soft = action in ('probation', 'vacation')

    # 11-ish: staff admin cannot touch owner / other staff admin
    if target.is_owner and not actor.is_owner:
        return False, 'Владельца трогает только владелец'
    if target.is_staff_admin and not actor.is_owner:
        if not (actor.is_owner):
            return False, 'Стафф админа трогает только владелец'

    # transfer — only global
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

    # 6. multi-branch target
    alert_needed = False
    if target.multi_branch:
        if not _is_global(actor):
            return False, 'У человека роли нескольких веток — только Стафф админ'
        alert_needed = True  # caller may log

    # determine working branch
    branch = new_branch or target.primary_branch
    if action == 'assign' and not branch:
        # assign to empty person — need new_branch from caller context
        if new_branch:
            branch = new_branch
        elif len(actor.responsible_branches) == 1:
            branch = next(iter(actor.responsible_branches))
        elif _is_global(actor) and new_branch:
            branch = new_branch
        else:
            return False, 'Укажите ветку для назначения'

    if action in ('promote', 'demote', 'remove', 'probation', 'vacation'):
        if not target.placements and action != 'assign':
            if action == 'remove':
                return False, 'У человека нет стафф-роли'
            return False, 'Человек не в стаффе'

    # global actors: almost everything
    if _is_global(actor):
        if new_role_key:
            if not ladder_by_key(new_role_key):
                return False, 'Неизвестная роль'
        # still cannot violate self (done) / owner rules (done)
        return True, ('' if not alert_needed else 'ALERT_MULTI_BRANCH')

    # --- branch-level actors ---
    if not actor.responsible_branches and not soft:
        # check optional curator/admin manage lists
        manage_keys = set()
        if actor.primary_branch:
            manage_keys = _actor_manage_keys(actor, actor.primary_branch)
        if not manage_keys:
            return False, 'Нет прав управлять ролями'

    # isolation: only own branch
    own = actor.responsible_branches or (
        {actor.primary_branch} if actor.primary_branch else set())
    if not own:
        return False, 'Нет прав управлять ролями'

    if branch and branch not in own:
        return False, 'Это другая ветка'
    if target.primary_branch and target.primary_branch not in own:
        if target.placements:  # has staff elsewhere
            return False, 'Это другая ветка'

    # remove / promote / demote / assign
    if action == 'remove':
        # cannot remove protected unless global (already handled)
        if target.primary_key and _role_protected(target.primary_key):
            return False, 'Роль Admin выдаёт только Стафф админ'
        # cannot touch equal/higher rank
        if target.max_rank and actor.max_rank and target.max_rank >= actor.max_rank:
            # responsible may not have ladder rank — treat responsible as above curator
            if branch not in actor.responsible_branches:
                return False, 'Нельзя изменить человека с рангом ≥ вашего'
        if branch in actor.responsible_branches:
            # responsible can remove keys in responsible_can_manage
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
                # responsible can set probation on non-admin; admin target blocked
                return False, 'Роль Admin выдаёт только Стафф админ'
        return True, ''

    if action in ('assign', 'promote', 'demote'):
        if not new_role_key:
            return False, 'Не указана роль'
        if not ladder_by_key(new_role_key):
            return False, 'Неизвестная роль'
        # 1. protected
        if _role_protected(new_role_key):
            return False, 'Роль Admin выдаёт только Стафф админ'
        if target.primary_key and _role_protected(target.primary_key) and action in ('demote', 'promote'):
            return False, 'Роль Admin выдаёт только Стафф админ'

        allowed_keys = _actor_manage_keys(actor, branch or '')
        if new_role_key not in allowed_keys:
            return False, 'Нет прав на эту роль'

        # 3. cannot grant rank >= actor rank (if actor has ladder rank in branch)
        # Responsible without ladder placement: allowed keys already limited by config
        new_rank = _role_rank(new_role_key)
        if actor.max_rank and branch == actor.primary_branch and branch not in actor.responsible_branches:
            if new_rank >= actor.max_rank:
                return False, 'Нельзя выдать роль выше или равную вашей'

        # 4. cannot act on equal/higher target (unless responsible)
        if target.max_rank and branch not in actor.responsible_branches:
            if target.max_rank >= actor.max_rank and actor.max_rank:
                return False, 'Нельзя изменить человека с рангом ≥ вашего'

        if action == 'promote' and target.max_rank and new_rank <= target.max_rank:
            return False, 'Новая роль не выше текущей'
        if action == 'demote' and target.max_rank and new_rank >= target.max_rank:
            return False, 'Новая роль не ниже текущей'
        if action == 'assign' and target.placements:
            # already staff — use promote/transfer
            if target.primary_branch == branch:
                return False, 'Уже в этой ветке — используйте повысить/понизить'
            return False, 'Это другая ветка'

        return True, ''

    return False, 'Неизвестное действие'


def get_allowed_actions(actor: ActorContext, target: TargetContext) -> Dict[str, Any]:
    """Что показать в меню: actions[], roles[{key,name,rank}], branches[], can_request."""
    cfg = get_config() or {}
    actions: List[str] = []
    roles: List[dict] = []
    branches: List[dict] = []

    for act in ('assign', 'promote', 'demote', 'remove', 'transfer',
                'probation', 'vacation', 'history', 'request'):
        ok, _ = can_manage_staff(actor, target, act, new_role_key=None)
        # transfer/assign need more context — probe with dummy later
        if act in ('assign', 'promote', 'demote'):
            continue
        if act == 'transfer':
            if _is_global(actor):
                actions.append('transfer')
            continue
        if ok:
            actions.append(act)

    # roles for assign/promote/demote
    candidate_branches = []
    if _is_global(actor):
        candidate_branches = list((cfg.get('branches') or {}).keys())
    else:
        candidate_branches = list(actor.responsible_branches or [])
        if not candidate_branches and actor.primary_branch:
            candidate_branches = [actor.primary_branch]

    role_keys_ok: Set[str] = set()
    for b in candidate_branches:
        # pick action type based on target state
        if not target.placements:
            act = 'assign'
        elif target.max_rank:
            act = 'promote'  # probe both
        else:
            act = 'assign'
        for item in cfg.get('ladder') or []:
            key = item['key']
            for probe in ('assign', 'promote', 'demote'):
                ok, _ = can_manage_staff(
                    actor, target, probe, new_role_key=key, new_branch=b)
                if ok:
                    role_keys_ok.add(key)
                    break

    # which high-level actions available
    if not target.placements:
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
            # never show protected to non-global
            if item.get('protected') and not _is_global(actor):
                continue
            roles.append({
                'key': item['key'],
                'name': item['name'],
                'rank': item['rank'],
                'emoji': item.get('emoji') or '',
                'protected': bool(item.get('protected')),
            })

    if 'transfer' in actions or _is_global(actor):
        for bkey, b in (cfg.get('branches') or {}).items():
            branches.append({
                'key': bkey,
                'label': b.get('label') or bkey,
                'color': b.get('color'),
            })

    can_request = False
    ok, _ = can_manage_staff(actor, target, 'request')
    if ok:
        can_request = True

    # unique preserve order
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
            set(actions_u) <= {'history', 'request'} and can_request
            and 'assign' not in actions_u and 'promote' not in actions_u
        ),
    }
