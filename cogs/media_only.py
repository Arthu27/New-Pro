"""
Medialock — режим каналов (медиа-только / текст-только / ссылки-только).

Для каналов-галерей: разрешены только картинки/видео. Для каналов-обсуждений:
без вложений. Для каналов-ресурсов: только сообщения со ссылкой.

Нарушение — сообщение удаляется, автор получает вежливое DM-предупреждение
(не чаще 1 раза в 60 сек на человека, чтобы не спамить).

Команды: /medialock set|remove|list (manage_guild).
Хранилище: data/media_only.json
"""

from logger import get_logger

_log = get_logger("media_only")

import os
import re
import json
import time
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from logger import get_logger

log = get_logger("media_only")

DATA_PATH = 'data/media_only.json'

GOLD = 0xD4AF37
ORANGE = 0xE67E22
DIVIDER = "✦ ───────────────────── ✦"

MODES = {
    'media': {'label': '🖼 Только медиа', 'desc': 'картинки и видео',
              'hint': 'В этом канале разрешены только изображения и видео.'},
    'text': {'label': '💬 Только текст', 'desc': 'без вложений и ссылок',
             'hint': 'В этом канале запрещены вложения и ссылки.'},
    'link': {'label': '🔗 Только ссылки', 'desc': 'сообщения должны содержать ссылку',
             'hint': 'В этом канале сообщение должно содержать ссылку.'},
}

_URL_RE = re.compile(r'https?://\S+', re.IGNORECASE)
_MEDIA_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.mov', '.webm', '.avif', '.bmp')

DM_COOLDOWN = 60  # сек


def _load():
    try:
        if os.path.exists(DATA_PATH):
            with open(DATA_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as _ex:
        _log.debug("_load(): подавлено: %s", _ex)
    return {}


def _save(data):
    try:
        os.makedirs('data', exist_ok=True)
        tmp = DATA_PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_PATH)
    except Exception as e:
        log.error(f"[MEDIALOCK] ошибка записи: {e}")


