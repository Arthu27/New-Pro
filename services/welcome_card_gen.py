# -*- coding: utf-8 -*-
"""Карточка приветствия/прощания: генератор + настройки оформления.

Карта рисуется ботом при входе/выходе участника (cogs/welcome_card.py).
Оформление настраивается в панели (Приветствие → карточка): авто-картинка
в одной из фирменных тем, своя картинка по URL или вовсе без картинки.

Темы — те же, что у баннеров правил, карточек апелляций и логов: золотая
Hakumo (исторический вид приветствия, 1:1), фиалковая, янтарная, океан, лес.
Хранилище — data/welcome_card.json (тот же файл, что читает ког).
"""
import io
import json
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from logger import get_logger

_log = get_logger('welcome_card_gen')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, 'assets', 'fonts')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

CFG_PATH = 'data/welcome_card.json'

W, H = 1000, 320
SS = 2

# ═══════════════════════════════════════════════════════════════════════
# Палитры карточек приветствия. 'hakumo' — историческое золото на полуночном
# небе (ровно тот вид, что был всегда: те же RGB-константы, что у кога).
# ═══════════════════════════════════════════════════════════════════════
WELCOME_THEMES = {
    'hakumo': {
        'bg_top': (10, 16, 30), 'bg_bot': (17, 28, 52),
        'accent': (212, 175, 55), 'accent_soft': (150, 122, 44),
        'ink': (236, 238, 244), 'dim': (150, 158, 175),
        'glow2': (245, 215, 110), 'grid': (52, 48, 78),
        'label': 'Hakumo Gold (фирменная)',
    },
    'violet': {
        'bg_top': (16, 14, 32), 'bg_bot': (26, 20, 50),
        'accent': (165, 140, 255), 'accent_soft': (120, 100, 210),
        'ink': (244, 244, 248), 'dim': (170, 170, 190),
        'glow2': (34, 211, 238), 'grid': (52, 48, 96),
        'label': 'Фиалковая ночь',
    },
    'night': {
        'bg_top': (12, 12, 16), 'bg_bot': (22, 20, 30),
        'accent': (240, 170, 70), 'accent_soft': (185, 125, 50),
        'ink': (245, 245, 243), 'dim': (168, 168, 172),
        'glow2': (244, 127, 60), 'grid': (44, 46, 56),
        'label': 'Ночная янтарь',
    },
    'ocean': {
        'bg_top': (8, 22, 30), 'bg_bot': (14, 36, 52),
        'accent': (34, 211, 238), 'accent_soft': (24, 150, 190),
        'ink': (240, 250, 252), 'dim': (150, 176, 186),
        'glow2': (14, 165, 233), 'grid': (22, 62, 80),
        'label': 'Океан',
    },
    'forest': {
        'bg_top': (10, 24, 18), 'bg_bot': (16, 38, 28),
        'accent': (52, 211, 153), 'accent_soft': (34, 150, 105),
        'ink': (242, 250, 245), 'dim': (152, 180, 160),
        'glow2': (132, 204, 22), 'grid': (24, 64, 46),
        'label': 'Лес',
    },
}
WELCOME_THEME_ORDER = tuple(WELCOME_THEMES)
DEFAULT_WELCOME_THEME = 'hakumo'

WELCOME_MODES = ('auto', 'url', 'file', 'off')
WELCOME_MODE_LABELS = {'auto': 'авто-картинка', 'url': 'своя по URL',
                       'file': 'свой файл фона', 'off': 'без картинки'}

# Каталог загруженных фонов карточек (панель грузит файл, ког рисует на нём)
BG_DIR = os.path.join('data', 'uploads', 'welcome')
BG_MAX_BYTES = 8 * 1024 * 1024          # 8 МБ достаточно для фонов 1000x320+
BG_MIME_EXT = {'image/png': '.png', 'image/jpeg': '.jpg',
               'image/gif': '.gif', 'image/webp': '.webp'}

_font_cache = {}


def _font(bold, size):
    key = (bold, size)
    f = _font_cache.get(key)
    if f is None:
        try:
            f = ImageFont.truetype(FONT_B if bold else FONT_R, size)
        except Exception:
            f = ImageFont.load_default()
        _font_cache[key] = f
    return f


# ── Доступ к конфигу (общий файл с когом cogs/welcome_card.py) ──────────
def _load_raw():
    try:
        if os.path.exists(CFG_PATH):
            with open(CFG_PATH, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
            return data if isinstance(data, dict) else {}
    except Exception as _ex:
        _log.debug('_load_raw(): %s', _ex)
    return {}


def _save_raw(data):
    os.makedirs('data', exist_ok=True)
    tmp = CFG_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, CFG_PATH)


