"""
Profile Cog — Генерация карточки профиля через Pillow
Glassmorphism, фиолетовый неон, фоновое изображение
Данные подтягиваются из economy DB, leaderboard, voice tracker, gamification
"""
import discord
from discord.ext import commands
from discord import app_commands
import os
import io
import json
import math
import aiohttp
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from logger import get_logger
from db import UserData, GuildData

log = get_logger("profile")

# ── Пути ──────────────────────────────────────────────────────────────────────
FONTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'fonts')
FONT_BOLD = os.path.join(FONTS_DIR, 'Bold.ttf')
FONT_REG = os.path.join(FONTS_DIR, 'Regular.ttf')
DATA_DIR = 'data'

# ── Цвета ─────────────────────────────────────────────────────────────────────
NEON = (160, 70, 255)
NEON_BRIGHT = (200, 120, 255)
NEON_DIM = (100, 40, 180)
WHITE = (255, 255, 255)
LIGHT = (220, 210, 255)
DIM = (140, 130, 170)
PANEL_BG = (25, 20, 45, 190)
PANEL_BORDER = (160, 70, 255, 100)
STAT_BG = (35, 28, 60, 200)
XP_BG = (40, 35, 65)
XP_START = (120, 50, 200)
XP_END = (220, 100, 255)

# ── Размеры ───────────────────────────────────────────────────────────────────
W, H = 900, 480
LEFT_W = 240
GAP = 16
RX = LEFT_W + GAP + 16
RW = W - RX - 16


def _font(bold=False, size=20):
    try:
        return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)
    except Exception:
        return ImageFont.load_default()


def _rounded_rect(img, xy, radius, fill, outline=None, outline_w=1):
    """Нарисовать полупрозрачный прямоугольник с закруглёнными углами"""
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=outline_w)
    return Image.alpha_composite(img, overlay)


def _glow(img, xy, color, radius=40):
    """Нарисовать свечение"""
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    cx = (xy[0] + xy[2]) // 2
    cy = (xy[1] + xy[3]) // 2
    rw = (xy[2] - xy[0]) // 2
    rh = (xy[3] - xy[1]) // 2
    d.ellipse((cx - rw, cy - rh, cx + rw, cy + rh), fill=(*color, 30))
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius))
    return Image.alpha_composite(img, overlay)


def _text_center_x(draw, text, font, x1, x2):
    """Центрировать текст по X"""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    return x1 + (x2 - x1 - tw) // 2


def _progress_bar(w, h, progress):
    """Градиентный прогресс-бар с закруглениями"""
    bar = Image.new('RGBA', (w, h), XP_BG + (255,))
    fill_w = max(0, int(w * min(progress, 1.0)))
    if fill_w > 0:
        for x in range(fill_w):
            t = x / max(w - 1, 1)
            r = int(XP_START[0] + (XP_END[0] - XP_START[0]) * t)
            g = int(XP_START[1] + (XP_END[1] - XP_START[1]) * t)
            b = int(XP_START[2] + (XP_END[2] - XP_START[2]) * t)
            ImageDraw.Draw(bar).line([(x, 0), (x, h - 1)], fill=(r, g, b, 255))
    # Закругление
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=h // 2, fill=255)
    bar.putalpha(mask)
    return bar


def _generate_bg(w, h):
    """Генерация фонового изображения"""
    img = Image.new('RGBA', (w, h), (12, 10, 24, 255))
    draw = ImageDraw.Draw(img)

    # Градиент сверху-вниз
    for y in range(h):
        t = y / h
        r = int(12 + 8 * t)
        g = int(10 + 5 * t)
        b = int(24 + 15 * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b, 255))

    # Неоновые свечения
    img = _glow(img, (-80, -80, 300, 300), NEON, 80)
    img = _glow(img, (600, 250, 1000, 600), NEON_DIM, 70)
    img = _glow(img, (350, -50, 600, 150), (80, 40, 160), 50)

    # Тонкая сетка
    grid_overlay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid_overlay)
    for x in range(0, w, 40):
        gd.line([(x, 0), (x, h)], fill=(255, 255, 255, 6), width=1)
    for y in range(0, h, 40):
        gd.line([(0, y), (w, y)], fill=(255, 255, 255, 6), width=1)
    img = Image.alpha_composite(img, grid_overlay)

    return img


