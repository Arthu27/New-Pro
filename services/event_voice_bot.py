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

# Opus для voice protocol — пробуем несколько имён .so
try:
    if not discord.opus.is_loaded():
        for _name in (
            'libopus.so.0', 'libopus.so', 'opus',
            '/usr/lib/x86_64-linux-gnu/libopus.so.0',
            '/usr/lib/libopus.so.0',
        ):
            try:
                discord.opus.load_opus(_name)
                if discord.opus.is_loaded():
                    break
            except Exception:
                continue
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
_last_join_ts = 0.0
_last_silence_ts = 0.0
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
                              channel_id: int | None = None,
                              *, force: bool = False) -> tuple[bool, str]:
    """Держать event-бота в войсе. Сами не leave'им без zombie.

    Silence ON → unmute + opus keepalive (mute+play флапает).
    discord-in-lib-dead → repair без force_drop (иначе видно leave).
    """
    global _joining, _suppress_rejoin_until, _last_join_ts
    from services.voice_stay_health import (
        really_in_channel, force_drop_voice, voice_client_connected,
        silence_ping_enabled, start_silence_keepalive)

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

    _silence_on = silence_ping_enabled() and discord.opus.is_loaded()
    _self_mute = not _silence_on
    _self_deaf = True

    ok, vc, reason = really_in_channel(client, cid)
    if ok and not force:
        if _silence_on and vc:
            try:
                if not vc.is_playing():
                    start_silence_keepalive(vc)
            except Exception:
                pass
        return True, f'Уже в <#{cid}>'

    drop = (reason == 'zombie-lib-in-discord-out')
    if reason == 'zombie-lib-in-discord-out':
        log.warning('event-bot zombie — drop+reconnect')
    elif reason == 'discord-in-lib-dead':
        log.warning('event-bot lib-dead (Discord ещё in) — repair без leave')
    elif reason == 'out':
        log.warning('event-bot out — reconnect без drop')

    lock = _lock()
    try:
        await asyncio.wait_for(lock.acquire(), timeout=8.0)
    except asyncio.TimeoutError:
        return False, 'ensure занят — retry'
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

        if drop:
            await force_drop_voice(client, channel.guild)
        else:
            for stale in list(client.voice_clients or []):
                try:
                    if not voice_client_connected(stale):
                        await stale.disconnect(force=True)
                except Exception:
                    pass

        vc = discord.utils.get(client.voice_clients, guild=channel.guild)
        if vc and voice_client_connected_safe(vc):
            if getattr(vc.channel, 'id', None) == cid:
                ok2, _, reason2 = really_in_channel(client, cid)
                if ok2:
                    if _silence_on:
                        try:
                            if not vc.is_playing():
                                start_silence_keepalive(vc)
                        except Exception:
                            pass
                    return True, f'Уже в <#{cid}>'
                if reason2 == 'zombie-lib-in-discord-out':
                    await force_drop_voice(client, channel.guild)
                else:
                    try:
                        await vc.disconnect(force=True)
                    except Exception:
                        pass
            else:
                try:
                    await asyncio.wait_for(vc.move_to(channel), timeout=15.0)
                    _last_join_ts = time.time()
                    if _silence_on:
                        start_silence_keepalive(vc)
                    log.info('event-bot moved to voice %s', cid)
                    return True, f'Переехал в <#{cid}>'
                except Exception:
                    try:
                        await vc.disconnect(force=True)
                    except Exception:
                        pass

        async def _connect_once():
            await asyncio.wait_for(
                channel.connect(
                    self_deaf=_self_deaf, self_mute=_self_mute, reconnect=True,
                    timeout=20.0),
                timeout=25.0)
            if _silence_on:
                try:
                    await channel.guild.change_voice_state(
                        channel=channel, self_mute=False, self_deaf=True)
                except Exception:
                    pass
                vc_now = discord.utils.get(
                    client.voice_clients, guild=channel.guild)
                start_silence_keepalive(vc_now)

        try:
            await _connect_once()
        except Exception as ex:
            msg = str(ex).lower() or type(ex).__name__
            if 'already' in msg and 'connected' in msg:
                await force_drop_voice(client, channel.guild)
                try:
                    await _connect_once()
                except Exception as ex2:
                    return False, f'Не удалось зайти: {ex2 or type(ex2).__name__}'
            else:
                return False, f'Не удалось зайти: {ex or type(ex).__name__}'

        _last_join_ts = time.time()
        # confirm Discord
        confirmed = False
        deadline = time.time() + 8.0
        while time.time() < deadline:
            ok3, vc3, why3 = really_in_channel(client, cid)
            if ok3 or why3 == 'lib-ok-discord-unknown':
                if _silence_on and vc3:
                    try:
                        if not vc3.is_playing():
                            start_silence_keepalive(vc3)
                    except Exception:
                        pass
                confirmed = True
                break
            await asyncio.sleep(0.35)
        log.info('event-bot joined voice %s (silence=%s confirmed=%s)',
                 cid, _silence_on, confirmed)
        if not confirmed:
            await force_drop_voice(client, channel.guild)
            try:
                await _connect_once()
                _last_join_ts = time.time()
            except Exception as ex3:
                return False, f'Не удалось зайти: {ex3 or type(ex3).__name__}'
        return True, f'Зашёл в <#{cid}>'
    finally:
        _joining = False
        _suppress_rejoin_until = time.time() + 15.0
        try:
            lock.release()
        except Exception:
            pass



