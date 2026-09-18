# -*- coding: utf-8 -*-
"""Фирменные баннеры меню Discord (стиль HAKUMO «НАБОРЫ»).

Тёмный фон, фиолетовый дым по краям, крупный заголовок, pill-CTA,
буквы H A K U M O сверху/снизу. Используется в /modpanel и меню апелляций.

Можно подложить свой файл:
  assets/modpanel_banner.png | .jpg
  assets/appeals_banner.png  | .jpg
Иначе рисуем PIL-баннер автоматически.
"""
from __future__ import annotations

import io
import math
import os
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, 'assets')
FONTS = os.path.join(ASSETS, 'fonts')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

W, H = 960, 360

# Пресеты меню: (headline, pill text, accent rgb)
PRESETS = {
    'modpanel': (
        'МОДЕРАЦИЯ',
        'Панель модерации · Hakumo',
        (139, 92, 246),
    ),
    'appeals': (
        'АПЕЛЛЯЦИИ',
        'Обжаловать наказание · Hakumo',
        (167, 139, 250),
    ),
    'staff': (
        'НАБОРЫ',
        'Стань частью команды HAKUMO',
        (168, 85, 247),
    ),
}

_CUSTOM_NAMES = {
    'modpanel': ('modpanel_banner.png', 'modpanel_banner.jpg',
                 'modpanel.jpg', 'modpanel.png'),
    'appeals': ('appeals_banner.png', 'appeals_banner.jpg',
                'appeals.jpg', 'appeals.png', 'appeal_banner.png'),
    'staff': ('staff.jpg', 'staff_hakumo_banner.png', 'staff_banner_custom.png'),
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


def _smoke_layer(w, h, accent=(139, 92, 246)) -> Image.Image:
    """Фиолетовый «дым» по бокам — как на баннере НАБОРЫ."""
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    px = layer.load()
    ax, ay, az = accent
    for x in range(w):
        for y in range(h):
            # сила дыма у левого и правого края
            edge = min(x, w - 1 - x) / (w * 0.42)
            edge = max(0.0, 1.0 - edge)
            # вертикальные волны
            wave = 0.55 + 0.45 * math.sin(y / 28.0 + x / 90.0)
            wave2 = 0.55 + 0.45 * math.sin(y / 17.0 - x / 60.0)
            a = int(210 * edge * wave * wave2)
            if a < 8:
                continue
            # чуть светлее к центру пятна
            mid = abs(y - h / 2) / (h / 2)
            bright = 1.0 - 0.35 * mid
            px[x, y] = (
                min(255, int(ax * bright)),
                min(255, int(ay * bright)),
                min(255, int(az * bright)),
                min(255, a),
            )
    return layer.filter(ImageFilter.GaussianBlur(radius=18))


def _spaced(text: str) -> str:
    return '  '.join(list(text.replace(' ', '')))


def _center_text(draw, text, font, y, fill, w):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((w - tw) / 2, y), text, font=font, fill=fill)


def render_menu_banner(kind: str = 'modpanel') -> Image.Image:
    """PNG-баннер 960×360 для меню kind (modpanel/appeals/staff)."""
    custom = _find_custom(kind)
    if custom:
        try:
            return _cover(Image.open(custom).convert('RGBA'), W, H)
        except Exception:
            pass

    headline, pill, accent = PRESETS.get(kind, PRESETS['modpanel'])
    # база
    img = Image.new('RGBA', (W, H), (12, 10, 18, 255))
    d = ImageDraw.Draw(img)
    # лёгкий градиент вниз
    for y in range(H):
        t = y / H
        c = int(12 + 8 * t)
        d.line([(0, y), (W, y)], fill=(c, c + 1, c + 6, 255))

    smoke = _smoke_layer(W, H, accent)
    img = Image.alpha_composite(img, smoke)
    d = ImageDraw.Draw(img)

    brand = _spaced('HAKUMO')
    f_brand = _font(False, 18)
    f_head = _font(True, 72)
    f_pill = _font(False, 18)

    _center_text(d, brand, f_brand, 28, (200, 190, 220, 200), W)
    # заголовок с лёгким фиолетовым низом (два слоя)
    _center_text(d, headline, f_head, 118, (255, 255, 255, 255), W)
    # полупрозрачный «отрезок» снизу букв
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    _center_text(od, headline, f_head, 118, (*accent, 160), W)
    # обрежем верх заголовка — оставим только нижнюю треть букв
    mask = Image.new('L', (W, H), 0)
    md = ImageDraw.Draw(mask)
    md.rectangle((0, 118 + 48, W, 118 + 90), fill=255)
    tinted = Image.composite(overlay, Image.new('RGBA', (W, H), (0, 0, 0, 0)), mask)
    img = Image.alpha_composite(img, tinted)
    d = ImageDraw.Draw(img)

    # pill CTA
    pb = d.textbbox((0, 0), pill, font=f_pill)
    pw, ph = pb[2] - pb[0] + 36, pb[3] - pb[1] + 18
    px0, py0 = (W - pw) // 2, 230
    d.rounded_rectangle((px0, py0, px0 + pw, py0 + ph),
                        radius=ph // 2,
                        fill=(22, 18, 32, 230),
                        outline=(*accent, 200), width=2)
    _center_text(d, pill, f_pill, py0 + 6, (235, 230, 245, 255), W)

    _center_text(d, brand, f_brand, H - 42, (180, 170, 200, 170), W)
    return img.convert('RGBA')


def menu_banner_bytes(kind: str = 'modpanel') -> bytes:
    buf = io.BytesIO()
    render_menu_banner(kind).save(buf, format='PNG', optimize=True)
    return buf.getvalue()


def menu_banner_file(kind: str = 'modpanel', filename: str = None):
    """(discord.File-ready BytesIO, filename) — BytesIO на позиции 0."""
    raw = menu_banner_bytes(kind)
    bio = io.BytesIO(raw)
    bio.seek(0)
    name = filename or f'hakumo_{kind}_banner.png'
    return bio, name


def select_label(text: str) -> str:
    """Подпись пункта селекта в стиле «› Moderator»."""
    t = str(text or '').strip()
    if t.startswith('›') or t.startswith('🤍'):
        return t[:100]
    return f'› {t}'[:100]


def select_emoji():
    """Единый эмодзи пунктов меню (как на референсе наборов)."""
    return '🤍'
