# -*- coding: utf-8 -*-
"""Единый контроллер voice stay 24/7.

- Цели в SQLite (voice_targets): бот знает канал после рестарта.
- on_ready → join всех целей (один раз).
- on_voice_state_update → кик/перенос → rejoin.
- Watchdog каждые ~45с: Discord-truth + is_connected.
- Zombie VC → disconnect(force=True) → connect заново.
- Exponential backoff 5→10→20→40… max 300с; после успеха сброс.
- asyncio.Lock на (bot_id, guild_id) — без гонок.
- Намеренный leave = clear_target → вотчдог не возвращает.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Dict, Optional, Tuple

import discord

from logger import get_logger
from services import voice_targets as VT
from services.voice_stay_health import (
    really_in_channel, force_drop_voice, voice_client_alive,
    needs_soft_reconnect, SOFT_RECONNECT_SEC,
)

log = get_logger('voice_stay')

# Backoff: 5, 10, 20, 40 … max 5 мин
_BACKOFF_START = 5.0
_BACKOFF_MAX = 300.0
_WATCHDOG_SEC = 45.0
# Нет прав / канал удалён — реже долбим
_PERM_RETRY_SEC = 180.0


def _enable_discord_voice_logging() -> None:
    """INFO для discord; DEBUG для voice/gateway при VOICE_DEBUG=1."""
    try:
        logging.getLogger('discord').setLevel(logging.INFO)
        dbg = (os.environ.get('VOICE_DEBUG') or '').strip().lower() in (
            '1', 'true', 'yes', 'on')
        for name in ('discord.voice_state', 'discord.gateway',
                     'discord.voice_client', 'discord.player'):
            logging.getLogger(name).setLevel(
                logging.DEBUG if dbg else logging.INFO)
    except Exception as ex:
        log.debug('voice logging setup: %s', ex)


def load_opus() -> bool:
    try:
        if discord.opus.is_loaded():
            return True
        for name in (
            'libopus.so.0', 'libopus.so', 'opus',
            '/usr/lib/x86_64-linux-gnu/libopus.so.0',
            '/usr/lib/libopus.so.0',
        ):
            try:
                discord.opus.load_opus(name)
                if discord.opus.is_loaded():
                    log.info('opus loaded via %s', name)
                    return True
            except Exception:
                continue
    except Exception as ex:
        log.debug('opus load: %s', ex)
    return False


class VoiceStayController:
    """Один контроллер на процесс бота (main / event)."""

    def __init__(self, client: discord.Client, bot_id: str):
        self.client = client
        self.bot_id = str(bot_id)
        self._locks: Dict[int, asyncio.Lock] = {}
        self._backoff: Dict[int, float] = {}  # guild_id → next delay
        self._next_try: Dict[int, float] = {}  # guild_id → monotonic
        self._joining: Dict[int, bool] = {}
        self._suppress_until: Dict[int, float] = {}
        self._last_join_ts: Dict[int, float] = {}
        self._rejoin_tasks: Dict[int, asyncio.Task] = {}
        self._watchdog_task: Optional[asyncio.Task] = None
        self._ready_once = False
        self._last_silence_ts: Dict[int, float] = {}
        self._perm_fail_until: Dict[int, float] = {}
        _enable_discord_voice_logging()
        load_opus()
        VT.ensure_table()

    # ── targets ─────────────────────────────────────────────────────
    def set_target(self, guild_id: int, channel_id: int) -> None:
        VT.set_target(self.bot_id, int(guild_id), int(channel_id))

    def clear_target(self, guild_id: int) -> None:
        """Намеренный /leave — вотчдог не вернёт."""
        VT.clear_target(self.bot_id, int(guild_id))
        self._backoff.pop(int(guild_id), None)
        self._next_try.pop(int(guild_id), None)

    def target_for(self, guild_id: int) -> Optional[int]:
        return VT.get_target(self.bot_id, int(guild_id))

    def all_targets(self):
        return VT.list_targets(self.bot_id)

    def seed_from_channel_id(self, channel_id: int,
                             guild_id: int | None = None) -> None:
        """Из env/json при старте: узнать guild через get_channel после ready."""
        cid = int(channel_id or 0)
        if not cid:
            return
        if guild_id:
            self.set_target(int(guild_id), cid)
            return
        # guild неизвестен — сохраним с guild=0 как «pending», resolve в on_ready
        VT.set_target(self.bot_id, 0, cid)

    async def _resolve_pending_targets(self) -> None:
        """guild_id=0 → резолвим канал (cache → fetch) и переписываем запись."""
        pending = [c for g, c in self.all_targets() if g == 0]
        if not pending or self.client is None:
            return
        for cid in pending:
            ch = self.client.get_channel(cid)
            if ch is None:
                try:
                    ch = await self.client.fetch_channel(cid)
                except Exception as ex:
                    log.warning(
                        '[%s] pending channel %s ещё не доступен: %s',
                        self.bot_id, cid, ex)
                    continue
            gid = getattr(getattr(ch, 'guild', None), 'id', None)
            if not gid:
                continue
            VT.clear_target(self.bot_id, 0)
            self.set_target(int(gid), int(cid))
            log.info('voice_targets resolved pending channel %s → guild %s',
                     cid, gid)

    def _lock(self, guild_id: int) -> asyncio.Lock:
        gid = int(guild_id)
        if gid not in self._locks:
            self._locks[gid] = asyncio.Lock()
        return self._locks[gid]

    def _backoff_delay(self, guild_id: int) -> float:
        return float(self._backoff.get(int(guild_id), _BACKOFF_START))

    def _bump_backoff(self, guild_id: int) -> float:
        gid = int(guild_id)
        cur = self._backoff.get(gid, _BACKOFF_START)
        nxt = min(_BACKOFF_MAX, max(_BACKOFF_START, cur * 2))
        self._backoff[gid] = nxt
        self._next_try[gid] = time.monotonic() + cur
        return cur

    def _reset_backoff(self, guild_id: int) -> None:
        gid = int(guild_id)
        self._backoff.pop(gid, None)
        self._next_try.pop(gid, None)
        self._perm_fail_until.pop(gid, None)

    # ── connect ─────────────────────────────────────────────────────
    async def ensure_joined(self, guild_id: int | None = None,
                            channel_id: int | None = None,
                            *, force: bool = False,
                            reason: str = '') -> Tuple[bool, str]:
        """Подключить бота к целевому каналу гильдии."""
        client = self.client
        if client is None or client.is_closed():
            return False, 'бот офлайн'
        try:
            if not client.is_ready():
                return False, 'бот ещё не ready'
        except Exception:
            return False, 'бот не ready'

        cid = int(channel_id or 0)
        gid = int(guild_id or 0)
        if not cid and gid:
            cid = int(self.target_for(gid) or 0)
        if not cid:
            # единственная цель
            targets = self.all_targets()
            if len(targets) == 1:
                gid, cid = targets[0]
            elif not targets:
                return False, 'нет цели в voice_targets'
            else:
                return False, 'укажите guild_id/channel_id'

        if not gid:
            ch0 = client.get_channel(cid)
            gid = int(getattr(getattr(ch0, 'guild', None), 'id', 0) or 0)

        # намеренный leave?
        stored = self.target_for(gid) if gid else None
        if gid and stored is None and not channel_id:
            # нет записи — не возвращаемся
            return False, 'нет цели (intentional leave?)'
        if gid and cid and stored != cid:
            # обновить цель
            self.set_target(gid, cid)

        now_m = time.monotonic()
        if not force and now_m < self._perm_fail_until.get(gid, 0):
            return False, 'нет прав/канал — ждём retry'
        if not force and now_m < self._next_try.get(gid, 0):
            return False, 'backoff'

        if not force:
            ok, _vc, why = really_in_channel(client, cid)
            if ok:
                self._reset_backoff(gid)
                return True, f'уже в <#{cid}>'
            if why.startswith('zombie'):
                force = True
                log.warning('[%s] zombie (%s) — force reconnect',
                            self.bot_id, why)

        lock = self._lock(gid or cid)
        try:
            await asyncio.wait_for(lock.acquire(), timeout=10.0)
        except asyncio.TimeoutError:
            return False, 'ensure занят — retry'

        self._joining[gid] = True
        self._suppress_until[gid] = time.time() + 5.0
        try:
            channel = client.get_channel(cid)
            if channel is None:
                try:
                    channel = await client.fetch_channel(cid)
                except discord.NotFound:
                    log.error('[%s] канал %s удалён', self.bot_id, cid)
                    self._perm_fail_until[gid] = now_m + _PERM_RETRY_SEC
                    return False, f'канал {cid} не найден (удалён?)'
                except discord.Forbidden:
                    log.error('[%s] нет доступа к каналу %s', self.bot_id, cid)
                    self._perm_fail_until[gid] = now_m + _PERM_RETRY_SEC
                    return False, f'нет прав на канал {cid}'
                except Exception as ex:
                    return False, f'канал не найден: {ex}'
            if not isinstance(channel, discord.VoiceChannel):
                return False, 'ID не голосовой канал'
            gid = int(channel.guild.id)
            # снять pending guild=0, если заходили по channel_id из seed
            if VT.get_target(self.bot_id, 0) == cid:
                VT.clear_target(self.bot_id, 0)
            self.set_target(gid, cid)

            me = channel.guild.me
            if me is not None:
                perms = channel.permissions_for(me)
                if not (perms.connect and perms.view_channel):
                    log.error(
                        '[%s] нет Connect/View Channel в %s (guild=%s)',
                        self.bot_id, cid, gid)
                    self._perm_fail_until[gid] = time.monotonic() + _PERM_RETRY_SEC
                    await self._alert_log_channel(
                        channel.guild,
                        f'Нет прав Connect/View в <#{cid}> — stay остановлен '
                        f'на {_PERM_RETRY_SEC:.0f}с')
                    return False, 'нет прав Connect/View Channel'

            if force:
                await force_drop_voice(client, channel.guild)
            else:
                for stale in list(client.voice_clients or []):
                    try:
                        if getattr(stale, 'guild', None) is channel.guild \
                                and not voice_client_alive(stale):
                            await stale.disconnect(force=True)
                    except Exception:
                        pass

            vc = discord.utils.get(client.voice_clients, guild=channel.guild)
            if vc is not None:
                try:
                    connected = bool(vc.is_connected())
                except Exception:
                    connected = False
                if not connected:
                    # зависший VC
                    log.warning('[%s] stale VC is_connected=False — force drop',
                                self.bot_id)
                    try:
                        await vc.disconnect(force=True)
                    except Exception as ex:
                        log.debug('stale disconnect: %s', ex)
                    try:
                        cleanup = getattr(vc, 'cleanup', None)
                        if callable(cleanup):
                            cleanup()
                    except Exception:
                        pass
                    vc = None

            if vc and voice_client_alive(vc):
                if getattr(vc.channel, 'id', None) == cid:
                    ok2, _, _ = really_in_channel(client, cid)
                    if ok2:
                        self._reset_backoff(gid)
                        return True, f'уже в <#{cid}>'
                    try:
                        await vc.disconnect(force=True)
                    except Exception:
                        pass
                else:
                    try:
                        await asyncio.wait_for(vc.move_to(channel), timeout=20.0)
                        self._last_join_ts[gid] = time.time()
                        self._reset_backoff(gid)
                        log.info('[%s] moved → %s (reason=%s)',
                                 self.bot_id, cid, reason or '—')
                        return True, f'переехал в <#{cid}>'
                    except Exception:
                        try:
                            await vc.disconnect(force=True)
                        except Exception:
                            pass

            try:
                await asyncio.wait_for(
                    channel.connect(
                        timeout=30.0, reconnect=True,
                        self_deaf=True, self_mute=True),
                    timeout=35.0)
                self._last_join_ts[gid] = time.time()
                self._reset_backoff(gid)
                log.info('[%s] joined %s guild=%s reason=%s',
                         self.bot_id, cid, gid, reason or '—')
                return True, f'зашёл в <#{cid}>'
            except asyncio.TimeoutError:
                delay = self._bump_backoff(gid)
                log.warning('[%s] connect timeout %s — backoff %.0fs',
                            self.bot_id, cid, delay)
                return False, 'timeout connect'
            except discord.ClientException as ex:
                msg = str(ex).lower()
                if 'already' in msg and 'connected' in msg:
                    await force_drop_voice(client, channel.guild)
                    try:
                        await asyncio.wait_for(
                            channel.connect(
                                timeout=30.0, reconnect=True,
                                self_deaf=True, self_mute=True),
                            timeout=35.0)
                        self._last_join_ts[gid] = time.time()
                        self._reset_backoff(gid)
                        return True, f'перезашёл в <#{cid}>'
                    except Exception as ex2:
                        delay = self._bump_backoff(gid)
                        return False, f'reconnect fail: {ex2}'
                delay = self._bump_backoff(gid)
                log.warning('[%s] ClientException: %s — backoff %.0fs',
                            self.bot_id, ex, delay)
                return False, str(ex)
            except discord.ConnectionClosed as ex:
                code = getattr(ex, 'code', None)
                delay = self._bump_backoff(gid)
                log.warning(
                    '[%s] ConnectionClosed code=%s %s — backoff %.0fs',
                    self.bot_id, code, ex, delay)
                return False, f'closed:{code}'
            except discord.Forbidden:
                self._perm_fail_until[gid] = time.monotonic() + _PERM_RETRY_SEC
                log.error('[%s] Forbidden connect %s', self.bot_id, cid)
                return False, 'Forbidden'
            except discord.NotFound:
                self._perm_fail_until[gid] = time.monotonic() + _PERM_RETRY_SEC
                log.error('[%s] NotFound channel %s', self.bot_id, cid)
                return False, 'NotFound'
            except Exception as ex:
                delay = self._bump_backoff(gid)
                log.warning('[%s] connect fail: %s — backoff %.0fs',
                            self.bot_id, ex, delay)
                return False, str(ex) or type(ex).__name__
        finally:
            self._joining[gid] = False
            self._suppress_until[gid] = time.time() + 8.0
            try:
                lock.release()
            except Exception:
                pass

    # ── schedule rejoin with backoff ────────────────────────────────
    def schedule_rejoin(self, guild_id: int | None = None, *,
                        reason: str = '', force: bool = False) -> None:
        client = self.client
        if client is None or client.is_closed():
            return
        targets = []
        if guild_id:
            cid = self.target_for(int(guild_id))
            if cid:
                targets = [(int(guild_id), int(cid))]
        else:
            # включая pending guild=0 — join по channel_id
            targets = [(g, c) for g, c in self.all_targets() if c]
        for gid, cid in targets:
            if self._joining.get(gid) and not force:
                continue
            if (not force) and time.time() < self._suppress_until.get(gid, 0):
                continue
            existing = self._rejoin_tasks.get(gid)
            if existing is not None and not existing.done():
                if force:
                    try:
                        existing.cancel()
                    except Exception:
                        pass
                else:
                    continue
            try:
                self._rejoin_tasks[gid] = client.loop.create_task(
                    self._rejoin_loop(gid, cid, reason=reason, force=force),
                    name=f'voice-rejoin-{self.bot_id}-{gid}')
            except Exception as ex:
                log.debug('schedule_rejoin: %s', ex)

    async def _rejoin_loop(self, guild_id: int, channel_id: int, *,
                           reason: str, force: bool) -> None:
        attempt = 0
        while not self.client.is_closed():
            # цель снята (intentional leave)?
            if self.target_for(guild_id) is None:
                log.info('[%s] rejoin abort — target cleared guild=%s',
                         self.bot_id, guild_id)
                return
            attempt += 1
            if attempt == 1:
                delay = 0.5 if force else self._backoff_delay(guild_id)
            else:
                delay = self._backoff_delay(guild_id)
            await asyncio.sleep(delay)
            if self.client.is_closed():
                return
            if self._joining.get(guild_id):
                continue
            try:
                if not self.client.is_ready():
                    continue
            except Exception:
                continue
            use_force = force or attempt > 1 or reason in (
                'kicked-or-moved', 'soft-reconnect', 'zombie',
                'watchdog', 'stale-vc')
            if not use_force:
                ok, _, why = really_in_channel(self.client, channel_id)
                if ok:
                    self._reset_backoff(guild_id)
                    return
                if why.startswith('zombie'):
                    use_force = True
            ok, msg = await self.ensure_joined(
                guild_id, channel_id, force=use_force, reason=reason)
            if ok:
                log.info('[%s] rejoin OK (%s try=%s): %s',
                         self.bot_id, reason or 'auto', attempt, msg)
                return
            log.warning('[%s] rejoin fail (%s try=%s): %s — next backoff',
                        self.bot_id, reason or 'auto', attempt, msg)
            # bump already done in ensure on fail; loop sleeps backoff

    # ── lifecycle ───────────────────────────────────────────────────
    async def on_ready_once(self) -> None:
        if self._ready_once:
            return
        self._ready_once = True
        await self._resolve_pending_targets()
        targets = list(self.all_targets())
        log.info('[%s] voice stay on_ready — targets=%s',
                 self.bot_id, targets)
        for gid, cid in targets:
            if not cid:
                continue
            # guild=0 (pending): всё равно join по channel_id —
            # ensure_joined сам fetch'ит канал и пишет реальный guild.
            ok, msg = await self.ensure_joined(
                gid if gid else None, cid, force=True, reason='on_ready')
            log.info('[%s] on_ready join guild=%s ch=%s → %s %s',
                     self.bot_id, gid, cid, ok, msg)
        # если после join остался pending — повторим resolve
        await self._resolve_pending_targets()
        self.start_watchdog()

    async def handle_voice_state(self, member, before, after) -> None:
        me = getattr(self.client, 'user', None)
        if me is None or member is None:
            return
        if int(getattr(member, 'id', 0) or 0) != int(me.id):
            return
        guild = getattr(member, 'guild', None)
        gid = int(getattr(guild, 'id', 0) or 0)
        target = self.target_for(gid) if gid else None
        if not target:
            return
        if self._joining.get(gid) or time.time() < self._suppress_until.get(gid, 0):
            return
        before_id = getattr(getattr(before, 'channel', None), 'id', None)
        after_id = getattr(getattr(after, 'channel', None), 'id', None)
        if after_id == target:
            return
        if before_id == target or after_id is None or after_id != target:
            log.warning(
                '[%s] left voice guild=%s before=%s after=%s — FORCE return → %s',
                self.bot_id, gid, before_id, after_id, target)
            self._suppress_until[gid] = 0.0
            self.schedule_rejoin(gid, reason='kicked-or-moved', force=True)

    def start_watchdog(self) -> None:
        if self._watchdog_task is not None and not self._watchdog_task.done():
            return
        try:
            self._watchdog_task = self.client.loop.create_task(
                self._watchdog(), name=f'voice-watchdog-{self.bot_id}')
        except Exception as ex:
            log.debug('start_watchdog: %s', ex)

    async def _watchdog(self) -> None:
        await self.client.wait_until_ready()
        await asyncio.sleep(2)
        silence_env = (os.environ.get('VOICE_SILENCE_PING') or '0').strip().lower()
        silence = silence_env in ('1', 'true', 'yes', 'on')
        if silence and not discord.opus.is_loaded():
            log.warning('[%s] VOICE_SILENCE_PING=1, но libopus нет — silence OFF',
                        self.bot_id)
            silence = False
        log.info('[%s] watchdog every %.0fs silence=%s',
                 self.bot_id, _WATCHDOG_SEC, silence)
        while not self.client.is_closed():
            await asyncio.sleep(_WATCHDOG_SEC)
            if not self.client.is_ready():
                continue
            # pending guild=0 — попробовать resolve + join по channel_id
            pending = [c for g, c in self.all_targets() if g == 0 and c]
            if pending:
                await self._resolve_pending_targets()
                for pcid in pending:
                    if VT.get_target(self.bot_id, 0) == pcid:
                        await self.ensure_joined(
                            None, pcid, force=True, reason='watchdog-pending')
            for gid, cid in list(self.all_targets()):
                if not gid or not cid:
                    continue
                if self._joining.get(gid):
                    continue
                if time.time() < self._suppress_until.get(gid, 0):
                    continue
                if time.monotonic() < self._perm_fail_until.get(gid, 0):
                    continue
                ok, vc, why = really_in_channel(self.client, cid)
                now = time.time()
                if not ok:
                    force = why.startswith('zombie') or why == 'discord-in-lib-dead'
                    log.warning('[%s] watchdog miss guild=%s (%s) force=%s',
                                self.bot_id, gid, why, force)
                    ok2, msg = await self.ensure_joined(
                        gid, cid, force=force, reason='watchdog')
                    if not ok2:
                        self.schedule_rejoin(
                            gid, reason='watchdog', force=True)
                        if 'Forbidden' in msg or 'не найден' in msg:
                            await self._alert_log_channel(
                                self.client.get_guild(gid),
                                f'Не могу вернуться в <#{cid}>: {msg}')
                    continue
                last = self._last_join_ts.get(gid, 0)
                if why == 'ok-latency-high' and needs_soft_reconnect(
                        last, now, interval=120):
                    log.warning('[%s] latency bad >2min — heal guild=%s',
                                self.bot_id, gid)
                    self.schedule_rejoin(gid, reason='latency-heal', force=True)
                    continue
                if needs_soft_reconnect(last, now, interval=SOFT_RECONNECT_SEC):
                    log.info('[%s] soft-reconnect after %.1fh guild=%s',
                             self.bot_id, (now - last) / 3600.0, gid)
                    self.schedule_rejoin(
                        gid, reason='soft-reconnect', force=True)
                    continue
                if silence and (now - self._last_silence_ts.get(gid, 0)) > 60:
                    try:
                        if vc and not vc.is_playing() and discord.opus.is_loaded():
                            import io
                            silence_buf = io.BytesIO(b'\x00' * 3840)
                            source = discord.PCMAudio(silence_buf)
                            await asyncio.wait_for(
                                asyncio.to_thread(vc.play, source), timeout=10.0)
                        self._last_silence_ts[gid] = now
                    except asyncio.TimeoutError:
                        log.warning('[%s] silence timeout — rejoin', self.bot_id)
                        self.schedule_rejoin(
                            gid, reason='silence-timeout', force=True)
                    except Exception as ex:
                        log.debug('silence: %s', ex)
                        self._last_silence_ts[gid] = now

    async def _alert_log_channel(self, guild, text: str) -> None:
        """Важные сбои stay — в мод-лог, если настроен."""
        if guild is None:
            return
        try:
            from cogs.logs import send_action_log
            await send_action_log(
                guild, 'system', None, None,
                reason=f'[{self.bot_id}] voice stay',
                extra=str(text)[:500])
        except Exception as ex:
            log.debug('alert log: %s', ex)

    def bind_gateway_listeners(self) -> None:
        """Soft rejoin на disconnect/resume."""
        client = self.client

        async def _on_disconnect():
            log.warning('[%s] gateway disconnect — soft rejoin', self.bot_id)
            self.schedule_rejoin(reason='gateway-disconnect', force=False)

        async def _on_resumed():
            log.info('[%s] gateway resume — soft rejoin check', self.bot_id)
            self.schedule_rejoin(reason='resume', force=False)

        try:
            client.add_listener(_on_disconnect, 'on_disconnect')
            client.add_listener(_on_resumed, 'on_resumed')
        except Exception as ex:
            log.debug('bind_gateway: %s', ex)


# Реестр контроллеров (main / event)
_CONTROLLERS: Dict[str, VoiceStayController] = {}


def get_controller(bot_id: str) -> Optional[VoiceStayController]:
    return _CONTROLLERS.get(str(bot_id))


def attach(client: discord.Client, bot_id: str) -> VoiceStayController:
    ctrl = VoiceStayController(client, bot_id)
    _CONTROLLERS[str(bot_id)] = ctrl
    return ctrl
