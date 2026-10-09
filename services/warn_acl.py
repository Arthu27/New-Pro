# -*- coding: utf-8 -*-
"""Права на ручной варн.

Правила:
  • Участникам (не стафф) — мод+ / администрация с ACL warn.
  • Стаффу — только «× Отвечаю за …» / админ своей ветки
    (пересечение веток issuer ∩ target). Кросс-ветка — отказ.
  • В /modpanel:
      – цель участник → обычное меню + кнопка Warn (если ACL ок);
      – цель стафф → ТОЛЬКО Warn (+ история / снять варн при правах).
  • Проверка прав — на сервере при каждом действии (не только скрытие кнопок).
  • Нельзя варннуть себя; иерархия через staff_hierarchy.
"""
from __future__ import annotations

from logger import get_logger

_log = get_logger('warn_acl')


def _grant_role_ids() -> dict:
    out = {}
    try:
        from services.warn_config import branch_grant_roles
        for kind, rid in (branch_grant_roles() or {}).items():
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
        from services.warn_config import branch_curator_roles
        for kind, rid in (branch_curator_roles() or {}).items():
            try:
                out[str(kind)] = str(int(rid))
            except (TypeError, ValueError):
                continue
    except Exception as _ex:
        _log.debug('curator ids: %s', _ex)
    return out


def issuer_branches_of(member) -> frozenset:
    """Ветки, за которые отвечает исполнитель («× Отвечаю за …»).

    Куратор и администратор ветки определяются этой ролью — единый
    источник «своей ветки» для правил варна стаффу.
    """
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
    """Стафф = роль ветки набора / mapped helper+ / активный отпуск Staff Manager."""
    if target is None:
        return False
    if branches_of(target):
        return True
    try:
        from services.staff_hierarchy import best_mapped_tier, RANK
        mapped = best_mapped_tier(target)
        if RANK.get(mapped, -1) >= RANK.get('helper', 1):
            return True
    except Exception:
        pass
    # отпуск: нет ladder-ролей, но остаётся стаффом (не выдавать warn)
    try:
        from services.staff_manager.acl import get_staff_info as sm_info
        from services.staff_manager.config import is_enabled
        if is_enabled():
            gid = getattr(guild, 'id', None) or getattr(
                getattr(target, 'guild', None), 'id', None)
            info = sm_info(target, guild_id=gid)
            if info.get('is_staff') or info.get('on_vacation'):
                return True
    except Exception:
        pass
    return False


def is_staff_target(guild, target) -> bool:
    """Публичный алиас."""
    return _is_staff_target(guild, target)


def get_staff_info(member) -> tuple:
    """Текущий статус из ролей: (is_staff, branch|None, rank).

    Истина — только роли Discord. Не читать is_staff из БД/варна.
    """
    if member is None:
        return False, None, 0
    guild = getattr(member, 'guild', None)
    is_staff = bool(_is_staff_target(guild, member))
    branch = None
    rank = 0
    try:
        from services.warn_config import member_rank_snapshot
        rank, _rid, _name = member_rank_snapshot(member)
    except Exception:
        rank = 0
    if is_staff:
        try:
            br = branches_of(member)
            branch = sorted(br)[0] if br else None
        except Exception:
            branch = None
    return is_staff, branch, int(rank or 0)


def _mod_plus(actor) -> bool:
    """Может варннуть обычного участника (тир mod+, не helper)."""
    if actor is None:
        return False
    if getattr(actor, 'is_panel', False) or _is_bot_owner(actor):
        return True
    try:
        from services.staff_hierarchy import best_mapped_tier, RANK
        mapped = best_mapped_tier(actor)
        if mapped in ('mod', 'master', 'curator', 'assistent', 'admin', 'owner'):
            return True
        if RANK.get(mapped, -1) > RANK.get('helper', 1):
            return True
    except Exception as _ex:
        _log.debug('mod_plus: %s', _ex)
    return bool(issuer_branches_of(actor))


def can_issue_manual_warn(actor, target=None, guild=None) -> bool:
    """Есть ли право на ручной варн (с учётом цели, если передана)."""
    if actor is None:
        return False
    if getattr(actor, 'is_panel', False) or _is_bot_owner(actor):
        return True
    if target is None:
        return _mod_plus(actor) or bool(issuer_branches_of(actor))
    g = guild or getattr(actor, 'guild', None) or getattr(target, 'guild', None)
    if _is_staff_target(g, target):
        return bool(issuer_branches_of(actor))
    return _mod_plus(actor)


