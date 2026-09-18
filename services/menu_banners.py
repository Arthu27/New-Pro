# -*- coding: utf-8 -*-
"""Фирменные баннеры и стикеры меню Discord (стиль HAKUMO «НАБОРЫ»).

Баннеры: реальный фон из assets (золотой дым/звёзды) + фиолетовый тон
как у наборов, крупный градиентный заголовок, pill-CTA, H A K U M O.

Стикер в селекте по умолчанию — 🤍 (как в референсе). Можно заменить:
  • env MENU_SELECT_EMOJI=🤍
  • или свой эмодзи сервера: MENU_SELECT_EMOJI='<:hakumo:1234567890>'
Свои баннеры: assets/modpanel_banner.png, assets/appeals_banner.jpg
Стикеры-иконки (залить как эмодзи сервера): assets/stickers/*.png
"""
from __future__ import annotations

import io
import math
import os
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
        'accent': (168, 85, 247),
        'tint': (120, 60, 220),
        'bgs': ('help_bg.png', 'hakumo_log_bg.png', 'staff.jpg'),
    },
    'appeals': {
        'headline': 'АПЕЛЛЯЦИИ',
        'pill': 'Обжаловать наказание · Hakumo',
        'accent': (192, 132, 252),
        'tint': (140, 80, 230),
        'bgs': ('hakumo_log_bg.png', 'help_bg.png', 'staff.jpg'),
    },
    'staff': {
        'headline': 'НАБОРЫ',
        'pill': 'Стань частью команды HAKUMO',
        'accent': (168, 85, 247),
        'tint': (130, 70, 220),
        'bgs': ('staff.jpg', 'help_bg.png', 'hakumo_log_bg.png'),
    },
}

_CUSTOM_NAMES = {
    'modpanel': ('modpanel_banner.png', 'modpanel_banner.jpg',
                 'modpanel.jpg', 'modpanel.png'),
    'appeals': ('appeals_banner.png', 'appeals_banner.jpg',
                'appeals.jpg', 'appeals.png', 'appeal_banner.png'),
    'staff': ('staff_hakumo_banner.png', 'staff_banner_custom.png'),
}

# Стикеры действий → подпись на иконке
STICKER_SPECS = {
    'warn': ('ВАРН', (251, 191, 36)),
    'mute': ('МУТ', (96, 165, 250)),
    'ban': ('БАН', (248, 113, 113)),
    'clear': ('ЧИСТ', (52, 211, 153)),
    'unban': ('РАЗБ', (74, 222, 128)),
    'appeal': ('АПЕЛ', (192, 132, 252)),
    'helper': ('HELP', (167, 139, 250)),
    'moderator': ('MOD', (129, 140, 248)),
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
    """Премиум-фон: реальный asset + фиолетовый тон как у «НАБОРЫ»."""
    preset = PRESETS.get(kind, PRESETS['modpanel'])
    # свой баннер целиком
    custom = _find_custom(kind)
    if custom:
        try:
            return _cover(Image.open(custom).convert('RGBA'), W, H)
        except Exception:
            pass
    # для staff — если есть staff.jpg без текста-оверлея желанен свой;
    # всё равно наложим заголовок поверх атмосферы
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

    # затемнить центр под текст
    dark = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dark)
    for y in range(H):
        # vignette сверху/снизу и по центру чуть светлее краёв дыма
        edge_y = min(y, H - 1 - y) / (H * 0.45)
        a = int(90 + 70 * max(0.0, 1.0 - edge_y))
        dd.line([(0, y), (W, y)], fill=(8, 6, 14, a))
    base = Image.alpha_composite(base, dark)

    # фиолетовый тон (как у наборов), не затирает золотой дым полностью
    tint = Image.new('RGBA', (W, H), (*preset['tint'], 0))
    tp = tint.load()
    tr, tg, tb = preset['tint']
    for x in range(0, W, 2):
        for y in range(0, H, 2):
            edge = min(x, W - 1 - x) / (W * 0.38)
            edge = max(0.0, 1.0 - edge)
            a = int(95 * edge)
            if a < 4:
                continue
            for dx in (0, 1):
                for dy in (0, 1):
                    xx, yy = x + dx, y + dy
                    if xx < W and yy < H:
                        tp[xx, yy] = (tr, tg, tb, a)
    tint = tint.filter(ImageFilter.GaussianBlur(14))
    base = Image.alpha_composite(base, tint)

    # лёгкий контраст
    base = ImageEnhance.Contrast(base).enhance(1.08)
    base = ImageEnhance.Color(base).enhance(1.12)
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
    f_head = _font(True, 86)
    # белый слой
    white_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    wd = ImageDraw.Draw(white_layer)
    _center_text(wd, text, f_head, y, (255, 255, 255, 255), W,
                 stroke=2, stroke_fill=(20, 10, 40, 160))
    # фиолетовый слой
    purple_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(purple_layer)
    _center_text(pd, text, f_head, y, (*accent, 255), W,
                 stroke=2, stroke_fill=(20, 10, 40, 120))
    # маска нижней половины букв
    bbox = wd.textbbox((0, 0), text, font=f_head)
    th = bbox[3] - bbox[1]
    mask = Image.new('L', (W, H), 0)
    md = ImageDraw.Draw(mask)
    split = y + int(th * 0.48)
    md.rectangle((0, split, W, y + th + 8), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(1.2))
    mixed = Image.composite(purple_layer, white_layer, mask)
    # мягкое свечение под текстом
    glow = mixed.filter(ImageFilter.GaussianBlur(10))
    glow = ImageEnhance.Brightness(glow).enhance(1.4)
    out = Image.alpha_composite(img, glow)
    out = Image.alpha_composite(out, mixed)
    return out


