# -*- coding: utf-8 -*-
"""Страж подмножества FontAwesome.

Панель использует 318 иконок из 2452, поэтому all.min.css и полные шрифты
заменены на all.subset.css + *.subset.woff2 (scripts/subset_fontawesome.py).
Подмножество собирается сканом по исходникам — значит оно может отстать от
кода: добавили страницу с новой иконкой, а шрифт не пересобрали, и в
сайдбаре пустой квадратик. Тест ловит именно это.

Запуск: python3 tests/test_fontawesome_subset.py
"""
import glob
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

PASS = 0
FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


FA = os.path.join(ROOT, 'web', 'static', 'vendor', 'fontawesome')
SUBSET_CSS = os.path.join(FA, 'css', 'all.subset.css')
FULL_CSS = os.path.join(FA, 'css', 'all.min.css')

check(os.path.exists(SUBSET_CSS), 'all.subset.css существует')
check(os.path.exists(FULL_CSS), 'оригинальный all.min.css сохранён (путь отката)')

import subset_fontawesome as S  # noqa: E402

used = S.scan_sources()
css = io.open(SUBSET_CSS, encoding='utf-8').read()
defined = {}
for sel, body in S.split_rules(css):
    for name in re.findall(r'\.fa-([a-z0-9-]+):before', sel):
        cp = S.codepoint_of(body)
        if cp:
            defined[name] = cp

check(len(used) > 100, f'скан находит иконки в исходниках ({len(used)} шт.)')

# Иконки обязаны находиться не только в разметке: services/panel_menu.py
# задаёт иконку каждой страницы меню, app.js вставляет её через 'fas ' + icon.
py_files = (glob.glob(os.path.join(ROOT, 'services', '**', '*.py'), recursive=True)
            + glob.glob(os.path.join(ROOT, 'web', '**', '*.py'), recursive=True))
py_icons = set()
for p in py_files:
    for n in re.findall(r'\bfa-([a-z0-9][a-z0-9-]*)',
                        io.open(p, encoding='utf-8', errors='ignore').read()):
        if n not in S.SKIP:
            py_icons.add(n)
check(bool(py_icons & set(defined)),
      f'иконки из Python учтены ({len(py_icons & set(defined))} из меню/уведомлений)')

unknown = sorted(n for n in used if n not in defined)
check(len(defined) >= len(used) - len(unknown) and len(defined) > 300,
      f'все используемые иконки определены в подмножестве ({len(defined)} шт.)')
check(not unknown, f'нет иконок без определения в FontAwesome ({len(unknown)}: {unknown[:5]})')

# Глифы обязаны физически лежать в шрифте — CSS без глифа даст квадратик.
try:
    from fontTools.ttLib import TTFont  # noqa: E402
except ImportError:
    TTFont = None
    print('  SKIP: нет fontTools — наличие глифов в шрифтах не проверено '
          '(pip install -r requirements-test.txt)')

per_font = {}
for name in used:
    if name not in defined:
        continue
    for font in used[name]:
        per_font.setdefault(font, set()).add(name)
all_ok, detail = True, []
for font, names in sorted(per_font.items()):
    path = os.path.join(FA, 'webfonts', font + '.subset.woff2')
    if not os.path.exists(path):
        all_ok, detail = False, [font + ': файла нет']
        continue
    if TTFont is None:
        continue
    cm = TTFont(path).getBestCmap()
    gone = sorted(n for n in names if defined[n] not in cm)
    if gone:
        all_ok = False
        detail.append(f'{font}: нет {gone[:8]}')
if TTFont is not None:
    check(all_ok, 'в подмножествах шрифтов есть глифы для каждой иконки'
          + ('' if all_ok else ' — ' + '; '.join(detail)))

# Начертание fa-regular панель не использует — оно не должно грузиться.
check('fa-regular-400.subset.woff2' not in css
      and not re.search(r'url\([^)]*fa-regular-400', css),
      'неиспользуемое начертание fa-regular не подключено')

# Базовые классы живут в сгруппированном правиле — проверяем по селекторам.
base = ['fa-solid', 'fa-brands', 'fa-fw', 'fa-spin', 'fa-lg', 'fa-2x',
        'fa-stack', 'fa-inverse']
sels = [s for s, _ in S.split_rules(css)]
lost = [c for c in base
        if not any(re.search(r'(^|,)\s*\.%s\s*(,|$)' % re.escape(c), s) for s in sels)]
check(not lost, f'базовые классы FontAwesome на месте (пропало: {lost or "нет"})')

# Шаблоны должны смотреть на подмножество, а не на полный CSS.
tpl = glob.glob(os.path.join(ROOT, 'web', 'templates', '*.html'))
on_full = [os.path.basename(p) for p in tpl
           if 'all.min.css' in io.open(p, encoding='utf-8').read()]
check(not on_full, f'ни один шаблон не подключает all.min.css (остались: {on_full or "нет"})')
on_sub = [os.path.basename(p) for p in tpl
          if 'all.subset.css' in io.open(p, encoding='utf-8').read()]
check(len(on_sub) >= 7, f'подмножество подключено в шаблонах ({len(on_sub)} шт.)')

# preload снимает цепочку HTML → CSS → woff2 — ради этого всё и затевалось.
pre = [os.path.basename(p) for p in tpl
       if 'rel="preload"' in io.open(p, encoding='utf-8').read()
       and '.woff2' in io.open(p, encoding='utf-8').read()]
check('base.html' in pre and 'login.html' in pre,
      f'критические шрифты предзагружаются ({len(pre)} шаблонов)')
check('as="font"' in io.open(os.path.join(ROOT, 'web', 'templates', 'base.html'),
                             encoding='utf-8').read()
      and 'crossorigin' in io.open(os.path.join(ROOT, 'web', 'templates', 'base.html'),
                                   encoding='utf-8').read(),
      'preload помечен as="font" и crossorigin (иначе браузер качает шрифт дважды)')

# Экономия должна оставаться экономией.
full = os.path.getsize(FULL_CSS)
check(len(css) < full // 2,
      f'all.subset.css вдвое меньше оригинала ({len(css)} против {full} Б)')
s_full = os.path.getsize(os.path.join(FA, 'webfonts', 'fa-solid-900.woff2'))
s_sub = os.path.getsize(os.path.join(FA, 'webfonts', 'fa-solid-900.subset.woff2'))
check(s_sub * 3 < s_full,
      f'fa-solid-900.subset.woff2 минимум втрое меньше полного ({s_sub} против {s_full} Б)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
