"""
Leaderboard Cog — Professional Dashboard/ID-Card Style via Pillow
Белый фон, тонкие чёрные линии, золотые/янтарные line-art акценты.
Рейтинги по сообщениям, голосовой активности и балансу,
переключаемые через Discord Select Menu (без кнопок и классических эмодзи).
"""

import os
import io
import json
import math
import datetime
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
from cogs.menu_bg import load_menu_bg

ROOT = os.path.join(os.path.dirname(__file__), '..')
FONTS = os.path.join(ROOT, 'assets', 'fonts')
BG_PATH = os.path.join(ROOT, 'assets', 'profile_bg_pro.jpg')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

WHITE = (255, 255, 255)
BLACK = (20, 20, 25)
GOLD = (217, 119, 6)
RED = (220, 38, 38)
MUTED = (110, 115, 125)
SS = 4

DATA_DIR = os.path.join(ROOT, 'data')


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


def _icon_trophy(d, cx, cy, s, w, color):
    cup_w, cup_h = s * 0.44, s * 0.36
    d.rounded_rectangle((cx - cup_w, cy - cup_h*0.8, cx + cup_w, cy + cup_h*0.2), radius=s*0.08, outline=color, width=w)
    d.line([(cx - s*0.2, cy + cup_h*0.2), (cx, cy + cup_h*0.8), (cx + s*0.2, cy + cup_h*0.2)], fill=color, width=w)
    d.line([(cx - s*0.3, cy + cup_h*0.8), (cx + s*0.3, cy + cup_h*0.8)], fill=color, width=int(w*1.3))
    r = s * 0.12
    d.ellipse((cx - r, cy - s*0.25 - r, cx + r, cy - s*0.25 + r), fill=color)


