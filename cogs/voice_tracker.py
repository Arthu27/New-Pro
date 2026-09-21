"""
Отслеживание голосовых каналов
Статистика времени в голосовых каналах — database (SQLite)
Отслеживает ВСЕ каналы на ВСЕХ серверах
"""

import discord
from discord.ext import commands, tasks
import time
from datetime import date, datetime

from logger import get_logger
from db import GuildData

log = get_logger("voice_tracker")

import json
import os


# ═════════════════════ единый доступ к голосовой статистике ═════════════════
# Данные живут в SQLite — GuildData("voice_stats") {uid: {name, avatar,
# total_seconds, daily{YYYY-MM-DD: sec}}}. Легаси-файлы data/voice_stats_*.json
# мёртвы с миграции на SQLite; при первом чтении они переносятся в базу
# (_migrate_legacy_json) и переименовываются в *.json.legacy.

def fmt_duration(seconds):
    # Секунды -> короткая русская строка: '2 д 3 ч', '3 ч 5 мин',
    # '5 мин 12 сек', '12 сек' (0 -> '0 мин').
    try:
        secs = max(0, int(seconds or 0))
    except (TypeError, ValueError):
        secs = 0
    if secs == 0:
        return '0 мин'
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return f'{d} д {h} ч'
    if h:
        return f'{h} ч {m} мин'
    if m:
        return f'{m} мин {s} сек' if s else f'{m} мин'
    return f'{s} сек'


def _voice_db():
    return GuildData('voice_stats')


_migrated_guilds = set()


