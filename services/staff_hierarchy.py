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
  • цель: панельная роль участника (та же _get_role_from_discord, что при
    входе) + Discord-метки (владелец бота/сервера, бот).
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
REMOVE_ACTIONS = ('unwarn', 'untimeout', 'vunmute', 'unban')


def target_panel_role(guild, member, bot=None):
    """Панельная роль цели: та же логика, что при входе в панель.

    mod/curator/admin по Discord-ролям и правам, owner — владелец сервера
    или владелец бота. Порядок и источники — как в web.app._get_role_from_discord,
    чтобы панель и бот НЕ разошлись во мнениях, кто перед ними.
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
        # права считаем БЕЗ игнорируемых ролей (владелец 2026-09-05:
        # «облачная» роль с правами не делает носителя модератором/админом)
        try:
            from services import ignored_roles as _IR
            perms = _IR.effective_permissions(member, guild)
        except Exception as _ex:
            _log.debug('target_panel_role: ignored: %s', _ex)
            perms = getattr(member, 'guild_permissions', None)
        if perms is not None and getattr(perms, 'administrator', False):
            return 'admin'
        # настроенная модер-роль (единый источник панели) → модератор+
        try:
            from services.mod_role import get_mod_role_id
            rid = str(get_mod_role_id(guild.id) or '')
            if rid and any(str(r.id) == rid
                           for r in (getattr(member, 'roles', None) or [])):
                return 'mod'
        except Exception as _ex:
            _log.debug('target_panel_role: mod_role: %s', _ex)
        if perms is not None and (getattr(perms, 'ban_members', False)
                                  or getattr(perms, 'manage_guild', False)
                                  or getattr(perms, 'manage_messages', False)):
            return 'mod'
        return 'uye'
    except Exception as _ex:
        _log.debug('target_panel_role: %s', _ex)
        return 'uye'


def actor_panel_role(guild, actor, session_role=None):
    """Панельная роль исполнителя.

    actor — Discord-мембер (бот/панель под Discord-аккаунтом) или None
    (статический вход из .env = владелец панели). session_role — панельная
    роль входа ('mod'/'curator'/'admin'), панель знает её точно и передаёт:
    Discord-роли не различают куратора от модератора, а панельная — да.
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
                        and a_role != 'owner':
                    return (False, 'Это владелец бота — его наказывать нельзя.',
                            a_role, t_role)
            except Exception as _ex:
                _log.debug('check: bot-owner target: %s', _ex)
            if getattr(target, 'id', None) == getattr(guild, 'owner_id', None) \
                    and a_role != 'owner':
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
