"""
Join-to-Create — личные голосовые комнаты.

Участник заходит в канал-«лобби» → бот создаёт ему персональную
голосовую комнату и переносит в неё. Комната живёт, пока в ней
есть люди; когда последний выходит — удаляется автоматически.

Владелец комнаты управляет ею: /vc rename /limit /lock /unlock /transfer.
Настройка: /j2c lobby /category /template /on /off (админ).

Реестр комнат переживает рестарт бота: data/j2c_rooms.json.
"""

from logger import get_logger

_log = get_logger("join_to_create")

import os
import json
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from logger import get_logger

log = get_logger("j2c")

CFG_PATH = 'data/j2c.json'
ROOMS_PATH = 'data/j2c_rooms.json'

GOLD = 0xD4AF37
GREEN = 0x2ECC71
GRAY = 0x95A5A6
DIVIDER = "✦ ───────────────────── ✦"

DEFAULT_CFG = {
    "enabled": True,
    "lobby_id": 0,                 # канал-лобби (0 = система выкл)
    "category_id": 0,              # куда создавать (0 = категория лобби)
    "user_limit": 0,               # лимит по умолчанию (0 = безлимит)
    "name_template": "🔊 {user}",  # {user} = имя владельца
}


def _load(path, default):
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as _ex:
        _log.debug("_load(): подавлено: %s", _ex)
    return default


