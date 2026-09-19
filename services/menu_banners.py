# -*- coding: utf-8 -*-
"""Фирменные баннеры и стикеры меню Discord (стиль HAKUMO «НАБОРЫ»).

Баннеры: золотой дым/звёзды из assets + мягкий фиолетовый тон,
крупный градиентный заголовок, pill-CTA, H A K U M O.

Стикер в селекте по умолчанию — 🤍 (как в референсе). Можно заменить:
  • env MENU_SELECT_EMOJI=🤍
  • или свой эмодзи сервера: MENU_SELECT_EMOJI='<:hakumo:1234567890>'
    (залить assets/stickers/heart.png как эмодзи)
Свои баннеры (без перерисовки): assets/modpanel_banner_custom.png
Стикеры-иконки (залить как эмодзи сервера): assets/stickers/*.png
"""
from __future__ import annotations

import io
import math
import os
import random
import re
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, 'assets')
STICKERS = os.path.join(ASSETS, 'stickers')
FONTS = os.path.join(ASSETS, 'fonts')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

W, H = 1200, 520

# Пресеты: headline + pill без повторов (слово заголовка и бренд HAKUMO
# уже на баннере — в pill их не дублируем).
PRESETS = {
    'modpanel': {
        'headline': 'МОДЕРАЦИЯ',
        'pill': 'Панель модерации · Hakumo',
        'accent': (245, 245, 248),
        'tint': (8, 8, 10),
        'bgs': ('help_bg.png', 'hakumo_log_bg.png', 'staff.jpg'),
    },
    'appeals': {
        'headline': 'АПЕЛЛЯЦИИ',
        'pill': 'Обжаловать наказание',
        'accent': (245, 245, 248),
        'tint': (8, 8, 10),
        'bgs': ('hakumo_log_bg.png', 'help_bg.png', 'staff.jpg'),
    },
    'staff': {
        'headline': 'НАБОРЫ',
        'pill': 'Стань частью команды',
        'accent': (245, 245, 248),
        'tint': (8, 8, 10),
        'bgs': ('staff.jpg', 'help_bg.png', 'hakumo_log_bg.png'),
    },
    'events': {
        'headline': 'ИВЕНТЫ',
        'pill': 'Анонсы и запись',
        'accent': (245, 245, 248),
        'tint': (8, 8, 10),
        'bgs': ('help_bg.png', 'hakumo_log_bg.png', 'staff.jpg'),
    },
}

# Только *_custom* — ручная подмена без перерисовки кода
_CUSTOM_NAMES = {
    'modpanel': ('modpanel_banner_custom.png', 'modpanel_banner_custom.jpg',
                 'modpanel_custom.png', 'modpanel_custom.jpg'),
    'appeals': ('appeals_banner_custom.png', 'appeals_banner_custom.jpg',
                'appeals_custom.png', 'appeals_custom.jpg'),
    'staff': ('staff_banner_custom.png', 'staff_hakumo_banner.png',
              'staff_banner_custom.jpg'),
    'events': ('events_banner_custom.png', 'events_banner_custom.jpg',
               'events_banner.png'),
}

# Стикеры действий → серебристый акцент (чёрная тема)
STICKER_SPECS = {
    'warn':       {'accent': (240, 240, 245), 'icon': 'warn'},
    'mute':       {'accent': (220, 225, 235), 'icon': 'mute'},
    'ban':        {'accent': (235, 235, 240), 'icon': 'ban'},
    'clear':      {'accent': (230, 235, 240), 'icon': 'clear'},
    'unban':      {'accent': (225, 230, 235), 'icon': 'unban'},
    'appeal':     {'accent': (235, 235, 240), 'icon': 'appeal'},
    'helper':     {'accent': (240, 240, 245), 'icon': 'helper'},
    'moderator':  {'accent': (230, 230, 240), 'icon': 'mod'},
    'heart':      {'accent': (245, 245, 250), 'icon': 'heart'},
}


def _font(bold=False, sz=20):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT_R, sz)
    except Exception:
        return ImageFont.load_default()


