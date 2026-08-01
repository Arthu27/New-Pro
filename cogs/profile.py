"""
Profile Cog — Anime/Comic pop-art card generation via Pillow
Broken asymmetric layout, hexagon panels, halftone dots, speed-line comic vibe
"""
import discord
from discord.ext import commands
from discord import app_commands
import os, io, json, math, aiohttp
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from logger import get_logger
from db import UserData, GuildData

log = get_logger("profile")

ROOT = os.path.join(os.path.dirname(__file__), '..')
FONTS = os.path.join(ROOT, 'assets', 'fonts')
BG_PATH = os.path.join(ROOT, 'assets', 'profile_bg_anime.jpg')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

# ═══════════════════════════════════════════════════════════════════════
# Palette — vivid anime / comic pop-art
# ═══════════════════════════════════════════════════════════════════════
PINK       = (255, 45, 145)
PINK_DK    = (185, 15, 105)
CYAN       = (60, 225, 255)
CYAN_DK    = (15, 150, 200)
PURPLE     = (160, 70, 235)
PURPLE_DK  = (95, 30, 175)
YELLOW     = (255, 222, 40)
YELLOW_DK  = (240, 160, 20)
GOLD       = (255, 200, 60)
SILVER     = (215, 220, 230)
BRONZE     = (205, 140, 85)
INK        = (16, 11, 22, 255)      # comic outline "ink" color
WHITE      = (255, 255, 255, 255)
PANEL_DARK = (14, 9, 22, 210)
TEXT_MUTE  = (225, 210, 240, 210)

W, H = 1040, 760


def _f(bold=False, sz=20):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT_R, sz)
    except Exception:
        return ImageFont.load_default()


# ═══════════════════════════════════════════════════════════════════════
# Geometry helpers
# ═══════════════════════════════════════════════════════════════════════

def _hex_points(cx, cy, r, rot=-90):
    pts = []
    for i in range(6):
        ang = math.radians(rot + i * 60)
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def _star_points(cx, cy, r_out, r_in, n, rot=-90):
    pts = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        ang = math.radians(rot + i * (360 / (n * 2)))
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def _grad_diag(size, color_a, color_b):
    """Diagonal gradient square image (top-left color_a -> bottom-right color_b)."""
    grad = Image.new('RGB', (size, size), color_a)
    gd = ImageDraw.Draw(grad)
    diag = size * 1.6
    steps = int(diag)
    for i in range(steps):
        t = i / steps
        r = int(color_a[0] + (color_b[0] - color_a[0]) * t)
        g = int(color_a[1] + (color_b[1] - color_a[1]) * t)
        b = int(color_a[2] + (color_b[2] - color_a[2]) * t)
        gd.line([(i, 0), (0, i)], fill=(r, g, b), width=2)
    return grad


def _halftone_layer(size, spacing, dot_r, color):
    layer = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    row = 0
    y = -spacing
    while y < size + spacing:
        offset = (spacing / 2) if row % 2 else 0
        x = -spacing + offset
        while x < size + spacing:
            d.ellipse((x - dot_r, y - dot_r, x + dot_r, y + dot_r), fill=color)
            x += spacing
        y += spacing
        row += 1
    return layer


# ═══════════════════════════════════════════════════════════════════════
# Vector glyph icons (drawn crisp at any size, white fill)
# ═══════════════════════════════════════════════════════════════════════

def _glyph_chat(d, cx, cy, s):
    w, h = s * 0.9, s * 0.68
    x0, y0 = cx - w / 2, cy - h / 2 - s * 0.06
    x1, y1 = cx + w / 2, cy + h / 2 - s * 0.06
    d.rounded_rectangle((x0, y0, x1, y1), radius=h * 0.34, fill=WHITE)
    tail = [(cx - w * 0.16, y1 - 1), (cx - w * 0.02, y1 + h * 0.28), (cx + w * 0.12, y1 - 1)]
    d.polygon(tail, fill=WHITE)
    r = s * 0.05
    for i in (-1, 0, 1):
        dx = i * s * 0.17
        d.ellipse((cx + dx - r, cy - s * 0.06 - r, cx + dx + r, cy - s * 0.06 + r), fill=PINK_DK)


