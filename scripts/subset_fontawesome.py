# -*- coding: utf-8 -*-
"""Урезает FontAwesome до иконок, которые панель реально использует.

В all.min.css 2452 иконки, в шаблонах и скриптах — около трёхсот. Из-за
этого на каждую страницу приезжает 102 КБ CSS и три шрифта (150 КБ solid,
108 КБ brands, 25 КБ regular), хотя fa-regular не используется вообще,
а fa-brands — ради двух иконок (discord, github).

Скрипт собирает подмножество и кладёт его рядом с оригиналом:
  web/static/vendor/fontawesome/css/all.subset.css
  web/static/vendor/fontawesome/webfonts/fa-solid-900.subset.woff2
  web/static/vendor/fontawesome/webfonts/fa-brands-400.subset.woff2
Оригиналы не трогаются — их всегда можно вернуть одной правкой в base.html.

Запуск:  python3 scripts/subset_fontawesome.py
Нужны:   fonttools, brotli  (pip install fonttools brotli)
"""
import glob
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FA = os.path.join(ROOT, 'web', 'static', 'vendor', 'fontawesome')
CSS_IN = os.path.join(FA, 'css', 'all.min.css')
CSS_OUT = os.path.join(FA, 'css', 'all.subset.css')
WF = os.path.join(FA, 'webfonts')

# Префиксы/модификаторы — не имена иконок.
SKIP = {
    'solid', 'regular', 'brands', 'light', 'thin', 'duotone', 'sharp', 'free',
    'fw', 'spin', 'pulse', 'border', 'inverse', 'stack', 'stack-1x', 'stack-2x',
    'li', 'ul', 'lg', 'xs', 'sm', '2xs', '1x', '2x', '3x', '4x', '5x', '6x',
    '7x', '8x', '9x', '10x', 'rotate-90', 'rotate-180', 'rotate-270',
    'flip-horizontal', 'flip-vertical', 'flip-both', 'beat', 'fade',
    'beat-fade', 'bounce', 'shake', 'spin-pulse', 'spin-reverse', 'sr-only',
    'sr-only-focusable', '6',
    # имена файлов шрифтов, а не иконки — попадаются в ссылках на webfonts
    'solid-900', 'regular-400', 'brands-400', 'v4compatibility',
}

# Класс-префикс -> файл шрифта.
STYLE_FONT = {
    'fas': 'fa-solid-900',
    'fa-solid': 'fa-solid-900',
    'fab': 'fa-brands-400',
    'fa-brands': 'fa-brands-400',
    'far': 'fa-regular-400',
    'fa-regular': 'fa-regular-400',
}


def scan_sources():
    """Какие иконки и в каком начертании использует панель."""
    explicit = {}   # имя -> set(начертаний), задано явно: «fab fa-discord»
    bare = set()    # имена без явного стиля — FontAwesome трактует их как solid
    # Иконки приходят не только из разметки: services/panel_menu.py задаёт
    # иконку каждой страницы меню, уведомления и логи — свои. app.js вставляет
    # их через 'fas ' + icon, поэтому скан обязан читать и Python.
    files = (glob.glob(os.path.join(ROOT, 'web', 'templates', '*.html'))
             + glob.glob(os.path.join(ROOT, 'web', 'static', '*.js')))
    for sub in ('services', 'cogs', 'web'):
        files += glob.glob(os.path.join(ROOT, sub, '**', '*.py'), recursive=True)
    for path in files:
        s = io.open(path, encoding='utf-8', errors='ignore').read()
        for style, name in re.findall(r'\b(fas|far|fab|fa-solid|fa-regular|fa-brands)\s+fa-([a-z0-9][a-z0-9-]*)', s):
            if name in SKIP:
                continue
            explicit.setdefault(name, set()).add(STYLE_FONT[style])
        for name in re.findall(r'\bfa-([a-z0-9][a-z0-9-]*)', s):
            if name in SKIP or name in STYLE_FONT:
                continue
            bare.add(name)

    # Второй проход видит «голое» fa-discord внутри «fab fa-discord». Если имя
    # уже получило явное начертание, в solid его дублировать не нужно — иначе
    # в подмножество solid попадают брендовые глифы, которых там нет.
    used = {n: set(v) for n, v in explicit.items()}
    for name in bare:
        if name not in used:
            used[name] = {'fa-solid-900'}
    return used


def split_rules(css):
    """Минифицированный CSS -> список (селектор, тело)."""
    rules = []
    for m in re.finditer(r'([^{}]+)\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}', css):
        rules.append((m.group(1).strip(), m.group(2)))
    return rules


def codepoint_of(body):
    #FontAwesome пишет ASCII-символы коротко: .fa-at:before{content:"\40"}.
    # Шаблон обязан принимать от 1 до 6 цифр, иначе «at», «plus», «percent»
    # и «hashtag» выглядят как несуществующие иконки.
    m = re.search(r'content:\s*"\\([0-9a-fA-F]{1,6})"', body)
    return int(m.group(1), 16) if m else None


