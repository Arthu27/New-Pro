# -*- coding: utf-8 -*-
"""ROLE_BUNDLES: доп. роли при смене ступени + условия повышения."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from services.staff_manager.config import get_config, ladder_by_key, role_emoji


def _norm_key(key: str) -> str:
    key = (key or '').strip().lower()
    return 'assistant' if key == 'assistent' else key


def get_role_bundle(role_key: str, branch: str | None = None,
                    cfg: dict | None = None) -> dict:
    """Глобальный ROLE_BUNDLES + переопределение branches[x].role_bundles."""
    cfg = cfg or get_config() or {}
    key = _norm_key(role_key)
    base = dict((cfg.get('role_bundles') or {}).get(key) or {})
    add = list(base.get('add_roles') or [])
    remove = list(base.get('remove_roles') or [])
    requires = dict(base.get('requires') or {})
    probation_days = int(base.get('probation_days') or 0)
    announce = bool(base.get('announce', True))
    dm_guide = bool(base.get('dm_guide', True))

    if branch:
        b = (cfg.get('branches') or {}).get(branch) or {}
        ov = (b.get('role_bundles') or {}).get(key) or {}
        if ov:
            if 'add_roles' in ov:
                add = list(ov.get('add_roles') or [])
            if 'remove_roles' in ov:
                remove = list(ov.get('remove_roles') or [])
            if 'requires' in ov and isinstance(ov['requires'], dict):
                requires = {**requires, **ov['requires']}
            if 'probation_days' in ov:
                probation_days = int(ov.get('probation_days') or 0)
            if 'announce' in ov:
                announce = bool(ov['announce'])
            if 'dm_guide' in ov:
                dm_guide = bool(ov['dm_guide'])

    return {
        'add_roles': [int(x) for x in add if int(x or 0)],
        'remove_roles': [int(x) for x in remove if int(x or 0)],
        'requires': requires,
        'probation_days': probation_days,
        'announce': announce,
        'dm_guide': dm_guide,
    }


def all_bundle_role_ids(cfg: dict | None = None) -> Set[int]:
    cfg = cfg or get_config() or {}
    out: Set[int] = set()
    for key, b in (cfg.get('role_bundles') or {}).items():
        for rid in (b.get('add_roles') or []):
            if int(rid or 0):
                out.add(int(rid))
        for rid in (b.get('remove_roles') or []):
            if int(rid or 0):
                out.add(int(rid))
    for b in (cfg.get('branches') or {}).values():
        for bb in (b.get('role_bundles') or {}).values():
            for rid in (bb.get('add_roles') or []):
                if int(rid or 0):
                    out.add(int(rid))
            for rid in (bb.get('remove_roles') or []):
                if int(rid or 0):
                    out.add(int(rid))
    return out


def format_role_label(role_key: str, *, branch: str | None = None,
                      cfg: dict | None = None, with_emoji: bool = True) -> str:
    """«🦋 Assistent» — иконка всегда вместе с названием."""
    cfg = cfg or get_config() or {}
    key = _norm_key(role_key)
    item = ladder_by_key(key, cfg) or {}
    name = item.get('name') or (key.title() if key else '—')
    if not with_emoji:
        return name
    em = role_emoji(key, branch=branch, cfg=cfg) if branch else role_emoji(key, cfg=cfg)
    # branch-aware emoji via config helper if available
    try:
        from services.staff_manager.config import role_emoji as re2
        em = re2(key, cfg=cfg, branch=branch)
    except TypeError:
        em = role_emoji(key, cfg=cfg)
    em = em or item.get('emoji') or '•'
    return f'{em} {name}'


def format_actor_label(display_name: str, role_key: str | None = None,
                       *, branch: str | None = None,
                       emoji_override: str | None = None,
                       cfg: dict | None = None) -> str:
    """«🦋 Иван» — иконка роли исполнителя рядом с ником."""
    name = (display_name or '—').strip() or '—'
    if emoji_override:
        return f'{emoji_override} {name}'
    key = _norm_key(role_key or '')
    if not key:
        return f'• {name}'
    try:
        from services.staff_manager.config import role_emoji as re2
        em = re2(key, cfg=cfg, branch=branch) or '•'
    except TypeError:
        em = role_emoji(key, cfg=cfg) or '•'
    return f'{em} {name}'


def format_transition(old_key: str, new_key: str, *,
                      branch: str | None = None,
                      cfg: dict | None = None) -> str:
    """«🌂 Curator → 🦋 Assistent»."""
    if old_key and new_key:
        return (
            f'{format_role_label(old_key, branch=branch, cfg=cfg)} → '
            f'{format_role_label(new_key, branch=branch, cfg=cfg)}'
        )
    if new_key:
        return format_role_label(new_key, branch=branch, cfg=cfg)
    if old_key:
        return f'{format_role_label(old_key, branch=branch, cfg=cfg)} → —'
    return '—'


def get_promotion_requirements(
    role_key: str,
    *,
    branch: str | None = None,
    days_in_role: float = 0,
    active_warns: int = 0,
    on_probation: bool = False,
    on_vacation: bool = False,
    cfg: dict | None = None,
) -> Tuple[bool, List[str]]:
    """Проверка условий бандла. Возвращает (ok, список недостач на русском)."""
    bundle = get_role_bundle(role_key, branch, cfg)
    req = bundle.get('requires') or {}
    missing: List[str] = []

    min_days = int(req.get('min_days_in_role') or 0)
    if min_days > 0 and days_in_role < min_days:
        left = max(0, int(round(min_days - days_in_role)))
        missing.append(f'Мало времени в роли: осталось {left} дн.')

    max_warns = req.get('max_active_warns')
    if max_warns is not None and int(active_warns) > int(max_warns):
        missing.append('Есть активный варн')

    if req.get('not_on_probation') and on_probation:
        missing.append('Идёт испытательный срок')

    if req.get('not_on_vacation') and on_vacation:
        missing.append('Человек в отпуске')

    return (not missing), missing


def role_description(role_key: str, cfg: dict | None = None) -> str:
    cfg = cfg or get_config() or {}
    key = _norm_key(role_key)
    return str((cfg.get('role_descriptions') or {}).get(key) or '')


def compute_bundle_delta(
    *,
    old_key: str,
    new_key: str,
    branch: str,
    current_role_ids: Set[int],
    cfg: dict | None = None,
) -> Tuple[List[int], List[int]]:
    """Какие доп. роли добавить/снять при смене ступени (без ladder/entry)."""
    cfg = cfg or get_config() or {}
    old_b = get_role_bundle(old_key, branch, cfg) if old_key else {
        'add_roles': [], 'remove_roles': []}
    new_b = get_role_bundle(new_key, branch, cfg) if new_key else {
        'add_roles': [], 'remove_roles': []}

    old_extras = set(int(x) for x in (old_b.get('add_roles') or []))
    new_extras = set(int(x) for x in (new_b.get('add_roles') or []))
    # снять extras старого набора + явные remove нового
    to_remove = sorted(
        (old_extras - new_extras)
        | set(int(x) for x in (new_b.get('remove_roles') or []))
    )
    to_add = sorted(new_extras - set(current_role_ids))
    # не снимать то, что сразу добавим
    to_remove = [r for r in to_remove if r not in new_extras and r in current_role_ids]
    return to_add, to_remove


def days_since(iso: str | None) -> float:
    if not iso:
        return 0.0
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)
    except Exception:
        return 0.0
