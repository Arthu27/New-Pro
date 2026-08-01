"""
Level Cog
Расширенная seviye система cog'u
"""
import discord
from discord.ext import commands
from datetime import datetime
import random

from logger import get_logger
log = get_logger("level_cog")



class LevelCog(commands.Cog):
    """Расширенная seviye система cog'u"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='rank', aliases=['seviye'])
    async def rank(self, ctx, member: discord.Member = None):
        """Уровень kartını göster"""
        member = member or ctx.author
        
        embed = discord.Embed(
            title=f" {member.display_name}'s Уровень",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Уровень", value="10", inline=True)
        embed.add_field(name="XP", value="5,000/10,000", inline=True)
        embed.add_field(name="Sıralama", value="#5", inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='leaderboard', aliases=['sıralama'])
    async def leaderboard(self, ctx):
        """Уровень lider tablosunu göster"""
        embed = discord.Embed(
            title=" Уровень Lider Tablosu",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        # Örnek lider tablosu
        for i in range(1, 11):
            embed.add_field(
                name=f"#{i} Пользователь{i}",
                value=f"Уровень {20-i} | XP: {10000-i*500:,}",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='rewards', aliases=['ödüller'])
    async def rewards(self, ctx):
        """Уровень ödüllerini göster"""
        embed = discord.Embed(
            title=" Уровень Ödülleri",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        rewards = [
            ("Уровень 5", "@Üye rolü"),
            ("Уровень 10", "@Aktif Üye rolü"),
            ("Уровень 20", "@VIP rolü"),
            ("Уровень 50", "@Efsane rolü")
        ]
        
        for level, reward in rewards:
            embed.add_field(
                name=level,
                value=reward,
                inline=True
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='setlevel', aliases=['seviyeayarla'])
    @commands.has_permissions(administrator=True)
    async def setlevel(self, ctx, member: discord.Member, level: int):
        """Kullanıcının seviyesini настроить"""
        embed = discord.Embed(
            title=" Уровень Ayarlandı",
            description=f"**{member.mention}'ın seviyesi:** {level}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Bot hazır olduğunda"""
        log.info(f" LevelCog loaded")


async def setup(bot):
    await bot.add_cog(LevelCog(bot))
