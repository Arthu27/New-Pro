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
    get_changes / revert_change            — журнал «кто/когда/что» и откат

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
#
# Дефолты ВКЛЮЧЕНЫ по просьбе владельца (2026-09-02, переписка с Sabotash):
# «это так для безопасности… авто настроишь — я потом поменяю». Это нижний,
# МОДЕРАТОРСКИЙ порог — он же применяется, пока для конкретных ролей в панели
# («Щит сервера» → «Лимиты») не заданы свои, более высокие цифры. Так у
# кураторов/админов лимит поднимается пер-рольным оверрайдом (ban 3/5,
# unmute 5), а базовый модераторский уровень защищает сервер сразу.
#   • бан/апелляция — 1/день (кураторы 3, админы 5 — через панель)
#   • размут (снятие мута/таймаута/войса) — 3/день (кураторы/админы 5)
#   • мут/таймаут — симметрично размуту, 3/день
#   • очистка — 10 сообщений/день (договорились «5–10 достаточно»)
# Владелец всё это меняет в панели; 0 по-прежнему означает «без лимита».
DEFAULT_LIMITS = {
    # ── наказания ──
    'warn': 1,       # предупреждений (/warn и ПКМ-варн) — 1 в день У ВСЕХ
                     # (владелец 2026-09-05); окно 24 ч, счётчики на диске
    'mute': 3,       # мутов (таймаут/чат/войс/тихий ghostmute) — 3/день
    'unmute': 3,     # снятий мута — 3/день (кураторы/админы — 5 через панель)
    'kick': 0,       # киков (команда отключена — лимит на будущее)
    'vkick': 0,      # киков из голосового канала
    'ban': 1,        # банов/апелляций — 1/день (кураторы 3, админы 5 — панель)
    'unban': 0,      # разбанов / снятий апелляции — без жёсткого дефолта
    # ── опасные операции ──
    'clear': 10,     # сообщений, удалённых очисткой — 10/день у персонала
                     # (владелец 2026-09-05); владелец сервера/бота — без лимита
}

# Человеческие названия для сообщений и панели.
ACTION_TITLES = {
    'warn': 'варнов',
    'unwarn': 'снятий варна',
    'mute': 'мутов',
    'unmute': 'снятий мута',
    'kick': 'киков',
    'vkick': 'киков из войса',
    'ban': 'банов',
    'unban': 'разбанов',
    'clear': 'сообщений чисткой',
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
}

# Порядок и группировка полей в панели.
# Показываем ТОЛЬКО действия, которые бот реально гейтит лимитами (модерация
# их вызывает через check_limit/record_hit): предупреждения, муты, снятие
# мутов, баны и очистка сообщений. Действия, которых нет в боте (nuke и пр.),
# убраны совсем (владелец 2026-09-05: «нету такого»); kick/vkick/unban
# считаются, но в форму не выводятся, пока не подключим к ним поля.
ACTION_GROUPS = [
    ('punish', 'Наказания', ['warn', 'mute', 'unmute', 'ban']),
    ('heavy', 'Опасные операции', ['clear']),
]

# Полный список действий, которые панель лимитов реально предлагает настроить
# (для тестов и проверок согласованности с ACTION_GROUPS).
PANEL_ACTION_KEYS = ('warn', 'mute', 'unmute', 'ban', 'clear')


def action_meta():
    """Метаданные действий для панели: только рабочие группы с полями."""
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


# ── Тиры персонала по ролям (заказ владельца 2026-09-02) ──────────────
# Роли персонала настраиваются в панели «Настройки → Панели и роли»
# (data/role_map.json): role_id → 'mod' | 'curator' | 'admin' | 'owner'.
# staff_limits читает ТОТ ЖЕ файл и по нему назначает тировые дефолты —
# отдельные роли «модер/куратор/админ» заводить не нужно.
ROLE_MAP_PATH = 'data/role_map.json'

# Порядок старшинства: больший индекс — больше прав (мягче лимиты).
TIER_ORDER = ('mod', 'curator', 'admin', 'owner')

