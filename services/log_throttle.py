"""Противодействие «спаму» логов: пачкование одинаковых событий.

Боль владельца (2026-08): «когда меняю роли/профили — лог-канал засыпает
одинаковыми карточками». При массовой раздаче ролей каждая выдача — своя
карточка. Throttler копит события с живым окном: одиночное — ~1.2с, поток
продлевает окно до 6с, и всё уходит ОДНОЙ сводной карточкой. Полный аудит при этом не теряется: save_event
слушатели пишут по-прежнему на каждое событие; пачкует только вывод в канал.

Использование:
    from services.log_throttle import member_updates
    member_updates.feed(key, item, flush_factory)
    # flush_factory — async-функция(items), которая шлёт сводную карточку.
"""
from __future__ import annotations

import asyncio

from logger import get_logger

_log = get_logger('log_throttle')


class Throttler:
    """Накопитель с живым окном (дебаунс): одиночное событие уходит почти
    сразу (linger), при продолжающемся потоке окно продлевается до
    hard_cap — массовая раздача ролей всё равно соберётся одной карточкой,
    но ждать «12 секунд на одну роль» больше не приходится."""

    def __init__(self, window: float = 1.2, max_keep: int = 200,
                 hard_cap: float = 6.0):
        self.window = float(window)
        self.max_keep = int(max_keep)
        self.hard_cap = float(hard_cap)
        self._buffers = {}

    def feed(self, key, item, flush_factory) -> int:
        """Добавить событие в пачку. Возвращает размер пачки."""
        buf = self._buffers.setdefault(key, {'items': [], 'task': None})
        if len(buf['items']) < self.max_keep:
            buf['items'].append(item)
        task = buf['task']
        if task is None or task.done():
            buf['task'] = asyncio.get_event_loop().create_task(
                self._flush_later(key, flush_factory))
        return len(buf['items'])

    async def _flush_later(self, key, flush_factory):
        import time as _time
        buf = self._buffers.get(key) or {}
        deadline = _time.monotonic() + self.hard_cap
        seen = 0
        try:
            while _time.monotonic() < deadline:
                await asyncio.sleep(self.window)
                n = len((self._buffers.get(key) or {}).get('items') or [])
                if n <= seen:
                    break  # тишина: хватит копить — отправляем
                seen = n
        except asyncio.CancelledError:  # pragma: no cover - отмена при выгрузке
            return
        buf = self._buffers.pop(key, None)
        items = (buf or {}).get('items') or []
        if not items:
            return
        try:
            await flush_factory(items)
        except Exception as ex:
            _log.debug('flush %s: %s', key, ex)

    def pending(self, key) -> int:
        buf = self._buffers.get(key) or {}
        return len(buf.get('items') or [])


# Глобальный накопитель для апдейтов участников (роли/профили).
# 12 секунд — за это время «раздача ролей пачкой» как правило заканчивается,
# а для одиночных действий лог остаётся почти мгновенным.
member_updates = Throttler(window=1.2, hard_cap=6.0)
