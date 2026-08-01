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
        """Показать время в голосовых каналах"""
        member = member or ctx.author
        data = self.db.get(ctx.guild.id, str(member.id))

        if not data or data.get('total_seconds', 0) == 0:
            embed = discord.Embed(
                title="Голосовая статистика",
                description=f"{member.display_name} ещё не был в голосовых каналах.",
                color=discord.Color.dark_grey()
            )
            await ctx.send(embed=embed)
            return

        total = data['total_seconds']
        h, m = divmod(total // 60, 60)
        d, h = divmod(h, 24)

        embed = discord.Embed(
            title=f"Голосовая статистика — {member.display_name}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        time_str = ""
        if d > 0:
            time_str += f"{d}д "
        if h > 0:
            time_str += f"{h}ч "
        time_str += f"{m}мин"

        embed.add_field(name="Общее время", value=time_str, inline=True)

        # Сегодня
        today = str(date.today())
        today_sec = data.get('daily', {}).get(today, 0)
        th, tm = divmod(today_sec // 60, 60)
        embed.add_field(name="Сегодня", value=f"{th}ч {tm}мин", inline=True)

        # За неделю
        week_sec = 0
        for i in range(7):
            day = str(date.today() - __import__('datetime').timedelta(days=i))
            week_sec += data.get('daily', {}).get(day, 0)
        wh, wm = divmod(week_sec // 60, 60)
        embed.add_field(name="За неделю", value=f"{wh}ч {wm}мин", inline=True)

        embed.set_footer(text=ctx.guild.name)
        await ctx.send(embed=embed)

    @commands.command(name='voiceleaderboard', aliases=['vtop', 'голостоп'])
    async def voice_leaderboard(self, ctx):
        """Топ-10 по времени в голосовых каналах"""
        all_data = self.db.get_all(ctx.guild.id)

        if not all_data:
            embed = discord.Embed(
                title="Голосовой рейтинг",
                description="Нет данных.",
                color=discord.Color.dark_grey()
            )
            await ctx.send(embed=embed)
            return

        # Сортировка по total_seconds
        sorted_users = sorted(
            [(uid, data) for uid, data in all_data.items() if isinstance(data, dict) and data.get('total_seconds', 0) > 0],
            key=lambda x: x[1].get('total_seconds', 0),
            reverse=True
        )[:10]

        embed = discord.Embed(
            title="Голосовой рейтинг — Топ 10",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )

        for i, (uid, data) in enumerate(sorted_users, 1):
            total = data.get('total_seconds', 0)
            h, m = divmod(total // 60, 60)
            d, h = divmod(h, 24)
            time_str = f"{d}д {h}ч {m}мин" if d > 0 else f"{h}ч {m}мин"
            name = data.get('name', f'ID: {uid}')
            embed.add_field(name=f"{i}. {name}", value=time_str, inline=False)

        embed.set_footer(text=ctx.guild.name)
        await ctx.send(embed=embed)

    @commands.command(name='voiceonline', aliases=['голосонлайн'])
    async def voice_online(self, ctx):
        """Показать всех в голосовых каналах"""
        voice_members = []
        for channel in ctx.guild.voice_channels:
            for member in channel.members:
                if not member.bot:
                    voice_members.append((member, channel))

        if not voice_members:
            embed = discord.Embed(
                title="Голосовые каналы",
                description="Сейчас никого нет в голосовых каналах.",
                color=discord.Color.dark_grey()
            )
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(
            title=f"Голосовые каналы — {len(voice_members)} участников",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )

        # Группировка по каналам
        channels = {}
        for member, channel in voice_members:
            if channel.name not in channels:
                channels[channel.name] = []
            channels[channel.name].append(member.display_name)

        for ch_name, members in channels.items():
            embed.add_field(
                name=f"{ch_name} ({len(members)})",
                value=", ".join(members[:10]) + ("..." if len(members) > 10 else ""),
                inline=False
            )

        embed.set_footer(text=ctx.guild.name)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(VoiceTracker(bot))
    log.info("VoiceTracker загружен — все каналы отслеживаются")
