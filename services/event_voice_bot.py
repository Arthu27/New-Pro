# -*- coding: utf-8 -*-
"""Отдельный Event-бот: войс 24/7 + слеш /mafia.

Токен: EVENT_BOT_TOKEN в .env (НЕ коммитить) — правится из панели
«Совместные боты». Канал: config/event_voice_stay.json.

Stay всегда включён — без выключателя и без лимита попыток.
Если кикнули/отвалился — сразу и бесконечно заходит обратно
(voice_state_update + монитор каждые 2с + daemon heartbeat).

Запуск: start.bat → main.py (второй клиент) или
scripts/run_event_voice_stay.py.
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

# Канал войса Event-бота (заказ владельца 2026-09-22).
DEFAULT_EVENT_VOICE_CHANNEL_ID = 1550986919981351043
_CFG_REL = 'config/event_voice_stay.json'

# Opus для voice protocol (если есть в системе) — без play тоже полезно.
try:
    if not discord.opus.is_loaded():
        discord.opus.load_opus('libopus.so.0')
except Exception:
    pass

_event_client: Optional[discord.Client] = None
_monitor_task: Optional[asyncio.Task] = None
_connect_lock: Optional[asyncio.Lock] = None
_rejoin_task: Optional[asyncio.Task] = None
_stop_runner = False
_voice_channel_id: Optional[int] = None
_stay_enabled = True
# Пока сами коннектимся/переезжаем — не реагируем на свой же disconnect
# (иначе race: disconnect → on_voice_state_update → rejoin поверх connect).
_joining = False
_suppress_rejoin_until = 0.0
_commands_synced = False
_synced_command_names: list[str] = []


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cfg_path() -> str:
    return os.path.join(_repo_root(), _CFG_REL)


def event_bot_token() -> str:
    return (os.environ.get('EVENT_BOT_TOKEN') or '').strip()


def load_event_voice_cfg() -> dict:
    """channel_id из JSON / env. Stay всегда включён (без выключателя)."""
    cfg = {
        'channel_id': str(DEFAULT_EVENT_VOICE_CHANNEL_ID),
        'stay_enabled': True,
    }
    path = _cfg_path()
    try:
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as fh:
                raw = json.load(fh) or {}
            if isinstance(raw, dict):
                cid = raw.get('channel_id') or raw.get('VOICE_CHANNEL_ID') or ''
                if str(cid).strip() and str(cid).strip() not in ('0', 'none'):
                    cfg['channel_id'] = str(cid).strip()
    except Exception as ex:
        log.debug('event voice cfg load: %s', ex)
    env_cid = (os.environ.get('EVENT_VOICE_CHANNEL_ID') or '').strip()
    if env_cid and env_cid not in ('0', 'none', 'None'):
        cfg['channel_id'] = env_cid
    # Stay нельзя выключить — бот всегда в войсе
    cfg['stay_enabled'] = True
    os.environ['EVENT_VOICE_STAY_ENABLED'] = '1'
    return cfg


def save_event_voice_cfg(channel_id: str | int | None = None,
                         stay_enabled: bool | None = None) -> dict:
    """Сохранить канал. stay_enabled игнорируется — всегда True."""
    cur = load_event_voice_cfg()
    if channel_id is not None:
        cur['channel_id'] = str(channel_id or '').strip()
    cur['stay_enabled'] = True
    payload = {
        'channel_id': cur['channel_id'],
        'stay_enabled': True,
        'note': 'Event-бот всегда сидит в этом войсе (24/7). '
                'Кикнули — сразу заходит обратно. Stay выключить нельзя. '
                'Токен — только EVENT_BOT_TOKEN в .env.',
    }
    path = _cfg_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    global _voice_channel_id, _stay_enabled
    try:
        _voice_channel_id = int(payload['channel_id']) if payload['channel_id'] else None
    except (TypeError, ValueError):
        _voice_channel_id = DEFAULT_EVENT_VOICE_CHANNEL_ID
    _stay_enabled = True
    if _voice_channel_id:
        os.environ['EVENT_VOICE_CHANNEL_ID'] = str(_voice_channel_id)
    os.environ['EVENT_VOICE_STAY_ENABLED'] = '1'
    return payload


def _resolve_event_voice_channel_id() -> Optional[int]:
    global _voice_channel_id
    # всегда перечитываем cfg/env — панель могла сменить канал
    cfg = load_event_voice_cfg()
    try:
        cid = int(str(cfg.get('channel_id') or 0) or 0) or None
    except (TypeError, ValueError):
        cid = DEFAULT_EVENT_VOICE_CHANNEL_ID
    _voice_channel_id = cid or DEFAULT_EVENT_VOICE_CHANNEL_ID
    return _voice_channel_id


def _stay_on() -> bool:
    """Stay всегда включён — без лимитов и выключателя."""
    global _stay_enabled
    _stay_enabled = True
    return True


def _lock() -> asyncio.Lock:
    global _connect_lock
    if _connect_lock is None:
        _connect_lock = asyncio.Lock()
    return _connect_lock


async def ensure_voice_joined(client: discord.Client | None = None,
                              channel_id: int | None = None) -> tuple[bool, str]:
    """Подключить event-бота к войсу. Кикнули — зови снова (без лимитов)."""
    global _joining, _suppress_rejoin_until
    client = client or _event_client
    if client is None or client.is_closed():
        return False, 'Event-бот офлайн — запусти через start.bat'
    try:
        if not client.is_ready():
            return False, 'Event-бот ещё не ready'
    except Exception:
        return False, 'Event-бот не ready'
    cid = int(channel_id or _resolve_event_voice_channel_id() or 0)
    if not cid:
        return False, 'Не задан голосовой канал event-бота'
    async with _lock():
        try:
            for v in list(client.voice_clients or []):
                if (v.is_connected()
                        and getattr(getattr(v, 'channel', None), 'id', None) == cid):
                    return True, f'Уже в <#{cid}>'
        except Exception:
            pass
        _joining = True
        _suppress_rejoin_until = time.time() + 5.0
        try:
            channel = client.get_channel(cid)
            if channel is None:
                try:
                    channel = await client.fetch_channel(cid)
                except Exception as ex:
                    return False, f'Канал не найден: {ex}'
            if not isinstance(channel, discord.VoiceChannel):
                return False, 'ID не голосовой канал'
            for stale in list(client.voice_clients or []):
                try:
                    if not stale.is_connected():
                        await stale.disconnect(force=True)
                except Exception:
                    pass
            vc = discord.utils.get(client.voice_clients, guild=channel.guild)
            if vc and vc.is_connected():
                if getattr(vc.channel, 'id', None) == cid:
                    return True, f'Уже в <#{cid}>'
                try:
                    await vc.move_to(channel)
                    log.info('event-bot moved to voice %s', cid)
                    return True, f'Переехал в <#{cid}>'
                except Exception:
                    try:
                        await vc.disconnect(force=True)
                    except Exception:
                        pass
            try:
                # self_deaf=True стабильнее для «просто сидеть» 24/7
                await channel.connect(
                    self_deaf=True, self_mute=True, reconnect=True)
                log.info('event-bot joined voice %s', cid)
                return True, f'Зашёл в <#{cid}>'
            except Exception as ex:
                msg = str(ex).lower()
                if 'already' in msg and 'connected' in msg:
                    return True, f'Уже подключён (<#{cid}>)'
                return False, f'Не удалось зайти: {ex}'
        finally:
            _joining = False
            _suppress_rejoin_until = time.time() + 1.0


def _schedule_rejoin(client: discord.Client, reason: str = '') -> None:
    """Бесконечный возврат в войс — без потолка попыток."""
    global _rejoin_task
    if client.is_closed():
        return
    if time.time() < _suppress_rejoin_until:
        return
    if _joining:
        return

    async def _go():
        attempt = 0
        # короткий старт, потом плато 5с — никогда не сдаёмся
        while not client.is_closed() and not _stop_runner:
            attempt += 1
            delay = 0.3 if attempt == 1 else (1.0 if attempt < 5 else 5.0)
            await asyncio.sleep(delay)
            if client.is_closed() or _stop_runner:
                return
            if _joining:
                continue
            if time.time() < _suppress_rejoin_until:
                continue
            try:
                if not client.is_ready():
                    continue
            except Exception:
                continue
            cid = _resolve_event_voice_channel_id()
            for v in list(client.voice_clients or []):
                try:
                    if (v.is_connected()
                            and getattr(v.channel, 'id', None) == cid):
                        if attempt > 1:
                            log.info('event-bot rejoin skip — already in %s', cid)
                        return
                except Exception:
                    pass
            ok, msg = await ensure_voice_joined(client)
            if ok:
                log.info('event-bot rejoin (%s try=%s): %s',
                         reason or 'auto', attempt, msg)
                return
            log.warning('event-bot rejoin fail (%s try=%s): %s',
                        reason or 'auto', attempt, msg)

    if _rejoin_task is not None and not _rejoin_task.done():
        return
    try:
        _rejoin_task = client.loop.create_task(_go(), name='event-voice-rejoin')
    except Exception as ex:
        log.debug('schedule rejoin: %s', ex)


def _event_sync_guilds(bot: discord.Client) -> list:
    """Гильдии для slash-синка: Config → иначе все серверы, где бот уже есть."""
    guilds = []
    try:
        from config import Config
        guilds = list(Config.guild_objects() or [])
    except Exception as ex:
        log.debug('event guild_objects: %s', ex)
    if guilds:
        return guilds
    out = []
    for g in list(getattr(bot, 'guilds', None) or []):
        try:
            out.append(discord.Object(id=int(g.id)))
        except Exception:
            pass
    return out


async def _load_and_sync_event_commands(bot) -> list[str]:
    """Загрузить только Мафию и синкнуть slash (без event-panel)."""
    global _commands_synced, _synced_command_names
    names: list[str] = []
    guilds = _event_sync_guilds(bot)

    # Мафия на Event-боте — публичное лобби + /mafia для ведущего
    try:
        if bot.get_cog('mafia') is None:
            from cogs.mafia import Mafia, PublicLobbyView, HostPanelView
            if guilds:
                await bot.add_cog(Mafia(bot), guilds=guilds)
            else:
                await bot.add_cog(Mafia(bot))
            try:
                bot.add_view(PublicLobbyView(0))
                bot.add_view(HostPanelView())
            except Exception:
                pass
            log.info('event-bot: cog mafia загружен')
    except Exception as ex:
        log.warning('event-bot add_cog mafia: %s', ex)
        return names

    # Снять старый EventPanel, если вдруг остался в памяти
    try:
        if bot.get_cog('EventPanel') is not None:
            await bot.remove_cog('EventPanel')
            log.info('event-bot: EventPanel снят')
    except Exception as ex:
        log.debug('event-bot remove EventPanel: %s', ex)

    tree = getattr(bot, 'tree', None)
    if tree is None:
        log.warning('event-bot: нет command tree')
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
                    log.info('event-bot slash sync guild=%s → %s',
                             getattr(g, 'id', g),
                             [getattr(c, 'name', '?') for c in (synced or [])])
                except Exception as ex:
                    log.warning('event-bot sync guild %s: %s',
                                getattr(g, 'id', g), ex)
        else:
            synced = await tree.sync()
            for c in synced or []:
                n = getattr(c, 'name', None)
                if n and n not in names:
                    names.append(str(n))
            log.info('event-bot slash sync GLOBAL → %s',
                     [getattr(c, 'name', '?') for c in (synced or [])])
    except Exception as ex:
        log.warning('event-bot tree.sync: %s', ex)

    _synced_command_names = list(names)
    _commands_synced = bool(names)
    return names


def build_event_client():
    """Bot: voice-stay + slash /mafia (ведущий). Без event-panel."""
    from discord.ext import commands

    intents = discord.Intents.none()
    intents.guilds = True
    intents.voice_states = True
    # members не privileged-обязателен для slash: роли приходят в interaction
    bot = commands.Bot(command_prefix=commands.when_mentioned,
                       intents=intents,
                       help_command=None)

    @bot.event
    async def on_ready():
        global _commands_synced, _monitor_task
        log.info('event-bot online as %s (%s)', bot.user, bot.user.id)
        try:
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name='Events'),
                status=discord.Status.online)
        except Exception as ex:
            log.debug('event-bot presence: %s', ex)

        # Команды — /mafia у Event-бота (без event-panel)
        if not _commands_synced or bot.get_cog('mafia') is None:
            try:
                names = await _load_and_sync_event_commands(bot)
                if names:
                    log.info('event-bot commands ready: %s', names)
                else:
                    log.warning('event-bot commands: sync вернул пусто '
                                '(проверь, что бот на сервере + scopes)')
            except Exception as ex:
                log.warning('event-bot commands setup: %s', ex)
        try:
            from services.menu_emojis import schedule_ensure_menu_emojis
            schedule_ensure_menu_emojis(bot)
        except Exception:
            pass
        try:
            from services.menu_banners import ensure_sticker_pack
            ensure_sticker_pack()
        except Exception:
            pass

        # Stay всегда включён — сразу в войс + монитор
        cid = _resolve_event_voice_channel_id()
        if not cid:
            return
        if _monitor_task is None or _monitor_task.done():
            _monitor_task = bot.loop.create_task(
                _monitor_event_voice(bot), name='event-voice-monitor')
        ok, msg = await ensure_voice_joined(bot, cid)
        if ok:
            log.info('event-bot voice: %s', msg)
        else:
            log.warning('event-bot voice: %s', msg)
            _schedule_rejoin(bot, 'on_ready-fail')

    @bot.event
    async def on_resumed():
        log.info('event-bot resumed — проверяю войс')
        _schedule_rejoin(bot, 'resume')

    @bot.event
    async def on_voice_state_update(member, before, after):
        me = bot.user
        if me is None or member is None:
            return
        if int(getattr(member, 'id', 0) or 0) != int(me.id):
            return
        if _joining or time.time() < _suppress_rejoin_until:
            return
        target = _resolve_event_voice_channel_id()
        before_id = getattr(getattr(before, 'channel', None), 'id', None)
        after_id = getattr(getattr(after, 'channel', None), 'id', None)
        if after_id == target:
            return
        if before_id == target or after_id is None or after_id != target:
            log.warning(
                'event-bot left voice (before=%s after=%s) — returning to %s',
                before_id, after_id, target)
            _schedule_rejoin(bot, 'kicked-or-moved')

    @bot.event
    async def on_disconnect():
        log.warning('event-bot gateway disconnect — schedule rejoin')
        try:
            _schedule_rejoin(bot, 'gateway-disconnect')
        except Exception:
            pass

    return bot


async def _monitor_event_voice(client: discord.Client) -> None:
    """Каждые 2с проверяем войс — без backoff-потолка, всегда возвращаемся."""
    await client.wait_until_ready()
    await asyncio.sleep(1)
    while not client.is_closed() and not _stop_runner:
        await asyncio.sleep(2)
        if _joining or time.time() < _suppress_rejoin_until:
            continue
        try:
            if not client.is_ready():
                continue
        except Exception:
            continue
        cid = _resolve_event_voice_channel_id()
        if not cid:
            continue
        in_target = False
        for v in list(client.voice_clients or []):
            try:
                if v.is_connected() and getattr(v.channel, 'id', None) == cid:
                    in_target = True
                    break
            except Exception:
                pass
        if in_target:
            continue
        ok, msg = await ensure_voice_joined(client, cid)
        if ok:
            log.info('event-bot monitor: %s', msg)
        else:
            log.warning('event-bot monitor: %s', msg)
            _schedule_rejoin(client, 'monitor-miss')


async def start_event_bot() -> Optional[discord.Client]:
    """Старт event-бота, если EVENT_BOT_TOKEN задан. Иначе None."""
    global _event_client, _stop_runner, _voice_channel_id, _commands_synced
    token = event_bot_token()
    if not token:
        log.info('EVENT_BOT_TOKEN пуст — event-бот не запускается')
        return None
    if _event_client is not None and not _event_client.is_closed():
        return _event_client
    _stop_runner = False
    _voice_channel_id = None  # перечитать cfg
    _commands_synced = False
    load_event_voice_cfg()
    _event_client = build_event_client()

    async def _runner():
        global _event_client, _commands_synced
        delay = 2
        while not _stop_runner:
            client = _event_client
            if client is None or client.is_closed():
                _commands_synced = False
                client = build_event_client()
                _event_client = client
            try:
                log.info('event-bot connecting… channel=%s',
                         _resolve_event_voice_channel_id())
                await client.start(token)
                if _stop_runner:
                    break
                log.warning('event-bot session ended — retry in %ss', delay)
            except discord.LoginFailure:
                log.error('EVENT_BOT_TOKEN неверный — event-бот остановлен')
                break
            except Exception as ex:
                log.warning('event-bot error: %s — retry in %ss', ex, delay)
            await asyncio.sleep(delay)
            # без потолка — максимум 15с между перезапусками сессии
            delay = min(15, max(2, delay + 1))
            if not _stop_runner:
                _commands_synced = False
                _event_client = build_event_client()

    asyncio.get_running_loop().create_task(_runner(), name='event-voice-bot')
    return _event_client


def get_event_client() -> Optional[discord.Client]:
    return _event_client


def event_bot_status() -> dict:
    """Снимок для панели «Совместные боты» (без сырого токена)."""
    tok = event_bot_token()
    cfg = load_event_voice_cfg()
    client = _event_client
    online = False
    name = ''
    uid = ''
    voice_id = None
    voice_ok = False
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
        for v in list(getattr(client, 'voice_clients', None) or []):
            try:
                if v.is_connected():
                    voice_ok = True
                    voice_id = getattr(getattr(v, 'channel', None), 'id', None)
                    break
            except Exception:
                pass
    hint = ''
    if tok:
        hint = ('••••' + tok[-4:]) if len(tok) >= 4 else '••••'
    return {
        'token_set': bool(tok),
        'token_hint': hint,
        'channel_id': str(cfg.get('channel_id') or ''),
        'stay_enabled': bool(cfg.get('stay_enabled', True)),
        'online': online,
        'name': name,
        'id': uid,
        'voice_connected': voice_ok,
        'voice_channel_id': str(voice_id) if voice_id else '',
        'default_channel_id': str(DEFAULT_EVENT_VOICE_CHANNEL_ID),
        'commands_synced': bool(_commands_synced),
        'commands': list(_synced_command_names),
    }
