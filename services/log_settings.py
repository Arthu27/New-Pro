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

# Две группы панели «Логи сервера» — по веткам Discord:
#   #・логи   → сообщения / войсы / никнеймы / зашёл-вышел / остальное
#   #・отчеты → баны / муты войс+чат / снятие·ЧС стаффа / варны
# Наказания специально разделены: не одна «модерация».
LOG_GROUPS = (
    ('logs', 'Логи', '🧵',
     'Ветки канала «логи»: сообщения, войсы, никнеймы, зашёл/вышел, остальное.',
     (
         ('message', 'Сообщения', '💬'),
         ('voice',   'Войсы', '🔊'),
         ('nick',    'Никнеймы', '🏷'),
         ('member',  'Зашёл / вышел', '👋'),
         ('rest',    'Остальное', '📋'),
     )),
    ('reports', 'Отчёты', '📑',
     'Ветки канала «отчёты»: баны, муты войс/чат, снятие/ЧС стаффа, варны.',
     (
         ('ban',   'Баны', '🔨'),
         ('mute',  'Муты войс / чат', '🔇'),
         ('staff', 'Снятие / ЧС стаффа', '🚷'),
         ('warn',  'Варны', '⚠'),
     )),
)

LOG_CATEGORIES = tuple(
    cat for _g, _gl, _ge, _gh, cats in LOG_GROUPS for cat in cats
)

# Старые ключи журнала/настроек — свёртка и миграция, в панели не показываем.
_LEGACY_CANONICAL = {
    'mod', 'punish', 'channel', 'role', 'invite', 'сервер', 'automod', 'proof',
}

# Канонические ключи панели. Слушатели Discord часто передают русское имя
# канала («модерация») или старый ключ («guild») — без свёртки enabled
# смотрит в неизвестный ключ и по умолчанию остаётся True, а autocreate
# (дефолт False) никогда не срабатывает для той же категории.
_CANONICAL = {key for key, _l, _e in LOG_CATEGORIES} | _LEGACY_CANONICAL
_CATEGORY_ALIASES = {
    'модерация': 'mod',
    'moderasyon': 'mod',
    'moderation': 'mod',
    'mod-log': 'mod',
    'участники': 'member',
    'members': 'member',
    'member-log': 'member',
    'никнеймы': 'nick',
    'ник': 'nick',
    'nickname': 'nick',
    'nicknames': 'nick',
    'наказания': 'punish',
    'punishment': 'punish',
    'punishments': 'punish',
    'сообщения': 'message',
    'messages': 'message',
    'message-log': 'message',
    'голос': 'voice',
    'войсы': 'voice',
    'ses': 'voice',
    'voice-log': 'voice',
    'каналы': 'channel',
    'channels': 'channel',
    'роли': 'role',
    'roles': 'role',
    'приглашения': 'invite',
    'invites': 'invite',
    'guild': 'сервер',
    'server': 'сервер',
    'автоматически': 'automod',
    'автомод': 'automod',
    'доказательства': 'proof',
    'demki': 'proof',
    'демки': 'proof',
    'баны': 'ban',
    'бан': 'ban',
    'bans': 'ban',
    'муты': 'mute',
    'мут': 'mute',
    'mutes': 'mute',
    'варны': 'warn',
    'варн': 'warn',
    'warns': 'warn',
    'стафф': 'staff',
    'чс': 'staff',
    'остальное': 'rest',
    'прочее': 'rest',
}

# Куда писать в Discord: старые смешанные категории → новые ветки.
# «mod» нарочно не трогаем: журнал и тесты ждут ключ mod.
_DEST = {
    'channel': 'rest',
    'role': 'rest',
    'invite': 'rest',
    'сервер': 'rest',
    'automod': 'rest',
    'proof': 'rest',
    'punish': 'warn',
}


def canonical_category(category):
    """Русское/legacy имя категории → ключ панели (mod, member, …).

    Неизвестные ключи (ticket-log, ai-alerts) оставляем как есть —
    у них нет тумблера в «Логах сервера».
    """
    raw = str(category or '').strip()
    if not raw:
        return raw
    if raw in _CANONICAL:
        return raw
    low = raw.lower()
    if low in _CANONICAL:
        return low
    return _CATEGORY_ALIASES.get(raw) or _CATEGORY_ALIASES.get(low) or raw


def dest_category(category):
    """Куда писать в Discord: старые смешанные ключи → ветка панели."""
    cat = canonical_category(category)
    return _DEST.get(cat, cat)


def _fold_bool_map(src):
    """Слить alias-ключи в канонические; точный канон побеждает alias."""
    folded, exact = {}, {}
    for key, val in (src or {}).items():
        ck = canonical_category(str(key))
        if str(key) == ck:
            exact[ck] = bool(val)
        else:
            folded[ck] = bool(val)
    folded.update(exact)
    return folded


def _fold_channel_map(src):
    folded, exact = {}, {}
    for key, val in (src or {}).items():
        cid = str(val or '').strip()
        if not cid.isdigit():
            continue
        ck = canonical_category(str(key))
        if str(key) == ck:
            exact[ck] = cid
        else:
            folded[ck] = cid
    folded.update(exact)
    return folded


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


