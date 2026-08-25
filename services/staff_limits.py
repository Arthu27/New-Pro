"""Лимиты действий стаффа — защита сервера от «плохих» модераторов/админов.

Идея: даже если у модератора есть права на бан/чистку, он может сделать
лишь ограниченное количество таких действий за период. Период выбирается
в панели: «за N часов» или «за N дней» — глобально и ОТДЕЛЬНО для каждой
роли (заказ владельца 2026-08). Владелец сервера не ограничивается никогда.

Счётчики: data/staff_limits_<gid>.json  {uid: {действие: [ts, ts, ...]}}
    (метки времени; всё старше 31 дня подчищается автоматически)
Лимиты:   data/staff_limit_cfg_<gid>.json   {"limits": {...}, "windows": {действие: сек}}
Роли:     data/staff_limit_roles_<gid>.json {rid: {"limits": {...}, "windows": {...}}}
Старый формат файлов (плоский {ban: 8}) читается как лимиты без окон.

API:
    check_limit(guild_id, user_id, key, amount, role_ids) -> (allowed, used, limit)
    check_action(guild, actor, key, amount=1) -> (allowed, deny_text)
        Гейт для когов: сам достаёт роли, владельца пропускает.
    record_hit(guild_id, user_id, key, amount) -> None
    get_limits / set_limits(**kw)          — числа лимитов
    get_windows / set_windows(**kw)        — окна в секундах (3600..31 день)
    human_window(sec)                      — «2 ч» / «7 дн.» для сообщений

Ключи лимитов — ВСЕ действия стаффа, которыми можно «обнаглеть»:
наказания + опасные операции (12 действий).
"""
import json
import os
import time as _time
from datetime import datetime, timezone

from logger import get_logger

_log = get_logger('staff_limits')

DEFAULT_WINDOW = 24 * 3600      # окно по умолчанию: 1 день
MIN_WINDOW = 3600               # минимум: 1 час
MAX_WINDOW = 31 * 24 * 3600     # максимум: 31 день
_MAX_TS = 1000                  # сколько меток держать на действие

