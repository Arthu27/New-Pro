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


_event_voice_ctrl = None


def _get_event_ctrl(client: discord.Client | None = None):
    """VoiceStayController для event-бота (lock/backoff/voice_targets)."""
    global _event_voice_ctrl
    client = client or _event_client
    if client is None:
        return _event_voice_ctrl
    if _event_voice_ctrl is not None and _event_voice_ctrl.client is client:
        return _event_voice_ctrl
    from services import voice_stay as VS
    _event_voice_ctrl = VS.attach(client, 'event')
    cid = _resolve_event_voice_channel_id()
    if cid:
        _event_voice_ctrl.seed_from_channel_id(int(cid))
    return _event_voice_ctrl


def _lock() -> asyncio.Lock:
    global _connect_lock
    if _connect_lock is None:
        _connect_lock = asyncio.Lock()
    return _connect_lock


async def ensure_voice_joined(client: discord.Client | None = None,
                              channel_id: int | None = None,
                              *, force: bool = False) -> tuple[bool, str]:
    """Подключить event-бота к войсу через VoiceStayController.

    force=True — сбросить zombie VoiceClient и зайти заново.
    Connect timeout=30, reconnect=True, self_deaf (в контроллере).
    """
    global _joining, _suppress_rejoin_until, _last_join_ts
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

    ctrl = _get_event_ctrl(client)
    if ctrl is None:
        return False, 'voice_stay недоступен'
    _joining = True
    try:
        ok, msg = await ctrl.ensure_joined(
            channel_id=cid, force=force, reason='ensure')
        if ok:
            _last_join_ts = time.time()
        return ok, msg
    finally:
        _joining = False
        _suppress_rejoin_until = time.time() + 8.0


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
    """Бесконечный возврат в войс — exponential backoff в VoiceStayController."""
    global _rejoin_task, _suppress_rejoin_until
    if client.is_closed():
        return
    if force:
        _suppress_rejoin_until = 0.0
    elif time.time() < _suppress_rejoin_until:
        return
    if _joining and not force:
        return
    ctrl = _get_event_ctrl(client)
    if ctrl is None:
        return
    ctrl.schedule_rejoin(reason=reason or 'auto', force=force)


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

        # Stay всегда включён — voice_targets + watchdog (45с) + backoff
        cid = _resolve_event_voice_channel_id()
        if not cid:
            return
        ctrl = _get_event_ctrl(bot)
        if ctrl is not None:
            ctrl.seed_from_channel_id(int(cid))
            ctrl.bind_gateway_listeners()
            await ctrl.on_ready_once()
        if _monitor_task is None or _monitor_task.done():
            _monitor_task = bot.loop.create_task(
                _monitor_event_voice(bot), name='event-voice-monitor')

    @bot.event
    async def on_resumed():
        log.info('event-bot resumed — FORCE voice rebuild (после ready)')

        async def _after_ready():
            # дать gateway стабилизироваться, потом force join
            for _ in range(20):
                try:
                    if client_ready(bot):
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.25)
            await asyncio.sleep(0.5)
            _schedule_rejoin(bot, 'resume', force=True)

        try:
            bot.loop.create_task(_after_ready(), name='event-voice-after-resume')
        except Exception:
            _schedule_rejoin(bot, 'resume', force=True)

    @bot.event
    async def on_voice_state_update(member, before, after):
        ctrl = _get_event_ctrl(bot)
        if ctrl is None:
            return
        try:
            await ctrl.handle_voice_state(member, before, after)
        except Exception as ex:
            log.debug('event on_voice_state_update: %s', ex)

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
    """Совместимость: watchdog живёт в VoiceStayController (45с).

    Silence keepalive default OFF (VOICE_SILENCE_PING=0) — без libopus
    play() ломал voice WS → leave/join каждые ~20с.
    """
    ctrl = _get_event_ctrl(client)
    if ctrl is not None:
        ctrl.start_watchdog()
    while not client.is_closed() and not _stop_runner:
        await asyncio.sleep(60)


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