def voice_client_connected_safe(vc) -> bool:
    try:
        from services.voice_stay_health import voice_client_connected
        return voice_client_connected(vc)
    except Exception:
        try:
            return bool(vc and vc.is_connected())
        except Exception:
            return False


def _schedule_rejoin(client: discord.Client, reason: str = '',
                     *, force: bool = False) -> None:
    """Бесконечный возврат в войс — без потолка попыток."""
    global _rejoin_task, _suppress_rejoin_until
    if client.is_closed():
        return
    if force:
        _suppress_rejoin_until = 0.0
    elif time.time() < _suppress_rejoin_until:
        return
    if _joining and not force:
        return

    async def _go():
        from services.voice_stay_health import really_in_channel
        attempt = 0
        while not client.is_closed() and not _stop_runner:
            attempt += 1
            delay = 0.3 if attempt == 1 else (1.0 if attempt < 5 else 5.0)
            await asyncio.sleep(delay)
            if client.is_closed() or _stop_runner:
                return
            if _joining:
                continue
            if (not force) and time.time() < _suppress_rejoin_until:
                continue
            try:
                if not client.is_ready():
                    continue
            except Exception:
                continue
            cid = _resolve_event_voice_channel_id()
            use_force = force or attempt > 1 or reason in (
                'kicked-or-moved', 'resume', 'gateway-disconnect',
                'soft-reconnect', 'zombie', 'daemon-heartbeat',
                'monitor-miss')
            if not use_force:
                ok, _, why = really_in_channel(client, cid)
                if ok:
                    if attempt > 1:
                        log.info('event-bot rejoin skip — healthy in %s', cid)
                    return
                if why.startswith('zombie'):
                    use_force = True
            ok, msg = await ensure_voice_joined(client, force=use_force)
            if ok:
                log.info('event-bot rejoin (%s try=%s force=%s): %s',
                         reason or 'auto', attempt, use_force, msg)
                return
            log.warning('event-bot rejoin fail (%s try=%s): %s',
                        reason or 'auto', attempt, msg)

    if force and _rejoin_task is not None and not _rejoin_task.done():
        try:
            _rejoin_task.cancel()
        except Exception:
            pass
        _rejoin_task = None
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
            from cogs import mafia as mafia_mod
            Mafia = mafia_mod.Mafia
            if guilds:
                await bot.add_cog(Mafia(bot), guilds=guilds)
            else:
                await bot.add_cog(Mafia(bot))
            for view_name in ('PublicLobbyView', 'HostPanelView'):
                ViewCls = getattr(mafia_mod, view_name, None)
                if ViewCls is None:
                    continue
                try:
                    bot.add_view(ViewCls(0) if view_name == 'PublicLobbyView'
                                 else ViewCls())
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
    # Members — только если включён в Developer Portal (иначе бот не коннектится).
    # Вкл: EVENT_BOT_MEMBERS_INTENT=1 + Privileged Intent «Server Members».
    _mem = (os.environ.get('EVENT_BOT_MEMBERS_INTENT') or '').strip().lower()
    intents.members = _mem in ('1', 'true', 'yes', 'on')
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
            _schedule_rejoin(bot, 'on_ready-fail', force=True)

    @bot.event
    async def on_resumed():
        # Gateway resume ≠ voice dead. Сначала Discord-truth, без force_drop.
        log.info('event-bot resumed — soft voice check (без force rebuild)')

        async def _after_ready():
            for _ in range(20):
                try:
                    if client_ready(bot):
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.25)
            await asyncio.sleep(0.5)
            cid = _resolve_event_voice_channel_id()
            if not cid:
                return
            from services.voice_stay_health import really_in_channel
            ok, _, why = really_in_channel(bot, cid)
            if ok:
                log.info('event-bot resume: voice already ok (%s)', why)
                return
            # Только если реально выпал — reconnect (zombie → force)
            force = (why or '').startswith('zombie') or why == 'discord-in-lib-dead'
            _schedule_rejoin(bot, 'resume', force=force)

        try:
            bot.loop.create_task(_after_ready(), name='event-voice-after-resume')
        except Exception:
            _schedule_rejoin(bot, 'resume', force=False)

    @bot.event
    async def on_voice_state_update(member, before, after):
        global _suppress_rejoin_until
        me = bot.user
        if me is None or member is None:
            return
        if int(getattr(member, 'id', 0) or 0) != int(me.id):
            return
        # Свой disconnect во время connect — не штормить
        if _joining:
            return
        target = _resolve_event_voice_channel_id()
        if not target:
            return
        before_id = getattr(getattr(before, 'channel', None), 'id', None)
        after_id = getattr(getattr(after, 'channel', None), 'id', None)
        if after_id == target:
            return
        if before_id == target or after_id is None or after_id != target:
            if (time.time() - (_last_join_ts or 0)) < 3.0:
                return
            log.warning(
                'event-bot left voice (before=%s after=%s) — return NOW to %s',
                before_id, after_id, target)
            _suppress_rejoin_until = 0.0
            _schedule_rejoin(bot, 'kicked-or-moved', force=True)

    @bot.event
    async def on_disconnect():
        # Gateway упал — connect сейчас бесполезен (висит). Ждём resume.
        log.warning('event-bot gateway disconnect — жду resume (без connect)')

    return bot


