"""
Aether — профессиональный генератор карточек логов (Pillow).

Для каждой категории событий создаётся уникальный дизайн:
  • MOD / AUTOMOD   — глубокий обсидиановый фон, магма-красные акценты, знаки предупреждения, плашки причин
  • MESSAGE         — кибер-сапфировый/неоновый циановый стиль, чат-бабблы, diff-блоки сообщений, хэштеги каналов
  • MEMBER          — аврора-мятный/изумрудный градиент, портал входа/выхода, статус-чипы и карточки участников
  • VOICE           — аквамариновый/морской стиль с визуальным звуковым эквалайзером и стрелками перемещения
  • ROLE            — королевский аметистовый/пурпурный стиль, бейджи иерархии, чипы +/− ролей
  • CHANNEL         — архитектурный янтарно-золотой стиль, чертёжная сетка, индикаторы типов каналов
  • GUILD / СЕРВЕР  — имперское обсидиановое золото, двойная рамка, герб сервера, премиум-типографика
  • INVITE          — индиго-фиолетовый портальный стиль, моноширинный чип ссылки discord.gg/
  • TICKET          — высокотехнологичный индиго-голубой саппорт-стиль с ID-бейджем тикета

Использование:
    from services.log_card import render_log_card, LOG_CARD_OK
    png = render_log_card('mod', 'Бан участника',
                          [('Участник', 'Ivan `123`'), ('Модератор', 'Admin `456`'), ('Причина', 'Спам')],
                          color=0xE74C3C, cat_name='Модерация', guild_name='AETHER')
"""
import io
import os
import re
import math

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
    """Очистка текста для рендеринга на изображении."""
    t = str(text or '')
    t = re.sub(r'<@&(\d+)>', r'@роль·\1', t)
    t = re.sub(r'<@!?(\d+)>', r'@\1', t)
    t = re.sub(r'<#(\d+)>', r'#\1', t)
    t = re.sub(r'<a?:(\w+):\d+>', r'\1', t)
    return t.replace('**', '').replace('`', '').strip()


def _ellipsize(draw, text, font_obj, max_w):
    """Обрезать строку с многоточием при превышении max_w."""
    text = str(text or '')
    if draw.textlength(text, font=font_obj) <= max_w:
        return text
    while text and draw.textlength(text + '…', font=font_obj) > max_w:
        text = text[:-1]
    return text + '…'


def _rgb(color_int, default=(200, 146, 42)):
    """Преобразование int/hex цвета в RGB кортеж."""
    try:
        c = int(color_int)
        return ((c >> 16) & 255, (c >> 8) & 255, c & 255)
    except Exception:
        return default


