"""
Search Cog
Команды поиска по серверу
"""

import discord
from discord.ext import commands
from datetime import datetime

from logger import get_logger
log = get_logger("search_cog")


class SearchCog(commands.Cog):
    """Команды поиска по серверу"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='search', aliases=['найти'])
    async def search(self, ctx, *, query: str):
        """Общий поиск"""
        embed = discord.Embed(
            title=f"🔍 Поиск: {query}",
            description="Результаты поиска загружаются...",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )

        await ctx.send(embed=embed)

    @commands.command(name='searchuser', aliases=['найтиучастника'])
    async def searchuser(self, ctx, *, query: str):
        """Поиск участника"""
        members = [m for m in ctx.guild.members if query.lower() in m.display_name.lower()]

        if not members:
            await ctx.send("❌ Участник не найден!")
            return

        embed = discord.Embed(
            title=f"🔍 Поиск участника: {query}",
            description=f"**Найдено:** {len(members)} участник(ов)",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )

        for member in members[:10]:
            embed.add_field(
                name=member.display_name,
                value=f"ID: {member.id}",
                inline=True
            )

        await ctx.send(embed=embed)

    @commands.command(name='searchticket', aliases=['найтитикет'])
    async def searchticket(self, ctx, ticket_id: str):
        """Поиск тикета"""
        embed = discord.Embed(
            title=f"🎫 Поиск тикета: {ticket_id}",
            description="Информация о тикете загружается...",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )

        await ctx.send(embed=embed)

    @commands.command(name='searchrole', aliases=['найтироль'])
    async def searchrole(self, ctx, *, query: str):
        """Поиск роли"""
        roles = [r for r in ctx.guild.roles if query.lower() in r.name.lower()]

        if not roles:
            await ctx.send("❌ Роль не найдена!")
            return

        embed = discord.Embed(
            title=f"🔍 Поиск роли: {query}",
            description=f"**Найдено:** {len(roles)} роль(ей)",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )

        for role in roles[:10]:
            embed.add_field(
                name=role.name,
                value=f"ID: {role.id} | Участников: {len(role.members)}",
                inline=True
            )

        await ctx.send(embed=embed)

    @commands.command(name='searchchannel', aliases=['найтиканал'])
    async def searchchannel(self, ctx, *, query: str):
        """Поиск канала"""
        channels = [c for c in ctx.guild.channels if query.lower() in c.name.lower()]

        if not channels:
            await ctx.send("❌ Канал не найден!")
            return

        embed = discord.Embed(
            title=f"🔍 Поиск канала: {query}",
            description=f"**Найдено:** {len(channels)} канал(ов)",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )

        for channel in channels[:10]:
            embed.add_field(
                name=channel.name,
                value=f"ID: {channel.id}",
                inline=True
            )

        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_ready(self):
        """Бот готов"""
        log.info("SearchCog loaded")


async def setup(bot):
    await bot.add_cog(SearchCog(bot))
