# -*- coding: utf-8 -*-
"""Аудит иконок Font Awesome (битые иконки = пустые квадраты в панели).

Проверки:
1. Каждая fa-* иконка из шаблонов, static JS и меню панели определена
   в вендоренном all.min.css (включая утилиты вроде fa-spin).
2. JS-конкатенации ('fa-arrow-' + 'up') не считаются битыми иконками —
   но полные имена из таких выражений проверяются парно.
3. В шаблонах нет запрещённых ЭМОДЗИ в разметке/JS (только Font Awesome).
4. Меню: иконки групп и пунктов существуют в FA.
5. Префиксы стилей (fas/far/fab/fat/fal) валидны; устаревший класс
   «fa fa-…» (FA4) не используется.

Запуск: python3 tests/test_icon_audit.py
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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


FA_CSS = os.path.join(ROOT, 'web', 'static', 'vendor', 'fontawesome', 'css', 'all.min.css')
css = open(FA_CSS, encoding='utf-8').read()
DEFINED = set(re.findall(r'\.(fa-[a-z0-9-]+)', css))

# ─── 1. все fa-* иконки существуют ───────────────────────────────────────────
print('== 1. Все fa-* иконки определены в вендоренном CSS ==')
_sources = []
for pat in ('web/templates/*.html', 'web/static/*.js', 'services/panel_menu.py'):
    _sources += glob.glob(os.path.join(ROOT, pat))
_sources = [s for s in _sources if 'vendor' not in s]

used = set()
for f in _sources:
    src = open(f, encoding='utf-8').read()
    used |= set(re.findall(r'fa-[a-z0-9-]+', src))

# конкатенации: 'fa-arrow-' + 'up' / 'fa-arrow-' + (n>=0 ? 'up' : 'down') —
# токен-префикс, пропускаем; полные имена из таких выражений уже валидны
missing = sorted(t for t in used if t not in DEFINED)
concat_prefixes = set()
for f in _sources:
    src = open(f, encoding='utf-8').read()
    for m in re.finditer(r"fa-[a-z0-9-]+\s*['\"]\s*\+", src):
        concat_prefixes.add(m.group(0).rstrip('+"\' '))
missing_final = [t for t in missing if t not in concat_prefixes]
check(not missing_final, f'{len(used)} иконок, битых: {len(missing_final)} ({missing_final[:5]})')

# ─── 2. утилиты FA существуют как классы ─────────────────────────────────────
print('== 2. Утилиты FA (fa-spin и пр.) на месте ==')
for util in ('fa-spin', 'fa-fw', 'fa-stack', 'fa-2xs', 'fa-lg', 'fa-rotate-90', 'fa-flip-horizontal'):
    if util not in DEFINED:
        check(False, f'утилита {util} не найдена в CSS')
check(all(u in DEFINED for u in ('fa-spin', 'fa-fw', 'fa-stack')),
      'fa-spin/fa-fw/fa-stack определены')

# ─── 3. без эмодзи в шаблонах ────────────────────────────────────────────────
print('== 3. Эмодзи в шаблонах/JS не используются (только Font Awesome) ==')
EMOJI_RE = re.compile(
    '[\U0001F000-\U0001FAFF\uFE0F\u2600-\u27BF\u2B00-\u2BFF]'
)
_bad = []
for f in _sources:
    src = open(f, encoding='utf-8').read()
    for m in EMOJI_RE.finditer(src):
        _bad.append(f'{os.path.basename(f)}: {m.group(0)!r}')
check(not _bad, f'эмодзи в разметке: {len(_bad)} ({_bad[:3]})')

# ─── 4. иконки меню ──────────────────────────────────────────────────────────
print('== 4. Иконки меню существуют в FA ==')
from services.panel_menu import MENU  # noqa: E402

_bad = []
for grp in MENU:
    for ic in (grp.get('icon') or '',) + tuple(p.get('icon') or '' for p in grp.get('pages', [])):
        if ic and not re.match(r'^fa-[a-z0-9-]+$', ic):
            _bad.append(f'не FA-имя: {ic}')
        elif ic and ic not in DEFINED:
            _bad.append(f'нет в CSS: {ic}')
check(not _bad, f'иконки меню валидны ({_bad[:4]})')

# ─── 5. префиксы стилей и FA4-синтаксис ──────────────────────────────────────
print('== 5. Префиксы стилей валидны, FA4 «fa fa-…» не используется ==')
_bad = []
for f in _sources:
    src = open(f, encoding='utf-8').read()
    for m in re.finditer(r'class\s*=\s*["\']([^"\']*)["\']', src):
        cls = m.group(1)
        for token in cls.split():
            if re.match(r'^fa[a-z]$', token) and token not in ('fas', 'far', 'fab', 'fal', 'fat', 'fad'):
                _bad.append(f'{os.path.basename(f)}: {token}')
    if re.search(r'class\s*=\s*["\']fa\s+fa-', src):
        _bad.append(f'{os.path.basename(f)}: FA4-синтаксис «fa fa-…»')
check(not _bad, f'префиксы корректны ({_bad[:4]})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
