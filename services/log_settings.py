# -*- coding: utf-8 -*-
"""Какие логи нужны серверу: включение категорий и автосоздание каналов.

Заказ владельца (2026-08): «логи не должны создаваться сами по себе —
в панели настрою, какой нужен, какой не нужен». Отсюда два правила:

  1) enabled  — логируется ли категория вообще (дефолт: ДА, как было);
  2) autocreate — разрешено ли боту САМОМУ создавать недостающий
     лог-канал (дефолт: НЕТ — ничего само по себе не появляется).

Хранилище: data/log_settings_<gid>.json
    {"enabled": {"mod": true, ...}, "autocreate": {"mod": false, ...},
     "channels": {"mod": "123456789", ...}}

Бот читает файл на каждом событии (cogs/logs.py) — панель сохранила,
изменение применилось мгновенно, без рестарта.

  3) channels — куда писать категорию: ID выбранного канала ('' = авто,
     прежний поиск по имени). Выбранный канал бот никогда не создаёт —
     только использует существующий (заказ владельца 2026-08).
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
    ('nick',     'Никнеймы',     '🏷'),
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
    channels = {key: '' for key, _l, _e in LOG_CATEGORIES}       # '' = авто (поиск по имени)
    for key, val in (saved.get('enabled') or {}).items():
        enabled[str(key)] = bool(val)
    for key, val in (saved.get('autocreate') or {}).items():
        autocreate[str(key)] = bool(val)
    for key, val in (saved.get('channels') or {}).items():
        if str(val or '').strip().isdigit():
            channels[str(key)] = str(val).strip()
    return {'enabled': enabled, 'autocreate': autocreate, 'channels': channels}


def target_channel_id(gid, category):
    """ID канала, выбранного для категории ('' — авто)."""
    return get_log_settings(gid)['channels'].get(str(category), '') or ''


def category_enabled(gid, category):
    """Логируется ли категория (нет файла — да, прежнее поведение)."""
    return bool(get_log_settings(gid)['enabled'].get(str(category), True))


def autocreate_allowed(gid, category):
    """Разрешено ли СОЗДАНИЕ недостающего канала (нет файла — НЕТ)."""
    return bool(get_log_settings(gid)['autocreate'].get(str(category), False))


def set_log_settings(gid, enabled=None, autocreate=None, channels=None):
    """Сохранить изменения (частично). Возвращает итоговые настройки."""
    saved = _load(gid)
    cur_en = dict(saved.get('enabled') or {})
    cur_ac = dict(saved.get('autocreate') or {})
    cur_ch = dict(saved.get('channels') or {})
    if isinstance(enabled, dict):
        for key, val in enabled.items():
            cur_en[str(key)] = bool(val)
    if isinstance(autocreate, dict):
        for key, val in autocreate.items():
            cur_ac[str(key)] = bool(val)
    if isinstance(channels, dict):
        for key, val in channels.items():
            cur_ch[str(key)] = str(val or '').strip() if str(val or '').strip().isdigit() else ''
    _save(gid, {'enabled': cur_en, 'autocreate': cur_ac, 'channels': cur_ch})
    return get_log_settings(gid)


# ── «Удалил канал — значит, не нужен» (заказ владельца 2026-08-25) ──────
# Раньше: владелец удалял автосозданный лог-канал, а бот честно создавал
# его заново при следующем событии. Теперь: однажды автосозданный канал,
# исчезнувший с сервера, помечается удалённым и больше НЕ воссоздаётся.
# Вернуть логи может только явная настройка канала в панели.

def _ac_block(gid):
    return dict(_load(gid).get('ac') or {})


def _ac_save(gid, sub):
    data = _load(gid)
    data['ac'] = sub
    _save(gid, data)


def autocreate_note(gid, cat, ch_id):
    """Запомнить: канал этой категории создал сам бот (id)."""
    sub = _ac_block(gid)
    created = dict(sub.get('created') or {})
    created[str(cat)] = str(ch_id)
    sub['created'] = created
    _ac_save(gid, sub)


def autocreate_is_dead(gid, cat, guild_has=None):
    """Канал категории уже создавался ботом и был удалён владельцем?

    guild_has — callable(id)->bool (существует ли канал), чтобы не тащить
    discord в сервис. Первый же «пропавший» канал помечает категорию
    мёртвой — навсегда (до явной настройки в панели).
    """
    sub = _ac_block(gid)
    cat = str(cat)
    cid = (sub.get('created') or {}).get(cat)
    if not cid:
        return False
    if cat in (sub.get('dead') or {}):
        return True
    if guild_has is not None and not guild_has(cid):
        dead = dict(sub.get('dead') or {})
        dead[cat] = True
        sub['dead'] = dead
        _ac_save(gid, sub)
        _log.info('логи: канал категории %s удалён владельцем — больше '
                 'не создаю его сам', cat)
        return True
    return False


def autocreate_forget(gid, cat):
    """Владелец явно настроил категорию в панели — снять маркеры."""
    sub = _ac_block(gid)
    changed = False
    for block in ('created', 'dead'):
        b = dict(sub.get(block) or {})
        if str(cat) in b:
            del b[str(cat)]
            sub[block] = b
            changed = True
    if changed:
        _ac_save(gid, sub)
