"""
A/B Testing Cog
A/B testing cog'u
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from services.ab_testing import ab_test_manager, ab_test_tracking, ab_test_analytics, ABTestVariant

from logger import get_logger
log = get_logger("ab_cog")



class ABCog(commands.Cog):
    """A/B testing cog'u"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name='ab-create', description='Создать A/B тест')
    @app_commands.describe(name='Test adı', description='Test açıklaması')
    @app_commands.checks.has_permissions(administrator=True)
    async def ab_create(self, interaction: discord.Interaction, 
                       name: str, description: str):
        """Создать A/B тест"""
        # Test создать
        test = ab_test_manager.create_test(name, description)
        
        # Embed создать
        embed = discord.Embed(
            title=" A/B Test Создано",
            description=f"**Ad:** {name}\n**Açıklama:** {description}\n**ID:** {test.test_id}",
            color=discord.Color.purple(),
            timestamp=datetime.now()
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name='ab-variants', description='Test varyantlarını görüntüle')
    @app_commands.describe(test_id='Test ID')
    async def ab_variants(self, interaction: discord.Interaction, test_id: str):
        """Test varyantlarını görüntüle"""
        # Test al
        test = ab_test_manager.get_test(test_id)
        
        if not test:
            await interaction.response.send_message(
                " Тест не найден!",
                ephemeral=True
            )
            return
        
        # Varyantlar al
        variants = test.get_all_variants()
        
        if not variants:
            await interaction.response.send_message(
                " Вариант не найден!",
                ephemeral=True
            )
            return
        
        # Embed создать
        embed = discord.Embed(
            title=f" Test Variants: {test.name}",
            description=f"Toplam {len(variants)} varyant",
            color=discord.Color.purple(),
            timestamp=datetime.now()
        )
        
        # Varyant listesi
        for variant in variants:
            enabled_text = " Enabled" if variant.enabled else " Disabled"
            embed.add_field(
                name=f"{variant.name}",
                value=f"{variant.description}\nWeight: {variant.weight}\n{enabled_text}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name='ab-add-variant', description='Добавить вариант теста')
    @app_commands.describe(test_id='Test ID', name='Varyant adı', 
                          description='Varyant açıklaması', weight='Ağırlık (varsayılan: 50)')
    @app_commands.checks.has_permissions(administrator=True)
    async def ab_add_variant(self, interaction: discord.Interaction, 
                          test_id: str, name: str, description: str, 
                          weight: int = 50):
        """Добавить вариант теста"""
        # Test al
        test = ab_test_manager.get_test(test_id)
        
        if not test:
            await interaction.response.send_message(
                " Тест не найден!",
                ephemeral=True
            )
            return
        
        # Varyant создать
        variant = ABTestVariant(name, description, weight)
        test.add_variant(variant)
        ab_test_manager.save_test(test)
        
        # Embed создать
        embed = discord.Embed(
            title=" Varyant Eklendi",
            description=f"**Test:** {test.name}\n**Varyant:** {name}\n**Ağırlık:** {weight}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name='ab-stats', description='Test istatistiklerini görüntüle')
    @app_commands.describe(test_id='Test ID')
    async def ab_stats(self, interaction: discord.Interaction, test_id: str):
        """Test istatistiklerini görüntüle"""
        # Test al
        test = ab_test_manager.get_test(test_id)
        
        if not test:
            await interaction.response.send_message(
                " Тест не найден!",
                ephemeral=True
            )
            return
        
        # İstatistikler al
        stats = ab_test_analytics.get_test_stats(test_id)
        
        # Embed создать
        embed = discord.Embed(
            title=f" Test Stats: {test.name}",
            color=discord.Color.purple(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="Status", value=test.status, inline=True)
        embed.add_field(name="Total Users", value=str(stats['total_users']), inline=True)
        embed.add_field(name="Total Conversions", value=str(stats['total_conversions']), inline=True)
        
        # Varyant istatistikleri
        if stats.get('variant_stats'):
            for variant_id, variant_stats in stats['variant_stats'].items():
                conversion_rate = variant_stats['conversion_rate'] * 100
                embed.add_field(
                    name=f"{variant_stats['variant_name']}",
                    value=f"Impressions: {variant_stats['impressions']}\nConversions: {variant_stats['conversions']}\nRate: {conversion_rate:.2f}%",
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name='ab-start', description='Testi запустить')
    @app_commands.describe(test_id='Test ID')
    @app_commands.checks.has_permissions(administrator=True)
    async def ab_start(self, interaction: discord.Interaction, test_id: str):
        """Testi запустить"""
        # Test запустить
        success = ab_test_manager.start_test(test_id)
        
        if not success:
            await interaction.response.send_message(
                " Test başlatılamadı!",
                ephemeral=True
            )
            return
        
        # Embed создать
        embed = discord.Embed(
            title=" Test Başlatıldı",
            description=f"Test ID: {test_id}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name='ab-stop', description='Testi остановить')
    @app_commands.describe(test_id='Test ID')
    @app_commands.checks.has_permissions(administrator=True)
    async def ab_stop(self, interaction: discord.Interaction, test_id: str):
        """Testi остановить"""
        # Test остановить
        success = ab_test_manager.stop_test(test_id)
        
        if not success:
            await interaction.response.send_message(
                " Test durdurulamadı!",
                ephemeral=True
            )
            return
        
        # Embed создать
        embed = discord.Embed(
            title="⏹ Test Durduruldu",
            description=f"Test ID: {test_id}",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        
        await interaction.response.send_message(embed=embed)
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Bot hazır olduğunda"""
        log.info(f" ABCog loaded")


async def setup(bot):
    await bot.add_cog(ABCog(bot))
