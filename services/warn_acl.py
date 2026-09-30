# -*- coding: utf-8 -*-
"""Права на ручной варн стаффу своей ветки (заказ 2026-09-30).

Правила:
  • Ручной варн — только из /modpanel у куратора / ассистента / админа
    (и владельца бота).
  • Хелпер / модер без кураторской роли варн не выдают.
  • Обычным участникам варн вручную НЕЛЬЗЯ — только бот.
  • Варн только своей ветке (Helper / Mod / Events / Support /
    Close mod / Creative / Broadcaster): кросс-ветка запрещена.
  • В /modpanel пункт «Варн» появляется только после выбора человека
    из своего стафа.
  • Discord-роль warn (≥3) — только куратору/админу на неделю.
"""
from __future__ import annotations

from logger import get_logger

_log = get_logger('warn_acl')

# Тиры, которые могут вручную варннуть стафф своей ветки
ISSUER_TIERS = frozenset({'master', 'curator', 'admin', 'owner'})


def _grant_role_ids() -> dict:
    """kind → discord role id (роль ветки, кого принимают)."""
    out = {}
    try:
        from services.staff_roles import KNOWN_GRANT_BY_KIND
        for kind, rid in (KNOWN_GRANT_BY_KIND or {}).items():
            try:
                out[str(kind)] = str(int(rid))
            except (TypeError, ValueError):
                continue
    except Exception as _ex:
        _log.debug('grant ids: %s', _ex)
    # фолбек helper/mod
    out.setdefault('helper', '948969471916249119')
    out.setdefault('moderator', '803553848396349510')
    return out


def _curator_role_ids() -> dict:
    """kind → «× Отвечаю за …» role id."""
    out = {}
    try:
        from services.staff_roles import KNOWN_CURATOR_BY_KIND
        for kind, rid in (KNOWN_CURATOR_BY_KIND or {}).items():
            try:
                out[str(kind)] = str(int(rid))
            except (TypeError, ValueError):
                continue
    except Exception as _ex:
        _log.debug('curator ids: %s', _ex)
    return out


def branches_of(member) -> frozenset:
    """Ветки участника по ролям набора / «отвечаю за».

    Возвращает frozenset kind'ов: helper, moderator, event, …
    """
    if member is None:
        return frozenset()
    grants = _grant_role_ids()
    curators = _curator_role_ids()
    # reverse maps
    by_grant = {rid: kind for kind, rid in grants.items()}
    by_cur = {rid: kind for kind, rid in curators.items()}
    out = set()
    try:
        from services.staff_limits import _role_tier_map
        tmap = _role_tier_map() or {}
    except Exception:
        tmap = {}
    # legacy: role_map helper/mod → kind
    tier_to_kind = {'helper': 'helper', 'mod': 'moderator'}
    for role in (getattr(member, 'roles', None) or []):
        rid = str(getattr(role, 'id', '') or '')
        if not rid:
            continue
        if rid in by_grant:
            out.add(by_grant[rid])
        if rid in by_cur:
            out.add(by_cur[rid])
        mapped = tmap.get(rid)
        if mapped in tier_to_kind:
            out.add(tier_to_kind[mapped])
    return frozenset(out)


def _is_bot_actor(actor) -> bool:
    if actor is None:
        return False
    if getattr(actor, 'bot', False):
        return True
    try:
        me = getattr(getattr(actor, 'guild', None), 'me', None)
        return bool(me and int(actor.id) == int(me.id))
    except Exception:
        return False


def _is_bot_owner(actor) -> bool:
    try:
        from config import Config
        return int(getattr(actor, 'id', 0) or 0) in Config.all_owner_ids()
    except Exception:
        return False


def _has_branch_curator_role(member) -> bool:
    """Есть ли «× Отвечаю за …» (ассистент/куратор ветки)."""
    if member is None:
        return False
    want = set(_curator_role_ids().values())
    if not want:
        return False
    for role in (getattr(member, 'roles', None) or []):
        rid = str(getattr(role, 'id', '') or '')
        if rid in want:
            return True
    return False


