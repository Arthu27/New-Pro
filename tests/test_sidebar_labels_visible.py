# -*- coding: utf-8 -*-
"""Пункты бокового меню видны целиком (жалоба владельца 2026-09).

«Аналитика сервера» обрезалась до «Аналитика», пункт «Статистика бота»
не виден без выделения. Причины:
  * .nav-link span резал текст эллипсисом (overflow:hidden + nowrap);
  * у пунктов групп без подразделов не было title — в свёрнутом сайдбаре
    (иконки) имя пункта не появлялось даже по наведению.

Ожидание: у любого nav-link текст переносится вместо обрезки, а полное
имя пункта всегда доступно во всплывающей подсказке (title).

Запуск: python3 tests/test_sidebar_labels_visible.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = 0
FAIL = 0


def check(cond, label, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


css = open(os.path.join(ROOT, 'web', 'static', 'style.css'), encoding='utf-8').read()
tpl = open(os.path.join(ROOT, 'web', 'templates', '_sidebar_nav.html'), encoding='utf-8').read()

print('== style.css: текст пункта не режется ==')
m = re.search(r'\.nav-link\s+span\s*\{[^}]*\}', css)
seg = m.group(0) if m else ''
check('text-overflow' not in seg and 'ellipsis' not in seg and 'nowrap' not in seg,
      'у .nav-link span нет обрезки многоточием', f'→ {seg[:90]}')
check('overflow-wrap' in seg and 'white-space: normal' in seg,
      'длинное имя переносится, а не пропадает', f'→ {seg[:90]}')

print('== _sidebar_nav.html: полное имя доступно по наведению ==')
check('title="{{ it.label }}"' in tpl or 'title="{{ it.label }}' in tpl,
      'пункты групп без подразделов несут title с полным именем')
check('title="{{ it.label }}{% if it.description %}' in tpl,
      'пункты подразделов: title начинается с полного имени')

js = open(os.path.join(ROOT, 'web', 'static', 'app.js'), encoding='utf-8').read()

print('== Подгруппы (Модерация/Защита): пункты ВИДНЫ сразу ==')
mi = css.find('.nav-subgroup-items')
m = re.search(r'\.nav-subgroup-items\s*\{[^}]*\}', css)
seg = m.group(0) if m else ''
check('max-height: 700px' in seg and 'opacity: 1' in seg and 'max-height: 0' not in seg,
      'пункты подгрупп по умолчанию открыты (не спрятаны)',
      f'→ {seg[:100]}')
check('.nav-subgroup.closed .nav-subgroup-items' in css and 'max-height: 0' in css,
      'закрытие — только по клику (класс .closed)')
check('.nav-subgroup.closed .nav-subgroup-caret' in css,
      'стрелка подгруппы честно показывает состояние (закрыта)')
check("btn.addEventListener('click', function () { sub.classList.toggle('closed'); });" in js,
      'клик по подгруппе сворачивает/разворачивает')
check("sub.classList.toggle('open')" not in js.replace("pill.classList.toggle('open')", ''),
      'старая логика «открыть только активную» убрана')

print()
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)