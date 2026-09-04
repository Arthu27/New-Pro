"""
Hakumo — профессиональный генератор карточек логов (Pillow).

Фирменная эстетика HAKUMO:
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

from logger import get_logger

_log = get_logger("log_card")

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
# Палитры карточек логов. 'hakumo' — историческое фирменное золото на
# полуночном небе (ровно тот вид, что был всегда). Остальные — цветовые
# вариации «по нашей теме», выбираются из панели (data/log_cards_<gid>.json).
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

LOG_CARD_THEMES = {
    'hakumo': {'gold': C_GOLD, 'bright': C_GOLD_BRIGHT, 'soft': C_GOLD_SOFT,
               'dim': C_GOLD_DIM, 'bg_top': C_BG_TOP, 'bg_bot': C_BG_BOT,
               'stars': (C_GOLD, C_GOLD_BRIGHT, (255, 255, 255)),
               'label': 'Hakumo Gold (фирменная)'},
    'violet': {'gold': (165, 140, 255), 'bright': (205, 190, 255),
               'soft': (120, 100, 210), 'dim': (85, 70, 150),
               'bg_top': (14, 12, 30), 'bg_bot': (26, 20, 50),
               'stars': ((165, 140, 255), (140, 220, 255), (255, 255, 255)),
               'label': 'Фиалковая ночь'},
    'night': {'gold': (240, 170, 70), 'bright': (255, 205, 130),
              'soft': (185, 125, 50), 'dim': (125, 85, 35),
              'bg_top': (12, 12, 16), 'bg_bot': (22, 20, 30),
              'stars': ((240, 170, 70), (255, 220, 160), (255, 255, 255)),
              'label': 'Ночная янтарь'},
    'ocean': {'gold': (80, 200, 250), 'bright': (160, 230, 255),
              'soft': (50, 150, 205), 'dim': (35, 105, 145),
              'bg_top': (6, 20, 30), 'bg_bot': (12, 34, 48),
              'stars': ((80, 200, 250), (140, 240, 230), (255, 255, 255)),
              'label': 'Океан'},
    'forest': {'gold': (90, 220, 150), 'bright': (165, 240, 195),
               'soft': (60, 165, 110), 'dim': (42, 115, 80),
               'bg_top': (8, 22, 16), 'bg_bot': (16, 36, 24),
               'stars': ((90, 220, 150), (190, 250, 200), (255, 255, 255)),
               'label': 'Лес'},
}
LOG_CARD_THEME_ORDER = tuple(LOG_CARD_THEMES)
DEFAULT_LOG_THEME = 'hakumo'


def _clamp(v):
    return max(0, min(255, int(v)))


def _mix(rgb, to, t):
    """Линейный сдвиг цвета к to (белый или чёрный) на долю t."""
    return tuple(_clamp(c + (t2 - c) * t) for c, t2 in zip(rgb, to))


def _ui_color(v):
    """Цвет из UI: '#22d3ee' | '22d3ee' | int 0x22D3EE → RGB или None."""
    if v is None:
        return None
    if isinstance(v, int):
        return _rgb(v, default=None)
    s = str(v).strip().lstrip('#')
    if len(s) != 6:
        return None
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return None


def _palette(theme=None, accent=None):
    """Собрать палитру: тема из реестра + опциональный акцент владельца.

    Акцент заменяет золотую гамму (основной/светлый/тёмный/приглушённый),
    фон и звёздная пыль остаются от выбранной темы.
    """
    base = LOG_CARD_THEMES.get(str(theme or '').strip().lower(),
                               LOG_CARD_THEMES[DEFAULT_LOG_THEME])
    pal = dict(base)
    rgb = _ui_color(accent)
    if rgb:
        pal['gold'] = rgb
        pal['bright'] = _mix(rgb, (255, 255, 255), 0.35)
        pal['soft'] = _mix(rgb, (0, 0, 0), 0.28)
        pal['dim'] = _mix(rgb, (0, 0, 0), 0.52)
    return pal


# ── Настройки карточек логов (один файл на сервер, как warn_config_<gid>) ──
def log_cards_cfg_path(gid):
    return os.path.join(ROOT, 'data', f'log_cards_{gid}.json')


def get_log_cards_cfg(gid):
    """{'enabled': bool, 'theme': str, 'accent': ''} — с валидацией мусора."""
    cfg = {'enabled': True, 'theme': DEFAULT_LOG_THEME, 'accent': ''}
    try:
        path = log_cards_cfg_path(gid)
        if os.path.exists(path):
            import json as _json
            with open(path, 'r', encoding='utf-8') as fp:
                raw = _json.load(fp)
            if isinstance(raw, dict):
                if isinstance(raw.get('enabled'), bool):
                    cfg['enabled'] = raw['enabled']
                theme = str(raw.get('theme') or '').strip().lower()
                if theme in LOG_CARD_THEMES:
                    cfg['theme'] = theme
                acc = str(raw.get('accent') or '').strip().lstrip('#')
                if not acc or _ui_color(acc):
                    cfg['accent'] = acc
    except Exception as _ex:
        _log.debug('get_log_cards_cfg(): %s', _ex)
    return cfg


def save_log_cards_cfg(gid, data):
    """Записать настройки после валидации. Возвращает нормализованный dict."""
    if not isinstance(data, dict):
        data = {}
    cfg = {
        'enabled': bool(data.get('enabled', True)),
        'theme': DEFAULT_LOG_THEME,
        'accent': '',
    }
    theme = str(data.get('theme') or '').strip().lower()
    if theme in LOG_CARD_THEMES:
        cfg['theme'] = theme
    acc = str(data.get('accent') or '').strip().lstrip('#')
    if _ui_color(acc):
        cfg['accent'] = acc
    try:
        os.makedirs(os.path.dirname(log_cards_cfg_path(gid)), exist_ok=True)
        import json as _json
        with open(log_cards_cfg_path(gid), 'w', encoding='utf-8') as fp:
            _json.dump(cfg, fp, ensure_ascii=False, indent=2)
    except Exception as _ex:
        _log.debug('save_log_cards_cfg(): %s', _ex)
    return cfg

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
    """Очистка текста от эмодзи, markdown, ссылок и сырых упоминаний."""
    t = str(text or '')
    # Маркдаун-ссылки на картинке бесполезны: [Перейти...](url) -> «Перейти...»,
    # а «Перейти к сообщению»/«Перейти» без ссылки — мусор, убираем целиком.
    t = re.sub(r'\[([^\]\[]*)\]\([^)]*\)', r'\1', t)
    t = t.replace(' · Перейти к сообщению', '').replace(' · Перейти', '')
    t = t.replace('Перейти к сообщению · ', '').replace('Перейти · ', '')
    t = re.sub(r'^Перейти(?: к сообщению)?\s*$', '', t)
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
# Категории HAKUMO: золотой стиль + индивидуальные виджеты
# ═══════════════════════════════════════════════════════════════════════
CATEGORY_STYLES = {
    'mod': {
        'tag': '✦ HAKUMO · МОДЕРАЦИЯ',
        'glow_color': (235, 65, 85),
        'type': 'mod',
    },
    'automod': {
        'tag': '✦ HAKUMO · АВТОМОДЕРАЦИЯ',
        'glow_color': (255, 90, 45),
        'type': 'mod',
    },
    'message': {
        'tag': '✦ HAKUMO · АУДИТ СООБЩЕНИЙ',
        'glow_color': (0, 195, 255),
        'type': 'message',
    },
    'member': {
        'tag': '✦ HAKUMO · УЧАСТНИКИ СЕРВЕРА',
        'glow_color': (46, 213, 115),
        'type': 'member',
    },
    'welcome': {
        'tag': '✦ HAKUMO · ВРАТА СЕРВЕРА',
        'glow_color': (32, 227, 178),
        'type': 'member',
    },
    'voice': {
        'tag': '✦ HAKUMO · ГОЛОСОВАЯ АКТИВНОСТЬ',
        'glow_color': (26, 188, 156),
        'type': 'voice',
    },
    'role': {
        'tag': '✦ HAKUMO · ИЕРАРХИЯ РОЛЕЙ',
        'glow_color': (165, 94, 234),
        'type': 'role',
    },
    'channel': {
        'tag': '✦ HAKUMO · СТРУКТУРА КАНАЛОВ',
        'glow_color': (243, 156, 18),
        'type': 'channel',
    },
    'guild': {
        'tag': '✦ HAKUMO · НАСТРОЙКИ СЕРВЕРА',
        'glow_color': (212, 175, 55),
        'type': 'guild',
    },
    'сервер': {
        'tag': '✦ HAKUMO · НАСТРОЙКИ СЕРВЕРА',
        'glow_color': (212, 175, 55),
        'type': 'guild',
    },
    'invite': {
        'tag': '✦ HAKUMO · ПРИГЛАШЕНИЯ',
        'glow_color': (108, 92, 231),
        'type': 'invite',
    },
    'ticket': {
        'tag': '✦ HAKUMO · СЛУЖБА ПОДДЕРЖКИ',
        'glow_color': (84, 160, 255),
        'type': 'ticket',
    },
}


def _draw_stardust(img, W, H, pal=None):
    """Нарисовать мерцающие звёзды и частицы в цветах темы на фоне."""
    pal = pal or LOG_CARD_THEMES[DEFAULT_LOG_THEME]
    gold, bright = pal['gold'], pal['bright']
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    rnd = random.Random(42)
    for _ in range(65):
        sx = rnd.randint(18, W - 18)
        sy = rnd.randint(18, H - 18)
        size = rnd.choice([1, 1, 2, 2, 3])
        alpha = rnd.randint(50, 170)
        gold_tint = rnd.choice(list(pal['stars']))
        od.ellipse((sx, sy, sx + size, sy + size), fill=gold_tint + (alpha,))

    # 4-конечные звёздочки
    for _ in range(7):
        cx = rnd.randint(60, W - 60)
        cy = rnd.randint(30, min(240, H - 30))
        r = rnd.randint(3, 5)
        od.line([(cx - r, cy), (cx + r, cy)], fill=bright + (180,), width=1)
        od.line([(cx, cy - r), (cx, cy + r)], fill=bright + (180,), width=1)

    return Image.alpha_composite(img, overlay)


def _draw_category_widget(d, ctype, W, H, PAD, right_bound, pal=None):
    """Нарисовать уникальный графический виджет в шапке карточки."""
    pal = pal or LOG_CARD_THEMES[DEFAULT_LOG_THEME]
    gold, bright = pal['gold'], pal['bright']
    right_bound = int(right_bound)
    if ctype == 'voice':
        # Эквалайзер
        eq_x = right_bound - 190
        eq_y = 66
        heights = [14, 26, 42, 20, 48, 34, 22, 40, 52, 28, 36, 44]
        for i, h in enumerate(heights):
            x = eq_x + i * 15
            d.line([(x, eq_y - h // 2), (x, eq_y + h // 2)], fill=gold + (180,), width=3)
            d.ellipse((x - 1, eq_y - h // 2 - 2, x + 1, eq_y - h // 2), fill=bright + (230,))

    elif ctype == 'mod':
        # Предупреждающие диагональные насечки
        for i in range(6):
            x = right_bound - 190 + i * 30
            d.line([(x, 48), (x + 18, 76)], fill=gold + (140,), width=3)

    elif ctype == 'guild':
        # Алмазные декоративные угловые кристаллы
        for cx, cy in [(24, 24), (W - 24, 24), (24, H - 24), (W - 24, H - 24)]:
            d.polygon([(cx, cy - 6), (cx + 6, cy), (cx, cy + 6), (cx - 6, cy)], fill=bright + (230,))

    elif ctype == 'message':
        # Цифровая точечная матрица
        for gx in range(right_bound - 180, right_bound - 10, 20):
            for gy in range(48, 88, 14):
                d.rectangle((gx, gy, gx + 2, gy + 2), fill=gold + (110,))

    elif ctype == 'member':
        # Звёздные арки авроры
        d.arc((right_bound - 180, 20, right_bound - 10, 120), start=180, end=360, fill=gold + (90,), width=2)
        d.arc((right_bound - 150, 36, right_bound - 40, 110), start=180, end=360, fill=bright + (130,), width=2)

    elif ctype == 'role':
        # Шевроны иерархии
        rx = right_bound - 180
        for i in range(4):
            x = rx + i * 36
            d.line([(x, 48), (x + 12, 62), (x, 76)], fill=gold + (140,), width=3)

    elif ctype == 'channel':
        # Архитектурные направляющие
        d.line([(right_bound - 180, 50), (right_bound - 10, 50)], fill=gold + (100,), width=1)
        d.line([(right_bound - 180, 74), (right_bound - 10, 74)], fill=gold + (100,), width=1)
        for i in range(5):
            x = right_bound - 165 + i * 34
            d.line([(x, 44), (x, 80)], fill=gold + (70,), width=1)


_BG_CACHE = {}


def _load_celestial_bg(w, h, cat_tint=None, pal=None, use_asset=True):
    """Загружает фирменный звёздно-космический фон карточки логов.

    Приоритет: assets/hakumo_log_bg.png (фирменный тёмный фон с
    туманностью по краям и чистым центром под текст) -> assets/help_bg.png
    (старый фон) -> процедурный градиент темы (совсем запасной вариант).
    Картинка фирменная и окрашена в золото — при другой теме или своём
    акценте (use_asset=False) строим градиент из палитры темы, чтобы
    карточка не спорила сама с собой.
    """
    pal = pal or LOG_CARD_THEMES[DEFAULT_LOG_THEME]
    base = None
    for bg_name in ('hakumo_log_bg.png', 'help_bg.png') if use_asset else ():
        bg_path = os.path.join(ROOT, 'assets', bg_name)
        bg_path = os.path.join(ROOT, 'assets', bg_name)
        if not os.path.exists(bg_path):
            continue
        try:
            _ck = (bg_name, w, h)
            _cached = _BG_CACHE.get(_ck)
            if _cached is not None:
                base = _cached.copy()
                break
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
            _BG_CACHE[_ck] = base.copy()
            break
        except Exception as _ex:
            _log.debug("_load_celestial_bg(): подавлено: %s", _ex)
            continue
    if base is None:
        bg_top, bg_bot = pal['bg_top'], pal['bg_bot']
        grad = Image.new('RGB', (1, h))
        for y in range(h):
            t = y / max(1, h - 1)
            grad.putpixel((0, y), tuple(int(bg_top[i] + (bg_bot[i] - bg_top[i]) * t) for i in range(3)))
        base = grad.resize((w, h)).convert('RGBA')

    if cat_tint:
        glow = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse((-140, -160, 650, 420), fill=pal['gold'] + (34,))
        gd.ellipse((w - 550, -200, w + 180, 360), fill=cat_tint + (22,))
        glow = glow.filter(ImageFilter.GaussianBlur(85))
        base = Image.alpha_composite(base, glow)

    return base


def render_log_card(category, title, rows, color=0xC8922A, cat_name='',
                    guild_name='', time_str='', theme=None, accent=None,
                    fmt='jpeg'):
    """Нарисовать премиальную карточку лога в единой стилистике HAKUMO.

    theme — одна из LOG_CARD_THEMES ('hakumo' — исторический фирменный вид,
    ровно как было); accent ('#rrggbb'/int) заменяет золотую гамму своим
    цветом. Оба параметра пробрасывает бот из настроек панели
    (data/log_cards_<gid>.json, get_log_cards_cfg).
    """
    if not LOG_CARD_OK:
        return None
    try:
        W = 1440
        PAD = 52
        pal = _palette(theme, accent)
        gold, bright, soft = pal['gold'], pal['bright'], pal['soft']
        cell_border = gold + (65,)
        cat_key = str(category or 'guild').lower().strip()
        cstyle = CATEGORY_STYLES.get(cat_key, CATEGORY_STYLES.get('guild'))

        clean_rows = [(n, v) for n, v in (rows or []) if v not in (None, '')][:7]
        # «Ссылка»/«Перейти» на картинке не имеет смысла — ссылку не кликнуть
        clean_rows = [(n, v) for n, v in clean_rows
                      if _clean(n).strip().lower() not in ('ссылка', 'link')]
        header_h = 248
        row_h = 72
        footer_h = 82
        H = header_h + max(1, len(clean_rows)) * row_h + footer_h

        # 1. Полноценная фоновая звёздная иллюстрация с неоновым свечением
        cat_glow = cstyle['glow_color']
        # Фирменный PNG-фон золотой: берём его только для родной темы
        # без своего акцента — иначе строим градиент палитры темы.
        use_asset = (str(theme or DEFAULT_LOG_THEME).strip().lower() == DEFAULT_LOG_THEME
                     and not _ui_color(accent))
        img = _load_celestial_bg(W, H, cat_tint=cat_glow, pal=pal, use_asset=use_asset)
        d = ImageDraw.Draw(img)

        # 4. Двойная рамка по контуру карточки
        d.rectangle((10, 10, W - 10, H - 10), outline=gold + (90,), width=2)
        d.rectangle((16, 16, W - 16, H - 16), outline=soft + (40,), width=1)

        # Левая неоновая полоса
        d.rectangle((0, 0, 10, H), fill=gold + (255,))
        d.rectangle((10, 0, 14, H), fill=bright + (140,))

        # 5. Время (в правом верхнем углу шапки)
        time_clean = _clean(time_str)
        t_font = _font(22, True)
        time_w = d.textlength(time_clean, font=t_font) if time_clean else 0
        right_limit = W - PAD

        if time_clean:
            t_pad_w = time_w + 24
            t_box_x = W - PAD - t_pad_w
            d.rounded_rectangle((t_box_x, 48, W - PAD, 48 + 36), radius=10,
                                fill=(20, 28, 48, 220), outline=gold + (100,), width=1)
            d.text((t_box_x + 12, 54), time_clean, font=t_font, fill=bright)
            right_limit = t_box_x - 18

        # 6. Графический виджет категории в шапке (слева от плашки времени)
        _draw_category_widget(d, cstyle['type'], W, H, PAD, right_limit, pal)

        # 7. Фирменная иконка категории
        icon = _load_icon(cat_key, size=154)
        tx = PAD
        if icon is not None:
            # Тень под иконкой
            d.rounded_rectangle((PAD + 4, 46 + 4, PAD + 154 + 4, 46 + 154 + 4), radius=26,
                                fill=(0, 0, 0, 110))
            img.paste(icon, (PAD, 46), icon)
            d.rounded_rectangle((PAD, 46, PAD + 154, 46 + 154), radius=26,
                                outline=gold + (210,), width=3)
            tx = PAD + 154 + 32

        # 8. Бейдж категории в шапке (акцент + мягкий фон)
        cat_badge = cstyle.get('tag') or f'✦ HAKUMO · {str(cat_name or cat_key).upper()}'
        badge_font = _font(22, True)
        bw = d.textlength(cat_badge, font=badge_font) + 28
        bh = 38
        d.rounded_rectangle((tx, 48, tx + bw, 48 + bh), radius=12,
                            fill=(20, 28, 48, 220), outline=gold + (120,), width=1)
        d.text((tx + 14, 55), cat_badge, font=badge_font, fill=bright)

        # Заголовок события (крупный акцентный / белый)
        title_font = _font(44, True)
        title_txt = _ellipsize(d, _clean(title), title_font, W - tx - PAD - 20)
        d.text((tx, 98), title_txt, font=title_font, fill=C_TEXT_WHITE)

        # Разделитель шапки с градиентным акцентным штрихом
        sep_y = header_h - 22
        d.line([(PAD, sep_y), (W - PAD, sep_y)], fill=gold + (80,), width=1)
        d.line([(PAD, sep_y), (PAD + 240, sep_y)], fill=bright + (230,), width=2)

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
            box_outline = (235, 75, 85, 160) if is_reason else cell_border

            d.rounded_rectangle((PAD, y + 4, PAD + card_w, y + row_h - 8), radius=14,
                                fill=box_fill, outline=box_outline, width=1)

            # Левый акцентный штрих плашки (тема или рубин для причины)
            bar_color = (255, 80, 90, 255) if is_reason else gold + (255,)
            d.rounded_rectangle((PAD + 3, y + 10, PAD + 8, y + row_h - 14), radius=3,
                                fill=bar_color)

            # Название поля
            n_font = _font(22, True)
            d.text((PAD + 24, y + 20), _ellipsize(d, clean_n, n_font, name_col_w - 30),
                   font=n_font, fill=bright if not is_reason else (255, 145, 155, 255))

            # Разделитель
            d.text((PAD + name_col_w, y + 18), '›', font=_font(26, True), fill=gold + (170,))

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

        # 10. Фирменный футер с акцентным разделителем
        fy = H - footer_h + 16
        d.line([(PAD, fy), (W - PAD, fy)], fill=gold + (80,), width=1)

        f_txt = f"HAKUMO LOG · {str(cat_name or cat_key).upper()}"
        if guild_name:
            f_txt += f" · {_clean(guild_name)}"
        d.text((PAD, fy + 18), _ellipsize(d, f_txt, _font(22), W - PAD * 2 - 200),
               font=_font(22), fill=C_TEXT_DIM)

        brand = "✦ HAKUMO"
        bw = d.textlength(brand, font=_font(24, True))
        d.text((W - PAD - bw, fy + 16), brand, font=_font(24, True), fill=bright)

        buf = io.BytesIO()
        # JPEG вместо PNG: кодирование PNG жрало ~1.2 секунды НА КАЖДЫЙ лог
        # («логи медленные»), JPEG делает то же за ~5-20 мс и файл в 4 раза
        # меньше — Discord быстрее грузит. Качество 90 — артефактов нет.
        # fmt='png' остаётся для превью панели (эндпоинт .../preview.png).
        if str(fmt).lower() == 'png':
            img.convert('RGB').save(buf, 'PNG')
        else:
            img.convert('RGB').save(buf, 'JPEG', quality=90, optimize=False)
        return buf.getvalue()
    except Exception:
        return None
