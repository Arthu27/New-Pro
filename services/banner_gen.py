# -*- coding: utf-8 -*-
"""Генератор баннеров для правил сервера («авто-картинка» вместо голого URL).

Редактор правил умеет два источника картинки правила:
- свой URL (как раньше — img-поле);
- «создать автоматически» — этот модуль рендерит фирменный баннер 1200x400:
  тёмная сетка + свечения в цвете акцента, крупный номер правила, текст
  из редактора, футер «Правило X из N · бренд».

Публикация (web/routes/tasks_rules.py) при живом боте прикладывает PNG
к эмбеду файлом (attachment://), в демо-режиме баннер виден в предпросмотре
панели (/api/guild/<gid>/rules/banner).

Стиль рисуем чистым PIL, шрифты — assets/fonts (Bold/Regular).
"""
import io
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, 'assets', 'fonts')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

W, H = 1200, 400
SS = 2  # мягкий supersampling итогового ресайза

# Темы баннера: (база фона, свечение 1, свечение 2, цвет сетки, текст, под-текст)
THEMES = {
    'violet': ((16, 14, 32), (99, 102, 241), (34, 211, 238), (52, 48, 96), (244, 244, 248), (170, 170, 190)),
    'night': ((12, 14, 18), (240, 180, 60), (244, 127, 60), (44, 46, 56), (245, 245, 243), (168, 168, 172)),
    'ocean': ((8, 22, 30), (14, 165, 233), (34, 211, 238), (22, 62, 80), (240, 250, 252), (150, 176, 186)),
    'forest': ((10, 24, 18), (34, 197, 94), (132, 204, 22), (24, 64, 46), (242, 250, 245), (152, 180, 160)),
}
THEME_ORDER = tuple(THEMES)
DEFAULT_THEME = 'violet'


def _font(bold, sz):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT_R, sz)
    except Exception:
        return ImageFont.load_default()


def _hex_rgb(v):
    v = str(v or '').strip().lstrip('#')
    if len(v) != 6:
        return (99, 102, 241)
    try:
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (99, 102, 241)


def _wrap(draw, text, f, max_w):
    """Перенос строк по ширине рендера (слова целиком)."""
    lines = []
    for raw in str(text or '').split('\n'):
        words = raw.split()
        if not words:
            lines.append('')
            continue
        line = words[0]
        for w in words[1:]:
            probe = line + ' ' + w
            if draw.textbbox((0, 0), probe, font=f)[2] - draw.textbbox((0, 0), probe, font=f)[0] <= max_w:
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


