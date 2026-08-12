"""
Moderation Cog
Модерационные команды — чистое русское оформление
"""

import discord
from discord.ext import commands
from datetime import datetime, timedelta
import asyncio

from logger import get_logger
log = get_logger("moderation_cog")

MUTE_ROLE = "Muted"


class ModerationCog(commands.Cog):
    """Модерационные команды"""

    def __init__(self, bot):
        self.bot = bot

    def _embed(self, title, desc, color=0xe67e22, icon=""):
        e = discord.Embed(
            title=f"{icon} {title}".strip(),
            description=desc,
            color=color,
            timestamp=datetime.now()
        )
        return e

    async def _get_mute_role(self, guild):
        """Найти или создать роль Muted и настроить все каналы"""
        mute_role = discord.utils.get(guild.roles, name=MUTE_ROLE)
        if mute_role:
            return mute_role
        mute_role = await guild.create_role(name=MUTE_ROLE, color=discord.Color.dark_gray(),
                                            reason="Автоматически созданная роль мута")
        for channel in guild.channels:
            try:
                await channel.set_permissions(mute_role, send_messages=False, speak=False)
            except Exception as _ex:
                log.debug("_get_mute_role(): подавлено: %s", _ex)
                continue
        return mute_role

    # ПРИМЕЧАНИЕ: команда !warn убрана отсюда — она конфликтовала
    # с /warn из cogs/warnings.py и мешала загрузке warnings-кога.

    @commands.command(name='mute', aliases=['замьютить'])
    @commands.has_permissions(manage_messages=True)
    async def mute(self, ctx, member: discord.Member, duration: int = 10, *, reason: str = 'Причина не указана'):
        """Временно замьютить пользователя (минуты)"""
        if duration <= 0:
            await ctx.send("Длительность должна быть больше 0!")
            return

        mute_role = await self._get_mute_role(ctx.guild)

        if mute_role in member.roles:
            await ctx.send(f"{member.mention} уже замьючен!")
            return

        await member.add_roles(mute_role, reason=reason)

        embed = self._embed(
            "Пользователь замьючен",
            f"**Пользователь:** {member.mention}\n**Длительность:** {duration} мин.\n**Причина:** {reason}\n**Модератор:** {ctx.author.mention}",
            discord.Color.orange(), "🔇"
        )
        await ctx.send(embed=embed)

        # Автоматический анмьют в фоне
        async def auto_unmute():
            await asyncio.sleep(duration * 60)
            fresh = ctx.guild.get_member(member.id)
            if fresh and mute_role in fresh.roles:
                await fresh.remove_roles(mute_role, reason="Срок мута истёк")
        asyncio.get_event_loop().create_task(auto_unmute())

    @commands.command(name='unmute', aliases=['размьютить'])
    @commands.has_permissions(manage_messages=True)
    async def unmute(self, ctx, member: discord.Member):
        """Снять мьют с пользователя"""
        mute_role = discord.utils.get(ctx.guild.roles, name=MUTE_ROLE)

        if not mute_role or mute_role not in member.roles:
            await ctx.send("Этот пользователь не замьючен!")
            return

        await member.remove_roles(mute_role, reason="Мьют снят")

        embed = self._embed(
            "Мьют снят",
            f"**Пользователь:** {member.mention}\n**Модератор:** {ctx.author.mention}",
            discord.Color.green(), "🔊"
        )
        await ctx.send(embed=embed)

    @commands.command(name='kick', aliases=['кик'])
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = 'Причина не указана'):
        """Выгнать пользователя с сервера"""
        if member.top_role >= ctx.author.top_role and member.id != ctx.guild.owner_id:
            await ctx.send("Роль этого пользователя выше или равна твоей!")
            return

        await member.kick(reason=reason)

        embed = self._embed(
            "Пользователь кикнут",
            f"**Пользователь:** {member.mention}\n**Причина:** {reason}\n**Модератор:** {ctx.author.mention}",
            discord.Color.orange(), "👢"
        )
        await ctx.send(embed=embed)

    @commands.command(name='ban', aliases=['забанить'])
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = 'Причина не указана'):
        """Забанить пользователя на сервере"""
        if member.top_role >= ctx.author.top_role and member.id != ctx.guild.owner_id:
            await ctx.send("Роль этого пользователя выше или равна твоей!")
            return

        await member.ban(reason=reason)

        embed = self._embed(
            "Пользователь забанен",
            f"**Пользователь:** {member.mention}\n**Причина:** {reason}\n**Модератор:** {ctx.author.mention}",
            discord.Color.red(), "🔨"
        )
        await ctx.send(embed=embed)

        try:
            dm = discord.Embed(title="🔨 Вы забанены",
                               description=f"**Сервер:** {ctx.guild.name}\n**Причина:** {reason}",
                               color=discord.Color.red(), timestamp=datetime.now())
            await member.send(embed=dm)
        except Exception as _ex:
            log.debug("ban(): подавлено: %s", _ex)

    @commands.command(name='unban', aliases=['разбанить'])
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int):
        """Снять бан с пользователя"""
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user)
        except discord.NotFound:
            await ctx.send("Пользователь не найден или не забанен!")
            return
        except Exception as e:
            await ctx.send(f"Не удалось снять бан: {e}")
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
            await ctx.send("Введите корректное число!")
            return
        if amount > 100:
            await ctx.send("Максимум 100 сообщений за раз!")
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
            await ctx.send("Секунды не могут быть отрицательными!")
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