# Тировые дефолты за окно (день). Цифры из переписки владельца с Sabotash:
# бан — модер 1 / куратор 3 / админ 5; размут — модер 3 / куратор 5 / админ 5;
# мут/таймаут — симметрично; очистка — 10 сообщений. Владелец поднимает
# пер-рольно через панель; глобальные и пер-рольные оверрайды ВАЖНЕЕ этих.
TIER_DEFAULT_LIMITS = {
    # warn=1 и clear=10 — единые для персонала (владелец 2026-09-05);
    # тир владельца (owner) — ВСЁ без лимитов (владелец 2026-09-05:
    # «у владельца без лимит надо сделать всё»)
    'mod':     {'warn': 1, 'ban': 1, 'unmute': 3, 'mute': 3, 'clear': 10},
    'curator': {'warn': 1, 'ban': 3, 'unmute': 5, 'mute': 5, 'clear': 10},
    'admin':   {'warn': 1, 'ban': 5, 'unmute': 5, 'mute': 5, 'clear': 10},
    'owner':   {},   # владелец не ограничен ни в чём
}


def _role_tier_map(guild_id=None):
    """{role_id(str): tier} из data/role_map.json (та же настройка, что в
    панели «Панели и роли»). Сбой чтения — пустой словарь (не мешаем)."""
    try:
        data = _load_json(ROLE_MAP_PATH, {})
        if not isinstance(data, dict):
            return {}
        return {str(rid): str(tier) for rid, tier in data.items()
                if str(tier) in TIER_ORDER}
    except Exception:
        return {}


def tier_for_roles(role_ids):
    """Старший тир из набора ролей участника: 'owner' > 'admin' > 'curator'
    > 'mod' > None (роль не помечена как стафф — действует общий дефолт)."""
    tmap = _role_tier_map()
    best = None
    best_i = -1
    for rid in role_ids or ():
        tier = tmap.get(str(rid))
        if tier and TIER_ORDER.index(tier) > best_i:
            best, best_i = tier, TIER_ORDER.index(tier)
    return best


def _tier_defaults(role_ids):
    """Лимиты старшего тира участника (или {} если стафф-ролей нет).

    Для owner — ЯВНЫЕ нули по всем действиям: владелец (тир, владелец
    сервера и владелец бота) не ограничен ВООБЩЕ ничем (2026-09-05:
    «у владельца без лимит надо сделать все»). Ноль = без лимита и
    перекрывает базовые дефолты warn=1/clear=10 персонала."""
    tier = tier_for_roles(role_ids)
    if not tier:
        return {}
    if tier == 'owner':
        return {k: 0 for k in DEFAULT_LIMITS}
    return dict(TIER_DEFAULT_LIMITS.get(tier) or {})


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
        # (прочие новые блоки — windows/durations — сохраняем)
        legacy = _clean_limits(saved)
        keep = {k: v for k, v in saved.items()
                if k in ('windows', 'durations') and isinstance(v, dict)}
        saved = {'limits': legacy, **keep}
    saved.setdefault('limits', {})
    if limits_patch:
        saved['limits'].update(_clean_limits(limits_patch))
    if windows_patch:
        saved.setdefault('windows', {})
        saved['windows'].update(_clean_windows(windows_patch))
    _save_json(_cfg_path(guild_id), saved)
    return saved


def set_limits(guild_id, who=None, **kw):
    """Обновить лимиты гильдии (например set_limits(gid, ban=5)).

    who — кто менял (для журнала изменений).
    """
    cur = get_limits(guild_id)
    diffs = [{'key': k, 'field': 'limit', 'old': cur.get(k), 'new': int(v)}
             for k, v in kw.items()
             if k in DEFAULT_LIMITS and isinstance(v, int) and v > 0
             and cur.get(k) != int(v)]
    _write_cfg(guild_id, limits_patch=kw)
    _journal(guild_id, 'global', None, None, diffs, who)
    return get_limits(guild_id)


def set_windows(guild_id, who=None, **kw):
    """Обновить окна гильдии в СЕКУНДАХ (например set_windows(gid, ban=3600))."""
    cur = get_windows(guild_id)
    diffs = [{'key': k, 'field': 'window', 'old': cur.get(k), 'new': int(v)}
             for k, v in kw.items()
             if k in DEFAULT_LIMITS and isinstance(v, int) and v > 0
             and cur.get(k) != int(v)]
    _write_cfg(guild_id, windows_patch=kw)
    _journal(guild_id, 'global', None, None, diffs, who)
    return get_windows(guild_id)