def _migrate_legacy_json(guild_id):
    # Одноразовый перенос data/voice_stats_GID.json -> SQLite (за процесс).
    # Если база по серверу уже непустая -- файл просто архивируется (.legacy).
    gid = int(guild_id)
    if gid in _migrated_guilds:
        return
    _migrated_guilds.add(gid)
    path = os.path.join('data', f'voice_stats_{gid}.json')
    if not os.path.exists(path):
        return
    try:
        if _voice_db().count(gid):
            os.replace(path, path + '.legacy')
            log.info('voice_stats: legacy JSON %s заархивирован (база уже непустая)', path)
            return
        try:
            with open(path, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
        except Exception:
            # битый JSON — архивируем с дороги и живём дальше на пустой базе
            try:
                os.replace(path, path + '.legacy')
            except OSError as _ex:
                log.debug('voice_stats: не удалось заархивировать %s: %s', path, _ex)
            log.warning('voice_stats: битый legacy JSON %s заархивирован', path)
            return
        users = data.get('users', data) if isinstance(data, dict) else {}
        today = str(date.today())
        moved = 0
        for uid, entry in users.items():
            if isinstance(entry, dict):
                secs = entry.get('total_seconds', entry.get('seconds', 0))
                if not secs:
                    try:
                        secs = float(entry.get('minutes', 0) or 0) * 60
                    except (TypeError, ValueError):
                        secs = 0
                daily = entry.get('daily', {}) if isinstance(entry.get('daily'), dict) else {}
                rec = {
                    'name': entry.get('name', uid),
                    'avatar': entry.get('avatar', ''),
                    'total_seconds': int(secs or 0),
                    'daily': daily,
                }
            else:
                try:
                    secs = int(entry or 0)
                except (TypeError, ValueError):
                    secs = 0
                rec = {'name': str(uid), 'avatar': '', 'total_seconds': secs,
                       'daily': {today: secs} if secs else {}}
            _voice_db().set(gid, str(uid), rec)
            moved += 1
        os.replace(path, path + '.legacy')
        log.info('voice_stats: мигрировано %s записей из %s в SQLite', moved, path)
    except Exception as _ex:
        log.warning('voice_stats: миграция %s не удалась: %s', path, _ex)


def voice_all(guild_id):
    # Все записи голосовой статистики сервера: {uid: {...}} (с автомиграцией).
    _migrate_legacy_json(guild_id)
    try:
        data = _voice_db().get_all(int(guild_id)) or {}
    except Exception as _ex:
        log.debug('voice_all(): подавлено: %s', _ex)
        return {}
    return {str(uid): rec for uid, rec in data.items() if isinstance(rec, dict)}


def voice_seconds(guild_id, user_id):
    # Суммарные секунды пользователя в голосовых каналах сервера.
    rec = voice_all(guild_id).get(str(user_id))
    if not rec:
        return 0
    try:
        return max(0, int(rec.get('total_seconds', 0) or 0))
    except (TypeError, ValueError):
        return 0


def voice_today_seconds(guild_id, user_id=None):
    # Секунды за сегодня: одного пользователя или сумма по серверу.
    today = str(date.today())
    if user_id is not None:
        rec = voice_all(guild_id).get(str(user_id)) or {}
        try:
            return max(0, int((rec.get('daily') or {}).get(today, 0) or 0))
        except (TypeError, ValueError):
            return 0
    total = 0
    for rec in voice_all(guild_id).values():
        try:
            total += max(0, int((rec.get('daily') or {}).get(today, 0) or 0))
        except (TypeError, ValueError) as _ex:
            log.debug('voice_today_seconds(): подавлено: %s', _ex)
    return total


def voice_today_users(guild_id):
    # Сколько разных людей сегодня побывали в голосовых каналах.
    today = str(date.today())
    n = 0
    for rec in voice_all(guild_id).values():
        try:
            if int((rec.get('daily') or {}).get(today, 0) or 0) > 0:
                n += 1
        except (TypeError, ValueError) as _ex:
            log.debug('voice_today_users(): подавлено: %s', _ex)
    return n


def voice_leaderboard(guild_id, limit=20):
    # Топ по суммарному времени: [{'user_id','name','avatar','seconds','daily'}].
    rows = []
    for uid, rec in voice_all(guild_id).items():
        try:
            secs = max(0, int(rec.get('total_seconds', 0) or 0))
        except (TypeError, ValueError):
            secs = 0
        if secs <= 0:
            continue
        rows.append({
            'user_id': uid,
            'name': rec.get('name') or uid,
            'avatar': rec.get('avatar') or '',
            'seconds': secs,
            'daily': rec.get('daily') or {},
        })
    rows.sort(key=lambda r: r['seconds'], reverse=True)
    return rows[:limit] if limit else rows


def voice_view(guild_id):
    # Легаси-совместимый вид {'users': {uid: {...}}} для старых читателей.
    # Дублирует поля seconds/minutes, чтобы код, написанный под старый JSON,
    # продолжал работать без правок полей.
    users = {}
    for uid, rec in voice_all(guild_id).items():
        try:
            secs = max(0, int(rec.get('total_seconds', 0) or 0))
        except (TypeError, ValueError):
            secs = 0
        users[uid] = {
            'name': rec.get('name') or uid,
            'avatar': rec.get('avatar') or '',
            'total_seconds': secs,
            'seconds': secs,
            'minutes': secs // 60,
            'daily': rec.get('daily') or {},
        }
    return {'users': users}


class VoiceTracker(commands.Cog):
    """Отслеживание времени в голосовых каналах"""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData("voice_stats")
        # {guild_id: {user_id: join_timestamp}}
        self.sessions: dict = {}
        # Буфер записей: НЕ пишем SQLite на каждый leave — иначе
        # on_voice_state_update блокирует event loop и /modpanel
        # получает «не ответило вовремя». Сливаем пачкой раз в N сек.
        # ключ (gid, uid) -> rec dict
        self._pending: dict = {}
        self._flush_voice_stats.start()

    def cog_unload(self):
        try:
            self._flush_voice_stats.cancel()
        except Exception:
            pass
        try:
            self._flush_sync()
        except Exception:
            pass

    # ── Запись статистики ────────────────────────────────────────────────

    def _record(self, guild_id: int, member: discord.Member, elapsed: int):
        """Накопить время в буфере (без SQLite на горячем пути)."""
        if elapsed <= 0:
            return
        uid = str(member.id)
        key = (guild_id, uid)
        data = self._pending.get(key)
        if data is None:
            # Читаем кэш/БД один раз при первом касании буфера
            data = self.db.get(guild_id, uid, {
                'name': member.display_name,
                'avatar': str(member.display_avatar.url),
                'total_seconds': 0,
                'daily': {}
            }) or {
                'name': member.display_name,
                'avatar': str(member.display_avatar.url),
                'total_seconds': 0,
                'daily': {}
            }
        data['total_seconds'] = int(data.get('total_seconds', 0) or 0) + elapsed
        data['name'] = member.display_name
        try:
            data['avatar'] = str(member.display_avatar.url)
        except Exception:
            pass
        today = str(date.today())
        daily = data.get('daily') or {}
        daily[today] = int(daily.get(today, 0) or 0) + elapsed
        if len(daily) > 30:
            for old_day in sorted(daily.keys())[:-30]:
                del daily[old_day]
        data['daily'] = daily
        self._pending[key] = data

    def _flush_sync(self):
        """Слить буфер в SQLite (вызывать из to_thread / unload)."""
        if not self._pending:
            return
        batch = self._pending
        self._pending = {}
        for (gid, uid), data in batch.items():
            try:
                self.db.set(gid, uid, data)
            except Exception as ex:
                log.debug('voice_stats flush %s/%s: %s', gid, uid, ex)

    @tasks.loop(seconds=10.0)
    async def _flush_voice_stats(self):
        if not self._pending:
            return
        import asyncio
        try:
            await asyncio.to_thread(self._flush_sync)
        except Exception as ex:
            log.debug('voice_stats flush loop: %s', ex)

    @_flush_voice_stats.before_loop
    async def _flush_voice_stats_wait(self):
        await self.bot.wait_until_ready()

    # ── События ──────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self):
        """При запуске бота — зафиксировать всех в голосовых каналах"""
        now = time.time()
        for guild in self.bot.guilds:
            gid = guild.id
            if gid not in self.sessions:
                self.sessions[gid] = {}
            for channel in guild.voice_channels:
                for member in channel.members:
                    if not member.bot:
                        uid = str(member.id)
                        if uid not in self.sessions[gid]:
                            self.sessions[gid][uid] = now

        log.info(f"Голосовой трекер запущен — отслеживаются все каналы на {len(self.bot.guilds)} серверах")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Отслеживание всех изменений голосового состояния"""
        if member.bot:
            return

        gid = member.guild.id
        uid = str(member.id)

        # Подключился к каналу
        if before.channel is None and after.channel is not None:
            if gid not in self.sessions:
                self.sessions[gid] = {}
            self.sessions[gid][uid] = time.time()

        # Отключился от канала
        elif before.channel is not None and after.channel is None:
            join_time = self.sessions.get(gid, {}).pop(uid, None)
            if join_time is None:
                return
            elapsed = int(time.time() - join_time)
            self._record(gid, member, elapsed)

        # Перешёл между каналами
        elif before.channel is not None and after.channel is not None and before.channel != after.channel:
            join_time = self.sessions.get(gid, {}).pop(uid, None)
            if join_time:
                elapsed = int(time.time() - join_time)
                self._record(gid, member, elapsed)
            if gid not in self.sessions:
                self.sessions[gid] = {}
            self.sessions[gid][uid] = time.time()

async def setup(bot):
    await bot.add_cog(VoiceTracker(bot))
    log.info("VoiceTracker загружен — все каналы отслеживаются")
