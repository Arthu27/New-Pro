# -*- coding: utf-8 -*-
"""Активность сервера → «Аналитика» в панели.

Каждое сообщение участников (не ботов, не вебхуки, не ЛС) идёт лёгкой
записью в services.message_stats — оттуда панель рисует сообщения/дня,
топ участников, топ каналов и теплокарту. Текст сообщения НЕ пишется.
Сбор работает всегда и не зависит от настроек лог-каналов: это внутренняя
статистика, а не лог на всеобщее обозрение.
"""
import discord
from discord.ext import commands

from logger import get_logger
from services import message_stats

_log = get_logger('activity_stats')


class ActivityStats(commands.Cog):
    """Счётчик сообщений для аналитики (слушатель, без команд)."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        try:
            if not message.guild or message.author.bot or message.webhook_id:
                return
            message_stats.record(
                message.guild.id,
                message.author.display_name or str(message.author),
                getattr(message.channel, 'name', 'неизвестно'),
            )
        except Exception as _se:
            _log.debug('activity_stats: подавлено: %s', _se)  # статистика не ломает обработку


async def setup(bot):
    await bot.add_cog(ActivityStats(bot))
    message_stats.start()