def normalize_appearance(raw):
    """Оформление карточки приветствия с валидацией мусора."""
    raw = raw if isinstance(raw, dict) else {}
    mode = str(raw.get('mode') or '').strip().lower()
    theme = str(raw.get('theme') or '').strip().lower()
    url = str(raw.get('url') or '').strip()
    # Загруженный файл фона: только безопасное имя (basename, без путей)
    file_name = os.path.basename(str(raw.get('file') or '').strip())
    if not file_name or file_name in ('.', '..'):
        file_name = ''
    return {
        'mode': mode if mode in WELCOME_MODES else 'auto',
        'theme': theme if theme in WELCOME_THEMES else DEFAULT_WELCOME_THEME,
        'url': url[:500],
        'file': file_name[:80],
    }


def get_appearance(gid):
    """Оформление карточки сервера gid → нормализованный dict."""
    sec = _load_raw().get(str(gid))
    if isinstance(sec, dict):
        return normalize_appearance(sec.get('appearance'))
    return normalize_appearance(None)


def save_appearance(gid, raw):
    """Принять оформление из панели → нормализованный dict (письмо в файл)."""
    cfg = normalize_appearance(raw)
    data = _load_raw()
    sec = data.get(str(gid)) if isinstance(data.get(str(gid)), dict) else {}
    if not isinstance(sec, dict):
        sec = {}
    sec['appearance'] = cfg
    data[str(gid)] = sec
    _save_raw(data)
    return cfg


# ── Загруженный файл фона (режим 'file') ────────────────────────────────
def bg_path(file_name):
    """Безопасный путь к файлу фона внутри BG_DIR ('' → None)."""
    name = os.path.basename(str(file_name or ''))
    if not name or name in ('.', '..'):
        return None
    base = os.path.abspath(BG_DIR)
    full = os.path.abspath(os.path.join(base, name))
    return full if full.startswith(base + os.sep) else None


def load_bg_bytes(file_name):
    """bytes фона для рендера ('' / нет файла / не файл → None)."""
    path = bg_path(file_name)
    try:
        if path and os.path.isfile(path):
            with open(path, 'rb') as fp:
                return fp.read()
    except Exception as _ex:
        _log.debug('load_bg_bytes(): %s', _ex)
    return None


