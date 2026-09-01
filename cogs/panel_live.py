# -*- coding: utf-8 -*-
"""Живые обновления панели из Discord-событий (SSE-поток, services.live_bus).

Когда в Discord что-то меняется (канал/роль/участник/голос/мод-действие),
бот коротким сигналом «толкает» соответствующую страницу панели — она
перечитывает себя сама сразу, без опроса по таймеру.

Никаких данных в сигнале нет (только имя топика), ког ничего не пишет на диск
и не лезет в сеть — это просто мост «событие Discord → пуш в браузер».
"""
import discord
from discord.ext import commands

try:
    from logger import get_logger
    _log = get_logger('panel_live')
except Exception:                                   # noqa: BLE001
    import logging
    _log = logging.getLogger('panel_live')

try:
    from services import live_bus
except Exception as _e:                              # noqa: BLE001
    live_bus = None
    _log.debug('panel_live: шина недоступна: %s', _e)


def _pub(gid, topic):
    if live_bus is None or not gid:
        return
    try:
        live_bus.publish(gid, topic)
    except Exception as _ex:                          # noqa: BLE001
        _log.debug('panel_live publish %s/%s: %s', gid, topic, _ex)


class PanelLive(commands.Cog):
    """Мост событий Discord в живые обновления панели."""

    def __init__(self, bot):
        self.bot = bot

    # ── Каналы (страница «Каналы и маршруты», списки каналов) ──
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        _pub(getattr(channel.guild, 'id', None), 'channels')
        _pub(getattr(channel.guild, 'id', None), 'guild')

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        _pub(getattr(channel.guild, 'id', None), 'channels')
        _pub(getattr(channel.guild, 'id', None), 'guild')

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        _pub(getattr(after.guild, 'id', None), 'channels')

    # ── Роли ──
    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        _pub(getattr(role.guild, 'id', None), 'roles')

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        _pub(getattr(role.guild, 'id', None), 'roles')

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        _pub(getattr(after.guild, 'id', None), 'roles')

    # ── Участники (рост/состав, профиль, белые списки) ──
    @commands.Cog.listener()
    async def on_member_join(self, member):
        _pub(getattr(member.guild, 'id', None), 'members')
        _pub(getattr(member.guild, 'id', None), 'analytics')

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        _pub(getattr(member.guild, 'id', None), 'members')
        _pub(getattr(member.guild, 'id', None), 'analytics')

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        # роли/ник поменялись — списки участников и роли могли устареть
        if (before.roles != after.roles or before.display_name != after.display_name):
            _pub(getattr(after.guild, 'id', None), 'members')

    # ── Голос (пульс войса на аналитике) ──
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel != after.channel:
            _pub(getattr(member.guild, 'id', None), 'voice')
            _pub(getattr(member.guild, 'id', None), 'analytics')

    # ── Баны/разбаны (журнал модерации, щит) ──
    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        _pub(getattr(guild, 'id', None), 'moderation')
        _pub(getattr(guild, 'id', None), 'security')

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        _pub(getattr(guild, 'id', None), 'moderation')

    # ── Инвайты (лидеры инвайтов на аналитике) ──
    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        _pub(getattr(invite.guild, 'id', None), 'invites')
        _pub(getattr(invite.guild, 'id', None), 'analytics')


async def setup(bot):
    await bot.add_cog(PanelLive(bot))
