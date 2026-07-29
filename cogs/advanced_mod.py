import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime
from cogs.embed_utils import _divider, now_ts, error_embed

class AdvancedMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_file = "data/mod_data.json"
        self.load_data()

    def load_data(self):
        os.makedirs("data", exist_ok=True)
        if os.path.exists(self.data_file):
            with open(self.data_file, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        else:
            self.data = {"case": {}, "notes": {}, "watchlist": {}}

    def save_data(self):
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def add_case(self, guild_id, user_id, mod_id, action, reason):
        guild_id = str(guild_id)
        if guild_id not in self.data["case"]:
            self.data["case"][guild_id] = []
        case_id = len(self.data["case"][guild_id]) + 1
        self.data["case"][guild_id].append({
            "id": case_id, "user_id": user_id, "mod_id": mod_id,
            "action": action, "reason": reason,
            "timestamp": datetime.utcnow().isoformat()
        })
        self.save_data()
        return case_id

    @app_commands.command(name="history", description="Показать история moderasyonu пользователь")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def history(self, interaction: discord.Interaction, user: discord.Member):
        guild_id = str(interaction.guild.id)
        case = self.data["case"].get(guild_id, [])
        user_case = [c for c in case if str(c["user_id"]) == str(user.id)]

        if not user_case:
            e = discord.Embed(title="✅  Temiz История", color=0x2ECC71, timestamp=datetime.utcnow())
            e.description = (
                f"```ansi\n\u001b[1;32m✔ TEMİZ ЗАПИСЬ\u001b[0m\n```\n{_divider()}\n\n"
                f"{user.mention} для каждый bir moderasyon kaydı не найдено.\n\n{_divider()}"
            )
            e.set_thumbnail(url=user.display_avatar.url)
            e.add_field(name="👤 Пользователь", value=f"`{user.name}` • `{user.id}`", inline=True)
            e.add_field(name="📊 Состояние", value="```diff\n+ Hiç mod действие yok\n```", inline=True)
            e.set_footer(text=f"Aether Moderasyon • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.send_message(embed=e, ephemeral=True)
            return

        action_emojis = {"ban": "🔨", "kick": "👢", "timeout": "🔇", "warn": "⚠️", "unban": "🔓"}
        action_colors = {"ban": "31", "kick": "33", "timeout": "33", "warn": "33", "unban": "32"}

        e = discord.Embed(title=f"📋  Moderasyon История", color=0xE74C3C, timestamp=datetime.utcnow())
        e.description = (
            f"```ansi\n\u001b[1;31m⚠ MOD ЗАПИСЬ\u001b[0m\n```\n{_divider()}"
        )
        e.set_thumbnail(url=user.display_avatar.url)
        e.set_author(name=f"{user.display_name} — История Запись", icon_url=user.display_avatar.url)

        for case in user_case[-8:]:
            act = case['action'].lower()
            emoji = action_emojis.get(act, "📌")
            color_code = action_colors.get(act, "37")
            e.add_field(
                name=f"{emoji} Case #{case['id']} — {case['action'].upper()}",
                value=(
                    f"```ansi\n\u001b[1;{color_code}m{case['action'].upper()}\u001b[0m\n```"
                    f"📝 {case['reason']}\n"
                    f"🕐 `{case['timestamp'][:10]}`"
                ),
                inline=False
            )

        e.add_field(
            name="📊 Сводка",
            value=f"```Всего {len(user_case)} moderasyon действие```",
            inline=False
        )
        e.set_footer(
            text=f"Aether Moderasyon • {interaction.guild.name}",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="case", description="Показать konkretnoe delo")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def case(self, interaction: discord.Interaction, case_id: int):
        guild_id = str(interaction.guild.id)
        case = self.data["case"].get(guild_id, [])
        case = next((c for c in case if c["id"] == case_id), None)

        if not case:
            await interaction.response.send_message(embed=error_embed(f"Case #{case_id} не найдено."), ephemeral=True)
            return

        try:
            user = await self.bot.fetch_user(case["user_id"])
            mod = await self.bot.fetch_user(case["mod_id"])
        except:
            user = mod = None

        action_emojis = {"ban": "🔨", "kick": "👢", "timeout": "🔇", "warn": "⚠️"}
        emoji = action_emojis.get(case["action"].lower(), "📌")

        e = discord.Embed(title=f"{emoji}  Case #{case_id} Детали", color=0x3498DB, timestamp=datetime.utcnow())
        e.description = (
            f"```ansi\n\u001b[1;34m📋 CASE ДЕТАЛИ\u001b[0m\n```\n{_divider()}"
        )
        if user:
            e.set_thumbnail(url=user.display_avatar.url)
        e.add_field(name="👤 Цель", value=f"`{user}` • `{case['user_id']}`" if user else f"`{case['user_id']}`", inline=True)
        e.add_field(name="👮 Модератор", value=f"`{mod}`" if mod else f"`{case['mod_id']}`", inline=True)
        e.add_field(name="⚡ Действие", value=f"```{case['action'].upper()}```", inline=True)
        e.add_field(name="📝 Причина", value=f"```{case['reason']}```", inline=False)
        e.add_field(name="🕐 Дата", value=f"`{case['timestamp'][:19].replace('T', ' ')}`", inline=False)
        e.set_footer(
            text=f"Aether Moderasyon • {interaction.guild.name}",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="note", description="Добавлено notu пользователю")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def note(self, interaction: discord.Interaction, user: discord.Member, note: str):
        guild_id = str(interaction.guild.id)
        user_id = str(user.id)
        if guild_id not in self.data["notes"]:
            self.data["notes"][guild_id] = {}
        if user_id not in self.data["notes"][guild_id]:
            self.data["notes"][guild_id][user_id] = []
        self.data["notes"][guild_id][user_id].append({
            "note": note, "mod": str(interaction.user),
            "timestamp": datetime.utcnow().isoformat()
        })
        self.save_data()

        e = discord.Embed(title="📝  Not Добавлено", color=0xF1C40F, timestamp=datetime.utcnow())
        e.description = (
            f"```ansi\n\u001b[1;33m✔ NOT СОХРАНЕНО\u001b[0m\n```\n{_divider()}"
        )
        e.set_thumbnail(url=user.display_avatar.url)
        e.add_field(name="👤 Пользователь", value=f"{user.mention}\n`{user.id}`", inline=True)
        e.add_field(name="👮 Добавлено", value=interaction.user.mention, inline=True)
        e.add_field(name="📝 Not", value=f"```{note}```", inline=False)
        e.add_field(name="🕐 Дата", value=f"<t:{now_ts()}:F>", inline=False)
        e.set_footer(text=f"Aether Moderasyon • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="notes", description="Показать notlar пользователь")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def notes(self, interaction: discord.Interaction, user: discord.Member):
        guild_id = str(interaction.guild.id)
        user_id = str(user.id)
        notes = self.data["notes"].get(guild_id, {}).get(user_id, [])

        if not notes:
            await interaction.response.send_message(
                embed=discord.Embed(description=f"📝 {user.mention} для запись not yok.", color=0x3498DB),
                ephemeral=True
            )
            return

        e = discord.Embed(title=f"📝  {user.display_name} — Notlar", color=0xF1C40F, timestamp=datetime.utcnow())
        e.description = f"```ansi\n\u001b[1;33m📋 ЗАПИСЬ NOTLAR\u001b[0m\n```\n{_divider()}"
        e.set_thumbnail(url=user.display_avatar.url)
        for i, n in enumerate(notes, 1):
            e.add_field(
                name=f"📌 Not #{i} — `{n['timestamp'][:10]}`",
                value=f"```{n['note']}```*— {n['mod']}*",
                inline=False
            )
        e.set_footer(text=f"Всего {len(notes)} not • Aether Moderasyon", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="watchlist", description="Добавлено/удалить den spiska наблюдение")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def watchlist(self, interaction: discord.Interaction, user: discord.Member, reason: str = None):
        guild_id = str(interaction.guild.id)
        user_id = str(user.id)
        if guild_id not in self.data["watchlist"]:
            self.data["watchlist"][guild_id] = {}

        if user_id in self.data["watchlist"][guild_id]:
            del self.data["watchlist"][guild_id][user_id]
            self.save_data()
            e = discord.Embed(title="👁️  İzleme Listesinden Удалить", color=0x2ECC71, timestamp=datetime.utcnow())
            e.description = f"```ansi\n\u001b[1;32m✔ LİSTEDEN УДАЛИТЬ\u001b[0m\n```\n{_divider()}"
            e.set_thumbnail(url=user.display_avatar.url)
            e.add_field(name="👤 Пользователь", value=f"{user.mention}\n`{user.id}`", inline=True)
            e.add_field(name="🕐 Дата", value=f"<t:{now_ts()}:R>", inline=True)
            e.set_footer(text=f"Aether Moderasyon • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        else:
            self.data["watchlist"][guild_id][user_id] = {
                "reason": reason or "Не belirtildi",
                "added_by": str(interaction.user),
                "timestamp": datetime.utcnow().isoformat()
            }
            self.save_data()
            e = discord.Embed(title="👁️  İzleme Listesine Добавлено", color=0xF39C12, timestamp=datetime.utcnow())
            e.description = (
                f"```ansi\n\u001b[1;33m⚠ İZLEMEYE ALINDI\u001b[0m\n```\n{_divider()}\n\n"
                f"{user.mention} теперь liste наблюдение. Hareketleri takip edilecek.\n\n{_divider()}"
            )
            e.set_thumbnail(url=user.display_avatar.url)
            e.add_field(name="👤 Пользователь", value=f"{user.mention}\n`{user.id}`", inline=True)
            e.add_field(name="👮 Добавлено", value=interaction.user.mention, inline=True)
            e.add_field(name="📝 Причина", value=f"```{reason or 'Не belirtildi'}```", inline=False)
            e.add_field(name="🕐 Дата", value=f"<t:{now_ts()}:F>", inline=False)
            e.set_footer(text=f"Aether Moderasyon • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="watchlist-show", description="Показать liste наблюдение")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def watchlist_show(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        watchlist = self.data["watchlist"].get(guild_id, {})

        if not watchlist:
            await interaction.response.send_message(
                embed=discord.Embed(description="👁️ Liste наблюдение şu an пусто.", color=0x3498DB),
                ephemeral=True
            )
            return

        e = discord.Embed(title="👁️  İzleme список", color=0xF39C12, timestamp=datetime.utcnow())
        e.description = (
            f"```ansi\n\u001b[1;33m⚠ İZLEMEDEKİ ПОЛЬЗОВАТЕЛИ\u001b[0m\n```\n{_divider()}"
        )
        for user_id, data in watchlist.items():
            try:
                user = await self.bot.fetch_user(int(user_id))
                name = str(user)
                avatar = user.display_avatar.url
            except:
                name, avatar = user_id, None
            e.add_field(
                name=f"👤 {name}",
                value=f"📝 `{data['reason']}`\n👮 *{data['added_by']}*\n🕐 `{data['timestamp'][:10]}`",
                inline=False
            )
        e.set_footer(
            text=f"Всего {len(watchlist)} user • Aether Moderasyon",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="banlist", description="Показать список забаненных пользователей")
    @app_commands.checks.has_permissions(ban_members=True)
    async def banlist(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        bans = [entry async for entry in interaction.guild.bans(limit=50)]

        if not bans:
            await interaction.followup.send(
                embed=discord.Embed(description="✅ Yasaklanmış user yok.", color=0x2ECC71),
                ephemeral=True
            )
            return

        e = discord.Embed(title=f"🔨  Ban список", color=0xE74C3C, timestamp=datetime.utcnow())
        e.description = (
            f"```ansi\n\u001b[1;31m🔨 BANLI ПОЛЬЗОВАТЕЛИ\u001b[0m\n```\n{_divider()}"
        )
        for entry in bans[:20]:
            e.add_field(
                name=f"👤 {entry.user}",
                value=f"`{entry.user.id}`\n📝 *{entry.reason or 'Причина не belirtildi'}*",
                inline=False
            )
        e.set_footer(
            text=f"Всего {len(bans)} ban • Aether Moderasyon",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="massrole", description="Массовая выдача/удаление роли")
    @app_commands.checks.has_permissions(administrator=True)
    async def massrole(self, interaction: discord.Interaction, role: discord.Role, action: str):
        await interaction.response.defer(ephemeral=True)
        count = 0
        if action.lower() == "ver":
            for member in interaction.guild.members:
                if role not in member.roles and not member.bot:
                    try:
                        await member.add_roles(role)
                        count += 1
                    except:
                        pass
            e = discord.Embed(title="🎭  Toplu Роли Verildi", color=0x2ECC71, timestamp=datetime.utcnow())
            e.description = f"```ansi\n\u001b[1;32m✔ TOPLU РОЛЬ\u001b[0m\n```\n{_divider()}"
            e.add_field(name="🎭 Роль", value=role.mention, inline=True)
            e.add_field(name="👥 Затронуто", value=f"```{count} человек```", inline=True)
        elif action.lower() == "al":
            for member in interaction.guild.members:
                if role in member.roles:
                    try:
                        await member.remove_roles(role)
                        count += 1
                    except:
                        pass
            e = discord.Embed(title="🎭  Toplu Роли Alındı", color=0xE74C3C, timestamp=datetime.utcnow())
            e.description = f"```ansi\n\u001b[1;31m✔ TOPLU РОЛЬ ALINDI\u001b[0m\n```\n{_divider()}"
            e.add_field(name="🎭 Роль", value=role.mention, inline=True)
            e.add_field(name="👥 Затронуто", value=f"```{count} человек```", inline=True)
        else:
            await interaction.followup.send("❌ Неверный действие! `ver` или `al` использовать.", ephemeral=True)
            return
        e.set_footer(text=f"Aether Moderasyon • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.followup.send(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdvancedMod(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
