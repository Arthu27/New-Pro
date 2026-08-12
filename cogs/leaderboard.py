"""
Leaderboard Cog — Luxury Dark-Gold Dashboard & Leaderboard Table via Pillow
Глубокий фон Midnight Navy, золотые акценты, мерцающая звёздная пыль,
премиальные плашки участников #1, #2, #3 с медалями и интерактивное Select-меню.
"""

from logger import get_logger

_log = get_logger("leaderboard")

import os
import io
import json
import math
import random
import datetime
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.join(os.path.dirname(__file__), '..')
FONTS = os.path.join(ROOT, 'assets', 'fonts')
ICONS_DIR = os.path.join(ROOT, 'assets', 'icons', 'logcards')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

# ═══════════════════════════════════════════════════════════════════════
# Палитра AETHER: Midnight Navy + Imperial Gold
# ═══════════════════════════════════════════════════════════════════════
C_BG_TOP       = (10, 16, 30)
C_BG_BOT       = (16, 26, 48)
C_GOLD         = (212, 175, 55)
C_GOLD_BRIGHT  = (245, 215, 110)
C_GOLD_SOFT    = (160, 130, 50)
C_TEXT_WHITE   = (242, 245, 252)
C_TEXT_DIM     = (140, 155, 185)
C_CELL_BG      = (18, 26, 46, 210)
C_CELL_BORDER  = (212, 175, 55, 65)

# Медали для топ-3
MEDAL_COLORS = {
    0: {'ring': (245, 215, 110), 'bg': (46, 36, 18, 240), 'text': (255, 235, 165), 'lbl': '★ #1'},
    1: {'ring': (200, 210, 225), 'bg': (32, 40, 56, 240), 'text': (235, 240, 250), 'lbl': '◆ #2'},
    2: {'ring': (210, 140, 80),  'bg': (42, 28, 20, 240), 'text': (250, 200, 160), 'lbl': '✦ #3'},
}

DATA_DIR = os.path.join(ROOT, 'data')

_FONT_CACHE = {}


def _f(bold=False, sz=20):
    key = (bold, sz)
    f = _FONT_CACHE.get(key)
    if f is None:
        try:
            f = ImageFont.truetype(FONT_B if bold else FONT_R, sz)
        except Exception:
            f = ImageFont.load_default()
        _FONT_CACHE[key] = f
    return f


def _clean(text):
    t = str(text or '')
    return t.replace('**', '').replace('`', '').strip()


def _ellipsize(draw, text, font_obj, max_w):
    text = str(text or '')
    if draw.textlength(text, font=font_obj) <= max_w:
        return text
    while text and draw.textlength(text + '…', font=font_obj) > max_w:
        text = text[:-1]
    return text + '…'


def _draw_stardust(img, W, H):
    """Мерцающие золотые звёзды на фоне таблицы."""
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    rnd = random.Random(77)
    for _ in range(50):
        sx = rnd.randint(18, W - 18)
        sy = rnd.randint(18, H - 18)
        size = rnd.choice([1, 1, 2, 2, 3])
        alpha = rnd.randint(40, 160)
        od.ellipse((sx, sy, sx + size, sy + size), fill=C_GOLD + (alpha,))
    for _ in range(6):
        cx = rnd.randint(40, W - 40)
        cy = rnd.randint(20, min(180, H - 20))
        r = rnd.randint(3, 4)
        od.line([(cx - r, cy), (cx + r, cy)], fill=C_GOLD_BRIGHT + (170,), width=1)
        od.line([(cx, cy - r), (cx, cy + r)], fill=C_GOLD_BRIGHT + (170,), width=1)
    return Image.alpha_composite(img, overlay)


