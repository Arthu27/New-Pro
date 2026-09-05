# -*- coding: utf-8 -*-
"""Фирменная карточка апелляции для лог-канала (PIL, как баннеры правил).

Карточка прикладывается к эмбеду при подаче апелляции (cogs/appeals.py).
Оформление настраивается в панели (Апелляции → оформление): авто-картинка
в одной из тем, своя картинка по URL или вовсе без картинки.
"""
import io
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, 'assets', 'fonts')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

W, H = 1200, 420
SS = 2

# Те же фирменные темы, что у баннеров правил: (база, свечение 1, свечение 2,
# сетка, текст, под-текст). 'hakumo' — золото в тон карточкам логов.
APPEAL_THEMES = {
    'hakumo': ((10, 16, 30), (212, 175, 55), (245, 215, 110), (52, 48, 78), (242, 245, 252), (165, 172, 200)),
    'violet': ((16, 14, 32), (99, 102, 241), (34, 211, 238), (52, 48, 96), (244, 244, 248), (170, 170, 190)),
    'night': ((12, 14, 18), (240, 180, 60), (244, 127, 60), (44, 46, 56), (245, 245, 243), (168, 168, 172)),
    'ocean': ((8, 22, 30), (14, 165, 233), (34, 211, 238), (22, 62, 80), (240, 250, 252), (150, 176, 186)),
    'forest': ((10, 24, 18), (34, 197, 94), (132, 204, 22), (24, 64, 46), (242, 250, 245), (152, 180, 160)),
}
APPEAL_THEME_ORDER = tuple(APPEAL_THEMES)
DEFAULT_APPEAL_THEME = 'violet'

APPEAL_MODES = ('auto', 'url', 'off')
APPEAL_MODE_LABELS = {'auto': 'авто-картинка', 'url': 'своя по URL', 'off': 'без картинки'}


def _font(bold, sz):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT_R, sz)
    except Exception:
        return ImageFont.load_default()


def _wrap(draw, text, f, max_w):
    lines = []
    for raw in str(text or '').split('\n'):
        words = raw.split()
        if not words:
            lines.append('')
            continue
        line = words[0]
        for w in words[1:]:
            probe = line + ' ' + w
            bb = draw.textbbox((0, 0), probe, font=f)
            if bb[2] - bb[0] <= max_w:
                line = probe
            else:
                lines.append(line)
                line = w
        lines.append(line)
    return lines


def _fit(draw, text, bold, start, max_w, min_sz=14):
    f = _font(bold, start)
    while True:
        bb = draw.textbbox((0, 0), text, font=f)
        if bb[2] - bb[0] <= max_w or f.size <= min_sz:
            return f
        f = _font(bold, f.size - 1)


def normalize_appearance(raw):
    """Настройки оформления карточки апелляции с валидацией мусора."""
    raw = raw if isinstance(raw, dict) else {}
    mode = str(raw.get('mode') or '').strip().lower()
    theme = str(raw.get('theme') or '').strip().lower()
    url = str(raw.get('url') or '').strip()
    return {
        'mode': mode if mode in APPEAL_MODES else 'auto',
        'theme': theme if theme in APPEAL_THEMES else DEFAULT_APPEAL_THEME,
        'url': url[:500],
    }


# ── Своя картинка по URL: скачивание и «медиа-план» карточки ────────────────
# Владелец (2026-09-05): «своя url не работает и не показывает картинку» +
# «отправлять туда фото, чтобы качество не портилось». Discord-эмбед по
# внешней ссылке пережимает картинку и молча пустеет, если хост отдаёт
# ошибку/банит хотлинк (imgur). Поэтому бот СКАЧИВАЕТ оригинал и
# прикрепляет ФАЙЛОМ (attachment://) — байты едут как есть, без пережатия.
MAX_REMOTE_IMAGE_BYTES = 8 * 1024 * 1024   # лимит вложения Discord — 8 МиБ
_IMAGE_EXTS = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
               '.gif': 'image/gif', '.webp': 'image/webp'}


