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


    @commands.Cog.listener()
    async def on_ready(self):
        """Когда бот готов"""
        log.info("ModerationCog loaded")


async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
