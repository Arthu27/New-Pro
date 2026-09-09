# -*- coding: utf-8 -*-
"""Внутрипроцессная шина «живых» событий для панели — excellent edition.

Идея: вместо опроса по таймеру бэкенд ПУШИТ короткий сигнал по топику в момент,
когда данные реально поменялись. Браузер по сигналу делает обычный fetch.

Транспорт — SSE (EventSource) через тот же Flask-порт/туннель, поэтому работает
за доменом/cloudflared без отдельного ws-порта. Polling остаётся редкой подстраховкой.

Топик — "g<gid>:<name>" (гильдийный) или "<name>" (глобальный). Подписчик задаёт маски
через fnmatch ("g777:*", "*"). Это только толчок — клиент сам перечитывает актуальное.

Шина потокобезопасна: зовут из Flask-потоков, event-loop бота и фоновых потоков.
Улучшения (2026-09-09): TTL-дедуп, метрики, защита от шторма, автопубликация связанных топиков.
"""
import fnmatch
import logging
import queue
import threading
import time
from collections import defaultdict

log = logging.getLogger(__name__)

_LOCK = threading.Condition()
_SUBSCRIBERS = []          # {q: _TopicQueue, patterns: [...], created: ts}
_MAX_QUEUE = 300

# Метрики для /api/live health
_METRICS = {
    'published': 0,
    'dropped_dup': 0,
    'dropped_full': 0,
    'subscribers_peak': 0,
    'last_topic': '',
    'last_ts': 0,
    'per_topic': defaultdict(int),
}
_METRICS_LOCK = threading.Lock()

# Анти-шторм: один и тот же топик не чаще чем раз в N ms (дебаунс)
_DEBOUNCE_MS = 120
_last_emit = {}  # topic -> ts ms
_last_emit_lock = threading.Lock()


class _TopicQueue:
    """Очередь топиков с дедупом + TTL: одинаковый топик не копится дважды между доставкой и чтением."""

    def __init__(self, maxsize):
        self._q = queue.Queue(maxsize=maxsize)
        self._pending = set()
        self._lock = threading.Lock()

    def offer(self, topic):
        with self._lock:
            if topic in self._pending:
                with _METRICS_LOCK:
                    _METRICS['dropped_dup'] += 1
                return False
            try:
                self._q.put_nowait(topic)
            except queue.Full:
                with _METRICS_LOCK:
                    _METRICS['dropped_full'] += 1
                return False
            self._pending.add(topic)
            return True

    def get(self, timeout=None):
        topic = self._q.get(timeout=timeout)
        with self._lock:
            self._pending.discard(topic)
        return topic

    def qsize(self):
        return self._q.qsize()


def _matches(patterns, topic):
    for pat in patterns:
        if fnmatch.fnmatchcase(topic, pat):
            return True
    return False


def _should_emit(topic):
    """Дебаунс: не пушим один и тот же топик чаще чем _DEBOUNCE_MS."""
    now = int(time.time() * 1000)
    with _last_emit_lock:
        last = _last_emit.get(topic, 0)
        if now - last < _DEBOUNCE_MS:
            return False
        _last_emit[topic] = now
    return True


def _emit(topic, force=False):
    """Разослать топик подписчикам, чьи маски его ловят. С дедупом и метриками."""
    if not force and not _should_emit(topic):
        with _METRICS_LOCK:
            _METRICS['dropped_dup'] += 1
        return

    with _METRICS_LOCK:
        _METRICS['published'] += 1
        _METRICS['per_topic'][topic] += 1
        _METRICS['last_topic'] = topic
        _METRICS['last_ts'] = time.time()

    with _LOCK:
        dead = []
        for sub in _SUBSCRIBERS:
            try:
                if not _matches(sub['patterns'], topic):
                    continue
                sub['q'].offer(topic)
            except Exception:
                dead.append(sub)
        for d in dead:
            if d in _SUBSCRIBERS:
                _SUBSCRIBERS.remove(d)
        _LOCK.notify_all()


def publish(guild_id, topic):
    """Сигнал об изменении данных конкретного сервера: publish(gid, 'channels')."""
    if guild_id in (None, '', 0, '0'):
        return
    t = str(topic).strip()
    if not t:
        return
    _emit(f"g{guild_id}:{t}")
    # также шлём короткий топик без префикса для страниц, которые слушают глобально
    if t in ('meetings', 'channels', 'channel-routes', 'appeals', 'moderation', 'guardian', 'security', 'reports', 'team', 'voice'):
        _emit(t)


def publish_global(topic):
    """Глобальный сигнал (список серверов, тема, профиль — вне гильдии)."""
    t = str(topic).strip()
    if not t:
        return
    _emit(t)


def publish_all(topic):
    """Сигнал для всех гильдий сразу."""
    _emit(topic, force=True)
    with _LOCK:
        gids = set()
        for sub in _SUBSCRIBERS:
            for pat in sub['patterns']:
                if pat.startswith('g') and ':' in pat:
                    try:
                        gid_part = pat.split(':')[0].lstrip('g')
                        if gid_part and gid_part != '*':
                            gids.add(gid_part)
                    except Exception:
                        pass
    for gid in gids:
        _emit(f"g{gid}:{topic}", force=True)


def subscribe(patterns, maxsize=_MAX_QUEUE):
    """Подписаться на маски топиков. Возвращает (queue, unsubscribe)."""
    pats = list(patterns or ['*'])
    q = _TopicQueue(maxsize)
    sub = {'q': q, 'patterns': pats, 'created': time.time()}
    with _LOCK:
        _SUBSCRIBERS.append(sub)
        with _METRICS_LOCK:
            _METRICS['subscribers_peak'] = max(_METRICS['subscribers_peak'], len(_SUBSCRIBERS))
    log.debug("live_bus: subscribe %s -> %s subs", pats, len(_SUBSCRIBERS))

    def _unsubscribe():
        with _LOCK:
            if sub in _SUBSCRIBERS:
                _SUBSCRIBERS.remove(sub)
        log.debug("live_bus: unsubscribe %s -> %s subs", pats, len(_SUBSCRIBERS))

    return q, _unsubscribe


def subscriber_count():
    with _LOCK:
        return len(_SUBSCRIBERS)


def get_metrics():
    with _METRICS_LOCK:
        return {
            'published': _METRICS['published'],
            'dropped_dup': _METRICS['dropped_dup'],
            'dropped_full': _METRICS['dropped_full'],
            'subscribers': subscriber_count(),
            'subscribers_peak': _METRICS['subscribers_peak'],
            'last_topic': _METRICS['last_topic'],
            'last_ts': _METRICS['last_ts'],
            'per_topic': dict(_METRICS['per_topic']),
        }