# Лимиты по умолчанию (за окно, по умолчанию — день). Подобраны так, чтобы
# обычной модерации хватало с запасом, а «рейдера в правах» останавливали.
DEFAULT_LIMITS = {
    # ── наказания ──
    'warn': 30,      # предупреждений (/warn и ПКМ-варн)
    'mute': 20,      # мутов (таймаут/чат/войс/тихий ghostmute)
    'unmute': 30,    # снятий мута
    'kick': 6,       # киков (команда отключена — лимит на будущее)
    'vkick': 20,     # киков из голосового канала
    'ban': 8,        # банов/апелляций
    'unban': 10,     # разбанов / снятий апелляции
    # ── опасные операции ──
    'clear': 500,    # сообщений, удалённых очисткой
    'nuke': 2,       # пересозданий канала начисто (/nuke)
    'raid': 3,       # массовых зачисток недавних входов (/raidcleanup)
    'lockdown': 12,  # каналов, закрытых локдауном
    'dehoist': 5,    # массовых переименований ников (/dehoist)
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
    'warn': 'варнов',
    'mute': 'мутов (включая тихие)',
    'unmute': 'снятий мута',
    'kick': 'киков (отключено — на будущее)',
    'vkick': 'выгонок из голоса',
    'ban': 'банов/апелляций',
    'unban': 'разбанов',
    'clear': 'сообщений чисткой',
    'nuke': 'пересозданий канала',
    'raid': 'массовых зачисток входов',
    'lockdown': 'закрытых каналов',
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


def human_window(sec):
    """Человекочитаемое окно: 3600 → «1 ч», 172800 → «2 дн.»."""
    try:
        sec = int(sec)
    except (TypeError, ValueError):
        sec = DEFAULT_WINDOW
    if sec % 86400 == 0:
        return f'{sec // 86400} дн.'
    return f'{max(1, sec // 3600)} ч'


def _now():
    """Текущее время (отдельная функция — для тестов_WINDOW)."""
    return _time.time()


def _cfg_path(gid):
    return f'data/staff_limit_cfg_{int(gid)}.json'


def _cnt_path(gid):
    return f'data/staff_limits_{int(gid)}.json'


def _roles_path(gid):
    return f'data/staff_limit_roles_{int(gid)}.json'


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


def _clean_limits(raw):
    """{ключ: число>0} только для известных действий."""
    if not isinstance(raw, dict):
        return {}
    return {k: int(v) for k, v in raw.items()
            if k in DEFAULT_LIMITS and isinstance(v, int) and v > 0}


def _clean_windows(raw):
    """{ключ: секунды в [MIN_WINDOW, MAX_WINDOW]} только для известных действий."""
    if not isinstance(raw, dict):
        return {}
    return {k: max(MIN_WINDOW, min(MAX_WINDOW, int(v))) for k, v in raw.items()
            if k in DEFAULT_LIMITS and isinstance(v, int) and v > 0}


# ─── Глобальные лимиты и окна ───────────────────────────────────────────

def get_limits(guild_id):
    """Действующие лимиты гильдии (дефолты + переопределения из файла)."""
    cfg = dict(DEFAULT_LIMITS)
    saved = _load_json(_cfg_path(guild_id), {})
    saved_limits = saved.get('limits') if isinstance(saved.get('limits'), dict) else saved
    cfg.update(_clean_limits(saved_limits))
    return cfg


def get_windows(guild_id):
    """Действующие окна гильдии в секундах (дефолт — 1 день)."""
    win = {key: DEFAULT_WINDOW for key in DEFAULT_LIMITS}
    saved = _load_json(_cfg_path(guild_id), {})
    win.update(_clean_windows(saved.get('windows')))
    return win


def _write_cfg(guild_id, limits_patch=None, windows_patch=None):
    saved = _load_json(_cfg_path(guild_id), {})
    if 'limits' not in saved or not isinstance(saved.get('limits'), dict):
        # миграция старого плоского формата {ban: 8} → {"limits": {...}}
        legacy = _clean_limits(saved)
        saved = {'limits': legacy}
    saved.setdefault('limits', {})
    if limits_patch:
        saved['limits'].update(_clean_limits(limits_patch))
    if windows_patch:
        saved.setdefault('windows', {})
        saved['windows'].update(_clean_windows(windows_patch))
    _save_json(_cfg_path(guild_id), saved)
    return saved


def set_limits(guild_id, **kw):
    """Обновить лимиты гильдии (например set_limits(gid, ban=5))."""
    _write_cfg(guild_id, limits_patch=kw)
    return get_limits(guild_id)


def set_windows(guild_id, **kw):
    """Обновить окна гильдии в СЕКУНДАХ (например set_windows(gid, ban=3600))."""
    _write_cfg(guild_id, windows_patch=kw)
    return get_windows(guild_id)


# ─── Счётчики (метки времени) ───────────────────────────────────────────

def _hits(guild_id, user_id, key):
    """Метки времени действия (вычищаем всё старше MAX_WINDOW)."""
    data = _load_json(_cnt_path(guild_id), {})
    mine = data.get(str(user_id))
    if not isinstance(mine, dict):
        return [], data
    lst = mine.get(key)
    if not isinstance(lst, list):
        return [], data
    floor = _now() - MAX_WINDOW - 60
    fresh = [t for t in lst if isinstance(t, (int, float)) and t > floor]
    return fresh, data


def _count_within(hits, window):
    edge = _now() - max(MIN_WINDOW, min(MAX_WINDOW, int(window)))
    return sum(1 for t in hits if t > edge)


def check_limit(guild_id, user_id, key, amount=1, role_ids=None):
    """Разрешено ли действие: (allowed, used_in_window, limit).

    role_ids — роли модератора: если у каких-то из них есть свои
    переопределения, действует САМЫЙ СТРОГИЙ лимит/окно (обойти лимит,
    добавив себе лишнюю роль, нельзя).
    """
    if role_ids:
        lim_map, win_map = effective_limits(guild_id, role_ids)
    else:
        lim_map, win_map = get_limits(guild_id), get_windows(guild_id)
    limit = lim_map.get(key, 0)
    if limit <= 0:
        return True, 0, 0                       # лимит не задан — не ограничиваем
    window = win_map.get(key, DEFAULT_WINDOW)
    hits, _data = _hits(guild_id, user_id, key)
    used = _count_within(hits, window)
    return (used + amount) <= limit, used, limit


def record_hit(guild_id, user_id, key, amount=1):
    """Записать успешное действие в счётчик (метками времени)."""
    try:
        ts = _now()
        data = _load_json(_cnt_path(guild_id), {})
        if not isinstance(data.get(str(user_id)), dict):
            # старый формат {день: {uid: ...}} или мусор — начинаем чистый лист
            data[str(user_id)] = {}
        mine = data[str(user_id)]
        lst = mine.get(key) if isinstance(mine.get(key), list) else []
        for _ in range(max(1, int(amount))):
            lst.append(ts)
        floor = ts - MAX_WINDOW - 60
        lst = [t for t in lst if isinstance(t, (int, float)) and t > floor]
        mine[key] = lst[-_MAX_TS:]
        data[str(user_id)] = mine
        _save_json(_cnt_path(guild_id), data)
    except Exception as ex:                     # счётчик не должен ронять модерацию
        _log.debug('record_hit(): %s', ex)


def status_text(guild_id, user_id):
    """Строка статуса для показа модератору: сколько он уже потратил."""
    lim = get_limits(guild_id)
    win = get_windows(guild_id)
    short = {'warn': 'варны', 'mute': 'муты', 'unmute': 'размуты',
             'kick': 'кики', 'vkick': 'войс-кики', 'ban': 'баны',
             'unban': 'разбаны', 'nuke': 'nuke', 'raid': 'зачистки',
             'lockdown': 'локдауны', 'dehoist': 'dehoist'}
    parts = []
    for key, name in short.items():
        if lim.get(key):
            hits, _d = _hits(guild_id, user_id, key)
            used = _count_within(hits, win.get(key, DEFAULT_WINDOW))
            parts.append(f'{name} {used}/{lim[key]}')
    if lim.get('clear'):
        hits, _d = _hits(guild_id, user_id, 'clear')
        used = _count_within(hits, win.get('clear', DEFAULT_WINDOW))
        parts.append(f'чистка {used}/{lim["clear"]} сообщ.')
    return ' · '.join(parts) if parts else 'без лимитов'


# ─── Гейт для когов ─────────────────────────────────────────────────────

def check_action(guild, actor, key, amount=1):
    """(allowed, deny_text). deny_text готов для показа модератору.

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
        lim_map, win_map = effective_limits(guild.id, role_ids)
        limit = lim_map.get(key, 0)
        if limit <= 0:
            return True, None
        window = win_map.get(key, DEFAULT_WINDOW)
        hits, _d = _hits(guild.id, actor.id, key)
        used = _count_within(hits, window)
        if used + amount <= limit:
            return True, None
        what = ACTION_TITLES.get(key, 'действий')
        return False, (f'Лимит исчерпан: {limit} {what} за {human_window(window)} '
                       f'(уже {used}).')
    except Exception as ex:
        _log.debug('check_action(%s): %s', key, ex)
        return True, None


# ─── Пер-рольные лимиты и окна ──────────────────────────────────────────

def get_role_overrides(guild_id):
    """Полные переопределения по ролям: {rid: {'limits': {...}, 'windows': {...}}}."""
    saved = _load_json(_roles_path(guild_id), {})
    out = {}
    for rid, ov in saved.items():
        if not isinstance(ov, dict):
            continue
        # старый плоский формат {ban: 3} → {'limits': {...}}
        limits = _clean_limits(ov.get('limits') if isinstance(ov.get('limits'), dict) else ov)
        windows = _clean_windows(ov.get('windows'))
        if limits or windows:
            out[str(rid)] = {'limits': limits, 'windows': windows}
    return out


def get_role_limits(guild_id):
    """Только лимиты ролей (совместимость): {rid: {ключ: лимит}}."""
    return {rid: dict(o['limits']) for rid, o in get_role_overrides(guild_id).items()
            if o['limits']}


def set_role_limits(guild_id, role_id, **kw):
    """Задать лимиты роли (окна роли не трогаем). Возвращает её лимиты."""
    saved = _load_json(_roles_path(guild_id), {})
    cur = saved.get(str(role_id))
    if not isinstance(cur, dict) or not isinstance(cur.get('limits'), dict):
        cur = {'limits': _clean_limits(cur if isinstance(cur, dict) else {})}
    cur['limits'].update(_clean_limits(kw))
    saved[str(role_id)] = cur
    _save_json(_roles_path(guild_id), saved)
    return cur.get('limits') or {}


def set_role_windows(guild_id, role_id, **kw):
    """Задать окна роли в СЕКУНДАХ. Возвращает её окна."""
    saved = _load_json(_roles_path(guild_id), {})
    cur = saved.get(str(role_id))
    if not isinstance(cur, dict) or not isinstance(cur.get('limits'), dict):
        cur = {'limits': _clean_limits(cur if isinstance(cur, dict) else {})}
    cur.setdefault('windows', {})
    cur['windows'].update(_clean_windows(kw))
    saved[str(role_id)] = cur
    _save_json(_roles_path(guild_id), saved)
    return cur.get('windows') or {}


def clear_role_limits(guild_id, role_id):
    """Убрать переопределение роли — она живёт по глобальным лимитам."""
    saved = _load_json(_roles_path(guild_id), {})
    if str(role_id) in saved:
        saved.pop(str(role_id), None)
        _save_json(_roles_path(guild_id), saved)
        return True
    return False


def effective_limits(guild_id, role_ids=()):
    """Эффективные (лимиты, окна) пользователя: глобальные, ужатые ролями.

    На каждый ключ побеждает ИСТОЧНИК С МЕНЬШИМ ЧИСЛОМ — его окно и
    действует (8/день против 3/12 часов → 3 за 12 часов). Выдать себе
    «мягкую» роль нельзя.
    """
    lim = get_limits(guild_id)
    win = get_windows(guild_id)
    overrides = get_role_overrides(guild_id)
    for rid in role_ids or ():
        ov = overrides.get(str(rid))
        if not ov:
            continue
        for k, v in (ov.get('limits') or {}).items():
            if k not in lim:
                continue
            w = (ov.get('windows') or {}).get(k, win.get(k, DEFAULT_WINDOW))
            if v < lim[k] or (v == lim[k] and w < win.get(k, DEFAULT_WINDOW)):
                lim[k] = v
                win[k] = w
    return lim, win


def limits_for_roles(guild_id, role_ids=()):
    """Эффективные лимиты пользователя (совместимость: плоский словарь)."""
    return effective_limits(guild_id, role_ids)[0]