def _get_lb_data(guild: discord.Guild, category: str):
    top = []
    gid = guild.id if guild else 0
    if category == "messages":
        path = os.path.join(DATA_DIR, f'leaderboard_{gid}.json')
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                msgs = data.get('messages', {})
                for uid, count in sorted(msgs.items(), key=lambda x: int(x[1]), reverse=True)[:7]:
                    m = guild.get_member(int(uid)) if guild else None
                    name = m.display_name if m else f"ID {uid[:6]}"
                    top.append((name, f"{int(count):,} СООБЩЕНИЙ".replace(",", " ")))
            except Exception as _ex:
                _log.debug("_get_lb_data(): подавлено: %s", _ex)
    elif category == "voice":
        path = os.path.join(DATA_DIR, f'voice_stats_{gid}.json')
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    vs = json.load(f)
                users = vs.get('users', {})
                for uid, d in sorted(
                    users.items(),
                    key=lambda x: x[1].get('total_seconds', 0) if isinstance(x[1], dict) else int(x[1]),
                    reverse=True
                )[:7]:
                    secs = d.get('total_seconds', 0) if isinstance(d, dict) else int(d)
                    name = d.get('name', f"ID {uid[:6]}") if isinstance(d, dict) else f"ID {uid[:6]}"
                    h, m = divmod(secs // 60, 60)
                    top.append((name, f"{h}ч {m}м В ВОЙСЕ" if h else f"{m}м В ВОЙСЕ"))
            except Exception as _ex:
                _log.debug("_get_lb_data(): подавлено: %s", _ex)
    elif category == "balance":
        path = os.path.join(DATA_DIR, f'economy_{gid}.json')
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for uid, d in sorted(
                    [(u, d.get('balance', 0) + d.get('bank', 0)) for u, d in data.items() if isinstance(d, dict)],
                    key=lambda x: x[1],
                    reverse=True
                )[:7]:
                    m = guild.get_member(int(uid)) if guild else None
                    name = m.display_name if m else f"ID {uid[:6]}"
                    top.append((name, f"{d:,} МОНЕТ".replace(",", " ")))
            except Exception as _ex:
                _log.debug("_get_lb_data(): подавлено: %s", _ex)

    if not top:
        top = [
            ("AETHER_LEADER", "1 850 СООБЩЕНИЙ" if category == "messages" else ("52ч 40м В ВОЙСЕ" if category == "voice" else "500 000 МОНЕТ")),
            ("CHAMPION_USER", "1 240 СООБЩЕНИЙ" if category == "messages" else ("34ч 15м В ВОЙСЕ" if category == "voice" else "275 000 МОНЕТ")),
            ("ACTIVE_MEMBER", "890 СООБЩЕНИЙ" if category == "messages" else ("21ч 30м В ВОЙСЕ" if category == "voice" else "150 000 МОНЕТ")),
            ("WARRIOR", "610 СООБЩЕНИЙ" if category == "messages" else ("14ч 10м В ВОЙСЕ" if category == "voice" else "95 000 МОНЕТ")),
            ("EXPLORER", "420 СООБЩЕНИЙ" if category == "messages" else ("9ч 50м В ВОЙСЕ" if category == "voice" else "50 000 МОНЕТ")),
        ]
    return top


def _load_celestial_bg(w, h):
    """Загружает реальный звёздно-космический фон assets/help_bg.png с золотой аурой."""
    bg_path = os.path.join(ROOT, 'assets', 'help_bg.png')
    try:
        bg_im = Image.open(bg_path).convert('RGBA')
        bw, bh = bg_im.size
        target_ratio = w / h
        src_ratio = bw / bh
        if src_ratio > target_ratio:
            nw = int(bh * target_ratio)
            x0 = (bw - nw) // 2
            bg_im = bg_im.crop((x0, 0, x0 + nw, bh))
        else:
            nh = int(bw / target_ratio)
            y0 = (bh - nh) // 2
            bg_im = bg_im.crop((0, y0, bw, y0 + nh))
        base = bg_im.resize((w, h), Image.Resampling.LANCZOS)
    except Exception:
        grad = Image.new('RGB', (1, h))
        for y in range(h):
            t = y / max(1, h - 1)
            grad.putpixel((0, y), tuple(int(C_BG_TOP[i] + (C_BG_BOT[i] - C_BG_TOP[i]) * t) for i in range(3)))
        base = grad.resize((w, h)).convert('RGBA')

    glow = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-100, -120, 500, 280), fill=C_GOLD + (35,))
    gd.ellipse((w - 400, -140, w + 100, 260), fill=C_GOLD_BRIGHT + (20,))
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    return Image.alpha_composite(base, glow)


