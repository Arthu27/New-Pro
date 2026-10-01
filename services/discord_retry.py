# -*- coding: utf-8 -*-
"""Повтор Discord API при 502/503 (upstream connect error).

Discord иногда рвёт HTTP до ответа — бот показывал сырой 503.
Делаем 2–3 попытки с короткой паузой.
"""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger('discord_retry')

_RETRY_STATUS = frozenset({500, 502, 503, 504})


def _is_retryable(exc) -> bool:
    try:
        import discord
        if isinstance(exc, discord.DiscordServerError):
            status = int(getattr(getattr(exc, 'response', None), 'status', 0)
                         or getattr(exc, 'status', 0) or 0)
            return status in _RETRY_STATUS or status == 0
        # иногда приходит как HTTPException со status 503
        if isinstance(exc, discord.HTTPException):
            status = int(getattr(exc, 'status', 0) or 0)
            return status in _RETRY_STATUS
    except Exception:
        pass
    text = str(exc or '').lower()
    return ('503' in text or '502' in text
            or 'upstream connect' in text
            or 'connection termination' in text)


async def call(coro_factory, *, attempts=3, delays=(0.4, 1.0, 2.0),
               label='discord'):
    """Вызвать coro_factory() с ретраями на 502/503.

    coro_factory — callable без аргументов, каждый раз новый awaitable
    (нельзя reuse уже awaited coroutine).
    """
    last = None
    n = max(1, int(attempts or 1))
    for i in range(n):
        try:
            return await coro_factory()
        except Exception as ex:
            last = ex
            if i + 1 >= n or not _is_retryable(ex):
                raise
            pause = delays[min(i, len(delays) - 1)] if delays else 0.5
            log.info('%s: %s — повтор %s/%s через %.1fs',
                     label, ex, i + 2, n, pause)
            await asyncio.sleep(pause)
    raise last


def friendly_api_error(exc) -> str:
    """Текст для модератора вместо сырого upstream connect error."""
    if _is_retryable(exc):
        return (
            'Discord сейчас не отвечает (сбой связи 503). '
            'Наказание могло не примениться — нажми ещё раз через пару секунд.'
        )
    try:
        import discord
        if isinstance(exc, discord.Forbidden):
            return 'У бота не хватило прав на это действие.'
    except Exception:
        pass
    text = str(exc or '').strip()
    return text[:300] if text else 'Неизвестная ошибка Discord.'
