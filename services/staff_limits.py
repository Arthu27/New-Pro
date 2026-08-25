"""Лимиты действий стаффа — защита сервера от «плохих» модераторов/админов.

Идея: даже если у модератора есть права на бан/чистку, он может сделать
лишь ограниченное количество таких действий в день (по UTC). Владелец
сервера не ограничивается никогда. Счётчики хранятся на диске
(data/staff_limits_<gid>.json), а лимиты — в data/staff_limit_cfg_<gid>.json.

API:
    check_limit(guild_id, user_id, key, amount, role_ids) -> (allowed, used, limit)
        Проверить, можно ли выполнить действие (без записи).
    check_action(guild, actor, key, amount=1) -> (allowed, deny_text)
        Удобный гейт для когов: сам достаёт роли, владельца пропускает.
    record_hit(guild_id, user_id, key, amount) -> None
        Зафиксировать успешно выполненное действие в дневном счётчике.
    get_limits(guild_id) -> dict
        Текущие лимиты гильдии (дефолты + переопределения).
    set_limits(guild_id, **kw) -> dict
        Обновить лимиты (например set_limits(gid, ban=5, clear=200)).

Ключи лимитов — ВСЕ действия стаффа, которыми можно «обнаглеть»
(заказ владельца 2026-08: «лимиты на всё»): наказания + опасные операции.
"""
import json
import os
from datetime import datetime, timezone

from logger import get_logger

_log = get_logger('staff_limits')

# Лимиты по умолчанию (в день, UTC). Подобраны так, чтобы обычной
# модерации хватало с запасом, а «рейдера в правах» они останавливали.
DEFAULT_LIMITS = {
    # ── наказания ──
    'warn': 30,      # предупреждений в день (/warn и ⚡-варн реакцией)
    'mute': 20,      # мутов в день (таймаут/чат/войс/тихий ghostmute)
    'unmute': 30,    # снятий мута в день
    'kick': 6,       # киков в день (команда отключена — лимит на будущее)
    'vkick': 20,     # киков из голосового канала в день
    'ban': 8,        # банов/апелляций в день
    'unban': 10,     # разбанов / снятий апелляции в день
    # ── опасные операции ──
    'clear': 500,    # сообщений, удалённых очисткой, в день
    'nuke': 2,       # пересозданий канала начисто (/nuke) в день
    'raid': 3,       # массовых зачисток недавних входов (/raidcleanup)
    'lockdown': 12,  # каналов, закрытых локдауном, в день
    'dehoist': 5,    # массовых переименований ников (/dehoist) в день
}

# Человеческие названия для сообщений и панели.
ACTION_TITLES = {
    'warn': 'варнов',
    'mute': 'мутов',
    'unmute': 'снятий мута',
    'kick': 'киков',
    'vkick': 'киков из войса',
    'ban': 'банов',
    'unban': 'разбанов',
    'clear': 'сообщений чисткой',
    'nuke': 'пересозданий канала',
    'raid': 'массовых зачисток',
    'lockdown': 'локдаунов',
    'dehoist': 'массовых переименований',
}

# Подсказки к полям в панели (что именно считается).
ACTION_HINTS = {
    'warn': 'варнов в день',
    'mute': 'мутов в день (включая тихие)',
    'unmute': 'снятий мута в день',
    'kick': 'киков в день (отключено — на будущее)',
    'vkick': 'выгонок из голоса в день',
    'ban': 'банов/апелляций в день',
    'unban': 'разбанов в день',
    'clear': 'сообщений чисткой в день',
    'nuke': 'пересозданий канала в день',
    'raid': 'массовых зачисток входов',
    'lockdown': 'закрытых каналов в день',
    'dehoist': 'массовых переименований',
}

# Порядок и группировка полей в панели.
ACTION_GROUPS = [
    ('punish', 'Наказания', ['warn', 'mute', 'unmute', 'kick', 'vkick', 'ban', 'unban']),
    ('heavy', 'Опасные операции', ['clear', 'nuke', 'raid', 'lockdown', 'dehoist']),
]


