# -*- coding: utf-8 -*-
"""Сбор реальной активности сообщений для «Аналитики сервера».

Проблема (жалоба владельца 2026-08-25): страница «Аналитика» читает
data/message_logs_<gid>.json, но НИКТО в боте этот файл не писал —
сколько ни пиши в Discord, все графики оставались нулями.

Решение: лёгкий сборщик метаданных (автор, канал, время — БЕЗ текста
сообщений, приватность), скользящее окно на сервер, фоновая запись
пачками, чтобы файл не рос бесконечно и диск не дёргался на каждом
сообщении. Данные — только настоящие, ничего выдуманного (заказ
владельца: аналитика показывает ТОЛЬКО реальные данные).
"""
import json
import os
import threading
import time
from datetime import datetime, timezone

_LOCK = threading.Lock()
_PENDING = {}          # gid -> [ {author, channel, timestamp}, ... ]
_DIRTY = set()
_STOP = threading.Event()
_THREAD = None
MAX_PER_GUILD = 20000  # ~последние 20k сообщений на сервер (~2-3 МБ максимум)
FLUSH_EVERY = 15.0     # секунд между записями на диск
_log = None


def _logger():
    global _log
    if _log is None:
        import logging
        _log = logging.getLogger('message_stats')
        _log.addHandler(logging.NullHandler())
    return _log


def _path(gid):
    return f'data/message_logs_{gid}.json'


def _load(gid):
    if not os.path.exists(_path(gid)):
        return []
    try:
        with open(_path(gid), 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError) as ex:
        _logger().debug('message_stats: прочитать %s не вышло: %s', gid, ex)
        return []


def _atomic_write(path, payload):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False)
    os.replace(tmp, path)


def record(guild_id, author, channel, when=None, user_id=None):
    """Запомнить сообщение (метаданные). Потокобезопасно, неблокирующе.

    user_id — ЛИЧНОСТЬ автора: агрегация топов идёт по нему, поэтому смена
    ника не дробит человека на двоих в «Аналитике» (жалоба владельца
    2026-09-05: «это один и тот же человек, просто имя поменял»). Ник в
    'author' — живая подпись: у записи свежее имя побеждает.
    """
    gid = str(guild_id)
    if not gid or not author:
        return False
    event = {
        'author': str(author),
        'channel': str(channel or '?'),
        'timestamp': (when or datetime.now(timezone.utc)).isoformat(),
    }
    try:
        if user_id and int(user_id):
            event['uid'] = str(int(user_id))
    except (TypeError, ValueError) as ex:
        _logger().debug('message_stats: uid не штампуется: %s', ex)
    with _LOCK:
        _PENDING.setdefault(gid, []).append(event)
        _DIRTY.add(gid)
    return True


def pending_count():
    with _LOCK:
        return sum(len(v) for v in _PENDING.values())


def flush_all():
    """Записать всё накопленное на диск (вызывается фоном и при остановке)."""
    with _LOCK:
        gids = list(_DIRTY)
        _DIRTY.clear()
        batches = {g: _PENDING.pop(g, []) for g in gids}
    for gid, batch in batches.items():
        if not batch:
            continue
        try:
            data = _load(gid)
            data.extend(batch)
            _atomic_write(_path(gid), data[-MAX_PER_GUILD:])
            # Живой пуш в панель: сообщения записаны — Аналитика обновится
            # сразу (а не по таймеру). Немного дебаунсим на стороне фронта
            # (события коалесцируются), так что частые сообщения не штормят.
            try:
                from services.live_bus import publish
                publish(gid, 'analytics')
            except Exception as _live_ex:
                _logger().debug('message_stats: live-пуш analytics для %s не ушёл: %s',
                                gid, _live_ex)
        except OSError as ex:
            _logger().warning('message_stats: запись %s не удалась: %s', gid, ex)
            # не теряем события — вернём в очередь
            with _LOCK:
                _PENDING.setdefault(gid, []).extend(batch)
                _DIRTY.add(gid)


def load_full(gid):
    """Все события сервера (для миграции/пересчётов)."""
    return _load(gid)


def save_full(gid, events):
    """Атомарно перезаписать события (использует миграция имён)."""
    data = [e for e in (events or []) if isinstance(e, dict)]
    _atomic_write(_path(str(gid)), data[-MAX_PER_GUILD:])


def attach_uids(events, resolver):
    """Проставить uid старым записям (миграция «до ID»).

    resolver(имя) -> user_id | None (ког даёт словарь по участникам сервера:
    display_name/name/nick без учёта регистра). Нераспознанные остаются без
    uid и группируются по имени — как раньше (окно скользящее, выйдут сами).
    Возвращает число проставленных.
    """
    changed = 0
    for ev in events or []:
        if not isinstance(ev, dict) or ev.get('uid'):
            continue
        name = str(ev.get('author') or '').strip()
        if not name:
            continue
        try:
            uid = resolver(name)
        except Exception:
            uid = None
        try:
            uid = int(uid) if uid else 0
        except (TypeError, ValueError):
            uid = 0
        if uid:
            ev['uid'] = str(uid)
            changed += 1
    return changed


def merge_members_top(msgs, limit=10):
    """Топ участников, склеенный ПО ЛИЧНОСТИ (uid), — чистая функция.

    Смена ника не дробит счёт: у одного uid записи складываются, а подпись
    берётся из САМОЙ СВЕЖЕЙ записи (файл хронологический — просто перезапись).
    Старые записи без uid группируются по имени (прежнее поведение).
    """
    counts, labels = {}, {}
    for m in msgs or []:
        if not isinstance(m, dict):
            continue
        author = str(m.get('author') or m.get('user_name') or '?')
        uid = str(m.get('uid') or '')
        key = ('u:' + uid) if uid else ('n:' + author)
        counts[key] = counts.get(key, 0) + 1
        labels[key] = author
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return [{'name': labels[k], 'messages': c,
             'uid': (k[2:] if k.startswith('u:') else None)}
            for k, c in ranked]


def _loop():
    while not _STOP.wait(FLUSH_EVERY):
        try:
            flush_all()
        except Exception as ex:            # флаш не должен ронять поток
            _logger().debug('message_stats: флаш подавлен: %s', ex)


def start():
    """Поднять фоновый писатель (повторный вызов безопасен)."""
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return _THREAD
    _STOP.clear()
    _THREAD = threading.Thread(target=_loop, name='msg-stats', daemon=True)
    _THREAD.start()
    return _THREAD


def stop():
    """Остановить и сбросить всё на диск (выход из бота, тесты)."""
    _STOP.set()
    if _THREAD:
        _THREAD.join(timeout=5)
    try:
        flush_all()
    except Exception as ex:
        _logger().debug('message_stats: stop-флаш подавлен: %s', ex)


# Бот стартует — писатель поднимается сам при импорте сервиса ботом.
if os.path.isdir('data') or os.path.isdir('cogs'):
    try:
        start()
    except Exception as _sx1:
        _logger().debug('message_stats: автостарт подавлен: %s', _sx1)