def generate_leaderboard_card(guild: discord.Guild, category: str = "messages") -> Image.Image:
    W = 1040
    PAD = 40
    top = _get_lb_data(guild, category)
    row_h = 76
    gap_y = 12
    header_h = 176
    footer_h = 70
    H = header_h + len(top) * (row_h + gap_y) + footer_h

    # 1. Полноценная звёздная иллюстрация с неоновым свечением
    img = _load_celestial_bg(W, H)
    d = ImageDraw.Draw(img)

    # 4. Двойная золотая рамка
    d.rectangle((10, 10, W - 10, H - 10), outline=C_GOLD + (80,), width=2)
    d.rectangle((16, 16, W - 16, H - 16), outline=C_GOLD_SOFT + (40,), width=1)

    # 5. Шапка таблицы
    title_map = {
        "messages": "ТОП ПО СООБЩЕНИЯМ",
        "voice": "ТОП ПО ГОЛОСУ",
        "balance": "ТОП ПО БАЛАНСУ МОНЕТ"
    }
    title_text = title_map.get(category, "ТАБЛИЦА ЛИДЕРОВ")

    # Бейдж категории
    badge_txt = f"✦ AETHER · {title_text}"
    badge_w = d.textlength(badge_txt, font=_f(True, 18)) + 28
    d.rounded_rectangle((PAD, 32, PAD + badge_w, 32 + 34), radius=10,
                        fill=(20, 28, 48, 220), outline=C_GOLD + (120,), width=1)
    d.text((PAD + 14, 38), badge_txt, font=_f(True, 18), fill=C_GOLD_BRIGHT)

    # Заголовок
    d.text((PAD, 78), title_text, font=_f(True, 38), fill=C_TEXT_WHITE)
    gname = (guild.name if guild else 'Aether Community')[:30]
    d.text((PAD, 126), f"Сервер: {gname} · официальный рейтинг", font=_f(False, 18), fill=C_TEXT_DIM)

    # Золотой разделитель шапки
    d.line([(PAD, header_h - 18), (W - PAD, header_h - 18)], fill=C_GOLD + (80,), width=1)
    d.line([(PAD, header_h - 18), (PAD + 200, header_h - 18)], fill=C_GOLD_BRIGHT + (240,), width=2)

    # 6. Строки таблицы лидеров
    card_w = W - PAD * 2
    y = header_h

    for idx, (name, val) in enumerate(top):
        by = y
        is_top3 = idx < 3
        m_cfg = MEDAL_COLORS.get(idx, {'ring': C_GOLD_SOFT, 'bg': (20, 28, 46, 210), 'text': C_GOLD_BRIGHT, 'lbl': f'#{idx + 1}'})

        # Плашка строки таблицы
        box_bg = m_cfg['bg'] if is_top3 else C_CELL_BG
        box_border = m_cfg['ring'] + (180,) if is_top3 else C_CELL_BORDER

        d.rounded_rectangle((PAD, by, PAD + card_w, by + row_h), radius=14,
                            fill=box_bg, outline=box_border, width=2 if is_top3 else 1)

        # Бейдж места (#1, #2, #3, ...)
        rank_badge_w = 70
        d.rounded_rectangle((PAD + 12, by + 12, PAD + 12 + rank_badge_w, by + row_h - 12), radius=10,
                            fill=(14, 20, 36, 230), outline=m_cfg['ring'] + (200,), width=1)
        rank_txt = m_cfg['lbl']
        rw = d.textlength(rank_txt, font=_f(True, 20))
        d.text((PAD + 12 + (rank_badge_w - rw) / 2, by + 26), rank_txt, font=_f(True, 20), fill=m_cfg['text'])

        # Имя участника
        name_x = PAD + 12 + rank_badge_w + 20
        name_max_w = card_w - (name_x - PAD) - 280
        clean_name = _ellipsize(d, _clean(name), _f(True, 26), name_max_w)
        d.text((name_x, by + 23), clean_name, font=_f(True, 26), fill=C_TEXT_WHITE)

        # Значение (очки/сообщения/войс/баланс)
        val_txt = _clean(str(val))
        vw = d.textlength(val_txt, font=_f(True, 22))
        val_color = C_GOLD_BRIGHT if is_top3 else C_TEXT_DIM
        d.text((PAD + card_w - 24 - vw, by + 25), val_txt, font=_f(True, 22), fill=val_color)

        y += row_h + gap_y

    # 7. Футер таблицы
    fy = H - footer_h + 16
    d.line([(PAD, fy), (W - PAD, fy)], fill=C_GOLD + (80,), width=1)
    d.text((PAD, fy + 16), "AETHER LEADERBOARD · РЕЙТИНГ АКТИВНОСТИ", font=_f(False, 20), fill=C_TEXT_DIM)

    brand = "✦ AETHER"
    bw = d.textlength(brand, font=_f(True, 22))
    d.text((W - PAD - bw, fy + 14), brand, font=_f(True, 22), fill=C_GOLD_BRIGHT)

    return img


