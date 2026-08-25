# -*- coding: utf-8 -*-
"""Какие логи нужны серверу: включение категорий и автосоздание каналов.

Заказ владельца (2026-08): «логи не должны создаваться сами по себе —
в панели настрою, какой нужен, какой не нужен». Отсюда два правила:

  1) enabled  — логируется ли категория вообще (дефолт: ДА, как было);
  2) autocreate — разрешено ли боту САМОМУ создавать недостающий
     лог-канал (дефолт: НЕТ — ничего само по себе не появляется).

Хранилище: data/log_settings_<gid>.json
    {"enabled": {"mod": true, ...}, "autocreate": {"mod": false, ...}}

Бот читает файл на каждом событии (cogs/logs.py) — панель сохранила,
изменение применилось мгновенно, без рестарта.
"""
import json
import os

from logger import get_logger

_log = get_logger('log_settings')

# Канонический список категорий (зеркалит CATEGORIES из cogs/logs.py,
# чтобы панель не зависела от импорта дискорд-когов).
LOG_CATEGORIES = (
    ('mod',      'Модерация',    '🛡'),
    ('member',   'Участники',    '👋'),
    ('message',  'Сообщения',    '💬'),
    ('voice',    'Голос',        '🔊'),
    ('channel',  'Каналы',       '🗂'),
    ('role',     'Роли',         '🎭'),
    ('invite',   'Приглашения',  '🔗'),
    ('сервер',   'Сервер',       '🏠'),
    ('automod',  'Автомодерация', '⚔'),
    ('proof',    'Доказательства', '📸'),
)


def _path(gid):
    return f'data/log_settings_{int(gid)}.json'


def _load(gid):
    if not os.path.exists(_path(gid)):
        return {}
    try:
        with open(_path(gid), 'r', encoding='utf-8') as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as ex:
        _log.debug('log_settings: битый файл %s: %s', _path(gid), ex)
        return {}


def _save(gid, data):
    os.makedirs('data', exist_ok=True)
    tmp = _path(gid) + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, _path(gid))


def get_log_settings(gid):
    """Настройки категории по умолчанию + сохранённые переопределения."""
    saved = _load(gid)
    enabled = {key: True for key, _l, _e in LOG_CATEGORIES}
    autocreate = {key: False for key, _l, _e in LOG_CATEGORIES}  # ничего само не создаётся
    for key, val in (saved.get('enabled') or {}).items():
        enabled[str(key)] = bool(val)
    for key, val in (saved.get('autocreate') or {}).items():
        autocreate[str(key)] = bool(val)
    return {'enabled': enabled, 'autocreate': autocreate}


def category_enabled(gid, category):
    """Логируется ли категория (нет файла — да, прежнее поведение)."""
    return bool(get_log_settings(gid)['enabled'].get(str(category), True))


def autocreate_allowed(gid, category):
    """Разрешено ли СОЗДАНИЕ недостающего канала (нет файла — НЕТ)."""
    return bool(get_log_settings(gid)['autocreate'].get(str(category), False))


def set_log_settings(gid, enabled=None, autocreate=None):
    """Сохранить изменения (частично). Возвращает итоговые настройки."""
    saved = _load(gid)
    cur_en = dict(saved.get('enabled') or {})
    cur_ac = dict(saved.get('autocreate') or {})
    if isinstance(enabled, dict):
        for key, val in enabled.items():
            cur_en[str(key)] = bool(val)
    if isinstance(autocreate, dict):
        for key, val in autocreate.items():
            cur_ac[str(key)] = bool(val)
    _save(gid, {'enabled': cur_en, 'autocreate': cur_ac})
    return get_log_settings(gid)