def action_meta():
    """Метаданные всех действий для панели: группы с полями."""
    return [
        {'key': gkey, 'label': label,
         'items': [{'key': k, 'title': ACTION_TITLES.get(k, k),
                    'hint': ACTION_HINTS.get(k, ''), 'default': DEFAULT_LIMITS[k]}
                   for k in keys if k in DEFAULT_LIMITS]}
        for gkey, label, keys in ACTION_GROUPS
        if any(k in DEFAULT_LIMITS for k in keys)
    ]


def _cfg_path(gid):
    return f'data/staff_limit_cfg_{int(gid)}.json'


def _cnt_path(gid):
    return f'data/staff_limits_{int(gid)}.json'


def _day_key():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else default
    except (OSError, ValueError) as ex:
        _log.debug('staff_limits: битый/недоступный %s: %s', path, ex)
        return default


def _save_json(path, data):
    os.makedirs('data', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, path)


def get_limits(guild_id):
    """Действующие лимиты гильдии (дефолты + переопределения из файла)."""
    cfg = dict(DEFAULT_LIMITS)
    saved = _load_json(_cfg_path(guild_id), {})
    for key, val in saved.items():
        if isinstance(val, int) and val > 0:
            cfg[key] = val
    return cfg


def set_limits(guild_id, **kw):
    """Обновить лимиты гильдии. Возвращает итоговый словарь лимитов."""
    cfg = get_limits(guild_id)
    for key, val in kw.items():
        if key in cfg and isinstance(val, int) and val > 0:
            cfg[key] = val
    saved = _load_json(_cfg_path(guild_id), {})
    saved.update({k: cfg[k] for k in kw if k in cfg})
    _save_json(_cfg_path(guild_id), saved)
    return cfg


def _today_counts(guild_id):
    data = _load_json(_cnt_path(guild_id), {})
    day = _day_key()
    per_day = data.get(day)
    if not isinstance(per_day, dict):
        per_day = {}
    return data, day, per_day


def check_limit(guild_id, user_id, key, amount=1, role_ids=None):
    """Разрешено ли действие: (allowed, used_today, limit).

    role_ids — роли модератора: если у каких-то из них есть свои
    переопределения, действует САМЫЙ СТРОГИЙ лимит (обойти лимит,
    добавив себе лишнюю роль, нельзя).
    """
    if role_ids:
        limit = limits_for_roles(guild_id, role_ids).get(key, 0)
    else:
        limit = get_limits(guild_id).get(key, 0)
    if limit <= 0:
        return True, 0, 0                       # лимит не задан — не ограничиваем
    _data, _day, per_day = _today_counts(guild_id)
    mine = per_day.get(str(user_id)) or {}
    used = int(mine.get(key, 0) or 0)
    return (used + amount) <= limit, used, limit


def check_action(guild, actor, key, amount=1):
    """Гейт для когов: (allowed, deny_text). deny_text готов для показа.

    Сам достаёт роли модератора, владельца гильдии пропускает всегда,
    любая ошибка НЕ мешает модерации (защита не ломает работу).
    """
    try:
        if not guild or not actor:
            return True, None
        if getattr(actor, 'id', 0) == getattr(guild, 'owner_id', 0):
            return True, None
        role_ids = [r.id for r in (getattr(actor, 'roles', None) or [])
                    if getattr(r, 'id', None) != getattr(guild, 'id', None)]
        allowed, used, lim = check_limit(guild.id, actor.id, key, amount,
                                         role_ids=role_ids)
        if allowed:
            return True, None
        what = ACTION_TITLES.get(key, 'действий')
        return False, (f'Дневной лимит исчерпан: {lim} {what} в день '
                       f'(уже {used}). Сброс — после полуночи по UTC.')
    except Exception as ex:
        _log.debug('check_action(%s): %s', key, ex)
        return True, None


