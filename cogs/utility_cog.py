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
    
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import io
import os
import math
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.join(os.path.dirname(__file__), '..')
FONTS = os.path.join(ROOT, 'assets', 'fonts')
BG_PATH = os.path.join(ROOT, 'assets', 'profile_bg_pro.jpg')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

WHITE = (255, 255, 255)
BLACK = (20, 20, 25)
BLUE = (2, 132, 199)
MUTED = (110, 115, 125)
SS = 4


def _f(bold=False, sz=20):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT_R, sz)
    except Exception:
        return ImageFont.load_default()


def _ss_render(w, h, draw_fn, scale=SS):
    big = Image.new('RGBA', (w * scale, h * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    draw_fn(d, scale)
    return big.resize((w, h), Image.Resampling.LANCZOS)


def _load_bg(w, h):
    try:
        bg = Image.open(BG_PATH).convert('RGBA')
        bw, bh = bg.size
        target_ratio = w / h
        src_ratio = bw / bh
        if src_ratio > target_ratio:
            new_w = int(bh * target_ratio)
            x0 = (bw - new_w) // 2
            bg = bg.crop((x0, 0, x0 + new_w, bh))
        else:
            new_h = int(bw / target_ratio)
            y0 = (bh - new_h) // 2
            bg = bg.crop((0, y0, bw, y0 + new_h))
        return bg.resize((w, h), Image.Resampling.LANCZOS)
    except Exception:
        return Image.new('RGBA', (w, h), (255, 255, 255, 255))


def _icon_tech(d, cx, cy, s, w, color):
    r_out = s * 0.4
    r_in = s * 0.28
    for idx in range(8):
        a1 = math.radians(idx * 45 - 12)
        a2 = math.radians(idx * 45 + 12)
        p1 = (cx + r_in * math.cos(a1), cy + r_in * math.sin(a1))
        p2 = (cx + r_out * math.cos(a1), cy + r_out * math.sin(a1))
        p3 = (cx + r_out * math.cos(a2), cy + r_out * math.sin(a2))
        p4 = (cx + r_in * math.cos(a2), cy + r_in * math.sin(a2))
        d.line([p1, p2, p3, p4], fill=color, width=w, joint='curve')
    r_mid = s * 0.28
    d.ellipse((cx - r_mid, cy - r_mid, cx + r_mid, cy + r_mid), outline=color, width=w)
    r_center = s * 0.12
    d.ellipse((cx - r_center, cy - r_center, cx + r_center, cy + r_center), outline=color, width=w)


def _icon_badge(diameter, glyph_fn, ring_color=BLACK, ring_w=None, icon_color=BLUE):
    ring_w = ring_w if ring_w is not None else max(2, diameter // 22)

    def draw(d, scale):
        size = diameter * scale
        rw = ring_w * scale
        r = size * 0.22
        d.rounded_rectangle((rw / 2, rw / 2, size - rw / 2 - 1, size - rw / 2 - 1),
                             radius=r, fill=WHITE, outline=ring_color, width=rw)
        glyph_fn(d, size / 2, size / 2, size * 0.60, max(2, int(size * 0.032)), icon_color)

    return _ss_render(diameter, diameter, draw)


def _corner_bracket(size, thickness, length_ratio=0.35, color=BLUE):
    def draw(d, scale):
        t = thickness * scale
        L = size * scale * length_ratio
        d.line([(0, t / 2), (L, t / 2)], fill=color, width=t)
        d.line([(t / 2, 0), (t / 2, L)], fill=color, width=t)
    return _ss_render(size, size, draw)


def _rounded_panel(w, h, radius, fill=WHITE, outline=BLACK, ow=3):
    def draw(d, scale):
        r = radius * scale
        o = ow * scale
        d.rounded_rectangle((o / 2, o / 2, w * scale - o / 2 - 1, h * scale - o / 2 - 1),
                             radius=r, fill=fill, outline=outline, width=o)
    return _ss_render(w, h, draw)


def generate_info_card(guild: discord.Guild, member: discord.Member = None, category: str = "server") -> Image.Image:
    W, H = 920, 520
    bg = _load_bg(W, H)
    d = ImageDraw.Draw(bg)

    header_box = _rounded_panel(872, 72, radius=14, fill=WHITE, outline=BLACK, ow=2)
    bg.alpha_composite(header_box, (24, 20))

    badge = _icon_badge(52, _icon_tech, ring_color=BLACK, ring_w=2, icon_color=BLUE)
    bg.alpha_composite(badge, (36, 30))

    if category == "user" and member:
        title_text = f"УЧАСТНИК • {member.display_name.upper()}"
        sub_text = f"ID: {member.id} • НА СЕРВЕРЕ С {member.joined_at.strftime('%d.%m.%Y') if member.joined_at else '---'}"
        items = [
            ("АККАУНТ И ДАТА", f"Создан: {member.created_at.strftime('%d.%m.%Y')}", "Статус в норме"),
            ("ВЫСШАЯ РОЛЬ", member.top_role.name, "Привилегии"),
            ("АКТИВНОСТЬ", f"Ролей: {len(member.roles)}", "Доступ на сервере"),
            ("ID ПОЛЬЗОВАТЕЛЯ", str(member.id), "Идентификатор")
        ]
    else:
        title_text = f"СЕРВЕР • {guild.name.upper()}"
        created_str = guild.created_at.strftime('%d.%m.%Y') if getattr(guild, 'created_at', None) else "01.08.2026"
        sub_text = f"ID: {guild.id} • СОЗДАН {created_str}"
        owner_name = getattr(guild.owner, 'display_name', "SABOTASH") if getattr(guild, 'owner', None) else "SABOTASH"
        items = [
            ("ВЛАДЕЛЕЦ СЕРВЕРА", owner_name, "Администрация"),
            ("УЧАСТНИКИ И РОЛИ", f"{guild.member_count:,} УЧАСТНИКОВ".replace(",", " "), f"Ролей: {len(guild.roles)}"),
            ("КАНАЛЫ СЕРВЕРА", f"{len(guild.channels)} КАНАЛОВ", f"Эмодзи: {len(guild.emojis)}"),
            ("БУСТ И ПРЕМИУМ", f"Уровень {guild.premium_tier}", f"{guild.premium_subscription_count} бустов")
        ]

    d.text((100, 26), title_text[:28], fill=BLACK, font=_f(True, 24))
    d.text((100, 56), sub_text, fill=MUTED, font=_f(False, 15))

    pill = _rounded_panel(156, 36, radius=10, fill=WHITE, outline=BLUE, ow=2)
    bg.alpha_composite(pill, (724, 38))
    d.text((742, 46), "SYSTEM v4.0", fill=BLUE, font=_f(True, 14))

    box_w, box_h = 426, 110
    gap_x, gap_y = 20, 14
    start_x, start_y = 24, 106

    for idx, (title, sub, note) in enumerate(items):
        c = idx % 2
        r = idx // 2
        bx = start_x + c * (box_w + gap_x)
        by = start_y + r * (box_h + gap_y)

        box = _rounded_panel(box_w, box_h, radius=14, fill=WHITE, outline=BLACK, ow=2)
        bg.alpha_composite(box, (bx, by))

        ibadge = _icon_badge(64, _icon_tech, ring_color=BLACK, ring_w=2, icon_color=BLUE)
        bg.alpha_composite(ibadge, (bx + 16, by + 23))

        d.text((bx + 94, by + 18), title, fill=BLACK, font=_f(True, 23))
        d.text((bx + 94, by + 50), sub, fill=BLUE, font=_f(True, 17))
        d.text((bx + 94, by + 78), note, fill=MUTED, font=_f(False, 15))

    br = _corner_bracket(40, 4, color=BLUE)
    bg.alpha_composite(br, (6, 6))
    bg.alpha_composite(br.rotate(270), (W - 46, 6))
    bg.alpha_composite(br.rotate(90), (6, H - 46))
    bg.alpha_composite(br.rotate(180), (W - 46, H - 46))

    return bg


def generate_info_bytes(guild: discord.Guild, member: discord.Member = None, category: str = "server") -> io.BytesIO:
    card = generate_info_card(guild, member, category).convert('RGB')
    buf = io.BytesIO()
    card.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf


class InfoSelect(discord.ui.Select):
    def __init__(self, guild, member, current_cat="server"):
        self.guild_obj = guild
        self.member_obj = member
        options = [
            discord.SelectOption(
                label="Информация о сервере",
                value="server",
                description="Статистика участников, ролей и каналов",
                emoji="🌐",
                default=(current_cat == "server")
            ),
            discord.SelectOption(
                label="Информация об участнике",
                value="user",
                description="Просмотр профиля, даты регистрации и ролей",
                emoji="👤",
                default=(current_cat == "user")
            )
        ]
        super().__init__(
            placeholder="📂 Выберите категорию информации...",
            options=options,
            custom_id="info_select_v4_pro"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cat_id = self.values[0]
        img_buf = await interaction.client.loop.run_in_executor(
            None, generate_info_bytes, self.guild_obj, interaction.user, cat_id
        )
        file = discord.File(img_buf, filename="info_card.png")
        view = InfoView(self.guild_obj, interaction.user, current_cat=cat_id)
        await interaction.edit_original_response(embed=None, attachments=[file], view=view)


class InfoView(discord.ui.View):
    def __init__(self, guild, member, current_cat="server"):
        super().__init__(timeout=300)
        self.add_item(InfoSelect(guild, member, current_cat=current_cat))


class UtilityCog(commands.Cog):
    """Utility команды"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='ping', aliases=['gecikme'])
    async def ping(self, ctx):
        """Botun gecikme süresini göster"""
        websocket_ping = round(self.bot.latency * 1000)
        await ctx.send(f"**Aether Bot System** • Задержка: `{websocket_ping}ms`")

    @commands.command(name='serverinfo', aliases=['server', 'сервер', 'sunucu'])
    async def serverinfo(self, ctx):
        """Профессиональная карточка информации о сервере"""
        img_buf = await self.bot.loop.run_in_executor(
            None, generate_info_bytes, ctx.guild, ctx.author, "server"
        )
        file = discord.File(img_buf, filename="info_card.png")
        view = InfoView(ctx.guild, ctx.author, current_cat="server")
        await ctx.send(file=file, view=view)

    @commands.command(name='userinfo', aliases=['user', 'пользователь'])
    async def userinfo(self, ctx, member: discord.Member = None):
        """Профессиональная карточка информации об участнике"""
        member = member or ctx.author
        img_buf = await self.bot.loop.run_in_executor(
            None, generate_info_bytes, ctx.guild, member, "user"
        )
        file = discord.File(img_buf, filename="info_card.png")
        view = InfoView(ctx.guild, member, current_cat="user")
        await ctx.send(file=file, view=view)


async def setup(bot):
    await bot.add_cog(UtilityCog(bot))
    
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