def _find_custom(kind: str) -> Optional[str]:
    for name in _CUSTOM_NAMES.get(kind, ()):
        path = os.path.join(ASSETS, name)
        if os.path.isfile(path):
            return path
    return None


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    bw, bh = img.size
    target = w / h
    src = bw / bh
    if src > target:
        nw = int(bh * target)
        x0 = (bw - nw) // 2
        img = img.crop((x0, 0, x0 + nw, bh))
    else:
        nh = int(bw / target)
        y0 = (bh - nh) // 2
        img = img.crop((0, y0, bw, y0 + nh))
    return img.resize((w, h), Image.Resampling.LANCZOS)


def _load_atmosphere(kind: str) -> Image.Image:
    """Премиум-фон: реальный asset + мягкий фиолетовый тон как у «НАБОРЫ»."""
    preset = PRESETS.get(kind, PRESETS['modpanel'])
    custom = _find_custom(kind)
    if custom:
        try:
            return _cover(Image.open(custom).convert('RGBA'), W, H)
        except Exception:
            pass

    base = None
    for name in preset['bgs']:
        path = os.path.join(ASSETS, name)
        if os.path.isfile(path):
            try:
                base = _cover(Image.open(path).convert('RGBA'), W, H)
                break
            except Exception:
                continue
    if base is None:
        base = Image.new('RGBA', (W, H), (12, 10, 18, 255))

    # лёгкое затемнение только центра — золотой дым по краям читается
    dark = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dark)
    for y in range(H):
        edge_y = min(y, H - 1 - y) / (H * 0.48)
        a = int(35 + 45 * max(0.0, 1.0 - edge_y))
        dd.line([(0, y), (W, y)], fill=(6, 4, 12, a))
    # горизонтальный центр чуть темнее для контраста текста
    for x in range(W):
        edge_x = min(x, W - 1 - x) / (W * 0.35)
        a = int(40 * max(0.0, 1.0 - edge_x))
        if a:
            dd.line([(x, int(H * 0.22)), (x, int(H * 0.72))],
                    fill=(4, 2, 10, a))
    base = Image.alpha_composite(base, dark)

    # очень мягкий фиолетовый тон по краям — золото остаётся главным
    tint = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    tp = tint.load()
    tr, tg, tb = preset['tint']
    for x in range(0, W, 2):
        for y in range(0, H, 2):
            edge = min(x, W - 1 - x) / (W * 0.48)
            edge = max(0.0, 1.0 - edge)
            a = int(42 * edge)
            if a < 3:
                continue
            for dx in (0, 1):
                for dy in (0, 1):
                    xx, yy = x + dx, y + dy
                    if xx < W and yy < H:
                        tp[xx, yy] = (tr, tg, tb, a)
    tint = tint.filter(ImageFilter.GaussianBlur(22))
    base = Image.alpha_composite(base, tint)

    # мягкие световые орбы (глубина)
    orbs = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(orbs)
    for cx, cy, r, col in (
        (180, 90, 160, (*preset['accent'], 28)),
        (1020, 330, 180, (255, 200, 140, 22)),
        (600, 380, 220, (*preset['accent'], 18)),
    ):
        od.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)
    orbs = orbs.filter(ImageFilter.GaussianBlur(40))
    base = Image.alpha_composite(base, orbs)

    # редкие блики-звёзды поверх
    spark = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(spark)
    rng = random.Random(hash(kind) & 0xFFFF)
    for _ in range(48):
        x = rng.randint(40, W - 40)
        y = rng.randint(20, H - 20)
        s = rng.choice((1, 1, 2, 2, 3))
        a = rng.randint(90, 200)
        sd.ellipse((x, y, x + s, y + s), fill=(255, 245, 230, a))
    base = Image.alpha_composite(base, spark)

    base = ImageEnhance.Contrast(base).enhance(1.08)
    base = ImageEnhance.Color(base).enhance(1.18)
    base = ImageEnhance.Brightness(base).enhance(1.04)
    return base


def _spaced(text: str) -> str:
    return '  '.join(list(text.replace(' ', '')))


