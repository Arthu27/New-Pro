# -*- coding: utf-8 -*-
"""Права на ручной варн и роль warn (заказ 2026-09-24).

Правила:
  • Ручной варн — только из /modpanel у куратора/админа (и владельца).
  • Хелпер / модер / мастер пункт «Варн» в /modpanel не видят.
  • Обычным участникам варн вручную НЕЛЬЗЯ — только бот (авто-мут,
    автофильтр, AI).
  • Куратор/админ варнит только свою ветку (Helper ↔ Moderator):
    админ хелперов не может варннуть модера другой ветки.
  • Discord-роль warn (≥3) — только куратору/админу на неделю.
"""
from __future__ import annotations

from logger import get_logger

_log = get_logger('warn_acl')

BRANCH_HELPER = 'helper'
BRANCH_MOD = 'mod'


def _known_branch_ids():
    helper = mod = None
    try:
        from services.staff_roles import (
            KNOWN_HELPER_ROLE_ID, KNOWN_MODERATOR_ROLE_ID)
        helper = str(int(KNOWN_HELPER_ROLE_ID))
        mod = str(int(KNOWN_MODERATOR_ROLE_ID))
    except Exception:
        helper = '948969471916249119'
        mod = '803553848396349510'
    return helper, mod


def branches_of(member) -> frozenset:
    """Ветки участника: frozenset({'helper'|'mod'}).

    Ветка = роль Helper и/или Moderator (в т.ч. у куратора/админа).
    """
    if member is None:
        return frozenset()
    helper_id, mod_id = _known_branch_ids()
    out = set()
    try:
        from services.staff_limits import _role_tier_map
        tmap = _role_tier_map() or {}
    except Exception:
        tmap = {}
    for role in (getattr(member, 'roles', None) or []):
        rid = str(getattr(role, 'id', '') or '')
        if not rid:
            continue
        if rid == helper_id or tmap.get(rid) == 'helper':
            out.add(BRANCH_HELPER)
        if rid == mod_id or tmap.get(rid) == 'mod':
            out.add(BRANCH_MOD)
    return frozenset(out)


def _is_bot_actor(actor) -> bool:
    if actor is None:
        return False
    if getattr(actor, 'bot', False):
        return True
    # guild.me / bot user
    try:
        return bool(getattr(getattr(actor, 'guild', None), 'me', None)
                    and int(actor.id) == int(actor.guild.me.id))
    except Exception:
        return False


def _is_bot_owner(actor) -> bool:
    try:
        from config import Config
        return int(getattr(actor, 'id', 0) or 0) in Config.all_owner_ids()
    except Exception:
        return False


def issuer_tier(member) -> str | None:
    """Тир выдающего варн: curator/admin/owner или None."""
    if member is None:
        return None
    if getattr(member, 'is_panel', False):
        return 'owner'  # веб-панель = сессия владельца
    if _is_bot_owner(member):
        return 'owner'
    try:
        from services.staff_hierarchy import best_mapped_tier, RANK
        mapped = best_mapped_tier(member)
        if RANK.get(mapped, -1) >= RANK.get('curator', 4):
            return mapped
    except Exception as _ex:
        _log.debug('issuer_tier: %s', _ex)
    return None


def can_issue_manual_warn(actor) -> bool:
    """Куратор/админ/owner — да; хелпер/мод/мастер — нет."""
    return issuer_tier(actor) is not None


def warn_role_eligible(member) -> bool:
    """Discord-роль warn (≥3) только куратору/админу."""
    if member is None:
        return False
    try:
        from services.staff_hierarchy import best_mapped_tier, RANK
        mapped = best_mapped_tier(member)
        return RANK.get(mapped, -1) >= RANK.get('curator', 4)
    except Exception:
        return False


def manual_warn_check(guild, actor, target) -> tuple:
    """(ok, deny_text|None) для ручного варна (не бот).

    1) Выдающий — куратор/админ/owner.
    2) Цель — стафф (не обычный участник).
    3) Одна ветка: пересечение branches_of(actor) ∩ branches_of(target).
    4) Плюс обычная иерархия (не свой уровень и выше).
    """
    if _is_bot_actor(actor):
        return True, None
    if actor is None:
        return False, 'Нет исполнителя варна.'

    tier = issuer_tier(actor)
    if tier is None:
        return False, (
            'Варн вручную выдают только **куратор** и **админ** ветки. '
            'Хелпер / модер / мастер — без варна. '
            'Обычным участникам варн ставит бот автоматически.')

    if target is None:
        return False, 'Участник не найден.'

    # Обычный участник — только авто-варн бота
    t_role = 'uye'
    try:
        from services.staff_hierarchy import target_panel_role, RANK
        t_role = target_panel_role(guild, target)
        if RANK.get(t_role, 0) < RANK.get('helper', 1):
            return False, (
                'Обычным участникам варн вручную нельзя — '
                'его выдаёт **бот** автоматически (после серии мутов и т.п.).')
    except Exception as _ex:
        _log.debug('manual_warn target role: %s', _ex)

    # Ветка: куратор/админ без Helper/Mod не «ветки» — отказ
    if tier != 'owner':
        from services.staff_hierarchy import RANK
        a_br = branches_of(actor)
        t_br = branches_of(target)
        if not a_br:
            return False, (
                'Нужна роль своей ветки (**Helper** или **Moderator**), '
                'чтобы выдавать варн в этой ветке.')
        if t_br and not (a_br & t_br):
            a_lbl = 'хелперов' if BRANCH_HELPER in a_br else 'модераторов'
            t_lbl = 'хелперов' if BRANCH_HELPER in t_br else 'модераторов'
            return False, (
                f'Нельзя варн через ветку: ты из ветки **{a_lbl}**, '
                f'цель — ветка **{t_lbl}**.')
        # цель без ветки (голый куратор) — только owner
        if not t_br and RANK.get(t_role, 0) >= RANK.get('curator', 4):
            return False, (
                'У цели нет роли ветки (Helper/Moderator) — '
                'такой варн только у владельца.')

    # Иерархия персонала
    try:
        from services.staff_hierarchy import check as _hchk
        ok, deny, _a, _t = _hchk(guild, actor, target, 'warn')
        if not ok:
            return False, deny
    except Exception as _ex:
        _log.debug('manual_warn hierarchy: %s', _ex)

    return True, None


def filter_modpanel_actions(member, actions):
    """Убрать «warn» из меню, если не куратор/админ/owner."""
    if can_issue_manual_warn(member):
        return list(actions or [])
    return [a for a in (actions or []) if (a[0] if isinstance(a, (tuple, list)) else a) != 'warn']
