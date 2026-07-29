import discord
from discord.ext import commands
from discord import app_commands
import json, os
from datetime import datetime, timezone, timedelta
from cogs.embed_utils import _divider, now_ts, mod_dm_embed

WARNINGS_FILE = "data/warnings.json"
WARN_CFG_FILE = "data/warn_config_{guild_id}.json"
DIV = _divider()

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
        """Warning sayısına göre otomatik ceza uygula."""
        cfg = load_warn_config(str(guild.id))
        steps = cfg.get('steps', [])
        if not steps:
            return None

        # Tam eşleşen adımı найти
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
                await member.timeout(until, reason=f'Otomatik ceza: {warn_count} предупреждений')
                return f'🔇 {duration} {unit} timeout'
            elif action == 'kick':
                await member.kick(reason=f'Otomatik ceza: {warn_count} предупреждений')
                return '👢 Кик'
            elif action == 'ban':
                await member.ban(reason=f'Otomatik ceza: {warn_count} предупреждений')
                return '🔨 Бан'
        except Exception as e:
            print(f'[WARN] Otomatik ceza Ошибкаsı: {e}')
        return None

    @app_commands.command(name="warn", description="Выдать предупреждение")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, user: discord.Member, причина: str = None):
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

        # Warning DM — özel message varsa onu kullan
        dm_file = f'data/warn_dm_{guild.id}.json'
        custom_dm = None
        if os.path.exists(dm_file):
            with open(dm_file, 'r', encoding='utf-8') as df:
                dm_cfg = json.load(df)
            custom_dm = dm_cfg.get('message')

        if custom_dm:
            msg = custom_dm.replace('{user}', user.display_name).replace('{reason}', причина or 'Не указана').replace('{mod}', interaction.user.display_name).replace('{server}', guild.name)
            dm_embed = discord.Embed(
                title="⚠️  Вы получили предупреждение",
                color=0xFF6B6B,
                timestamp=datetime.now(timezone.utc)
            )
            dm_embed.description = (
                f"```ansi\n\u001b[1;31m⚠ UYARI #{warn_id}\u001b[0m\n```\n"
                f"{DIV}\n\n{msg}\n\n{DIV}"
            )
            dm_embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
            dm_embed.add_field(name="🏰 Сервер", value=f"```{guild.name}```", inline=True)
            dm_embed.add_field(name="👮 Модератор", value=f"```{interaction.user.display_name}```", inline=True)
            dm_embed.add_field(name="📊 Всего предупреждений", value=f"```{total} предупреждений```", inline=True)
            dm_embed.add_field(name="📝 Причина", value=f"```{причина or 'Не указана'}```", inline=False)
            dm_embed.set_footer(text=f"Aether Moderasyon • {guild.name}", icon_url=guild.icon.url if guild.icon else None)
            await self.send_dm(user, dm_embed)
        else:
            await self.send_dm(user, mod_dm_embed("warn", guild, interaction.user, причина))

        # Otomatik ceza kontroleü
        punishment_result = await self.apply_warn_punishment(guild, user, total)

        # Модераторe onay embed
        e = discord.Embed(
            title="⚠️  Warning Verildi",
            color=0xFF6B6B,
            timestamp=datetime.now(timezone.utc)
        )
        e.description = (
            f"```ansi\n\u001b[1;31m✔ UYARI KAYDEDİLDİ\u001b[0m\n```\n"
            f"{DIV}"
        )
        e.set_thumbnail(url=user.display_avatar.url)
        e.add_field(name="👤 Пользователь", value=f"{user.mention}\n`{user.id}`", inline=True)
        e.add_field(name="🆔 Warning No", value=f"```#{warn_id}```", inline=True)
        e.add_field(name="📊 Всего", value=f"```{total} предупреждений```", inline=True)
        e.add_field(name="📝 Причина", value=f"```{причина or 'Не указана'}```", inline=False)
        if punishment_result:
            e.add_field(name="⚡ Otomatik Наказание", value=f"```{punishment_result}```", inline=False)
        e.add_field(name="🕐 Дата", value=f"<t:{now_ts()}:F>", inline=False)
        e.set_footer(text=f"Aether Moderasyon • {guild.name}", icon_url=guild.icon.url if guild.icon else None)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="warnings", description="Пользователя предупрежденийlarını listeler")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings_list(self, interaction: discord.Interaction, user: discord.Member):
        data = load_warnings()
        gid, uid = str(interaction.guild.id), str(user.id)
        warns = data.get(gid, {}).get(uid, [])

        e = discord.Embed(
            title=f"📋  {user.display_name} — Warning Geçmişi",
            color=0xFF6B6B,
            timestamp=datetime.now(timezone.utc)
        )
        e.set_thumbnail(url=user.display_avatar.url)
        e.description = f"```ansi\n\u001b[1;31m{'⚠ ' + str(len(warns)) + ' UYARI' if warns else '✅ TEMİZ KAYIT'}\u001b[0m\n```\n{DIV}"

        if not warns:
            e.add_field(name="✅ Статус", value="```Bu usernın hiç предупрежденийsı yok.```", inline=False)
        else:
            for w in warns[-8:]:
                e.add_field(
                    name=f"⚠️ Warning #{w['id']} — `{w['timestamp'][:10]}`",
                    value=f"📝 {w['reason']}\n👮 *{w.get('mod', '?')}*",
                    inline=False
                )
        e.set_footer(text=f"Всего {len(warns)} предупреждений • Aether Moderasyon", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="clearwarns", description="Пользователя предупрежденийlarını clearr")
    @app_commands.checks.has_permissions(administrator=True)
    async def clearwarns(self, interaction: discord.Interaction, user: discord.Member):
        data = load_warnings()
        gid, uid = str(interaction.guild.id), str(user.id)
        count = len(data.get(gid, {}).get(uid, []))
        data.setdefault(gid, {})[uid] = []
        save_warnings(data)

        e = discord.Embed(
            title="🧹  Warninglar Очиститьndi",
            color=0x2ECC71,
            timestamp=datetime.now(timezone.utc)
        )
        e.description = f"```ansi\n\u001b[1;32m✔ UYARILAR SİLİNDİ\u001b[0m\n```\n{DIV}"
        e.set_thumbnail(url=user.display_avatar.url)
        e.add_field(name="👤 Пользователь", value=f"{user.mention}", inline=True)
        e.add_field(name="🗑️ Удалитьinen", value=f"```{count} предупреждений```", inline=True)
        e.set_footer(text=f"Aether Moderasyon • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Warnings(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])