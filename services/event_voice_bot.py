# -*- coding: utf-8 -*-
"""Отдельный Event-бот: сидит в голосовом канале 24/7 (как основной).

Токен: EVENT_BOT_TOKEN в .env (НЕ коммитить) — правится из панели
«Совместные боты». Канал/stay: config/event_voice_stay.json.

Не грузит коги модерации — только presence + voice stay. Запускается
вторым клиентом из main.py (start.bat), если токен задан.
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

DEFAULT_EVENT_VOICE_CHANNEL_ID = 1547390550108540948
_CFG_REL = 'config/event_voice_stay.json'

_event_client: Optional[discord.Client] = None
_monitor_task: Optional[asyncio.Task] = None
_connect_lock: Optional[asyncio.Lock] = None
_stop_runner = False
_voice_channel_id: Optional[int] = None
_stay_enabled = True


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cfg_path() -> str:
    return os.path.join(_repo_root(), _CFG_REL)


def event_bot_token() -> str:
    return (os.environ.get('EVENT_BOT_TOKEN') or '').strip()


def load_event_voice_cfg() -> dict:
    """channel_id + stay_enabled из JSON / env."""
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
                if 'stay_enabled' in raw:
                    cfg['stay_enabled'] = bool(raw.get('stay_enabled'))
    except Exception as ex:
        log.debug('event voice cfg load: %s', ex)
    env_cid = (os.environ.get('EVENT_VOICE_CHANNEL_ID') or '').strip()
    if env_cid and env_cid not in ('0', 'none', 'None'):
        cfg['channel_id'] = env_cid
    env_stay = (os.environ.get('EVENT_VOICE_STAY_ENABLED') or '').strip().lower()
    if env_stay in ('0', 'false', 'no', 'off'):
        cfg['stay_enabled'] = False
    elif env_stay in ('1', 'true', 'yes', 'on'):
        cfg['stay_enabled'] = True
    return cfg


def save_event_voice_cfg(channel_id: str | int | None = None,
                         stay_enabled: bool | None = None) -> dict:
    """Сохранить канал/stay в JSON (без токена)."""
    cur = load_event_voice_cfg()
    if channel_id is not None:
        cur['channel_id'] = str(channel_id or '').strip()
    if stay_enabled is not None:
        cur['stay_enabled'] = bool(stay_enabled)
    payload = {
        'channel_id': cur['channel_id'],
        'stay_enabled': cur['stay_enabled'],
        'note': 'Event-бот заходит в этот голосовой канал при старте '
                '(start.bat → main.py). Токен — только EVENT_BOT_TOKEN в .env.',
    }
    path = _cfg_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    # live apply
    global _voice_channel_id, _stay_enabled
    try:
        _voice_channel_id = int(payload['channel_id']) if payload['channel_id'] else None
    except (TypeError, ValueError):
        _voice_channel_id = DEFAULT_EVENT_VOICE_CHANNEL_ID
    _stay_enabled = bool(payload['stay_enabled'])
    if _voice_channel_id:
        os.environ['EVENT_VOICE_CHANNEL_ID'] = str(_voice_channel_id)
    os.environ['EVENT_VOICE_STAY_ENABLED'] = '1' if _stay_enabled else '0'
    return payload


def _resolve_event_voice_channel_id() -> Optional[int]:
    global _voice_channel_id
    if _voice_channel_id:
        return _voice_channel_id
    cfg = load_event_voice_cfg()
    try:
        cid = int(str(cfg.get('channel_id') or 0) or 0) or None
    except (TypeError, ValueError):
        cid = DEFAULT_EVENT_VOICE_CHANNEL_ID
    _voice_channel_id = cid or DEFAULT_EVENT_VOICE_CHANNEL_ID
    return _voice_channel_id


def _stay_on() -> bool:
    global _stay_enabled
    cfg = load_event_voice_cfg()
    _stay_enabled = bool(cfg.get('stay_enabled', True))
    return _stay_enabled


def _lock() -> asyncio.Lock:
    global _connect_lock
    if _connect_lock is None:
        _connect_lock = asyncio.Lock()
    return _connect_lock


async def ensure_voice_joined(client: discord.Client | None = None,
                              channel_id: int | None = None) -> tuple[bool, str]:
    """Подключить event-бота к войсу (с замком, без двойного connect)."""
    client = client or _event_client
    if client is None or client.is_closed() or not client.is_ready():
        return False, 'Event-бот офлайн — запусти через start.bat'
    if not _stay_on():
        return False, 'Voice stay выключен в настройках совместных ботов'
    cid = int(channel_id or _resolve_event_voice_channel_id() or 0)
    if not cid:
        return False, 'Не задан голосовой канал event-бота'
    async with _lock():
        channel = client.get_channel(cid)
        if channel is None:
            try:
                channel = await client.fetch_channel(cid)
            except Exception as ex:
                return False, f'Канал не найден: {ex}'
        if not isinstance(channel, discord.VoiceChannel):
            return False, 'ID не голосовой канал'
        vc = discord.utils.get(client.voice_clients, guild=channel.guild)
        if vc and vc.is_connected():
            if getattr(vc.channel, 'id', None) == cid:
                return True, f'Уже в <#{cid}>'
            try:
                await vc.move_to(channel)
                return True, f'Переехал в <#{cid}>'
            except Exception as ex:
                try:
                    await vc.disconnect(force=True)
                except Exception:
                    pass
        try:
            await asyncio.wait_for(channel.connect(self_deaf=False), timeout=45.0)
            log.info('event-bot joined voice %s', cid)
            return True, f'Зашёл в <#{cid}>'
        except Exception as ex:
            return False, f'Не удалось зайти: {ex}'


def build_event_client() -> discord.Client:
    """Лёгкий клиент: intents только guilds + voice states."""
    intents = discord.Intents.none()
    intents.guilds = True
    intents.voice_states = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        # on_ready также на resume — не рвём сессию повторным connect
        log.info('event-bot online as %s (%s)', client.user, client.user.id)
        try:
            await client.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name='Events'),
                status=discord.Status.online)
        except Exception as ex:
            log.debug('event-bot presence: %s', ex)
        if not _stay_on():
            log.info('event-bot voice stay off')
            return
        cid = _resolve_event_voice_channel_id()
        if not cid:
            return
        global _monitor_task
        if _monitor_task is None or _monitor_task.done():
            _monitor_task = client.loop.create_task(
                _monitor_event_voice(client), name='event-voice-monitor')
        ok, msg = await ensure_voice_joined(client, cid)
        if ok:
            log.info('event-bot voice: %s', msg)
        else:
            log.warning('event-bot voice: %s', msg)

    return client


async def _monitor_event_voice(client: discord.Client) -> None:
    """Держим войсе-сессию: reconnect только если реально отвалились."""
    await client.wait_until_ready()
    await asyncio.sleep(8)
    backoff_until = 0.0
    while not client.is_closed() and not _stop_runner:
        await asyncio.sleep(30)
        if not client.is_ready() or not _stay_on():
            continue
        if time.time() < backoff_until:
            continue
        cid = _resolve_event_voice_channel_id()
        if not cid:
            continue
        vc = None
        for v in list(client.voice_clients or []):
            if v.is_connected():
                vc = v
                break
        if vc and getattr(vc.channel, 'id', None) == cid:
            continue
        ok, msg = await ensure_voice_joined(client, cid)
        if ok:
            backoff_until = 0.0
            log.info('event-bot monitor: %s', msg)
        else:
            backoff_until = time.time() + 45
            log.debug('event-bot monitor: %s', msg)


async def start_event_bot() -> Optional[discord.Client]:
    """Старт event-бота, если EVENT_BOT_TOKEN задан. Иначе None."""
    global _event_client, _stop_runner
    token = event_bot_token()
    if not token:
        log.info('EVENT_BOT_TOKEN пуст — event-бот не запускается')
        return None
    if _event_client is not None and not _event_client.is_closed():
        return _event_client
    _stop_runner = False
    load_event_voice_cfg()  # прогреть stay/channel
    _event_client = build_event_client()

    async def _runner():
        global _event_client
        delay = 5
        while not _stop_runner:
            client = _event_client
            if client is None or client.is_closed():
                client = build_event_client()
                _event_client = client
            try:
                log.info('event-bot connecting…')
                await client.start(token)
                # start() вернулся — сессия закрыта. Не долбим close() ещё раз.
                if _stop_runner:
                    break
                log.warning('event-bot session ended — retry in %ss', delay)
            except discord.LoginFailure:
                log.error('EVENT_BOT_TOKEN неверный — event-бот остановлен')
                break
            except Exception as ex:
                log.warning('event-bot error: %s — retry in %ss', ex, delay)
            await asyncio.sleep(delay)
            delay = min(60, delay * 2)
            if not _stop_runner:
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
    }