def issuer_tier(member) -> str | None:
    """Тир выдающего: master/curator/admin/owner или None.

    «Ассистенты» = master и/или роли «× Отвечаю за …».
    """
    if member is None:
        return None
    if getattr(member, 'is_panel', False):
        return 'owner'
    if _is_bot_owner(member):
        return 'owner'
    try:
        from services.staff_hierarchy import best_mapped_tier, RANK
        mapped = best_mapped_tier(member)
        if mapped in ISSUER_TIERS or RANK.get(mapped, -1) >= RANK.get('master', 2):
            if mapped in ISSUER_TIERS:
                return mapped
            if RANK.get(mapped, -1) >= RANK.get('master', 2):
                return mapped
    except Exception as _ex:
        _log.debug('issuer_tier: %s', _ex)
    # Куратор ветки без маппинга в role_map — всё равно issuer
    if _has_branch_curator_role(member):
        return 'curator'
    return None


def can_issue_manual_warn(actor) -> bool:
    """Куратор / ассистент / админ / owner — да."""
    return issuer_tier(actor) is not None


def warn_role_eligible(member) -> bool:
    """Discord-роль warn (≥3) только куратору/админу."""
    if member is None:
        return False
    try:
        from services.staff_hierarchy import best_mapped_tier, RANK
        mapped = best_mapped_tier(member)
        return RANK.get(mapped, -1) >= RANK.get('curator', 3)
    except Exception:
        return False


def manual_warn_check(guild, actor, target) -> tuple:
    """(ok, deny_text|None) для ручного варна (не бот)."""
    if _is_bot_actor(actor):
        return True, None
    if actor is None:
        return False, 'Нет исполнителя варна.'

    tier = issuer_tier(actor)
    if tier is None:
        return False, (
            'Варн стаффу выдают только **куратор**, **ассистент** и **админ** '
            'своей ветки. Обычным участникам варн ставит бот.')

    if target is None:
        return False, 'Участник не найден.'

    t_role = 'uye'
    try:
        from services.staff_hierarchy import target_panel_role, RANK
        t_role = target_panel_role(guild, target)
        if RANK.get(t_role, 0) < RANK.get('helper', 1):
            # цель без стафф-тира, но с ролью ветки — считаем стаффом
            if not branches_of(target):
                return False, (
                    'Обычным участникам варн вручную нельзя — '
                    'его выдаёт **бот** автоматически.')
    except Exception as _ex:
        _log.debug('manual_warn target role: %s', _ex)

    if tier != 'owner':
        from services.staff_hierarchy import RANK
        a_br = branches_of(actor)
        t_br = branches_of(target)
        if not a_br:
            return False, (
                'Нужна роль своей ветки (Helper / Moderator / Events / … '
                'или «× Отвечаю за …»), чтобы выдавать варн в этой ветке.')
        if not t_br:
            if RANK.get(t_role, 0) >= RANK.get('helper', 1):
                return False, (
                    'У цели нет роли ветки набора — '
                    'такой варн только у владельца.')
            return False, 'Цель не из стаффа ветки.'
        if not (a_br & t_br):
            return False, (
                f'Нельзя варн через ветку: ты — **{", ".join(sorted(a_br))}**, '
                f'цель — **{", ".join(sorted(t_br))}**.')

    try:
        from services.staff_hierarchy import check as _hchk
        ok, deny, _a, _t = _hchk(guild, actor, target, 'warn')
        if not ok:
            return False, deny
    except Exception as _ex:
        _log.debug('manual_warn hierarchy: %s', _ex)

    return True, None


def filter_modpanel_actions(member, actions, *, target=None, guild=None):
    """Пункт warn: только если выбран свой стафф и issuer может варннуть.

    Без target — warn скрыт (даже у куратора).
    """
    out = []
    warn_row = None
    for a in (actions or []):
        key = a[0] if isinstance(a, (tuple, list)) else a
        if key == 'warn':
            warn_row = a
            continue
        out.append(a)
    if warn_row is None:
        return out
    if target is None or not can_issue_manual_warn(member):
        return out
    g = guild or getattr(member, 'guild', None) or getattr(target, 'guild', None)
    ok, _deny = manual_warn_check(g, member, target)
    if ok:
        # варн первым — видно сразу после выбора своего стаффа
        out = [warn_row] + out
    return out
