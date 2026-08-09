"""
Aether — визуальная лестница наказаний (Pillow).

Ступени слева направо: «N предупреждений → действие». Рисует бот.

    from services.ladder_card import render_ladder_card, LADDER_CARD_OK
    png = render_ladder_card(steps, guild_name='MOEBIUS')
"""
import io
import os

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    LADDER_CARD_OK = True
except Exception:
    Image = ImageDraw = ImageFilter = ImageFont = None
    LADDER_CARD_OK = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_B = os.path.join(ROOT, 'assets', 'fonts', 'Bold.ttf')
FONT_R = os.path.join(ROOT, 'assets', 'fonts', 'Regular.ttf')
ICONS_DIR = os.path.join(ROOT, 'assets', 'icons', 'logcards')

GOLD = (212, 175, 55, 255)
GOLD_SOFT = (212, 175, 55, 90)
TEXT = (240, 244, 252, 255)
MUTED = (143, 163, 200, 255)
DIM = (124, 141, 176, 255)

ACTIONS = {
    'mute':    ('МУТ', (230, 126, 34), 'log_mod_256.png'),
    'timeout': ('МУТ', (230, 126, 34), 'log_mod_256.png'),
    'kick':    ('КИК', (231, 76, 60), 'log_mod_256.png'),
    'ban':     ('БАН', (192, 57, 43), 'log_mod_256.png'),
}

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


def _icon(fn, size=64):
    if not LADDER_CARD_OK:
        return None
    p = os.path.join(ICONS_DIR, fn)
    if not os.path.exists(p):
        return None
    try:
        im = Image.open(p).convert('RGB').resize((size, size), Image.LANCZOS)
        mask = Image.new('L', (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius=14, fill=255)
        out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        out.paste(im, (0, 0), mask)
        return out
    except Exception:
        return None


def _blend(c1, c2, k):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * k) for i in range(3))


def _duration_text(step):
    d = step.get('duration', 0) or 0
    unit = step.get('unit', 'minute')
    if not d:
        return 'навсегда' if (step.get('action') == 'ban') else ''
    n = int(d)
    if unit == 'hour':
        word = 'час' if n == 1 else ('часа' if 2 <= n <= 4 else 'часов')
        return f'{n} {word}'
    if unit == 'day':
        word = 'день' if n == 1 else ('дня' if 2 <= n <= 4 else 'дней')
        return f'{n} {word}'
    if n == 60:
        return '1 час'
    if n == 1440:
        return '1 день'
    word = 'минута' if n == 1 else ('минуты' if 2 <= n <= 4 else 'минут')
    return f'{n} {word}'


def render_ladder_card(steps, guild_name=''):
    """steps: [{'count':N,'action':'mute|kick|ban','duration':..,'unit':..}]
    Возвращает PNG-байты или None."""
    if not LADDER_CARD_OK:
        return None
    try:
        steps = sorted(steps or [], key=lambda s: int(s.get('count', 0)))[:6]
        W, H, PAD = 1440, 780, 56
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
        d.text((PAD, 58), 'ЛЕСТНИЦА НАКАЗАНИЙ', font=_font(26, True), fill=GOLD)
        d.text((PAD, 100), _ellipsize(d, guild_name or 'Сервер', _font(52, True), W - PAD * 2),
               font=_font(52, True), fill=TEXT)
        d.text((PAD, 170), 'Автоматические меры по количеству предупреждений', font=_font(26), fill=DIM)
        d.rectangle((PAD, 224, W - PAD, 226), fill=GOLD_SOFT)

        # Ступени
        floor = 640
        zone_w = W - PAD * 2
        if steps:
            n = len(steps)
            col = min(210, zone_w // n - 18)
            x = PAD
            for i, st in enumerate(steps):
                cnt = int(st.get('count', 0))
                act = str(st.get('action', 'mute'))
                label, col_rgb, icon_fn = ACTIONS.get(act, (act.upper(), (230, 126, 34), 'log_mod_256.png'))
                step_h = 150 + int(230 * (i + 1) / n)
                top = floor - step_h
                # Ступень: тёмное тело с оттенком цвета действия (без прозрачности)
                body = _blend((24, 34, 54), col_rgb, 0.16)
                d.rounded_rectangle((x, top, x + col, floor), radius=16,
                                    fill=body + (255,), outline=col_rgb + (255,), width=3)
                # Бейдж количества
                bx, by = x + col // 2, top - 34
                d.ellipse((bx - 34, by - 34, bx + 34, by + 34), fill=col_rgb + (255,),
                          outline=GOLD, width=3)
                num = str(cnt)
                nf = _font(34, True)
                d.text((bx - d.textlength(num, font=nf) / 2, by - 24), num, font=nf, fill=(255, 255, 255, 255))
                # Иконка действия
                ic = _icon(icon_fn)
                if ic is not None:
                    img.paste(ic, (x + col // 2 - 32, top + 26), ic)
                # Действие
                lf = _font(32, True)
                d.text((x + col // 2 - d.textlength(label, font=lf) / 2, top + 104), label,
                       font=lf, fill=col_rgb + (255,))
                dur = _duration_text(st)
                if dur:
                    df = _font(26, True)
                    d.text((x + col // 2 - d.textlength(dur, font=df) / 2, top + 148), dur,
                           font=df, fill=TEXT)
                # Подпись под ступенью
                cap = f'{cnt} предупреждений' if cnt >= 5 else (
                      f'{cnt} предупреждения' if 2 <= cnt <= 4 else 'первое')
                cf = _font(22)
                d.text((x + col // 2 - d.textlength(cap, font=cf) / 2, floor + 20), cap,
                       font=cf, fill=MUTED)
                x += col + int((zone_w - col * n) / max(1, n - 1)) if n > 1 else 0
            d.rectangle((PAD - 6, floor, W - PAD + 6, floor + 3), fill=GOLD_SOFT)
        else:
            d.text((PAD, 340), 'Лестница пока не настроена.', font=_font(32, True), fill=TEXT)
            d.text((PAD, 394), 'Добавьте ступени в панели (Предупреждения) или командой /ladder-add',
                   font=_font(26), fill=DIM)

        # Футер
        fy = H - 66
        d.rectangle((PAD, fy, W - PAD, fy + 2), fill=GOLD_SOFT)
        d.text((PAD, fy + 14), 'AETHER MODERATION', font=_font(24, True), fill=GOLD)
        brand = 'Авто-наказание по варнам'
        d.text((W - PAD - d.textlength(brand, font=_font(22)), fy + 16),
               brand, font=_font(22), fill=DIM)

        buf = io.BytesIO()
        img.convert('RGB').save(buf, 'PNG', optimize=True)
        return buf.getvalue()
    except Exception:
        return None
