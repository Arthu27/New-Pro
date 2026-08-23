"""
Moderation Cog
Модерационные команды — чистое русское оформление.

ПРИМЕЧАНИЕ: наказания (бан/кик/мут) выдаются через /modpanel (select-меню
в cogs/moderation.py). Префиксные !ban / !kick / !mute удалены — всё в одном
меню, с обязательным доказательством. Здесь остались утилиты канала:
разбан, очистка, слоумод, блокировка.
"""

import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
import asyncio

from logger import get_logger
log = get_logger("moderation_cog")


class ModerationCog(commands.Cog):
    """Модерационные команды"""

    def __init__(self, bot):
        self.bot = bot

    def _embed(self, title, desc, color=0xe67e22, icon=""):
        e = discord.Embed(
            title=f"{icon} {title}".strip(),
            description=desc,
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        return e

    @commands.command(name='unban', aliases=['разбанить'])
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int):
        """Снять бан с пользователя"""
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user)
        except discord.NotFound:
            await ctx.send(embed=self._embed("Не удалось", "Пользователь не найден или не забанен!", discord.Color.red(), ""))
            return
        except Exception as e:
            await ctx.send(embed=self._embed("Не удалось снять бан", str(e), discord.Color.red(), ""))
            return

        embed = self._embed(
            "Бан снят",
            f"**Пользователь:** {user.mention}\n**Модератор:** {ctx.author.mention}",
            discord.Color.green(), "🔓"
        )
        await ctx.send(embed=embed)

    @commands.command(name='clear', aliases=['очистить'])
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int = 5):
        """Очистить указанное количество сообщений (макс. 100)"""
        if amount <= 0:
            await ctx.send(embed=self._embed("Неверное число", "Количество сообщений должно быть больше нуля.", discord.Color.red(), ""))
            return
        if amount > 100:
            await ctx.send(embed=self._embed("Слишком много", "Максимум 100 сообщений за раз!", discord.Color.red(), ""))
            return

        deleted = await ctx.channel.purge(limit=amount + 1)

        embed = self._embed(
            "Сообщения очищены",
            f"**Удалено сообщений:** {len(deleted) - 1}\n**Модератор:** {ctx.author.mention}",
            discord.Color.green(), "🧹"
        )
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(3)
        await msg.delete()

    @commands.command(name='slowmode', aliases=['слоумод'])
    @commands.has_permissions(manage_messages=True)
    async def slowmode(self, ctx, seconds: int = 0):
        """Установить медленный режим канала (секунды, 0 = выключить)"""
        if seconds < 0:
            await ctx.send(embed=self._embed("Неверное время", "Секунды не могут быть отрицательными!", discord.Color.red(), ""))
            return

        await ctx.channel.edit(slowmode_delay=seconds)

        if seconds > 0:
            embed = self._embed(
                "Медленный режим активен",
                f"**Длительность:** {seconds} сек.\n**Модератор:** {ctx.author.mention}",
                discord.Color.orange(), "🐢"
            )
        else:
            embed = self._embed(
                "Медленный режим выключен",
                f"**Модератор:** {ctx.author.mention}",
                discord.Color.green(), "🏃"
            )
        await ctx.send(embed=embed)

    @commands.command(name='lock', aliases=['закрыть'])
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx):
        """Закрыть канал (все не могут писать)"""
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)

        embed = self._embed(
            "Канал закрыт",
            f"**Канал:** {ctx.channel.mention}\n**Модератор:** {ctx.author.mention}",
            discord.Color.red(), "🔒"
        )
        await ctx.send(embed=embed)

    @commands.command(name='unlock', aliases=['открыть'])
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx):
        """Открыть канал"""
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)

        embed = self._embed(
            "Канал открыт",
            f"**Канал:** {ctx.channel.mention}\n**Модератор:** {ctx.author.mention}",
            discord.Color.green(), "🔓"
        )
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_ready(self):
        """Когда бот готов"""
        log.info("ModerationCog loaded")


async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
