import discord
from discord.ext import commands
from discord import app_commands
from collections import defaultdict
import time
import json
import os

class AntiRaid(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.join_tracker = defaultdict(list)
        self.config_file = "data/antiraid.json"
        self.load_config()

    def load_config(self):
        os.makedirs("data", exist_ok=True)
        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as f:
                self.config = json.load(f)
        else:
            self.config = {}

    def save_config(self):
        with open(self.config_file, "w") as f:
            json.dump(self.config, f, indent=2)

    def is_enabled(self, guild_id):
        return self.config.get(str(guild_id), {}).get("enabled", False)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not self.is_enabled(member.guild.id):
            return

        guild_id = member.guild.id
        current_time = time.time()
        
        # Последний 10 saniyedeki katılımları tut
        self.join_tracker[guild_id] = [t for t in self.join_tracker[guild_id] if current_time - t < 10]
        self.join_tracker[guild_id].append(current_time)

        # Alt hesap kontroleü
        account_age = (discord.utils.utcnow() - member.created_at).days
        if account_age < 7:
            try:
                await member.kick(reason=f"Alt hesap tespiti ({account_age} деньlük hesap)")
                e = discord.Embed(title="🛡️ Alt Hesap Engellendi", color=discord.Color.red())
                e.add_field(name="Пользователь", value=f"{member} (`{member.id}`)")
                e.add_field(name="Hesap Yaşı", value=f"{account_age} день")
                
                log_ch = discord.utils.get(member.guild.text_channels, name="mod-log")
                if log_ch:
                    await log_ch.send(embed=e)
                return
            except:
                pass

        # Raid kontroleü (10 saniyede 5+ katılım)
        if len(self.join_tracker[guild_id]) >= 5:
            try:
                # Lockdown modu
                for channel in member.guild.text_channels:
                    await channel.set_permissions(member.guild.default_role, send_messages=False)
                
                e = discord.Embed(title="🚨 RAID ALGILANDI", color=discord.Color.dark_red())
                e.description = "Сервер otomatik olarak kilitlendi!\n`/unlock-server` ile kilidi açabilirsiniz."
                e.add_field(name="Katılım Sayısı", value=f"{len(self.join_tracker[guild_id])} kişi (10 saniye)")
                
                log_ch = discord.utils.get(member.guild.text_channels, name="mod-log")
                if log_ch:
                    await log_ch.send("@everyone", embed=e)
                
                self.join_tracker[guild_id].clear()
            except:
                pass

    @app_commands.command(name="antiraid", description="Включить/выключить анти-рейд систему")
    @app_commands.checks.has_permissions(administrator=True)
    async def antiraid(self, interaction: discord.Interaction, status: bool):
        guild_id = str(interaction.guild.id)
        if guild_id not in self.config:
            self.config[guild_id] = {}
        self.config[guild_id]["enabled"] = status
        self.save_config()
        
        e = discord.Embed(
            title="🛡️ ANTI-RAID SİSTEMİ",
            description=f"╔═══════════════════════════╗\n║  Система {'активна' if status else 'неактивна'}!  ║\n╚═══════════════════════════╝",
            color=0x2ECC71 if status else 0xE74C3C
        )
        e.add_field(name="📊 Статус", value=f"```diff\n{'+ Открыт' if status else '- Закрыт'}\n```", inline=False)
        e.add_field(name="🔍 Özellikler", value="```yaml\n- Alt hesap kontroleü (7 день)\n- Raid algılama (10sn/5+ участник)\n- Otomatik lockdown\n```", inline=False)
        e.set_footer(text="Anti-Raid Sistemi")
        
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="unlock-server", description="Разблокировать server")
    @app_commands.checks.has_permissions(administrator=True)
    async def unlock_server(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        for channel in interaction.guild.text_channels:
            await channel.set_permissions(interaction.guild.default_role, send_messages=None)
        await interaction.followup.send("🔓 Сервер kilidi açıldı.", ephemeral=True)

    @app_commands.command(name="massban", description="Toplu ban (ID listesi)")
    @app_commands.checks.has_permissions(administrator=True)
    async def massban(self, interaction: discord.Interaction, ids: str, reason: str = "Toplu ban"):
        await interaction.response.defer(ephemeral=True)
        id_list = [int(x.strip()) for x in ids.split(",")]
        banned = 0
        for user_id in id_list:
            try:
                user = await self.bot.fetch_user(user_id)
                await interaction.guild.ban(user, reason=reason)
                banned += 1
            except:
                pass
        await interaction.followup.send(f"✅ {banned}/{len(id_list)} user banlandı.", ephemeral=True)

    @app_commands.command(name="masskick", description="Массовое исключение ботов")
    @app_commands.checks.has_permissions(administrator=True)
    async def masskick(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        kicked = 0
        for member in interaction.guild.members:
            if member.bot and member != self.bot.user:
                try:
                    await member.kick(reason="Бот temizliği")
                    kicked += 1
                except:
                    pass
        await interaction.followup.send(f"✅ {kicked} bot atıldı.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AntiRaid(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