def _load_icon(category, size=160):
    """Загрузить и подготовить скруглённую иконку категории."""
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
        md.rounded_rectangle((0, 0, size, size), radius=26, fill=255)
        out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        out.paste(im, (0, 0), mask)
        return out
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════
# Темы категорий: уникальные палитры, эффекты и декоративные элементы
# ═══════════════════════════════════════════════════════════════════════
THEMES = {
    'mod': {
        'bg_top': (16, 12, 18),
        'bg_bot': (26, 14, 20),
        'accent': (235, 65, 85),
        'accent_sec': (250, 130, 49),
        'pill_bg': (38, 18, 24, 210),
        'pill_border': (235, 65, 85, 140),
        'tag_text': '🛡️ SECURITY / MODERATION',
        'tag_color': (255, 107, 129),
        'style': 'mod',
    },
    'automod': {
        'bg_top': (18, 12, 14),
        'bg_bot': (28, 16, 20),
        'accent': (255, 75, 43),
        'accent_sec': (255, 180, 0),
        'pill_bg': (40, 18, 22, 210),
        'pill_border': (255, 75, 43, 140),
        'tag_text': '⚡ AUTOMOD / SYSTEM',
        'tag_color': (255, 120, 90),
        'style': 'mod',
    },
    'message': {
        'bg_top': (10, 18, 30),
        'bg_bot': (16, 26, 44),
        'accent': (0, 200, 255),
        'accent_sec': (70, 130, 250),
        'pill_bg': (18, 32, 54, 200),
        'pill_border': (0, 200, 255, 130),
        'tag_text': '💬 MESSAGE AUDIT',
        'tag_color': (90, 220, 255),
        'style': 'message',
    },
    'member': {
        'bg_top': (10, 22, 18),
        'bg_bot': (16, 36, 28),
        'accent': (46, 213, 115),
        'accent_sec': (0, 230, 118),
        'pill_bg': (18, 42, 32, 200),
        'pill_border': (46, 213, 115, 130),
        'tag_text': '👤 MEMBER EVENT',
        'tag_color': (120, 240, 170),
        'style': 'member',
    },
    'welcome': {
        'bg_top': (10, 24, 22),
        'bg_bot': (16, 38, 34),
        'accent': (32, 227, 178),
        'accent_sec': (255, 215, 0),
        'pill_bg': (18, 44, 40, 200),
        'pill_border': (32, 227, 178, 140),
        'tag_text': '✨ WELCOME / GATEWAY',
        'tag_color': (80, 245, 205),
        'style': 'member',
    },
    'voice': {
        'bg_top': (8, 20, 28),
        'bg_bot': (12, 32, 44),
        'accent': (26, 188, 156),
        'accent_sec': (0, 210, 255),
        'pill_bg': (16, 38, 50, 200),
        'pill_border': (26, 188, 156, 140),
        'tag_text': '🎙️ VOICE ACTIVITY',
        'tag_color': (80, 230, 210),
        'style': 'voice',
    },
    'role': {
        'bg_top': (18, 12, 28),
        'bg_bot': (28, 16, 44),
        'accent': (155, 89, 182),
        'accent_sec': (235, 77, 150),
        'pill_bg': (36, 22, 54, 200),
        'pill_border': (155, 89, 182, 130),
        'tag_text': '🎭 ROLE MANAGEMENT',
        'tag_color': (205, 155, 230),
        'style': 'role',
    },
    'channel': {
        'bg_top': (24, 18, 10),
        'bg_bot': (38, 26, 14),
        'accent': (243, 156, 18),
        'accent_sec': (230, 126, 34),
        'pill_bg': (48, 34, 18, 200),
        'pill_border': (243, 156, 18, 130),
        'tag_text': '📁 CHANNEL STRUCTURE',
        'tag_color': (255, 195, 90),
        'style': 'channel',
    },
    'guild': {
        'bg_top': (15, 16, 24),
        'bg_bot': (24, 26, 38),
        'accent': (212, 175, 55),
        'accent_sec': (241, 196, 15),
        'pill_bg': (38, 34, 24, 210),
        'pill_border': (212, 175, 55, 150),
        'tag_text': '👑 SERVER UPDATE',
        'tag_color': (245, 215, 110),
        'style': 'guild',
    },
    'сервер': {
        'bg_top': (15, 16, 24),
        'bg_bot': (24, 26, 38),
        'accent': (212, 175, 55),
        'accent_sec': (241, 196, 15),
        'pill_bg': (38, 34, 24, 210),
        'pill_border': (212, 175, 55, 150),
        'tag_text': '👑 SERVER UPDATE',
        'tag_color': (245, 215, 110),
        'style': 'guild',
    },
    'invite': {
        'bg_top': (15, 14, 28),
        'bg_bot': (24, 22, 44),
        'accent': (108, 92, 231),
        'accent_sec': (162, 155, 254),
        'pill_bg': (32, 26, 56, 200),
        'pill_border': (108, 92, 231, 130),
        'tag_text': '🔗 INVITE PORTAL',
        'tag_color': (180, 165, 255),
        'style': 'invite',
    },
    'ticket': {
        'bg_top': (14, 18, 32),
        'bg_bot': (20, 28, 48),
        'accent': (84, 160, 255),
        'accent_sec': (95, 39, 205),
        'pill_bg': (24, 34, 60, 200),
        'pill_border': (84, 160, 255, 140),
        'tag_text': '🎫 SUPPORT TICKET',
        'tag_color': (140, 200, 255),
        'style': 'message',
    },
}