class MediaLock(commands.Cog):
    """Замок режима канала: медиа / текст / ссылки."""

    def __init__(self, bot):
        self.bot = bot
        self._data = _load()
        self._dm_cd = {}  # (gid, uid) -> ts последнего DM

    def channels(self, guild_id: int) -> dict:
        """{channel_id(str): {'mode': str, 'exempt_mods': bool}}"""
        return self._data.setdefault(str(guild_id), {})

    def _save(self):
        _save(self._data)

    # ────────────────────────────────────────────────────────────
    # Проверка сообщения
    # ────────────────────────────────────────────────────────────
    def _has_media(self, message: discord.Message) -> bool:
        for a in message.attachments or []:
            fn = (a.filename or '').lower()
            ct = (a.content_type or '')
            if ct.startswith('image/') or ct.startswith('video/') or fn.endswith(_MEDIA_EXT):
                return True
        # ссылки на картинки в тексте тоже считаем медиа
        content = (message.content or '').lower()
        return bool(re.search(
            r'https?://\S+\.(?:png|jpe?g|gif|webp|mp4|mov|webm|avif|bmp)\b', content))

    def _has_link(self, message: discord.Message) -> bool:
        return bool(_URL_RE.search(message.content or ''))

    def violates(self, message: discord.Message, mode: str) -> bool:
        if mode == 'media':
            return not self._has_media(message)
        if mode == 'text':
            return bool(message.attachments) or self._has_link(message)
        if mode == 'link':
            return not self._has_link(message)
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot or not isinstance(message.author, discord.Member):
            return
        rec = self.channels(message.guild.id).get(str(message.channel.id))
        if not rec:
            return
        member = message.author
        if rec.get('exempt_mods', True) and (
            member.guild_permissions.manage_messages
            or member.guild_permissions.moderate_members
            or member.guild_permissions.administrator):
            return
        mode = rec.get('mode', 'media')
        if not self.violates(message, mode):
            return

        try:
            await message.delete()
        except Exception:
            return

        key = (message.guild.id, member.id)
        now = time.time()
        if now - self._dm_cd.get(key, 0) >= DM_COOLDOWN:
            self._dm_cd[key] = now
            try:
                meta = MODES.get(mode, MODES['media'])
                e = discord.Embed(color=ORANGE, timestamp=datetime.now(timezone.utc))
                e.description = (
                    f"## {meta['label']}\n"
                    f"Сервер: **{message.guild.name}**\n"
                    f"Канал: **#{getattr(message.channel, 'name', '?')}**\n\n"
                    f"{meta['hint']} Ваше сообщение удалено.")
                e.set_footer(text=message.guild.name)
                await member.send(embed=e)
            except Exception as _ex:
                _log.debug("on_message(): подавлено: %s", _ex)

    # ────────────────────────────────────────────────────────────
    # Slash: /medialock
    # ────────────────────────────────────────────────────────────
    medialock = app_commands.Group(name="medialock", description="Режим канала (медиа/текст/ссылки)")

    @medialock.command(name="set", description="Задать режим канала")
    @app_commands.describe(
        канал="Канал для замка",
        режим="Что разрешено",
        исключить_модов="Модераторы могут писать свободно (по умолч. да)")
    @app_commands.choices(режим=[
        app_commands.Choice(name="🖼 Только медиа (картинки/видео)", value="media"),
        app_commands.Choice(name="💬 Только текст (без вложений/ссылок)", value="text"),
        app_commands.Choice(name="🔗 Только ссылки", value="link"),
    ], исключить_модов=[
        app_commands.Choice(name="Да", value=1),
        app_commands.Choice(name="Нет", value=0),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ml_set(self, interaction: discord.Interaction, канал: discord.TextChannel,
                     режим: app_commands.Choice[str], исключить_модов: app_commands.Choice[int] = None):
        chs = self.channels(interaction.guild.id)
        chs[str(канал.id)] = {
            'mode': режим.value,
            'exempt_mods': bool(исключить_модов.value) if исключить_модов else True,
        }
        self._save()
        meta = MODES[режим.value]
        await interaction.response.send_message(
            f"✅ {канал.mention}: режим **{meta['label']}** ({meta['desc']}).", ephemeral=True)

    @medialock.command(name="remove", description="Снять замок с канала")
    @app_commands.describe(канал="Канал")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ml_remove(self, interaction: discord.Interaction, канал: discord.TextChannel):
        chs = self.channels(interaction.guild.id)
        if chs.pop(str(канал.id), None) is not None:
            self._save()
            await interaction.response.send_message(f"🔓 Замок с {канал.mention} снят.", ephemeral=True)
        else:
            await interaction.response.send_message(f"ℹ️ На {канал.mention} замка не было.", ephemeral=True)

    @medialock.command(name="list", description="Каналы с режимами")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ml_list(self, interaction: discord.Interaction):
        chs = self.channels(interaction.guild.id)
        e = discord.Embed(color=GOLD, timestamp=datetime.now(timezone.utc))
        if not chs:
            e.description = "## 🔒 Medialock\nНи одного замка нет — `/medialock set`"
        else:
            lines = ["## 🔒 Medialock — активные замки\n"]
            for cid, rec in chs.items():
                ch = interaction.guild.get_channel(int(cid))
                meta = MODES.get(rec.get('mode'), MODES['media'])
                ex = "моды свободны" if rec.get('exempt_mods', True) else "для всех"
                lines.append(f"{meta['label']} — {ch.mention if ch else f'`{cid}`'} · {ex}")
            lines.append(DIVIDER)
            e.description = "\n".join(lines)
        e.set_footer(text=f"{interaction.guild.name} · medialock")
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(MediaLock(bot))
    log.info("[MEDIALOCK] Ког загружен")
