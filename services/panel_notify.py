# -*- coding: utf-8 -*-
"""Уведомление панели о событии (веб-колокольчик / Discord-канал / email).

Вынесено из cogs/ticket.py: тикет-система полностью снята с эксплуатации
(решение владельца 2026-08-31, её роль выполняет /report), а этот помощник
никакой тикетной логики не содержит — им пользуются cogs/moderation.py и
cogs/warnings.py, чтобы событие наказания долетело до панели.

Полностью fail-safe: выполняется в фоне и никогда не роняет вызвавший код.
"""

from logger import get_logger

_log = get_logger("panel_notify")

import asyncio

import discord


def notify_panel_event(interaction, event, title, body):
    """Уведомить панель о событии по настроенным каналам (веб/Discord/email).

    interaction — объект, из которого берётся клиент бота (нужен, чтобы
    отправить эмбед в настроенный Discord-канал).
    """
    try:
        from services.notification_dispatcher import notify_event as _notify_event
        loop = asyncio.get_running_loop()
        client = interaction.client

        def _sender(cid, title_, body_):
            try:
                ch = client.get_channel(int(cid))
                if not ch:
                    return False
                emb = discord.Embed(title=title_, description=(body_ or '')[:4000],
                                    color=0xC8922A)
                asyncio.run_coroutine_threadsafe(ch.send(embed=emb), loop).result(timeout=10)
                return True
            except Exception:
                return False

        loop.run_in_executor(None, lambda: _notify_event(event, title, body,
                                                        discord_sender=_sender))
    except Exception as _ex:
        _log.debug("notify_panel_event(): подавлено: %s", _ex)


# Старое имя из cogs/ticket.py — оставлено алиасом, чтобы внешние callers
# (и старые тесты) не сломались в один момент с удалением кога.
_notify_panel_ticket_event = notify_panel_event