def resolve_image_url(url, max_bytes=None):
    """Скачать картинку по ссылке «как у пользователя» (в т.ч. Pinterest).

    Люди копируют ссылки из Pinterest и соцсетей, а там чаще всего СТРАНИЦА,
    а не файл: pin.it/…, pinterest.com/pin/123456/…. Раньше такую ссылку
    получал только Discord (embed.set_image) и показывал битую картинку.

    Теперь панель сама скачивает и понимает:
      • прямые ссылки на файл (i.pinimg.com/…jpg, любой сайт);
      • страницы Pinterest (pin.it, /pin/…) — из HTML берётся og:image;
      • любую страницу с og:image / twitter:image (VK, TG, сайты).

    Возвращает {'ok': True, 'data': bytes, 'direct_url': str, 'via': str}
    или {'ok': False, 'error': текст-подсказка для владельца}.
    """
    import re as _re
    import requests as _rq
    limit = int(max_bytes or BG_MAX_BYTES)
    u = str(url or '').strip()
    if not u:
        return {'ok': False, 'error': 'Ссылка пустая'}
    if not u.lower().startswith(('https://', 'http://')):
        return {'ok': False, 'error': 'Ссылка должна начинаться с https://'}
    low = u.lower()
    if any(h in low for h in ('//localhost', '//127.0.0.1', '//0.0.0.0', '//[::1]')):
        return {'ok': False, 'error': 'Адрес должен быть публичным'}
    headers = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/124.0 Safari/537.36'),
        'Accept': 'image/avif,image/webp,image/*,*/*;q=0.8',
    }

    def _download(target):
        try:
            r = _rq.get(target, headers=headers, timeout=(8, 15),
                        allow_redirects=True, stream=True)
        except _rq.exceptions.ConnectionError:
            return {'ok': False,
                    'error': 'Сайт недоступен (не отвечает). Проверь ссылку '
                             'или скачай файл и загрузи его в панель'}
        except _rq.exceptions.Timeout:
            return {'ok': False,
                    'error': 'Сайт отвечает слишком долго — попробуй позже '
                             'или загрузи файл напрямую'}
        except _rq.exceptions.RequestException as _e:
            return {'ok': False, 'error': f'Не удалось скачать: {_e}'[:160]}
        if r.status_code >= 400:
            return {'ok': False,
                    'error': f'Сайт ответил кодом {r.status_code} — ссылка недоступна'}
        ct = (r.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        buf = bytearray()
        for chunk in r.iter_content(65536):
            buf.extend(chunk)
            if len(buf) > limit:
                return {'ok': False,
                        'error': 'Картинка больше 8 МБ — сохраните поменьше'}
        return {'ok': True, 'data': bytes(buf), 'content_type': ct, 'url': str(r.url)}

    first = _download(u)
    if not first.get('ok') and 'кодом' in first.get('error', ''):
        return first   # сайт недоступен/404 — честно сказать об этом
    if first.get('ok') and first['content_type'].startswith('image/'):
        return {'ok': True, 'data': first['data'],
                'direct_url': first['url'], 'via': 'прямая ссылка'}
    # HTML-страница (Pinterest, VK, сайты): вытащить og:image / twitter:image
    html = ''
    if first.get('ok'):
        try:
            html = first['data'].decode('utf-8', 'ignore')
        except Exception:
            html = ''
    cand = None
    m = _re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:image(?::secure_url)?|twitter:image(?:src)?)["\'][^>]+content=["\']([^"\']+)["\']', html, _re.I)
    if not m:
        m = _re.search(r'content=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\'][^>]*(?:property|name)=["\'](?:og:image|twitter:image)["\']', html, _re.I)
    if m:
        cand = m.group(1).replace('&amp;', '&')
    if not cand:
        if 'pinterest' in low or 'pin.it' in low:
            return {'ok': False,
                    'error': 'Pinterest не отдал картинку. Откройте пин, '
                             'нажмите на изображение правой кнопкой → '
                             '«Копировать ссылку на изображение» (i.pinimg.com/…jpg) '
                             '— или пришлите ссылку на сам пин ещё раз позже'}
        return {'ok': False,
                'error': 'По ссылке страница, а не картинка. Нужна прямая '
                         'ссылка на изображение (.jpg/.png/.webp) или пин Pinterest'}
    second = _download(cand)
    if second.get('ok') and second['content_type'].startswith('image/'):
        return {'ok': True, 'data': second['data'],
                'direct_url': second['url'], 'via': 'страница → og:image'}
    if not second.get('ok') and 'кодом' in second.get('error', ''):
        return second
    return {'ok': False,
            'error': 'Нашёл на странице картинку, но скачать не смог — сайт закрыт от ботов. Скачайте файл и загрузите его в панель'}


def save_bg_file(gid, original_name, data):
    """Принять загрузку фона: валидация картинки → dict результата.

    Возвращает {'ok': True, 'appearance': normalized} или {'ok': False, 'error': str}.
    """
    if not data:
        return {'ok': False, 'error': 'Файл не передан'}
    if len(data) > BG_MAX_BYTES:
        return {'ok': False,
                'error': 'Файл больше 8 МБ — сожмите картинку'}
    try:
        probe = Image.open(io.BytesIO(data))
        probe.verify()
        fmt = (probe.format or '').upper()
    except Exception:
        return {'ok': False, 'error': 'Это не картинка (нужны PNG/JPEG/GIF/WebP)'}
    if fmt not in ('PNG', 'JPEG', 'GIF', 'WEBP'):
        return {'ok': False, 'error': 'Формат не поддержан: PNG/JPEG/GIF/WebP'}
    ext = {'PNG': '.png', 'JPEG': '.jpg', 'GIF': '.gif',
           'WEBP': '.webp'}[fmt]
    os.makedirs(BG_DIR, exist_ok=True)
    name = 'bg_%s%s' % (int(gid), ext)          # один фон на сервер
    # Чистим старые файлы этого сервера с другим расширением
    for old_ext in BG_MIME_EXT.values():
        old = os.path.join(BG_DIR, 'bg_%s%s' % (int(gid), old_ext))
        if old_ext != ext and os.path.exists(old):
            try:
                os.remove(old)
            except OSError as _ex:
                _log.debug('старый фон %s не удалён: %s', old, _ex)
    tmp = os.path.join(BG_DIR, '.' + name + '.tmp')
    with open(tmp, 'wb') as fp:
        fp.write(data)
    os.replace(tmp, os.path.join(BG_DIR, name))
    _log.info('фон welcome-card от панели: сервер %s, файл %s (%d байт)',
              gid, name, len(data))
    cur = get_appearance(gid)
    return {'ok': True, 'appearance': save_appearance(gid, {
        'mode': 'file', 'theme': cur['theme'], 'url': cur['url'],
        'file': name})}


