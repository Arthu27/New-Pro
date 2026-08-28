# -*- coding: utf-8 -*-
"""Достижения (Achievements Cog)
===============================
Игровая витрина активности сервера: пользователи получают ачивки за
сообщения, голосовое время и стаж. Анонсы новых ачивок в канал, профиль
достижений по команде.

- /ачивки [@user]   — карточка достижений
- /ачивлидеры       — топ сервера по очкам достижений

Статистика сообщений собирается слушателем (батч-запись раз в минуту —
БД не дёргается на каждое сообщение). Голосовое время подтягивается из
voice_tracker, если тот загружен. Хранилище — SQLite (GuildData
'achievements'). Метки — aware UTC.
"""
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from db import GuildData
from logger import get_logger
from services import text_format as tf

# Заказ владельца 2026-08-25: достижения «пока что не нужны» — выключены
# целиком (ког не грузится ни в одном профиле: ни BOT_FULL, ни EXTRA_COGS).
# Код и накопленные данные на месте. Вернуть: ACHIEVEMENTS_ENABLED = True.
ACHIEVEMENTS_ENABLED = False

log = get_logger("achievements")

UTC = timezone.utc
COLOR = 0xF1C40F

# ─── каталог достижений ─────────────────────────────────────────────────────
# key: (name, desc, points, check(stats) -> bool)
# stats: {'messages', 'voice_seconds', 'days_member'}
ACHIEVEMENTS = {
    'first_words':   ('Первые слова', 'Написать первое сообщение', 5,
                      lambda s: s['messages'] >= 1),
    'talker_100':    ('Говорун', 'Написать 100 сообщений', 10,
                      lambda s: s['messages'] >= 100),
    'talker_1000':   ('Душа чата', 'Написать 1 000 сообщений', 25,
                      lambda s: s['messages'] >= 1000),
    'talker_10000':  ('Легенда сервера', 'Написать 10 000 сообщений', 100,
                      lambda s: s['messages'] >= 10000),
    'voice_1h':      ('Голосовой дебют', 'Провести 1 час в голосовых', 10,
                      lambda s: s['voice_seconds'] >= 3600),
    'voice_10h':     ('Радиоведущий', 'Провести 10 часов в голосовых', 25,
                      lambda s: s['voice_seconds'] >= 36000),
    'voice_100h':    ('Житель войса', 'Провести 100 часов в голосовых', 75,
                      lambda s: s['voice_seconds'] >= 360000),
    'member_7d':     ('Недельный', 'Неделя на сервере', 5,
                      lambda s: s['days_member'] >= 7),
    'member_30d':    ('Осевший', 'Месяц на сервере', 15,
                      lambda s: s['days_member'] >= 30),
    'member_365d':   ('Старожил', 'Год на сервере', 100,
                      lambda s: s['days_member'] >= 365),
}


# ─── чистые функции (покрыты тестом) ────────────────────────────────────────

def norm_stats(stats):
    """Нормализованные счётчики: недостающие поля -> 0, мусор -> 0."""
    out = {}
    for key in ('messages', 'voice_seconds', 'days_member'):
        try:
            out[key] = max(0, int((stats or {}).get(key, 0) or 0))
        except (TypeError, ValueError):
            out[key] = 0
    return out


def evaluate(stats):
    """Какие ключи ачивок заслужены при таких счётчиках."""
    s = norm_stats(stats)
    earned = set()
    for key, (_name, _desc, _pts, check) in ACHIEVEMENTS.items():
        try:
            if check(s):
                earned.add(key)
        except Exception as _ex:  # защита от битой ачивки в каталоге
            log.error('achievements: проверка %s упала: %s', key, _ex)
    return earned


def new_grants(earned, already):
    """Новые ачивки — те, что заслужены, но ещё не выданы."""
    return sorted(set(earned) - set(already or []))


def total_points(grants):
    return sum(ACHIEVEMENTS[k][2] for k in grants if k in ACHIEVEMENTS)


def progress_rows(stats, grants):
    """Строки карточки: (имя, описание, очки, получена ли)."""
    earned = evaluate(stats)
    have = set(grants or [])
    rows = []
    for key, (name, desc, pts, _c) in ACHIEVEMENTS.items():
        rows.append({'key': key, 'name': name, 'desc': desc,
                     'points': pts, 'done': key in earned and key in have})
    return rows


def user_record():
    return {'messages': 0, 'grants': [], 'granted_at': {}}


# ─── ког ────────────────────────────────────────────────────────────────────

