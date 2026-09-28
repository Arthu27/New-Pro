# -*- coding: utf-8 -*-
"""Автобан при входе/смене ника: АртемаВавилова + EN-варианты."""
from __future__ import annotations

import discord
from discord.ext import commands

from logger import get_logger
from services.name_autoban import BAN_REASON, member_banned_identity

log = get_logger('name_autoban')


class NameAutoban(commands.Cog):
    """Жёсткий автобан по списку имён — без панели, всегда вкл."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _maybe_ban(self, member: discord.Member, *, source: str) -> bool:
        if member is None or getattr(member, 'bot', False):
            return False
        guild = member.guild
        if guild is None:
            return False
        # Не трогаем владельца сервера.
        if guild.owner_id and int(member.id) == int(guild.owner_id):
            return False
        hit = member_banned_identity(member)
        if not hit:
            return False
        reason = f'{BAN_REASON} · {source} · «{hit}»'
        try:
            await guild.ban(
                member, reason=reason[:512], delete_message_days=0)
            log.warning(
                'name autoban uid=%s guild=%s hit=%r source=%s',
                member.id, guild.id, hit, source)
            return True
        except discord.Forbidden:
            log.warning(
                'name autoban FORBIDDEN uid=%s guild=%s (нет Ban Members?)',
                member.id, guild.id)
        except Exception as ex:
            log.warning('name autoban fail uid=%s: %s', member.id, ex)
        return False

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._maybe_ban(member, source='вход')

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before is None or after is None:
            return
        if (before.nick, before.display_name) == (after.nick, after.display_name):
            return
        await self._maybe_ban(after, source='смена ника')

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        if before is None or after is None:
            return
        if (before.name, getattr(before, 'global_name', None)) == (
                after.name, getattr(after, 'global_name', None)):
            return
        for guild in self.bot.guilds:
            m = guild.get_member(after.id)
            if m is not None:
                await self._maybe_ban(m, source='смена имени')


async def setup(bot: commands.Bot):
    await bot.add_cog(NameAutoban(bot))
    log.info('NameAutoban загружен')