def _save(path, data):
    try:
        os.makedirs('data', exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        log.error(f"[J2C] ошибка записи {path}: {e}")


class JoinToCreate(commands.Cog):
    """Персональные голосовые комнаты по входу в лобби."""

    def __init__(self, bot):
        self.bot = bot
        self._cfgs = _load(CFG_PATH, {})
        self._rooms = _load(ROOMS_PATH, {})
        self._reconciled = False

    def cfg(self, guild_id: int) -> dict:
        c = dict(DEFAULT_CFG)
        c.update(self._cfgs.get(str(guild_id), {}))
        return c

    def set_cfg(self, guild_id: int, key: str, value):
        self._cfgs.setdefault(str(guild_id), {})[key] = value
        _save(CFG_PATH, self._cfgs)

    # ── реестр комнат ──
    def _room_map(self, guild_id: int) -> dict:
        return self._rooms.setdefault(str(guild_id), {})

    def owner_of(self, guild_id: int, channel_id: int):
        v = self._room_map(guild_id).get(str(channel_id))
        return int(v) if v else None

    def _set_room(self, guild_id: int, channel_id: int, owner_id: int):
        self._room_map(guild_id)[str(channel_id)] = int(owner_id)
        _save(ROOMS_PATH, self._rooms)

    def _del_room(self, guild_id: int, channel_id: int):
        if self._room_map(guild_id).pop(str(channel_id), None) is not None:
            _save(ROOMS_PATH, self._rooms)

    # ────────────────────────────────────────────────────────────
    # Создание / удаление
    # ────────────────────────────────────────────────────────────
    async def _create_room(self, member: discord.Member):
        guild = member.guild
        cfg = self.cfg(guild.id)
        lobby = guild.get_channel(int(cfg.get('lobby_id', 0) or 0))
        if lobby is None:
            return
        category = guild.get_channel(int(cfg.get('category_id', 0) or 0))
        if category is None:
            category = lobby.category
        name = str(cfg.get('name_template') or '🔊 {user}')[:96].replace('{user}', member.display_name)
        limit = int(cfg.get('user_limit', 0) or 0)
        try:
            overwrites = {guild.default_role: discord.PermissionOverwrite(connect=True)}
            vc = await guild.create_voice_channel(
                name=name, category=category, user_limit=limit,
                overwrites=overwrites,
                reason=f"[J2C] личная комната для {member}")
            self._set_room(guild.id, vc.id, member.id)
            await member.move_to(vc, reason="[J2C] вход в личную комнату")
            log.info(f"[J2C] {guild.name}: комната «{vc.name}» создана для {member}")
        except Exception as e:
            log.warning(f"[J2C] {guild.name}: создание комнаты: {e}")

    async def _cleanup_room(self, channel: discord.VoiceChannel):
        """Удалить комнату, если она наша и опустела."""
        if not isinstance(channel, discord.VoiceChannel):
            return
        if self.owner_of(channel.guild.id, channel.id) is None:
            return
        if len(channel.members) > 0:
            return
        try:
            await channel.delete(reason="[J2C] комната опустела")
            log.info(f"[J2C] {channel.guild.name}: комната «{channel.name}» удалена")
        except Exception as e:
            log.warning(f"[J2C] удаление комнаты: {e}")
        finally:
            self._del_room(channel.guild.id, channel.id)

    # ────────────────────────────────────────────────────────────
    # Слушатели
    # ────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        guild = member.guild
        cfg = self.cfg(guild.id)
        if not cfg.get('enabled'):
            return
        lobby_id = int(cfg.get('lobby_id', 0) or 0)

        # зашёл в лобби → своя комната
        if lobby_id and after.channel and after.channel.id == lobby_id \
                and (not before.channel or before.channel.id != lobby_id):
            await self._create_room(member)
            return

        # вышел из комнаты → подчистить, если опустела
        if before.channel and (not after.channel or after.channel.id != before.channel.id):
            await self._cleanup_room(before.channel)

    @commands.Cog.listener()
    async def on_ready(self):
        """Подчистка после рестарта: битые/пустые комнаты."""
        if self._reconciled:
            return
        self._reconciled = True
        for guild in self.bot.guilds:
            try:
                for cid in list(self._room_map(guild.id).keys()):
                    ch = guild.get_channel(int(cid))
                    if ch is None:
                        self._del_room(guild.id, int(cid))
                    elif isinstance(ch, discord.VoiceChannel) and len(ch.members) == 0:
                        await self._cleanup_room(ch)
            except Exception as e:
                log.error(f"[J2C] reconcile {guild}: {e}")
        log.info("[J2C] reconcile завершён")

    # ────────────────────────────────────────────────────────────
    # Управление комнатой (/vc) — владелец
    # ────────────────────────────────────────────────────────────
    def _own_room(self, member: discord.Member):
        """Комната, в которой участник сейчас И которой владеет."""
        if not member.voice or not member.voice.channel:
            return None
        if self.owner_of(member.guild.id, member.voice.channel.id) == member.id:
            return member.voice.channel
        return None

    vc = app_commands.Group(name="vc", description="Управление своей голосовой комнатой")

    async def _no_room(self, interaction: discord.Interaction, lo: discord.VoiceChannel = None) -> bool:
        if lo is None:
            await interaction.response.send_message(
                "❌ Ты не в своей комнате (зайди в лобби, чтобы создать её).", ephemeral=True)
            return True
        return False

    @vc.command(name="rename", description="Переименовать комнату")
    @app_commands.describe(название="Новое имя комнаты")
    async def vc_rename(self, interaction: discord.Interaction, название: str):
        room = self._own_room(interaction.user)
        if await self._no_room(interaction, room):
            return
        try:
            await room.edit(name=название[:96], reason=f"[J2C] rename от {interaction.user}")
            await interaction.response.send_message(f"✏️ Комната переименована: **{название[:96]}**", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Не удалось: `{e}`", ephemeral=True)

    @vc.command(name="limit", description="Лимит мест в комнате (0 = безлимит)")
    @app_commands.describe(число="От 0 до 99")
    async def vc_limit(self, interaction: discord.Interaction, число: app_commands.Range[int, 0, 99]):
        room = self._own_room(interaction.user)
        if await self._no_room(interaction, room):
            return
        try:
            await room.edit(user_limit=число, reason=f"[J2C] limit от {interaction.user}")
            txt = "безлимит" if число == 0 else str(число)
            await interaction.response.send_message(f"👥 Лимит комнаты: **{txt}**", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Не удалось: `{e}`", ephemeral=True)

    @vc.command(name="lock", description="Закрыть комнату (никто новый не зайдёт)")
    async def vc_lock(self, interaction: discord.Interaction):
        room = self._own_room(interaction.user)
        if await self._no_room(interaction, room):
            return
        try:
            await room.set_permissions(interaction.guild.default_role, connect=False,
                                       reason=f"[J2C] lock от {interaction.user}")
            await interaction.response.send_message("🔒 Комната **закрыта** — новые не зайдут.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Не удалось: `{e}`", ephemeral=True)

    @vc.command(name="unlock", description="Открыть комнату снова")
    async def vc_unlock(self, interaction: discord.Interaction):
        room = self._own_room(interaction.user)
        if await self._no_room(interaction, room):
            return
        try:
            await room.set_permissions(interaction.guild.default_role, connect=None,
                                       reason=f"[J2C] unlock от {interaction.user}")
            await interaction.response.send_message("🔓 Комната **открыта**.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Не удалось: `{e}`", ephemeral=True)

    @vc.command(name="transfer", description="Передать комнату другому участнику (он должен быть в ней)")
    @app_commands.describe(участник="Новый владелец")
    async def vc_transfer(self, interaction: discord.Interaction, участник: discord.Member):
        room = self._own_room(interaction.user)
        if await self._no_room(interaction, room):
            return
        if участник.bot or участник not in room.members:
            await interaction.response.send_message(
                "❌ Участник должен находиться в твоей комнате.", ephemeral=True)
            return
        self._set_room(interaction.guild.id, room.id, участник.id)
        await interaction.response.send_message(
            f"👑 Владелец комнаты теперь {участник.mention}.", ephemeral=True)

    # ────────────────────────────────────────────────────────────
    # Настройка (/j2c) — админ
    # ────────────────────────────────────────────────────────────
    j2c = app_commands.Group(name="j2c", description="Join-to-Create: личные голосовые комнаты")

    def _status_embed(self, guild: discord.Guild) -> discord.Embed:
        cfg = self.cfg(guild.id)
        lobby = guild.get_channel(int(cfg.get('lobby_id', 0) or 0))
        cat = guild.get_channel(int(cfg.get('category_id', 0) or 0))
        rooms = self._room_map(guild.id)
        e = discord.Embed(color=GOLD if cfg.get('enabled') and lobby else GRAY,
                          timestamp=datetime.now(timezone.utc))
        e.description = (
            "## 🔊 Join-to-Create\n"
            f"Система: **{'🟢 вкл' if cfg.get('enabled') else '🔴 выкл'}**\n"
            f"Лобби: {lobby.mention if lobby else '`не задано — /j2c lobby`'}\n"
            f"Категория: {cat.mention if cat else '`как у лобби`'}\n"
            f"Шаблон имени: `{cfg.get('name_template')}`\n"
            f"Лимит по умолч.: **{int(cfg.get('user_limit', 0)) or 'безлимит'}**\n"
            f"Активных комнат: **{len(rooms)}**\n{DIVIDER}")
        e.set_footer(text=f"{guild.name} · join-to-create")
        return e

    @j2c.command(name="status", description="Настройки Join-to-Create")
    @app_commands.checks.has_permissions(administrator=True)
    async def j_status(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self._status_embed(interaction.guild), ephemeral=True)

    @j2c.command(name="lobby", description="Задать канал-лобби (вход = своя комната)")
    @app_commands.describe(канал="Голосовой канал-лобби")
    @app_commands.checks.has_permissions(administrator=True)
    async def j_lobby(self, interaction: discord.Interaction, канал: discord.VoiceChannel):
        self.set_cfg(interaction.guild.id, 'lobby_id', канал.id)
        self.set_cfg(interaction.guild.id, 'enabled', True)
        await interaction.response.send_message(
            f"✅ Лобби: **{канал.name}** — заходите, система создаст личную комнату.", ephemeral=True)

    @j2c.command(name="category", description="Категория для новых комнат")
    @app_commands.describe(категория="Категория (или как у лобби)")
    @app_commands.checks.has_permissions(administrator=True)
    async def j_category(self, interaction: discord.Interaction, категория: discord.CategoryChannel):
        self.set_cfg(interaction.guild.id, 'category_id', категория.id)
        await interaction.response.send_message(f"✅ Категория комнат: **{категория.name}**", ephemeral=True)

    @j2c.command(name="template", description="Шаблон имени комнат ({user} = владелец)")
    @app_commands.describe(текст="Например: 🔊 {user}")
    @app_commands.checks.has_permissions(administrator=True)
    async def j_template(self, interaction: discord.Interaction, текст: str):
        self.set_cfg(interaction.guild.id, 'name_template', текст[:96] or '🔊 {user}')
        await interaction.response.send_message(f"✅ Шаблон: `{текст[:96]}`", ephemeral=True)

    @j2c.command(name="limit", description="Лимит мест по умолчанию (0 = безлимит)")
    @app_commands.describe(число="От 0 до 99")
    @app_commands.checks.has_permissions(administrator=True)
    async def j_limit(self, interaction: discord.Interaction, число: app_commands.Range[int, 0, 99]):
        self.set_cfg(interaction.guild.id, 'user_limit', число)
        await interaction.response.send_message(
            f"✅ Лимит по умолчанию: **{число or 'безлимит'}**", ephemeral=True)

    @j2c.command(name="on", description="Включить Join-to-Create")
    @app_commands.checks.has_permissions(administrator=True)
    async def j_on(self, interaction: discord.Interaction):
        self.set_cfg(interaction.guild.id, 'enabled', True)
        await interaction.response.send_message(embed=self._status_embed(interaction.guild), ephemeral=True)

    @j2c.command(name="off", description="Выключить Join-to-Create")
    @app_commands.checks.has_permissions(administrator=True)
    async def j_off(self, interaction: discord.Interaction):
        self.set_cfg(interaction.guild.id, 'enabled', False)
        await interaction.response.send_message(embed=self._status_embed(interaction.guild), ephemeral=True)


async def setup(bot):
    await bot.add_cog(JoinToCreate(bot))
    log.info("[J2C] Ког загружен")
