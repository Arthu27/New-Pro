# -*- coding: utf-8 -*-
"""Иерархия персонала: кто кого может наказывать (владелец, 2026-09-05).

Жалоба владельца: «модер может выдать наказание другому модеру, модер может
дать вообще куратору — беспредел». Раньше цели не проверялись вовсе.

ПРАВИЛА (единые для бота и панели):
  • персонал НЕ наказывает персонал СВОЕГО уровня и ВЫШЕ:
      модератор (mod)     → только участники (uye);
      куратор (curator)   → участники и модераторы;
      администратор (admin) → участники, модераторы, кураторы;
      владелец панели (owner) → всех, кроме владельца бота и владельца сервера;
  • владелец БОТА и владелец СЕРВЕРА — вне юрисдикции всех;
  • боты не наказываются;
  • нельзя наказывать самого себя;
  • «снятия» (unwarn/untimeout/vunmute/unban) — по той же иерархии:
    нельзя трогать персонал своего уровня и выше (иначе модеры снимали бы
    наказания друг друга — тот же беспредел);
  • варн (warn) — тоже наказание и подчиняется иерархии.

Кто есть кто:
  • исполнитель: панельная роль входа (session['role']) + Discord-мембер;
    статический вход из .env — это владелец (owner);
  • цель/исполнитель без сессии: та же лестница, что web.app._get_role_from_discord
    — высший тир из data/role_map.json (куратор+хелпер → куратор), не нижний.
"""
from logger import get_logger

_log = get_logger('staff_hierarchy')

# Панельные роли по старшинству (тот же порядок, что web/app.ROLES)
RANK = {'uye': 0, 'mod': 1, 'curator': 2, 'admin': 3, 'owner': 4}

LABELS = {
    'uye': 'участник',
    'mod': 'модератор',
    'curator': 'куратор',
    'admin': 'администратор',
    'owner': 'владелец панели',
}

# Действия-«снятия»: к ним применяется та же иерархия (нельзя лезть в
# наказания персонала своего уровня и выше).
REMOVE_ACTIONS = ('unwarn', 'untimeout', 'vunmute', 'unmute_chat', 'unban', 'unmute')


def _role_map_tiers():
    """{discord_role_id(str): panel_tier} из data/role_map.json + известная
    роль куратора сервера (807030012301541377), если в карте ещё нет."""
    out = {}
    try:
        from services.staff_limits import _role_tier_map
        out.update(_role_tier_map() or {})
    except Exception as _ex:
        _log.debug('role_map_tiers: %s', _ex)
    try:
        from services.staff_roles import KNOWN_CURATOR_ROLE_ID
        kid = str(int(KNOWN_CURATOR_ROLE_ID))
        if kid not in out:
            out[kid] = 'curator'
    except Exception as _ex:
        _log.debug('role_map_tiers curator fallback: %s', _ex)
    try:
        from services.staff_roles import KNOWN_HELPER_ROLE_ID
        hid = str(int(KNOWN_HELPER_ROLE_ID))
        if hid not in out:
            out[hid] = 'mod'
    except Exception as _ex:
        _log.debug('role_map_tiers helper fallback: %s', _ex)
    return out


def best_mapped_tier(member):
    """Высший панельный тир по Discord-ролям участника (role_map).

    Куратор + хелпер (mod) → 'curator'. Без стафф-ролей → None.
    """
    if member is None:
        return None
    tmap = _role_map_tiers()
    if not tmap:
        return None
    best = None
    best_rank = -1
    for role in (getattr(member, 'roles', None) or []):
        rid = str(getattr(role, 'id', '') or '')
        tier = tmap.get(rid)
        if not tier:
            continue
        rank = RANK.get(tier, -1)
        if rank > best_rank:
            best, best_rank = tier, rank
    return best


