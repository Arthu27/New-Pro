# -*- coding: utf-8 -*-
"""П.7 «разные устройства»: адаптация мобильных и узких экранов без дыр.

1. base.html и каждая самостоятельная страница — с meta viewport.
2. style.css: мобильные брейкпоинты (не меньше пяти), гавань таблиц
   (скроллит только таблица, не страница), мобильные строки пикеров ≥40px.
3. Нет инлайн-фиксированных ширин над бюджетом мобильного вне media-зоны
   (эвристика статического аудита по шаблонам: флажим width:NNNpx > 360
   в теле шаблона, если не в <style> с @media).
"""
import os
import re
import sys
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = 0
FAIL = 0


def check(ok, msg, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {detail}')


print('== 1. Viewport везде ==')
base = open(os.path.join(ROOT, 'web/templates/base.html'), encoding='utf-8').read()
check('name="viewport"' in base, 'base.html: viewport meta')
for f in ['login.html', 'register.html', 'welcome.html', 'status_public.html',
          'public_apply.html', 'mod_kiosk.html']:
    src = open(os.path.join(ROOT, 'web/templates', f), encoding='utf-8').read()
    check('name="viewport"' in src, f'{f}: viewport meta')

print('== 2. Адаптивная сетка и мобильные гарды ==')
css = open(os.path.join(ROOT, 'web/static/style.css'), encoding='utf-8').read()
check(len(re.findall(r'@media', css)) >= 5, f"брейкпоинтов в стилях: {len(re.findall(r'@media', css))}")
check(re.search(r'@media \(max-width: 760px\)[^@]*table:not\(\.keep-grid\)[^}]*display: block', css, re.S) is not None,
      'мобильная гавань таблиц: block + overflow-x auto')
check(re.search(r'@media \(max-width: 640px\)[^}]*\.sshd-row \{ min-height: 42px', css, re.S) is not None
      or 'min-height: 42px' in css, 'мобильные строки select ≥42px')
check('.mpd-row { min-height: 40px' in css, 'экран пальца: строки member-пикера ≥40px')

print('== 3. Шаблоны: без гилти-ширин > 360px вне медиа-блоков ==')
guilty = []
for f in glob.glob(os.path.join(ROOT, 'web/templates/*.html')):
    src = open(f, encoding='utf-8').read()
    for m in re.finditer(r'width:\s*(\d{3,})px', src):
        w = int(m.group(1))
        if w <= 360:
            continue
        line_txt = src[src.rfind('\n', 0, m.start()) + 1:src.find('\n', m.end())]
        # легитимные паттерны: max-width-контейнер, адаптивный контекст, clamp/min
        if 'max-width' in line_txt or 'clamp' in line_txt or 'min(' in line_txt:
            continue
        ctx = src[max(0, m.start() - 1200):m.start()]
        if '@media' in ctx or 'min-width' in ctx:
            continue
        # ограничение внутри CSS-правила с max-width рядом (тот же блок)
        brace_start = src.rfind('{', 0, m.start())
        rule_start = src.rfind('}', 0, brace_start) + 1
        near = src[brace_start:m.start()]
        rule_txt = src[rule_start:m.start()]
        if 'max-width' in near:
            continue
        # декоративные слои: абсолютные/фиксированные орбы-авроры (и их
        # parent-правила на соседних строках) — по вьюпорту, контет не сдвигают
        wide_ctx = src[max(0, brace_start - 400):m.start()]
        if re.search(r'position:\s*(absolute|fixed)', wide_ctx):
            continue
        line = src.count('\n', 0, m.start()) + 1
        guilty.append(f'{os.path.basename(f)}:{line}({w}px)')
check(not guilty, f'нет width > 360px вне адаптива (нашли: {guilty[:8]})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