def _icon_badge(diameter, glyph_fn, ring_color=BLACK, ring_w=None, icon_color=GOLD):
    ring_w = ring_w if ring_w is not None else max(2, diameter // 22)

    def draw(d, scale):
        size = diameter * scale
        rw = ring_w * scale
        r = size * 0.22
        d.rounded_rectangle((rw / 2, rw / 2, size - rw / 2 - 1, size - rw / 2 - 1),
                             radius=r, fill=WHITE, outline=ring_color, width=rw)
        glyph_fn(d, size / 2, size / 2, size * 0.60, max(2, int(size * 0.032)), icon_color)

    return _ss_render(diameter, diameter, draw)


def _rank_badge(diameter, num, ring_color=BLACK, ring_w=None, text_color=GOLD):
    ring_w = ring_w if ring_w is not None else max(2, diameter // 22)

    def draw(d, scale):
        size = diameter * scale
        rw = ring_w * scale
        r = size * 0.22
        d.rounded_rectangle((rw / 2, rw / 2, size - rw / 2 - 1, size - rw / 2 - 1),
                             radius=r, fill=WHITE, outline=ring_color, width=rw)
        txt = f"#{num}"
        f = _f(True, int(size * 0.40))
        bb = d.textbbox((0, 0), txt, font=f)
        tw = bb[2] - bb[0]
        th = bb[3] - bb[1]
        d.text(((size - tw) / 2 - bb[0], (size - th) / 2 - bb[1]), txt, fill=text_color, font=f)

    return _ss_render(diameter, diameter, draw)


def _corner_bracket(size, thickness, length_ratio=0.35, color=GOLD):
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
            except Exception:
                pass
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
            except Exception:
                pass
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
            except Exception:
                pass

    if not top:
        top = [
            ("SABOTASH", "1 450 СООБЩЕНИЙ" if category == "messages" else ("42ч 15м В ВОЙСЕ" if category == "voice" else "250 000 МОНЕТ")),
            ("TOP_PLAYER", "980 СООБЩЕНИЙ" if category == "messages" else ("28ч 40м В ВОЙСЕ" if category == "voice" else "145 000 МОНЕТ")),
            ("AETHER_MOD", "640 СООБЩЕНИЙ" if category == "messages" else ("19ч 10м В ВОЙСЕ" if category == "voice" else "98 500 МОНЕТ")),
        ]
    return top


def generate_leaderboard_card(guild: discord.Guild, category: str = "messages") -> Image.Image:
    W = 920
    top = _get_lb_data(guild, category)
    H = max(460, 110 + len(top) * 88 + 30)

    bg = load_menu_bg(W, H, "gold")
    d = ImageDraw.Draw(bg)

    # Top Header Panel (872x72 px)
    header_box = _rounded_panel(872, 72, radius=14, fill=WHITE, outline=BLACK, ow=2)
    bg.alpha_composite(header_box, (24, 20))

    title_map = {
        "messages": "ТОП ПО СООБЩЕНИЯМ",
        "voice": "ТОП ПО ГОЛОСОВОЙ АКТИВНОСТИ",
        "balance": "ТОП ПО БАЛАНСУ МОНЕТ"
    }
    title_text = title_map.get(category, "ТАБЛИЦА ЛИДЕРОВ")

    badge = _icon_badge(52, _icon_trophy, ring_color=BLACK, ring_w=2, icon_color=GOLD)
    bg.alpha_composite(badge, (36, 30))

    d.text((100, 26), title_text, fill=BLACK, font=_f(True, 24))
    d.text((100, 56), "ПРОФЕССИОНАЛЬНЫЙ РЕЙТИНГ АКТИВНОСТИ СЕРВЕРА", fill=MUTED, font=_f(False, 15))

    pill = _rounded_panel(160, 36, radius=10, fill=WHITE, outline=GOLD, ow=2)
    bg.alpha_composite(pill, (720, 38))
    d.text((738, 46), "TOP RANKING", fill=GOLD, font=_f(True, 14))

    # Leaderboard rows
    box_w = 872
    box_h = 76
    gap_y = 12
    start_x, start_y = 24, 108

    for idx, (name, val) in enumerate(top):
        bx = start_x
        by = start_y + idx * (box_h + gap_y)

        box = _rounded_panel(box_w, box_h, radius=14, fill=WHITE, outline=BLACK, ow=2)
        bg.alpha_composite(box, (bx, by))

        r_color = GOLD if idx == 0 else BLACK
        t_color = GOLD if idx == 0 else (RED if idx < 3 else MUTED)
        rank_badge = _rank_badge(52, idx + 1, ring_color=r_color, ring_w=2, text_color=t_color)
        bg.alpha_composite(rank_badge, (bx + 16, by + 12))

        d.text((bx + 86, by + 22), name[:22], fill=BLACK, font=_f(True, 26))

        vw = len(str(val)) * 14
        d.text((bx + box_w - 24 - vw, by + 24), str(val), fill=GOLD if idx == 0 else MUTED, font=_f(True, 22))

    # 4 Corner brackets (Gold accent)
    br = _corner_bracket(40, 4, color=GOLD)
    bg.alpha_composite(br, (6, 6))
    bg.alpha_composite(br.rotate(270), (W - 46, 6))
    bg.alpha_composite(br.rotate(90), (6, H - 46))
    bg.alpha_composite(br.rotate(180), (W - 46, H - 46))

    return bg


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
            except Exception:
                pass
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
        now = datetime.datetime.utcnow()
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
                        except Exception:
                            pass
                    suid = str(uid)
                    d = vs['users'].get(suid, {'total_seconds': 0, 'name': member.display_name})
                    d['total_seconds'] = d.get('total_seconds', 0) + minutes * 60
                    vs['users'][suid] = d
                    os.makedirs(DATA_DIR, exist_ok=True)
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(vs, f, ensure_ascii=False, indent=2)

    @commands.command(name="leaderboard", aliases=["rank", "top", "лб", "рейтинг"])
    async def leaderboard_cmd(self, ctx, category: str = "messages"):
        try:
            await ctx.message.delete()
        except Exception:
            pass
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