def render_rules_banner(*, title, text, index=1, total=1, accent='4f46e5',
                        theme=DEFAULT_THEME, brand='Hakumo', seed=None,
                        return_image=False):
    """Отрисовать баннер правила; вернуть PNG-байты (или Image при return_image)."""
    base, glow_a, glow_b, grid_c, ink, ink2 = THEMES.get(str(theme), THEMES[DEFAULT_THEME])
    acc = _hex_rgb(accent)
    rnd = random.Random(seed if seed is not None else (int(index) * 1000 + int(total)))

    canvas = Image.new('RGBA', (W * SS, H * SS), base + (255,))
    d = ImageDraw.Draw(canvas)

    def S(px):
        return px * SS

    # ── фон: диагональный градиент + свечения ──────────────────────────
    for y in range(H * SS):
        t = y / (H * SS)
        r = int(base[0] * (1 - t * 0.55))
        g = int(base[1] * (1 - t * 0.35))
        b = int(base[2] * (1 + t * 0.25))
        d.line([(0, y), (W * SS, y)], fill=(max(0, r), max(0, g), min(255, b), 255))
    glow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for _ in range(3):
        cx = rnd.randint(W * SS // 3, W * SS - S(80))
        cy = rnd.randint(-S(120), H * SS // 2)
        rr = rnd.randint(S(150), S(260))
        col = acc if rnd.random() < 0.55 else glow_a
        gd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=col + (110,))
    gd.ellipse([-S(220), H * SS - S(140), S(120), H * SS + S(220)], fill=glow_b + (90,))
    glow = glow.filter(ImageFilter.GaussianBlur(S(60)))
    canvas.alpha_composite(glow)
    d = ImageDraw.Draw(canvas)

    # ── сетка ──────────────────────────────────────────────────────────
    step = S(48)
    for x in range(0, W * SS, step):
        d.line([(x, 0), (x, H * SS)], fill=grid_c + (60,), width=max(1, S(1)))
    for y in range(0, H * SS, step):
        d.line([(0, y), (W * SS, y)], fill=grid_c + (60,), width=max(1, S(1)))

    # ── крупный номер правила водяным знаком ───────────────────────────
    num_txt = f'{int(index):02d}'
    f_num = _font(True, 300)
    nb = d.textbbox((0, 0), num_txt, font=f_num)
    d.text((W * SS - (nb[2] - nb[0]) - S(40), (H * SS - (nb[3] - nb[1])) // 2 - S(60)),
           num_txt, font=f_num, fill=acc + (42,))

    # ── угловые кронштейны акцентом ────────────────────────────────────
    L = S(42)
    t = max(S(4), 4 * SS)
    for (cx, cy, sx, sy) in ((40, 40, 1, 1), (W - 40, 40, -1, 1), (40, H - 40, 1, -1), (W - 40, H - 40, -1, -1)):
        x0, y0 = S(cx), S(cy)
        d.line([(x0, y0), (x0 + S(42) * sx, y0)], fill=acc + (230,), width=t)
        d.line([(x0, y0), (x0, y0 + S(42) * sy)], fill=acc + (230,), width=t)

    # ── текстовый блок ─────────────────────────────────────────────────
    pad = S(96)
    text_zone = W * SS - 2 * pad          # масштабированная ширина колонки
    title_up = str(title or 'Правила сервера').strip() or 'Правила сервера'
    title_up = title_up.upper()
    f_title = _fit(d, title_up, True, 30 * SS, int(text_zone * 0.58))
    d.text((pad, S(74)), title_up, font=f_title, fill=ink + (255,))
    tw = d.textbbox((0, 0), title_up, font=f_title)[2]
    d.rounded_rectangle([pad, S(112), pad + min(tw, int(text_zone * 0.58)) + S(60), S(119)],
                        radius=S(3), fill=acc + (255,))

    # Текст правила: подбираем размер, чтобы влезло в 3 строки целиком;
    # если не влезает даже на минимуме — красиво обрезаем с многоточием,
    # чтобы фраза не рвалась на полуслове.
    text_w = int(text_zone * 0.62)
    f_text = None
    lines = None
    for size in range(34 * SS, 22 * SS - 1, -2 * SS):
        f_try = _font(False, size)
        ls = _wrap(d, str(text or ''), f_try, text_w)
        if len(ls) <= 3:
            f_text, lines = f_try, ls
            break
    if lines is None:
        f_text = _font(False, 22 * SS)
        lines = _wrap(d, str(text or ''), f_text, text_w)[:3]
        last = lines[-1]

        def _w(s):
            bb = d.textbbox((0, 0), s or 'Ag', font=f_text)
            return bb[2] - bb[0]

        while last and _w(last + '…') > text_w:
            last = last[:-1]
        lines[-1] = last.rstrip() + '…'
    yy = S(150)
    for ln in lines:
        d.text((pad, yy), ln, font=f_text, fill=ink2 + (255,))
        bb = d.textbbox((0, 0), ln or 'Ag', font=f_text)
        yy += (bb[3] - bb[1]) + S(16)

    # ── футер ──────────────────────────────────────────────────────────
    f_foot = _font(True, 22 * SS)
    foot = f'Правило {int(index)} из {int(total)}  ·  {brand}'
    d.text((pad, H * SS - S(74)), foot, font=f_foot, fill=acc + (255,))

    out = canvas.resize((W, H), Image.Resampling.LANCZOS).convert('RGB')
    if return_image:
        return out
    buf = io.BytesIO()
    out.save(buf, format='PNG', optimize=True)
    return buf.getvalue()


def banner_filename(index):
    return f'hakumo_rule_{int(index):02d}.png'


__all__ = ('THEMES', 'THEME_ORDER', 'DEFAULT_THEME', 'render_rules_banner', 'banner_filename')


if __name__ == '__main__':  # ручной просмотр: python3 services/banner_gen.py
    png = render_rules_banner(title='Правила сервера', index=1, total=6,
                              text='Уважай участников. Никакой рекламы и рейдов.',
                              accent='4f46e5', theme='violet')
    out = os.path.join(os.path.dirname(ROOT), '_banner_demo.png')
    with open('_banner_demo.png', 'wb') as fp:
        fp.write(png)
    print('ok ->', '_banner_demo.png', f'({len(png)} байт)')