def _draw_decorations(d, theme, W, H, PAD):
    """Нарисовать индивидуальные графические декорации для стиля категории."""
    st = theme['style']
    acc = theme['accent']
    sec = theme['accent_sec']

    if st == 'mod':
        # Диагональные предупреждающие насечки в правом верхнем углу
        for i in range(7):
            x = W - PAD - 260 + i * 36
            d.line([(x, 34), (x + 22, 70)], fill=acc + (60,), width=3)
        # Технические угловые скобки [ ]
        d.line([(PAD - 16, 32), (PAD + 24, 32)], fill=acc + (180,), width=2)
        d.line([(PAD - 16, 32), (PAD - 16, 72)], fill=acc + (180,), width=2)
        d.line([(W - PAD + 16, H - 32), (W - PAD - 24, H - 32)], fill=acc + (180,), width=2)
        d.line([(W - PAD + 16, H - 32), (W - PAD + 16, H - 72)], fill=acc + (180,), width=2)

    elif st == 'voice':
        # Аудио-эквалайзер / звуковые волны в шапке
        eq_x = W - PAD - 280
        eq_y = 74
        heights = [18, 32, 48, 22, 54, 38, 26, 44, 58, 30, 42, 52, 24, 36, 20]
        for i, h in enumerate(heights):
            x = eq_x + i * 18
            d.line([(x, eq_y - h // 2), (x, eq_y + h // 2)], fill=acc + (160,), width=4)

    elif st == 'message':
        # Точечная сетка кибер-терминала
        for gx in range(W - PAD - 240, W - PAD - 20, 24):
            for gy in range(40, 96, 18):
                d.rectangle((gx, gy, gx + 2, gy + 2), fill=acc + (80,))

    elif st == 'guild':
        # Двойная золотая рамка с декоративными углами
        d.rectangle((18, 18, W - 18, H - 18), outline=acc + (110,), width=2)
        d.rectangle((26, 26, W - 26, H - 26), outline=acc + (50,), width=1)
        # Угловые алмазные акценты
        for cx, cy in [(26, 26), (W - 26, 26), (26, H - 26), (W - 26, H - 26)]:
            d.polygon([(cx, cy - 6), (cx + 6, cy), (cx, cy + 6), (cx - 6, cy)], fill=acc + (220,))

    elif st == 'role':
        # Иерархические шевроны
        rx = W - PAD - 220
        for i in range(4):
            x = rx + i * 42
            d.line([(x, 46), (x + 16, 62), (x, 78)], fill=acc + (120,), width=3)

    elif st == 'channel':
        # Архитектурные направляющие и хэш-паттерн
        d.line([(W - PAD - 240, 48), (W - PAD, 48)], fill=acc + (80,), width=1)
        d.line([(W - PAD - 240, 78), (W - PAD, 78)], fill=acc + (80,), width=1)
        for i in range(5):
            x = W - PAD - 220 + i * 45
            d.line([(x, 40), (x, 86)], fill=acc + (50,), width=1)

    elif st == 'member':
        # Радиальные кольца авроры
        d.arc((W - PAD - 260, 20, W - PAD + 20, 180), start=180, end=360, fill=acc + (70,), width=2)
        d.arc((W - PAD - 220, 40, W - PAD - 20, 160), start=180, end=360, fill=sec + (90,), width=2)


def render_log_card(category, title, rows, color=0xC8922A, cat_name='',
                    guild_name='', time_str=''):
    """Нарисовать премиальную уникальную карточку лога в зависимости от категории."""
    if not LOG_CARD_OK:
        return None
    try:
        W = 1440
        PAD = 52
        cat_key = str(category or 'guild').lower().strip()
        theme = THEMES.get(cat_key, THEMES.get('guild')).copy()
        if color and color != 0xC8922A:
            theme['accent'] = _rgb(color, theme['accent'])

        clean_rows = [(n, v) for n, v in (rows or []) if v not in (None, '')][:7]
        header_h = 248
        row_h = 72
        footer_h = 80
        H = header_h + max(1, len(clean_rows)) * row_h + footer_h

        accent = theme['accent']
        accent_sec = theme['accent_sec']
        top, bot = theme['bg_top'], theme['bg_bot']

        # 1. Градиентная основа фона
        grad = Image.new('RGB', (1, H))
        for y in range(H):
            t = y / max(1, H - 1)
            grad.putpixel((0, y), tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
        img = grad.resize((W, H))

        # 2. Мягкое неоновое свечение в шапке
        glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse((-120, -160, 680, 420), fill=accent + (32,))
        gd.ellipse((W - 500, -200, W + 200, 360), fill=accent_sec + (18,))
        glow = glow.filter(ImageFilter.GaussianBlur(80))
        img = Image.alpha_composite(img.convert('RGBA'), glow)
        d = ImageDraw.Draw(img)

        # 3. Акцентная боковая неоновая полоса слева
        d.rectangle((0, 0, 12, H), fill=accent + (255,))
        d.rectangle((12, 0, 16, H), fill=accent + (90,))

        # 4. Уникальные графические декорации категории
        _draw_decorations(d, theme, W, H, PAD)

        # 5. Иконка категории
        icon = _load_icon(cat_key, size=154)
        tx = PAD
        if icon is not None:
            # Тень под иконкой
            d.rounded_rectangle((PAD + 4, 46 + 4, PAD + 154 + 4, 46 + 154 + 4), radius=26,
                                fill=(0, 0, 0, 90))
            img.paste(icon, (PAD, 46), icon)
            d.rounded_rectangle((PAD, 46, PAD + 154, 46 + 154), radius=26,
                                outline=accent + (230,), width=3)
            tx = PAD + 154 + 32

        # 6. Бейдж категории в шапке
        cat_badge = theme.get('tag_text') or f'● {str(cat_name or cat_key).upper()}'
        badge_font = _font(22, True)
        bw = d.textlength(cat_badge, font=badge_font) + 28
        bh = 38
        d.rounded_rectangle((tx, 48, tx + bw, 48 + bh), radius=12,
                            fill=theme['pill_bg'], outline=theme['pill_border'], width=1)
        d.text((tx + 14, 55), cat_badge, font=badge_font, fill=theme['tag_color'])

        # Время (в правом углу шапки)
        if time_str:
            t_font = _font(24, False)
            t_txt = f"⏱ {_clean(time_str)}"
            t_w = d.textlength(t_txt, font=t_font)
            d.text((W - PAD - t_w, 48), t_txt, font=t_font, fill=(140, 155, 185, 255))

        # Заголовок события
        title_font = _font(44, True)
        title_txt = _ellipsize(d, _clean(title), title_font, W - tx - PAD - 20)
        d.text((tx, 98), title_txt, font=title_font, fill=(244, 248, 255, 255))

        # Разделитель шапки (тонкий градиентный)
        sep_y = header_h - 22
        d.line([(PAD, sep_y), (W - PAD, sep_y)], fill=accent + (100,), width=2)
        d.line([(PAD, sep_y), (PAD + 220, sep_y)], fill=accent + (255,), width=2)

        # 7. Индивидуальные строки данных в виде премиум-карточек
        y = header_h
        card_w = W - PAD * 2
        name_col_w = 280

        for name, value in clean_rows:
            clean_n = _clean(name).upper()
            clean_v = _clean(value)
            is_reason = clean_n in ('ПРИЧИНА', 'REASON', 'ПРИЧИНА НАКАЗАНИЯ')
            is_diff = clean_n in ('БЫЛО', 'СТАЛО', 'ТЕКСТ', 'СООБЩЕНИЕ', 'CONTENT')

            # Фоновая плашка строки
            box_fill = (44, 20, 24, 210) if is_reason else theme['pill_bg']
            box_outline = (255, 80, 90, 160) if is_reason else theme['pill_border']

            d.rounded_rectangle((PAD, y + 4, PAD + card_w, y + row_h - 8), radius=14,
                                fill=box_fill, outline=box_outline, width=1)

            # Левый акцентный штрих плашки
            bar_color = (255, 75, 85, 255) if is_reason else accent + (255,)
            d.rounded_rectangle((PAD + 3, y + 10, PAD + 8, y + row_h - 14), radius=3,
                                fill=bar_color)

            # Название поля
            n_font = _font(22, True)
            d.text((PAD + 24, y + 20), _ellipsize(d, clean_n, n_font, name_col_w - 30),
                   font=n_font, fill=theme['tag_color'] if not is_reason else (255, 140, 150, 255))

            # Разделительная точка
            d.text((PAD + name_col_w, y + 18), '›', font=_font(26, True), fill=(120, 135, 165, 180))

            # Значение поля
            v_font = _font(26, False) if not is_reason else _font(26, True)
            val_x = PAD + name_col_w + 24
            max_val_w = W - PAD - val_x - 20
            val_txt = _ellipsize(d, clean_v, v_font, max_val_w)
            val_color = (248, 250, 255, 255) if not is_reason else (255, 235, 235, 255)
            d.text((val_x, y + 19), val_txt, font=v_font, fill=val_color)

            y += row_h

        if not clean_rows:
            d.text((PAD + 24, y + 18), 'Нет дополнительных параметров', font=_font(26), fill=(140, 155, 180, 255))

        # 8. Фирменный футер
        fy = H - footer_h + 16
        d.line([(PAD, fy), (W - PAD, fy)], fill=accent + (90,), width=1)

        f_txt = f"AETHER LOG · {str(cat_name or cat_key).upper()}"
        if guild_name:
            f_txt += f" · {_clean(guild_name)}"
        d.text((PAD, fy + 18), _ellipsize(d, f_txt, _font(22), W - PAD * 2 - 200),
               font=_font(22), fill=(130, 148, 180, 255))

        brand = "✦ AETHER"
        bw = d.textlength(brand, font=_font(24, True))
        d.text((W - PAD - bw, fy + 16), brand, font=_font(24, True), fill=accent + (255,))

        buf = io.BytesIO()
        img.convert('RGB').save(buf, 'PNG', optimize=True)
        return buf.getvalue()
    except Exception:
        return None
