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

W, H = 1200, 420

# Пресеты: headline, pill, accent, bg candidates
PRESETS = {
    'modpanel': {
        'headline': 'МОДЕРАЦИЯ',
        'pill': 'Панель модерации · Hakumo',
        'accent': (196, 140, 255),
        'tint': (110, 55, 200),
        'bgs': ('help_bg.png', 'hakumo_log_bg.png', 'staff.jpg'),
    },
    'appeals': {
        'headline': 'АПЕЛЛЯЦИИ',
        'pill': 'Обжаловать наказание · Hakumo',
        'accent': (210, 160, 255),
        'tint': (125, 70, 210),
        'bgs': ('hakumo_log_bg.png', 'help_bg.png', 'staff.jpg'),
    },
    'staff': {
        'headline': 'НАБОРЫ',
        'pill': 'Стань частью команды HAKUMO',
        'accent': (196, 140, 255),
        'tint': (120, 60, 205),
        'bgs': ('staff.jpg', 'help_bg.png', 'hakumo_log_bg.png'),
    },
}

# Только *_custom* — ручная подмена без перерисовки кода
_CUSTOM_NAMES = {
    'modpanel': ('modpanel_banner_custom.png', 'modpanel_banner_custom.jpg',
                 'modpanel_custom.png', 'modpanel_custom.jpg'),
    'appeals': ('appeals_banner_custom.png', 'appeals_banner_custom.jpg',
                'appeals_custom.png', 'appeals_custom.jpg'),
    'staff': ('staff_hakumo_banner.png', 'staff_banner_custom.png'),
}

