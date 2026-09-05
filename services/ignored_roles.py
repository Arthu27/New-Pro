# -*- coding: utf-8 -*-
"""Игнорируемые роли — роли, которые НИКОГДА не дают прав (владелец, 2026-09-05).

Проблема владельца: «облачная» роль (1192970051821772890) выдаётся модераторами
и обычным участникам; у неё стоят Discord-права, из-за которых её носители
считались модераторами/админами панели и могли мутить модеров.

ПРАВИЛА:
  • роль из списка НЕ УЧИТЫВАЕТСЯ НИКАК: её Discord-права не превращают
    носителя в модератора/админа панели (ни по правам, ни по карте ролей);
  • если роль есть у МОДЕРАТОРА — она просто игнорируется: модератор остаётся
    модератором, не «выше других модеров»;
  • права такие люди получают ТОЛЬКО явно: через панель (Права команд,
    карта ролей, модер-роль) — по ДРУГИМ ролям;
  • список настраивается в панели (Доступ → «Игнорируемые роли») — если
    появятся ещё такие роли, владелец добавит их сам.

Хранение: data/ignored_roles.json → {'global': [id, ...]}. Вне файла —
дефолт: только «облачная» роль владельца.
"""
import json
import os

from logger import get_logger

_log = get_logger('ignored_roles')

# Роль владельца, которую НЕ учитывать ни в каком виде (заказ 2026-09-05)
DEFAULT_IGNORED = [1192970051821772890]

_PATH = 'data/ignored_roles.json'
_CACHE = {'ts': 0.0, 'data': None}


def _load():
    try:
        with open(_PATH, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    tmp = _PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _PATH)


def get_ignored(guild_id=None):
    """Множество ID игнорируемых ролей (глобальные + серверные)."""
    try:
        data = _load()
        ids = set(int(x) for x in (data.get('global') or DEFAULT_IGNORED))
        if guild_id is not None:
            row = data.get(str(int(guild_id))) or []
            ids |= set(int(x) for x in row)
        return ids
    except Exception as _ex:
        _log.debug('get_ignored: %s', _ex)
        return set(DEFAULT_IGNORED)


def add(role_id, guild_id=None):
    try:
        rid = int(role_id)
    except (TypeError, ValueError):
        return False
    data = _load()
    key = 'global' if guild_id is None else str(int(guild_id))
    lst = [int(x) for x in (data.get(key) or (DEFAULT_IGNORED if key == 'global' else []))]
    if rid not in lst:
        lst.append(rid)
    data[key] = lst
    _save(data)
    return True


def remove(role_id, guild_id=None):
    try:
        rid = int(role_id)
    except (TypeError, ValueError):
        return False
    data = _load()
    key = 'global' if guild_id is None else str(int(guild_id))
    lst = [int(x) for x in (data.get(key) or (DEFAULT_IGNORED if key == 'global' else []))]
    if rid in lst:
        lst.remove(rid)
        data[key] = lst
        _save(data)
    return True


def effective_permissions(member, guild):
    """Discord-права участника БЕЗ учёта игнорируемых ролей.

    member.guild_permissions — агрегат всех ролей, понять, какая роль дала
    право, нельзя. Поэтому пересобираем права по ролям вручную, выкидывая
    игнорируемые (и @everyone не трогаем — его права остаются).
    """
    try:
        import discord
        ignored = get_ignored(getattr(guild, 'id', None))
        collected = 0
        counted = False
        for role in (getattr(member, 'roles', None) or []):
            try:
                rid = int(getattr(role, 'id', 0) or 0)
            except (TypeError, ValueError) as _ex:
                _log.debug('effective_permissions: id роли: %s', _ex)
                continue
            if rid in ignored:
                counted = True   # роль настоящая, но игнорируется — учтено
                continue
            rp = getattr(role, 'permissions', None)
            if rp is None:
                continue
            try:
                collected |= int(getattr(rp, 'value', 0))
                counted = True
            except Exception as _ex:
                _log.debug('effective_permissions: роль %s: %s', rid, _ex)
        if counted:
            # роли настоящие (discord.Role с permissions) — пересобрали честно
            return discord.Permissions(collected)
        # роли не несут .permissions (упрощённый/фейк-объект) — не выдумываем:
        # возвращаем агрегат Discord как есть (правила игнора неприменимы)
        return getattr(member, 'guild_permissions', None)
    except Exception as _ex:
        _log.debug('effective_permissions: %s', _ex)
        return getattr(member, 'guild_permissions', None)


def is_ignored_role(role_id, guild_id=None):
    """Эта роль — игнорируемая? (для переборов ролей в картах/пингах)"""
    try:
        return int(role_id) in get_ignored(guild_id)
    except (TypeError, ValueError):
        return False
