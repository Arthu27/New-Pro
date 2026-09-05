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
    'sakura': {'gold': (255, 130, 190), 'bright': (255, 190, 225),
               'soft': (205, 95, 155), 'dim': (140, 65, 105),
               'bg_top': (26, 12, 22), 'bg_bot': (44, 20, 36),
               'stars': ((255, 130, 190), (255, 200, 230), (255, 255, 255)),
               'label': 'Сакура'},
    'crimson': {'gold': (255, 75, 85), 'bright': (255, 150, 155),
                'soft': (200, 50, 60), 'dim': (135, 35, 42),
                'bg_top': (24, 8, 12), 'bg_bot': (40, 14, 20),
                'stars': ((255, 75, 85), (255, 190, 120), (255, 255, 255)),
                'label': 'Багровый неон'},
    'steel': {'gold': (170, 190, 215), 'bright': (225, 235, 248),
              'soft': (120, 140, 165), 'dim': (80, 95, 115),
              'bg_top': (13, 16, 22), 'bg_bot': (24, 30, 40),
              'stars': ((170, 190, 215), (225, 235, 248), (255, 255, 255)),
              'label': 'Сталь'},
    'aurora': {'gold': (95, 235, 210), 'bright': (175, 255, 240),
               'soft': (70, 180, 165), 'dim': (48, 120, 112),
               'bg_top': (8, 18, 26), 'bg_bot': (20, 30, 52),
               'stars': ((95, 235, 210), (170, 160, 255), (255, 255, 255)),
               'label': 'Аврора'},
}

# «Разными образами» (заказ владельца): каждой категории логов — свой образ
# по умолчанию. Владелец может перекрыть любую в панели (Логи → оформление).
DEFAULT_THEME_BY_CAT = {
    'mod': 'hakumo', 'automod': 'crimson', 'punish': 'crimson', 'message': 'ocean',
    'voice': 'violet', 'member': 'forest', 'nick': 'sakura',
    'role': 'aurora', 'channel': 'steel', 'invite': 'aurora',
    'сервер': 'hakumo', 'guild': 'hakumo', 'ticket': 'ocean',
    'proof': 'steel', 'welcome': 'sakura',
}
LOG_CARD_THEME_ORDER = tuple(LOG_CARD_THEMES)
DEFAULT_LOG_THEME = 'hakumo'

# Форма плашек поверх фото: стекло читается на любом фоне.
CARD_FORMS = {
    'glass': 'Стекло',
    'rounded': 'Мягкая',
    'pill': 'Пилюля',
    'sharp': 'Прямая',
}
DEFAULT_FORM = 'glass'
DEFAULT_FORM_RGB = (12, 16, 28)


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


def _valid_theme_by_cat(raw):
    """dict категория→тема: ключи из CATEGORY_STYLES, значения из тем."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        k = str(k).strip().lower()
        v = str(v).strip().lower()
        if k in CATEGORY_STYLES and v in LOG_CARD_THEMES:
            out[k] = v
    return out


def _valid_bg_url(raw):
    """Свой фон-фото карточек: только http(s), без локальных адресов."""
    u = str(raw or '').strip()
    if not u.startswith(('https://', 'http://')):
        return ''
    if any(bad in u.lower() for bad in ('//localhost', '//127.0.0.1',
                                        '//0.0.0.0', '//[::1]')):
        return ''
    return u


def _valid_bg_url_by_cat(raw):
    """dict категория → URL фона. Пустые/мусорные ссылки выкидываем."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        k = str(k).strip().lower()
        u = _valid_bg_url(v)
        if k in CATEGORY_STYLES and u:
            out[k] = u
    return out


def bg_url_for_cat(cfg, cat):
    """Фон этой категории: свой URL, иначе общий bg_url сервера."""
    cfg = cfg if isinstance(cfg, dict) else {}
    cat = str(cat or '').strip().lower()
    by = cfg.get('bg_url_by_cat') or {}
    return str(by.get(cat) or cfg.get('bg_url') or '')


def _valid_form(raw):
    s = str(raw or '').strip().lower()
    return s if s in CARD_FORMS else DEFAULT_FORM