# ── Потолки длительности (макс. мут) ─────────────────────────────────────
# Хранение: cfg['durations'] = {'mute': секунды}; у роли — 'durations'.
# 0/отсутствует = без ограничения. Роль ГЛАВНЕЕ общего (как у счётчиков).

DURATION_KEYS = ('mute',)          # timeout/мут чата/войс-мут — один потолок
DURATION_TITLES = {'mute': 'мут'}


def _clean_durations(raw):
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        if k in DURATION_KEYS and isinstance(v, int) and v > 0:
            out[k] = max(60, min(28 * 86400, v))     # от минуты до 28 дней
    return out


def get_durations(guild_id):
    """Глобальные потолки длительности: {ключ: секунды}."""
    saved = _load_json(_cfg_path(guild_id), {})
    return _clean_durations(saved.get('durations'))


def set_durations(guild_id, who=None, **kw):
    """Задать глобальный потолок (set_durations(gid, mute=3600)); 0 = убрать."""
    saved = _load_json(_cfg_path(guild_id), {})
    if not isinstance(saved, dict):
        saved = {}
    cur = dict(saved.get('durations') or {})
    for k, v in (kw or {}).items():
        if k not in DURATION_KEYS:
            continue
        if isinstance(v, int) and v > 0:
            cur[k] = max(60, min(28 * 86400, v))
        else:
            cur.pop(k, None)
    if cur:
        saved['durations'] = cur
    else:
        saved.pop('durations', None)
    _save_json(_cfg_path(guild_id), saved)
    _journal(guild_id, 'global', None, None,
             [{'key': k, 'field': 'duration', 'old': None, 'new': v}
              for k, v in cur.items()], who)
    return dict(cur)


def set_role_durations(guild_id, role_id, who=None, role_name=None, **kw):
    """Свой потолок длительности для роли (роль главнее общего)."""
    saved = _load_json(_roles_path(guild_id), {})
    if not isinstance(saved, dict):
        saved = {}
    row = saved.setdefault(str(role_id), {})
    if not isinstance(row, dict):
        row = {}
        saved[str(role_id)] = row
    if 'durations' not in row or not isinstance(row.get('durations'), dict):
        row['durations'] = {}
    for k, v in (kw or {}).items():
        if k not in DURATION_KEYS:
            continue
        if isinstance(v, int) and v > 0:
            row['durations'][k] = max(60, min(28 * 86400, v))
        else:
            row['durations'].pop(k, None)
    if not row.get('durations'):
        row.pop('durations', None)
    if not row:
        saved.pop(str(role_id), None)
    _save_json(_roles_path(guild_id), saved)
    if role_name:
        _journal(guild_id, 'role', role_id, role_name,
                 [{'key': k, 'field': 'role_duration', 'old': None, 'new': v}
                  for k, v in (row.get('durations') or {}).items()], who)
    return dict(row.get('durations') or {})


def role_scoped_actions(guild_id, role_ids=()):
    """Какие действия доступны модератору через /modpanel.

    По умолчанию ограничений нет → None (видно всё). Если хоть у одной
    роли модератора есть свои настройки (лимиты/окна/потолки), доступны
    ТОЛЬКО настроенные действия — объединение по всем таким ролям.
    """
    overrides = get_role_overrides(guild_id)
    scoped = None
    for rid in role_ids or ():
        ov = overrides.get(str(rid)) or {}
        keys = (set(ov.get('limits') or ())
                | set(ov.get('windows') or ())
                | set(ov.get('durations') or ()))
        if keys:
            scoped = (scoped or set()) | keys
    return scoped


def effective_max_duration(guild_id, key, role_ids=()):
    """Потолок длительности в секундах (0 = без ограничения).

    Свой потолок роли ГЛАВНЕЕ общего; несколько ролей — мягчайший.
    """
    overrides = get_role_overrides(guild_id)
    best = 0
    for rid in role_ids or ():
        ov = overrides.get(str(rid)) or {}
        v = int((ov.get('durations') or {}).get(key) or 0)
        if v > best:
            best = v
    if best:
        return best
    return int(get_durations(guild_id).get(key) or 0)


