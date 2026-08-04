"""
Level Cog
Расширенная система уровней
"""
import discord
from discord.ext import commands
from datetime import datetime
import random

from logger import get_logger
log = get_logger("level_cog")


class LevelCog(commands.Cog):
    """Расширенная система уровней"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='level-rank', aliases=['уровень'])
    async def rank(self, ctx, member: discord.Member = None):
        """Показать карточку уровня"""
        member = member or ctx.author

        embed = discord.Embed(
            title=f"📊 Уровень — {member.display_name}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )

        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Уровень", value="10", inline=True)
        embed.add_field(name="XP", value="5,000/10,000", inline=True)
        embed.add_field(name="Рейтинг", value="#5", inline=True)

        await ctx.send(embed=embed)

    @commands.command(name='level-lb', aliases=['level-top'])
    async def leaderboard(self, ctx):
        """Показать таблицу лидеров по уровням"""
        embed = discord.Embed(
            title="🏆 Таблица лидеров по уровням",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )

        # Пример таблицы лидеров
        for i in range(1, 11):
            embed.add_field(
                name=f"#{i} Пользователь{i}",
                value=f"Уровень {20 - i} | XP: {10000 - i * 500:,}",
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.command(name='rewards', aliases=['награды'])
    async def rewards(self, ctx):
        """Показать награды за уровни"""
        embed = discord.Embed(
            title="🎁 Награды за уровни",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )

        rewards = [
            ("Уровень 5", "Роль «Участник»"),
            ("Уровень 10", "Роль «Активный участник»"),
            ("Уровень 20", "Роль «VIP»"),
            ("Уровень 50", "Роль «Легенда»")
        ]

        for level, reward in rewards:
            embed.add_field(
                name=level,
                value=reward,
                inline=True
            )

        await ctx.send(embed=embed)

    @commands.command(name='setlevel', aliases=['установитьуровень'])
    @commands.has_permissions(administrator=True)
    async def setlevel(self, ctx, member: discord.Member, level: int):
        """Установить уровень участника"""
        embed = discord.Embed(
            title="✅ Уровень обновлён",
            description=f"**Новый уровень {member.mention}:** {level}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )

        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_ready(self):
        """Бот готов"""
        log.info("LevelCog loaded")


async def setup(bot):
    await bot.add_cog(LevelCog(bot))
