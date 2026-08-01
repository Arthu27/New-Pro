"""
Profile Cog — Генерация карточки профиля через Pillow
Glassmorphism стиль, фиолетовый неоновый акцент, тёмный фон
"""
import discord
from discord.ext import commands
from discord import app_commands
import os
import io
import aiohttp
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from logger import get_logger
from db import UserData

log = get_logger("profile")

# ── Пути ──────────────────────────────────────────────────────────────────────
FONTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'fonts')
FONT_BOLD = os.path.join(FONTS_DIR, 'Bold.ttf')
FONT_REG = os.path.join(FONTS_DIR, 'Regular.ttf')

# ── Цвета ─────────────────────────────────────────────────────────────────────
COLOR_BG = (18, 18, 28)
COLOR_PANEL = (30, 30, 50, 180)
COLOR_PANEL_BORDER = (160, 80, 240, 120)
COLOR_NEON = (184, 84, 245)
COLOR_NEON_BRIGHT = (200, 120, 255)
COLOR_WHITE = (255, 255, 255)
COLOR_LIGHT_PURPLE = (200, 180, 255)
COLOR_XP_BG = (40, 40, 60)
COLOR_XP_FILL_START = (140, 60, 220)
COLOR_XP_FILL_END = (200, 100, 255)
COLOR_STAT_BG = (35, 35, 55, 200)

# ── Размеры карточки ─────────────────────────────────────────────────────────
CARD_W, CARD_H = 900, 500
LEFT_W = 260
RIGHT_X = LEFT_W + 20
RIGHT_W = CARD_W - RIGHT_X - 20