def refresh_in_text(guild_id, user_id, key):
    """Через сколько лимит отпустит: '3 ч 12 мин' или None."""
    try:
        win = get_windows(guild_id).get(key, DEFAULT_WINDOW)
        hits, _d = _hits(guild_id, user_id, key)
        now = _now()
        live = [t for t in hits if now - t < win]
        if not live:
            return None
        # отпустит, когда самая старая «расходка» выйдет из окна
        left = max(0, int((min(live) + win - now)))
        if left <= 60:
            return 'меньше минуты'
        h, m = left // 3600, (left % 3600) // 60
        return (f'{h} ч {m} мин' if h else f'{m} мин')
    except Exception:
        return None


def _unset_cfg(guild_id, limit_keys=(), window_keys=()):
    """Убрать глобальные переопределения выбранных ключей (вернутся дефолты)."""
    saved = _load_json(_cfg_path(guild_id), {})
    if not isinstance(saved.get('limits'), dict):
        legacy = _clean_limits(saved)
        keep = {k: v for k, v in saved.items()
                if k in ('windows', 'durations') and isinstance(v, dict)}
        saved = {'limits': legacy, **keep}
    lims = saved.setdefault('limits', {})
    for k in limit_keys or ():
        lims.pop(k, None)
    if window_keys:
        wins = saved.setdefault('windows', {})
        for k in window_keys:
            wins.pop(k, None)
        if not wins:
            saved.pop('windows', None)
    _save_json(_cfg_path(guild_id), saved)


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

    role_ids — роли модератора: если у какой-то из них задан СВОЙ лимит,
    действует он вместо общего (заказ владельца).
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
             'unban': 'разбаны'}
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
        try:  # владелец бота (OWNER_ID/OWNER_IDS) — лимиты не проверяем
            from config import Config
            if int(getattr(actor, 'id', 0) or 0) in Config.all_owner_ids():
                return True, None
        except Exception as _ex:
            # НЕ глотаем молча: ошибка здесь (например, недоступен config)
            # не должна превращать проверку лимита в «разрешено всем»
            _log.debug('staff_limits: владелец бота не проверен: %s', _ex)
        if getattr(actor, 'bot', False):
            return True, None      # сам бот (панель/автоматика) — лимитами не грудим
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
        left = max(0, limit - used)
        txt = (f'Лимит исчерпан: {limit} {what} за {human_window(window)} '
               f'(использовано {used}, осталось {left}).')
        when = refresh_in_text(guild.id, actor.id, key)
        if when:
            txt += f' Обновится через {when}.'
        return False, txt
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
        durations = _clean_durations(ov.get('durations'))
        if limits or windows or durations:
            out[str(rid)] = {'limits': limits, 'windows': windows,
                             'durations': durations}
    return out


def get_role_limits(guild_id):
    """Только лимиты ролей (совместимость): {rid: {ключ: лимит}}."""
    return {rid: dict(o['limits']) for rid, o in get_role_overrides(guild_id).items()
            if o['limits']}


def set_role_limits(guild_id, role_id, who=None, role_name=None, **kw):
    """Задать лимиты роли (окна роли не трогаем). Возвращает её лимиты."""
    cur = get_role_overrides(guild_id).get(str(role_id)) or {}
    cur_lims = cur.get('limits') or {}
    diffs = [{'key': k, 'field': 'limit', 'old': cur_lims.get(k), 'new': int(v)}
             for k, v in kw.items()
             if k in DEFAULT_LIMITS and isinstance(v, int) and v > 0
             and cur_lims.get(k) != int(v)]
    saved = _load_json(_roles_path(guild_id), {})
    cur = saved.get(str(role_id))
    if not isinstance(cur, dict) or not isinstance(cur.get('limits'), dict):
        cur = {'limits': _clean_limits(cur if isinstance(cur, dict) else {})}
    cur['limits'].update(_clean_limits(kw))
    saved[str(role_id)] = cur
    _save_json(_roles_path(guild_id), saved)
    _journal(guild_id, 'role', str(role_id), role_name, diffs, who)
    return cur.get('limits') or {}


