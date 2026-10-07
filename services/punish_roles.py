# -*- coding: utf-8 -*-
"""Роли наказаний: мут / войс-мут / бан / уровни варнов — из панели.

Владелец сам выбирает, какая роль сервера = какое наказание
(панель → «Настройки» → «Роли наказаний»). Если роль не выбрана,
бот работает как раньше: мут — таймаутом, «бан» — изоляцией каналов.

Роль не снимается сама — поэтому сервис ведёт журнал временных выдач:
(когда чей срок вышел) и ког Moderation раз в минуту снимает просроченные.

Уровни варнов (warn_N — N любое от 1 до 100, НЕ фиксированные 10):
владелец сам добавляет уровни в панели («Роли наказаний»), у каждого —
своя роль; участник с warn_count варнами получает роль БЛИЖАЙШЕГО уровня
не выше warn_count, роль предыдущего уровня снимается автоматически
(level_transition — «что снять/что выдать»). Список добавленных уровней
хранится отдельно (warn_levels), чтобы карточка «уровень без роли»
не пропадала при перезагрузке панели.

Хранилище: data/punish_roles.json
    {"<gid>": {"roles": {"mute": id, "vmute": id, "ban": id, "warn_3": id},
               "warn_levels": [1, 3, 7],
               "temps": {"<uid>": {"<role_id>": until_ts}},
               "held_roles": {"<uid>": [role_id, ...]}}}

held_roles — снимок ролей на момент бана: бан забирает все (кроме
@everyone / managed / роли бана), разбан отдаёт обратно.
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
WARN_LEVEL_MAX = 100
_WARN_KEY_RE = re.compile(r'^warn_(\d+)$')
MAX_SECONDS = 28 * 86400            # роли дольше 28 дней не выдаём

# Жёсткие роли уровней варна (владелец 2026-10-07)
KNOWN_WARN_ROLE_BY_LEVEL = {
    1: 1545468739221327942,  # warn 1
    2: 1557474469394518187,  # warn 2
    3: 1557474898069430394,  # warn 3
}
# После N варнов: участник → бан; стафф → снятие staff + бан набора
MAX_WARN_BEFORE_PUNISH = 3
STAFF_APPLY_BAN_DAYS = 30

_lock = threading.Lock()


def valid_kind(kind):
    """mute/vmute/ban или warn_N — роль уровня (N варнов, 1..100)."""
    kind = str(kind or '')
    if kind in KINDS:
        return True
    m = _WARN_KEY_RE.match(kind)
    if not m:
        return False
    try:
        n = int(m.group(1))
    except (TypeError, ValueError):
        return False
    return WARN_LEVEL_MIN <= n <= WARN_LEVEL_MAX


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


def levels(gid):
    """Добавленные уровни варнов (сортировка): список из warn_levels + тех,
    у кого уже выбрана роль (обратная совместимость с warn_1..warn_10)."""
    row = _load().get(str(gid)) or {}
    out = set()
    for v in row.get('warn_levels') or []:
        try:
            n = int(v)
        except (TypeError, ValueError) as _ex:
            log.debug('levels: битый уровень %r: %s', v, _ex)
            continue
        if WARN_LEVEL_MIN <= n <= WARN_LEVEL_MAX:
            out.add(n)
    for k, v in (row.get('roles') or {}).items():
        m = _WARN_KEY_RE.match(str(k))
        if not m:
            continue
        try:
            n = int(m.group(1))
            rid = int(v or 0)
        except (TypeError, ValueError) as _ex:
            log.debug('levels: битый warn-ключ %r: %s', k, _ex)
            continue
        if WARN_LEVEL_MIN <= n <= WARN_LEVEL_MAX and rid > 0:
            out.add(n)
    return sorted(out)


def add_level(gid, level):
    """Добавить уровень (карточку) N варнов. Роль подбирается потом."""
    try:
        level = int(level or 0)
    except (TypeError, ValueError):
        return False, 'Уровень должен быть числом'
    if not (WARN_LEVEL_MIN <= level <= WARN_LEVEL_MAX):
        return False, f'Уровень — от {WARN_LEVEL_MIN} до {WARN_LEVEL_MAX} варнов'
    if level in levels(gid):
        return False, f'Уровень {level} уже есть'
    data = _load()
    row = data.setdefault(str(gid), {})
    row.setdefault('warn_levels', [])
    row['warn_levels'].append(level)
    row['warn_levels'].sort()
    _save(data)
    return True, f'Уровень {level} добавлен'


def remove_level(gid, level):
    """Удалить уровень целиком: карточку и её роль (если выбрана)."""
    try:
        level = int(level or 0)
    except (TypeError, ValueError):
        return False, 'Уровень должен быть числом'
    if not (WARN_LEVEL_MIN <= level <= WARN_LEVEL_MAX):
        return False, f'Уровень — от {WARN_LEVEL_MIN} до {WARN_LEVEL_MAX} варнов'
    data = _load()
    row = data.setdefault(str(gid), {})
    if 'warn_levels' in row:
        row['warn_levels'] = [int(x) for x in row['warn_levels']
                              if int(x) != level]
        if not row['warn_levels']:
            row.pop('warn_levels', None)
    roles = row.get('roles') or {}
    if f'warn_{level}' in roles:
        roles.pop(f'warn_{level}', None)
        row['roles'] = roles
    _save(data)
    return True, f'Уровень {level} удалён'


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


# mtime-кэш: role_for/get/due зовут _load() на КАЖДЫЙ voice/join-ивент и
# в циклах — раньше это был полный read+json.loads файла каждый раз, что
# грузило event loop. Теперь читаем с диска только когда файл изменился.
_CACHE = {'mtime': None, 'size': None, 'data': None}


def _load():
    try:
        st = os.stat(PATH)
    except OSError:
        _CACHE['mtime'] = None
        _CACHE['size'] = None
        _CACHE['data'] = {}
        return {}
    sig_m, sig_s = st.st_mtime, st.st_size
    if _CACHE['data'] is not None and _CACHE['mtime'] == sig_m \
            and _CACHE['size'] == sig_s:
        return _CACHE['data']
    try:
        with open(PATH, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    _CACHE['mtime'] = sig_m
    _CACHE['size'] = sig_s
    _CACHE['data'] = data
    return data


def _save(data):
    os.makedirs(os.path.dirname(PATH) or '.', exist_ok=True)
    tmp = PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)
    # Обновляем кэш сразу — следующий _load() не пойдёт на диск.
    try:
        st = os.stat(PATH)
        _CACHE['mtime'] = st.st_mtime
        _CACHE['size'] = st.st_size
        _CACHE['data'] = data
    except OSError:
        _CACHE['mtime'] = None
        _CACHE['size'] = None
        _CACHE['data'] = data


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
    with _lock:
        _CACHE['mtime'] = None
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


def ensure_known_warn_roles(gid, *, who: str = 'known-warn') -> dict:
    """Прописать warn_1/2/3 из KNOWN_WARN_ROLE_BY_LEVEL (идемпотентно).

    Не затирает уже заданные уровни с другим id — только пустые слоты
    и гарантирует карточки уровней 1..3.
    """
    try:
        gid = int(gid or 0)
    except (TypeError, ValueError):
        return {}
    if not gid:
        return {}
    cur = get(gid)
    patch = {}
    for lvl, rid in KNOWN_WARN_ROLE_BY_LEVEL.items():
        key = f'warn_{int(lvl)}'
        try:
            have = int(cur.get(key) or 0)
        except (TypeError, ValueError):
            have = 0
        if have <= 0:
            patch[key] = int(rid)
    if patch:
        set_roles(gid, who=who, **patch)
    for lvl in KNOWN_WARN_ROLE_BY_LEVEL:
        try:
            add_level(gid, int(lvl))
        except Exception:
            pass
    return get(gid)


def auto_seed_warn_role(guild) -> bool:
    """Если warn_N не заданы — сначала KNOWN ids, иначе имя warn/варн → warn_1.

    Возвращает True, если что-то записали. Идемпотентно.
    """
    try:
        gid = int(getattr(guild, 'id', 0) or 0)
    except (TypeError, ValueError):
        return False
    if not gid:
        return False
    before = dict(warn_levels(get(gid)))
    # 1) жёсткие ID владельца (warn 1/2/3)
    ensure_known_warn_roles(gid, who='auto-seed-known-warn')
    after = warn_levels(get(gid))
    if after != before:
        log.warning(
            'punish_roles: auto-seed known warn roles guild=%s → %s',
            gid, after)
        return True
    if after:
        return False
    names = {
        'warn', 'варн', 'warn 1', 'варн 1', 'warning', 'предупреждение',
        'warn1', 'варн1',
    }
    found = None
    for role in list(getattr(guild, 'roles', None) or []):
        n = str(getattr(role, 'name', '') or '').strip().lower()
        if n in names:
            found = role
            break
    if found is None:
        # частичное совпадение: начинается с warn / варн
        for role in list(getattr(guild, 'roles', None) or []):
            n = str(getattr(role, 'name', '') or '').strip().lower()
            if n.startswith('warn') or n.startswith('варн'):
                found = role
                break
    if found is None:
        return False
    set_roles(gid, who='auto-seed-warn', warn_1=int(found.id))
    add_level(gid, 1)  # карточка уровня (если ещё нет)
    log.warning(
        'punish_roles: auto-seed warn_1=%s (%s) guild=%s',
        found.id, found.name, gid)
    return True

# ── временные выдачи (авто-снятие по сроку) ─────────────────────────────

def add_temp(gid, uid, role_id, until_ts):
    """Запомнить, что роль выдана до момента until_ts."""
    with _lock:
        # Всегда свежий диск: чужой writer (role_seed / set_roles) мог
        # обновить файл, а кэш ещё держит старую копию без temps.
        _CACHE['mtime'] = None
        data = _load()
        row = data.setdefault(str(gid), {})
        temps = row.setdefault('temps', {})
        user = temps.setdefault(str(uid), {})
        user[str(int(role_id))] = float(until_ts)
        _save(data)


def _case_until_ts(case):
    """timestamp + duration_minutes → unix until, или 0."""
    try:
        mins = int(case.get('duration_minutes') or 0)
    except (TypeError, ValueError):
        mins = 0
    if mins <= 0:
        return 0.0
    raw = case.get('timestamp') or ''
    try:
        # ISO из save_case (UTC)
        from datetime import datetime
        ts = str(raw).replace('Z', '+00:00')
        dt = datetime.fromisoformat(ts)
        return float(dt.timestamp()) + mins * 60
    except Exception:
        try:
            return float(raw) + mins * 60
        except (TypeError, ValueError):
            return 0.0


def restore_temps_from_mod_data(gid, members_with_roles):
    """Восстановить temps после рестарта по ролям Discord + делам.

    members_with_roles: iterable (uid, role_id) — у кого сейчас висит
    mute/vmute роль. Если в temps срока нет — берём последнее дело
    mute_chat/timeout/vmute с duration_minutes.

    Возвращает {'restored': N, 'expired': [(uid, role_id), ...],
                'unknown': N}.
    """
    report = {'restored': 0, 'expired': [], 'unknown': 0}
    try:
        gid = str(int(gid))
    except (TypeError, ValueError):
        return report
    now = time.time()
    # дела гильдии
    cases_by_user = {}
    try:
        with open('data/mod_data.json', 'r', encoding='utf-8') as fp:
            md = json.load(fp) or {}
        for c in (md.get('cases') or {}).get(gid) or []:
            uid = str(c.get('user_id') or '')
            if not uid:
                continue
            cases_by_user.setdefault(uid, []).append(c)
    except (OSError, ValueError) as ex:
        log.debug('restore_temps: mod_data: %s', ex)

    mute_id = role_for(gid, 'mute')
    vmute_id = role_for(gid, 'vmute')
    kind_by_role = {}
    if mute_id:
        kind_by_role[int(mute_id)] = ('mute_chat', 'timeout')
    if vmute_id:
        kind_by_role[int(vmute_id)] = ('vmute', 'timeout')

    with _lock:
        _CACHE['mtime'] = None
        data = _load()
        row = data.setdefault(gid, {})
        temps = row.setdefault('temps', {})
        dirty = False
        for uid, role_id in members_with_roles or ():
            try:
                uid_s = str(int(uid))
                rid = int(role_id)
            except (TypeError, ValueError):
                continue
            if rid not in kind_by_role:
                continue
            user = temps.setdefault(uid_s, {})
            cur_until = 0.0
            try:
                cur_until = float(user.get(str(rid)) or 0)
            except (TypeError, ValueError):
                cur_until = 0.0
            if cur_until > now:
                continue  # срок уже есть и ещё действует
            # ищем последнее подходящее дело
            want = kind_by_role[rid]
            until = 0.0
            for c in reversed(cases_by_user.get(uid_s) or []):
                act = str(c.get('action') or '')
                if act not in want:
                    continue
                # снятие после этого дела?
                lifts = {
                    'mute_chat': ('unmute_chat', 'untimeout'),
                    'timeout': ('untimeout', 'unmute_chat', 'vunmute'),
                    'vmute': ('vunmute', 'untimeout'),
                }.get(act, ())
                idx = (cases_by_user.get(uid_s) or []).index(c)
                later = (cases_by_user.get(uid_s) or [])[idx + 1:]
                if any(str(x.get('action') or '') in lifts for x in later):
                    continue
                until = _case_until_ts(c)
                if until > 0:
                    break
            if until <= 0:
                report['unknown'] += 1
                continue
            if until <= now:
                # срок уже вышел, пока бот лежал — снимем в loop
                user[str(rid)] = now - 1
                dirty = True
                report['expired'].append((uid_s, rid))
            else:
                user[str(rid)] = float(until)
                dirty = True
                report['restored'] += 1
        if dirty:
            if temps:
                row['temps'] = temps
            _save(data)
        elif not temps:
            row.pop('temps', None)
    return report


def clear(gid, uid, role_id=None):
    """Снять запись о временной роли (одну или все роли пользователя).

    Снимок held_roles не трогаем: разбан читает его отдельно.
    """
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


def _clean_role_ids(role_ids):
    """Уникальные положительные id, порядок как пришёл."""
    ids, seen = [], set()
    for raw in role_ids or ():
        try:
            rid = int(raw)
        except (TypeError, ValueError) as _e:
            log.debug('punish_roles: id %r пропущен: %s', raw, _e)
            continue
        if rid <= 0 or rid in seen:
            continue
        seen.add(rid)
        ids.append(rid)
    return ids


def save_held_roles(gid, uid, role_ids):
    """Снимок ролей, снятых при бане. Пустой список не затирает уже сохранённое."""
    ids = _clean_role_ids(role_ids)
    with _lock:
        data = _load()
        row = data.setdefault(str(gid), {})
        held = row.setdefault('held_roles', {})
        key = str(uid)
        if not ids:
            if held.get(key):
                return
            held.pop(key, None)
            if not held:
                row.pop('held_roles', None)
            if not row:
                data.pop(str(gid), None)
            _save(data)
            return
        held[key] = ids
        _save(data)


def held_roles(gid, uid):
    """Роли, которые вернём после разбана (копия списка)."""
    with _lock:
        row = _load().get(str(gid)) or {}
        raw = (row.get('held_roles') or {}).get(str(uid)) or []
        return _clean_role_ids(raw)


def take_held_roles(gid, uid):
    """Забрать снимок (разбан). clear() сроки не трогает этот ключ."""
    with _lock:
        data = _load()
        row = data.get(str(gid)) or {}
        held = row.get('held_roles') or {}
        raw = held.pop(str(uid), None) or []
        if not held:
            row.pop('held_roles', None)
        if row:
            data[str(gid)] = row
        elif str(gid) in data:
            data.pop(str(gid), None)
        _save(data)
        return _clean_role_ids(raw)
