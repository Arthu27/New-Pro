"""
Информация и инструменты — префиксные команды (!uptime, !botinfo, !avatar, и т.д.)
"""
import discord
from discord.ext import commands
import time
import re as _re
import base64 as _b64
import ast as _ast
from datetime import datetime

START_TIME = time.time()
ACCENT = 0xdc143c


class InfoTools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _embed(self, title, icon=None):
        e = discord.Embed(title=f"{icon or ''} {title}".strip(), color=ACCENT, timestamp=datetime.utcnow())
        return e

    @commands.command(name="uptime")
    async def uptime(self, ctx):
        elapsed = int(time.time() - START_TIME)
        d, rem = divmod(elapsed, 86400)
        h, rem = divmod(rem, 3600)
        m, s = divmod(rem, 60)
        e = self._embed("АПТАЙМ БОТА", "⏱")
        e.add_field(name="Время работы", value=f"```{d}д {h}ч {m}м {s}с```")
        e.set_thumbnail(url=self.bot.user.display_avatar.url)
        await ctx.send(embed=e)

    @commands.command(name="botinfo")
    async def botinfo(self, ctx):
        b = self.bot
        e = self._embed(f"{b.user.name} — Информация", "🤖")
        e.set_thumbnail(url=b.user.display_avatar.url)
        e.add_field(name="Серверы", value=f"```{len(b.guilds)}```", inline=True)
        e.add_field(name="Пользователи", value=f"```{sum(g.member_count for g in b.guilds)}```", inline=True)
        e.add_field(name="Пинг", value=f"```{round(b.latency*1000)}мс```", inline=True)
        e.set_footer(text=f"Просил: {ctx.author}")
        await ctx.send(embed=e)

    @commands.command(name="avatar", aliases=["аватар"])
    async def avatar(self, ctx, member: discord.Member = None):
        """Показать аватар пользователя"""
        m = member or ctx.author
        e = self._embed(f"{m.display_name} — Аватар", "🖼")
        e.set_image(url=m.display_avatar.url)
        e.set_footer(text=f"Просил: {ctx.author}", icon_url=ctx.author.display_avatar.url)
        e.add_field(name="Пользователь", value=m.mention, inline=True)
        e.add_field(name="Ссылка", value=f"[Открыть]({m.display_avatar.url})", inline=True)
        await ctx.send(embed=e)

    @commands.command(name="roleinfo")
    async def role_info(self, ctx, *, role: discord.Role):
        e = self._embed(f"РОЛЬ: {role.name}", "🎭")
        e.color = role.color if role.color.value else ACCENT
        e.add_field(name="ID", value=f"```{role.id}```", inline=True)
        e.add_field(name="Участников", value=f"```{len(role.members)}```", inline=True)
        e.add_field(name="Цвет", value=f"```{role.color}```", inline=True)
        e.add_field(name="Создана", value=f"<t:{int(role.created_at.timestamp())}:R>", inline=True)
        e.add_field(name="Позиция", value=f"```{role.position}```", inline=True)
        await ctx.send(embed=e)

    @commands.command(name="channelinfo")
    async def channel_info(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        e = self._embed(f"КАНАЛ: #{ch.name}", "📢")
        e.add_field(name="ID", value=f"```{ch.id}```", inline=True)
        e.add_field(name="Категория", value=f"```{ch.category.name if ch.category else 'Нет'}```", inline=True)
        e.add_field(name="Создан", value=f"<t:{int(ch.created_at.timestamp())}:R>", inline=True)
        if ch.topic:
            e.add_field(name="Тема", value=f"```{ch.topic[:100]}```", inline=False)
        await ctx.send(embed=e)

    @commands.command(name="emojiler")
    async def emoji_listesi(self, ctx):
        emojis = ctx.guild.emojis
        if not emojis:
            await ctx.send("На этом сервере нет особых эмодзи!")
            return
        e = self._embed("СПИСОК ЭМОДЗИ", "😀")
        e.description = f"Всего **{len(emojis)}** эмодзи\n" + ' '.join(str(em) for em in emojis[:40])
        await ctx.send(embed=e)

    @commands.command(name="davet")
    async def davet_link(self, ctx):
        url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(8))
        e = self._embed("ПРИГЛАШЕНИЕ БОТА", "🔗")
        e.description = f"[**Добавить бота на сервер**]({url})"
        e.set_thumbnail(url=self.bot.user.display_avatar.url)
        await ctx.send(embed=e)

    @commands.command(name="color")
    async def color(self, ctx, hex_kod: str):
        hex_kod = hex_kod.lstrip('#')
        try:
            r, g, b = int(hex_kod[0:2], 16), int(hex_kod[2:4], 16), int(hex_kod[4:6], 16)
            color_int = int(hex_kod, 16)
        except (ValueError, IndexError):
            await ctx.send("Неверный hex-код! Пример: `!color ff0000`")
            return
        e = self._embed(f"#{hex_kod.upper()}", "🎨")
        e.color = color_int
        e.add_field(name="HEX", value=f"```#{hex_kod.upper()}```", inline=True)
        e.add_field(name="RGB", value=f"```rgb({r}, {g}, {b})```", inline=True)
        e.add_field(name="Предпросмотр", value="```█```", inline=True)
        await ctx.send(embed=e)

    @commands.command(name="vakit")
    async def vakit(self, ctx):
        ts = int(datetime.utcnow().timestamp())
        e = self._embed("ТЕКУЩЕЕ ВРЕМЯ", "🕐")
        e.add_field(name="Коротко", value=f"<t:{ts}:t>", inline=True)
        e.add_field(name="Полно", value=f"<t:{ts}:F>", inline=True)
        e.add_field(name="Относительно", value=f"<t:{ts}:R>", inline=True)
        await ctx.send(embed=e)

    @commands.command(name="hesap")
    async def hesap(self, ctx, *, islem: str):
        if not _re.match(r'^[\d\s\+\-\*\/\.\(\)]+$', islem):
            await ctx.send("Используйте только цифры и операторы!")
            return
        try:
            tree = _ast.parse(islem, mode='eval')
            sonuc = eval(compile(tree, '<string>', 'eval'), {"__builtins__": {}}, {})
            e = self._embed("ВЫЧИСЛЕНИЕ", "🧮")
            e.add_field(name="Действие", value=f"`{islem}`")
            e.add_field(name="Результат", value=f"`{sonuc}`")
            await ctx.send(embed=e)
        except Exception:
            await ctx.send("Неверное действие!")

    @commands.command(name="base64")
    async def base64_cmd(self, ctx, islem: str, *, metin: str):
        try:
            if islem.lower() == "encode":
                sonuc = _b64.b64encode(metin.encode()).decode()
            else:
                sonuc = _b64.b64decode(metin.encode()).decode()
            e = self._embed(f"BASE64 {islem.upper()}", "🔐")
            e.add_field(name="Вход", value=f"`{metin[:100]}`", inline=False)
            e.add_field(name="Выход", value=f"`{sonuc[:200]}`", inline=False)
            await ctx.send(embed=e)
        except Exception:
            await ctx.send("Ошибка преобразования!")

    @commands.command(name="banner")
    async def banner(self, ctx):
        g = ctx.guild
        if not g.banner:
            await ctx.send("У этого сервера нет баннера!")
            return
        e = self._embed(f"{g.name} Баннер", "🏞")
        e.set_image(url=g.banner.url)
        await ctx.send(embed=e)

    @commands.command(name="rolemembers")
    async def role_uyeler(self, ctx, *, role: discord.Role):
        members = role.members
        if not members:
            await ctx.send(f"В роли {role.name} никого нет!")
            return
        liste = ', '.join(m.display_name for m in members[:30])
        if len(members) > 30:
            liste += f" (+{len(members)-30} ещё)"
        e = self._embed(f"{role.name} — {len(members)} участников", "👥")
        e.description = liste
        await ctx.send(embed=e)

    @commands.command(name="ilkmessage")
    async def ilk_message(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        async for msg in ch.history(limit=1, oldest_first=True):
            e = self._embed("ПЕРВОЕ СООБЩЕНИЕ", "📜")
            e.description = f"[Перейти к сообщению]({msg.jump_url})\n\n{msg.content[:200] if msg.content else '*(embed)*'}"
            await ctx.send(embed=e)
            return
        await ctx.send("Сообщение не найдено!")

    @commands.command(name="announce")
    @commands.has_permissions(administrator=True)
    async def announce(self, ctx, channel: discord.TextChannel, baslik: str, *, icerik: str):
        e = discord.Embed(title=baslik, description=icerik, color=ACCENT)
        e.set_footer(text=f"Объявил: {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        e.timestamp = datetime.utcnow()
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
