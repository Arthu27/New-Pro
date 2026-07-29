import discord
from discord.ext import commands
from discord import app_commands
import json, os
from datetime import datetime, timezone, timedelta
from cogs.embed_utils import mod_dm_embed, DIVIDER

WARNINGS_FILE = "data/warnings.json"

def load_warnings():
    os.makedirs("data", exist_ok=True)
    if os.path.exists(WARNINGS_FILE):
        with open(WARNINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_warnings(data):
    with open(WARNINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_warn_config(guild_id):
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


class Warnings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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
                return f'Мут {duration} {unit}'
            elif action == 'kick':
                await member.kick(reason=f'Авто-наказание: {warn_count} предупреждений')
                return 'Кик'
            elif action == 'ban':
                await member.ban(reason=f'Авто-наказание: {warn_count} предупреждений')
                return 'Бан'
        except Exception as e:
            print(f'[WARN] Ошибка авто-наказания: {e}')
        return None

    # ─── /warn ─────────────────────────────────────────────────────────

    @app_commands.command(name="warn", description="Выдать предупреждение")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction, user: discord.Member, причина: str = None):
        guild = interaction.guild
        data = load_warnings()
        gid, uid = str(guild.id), str(user.id)
        data.setdefault(gid, {}).setdefault(uid, [])
        warn_id = len(data[gid][uid]) + 1
        data[gid][uid].append({
            "id": warn_id,
            "reason": причина or "Не указана",
            "mod": str(interaction.user),
            "mod_id": str(interaction.user.id),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        save_warnings(data)
        total = len(data[gid][uid])

        # DM пользователю
        dm_file = f'data/warn_dm_{guild.id}.json'
        custom_dm = None
        if os.path.exists(dm_file):
            with open(dm_file, 'r', encoding='utf-8') as df:
                dm_cfg = json.load(df)
            custom_dm = dm_cfg.get('message')

        if custom_dm:
            msg = custom_dm.replace('{user}', user.display_name).replace('{reason}', причина or 'Не указана').replace('{mod}', interaction.user.display_name).replace('{server}', guild.name)
            dm_embed = discord.Embed(color=0xFF6B6B, timestamp=datetime.now(timezone.utc))
            dm_embed.description = (
                f"## Предупреждение #{warn_id}\n"
                f"{msg}\n\n"
                f"Сервер: **{guild.name}**\n"
                f"Модератор: **{interaction.user.display_name}**\n"
                f"Всего предупреждений: **{total}**\n"
                f"Причина: {причина or 'Не указана'}"
            )
            dm_embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
            dm_embed.set_footer(text=f"{guild.name}")
            await self.send_dm(user, dm_embed)
        else:
            await self.send_dm(user, mod_dm_embed("warn", guild, interaction.user, причина))

        # Авто-наказание
        punishment_result = await self.apply_warn_punishment(guild, user, total)

        # Embed подтверждения для модератора
        e = discord.Embed(color=0xFF6B6B, timestamp=datetime.now(timezone.utc))
        desc = (
            f"## Предупреждение выдано\n"
            f"**{user.display_name}** · `{user.id}`\n\n"
            f"Предупреждение: **#{warn_id}**\n"
            f"Всего: **{total}**\n"
            f"Причина: {причина or 'Не указана'}\n"
            f"Модератор: {interaction.user.mention}"
        )
        if punishment_result:
            desc += f"\nАвто-наказание: **{punishment_result}**"
        desc += f"\n\n{DIVIDER}"
        e.description = desc
        e.set_footer(text=f"{guild.name}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ─── /warnings ─────────────────────────────────────────────────────

    @app_commands.command(name="warnings", description="Список предупреждений пользователя")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings_list(self, interaction, user: discord.Member):
        data = load_warnings()
        gid, uid = str(interaction.guild.id), str(user.id)
        warns = data.get(gid, {}).get(uid, [])

        e = discord.Embed(color=0xFF6B6B, timestamp=datetime.now(timezone.utc))

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

    # ─── /clearwarns ───────────────────────────────────────────────────

    @app_commands.command(name="clearwarns", description="Очистить предупреждения пользователя")
    @app_commands.checks.has_permissions(administrator=True)
    async def clearwarns(self, interaction, user: discord.Member):
        data = load_warnings()
        gid, uid = str(interaction.guild.id), str(user.id)
        count = len(data.get(gid, {}).get(uid, []))
        data.setdefault(gid, {})[uid] = []
        save_warnings(data)

        e = discord.Embed(color=0x2ECC71, timestamp=datetime.now(timezone.utc))
        e.description = (
            f"## Предупреждения очищены\n"
            f"**{user.display_name}** · `{user.id}`\n\n"
            f"Удалено: **{count}** предупреждений\n"
            f"Модератор: {interaction.user.mention}\n\n"
            f"{DIVIDER}"
        )
        e.set_footer(text=f"{interaction.guild.name}")
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Warnings(bot))
