# -*- coding: utf-8 -*-
"""Отдельный Event-бот: сидит в голосовом канале 24/7 (как основной).

Токен: EVENT_BOT_TOKEN в .env (НЕ коммитить).
Канал: EVENT_VOICE_CHANNEL_ID → config/event_voice_stay.json →
       тот же fallback, что у основного (VOICE_CHANNEL_ID / voice_stay.json).

Не грузит коги модерации — только presence + voice stay. Запускается
вторым клиентом из main.py, если токен задан.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Optional

import discord

from logger import get_logger

log = get_logger('event_voice_bot')

# Канал по умолчанию (заказ владельца 2026-09-22).
DEFAULT_EVENT_VOICE_CHANNEL_ID = 1547390550108540948

_event_client: Optional[discord.Client] = None
_monitor_task: Optional[asyncio.Task] = None


def event_bot_token() -> str:
    return (os.environ.get('EVENT_BOT_TOKEN') or '').strip()


def _resolve_event_voice_channel_id() -> Optional[int]:
    raw = (os.environ.get('EVENT_VOICE_CHANNEL_ID') or '').strip()
    if raw and raw not in ('0', 'none', 'None'):
        try:
            return int(raw) or None
        except (TypeError, ValueError):
            pass
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in ('config/event_voice_stay.json', 'config/voice_stay.json'):
        path = os.path.join(base, rel)
        try:
            if os.path.isfile(path):
                with open(path, encoding='utf-8') as fh:
                    data = json.load(fh) or {}
                cid = data.get('channel_id') or data.get('VOICE_CHANNEL_ID') or 0
                return int(str(cid).strip() or 0) or None
        except Exception as ex:
            log.debug('event voice cfg %s: %s', rel, ex)
    return DEFAULT_EVENT_VOICE_CHANNEL_ID


def build_event_client() -> discord.Client:
    """Лёгкий клиент: intents только guilds + voice states."""
    intents = discord.Intents.none()
    intents.guilds = True
    intents.voice_states = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        log.info('event-bot online as %s (%s)', client.user, client.user.id)
        try:
            await client.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name='Events'),
                status=discord.Status.online)
        except Exception as ex:
            log.debug('event-bot presence: %s', ex)
        stay = (os.environ.get('EVENT_VOICE_STAY_ENABLED') or '1').strip().lower() \
            not in ('0', 'false', 'no', 'off')
        cid = _resolve_event_voice_channel_id()
        if stay and cid:
            global _monitor_task
            if _monitor_task is None or _monitor_task.done():
                _monitor_task = client.loop.create_task(
                    _monitor_event_voice(client, cid))
            # мгновенный заход (как у основного бота)
            try:
                channel = client.get_channel(cid)
                if channel is None:
                    try:
                        channel = await client.fetch_channel(cid)
                    except Exception as ex:
                        log.debug('event-bot fetch channel: %s', ex)
                        channel = None
                if isinstance(channel, discord.VoiceChannel):
                    vc = discord.utils.get(client.voice_clients, guild=channel.guild)
                    if not vc or not vc.is_connected():
                        await asyncio.wait_for(
                            channel.connect(self_deaf=False), timeout=60.0)
                        log.info('event-bot joined voice %s', cid)
            except Exception as ex:
                log.warning('event-bot initial voice join: %s', ex)
        else:
            log.info('event-bot voice stay off (cid=%s stay=%s)', cid, stay)

    return client


async def _monitor_event_voice(client: discord.Client, channel_id: int) -> None:
    """Держим войсе-сессию event-бота (reconnect каждые 30с при обрыве)."""
    await client.wait_until_ready()
    await asyncio.sleep(5)
    backoff_until = 0.0
    while not client.is_closed():
        await asyncio.sleep(30)
        if not client.is_ready():
            continue
        if time.time() < backoff_until:
            continue
        channel = client.get_channel(channel_id)
        if channel is None:
            try:
                channel = await client.fetch_channel(channel_id)
            except Exception:
                continue
        if not isinstance(channel, discord.VoiceChannel):
            continue
        vc = discord.utils.get(client.voice_clients, guild=channel.guild)
        if vc and vc.is_connected():
            continue
        try:
            await asyncio.wait_for(channel.connect(self_deaf=False), timeout=30.0)
            backoff_until = 0.0
            log.info('event-bot reconnected voice %s', channel_id)
        except asyncio.TimeoutError:
            backoff_until = time.time() + 60
            log.warning('event-bot voice connect timeout — pause 60s')
        except Exception as ex:
            backoff_until = time.time() + 30
            log.debug('event-bot voice reconnect: %s', ex)


async def start_event_bot() -> Optional[discord.Client]:
    """Старт event-бота, если EVENT_BOT_TOKEN задан. Иначе None."""
    global _event_client
    token = event_bot_token()
    if not token:
        log.info('EVENT_BOT_TOKEN пуст — event-бот не запускается')
        return None
    if _event_client is not None and not _event_client.is_closed():
        return _event_client
    _event_client = build_event_client()

    async def _runner():
        global _event_client
        delay = 5
        while True:
            client = _event_client
            if client is None or client.is_closed():
                client = build_event_client()
                _event_client = client
            try:
                log.info('event-bot connecting…')
                await client.start(token)
                delay = 5
            except discord.LoginFailure:
                log.error('EVENT_BOT_TOKEN неверный — event-бот остановлен')
                break
            except Exception as ex:
                log.warning('event-bot disconnect: %s — retry in %ss', ex, delay)
                try:
                    if not client.is_closed():
                        await client.close()
                except Exception:
                    pass
                await asyncio.sleep(delay)
                delay = min(60, delay * 2)
                _event_client = build_event_client()

    asyncio.get_running_loop().create_task(_runner(), name='event-voice-bot')
    return _event_client


def get_event_client() -> Optional[discord.Client]:
    return _event_client