def _load_font(bold: bool = False, size: int = 20) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REG
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _draw_rounded_rect(draw: ImageDraw.Draw, xy, radius, fill=None, outline=None, width=1):
    """Нарисовать прямоугольник с закруглёнными углами"""
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def _draw_glow(img: Image.Image, xy, color, radius=20):
    """Нарисовать свечение"""
    glow = Image.new('RGBA', img.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(xy, fill=(*color[:3], 40))
    glow = glow.filter(ImageFilter.GaussianBlur(radius))
    return Image.alpha_composite(img, glow)


def _make_progress_bar(width, height, progress, fill_start, fill_end, bg_color):
    """Создать градиентный прогресс-бар"""
    bar = Image.new('RGBA', (width, height), bg_color)
    fill_w = int(width * min(progress, 1.0))
    if fill_w > 0:
        for x in range(fill_w):
            r = int(fill_start[0] + (fill_end[0] - fill_start[0]) * (x / width))
            g = int(fill_start[1] + (fill_end[1] - fill_start[1]) * (x / width))
            b = int(fill_start[2] + (fill_end[2] - fill_start[2]) * (x / width))
            for y in range(height):
                bar.putpixel((x, y), (r, g, b, 255))
    return bar


async def _download_avatar(url: str, size: int = 200) -> Image.Image:
    """Скачать и обрезать аватар в круг"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.read()
        avatar = Image.open(io.BytesIO(data)).convert('RGBA')
        avatar = avatar.resize((size, size), Image.Resampling.LANCZOS)

        # Обрезать в круг
        mask = Image.new('L', (size, size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, size, size), fill=255)
        avatar.putalpha(mask)
        return avatar
    except Exception as e:
        log.error(f"Ошибка загрузки аватара: {e}")
        # Пустой круг как fallback
        avatar = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(avatar)
        draw.ellipse((0, 0, size, size), fill=(80, 80, 120, 255))
        return avatar


def _format_number(n: int) -> str:
    """Форматировать число с пробелами: 12345 -> 12 345"""
    return f"{n:,}".replace(",", " ")


def _format_time(seconds: int) -> str:
    """Форматировать секунды в часы и минуты"""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}ч {m}мин"


def generate_profile_card(
    avatar: Image.Image,
    nickname: str,
    level: int,
    xp: int,
    xp_needed: int,
    messages: int,
    voice_seconds: int,
    balance: int,
    rank_messages: int,
    rank_voice: int,
    rank_balance: int,
) -> Image.Image:
    """Генерация карточки профиля"""

    img = Image.new('RGBA', (CARD_W, CARD_H), COLOR_BG + (255,))
    draw = ImageDraw.Draw(img)

    # ── Фоновые свечения ────────────────────────────────────────────────
    img = _draw_glow(img, (-50, -50, 250, 250), COLOR_NEON, 60)
    img = _draw_glow(img, (650, 300, 950, 600), COLOR_NEON, 50)
    draw = ImageDraw.Draw(img)

    # ── Левая панель (пользователь) ─────────────────────────────────────
    left_panel = Image.new('RGBA', (CARD_W, CARD_H), (0, 0, 0, 0))
    lp_draw = ImageDraw.Draw(left_panel)
    lp_draw.rounded_rectangle((15, 15, LEFT_W + 15, CARD_H - 15), radius=20, fill=COLOR_PANEL, outline=COLOR_PANEL_BORDER, width=2)
    img = Image.alpha_composite(img, left_panel)
    draw = ImageDraw.Draw(img)

    # Аватар с неоновым кольцом
    avatar_size = 160
    avatar_x = 15 + (LEFT_W - avatar_size) // 2
    avatar_y = 50

    # Неоновое кольцо
    ring_padding = 8
    draw.ellipse(
        (avatar_x - ring_padding, avatar_y - ring_padding,
         avatar_x + avatar_size + ring_padding, avatar_y + avatar_size + ring_padding),
        outline=COLOR_NEON, width=4
    )
    # Свечение кольца
    ring_glow = Image.new('RGBA', (CARD_W, CARD_H), (0, 0, 0, 0))
    rg_draw = ImageDraw.Draw(ring_glow)
    rg_draw.ellipse(
        (avatar_x - ring_padding - 4, avatar_y - ring_padding - 4,
         avatar_x + avatar_size + ring_padding + 4, avatar_y + avatar_size + ring_padding + 4),
        outline=(*COLOR_NEON, 60), width=8
    )
    ring_glow = ring_glow.filter(ImageFilter.GaussianBlur(6))
    img = Image.alpha_composite(img, ring_glow)
    draw = ImageDraw.Draw(img)

    # Вставить аватар
    img.paste(avatar, (avatar_x, avatar_y), avatar)

    # Никнейм
    font_nick = _load_font(bold=True, size=26)
    nick_bbox = draw.textbbox((0, 0), nickname, font=font_nick)
    nick_w = nick_bbox[2] - nick_bbox[0]
    nick_x = 15 + (LEFT_W - nick_w) // 2
    nick_y = avatar_y + avatar_size + 25
    draw.text((nick_x, nick_y), nickname, fill=COLOR_WHITE, font=font_nick)

    # Разделитель
    line_y = nick_y + 40
    draw.line((35, line_y, LEFT_W - 5, line_y), fill=(*COLOR_NEON, 100), width=1)

    # Подпись
    font_small = _load_font(bold=False, size=14)
    draw.text((15 + (LEFT_W - 100) // 2, line_y + 15), "ПРОФИЛЬ", fill=COLOR_LIGHT_PURPLE, font=font_small)

    # ── Правая верхняя панель (уровень) ─────────────────────────────────
    top_h = 180
    top_panel = Image.new('RGBA', (CARD_W, CARD_H), (0, 0, 0, 0))
    tp_draw = ImageDraw.Draw(top_panel)
    tp_draw.rounded_rectangle((RIGHT_X, 15, CARD_W - 20, 15 + top_h), radius=20, fill=COLOR_PANEL, outline=COLOR_PANEL_BORDER, width=2)
    img = Image.alpha_composite(img, top_panel)
    draw = ImageDraw.Draw(img)

    # "УРОВЕНЬ" + число
    font_level_label = _load_font(bold=True, size=18)
    font_level_num = _load_font(bold=True, size=64)

    draw.text((RIGHT_X + 30, 40), "УРОВЕНЬ", fill=COLOR_LIGHT_PURPLE, font=font_level_label)
    draw.text((RIGHT_X + 30, 70), str(level), fill=COLOR_WHITE, font=font_level_num)

    # XP текст
    font_xp = _load_font(bold=False, size=16)
    xp_text = _format_number(xp)
    xp_max_text = _format_number(xp_needed)
    bar_y = 15 + top_h - 45

    draw.text((RIGHT_X + 30, bar_y - 22), xp_text, fill=COLOR_WHITE, font=font_xp)
    xp_max_bbox = draw.textbbox((0, 0), xp_max_text, font=font_xp)
    xp_max_w = xp_max_bbox[2] - xp_max_bbox[0]
    draw.text((CARD_W - 20 - 30 - xp_max_w, bar_y - 22), xp_max_text, fill=COLOR_LIGHT_PURPLE, font=font_xp)

    # Прогресс-бар
    bar_w = CARD_W - RIGHT_X - 60 - 20
    bar_h = 16
    progress = xp / xp_needed if xp_needed > 0 else 0
    bar_img = _make_progress_bar(bar_w, bar_h, progress, COLOR_XP_FILL_START, COLOR_XP_FILL_END, COLOR_XP_BG)
    # Закруглить прогресс-бар
    bar_mask = Image.new('L', (bar_w, bar_h), 0)
    bar_mask_draw = ImageDraw.Draw(bar_mask)
    bar_mask_draw.rounded_rectangle((0, 0, bar_w, bar_h), radius=8, fill=255)
    bar_img.putalpha(bar_mask)
    img.paste(bar_img, (RIGHT_X + 30, bar_y), bar_img)

    # ── Правая нижняя зона (статистика + рейтинг) ───────────────────────
    bottom_y = 15 + top_h + 15
    bottom_h = CARD_H - bottom_y - 15
    panel_w = (CARD_W - RIGHT_X - 20 - 15) // 2

    # Левая мини-панель: СТАТИСТИКА
    stats_panel = Image.new('RGBA', (CARD_W, CARD_H), (0, 0, 0, 0))
    sp_draw = ImageDraw.Draw(stats_panel)
    sp_draw.rounded_rectangle((RIGHT_X, bottom_y, RIGHT_X + panel_w, bottom_y + bottom_h), radius=16, fill=COLOR_PANEL, outline=COLOR_PANEL_BORDER, width=2)
    img = Image.alpha_composite(img, stats_panel)
    draw = ImageDraw.Draw(img)

    font_title = _load_font(bold=True, size=15)
    font_value = _load_font(bold=True, size=22)
    font_label = _load_font(bold=False, size=11)

    # Заголовок
    draw.text((RIGHT_X + (panel_w - 100) // 2, bottom_y + 12), "СТАТИСТИКА", fill=COLOR_LIGHT_PURPLE, font=font_title)

    # Блоки статистики
    stat_items = [
        (f"{_format_number(messages)}", "СООБЩЕНИЙ"),
        (_format_time(voice_seconds), "ОНЛАЙН"),
        (f"${_format_number(balance)}", "БАЛАНС"),
    ]
    block_h = (bottom_h - 55) // 3
    for i, (value, label) in enumerate(stat_items):
        by = bottom_y + 38 + i * block_h
        bx = RIGHT_X + 10
        bw = panel_w - 20
        bh = block_h - 6

        block_panel = Image.new('RGBA', (CARD_W, CARD_H), (0, 0, 0, 0))
        bp_draw = ImageDraw.Draw(block_panel)
        bp_draw.rounded_rectangle((bx, by, bx + bw, by + bh), radius=10, fill=COLOR_STAT_BG)
        img = Image.alpha_composite(img, block_panel)
        draw = ImageDraw.Draw(img)

        draw.text((bx + 15, by + 8), value, fill=COLOR_WHITE, font=font_value)
        draw.text((bx + 15, by + bh - 18), label, fill=COLOR_LIGHT_PURPLE, font=font_label)

    # Правая мини-панель: РЕЙТИНГ
    rank_x = RIGHT_X + panel_w + 15
    rank_panel = Image.new('RGBA', (CARD_W, CARD_H), (0, 0, 0, 0))
    rp_draw = ImageDraw.Draw(rank_panel)
    rp_draw.rounded_rectangle((rank_x, bottom_y, rank_x + panel_w, bottom_y + bottom_h), radius=16, fill=COLOR_PANEL, outline=COLOR_PANEL_BORDER, width=2)
    img = Image.alpha_composite(img, rank_panel)
    draw = ImageDraw.Draw(img)

    # Заголовок
    draw.text((rank_x + (panel_w - 70) // 2, bottom_y + 12), "РЕЙТИНГ", fill=COLOR_LIGHT_PURPLE, font=font_title)

    rank_items = [
        (f"#{rank_messages}", "СООБЩЕНИЙ"),
        (f"#{rank_voice}", "ОНЛАЙН"),
        (f"#{rank_balance}", "БАЛАНС"),
    ]
    for i, (value, label) in enumerate(rank_items):
        by = bottom_y + 38 + i * block_h
        bx = rank_x + 10
        bw = panel_w - 20
        bh = block_h - 6

        block_panel = Image.new('RGBA', (CARD_W, CARD_H), (0, 0, 0, 0))
        bp_draw = ImageDraw.Draw(block_panel)
        bp_draw.rounded_rectangle((bx, by, bx + bw, by + bh), radius=10, fill=COLOR_STAT_BG)
        img = Image.alpha_composite(img, block_panel)
        draw = ImageDraw.Draw(img)

        draw.text((bx + 15, by + 8), value, fill=COLOR_NEON_BRIGHT, font=font_value)
        draw.text((bx + 15, by + bh - 18), label, fill=COLOR_LIGHT_PURPLE, font=font_label)

    return img.convert('RGB')


# ══════════════════════════════════════════════════════════════════════════════
# Cog
# ══════════════════════════════════════════════════════════════════════════════

class ProfileCog(commands.Cog):
    """Карточка профиля"""

    def __init__(self, bot):
        self.bot = bot
        self.economy_db = UserData("economy")
        self.voice_db = UserData("voice_stats")

    def _get_level_data(self, user_id: int) -> dict:
        """Получить данные уровня"""
        # Пробуем из level_cog
        level_cog = self.bot.get_cog("LevelCog") or self.bot.get_cog("Level")
        if level_cog and hasattr(level_cog, 'db'):
            data = level_cog.db.get(0, str(user_id))
            if data:
                return data
        # Fallback
        return {"xp": 0, "level": 1}

    def _get_xp_needed(self, level: int) -> int:
        """XP для следующего уровня"""
        return 100 + (level ** 2) * 50

    def _get_messages(self, guild_id: int, user_id: int) -> int:
        """Получить количество сообщений"""
        try:
            from db import GuildData
            db = GuildData("messages")
            data = db.get(guild_id, str(user_id), {})
            return data.get("count", 0) if isinstance(data, dict) else 0
        except Exception:
            return 0

    def _get_voice_time(self, guild_id: int, user_id: int) -> int:
        """Получить время в голосовых (секунды)"""
        try:
            from db import GuildData
            db = GuildData("voice_stats")
            data = db.get(guild_id, str(user_id), {})
            return data.get("total_seconds", 0) if isinstance(data, dict) else 0
        except Exception:
            return 0

    def _get_balance(self, user_id: int) -> int:
        """Получить баланс"""
        data = self.economy_db.get(user_id)
        if data and isinstance(data, dict):
            return data.get("balance", 0) + data.get("bank", 0)
        return 0

    def _get_rank(self, guild_id: int, field: str, user_id: int) -> int:
        """Получить ранг пользователя"""
        # Упрощённый расчёт ранга
        return 1  # Пока заглушка

    @commands.command(name="profile", aliases=["профиль", "карточка", "me"])
    async def profile_cmd(self, ctx, member: discord.Member = None):
        """Показать карточку профиля"""
        member = member or ctx.author

        # Показываем "загрузка"
        loading_embed = discord.Embed(
            title="Загрузка профиля...",
            color=discord.Color.dark_grey()
        )
        msg = await ctx.send(embed=loading_embed)

        try:
            # Собираем данные
            avatar = await _download_avatar(member.display_avatar.url)
            level_data = self._get_level_data(member.id)
            level = level_data.get("level", 1)
            xp = level_data.get("xp", 0)
            xp_needed = self._get_xp_needed(level)
            messages = self._get_messages(ctx.guild.id, member.id)
            voice_seconds = self._get_voice_time(ctx.guild.id, member.id)
            balance = self._get_balance(member.id)

            # Генерируем карточку
            card = generate_profile_card(
                avatar=avatar,
                nickname=member.display_name[:15],
                level=level,
                xp=xp,
                xp_needed=xp_needed,
                messages=messages,
                voice_seconds=voice_seconds,
                balance=balance,
                rank_messages=self._get_rank(ctx.guild.id, "messages", member.id),
                rank_voice=self._get_rank(ctx.guild.id, "voice", member.id),
                rank_balance=self._get_rank(ctx.guild.id, "balance", member.id),
            )

            # Отправляем
            buf = io.BytesIO()
            card.save(buf, format='PNG')
            buf.seek(0)
            file = discord.File(buf, filename='profile.png')

            await msg.delete()
            await ctx.send(file=file)

        except Exception as e:
            log.error(f"Ошибка генерации профиля: {e}")
            import traceback
            traceback.print_exc()
            embed = discord.Embed(
                title="Ошибка",
                description="Не удалось сгенерировать профиль.",
                color=discord.Color.dark_grey()
            )
            await msg.edit(embed=embed)

    @app_commands.command(name="profile", description="Карточка профиля")
    async def profile_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        """Карточка профиля (slash)"""
        member = member or interaction.user
        await interaction.response.defer()

        try:
            avatar = await _download_avatar(member.display_avatar.url)
            level_data = self._get_level_data(member.id)
            level = level_data.get("level", 1)
            xp = level_data.get("xp", 0)
            xp_needed = self._get_xp_needed(level)
            messages = self._get_messages(interaction.guild.id, member.id)
            voice_seconds = self._get_voice_time(interaction.guild.id, member.id)
            balance = self._get_balance(member.id)

            card = generate_profile_card(
                avatar=avatar,
                nickname=member.display_name[:15],
                level=level,
                xp=xp,
                xp_needed=xp_needed,
                messages=messages,
                voice_seconds=voice_seconds,
                balance=balance,
                rank_messages=self._get_rank(interaction.guild.id, "messages", member.id),
                rank_voice=self._get_rank(interaction.guild.id, "voice", member.id),
                rank_balance=self._get_rank(interaction.guild.id, "balance", member.id),
            )

            buf = io.BytesIO()
            card.save(buf, format='PNG')
            buf.seek(0)
            file = discord.File(buf, filename='profile.png')

            await interaction.followup.send(file=file)

        except Exception as e:
            log.error(f"Ошибка генерации профиля: {e}")
            embed = discord.Embed(
                title="Ошибка",
                description="Не удалось сгенерировать профиль.",
                color=discord.Color.dark_grey()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ProfileCog(bot))
    log.info("ProfileCog загружен")
