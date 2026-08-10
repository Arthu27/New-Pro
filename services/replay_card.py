"""
Aether — «Реплеер инцидентов»: визуальная лента событий сервера (Pillow).

Вертикальный таймлайн: время → золотая иконка категории → что произошло → детали.
Рисуется ботом на фирменном фоне Midnight Navy с золотой звёздной пылью.
"""
import io
import os
import random

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    REPLAY_CARD_OK = True
except Exception:
    Image = ImageDraw = ImageFilter = ImageFont = None
    REPLAY_CARD_OK = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_B = os.path.join(ROOT, 'assets', 'fonts', 'Bold.ttf')
FONT_R = os.path.join(ROOT, 'assets', 'fonts', 'Regular.ttf')
ICONS_DIR = os.path.join(ROOT, 'assets', 'icons', 'logcards')

C_BG_TOP       = (10, 16, 30)
C_BG_BOT       = (16, 26, 48)
GOLD           = (212, 175, 55, 255)
GOLD_BRIGHT    = (245, 215, 110, 255)
GOLD_SOFT      = (212, 175, 55, 90)
TEXT           = (240, 244, 252, 255)
MUTED          = (143, 163, 200, 255)
DIM            = (124, 141, 176, 255)
SPINE          = (212, 175, 55, 180)

# Цвет точки/свечения категории
CAT_COLORS = {
    'mod': (231, 76, 60), 'member': (46, 213, 115), 'message': (0, 195, 255),
    'voice': (26, 188, 156), 'channel': (243, 156, 18), 'role': (165, 94, 234),
    'invite': (108, 92, 231), 'guild': (212, 175, 55), 'ticket': (84, 160, 255),
    'ai': (233, 30, 99), 'welcome': (32, 227, 178),
}
DEFAULT_COLOR = (212, 175, 55)

_fonts = {}


def _font(size, bold=False):
    key = (size, bool(bold))
    f = _fonts.get(key)
    if f is None:
        try:
            f = ImageFont.truetype(FONT_B if bold else FONT_R, size)
        except Exception:
            f = ImageFont.load_default()
        _fonts[key] = f
    return f


def _ellipsize(draw, text, font, max_w):
    text = str(text or '')
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + '…', font=font) > max_w:
        text = text[:-1]
    return text + '…'


def _icon(cat, size=48):
    if not REPLAY_CARD_OK:
        return None
    p = os.path.join(ICONS_DIR, f'log_{cat}_256.png')
    if not os.path.exists(p):
        p = os.path.join(ICONS_DIR, 'log_guild_256.png')
    if not os.path.exists(p):
        return None
    key = ('ic', cat, size)
    f = _fonts.get(key)
    if f is None:
        try:
            im = Image.open(p).convert('RGBA').resize((size, size), Image.Resampling.LANCZOS)
            mask = Image.new('L', (size, size), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius=12, fill=255)
            out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            out.paste(im, (0, 0), mask)
            f = out
        except Exception:
            f = None
        _fonts[key] = f
    return f


def _draw_stardust(img, W, H):
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    rnd = random.Random(42)
    for _ in range(50):
        sx = rnd.randint(18, W - 18)
        sy = rnd.randint(18, H - 18)
        size = rnd.choice([1, 1, 2, 2, 3])
        alpha = rnd.randint(40, 160)
        od.ellipse((sx, sy, sx + size, sy + size), fill=(212, 175, 55, alpha))
    return Image.alpha_composite(img, overlay)