def main():
    from fontTools import subset as ftsubset

    css = io.open(CSS_IN, encoding='utf-8').read()
    used = scan_sources()
    rules = split_rules(css)

    # кодпоинты каждой иконки — из .fa-имя:before
    cps = {}
    for sel, body in rules:
        for name in re.findall(r'\.fa-([a-z0-9-]+)(?::before)', sel):
            cp = codepoint_of(body)
            if cp:
                cps[name] = cp

    known = {n for n in used if n in cps}
    unknown = sorted(n for n in used if n not in cps)
    if unknown:
        print(f'  ВНИМАНИЕ: иконки без определения в CSS ({len(unknown)}): {unknown[:15]}')

    # ── CSS: базовые правила + только используемые иконки ───────────────
    # Селекторы в all.min.css сгруппированы:
    #   .fa-trash-alt:before,.fa-trash-can:before{content:"\f2ed"}
    # Поэтому правило чистится ПО СЕЛЕКТОРАМ: нужные остаются, лишние
    # выкидываются; если нужных не осталось — правило уходит целиком.
    keep_sel, drop = [], 0
    icon_sel = re.compile(r'^\.fa-([a-z0-9-]+):before$')
    for sel, body in rules:
        if sel.startswith('@font-face'):
            continue    # переписываем ниже под подмножества
        parts = [x.strip() for x in sel.split(',')]
        if any(icon_sel.match(x) for x in parts):
            kept = [x for x in parts
                    if not icon_sel.match(x) or icon_sel.match(x).group(1) in known]
            dropped = [x for x in parts
                       if icon_sel.match(x) and icon_sel.match(x).group(1) not in known]
            drop += len(dropped)
            if kept:
                keep_sel.append((','.join(kept), body))
        else:
            keep_sel.append((sel, body))

    # @font-face: только те начертания, где есть используемые иконки
    per_font = {}
    for name in known:
        for font in used[name]:
            per_font.setdefault(font, set()).add(name)

    faces = []
    fam_weight = {'fa-solid-900': ('Font Awesome 6 Free', 900),
                  'fa-brands-400': ('Font Awesome 6 Brands', 400),
                  'fa-regular-400': ('Font Awesome 6 Free', 400)}
    for font in ('fa-solid-900', 'fa-brands-400', 'fa-regular-400'):
        if font not in per_font:
            continue
        fam, w = fam_weight[font]
        faces.append(
            '@font-face{font-family:"%s";font-style:normal;font-weight:%d;'
            'font-display:swap;src:url(../webfonts/%s.subset.woff2) format("woff2")}'
            % (fam, w, font))

    # ── шрифты: подмножество глифов ─────────────────────────────────────
    saved = []
    for font, names in per_font.items():
        src = os.path.join(WF, font + '.woff2')
        dst = os.path.join(WF, font + '.subset.woff2')
        uni = sorted(cps[n] for n in names)
        args = [src, '--output-file=' + dst, '--flavor=woff2',
                '--unicodes=' + ','.join('U+%04X' % u for u in uni),
                '--layout-features=*', '--no-hinting', '--desubroutinize']
        ftsubset.main(args)
        before, after = os.path.getsize(src), os.path.getsize(dst)
        saved.append((font, len(names), before, after))

    out = '\n'.join(faces) + '\n' + '\n'.join(
        '%s{%s}' % (s, b) for s, b in keep_sel)
    io.open(CSS_OUT, 'w', encoding='utf-8').write(out)

    print(f'  иконок в use: {len(known)} из {len(cps)} в all.min.css '
          f'(правил иконок выброшено: {drop})')
    print(f'  CSS: {len(css)} -> {len(out)} Б')
    for font, n, b, a in saved:
        print(f'  {font}: {b} -> {a} Б  ({n} иконок, −{100 - 100 * a // b}%)')
    # ── самопроверка: ни одна используемая иконка не должна пропасть ─────
    out_css = io.open(CSS_OUT, encoding='utf-8').read()
    have = {n for n in re.findall(r'\.fa-([a-z0-9-]+):before', out_css)}
    lost = sorted(n for n in known if n not in have)
    if lost:
        print(f'  ОШИБКА: {len(lost)} иконок не попали в подмножество: {lost[:20]}')
        return 1
    for font, names in per_font.items():
        from fontTools.ttLib import TTFont
        cm = TTFont(os.path.join(WF, font + '.subset.woff2')).getBestCmap()
        miss = sorted(n for n in names if cps.get(n) not in cm)
        if miss:
            print(f'  ОШИБКА: в {font}.subset.woff2 нет глифов для {miss[:20]}')
            return 1
    print(f'  самопроверка: {len(known)} иконок в CSS, все глифы на месте')

    unused = {'fa-regular-400'} - set(per_font)
    for font in sorted(unused):
        p = os.path.join(WF, font + '.woff2')
        if os.path.exists(p):
            print(f'  {font}: начертание не используется — @font-face убран '
                  f'({os.path.getsize(p)} Б больше не грузятся)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
