"""
Aether — генератор карточек логов (Pillow).

Бот сам рисует премиальную карточку для каждого лог-события:
глубокий тёмно-синий фон, золотая шапка с иконкой категории,
подробные строки «Имя — значение», фирменный футер.

Использование:
    from services.log_card import render_log_card, LOG_CARD_OK
    png = render_log_card('role', 'Изменение ролей участника',
                          [('Участник', 'Ivan `123`'), ('Модератор', 'Mod `456`')],
                          color=0x9B59B6, cat_name='Роли', guild_name='MOEBIUS')
    # png -> bytes | None (ошибки не роняют вызывающий код)
"""
import io
import os
import re

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    LOG_CARD_OK = True
except Exception:  # Pillow отсутствует — карточки просто выключаются
    Image = ImageDraw = ImageFilter = ImageFont = None
    LOG_CARD_OK = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_B = os.path.join(ROOT, 'assets', 'fonts', 'Bold.ttf')
FONT_R = os.path.join(ROOT, 'assets', 'fonts', 'Regular.ttf')
ICONS_DIR = os.path.join(ROOT, 'assets', 'icons', 'logs')

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


def _clean(text):
    """Текст поля для картинки: без markdown и «сырых» упоминаний."""
    t = str(text or '')
    t = re.sub(r'<@&(\d+)>', r'@роль·\1', t)
    t = re.sub(r'<@!?(\d+)>', r'@\1', t)
    t = re.sub(r'<#(\d+)>', r'#\1', t)
    t = re.sub(r'<a?:(\w+):\d+>', r'\1', t)
    return t.replace('**', '').replace('`', '').strip()


def _ellipsize(draw, text, font, max_w):
    """Обрезать строку по ширине с многоточием."""
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + '…', font=font) > max_w:
        text = text[:-1]
    return text + '…'


def _rounded_icon(cat, size=176):
    """Иконка категории со скруглением; None, если нет файла."""
    if not LOG_CARD_OK:
        return None
    path = os.path.join(ICONS_DIR, f'log_{cat}_256.png')
    if not os.path.exists(path):
        path = os.path.join(ICONS_DIR, f'log_{cat}.png')
    if not os.path.exists(path):
        return None
    try:
        im = Image.open(path).convert('RGB').resize((size, size), Image.LANCZOS)
        mask = Image.new('L', (size, size), 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle((0, 0, size, size), radius=28, fill=255)
        out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        out.paste(im, (0, 0), mask)
        return out
    except Exception:
        return None


def _rgb(color_int, default=(200, 146, 42)):
    try:
        c = int(color_int)
        return ((c >> 16) & 255, (c >> 8) & 255, c & 255)
    except Exception:
        return default


def render_log_card(category, title, rows, color=0xC8922A, cat_name='',
                    guild_name='', time_str=''):
    """Нарисовать карточку лога; вернуть PNG-байты или None."""
    if not LOG_CARD_OK:
        return None
    try:
        W = 1440
        PAD = 56
        rows = [(n, v) for n, v in (rows or []) if v not in (None, '')][:8]
        header_h = 278
        row_h = 58
        footer_h = 86
        H = header_h + max(1, len(rows)) * row_h + footer_h

        accent = _rgb(color)
        # Фон: вертикальный градиент тёмного синего
        top, bottom = (13, 20, 32), (21, 30, 48)
        grad = Image.new('RGB', (1, H))
        for y in range(H):
            k = y / max(1, H - 1)
            grad.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)))
        img = grad.resize((W, H))
        # Мягкое свечение категории слева сверху
        glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse((-220, -260, 560, 430), fill=accent + (28,))
        glow = glow.filter(ImageFilter.GaussianBlur(90))
        img = Image.alpha_composite(img.convert('RGBA'), glow)
        d = ImageDraw.Draw(img)

        # Акцентная полоса слева
        d.rectangle((0, 0, 14, H), fill=accent + (255,))

        # Шапка: иконка + категория + заголовок + время
        icon = _rounded_icon(category)
        tx = PAD
        if icon is not None:
            img.paste(icon, (PAD, 48), icon)
            d.rounded_rectangle((PAD, 48, PAD + 176, 224), radius=28,
                                outline=accent + (220,), width=3)
            tx = PAD + 176 + 36

        if cat_name:
            d.text((tx, 64), _ellipsize(d, str(cat_name).upper(), _font(26, True), 640),
                   font=_font(26, True), fill=(212, 175, 55, 255))
        d.text((tx, 108), _ellipsize(d, _clean(title), _font(52, True), W - tx - PAD - 220),
               font=_font(52, True), fill=(240, 244, 252, 255))
        if time_str:
            d.text((W - PAD - 200, 70), _clean(time_str), font=_font(26),
                   fill=(124, 141, 176, 255))

        # Золотой разделитель шапки
        dy = header_h - 32
        d.rectangle((PAD, dy, W - PAD, dy + 2), fill=(212, 175, 55, 90))

        # Строки «Имя — значение»
        y = header_h
        name_w = 300
        for name, value in rows:
            nm = _ellipsize(d, _clean(name).upper(), _font(24, True), name_w - 20)
            d.text((PAD + 8, y + 14), nm, font=_font(24, True), fill=(143, 163, 200, 255))
            val = _ellipsize(d, _clean(value), _font(30), W - PAD - (PAD + name_w) - 8)
            d.text((PAD + name_w, y + 8), val, font=_font(30), fill=(232, 236, 244, 255))
            y += row_h
        if not rows:
            d.text((PAD + 8, y + 14), '—', font=_font(30), fill=(180, 190, 210, 255))

        # Футер
        fy = H - footer_h + 18
        d.rectangle((PAD, fy, W - PAD, fy + 2), fill=(212, 175, 55, 90))
        fl = f'AETHER LOG · {str(cat_name or category).upper()}'
        if guild_name:
            fl += f' · {_clean(guild_name)}'
        d.text((PAD, fy + 20), _ellipsize(d, fl, _font(24), W - PAD * 2 - 220),
               font=_font(24), fill=(124, 141, 176, 255))
        brand = 'AETHER'
        bw = d.textlength(brand, font=_font(26, True))
        d.text((W - PAD - bw, fy + 18), brand, font=_font(26, True), fill=(212, 175, 55, 255))

        buf = io.BytesIO()
        img.convert('RGB').save(buf, 'PNG', optimize=True)
        return buf.getvalue()
    except Exception:
        return None