def validate_image_url(url):
    """Проверка ссылки на картинку. Возвращает (ok, причина).

    Только https, публичный хост (без localhost/приватных адресов),
    путь с картинным расширением ИЛИ без расширения (хост может отдать
    image/* контентом — решит загрузка).
    """
    from urllib.parse import urlparse
    u = str(url or '').strip()
    low = u.lower()
    if not u:
        return False, 'пустая ссылка'
    if not low.startswith('https://'):
        return False, 'только https://'
    if any(bad in low for bad in ('localhost', '127.0.0.1', '0.0.0.0',
                                  '[::1]', '10.', '192.168.', '169.254.')):
        return False, 'адрес должен быть публичным'
    try:
        p = urlparse(u)
    except ValueError:
        return False, 'не похоже на ссылку'
    if not p.netloc:
        return False, 'в ссылке нет хоста'
    ext = os.path.splitext(p.path or '')[1].lower()
    if ext and ext not in _IMAGE_EXTS:
        # Страницы-пины (pin.it/7jxEf3HAx, pinterest.com/pin/123/) —
        # валидны: fetch_remote_image вытащит og:image со страницы
        # (владелец 2026-09-05: «вот вам например pin.it/…»).
        low_host = (p.netloc or '').lower()
        low_path = (p.path or '').lower()
        if not ('pin.it' in low_host or 'pinterest.' in low_host
                and '/pin/' in low_path):
            return False, f'«{ext}» — не картинка (нужны png/jpg/gif/webp ' \
                          'или ссылка на пин Pinterest)'
    return True, ''


def _host_check(url):
    """Анти-SSRF: (публичный_ли_хост, причина_отказа).

    Домен не резолвится и адреса приватные — разные причины, чтобы
    владелец понимал, что именно не так со ссылкой.
    """
    from urllib.parse import urlparse
    import ipaddress as _ipa
    import socket as _sock
    try:
        host = (urlparse(str(url)).hostname or '').strip()
    except ValueError:
        return False, 'в ссылке нет адреса'
    if not host:
        return False, 'в ссылке нет адреса'
    try:
        infos = _sock.getaddrinfo(host, 443, proto=_sock.IPPROTO_TCP)
    except OSError:
        return False, 'домен не найден — проверь ссылку'
    for info in infos or ():
        addr = info[4][0]
        try:
            ip = _ipa.ip_address(addr)
        except ValueError:
            return False, 'домен отдал странный адрес'
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False, 'адрес ведёт в приватную сеть'
    return True, '' 


def _og_image_of(html):
    """Достать og:image / twitter:image из HTML страницы (или None)."""
    import re as _re
    html = str(html or '')
    m = _re.search(
        r'<meta[^>]+(?:property|name)=["\']'
        r'(?:og:image(?::secure_url)?|twitter:image(?:src)?)["\']'
        r'[^>]+content=["\']([^"\']+)["\']', html, _re.I)
    if not m:
        m = _re.search(
            r'content=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']'
            r'[^>]*(?:property|name)=["\']'
            r'(?:og:image|twitter:image)["\']', html, _re.I)
    if not m:
        return None
    from urllib.parse import urljoin
    cand = m.group(1).replace('&amp;', '&').strip()
    return urljoin(str(url), cand) if 'url' in dir() else cand


def _sniff_image_ext(head):
    """Расширение по магическим байтам (контент решает, не URL)."""
    png = bytes([0x89]) + b"PNG" + bytes([0x0D, 0x0A, 0x1A, 0x0A])
    if head[:8] == png:
        return ".png"
    if head[:3] == bytes([0xFF, 0xD8, 0xFF]):
        return ".jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return None


