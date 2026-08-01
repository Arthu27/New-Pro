"""
Fun Cog
Eğlence komutları cog'u
"""

import discord
from discord.ext import commands
from datetime import datetime
import random
import aiohttp

from logger import get_logger
log = get_logger("fun_cog")



class FunCog(commands.Cog):
    """Eğlence komutları cog'u"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='8ball', aliases=['8top'])
    async def eightball(self, ctx, *, question: str):
        """8 ball"""
        responses = [
            "Kesinlikle evet.",
            "Kesinlikle.",
            "Şüphesiz.",
            "Evet, kesinlikle.",
            "Buna güvenebilirsiniz.",
            "Gördüğüm kadarıyla evet.",
            "Muhtemelen.",
            "Evet.",
            "İşaretler evet'i gösteriyor.",
            "Yanıt bulanık, tekrar dene.",
            "Daha sonra sor.",
            "Şimdi söylemesem daha iyi.",
            "Şu anda tahmin edemiyorum.",
            "Konsantre ol ve tekrar sor.",
            "Buna güvenme.",
            "Cevabım hayır.",
            "Kaynaklarım hayır diyor.",
            "Görünüşe göre hayır.",
            "Çok şüpheli.",
            "Hayır."
        ]
        
        response = random.choice(responses)
        
        embed = discord.Embed(
            title=" 8 Ball",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="Soru", value=question, inline=False)
        embed.add_field(name="Cevap", value=response, inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='coinflip', aliases=['yazıtura', 'coin'])
    async def coinflip(self, ctx):
        """Yazı tura"""
        result = random.choice(["Yazı", "Tura"])
        
        embed = discord.Embed(
            title=" Yazı Tura",
            description=f"**Sonuç:** {result}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='dice', aliases=['zar'])
    async def dice(self, ctx, sides: int = 6):
        """Zar at"""
        if sides < 2:
            await ctx.send(" Zar en az 2 yüzlü olmalı!")
            return
        
        result = random.randint(1, sides)
        
        embed = discord.Embed(
            title=" Zar Atışı",
            description=f"**{sides} yüzlü zar:** {result}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='meme')
    async def meme(self, ctx):
        """Rastgele meme"""
        # Placeholder - gerçek API entegrasyonu yapılabilir
        embed = discord.Embed(
            title=" Rastgele Meme",
            description="Meme yükleniyor...",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='joke', aliases=['şaka'])
    async def joke(self, ctx):
        """Rastgele şaka"""
        jokes = [
            "Programcı neden gözlük takar? Çünkü C# göremez!",
            "Bir SQL sorgusu bara girer, iki tabloya yaklaşır ve sorar: 'JOIN olabilir miyim?'",
            "99 bug vardı, düzelttim birini. 127 bug oldu.",
            "Bir programcı neden karanlıkta çalışır? Çünkü light bugs!",
            "Bir programcı karısını terk etti çünkü onunla interface yapamıyordu.",
            "Bir programcı neden gözlük takar? Çünkü C# göremez!",
            "Bir programcı neden evden çalışır? Çünkü evde daha fazla cache var!",
            "Bir programcı neden bilgisayarını sevdi? Çünkü onunla byte'ları paylaşabiliyordu!",
            "Bir programcı neden bilgisayarıyla evlendi? Çünkü onunla çok iyi anlaşıyordu!",
            "Bir programcı neden bilgisayarıyla kavga etti? Çünkü onunla çok fazla conflict vardı!"
        ]
        
        joke = random.choice(jokes)
        
        embed = discord.Embed(
            title=" Rastgele Şaka",
            description=joke,
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='cat', aliases=['kedi'])
    async def cat(self, ctx):
        """Rastgele kedi resmi"""
        # Placeholder - gerçek API entegrasyonu yapılabilir
        embed = discord.Embed(
            title=" Rastgele Kedi",
            description="Kedi resmi yükleniyor...",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='dog', aliases=['köpek'])
    async def dog(self, ctx):
        """Rastgele köpek resmi"""
        # Placeholder - gerçek API entegrasyonu yapılabilir
        embed = discord.Embed(
            title=" Rastgele Köpek",
            description="Köpek resmi yükleniyor...",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='quote', aliases=['alıntı'])
    async def quote(self, ctx):
        """Rastgele alıntı"""
        quotes = [
            "Hayat kısa, sanat uzun.",
            "Bilgi güçtür.",
            "Başarı, hazırlıkla fırsatın buluştuğu yerdir.",
            "Gelecek, bugünün hazırlığına bağlıdır.",
            "Başarısızlık, başarının baharatıdır.",
            "Hayal edebiliyorsan, yapabilirsin.",
            "Başarı, küçük çabaların her gün tekrarlanmasıdır.",
            "Zorluklar, bizi güçlendirir.",
            "Başarı, pes etmemektir.",
            "Hayat, bir yolculuktur, varış noktası değil."
        ]
        
        quote = random.choice(quotes)
        
        embed = discord.Embed(
            title=" Rastgele Alıntı",
            description=f"*{quote}*",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Bot hazır olduğunda"""
        log.info(f" FunCog loaded")


async def setup(bot):
    await bot.add_cog(FunCog(bot))
