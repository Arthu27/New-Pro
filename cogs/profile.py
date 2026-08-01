"""
Profile Cog — Premium card generation via Pillow
Dark neon-purple glassmorphism, custom vector icons, real data
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

FONTS = os.path.join(os.path.dirname(__file__), '..', 'assets', 'fonts')
ICONS = os.path.join(os.path.dirname(__file__), '..', 'assets', 'icons')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

# Palette
BG1, BG2 = (8, 5, 18), (18, 12, 35)
NEON = (165, 80, 255)
NEON2 = (120, 50, 220)
BRIGHT = (210, 160, 255)
WHITE = (245, 242, 255)
MUTED = (130, 115, 165)
PANEL = (22, 16, 42, 200)
PANEL_HI = (30, 22, 55, 220)
BORDER = (140, 70, 230, 90)
STAT = (28, 20, 52, 210)
XP_BG = (35, 28, 60)
XP_A, XP_B = (130, 55, 215), (210, 90, 255)

W, H = 920, 500
LW = 250
GAP = 14
RX = LW + GAP + 18
RW = W - RX - 18


def _f(bold=False, sz=20):
    try: return ImageFont.truetype(FONT_B if bold else FONT_R, sz)
    except: return ImageFont.load_default()


# ═══════════════════════════════════════════════════════════════════════
# Vector Icons — programmatic neon cyberpunk
# ═══════════════════════════════════════════════════════════════════════

def _icon_base(sz=56):
    """Create base icon canvas with subtle glow"""
    img = Image.new('RGBA', (sz, sz), (0,0,0,0))
    g = Image.new('RGBA', (sz, sz), (0,0,0,0))
    gd = ImageDraw.Draw(g)
    gd.ellipse((sz//4, sz//4, sz*3//4, sz*3//4), fill=(*NEON2, 25))
    g = g.filter(ImageFilter.GaussianBlur(sz//5))
    return Image.alpha_composite(g, Image.new('RGBA', (sz, sz), (0,0,0,0))), ImageDraw.Draw(img)


def _neon_line(draw, p1, p2, color=NEON, width=2, glow_img=None):
    """Draw a line with neon glow"""
    if glow_img:
        gd = ImageDraw.Draw(glow_img)
        gd.line([p1, p2], fill=(*color, 60), width=width+4)
    draw.line([p1, p2], fill=(*BRIGHT, 220), width=width)


def _neon_poly(draw, pts, color=NEON, fill_alpha=25, glow_img=None, width=2):
    """Draw polygon with glow"""
    if glow_img:
        gd = ImageDraw.Draw(glow_img)
        gd.polygon(pts, fill=(*color, 40))
    draw.polygon(pts, outline=(*BRIGHT, 220), fill=(*color, fill_alpha))


def icon_messages(sz=56):
    """Crystal chat bubble with data streams"""
    glow = Image.new('RGBA', (sz, sz), (0,0,0,0))
    img = Image.new('RGBA', (sz, sz), (0,0,0,0))

    # Outer glow
    gd = ImageDraw.Draw(glow)
    pts = [(10,8),(sz-10,8),(sz-4,16),(sz-4,sz-20),(sz-10,sz-14),(sz//2+4,sz-14),
           (sz//2-2,sz-4),(sz//2-6,sz-14),(10,sz-14),(4,sz-20),(4,16)]
    gd.polygon(pts, fill=(*NEON, 50))
    glow = glow.filter(ImageFilter.GaussianBlur(6))

    d = ImageDraw.Draw(img)
    # Bubble shape
    d.polygon(pts, outline=(*BRIGHT, 200), fill=(*NEON2, 30))

    # Inner lines (data streams)
    for y_off, length, alpha in [(14, sz-28, 160), (20, sz-36, 120), (26, sz-44, 90), (32, sz-50, 60)]:
        x1 = 12
        x2 = x1 + length
        if x2 > sz - 12: x2 = sz - 12
        d.line([(x1, y_off), (x2, y_off)], fill=(*BRIGHT, alpha), width=1)

    # Floating data particles
    particles = [(sz-8, 4, 3), (sz-3, 10, 2), (sz-12, 2, 2), (sz+1, 6, 2), (sz-6, -2, 2)]
    for px, py, ps in particles:
        if 0 <= px < sz and 0 <= py < sz:
            d.rectangle((px, py, px+ps, py+ps), fill=(*BRIGHT, 180))

    glow_layer = glow.filter(ImageFilter.GaussianBlur(3))
    result = Image.alpha_composite(glow_layer, img)
    return result


def icon_voice(sz=56):
    """Sound wave spiral with frequency bars"""
    glow = Image.new('RGBA', (sz, sz), (0,0,0,0))
    img = Image.new('RGBA', (sz, sz), (0,0,0,0))
    cx, cy = sz//2, sz//2

    # Central glow
    gd = ImageDraw.Draw(glow)
    gd.ellipse((cx-12, cy-12, cx+12, cy+12), fill=(*NEON, 40))
    glow = glow.filter(ImageFilter.GaussianBlur(8))

    d = ImageDraw.Draw(img)

    # Frequency bars (equalizer style)
    bar_count = 9
    bar_w = 3
    total_w = bar_count * bar_w + (bar_count-1) * 2
    start_x = (sz - total_w) // 2
    heights = [12, 20, 28, 36, 40, 36, 28, 20, 12]

    for i, h in enumerate(heights):
        x = start_x + i * (bar_w + 2)
        y_top = cy - h//2
        y_bot = cy + h//2
        alpha = 140 + int(115 * (h / 40))
        # Bar glow
        d.rectangle((x-1, y_top-1, x+bar_w+1, y_bot+1), fill=(*NEON2, 40))
        # Bar
        d.rectangle((x, y_top, x+bar_w, y_bot), fill=(*BRIGHT, alpha))
        # Top cap
        d.rectangle((x-1, y_top-2, x+bar_w+1, y_top), fill=(*BRIGHT, min(255, alpha+40)))

    # Circular wave rings
    for r, alpha in [(sz//2-2, 50), (sz//2+4, 30)]:
        d.arc((cx-r, cy-r, cx+r, cy+r), -30, 30, fill=(*NEON, alpha), width=1)
        d.arc((cx-r, cy-r, cx+r, cy+r), 150, 210, fill=(*NEON, alpha), width=1)

    result = Image.alpha_composite(glow, img)
    return result


def icon_balance(sz=56):
    """Hexagonal crystal vault with currency symbol"""
    glow = Image.new('RGBA', (sz, sz), (0,0,0,0))
    img = Image.new('RGBA', (sz, sz), (0,0,0,0))
    cx, cy = sz//2, sz//2

    # Hex dimensions
    r = sz//2 - 6
    hex_pts = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        hex_pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    # Glow
    gd = ImageDraw.Draw(glow)
    gd.polygon(hex_pts, fill=(*NEON, 40))
    glow = glow.filter(ImageFilter.GaussianBlur(7))

    d = ImageDraw.Draw(img)

    # Outer hex
    d.polygon(hex_pts, outline=(*BRIGHT, 200), fill=(*NEON2, 25))

    # Inner hex
    r2 = r * 0.65
    inner_pts = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        inner_pts.append((cx + r2 * math.cos(angle), cy + r2 * math.sin(angle)))
    d.polygon(inner_pts, outline=(*NEON, 100), fill=(*NEON2, 15))

    # Connecting lines (crystal facets)
    for i in range(6):
        d.line([hex_pts[i], inner_pts[i]], fill=(*NEON, 60), width=1)

    # Currency symbol — custom drawn $ as two S curves + vertical line
    # Vertical line
    d.line([(cx, cy-12), (cx, cy+12)], fill=(*BRIGHT, 200), width=2)
    # S curves
    d.arc((cx-7, cy-12, cx+7, cy), 180, 360, fill=(*BRIGHT, 200), width=2)
    d.arc((cx-7, cy, cx+7, cy+12), 0, 180, fill=(*BRIGHT, 200), width=2)

    # Corner dots
    for pt in hex_pts:
        d.ellipse((pt[0]-2, pt[1]-2, pt[0]+2, pt[1]+2), fill=(*BRIGHT, 180))

    result = Image.alpha_composite(glow, img)
    return result


def icon_rank(sz=56):
    """Trophy/crown microphone with aura"""
    glow = Image.new('RGBA', (sz, sz), (0,0,0,0))
    img = Image.new('RGBA', (sz, sz), (0,0,0,0))
    cx = sz//2

    # Aura glow
    gd = ImageDraw.Draw(glow)
    gd.ellipse((cx-16, 6, cx+16, 38), fill=(*NEON, 35))
    glow = glow.filter(ImageFilter.GaussianBlur(7))

    d = ImageDraw.Draw(img)

    # Microphone capsule
    cap_top, cap_bot = 10, 30
    cap_w = 9
    d.rounded_rectangle((cx-cap_w, cap_top, cx+cap_w, cap_bot), radius=cap_w,
                        outline=(*BRIGHT, 200), fill=(*NEON2, 35))
    # Mesh lines
    for y in range(cap_top+5, cap_bot-3, 3):
        d.line([(cx-cap_w+3, y), (cx+cap_w-3, y)], fill=(*NEON, 70), width=1)

    # Stand
    d.line([(cx, cap_bot), (cx, 40)], fill=(*BRIGHT, 180), width=2)
    # Base arc
    d.arc((cx-12, 34, cx+12, 48), 0, 180, fill=(*BRIGHT, 140), width=2)
    d.line([(cx-14, 44), (cx+14, 44)], fill=(*NEON, 100), width=1)

    # Crown (3 peaks)
    cr_y = 4
    crown = [
        (cx-14, cr_y+10), (cx-10, cr_y+2), (cx-5, cr_y+7),
        (cx, cr_y-2), (cx+5, cr_y+7), (cx+10, cr_y+2), (cx+14, cr_y+10)
    ]
    d.polygon(crown, outline=(*BRIGHT, 220), fill=(*NEON, 30))

    # Crown jewels
    for px, py in [(cx-10, cr_y+2), (cx, cr_y-2), (cx+10, cr_y+2)]:
        d.ellipse((px-2, py-2, px+2, py+2), fill=(*BRIGHT, 255))
        # Tiny glow
        d.ellipse((px-4, py-4, px+4, py+4), fill=(*NEON, 30))

    # Sound waves from mic
    for r, alpha in [(18, 80), (24, 50), (30, 30)]:
        d.arc((cx-r, 15-r//2, cx+r, 15+r//2+r), -60, 60, fill=(*NEON, alpha), width=1)

    result = Image.alpha_composite(glow, img)
    return result


def _gen_icons(sz=56):
    """Generate all icons"""
    return {
        'messages': icon_messages(sz),
        'voice': icon_voice(sz),
        'balance': icon_balance(sz),
        'rank': icon_rank(sz),
    }


# ═══════════════════════════════════════════════════════════════════════
# Drawing Helpers
# ═══════════════════════════════════════════════════════════════════════

def _panel(img, xy, radius, fill=PANEL, border=BORDER, bw=2):
    o = Image.new('RGBA', img.size, (0,0,0,0))
    ImageDraw.Draw(o).rounded_rectangle(xy, radius=radius, fill=fill, outline=border, width=bw)
    return Image.alpha_composite(img, o)


def _glow_spot(img, cx, cy, r, color=NEON, alpha=25, blur=50):
    o = Image.new('RGBA', img.size, (0,0,0,0))
    ImageDraw.Draw(o).ellipse((cx-r, cy-r, cx+r, cy+r), fill=(*color, alpha))
    o = o.filter(ImageFilter.GaussianBlur(blur))
    return Image.alpha_composite(img, o)


def _text_cx(draw, text, font, x1, x2):
    bb = draw.textbbox((0,0), text, font=font)
    return x1 + (x2 - x1 - (bb[2]-bb[0])) // 2


def _xp_bar(w, h, progress):
    bar = Image.new('RGBA', (w, h), XP_BG + (255,))
    fw = max(1, int(w * min(progress, 1.0)))
    for x in range(fw):
        t = x / max(w-1, 1)
        r = int(XP_A[0]+(XP_B[0]-XP_A[0])*t)
        g = int(XP_A[1]+(XP_B[1]-XP_A[1])*t)
        b = int(XP_A[2]+(XP_B[2]-XP_A[2])*t)
        ImageDraw.Draw(bar).line([(x,0),(x,h-1)], fill=(r,g,b,255))
    m = Image.new('L', (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0,0,w,h), radius=h//2, fill=255)
    bar.putalpha(m)
    # Bright tip
    if fw > 4:
        tip = Image.new('RGBA', (6, h), (0,0,0,0))
        ImageDraw.Draw(tip).rounded_rectangle((0,0,6,h), radius=3, fill=(*BRIGHT, 120))
        tip = tip.filter(ImageFilter.GaussianBlur(2))
        bar.paste(tip, (fw-6, 0), tip)
    return bar


def _bg(w, h):
    """Generate premium background"""
    # Try loading cached bg
    bg_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'profile_bg.png')
    try:
        bg = Image.open(bg_path).convert('RGBA').resize((w, h), Image.Resampling.LANCZOS)
        return bg
    except:
        pass
    # Fallback: generate
    img = Image.new('RGBA', (w, h), BG1 + (255,))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        r = int(BG1[0]+(BG2[0]-BG1[0])*t)
        g = int(BG1[1]+(BG2[1]-BG1[1])*t)
        b = int(BG1[2]+(BG2[2]-BG1[2])*t)
        d.line([(0,y),(w,y)], fill=(r,g,b,255))
    return img


def _fmt(n): return f"{n:,}".replace(","," ")
def _fmt_t(s):
    h, m = s//3600, (s%3600)//60
    return f"{h}h {m}m" if h else f"{m}m"


async def _avatar(url, sz=180):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.read()
        av = Image.open(io.BytesIO(data)).convert('RGBA').resize((sz,sz), Image.Resampling.LANCZOS)
        m = Image.new('L', (sz,sz), 0)
        ImageDraw.Draw(m).ellipse((0,0,sz,sz), fill=255)
        av.putalpha(m)
        return av
    except:
        av = Image.new('RGBA', (sz,sz), (0,0,0,0))
        ImageDraw.Draw(av).ellipse((0,0,sz,sz), fill=(50,40,80,255))
        return av


# ═══════════════════════════════════════════════════════════════════════
# Card Generator
# ═══════════════════════════════════════════════════════════════════════

def generate_profile_card(avatar, nickname, level, xp, xp_needed,
                          messages, voice_seconds, balance,
                          rank_messages, rank_voice, rank_balance):

    img = _bg(W, H)

    # Atmospheric glow spots
    img = _glow_spot(img, 60, 60, 200, NEON, 20, 80)
    img = _glow_spot(img, W-100, H-80, 180, NEON2, 18, 70)
    img = _glow_spot(img, W//2, -30, 160, (100,50,200), 12, 60)

    d = ImageDraw.Draw(img)

    # Subtle grid
    grid = Image.new('RGBA', (W,H), (0,0,0,0))
    gd = ImageDraw.Draw(grid)
    for x in range(0, W, 50):
        gd.line([(x,0),(x,H)], fill=(255,255,255,4), width=1)
    for y in range(0, H, 50):
        gd.line([(0,y),(W,y)], fill=(255,255,255,4), width=1)
    img = Image.alpha_composite(img, grid)

    # ─── LEFT PANEL ─────────────────────────────────────────────────
    lx, ly = 18, 18
    img = _panel(img, (lx, ly, lx+LW, H-18), 20, PANEL, BORDER, 2)
    d = ImageDraw.Draw(img)

    # Decorative line at top of panel
    d.line([(lx+20, ly+2), (lx+LW-20, ly+2)], fill=(*NEON, 60), width=1)

    # Avatar with double ring
    av_sz = 155
    av_x = lx + (LW - av_sz) // 2
    av_y = ly + 45

    # Outer glow ring
    ring_glow = Image.new('RGBA', (W,H), (0,0,0,0))
    rgd = ImageDraw.Draw(ring_glow)
    p1 = 14
    rgd.ellipse((av_x-p1, av_y-p1, av_x+av_sz+p1, av_y+av_sz+p1),
                outline=(*NEON, 35), width=12)
    ring_glow = ring_glow.filter(ImageFilter.GaussianBlur(10))
    img = Image.alpha_composite(img, ring_glow)
    d = ImageDraw.Draw(img)

    # Outer ring
    p2 = 6
    d.ellipse((av_x-p2, av_y-p2, av_x+av_sz+p2, av_y+av_sz+p2),
              outline=(*NEON, 160), width=2)
    # Inner ring
    d.ellipse((av_x-2, av_y-2, av_x+av_sz+2, av_y+av_sz+2),
              outline=(*BRIGHT, 120), width=1)

    # Paste avatar
    img.paste(avatar, (av_x, av_y), avatar)

    # Level badge on avatar
    badge_r = 18
    badge_x = av_x + av_sz - 8
    badge_y = av_y + av_sz - 8
    badge = Image.new('RGBA', (W,H), (0,0,0,0))
    bd = ImageDraw.Draw(badge)
    bd.ellipse((badge_x-badge_r, badge_y-badge_r, badge_x+badge_r, badge_y+badge_r),
               fill=(20,14,40,240), outline=(*NEON, 200), width=2)
    img = Image.alpha_composite(img, badge)
    d = ImageDraw.Draw(img)
    f_badge = _f(bold=True, sz=16)
    lv_txt = str(level)
    lv_x = _text_cx(d, lv_txt, f_badge, badge_x-badge_r, badge_x+badge_r)
    d.text((lv_x, badge_y-9), lv_txt, fill=WHITE, font=f_badge)

    # Nickname with backdrop
    f_nick = _f(bold=True, sz=28)
    nick_y = av_y + av_sz + 22
    bb = d.textbbox((0,0), nickname, font=f_nick)
    nw = bb[2]-bb[0]
    nh = bb[3]-bb[1]
    nx = lx + (LW - nw) // 2

    # Backdrop
    bdrop = Image.new('RGBA', (W,H), (0,0,0,0))
    ImageDraw.Draw(bdrop).rounded_rectangle(
        (nx-14, nick_y-8, nx+nw+14, nick_y+nh+10),
        radius=10, fill=(8,5,18,210))
    img = Image.alpha_composite(img, bdrop)
    d = ImageDraw.Draw(img)

    # Text shadow
    for ox in [-1,0,1]:
        for oy in [-1,0,1]:
            if ox==0 and oy==0: continue
            d.text((nx+ox, nick_y+oy), nickname, fill=(30,20,50), font=f_nick)
    d.text((nx, nick_y), nickname, fill=WHITE, font=f_nick)

    # Separator
    sep_y = nick_y + nh + 20
    # Gradient line
    for x in range(lx+30, lx+LW-30):
        t = (x - (lx+30)) / (LW-60)
        alpha = int(100 * math.sin(t * math.pi))
        d.point((x, sep_y), fill=(*NEON, alpha))
        d.point((x, sep_y+1), fill=(*NEON, alpha//2))

    # Server rank
    f_rl = _f(bold=False, sz=11)
    f_rv = _f(bold=True, sz=22)
    avg_rank = max(1, (rank_messages + rank_voice + rank_balance) // 3)

    rl_y = sep_y + 14
    rx = _text_cx(d, "SERVER RANK", f_rl, lx, lx+LW)
    d.text((rx, rl_y), "SERVER RANK", fill=MUTED, font=f_rl)
    rv_txt = f"#{avg_rank}"
    rv_x = _text_cx(d, rv_txt, f_rv, lx, lx+LW)
    # Glow behind rank
    d.text((rv_x, rl_y+16), rv_txt, fill=(*NEON, 60), font=f_rv)
    d.text((rv_x+1, rl_y+16), rv_txt, fill=BRIGHT, font=f_rv)

    # ─── TOP RIGHT: LEVEL ──────────────────────────────────────────
    ty = 18
    top_h = 160
    img = _panel(img, (RX, ty, W-18, ty+top_h), 20, PANEL, BORDER, 2)
    d = ImageDraw.Draw(img)

    # Decorative accent line
    d.line([(RX+24, ty+3), (RX+100, ty+3)], fill=(*NEON, 80), width=2)

    f_ll = _f(bold=True, sz=12)
    f_ln = _f(bold=True, sz=60)
    f_xp = _f(bold=False, sz=13)

    d.text((RX+28, ty+18), "LEVEL", fill=MUTED, font=f_ll)

    # Big level number with glow
    lv_str = str(level)
    d.text((RX+29, ty+34), lv_str, fill=(*NEON, 50), font=f_ln)
    d.text((RX+28, ty+33), lv_str, fill=WHITE, font=f_ln)

    # XP info
    bar_y = ty + top_h - 44
    d.text((RX+28, bar_y-20), f"{_fmt(xp)} XP", fill=WHITE, font=f_xp)
    xp_max = _fmt(xp_needed) + " XP"
    bb2 = d.textbbox((0,0), xp_max, font=f_xp)
    d.text((W-18-28-(bb2[2]-bb2[0]), bar_y-20), xp_max, fill=MUTED, font=f_xp)

    # Progress bar
    bw = RW - 56
    bh = 12
    prog = xp / xp_needed if xp_needed > 0 else 0
    bar = _xp_bar(bw, bh, prog)
    img.paste(bar, (RX+28, bar_y), bar)
    d = ImageDraw.Draw(img)

    # Percentage
    pct = f"{int(prog*100)}%"
    f_pct = _f(bold=True, sz=11)
    px = _text_cx(d, pct, f_pct, RX+28, RX+28+bw)
    d.text((px, bar_y+bh+4), pct, fill=MUTED, font=f_pct)

    # ─── BOTTOM: STATS + RANKINGS ─────────────────────────────────
    by = ty + top_h + GAP
    bh_total = H - by - 18
    pw = (RW - GAP) // 2

    # Generate icons
    icons = _gen_icons(42)

    # STATS panel
    img = _panel(img, (RX, by, RX+pw, by+bh_total), 18, PANEL, BORDER, 2)
    d = ImageDraw.Draw(img)

    f_t = _f(bold=True, sz=12)
    f_v = _f(bold=True, sz=19)
    f_l = _f(bold=False, sz=10)

    tx = _text_cx(d, "STATISTICS", f_t, RX, RX+pw)
    d.text((tx, by+10), "STATISTICS", fill=MUTED, font=f_t)
    d.line([(RX+20, by+26), (RX+pw-20, by+26)], fill=(*NEON, 40), width=1)

    stat_items = [
        (icons['messages'], _fmt(messages), "MESSAGES"),
        (icons['voice'], _fmt_t(voice_seconds), "VOICE TIME"),
        (icons['balance'], f"${_fmt(balance)}", "BALANCE"),
    ]
    blk_h = (bh_total - 42) // 3
    for i, (icon, val, label) in enumerate(stat_items):
        bx = RX + 8
        bby = by + 34 + i * blk_h
        bwi = pw - 16
        bhi = blk_h - 6

        img = _panel(img, (bx, bby, bx+bwi, bby+bhi), 10, STAT, (*NEON, 40), 1)
        d = ImageDraw.Draw(img)

        iy = bby + (bhi - 42) // 2
        img.paste(icon, (bx+6, iy), icon)
        d = ImageDraw.Draw(img)

        d.text((bx+54, bby+8), val, fill=WHITE, font=f_v)
        d.text((bx+54, bby+bhi-16), label, fill=MUTED, font=f_l)

    # RANKINGS panel
    rkx = RX + pw + GAP
    img = _panel(img, (rkx, by, rkx+pw, by+bh_total), 18, PANEL, BORDER, 2)
    d = ImageDraw.Draw(img)

    tx = _text_cx(d, "RANKINGS", f_t, rkx, rkx+pw)
    d.text((tx, by+10), "RANKINGS", fill=MUTED, font=f_t)
    d.line([(rkx+20, by+26), (rkx+pw-20, by+26)], fill=(*NEON, 40), width=1)

    rank_items = [
        (icons['messages'], f"#{rank_messages}", "MESSAGES"),
        (icons['voice'], f"#{rank_voice}", "VOICE TIME"),
        (icons['balance'], f"#{rank_balance}", "BALANCE"),
    ]
    for i, (icon, val, label) in enumerate(rank_items):
        bx = rkx + 8
        bby = by + 34 + i * blk_h
        bwi = pw - 16
        bhi = blk_h - 6

        img = _panel(img, (bx, bby, bx+bwi, bby+bhi), 10, STAT, (*NEON, 40), 1)
        d = ImageDraw.Draw(img)

        iy = bby + (bhi - 42) // 2
        img.paste(icon, (bx+6, iy), icon)
        d = ImageDraw.Draw(img)

        d.text((bx+54, bby+8), val, fill=BRIGHT, font=f_v)
        d.text((bx+54, bby+bhi-16), label, fill=MUTED, font=f_l)

    # ─── Watermark ─────────────────────────────────────────────────
    f_wm = _f(bold=False, sz=9)
    d.text((W-80, H-14), "AETHER BOT", fill=(*MUTED, 80), font=f_wm)

    return img.convert('RGB')


# ═══════════════════════════════════════════════════════════════════════
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
            av = await _avatar(member.display_avatar.url)
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
            av = await _avatar(member.display_avatar.url)
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