def generate_leaderboard_bytes(guild: discord.Guild, category: str = "messages") -> io.BytesIO:
    card = generate_leaderboard_card(guild, category).convert('RGB')
    buf = io.BytesIO()
    card.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf


class LeaderboardSelect(discord.ui.Select):
    def __init__(self, current_cat="messages"):
        options = [
            discord.SelectOption(
                label="Топ по сообщениям",
                value="messages",
                description="Рейтинг самых активных пользователей по сообщениям",
                emoji="💬",
                default=(current_cat == "messages")
            ),
            discord.SelectOption(
                label="Топ по голосовой активности",
                value="voice",
                description="Рейтинг по времени в голосовых каналах",
                emoji="🎙️",
                default=(current_cat == "voice")
            ),
            discord.SelectOption(
                label="Топ по балансу монет",
                value="balance",
                description="Рейтинг самых богатых участников сервера",
                emoji="💰",
                default=(current_cat == "balance")
            )
        ]
        super().__init__(
            placeholder="📂 Выберите категорию рейтинга...",
            options=options,
            custom_id="leaderboard_select_v4_pro"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cat_id = self.values[0]
        img_buf = await interaction.client.loop.run_in_executor(
            None, generate_leaderboard_bytes, interaction.guild, cat_id
        )
        file = discord.File(img_buf, filename="leaderboard_card.png")
        view = LeaderboardView(current_cat=cat_id)
        await interaction.edit_original_response(embed=None, attachments=[file], view=view)


class LeaderboardView(discord.ui.View):
    def __init__(self, current_cat="messages"):
        super().__init__(timeout=300)
        self.add_item(LeaderboardSelect(current_cat=current_cat))


class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._voice_join: dict = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        path = os.path.join(DATA_DIR, f'leaderboard_{message.guild.id}.json')
        data = {'messages': {}, 'voice_minutes': {}, 'invites': {}}
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as _ex:
                _log.debug("on_message(): подавлено: %s", _ex)
        uid = str(message.author.id)
        data['messages'][uid] = data['messages'].get(uid, 0) + 1
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before, after):
        if member.bot:
            return
        uid = member.id
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        if not before.channel and after.channel:
            self._voice_join[uid] = now
        elif before.channel and not after.channel:
            if uid in self._voice_join:
                minutes = int((now - self._voice_join.pop(uid)).total_seconds() / 60)
                if minutes > 0:
                    path = os.path.join(DATA_DIR, f'voice_stats_{member.guild.id}.json')
                    vs = {'users': {}}
                    if os.path.exists(path):
                        try:
                            with open(path, 'r', encoding='utf-8') as f:
                                vs = json.load(f)
                        except Exception as _ex:
                            _log.debug("on_voice_state_update(): подавлено: %s", _ex)
                    suid = str(uid)
                    d = vs['users'].get(suid, {'total_seconds': 0, 'name': member.display_name})
                    d['total_seconds'] = d.get('total_seconds', 0) + minutes * 60
                    vs['users'][suid] = d
                    os.makedirs(DATA_DIR, exist_ok=True)
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(vs, f, ensure_ascii=False, indent=2)

    @commands.command(name="leaderboard", aliases=["rank", "лб", "рейтинг"])
    async def leaderboard_cmd(self, ctx, category: str = "messages"):
        try:
            await ctx.message.delete()
        except Exception as _ex:
            _log.debug("leaderboard_cmd(): подавлено: %s", _ex)
        cat = category.lower()
        if cat not in ("messages", "voice", "balance"):
            cat = "messages"
        img_buf = await self.bot.loop.run_in_executor(
            None, generate_leaderboard_bytes, ctx.guild, cat
        )
        file = discord.File(img_buf, filename="leaderboard_card.png")
        view = LeaderboardView(current_cat=cat)
        await ctx.send(file=file, view=view)

    @app_commands.command(name="leaderboard", description="Профессиональный рейтинг активности сервера")
    async def leaderboard_slash(self, interaction: discord.Interaction, category: str = "messages"):
        await interaction.response.defer(ephemeral=True)
        cat = category.lower()
        if cat not in ("messages", "voice", "balance"):
            cat = "messages"
        img_buf = await interaction.client.loop.run_in_executor(
            None, generate_leaderboard_bytes, interaction.guild, cat
        )
        file = discord.File(img_buf, filename="leaderboard_card.png")
        view = LeaderboardView(current_cat=cat)
        await interaction.followup.send(file=file, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Leaderboard(bot))
