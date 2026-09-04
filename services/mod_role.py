# -*- coding: utf-8 -*-
"""Единый источник роли модераторов сервера.

До этого роль модератора настраивалась в РАЗНЫХ местах и жила в РАЗНЫХ
файлах, которые друг о друге не знали:
  * data/reports_<gid>.json        -> mod_role_id   (/report-setup + панель жалоб)
  * data/ticket_notify_<gid>.json  -> mod_role_id   (призыв модеров в тикетах)
  * data/ticket_permissions_<gid>.json -> mod_roles (панель «Тикеты»)
  * data/staff_roles.json          -> moderator_role (заявки в команду)

Владелец выбирал роль на одной странице — остальные системы её не видели
(«настроил, а не работает»). Теперь у бота ОДИН канонический источник —
конфиг репортов (тот же, что пишет /report-setup), а все остальные места
читают через этот модуль и при отсутствии совместимо откатываются на свои
старые файлы (ничего не ломается при обновлении).

Панель вызывает set_mod_role_id() в одном месте — значение подхватывают все.
"""
import json
import os

from logger import get_logger

_log = get_logger('mod_role')


def _reports_cfg_path(guild_id) -> str:
    return f'data/reports_{guild_id}.json'


def _read_json(path):
    try:
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception as _ex:
        _log.debug('read_json %s: %s', path, _ex)
    return {}


def get_mod_role_id(guild_id) -> str:
    """Канонический ID роли модераторов (строка) или '' если не задана.

    Источник истины — конфиг репортов. Если там пусто, по очереди
    подхватываем легаси-значения (ticket_notify / ticket_permissions /
    staff_roles), чтобы настройка с любой старой страницы не терялась.
    """
    gid = str(guild_id or '')
    if not gid:
        return ''

    # 1. Канон: конфиг репортов
    rid = str(_read_json(_reports_cfg_path(gid)).get('mod_role_id') or '').strip()
    if rid.isdigit():
        return rid

    # 2. Легаси: призыв модераторов в тикетах
    rid = str(_read_json(f'data/ticket_notify_{gid}.json').get('mod_role_id') or '').strip()
    if rid.isdigit():
        return rid

    # 3. Легаси: права тикетов (список ролей — берём первую)
    for r in _read_json(f'data/ticket_permissions_{gid}.json').get('mod_roles') or []:
        rid = str(r or '').strip()
        if rid.isdigit():
            return rid

    # 4. Легаси: ручная привязка роли модератора в заявках в команду
    node = _read_json('data/staff_roles.json').get(gid) or {}
    rid = str(node.get('moderator_role') or '').strip()
    if rid.isdigit():
        return rid

    return ''


def set_mod_role_id(guild_id, role_id) -> str:
    """Записать роль модераторов в КАНОНИЧЕСКИЙ конфиг (репортов).

    Туда же зеркалим в легаси-файлы, которые ещё читают существующие коги,
    чтобы система была консистентна немедленно. Возвращает сохранённый ID.
    """
    gid = str(guild_id or '')
    rid = str(role_id or '').strip()
    if rid and not rid.isdigit():
        return ''
    if not gid:
        return ''

    os.makedirs('data', exist_ok=True)

    def _write(path, data):
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    # 1. Канон — конфиг репортов (сохраняем остальные поля)
    try:
        p = _reports_cfg_path(gid)
        cfg = _read_json(p)
        cfg['mod_role_id'] = rid
        _write(p, cfg)
    except Exception as _ex:
        _log.warning('set_mod_role_id: reports cfg: %s', _ex)

    # 2. Зеркало в ticket_notify (призыв модеров читает его напрямую)
    if rid:
        try:
            p = f'data/ticket_notify_{gid}.json'
            d = _read_json(p)
            d['mod_role_id'] = rid
            _write(p, d)
        except Exception as _ex:
            _log.debug('set_mod_role_id: ticket_notify mirror: %s', _ex)

    # 3. Зеркало в staff_roles (заявки в команду)
    if rid:
        try:
            p = 'data/staff_roles.json'
            d = _read_json(p)
            node = d.get(gid) or {}
            node['moderator_role'] = rid
            d[gid] = node
            _write(p, d)
        except Exception as _ex:
            _log.debug('set_mod_role_id: staff_roles mirror: %s', _ex)

    return rid


def resolve_mod_role(guild):
    """Вернуть discord.Role модераторов для гильдии или None."""
    if guild is None:
        return None
    rid = get_mod_role_id(getattr(guild, 'id', ''))
    if not rid:
        return None
    try:
        return guild.get_role(int(rid))
    except Exception:
        return None


def member_is_mod(member, guild=None) -> bool:
    """Есть ли у участника модераторские права/роль (канонический источник).

    База — права Discord (administrator / manage_guild / manage_messages /
    moderate_members / ban / kick); плюс настроенная роль модераторов.
    """
    if member is None:
        return False
    gp = getattr(member, 'guild_permissions', None)
    if gp is not None and (getattr(gp, 'administrator', False)
                           or getattr(gp, 'manage_guild', False)
                           or getattr(gp, 'manage_messages', False)
                           or getattr(gp, 'moderate_members', False)
                           or getattr(gp, 'ban_members', False)
                           or getattr(gp, 'kick_members', False)):
        return True
    g = guild or getattr(member, 'guild', None)
    rid = get_mod_role_id(getattr(g, 'id', '') if g else '')
    if not rid:
        return False
    try:
        return any(str(r.id) == rid for r in (getattr(member, 'roles', None) or []))
    except Exception:
        return False