# ── Аватарки ────────────────────────────────────────────────────────────
def _circle_avatar(img_bytes, size):
    av = Image.open(io.BytesIO(img_bytes)).convert('RGBA').resize(
        (size, size), Image.LANCZOS)
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    out.paste(av, (0, 0), mask)
    return out


def _letter_avatar(letter, size, pal):
    """Заглушка: буква в тёмном круге цвета темы."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bg = pal['bg_bot']
    d.ellipse([0, 0, size, size], fill=(bg[0], bg[1], bg[2], 255))
    f = _font(True, int(size * 0.44))
    d.text((size / 2, size / 2), (letter or '?').upper(), font=f,
           fill=pal['accent'], anchor='mm')
    return img


# ── Рендер карточки ─────────────────────────────────────────────────────
def _cover_bg(bg_bytes, tw, th):
    """Своя картинка как фон карточки: cover-обрезка под tw×th, чуть приглушена."""
    src = Image.open(io.BytesIO(bg_bytes)).convert('RGB')
    sw, sh = src.size
    if sw <= 0 or sh <= 0:
        return None
    scale = max(tw / sw, th / sh)
    src = src.resize((max(1, int(sw * scale + 0.5)),
                      max(1, int(sh * scale + 0.5))), Image.LANCZOS)
    left = (src.width - tw) // 2
    top = (src.height - th) // 2
    src = src.crop((left, top, left + tw, top + th))
    # Виньетка-затемнение: текст и рамка должны читаться на любом фоне
    veil = Image.new('RGB', (tw, th), (6, 8, 14))
    src = Image.blend(src, veil, 0.42)
    return src


def render_welcome_card(member_name, guild_name, count, avatar_bytes=None,
                        kind='welcome', theme=None, bg_bytes=None):
    """Карта приветствия/прощания → PNG bytes. Никогда не бросает наружу.

    bg_bytes — свой файл фона (режим 'file'): кладём его «cover» на холст
    вместо градиента темы; при ошибке молча откатываемся на градиент.
    """
    try:
        theme_key = str(theme or DEFAULT_WELCOME_THEME).strip().lower()
        pal = WELCOME_THEMES.get(theme_key, WELCOME_THEMES[DEFAULT_WELCOME_THEME])
        if kind not in ('welcome', 'goodbye'):
            kind = 'welcome'
        acc = pal['accent']
        soft = pal['accent_soft']

        def S(px):
            return px * SS

        img = Image.new('RGB', (W * SS, H * SS), pal['bg_top'])
        d = ImageDraw.Draw(img, 'RGBA')

        # 1. Фон: свой файл-фон (cover) или вертикальный градиент темы
        custom = None
        if bg_bytes:
            try:
                custom = _cover_bg(bg_bytes, W * SS, H * SS)
            except Exception:
                custom = None
        if custom is not None:
            img = custom
            d = ImageDraw.Draw(img, 'RGBA')
        else:
            for y in range(H * SS):
                t = y / max(1, H * SS - 1)
                d.line([(0, y), (W * SS, y)],
                       fill=tuple(int(pal['bg_top'][i] + (pal['bg_bot'][i] - pal['bg_top'][i]) * t)
                                  for i in range(3)))

        # 2. Мягкие свечения (справа сверху и слева снизу, цвета темы)
        rnd = random.Random(hash((theme_key, kind)) & 0x7fffffff)
        glow = Image.new('RGBA', img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse([W * SS - S(320), -S(190), W * SS + S(120), S(210)],
                   fill=acc + (70,))
        gd.ellipse([W * SS - S(210), -S(120), W * SS + S(40), S(150)],
                   fill=pal['glow2'] + (60,))
        gd.ellipse([-S(170), H * SS - S(150), S(130), H * SS + S(120)],
                   fill=soft + (75,))
        glow = glow.filter(ImageFilter.GaussianBlur(S(38)))
        img = Image.alpha_composite(img.convert('RGBA'), glow).convert('RGB')
        d = ImageDraw.Draw(img, 'RGBA')

        # 3. Тонкая сетка
        step = S(46)
        for x in range(0, W * SS, step):
            d.line([(x, 0), (x, H * SS)], fill=pal['grid'] + (45,),
                   width=max(1, S(1)))
        for y in range(0, H * SS, step):
            d.line([(0, y), (W * SS, y)], fill=pal['grid'] + (45,),
                   width=max(1, S(1)))

        # 4. Двойная рамка + угловые кронштейны
        d.rectangle([S(12), S(12), W * SS - S(12), H * SS - S(12)],
                    outline=acc, width=S(2))
        d.rectangle([S(20), S(20), W * SS - S(20), H * SS - S(20)],
                    outline=soft + (110,), width=S(1))
        cl = S(46)   # длина кронштейна
        for cx, cy, sx, sy in ((12, 12, 1, 1), (W - 12, 12, -1, 1),
                               (12, H - 12, 1, -1), (W - 12, H - 12, -1, -1)):
            x0, y0 = S(cx), S(cy)
            d.line([x0, y0, x0 + sx * cl, y0], fill=acc, width=max(S(2), 3))
            d.line([x0, y0, x0, y0 + sy * cl], fill=acc, width=max(S(2), 3))

        # 5. Аватар с двойным кольцом + искры
        av_size = S(208)
        ax, ay = S(58), (H * SS - av_size) // 2
        if avatar_bytes:
            try:
                av = _circle_avatar(avatar_bytes, av_size)
            except Exception:
                av = _letter_avatar((member_name or '?')[0], av_size, pal)
        else:
            av = _letter_avatar((member_name or '?')[0], av_size, pal)
        d.ellipse([ax - S(6), ay - S(6), ax + av_size + S(6), ay + av_size + S(6)],
                  outline=acc, width=S(3))
        d.ellipse([ax - S(12), ay - S(12), ax + av_size + S(12), ay + av_size + S(12)],
                  outline=soft + (120,), width=S(1))
        for sx, sy, sr in ((ax - S(18), ay + S(20), 3),
                           (ax + av_size + S(22), ay + av_size - S(30), 4),
                           (ax + av_size + S(14), ay + S(26), 2)):
            d.ellipse([sx - S(sr), sy - S(sr), sx + S(sr), sy + S(sr)],
                      fill=acc + (200,))
        img.paste(av, (ax, ay), av)
        d = ImageDraw.Draw(img, 'RGBA')

        # 6. Текст
        tx = ax + av_size + S(56)
        if kind == 'welcome':
            title, title_color = 'ДОБРО ПОЖАЛОВАТЬ', acc
            try:
                sub = f'ты {int(count)}-й участник сервера'
            except Exception:
                sub = 'новый участник сервера'
        else:
            title, title_color = 'ДО СВИДАНИЯ', tuple(
                max(60, c - 36) for c in pal['ink'])
            try:
                sub = f'нас стало {int(count)} участников'
            except Exception:
                sub = 'участник покинул сервер'

        d.text((tx, S(56)), title, font=_font(True, S(30)), fill=title_color)
        name = str(member_name or 'Участник')[:26]
        d.text((tx, S(100)), name, font=_font(True, S(46)), fill=pal['ink'])
        d.line([tx, S(168), tx + S(420), S(168)], fill=acc + (160,), width=S(2))
        d.text((tx, S(186)), sub, font=_font(False, S(22)), fill=pal['dim'])
        gname = str(guild_name or '')[:44]
        d.text((tx, S(224)), gname, font=_font(False, S(19)), fill=pal['dim'])

        # 7. Футер: бренд слева-снизу в углу, дата справа
        f_foot = _font(True, S(15))
        d.text((S(34), H * SS - S(34)), '✦ HAKUMO',
               font=f_foot, fill=soft, anchor='ls')
        from datetime import datetime as _dt
        dt = _dt.now().strftime('%d.%m.%Y')
        d.text((W * SS - S(34), H * SS - S(34)), dt,
               font=_font(False, S(15)), fill=pal['dim'], anchor='rs')

        img = img.resize((W, H), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    except Exception:
        # Последняя линия обороны: минимальная читаемая карта.
        img = Image.new('RGB', (W, H), (16, 22, 38))
        d = ImageDraw.Draw(img)
        f = _font(True, 42)
        d.text((40, 40), 'Добро пожаловать!' if kind == 'welcome' else 'До свидания',
               font=f, fill=(212, 175, 55))
        d.text((40, 110), str(member_name or 'Участник')[:30], font=f,
               fill=(236, 238, 244))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()


def welcome_card_filename(kind):
    return f'hakumo_{kind or "welcome"}.png'
