# -*- coding: utf-8 -*-
"""Профи-статистика модераторов: счётчик сообщений по дням.

Бот пишет каждое сообщение через record_message() (буфер в памяти),
фоновый поток сбрасывает буфер в bot.db (GuildData 'mod_activity')
раз в 60 секунд. Панель читает message_counts() — буфер своего процесса
синхронизируется при чтении, поэтому даже при раздельных процессах
данные не теряются.

Правила:
- храним только последние 30 дней (дневная сетка, старьё подрезается);
- любая ошибка глушится в debug — счётчик НЕ должен ронять on_message.
"""
import threading
import time
from datetime import date, timedelta

from db import GuildData
from logger import get_logger

_log = get_logger('mod_activity')

_keep_days = 30
_buf = {}
_buf_lock = threading.Lock()
_flush_thread = None


def _store():
    return GuildData('mod_activity')


def record_message(guild_id, user_id, name=''):
    """Учесть сообщение участника (вызов из on_message бота)."""
    try:
        key = (int(guild_id), str(user_id))
        with _buf_lock:
            day = _buf.setdefault(key, {})
            today = str(date.today())
            day[today] = int(day.get(today, 0) or 0) + 1
            if name:
                day['__name'] = str(name)[:100]
        _ensure_flusher()
    except Exception as _ex:
        _log.debug('record_message(): подавлено: %s', _ex)


def _ensure_flusher():
    global _flush_thread
    if _flush_thread is None or not _flush_thread.is_alive():
        _flush_thread = threading.Thread(target=_flush_loop, name='mod-activity-flush', daemon=True)
        _flush_thread.start()


def _flush_loop():
    while True:
        time.sleep(60)
        try:
            flush()
        except Exception as _ex:
            _log.debug('_flush_loop(): подавлено: %s', _ex)


def flush():
    """Слить буфер в bot.db. Идемпотентно, безопасно при пустом буфере."""
    global _buf
    with _buf_lock:
        if not _buf:
            return
        pending = _buf
        _buf = {}
    store = _store()
    cutoff = str(date.today() - timedelta(days=_keep_days))
    for (gid, uid), day in pending.items():
        day = dict(day)
        name = day.pop('__name', None)
        if not day:
            continue
        try:
            rec = store.get(gid, uid) or {}
            if not isinstance(rec, dict):
                rec = {}
            days = rec.get('days') or {}
            if not isinstance(days, dict):
                days = {}
            for d, cnt in day.items():
                try:
                    cnt = int(cnt)
                except (TypeError, ValueError) as _ex:
                    _log.debug('flush(): битое значение дня %s: %s', d, _ex)
                    continue
                days[d] = int(days.get(d, 0) or 0) + cnt
            days = {d: c for d, c in days.items() if d >= cutoff and isinstance(c, int)}
            rec['days'] = days
            if name:
                rec['name'] = name
            store.set(gid, uid, rec)
        except Exception as _ex:
            _log.debug('flush(): подавлено: %s', _ex)
            # возвращаем недоучтённое в буфер, чтобы не потерять счёт
            with _buf_lock:
                merged = _buf.setdefault((gid, uid), {})
                for d, cnt in day.items():
                    merged[d] = int(merged.get(d, 0) or 0) + cnt


def message_counts(guild_id, days=7, as_of=None):
    """Сообщения за последние N дней: {user_id: {'user_id','name','messages'}}."""
    flush()
    store = _store()
    start = (as_of or date.today()) - timedelta(days=max(1, int(days)) - 1)
    start_s = str(start)
    out = {}
    try:
        raw = store.get_all(int(guild_id)) or {}
    except Exception as _ex:
        _log.debug('message_counts(): подавлено: %s', _ex)
        return out
    for uid, rec in raw.items():
        if not isinstance(rec, dict):
            continue
        daymap = rec.get('days') or {}
        if not isinstance(daymap, dict):
            continue
        total = 0
        for dstr, cnt in daymap.items():
            try:
                if dstr >= start_s and isinstance(cnt, int):
                    total += cnt
            except Exception as _ex:
                _log.debug('message_counts(): битая метка дня %s: %s', dstr, _ex)
                continue
        out[str(uid)] = {
            'user_id': str(uid),
            'name': str(rec.get('name') or ''),
            'messages': total,
        }
    return out
