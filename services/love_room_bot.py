# -*- coding: utf-8 -*-
"""Отдельный Love Room бот: панель V2 + temp VC на двоих.

Токен: LOVE_ROOM_BOT_TOKEN в .env (НЕ коммитить).
Каналы/категория: config/love_room.json + env overrides (IDs=0 OK).

НЕ сидит в love rooms (в отличие от Event voice-stay).
Запуск: main.py (второй клиент) или scripts/run_love_room.py + systemd.
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

import discord

from logger import get_logger

log = get_logger('love_room_bot')

_love_client: Optional[discord.Client] = None
_stop_runner = False
_commands_synced = False
_synced_command_names: list[str] = []


def love_bot_token() -> str:
    return (os.environ.get('LOVE_ROOM_BOT_TOKEN') or '').strip()


def token_hint(tok: str | None = None) -> str:
    t = tok if tok is not None else love_bot_token()
    if not t:
        return ''
    return ('••••' + t[-4:]) if len(t) >= 4 else '••••'


def _sync_guilds(bot: discord.Client) -> list:
    guilds = []
    try:
        from config import Config
        guilds = list(Config.guild_objects() or [])
    except Exception as ex:
        log.debug('love guild_objects: %s', ex)
    if guilds:
        return guilds
    # LOVE_ROOM_GUILD_ID / JSON
    try:
        from services.love_room_store import load_love_room_cfg, cfg_int
        gid = cfg_int(load_love_room_cfg(), 'guild_id')
        if gid:
            return [discord.Object(id=gid)]
    except Exception:
        pass
    out = []
    for g in list(getattr(bot, 'guilds', None) or []):
        try:
            out.append(discord.Object(id=int(g.id)))
        except Exception:
            pass
    return out


async def _ensure_love_emojis(bot) -> None:
    """Залить только love_* стикеры на этот application (не основной бот)."""
    try:
        from services.menu_emojis import ensure_love_room_emojis
        await ensure_love_room_emojis(bot)
    except Exception as ex:
        log.debug('love emojis: %s', ex)


async def _load_and_sync_commands(bot) -> list[str]:
    global _commands_synced, _synced_command_names
    names: list[str] = []
    guilds = _sync_guilds(bot)

    try:
        if bot.get_cog('love_room') is None:
            from cogs.love_room import LoveRoom, ClassicLoveRoomView
            if guilds:
                await bot.add_cog(LoveRoom(bot), guilds=guilds)
            else:
                await bot.add_cog(LoveRoom(bot))
            try:
                bot.add_view(ClassicLoveRoomView())
            except Exception:
                pass
            log.info('love-bot: cog love_room загружен')
    except Exception as ex:
        log.warning('love-bot add_cog: %s', ex)
        return names

    tree = getattr(bot, 'tree', None)
    if tree is None:
        return names

    try:
        if guilds:
            for g in guilds:
                try:
                    synced = await tree.sync(guild=g)
                    for c in synced or []:
                        n = getattr(c, 'name', None)
                        if n and n not in names:
                            names.append(str(n))
                    log.info('love-bot slash sync guild=%s → %s',
                             getattr(g, 'id', g),
                             [getattr(c, 'name', '?') for c in (synced or [])])
                except Exception as ex:
                    log.warning('love-bot sync guild %s: %s',
                                getattr(g, 'id', g), ex)
        else:
            synced = await tree.sync()
            for c in synced or []:
                n = getattr(c, 'name', None)
                if n and n not in names:
                    names.append(str(n))
            log.info('love-bot slash sync GLOBAL → %s', names)
    except Exception as ex:
        log.warning('love-bot tree.sync: %s', ex)

    _synced_command_names = list(names)
    _commands_synced = bool(names)
    return names


def build_love_client():
    """Bot: love-room panel + voice cleanup. Не коннектится в VC."""
    from discord.ext import commands

    intents = discord.Intents.none()
    intents.guilds = True
    intents.voice_states = True
    intents.members = True  # move/roster; enable in Dev Portal
    bot = commands.Bot(command_prefix=commands.when_mentioned,
                       intents=intents,
                       help_command=None)

    @bot.event
    async def on_ready():
        global _commands_synced
        log.info('love-bot online as %s (%s) token=%s',
                 bot.user, bot.user.id, token_hint())
        try:
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name='love room'),
                status=discord.Status.online)
        except Exception as ex:
            log.debug('love-bot presence: %s', ex)

        # Ведущий seed (lightweight)
        for g in list(bot.guilds):
            try:
                from services.vedushiy_role_seed import apply_vedushiy_on_ready
                report = await apply_vedushiy_on_ready(g)
                log.info('vedushiy seed guild=%s: %s role=%s',
                         g.id, report.get('reason'), report.get('role_id'))
            except Exception as ex:
                log.debug('vedushiy on_ready: %s', ex)

        if not _commands_synced or bot.get_cog('love_room') is None:
            try:
                names = await _load_and_sync_commands(bot)
                if names:
                    log.info('love-bot commands ready: %s', names)
                else:
                    log.warning('love-bot commands: sync пуст '
                                '(бот не на сервере / scopes / ID=0 OK)')
            except Exception as ex:
                log.warning('love-bot commands setup: %s', ex)

        # love_* application emoji — только этот бот
        try:
            await _ensure_love_emojis(bot)
        except Exception as ex:
            log.debug('love emoji ensure: %s', ex)

        # Startup sweep empty rooms (no-op if category_id=0)
        try:
            from cogs.love_room import startup_sweep
            rep = await startup_sweep(bot)
            log.info('love-bot sweep: %s', rep)
        except Exception as ex:
            log.debug('love sweep: %s', ex)

        # Auto-publish panel if channel configured
        try:
            from services.love_room_store import load_love_room_cfg, cfg_int
            cfg = load_love_room_cfg()
            panel_id = cfg_int(cfg, 'panel_channel_id')
            if panel_id:
                ch = bot.get_channel(panel_id)
                if ch is None:
                    try:
                        ch = await bot.fetch_channel(panel_id)
                    except Exception:
                        ch = None
                # Не спамим каждый ready — только если канал пуст от наших панелей
                # (пропускаем авто-паблиш; slash /love-room-panel ручной)
                log.info('love-bot panel channel configured: %s '
                         '(publish via /love-room-panel)', panel_id)
        except Exception as ex:
            log.debug('panel cfg: %s', ex)

    @bot.event
    async def on_disconnect():
        log.warning('love-bot gateway disconnect')

    return bot


async def start_love_room_bot() -> Optional[discord.Client]:
    """Старт love-бота, если LOVE_ROOM_BOT_TOKEN задан. Иначе None."""
    global _love_client, _stop_runner, _commands_synced
    token = love_bot_token()
    if not token:
        log.info('LOVE_ROOM_BOT_TOKEN пуст — love-бот не запускается')
        return None
    if _love_client is not None and not _love_client.is_closed():
        return _love_client
    _stop_runner = False
    _commands_synced = False
    _love_client = build_love_client()

    async def _runner():
        global _love_client, _commands_synced
        delay = 2
        while not _stop_runner:
            client = _love_client
            if client is None or client.is_closed():
                _commands_synced = False
                client = build_love_client()
                _love_client = client
            try:
                log.info('love-bot connecting… token=%s', token_hint(token))
                await client.start(token)
                if _stop_runner:
                    break
                log.warning('love-bot session ended — retry in %ss', delay)
            except discord.LoginFailure:
                log.error('LOVE_ROOM_BOT_TOKEN неверный — love-бот остановлен')
                break
            except Exception as ex:
                log.warning('love-bot error: %s — retry in %ss', ex, delay)
            await asyncio.sleep(delay)
            delay = min(15, max(2, delay + 1))
            if not _stop_runner:
                _commands_synced = False
                _love_client = build_love_client()

    asyncio.get_running_loop().create_task(_runner(), name='love-room-bot')
    return _love_client


def get_love_client() -> Optional[discord.Client]:
    return _love_client


def love_bot_status() -> dict:
    tok = love_bot_token()
    client = _love_client
    online = False
    name = ''
    uid = ''
    if client is not None and not client.is_closed():
        try:
            online = bool(client.is_ready())
        except Exception:
            online = False
        u = getattr(client, 'user', None)
        if u is not None:
            name = str(getattr(u, 'name', '') or '')
            try:
                uid = str(u.id)
            except Exception:
                uid = ''
    return {
        'token_set': bool(tok),
        'token_hint': token_hint(tok),
        'online': online,
        'name': name,
        'id': uid,
        'commands_synced': bool(_commands_synced),
        'commands': list(_synced_command_names),
        'sits_in_voice': False,
    }