def render_menu_banner(kind: str = 'modpanel') -> Image.Image:
    """PNG-баннер для меню kind (modpanel/appeals/staff)."""
    # полный кастомный файл без оверлея текста — если имя *banner*
    custom = _find_custom(kind)
    if custom and 'banner' in os.path.basename(custom).lower():
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
    f_brand = _font(False, 20)
    f_pill = _font(False, 20)
    accent = preset['accent']
    headline = preset['headline']
    pill = preset['pill']

    _center_text(d, brand, f_brand, 32, (220, 210, 240, 210), W)
    img = _gradient_headline(img, headline, 130, accent)
    d = ImageDraw.Draw(img)

    # pill CTA со свечением
    pb = d.textbbox((0, 0), pill, font=f_pill)
    pw, ph = pb[2] - pb[0] + 44, pb[3] - pb[1] + 20
    px0, py0 = (W - pw) // 2, 268
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.rounded_rectangle((px0 - 6, py0 - 6, px0 + pw + 6, py0 + ph + 6),
                         radius=ph // 2 + 6, fill=(*accent, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(8))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((px0, py0, px0 + pw, py0 + ph),
                        radius=ph // 2,
                        fill=(16, 12, 28, 235),
                        outline=(*accent, 230), width=2)
    _center_text(d, pill, f_pill, py0 + 7, (245, 240, 255, 255), W)
    _center_text(d, brand, f_brand, H - 48, (190, 180, 210, 180), W)
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


def render_sticker(key: str, size: int = 128) -> Image.Image:
    """Круглый стикер-иконка для загрузки как эмодзи сервера."""
    label, accent = STICKER_SPECS.get(key, (key.upper()[:4], (168, 85, 247)))
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = 4
    # glow
    glow = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((pad, pad, size - pad - 1, size - pad - 1), fill=(*accent, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(6))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)
    d.ellipse((pad + 4, pad + 4, size - pad - 5, size - pad - 5),
              fill=(18, 14, 28, 255), outline=(*accent, 255), width=4)
    # внутреннее кольцо
    d.ellipse((pad + 14, pad + 14, size - pad - 15, size - pad - 15),
              outline=(255, 255, 255, 40), width=2)
    f = _font(True, 28 if len(label) <= 4 else 22)
    bbox = d.textbbox((0, 0), label, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) / 2, (size - th) / 2 - 2), label, font=f,
           fill=(255, 255, 255, 255))
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
    """Сохранить готовые баннеры в assets/ для ручной подмены."""
    out_dir = out_dir or ASSETS
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    for kind in ('modpanel', 'appeals'):
        path = os.path.join(out_dir, f'{kind}_banner.png')
        render_menu_banner(kind).save(path, format='PNG', optimize=True)
        paths[kind] = path
    return paths
