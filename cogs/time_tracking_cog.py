"""
Time Tracking Cog
Отслеживание времени cog'u
"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
from services.time_tracking import time_tracker, pomodoro_timer

from logger import get_logger
log = get_logger("time_tracking_cog")



class TimeTrackingCog(commands.Cog):
    """Отслеживание времени cog'u"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name='time-start', description='Запустить таймер')
    @app_commands.describe(description='Zamanlayıcı açıklaması')
    async def time_start(self, interaction: discord.Interaction, 
                        description: str = 'Çalışma'):
        """Запустить таймер"""
        # Zaten aktif zamanlayıcı var mı проверить et
        active_entry = time_tracker.get_active_entry(interaction.user.id)
        
        if active_entry:
            await interaction.response.send_message(
                f"⏱ Zaten aktif bir zamanlayıcınız var! Başlangıç: {active_entry['start_time'][:16]}",
                ephemeral=True
            )
            return
        
        # Запустить таймер
        entry = time_tracker.start_timer(
            user_id=interaction.user.id,
            description=description
        )
        
        # Embed создать
        embed = discord.Embed(
            title="⏱ Zamanlayıcı Başlatıldı",
            description=f"**Açıklama:** {description}\n**Başlangıç:** {entry['start_time'][:16]}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name='time-stop', description='Zamanlayıcı остановить')
    async def time_stop(self, interaction: discord.Interaction):
        """Zamanlayıcı остановить"""
        # Zamanlayıcı остановить
        entry = time_tracker.stop_timer(interaction.user.id)
        
        if not entry:
            await interaction.response.send_message(
                " Aktif zamanlayıcınız yok!",
                ephemeral=True
            )
            return
        
        # Süre hesapla
        duration = datetime.fromisoformat(entry['end_time']) - datetime.fromisoformat(entry['start_time'])
        hours = int(duration.total_seconds() / 3600)
        minutes = int((duration.total_seconds() % 3600) / 60)
        
        # Embed создать
        embed = discord.Embed(
            title="⏱ Zamanlayıcı Durduruldu",
            description=f"**Açıklama:** {entry['description']}\n**Süre:** {hours}s {minutes}d",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name='time-report', description='Zaman raporunuzu görüntüleyin')
    @app_commands.describe(days='Gün sayısı (varsayılan: 7)')
    async def time_report(self, interaction: discord.Interaction, days: int = 7):
        """Zaman raporunuzu görüntüleyin"""
        # Rapor al
        report = time_tracker.get_user_report(interaction.user.id, days=days)
        
        # Embed создать
        embed = discord.Embed(
            title=f" Zaman Raporu ({days} gün)",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="⏱ Toplam Süre", value=f"{report['total_hours']:.2f} saat", inline=True)
        embed.add_field(name=" Toplam Giriş", value=str(report['total_entries']), inline=True)
        embed.add_field(name=" Ortalama", value=f"{report['avg_hours_per_day']:.2f} saat/gün", inline=True)
        
        # Günlük breakdown
        if report['daily_breakdown']:
            daily_text = "\n".join([
                f"• {day}: {hours:.2f} saat"
                for day, hours in list(report['daily_breakdown'].items())[:7]
            ])
            embed.add_field(name="Günlük Breakdown", value=daily_text, inline=False)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name='pomodoro', description='Pomodoro timer запустить')
    @app_commands.describe(work_minutes='Çalışma süresi (varsayılan: 25)', 
                          break_minutes='Mola süresi (varsayılan: 5)')
    async def pomodoro(self, interaction: discord.Interaction, 
                      work_minutes: int = 25, break_minutes: int = 5):
        """Pomodoro timer запустить"""
        # Pomodoro запустить
        session = pomodoro_timer.start_session(
            user_id=interaction.user.id,
            work_minutes=work_minutes,
            break_minutes=break_minutes
        )
        
        # Embed создать
        embed = discord.Embed(
            title=" Pomodoro Başlatıldı",
            description=f"**Çalışma Süresi:** {work_minutes} dakika\n**Mola Süresi:** {break_minutes} dakika\n\nÇalışmaya başlayın!",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name='pomodoro-complete', description='Pomodoro\'yu tamamla')
    async def pomodoro_complete(self, interaction: discord.Interaction):
        """Pomodoro'yu tamamla"""
        # Pomodoro tamamla
        session = pomodoro_timer.complete_pomodoro(interaction.user.id)
        
        if not session:
            await interaction.response.send_message(
                " Aktif pomodoro yok!",
                ephemeral=True
            )
            return
        
        # İstatistikler al
        stats = pomodoro_timer.get_user_stats(interaction.user.id)
        
        # Embed создать
        embed = discord.Embed(
            title=" Pomodoro Tamamlandı!",
            description=f"**Tebrikler!** Bir pomodoro более tamamladınız!",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name=" Toplam Pomodoro", value=str(stats['total_pomodoros']), inline=True)
        embed.add_field(name="⏱ Toplam Süre", value=f"{stats['total_hours']:.2f} saat", inline=True)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name='pomodoro-stats', description='Pomodoro istatistiklerinizi görüntüleyin')
    async def pomodoro_stats(self, interaction: discord.Interaction):
        """Pomodoro istatistiklerinizi görüntüleyin"""
        # İstatistikler al
        stats = pomodoro_timer.get_user_stats(interaction.user.id)
        
        # Embed создать
        embed = discord.Embed(
            title=" Pomodoro İstatistikleri",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name=" Toplam Pomodoro", value=str(stats['total_pomodoros']), inline=True)
        embed.add_field(name="⏱ Toplam Süre", value=f"{stats['total_hours']:.2f} saat", inline=True)
        embed.add_field(name=" Günlük Ortalama", value=f"{stats['avg_per_day']:.2f}", inline=True)
        
        await interaction.response.send_message(embed=embed)
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Bot hazır olduğunda"""
        log.info(f" TimeTrackingCog loaded")


async def setup(bot):
    await bot.add_cog(TimeTrackingCog(bot))
