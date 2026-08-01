"""
AutoModeration Cog
Otomatik moderasyon cog'u
"""

import discord
from discord.ext import commands
from datetime import datetime
import re

from logger import get_logger
log = get_logger("automod_cog")



class AutoModCog(commands.Cog):
    """Otomatik moderasyon cog'u"""
    
    def __init__(self, bot):
        self.bot = bot
        self.banned_words = ['küfür1', 'küfür2', 'küfür3']
    
    @commands.command(name='automod', aliases=['otomod'])
    @commands.has_permissions(administrator=True)
    async def automod(self, ctx):
        """Otomatik moderasyon ayarlarını göster"""
        embed = discord.Embed(
            title=" Otomatik Moderasyon",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="Anti-Spam", value=" Aktif", inline=True)
        embed.add_field(name="Anti-Link", value=" Aktif", inline=True)
        embed.add_field(name="Anti-Mention", value=" Aktif", inline=True)
        embed.add_field(name="Word Filter", value=" Aktif", inline=True)
        embed.add_field(name="Auto-Delete", value=" Aktif", inline=True)
        embed.add_field(name="Auto-Warn", value=" Aktif", inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='addword', aliases=['kelimeekle'])
    @commands.has_permissions(administrator=True)
    async def addword(self, ctx, word: str):
        """Yasaklı kelime добавить"""
        self.banned_words.append(word.lower())
        
        embed = discord.Embed(
            title=" Kelime Eklendi",
            description=f"**Yasaklı kelime:** {word}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='removeword', aliases=['kelimesil'])
    @commands.has_permissions(administrator=True)
    async def removeword(self, ctx, word: str):
        """Yasaklı kelimeyi kaldır"""
        if word.lower() in self.banned_words:
            self.banned_words.remove(word.lower())
            
            embed = discord.Embed(
                title=" Kelime Kaldırıldı",
                description=f"**Kaldırılan kelime:** {word}",
                color=discord.Color.dark_grey(),
                timestamp=datetime.now()
            )
            
            await ctx.send(embed=embed)
        else:
            await ctx.send(" Kelime не найдено!")
    
    @commands.command(name='wordlist', aliases=['kelimelistesi'])
    async def wordlist(self, ctx):
        """Yasaklı kelime listesini göster"""
        embed = discord.Embed(
            title=" Yasaklı Kelimeler",
            description=", ".join(self.banned_words[:20]) if self.banned_words else "Yasaklı kelime yok",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Сообщение geldiğinde проверить et"""
        if message.author.bot:
            return
        
        # Yasaklı kelime kontrolü
        for word in self.banned_words:
            if word in message.content.lower():
                await message.delete()
                await message.channel.send(f" {message.author.mention} Yasaklı kelime kullandınız!", delete_after=5)
                return
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Bot hazır olduğunda"""
        log.info(f" AutoModCog loaded")


async def setup(bot):
    await bot.add_cog(AutoModCog(bot))
