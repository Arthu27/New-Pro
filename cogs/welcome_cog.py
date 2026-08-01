"""
Welcome Cog
Hoş geldin sistemi cog'u
"""

import discord
from discord.ext import commands
from datetime import datetime

from logger import get_logger
log = get_logger("welcome_cog")



class WelcomeCog(commands.Cog):
    """Hoş geldin sistemi cog'u"""
    
    def __init__(self, bot):
        self.bot = bot
        self.welcome_message = "Hoş geldin {user}! Sunucumuza katıldığın için teşekkürler!"
        self.welcome_channel_id = None
    
    @commands.command(name='setwelcome', aliases=['hoşgeldinayarla'])
    @commands.has_permissions(administrator=True)
    async def setwelcome(self, ctx, *, message: str):
        """Hoş geldin mesajını ayarla"""
        self.welcome_message = message
        
        embed = discord.Embed(
            title=" Hoş Geldin Mesajı Ayarlandı",
            description=f"**Yeni mesaj:** {message}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='setwelcomechannel', aliases=['hoşgeldinkanalı'])
    @commands.has_permissions(administrator=True)
    async def setwelcomechannel(self, ctx, channel: discord.TextChannel):
        """Hoş geldin kanalını ayarla"""
        self.welcome_channel_id = channel.id
        
        embed = discord.Embed(
            title=" Hoş Geldin Kanalı Ayarlandı",
            description=f"**Yeni kanal:** {channel.mention}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='testwelcome', aliases=['hoşgeldintest'])
    async def testwelcome(self, ctx):
        """Hoş geldin mesajını test et"""
        message = self.welcome_message.replace("{user}", ctx.author.mention)
        
        embed = discord.Embed(
            title=" Hoş Geldin!",
            description=message,
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Yeni üye katıldığında"""
        if not self.welcome_channel_id:
            return
        
        channel = member.guild.get_channel(self.welcome_channel_id)
        if not channel:
            return
        
        message = self.welcome_message.replace("{user}", member.mention)
        
        embed = discord.Embed(
            title=" Hoş Geldin!",
            description=message,
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        
        await channel.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Bot hazır olduğunda"""
        log.info(f" WelcomeCog loaded")


async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))