def get_log_cards_cfg(gid):
    """{'enabled': bool, 'theme': str, 'accent': '', 'bg_url': '',
    'theme_by_cat': {}, 'bg_url_by_cat': {}, 'form': str, 'form_color': ''}."""
    cfg = {'enabled': True, 'theme': DEFAULT_LOG_THEME, 'accent': '',
           'bg_url': '', 'theme_by_cat': dict(DEFAULT_THEME_BY_CAT),
           'bg_url_by_cat': {}, 'form': DEFAULT_FORM, 'form_color': ''}
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
                if 'theme_by_cat' in raw:
                    cfg['theme_by_cat'] = _valid_theme_by_cat(raw.get('theme_by_cat'))
                cfg['bg_url'] = _valid_bg_url(raw.get('bg_url'))
                cfg['bg_url_by_cat'] = _valid_bg_url_by_cat(raw.get('bg_url_by_cat'))
                if 'form' in raw:
                    cfg['form'] = _valid_form(raw.get('form'))
                acc_f = str(raw.get('form_color') or '').strip().lstrip('#')
                if not acc_f or _ui_color(acc_f):
                    cfg['form_color'] = acc_f
    except Exception as _ex:
        _log.debug('get_log_cards_cfg(): %s', _ex)
    return cfg


def save_log_cards_cfg(gid, data):
    """Записать настройки после валидации. Возвращает нормализованный dict.

    Поля, которых нет в data, не затираем (merge-on-save): POST оформления
    логов без bg_url_by_cat не должен сносить URL по категориям, а POST
    «Логи сервера» с одним URL категории не должен сносить тему.
    """
    if not isinstance(data, dict):
        data = {}
    prev = {}
    try:
        path = log_cards_cfg_path(gid)
        if os.path.exists(path):
            import json as _json
            with open(path, 'r', encoding='utf-8') as fp:
                raw = _json.load(fp)
            if isinstance(raw, dict):
                prev = raw
    except Exception as _ex:
        _log.debug('save_log_cards_cfg prev: %s', _ex)
        prev = {}
    _theme_src = (data.get('theme_by_cat') if 'theme_by_cat' in data
                  else DEFAULT_THEME_BY_CAT)
    _bg = data.get('bg_url') if 'bg_url' in data else prev.get('bg_url')
    _by = (data.get('bg_url_by_cat') if 'bg_url_by_cat' in data
           else prev.get('bg_url_by_cat'))
    _form = data.get('form') if 'form' in data else prev.get('form')
    _fc = data.get('form_color') if 'form_color' in data else prev.get('form_color')
    cfg = {
        'enabled': bool(data.get('enabled', True if 'enabled' not in prev
                                 else prev.get('enabled', True))),
        'theme': DEFAULT_LOG_THEME,
        'accent': '',
        'bg_url': _valid_bg_url(_bg),
        'theme_by_cat': _valid_theme_by_cat(_theme_src),
        'bg_url_by_cat': _valid_bg_url_by_cat(_by),
        'form': _valid_form(_form),
        'form_color': '',
    }
    theme = str(data.get('theme') or prev.get('theme') or '').strip().lower()
    if theme in LOG_CARD_THEMES:
        cfg['theme'] = theme
    acc = str(data.get('accent') if 'accent' in data else prev.get('accent') or '')
    acc = acc.strip().lstrip('#')
    if _ui_color(acc):
        cfg['accent'] = acc
    fc = str(_fc or '').strip().lstrip('#')
    if _ui_color(fc):
        cfg['form_color'] = fc
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
    'nick': {
        'tag': '✦ HAKUMO · НИКНЕЙМЫ',
        'glow_color': (185, 130, 255),
        'type': 'message',
    },
    'proof': {
        'tag': '✦ HAKUMO · ДОКАЗАТЕЛЬСТВА',
        'glow_color': (200, 120, 255),
        'type': 'member',
    },
    'punish': {
        'tag': '✦ HAKUMO · НАКАЗАНИЯ',
        'glow_color': (255, 110, 60),
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


def _photo_bg(w, h, data):
    """Фото как фон: cover-масштаб, почти без затемнения —
    читаемость на плашках, не на мытье всего кадра."""
    ph = Image.open(io.BytesIO(data)).convert('RGB')
    scale = max(w / ph.width, h / ph.height)
    nw = max(w, int(ph.width * scale + 0.5))
    nh = max(h, int(ph.height * scale + 0.5))
    ph = ph.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    ph = ph.crop((left, top, left + w, top + h)).convert('RGBA')
    vig = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vig)
    vd.rectangle([0, 0, w, h], fill=(6, 8, 14, 28))
    band = max(24, h // 16)
    for i in range(band):
        a = int(64 * (1 - i / band))
        vd.line([(0, i), (w, i)], fill=(0, 0, 0, a))
        vd.line([(0, h - 1 - i), (w, h - 1 - i)], fill=(0, 0, 0, a))
    ph.alpha_composite(vig)
    return ph


def _form_fill(raw):
    return _ui_color(raw) or DEFAULT_FORM_RGB


def _ink_on(rgb):
    y = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    if y < 155:
        return (250, 252, 255), (168, 178, 196)
    return (18, 22, 30), (78, 86, 98)


def _form_radius(form, h):
    if form == 'pill':
        return max(10, int(h // 2))
    if form == 'sharp':
        return 5
    if form == 'rounded':
        return 16
    return 24


def _form_alpha(form):
    return {'glass': 168, 'rounded': 182, 'pill': 192, 'sharp': 208}.get(form, 168)


def _frost_plate(img, box, radius, fill_rgb, alpha, outline=None):
    """Матовое стекло: блюр куска фона + цвет формы. Читается на любом фото."""
    x0, y0, x1, y1 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
    x0 = max(0, min(x0, img.width - 2))
    y0 = max(0, min(y0, img.height - 2))
    x1 = max(x0 + 4, min(x1, img.width))
    y1 = max(y0 + 4, min(y1, img.height))
    w, h = x1 - x0, y1 - y0
    crop = img.crop((x0, y0, x1, y1)).convert('RGBA')
    plate = Image.alpha_composite(
        crop.filter(ImageFilter.GaussianBlur(12)),
        Image.new('RGBA', (w, h), fill_rgb + (int(alpha),)),
    )
    rad = max(2, min(int(radius), w // 2, h // 2))
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, w - 1, h - 1), radius=rad, fill=255)
    img.paste(plate, (x0, y0), mask)
    d = ImageDraw.Draw(img)
    if outline:
        d.rounded_rectangle((x0, y0, x1 - 1, y1 - 1), radius=rad,
                            outline=outline, width=1)


def _og_image_from_html(html, base=''):
    """og:image / twitter:image со страницы (pin.it и т.п.)."""
    html = str(html or '')
    m = re.search(
        r'<meta[^>]+(?:property|name)=["\']'
        r'(?:og:image(?::secure_url)?|twitter:image(?:src)?)["\']'
        r'[^>]+content=["\']([^"\']+)["\']', html, re.I)
    if not m:
        m = re.search(
            r'content=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']'
            r'[^>]*(?:property|name)=["\']'
            r'(?:og:image|twitter:image)["\']', html, re.I)
    if not m:
        return None
    cand = m.group(1).replace('&amp;', '&').strip()
    if not cand:
        return None
    if base:
        from urllib.parse import urljoin
        return urljoin(str(base), cand)
    return cand


def _looks_like_image(head):
    if not head or len(head) < 8:
        return False
    png = bytes([0x89]) + b'PNG' + bytes([0x0D, 0x0A, 0x1A, 0x0A])
    if head[:8] == png:
        return True
    if head[:3] == bytes([0xFF, 0xD8, 0xFF]):
        return True
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return True
    if head[:6] in (b'GIF87a', b'GIF89a'):
        return True
    return False


def fetch_bg_direct(url, max_bytes=8 * 1024 * 1024):
    """Скачать фон-фото без кэша (панель-превью). None — не вышло.

    Страница (pin.it / соцсеть) — вытаскиваем og:image и качаем её.
    """
    import requests as _rq
    url = str(url or '').strip()
    if not url.lower().startswith(('https://', 'http://')):
        return None
    try:
        r = _rq.get(url, timeout=(6, 15), allow_redirects=True,
                    headers={'User-Agent': 'Mozilla/5.0 (compatible; HakumoBot)'})
        if r.status_code >= 400:
            _log.debug('лог-фон: хост ответил %s', r.status_code)
            return None
        data = r.content or b''
        if len(data) > max_bytes:
            _log.debug('лог-фон: файл больше 8 МБ')
            return None
        ctype = (r.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        if ctype.startswith('text/html') or not _looks_like_image(data):
            og = _og_image_from_html(r.text, str(r.url or url))
            if not og:
                return None
            r2 = _rq.get(og, timeout=(6, 15), allow_redirects=True,
                         headers={'User-Agent': 'Mozilla/5.0 (compatible; HakumoBot)'})
            if r2.status_code >= 400:
                return None
            data = r2.content or b''
            if len(data) > max_bytes:
                return None
        Image.open(io.BytesIO(data)).verify()
        return data
    except Exception as _ex:
        _log.debug('лог-фон: %s', _ex)
        return None


_PHOTO_BG_CACHE = {}


def get_bg_bytes_sync(url, ttl=300):
    """Фон-фото для карточек логов с кэшем 5 минут (бот качает на каждый
    лог — без кэша дёргать хост нельзя). None — остаётся звёздный фон."""
    import time as _t
    url = str(url or '').strip()
    if not url.lower().startswith(('https://', 'http://')):
        return None
    now = _t.time()
    hit = _PHOTO_BG_CACHE.get(url)
    if hit and hit[0] and now - hit[1] < ttl:
        return hit[0]
    data = fetch_bg_direct(url)
    if data:
        _PHOTO_BG_CACHE[url] = (data, now)
        if len(_PHOTO_BG_CACHE) > 32:
            oldest = min(_PHOTO_BG_CACHE.items(), key=lambda kv: kv[1][1])
            _PHOTO_BG_CACHE.pop(oldest[0], None)
    return data


def render_log_card(category, title, rows, color=0xC8922A, cat_name='',
                    guild_name='', time_str='', theme=None, accent=None,
                    fmt='jpeg', bg_bytes=None, form=None, form_color=None):
    """Нарисовать карточку лога: фото на весь кадр, поверх — стеклянные
    плашки сообщений (форма и цвет задаются из панели).

    theme / accent — палитра темы; form — glass|rounded|pill|sharp;
    form_color — hex заливки плашек (пусто = тёмное стекло).
    bg_bytes — своё фото задним фоном (bg_url; качает cogs/logs.py).
    """
    if not LOG_CARD_OK:
        return None
    try:
        W = 1440
        PAD = 48
        pal = _palette(theme, accent)
        gold, bright, _soft = pal['gold'], pal['bright'], pal['soft']
        cat_key = str(category or 'guild').lower().strip()
        cstyle = CATEGORY_STYLES.get(cat_key, CATEGORY_STYLES.get('guild'))
        form = _valid_form(form)
        fill_rgb = _form_fill(form_color)
        ink, ink_dim = _ink_on(fill_rgb)
        alpha = _form_alpha(form)
        has_photo = bool(bg_bytes)

        clean_rows = [(n, v) for n, v in (rows or []) if v not in (None, '')][:7]
        # «Ссылка»/«Перейти» на картинке не имеет смысла — ссылку не кликнуть
        clean_rows = [(n, v) for n, v in clean_rows
                      if _clean(n).strip().lower() not in ('ссылка', 'link')]
        header_inner = 126
        header_top = 36
        row_h = 70
        footer_h = 72
        gap = 12
        H = header_top + header_inner + gap + max(1, len(clean_rows)) * row_h + footer_h

        cat_glow = cstyle['glow_color']
        use_asset = (str(theme or DEFAULT_LOG_THEME).strip().lower() == DEFAULT_LOG_THEME
                     and not _ui_color(accent))
        if bg_bytes:
            try:
                img = _photo_bg(W, H, bg_bytes)
            except Exception as _ex:
                _log.debug('лог-карточка: свой фон не открылся: %s', _ex)
                img = _load_celestial_bg(W, H, cat_tint=cat_glow, pal=pal,
                                         use_asset=use_asset)
                has_photo = False
        else:
            img = _load_celestial_bg(W, H, cat_tint=cat_glow, pal=pal,
                                     use_asset=use_asset)
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        if not has_photo:
            img = _draw_stardust(img, W, H, pal)

        hx0, hy0 = PAD, header_top
        hx1, hy1 = W - PAD, header_top + header_inner
        head_r = _form_radius(form, header_inner)
        outline = gold + (90,)
        _frost_plate(img, (hx0, hy0, hx1, hy1), head_r, fill_rgb, alpha, outline)
        d = ImageDraw.Draw(img)

        time_clean = _clean(time_str)
        t_font = _font(20, True)
        if time_clean:
            tw = d.textlength(time_clean, font=t_font)
            d.text((hx1 - 22 - tw, hy0 + 18), time_clean, font=t_font, fill=ink_dim)

        cat_badge = cstyle.get('tag') or f'HAKUMO · {str(cat_name or cat_key).upper()}'
        badge_font = _font(20, True)
        d.text((hx0 + 22, hy0 + 18),
               _ellipsize(d, cat_badge, badge_font, W - PAD * 2 - 220),
               font=badge_font, fill=bright)

        title_font = _font(40, True)
        title_txt = _ellipsize(d, _clean(title), title_font, W - PAD * 2 - 48)
        d.text((hx0 + 22, hy0 + 58), title_txt, font=title_font, fill=ink)

        y = hy1 + gap
        card_w = W - PAD * 2
        name_col_w = 268
        plate_r = _form_radius(form, row_h - 8)

        for name, value in clean_rows:
            clean_n = _clean(name).upper()
            clean_v = _clean(value)
            is_reason = clean_n in ('ПРИЧИНА', 'REASON', 'ПРИЧИНА НАКАЗАНИЯ')
            tint = _mix(fill_rgb, (160, 30, 40), 0.38) if is_reason else fill_rgb
            ol = ((235, 75, 85, 150) if is_reason else outline)
            _frost_plate(img, (PAD, y + 4, PAD + card_w, y + row_h - 6),
                         plate_r, tint, min(230, alpha + (18 if is_reason else 0)), ol)
            d = ImageDraw.Draw(img)
            bar = (255, 80, 90, 255) if is_reason else gold + (255,)
            d.rounded_rectangle((PAD + 10, y + 16, PAD + 16, y + row_h - 18),
                                radius=3, fill=bar)
            n_font = _font(20, True)
            n_fill = (255, 145, 155) if is_reason else bright
            d.text((PAD + 28, y + 20),
                   _ellipsize(d, clean_n, n_font, name_col_w - 24),
                   font=n_font, fill=n_fill)
            d.text((PAD + name_col_w, y + 18), '›', font=_font(24, True),
                   fill=gold + (170,))
            v_font = _font(24, True) if is_reason else _font(24, False)
            val_x = PAD + name_col_w + 22
            max_val_w = W - PAD - val_x - 20
            val_txt = _ellipsize(d, clean_v, v_font, max_val_w)
            val_color = (255, 235, 235) if is_reason else ink
            d.text((val_x, y + 18), val_txt, font=v_font, fill=val_color)
            y += row_h

        if not clean_rows:
            _frost_plate(img, (PAD, y + 4, PAD + card_w, y + row_h - 6),
                         plate_r, fill_rgb, alpha, outline)
            d = ImageDraw.Draw(img)
            d.text((PAD + 24, y + 20), 'Нет дополнительных параметров',
                   font=_font(24), fill=ink_dim)

        fy = H - footer_h + 10
        foot_r = _form_radius(form, 44)
        _frost_plate(img, (PAD, fy, W - PAD, fy + 44), foot_r, fill_rgb,
                     max(120, alpha - 20), outline)
        d = ImageDraw.Draw(img)
        f_txt = f"HAKUMO LOG · {str(cat_name or cat_key).upper()}"
        if guild_name:
            f_txt += f" · {_clean(guild_name)}"
        d.text((PAD + 20, fy + 10),
               _ellipsize(d, f_txt, _font(20), W - PAD * 2 - 220),
               font=_font(20), fill=ink_dim)
        brand = "HAKUMO"
        bw = d.textlength(brand, font=_font(20, True))
        d.text((W - PAD - 20 - bw, fy + 10), brand, font=_font(20, True), fill=bright)

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
