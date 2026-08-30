# -*- coding: utf-8 -*-
"""services/ttl_cache — компактный потокобезопасный кэш с TTL и лимитом.

Зачем: кэши без предела — утечка памяти. Бот на VDS жил 14 часов и
перезапускался: _message_cache AI-чата хранил по записи на КАЖДОГО
пользователя (`guild_user`) и никогда не чистился — на оживлённом сервере
RSS рос до лимита, Linux OOM-киллер убивал процесс, start.sh поднимал его
заново (перезапуск без видимой причины).

TTLMap:
- максимум maxsize записей: при переполнении сначала удаляются ПРОСРОЧЕННЫЕ,
  затем — самые старые (LRU-подобно);
- запись старше ttl секунд на чтении считается отсутствующей и удаляется;
- потокобезопасно (бот + панель в одном процессе, кэш дергается из разных
  потоков/задач).
"""
import threading
import time

__all__ = ['TTLMap']


class TTLMap:
    """Кэш «ключ -> значение» с TTL и жёстким лимитом записей."""

    def __init__(self, maxsize: int = 512, ttl: float = 300.0):
        self.maxsize = max(1, int(maxsize))
        self.ttl = max(1.0, float(ttl))
        self._data = {}
        self._lock = threading.Lock()

    def put(self, key, value, now: float = None):
        """Сохранить значение. При переполнении — вытеснить старое."""
        now = time.time() if now is None else now
        with self._lock:
            if key not in self._data and len(self._data) >= self.maxsize:
                self._evict(now)
            self._data[key] = (value, now)

    def get(self, key, now: float = None):
        """Вернуть значение, если оно свежее ttl; иначе None (и удалить)."""
        now = time.time() if now is None else now
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            value, ts = item
            if now - ts > self.ttl:
                self._data.pop(key, None)
                return None
            return value

    def clear(self):
        with self._lock:
            self._data.clear()

    def __len__(self):
        with self._lock:
            return len(self._data)

    def _evict(self, now: float):
        """Освободить место: просроченные, затем самые старые (~10%)."""
        expired = [k for k, (_, ts) in self._data.items() if now - ts > self.ttl]
        for k in expired:
            self._data.pop(k, None)
        need = max(1, self.maxsize // 10)
        while len(self._data) >= self.maxsize and need > 0:
            oldest = min(self._data.items(), key=lambda kv: kv[1][1])[0]
            self._data.pop(oldest, None)
            need -= 1