def set_role_windows(guild_id, role_id, who=None, role_name=None, **kw):
    """Задать окна роли в СЕКУНДАХ. Возвращает её окна."""
    cur = get_role_overrides(guild_id).get(str(role_id)) or {}
    cur_wins = cur.get('windows') or {}
    diffs = [{'key': k, 'field': 'window', 'old': cur_wins.get(k), 'new': int(v)}
             for k, v in kw.items()
             if k in DEFAULT_LIMITS and isinstance(v, int) and v > 0
             and cur_wins.get(k) != int(v)]
    saved = _load_json(_roles_path(guild_id), {})
    cur = saved.get(str(role_id))
    if not isinstance(cur, dict) or not isinstance(cur.get('limits'), dict):
        cur = {'limits': _clean_limits(cur if isinstance(cur, dict) else {})}
    cur.setdefault('windows', {})
    cur['windows'].update(_clean_windows(kw))
    saved[str(role_id)] = cur
    _save_json(_roles_path(guild_id), saved)
    _journal(guild_id, 'role', str(role_id), role_name, diffs, who)
    return cur.get('windows') or {}


def unset_role_keys(guild_id, role_id, limit_keys=(), window_keys=(),
                   who=None, role_name=None):
    """Убрать отдельные переопределения роли (пустую роль выкидываем)."""
    before = get_role_overrides(guild_id).get(str(role_id)) or {}
    diffs = [{'key': k, 'field': 'limit', 'old': v, 'new': None}
             for k, v in (before.get('limits') or {}).items()
             if k in (limit_keys or ())]
    diffs += [{'key': k, 'field': 'window', 'old': v, 'new': None}
              for k, v in (before.get('windows') or {}).items()
              if k in (window_keys or ())]
    saved = _load_json(_roles_path(guild_id), {})
    cur = saved.get(str(role_id))
    if not isinstance(cur, dict):
        _journal(guild_id, 'role', str(role_id), role_name, diffs, who)
        return False
    lims = cur.get('limits') if isinstance(cur.get('limits'), dict) else {}
    wins = cur.get('windows') if isinstance(cur.get('windows'), dict) else {}
    for k in limit_keys or ():
        lims.pop(k, None)
    for k in window_keys or ():
        wins.pop(k, None)
    if lims or wins:
        cur['limits'], cur['windows'] = lims, wins
        saved[str(role_id)] = cur
    else:
        saved.pop(str(role_id), None)
    _save_json(_roles_path(guild_id), saved)
    _journal(guild_id, 'role', str(role_id), role_name, diffs, who)
    return True


def clear_role_limits(guild_id, role_id, who=None, role_name=None):
    """Убрать переопределение роли — она живёт по глобальным лимитам."""
    before = get_role_overrides(guild_id).get(str(role_id)) or {}
    diffs = [{'key': k, 'field': 'limit', 'old': v, 'new': None}
             for k, v in (before.get('limits') or {}).items()]
    diffs += [{'key': k, 'field': 'window', 'old': v, 'new': None}
              for k, v in (before.get('windows') or {}).items()]
    saved = _load_json(_roles_path(guild_id), {})
    if str(role_id) in saved:
        saved.pop(str(role_id), None)
        _save_json(_roles_path(guild_id), saved)
        _journal(guild_id, 'role', str(role_id), role_name, diffs, who)
        return True
    return False


# ─── Журнал изменений: кто/когда/что — чтобы увидеть и переделать ────────

_JOURNAL_MAX = 80        # храним последние изменения


def _chg_path(gid):
    return f'data/staff_limit_changes_{int(gid)}.json'


def _load_changes(guild_id):
    data = _load_json(_chg_path(guild_id), {})
    lst = data.get('changes')
    return [e for e in lst if isinstance(e, dict)] if isinstance(lst, list) else []