def _center_text(draw, text, font, y, fill, w, stroke=0, stroke_fill=None):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    kw = {}
    if stroke:
        kw['stroke_width'] = stroke
        kw['stroke_fill'] = stroke_fill or (0, 0, 0, 180)
    draw.text(((w - tw) / 2, y), text, font=font, fill=fill, **kw)


# Готовые premium-исходники (AI) → assets/, иначе procedural
_PREMIUM_SRC = {
    'modpanel': (
        'modpanel_banner_premium_src.png',
        '/opt/cursor/artifacts/assets/modpanel-banner-premium.png',
    ),
    'appeals': (
        'appeals_banner_premium_src.png',
        '/opt/cursor/artifacts/assets/appeals-banner-premium.png',
    ),
}


def _gradient_headline(img: Image.Image, text: str, y: int, accent) -> Image.Image:
    """Чёткий белый заголовок с лёгким neon-glow (буквы острые)."""
    f_head = _font(True, max(64, min(96, H // 4)))
    glow_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    _center_text(gd, text, f_head, y, (255, 255, 255, 100), W,
                 stroke=10, stroke_fill=(255, 255, 255, 50))
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(10))
    out = Image.alpha_composite(img, glow_layer)
    # второй мягкий ореол
    glow2 = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    g2 = ImageDraw.Draw(glow2)
    _center_text(g2, text, f_head, y, (255, 255, 255, 55), W)
    glow2 = glow2.filter(ImageFilter.GaussianBlur(22))
    out = Image.alpha_composite(out, glow2)
    sharp = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sharp)
    _center_text(sd, text, f_head, y, (255, 255, 255, 255), W,
                 stroke=1, stroke_fill=(0, 0, 0, 140))
    return Image.alpha_composite(out, sharp)


def _draw_banner_chrome(img: Image.Image, kind: str) -> Image.Image:
    """HAKUMO + headline + pill поверх фона — всегда чёткие буквы."""
    preset = PRESETS.get(kind, PRESETS['modpanel'])
    d = ImageDraw.Draw(img)
    brand = _spaced('HAKUMO')
    f_brand = _font(False, 18)
    f_pill = _font(False, 20)
    accent = preset['accent']
    headline = preset['headline']
    pill = preset['pill']

    _center_text(d, brand, f_brand, 48, (240, 240, 245, 235), W)
    line_w = 120
    ly = 82
    d.line(((W - line_w) // 2, ly, (W + line_w) // 2, ly),
           fill=(255, 255, 255, 170), width=1)

    img = _gradient_headline(img, headline, 140, accent)
    d = ImageDraw.Draw(img)

    pb = d.textbbox((0, 0), pill, font=f_pill)
    pw, ph = pb[2] - pb[0] + 52, pb[3] - pb[1] + 24
    px0, py0 = (W - pw) // 2, 300
    # soft glow behind pill
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.rounded_rectangle((px0 - 10, py0 - 10, px0 + pw + 10, py0 + ph + 10),
                         radius=ph // 2 + 10, fill=(255, 255, 255, 35))
    glow = glow.filter(ImageFilter.GaussianBlur(12))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((px0, py0, px0 + pw, py0 + ph),
                        radius=max(14, ph // 2),
                        fill=(0, 0, 0, 230),
                        outline=(255, 255, 255, 230), width=2)
    _center_text(d, pill, f_pill, py0 + 9, (255, 255, 255, 255), W)
    return img.convert('RGBA')


def _premium_bg(kind: str) -> Optional[Image.Image]:
    """Мягкий premium-фон из AI-исходника (только атмосфера, без текста)."""
    names = _PREMIUM_SRC.get(kind)
    if not names:
        return None
    asset_name, artifact = names
    candidates = (
        os.path.join(ASSETS, asset_name),
        artifact,
    )
    for path in candidates:
        if not path or not os.path.isfile(path):
            continue
        try:
            raw = Image.open(path).convert('RGBA')
            covered = _cover(raw, W, H)
            # blur убивает AI/старый текст, космос остаётся читаемым
            covered = covered.filter(ImageFilter.GaussianBlur(20))
            covered = ImageEnhance.Brightness(covered).enhance(0.55)
            dark = Image.new('RGBA', (W, H), (0, 0, 0, 110))
            covered = Image.alpha_composite(covered, dark)
            # мягкая вуаль по центру под наш текст
            veil = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            vd = ImageDraw.Draw(veil)
            vd.ellipse((W * 0.12, H * 0.05, W * 0.88, H * 0.95),
                       fill=(0, 0, 0, 120))
            veil = veil.filter(ImageFilter.GaussianBlur(36))
            covered = Image.alpha_composite(covered, veil)
            # редкие острые звёзды поверх
            spark = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            sd = ImageDraw.Draw(spark)
            rng = random.Random(hash(kind) ^ 0xA5A5)
            for _ in range(70):
                x = rng.randint(20, W - 20)
                y = rng.randint(15, H - 15)
                s = rng.choice((1, 1, 1, 2))
                a = rng.randint(100, 210)
                sd.ellipse((x, y, x + s, y + s), fill=(255, 255, 255, a))
            return Image.alpha_composite(covered, spark)
        except Exception:
            continue
    return None


def render_menu_banner(kind: str = 'modpanel') -> Image.Image:
    """PNG-баннер 1200×520: premium-фон + чёткие буквы. Селекты не трогаем."""
    # ручная подмена целиком (без перерисовки), если *_custom*
    custom = _find_custom(kind)
    if custom:
        try:
            return _cover(Image.open(custom).convert('RGBA'), W, H)
        except Exception:
            pass
    return _render_banner_fresh(kind)


def menu_banner_bytes(kind: str = 'modpanel') -> bytes:
    buf = io.BytesIO()
    render_menu_banner(kind).save(buf, format='PNG', optimize=True)
    return buf.getvalue()


def menu_banner_file(kind: str = 'modpanel', filename: str = None):
    """(BytesIO, filename) для discord.File.

    Имя файла версионируем — иначе Discord CDN держит старый PNG
    с «Панель модерации · Hakumo».
    """
    raw = menu_banner_bytes(kind)
    bio = io.BytesIO(raw)
    bio.seek(0)
    name = filename or f'hakumo_{kind}_banner_v13.png'
    return bio, name


def select_label(text: str) -> str:
    """Подпись пункта селекта «› Moderator»."""
    t = str(text or '').strip()
    if t.startswith('›') or t.startswith('🤍'):
        return t[:100]
    return f'› {t}'[:100]


def select_emoji():
    """Стикер селекта: gold-neon heart (application emoji) или 🤍 / env.

    MENU_SELECT_EMOJI перекрывает всё (unicode или <:name:id>).
    """
    raw = (os.environ.get('MENU_SELECT_EMOJI') or '').strip()
    if raw:
        m = re.fullmatch(r'<(a)?:([\w~]+):(\d+)>', raw)
        if m:
            try:
                import discord
                return discord.PartialEmoji(
                    name=m.group(2), id=int(m.group(3)),
                    animated=bool(m.group(1)))
            except Exception:
                return '🤍'
        return raw
    try:
        from services.menu_emojis import emoji_heart
        return emoji_heart()
    except Exception:
        return '🤍'


# ─── иконки стикеров ───────────────────────────────────────────

def _icon_layer(size: int, accent, kind: str) -> Image.Image:
    """Мягкая светящаяся пиктограмма (рисуем крупно → blur glow)."""
    layer = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    ink = (255, 255, 255, 255)
    s = size / 128.0
    stroke = max(3, int(7 * s))

    def L(pts, w=None):
        ww = stroke if w is None else max(2, int(w * s))
        d.line([(p[0] * s, p[1] * s) for p in pts],
               fill=ink, width=ww, joint='curve')

    def E(box, fill=None, outline=ink, width=None):
        b = [v * s for v in box]
        ww = stroke if width is None else max(2, int(width * s))
        d.ellipse(b, fill=fill, outline=outline if fill is None else None,
                  width=ww if fill is None else 0)

    def P(pts, fill=ink):
        d.polygon([(p[0] * s, p[1] * s) for p in pts], fill=fill)

    def R(box, fill=None, outline=ink, width=None, radius=10):
        b = [v * s for v in box]
        ww = stroke if width is None else max(2, int(width * s))
        d.rounded_rectangle(
            b, radius=int(radius * s),
            fill=fill, outline=None if fill else outline,
            width=0 if fill else ww)

    if kind == 'warn':
        L([(64, 34), (95, 90)], 8)
        L([(95, 90), (33, 90)], 8)
        L([(33, 90), (64, 34)], 8)
        for cx, cy in ((64, 36), (93, 88), (35, 88)):
            E((cx - 4, cy - 4, cx + 4, cy + 4), fill=ink, outline=None, width=1)
        E((60, 52, 68, 70), fill=ink, outline=None, width=1)
        E((60, 76, 68, 84), fill=ink, outline=None, width=1)
    elif kind == 'mute':
        P([(36, 52), (52, 52), (68, 38), (68, 90), (52, 76), (36, 76)])
        L([(86, 44), (44, 92)], 8)
    elif kind == 'ban':
        E((36, 36, 92, 92), fill=None, outline=ink, width=8)
        L([(48, 48), (80, 80)], 8)
    elif kind == 'clear':
        L([(80, 32), (46, 82)], 7)
        P([(38, 74), (58, 90), (50, 98), (28, 84)])
        for sx, sy, r in ((86, 42, 5), (94, 56, 4), (76, 60, 3)):
            L([(sx - r, sy), (sx + r, sy)], 2)
            L([(sx, sy - r), (sx, sy + r)], 2)
    elif kind == 'unban':
        E((46, 34, 82, 66), fill=None, outline=ink, width=6)
        L([(82, 50), (82, 40)], 6)
        R((40, 56, 88, 98), fill=ink, outline=None, radius=10)
        E((58, 70, 70, 82), fill=(20, 14, 30, 255), outline=None, width=1)
    elif kind == 'appeal':
        R((42, 30, 86, 98), fill=None, outline=ink, width=6, radius=10)
        L([(54, 50), (74, 50)], 4)
        L([(54, 62), (74, 62)], 4)
        L([(54, 74), (66, 74)], 4)
    elif kind == 'helper':
        pts = []
        for i in range(10):
            ang = math.pi / 2 + i * math.pi / 5
            r = 32 if i % 2 == 0 else 14
            pts.append((64 + r * math.cos(ang), 64 - r * math.sin(ang)))
        P(pts)
    elif kind == 'mod':
        body = [(64, 30), (94, 44), (94, 72), (64, 100), (34, 72), (34, 44)]
        P(body)
        E((56, 54, 72, 70), fill=(*accent, 255), outline=None, width=1)
    elif kind == 'heart':
        pts = []
        for t in range(0, 360, 3):
            rad = math.radians(t)
            x = 16 * math.sin(rad) ** 3
            y = (13 * math.cos(rad) - 5 * math.cos(2 * rad)
                 - 2 * math.cos(3 * rad) - math.cos(4 * rad))
            pts.append((64 + x * 2.15, 58 - y * 2.15))
        P(pts)
    else:
        f = _font(True, int(40 * s))
        label = kind.upper()[:3]
        bbox = d.textbbox((0, 0), label, font=f)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((size - tw) / 2, (size - th) / 2 - 2), label, font=f, fill=ink)

    bloom = layer.filter(ImageFilter.GaussianBlur(max(2, size // 40)))
    bloom = ImageEnhance.Brightness(bloom).enhance(1.6)
    out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    out = Image.alpha_composite(out, bloom)
    out = Image.alpha_composite(out, layer)
    return out


def _radial_disc(size: int, inset: int, inner, outer) -> Image.Image:
    """Радиальный градиент-диск (стекло)."""
    disc = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    cx = cy = (size - 1) / 2.0
    r_max = max(1.0, (size - 2 * inset) / 2.0)
    px = disc.load()
    ir, ig, ib, ia = inner
    or_, og, ob, oa = outer
    for y in range(inset, size - inset):
        for x in range(inset, size - inset):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx * dx + dy * dy) / r_max
            if dist > 1.0:
                continue
            bias = max(0.0, 1.0 - ((y - inset) / max(1, size - 2 * inset))) * 0.22
            t = min(1.0, dist)
            t = t * t * (3 - 2 * t)
            r = int(ir + (or_ - ir) * t + 40 * bias)
            g = int(ig + (og - ig) * t + 35 * bias)
            b = int(ib + (ob - ib) * t + 45 * bias)
            a = int(ia + (oa - ia) * t)
            px[x, y] = (min(255, r), min(255, g), min(255, b), min(255, a))
    return disc


def _load_curated_sticker(key: str, size: int) -> Optional[Image.Image]:
    """Готовый арт из assets/stickers/{key}.png (если есть)."""
    path = os.path.join(STICKERS, f'{key}.png')
    if not os.path.isfile(path):
        return None
    try:
        im = Image.open(path).convert('RGBA')
        if im.size != (size, size):
            im = im.resize((size, size), Image.Resampling.LANCZOS)
        return im
    except Exception:
        return None


def render_sticker(key: str, size: int = 128, *, procedural: bool = False) -> Image.Image:
    """Стикер-эмодзи: курируемый арт из assets, иначе procedural орб."""
    if not procedural:
        curated = _load_curated_sticker(key, size)
        if curated is not None:
            return curated

    spec = STICKER_SPECS.get(key, {'accent': (196, 150, 255), 'icon': key})
    accent = spec['accent']
    icon = spec['icon']

    scale = 4 if size >= 64 else 2
    S = size * scale
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    pad = int(6 * scale * (size / 128.0))
    inset = pad + int(4 * scale)

    aura = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ad = ImageDraw.Draw(aura)
    ad.ellipse((pad // 2, pad // 2, S - pad // 2 - 1, S - pad // 2 - 1),
               fill=(*accent, 95))
    aura = aura.filter(ImageFilter.GaussianBlur(max(6, S // 14)))
    img = Image.alpha_composite(img, aura)

    glass = _radial_disc(
        S, inset,
        inner=(42, 32, 64, 235),
        outer=(12, 8, 22, 252),
    )
    tint = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    td = ImageDraw.Draw(tint)
    td.ellipse((inset, inset, S - inset - 1, S - inset - 1),
               fill=(*accent, 42))
    glass = Image.alpha_composite(glass, tint)
    img = Image.alpha_composite(img, glass)

    rim = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rim)
    rim_w = max(2 * scale, int(3.2 * scale))
    rd.ellipse((inset, inset, S - inset - 1, S - inset - 1),
               outline=(*accent, 220), width=rim_w)
    hi = inset + int(5 * scale)
    if S - 2 * hi > 8 * scale:
        rd.ellipse((hi, hi, S - hi - 1, S - hi - 1),
                   outline=(255, 255, 255, 50), width=max(1, scale))
    rim_soft = rim.filter(ImageFilter.GaussianBlur(max(1, scale // 2)))
    img = Image.alpha_composite(img, rim_soft)
    img = Image.alpha_composite(img, rim)

    gloss = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gloss)
    gx0, gy0 = inset + int(10 * scale), inset + int(6 * scale)
    gx1, gy1 = S - inset - int(10 * scale), S // 2 + int(2 * scale)
    gd.ellipse((gx0, gy0, gx1, gy1), fill=(255, 255, 255, 48))
    bx = inset + int(22 * scale)
    by = inset + int(18 * scale)
    br = int(10 * scale)
    gd.ellipse((bx, by, bx + br, by + br // 2), fill=(255, 255, 255, 80))
    gloss = gloss.filter(ImageFilter.GaussianBlur(max(3, 2 * scale)))
    mask = Image.new('L', (S, S), 0)
    ImageDraw.Draw(mask).ellipse(
        (inset, inset, S - inset - 1, S - inset - 1), fill=255)
    ga = gloss.split()[-1]
    gloss.putalpha(Image.composite(ga, Image.new('L', (S, S), 0), mask))
    img = Image.alpha_composite(img, gloss)

    icon_img = _icon_layer(S, accent, icon)
    img = Image.alpha_composite(img, icon_img)

    if scale > 1:
        img = img.resize((size, size), Image.Resampling.LANCZOS)
    return img


def ensure_sticker_pack(out_dir: str = None, *, force: bool = False) -> list:
    """Записать stickers/*.png. Курируемый арт в assets/ не затирается без force."""
    out_dir = out_dir or STICKERS
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for key in STICKER_SPECS:
        path = os.path.join(out_dir, f'{key}.png')
        curated = out_dir == STICKERS and os.path.isfile(path) and not force
        if not curated:
            render_sticker(key, procedural=True).save(path, format='PNG')
        paths.append(path)
    return paths


def save_default_banners(out_dir: str = None) -> dict:
    """Сохранить готовые баннеры в assets/ (не блокируют перегенерацию)."""
    out_dir = out_dir or ASSETS
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    for kind in ('modpanel', 'appeals', 'staff', 'events'):
        path = os.path.join(out_dir, f'{kind}_banner.png')
        # без *_custom*: иначе старый запечённый текст перебьёт пресет
        img = _render_banner_fresh(kind)
        img.save(path, format='PNG', optimize=True)
        paths[kind] = path
    return paths


def _render_banner_fresh(kind: str) -> Image.Image:
    """Баннер с актуальным chrome (игнор *_custom* подмены)."""
    if kind == 'staff':
        staff_path = os.path.join(ASSETS, 'staff.jpg')
        if os.path.isfile(staff_path):
            try:
                # staff.jpg — фото без нашего chrome; для меню нужна надпись
                base = _cover(Image.open(staff_path).convert('RGBA'), W, H)
                dark = Image.new('RGBA', (W, H), (0, 0, 0, 140))
                base = Image.alpha_composite(base, dark)
                return _draw_banner_chrome(base, kind)
            except Exception:
                pass
    img = _premium_bg(kind)
    if img is None:
        img = Image.new('RGBA', (W, H), (0, 0, 0, 255))
        rnd = random.Random(hash(kind) & 0xFFFFFFFF)
        spark = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(spark)
        for _ in range(160):
            x, yy = rnd.randint(0, W - 1), rnd.randint(0, H - 1)
            a = rnd.randint(40, 180)
            r = rnd.choice((0, 0, 1, 1, 2))
            sd.ellipse((x - r, yy - r, x + r, yy + r), fill=(255, 255, 255, a))
        img = Image.alpha_composite(img, spark)
        try:
            atm = _load_atmosphere(kind).convert('RGBA')
            atm = ImageEnhance.Brightness(atm).enhance(0.40)
            dark = Image.new('RGBA', (W, H), (0, 0, 0, 150))
            atm = Image.alpha_composite(atm, dark)
            img = Image.blend(img, atm, 0.28)
        except Exception:
            pass
    return _draw_banner_chrome(img, kind)


def render_stickers_preview(out_path: str = None) -> str:
    """Коллаж стикеров для превью."""
    keys = [k for k in STICKER_SPECS if k != 'heart'] + ['heart']
    cell, pad, top = 148, 28, 58
    cols = len(keys)
    w = cols * cell + pad * 2
    h = cell + pad * 2 + top + 30
    canvas = Image.new('RGBA', (w, h), (14, 12, 20, 255))
    d = ImageDraw.Draw(canvas)
    f = _font(False, 17)
    f_sm = _font(False, 14)
    title = 'Стикеры для эмодзи сервера (залить в Discord)'
    d.text((pad, 18), title, font=f, fill=(235, 230, 245, 255))
    for i, key in enumerate(keys):
        st = render_sticker(key, 120)
        x = pad + i * cell + (cell - 120) // 2
        y = top
        canvas.alpha_composite(st, (x, y))
        bbox = d.textbbox((0, 0), key, font=f_sm)
        tw = bbox[2] - bbox[0]
        d.text((x + (120 - tw) / 2, y + 126), key, font=f_sm,
               fill=(175, 170, 190, 220))
    out_path = out_path or os.path.join(
        '/opt/cursor/artifacts', 'stickers-pack-preview.png')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    canvas.save(out_path, format='PNG')
    return out_path