class Achievements(commands.Cog):
    """Ачивки за активность — с анонсами в канал."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('achievements')
        self._pending = {}  # (guild_id, user_id) -> +N сообщений (батч)
        self.flush_loop.start()

    def cog_unload(self):
        self.flush_loop.cancel()

    # ---- хранилище ----
    def _rec(self, guild_id, user_id):
        rec = self.db.get(guild_id, f'user_{user_id}', user_record()) or user_record()
        rec.setdefault('messages', 0)
        rec.setdefault('grants', [])
        rec.setdefault('granted_at', {})
        return rec

    def _save_rec(self, guild_id, user_id, rec):
        self.db.set(guild_id, f'user_{user_id}', rec)

    # ---- внешние счётчики ----
    def _voice_seconds(self, guild_id, user_id):
        """Голосовое время из voice_tracker (если модуль загружен)."""
        try:
            from cogs import voice_tracker as vt
            return int(vt.voice_seconds(guild_id, user_id) or 0)
        except Exception as _ex:
            log.debug('achievements: voice_seconds недоступен: %s', _ex)
            return 0

    def _stats(self, guild, user_id, member=None):
        days = 0
        member = member or (guild.get_member(user_id) if guild else None)
        joined = getattr(member, 'joined_at', None) if member else None
        if joined is not None:
            if joined.tzinfo is None:
                joined = joined.replace(tzinfo=UTC)
            days = max(0, (datetime.now(UTC) - joined).days)
        rec = self._rec(guild.id if guild else 0, user_id)
        return norm_stats({
            'messages': rec['messages'],
            'voice_seconds': self._voice_seconds(guild.id if guild else 0, user_id),
            'days_member': days,
        })

    # ---- слушатель: сообщения в батч ----
    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or getattr(message.author, 'bot', False):
            return
        key = (message.guild.id, message.author.id)
        self._pending[key] = self._pending.get(key, 0) + 1

    @tasks.loop(seconds=60)
    async def flush_loop(self):
        if not self._pending:
            return
        batch, self._pending = self._pending, {}
        for (guild_id, user_id), count in batch.items():
            rec = self._rec(guild_id, user_id)
            rec['messages'] += count
            self._save_rec(guild_id, user_id, rec)
            await self._maybe_announce(guild_id, user_id, rec)

    @flush_loop.before_loop
    async def _wait_ready(self):
        await self.bot.wait_until_ready()

    async def _maybe_announce(self, guild_id, user_id, rec):
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        stats = self._stats(guild, user_id)
        fresh = new_grants(evaluate(stats), rec['grants'])
        if not fresh:
            return
        now = datetime.now(UTC)
        for key in fresh:
            rec['grants'].append(key)
            rec['granted_at'][key] = now.isoformat()
        self._save_rec(guild_id, user_id, rec)

        channel = guild.system_channel
        member = guild.get_member(user_id)
        names = ' и '.join(f'**{ACHIEVEMENTS[k][0]}** (+{ACHIEVEMENTS[k][2]} очка)'
                           for k in fresh)
        embed = discord.Embed(
            title='Новое достижение',
            description=f'{member.mention if member else user_id} открывает {names}!',
            color=COLOR,
            timestamp=now,
        )
        if channel is not None:
            try:
                await channel.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.debug('achievements: анонс на %s не ушёл: %s', guild_id, _ex)

    # ---- команды ----
    @commands.hybrid_command(name='ачивки', aliases=['achievements', 'ачивка'],
                             description='Карточка достижений')
    async def cmd_card(self, ctx, участник: discord.Member = None):
        member = участник or ctx.author
        rec = self._rec(ctx.guild.id, member.id)
        stats = self._stats(ctx.guild, member.id, member)
        earned = evaluate(stats)
        # авто-довыдача, если условия выполнены вне потока сообщений
        fresh = new_grants(earned, rec['grants'])
        if fresh and not member.bot:
            now = datetime.now(UTC)
            for key in fresh:
                rec['grants'].append(key)
                rec['granted_at'][key] = now.isoformat()
            self._save_rec(ctx.guild.id, member.id, rec)

        rows = progress_rows(stats, rec['grants'])
        got = [r for r in rows if r['done']]
        todo = [r for r in rows if not r['done']]
        lines = [f"✦ **{r['name']}** — {r['desc']} (+{r['points']})" for r in got]
        lines += [f"◦ {r['name']} — {r['desc']} (+{r['points']})" for r in todo]
        embed = discord.Embed(
            title=f'Достижения · {member.display_name}',
            description=(f'Очки: **{total_points(rec["grants"])}** · '
                         f'Открыто: **{len(got)}/{len(rows)}**\n'
                         f'Сообщений: {stats["messages"]} · '
                         f'Войс: {tf.fmt_seconds(stats["voice_seconds"])} · '
                         f'На сервере: {tf.spell(stats["days_member"], "день", "дня", "дней")}\n\n'
                         + tf.clamp_text('\n'.join(lines), 3800)),
            color=COLOR,
        )
        embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else None)
        await ctx.reply(embed=embed, mention_author=False)

    @commands.hybrid_command(name='ачивлидеры', aliases=['achievetop'],
                             description='Топ сервера по очкам достижений')
    async def cmd_top(self, ctx):
        rows = []
        for key in self.db.get_all_keys(ctx.guild.id):
            if not key.startswith('user_'):
                continue
            rec = self.db.get(ctx.guild.id, key, user_record()) or user_record()
            pts = total_points(rec.get('grants', []))
            if pts > 0:
                rows.append((key[5:], pts, len(rec.get('grants', []))))
        rows.sort(key=lambda r: -r[1])
        if not rows:
            await ctx.reply('Пока никто не заработал очки достижений.',
                            mention_author=False)
            return
        lines = []
        for i, (uid, pts, count) in enumerate(rows[:10], 1):
            lines.append(f'**{i}.** <@{uid}> — {pts} очк. ({count} ачивок)')
        embed = discord.Embed(title='Топ по достижениям',
                              description='\n'.join(lines), color=COLOR)
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot):
    if not ACHIEVEMENTS_ENABLED:
        log.info('Достижения выключены владельцем (ACHIEVEMENTS_ENABLED=False) '
                 '— ког не загружается. Вернуть: флаг True в cogs/achievements.py')
        return
    await bot.add_cog(Achievements(bot))
