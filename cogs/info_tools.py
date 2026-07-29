"""Информация ve arac команды — prefix команды (!uptime, !botinfo, vb.)"""
import discord
from discord.ext import commands
import time
import re as _re
import base64 as _b64
from datetime import datetime

START_TIME = time.time()

class InfoTools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="uptime")
    async def uptime(self, ctx):
        elapsed = int(time.time() - START_TIME)
        d, rem = divmod(elapsed, 86400)
        h, rem = divmod(rem, 3600)
        m, s = divmod(rem, 60)
        e = discord.Embed(title="⏱️ UPTIME", color=0xdc143c, timestamp=datetime.utcnow())
        e.add_field(name="🕐 Работа Длительность", value=f"```{d}g {h}s {m}d {s}sn```")
        e.set_thumbnail(url=self.bot.user.display_avatar.url)
        await ctx.send(embed=e)

    @commands.command(name="botinfo")
    async def botinfo(self, ctx):
        b = self.bot
        e = discord.Embed(title=f"🤖 {b.user.name}", color=0xdc143c, timestamp=datetime.utcnow())
        e.set_thumbnail(url=b.user.display_avatar.url)
        e.add_field(name="🏠 Сервер", value=f"```{len(b.guilds)}```", inline=True)
        e.add_field(name="👥 Пользователь", value=f"```{sum(g.member_count for g in b.guilds)}```", inline=True)
        e.add_field(name="📡 Ping", value=f"```{round(b.latency*1000)}ms```", inline=True)
        await ctx.send(embed=e)

    @commands.command(name="roleinfo")
    async def role_info(self, ctx, *, role: discord.Role):
        e = discord.Embed(title=f"🎭 РОЛЬ: {role.name}", color=role.color if role.color.value else 0xdc143c)
        e.add_field(name="🆔 ID", value=f"```{role.id}```", inline=True)
        e.add_field(name="👥 Участник", value=f"```{len(role.members)}```", inline=True)
        e.add_field(name="🎨 Renk", value=f"```{role.color}```", inline=True)
        e.add_field(name="📅 Создал", value=f"<t:{int(role.created_at.timestamp())}:R>", inline=True)
        await ctx.send(embed=e)

    @commands.command(name="channelinfo")
    async def channel_info(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        e = discord.Embed(title=f"📺 КАНАЛ: #{ch.name}", color=0xdc143c)
        e.add_field(name="🆔 ID", value=f"```{ch.id}```", inline=True)
        e.add_field(name="📁 Kategori", value=f"```{ch.category.name if ch.category else 'Нет'}```", inline=True)
        e.add_field(name="📅 Создал", value=f"<t:{int(ch.created_at.timestamp())}:R>", inline=True)
        if ch.topic:
            e.add_field(name="📝 Konu", value=f"```{ch.topic[:100]}```", inline=False)
        await ctx.send(embed=e)

    @commands.command(name="emojiler")
    async def emoji_listesi(self, ctx):
        emojis = ctx.guild.emojis
        if not emojis:
            await ctx.send("❌ Особый emoji yok!")
            return
        e = discord.Embed(title="😀 EMOJİ LİSTESİ", color=0xdc143c)
        e.description = f"Всего **{len(emojis)}** emoji\n" + ' '.join(str(em) for em in emojis[:40])
        await ctx.send(embed=e)

    @commands.command(name="davet")
    async def davet_link(self, ctx):
        url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(8))
        e = discord.Embed(title="🔗 BOT DAVETİ", color=0xdc143c)
        e.description = f"[**➜ Botu Сервер Добавлено**]({url})"
        e.set_thumbnail(url=self.bot.user.display_avatar.url)
        await ctx.send(embed=e)

    @commands.command(name="color")
    async def color(self, ctx, hex_kod: str):
        hex_kod = hex_kod.lstrip('#')
        try:
            r, g, b = int(hex_kod[0:2], 16), int(hex_kod[2:4], 16), int(hex_kod[4:6], 16)
            color_int = int(hex_kod, 16)
        except (ValueError, IndexError):
            await ctx.send("❌ Неверный hex kodu! Пример: `!color ff0000`")
            return
        e = discord.Embed(title=f"🎨 #{hex_kod.upper()}", color=color_int)
        e.add_field(name="HEX", value=f"```#{hex_kod.upper()}```", inline=True)
        e.add_field(name="RGB", value=f"```rgb({r}, {g}, {b})```", inline=True)
        await ctx.send(embed=e)

    @commands.command(name="vakit")
    async def vakit(self, ctx):
        ts = int(datetime.utcnow().timestamp())
        e = discord.Embed(title="🕐 ВРЕМЯ", color=0xdc143c)
        e.add_field(name="⏰ Краткий", value=f"<t:{ts}:t>", inline=True)
        e.add_field(name="📅 Uzun", value=f"<t:{ts}:F>", inline=True)
        e.add_field(name="🔄 Видеть", value=f"<t:{ts}:R>", inline=True)
        await ctx.send(embed=e)

    @commands.command(name="hesap")
    async def hesap(self, ctx, *, islem: str):
        if not _re.match(r'^[\d\s\+\-\*\/\.\(\)]+$', islem):
            await ctx.send("❌ Используйте только цифры и операторы!")
            return
        try:
            sonuc = eval(islem)
            e = discord.Embed(title="🧮 HESAP", color=0xdc143c)
            e.add_field(name="Действие", value=f"`{islem}`")
            e.add_field(name="результат", value=f"`{sonuc}`")
            await ctx.send(embed=e)
        except Exception:
            await ctx.send("❌ Неверный действие!")

    @commands.command(name="base64")
    async def base64_cmd(self, ctx, islem: str, *, metin: str):
        try:
            if islem == "encode":
                sonuc = _b64.b64encode(metin.encode()).decode()
            else:
                sonuc = _b64.b64decode(metin.encode()).decode()
            e = discord.Embed(title=f"BASE64 {islem.upper()}", color=0xdc143c)
            e.add_field(name="Girdi", value=f"`{metin[:100]}`", inline=False)
            e.add_field(name="Вышел", value=f"`{sonuc[:200]}`", inline=False)
            await ctx.send(embed=e)
        except Exception:
            await ctx.send("❌ Ошибка преобразования!")

    @commands.command(name="banner")
    async def banner(self, ctx):
        g = ctx.guild
        if not g.banner:
            await ctx.send("Bu сервера banneri yok!")
            return
        e = discord.Embed(title=f"{g.name} Banner", color=0xdc143c)
        e.set_image(url=g.banner.url)
        await ctx.send(embed=e)

    @commands.command(name="rolemembers")
    async def role_uyeler(self, ctx, *, role: discord.Role):
        members = роли.members
        if not members:
            await ctx.send(f"{role.name} роли кто yok!")
            return
        liste = ', '.join(m.display_name for m in members[:30])
        if len(members) > 30:
            liste += f" (+{len(members)-30} более)"
        e = discord.Embed(title=f"{role.name} — {len(members)} участник", color=0xdc143c, description=liste)
        await ctx.send(embed=e)

    @commands.command(name="ilkmessage")
    async def ilk_message(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        async for msg in ch.history(limit=1, oldest_first=True):
            e = discord.Embed(title="📌 İLK СООБЩЕНИЕ", color=0xdc143c,
                description=f"[Сообщению git]({msg.jump_url})\n\n{msg.content[:200] if msg.content else '*(embed)*'}")
            await ctx.send(embed=e)
            return
        await ctx.send("Сообщение не найден!")

    @commands.command(name="announce")
    @commands.has_permissions(administrator=True)
    async def announce(self, ctx, channel: discord.TextChannel, baslik: str, *, icerik: str):
        e = discord.Embed(title=baslik, description=icerik, color=0xdc143c)
        e.set_footer(text=f"Duyuran: {ctx.author.display_name}")
        await channel.send(embed=e)
        await ctx.message.delete()

    @commands.command(name="say")
    @commands.has_permissions(administrator=True)
    async def say(self, ctx, channel: discord.TextChannel = None, *, message: str):
        ch = channel or ctx.channel
        await ch.send(message)
        try:
            await ctx.message.delete()
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(InfoTools(bot))
