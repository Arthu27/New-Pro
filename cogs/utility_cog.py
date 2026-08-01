"""
Utility Cog — Professional Dashboard/ID-Card Style via Pillow
Белый фон, тонкие чёрные линии, синие технические line-art иконки.
Технические карточки сервера и участников с переключением через Select Menu.
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import io
import os
import math
import asyncio
import random
from PIL import Image, ImageDraw, ImageFont
from cogs.menu_bg import load_menu_bg

from logger import get_logger
log = get_logger("utility_cog")

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
    bg = load_menu_bg(W, H, "blue")
    d = ImageDraw.Draw(bg)

    header_box = _rounded_panel(872, 72, radius=14, fill=WHITE, outline=BLACK, ow=2)
    bg.alpha_composite(header_box, (24, 20))

    badge = _icon_badge(52, _icon_tech, ring_color=BLACK, ring_w=2, icon_color=BLUE)
    bg.alpha_composite(badge, (36, 30))

    if category == "user" and member:
        title_text = f"УЧАСТНИК • {member.display_name.upper()}"
        joined_str = member.joined_at.strftime('%d.%m.%Y') if getattr(member, 'joined_at', None) else '---'
        sub_text = f"ID: {member.id} • НА СЕРВЕРЕ С {joined_str}"
        created_str = member.created_at.strftime('%d.%m.%Y') if getattr(member, 'created_at', None) else '---'
        top_role_name = getattr(getattr(member, 'top_role', None), 'name', '---')
        items = [
            ("АККАУНТ И ДАТА", f"Создан: {created_str}", "Статус в норме"),
            ("ВЫСШАЯ РОЛЬ", top_role_name, "Привилегии"),
            ("АКТИВНОСТЬ", f"Ролей: {len(getattr(member, 'roles', []))}", "Доступ на сервере"),
            ("ID ПОЛЬЗОВАТЕЛЯ", str(member.id), "Идентификатор")
        ]
    else:
        title_text = f"СЕРВЕР • {guild.name.upper()}"
        created_str = guild.created_at.strftime('%d.%m.%Y') if getattr(guild, 'created_at', None) else "01.08.2026"
        sub_text = f"ID: {guild.id} • СОЗДАН {created_str}"
        owner_name = getattr(guild.owner, 'display_name', "SABOTASH") if getattr(guild, 'owner', None) else "SABOTASH"
        items = [
            ("ВЛАДЕЛЕЦ СЕРВЕРА", owner_name, "Администрация"),
            ("УЧАСТНИКИ И РОЛИ", f"{getattr(guild, 'member_count', 0):,} УЧАСТНИКОВ".replace(",", " "), f"Ролей: {len(getattr(guild, 'roles', []))}"),
            ("КАНАЛЫ СЕРВЕРА", f"{len(getattr(guild, 'channels', []))} КАНАЛОВ", f"Эмодзи: {len(getattr(guild, 'emojis', []))}"),
            ("БУСТ И ПРЕМИУМ", f"Уровень {getattr(guild, 'premium_tier', 0)}", f"{getattr(guild, 'premium_subscription_count', 0)} бустов")
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
        """Задержка бота"""
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"**Aether Bot System** • Задержка: `{latency}ms`")

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

    @commands.command(name='weather', aliases=['hava'])
    async def weather(self, ctx, city: str):
        """Hava durumunu göster"""
        await ctx.send(f"**Погода** • Город `{city}`: Запрос обрабатывается...")

    @commands.command(name='translate', aliases=['çevir'])
    async def translate(self, ctx, target_lang: str, *, text: str):
        """Metin çevir"""
        await ctx.send(f"**Перевод** (`{target_lang}`): {text}")

    @commands.command(name='util-giveaway', aliases=['çekiliş'])
    @commands.has_permissions(manage_guild=True)
    async def giveaway(self, ctx, duration: int, unit: str = 'm', *, prize: str):
        """Çekiliş создать (Utility)"""
        await ctx.send(f"**Розыгрыш** • Приз: `{prize}` (Длительность: {duration}{unit})")

    @commands.command(name='util-botinfo')
    async def botinfo(self, ctx):
        """Bot информации (Utility)"""
        await ctx.send("**Aether Bot System** • Профессиональное управление сервером v4.0")

    @commands.command(name='util-help')
    async def util_help(self, ctx):
        """Справка (Utility)"""
        await ctx.send("Используйте главную команду **`!help`** или **`/help`** для открытия меню справки.")


async def setup(bot):
    await bot.add_cog(UtilityCog(bot))
    log.info("UtilityCog loaded")