def _inherit_split(enabled, autocreate, channels, saved):
    """Старая «модерация/наказания/сервер» → новые ветки, если те ещё пустые.

    ID не выдумываем: копируем только то, что уже выбрано в панели.
    """
    saved_en = {canonical_category(k) for k in (saved.get('enabled') or {})}
    saved_ac = {canonical_category(k) for k in (saved.get('autocreate') or {})}
    saved_ch = {canonical_category(k) for k in (saved.get('channels') or {})}
    if 'ban' not in saved_en and 'mod' in enabled:
        enabled['ban'] = bool(enabled.get('mod', True))
        enabled['mute'] = bool(enabled.get('mod', True))
    if 'warn' not in saved_en:
        if 'punish' in enabled:
            enabled['warn'] = bool(enabled.get('punish', True))
        elif 'mod' in enabled:
            enabled['warn'] = bool(enabled.get('mod', True))
    if 'rest' not in saved_en:
        leftovers = [enabled[k] for k in (
            'channel', 'role', 'invite', 'сервер', 'automod', 'proof'
        ) if k in enabled]
        if leftovers and not any(leftovers):
            enabled['rest'] = False
    if 'ban' not in saved_ac and 'mod' in autocreate:
        autocreate['ban'] = bool(autocreate.get('mod'))
        autocreate['mute'] = bool(autocreate.get('mod'))
    if 'warn' not in saved_ac:
        if 'punish' in autocreate:
            autocreate['warn'] = bool(autocreate.get('punish'))
        elif 'mod' in autocreate:
            autocreate['warn'] = bool(autocreate.get('mod'))
    if 'ban' not in saved_ch and channels.get('mod'):
        channels['ban'] = channels['mod']
        channels['mute'] = channels.get('mute') or channels['mod']
    if 'mute' not in saved_ch and not channels.get('mute') and channels.get('mod'):
        channels['mute'] = channels['mod']
    if 'warn' not in saved_ch and not channels.get('warn'):
        channels['warn'] = channels.get('punish') or ''
    if 'rest' not in saved_ch and not channels.get('rest'):
        for k in ('channel', 'role', 'invite', 'сервер', 'automod', 'proof'):
            if channels.get(k):
                channels['rest'] = channels[k]
                break
    return enabled, autocreate, channels


def get_log_settings(gid):
    """Настройки категории по умолчанию + сохранённые переопределения."""
    saved = _load(gid)
    enabled = {key: True for key, _l, _e in LOG_CATEGORIES}
    autocreate = {key: False for key, _l, _e in LOG_CATEGORIES}  # ничего само не создаётся
    channels = {key: '' for key, _l, _e in LOG_CATEGORIES}       # '' = авто (поиск по имени)
    enabled.update(_fold_bool_map(saved.get('enabled')))
    autocreate.update(_fold_bool_map(saved.get('autocreate')))
    channels.update(_fold_channel_map(saved.get('channels')))
    enabled, autocreate, channels = _inherit_split(
        enabled, autocreate, channels, saved)
    return {'enabled': enabled, 'autocreate': autocreate, 'channels': channels}


def target_channel_id(gid, category):
    """ID канала, выбранного для категории ('' — авто)."""
    cat = canonical_category(category)
    return get_log_settings(gid)['channels'].get(cat, '') or ''


def category_enabled(gid, category):
    """Логируется ли категория (нет файла — да, прежнее поведение)."""
    cat = canonical_category(category)
    return bool(get_log_settings(gid)['enabled'].get(cat, True))


def autocreate_allowed(gid, category):
    """Разрешено ли СОЗДАНИЕ недостающего канала (нет файла — НЕТ)."""
    cat = canonical_category(category)
    return bool(get_log_settings(gid)['autocreate'].get(cat, False))


def set_log_settings(gid, enabled=None, autocreate=None, channels=None):
    """Сохранить изменения (частично). Возвращает итоговые настройки."""
    saved = _load(gid)
    cur_en = dict(saved.get('enabled') or {})
    cur_ac = dict(saved.get('autocreate') or {})
    cur_ch = dict(saved.get('channels') or {})
    if isinstance(enabled, dict):
        for key, val in enabled.items():
            cur_en[canonical_category(key)] = bool(val)
    if isinstance(autocreate, dict):
        for key, val in autocreate.items():
            cur_ac[canonical_category(key)] = bool(val)
    if isinstance(channels, dict):
        for key, val in channels.items():
            cid = str(val or '').strip()
            cur_ch[canonical_category(key)] = cid if cid.isdigit() else ''
    extra = {k: v for k, v in saved.items()
             if k not in ('enabled', 'autocreate', 'channels')}
    _save(gid, {
        **extra,
        'enabled': _fold_bool_map(cur_en),
        'autocreate': _fold_bool_map(cur_ac),
        'channels': _fold_channel_map(cur_ch),
    })
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
