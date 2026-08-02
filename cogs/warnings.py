"""
Warnings Cog
Система предупреждений — database (SQLite)
Тёмная тема, русский язык
"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta

from cogs.embed_utils import mod_dm_embed, DIVIDER
from logger import get_logger
from db import GuildData

log = get_logger("warnings")


def load_warn_config(guild_id):
    """Загрузить конфигурацию наказаний (пока JSON, потом DB)"""
    import json, os
    f = f'data/warn_config_{guild_id}.json'
    if os.path.exists(f):
        with open(f, 'r', encoding='utf-8') as fp:
            return json.load(fp)
    return {'steps': []}


def duration_to_minutes(duration, unit):
    if unit == 'hour':
        return duration * 60
    if unit == 'day':
        return duration * 1440
    return duration


class warnings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData("warnings")

    def _get_warns(self, guild_id: int, user_id: int) -> list:
        return self.db.get(guild_id, str(user_id), [])

    def _save_warns(self, guild_id: int, user_id: int, warns: list):
        self.db.set(guild_id, str(user_id), warns)

    def _clear_warns(self, guild_id: int, user_id: int):
        self.db.set(guild_id, str(user_id), [])

    async def send_dm(self, user, embed):
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            pass

    async def apply_warn_punishment(self, guild, member, warn_count):
        """Автоматическое наказание по количеству предупреждений"""
        cfg = load_warn_config(str(guild.id))
        steps = cfg.get('steps', [])
        if not steps:
            return None

        matched = None
        for step in sorted(steps, key=lambda x: x['count']):
            if warn_count >= step['count']:
                matched = step

        if not matched:
            return None

        action = matched.get('action', 'mute')
        duration = matched.get('duration', 10)
        unit = matched.get('unit', 'minute')
        minutes = duration_to_minutes(duration, unit)

        try:
            if action in ('mute', 'timeout'):
                until = discord.utils.utcnow() + timedelta(minutes=minutes)
                await member.timeout(until, reason=f'Авто-наказание: {warn_count} предупреждений')
                return f'Мьют {duration} {unit}'
            elif action == 'kick':
                await member.kick(reason=f'Авто-наказание: {warn_count} предупреждений')
                return 'Кик'
            elif action == 'ban':
                await member.ban(reason=f'Авто-наказание: {warn_count} предупреждений')
                return 'Бан'
        except Exception as e:
            log.error(f'Ошибка авто-наказания: {e}')
        return None

    # ── /warn ────────────────────────────────────────────────────────────
    @app_commands.command(name="warn", description="Выдать предупреждение")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction, user: discord.Member, reason: str = None):
        guild = interaction.guild
        warns = self._get_warns(guild.id, user.id)
        warn_id = len(warns) + 1
        warns.append({
            "id": warn_id,
            "reason": reason or "Не указана",
            "mod": str(interaction.user),
            "mod_id": str(interaction.user.id),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        self._save_warns(guild.id, user.id, warns)
        total = len(warns)

        # DM пользователю
        import json, os
        dm_file = f'data/warn_dm_{guild.id}.json'
        custom_dm = None
        if os.path.exists(dm_file):
            with open(dm_file, 'r', encoding='utf-8') as df:
                dm_cfg = json.load(df)
            custom_dm = dm_cfg.get('message')

        if custom_dm:
            msg = custom_dm.replace('{user}', user.display_name).replace('{reason}', reason or 'Не указана').replace('{mod}', interaction.user.display_name).replace('{сервер}', guild.name)
            dm_embed = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
            dm_embed.description = (
                f"## Предупреждение #{warn_id}\n"
                f"{msg}\n\n"
                f"Сервер: **{guild.name}**\n"
                f"Модератор: **{interaction.user.display_name}**\n"
                f"Всего предупреждений: **{total}**\n"
                f"Причина: {reason or 'Не указана'}"
            )
            dm_embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
            dm_embed.set_footer(text=f"{guild.name}")
            await self.send_dm(user, dm_embed)
        else:
            await self.send_dm(user, mod_dm_embed("warn", guild, interaction.user, reason))

        # Авто-наказание
        punishment_result = await self.apply_warn_punishment(guild, user, total)

        # Ответ модератору
        e = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
        desc = (
            f"## Предупреждение выдано\n"
            f"**{user.display_name}** · `{user.id}`\n\n"
            f"Предупреждение: **#{warn_id}**\n"
            f"Всего: **{total}**\n"
            f"Причина: {reason or 'Не указана'}\n"
            f"Модератор: {interaction.user.mention}"
        )
        if punishment_result:
            desc += f"\nАвто-наказание: **{punishment_result}**"
        desc += f"\n\n{DIVIDER}"
        e.description = desc
        e.set_footer(text=f"{guild.name}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ── /warnings ────────────────────────────────────────────────────────
    @app_commands.command(name="warnings", description="Предупреждения пользователя")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings_list(self, interaction, user: discord.Member):
        warns = self._get_warns(interaction.guild.id, user.id)

        e = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))

        if not warns:
            e.description = (
                f"## Предупреждения\n"
                f"**{user.display_name}** · `{user.id}`\n\n"
                f"Предупреждений нет.\n\n"
                f"{DIVIDER}"
            )
        else:
            desc = (
                f"## Предупреждения\n"
                f"**{user.display_name}** · `{user.id}`\n"
                f"Всего: **{len(warns)}**\n\n"
            )
            for w in warns[-8:]:
                desc += f"**#{w['id']}** — {w['reason']}\n-# {w['timestamp'][:10]} · {w.get('mod', '?')}\n\n"
            desc += DIVIDER
            e.description = desc

        e.set_thumbnail(url=user.display_avatar.url)
        e.set_footer(text=f"{interaction.guild.name}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ── /clearwarns ──────────────────────────────────────────────────────
    @app_commands.command(name="clearwarns", description="Очистить все предупреждения")
    @app_commands.checks.has_permissions(administrator=True)
    async def clearwarns(self, interaction, user: discord.Member):
        warns = self._get_warns(interaction.guild.id, user.id)
        count = len(warns)
        self._clear_warns(interaction.guild.id, user.id)

        e = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
        e.description = (
            f"## Предупреждения очищены\n"
            f"**{user.display_name}** · `{user.id}`\n\n"
            f"Удалено: **{count}** предупреждений\n"
            f"Модератор: {interaction.user.mention}\n\n"
            f"{DIVIDER}"
        )
        e.set_footer(text=f"{interaction.guild.name}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ── /unwarn ─────────────────────────────────────────────────────────
    @app_commands.command(name="unwarn", description="Снять последнее предупреждение у пользователя")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unwarn(self, interaction, user: discord.Member):
        """Снять последнее предупреждение у пользователя"""
        warns = self._get_warns(interaction.guild.id, user.id)
        if not warns:
            e = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
            e.description = (
                f"## Снятие предупреждения\n"
                f"**{user.display_name}** · `{user.id}`\n\n"
                f"У пользователя нет предупреждений.\n\n"
                f"{DIVIDER}"
            )
            e.set_footer(text=f"{interaction.guild.name}")
            await interaction.response.send_message(embed=e, ephemeral=True)
            return

        removed = warns.pop()
        self._save_warns(interaction.guild.id, user.id, warns)
        total = len(warns)

        e = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
        e.description = (
            f"## Снятие предупреждения\n"
            f"**{user.display_name}** · `{user.id}`\n\n"
            f"Снято: **#{removed.get('id')}** — {removed.get('reason', 'Не указана')}\n"
            f"Осталось: **{total}**\n"
            f"Модератор: {interaction.user.mention}\n\n"
            f"{DIVIDER}"
        )
        e.set_thumbnail(url=user.display_avatar.url)
        e.set_footer(text=f"{interaction.guild.name}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ── add_warning (для AI-modератора, без interaction) ─────────────────
    async def add_warning(self, user: discord.Member, moderator: discord.Member, reason: str = None):
        """Добавить предупреждение без interaction"""
        guild = user.guild
        warns = self._get_warns(guild.id, user.id)
        warn_id = len(warns) + 1
        warns.append({
            "id": warn_id,
            "reason": reason or "Не указана",
            "mod": str(moderator),
            "mod_id": str(moderator.id),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        self._save_warns(guild.id, user.id, warns)
        total = len(warns)

        # DM
        try:
            dm_embed = discord.Embed(color=discord.Color.dark_grey(), timestamp=datetime.now(timezone.utc))
            dm_embed.description = (
                f"## Предупреждение #{warn_id}\n"
                f"**Сервер:** {guild.name}\n"
                f"**Причина:** {reason or 'Не указана'}\n"
                f"**Модератор:** {moderator.display_name}\n"
                f"**Всего предупреждений:** {total}"
            )
            if guild.icon:
                dm_embed.set_footer(text=f"{guild.name}", icon_url=guild.icon.url)
            await user.send(embed=dm_embed)
        except Exception:
            pass

        await self.apply_warn_punishment(guild, user, total)
        return warn_id, total


async def setup(bot):
    await bot.add_cog(warnings(bot))
    log.info("Warnings загружен (database)")
