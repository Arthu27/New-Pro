# -*- coding: utf-8 -*-
"""Общая проверка «реально ли бот в войсе» для stay 24/7.

Нельзя доверять только ``vc.is_connected()``: после gateway resume /
voice WS timeout discord.py часто оставляет zombie VoiceClient
(is_connected=True, а Discord уже channel=null). Тогда rejoin делает
skip, и бот часами «выпал».

Истина = Discord voice state (me.voice) + VoiceClient.
Latency inf сразу после connect — норма, не повод для force-rejoin.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

import discord

from logger import get_logger

log = get_logger('voice_stay_health')

# Периодический force-reconnect только если сидим очень долго.
# Частый soft-reconnect сам валил Event-бота (disconnect → fail → out).
SOFT_RECONNECT_SEC = 3 * 60 * 60  # 3 часа


def _member_voice_state(guild: discord.Guild, user_id: int):
    """(known, channel_id|None). known=False если me/member недоступен."""
    try:
        mem = guild.get_member(int(user_id))
        if mem is None:
            mem = getattr(guild, 'me', None)
        if mem is None:
            return False, None
        vs = getattr(mem, 'voice', None)
        if vs is None:
            return True, None
        ch = getattr(vs, 'channel', None)
        return True, (int(ch.id) if ch is not None else None)
    except Exception:
        return False, None


def discord_me_voice(client: discord.Client,
                     guild: Optional[discord.Guild] = None,
                     channel_id: Optional[int] = None
                     ) -> Tuple[bool, Optional[int]]:
    """(known, channel_id). channel_id=None и known=True → Discord: не в войсе."""
    try:
        me = getattr(client, 'user', None)
        if me is None:
            return False, None
        if guild is None and channel_id:
            ch = client.get_channel(int(channel_id))
            guild = getattr(ch, 'guild', None)
        if guild is not None:
            return _member_voice_state(guild, me.id)
        any_known = False
        for g in list(getattr(client, 'guilds', None) or []):
            known, cid = _member_voice_state(g, me.id)
            if known:
                any_known = True
                if cid:
                    return True, cid
        if any_known:
            return True, None
        return False, None
    except Exception as ex:
        log.debug('discord_me_voice: %s', ex)
        return False, None


def discord_me_channel_id(client: discord.Client,
                          guild: Optional[discord.Guild] = None,
                          channel_id: Optional[int] = None) -> Optional[int]:
    known, cid = discord_me_voice(client, guild=guild, channel_id=channel_id)
    return cid if known else None


def voice_client_connected(vc) -> bool:
    """Library говорит connected + канал есть (latency не смотрим)."""
    if vc is None:
        return False
    try:
        return bool(vc.is_connected())
    except Exception:
        return False


def voice_latency_bad(vc) -> bool:
    """True если latency явно мёртвая (inf/NaN/>60). Сразу после connect бывает."""
    if vc is None:
        return True
    try:
        lat = getattr(vc, 'latency', None)
        if lat is None:
            return False
        if isinstance(lat, (int, float)) and (math.isinf(lat) or math.isnan(lat)):
            return True
        if isinstance(lat, (int, float)) and lat > 60.0:
            return True
    except Exception:
        return False
    return False


def voice_client_alive(vc) -> bool:
    """Connected и latency не мёртвая. Для soft-reconnect / heal."""
    return voice_client_connected(vc) and not voice_latency_bad(vc)


def really_in_channel(client: discord.Client, channel_id: int
                      ) -> Tuple[bool, Optional[object], str]:
    """True если бот реально в channel_id (Discord + library).

    Returns: (ok, voice_client_or_None, reason)

    ok=True причины:
      - ok: Discord и library согласны
      - ok-latency-high: Discord in + connected, latency пока плохая
        (НЕ повод force-rejoin — иначе шторм после connect)
      - lib-ok-discord-unknown: Discord state недоступен, library connected
    """
    cid = int(channel_id or 0)
    if not cid:
        return False, None, 'no-channel'
    vc = None
    lib_connected = False
    for v in list(getattr(client, 'voice_clients', None) or []):
        try:
            ch = getattr(v, 'channel', None)
            if getattr(ch, 'id', None) == cid and voice_client_connected(v):
                vc = v
                lib_connected = True
                break
        except Exception:
            continue

    known, disc = discord_me_voice(client, channel_id=cid)

    if known and disc == cid and lib_connected:
        if voice_latency_bad(vc):
            return True, vc, 'ok-latency-high'
        return True, vc, 'ok'
    if known and disc == cid and not lib_connected:
        return False, vc, 'discord-in-lib-dead'
    if known and disc != cid and lib_connected:
        return False, vc, 'zombie-lib-in-discord-out'
    if known and disc != cid and not lib_connected:
        return False, vc, 'out'
    if lib_connected:
        return True, vc, 'lib-ok-discord-unknown'
    return False, vc, 'out'


async def force_drop_voice(client: discord.Client,
                           guild: Optional[discord.Guild] = None) -> None:
    """Жёстко сбросить VoiceClient перед свежим connect."""
    clients = list(getattr(client, 'voice_clients', None) or [])
    for v in clients:
        try:
            if guild is not None and getattr(v, 'guild', None) is not guild:
                continue
            await v.disconnect(force=True)
        except Exception as ex:
            log.debug('force_drop: %s', ex)
        try:
            cleanup = getattr(v, 'cleanup', None)
            if callable(cleanup):
                cleanup()
        except Exception:
            pass


def needs_soft_reconnect(last_join_ts: float, now: float,
                         interval: float = SOFT_RECONNECT_SEC) -> bool:
    if not last_join_ts:
        return False
    return (now - last_join_ts) >= interval