# Стикеры действий → акцент + тип иконки
STICKER_SPECS = {
    'warn':       {'accent': (251, 191, 36),  'icon': 'warn'},
    'mute':       {'accent': (96, 165, 250),  'icon': 'mute'},
    'ban':        {'accent': (248, 113, 113), 'icon': 'ban'},
    'clear':      {'accent': (52, 211, 153),  'icon': 'clear'},
    'unban':      {'accent': (74, 222, 128),  'icon': 'unban'},
    'appeal':     {'accent': (192, 132, 252), 'icon': 'appeal'},
    'helper':     {'accent': (196, 160, 255), 'icon': 'helper'},
    'moderator':  {'accent': (129, 140, 248), 'icon': 'mod'},
    'heart':      {'accent': (255, 230, 245), 'icon': 'heart'},
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


def _gradient_headline(img: Image.Image, text: str, y: int, accent) -> Image.Image:
    """Белый верх → фиолетовый низ букв (как НАБОРЫ)."""
    f_head = _font(True, 90)
    white_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    wd = ImageDraw.Draw(white_layer)
    _center_text(wd, text, f_head, y, (255, 255, 255, 255), W,
                 stroke=2, stroke_fill=(20, 10, 40, 160))
    purple_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(purple_layer)
    _center_text(pd, text, f_head, y, (*accent, 255), W,
                 stroke=2, stroke_fill=(20, 10, 40, 120))
    bbox = wd.textbbox((0, 0), text, font=f_head)
    th = bbox[3] - bbox[1]
    mask = Image.new('L', (W, H), 0)
    md = ImageDraw.Draw(mask)
    split = y + int(th * 0.46)
    md.rectangle((0, split, W, y + th + 8), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(1.4))
    mixed = Image.composite(purple_layer, white_layer, mask)
    # bloom под заголовком
    glow = mixed.filter(ImageFilter.GaussianBlur(14))
    glow = ImageEnhance.Brightness(glow).enhance(1.55)
    out = Image.alpha_composite(img, glow)
    out = Image.alpha_composite(out, mixed)
    return out


def render_menu_banner(kind: str = 'modpanel') -> Image.Image:
    """PNG-баннер для меню kind (modpanel/appeals/staff)."""
    custom = _find_custom(kind)
    if custom:
        try:
            return _cover(Image.open(custom).convert('RGBA'), W, H)
        except Exception:
            pass
    # staff.jpg уже готовый арт — не перекрываем заголовком
    if kind == 'staff':
        staff_path = os.path.join(ASSETS, 'staff.jpg')
        if os.path.isfile(staff_path):
            try:
                return _cover(Image.open(staff_path).convert('RGBA'), W, H)
            except Exception:
                pass

    preset = PRESETS.get(kind, PRESETS['modpanel'])
    img = _load_atmosphere(kind)
    d = ImageDraw.Draw(img)

    brand = _spaced('HAKUMO')
    f_brand = _font(False, 18)
    f_pill = _font(False, 20)
    accent = preset['accent']
    headline = preset['headline']
    pill = preset['pill']

    # тонкая золотая линия под брендом
    _center_text(d, brand, f_brand, 28, (230, 220, 245, 220), W)
    line_w = 120
    ly = 58
    d.line(((W - line_w) // 2, ly, (W + line_w) // 2, ly),
           fill=(*accent, 140), width=1)

    img = _gradient_headline(img, headline, 125, accent)
    d = ImageDraw.Draw(img)

    # pill CTA со свечением
    pb = d.textbbox((0, 0), pill, font=f_pill)
    pw, ph = pb[2] - pb[0] + 48, pb[3] - pb[1] + 22
    px0, py0 = (W - pw) // 2, 270
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.rounded_rectangle((px0 - 8, py0 - 8, px0 + pw + 8, py0 + ph + 8),
                         radius=ph // 2 + 8, fill=(*accent, 55))
    glow = glow.filter(ImageFilter.GaussianBlur(10))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((px0, py0, px0 + pw, py0 + ph),
                        radius=ph // 2,
                        fill=(14, 10, 24, 230),
                        outline=(*accent, 220), width=2)
    _center_text(d, pill, f_pill, py0 + 8, (248, 244, 255, 255), W)
    _center_text(d, brand, f_brand, H - 44, (195, 185, 215, 170), W)
    return img.convert('RGBA')


def menu_banner_bytes(kind: str = 'modpanel') -> bytes:
    buf = io.BytesIO()
    render_menu_banner(kind).save(buf, format='PNG', optimize=True)
    return buf.getvalue()


def menu_banner_file(kind: str = 'modpanel', filename: str = None):
    """(BytesIO, filename) для discord.File."""
    raw = menu_banner_bytes(kind)
    bio = io.BytesIO(raw)
    bio.seek(0)
    name = filename or f'hakumo_{kind}_banner.png'
    return bio, name


def select_label(text: str) -> str:
    """Подпись пункта селекта «› Moderator»."""
    t = str(text or '').strip()
    if t.startswith('›') or t.startswith('🤍'):
        return t[:100]
    return f'› {t}'[:100]


def select_emoji():
    """Стикер селекта: 🤍 или свой эмодзи сервера из MENU_SELECT_EMOJI.

    Примеры:
      MENU_SELECT_EMOJI=🤍
      MENU_SELECT_EMOJI=<:hakumo:1234567890123456789>
    """
    raw = (os.environ.get('MENU_SELECT_EMOJI') or '🤍').strip() or '🤍'
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


# ─── иконки стикеров ───────────────────────────────────────────

def _icon_layer(size: int, accent, kind: str) -> Image.Image:
    """Белая пиктограмма по центру круга."""
    layer = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx = cy = size / 2
    ink = (255, 255, 255, 255)
    soft = (*accent, 220)
    s = size / 128.0  # scale from 128 base

    def L(pts, w=5):
        d.line([(p[0] * s, p[1] * s) for p in pts],
               fill=ink, width=max(2, int(w * s)), joint='curve')

    def E(box, fill=None, outline=ink, width=4):
        b = [v * s for v in box]
        d.ellipse(b, fill=fill, outline=outline,
                  width=max(2, int(width * s)))

    def P(pts, fill=ink, outline=None, width=2):
        d.polygon([(p[0] * s, p[1] * s) for p in pts],
                  fill=fill, outline=outline)

    def R(box, fill=None, outline=ink, width=3, radius=6):
        b = [v * s for v in box]
        d.rounded_rectangle(b, radius=int(radius * s), fill=fill,
                            outline=outline, width=max(1, int(width * s)))

    if kind == 'warn':
        L([(64, 30), (96, 90)], 5)
        L([(96, 90), (32, 90)], 5)
        L([(32, 90), (64, 30)], 5)
        E((60, 48, 68, 68), fill=ink, outline=None, width=1)
        E((60, 74, 68, 82), fill=ink, outline=None, width=1)
    elif kind == 'mute':
        # speaker body
        P([(34, 50), (50, 50), (66, 36), (66, 92), (50, 78), (34, 78)],
          fill=ink)
        # slash
        L([(90, 38), (40, 94)], 6)
    elif kind == 'ban':
        E((34, 34, 94, 94), fill=None, outline=ink, width=6)
        L([(46, 46), (82, 82)], 6)
    elif kind == 'clear':
        # broom handle
        L([(78, 30), (48, 78)], 5)
        # bristles
        P([(40, 72), (58, 86), (52, 96), (30, 84)], fill=ink)
        # sparkles
        for sx, sy in ((84, 44), (92, 58), (74, 62)):
            L([(sx - 4, sy), (sx + 4, sy)], 2)
            L([(sx, sy - 4), (sx, sy + 4)], 2)
    elif kind == 'unban':
        # unlocked padlock
        E((44, 36, 84, 70), fill=None, outline=ink, width=5)
        L([(84, 52), (84, 42)], 5)
        R((40, 58, 88, 98), fill=ink, outline=None, radius=8)
        E((58, 70, 70, 82), fill=(18, 14, 28, 255), outline=None, width=1)
    elif kind == 'appeal':
        R((40, 30, 88, 98), fill=None, outline=ink, width=4, radius=6)
        L([(52, 48), (76, 48)], 3)
        L([(52, 60), (76, 60)], 3)
        L([(52, 72), (68, 72)], 3)
        L([(72, 30), (88, 46), (72, 46), (72, 30)], 3)
    elif kind == 'helper':
        pts = []
        for i in range(10):
            ang = math.pi / 2 + i * math.pi / 5
            r = 34 if i % 2 == 0 else 15
            pts.append((64 + r * math.cos(ang), 64 - r * math.sin(ang)))
        P(pts, fill=ink)
    elif kind == 'mod':
        L([(64, 30), (94, 43), (94, 70), (64, 96), (34, 70), (34, 43), (64, 30)], 5)
        E((56, 54, 72, 70), fill=soft, outline=None, width=1)
    elif kind == 'heart':
        pts = []
        for t in range(0, 360, 4):
            rad = math.radians(t)
            x = 16 * math.sin(rad) ** 3
            y = (13 * math.cos(rad) - 5 * math.cos(2 * rad)
                 - 2 * math.cos(3 * rad) - math.cos(4 * rad))
            pts.append((64 + x * 2.1, 58 - y * 2.1))
        P(pts, fill=ink)
    else:
        f = _font(True, int(36 * s))
        label = kind.upper()[:3]
        bbox = d.textbbox((0, 0), label, font=f)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((size - tw) / 2, (size - th) / 2 - 2), label, font=f, fill=ink)

    return layer


def render_sticker(key: str, size: int = 128) -> Image.Image:
    """Стеклянный круглый стикер-иконка для загрузки как эмодзи сервера."""
    spec = STICKER_SPECS.get(key, {'accent': (168, 85, 247), 'icon': key})
    accent = spec['accent']
    icon = spec['icon']

    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    pad = 3

    # outer soft glow
    glow = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((pad, pad, size - pad - 1, size - pad - 1), fill=(*accent, 100))
    glow = glow.filter(ImageFilter.GaussianBlur(max(4, size // 18)))
    img = Image.alpha_composite(img, glow)

    d = ImageDraw.Draw(img)
    # glass disc
    inset = pad + max(2, size // 20)
    rim_w = max(2, size // 28)
    d.ellipse((inset, inset, size - inset - 1, size - inset - 1),
              fill=(16, 12, 26, 245))
    # accent rim
    d.ellipse((inset, inset, size - inset - 1, size - inset - 1),
              outline=(*accent, 255), width=rim_w)
    # inner highlight ring (only if enough room)
    hi = inset + max(4, size // 16)
    if size - 2 * hi > 4:
        d.ellipse((hi, hi, size - hi - 1, size - hi - 1),
                  outline=(255, 255, 255, 35),
                  width=max(1, size // 64))

    # top gloss
    if size >= 48:
        gloss = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        gld = ImageDraw.Draw(gloss)
        gld.ellipse((inset + 8, inset + 6, size - inset - 10, size // 2 + 4),
                    fill=(255, 255, 255, 28))
        gloss = gloss.filter(ImageFilter.GaussianBlur(4))
        mask = Image.new('L', (size, size), 0)
        ImageDraw.Draw(mask).ellipse(
            (inset, inset, size - inset - 1, size - inset - 1), fill=255)
        gloss.putalpha(Image.composite(
            gloss.split()[-1], Image.new('L', (size, size), 0), mask))
        img = Image.alpha_composite(img, gloss)

    # icon
    icon_img = _icon_layer(size, accent, icon)
    img = Image.alpha_composite(img, icon_img)
    return img


def ensure_sticker_pack(out_dir: str = None) -> list:
    """Записать assets/stickers/*.png — вернуть пути."""
    out_dir = out_dir or STICKERS
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for key in STICKER_SPECS:
        path = os.path.join(out_dir, f'{key}.png')
        render_sticker(key).save(path, format='PNG')
        paths.append(path)
    return paths


def save_default_banners(out_dir: str = None) -> dict:
    """Сохранить готовые баннеры в assets/ (не блокируют перегенерацию)."""
    out_dir = out_dir or ASSETS
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    for kind in ('modpanel', 'appeals'):
        path = os.path.join(out_dir, f'{kind}_banner.png')
        render_menu_banner(kind).save(path, format='PNG', optimize=True)
        paths[kind] = path
    return paths


def render_stickers_preview(out_path: str = None) -> str:
    """Коллаж стикеров для превью."""
    keys = [k for k in STICKER_SPECS if k != 'heart'] + ['heart']
    cell, pad, top = 140, 24, 56
    cols = len(keys)
    w = cols * cell + pad * 2
    h = cell + pad * 2 + top + 28
    canvas = Image.new('RGBA', (w, h), (18, 16, 24, 255))
    d = ImageDraw.Draw(canvas)
    f = _font(False, 16)
    f_sm = _font(False, 14)
    title = 'Стикеры для эмодзи сервера (залить в Discord)'
    d.text((pad, 18), title, font=f, fill=(230, 225, 240, 255))
    for i, key in enumerate(keys):
        st = render_sticker(key, 112)
        x = pad + i * cell + (cell - 112) // 2
        y = top
        canvas.alpha_composite(st, (x, y))
        bbox = d.textbbox((0, 0), key, font=f_sm)
        tw = bbox[2] - bbox[0]
        d.text((x + (112 - tw) / 2, y + 118), key, font=f_sm,
               fill=(180, 175, 195, 220))
    out_path = out_path or os.path.join(
        '/opt/cursor/artifacts', 'stickers-pack-preview.png')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    canvas.save(out_path, format='PNG')
    return out_path
