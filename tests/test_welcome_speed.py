# -*- coding: utf-8 -*-
"""Скорость витрины (PageSpeed Insights по hakumods.xyz, владелец
2026-09-08): welcome-страница не должна возвращать найденные проблемы.

Проверки по шаблону и файлам (без Flask):
  1. meta description — SEO-аудит «В документе нет метаописания»;
  2. CSS иконок/шрифтов НЕ блокируют отрисовку (media=print + onload,
     noscript-фолбэк) — аудит «Запросы, блокирующие отрисовку» (1.3 с);
  3. блик дракона и прогресс-скролл — только transform (аудиты
     «Принудительная компоновка» и «некомбинированные анимации»);
  4. начальные проверки геометрии — в rAF, перезапуски анимаций —
     пакетно (аудит «Принудительная компоновка», 680 мс);
  5. hero-дракон — fetchpriority=high (LCP), нижние — lazy;
  6. картинки дракона пережаты (аудит «Улучшите загрузку изображений»).

Запуск: python3 tests/test_welcome_speed.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, 'web', 'templates', 'welcome.html')

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


src = open(TPL, encoding='utf-8').read()

print('== 1. SEO: meta description ==')
check('<meta name="description"' in src and len(
    src.split('<meta name="description" content="', 1)[1].split('"', 1)[0]) > 60,
    'на витрине есть содержательное метаописание')

print('== 2. Неблокирующие CSS ==')
check('all.subset.css" media="print" onload="this.media=\'all\'"' in src,
      'иконки (all.subset.css) не блокируют первую отрисовку')
check('fonts.css" media="print" onload="this.media=\'all\'"' in src,
      'шрифты (fonts.css) не блокируют первую отрисовку')
check(src.count('<noscript><link rel="stylesheet"') == 2,
      'обa noscript-фолбэка на месте (без JS стили всё равно грузятся)')

print('== 3. Композитные анимации ==')
gloss = src.split('@keyframes wGloss', 1)[1].split('}', 2)[1]
check('left' not in gloss and 'transform' in gloss,
      'блик дракона бежит transform-ом, а не left (layout)')
check('transform: scaleX(0); transform-origin: 0 50%;' in src
      and "style.transform = 'scaleX('" in src
      and 'bar.style.width' not in src,
      'скролл-прогресс — scaleX без layout на каждый кадр')
check('@keyframes wFloat' in src,
      'левитация дракона определена (правило больше не мёртвое)')

print('== 4. Принудительная компоновка ==')
check(src.count('requestAnimationFrame(function () {\n        if (') >= 3
      or src.count('requestAnimationFrame(function () {') >= 4,
      'начальные проверки геометрии отложены до первого кадра (rAF)')
check('void barsBox.offsetWidth;' in src and 'void b.offsetWidth;' not in src,
      'перезапуск баров — один reflow на все (было: по одному на бар)')
check('void el.offsetWidth;' not in src
      and 'void document.documentElement.offsetWidth;' in src,
      'KPI-мерцание перезапускается пакетно')
check('rectOf = { el: t, r: t.getBoundingClientRect() }' in src,
      'tilt кэширует прямоугольник карточки (не читает геометрию на каждом движении)')

print('== 5. LCP и ленивая подгрузка ==')
check('fetchpriority="high"' in src and 'decoding="async"' in src,
      'hero-дракон: высокий приоритет + асинхронный декодинг (LCP)')
check(src.count('loading="lazy"') >= 2,
      'нижние драконы (витрина, футер) грузятся лениво')

print('== 6. Картинки пережаты ==')
for name, limit in (('emblem-dragon.webp', 21000), ('emblem-dragon-128.webp', 8100)):
    p = os.path.join(ROOT, 'web', 'static', 'brand', name)
    size = os.path.getsize(p)
    check(size <= limit, f'{name}: {size} байт ≤ {limit} (было 26238/9874)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
