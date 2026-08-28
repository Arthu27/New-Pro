"""
Hakumo — визуальная лестница наказаний (Pillow).

Ступени слева направо: «N предупреждений → действие». Рисуется ботом на фоне Midnight Navy.

    from services.ladder_card import render_ladder_card, LADDER_CARD_OK
    png = render_ladder_card(steps, guild_name='HAKUMO')
"""
import io
import os
import random

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

C_BG_TOP       = (10, 16, 30)
C_BG_BOT       = (16, 26, 48)
GOLD           = (212, 175, 55, 255)
GOLD_BRIGHT    = (245, 215, 110, 255)
GOLD_SOFT      = (212, 175, 55, 90)
TEXT           = (240, 244, 252, 255)
MUTED          = (143, 163, 200, 255)
DIM            = (124, 141, 176, 255)

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
    text = str(text or '')
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
        im = Image.open(p).convert('RGBA').resize((size, size), Image.Resampling.LANCZOS)
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


def _load_celestial_bg(w, h):
    """Загружает реальный звёздно-космический фон assets/help_bg.png с золотой аурой."""
    bg_path = os.path.join(ROOT, 'assets', 'help_bg.png')
    try:
        bg_im = Image.open(bg_path).convert('RGBA')
        bw, bh = bg_im.size
        target_ratio = w / h
        src_ratio = bw / bh
        if src_ratio > target_ratio:
            nw = int(bh * target_ratio)
            x0 = (bw - nw) // 2
            bg_im = bg_im.crop((x0, 0, x0 + nw, bh))
        else:
            nh = int(bw / target_ratio)
            y0 = (bh - nh) // 2
            bg_im = bg_im.crop((0, y0, bw, y0 + nh))
        base = bg_im.resize((w, h), Image.Resampling.LANCZOS)
    except Exception:
        grad = Image.new('RGB', (1, h))
        for y in range(h):
            t = y / max(1, h - 1)
            grad.putpixel((0, y), tuple(int(C_BG_TOP[i] + (C_BG_BOT[i] - C_BG_TOP[i]) * t) for i in range(3)))
        base = grad.resize((w, h)).convert('RGBA')

    glow = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((-240, -280, 620, 460), fill=(212, 175, 55, 30))
    return Image.alpha_composite(base, glow.filter(ImageFilter.GaussianBlur(90)))


def render_ladder_card(steps, guild_name=''):
    """steps: [{'count':N,'action':'mute|kick|ban','duration':..,'unit':..}]
    Возвращает PNG-байты или None."""
    if not LADDER_CARD_OK:
        return None
    try:
        steps = sorted(steps or [], key=lambda s: int(s.get('count', 0)))[:6]
        W, H, PAD = 1440, 780, 56
        img = _load_celestial_bg(W, H)
        d = ImageDraw.Draw(img)

        # Двойная золотая рамка
        d.rectangle((10, 10, W - 10, H - 10), outline=GOLD_SOFT, width=2)
        d.rectangle((16, 16, W - 16, H - 16), outline=(212, 175, 55, 40), width=1)

        # Шапка
        badge_txt = "✦ HAKUMO · ЛЕСТНИЦА НАКАЗАНИЙ"
        bw = d.textlength(badge_txt, font=_font(20, True)) + 24
        d.rounded_rectangle((PAD, 48, PAD + bw, 48 + 34), radius=10,
                            fill=(20, 28, 48, 220), outline=(212, 175, 55, 120), width=1)
        d.text((PAD + 12, 54), badge_txt, font=_font(20, True), fill=GOLD_BRIGHT)

        d.text((PAD, 96), _ellipsize(d, guild_name or 'Сервер', _font(48, True), W - PAD * 2),
               font=_font(48, True), fill=TEXT)
        d.text((PAD, 156), 'Автоматическая эскалация мер по количеству предупреждений', font=_font(24), fill=DIM)
        d.line([(PAD, 204), (W - PAD, 204)], fill=GOLD_SOFT, width=1)

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

                # Ступень: градиентная плашка
                body = _blend((20, 28, 46), col_rgb, 0.22)
                d.rounded_rectangle((x, top, x + col, floor), radius=16,
                                    fill=body + (240,), outline=col_rgb + (255,), width=2)

                # Бейдж количества
                bx, by = x + col // 2, top - 34
                d.ellipse((bx - 34, by - 34, bx + 34, by + 34), fill=col_rgb + (255,),
                          outline=GOLD, width=2)
                num = str(cnt)
                nf = _font(34, True)
                d.text((bx - d.textlength(num, font=nf) / 2, by - 24), num, font=nf, fill=(255, 255, 255, 255))

                # Иконка действия
                ic = _icon(icon_fn)
                if ic is not None:
                    img.paste(ic, (x + col // 2 - 32, top + 26), ic)

                # Название действия
                lf = _font(30, True)
                d.text((x + col // 2 - d.textlength(label, font=lf) / 2, top + 104), label,
                       font=lf, fill=col_rgb + (255,))
                dur = _duration_text(st)
                if dur:
                    df = _font(24, True)
                    d.text((x + col // 2 - d.textlength(dur, font=df) / 2, top + 146), dur,
                           font=df, fill=TEXT)

                # Подпись под ступенью
                cap = f'{cnt} предупреждений' if cnt >= 5 else (
                      f'{cnt} предупреждения' if 2 <= cnt <= 4 else 'первое')
                cf = _font(22)
                d.text((x + col // 2 - d.textlength(cap, font=cf) / 2, floor + 20), cap,
                       font=cf, fill=MUTED)
                x += col + int((zone_w - col * n) / max(1, n - 1)) if n > 1 else 0
            d.line([(PAD - 6, floor), (W - PAD + 6, floor)], fill=GOLD_SOFT, width=2)
        else:
            d.text((PAD, 340), 'Лестница пока не настроена.', font=_font(32, True), fill=TEXT)
            d.text((PAD, 394), 'Добавьте ступени в панели (Предупреждения) или командой /ladder-add',
                   font=_font(26), fill=DIM)

        # Футер
        fy = H - 66
        d.line([(PAD, fy), (W - PAD, fy)], fill=GOLD_SOFT, width=1)
        d.text((PAD, fy + 14), 'HAKUMO MODERATION · АВТО-НАКАЗАНИЯ', font=_font(22), fill=GOLD)
        brand = '✦ HAKUMO'
        d.text((W - PAD - d.textlength(brand, font=_font(24, True)), fy + 12),
               brand, font=_font(24, True), fill=GOLD_BRIGHT)

        buf = io.BytesIO()
        img.convert('RGB').save(buf, 'PNG', optimize=True)
        return buf.getvalue()
    except Exception:
        return None