def _glyph_voice(d, cx, cy, s):
    bx = cx - s * 0.28
    body = [(bx - s * 0.05, cy - s * 0.14), (bx + s * 0.12, cy - s * 0.14),
            (bx + s * 0.30, cy - s * 0.30), (bx + s * 0.30, cy + s * 0.30),
            (bx + s * 0.12, cy + s * 0.14), (bx - s * 0.05, cy + s * 0.14)]
    d.polygon(body, fill=WHITE)
    for r in (s * 0.14, s * 0.24, s * 0.34):
        bbox = (cx + s * 0.02 - r, cy - r, cx + s * 0.02 + r, cy + r)
        d.arc(bbox, -45, 45, fill=WHITE, width=max(2, int(s * 0.05)))


def _glyph_wallet(d, cx, cy, s):
    w, h = s * 0.80, s * 0.60
    x0, y0 = cx - w / 2, cy - h / 2
    x1, y1 = cx + w / 2, cy + h / 2
    d.rounded_rectangle((x0, y0, x1, y1), radius=h * 0.24, outline=WHITE, width=max(2, int(s * 0.06)))
    r = s * 0.20
    coin_cx = x1 - r * 1.1
    d.ellipse((coin_cx - r, cy - r, coin_cx + r, cy + r), fill=WHITE)
    f = _f(bold=True, sz=max(10, int(r * 1.35)))
    txt = "$"
    bb = d.textbbox((0, 0), txt, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    d.text((coin_cx - tw / 2 - bb[0], cy - th / 2 - bb[1]), txt, fill=PINK_DK, font=f)


GLYPHS = {'chat': _glyph_chat, 'voice': _glyph_voice, 'balance': _glyph_wallet}


def _draw_crown(d, cx, cy, s, fill=YELLOW, outline=INK):
    base_y = cy + s * 0.22
    pts = [
        (cx - s * 0.46, base_y), (cx - s * 0.46, cy - s * 0.02),
        (cx - s * 0.26, cy + s * 0.14), (cx - s * 0.13, cy - s * 0.30),
        (cx, cy + s * 0.02), (cx + s * 0.13, cy - s * 0.30),
        (cx + s * 0.26, cy + s * 0.14), (cx + s * 0.46, cy - s * 0.02),
        (cx + s * 0.46, base_y),
    ]
    d.polygon(pts, fill=fill, outline=outline, width=max(2, int(s * 0.05)))
    d.rectangle((cx - s * 0.46, base_y, cx + s * 0.46, base_y + s * 0.10), fill=fill, outline=outline, width=max(2, int(s * 0.05)))
    for jx in (-0.13, 0, 0.13):
        jr = s * 0.045
        d.ellipse((cx + jx * s - jr, cy - s * 0.06 - jr, cx + jx * s + jr, cy - s * 0.06 + jr), fill=PINK_DK)


# ═══════════════════════════════════════════════════════════════════════
# Hexagon badge / avatar builders
# ═══════════════════════════════════════════════════════════════════════

def _hex_badge(diameter, color_a, color_b, glyph_key=None, outline_w=7, halftone=True):
    """Comic-style hexagon icon badge with diagonal gradient, halftone dots and thick ink outline."""
    size = diameter
    cx = cy = size / 2
    r = size / 2 - outline_w - 2
    pts = _hex_points(cx, cy, r)

    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    grad = _grad_diag(size, color_a, color_b).convert('RGBA')
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    canvas.paste(grad, (0, 0), mask)

    if halftone:
        dots = _halftone_layer(size, max(8, size // 9), max(1.4, size * 0.012), (255, 255, 255, 55))
        dots_masked = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        dots_masked.paste(dots, (0, 0), mask)
        canvas.alpha_composite(dots_masked)

    d = ImageDraw.Draw(canvas)
    d.polygon(pts, outline=INK, width=outline_w)
    pts_inner = _hex_points(cx, cy, r - outline_w * 0.85)
    d.polygon(pts_inner, outline=(255, 255, 255, 90), width=2)

    if glyph_key:
        GLYPHS[glyph_key](d, cx, cy, r * 1.05)
    return canvas


def _hex_avatar(square_avatar, diameter, outline_w=11, ring_color=WHITE):
    size = diameter
    cx = cy = size / 2
    r = size / 2 - outline_w - 3
    pts = _hex_points(cx, cy, r)

    av = square_avatar
    if av.size != (size, size):
        av = av.resize((size, size), Image.Resampling.LANCZOS)

    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)

    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    canvas.paste(av, (0, 0), mask)
    d = ImageDraw.Draw(canvas)
    d.polygon(pts, outline=INK, width=outline_w)
    pts_inner = _hex_points(cx, cy, r - outline_w * 0.6)
    d.polygon(pts_inner, outline=ring_color, width=4)
    return canvas


def _sticker(w, h, fill=WHITE, outline=INK, outline_w=6, radius=None):
    radius = radius if radius is not None else h * 0.30
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ow = outline_w
    ImageDraw.Draw(img).rounded_rectangle((ow / 2, ow / 2, w - ow / 2 - 1, h - ow / 2 - 1),
                                          radius=radius, fill=fill, outline=outline, width=outline_w)
    return img


def _paste_rot(base, layer, cx, cy, angle):
    rot = layer.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    x = int(cx - rot.width / 2)
    y = int(cy - rot.height / 2)
    base.alpha_composite(rot, (x, y))


def _text_outline(draw, xy, text, font, fill, outline=INK, ow=3):
    x, y = xy
    for dx in range(-ow, ow + 1):
        for dy in range(-ow, ow + 1):
            if dx * dx + dy * dy <= ow * ow and (dx, dy) != (0, 0):
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


def _text_cx(draw, text, font, x1, x2):
    bb = draw.textbbox((0, 0), text, font=font)
    return x1 + (x2 - x1 - (bb[2] - bb[0])) // 2


def _xp_bar(w, h, progress, color_a=YELLOW, color_b=PINK):
    bar = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(bar).rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(30, 20, 40, 255),
                                          outline=INK, width=4)
    fw = max(1, int((w - 8) * min(progress, 1.0)))
    fill = Image.new('RGBA', (max(fw, 1), h - 8), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fill)
    for x in range(fw):
        t = x / max(w - 9, 1)
        r = int(color_a[0] + (color_b[0] - color_a[0]) * t)
        g = int(color_a[1] + (color_b[1] - color_a[1]) * t)
        b = int(color_a[2] + (color_b[2] - color_a[2]) * t)
        fd.line([(x, 0), (x, h - 9)], fill=(r, g, b, 255))
    fill_mask = Image.new('L', (max(fw, 1), h - 8), 0)
    ImageDraw.Draw(fill_mask).rounded_rectangle((0, 0, fw - 1, h - 9), radius=(h - 8) // 2, fill=255)
    bar.paste(fill, (4, 4), fill_mask)
    return bar


def _bg(w, h):
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
        return Image.new('RGBA', (w, h), (30, 10, 40, 255))


def _fmt(n):
    return f"{n:,}".replace(",", " ")


def _fmt_t(s):
    h, m = s // 3600, (s % 3600) // 60
    return f"{h}ч {m}м" if h else f"{m}м"


async def _avatar(url, sz=180, shape='square'):
    """Fetch and resize the user's avatar. shape='square' keeps a plain square
    (for hex-cropping); shape='circle' returns a circular-masked avatar."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.read()
        av = Image.open(io.BytesIO(data)).convert('RGBA').resize((sz, sz), Image.Resampling.LANCZOS)
    except Exception:
        av = Image.new('RGBA', (sz, sz), (0, 0, 0, 0))
        d = ImageDraw.Draw(av)
        for yy in range(sz):
            t = yy / sz
            r = int(PURPLE[0] + (PINK[0] - PURPLE[0]) * t)
            g = int(PURPLE[1] + (PINK[1] - PURPLE[1]) * t)
            b = int(PURPLE[2] + (PINK[2] - PURPLE[2]) * t)
            d.line([(0, yy), (sz, yy)], fill=(r, g, b, 255))
    if shape == 'circle':
        m = Image.new('L', (sz, sz), 0)
        ImageDraw.Draw(m).ellipse((0, 0, sz, sz), fill=255)
        av.putalpha(m)
    return av


# ═══════════════════════════════════════════════════════════════════════
# Card Generator — asymmetric anime/comic pop-art layout
# ═══════════════════════════════════════════════════════════════════════

def generate_profile_card(avatar, nickname, level, xp, xp_needed,
                          messages, voice_seconds, balance,
                          rank_messages, rank_voice, rank_balance):

    img = _bg(W, H).convert('RGBA')
    avg_rank = max(1, round((rank_messages + rank_voice + rank_balance) / 3))

    # ─── Speed-burst accent + scattered comic hexagon confetti ─────
    for i, (hx, hy, hr, hc) in enumerate([
        (60, 480, 10, (*CYAN, 130)), (110, 520, 6, (*YELLOW, 150)),
        (960, 60, 8, (*PINK, 140)), (930, 500, 12, (*PURPLE, 120)),
        (980, 420, 6, (*WHITE[:3], 120)),
    ]):
        conf = Image.new('RGBA', img.size, (0, 0, 0, 0))
        ImageDraw.Draw(conf).polygon(_hex_points(hx, hy, hr), fill=hc, outline=(*INK[:3], 160), width=2)
        img.alpha_composite(conf)

    # ─── AVATAR — big tilted hexagon bursting off the top-left edge ─
    av_d = 250
    av_hex = _hex_avatar(avatar, av_d, outline_w=11, ring_color=WHITE)
    av_cx, av_cy = 210, 175
    _paste_rot(img, av_hex, av_cx, av_cy, angle=-9)

    if avg_rank == 1:
        crown_layer = Image.new('RGBA', (140, 110), (0, 0, 0, 0))
        _draw_crown(ImageDraw.Draw(crown_layer), 70, 60, 100)
        _paste_rot(img, crown_layer, av_cx + 8, av_cy - 95, angle=-9)

    # ─── NICKNAME sticker — overlapping bottom-right of the avatar ──
    f_nick = _f(bold=True, sz=26)
    tmp = Image.new('RGBA', (10, 10))
    td = ImageDraw.Draw(tmp)
    nb = td.textbbox((0, 0), nickname, font=f_nick)
    nick_w = (nb[2] - nb[0]) + 56
    nick_h = 62
    sticker = _sticker(nick_w, nick_h, fill=WHITE, outline=INK, outline_w=6)
    sd = ImageDraw.Draw(sticker)
    sd.text(((nick_w - (nb[2] - nb[0])) / 2 - nb[0], (nick_h - (nb[3] - nb[1])) / 2 - nb[1] - 2),
            nickname, font=f_nick, fill=(*PURPLE_DK, 255))
    nick_cx, nick_cy = 205, 300
    _paste_rot(img, sticker, nick_cx, nick_cy, angle=5)

    # ─── LEVEL burst — tilted starburst top-right ───────────────────
    burst_d = 250
    burst = Image.new('RGBA', (burst_d, burst_d), (0, 0, 0, 0))
    bd = ImageDraw.Draw(burst)
    pts = _star_points(burst_d / 2, burst_d / 2, burst_d / 2 - 10, (burst_d / 2 - 10) * 0.66, 10)
    bd.polygon(pts, fill=YELLOW, outline=INK, width=7)
    pts_in = _star_points(burst_d / 2, burst_d / 2, burst_d / 2 - 26, (burst_d / 2 - 26) * 0.66, 10)
    bd.polygon(pts_in, outline=(*PINK_DK, 130), width=3)
    burst_cx, burst_cy = 860, 175
    _paste_rot(img, burst, burst_cx, burst_cy, angle=10)

    d = ImageDraw.Draw(img)
    f_lvl_lbl = _f(bold=True, sz=17)
    f_lvl_num = _f(bold=True, sz=64)
    lbl_txt = "УР."
    lb = d.textbbox((0, 0), lbl_txt, font=f_lvl_lbl)
    num_txt = str(level)
    nb2 = d.textbbox((0, 0), num_txt, font=f_lvl_num)
    lbl_x = burst_cx - (lb[2] - lb[0]) / 2
    _text_outline(d, (lbl_x, burst_cy - 66), lbl_txt, f_lvl_lbl, fill=PURPLE_DK, outline=WHITE, ow=2)
    num_x = burst_cx - (nb2[2] - nb2[0]) / 2 - nb2[0]
    num_y = burst_cy - (nb2[3] - nb2[1]) / 2 - nb2[1] - 8
    _text_outline(d, (num_x, num_y), num_txt, f_lvl_num, fill=WHITE, outline=INK, ow=4)

    # ─── XP power-meter bar, tilted, beneath the burst ──────────────
    barw, barh = 320, 30
    prog = xp / xp_needed if xp_needed > 0 else 0
    bar = _xp_bar(barw, barh, prog)
    bar_cx, bar_cy = 850, 340
    _paste_rot(img, bar, bar_cx, bar_cy, angle=-4)
    d = ImageDraw.Draw(img)

    f_xp = _f(bold=True, sz=13)
    xp_txt = f"{_fmt(xp)} / {_fmt(xp_needed)} XP"
    xb = d.textbbox((0, 0), xp_txt, font=f_xp)
    _text_outline(d, (bar_cx - (xb[2] - xb[0]) / 2 - xb[0] + 8, bar_cy + 32), xp_txt, f_xp,
                  fill=WHITE, outline=INK, ow=2)

    # ─── Dark comic panel strip (tilted) holding the hex stat badges ─
    panel_layer = Image.new('RGBA', (1000, 360), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel_layer)
    pd.rounded_rectangle((6, 6, 994, 354), radius=26, fill=PANEL_DARK, outline=INK, width=6)
    pd.rounded_rectangle((16, 16, 984, 344), radius=20, outline=(*WHITE[:3], 60), width=2)
    panel_cx, panel_cy = 520, 585
    _paste_rot(img, panel_layer, panel_cx, panel_cy, angle=-1.5)
    d = ImageDraw.Draw(img)

    f_t = _f(bold=True, sz=15)
    f_v = _f(bold=True, sz=21)
    f_l = _f(bold=False, sz=11)

    # Section headers (comic sticker tabs)
    tab1 = _sticker(190, 40, fill=CYAN, outline=INK, outline_w=5, radius=12)
    td1 = ImageDraw.Draw(tab1)
    tb1 = td1.textbbox((0, 0), "СТАТИСТИКА", font=f_t)
    td1.text(((190 - (tb1[2] - tb1[0])) / 2 - tb1[0], (40 - (tb1[3] - tb1[1])) / 2 - tb1[1]),
              "СТАТИСТИКА", font=f_t, fill=INK[:3])
    _paste_rot(img, tab1, 230, 435, angle=-3)

    tab2 = _sticker(190, 40, fill=PINK, outline=INK, outline_w=5, radius=12)
    td2 = ImageDraw.Draw(tab2)
    tb2 = td2.textbbox((0, 0), "РЕЙТИНГ", font=f_t)
    td2.text(((190 - (tb2[2] - tb2[0])) / 2 - tb2[0], (40 - (tb2[3] - tb2[1])) / 2 - tb2[1]),
              "РЕЙТИНГ", font=f_t, fill=(255, 255, 255))
    _paste_rot(img, tab2, 800, 428, angle=2)
    d = ImageDraw.Draw(img)

    # Honeycomb-staggered hex badges: STATISTICS (left) + RANKINGS (right)
    stat_defs = [
        ('chat', _fmt(messages), "сообщения", CYAN, CYAN_DK),
        ('voice', _fmt_t(voice_seconds), "войс", PURPLE, PURPLE_DK),
        ('balance', f"${_fmt(balance)}", "баланс", YELLOW, YELLOW_DK),
    ]
    rank_defs = [
        ('chat', rank_messages, "сообщения"),
        ('voice', rank_voice, "войс"),
        ('balance', rank_balance, "баланс"),
    ]

    hex_d = 92
    stat_x0 = 90
    stat_y_positions = [520, 600, 520]
    stat_angles = [-8, 6, -5]
    for i, (glyph, val, label, ca, cb) in enumerate(stat_defs):
        cx = stat_x0 + i * 118
        cy = stat_y_positions[i]
        badge = _hex_badge(hex_d, ca, cb, glyph_key=glyph)
        _paste_rot(img, badge, cx, cy, angle=stat_angles[i])
        d = ImageDraw.Draw(img)
        f_val_bb = d.textbbox((0, 0), val, font=f_v)
        text_cx = cx
        _text_outline(d, (text_cx - (f_val_bb[2] - f_val_bb[0]) / 2 - f_val_bb[0], cy + hex_d / 2 - 4),
                      val, f_v, fill=WHITE, outline=INK, ow=3)
        lbl_bb = d.textbbox((0, 0), label, font=f_l)
        d.text((text_cx - (lbl_bb[2] - lbl_bb[0]) / 2 - lbl_bb[0], cy + hex_d / 2 + 22),
               label, font=f_l, fill=TEXT_MUTE)

    rank_x0 = 665
    rank_y_positions = [520, 600, 520]
    rank_angles = [7, -6, 5]
    for i, (glyph, rank, label) in enumerate(rank_defs):
        cx = rank_x0 + i * 118
        cy = rank_y_positions[i]
        if rank == 1:
            ca, cb = GOLD, YELLOW_DK
        elif rank == 2:
            ca, cb = SILVER, (150, 155, 165)
        elif rank == 3:
            ca, cb = BRONZE, (140, 90, 55)
        else:
            ca, cb = PURPLE, PURPLE_DK
        badge = _hex_badge(hex_d, ca, cb, glyph_key=glyph)
        _paste_rot(img, badge, cx, cy, angle=rank_angles[i])
        d = ImageDraw.Draw(img)
        rv_txt = f"#{rank}"
        rv_bb = d.textbbox((0, 0), rv_txt, font=f_v)
        _text_outline(d, (cx - (rv_bb[2] - rv_bb[0]) / 2 - rv_bb[0], cy + hex_d / 2 - 4),
                      rv_txt, f_v, fill=WHITE, outline=INK, ow=3)
        lbl_bb = d.textbbox((0, 0), label, font=f_l)
        d.text((cx - (lbl_bb[2] - lbl_bb[0]) / 2 - lbl_bb[0], cy + hex_d / 2 + 22),
               label, font=f_l, fill=TEXT_MUTE)

    # Watermark sticker bottom-right
    f_wm = _f(bold=True, sz=11)
    wm = "AETHER"
    wb = d.textbbox((0, 0), wm, font=f_wm)
    _text_outline(d, (W - 26 - (wb[2] - wb[0]), H - 30), wm, f_wm, fill=WHITE, outline=INK, ow=2)

    return img.convert('RGB')



# Data Fetchers
# ═══════════════════════════════════════════════════════════════════════

def _lb(gid):
    p = os.path.join('data', f'leaderboard_{gid}.json')
    try:
        with open(p, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {'messages': {}, 'voice_minutes': {}}

def _vs(gid):
    p = os.path.join('data', f'voice_stats_{gid}.json')
    try:
        with open(p, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {'users': {}}

def _rank(sl, uid):
    for i, (u, _) in enumerate(sl):
        if u == uid: return i + 1
    return len(sl) + 1


# ═══════════════════════════════════════════════════════════════════════
# Cog
# ═══════════════════════════════════════════════════════════════════════

class ProfileCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.eco = UserData("economy")

    def _data(self, gid, uid):
        uid_s = str(uid)
        lb = _lb(gid)
        msgs = lb.get('messages', {}).get(uid_s, 0)

        voice = 0
        vs = _vs(gid)
        u = vs.get('users', {}).get(uid_s, {})
        if isinstance(u, dict): voice = u.get('total_seconds', 0)
        if not voice:
            voice = lb.get('voice_minutes', {}).get(uid_s, 0) * 60

        eco = self.eco.get(uid)
        bal = eco.get('balance', 0) + eco.get('bank', 0) if isinstance(eco, dict) else 0

        lvl, xp, xp_need = 1, 0, 200
        try:
            from services.gamification import level_system, points_system
            ld = level_system.get_level(uid)
            lvl = ld.get('level', 1) if isinstance(ld, dict) else (ld if isinstance(ld, int) else 1)
            xp = points_system.get_points(uid)
            xp_need = 100 + (lvl ** 2) * 50
        except:
            xp_need = 100 + (lvl ** 2) * 50

        ms = sorted(lb.get('messages', {}).items(), key=lambda x: x[1], reverse=True)
        vsd = {k: v.get('total_seconds', 0) for k, v in vs.get('users', {}).items() if isinstance(v, dict)}
        vss = sorted(vsd.items(), key=lambda x: x[1], reverse=True)
        all_e = self.eco.get_all()
        bs = sorted([(str(u), d.get('balance',0)+d.get('bank',0)) for u, d in all_e.items() if isinstance(d, dict)], key=lambda x: x[1], reverse=True)

        return dict(level=lvl, xp=xp, xp_needed=xp_need, messages=msgs,
                    voice_seconds=voice, balance=bal,
                    rank_messages=_rank(ms, uid_s), rank_voice=_rank(vss, uid_s),
                    rank_balance=_rank(bs, uid_s))

    @commands.command(name="profile", aliases=["профиль", "карточка", "me"])
    async def profile_cmd(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        msg = await ctx.send(embed=discord.Embed(title="...", color=discord.Color.dark_grey()))
        try:
            av = await _avatar(member.display_avatar.url, sz=260, shape='square')
            d = self._data(ctx.guild.id, member.id)
            card = generate_profile_card(avatar=av, nickname=member.display_name[:14], **d)
            buf = io.BytesIO()
            card.save(buf, format='PNG')
            buf.seek(0)
            await msg.delete()
            await ctx.send(file=discord.File(buf, filename='profile.png'))
        except Exception as e:
            log.error(f"Profile error: {e}")
            import traceback; traceback.print_exc()
            await msg.edit(embed=discord.Embed(title="Error", color=discord.Color.dark_grey()))

    @app_commands.command(name="profile", description="Profile card")
    async def profile_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        await interaction.response.defer()
        try:
            av = await _avatar(member.display_avatar.url, sz=260, shape='square')
            d = self._data(interaction.guild.id, member.id)
            card = generate_profile_card(avatar=av, nickname=member.display_name[:14], **d)
            buf = io.BytesIO()
            card.save(buf, format='PNG')
            buf.seek(0)
            await interaction.followup.send(file=discord.File(buf, filename='profile.png'))
        except Exception as e:
            log.error(f"Profile error: {e}")
            await interaction.followup.send(embed=discord.Embed(title="Error", color=discord.Color.dark_grey()), ephemeral=True)


async def setup(bot):
    await bot.add_cog(ProfileCog(bot))
    log.info("ProfileCog loaded (premium)")
