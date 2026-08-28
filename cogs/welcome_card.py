# -*- coding: utf-8 -*-
"""
Welcome Card — роскошная карточка приветствия (тёмно-синий + золото).

При входе участника бот рисует карту с его аватаром:
«ДОБРО ПОЖАЛОВАТЬ · Имя · ты N-й участник сервера».
Опционально — карта «ДО СВИДАНИЯ» при выходе.

Оформление карточки настраивается из панели (Приветствие → карточка):
авто-картинка в одной из 5 фирменных тем, своя картинка по URL
или вовсе без картинки (см. services/welcome_card_gen.py).

Команды: /welcome ... (админ).
Хранилище: data/welcome_card.json
"""

from logger import get_logger

_log = get_logger("welcome_card")

import io
import json
import os
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from logger import get_logger
from services import welcome_card_gen as WCG

log = get_logger("welcome_card")

CFG_PATH = WCG.CFG_PATH

GOLD = 0xD4AF37
DIVIDER = "✦ ───────────────────── ✦"

DEFAULT_CFG = {
    "enabled": False,         # авто-приветствия ВЫКЛЮЧЕНЫ по умолчанию
                               # (владелец сам включит и настроит в панели)
    "channel_id": 0,          # 0 = system_channel
    "welcome": False,         # карта при входе
    "goodbye": False,         # карта при выходе
}


def _load_cfg():
    return WCG._load_raw()


def _save_cfg(data):
    WCG._save_raw(data)


def render_card(member_name: str, guild_name: str, count: int,
                avatar_bytes: bytes = None, kind: str = 'welcome',
                theme: str = None) -> io.BytesIO:
    """kind: 'welcome' | 'goodbye' → PNG bytes (обёртка над сервисом)."""
    return io.BytesIO(WCG.render_welcome_card(
        member_name, guild_name, count, avatar_bytes=avatar_bytes,
        kind=kind, theme=theme))


class WelcomeCard(commands.Cog):
    """Картинка-приветствие с аватаром (темы настраиваются из панели)."""

    def __init__(self, bot):
        self.bot = bot
        self._cfgs = _load_cfg()

    def cfg(self, guild_id: int) -> dict:
        c = dict(DEFAULT_CFG)
        c.update(self._cfgs.get(str(guild_id), {}))
        return c

    def set_cfg(self, guild_id: int, key: str, value):
        self._cfgs.setdefault(str(guild_id), {})[key] = value
        _save_cfg(self._cfgs)

    def _appearance(self, guild_id: int) -> dict:
        """Оформление карточки: сначала из конфига кога, затем из файла."""
        sec = self._cfgs.get(str(guild_id))
        if isinstance(sec, dict) and isinstance(sec.get('appearance'), dict):
            return WCG.normalize_appearance(sec['appearance'])
        return WCG.get_appearance(guild_id)

    async def _avatar_bytes(self, member: discord.abc.User):
        try:
            return await member.display_avatar.replace(size=256, static_format='png').read()
        except Exception:
            return None

    async def _send_card(self, guild: discord.Guild, member: discord.abc.User, kind: str):
        cfg = self.cfg(guild.id)
        ch_id = int(cfg.get('channel_id', 0) or 0)
        ch = guild.get_channel(ch_id) if ch_id else None
        if ch is None:
            ch = guild.system_channel
        if ch is None:
            return
        appearance = self._appearance(guild.id)
        text = (f"Добро пожаловать, {member.mention} ✨" if kind == 'welcome'
                else f"До свидания, **{member.display_name}**")
        try:
            # Своя картинка по URL: эмбед с set_image (только https — проверяет панель)
            if appearance['mode'] == 'url':
                embed = discord.Embed(
                    color=GOLD if kind == 'welcome' else 0x95A5A6,
                    timestamp=datetime.now(timezone.utc))
                embed.set_image(url=appearance['url'])
                await ch.send(content=text, embed=embed)
                return
            # Без картинки: простое текстовое приветствие
            if appearance['mode'] == 'off':
                await ch.send(content=text)
                return
            # Авто-картинка: рисуем карточку в выбранной теме
            av = await self._avatar_bytes(member)
            png = WCG.render_welcome_card(
                member.display_name, guild.name, guild.member_count or 0,
                avatar_bytes=av, kind=kind, theme=appearance['theme'])
            file = discord.File(io.BytesIO(png),
                                filename=WCG.welcome_card_filename(kind))
            await ch.send(content=(text if kind == 'welcome' else None), file=file)
        except Exception as e:
            log.warning(f"[WCARD] {guild.name}: не смог отправить карту ({kind}): {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = self.cfg(member.guild.id)
        if cfg.get('enabled') and cfg.get('welcome'):
            await self._send_card(member.guild, member, 'welcome')

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        cfg = self.cfg(member.guild.id)
        if cfg.get('enabled') and cfg.get('goodbye'):
            await self._send_card(member.guild, member, 'goodbye')

    # ────────────────────────────────────────────────────────────

    def _status_embed(self, guild: discord.Guild) -> discord.Embed:
        cfg = self.cfg(guild.id)
        appearance = self._appearance(guild.id)
        ch = guild.get_channel(int(cfg.get('channel_id', 0) or 0))
        theme_lbl = WCG.WELCOME_THEMES.get(
            appearance['theme'], {}).get('label', appearance['theme'])
        mode_lbl = WCG.WELCOME_MODE_LABELS.get(appearance['mode'], appearance['mode'])
        e = discord.Embed(color=GOLD if cfg.get('enabled') else 0x95A5A6,
                          timestamp=datetime.now(timezone.utc))
        e.description = (
            "## 🖼 Welcome Card\n"
            f"Система: **{'🟢 вкл' if cfg.get('enabled') else '🔴 выкл'}**\n"
            f"Карта входа: **{'вкл' if cfg.get('welcome') else 'выкл'}**\n"
            f"Карта прощания: **{'вкл' if cfg.get('goodbye') else 'выкл'}**\n"
            f"Оформление: **{mode_lbl}**"
            + (f" · тема **{theme_lbl}**" if appearance['mode'] == 'auto' else '') + "\n"
            f"Канал: {ch.mention if ch else '`системный канал сервера`'}\n{DIVIDER}")
        e.set_footer(text=f"{guild.name} · welcome card")
        return e


async def setup(bot):
    await bot.add_cog(WelcomeCard(bot))
    log.info("[WCARD] Ког загружен")