async def fetch_remote_image(url, timeout=12):
    """Скачать картинку по URL. Возвращает (bytes, filename) или (None, причина).

    Никогда не бросает наружу. Проверяем размер и content-type: в файл
    уходит только настоящая картинка в пределах лимита вложения.
    """
    ok, why = validate_image_url(url)
    if not ok:
        return None, why
    import asyncio as _aio
    try:
        public, why = await _aio.to_thread(_host_check, str(url).strip())
    except Exception:                     # noqa: BLE001
        public, why = False, 'адрес недоступен'
    if not public:
        return None, why
    try:
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as ses:
            async with ses.get(str(url).strip(), timeout=None) as resp:
                if resp.status != 200:
                    return None, f'хост ответил {resp.status}'
                ctype = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
                if ctype and not ctype.startswith('image/'):
                    # Страница (pin.it, соцсети, сайты)? Пробуем вытащить
                    # og:image / twitter:image — люди копируют ссылки-СТРАНИЦЫ
                    # (владелец 2026-09-05: «вот вам например pin.it/…»).
                    page = await resp.text(errors='ignore')
                    cand = _og_image_of(page)
                    if not cand:
                        return None, 'по ссылке страница, а не картинка'
                    async with ses.get(cand, timeout=None) as r2:
                        if r2.status != 200:
                            return None, f'картинка на странице недоступна ({r2.status})'
                        ctype = (r2.headers.get('Content-Type') or '') \
                            .split(';')[0].strip().lower()
                        if ctype and not ctype.startswith('image/'):
                            return None, 'на странице не нашлось картинки'
                        data = await r2.read()
                        url = str(r2.url)
                else:
                    data = await resp.read()
                if len(data) > MAX_REMOTE_IMAGE_BYTES:
                    return None, (f'файл больше {MAX_REMOTE_IMAGE_BYTES // (1024 * 1024)} МиБ — '
                                  'Discord вложение такого размера не примет')
                if not data:
                    return None, 'пустой ответ'
                ext = _sniff_image_ext(data[:32]) or \
                    os.path.splitext(str(url).split('?')[0])[1].lower()
                if ext not in _IMAGE_EXTS:
                    ext = '.png'
                return data, 'appeal_image' + ext
    except Exception as _ex:                      # noqa: BLE001
        return None, str(_ex)[:160] or 'сеть недоступна'


