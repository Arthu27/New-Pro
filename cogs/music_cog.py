"""
Music Cog
Müzik komutları cog'u
"""

import discord
from discord.ext import commands
from datetime import datetime
import asyncio

from logger import get_logger
log = get_logger("music_cog")



class MusicCog(commands.Cog):
    """Müzik komutları cog'u"""
    
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}  # guild_id -> queue
    
    def get_queue(self, guild_id: int) -> list:
        """Сервер kuyruğunu al"""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]
    
    @commands.command(name='play', aliases=['çal'])
    async def play(self, ctx, *, query: str):
        """Şarkı çal"""
        # Voice channel kontrolü
        if not ctx.author.voice:
            await ctx.send(" Сначала подключитесь к голосовому каналу!")
            return
        
        # Bot voice channel'a katıl
        voice_channel = ctx.author.voice.channel
        
        if not ctx.voice_client:
            await voice_channel.connect()
        
        # Queue'ya добавить
        queue = self.get_queue(ctx.guild.id)
        queue.append({
            'query': query,
            'requester': ctx.author
        })
        
        embed = discord.Embed(
            title=" Kuyruğa Eklendi",
            description=f"**Şarkı:** {query}\n**Sıra:** {len(queue)}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='pause', aliases=['duraklat'])
    async def pause(self, ctx):
        """Şarkıyı duraklat"""
        if not ctx.voice_client:
            await ctx.send(" Сейчас ничего не играет!")
            return
        
        if ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            
            embed = discord.Embed(
                title="⏸ Duraklatıldı",
                color=discord.Color.dark_grey(),
                timestamp=datetime.now()
            )
            
            await ctx.send(embed=embed)
        else:
            await ctx.send(" Сейчас ничего не играет!")
    
    @commands.command(name='resume', aliases=['devam'])
    async def resume(self, ctx):
        """Şarkıyı devam ettir"""
        if not ctx.voice_client:
            await ctx.send(" Сейчас ничего не играет!")
            return
        
        if ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            
            embed = discord.Embed(
                title=" Devam Ediliyor",
                color=discord.Color.dark_grey(),
                timestamp=datetime.now()
            )
            
            await ctx.send(embed=embed)
        else:
            await ctx.send(" Şu anda duraklatılmış bir şarkı yok!")
    
    @commands.command(name='skip', aliases=['geç'])
    async def skip(self, ctx):
        """Şarkıyı geç"""
        if not ctx.voice_client:
            await ctx.send(" Сейчас ничего не играет!")
            return
        
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            
            embed = discord.Embed(
                title="⏭ Şarkı Geçildi",
                color=discord.Color.dark_grey(),
                timestamp=datetime.now()
            )
            
            await ctx.send(embed=embed)
        else:
            await ctx.send(" Сейчас ничего не играет!")
    
    @commands.command(name='queue', aliases=['kuyruk'])
    async def queue(self, ctx):
        """Kuyruğu göster"""
        queue = self.get_queue(ctx.guild.id)
        
        if not queue:
            await ctx.send(" Kuyruk boş!")
            return
        
        embed = discord.Embed(
            title=" Kuyruk",
            description=f"Toplam {len(queue)} şarkı",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        # İlk 10 şarkı
        for i, song in enumerate(queue[:10], 1):
            embed.add_field(
                name=f"{i}. {song['query']}",
                value=f"Ekleyen: {song['requester'].mention}",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='nowplaying', aliases=['şimdi', 'np'])
    async def nowplaying(self, ctx):
        """Şu an çalan şarkıyı göster"""
        queue = self.get_queue(ctx.guild.id)
        
        if not queue:
            await ctx.send(" Сейчас ничего не играет!")
            return
        
        current = queue[0]
        
        embed = discord.Embed(
            title=" Şu Anda Çalıyor",
            description=f"**Şarkı:** {current['query']}\n**Ekleyen:** {current['requester'].mention}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='volume', aliases=['ses'])
    async def volume(self, ctx, volume: int = None):
        """Голос seviyesini настроить"""
        if not ctx.voice_client:
            await ctx.send(" Сейчас ничего не играет!")
            return
        
        if volume is None:
            current_volume = ctx.voice_client.source.volume * 100 if ctx.voice_client.source else 100
            
            embed = discord.Embed(
                title=" Голос Seviyesi",
                description=f"**Mevcut:** {int(current_volume)}%",
                color=discord.Color.dark_grey(),
                timestamp=datetime.now()
            )
            
            await ctx.send(embed=embed)
            return
        
        if volume < 0 or volume > 200:
            await ctx.send(" Голос seviyesi 0-200 между olmalı!")
            return
        
        if ctx.voice_client.source:
            ctx.voice_client.source.volume = volume / 100
            
            embed = discord.Embed(
                title=" Голос Seviyesi Ayarlandı",
                description=f"**Новый Уровень:** {volume}%",
                color=discord.Color.dark_grey(),
                timestamp=datetime.now()
            )
            
            await ctx.send(embed=embed)
    
    @commands.command(name='leave', aliases=['ayrıl'])
    async def leave(self, ctx):
        """Голос kanalından ayrıl"""
        if not ctx.voice_client:
            await ctx.send(" Şu anda bir ses kanalında değilim!")
            return
        
        await ctx.voice_client.disconnect()
        
        # Kuyruğu очистить
        if ctx.guild.id in self.queues:
            self.queues[ctx.guild.id] = []
        
        embed = discord.Embed(
            title=" Голос Kanalından Ayrıldım",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='clearqueue', aliases=['kuyruktemizle'])
    @commands.has_permissions(manage_guild=True)
    async def clearqueue(self, ctx):
        """Kuyruğu очистить"""
        if ctx.guild.id in self.queues:
            self.queues[ctx.guild.id] = []
        
        embed = discord.Embed(
            title=" Kuyruk Temizlendi",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='shuffle', aliases=['karıştır'])
    async def shuffle(self, ctx):
        """Kuyruğu karıştır"""
        queue = self.get_queue(ctx.guild.id)
        
        if len(queue) < 2:
            await ctx.send(" Kuyrukta en az 2 şarkı olmalı!")
            return
        
        # İlk şarkıyı koru
        current = queue[0]
        rest = queue[1:]
        
        random.shuffle(rest)
        
        self.queues[ctx.guild.id] = [current] + rest
        
        embed = discord.Embed(
            title=" Kuyruk Karıştırıldı",
            description=f"**Toplam:** {len(queue)} şarkı",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='loop', aliases=['tekrar'])
    async def loop(self, ctx):
        """Tekrar modunu открыть/закрыть"""
        queue = self.get_queue(ctx.guild.id)
        
        if not queue:
            await ctx.send(" Kuyruk boş!")
            return
        
        # Basit loop - ilk şarkıyı sona добавить
        current = queue[0]
        queue.append(current)
        
        embed = discord.Embed(
            title=" Tekrar Modu",
            description=f"**Şarkı:** {current['query']}\nKuyruğun sonuna добавлено",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Bot hazır olduğunda"""
        log.info(f" MusicCog loaded")


async def setup(bot):
    await bot.add_cog(MusicCog(bot))
