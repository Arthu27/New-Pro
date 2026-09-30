# -*- coding: utf-8 -*-
"""Права на ручной варн стаффу своей ветки (заказ 2026-09-30).

Правила:
  • Ручной варн — ТОЛЬКО роли «× Отвечаю за …» своей ветки
    (и владелец бота / веб-панель).
  • Обычный куратор / админ / мастер / хелпер / модер без «отвечаю за»
    варн не выдают.
  • Обычным участникам варн вручную НЕЛЬЗЯ — только бот.
  • Варн только своей ветке: кросс-ветка запрещена.
  • В /modpanel пункт «Варн» появляется только после выбора человека
    из своего стафа.
"""
from __future__ import annotations

from logger import get_logger

_log = get_logger('warn_acl')


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


def issuer_branches_of(member) -> frozenset:
    """Ветки, за которые участник «отвечает» (только × Отвечаю за …)."""
    if member is None:
        return frozenset()
    by_cur = {rid: kind for kind, rid in _curator_role_ids().items()}
    out = set()
    for role in (getattr(member, 'roles', None) or []):
        rid = str(getattr(role, 'id', '') or '')
        if rid in by_cur:
            out.add(by_cur[rid])
    return frozenset(out)


def branches_of(member) -> frozenset:
    """Ветки стаффа-цели: роли набора (+ legacy helper/mod в role_map)."""
    if member is None:
        return frozenset()
    grants = _grant_role_ids()
    by_grant = {rid: kind for kind, rid in grants.items()}
    out = set()
    try:
        from services.staff_limits import _role_tier_map
        tmap = _role_tier_map() or {}
    except Exception:
        tmap = {}
    tier_to_kind = {'helper': 'helper', 'mod': 'moderator'}
    for role in (getattr(member, 'roles', None) or []):
        rid = str(getattr(role, 'id', '') or '')
        if not rid:
            continue
        if rid in by_grant:
            out.add(by_grant[rid])
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


def can_issue_manual_warn(actor) -> bool:
    """Только «× Отвечаю за …» / owner / панель."""
    if actor is None:
        return False
    if getattr(actor, 'is_panel', False) or _is_bot_owner(actor):
        return True
    return bool(issuer_branches_of(actor))


def warn_role_eligible(member) -> bool:
    """Discord-роль warn (≥3) — у кого есть «× Отвечаю за …»."""
    return bool(issuer_branches_of(member)) or _is_bot_owner(member)


def manual_warn_check(guild, actor, target) -> tuple:
    """(ok, deny_text|None) для ручного варна (не бот)."""
    if _is_bot_actor(actor):
        return True, None
    if actor is None:
        return False, 'Нет исполнителя варна.'

    is_owner = bool(
        getattr(actor, 'is_panel', False) or _is_bot_owner(actor))
    a_br = issuer_branches_of(actor)
    if not is_owner and not a_br:
        return False, (
            'Варн стаффу выдают только роли **× Отвечаю за …** своей ветки.')

    if target is None:
        return False, 'Участник не найден.'

    t_role = 'uye'
    try:
        from services.staff_hierarchy import target_panel_role, RANK
        t_role = target_panel_role(guild, target)
        if RANK.get(t_role, 0) < RANK.get('helper', 1):
            if not branches_of(target):
                return False, (
                    'Обычным участникам варн вручную нельзя — '
                    'его выдаёт **бот** автоматически.')
    except Exception as _ex:
        _log.debug('manual_warn target role: %s', _ex)

    if not is_owner:
        from services.staff_hierarchy import RANK
        t_br = branches_of(target)
        if not t_br:
            if RANK.get(t_role, 0) >= RANK.get('helper', 1):
                return False, (
                    'У цели нет роли ветки набора — '
                    'такой варн только у владельца.')
            return False, 'Цель не из стаффа ветки.'
        if not (a_br & t_br):
            return False, (
                f'Нельзя варн через ветку: ты отвечаешь за '
                f'**{", ".join(sorted(a_br))}**, '
                f'цель — **{", ".join(sorted(t_br))}**.')

    try:
        from services.staff_hierarchy import check as _hchk
        # «× Отвечаю за …» = куратор ветки (в role_map роли может не быть)
        a_role = 'owner' if is_owner else 'curator'
        ok, deny, _a, _t = _hchk(
            guild, actor, target, 'warn', actor_role=a_role)
        if not ok:
            return False, deny
    except Exception as _ex:
        _log.debug('manual_warn hierarchy: %s', _ex)

    return True, None


def filter_modpanel_actions(member, actions, *, target=None, guild=None):
    """Пункт warn: только «отвечаю за» + выбран свой стафф."""
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
        out = [warn_row] + out
    return out
