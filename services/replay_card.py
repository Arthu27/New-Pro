"""
Aether — «Реплеер инцидентов»: визуальная лента событий сервера (Pillow).

Вертикальный таймлайн: время → иконка категории → что произошло → детали.
Рисуется ботом, без внешних сервисов.

    from services.replay_card import render_replay_card, REPLAY_CARD_OK
    png = render_replay_card('События: Имя', 'за 30 минут', events_list)
"""
import io
import os

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

GOLD = (212, 175, 55, 255)
GOLD_SOFT = (212, 175, 55, 90)
TEXT = (240, 244, 252, 255)
MUTED = (143, 163, 200, 255)
DIM = (124, 141, 176, 255)
SPINE = (84, 100, 138, 255)

# Цвет точки/свечения категории (как у логов)
CAT_COLORS = {
    'mod': (231, 76, 60), 'member': (200, 146, 42), 'message': (52, 152, 219),
    'voice': (26, 188, 156), 'channel': (230, 126, 34), 'role': (155, 89, 182),
    'invite': (22, 160, 133), 'guild': (200, 146, 42), 'ticket': (243, 156, 18),
    'ai': (233, 30, 99), 'welcome': (46, 204, 113),
}
DEFAULT_COLOR = (200, 146, 42)

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
            im = Image.open(p).convert('RGB').resize((size, size), Image.LANCZOS)
            mask = Image.new('L', (size, size), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius=12, fill=255)
            out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            out.paste(im, (0, 0), mask)
            f = out
        except Exception:
            f = None
        _fonts[key] = f
    return f


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

        top_c, bot_c = (13, 20, 32), (24, 34, 54)
        grad = Image.new('RGB', (1, H))
        for y in range(H):
            k = y / max(1, H - 1)
            grad.putpixel((0, y), tuple(int(top_c[i] + (bot_c[i] - top_c[i]) * k) for i in range(3)))
        img = grad.resize((W, H)).convert('RGBA')
        glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse((-240, -280, 620, 460), fill=(212, 175, 55, 26))
        img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(100)))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((8, 8, W - 8, H - 8), radius=26, outline=GOLD_SOFT, width=3)

        # Шапка
        d.text((PAD, 58), 'РЕПЛЕЕР СОБЫТИЙ', font=_font(26, True), fill=GOLD)
        d.text((PAD, 100), _ellipsize(d, str(title), _font(52, True), W - PAD * 2 - 260),
               font=_font(52, True), fill=TEXT)
        if subtitle:
            d.text((PAD, 170), str(subtitle), font=_font(26), fill=DIM)
        if now_str:
            w = d.textlength(now_str, font=_font(26))
            d.text((W - PAD - w, 62), now_str, font=_font(26), fill=DIM)
        d.rectangle((PAD, header_h - 14, W - PAD, header_h - 12), fill=GOLD_SOFT)

        # Хребет таймлайна
        body_top = header_h + 8
        y = body_top
        n = len(events)
        if n:
            first_dot = y + ROW_H // 2
            last_dot = y + (n - 1) * ROW_H + ROW_H // 2
            d.rectangle((SPINE_X - 2, first_dot, SPINE_X + 2, last_dot), fill=SPINE)
            # Колпачки начала/конца
            d.ellipse((SPINE_X - 7, first_dot - 20, SPINE_X + 7, first_dot - 6), outline=SPINE, width=3)
            d.ellipse((SPINE_X - 7, last_dot + 6, SPINE_X + 7, last_dot + 20), outline=SPINE, width=3)

        for i, ev in enumerate(events):
            cy = y + i * ROW_H
            mid = cy + ROW_H // 2
            col = CAT_COLORS.get(ev.get('cat', ''), DEFAULT_COLOR)
            # Время слева
            t = str(ev.get('time', ''))
            tw = d.textlength(t, font=_font(28, True))
            d.text((SPINE_X - 40 - tw, mid - 18), t, font=_font(28, True), fill=MUTED)
            # Точка со свечением (прекомпозит, без альфа-канала)
            bg_here = tuple(int((13,20,32)[j] + ((24,34,54)[j] - (13,20,32)[j]) * (mid / max(1, H))) for j in range(3))
            halo = tuple(int(bg_here[j] + (col[j] - bg_here[j]) * 0.38) for j in range(3))
            d.ellipse((SPINE_X - 16, mid - 16, SPINE_X + 16, mid + 16), fill=halo + (255,))
            d.ellipse((SPINE_X - 9, mid - 9, SPINE_X + 9, mid + 9), fill=col + (255,))
            # Иконка категории
            ic = _icon(ev.get('cat', ''))
            ix = SPINE_X + 34
            if ic is not None:
                img.paste(ic, (ix, mid - 24), ic)
            d.rounded_rectangle((ix, mid - 24, ix + 48, mid + 24), radius=12,
                                outline=col + (200,), width=2)
            # Тексты
            tx = ix + 66
            d.text((tx, mid - 30), _ellipsize(d, str(ev.get('label', '')), _font(30, True), W - tx - PAD),
                   font=_font(30, True), fill=TEXT)
            det = str(ev.get('detail', '') or '')
            if det:
                d.text((tx, mid + 8), _ellipsize(d, det, _font(24), W - tx - PAD),
                       font=_font(24), fill=DIM)

        if not events:
            d.text((SPINE_X + 34, body_top + 10), 'Событий за окно не найдено',
                   font=_font(30), fill=DIM)

        if overflow:
            oy = y + n * ROW_H + 8
            d.text((SPINE_X + 34, oy), f'+ ещё {overflow} событий — смотрите лог-каналы',
                   font=_font(24, True), fill=GOLD)

        # Футер
        fy = H - footer_h + 22
        d.rectangle((PAD, fy, W - PAD, fy + 2), fill=GOLD_SOFT)
        d.text((PAD, fy + 16), 'AETHER REPLAY', font=_font(24, True), fill=GOLD)
        brand = 'Сгенерировано ботом'
        d.text((W - PAD - d.textlength(brand, font=_font(22)), fy + 18),
               brand, font=_font(22), fill=DIM)

        buf = io.BytesIO()
        img.convert('RGB').save(buf, 'PNG', optimize=True)
        return buf.getvalue()
    except Exception:
        return None