def _journal(guild_id, scope, role_id, role_name, diffs, who):
    """Дописать изменение в журнал (сам журнал не роняет настройку)."""
    if not diffs:
        return None
    try:
        data = _load_json(_chg_path(guild_id), {})
        lst = _load_changes(guild_id)
        seq = data.get('seq')
        seq = int(seq) + 1 if isinstance(seq, int) else len(lst) + 1
        entry = {
            'id': 'c' + str(seq),
            'ts': int(_now()),
            'who': str(who or 'панель'),
            'scope': scope,
            'role_id': str(role_id) if role_id else None,
            'role_name': str(role_name) if role_name else None,
            'changes': diffs,
        }
        lst.append(entry)
        _save_json(_chg_path(guild_id), {'seq': seq, 'changes': lst[-_JOURNAL_MAX:]})
        return entry
    except Exception as ex:
        _log.debug('journal: %s', ex)
        return None


def get_changes(guild_id, limit=60):
    """Последние изменения лимитов, новые первыми."""
    out = list(reversed(_load_changes(guild_id)))
    return out[:max(1, int(limit))]


def revert_change(guild_id, change_id, who=None):
    """(ok, entry): вернуть значения, как было ДО изменения из журнала."""
    for entry in reversed(_load_changes(guild_id)):
        if entry.get('id') != str(change_id):
            continue
        scope, rid = entry.get('scope'), entry.get('role_id')
        rname = entry.get('role_name')
        limits, windows = {}, {}
        for ch in entry.get('changes') or []:
            if not isinstance(ch, dict) or ch.get('key') not in DEFAULT_LIMITS:
                continue
            if ch.get('field') == 'limit':
                limits[ch['key']] = ch.get('old')
            elif ch.get('field') == 'window':
                windows[ch['key']] = ch.get('old')
        if scope == 'role' and rid:
            unset_role_keys(guild_id, rid,
                            limit_keys=[k for k, v in limits.items() if v is None],
                            window_keys=[k for k, v in windows.items() if v is None])
            own_l = {k: v for k, v in limits.items() if v is not None}
            own_w = {k: v for k, v in windows.items() if v is not None}
            if own_l:
                set_role_limits(guild_id, rid, who=who, role_name=rname, **own_l)
            if own_w:
                set_role_windows(guild_id, rid, who=who, role_name=rname, **own_w)
        elif scope == 'global':
            _unset_cfg(guild_id,
                       limit_keys=[k for k, v in limits.items() if v is None],
                       window_keys=[k for k, v in windows.items() if v is None])
            own_l = {k: v for k, v in limits.items() if v is not None}
            own_w = {k: v for k, v in windows.items() if v is not None}
            if own_l:
                set_limits(guild_id, who=who, **own_l)
            if own_w:
                set_windows(guild_id, who=who, **own_w)
        return True, entry
    return False, None


def effective_limits(guild_id, role_ids=()):
    """Эффективные (лимиты, окна) пользователя: свои лимиты ролей ГЛАВНЕЕ
    общих (так пожелал владелец). Задали роли лимит — действует ОН, больше
    общего или меньше — неважно. Общего лимита нет, а у роли есть —
    действует лимит роли. Несколько ролей со своими лимитами — побеждает
    самая мягкая (роль дают осознанно, наказывать за вторую роль странно).
    """
    lim = dict(get_limits(guild_id))
    win = dict(get_windows(guild_id))
    # Тировые дефолты (модер/куратор/админ из data/role_map.json) ВАЖНЕЕ
    # общих модераторских дефолтов: куратору 3 бана, админу 5 и т.д.
    for _k, _v in _tier_defaults(role_ids).items():
        lim[_k] = _v
    overrides = get_role_overrides(guild_id)
    best = {}          # ключ → (лимит, окно) — лучший из СВОИХ лимитов ролей
    for rid in role_ids or ():
        ov = overrides.get(str(rid))
        if not ov:
            continue
        for k, v in (ov.get('limits') or {}).items():
            if not isinstance(v, int) or v <= 0:
                continue
            w = (ov.get('windows') or {}).get(k, win.get(k, DEFAULT_WINDOW))
            if k not in best or v > best[k][0] or (v == best[k][0] and w > best[k][1]):
                best[k] = (v, w)
    for k, (v, w) in best.items():
        lim[k] = v     # свой лимит роли ЗАМЕНЯЕТ общий — больше он или меньше
        win[k] = w
    return lim, win


def limits_for_roles(guild_id, role_ids=()):
    """Эффективные лимиты пользователя (совместимость: плоский словарь)."""
    return effective_limits(guild_id, role_ids)[0]
