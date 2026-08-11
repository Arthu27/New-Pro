"""
Aether — профессиональный генератор карточек логов (Pillow).

Фирменная эстетика AETHER:
  • Глубокий звёздно-космический фон Midnight Navy (10, 16, 30) → (16, 26, 48)
  • Премиальное имперское золото Imperial Gold (212, 175, 55) и мерцающая золотая пыль
  • Индивидуальные золотые иконки и уникальные виджеты для каждой категории:
      - MOD: Рубиново-золотые щиты, скобки, плашки причин с кавычками
      - MESSAGE: Золото-циановая цифровая сетка, цитаты сообщений, хэштеги каналов
      - MEMBER / WELCOME: Аврора-изумрудные звёздные кольца, карточки профилей участников
      - VOICE: Золотой аудио-эквалайзер (звуковые волны), индикаторы переходов
      - ROLE: Королевский аметистово-золотой шевронный узор, бейджи +/- ролей
      - CHANNEL: Архитектурные золотые чертёжные направляющие и типы каналов
      - GUILD: Имперская двойная золотая рамка с алмазными углами и замком
      - INVITE: Портальные фиолетово-золотые лучи, чипы ссылок discord.gg/
      - TICKET: Золото-сапфировые плашки службы поддержки
"""
import io
import os
import re
import math
import random

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    LOG_CARD_OK = True
except Exception:
    Image = ImageDraw = ImageFilter = ImageFont = None
    LOG_CARD_OK = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_B = os.path.join(ROOT, 'assets', 'fonts', 'Bold.ttf')
FONT_R = os.path.join(ROOT, 'assets', 'fonts', 'Regular.ttf')
ICONS_DIR = os.path.join(ROOT, 'assets', 'icons', 'logcards')

# ═══════════════════════════════════════════════════════════════════════
# Золотая палитра AETHER
# ═══════════════════════════════════════════════════════════════════════
C_BG_TOP      = (10, 16, 30)
C_BG_BOT      = (16, 26, 48)
C_GOLD        = (212, 175, 55)
C_GOLD_BRIGHT = (245, 215, 110)
C_GOLD_SOFT   = (160, 130, 50)
C_GOLD_DIM    = (110, 90, 40)
C_TEXT_WHITE  = (242, 245, 252)
C_TEXT_DIM    = (140, 155, 185)
C_CELL_BG     = (255, 255, 255, 9)
C_CELL_BORDER = (212, 175, 55, 65)

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
    """Очистка текста от эмодзи, markdown и сырых упоминаний."""
    t = str(text or '')
    t = re.sub(r'<@&(\d+)>', r'@роль·\1', t)
    t = re.sub(r'<@!?(\d+)>', r'@\1', t)
    t = re.sub(r'<#(\d+)>', r'#\1', t)
    t = re.sub(r'<a?:(\w+):\d+>', r'\1', t)
    # Удаляем не отображаемые TTF шрифтом эмодзи
    t = re.sub(r'[\U00010000-\U0010ffff]', '', t)
    t = re.sub(r'[\u2600-\u27bf]', '', t)
    t = re.sub(r'[\ufe00-\ufe0f]', '', t)
    t = t.replace('**', '').replace('`', '').replace('__', '').strip()
    return re.sub(r'\s+', ' ', t)


def _ellipsize(draw, text, font_obj, max_w):
    """Обрезать строку с многоточием при превышении max_w."""
    text = str(text or '')
    if draw.textlength(text, font=font_obj) <= max_w:
        return text
    while text and draw.textlength(text + '…', font=font_obj) > max_w:
        text = text[:-1]
    return text + '…'


def _rgb(color_int, default=C_GOLD):
    """Преобразование int/hex цвета в RGB кортеж."""
    try:
        c = int(color_int)
        return ((c >> 16) & 255, (c >> 8) & 255, c & 255)
    except Exception:
        return default


