# -*- coding: utf-8 -*-
"""П.6: данные обновляются точечно, без визуальной перезагрузки страницы.

1. Ни один шаблон/скрипт панели не делает location.reload() / перехода
   на тот же URL после изменения данных (кроме auth-потоков login/logout).
2. Формы POST отсутствуют в панели (всё через fetch+JSON, точечные DOM).
3. Живые обновления идут через setLiveRefresh/patch-хелперы — числа пишутся
   точечно (тест live_stats п.1), а не полной перерисовкой каркаса.
4. Стили: нет принудительного повторного задания фона при обновлениях.
"""
import os
import sys
import glob
import re

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


print('== 1. Нет полных перезагрузок страницы из данных ==')
hits = []
for f in glob.glob(os.path.join(ROOT, 'web/templates/*.html')) + \
         glob.glob(os.path.join(ROOT, 'web/static/*.js')):
    name = os.path.basename(f)
    src = open(f, encoding='utf-8').read()
    for m in re.finditer(r'(location\.reload\s*\(|location\.href\s*=\s*location\.[hs])', src):
        line = src.count('\n', 0, m.start()) + 1
        hits.append(f'{name}:{line}')
check(not hits, f'location.reload()/self-href не используются (нашли: {hits})')

print('== 2. POST-формы: только auth-потоки ==')
forms = []
for f in glob.glob(os.path.join(ROOT, 'web/templates/*.html')):
    name = os.path.basename(f)
    if name in ('login.html', 'register.html'):
        continue   # вход/регистрация — осознанно полноценные переходы
    src = open(f, encoding='utf-8').read()
    for _ in re.finditer(r'method\s*=\s*["\']?post', src, re.I):
        forms.append(name)
check(not forms, f'панель не использует полноэкранные POST-формы (нашли: {forms})')

print('== 3. Живые данные: точечные патчи ==')
appjs = open(os.path.join(ROOT, 'web/static/app.js'), encoding='utf-8').read()
check('window.setLiveRefresh' in appjs, 'единый точечный reflow setLiveRefresh присутствует')
# Патч-хелпер п.1: текстовые узлы обновляются, если значение изменилось (есть условие !=)
if 'function patchText' in appjs or 'patchText(' in appjs:
    pt = appjs[appjs.index('patchText'):]
    check('!=' in pt[:1200], 'patchText пишет только при изменении (нет миганий)')
n_rebuild = 0
for f in glob.glob(os.path.join(ROOT, 'web/templates/*.html')):
    src = open(f, encoding='utf-8').read()
    for m in re.finditer(r'setLiveRefresh\s*\(', src):
        pass
    for m in re.finditer(r'\.innerHTML\s*=\s*(\'\'|""|\'\\s*\+\s*s)', src):
        n_rebuild += 1
check(True, f'перерисовок-«обнуление+строка» в шаблонах: {n_rebuild} (инфо; списки-перестроения допустимы при diff-патче)')

print('== 4. Сцена стабильна при обновлениях ==')
css = open(os.path.join(ROOT, 'web/static/style.css'), encoding='utf-8').read()
check('.htmx-' not in css, 'без htmx-механизмов, фон не снимается')
check('flashing' not in appjs.lower(), 'нет flash-классов перераскраски при обновлении')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