def render_appeal_card(*, appeal_id, user_name, text, link=None,
                       theme=DEFAULT_APPEAL_THEME, brand='Hakumo'):
    """Карточка поданной апелляции → PNG bytes. Никогда не бросает наружу."""
    try:
        base, glow_a, glow_b, grid_c, ink, ink2 = APPEAL_THEMES.get(
            str(theme), APPEAL_THEMES[DEFAULT_APPEAL_THEME])
        acc = glow_a
        rnd = random.Random(int(appeal_id) * 977)

        canvas = Image.new('RGBA', (W * SS, H * SS), base + (255,))
        d = ImageDraw.Draw(canvas)

        def S(px):
            return px * SS

        # фон: градиент + мягкие свечения
        for y in range(H * SS):
            t = y / (H * SS)
            r = int(base[0] * (1 - t * 0.4))
            g = int(base[1] * (1 - t * 0.25))
            b = int(base[2] * (1 + t * 0.3))
            d.line([(0, y), (W * SS, y)], fill=(max(0, r), max(0, g), min(255, b), 255))
        glow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        for _ in range(3):
            cx = rnd.randint(W * SS // 2, W * SS - S(60))
            cy = rnd.randint(-S(100), H * SS // 2)
            rr = rnd.randint(S(130), S(230))
            col = acc if rnd.random() < 0.6 else glow_a
            gd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=col + (105,))
        gd.ellipse([-S(200), H * SS - S(120), S(100), H * SS + S(200)], fill=glow_b + (85,))
        glow = glow.filter(ImageFilter.GaussianBlur(S(55)))
        canvas.alpha_composite(glow)
        d = ImageDraw.Draw(canvas)

        # сетка
        step = S(48)
        for x in range(0, W * SS, step):
            d.line([(x, 0), (x, H * SS)], fill=grid_c + (55,), width=max(1, S(1)))
        for y in range(0, H * SS, step):
            d.line([(0, y), (W * SS, y)], fill=grid_c + (55,), width=max(1, S(1)))

        # номер апелляции водяным знаком справа
        num_txt = f'#{int(appeal_id):02d}'
        f_num = _font(True, 235)
        nb = d.textbbox((0, 0), num_txt, font=f_num)
        d.text((W * SS - (nb[2] - nb[0]) - S(36), (H * SS - (nb[3] - nb[1])) // 2 - S(40)),
               num_txt, font=f_num, fill=acc + (40,))

        # угловые кронштейны
        t = max(S(4), 4 * SS)
        for (cx, cy, sx, sy) in ((40, 40, 1, 1), (W - 40, 40, -1, 1),
                                 (40, H - 40, 1, -1), (W - 40, H - 40, -1, -1)):
            x0, y0 = S(cx), S(cy)
            d.line([(x0, y0), (x0 + S(38) * sx, y0)], fill=acc + (230,), width=t)
            d.line([(x0, y0), (x0, y0 + S(38) * sy)], fill=acc + (230,), width=t)

        # статусная плашка
        pad = S(92)
        f_pill = _font(True, 20 * SS)
        pill = 'ОЖИДАЕТ РЕШЕНИЯ МОДЕРАЦИИ'
        pw = d.textbbox((0, 0), pill, font=f_pill)[2] + S(36)
        d.rounded_rectangle([pad, S(66), pad + pw, S(66 + 34)], radius=S(17),
                            fill=(244, 162, 97, 42), outline=(244, 162, 97, 190), width=max(1, S(2)))
        d.text((pad + S(18), S(66 + 5)), pill, font=f_pill, fill=(255, 205, 150, 255))

        # заголовок
        title = 'АПЕЛЛЯЦИЯ'
        f_title = _fit(d, title, True, 46 * SS, int((W * SS - 2 * pad) * 0.55))
        d.text((pad, S(120)), title, font=f_title, fill=ink + (255,))
        sub = f'от {user_name or "участника сервера"}'
        f_sub = _font(True, 24 * SS)
        d.text((pad, S(120) + f_title.size + S(10)), sub, font=f_sub, fill=acc + (255,))

        # текст апелляции: зона строго между подзаголовком и строкой ссылки,
        # шрифт уменьшаем, пока блок не влезет целиком (иначе — многоточие)
        text_w = int((W * SS - 2 * pad) * 0.60)
        zone_top = S(214)
        zone_bottom = (H * SS - S(100)) if link else (H * SS - S(84))
        f_text, lines = None, None
        for size in range(28 * SS, 18 * SS - 1, -2 * SS):
            f_try = _font(False, size)
            ls = _wrap(d, str(text or ''), f_try, text_w)
            probe = d.textbbox((0, 0), ls[0] or 'Ag', font=f_try)
            line_step = (probe[3] - probe[1]) + S(12)
            total_h = line_step * len(ls)
            if len(ls) <= 3 and zone_top + total_h <= zone_bottom:
                f_text, lines = f_try, ls
                break
        if lines is None:
            f_text = _font(False, 18 * SS)
            lines = _wrap(d, str(text or ''), f_text, text_w)[:3]
            last = lines[-1]
            while last and d.textbbox((0, 0), last + '…', font=f_text)[2] > text_w:
                last = last[:-1]
            lines[-1] = last.rstrip() + '…'
        yy = zone_top
        for ln in lines:
            d.text((pad, yy), ln, font=f_text, fill=ink2 + (255,))
            bb = d.textbbox((0, 0), ln or 'Ag', font=f_text)
            yy += (bb[3] - bb[1]) + S(12)

        # ссылка-доказательство — на собственной строке над футером,
        # футер — на дне; текстовый блок ограничен зоной выше них
        if link:
            f_link = _font(False, 18 * SS)
            hosted = str(link)[:64]
            d.text((pad, H * SS - S(92)), f'доказательство: {hosted}',
                   font=f_link, fill=acc + (220,))

        # футер
        f_foot = _font(True, 20 * SS)
        d.text((pad, H * SS - S(56)), f'Апелляция #{int(appeal_id)}  ·  {brand}',
               font=f_foot, fill=acc + (255,))

        out = canvas.resize((W, H), Image.Resampling.LANCZOS).convert('RGB')
        buf = io.BytesIO()
        out.save(buf, format='PNG')
        return buf.getvalue()
    except Exception:
        return None


def appeal_card_filename(appeal_id):
    return f'hakumo_appeal_{int(appeal_id):02d}.png'


__all__ = ('APPEAL_THEMES', 'APPEAL_THEME_ORDER', 'DEFAULT_APPEAL_THEME',
           'APPEAL_MODES', 'APPEAL_MODE_LABELS', 'normalize_appearance',
           'render_appeal_card', 'appeal_card_filename')
