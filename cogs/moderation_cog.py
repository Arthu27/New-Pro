"""
Moderation Cog
Moderasyon komutları cog'u
"""

import discord
from discord.ext import commands
from datetime import datetime, timedelta

from logger import get_logger
log = get_logger("moderation_cog")



class ModerationCog(commands.Cog):
    """Moderasyon komutları cog'u"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='warn', aliases=['uyarı'])
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str = 'Sebep belirtilmedi'):
        """Kullanıcıyı uyar"""
        from services.gamification import badge_system
        
        # Uyarı ver
        # Buraya warning система entegrasyonu
        
        embed = discord.Embed(
            title=" Uyarı Verildi",
            description=f"**Пользователь:** {member.mention}\n**Sebep:** {reason}\n**Модератор:** {ctx.author.mention}",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
        
        # DM отправить
        try:
            dm_embed = discord.Embed(
                title=" Uyarı Aldınız",
                description=f"**Сервер:** {ctx.guild.name}\n**Sebep:** {reason}",
                color=discord.Color.orange(),
                timestamp=datetime.now()
            )
            await member.send(embed=dm_embed)
        except Exception:
            pass
    
    @commands.command(name='mute', aliases=['sustur'])
    @commands.has_permissions(manage_messages=True)
    async def mute(self, ctx, member: discord.Member, duration: int = 10, *, reason: str = 'Sebep belirtilmedi'):
        """Kullanıcıyı sustur"""
        # Mute rolü найти или создать
        mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
        
        if not mute_role:
            mute_role = await ctx.guild.create_role(name="Muted", color=discord.Color.dark_gray())
            
            # Tüm kanallarda sustur
            for channel in ctx.guild.channels:
                await channel.set_permissions(mute_role, send_messages=False, speak=False)
        
        # Роль ver
        await member.add_roles(mute_role, reason=reason)
        
        embed = discord.Embed(
            title=" Пользователь Susturuldu",
            description=f"**Пользователь:** {member.mention}\n**Süre:** {duration} dakika\n**Sebep:** {reason}\n**Модератор:** {ctx.author.mention}",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
        
        # Otomatik unmute
        await asyncio.sleep(duration * 60)
        await member.remove_roles(mute_role, reason="Susturma süresi doldu")
    
    @commands.command(name='unmute', aliases=['susturma'])
    @commands.has_permissions(manage_messages=True)
    async def unmute(self, ctx, member: discord.Member):
        """Kullanıcının susturmasını kaldır"""
        mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
        
        if not mute_role or mute_role not in member.roles:
            await ctx.send(" Пользователь susturulmamış!")
            return
        
        await member.remove_roles(mute_role, reason="Susturma kaldırıldı")
        
        embed = discord.Embed(
            title=" Susturma Kaldırıldı",
            description=f"**Пользователь:** {member.mention}\n**Модератор:** {ctx.author.mention}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='kick', aliases=['at'])
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = 'Sebep belirtilmedi'):
        """Kullanıcıyı at"""
        await member.kick(reason=reason)
        
        embed = discord.Embed(
            title=" Пользователь Atıldı",
            description=f"**Пользователь:** {member.mention}\n**Sebep:** {reason}\n**Модератор:** {ctx.author.mention}",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='ban', aliases=['забанить'])
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = 'Sebep belirtilmedi'):
        """Kullanıcıyı забанить"""
        await member.ban(reason=reason)
        
        embed = discord.Embed(
            title=" Пользователь Yasaklandı",
            description=f"**Пользователь:** {member.mention}\n**Sebep:** {reason}\n**Модератор:** {ctx.author.mention}",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='unban', aliases=['yasakkaldır'])
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int):
        """Kullanıcının yasağını kaldır"""
        user = await self.bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        
        embed = discord.Embed(
            title=" Yasak Kaldırıldı",
            description=f"**Пользователь:** {user.mention}\n**Модератор:** {ctx.author.mention}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='clear', aliases=['очистить', 'удалить'])
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int = 5):
        """Mesajları удалить"""
        if amount > 100:
            await ctx.send(" Максимум 100 сообщений за раз!")
            return
        
        deleted = await ctx.channel.purge(limit=amount + 1)
        
        embed = discord.Embed(
            title=" Mesajlar Silindi",
            description=f"**Silinen Сообщение:** {len(deleted) - 1}\n**Модератор:** {ctx.author.mention}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(3)
        await msg.delete()
    
    @commands.command(name='slowmode', aliases=['yavaşmod'])
    @commands.has_permissions(manage_messages=True)
    async def slowmode(self, ctx, seconds: int = 0):
        """Yavaş mod настроить"""
        await ctx.channel.edit(slowmode_delay=seconds)
        
        if seconds > 0:
            embed = discord.Embed(
                title=" Yavaş Mod Aktif",
                description=f"**Süre:** {seconds} saniye\n**Модератор:** {ctx.author.mention}",
                color=discord.Color.orange(),
                timestamp=datetime.now()
            )
        else:
            embed = discord.Embed(
                title=" Yavaş Mod Kapatıldı",
                description=f"**Модератор:** {ctx.author.mention}",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='lock', aliases=['kilitle'])
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx):
        """Kanalı kilitle"""
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        
        embed = discord.Embed(
            title=" Канал Kilitlendi",
            description=f"**Канал:** {ctx.channel.mention}\n**Модератор:** {ctx.author.mention}",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='unlock', aliases=['kilidaç'])
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx):
        """Канал kilidini открыть"""
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
        
        embed = discord.Embed(
            title=" Канал Kilidi Açıldı",
            description=f"**Канал:** {ctx.channel.mention}\n**Модератор:** {ctx.author.mention}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Bot hazır olduğunda"""
        log.info(f" ModerationCog loaded")


async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
