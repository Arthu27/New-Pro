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

    # ── Запись статистики ────────────────────────────────────────────────

    def _record(self, guild_id: int, member: discord.Member, elapsed: int):
        """Записать время в базу"""
        if elapsed <= 0:
            return

        uid = str(member.id)
        data = self.db.get(guild_id, uid, {
            'name': member.display_name,
            'avatar': str(member.display_avatar.url),
            'total_seconds': 0,
            'daily': {}
        })

        data['total_seconds'] = data.get('total_seconds', 0) + elapsed
        data['name'] = member.display_name
        data['avatar'] = str(member.display_avatar.url)

        # Ежедневная статистика
        today = str(date.today())
        daily = data.get('daily', {})
        daily[today] = daily.get(today, 0) + elapsed
        # Храним только последние 30 дней
        if len(daily) > 30:
            sorted_days = sorted(daily.keys())
            for old_day in sorted_days[:-30]:
                del daily[old_day]
        data['daily'] = daily

        self.db.set(guild_id, uid, data)

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

    # ── Команды ──────────────────────────────────────────────────────────

    @commands.command(name='voicetime', aliases=['vtime', 'голос'])
    async def voicetime(self, ctx, member: discord.Member = None):
        """Сколько времени ты (или участник) провёл в голосовых каналах"""
        from cogs.embed_utils import aether_embed, fmt_duration, plural
        member = member or ctx.author
        data = self.db.get(ctx.guild.id, str(member.id))

        if not data or data.get('total_seconds', 0) == 0:
            embed = aether_embed(
                'voice', f'Голосовая статистика — {member.display_name}',
                'Пока тишина: этот человек ещё не был в голосовых каналах.',
                guild=ctx.guild, footer_extra='Голосовой трекер',
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await ctx.send(embed=embed)
            return

        total = int(data.get('total_seconds', 0))
        today = str(date.today())
        daily = data.get('daily', {}) or {}
        today_sec = int(daily.get(today, 0) or 0)
        week_sec = 0
        from datetime import timedelta
        for i in range(7):
            day = str(date.today() - timedelta(days=i))
            week_sec += int(daily.get(day, 0) or 0)

        embed = aether_embed(
            'voice', f'Голосовая статистика — {member.display_name}',
            f'## {fmt_duration(total)}',
            fields=[
                ('Сегодня', fmt_duration(today_sec), True),
                ('За неделю', fmt_duration(week_sec), True),
            ],
            guild=ctx.guild, footer_extra='Голосовой трекер',
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name='voiceleaderboard', aliases=['vtop', 'голостоп'])
    async def voice_leaderboard_cmd(self, ctx):
        """Топ-10 по времени в голосовых каналах"""
        from cogs.embed_utils import aether_embed, fmt_duration
        all_data = self.db.get_all(ctx.guild.id)
        sorted_users = sorted(
            [(uid, d) for uid, d in (all_data or {}).items()
             if isinstance(d, dict) and d.get('total_seconds', 0) > 0],
            key=lambda x: x[1].get('total_seconds', 0),
            reverse=True
        )[:10]

        if not sorted_users:
            embed = aether_embed(
                'voice', 'Голосовой рейтинг',
                'Пока данных нет — зайдите в войс, и я начну считать.',
                guild=ctx.guild, footer_extra='Голосовой трекер',
            )
            await ctx.send(embed=embed)
            return

        medals = {1: '🥇', 2: '🥈', 3: '🥉'}
        top_secs = sorted_users[0][1].get('total_seconds', 1) or 1
        today = str(date.today())
        rows = []
        for i, (uid, d) in enumerate(sorted_users, 1):
            total = int(d.get('total_seconds', 0))
            today_sec = int((d.get('daily') or {}).get(today, 0) or 0)
            name = d.get('name', f'ID: {uid}')
            mark = medals.get(i, f'`{i}.`')
            part = f' · сегодня {fmt_duration(today_sec)}' if today_sec else ''
            rows.append(f'{mark} **{name}**\n└ `{fmt_duration(total)}`{part}')

        embed = aether_embed(
            'voice', 'Голосовой рейтинг — Топ 10', '\n'.join(rows),
            guild=ctx.guild, footer_extra='Голосовой трекер',
        )
        await ctx.send(embed=embed)

    @commands.command(name='voiceonline', aliases=['голосонлайн'])
    async def voice_online(self, ctx):
        """Кто сейчас сидит в голосовых каналах"""
        from cogs.embed_utils import aether_embed, plural
        channels = {}
        n_members = 0
        for channel in ctx.guild.voice_channels:
            people = [m for m in channel.members if not m.bot]
            if people:
                channels[channel.name] = people
                n_members += len(people)

        if not channels:
            embed = aether_embed(
                'voice', 'Голосовые каналы',
                'Сейчас в войсах пусто. Заходите — будет весело.',
                guild=ctx.guild, footer_extra='Голосовой трекер',
            )
            await ctx.send(embed=embed)
            return

        fields = []
        for ch_name, members in list(channels.items())[:10]:
            names = ', '.join(f'**{m.display_name}**' for m in members[:10])
            if len(members) > 10:
                names += f' и ещё {len(members) - 10}'
            fields.append((f'🔊 {ch_name}', names, False))
        embed = aether_embed(
            'voice',
            f'В войсах сейчас: {n_members} {plural(n_members, "участник", "участника", "участников")}',
            None, fields=fields, guild=ctx.guild, footer_extra='Голосовой трекер',
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(VoiceTracker(bot))
    log.info("VoiceTracker загружен — все каналы отслеживаются")