def target_panel_role(guild, member, bot=None):
    """Панельная роль цели: та же логика, что при входе в панель.

    Порядок:
      1) владелец бота / сервера → owner
      2) высший из (role_map, Discord-права):
         curator/admin в карте и Discord Administrator важнее helper/mod
      3) uye

    Раньше куратор/админ с ролью хелпера определялся как «mod» —
    /modpanel давал права хелпера.
    """
    if member is None:
        return 'uye'
    try:
        # владелец бота — сразу owner (тот же критерий, что при входе)
        try:
            from config import Config
            if int(getattr(member, 'id', 0) or 0) in Config.all_owner_ids():
                return 'owner'
        except Exception as _ex:
            _log.debug('target_panel_role: bot-owner: %s', _ex)
        if getattr(member, 'id', None) == getattr(guild, 'owner_id', None):
            return 'owner'

        # Высший тир = max(role_map, Discord-права). Куратор/админ+хелпер
        # не схлопывается в mod: mapped helper не важнее Discord Administrator
        # и не важнее curator/admin в карте.
        mapped = best_mapped_tier(member)
        try:
            from services import ignored_roles as _IR
            perms = _IR.effective_permissions(member, guild)
        except Exception as _ex:
            _log.debug('target_panel_role: ignored: %s', _ex)
            perms = getattr(member, 'guild_permissions', None)

        perm_tier = None
        if perms is not None and getattr(perms, 'administrator', False):
            perm_tier = 'admin'
        else:
            try:
                from services.mod_role import get_mod_role_id
                rid = str(get_mod_role_id(guild.id) or '')
                if rid and any(str(r.id) == rid
                               for r in (getattr(member, 'roles', None) or [])):
                    perm_tier = 'mod'
            except Exception as _ex:
                _log.debug('target_panel_role: mod_role: %s', _ex)
            if (perm_tier is None and perms is not None
                    and (getattr(perms, 'ban_members', False)
                         or getattr(perms, 'manage_guild', False)
                         or getattr(perms, 'manage_messages', False))):
                perm_tier = 'mod'

        best = 'uye'
        for tier in (mapped, perm_tier):
            if tier in RANK and RANK[tier] > RANK.get(best, -1):
                best = tier
        return best
    except Exception as _ex:
        _log.debug('target_panel_role: %s', _ex)
        return 'uye'


def actor_panel_role(guild, actor, session_role=None):
    """Панельная роль исполнителя.

    actor — Discord-мембер (бот/панель под Discord-аккаунтом) или None
    (статический вход из .env = владелец панели). session_role — панельная
    роль входа ('mod'/'curator'/'admin'), панель знает её точно и передаёт.
    Без сессии — высший тир Discord-ролей (role_map), как у цели.
    """
    if actor is None or getattr(actor, 'is_panel', False):
        return 'owner'
    if session_role in RANK:
        return session_role
    return target_panel_role(guild, actor)


def explain(actor_role, target_role, label=None):
    """Текст отказа — сразу готов для показа модератору/панели."""
    a = LABELS.get(actor_role, actor_role)
    t = LABELS.get(target_role, target_role)
    what = f' ({label})' if label else ''
    return (f'Нельзя{what}: {t} — персонал твоего уровня или выше. '
            f'Иерархия: модератор → куратор → администратор → владелец. '
            f'Вопросы по правам — к владельцу панели.')


def check(guild, actor, target, action='', *, actor_role=None,
          target_role=None, session_role=None):
    """(ok, deny_text|None, actor_role, target_role).

    Единственная точка правды для бота (/modpanel, ПКМ) и панели
    (карточка участника, массовые действия). guild — discord.Guild,
    actor/target — discord.Member (target может быть None-подобным для
    оффлайн-ID: тогда считаем участником, наказание оффлайн-цели не
    поднимает его статус).
    """
    a_role = actor_role or actor_panel_role(guild, actor, session_role)
    t_role = target_role or target_panel_role(guild, target)
    try:
        # владелец бота и владелец сервера — вне юрисдикции всех, кроме owner
        if target is not None:
            try:
                from config import Config
                if int(getattr(target, 'id', 0) or 0) in Config.all_owner_ids() \
                        and a_role != 'owner' and action not in REMOVE_ACTIONS:
                    return (False, 'Это владелец бота — его наказывать нельзя.',
                            a_role, t_role)
            except Exception as _ex:
                _log.debug('check: bot-owner target: %s', _ex)
            if getattr(target, 'id', None) == getattr(guild, 'owner_id', None) \
                    and a_role != 'owner' and action not in REMOVE_ACTIONS:
                return (False, 'Это владелец сервера — его наказывать нельзя.',
                        a_role, t_role)
            if getattr(target, 'bot', False):
                return False, 'Ботов наказывать нельзя.', a_role, t_role
            if actor is not None and \
                    getattr(target, 'id', None) == getattr(actor, 'id', None):
                return False, 'Себя наказывать нельзя.', a_role, t_role
        # персонал не наказывает персонал СВОЕГО уровня ИЛИ ВЫШЕ:
        # модер(1)→куратор(2)/админ(3) нельзя, куратор(2)→модер(1) можно.
        # Исключение — владелец панели (owner): он может всё (его защита
        # от владельцев бота/сервера стоит выше).
        if (t_role != 'uye' and a_role != 'owner'
                and RANK.get(a_role, 0) <= RANK.get(t_role, 0)):
            label = str(action or '')
            return (False, explain(a_role, t_role, label or None),
                    a_role, t_role)
        return True, None, a_role, t_role
    except Exception as _ex:
        # сбой проверки НЕ открывает действие (fail-close)
        _log.debug('hierarchy check: %s', _ex)
        return False, 'Не смог проверить права — обратись к владельцу.', a_role, t_role
