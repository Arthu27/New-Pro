"""Лимиты действий стаффа — защита сервера от «плохих» модераторов/админов.

Идея: даже если у модератора есть права на бан/чистку, он может сделать
лишь ограниченное количество таких действий в день (по UTC). Владелец
сервера не ограничивается никогда. Счётчики хранятся на диске
(data/staff_limits_<gid>.json), а лимиты — в data/staff_limit_cfg_<gid>.json.

API:
    check_limit(guild_id, user_id, key, amount) -> (allowed, used, limit)
        Проверить, можно ли выполнить действие (без записи).
    record_hit(guild_id, user_id, key, amount) -> None
        Зафиксировать успешно выполненное действие в дневном счётчике.
    get_limits(guild_id) -> dict
        Текущие лимиты гильдии (дефолты + переопределения).
    set_limits(guild_id, **kw) -> dict
        Обновить лимиты (например set_limits(gid, ban=5, clear=200)).

Ключи лимитов: 'ban' — банов в день; 'clear' — сообщений чисткой в день.
"""
import json
import os
from datetime import datetime, timezone

from logger import get_logger

_log = get_logger('staff_limits')

# Лимиты по умолчанию (в день, UTC). Подобраны так, чтобы обычной
# модерации хватало с запасом, а «рейдера в правах» они останавливали.
DEFAULT_LIMITS = {
    'ban': 8,       # банов в день на модератора
    'clear': 500,   # сообщений, удалённых очисткой, в день на модератора
}


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


def check_limit(guild_id, user_id, key, amount=1):
    """Разрешено ли действие: (allowed, used_today, limit)."""
    limit = get_limits(guild_id).get(key, 0)
    if limit <= 0:
        return True, 0, 0                       # лимит не задан — не ограничиваем
    _data, _day, per_day = _today_counts(guild_id)
    mine = per_day.get(str(user_id)) or {}
    used = int(mine.get(key, 0) or 0)
    return (used + amount) <= limit, used, limit


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
    parts = []
    if lim.get('ban'):
        parts.append(f"баны {mine.get('ban', 0)}/{lim['ban']}")
    if lim.get('clear'):
        parts.append(f"чистка {mine.get('clear', 0)}/{lim['clear']} сообщ.")
    return ' · '.join(parts) if parts else 'без лимитов'