def client_ready(client) -> bool:
    try:
        return bool(client.is_ready())
    except Exception:
        return False


async def _monitor_event_voice(client: discord.Client) -> None:
    """Каждые 2с: Discord-truth + soft reconnect (+ opt-in silence)."""
    global _last_silence_ts, _last_join_ts
    from services.voice_stay_health import (
        really_in_channel,
        silence_ping_enabled, start_silence_keepalive)

    await client.wait_until_ready()
    await asyncio.sleep(1)
    _silence = silence_ping_enabled()
    if _silence and not discord.opus.is_loaded():
        log.warning('event-bot: VOICE_SILENCE_PING=1 без libopus — silence OFF')
        _silence = False
    if _silence:
        log.info('event-bot silence keepalive ON')
    else:
        log.info('event-bot silence keepalive OFF (default)')
    while not client.is_closed() and not _stop_runner:
        await asyncio.sleep(1.5)
        if _joining:
            continue
        try:
            if not client.is_ready():
                continue
        except Exception:
            continue
        cid = _resolve_event_voice_channel_id()
        if not cid:
            continue
        now = time.time()
        ok, vc, why = really_in_channel(client, cid)
        if ok:
            if _silence and vc and not vc.is_playing():
                try:
                    start_silence_keepalive(vc)
                    _last_silence_ts = now
                except Exception as ex:
                    log.debug('event-bot silence: %s', ex)
            continue
        # miss: suppress только 5с после своего join
        if (now < _suppress_rejoin_until
                and (now - (_last_join_ts or 0)) < 5.0
                and why != 'out'):
            continue
        log.warning('event-bot monitor miss (%s) — return now', why)
        ok2, msg = await ensure_voice_joined(client, cid, force=False)
        if ok2:
            log.info('event-bot monitor: %s', msg)
        else:
            log.warning('event-bot monitor: %s', msg)
            _schedule_rejoin(client, 'monitor-miss', force=True)


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
    from services.voice_stay_health import really_in_channel

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
        target = int(cfg.get('channel_id') or 0) or DEFAULT_EVENT_VOICE_CHANNEL_ID
        try:
            ok, vc, _why = really_in_channel(client, target)
            voice_ok = bool(ok)
            if vc is not None:
                voice_id = getattr(getattr(vc, 'channel', None), 'id', None)
            if not voice_id and ok:
                voice_id = target
        except Exception:
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
