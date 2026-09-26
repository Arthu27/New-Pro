# -*- coding: utf-8 -*-
"""Неблокирующий файловый I/O для async-кода бота.

Зачем: на Windows под антивирусом/OneDrive даже маленький open()/os.replace()
может дать задержку в доли-секунды и больше. В async-обработчике (on_message,
on_member_join, колбэки панели, планировщик) это МОРОЗИТ event loop шлюза —
ровно тот класс инцидентов, что был с psutil open_files (зависание 6.9с).

Правило: в любой async-функции файлы состояния data/*.json читать/писать
только через load_json_async/save_json_async — дисковый вызов уходит в
рабочий поток через asyncio.to_thread, loop не встаёт.

Под капотом — общий json_store (кэш по mtime/size + атомарная запись), так
что второй системы хранения не появляется и кэш общий с остальным ботом.
Синхронные load_json_sync/save_json_sync оставлены для кода вне loop'а
(Flask-потоки, фоновые потоки, старт до подключения к Discord).
"""
import asyncio

import json_store


async def load_json_async(path, default=None, *, log=None):
    """Неблокирующее чтение JSON через общий кэширующий json_store."""
    return await asyncio.to_thread(json_store.load_json, path, default, log=log)


async def save_json_async(path, data, *, indent=2, log=None) -> bool:
    """Неблокирующая атомарная запись JSON через json_store (в потоке)."""
    return await asyncio.to_thread(
        json_store.save_json, path, data, indent=indent, log=log)


# Синхронные обёртки на тот же стор — для не-async кода, чтобы везде был
# один и тот же бэкенд (и единый кэш).
def load_json_sync(path, default=None, *, log=None):
    return json_store.load_json(path, default, log=log)


def save_json_sync(path, data, *, indent=2, log=None) -> bool:
    return json_store.save_json(path, data, indent=indent, log=log)
