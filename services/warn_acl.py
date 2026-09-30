# -*- coding: utf-8 -*-
"""Права на ручной варн (заказ 2026-09-30).

Правила:
  • Участникам (не стафф) — варн вручную снова можно (мод+ с ACL warn),
    причина только из правил 1.1–1.9, где есть Варн/Пред.
  • Стаффу — только роли «× Отвечаю за …» своей ветки (кросс-ветка нельзя).
  • В /modpanel пункт «Варн» появляется после выбора цели:
      – участник → если у модера есть warn в ACL;
      – стафф → если «отвечаю за» той же ветки.
  • Обычным участникам авто-варн бота по-прежнему работает.
"""
from __future__ import annotations

from logger import get_logger

_log = get_logger('warn_acl')


def _grant_role_ids() -> dict:
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
    """Ветки «× Отвечаю за …»."""
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
    """Ветки стаффа-цели (роли набора)."""
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


def _is_staff_target(guild, target) -> bool:
    """Стафф = роль ветки набора или mapped helper+ (не Discord-права)."""
    if target is None:
        return False
    if branches_of(target):
        return True
    try:
        # Только role_map / known roles — manage_messages у участника
        # не делает его «стаффом» для ветки варна.
        from services.staff_hierarchy import best_mapped_tier, RANK
        mapped = best_mapped_tier(target)
        return RANK.get(mapped, -1) >= RANK.get('helper', 1)
    except Exception:
        return False


def _mod_plus(actor) -> bool:
    """Может варннуть обычного участника (тир mod+, не helper)."""
    if actor is None:
        return False
    if getattr(actor, 'is_panel', False) or _is_bot_owner(actor):
        return True
    try:
        from services.staff_hierarchy import best_mapped_tier, RANK
        mapped = best_mapped_tier(actor)
        # helper и mod оба RANK=1 — смотрим имя тира, не число
        if mapped in ('mod', 'master', 'curator', 'admin', 'owner'):
            return True
        if RANK.get(mapped, -1) > RANK.get('helper', 1):
            return True
    except Exception as _ex:
        _log.debug('mod_plus: %s', _ex)
    # «× Отвечаю за …» тоже может варннуть участника
    return bool(issuer_branches_of(actor))


def can_issue_manual_warn(actor, target=None, guild=None) -> bool:
    """Есть ли право на ручной варн (с учётом цели, если передана)."""
    if actor is None:
        return False
    if getattr(actor, 'is_panel', False) or _is_bot_owner(actor):
        return True
    if target is None:
        # без цели — пункт появится после выбора; заранее: мод+ или отвечаю
        return _mod_plus(actor) or bool(issuer_branches_of(actor))
    g = guild or getattr(actor, 'guild', None) or getattr(target, 'guild', None)
    if _is_staff_target(g, target):
        return bool(issuer_branches_of(actor))
    return _mod_plus(actor)


def warn_role_eligible(member) -> bool:
    """Discord-роль warn (≥3) — стафф с «отвечаю» / owner."""
    return bool(issuer_branches_of(member)) or _is_bot_owner(member)


def manual_warn_check(guild, actor, target) -> tuple:
    """(ok, deny_text|None) для ручного варна (не бот)."""
    if _is_bot_actor(actor):
        return True, None
    if actor is None:
        return False, 'Нет исполнителя варна.'
    if target is None:
        return False, 'Участник не найден.'

    is_owner = bool(
        getattr(actor, 'is_panel', False) or _is_bot_owner(actor))

    # ── Участник (не стафф) ──────────────────────────────────────
    if not _is_staff_target(guild, target):
        if not is_owner and not _mod_plus(actor):
            return False, (
                'Варн участникам выдают модераторы и выше '
                '(нужен доступ к пункту «Варн» в /modpanel).')
        try:
            from services.staff_hierarchy import check as _hchk
            ok, deny, _a, _t = _hchk(guild, actor, target, 'warn')
            if not ok:
                return False, deny
        except Exception as _ex:
            _log.debug('manual_warn member hierarchy: %s', _ex)
        return True, None

    # ── Стафф: только «× Отвечаю за …» своей ветки ───────────────
    a_br = issuer_branches_of(actor)
    if not is_owner and not a_br:
        return False, (
            'Варн стаффу выдают только роли **× Отвечаю за …** своей ветки.')

    if not is_owner:
        t_br = branches_of(target)
        if not t_br:
            return False, (
                'У цели нет роли ветки набора — '
                'такой варн только у владельца.')
        if not (a_br & t_br):
            return False, (
                f'Нельзя варн через ветку: ты отвечаешь за '
                f'**{", ".join(sorted(a_br))}**, '
                f'цель — **{", ".join(sorted(t_br))}**.')

    try:
        from services.staff_hierarchy import check as _hchk
        a_role = 'owner' if is_owner else 'curator'
        ok, deny, _a, _t = _hchk(
            guild, actor, target, 'warn', actor_role=a_role)
        if not ok:
            return False, deny
    except Exception as _ex:
        _log.debug('manual_warn staff hierarchy: %s', _ex)

    return True, None


def filter_modpanel_actions(member, actions, *, target=None, guild=None):
    """Варн в меню после выбора цели: участник или свой стафф."""
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
    # без выбранного человека — warn скрыт (откроется после выбора)
    if target is None:
        return out
    g = guild or getattr(member, 'guild', None) or getattr(target, 'guild', None)
    ok, _deny = manual_warn_check(g, member, target)
    if ok:
        out = [warn_row] + out
    return out