def render_replay_card(title, subtitle, events, now_str=''):
    """events: [{'time':'12:40','cat':'role','label':'Изменение ролей','detail':'...'}]
    Возвращает PNG-байты или None."""
    if not REPLAY_CARD_OK:
        return None
    try:
        W = 1440
        PAD = 56
        SPINE_X = 280
        ROW_H = 88
        MAX_ROWS = 14
        overflow = 0
        if len(events) > MAX_ROWS:
            overflow = len(events) - MAX_ROWS
            events = events[:MAX_ROWS]
        header_h = 210
        footer_h = 92
        body_h = max(1, len(events)) * ROW_H + (56 if overflow else 0)
        H = header_h + body_h + footer_h

        grad = Image.new('RGB', (1, H))
        for y in range(H):
            k = y / max(1, H - 1)
            grad.putpixel((0, y), tuple(int(C_BG_TOP[i] + (C_BG_BOT[i] - C_BG_TOP[i]) * k) for i in range(3)))
        img = grad.resize((W, H)).convert('RGBA')

        glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse((-240, -280, 620, 460), fill=(212, 175, 55, 30))
        img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(90)))
        img = _draw_stardust(img, W, H)
        d = ImageDraw.Draw(img)

        # Двойная золотая рамка
        d.rectangle((10, 10, W - 10, H - 10), outline=GOLD_SOFT, width=2)
        d.rectangle((16, 16, W - 16, H - 16), outline=(212, 175, 55, 40), width=1)

        # Шапка
        badge_txt = "✦ AETHER · РЕПЛЕЕР СОБЫТИЙ"
        bw = d.textlength(badge_txt, font=_font(20, True)) + 24
        d.rounded_rectangle((PAD, 48, PAD + bw, 48 + 34), radius=10,
                            fill=(20, 28, 48, 220), outline=(212, 175, 55, 120), width=1)
        d.text((PAD + 12, 54), badge_txt, font=_font(20, True), fill=GOLD_BRIGHT)

        d.text((PAD, 96), _ellipsize(d, str(title), _font(48, True), W - PAD * 2 - 260),
               font=_font(48, True), fill=TEXT)
        if subtitle:
            d.text((PAD, 160), str(subtitle), font=_font(24), fill=DIM)
        if now_str:
            w = d.textlength(now_str, font=_font(24, True))
            d.rounded_rectangle((W - PAD - w - 24, 48, W - PAD, 48 + 34), radius=10,
                                fill=(20, 28, 48, 220), outline=(212, 175, 55, 100), width=1)
            d.text((W - PAD - w - 12, 54), now_str, font=_font(24, True), fill=GOLD_BRIGHT)

        d.line([(PAD, header_h - 14), (W - PAD, header_h - 14)], fill=GOLD_SOFT, width=1)
        d.line([(PAD, header_h - 14), (PAD + 220, header_h - 14)], fill=GOLD_BRIGHT, width=2)

        # Хребет таймлайна
        body_top = header_h + 8
        y = body_top
        n = len(events)
        if n:
            first_dot = y + ROW_H // 2
            last_dot = y + (n - 1) * ROW_H + ROW_H // 2
            d.rectangle((SPINE_X - 2, first_dot, SPINE_X + 2, last_dot), fill=SPINE)
            d.ellipse((SPINE_X - 6, first_dot - 18, SPINE_X + 6, first_dot - 6), outline=GOLD_BRIGHT, width=2)
            d.ellipse((SPINE_X - 6, last_dot + 6, SPINE_X + 6, last_dot + 18), outline=GOLD_BRIGHT, width=2)

        for i, ev in enumerate(events):
            cy = y + i * ROW_H
            mid = cy + ROW_H // 2
            col = CAT_COLORS.get(ev.get('cat', ''), DEFAULT_COLOR)

            # Время слева
            t = str(ev.get('time', ''))
            tw = d.textlength(t, font=_font(28, True))
            d.text((SPINE_X - 40 - tw, mid - 18), t, font=_font(28, True), fill=GOLD_BRIGHT)

            # Точка со свечением
            d.ellipse((SPINE_X - 14, mid - 14, SPINE_X + 14, mid + 14), fill=col + (60,))
            d.ellipse((SPINE_X - 8, mid - 8, SPINE_X + 8, mid + 8), fill=col + (255,))

            # Иконка категории
            ic = _icon(ev.get('cat', ''))
            ix = SPINE_X + 34
            if ic is not None:
                img.paste(ic, (ix, mid - 24), ic)
            d.rounded_rectangle((ix, mid - 24, ix + 48, mid + 24), radius=12,
                                outline=(212, 175, 55, 180), width=2)

            # Карточка события
            tx = ix + 66
            d.text((tx, mid - 28), _ellipsize(d, str(ev.get('label', '')), _font(28, True), W - tx - PAD),
                   font=_font(28, True), fill=TEXT)
            det = str(ev.get('detail', '') or '')
            if det:
                d.text((tx, mid + 8), _ellipsize(d, det, _font(22), W - tx - PAD),
                       font=_font(22), fill=DIM)

        if not events:
            d.text((SPINE_X + 34, body_top + 10), 'Событий за окно не найдено',
                   font=_font(30), fill=DIM)

        if overflow:
            oy = y + n * ROW_H + 8
            d.text((SPINE_X + 34, oy), f'+ ещё {overflow} событий — смотрите лог-каналы',
                   font=_font(24, True), fill=GOLD_BRIGHT)

        # Футер
        fy = H - footer_h + 22
        d.line([(PAD, fy), (W - PAD, fy)], fill=GOLD_SOFT, width=1)
        d.text((PAD, fy + 16), 'AETHER REPLAY · ТАЙМЛАЙН СОБЫТИЙ', font=_font(22), fill=DIM)
        brand = '✦ AETHER'
        d.text((W - PAD - d.textlength(brand, font=_font(24, True)), fy + 14),
               brand, font=_font(24, True), fill=GOLD_BRIGHT)

        buf = io.BytesIO()
        img.convert('RGB').save(buf, 'PNG', optimize=True)
        return buf.getvalue()
    except Exception:
        return None