async def _download_avatar(url, size=200):
    """Скачать аватар и обрезать в круг"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.read()
        avatar = Image.open(io.BytesIO(data)).convert('RGBA')
        avatar = avatar.resize((size, size), Image.Resampling.LANCZOS)
        mask = Image.new('L', (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
        avatar.putalpha(mask)
        return avatar
    except Exception as e:
        log.error(f"Ошибка аватара: {e}")
        avatar = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(avatar).ellipse((0, 0, size, size), fill=(60, 50, 90, 255))
        return avatar


def _fmt(n):
    """Форматировать число: 12345 -> 12 345"""
    return f"{n:,}".replace(",", " ")


def _fmt_time(seconds):
    """Форматировать время: секунды -> Xч Yмин"""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h}ч {m}мин"
    return f"{m}мин"


# ══════════════════════════════════════════════════════════════════════════════
# Генерация карточки
# ══════════════════════════════════════════════════════════════════════════════

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

    # ── Фон ──────────────────────────────────────────────────────────────
    img = _generate_bg(W, H)
    draw = ImageDraw.Draw(img)

    # ── Левая панель (Пользователь) ─────────────────────────────────────
    lx, ly = 16, 16
    img = _rounded_rect(img, (lx, ly, lx + LEFT_W, H - 16), 18, PANEL_BG, PANEL_BORDER, 2)
    draw = ImageDraw.Draw(img)

    # Аватар с неоновым кольцом
    av_size = 150
    av_x = lx + (LEFT_W - av_size) // 2
    av_y = ly + 40

    # Внешнее свечение кольца
    ring_glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    rgd = ImageDraw.Draw(ring_glow)
    pad = 12
    rgd.ellipse(
        (av_x - pad, av_y - pad, av_x + av_size + pad, av_y + av_size + pad),
        outline=(*NEON, 50), width=10
    )
    ring_glow = ring_glow.filter(ImageFilter.GaussianBlur(8))
    img = Image.alpha_composite(img, ring_glow)
    draw = ImageDraw.Draw(img)

    # Кольцо
    draw.ellipse(
        (av_x - 5, av_y - 5, av_x + av_size + 5, av_y + av_size + 5),
        outline=NEON, width=3
    )

    # Аватар
    img.paste(avatar, (av_x, av_y), avatar)

    # Никнейм
    f_nick = _font(bold=True, size=24)
    nick_x = _text_center_x(draw, nickname, f_nick, lx, lx + LEFT_W)
    nick_y = av_y + av_size + 20
    draw.text((nick_x, nick_y), nickname, fill=WHITE, font=f_nick)

    # Разделитель
    line_y = nick_y + 38
    draw.line((lx + 25, line_y, lx + LEFT_W - 25, line_y), fill=(*NEON, 80), width=1)

    # Ранг пользователя
    f_rank_label = _font(bold=False, size=13)
    f_rank_val = _font(bold=True, size=20)

    # Общий ранг (средний из трёх)
    avg_rank = max(1, (rank_messages + rank_voice + rank_balance) // 3)
    rank_text = f"#{avg_rank}"
    rx_rank = _text_center_x(draw, "РАНГ НА СЕРВЕРЕ", f_rank_label, lx, lx + LEFT_W)
    draw.text((rx_rank, line_y + 15), "РАНГ НА СЕРВЕРЕ", fill=DIM, font=f_rank_label)
    rv_x = _text_center_x(draw, rank_text, f_rank_val, lx, lx + LEFT_W)
    draw.text((rv_x, line_y + 32), rank_text, fill=NEON_BRIGHT, font=f_rank_val)

    # ── Правая верхняя панель (Уровень) ─────────────────────────────────
    top_h = 155
    ty = 16
    img = _rounded_rect(img, (RX, ty, W - 16, ty + top_h), 18, PANEL_BG, PANEL_BORDER, 2)
    draw = ImageDraw.Draw(img)

    # "УРОВЕНЬ" + число
    f_lvl_label = _font(bold=True, size=14)
    f_lvl_num = _font(bold=True, size=56)
    f_xp = _font(bold=False, size=14)

    draw.text((RX + 28, ty + 20), "УРОВЕНЬ", fill=LIGHT, font=f_lvl_label)
    draw.text((RX + 28, ty + 40), str(level), fill=WHITE, font=f_lvl_num)

    # XP
    xp_str = _fmt(xp)
    xp_max_str = _fmt(xp_needed)
    bar_y = ty + top_h - 42
    draw.text((RX + 28, bar_y - 20), f"{xp_str} XP", fill=WHITE, font=f_xp)
    xp_max_bbox = draw.textbbox((0, 0), xp_max_str, font=f_xp)
    xp_max_w = xp_max_bbox[2] - xp_max_bbox[0]
    draw.text((W - 16 - 28 - xp_max_w, bar_y - 20), f"{xp_max_str} XP", fill=DIM, font=f_xp)

    # Прогресс-бар
    bar_w = RW - 40
    bar_h = 14
    progress = xp / xp_needed if xp_needed > 0 else 0
    bar_img = _progress_bar(bar_w, bar_h, progress)
    img.paste(bar_img, (RX + 28, bar_y), bar_img)
    draw = ImageDraw.Draw(img)

    # Процент
    pct_text = f"{int(progress * 100)}%"
    pct_bbox = draw.textbbox((0, 0), pct_text, font=f_xp)
    pct_w = pct_bbox[2] - pct_bbox[0]
    draw.text((RX + 28 + bar_w // 2 - pct_w // 2, bar_y + bar_h + 4), pct_text, fill=DIM, font=f_xp)

    # ── Правая нижняя зона (Статистика + Рейтинг) ───────────────────────
    by = ty + top_h + GAP
    bh = H - by - 16
    pw = (RW - GAP) // 2

    # СТАТИСТИКА
    img = _rounded_rect(img, (RX, by, RX + pw, by + bh), 16, PANEL_BG, PANEL_BORDER, 2)
    draw = ImageDraw.Draw(img)

    f_title = _font(bold=True, size=13)
    f_val = _font(bold=True, size=20)
    f_label = _font(bold=False, size=10)
    f_icon = _font(bold=True, size=18)

    # Заголовок
    tx = _text_center_x(draw, "СТАТИСТИКА", f_title, RX, RX + pw)
    draw.text((tx, by + 10), "СТАТИСТИКА", fill=LIGHT, font=f_title)

    stat_items = [
        (">", _fmt(messages), "СООБЩЕНИЙ"),
        ("V", _fmt_time(voice_seconds), "В ГОЛОСОВЫХ"),
        ("$", f"${_fmt(balance)}", "БАЛАНС"),
    ]
    block_h = (bh - 40) // 3
    for i, (icon, value, label) in enumerate(stat_items):
        bx = RX + 8
        bby = by + 32 + i * block_h
        bw = pw - 16
        bhi = block_h - 5

        img = _rounded_rect(img, (bx, bby, bx + bw, bby + bhi), 10, STAT_BG)
        draw = ImageDraw.Draw(img)

        # Иконка (символ)
        draw.text((bx + 12, bby + 6), icon, fill=NEON_BRIGHT, font=f_icon)
        # Значение
        draw.text((bx + 38, bby + 6), value, fill=WHITE, font=f_val)
        # Подпись
        draw.text((bx + 38, bby + bhi - 16), label, fill=DIM, font=f_label)

    # РЕЙТИНГ
    rkx = RX + pw + GAP
    img = _rounded_rect(img, (rkx, by, rkx + pw, by + bh), 16, PANEL_BG, PANEL_BORDER, 2)
    draw = ImageDraw.Draw(img)

    # Заголовок
    tx = _text_center_x(draw, "РЕЙТИНГ", f_title, rkx, rkx + pw)
    draw.text((tx, by + 10), "РЕЙТИНГ", fill=LIGHT, font=f_title)

    rank_items = [
        (">", f"#{rank_messages}", "СООБЩЕНИЙ"),
        ("V", f"#{rank_voice}", "В ГОЛОСОВЫХ"),
        ("$", f"#{rank_balance}", "БАЛАНС"),
    ]
    for i, (icon, value, label) in enumerate(rank_items):
        bx = rkx + 8
        bby = by + 32 + i * block_h
        bw = pw - 16
        bhi = block_h - 5

        img = _rounded_rect(img, (bx, bby, bx + bw, bby + bhi), 10, STAT_BG)
        draw = ImageDraw.Draw(img)

        draw.text((bx + 12, bby + 6), icon, fill=NEON_BRIGHT, font=f_icon)
        draw.text((bx + 38, bby + 6), value, fill=NEON_BRIGHT, font=f_val)
        draw.text((bx + 38, bby + bhi - 16), label, fill=DIM, font=f_label)

    return img.convert('RGB')


# ══════════════════════════════════════════════════════════════════════════════
# Данные пользователя
# ══════════════════════════════════════════════════════════════════════════════

def _load_leaderboard(guild_id: int) -> dict:
    """Загрузить данные из leaderboard JSON"""
    path = os.path.join(DATA_DIR, f'leaderboard_{guild_id}.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'messages': {}, 'voice_minutes': {}}


def _load_voice_stats(guild_id: int) -> dict:
    """Загрузить данные из voice_stats JSON"""
    path = os.path.join(DATA_DIR, f'voice_stats_{guild_id}.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'users': {}}


def _get_rank(sorted_list: list, user_id: str) -> int:
    """Найти ранг пользователя в отсортированном списке"""
    for i, (uid, _) in enumerate(sorted_list):
        if uid == user_id:
            return i + 1
    return len(sorted_list) + 1


# ══════════════════════════════════════════════════════════════════════════════
# Cog
# ══════════════════════════════════════════════════════════════════════════════

class ProfileCog(commands.Cog):
    """Карточка профиля"""

    def __init__(self, bot):
        self.bot = bot
        self.economy_db = UserData("economy")

    def _get_user_data(self, guild_id: int, user_id: int):
        """Собрать все данные пользователя"""
        uid = str(user_id)
        gid = guild_id

        # 1. Сообщения из leaderboard
        lb = _load_leaderboard(gid)
        messages = lb.get('messages', {}).get(uid, 0)

        # 2. Голосовое время — пробуем несколько источников
        voice_seconds = 0

        # Из voice_stats JSON
        vs = _load_voice_stats(gid)
        user_vs = vs.get('users', {}).get(uid, {})
        if isinstance(user_vs, dict):
            voice_seconds = user_vs.get('total_seconds', 0)

        # Fallback: leaderboard voice_minutes
        if voice_seconds == 0:
            voice_mins = lb.get('voice_minutes', {}).get(uid, 0)
            voice_seconds = voice_mins * 60

        # 3. Баланс из economy DB
        eco_data = self.economy_db.get(user_id)
        balance = 0
        if eco_data and isinstance(eco_data, dict):
            balance = eco_data.get('balance', 0) + eco_data.get('bank', 0)

        # 4. Уровень из gamification
        level = 1
        xp = 0
        xp_needed = 200
        try:
            from services.gamification import level_system, points_system
            level_data = level_system.get_level(user_id)
            if isinstance(level_data, dict):
                level = level_data.get('level', 1)
            elif isinstance(level_data, int):
                level = level_data
            xp = points_system.get_points(user_id)
            xp_needed = 100 + (level ** 2) * 50
        except Exception:
            # Fallback
            xp_needed = 100 + (level ** 2) * 50

        # 5. Ранги
        msg_sorted = sorted(lb.get('messages', {}).items(), key=lambda x: x[1], reverse=True)
        voice_sorted = sorted(
            {k: v * 60 for k, v in lb.get('voice_minutes', {}).items()}.items(),
            key=lambda x: x[1], reverse=True
        )
        # Если voice_stats JSON есть — используем его для ранга
        if vs.get('users'):
            voice_sorted = sorted(
                {k: v.get('total_seconds', 0) for k, v in vs['users'].items() if isinstance(v, dict)}.items(),
                key=lambda x: x[1], reverse=True
            )

        # Balance ranking
        all_eco = self.economy_db.get_all()
        balance_sorted = sorted(
            [(str(uid), d.get('balance', 0) + d.get('bank', 0))
             for uid, d in all_eco.items() if isinstance(d, dict)],
            key=lambda x: x[1], reverse=True
        )

        rank_messages = _get_rank(msg_sorted, uid)
        rank_voice = _get_rank(voice_sorted, uid)
        rank_balance = _get_rank(balance_sorted, uid)

        return {
            'level': level,
            'xp': xp,
            'xp_needed': xp_needed,
            'messages': messages,
            'voice_seconds': voice_seconds,
            'balance': balance,
            'rank_messages': rank_messages,
            'rank_voice': rank_voice,
            'rank_balance': rank_balance,
        }

    @commands.command(name="profile", aliases=["профиль", "карточка", "me"])
    async def profile_cmd(self, ctx, member: discord.Member = None):
        """Карточка профиля"""
        member = member or ctx.author

        loading = discord.Embed(title="Загрузка профиля...", color=discord.Color.dark_grey())
        msg = await ctx.send(embed=loading)

        try:
            avatar = await _download_avatar(member.display_avatar.url)
            data = self._get_user_data(ctx.guild.id, member.id)

            card = generate_profile_card(
                avatar=avatar,
                nickname=member.display_name[:15],
                **data
            )

            buf = io.BytesIO()
            card.save(buf, format='PNG')
            buf.seek(0)

            await msg.delete()
            await ctx.send(file=discord.File(buf, filename='profile.png'))

        except Exception as e:
            log.error(f"Ошибка профиля: {e}")
            import traceback
            traceback.print_exc()
            await msg.edit(embed=discord.Embed(
                title="Ошибка", description="Не удалось сгенерировать профиль.",
                color=discord.Color.dark_grey()
            ))

    @app_commands.command(name="profile", description="Карточка профиля")
    async def profile_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        """Карточка профиля (slash)"""
        member = member or interaction.user
        await interaction.response.defer()

        try:
            avatar = await _download_avatar(member.display_avatar.url)
            data = self._get_user_data(interaction.guild.id, member.id)

            card = generate_profile_card(
                avatar=avatar,
                nickname=member.display_name[:15],
                **data
            )

            buf = io.BytesIO()
            card.save(buf, format='PNG')
            buf.seek(0)

            await interaction.followup.send(file=discord.File(buf, filename='profile.png'))

        except Exception as e:
            log.error(f"Ошибка профиля: {e}")
            await interaction.followup.send(embed=discord.Embed(
                title="Ошибка", description="Не удалось сгенерировать профиль.",
                color=discord.Color.dark_grey()
            ), ephemeral=True)


async def setup(bot):
    await bot.add_cog(ProfileCog(bot))
    log.info("ProfileCog загружен")
