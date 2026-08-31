# -*- coding: utf-8 -*-
"""Внутрипроцессная шина «живых» событий для панели (замена опроса по таймеру).

Идея: вместо того чтобы каждая страница раз в N секунд дёргала API «а не
изменилось ли что?», бэкенд ПУШИТ в браузер короткий сигнал по топику в тот
момент, когда данные реально поменялись (сохранены настройки, создан канал,
пришёл участник, сброшен буфер сообщений и т.п.). Браузер по сигналу делает
обычный fetch — но только когда есть повод.

Транспорт — SSE (EventSource): обычный HTTP-ответ через тот же Flask/порт/туннель,
поэтому работает и за доменом/cloudflared без проброса отдельного ws-порта.
Медленный polling остаётся лишь редкой подстраховкой (если SSE не поднялся).

Топик — строка вида "g<guild_id>:<имя>" (гильдийный) или "<имя>" (глобальный).
Подписчик задаёт маски через fnmatch ("g777:*", "*"). Передавать данные не
нужно — это «толчок», клиент сам перечитывает актуальное.

Шина потокобезопасна: её зовут и из Flask-потоков, и из event-loop бота, и из
фоновых потоков записи.
"""
import fnmatch
import queue
import threading

_LOCK = threading.Condition()
_SUBSCRIBERS = []          # список словарей {q: Queue, patterns: [...]}
# Антидубль: если за тик топик пушится многократно — шлём один сигнал.
_MAX_QUEUE = 200


class _TopicQueue:
    """Очередь топиков с дедупом: одинаковый топик не копится дважды, а при
    чтении его снова можно прислать (т.е. дедуп работает только между
    доставкой и прочтением)."""

    def __init__(self, maxsize):
        self._q = queue.Queue(maxsize=maxsize)
        self._pending = set()
        self._lock = threading.Lock()

    def offer(self, topic):
        """True — добавлен, False — дубликат или переполнение."""
        with self._lock:
            if topic in self._pending:
                return False
            try:
                self._q.put_nowait(topic)
            except queue.Full:
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


def _emit(topic):
    """Разослать топик подписчикам, чьи маски его ловят.

    Дедуп: если для очереди такой топик уже лежит непрочитанным — не добавляем
    второй (антишторм). Маски проверяются ЗДЕСЬ: чужой сервер не должен течь в
    подписку, которая его не ждёт.
    """
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
            try:
                _SUBSCRIBERS.remove(d)
            except ValueError:
                pass
        _LOCK.notify_all()


def publish(guild_id, topic):
    """Сигнал об изменении данных конкретного сервера: publish(gid, 'channels')."""
    if guild_id in (None, '', 0, '0'):
        return
    _emit(f"g{guild_id}:{topic}")


def publish_global(topic):
    """Глобальный сигнал (список серверов, тема, профиль — вне гильдии)."""
    _emit(topic)


def subscribe(patterns, maxsize=_MAX_QUEUE):
    """Подписаться на маски топиков. Возвращает (queue, unsubscribe).

    В queue прилетают строки-топики. unsubscribe() снимает подписку.
    """
    pats = list(patterns or ['*'])
    q = _TopicQueue(maxsize)
    sub = {'q': q, 'patterns': pats}
    with _LOCK:
        _SUBSCRIBERS.append(sub)

    def _unsubscribe():
        with _LOCK:
            try:
                _SUBSCRIBERS.remove(sub)
            except ValueError:
                pass

    return q, _unsubscribe


def subscriber_count():
    """Диагностика: сколько активных SSE-подписок (для логов/тестов)."""
    with _LOCK:
        return len(_SUBSCRIBERS)
