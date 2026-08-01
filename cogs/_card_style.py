"""
Shared visual style kit — professional black/white/red dashboard aesthetic.
Used by profile.py, help_card.py and any future image-based UI so every
card in the bot shares the exact same fonts, palette and crisp rendering.
"""
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.join(os.path.dirname(__file__), '..')
FONTS = os.path.join(ROOT, 'assets', 'fonts')
BG_PATH = os.path.join(ROOT, 'assets', 'profile_bg_pro.jpg')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

# ═══════════════════════════════════════════════════════════════════════
# Palette — professional black / white / red
# ═══════════════════════════════════════════════════════════════════════
BLACK      = (18, 18, 20, 255)
INK        = (18, 18, 20, 255)
WHITE      = (255, 255, 255, 255)
RED        = (222, 28, 42, 255)
RED_DK     = (168, 18, 30, 255)
GRAY       = (128, 128, 132, 255)
GRAY_LT    = (205, 205, 208, 255)
GRAY_LINE  = (225, 225, 228, 255)
GOLD_TXT   = (180, 138, 20, 255)
SILVER_TXT = (110, 112, 118, 255)
BRONZE_TXT = (150, 92, 46, 255)

SS = 4  # supersampling factor for crisp anti-aliased vector shapes


def font(bold=False, sz=20):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT_R, sz)
    except Exception:
        return ImageFont.load_default()


def ss_render(w, h, draw_fn, scale=SS):
    """Render a transparent RGBA tile at `scale`x resolution using draw_fn(d, scale),
    then Lanczos-downscale to (w, h) for crisp anti-aliased output."""
    big = Image.new('RGBA', (max(1, w * scale), max(1, h * scale)), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    draw_fn(d, scale)
    return big.resize((w, h), Image.Resampling.LANCZOS)


def corner_bracket(size, thickness, length_ratio=0.30, color=RED):
    """A single L-shaped corner bracket (top-left orientation)."""
    def draw(d, scale):
        t = thickness * scale
        L = size * scale * length_ratio
        d.line([(0, t / 2), (L, t / 2)], fill=color, width=int(t))
        d.line([(t / 2, 0), (t / 2, L)], fill=color, width=int(t))
    return ss_render(size, size, draw)


def rounded_panel(w, h, radius, fill=WHITE, outline=BLACK, ow=3):
    def draw(d, scale):
        r = radius * scale
        o = ow * scale
        d.rounded_rectangle((o / 2, o / 2, w * scale - o / 2 - 1, h * scale - o / 2 - 1),
                             radius=r, fill=fill, outline=outline, width=int(o))
    return ss_render(w, h, draw)


def text_cx(draw, text, f, x1, x2):
    bb = draw.textbbox((0, 0), text, font=f)
    return x1 + (x2 - x1 - (bb[2] - bb[0])) // 2


def fit_font(draw, text, bold, start_sz, max_w, min_sz=8):
    f = font(bold=bold, sz=start_sz)
    bb = draw.textbbox((0, 0), text, font=f)
    while bb[2] - bb[0] > max_w and f.size > min_sz:
        f = font(bold=bold, sz=f.size - 1)
        bb = draw.textbbox((0, 0), text, font=f)
    return f


def bg(w, h, path=None):
    path = path or BG_PATH
    try:
        image = Image.open(path).convert('RGBA')
        bw, bh = image.size
        target_ratio = w / h
        src_ratio = bw / bh
        if src_ratio > target_ratio:
            new_w = int(bh * target_ratio)
            x0 = (bw - new_w) // 2
            image = image.crop((x0, 0, x0 + new_w, bh))
        else:
            new_h = int(bw / target_ratio)
            y0 = (bh - new_h) // 2
            image = image.crop((0, y0, bw, y0 + new_h))
        return image.resize((w, h), Image.Resampling.LANCZOS)
    except Exception:
        return Image.new('RGBA', (w, h), (255, 255, 255, 255))