def record_hit(guild_id, user_id, key, amount=1):
    """Записать успешное действие в дневной счётчик."""
    try:
        data, day, per_day = _today_counts(guild_id)
        mine = per_day.get(str(user_id)) or {}
        mine[key] = int(mine.get(key, 0) or 0) + int(amount)
        per_day[str(user_id)] = mine
        data[day] = per_day
        # храним только сегодня и вчера — файл остаётся маленьким
        for d_k in [k for k in data.keys() if k != day]:
            data.pop(d_k, None)
        _save_json(_cnt_path(guild_id), data)
    except Exception as ex:                     # счётчик не должен ронять модерацию
        _log.debug('record_hit(): %s', ex)


def status_text(guild_id, user_id):
    """Строка статуса для показа модератору: сколько он уже потратил."""
    lim = get_limits(guild_id)
    _data, _day, per_day = _today_counts(guild_id)
    mine = per_day.get(str(user_id)) or {}
    short = {'warn': 'варны', 'mute': 'муты', 'unmute': 'размуты',
             'kick': 'кики', 'vkick': 'войс-кики', 'ban': 'баны',
             'unban': 'разбаны', 'nuke': 'nuke', 'raid': 'зачистки',
             'lockdown': 'локдауны', 'dehoist': 'dehoist'}
    parts = []
    for key, name in short.items():
        if lim.get(key):
            parts.append(f'{name} {mine.get(key, 0)}/{lim[key]}')
    if lim.get('clear'):
        parts.append(f"чистка {mine.get('clear', 0)}/{lim['clear']} сообщ.")
    return ' · '.join(parts) if parts else 'без лимитов'


# ─── Пер-рольные лимиты (заказ владельца 2026-08: «выбирать роли») ──────
# Формат data/staff_limit_roles_<gid>.json: {"<role_id>": {"ban": 3, ...}}
# Действует для модератора, если ОДНА ИЗ ЕГО ролей имеет переопределение;
# при нескольких — побеждает самый строгий (min) на каждый ключ.

def _roles_path(gid):
    return f'data/staff_limit_roles_{int(gid)}.json'


def get_role_limits(guild_id):
    """Все переопределения по ролям: {role_id(str): {ключ: лимит}}."""
    saved = _load_json(_roles_path(guild_id), {})
    out = {}
    for rid, ov in saved.items():
        if isinstance(ov, dict):
            clean = {k: int(v) for k, v in ov.items()
                     if k in DEFAULT_LIMITS and isinstance(v, int) and v > 0}
            if clean:
                out[str(rid)] = clean
    return out


def set_role_limits(guild_id, role_id, **kw):
    """Задать лимиты для конкретной роли. Возвращает её итоговые лимиты."""
    saved = _load_json(_roles_path(guild_id), {})
    cur = saved.get(str(role_id)) or {}
    for key, val in kw.items():
        if key in DEFAULT_LIMITS and isinstance(val, int) and val > 0:
            cur[key] = int(val)
    saved[str(role_id)] = cur
    _save_json(_roles_path(guild_id), saved)
    return cur


def clear_role_limits(guild_id, role_id):
    """Убрать переопределение роли — она живёт по глобальным лимитам."""
    saved = _load_json(_roles_path(guild_id), {})
    if str(role_id) in saved:
        saved.pop(str(role_id), None)
        _save_json(_roles_path(guild_id), saved)
        return True
    return False


def limits_for_roles(guild_id, role_ids=()):
    """Эффективные лимиты пользователя: глобальные, ужатые его ролями.

    На каждый ключ берём МИНИМУМ среди глобального и всех переопределений
    ролей пользователя — выдать себе «мягкую» роль нельзя.
    """
    cfg = dict(get_limits(guild_id))
    overrides = get_role_limits(guild_id)
    for rid in role_ids or ():
        ov = overrides.get(str(rid))
        if not ov:
            continue
        for k, v in ov.items():
            if k in cfg:
                cfg[k] = min(cfg[k], v)
    return cfg