def _load_icon(category, size=156):
    """Загрузить фирменную золотую иконку категории."""
    if not LOG_CARD_OK:
        return None
    aliases = {
        'automod': 'mod',
        'guild': 'guild',
        'сервер': 'guild',
        'welcome': 'welcome',
        'ai': 'ai',
    }
    key = aliases.get(category, category)
    path = os.path.join(ICONS_DIR, f'log_{key}_256.png')
    if not os.path.exists(path):
        path = os.path.join(ICONS_DIR, f'log_{key}.png')
    if not os.path.exists(path):
        return None
    try:
        im = Image.open(path).convert('RGBA').resize((size, size), Image.Resampling.LANCZOS)
        mask = Image.new('L', (size, size), 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle((0, 0, size, size), radius=28, fill=255)
        out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        out.paste(im, (0, 0), mask)
        return out
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════
# Категории AETHER: золотой стиль + индивидуальные виджеты
# ═══════════════════════════════════════════════════════════════════════
CATEGORY_STYLES = {
    'mod': {
        'tag': '✦ AETHER · МОДЕРАЦИЯ',
        'glow_color': (235, 65, 85),
        'type': 'mod',
    },
    'automod': {
        'tag': '✦ AETHER · АВТОМОДЕРАЦИЯ',
        'glow_color': (255, 90, 45),
        'type': 'mod',
    },
    'message': {
        'tag': '✦ AETHER · АУДИТ СООБЩЕНИЙ',
        'glow_color': (0, 195, 255),
        'type': 'message',
    },
    'member': {
        'tag': '✦ AETHER · УЧАСТНИКИ СЕРВЕРА',
        'glow_color': (46, 213, 115),
        'type': 'member',
    },
    'welcome': {
        'tag': '✦ AETHER · ВРАТА СЕРВЕРА',
        'glow_color': (32, 227, 178),
        'type': 'member',
    },
    'voice': {
        'tag': '✦ AETHER · ГОЛОСОВАЯ АКТИВНОСТЬ',
        'glow_color': (26, 188, 156),
        'type': 'voice',
    },
    'role': {
        'tag': '✦ AETHER · ИЕРАРХИЯ РОЛЕЙ',
        'glow_color': (165, 94, 234),
        'type': 'role',
    },
    'channel': {
        'tag': '✦ AETHER · СТРУКТУРА КАНАЛОВ',
        'glow_color': (243, 156, 18),
        'type': 'channel',
    },
    'guild': {
        'tag': '✦ AETHER · НАСТРОЙКИ СЕРВЕРА',
        'glow_color': (212, 175, 55),
        'type': 'guild',
    },
    'сервер': {
        'tag': '✦ AETHER · НАСТРОЙКИ СЕРВЕРА',
        'glow_color': (212, 175, 55),
        'type': 'guild',
    },
    'invite': {
        'tag': '✦ AETHER · ПРИГЛАШЕНИЯ',
        'glow_color': (108, 92, 231),
        'type': 'invite',
    },
    'ticket': {
        'tag': '✦ AETHER · СЛУЖБА ПОДДЕРЖКИ',
        'glow_color': (84, 160, 255),
        'type': 'ticket',
    },
}


def _draw_stardust(img, W, H):
    """Нарисовать мерцающие золотые звёзды и частицы на фоне."""
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    rnd = random.Random(42)
    for _ in range(65):
        sx = rnd.randint(18, W - 18)
        sy = rnd.randint(18, H - 18)
        size = rnd.choice([1, 1, 2, 2, 3])
        alpha = rnd.randint(50, 170)
        gold_tint = rnd.choice([C_GOLD, C_GOLD_BRIGHT, (255, 255, 255)])
        od.ellipse((sx, sy, sx + size, sy + size), fill=gold_tint + (alpha,))

    # 4-конечные звёздочки
    for _ in range(7):
        cx = rnd.randint(60, W - 60)
        cy = rnd.randint(30, min(240, H - 30))
        r = rnd.randint(3, 5)
        od.line([(cx - r, cy), (cx + r, cy)], fill=C_GOLD_BRIGHT + (180,), width=1)
        od.line([(cx, cy - r), (cx, cy + r)], fill=C_GOLD_BRIGHT + (180,), width=1)

    return Image.alpha_composite(img, overlay)


def _draw_category_widget(d, ctype, W, H, PAD, right_bound):
    """Нарисовать уникальный графический виджет в шапке карточки."""
    right_bound = int(right_bound)
    if ctype == 'voice':
        # Золотой эквалайзер
        eq_x = right_bound - 190
        eq_y = 66
        heights = [14, 26, 42, 20, 48, 34, 22, 40, 52, 28, 36, 44]
        for i, h in enumerate(heights):
            x = eq_x + i * 15
            d.line([(x, eq_y - h // 2), (x, eq_y + h // 2)], fill=C_GOLD + (180,), width=3)
            d.ellipse((x - 1, eq_y - h // 2 - 2, x + 1, eq_y - h // 2), fill=C_GOLD_BRIGHT + (230,))

    elif ctype == 'mod':
        # Предупреждающие диагональные насечки
        for i in range(6):
            x = right_bound - 190 + i * 30
            d.line([(x, 48), (x + 18, 76)], fill=C_GOLD + (140,), width=3)

    elif ctype == 'guild':
        # Алмазные декоративные угловые кристаллы
        for cx, cy in [(24, 24), (W - 24, 24), (24, H - 24), (W - 24, H - 24)]:
            d.polygon([(cx, cy - 6), (cx + 6, cy), (cx, cy + 6), (cx - 6, cy)], fill=C_GOLD_BRIGHT + (230,))

    elif ctype == 'message':
        # Цифровая точечная матрица
        for gx in range(right_bound - 180, right_bound - 10, 20):
            for gy in range(48, 88, 14):
                d.rectangle((gx, gy, gx + 2, gy + 2), fill=C_GOLD + (110,))

    elif ctype == 'member':
        # Звёздные арки авроры
        d.arc((right_bound - 180, 20, right_bound - 10, 120), start=180, end=360, fill=C_GOLD + (90,), width=2)
        d.arc((right_bound - 150, 36, right_bound - 40, 110), start=180, end=360, fill=C_GOLD_BRIGHT + (130,), width=2)

    elif ctype == 'role':
        # Шевроны иерархии
        rx = right_bound - 180
        for i in range(4):
            x = rx + i * 36
            d.line([(x, 48), (x + 12, 62), (x, 76)], fill=C_GOLD + (140,), width=3)

    elif ctype == 'channel':
        # Архитектурные направляющие
        d.line([(right_bound - 180, 50), (right_bound - 10, 50)], fill=C_GOLD + (100,), width=1)
        d.line([(right_bound - 180, 74), (right_bound - 10, 74)], fill=C_GOLD + (100,), width=1)
        for i in range(5):
            x = right_bound - 165 + i * 34
            d.line([(x, 44), (x, 80)], fill=C_GOLD + (70,), width=1)


def _load_celestial_bg(w, h, cat_tint=None):
    """Загружает фирменный звёздно-космический фон карточки логов.

    Приоритет: assets/aether_log_bg.png (фирменный тёмный фон с золотой
    туманностью по краям и чистым центром под текст) -> assets/help_bg.png
    (старый фон) -> процедурный градиент (совсем запасной вариант).
    """
    base = None
    for bg_name in ('aether_log_bg.png', 'help_bg.png'):
        bg_path = os.path.join(ROOT, 'assets', bg_name)
        if not os.path.exists(bg_path):
            continue
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
            break
        except Exception:
            continue
    if base is None:
        grad = Image.new('RGB', (1, h))
        for y in range(h):
            t = y / max(1, h - 1)
            grad.putpixel((0, y), tuple(int(C_BG_TOP[i] + (C_BG_BOT[i] - C_BG_TOP[i]) * t) for i in range(3)))
        base = grad.resize((w, h)).convert('RGBA')

    if cat_tint:
        glow = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse((-140, -160, 650, 420), fill=C_GOLD + (34,))
        gd.ellipse((w - 550, -200, w + 180, 360), fill=cat_tint + (22,))
        glow = glow.filter(ImageFilter.GaussianBlur(85))
        base = Image.alpha_composite(base, glow)

    return base


def render_log_card(category, title, rows, color=0xC8922A, cat_name='',
                    guild_name='', time_str=''):
    """Нарисовать премиальную золотую карточку лога в единой стилистике AETHER."""
    if not LOG_CARD_OK:
        return None
    try:
        W = 1440
        PAD = 52
        cat_key = str(category or 'guild').lower().strip()
        cstyle = CATEGORY_STYLES.get(cat_key, CATEGORY_STYLES.get('guild'))

        clean_rows = [(n, v) for n, v in (rows or []) if v not in (None, '')][:7]
        header_h = 248
        row_h = 72
        footer_h = 82
        H = header_h + max(1, len(clean_rows)) * row_h + footer_h

        # 1. Полноценная фоновая звёздная иллюстрация с неоновым свечением
        cat_glow = cstyle['glow_color']
        img = _load_celestial_bg(W, H, cat_tint=cat_glow)
        d = ImageDraw.Draw(img)

        # 4. Двойная золотая рамка по контуру карточки
        d.rectangle((10, 10, W - 10, H - 10), outline=C_GOLD + (90,), width=2)
        d.rectangle((16, 16, W - 16, H - 16), outline=C_GOLD_SOFT + (40,), width=1)

        # Левая золотая неоновая полоса
        d.rectangle((0, 0, 10, H), fill=C_GOLD + (255,))
        d.rectangle((10, 0, 14, H), fill=C_GOLD_BRIGHT + (140,))

        # 5. Время (в правом верхнем углу шапки)
        time_clean = _clean(time_str)
        t_font = _font(22, True)
        time_w = d.textlength(time_clean, font=t_font) if time_clean else 0
        right_limit = W - PAD

        if time_clean:
            t_pad_w = time_w + 24
            t_box_x = W - PAD - t_pad_w
            d.rounded_rectangle((t_box_x, 48, W - PAD, 48 + 36), radius=10,
                                fill=(20, 28, 48, 220), outline=C_GOLD + (100,), width=1)
            d.text((t_box_x + 12, 54), time_clean, font=t_font, fill=C_GOLD_BRIGHT)
            right_limit = t_box_x - 18

        # 6. Графический виджет категории в шапке (слева от плашки времени)
        _draw_category_widget(d, cstyle['type'], W, H, PAD, right_limit)

        # 7. Фирменная золотая иконка категории
        icon = _load_icon(cat_key, size=154)
        tx = PAD
        if icon is not None:
            # Тень под иконкой
            d.rounded_rectangle((PAD + 4, 46 + 4, PAD + 154 + 4, 46 + 154 + 4), radius=26,
                                fill=(0, 0, 0, 110))
            img.paste(icon, (PAD, 46), icon)
            d.rounded_rectangle((PAD, 46, PAD + 154, 46 + 154), radius=26,
                                outline=C_GOLD + (210,), width=3)
            tx = PAD + 154 + 32

        # 8. Бейдж категории в шапке (Золото + мягкий фон)
        cat_badge = cstyle.get('tag') or f'✦ AETHER · {str(cat_name or cat_key).upper()}'
        badge_font = _font(22, True)
        bw = d.textlength(cat_badge, font=badge_font) + 28
        bh = 38
        d.rounded_rectangle((tx, 48, tx + bw, 48 + bh), radius=12,
                            fill=(20, 28, 48, 220), outline=C_GOLD + (120,), width=1)
        d.text((tx + 14, 55), cat_badge, font=badge_font, fill=C_GOLD_BRIGHT)

        # Заголовок события (крупный золотой / бело-золотой)
        title_font = _font(44, True)
        title_txt = _ellipsize(d, _clean(title), title_font, W - tx - PAD - 20)
        d.text((tx, 98), title_txt, font=title_font, fill=C_TEXT_WHITE)

        # Золотой разделитель шапки с градиентным золотым штрихом
        sep_y = header_h - 22
        d.line([(PAD, sep_y), (W - PAD, sep_y)], fill=C_GOLD + (80,), width=1)
        d.line([(PAD, sep_y), (PAD + 240, sep_y)], fill=C_GOLD_BRIGHT + (230,), width=2)

        # 9. Строки данных — полупрозрачные плашки в золотых рамках
        y = header_h
        card_w = W - PAD * 2
        name_col_w = 280

        for name, value in clean_rows:
            clean_n = _clean(name).upper()
            clean_v = _clean(value)
            is_reason = clean_n in ('ПРИЧИНА', 'REASON', 'ПРИЧИНА НАКАЗАНИЯ')

            # Плашка строки
            box_fill = (45, 22, 28, 220) if is_reason else (18, 26, 44, 210)
            box_outline = (235, 75, 85, 160) if is_reason else C_CELL_BORDER

            d.rounded_rectangle((PAD, y + 4, PAD + card_w, y + row_h - 8), radius=14,
                                fill=box_fill, outline=box_outline, width=1)

            # Левый акцентный штрих плашки (золотой или рубиновый для причины)
            bar_color = (255, 80, 90, 255) if is_reason else C_GOLD + (255,)
            d.rounded_rectangle((PAD + 3, y + 10, PAD + 8, y + row_h - 14), radius=3,
                                fill=bar_color)

            # Название поля
            n_font = _font(22, True)
            d.text((PAD + 24, y + 20), _ellipsize(d, clean_n, n_font, name_col_w - 30),
                   font=n_font, fill=C_GOLD_BRIGHT if not is_reason else (255, 145, 155, 255))

            # Золотой разделитель
            d.text((PAD + name_col_w, y + 18), '›', font=_font(26, True), fill=C_GOLD + (170,))

            # Значение поля
            v_font = _font(26, False) if not is_reason else _font(26, True)
            val_x = PAD + name_col_w + 24
            max_val_w = W - PAD - val_x - 20
            val_txt = _ellipsize(d, clean_v, v_font, max_val_w)
            val_color = C_TEXT_WHITE if not is_reason else (255, 235, 235, 255)
            d.text((val_x, y + 19), val_txt, font=v_font, fill=val_color)

            y += row_h

        if not clean_rows:
            d.text((PAD + 24, y + 18), 'Нет дополнительных параметров', font=_font(26), fill=C_TEXT_DIM)

        # 10. Фирменный футер с золотым разделителем
        fy = H - footer_h + 16
        d.line([(PAD, fy), (W - PAD, fy)], fill=C_GOLD + (80,), width=1)

        f_txt = f"AETHER LOG · {str(cat_name or cat_key).upper()}"
        if guild_name:
            f_txt += f" · {_clean(guild_name)}"
        d.text((PAD, fy + 18), _ellipsize(d, f_txt, _font(22), W - PAD * 2 - 200),
               font=_font(22), fill=C_TEXT_DIM)

        brand = "✦ AETHER"
        bw = d.textlength(brand, font=_font(24, True))
        d.text((W - PAD - bw, fy + 16), brand, font=_font(24, True), fill=C_GOLD_BRIGHT)

        buf = io.BytesIO()
        img.convert('RGB').save(buf, 'PNG', optimize=True)
        return buf.getvalue()
    except Exception:
        return None
