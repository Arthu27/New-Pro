# -*- coding: utf-8 -*-
"""Отдельный Event-бот: сидит в голосовом канале 24/7 (как основной).

Токен: EVENT_BOT_TOKEN в .env (НЕ коммитить) — правится из панели
«Совместные боты». Канал/stay: config/event_voice_stay.json.

Если кикнули/отвалился — сразу заходит обратно (voice_state_update +
монитор каждые 10с), по тому же принципу, что voice-stay у основного бота.

Запуск: start.bat → main.py (второй клиент).
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
                '(start.bat → main.py). Если кикнули — заходит снова. '
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
    _stay_enabled = bool(payload['stay_enabled'])
    if _voice_channel_id:
        os.environ['EVENT_VOICE_CHANNEL_ID'] = str(_voice_channel_id)
    os.environ['EVENT_VOICE_STAY_ENABLED'] = '1' if _stay_enabled else '0'
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
    """Подключить event-бота к войсу (с замком). Кикнули — зови снова."""
    global _joining, _suppress_rejoin_until
    client = client or _event_client
    if client is None or client.is_closed():
        return False, 'Event-бот офлайн — запусти через start.bat'
    try:
        if not client.is_ready():
            return False, 'Event-бот ещё не ready'
    except Exception:
        return False, 'Event-бот не ready'
    if not _stay_on():
        return False, 'Voice stay выключен в настройках совместных ботов'
    cid = int(channel_id or _resolve_event_voice_channel_id() or 0)
    if not cid:
        return False, 'Не задан голосовой канал event-бота'
    async with _lock():
        # уже в цели — не трогаем (нет disconnect → нет ложного leave)
        try:
            for v in list(client.voice_clients or []):
                if (v.is_connected()
                        and getattr(getattr(v, 'channel', None), 'id', None) == cid):
                    return True, f'Уже в <#{cid}>'
        except Exception:
            pass
        _joining = True
        # suppress только пока сами коннектимся (свой disconnect/move)
        _suppress_rejoin_until = time.time() + 3.0
        try:
            channel = client.get_channel(cid)
            if channel is None:
                try:
                    channel = await client.fetch_channel(cid)
                except Exception as ex:
                    return False, f'Канал не найден: {ex}'
            if not isinstance(channel, discord.VoiceChannel):
                return False, 'ID не голосовой канал'
            # убрать мёртвые voice clients
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
                # как мод-бот: self_deaf=False, без play; reconnect=True
                await asyncio.wait_for(
                    channel.connect(self_deaf=False, reconnect=True),
                    timeout=45.0)
                log.info('event-bot joined voice %s', cid)
                return True, f'Зашёл в <#{cid}>'
            except asyncio.TimeoutError:
                return False, 'Таймаут connect 45с'
            except Exception as ex:
                # Already connected / race
                msg = str(ex).lower()
                if 'already' in msg and 'connected' in msg:
                    return True, f'Уже подключён (<#{cid}>)'
                return False, f'Не удалось зайти: {ex}'
        finally:
            _joining = False
            # сразу после connect разрешаем реагировать на кик
            _suppress_rejoin_until = time.time() + 0.8


def _schedule_rejoin(client: discord.Client, reason: str = '') -> None:
    """Мгновенный возврат в войс после кика/обрыва (не ждём монитора)."""
    global _rejoin_task
    if not _stay_on() or client.is_closed():
        return
    if _joining:
        return

    async def _go():
        # Быстрый первый заход + retries (кик не должен оставлять бота снаружи)
        delays = (0.4, 1.0, 2.0, 3.5, 6.0, 10.0)
        for i, delay in enumerate(delays):
            await asyncio.sleep(delay)
            if client.is_closed() or not _stay_on():
                return
            if _joining:
                continue
            cid = _resolve_event_voice_channel_id()
            for v in list(client.voice_clients or []):
                try:
                    if (v.is_connected()
                            and getattr(v.channel, 'id', None) == cid):
                        log.info('event-bot rejoin skip — already in %s', cid)
                        return
                except Exception:
                    pass
            ok, msg = await ensure_voice_joined(client)
            if ok:
                log.info('event-bot rejoin (%s try=%s): %s',
                         reason or 'auto', i + 1, msg)
                return
            log.warning('event-bot rejoin fail (%s try=%s): %s',
                        reason or 'auto', i + 1, msg)

    if _rejoin_task is not None and not _rejoin_task.done():
        return
    try:
        _rejoin_task = client.loop.create_task(_go(), name='event-voice-rejoin')
    except Exception as ex:
        log.debug('schedule rejoin: %s', ex)


def build_event_client() -> discord.Client:
    """Лёгкий клиент: intents guilds + voice states (для кика/возврата)."""
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
            _schedule_rejoin(client, 'on_ready-fail')

    @client.event
    async def on_resumed():
        log.info('event-bot resumed — проверяю войс')
        _schedule_rejoin(client, 'resume')

    @client.event
    async def on_voice_state_update(member, before, after):
        # Нас кикнули / вытащили из канала → сразу обратно
        me = client.user
        if me is None or member is None:
            return
        if int(getattr(member, 'id', 0) or 0) != int(me.id):
            return
        if not _stay_on():
            return
        # Только пока сами в connect/move — иначе любой кик сразу возвращает
        if _joining:
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
            _schedule_rejoin(client, 'kicked-or-moved')

    @client.event
    async def on_disconnect():
        # Gateway drop — после resume монитор/rejoin поднимут войс
        log.warning('event-bot gateway disconnect')

    return client


async def _monitor_event_voice(client: discord.Client) -> None:
    """Каждые 5с проверяем и заходим обратно (плотнее мод-бота)."""
    await client.wait_until_ready()
    await asyncio.sleep(2)
    backoff_until = 0.0
    while not client.is_closed() and not _stop_runner:
        await asyncio.sleep(5)
        if not client.is_ready() or not _stay_on():
            continue
        if _joining:
            continue
        if time.time() < backoff_until:
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
            backoff_until = 0.0
            log.info('event-bot monitor: %s', msg)
        else:
            backoff_until = time.time() + 12
            log.warning('event-bot monitor: %s', msg)


async def start_event_bot() -> Optional[discord.Client]:
    """Старт event-бота, если EVENT_BOT_TOKEN задан. Иначе None."""
    global _event_client, _stop_runner, _voice_channel_id
    token = event_bot_token()
    if not token:
        log.info('EVENT_BOT_TOKEN пуст — event-бот не запускается')
        return None
    if _event_client is not None and not _event_client.is_closed():
        return _event_client
    _stop_runner = False
    _voice_channel_id = None  # перечитать cfg
    load_event_voice_cfg()
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
