"""
Profile Cog — Clean premium card generation via Pillow
Ribbon-shaped side panel, gradient icon badges, dark marble + bokeh background
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
BG_PATH = os.path.join(ROOT, 'assets', 'profile_bg_dark.jpg')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

# ═══════════════════════════════════════════════════════════════════════
# Palette — violet / magenta premium, dark marble backdrop
# ═══════════════════════════════════════════════════════════════════════
VIOLET     = (139, 92, 246)
VIOLET_DK  = (91, 56, 176)
PINK       = (236, 72, 153)
PINK_LT    = (250, 130, 190)
WHITE      = (245, 244, 250)
MUTED      = (158, 150, 178)
MUTED_DK   = (120, 112, 140)

PANEL      = (16, 13, 24, 175)
PANEL_BORDER = (168, 120, 255, 60)
BADGE_A, BADGE_B = VIOLET, PINK

W, H = 1000, 560
PAD = 22
LW = 270
GAP = 18
RX = PAD + LW + GAP
RW = W - PAD - RX
TOP_H = 168
BOT_Y = PAD + TOP_H + GAP
BOT_H = H - PAD - BOT_Y
PW = (RW - GAP) // 2
TAIL_H = 46          # height of the ribbon "flag tail" at bottom of left panel


def _f(bold=False, sz=20):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT_R, sz)
    except Exception:
        return ImageFont.load_default()


# ═══════════════════════════════════════════════════════════════════════
# Simple vector glyph icons — drawn crisp at any size, white on transparent
# ═══════════════════════════════════════════════════════════════════════

def _glyph_chat(d, cx, cy, s):
    """Speech bubble with three dots."""
    w, h = s * 0.9, s * 0.68
    x0, y0 = cx - w / 2, cy - h / 2 - s * 0.06
    x1, y1 = cx + w / 2, cy + h / 2 - s * 0.06
    d.rounded_rectangle((x0, y0, x1, y1), radius=h * 0.34, fill=WHITE)
    tail = [(cx - w * 0.16, y1 - 1), (cx - w * 0.02, y1 + h * 0.28), (cx + w * 0.12, y1 - 1)]
    d.polygon(tail, fill=WHITE)
    r = s * 0.045
    for i in (-1, 0, 1):
        dx = i * s * 0.16
        d.ellipse((cx + dx - r, cy - s * 0.06 - r, cx + dx + r, cy - s * 0.06 + r), fill=BADGE_A)


def _glyph_voice(d, cx, cy, s):
    """Speaker with sound waves."""
    bx = cx - s * 0.28
    body = [(bx - s * 0.05, cy - s * 0.14), (bx + s * 0.12, cy - s * 0.14),
            (bx + s * 0.30, cy - s * 0.30), (bx + s * 0.30, cy + s * 0.30),
            (bx + s * 0.12, cy + s * 0.14), (bx - s * 0.05, cy + s * 0.14)]
    d.polygon(body, fill=WHITE)
    for i, r in enumerate([s * 0.14, s * 0.24, s * 0.34]):
        bbox = (cx + s * 0.02 - r, cy - r, cx + s * 0.02 + r, cy + r)
        d.arc(bbox, -45, 45, fill=WHITE, width=max(2, int(s * 0.045)))


def _glyph_wallet(d, cx, cy, s):
    """Wallet / balance icon with a dollar sign badge."""
    w, h = s * 0.80, s * 0.60
    x0, y0 = cx - w / 2, cy - h / 2
    x1, y1 = cx + w / 2, cy + h / 2
    d.rounded_rectangle((x0, y0, x1, y1), radius=h * 0.24, outline=WHITE, width=max(2, int(s * 0.055)))
    r = s * 0.20
    coin_cx = x1 - r * 1.1
    d.ellipse((coin_cx - r, cy - r, coin_cx + r, cy + r), fill=WHITE)
    f = _f(bold=True, sz=max(10, int(r * 1.35)))
    txt = "$"
    bb = d.textbbox((0, 0), txt, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    d.text((coin_cx - tw / 2 - bb[0], cy - th / 2 - bb[1]), txt, fill=BADGE_A, font=f)


def _glyph_star(d, cx, cy, s):
    """5-point star (used for server rank)."""
    pts = []
    for i in range(10):
        r = s * 0.46 if i % 2 == 0 else s * 0.20
        ang = math.radians(-90 + i * 36)
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    d.polygon(pts, fill=WHITE)


GLYPHS = {
    'chat': _glyph_chat,
    'voice': _glyph_voice,
    'balance': _glyph_wallet,
    'rank': _glyph_star,
}


def _icon_badge(size, glyph_key, radius=None):
    """A rounded-square badge with a smooth diagonal violet→pink gradient and a white glyph icon."""
    radius = radius if radius is not None else int(size * 0.30)
    badge = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    grad = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    diag = size * 1.5
    for i in range(int(diag)):
        t = i / diag
        r = int(BADGE_A[0] + (BADGE_B[0] - BADGE_A[0]) * t)
        g = int(BADGE_A[1] + (BADGE_B[1] - BADGE_A[1]) * t)
        b = int(BADGE_A[2] + (BADGE_B[2] - BADGE_A[2]) * t)
        gd.line([(i, 0), (0, i)], fill=(r, g, b, 255), width=2)
    grad = grad.rotate(0)
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    badge.paste(grad.crop((0, 0, size, size)), (0, 0), mask)

    d = ImageDraw.Draw(badge)
    GLYPHS[glyph_key](d, size / 2, size / 2, size * 0.72)

    # subtle inner highlight top edge
    hl = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(hl).rounded_rectangle((1, 1, size - 2, size * 0.45), radius=radius,
                                          fill=(255, 255, 255, 26))
    hlm = Image.new('L', (size, size), 0)
    ImageDraw.Draw(hlm).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    hl.putalpha(Image.composite(hl.split()[-1], Image.new('L', (size, size), 0), hlm))
    badge.alpha_composite(hl)
    return badge


# ═══════════════════════════════════════════════════════════════════════
# Drawing helpers
# ═══════════════════════════════════════════════════════════════════════

def _panel(img, xy, radius, fill=PANEL, border=PANEL_BORDER, bw=2):
    o = Image.new('RGBA', img.size, (0, 0, 0, 0))
    ImageDraw.Draw(o).rounded_rectangle(xy, radius=radius, fill=fill, outline=border, width=bw)
    img.alpha_composite(o)


def _ribbon_panel(img, x0, y0, x1, y_flat, y_tip, radius=22, fill=PANEL, border=PANEL_BORDER, bw=2):
    """A rounded-top panel that tapers into a pointed ribbon/flag tail at the bottom."""
    cx = (x0 + x1) / 2
    y_notch = y_flat + (y_tip - y_flat) * 0.42

    # --- fill (rounded body + pointed tail) ---
    fillmask = Image.new('L', img.size, 0)
    fd = ImageDraw.Draw(fillmask)
    fd.rounded_rectangle((x0, y0, x1, y_flat), radius=radius, corners=(True, True, False, False), fill=255)
    fd.polygon([(x0, y_flat), (x1, y_flat), (x1, y_tip), (cx, y_notch), (x0, y_tip)], fill=255)
    solid = Image.new('RGBA', img.size, fill)
    img.paste(solid, (0, 0), fillmask)

    # --- outline path (no seam line at y_flat, continues smoothly into the tail) ---
    ol = Image.new('RGBA', img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(ol)
    r = radius
    od.arc((x0, y0, x0 + 2 * r, y0 + 2 * r), 180, 270, fill=border, width=bw)
    od.line([(x0 + r, y0), (x1 - r, y0)], fill=border, width=bw)
    od.arc((x1 - 2 * r, y0, x1, y0 + 2 * r), 270, 360, fill=border, width=bw)
    od.line([(x1, y0 + r), (x1, y_flat)], fill=border, width=bw)
    od.line([(x1, y_flat), (x1, y_tip)], fill=border, width=bw)
    od.line([(x1, y_tip), (cx, y_notch)], fill=border, width=bw)
    od.line([(cx, y_notch), (x0, y_tip)], fill=border, width=bw)
    od.line([(x0, y_tip), (x0, y_flat)], fill=border, width=bw)
    od.line([(x0, y_flat), (x0, y0 + r)], fill=border, width=bw)
    img.alpha_composite(ol)


def _text_cx(draw, text, font, x1, x2):
    bb = draw.textbbox((0, 0), text, font=font)
    return x1 + (x2 - x1 - (bb[2] - bb[0])) // 2


def _xp_bar(w, h, progress):
    bar = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(bar).rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(34, 28, 48, 255))
    fw = max(1, int(w * min(progress, 1.0)))
    fill = Image.new('RGBA', (max(fw, 1), h), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fill)
    for x in range(fw):
        t = x / max(w - 1, 1)
        r = int(VIOLET[0] + (PINK[0] - VIOLET[0]) * t)
        g = int(VIOLET[1] + (PINK[1] - VIOLET[1]) * t)
        b = int(VIOLET[2] + (PINK[2] - VIOLET[2]) * t)
        fd.line([(x, 0), (x, h - 1)], fill=(r, g, b, 255))
    fill_mask = Image.new('L', (max(fw, 1), h), 0)
    ImageDraw.Draw(fill_mask).rounded_rectangle((0, 0, fw - 1, h - 1), radius=h // 2, fill=255)
    bar.paste(fill, (0, 0), fill_mask)
    return bar


def _bg(w, h):
    """Load the dark marble + bokeh background and fit to card size."""
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
        img = Image.new('RGBA', (w, h), (12, 10, 16, 255))
        return img


def _fmt(n):
    return f"{n:,}".replace(",", " ")


def _fmt_t(s):
    h, m = s // 3600, (s % 3600) // 60
    return f"{h}h {m}m" if h else f"{m}m"


async def _avatar(url, sz=180):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.read()
        av = Image.open(io.BytesIO(data)).convert('RGBA').resize((sz, sz), Image.Resampling.LANCZOS)
        m = Image.new('L', (sz, sz), 0)
        ImageDraw.Draw(m).ellipse((0, 0, sz, sz), fill=255)
        av.putalpha(m)
        return av
    except Exception:
        av = Image.new('RGBA', (sz, sz), (0, 0, 0, 0))
        d = ImageDraw.Draw(av)
        for yy in range(sz):
            t = yy / sz
            r = int(VIOLET[0] + (PINK[0] - VIOLET[0]) * t)
            g = int(VIOLET[1] + (PINK[1] - VIOLET[1]) * t)
            b = int(VIOLET[2] + (PINK[2] - VIOLET[2]) * t)
            d.line([(0, yy), (sz, yy)], fill=(r, g, b, 255))
        m = Image.new('L', (sz, sz), 0)
        ImageDraw.Draw(m).ellipse((0, 0, sz, sz), fill=255)
        av.putalpha(m)
        return av


# ═══════════════════════════════════════════════════════════════════════
# Card Generator
# ═══════════════════════════════════════════════════════════════════════

def generate_profile_card(avatar, nickname, level, xp, xp_needed,
                          messages, voice_seconds, balance,
                          rank_messages, rank_voice, rank_balance):

    img = _bg(W, H).convert('RGBA')
    d = ImageDraw.Draw(img)

    avg_rank = max(1, round((rank_messages + rank_voice + rank_balance) / 3))

    # ─── LEFT PANEL — ribbon / flag shape ───────────────────────────
    lx, ly = PAD, PAD
    y_flat = H - PAD - TAIL_H
    y_tip = H - PAD
    _ribbon_panel(img, lx, ly, lx + LW, y_flat, y_tip, radius=24)
    d = ImageDraw.Draw(img)

    av_sz = 148
    av_x = lx + (LW - av_sz) // 2
    av_y = ly + 46
    av_cx, av_cy = av_x + av_sz // 2, av_y + av_sz // 2

    # Soft glow behind avatar
    glow = Image.new('RGBA', img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((av_cx - av_sz, av_cy - av_sz, av_cx + av_sz, av_cy + av_sz),
                                  fill=(*PINK, 60))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(30)))
    d = ImageDraw.Draw(img)

    # Gradient ring (violet -> pink) around avatar
    ring_pad = 8
    ring_d = av_sz + ring_pad * 2
    ring = Image.new('RGBA', (ring_d, ring_d), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    steps = 240
    for i in range(steps):
        t = i / steps
        ang0 = t * 360
        r = int(VIOLET[0] + (PINK[0] - VIOLET[0]) * t)
        g = int(VIOLET[1] + (PINK[1] - VIOLET[1]) * t)
        b = int(VIOLET[2] + (PINK[2] - VIOLET[2]) * t)
        rd.arc((2, 2, ring_d - 2, ring_d - 2), ang0, ang0 + 360 / steps + 1, fill=(r, g, b, 255), width=7)
    img.alpha_composite(ring, (av_cx - ring_d // 2, av_cy - ring_d // 2))
    d = ImageDraw.Draw(img)

    # Thin dark separator ring so avatar edge stays crisp against gradient ring
    d.ellipse((av_x - 3, av_y - 3, av_x + av_sz + 3, av_y + av_sz + 3), outline=(14, 10, 20, 255), width=3)

    img.alpha_composite(avatar, (av_x, av_y))
    d = ImageDraw.Draw(img)

    # Username
    f_nick = _f(bold=True, sz=25)
    nick_y = av_y + av_sz + 30
    bb = d.textbbox((0, 0), nickname, font=f_nick)
    nw, nh = bb[2] - bb[0], bb[3] - bb[1]
    nx = lx + (LW - nw) // 2
    d.text((nx, nick_y), nickname, fill=WHITE, font=f_nick)

    # Simple underline
    uline_y = nick_y + nh + 14
    uw = 46
    d.line([(lx + (LW - uw) // 2, uline_y), (lx + (LW + uw) // 2, uline_y)], fill=(*MUTED, 130), width=2)

    # ─── TOP RIGHT: LEVEL ──────────────────────────────────────────
    ty = PAD
    _panel(img, (RX, ty, RX + RW, ty + TOP_H), 22)
    d = ImageDraw.Draw(img)

    f_lvl_lbl = _f(bold=True, sz=15)
    f_lvl_num = _f(bold=True, sz=34)
    lbl_txt = "LEVEL"
    lbl_bb = d.textbbox((0, 0), lbl_txt, font=f_lvl_lbl)
    num_txt = str(level)
    total_w = (lbl_bb[2] - lbl_bb[0]) + 10 + d.textbbox((0, 0), num_txt, font=f_lvl_num)[2]
    start_x = RX + (RW - total_w) // 2
    top_y = ty + 26
    d.text((start_x, top_y + 8), lbl_txt, fill=VIOLET, font=f_lvl_lbl)
    d.text((start_x + (lbl_bb[2] - lbl_bb[0]) + 10, top_y - 2), num_txt, fill=WHITE, font=f_lvl_num)

    # XP row + progress bar
    f_xp = _f(bold=False, sz=13)
    barw = RW - 64
    barh = 10
    bar_x = RX + (RW - barw) // 2
    bar_y = ty + TOP_H - 40

    xp_txt = _fmt(xp)
    xp_max_txt = _fmt(xp_needed)
    d.text((bar_x, bar_y - 22), xp_txt, fill=WHITE, font=f_xp)
    bb2 = d.textbbox((0, 0), xp_max_txt, font=f_xp)
    d.text((bar_x + barw - (bb2[2] - bb2[0]), bar_y - 22), xp_max_txt, fill=MUTED, font=f_xp)

    prog = xp / xp_needed if xp_needed > 0 else 0
    bar = _xp_bar(barw, barh, prog)
    img.alpha_composite(bar, (bar_x, bar_y))
    d = ImageDraw.Draw(img)

    # ─── BOTTOM: STATS + RANKINGS ─────────────────────────────────
    by, bht = BOT_Y, BOT_H

    f_t = _f(bold=True, sz=13)
    f_v = _f(bold=True, sz=21)
    f_l = _f(bold=False, sz=11)

    badge_sz = 52
    blk_h = (bht - 50) // 3

    def _draw_stat_column(x0, title, rows):
        _panel(img, (x0, by, x0 + PW, by + bht), 20)
        dd = ImageDraw.Draw(img)
        tx = _text_cx(dd, title, f_t, x0, x0 + PW)
        dd.text((tx, by + 14), title, fill=VIOLET, font=f_t)
        dd.line([(x0 + 24, by + 34), (x0 + PW - 24, by + 34)], fill=(*MUTED_DK, 90), width=1)

        for i, (glyph_key, val_txt, label_txt) in enumerate(rows):
            row_y = by + 44 + i * blk_h
            icon_x = x0 + 20
            icon_y = row_y + (blk_h - badge_sz) // 2
            badge = _icon_badge(badge_sz, glyph_key)
            img.alpha_composite(badge, (icon_x, icon_y))
            dd = ImageDraw.Draw(img)

            text_x = icon_x + badge_sz + 16
            dd.text((text_x, row_y + blk_h // 2 - 22), val_txt, fill=WHITE, font=f_v)
            dd.text((text_x, row_y + blk_h // 2 + 4), label_txt, fill=MUTED, font=f_l)

    _draw_stat_column(RX, "STATISTICS", [
        ('chat', _fmt(messages), "messages"),
        ('voice', _fmt_t(voice_seconds), "voice time"),
        ('balance', f"${_fmt(balance)}", "balance"),
    ])

    _draw_stat_column(RX + PW + GAP, "RANKINGS", [
        ('chat', f"#{rank_messages}", "messages"),
        ('voice', f"#{rank_voice}", "voice time"),
        ('balance', f"#{rank_balance}", "balance"),
    ])

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
            av = await _avatar(member.display_avatar.url, sz=148)
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
            av = await _avatar(member.display_avatar.url, sz=148)
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
