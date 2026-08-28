# -*- coding: utf-8 -*-
"""Роли наказаний: мут / войс-мут / бан / уровни варнов — из панели.

Владелец сам выбирает, какая роль сервера = какое наказание
(панель → «Настройки» → «Роли наказаний»). Если роль не выбрана,
бот работает как раньше: мут — таймаутом, «бан» — изоляцией каналов.

Роль не снимается сама — поэтому сервис ведёт журнал временных выдач:
(когда чей срок вышел) и ког Moderation раз в минуту снимает просроченные.

Уровни варнов (warn_1..warn_10): участник с warn_count варнами получает
роль БЛИЖАЙШЕГО уровня не выше warn_count, роль предыдущего уровня
снимается автоматически (level_transition — «что снять/что выдать»).

Хранилище: data/punish_roles.json
    {"<gid>": {"roles": {"mute": id, "vmute": id, "ban": id},
               "temps": {"<uid>": {"<role_id>": until_ts}}}}
"""
import json
import os
import re
import threading
import time

from logger import get_logger

log = get_logger('punish_roles')

PATH = 'data/punish_roles.json'
KINDS = ('mute', 'vmute', 'ban')
WARN_LEVEL_MIN = 1
WARN_LEVEL_MAX = 10
_WARN_KEY_RE = re.compile(r'^warn_(10|[1-9])$')
MAX_SECONDS = 28 * 86400            # роли дольше 28 дней не выдаём

_lock = threading.Lock()


def valid_kind(kind):
    """mute/vmute/ban или warn_N — роль уровня (N варнов)."""
    kind = str(kind or '')
    return kind in KINDS or bool(_WARN_KEY_RE.match(kind))


def warn_levels(mapping=None):
    """{уровень: role_id} из выбранных warn-ролей (mapping = get(gid) или None)."""
    roles = mapping or {}
    out = {}
    for k, v in roles.items():
        m = _WARN_KEY_RE.match(str(k))
        if not m:
            continue
        try:
            v = int(v or 0)
        except (TypeError, ValueError) as _ex:
            log.debug('warn_levels: мусорное значение %r: %s', (k, v), _ex)
            continue
        if v > 0:
            out[int(m.group(1))] = v
    return out


def level_transition(gid, warn_count):
    """Роли-уровни: (add_id, remove_ids) при новом числе варнов.

    Целевой уровень — ближайший не выше warn_count (как ступень лестницы).
    Снимаем ВСЕ выбранные warn-роли кроме целевой: смена уровня снимает
    предыдущую роль автоматически, дублей не бывает. 0 варнов — снять всё.
    """
    levels = warn_levels(get(gid))
    try:
        count = max(0, int(warn_count or 0))
    except (TypeError, ValueError):
        count = 0
    target = max((lvl for lvl in levels if lvl <= count), default=0)
    add_id = int(levels.get(target) or 0)
    remove = []
    for rid in dict.fromkeys(int(v) for _lvl, v in levels.items() if v):
        if rid != add_id:
            remove.append(rid)
    return add_id, remove


def _load():
    try:
        with open(PATH, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    os.makedirs(os.path.dirname(PATH) or '.', exist_ok=True)
    tmp = PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)


def _clean_roles(raw):
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v0 in raw.items():
        if not valid_kind(k):
            continue
        try:
            v = int(v0 or 0)
        except (TypeError, ValueError):
            v = 0
        if v > 0:
            out[k] = v
    return out


def get(gid):
    """Текущий выбор ролей: {'mute': id, ..., 'warn_3': id} (пусто = не задано)."""
    row = _load().get(str(gid)) or {}
    return _clean_roles(row.get('roles'))


def set_roles(gid, who=None, **kw):
    """Задать роли (set_roles(gid, mute=123, warn_1=456, vmute=0...));
    0 = снять выбор. Невалидные ключи/значения игнорируются."""
    data = _load()
    row = data.setdefault(str(gid), {})
    cur = _clean_roles(row.get('roles'))
    for k in kw:
        if not valid_kind(k):
            log.debug('set_roles: неизвестный вид %r — пропуск', k)
            continue
        try:
            v = int(kw[k] or 0)
        except (TypeError, ValueError) as _ex:
            log.debug('set_roles: мусорное значение %s=%r: %s', k, kw[k], _ex)
            continue
        if v > 0:
            cur[k] = v
        else:
            cur.pop(k, None)
    if cur:
        row['roles'] = cur
    else:
        row.pop('roles', None)
    if not row:
        data.pop(str(gid), None)
    _save(data)
    log.info('punish_roles: %s → %s (кто: %s)', gid, cur, who or '?')
    return dict(cur)


def role_for(gid, kind):
    """ID выбранной роли для наказания (0 — не выбрано)."""
    return int(get(gid).get(kind) or 0)


# ── временные выдачи (авто-снятие по сроку) ─────────────────────────────

def add_temp(gid, uid, role_id, until_ts):
    """Запомнить, что роль выдана до момента until_ts."""
    with _lock:
        data = _load()
        row = data.setdefault(str(gid), {})
        temps = row.setdefault('temps', {})
        user = temps.setdefault(str(uid), {})
        user[str(int(role_id))] = float(until_ts)
        _save(data)


def clear(gid, uid, role_id=None):
    """Снять запись о временной роли (одну или все роли пользователя)."""
    with _lock:
        data = _load()
        row = data.get(str(gid)) or {}
        temps = row.get('temps') or {}
        user = temps.get(str(uid))
        if user is None:
            return
        if role_id is None:
            temps.pop(str(uid), None)
        else:
            user.pop(str(int(role_id)), None)
            if not user:
                temps.pop(str(uid), None)
        if not temps:
            row.pop('temps', None)
        if not row:
            data.pop(str(gid), None)
        _save(data)


def due(now=None):
    """[(gid, uid, role_id)] — все выдачи, чей срок наступил."""
    now = time.time() if now is None else float(now)
    out = []
    for gid, row in _load().items():
        for uid, user in (row.get('temps') or {}).items():
            for role_id, until in list(user.items()):
                try:
                    if float(until) <= now:
                        out.append((gid, uid, int(role_id)))
                except (TypeError, ValueError) as _ex:
                    log.debug("due: битая запись: {_ex}", _ex)
                    continue
    return out


def temps_for(gid, uid):
    """{role_id: until_ts} — активные временные роли пользователя."""
    row = _load().get(str(gid)) or {}
    user = (row.get('temps') or {}).get(str(uid)) or {}
    out = {}
    for role_id, until in user.items():
        try:
            out[int(role_id)] = float(until)
        except (TypeError, ValueError) as _ex:
            log.debug('temps_for: битая запись %s=%r: %s', role_id, until, _ex)
            continue
    return out
