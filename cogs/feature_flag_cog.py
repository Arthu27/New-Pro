"""
Feature Flags Cog
Feature flags cog'u
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from services.feature_flags import feature_flag_manager, feature_flag_rollout, feature_flag_analytics

from logger import get_logger
log = get_logger("feature_flag_cog")



class FeatureFlagCog(commands.Cog):
    """Feature flags cog'u"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name='flag-list', description='Tüm feature flag\'leri görüntüle')
    async def flag_list(self, interaction: discord.Interaction):
        """Tüm feature flag'leri görüntüle"""
        # Flag'ler al
        flags = feature_flag_manager.get_all_flags()
        
        if not flags:
            await interaction.response.send_message(
                " Feature flag bulunamadı!",
                ephemeral=True
            )
            return
        
        # Embed oluştur
        embed = discord.Embed(
            title=" Feature Flags",
            description=f"Toplam {len(flags)} flag",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        
        # Flag listesi
        for flag in flags[:15]:
            enabled_text = " Enabled" if flag.enabled else " Disabled"
            rollout_text = f"{flag.rollout_percentage}%" if flag.rollout_percentage < 100 else "Full"
            
            embed.add_field(
                name=f"{flag.flag_key}",
                value=f"{flag.name}\n{enabled_text} | Rollout: {rollout_text}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name='flag-info', description='Feature flag bilgilerini görüntüle')
    @app_commands.describe(flag_key='Flag key')
    async def flag_info(self, interaction: discord.Interaction, flag_key: str):
        """Feature flag bilgilerini görüntüle"""
        # Flag al
        flag = feature_flag_manager.get_flag(flag_key)
        
        if not flag:
            await interaction.response.send_message(
                " Feature flag bulunamadı!",
                ephemeral=True
            )
            return
        
        # Embed oluştur
        embed = discord.Embed(
            title=f" Feature Flag: {flag.flag_key}",
            description=flag.name,
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        
        enabled_text = " Enabled" if flag.enabled else " Disabled"
        embed.add_field(name="Status", value=enabled_text, inline=True)
        embed.add_field(name="Rollout", value=f"{flag.rollout_percentage}%", inline=True)
        
        # Hedefleme kuralları
        if flag.targeting_rules:
            rules_text = "\n".join([
                f"• {rule['type']}: {rule['value']}"
                for rule in flag.targeting_rules[:5]
            ])
            embed.add_field(name="Targeting Rules", value=rules_text, inline=False)
        
        # Varyantlar
        if flag.variants:
            variants_text = "\n".join([
                f"• {variant_key}: {'' if enabled else ''}"
                for variant_key, enabled in flag.variants.items()
            ])
            embed.add_field(name="Variants", value=variants_text, inline=False)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name='flag-enable', description='Feature flag etkinleştir')
    @app_commands.describe(flag_key='Flag key')
    @app_commands.checks.has_permissions(administrator=True)
    async def flag_enable(self, interaction: discord.Interaction, flag_key: str):
        """Feature flag etkinleştir"""
        # Flag etkinleştir
        success = feature_flag_manager.enable_flag(flag_key)
        
        if not success:
            await interaction.response.send_message(
                " Flag etkinleştirilemedi!",
                ephemeral=True
            )
            return
        
        # Embed oluştur
        embed = discord.Embed(
            title=" Flag Etkinleştirildi",
            description=f"Flag: {flag_key}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name='flag-disable', description='Feature flag devre dışı bırak')
    @app_commands.describe(flag_key='Flag key')
    @app_commands.checks.has_permissions(administrator=True)
    async def flag_disable(self, interaction: discord.Interaction, flag_key: str):
        """Feature flag devre dışı bırak"""
        # Flag devre dışı bırak
        success = feature_flag_manager.disable_flag(flag_key)
        
        if not success:
            await interaction.response.send_message(
                " Flag devre dışı bırakılamadı!",
                ephemeral=True
            )
            return
        
        # Embed oluştur
        embed = discord.Embed(
            title=" Flag Devre Dışı Bırakıldı",
            description=f"Flag: {flag_key}",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name='flag-rollout', description='Feature flag rollout yüzdesini ayarla')
    @app_commands.describe(flag_key='Flag key', percentage='Rollout yüzdesi (0-100)')
    @app_commands.checks.has_permissions(administrator=True)
    async def flag_rollout(self, interaction: discord.Interaction, 
                          flag_key: str, percentage: int):
        """Feature flag rollout yüzdesini ayarla"""
        if percentage < 0 or percentage > 100:
            await interaction.response.send_message(
                " Yüzde 0-100 arasında olmalı!",
                ephemeral=True
            )
            return
        
        # Flag al
        flag = feature_flag_manager.get_flag(flag_key)
        
        if not flag:
            await interaction.response.send_message(
                " Flag bulunamadı!",
                ephemeral=True
            )
            return
        
        # Rollout ayarla
        flag.set_rollout_percentage(percentage)
        feature_flag_manager.save_flag(flag)
        
        # Embed oluştur
        embed = discord.Embed(
            title=" Rollout Ayarlandı",
            description=f"**Flag:** {flag_key}\n**Rollout:** {percentage}%",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name='flag-create', description='Feature flag oluştur')
    @app_commands.describe(flag_key='Flag key', name='Flag adı')
    @app_commands.checks.has_permissions(administrator=True)
    async def flag_create(self, interaction: discord.Interaction, 
                         flag_key: str, name: str):
        """Feature flag oluştur"""
        # Flag oluştur
        flag = feature_flag_manager.create_flag(flag_key, name)
        
        # Embed oluştur
        embed = discord.Embed(
            title=" Feature Flag Oluşturuldu",
            description=f"**Key:** {flag_key}\n**Ad:** {name}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        await interaction.response.send_message(embed=embed)
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Bot hazır olduğunda"""
        log.info(f" FeatureFlagCog loaded")


async def setup(bot):
    await bot.add_cog(FeatureFlagCog(bot))
