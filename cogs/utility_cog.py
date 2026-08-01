"""
Utility Cog
Yardımcı komutlar cog'u
"""

import discord
from discord.ext import commands
from datetime import datetime
import aiohttp

from logger import get_logger
log = get_logger("utility_cog")



class UtilityCog(commands.Cog):
    """Yardımcı komutlar cog'u"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='ping', aliases=['gecikme'])
    async def ping(self, ctx):
        """Bot gecikmesini göster"""
        latency = round(self.bot.latency * 1000)
        
        embed = discord.Embed(
            title=" Pong!",
            description=f"**Gecikme:** {latency}ms",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='avatar', aliases=['av', 'pp'])
    async def avatar(self, ctx, member: discord.Member = None):
        """Пользователь avatarını göster"""
        member = member or ctx.author
        
        embed = discord.Embed(
            title=f" {member.display_name}'s Avatar",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.set_image(url=member.display_avatar.url)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='serverinfo', aliases=['server', 'сервер'])
    async def serverinfo(self, ctx):
        """Сервер bilgilerini göster"""
        guild = ctx.guild
        
        embed = discord.Embed(
            title=f" {guild.name}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        embed.add_field(name=" Sahip", value=guild.owner.mention, inline=True)
        embed.add_field(name=" ID", value=guild.id, inline=True)
        embed.add_field(name=" Oluşturulma", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
        
        embed.add_field(name=" Üyeler", value=guild.member_count, inline=True)
        embed.add_field(name=" Kanallar", value=len(guild.channels), inline=True)
        embed.add_field(name=" Roller", value=len(guild.roles), inline=True)
        
        embed.add_field(name=" Emojiler", value=len(guild.emojis), inline=True)
        embed.add_field(name=" Boost Level", value=guild.premium_tier, inline=True)
        embed.add_field(name=" Boosts", value=guild.premium_subscription_count, inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='userinfo', aliases=['user', 'пользователь'])
    async def userinfo(self, ctx, member: discord.Member = None):
        """Пользователь bilgilerini göster"""
        member = member or ctx.author
        
        embed = discord.Embed(
            title=f" {member.display_name}",
            color=member.color,
            timestamp=datetime.now()
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        
        embed.add_field(name=" ID", value=member.id, inline=True)
        embed.add_field(name=" Katılma", value=member.joined_at.strftime("%d/%m/%Y"), inline=True)
        embed.add_field(name=" Hesap Oluşturma", value=member.created_at.strftime("%d/%m/%Y"), inline=True)
        
        roles = [role.mention for role in member.roles if role.name != "@everyone"]
        embed.add_field(name=f" Roller ({len(roles)})", value=", ".join(roles[:10]) if roles else "Yok", inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='weather', aliases=['hava'])
    async def weather(self, ctx, city: str):
        """Hava durumunu göster"""
        embed = discord.Embed(
            title=f" {city} Hava Durumu",
            description="Hava durumu bilgisi загружается...",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='translate', aliases=['çevir'])
    async def translate(self, ctx, target_lang: str, *, text: str):
        """Metni çevir"""
        embed = discord.Embed(
            title=" Çeviri",
            description=f"**Hedef Dil:** {target_lang}\n**Metin:** {text[:100]}...",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='remind', aliases=['hatırlat'])
    async def remind(self, ctx, time: int, unit: str = 'm', *, message: str):
        """Hatırlatıcı настроить"""
        import asyncio
        
        if unit == 's':
            seconds = time
        elif unit == 'm':
            seconds = time * 60
        elif unit == 'h':
            seconds = time * 3600
        else:
            seconds = time * 60
        
        embed = discord.Embed(
            title="⏰ Hatırlatıcı Ayarlandı",
            description=f"**Süre:** {time}{unit}\n**Сообщение:** {message}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
        
        await asyncio.sleep(seconds)
        
        remind_embed = discord.Embed(
            title="⏰ Hatırlatıcı!",
            description=f"**Сообщение:** {message}\n**Süre:** {time}{unit}",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        
        await ctx.send(f"{ctx.author.mention}", embed=remind_embed)
    
    @commands.command(name='poll', aliases=['anket'])
    async def poll(self, ctx, question: str, *options):
        """Anket создать"""
        if len(options) < 2:
            await ctx.send(" En az 2 seçenek belirtmelisiniz!")
            return
        
        if len(options) > 10:
            await ctx.send(" En fazla 10 seçenek belirtebilirsiniz!")
            return
        
        emojis = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '']
        
        options_text = "\n".join([
            f"{emojis[i]} {option}"
            for i, option in enumerate(options)
        ])
        
        embed = discord.Embed(
            title=f" {question}",
            description=options_text,
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.set_footer(text=f"Anketi oluşturan: {ctx.author.display_name}")
        
        msg = await ctx.send(embed=embed)
        
        for i in range(len(options)):
            await msg.add_reaction(emojis[i])
    
    @commands.command(name='giveaway', aliases=['çekiliş'])
    @commands.has_permissions(manage_guild=True)
    async def giveaway(self, ctx, duration: int, unit: str = 'm', *, prize: str):
        """Çekiliş создать"""
        import asyncio
        import random
        
        if unit == 's':
            seconds = duration
        elif unit == 'm':
            seconds = duration * 60
        elif unit == 'h':
            seconds = duration * 3600
        else:
            seconds = duration * 60
        
        embed = discord.Embed(
            title=" Çekiliş!",
            description=f"**Ödül:** {prize}\n**Süre:** {duration}{unit}\n\nДля участия emojisine tıklayın!",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        embed.set_footer(text=f"Çekilişi oluşturan: {ctx.author.display_name}")
        
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("")
        
        await asyncio.sleep(seconds)
        
        msg = await ctx.channel.fetch_message(msg.id)
        users = await msg.reactions[0].users().flatten()
        users = [u for u in users if not u.bot]
        
        if users:
            winner = random.choice(users)
            
            winner_embed = discord.Embed(
                title=" Çekiliş Sonucu!",
                description=f"**Ödül:** {prize}\n**Kazanan:** {winner.mention}\n\nTebrikler! ",
                color=discord.Color.gold(),
                timestamp=datetime.now()
            )
            
            await ctx.send(embed=winner_embed)
        else:
            await ctx.send(" Kimse katılmadı!")
    
    @commands.command(name='botinfo', aliases=['bot'])
    async def botinfo(self, ctx):
        """Bot bilgilerini göster"""
        embed = discord.Embed(
            title=" Bot Bilgileri",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        
        embed.add_field(name=" İsim", value=self.bot.user.name, inline=True)
        embed.add_field(name=" ID", value=self.bot.user.id, inline=True)
        embed.add_field(name=" Oluşturulma", value=self.bot.user.created_at.strftime("%d/%m/%Y"), inline=True)
        
        embed.add_field(name=" Sunucular", value=len(self.bot.guilds), inline=True)
        embed.add_field(name=" Kullanıcılar", value=len(self.bot.users), inline=True)
        embed.add_field(name=" Komutlar", value=len(self.bot.commands), inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='invite', aliases=['davet'])
    async def invite(self, ctx):
        """Bot davet linkini göster"""
        invite_url = f"https://discord.com/api/oauth2/authorize?client_id={self.bot.user.id}&permissions=8&scope=bot%20applications.commands"
        
        embed = discord.Embed(
            title=" Bot Davet Linki",
            description=f"[Buraya tıklayarak botu sunucunuza davet edin!]({invite_url})",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='help', aliases=['yardım'])
    async def help(self, ctx, command: str = None):
        """Yardım göster"""
        if command:
            cmd = self.bot.get_command(command)
            
            if not cmd:
                await ctx.send(" Команда не найдена!")
                return
            
            embed = discord.Embed(
                title=f" {cmd.name}",
                description=cmd.help or "Açıklama yok",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            if cmd.aliases:
                embed.add_field(name="Alternatifler", value=", ".join(cmd.aliases), inline=False)
            
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title=" Yardım",
                description="Для списка команд `!help <команда>` yazın",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            cogs = self.bot.cogs
            
            for cog_name, cog in cogs.items():
                commands = [cmd.name for cmd in cog.get_commands()]
                
                if commands:
                    embed.add_field(
                        name=cog_name,
                        value=", ".join(commands[:10]),
                        inline=False
                    )
            
            await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Bot hazır olduğunda"""
        log.info(f" UtilityCog loaded")


async def setup(bot):
    await bot.add_cog(UtilityCog(bot))