def warn_role_eligible(member) -> bool:
    """Кто может управлять ролью warn у стаффа (ветковой ACL)."""
    return bool(issuer_branches_of(member)) or _is_bot_owner(member)


def manual_warn_check(guild, actor, target) -> tuple:
    """(ok, deny_text|None) для ручного варна (не бот)."""
    if _is_bot_actor(actor):
        return True, None
    if actor is None:
        return False, 'Нет исполнителя варна.'
    if target is None:
        return False, 'Участник не найден.'

    # себе нельзя
    try:
        if int(getattr(actor, 'id', 0)) == int(getattr(target, 'id', 0)):
            return False, 'Себе варн выдать нельзя.'
    except Exception:
        pass

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

    # ── Стафф: куратор/админ только своей ветки ──────────────────
    a_br = issuer_branches_of(actor)
    if not is_owner and not a_br:
        return False, (
            'Варн стаффу выдают только куратор/админ своей ветки '
            '(роль «× Отвечаю за …»).')

    if not is_owner:
        t_br = branches_of(target)
        if not t_br:
            return False, (
                'У цели нет роли ветки набора — '
                'такой варн только у владельца.')
        if not (a_br & t_br):
            return False, (
                f'Чужая ветка: ты отвечаешь за '
                f'**{", ".join(sorted(a_br))}**, '
                f'цель — **{", ".join(sorted(t_br))}**.')

    try:
        from services.staff_hierarchy import check as _hchk
        # для веткового варна исполнитель действует как минимум curator
        a_role = 'owner' if is_owner else 'curator'
        ok, deny, _a, _t = _hchk(
            guild, actor, target, 'warn', actor_role=a_role)
        if not ok:
            return False, deny
    except Exception as _ex:
        _log.debug('manual_warn staff hierarchy: %s', _ex)

    return True, None


# Действия, допустимые в staff-only меню /modpanel
_STAFF_MENU_KEYS = frozenset({'warn', 'unwarn', 'warn_history'})


def filter_modpanel_actions(member, actions, *, target=None, guild=None):
    """Меню /modpanel с учётом цели.

    Без цели — пункт Warn скрыт (откроется после выбора); остальное как есть.
    Цель-участник — обычное меню + Warn в начале (если ACL ок).
    Цель-стафф — ТОЛЬКО Warn / История / Снять варн (при правах ветки).
    """
    g = guild or getattr(member, 'guild', None)
    if target is not None:
        g = g or getattr(target, 'guild', None)

    def _key(a):
        return a[0] if isinstance(a, (tuple, list)) else a

    warn_row = None
    history_row = None
    rest = []
    for a in (actions or []):
        k = _key(a)
        if k == 'warn':
            warn_row = a
        elif k == 'warn_history':
            history_row = a
        else:
            rest.append(a)

    # без цели — обычное меню без Warn (unwarn остаётся, как раньше)
    if target is None:
        return rest

    staff = _is_staff_target(g, target)

    if staff:
        # Отдельное меню стаффа: Warn (+ история / снять) по праву ветки.
        # Inject defaults — даже если ACL «warn» не выдан роли в панели,
        # ветковый куратор/админ всё равно видит своё меню.
        out = []
        ok_warn, _deny = manual_warn_check(g, member, target)
        _WARN = ('warn', 'Варн', 'Предупреждение за нарушение', 'warn')
        _HIST = ('warn_history', 'История варнов',
                 'Список варнов с пагинацией', 'warn')
        _UNWARN = ('unwarn', 'Снять варн', 'Убрать последний варн', 'warn')
        if ok_warn:
            out.append(warn_row or _WARN)
            out.append(history_row or _HIST)
            # unwarn из rest или дефолт
            unwarn = next((a for a in rest if _key(a) == 'unwarn'), _UNWARN)
            out.append(unwarn)
        elif (_is_bot_owner(member)
              or getattr(member, 'is_panel', False)):
            out.append(history_row or _HIST)
        return out

    # обычный участник
    out = list(rest)
    ok, _deny = manual_warn_check(g, member, target)
    if ok and warn_row is not None:
        out = [warn_row] + out
    if ok and history_row is not None:
        insert_at = 1 if out and _key(out[0]) == 'warn' else 0
        out.insert(insert_at, history_row)
    return out
