# -*- coding: utf-8 -*-
"""Аудит UI-панели: крошки = меню, списки не «уезжают», выбор не промахивается.

Защита от трёх классов багов, о которых сообщил владелец:
1) хлебные крошки («Бот · Настройки») не совпадают с группой в меню —
   теперь везде ровно «Группа · Подпись» из services.panel_menu;
2) всплывающие списки каналов/людей (.sshd / .mpd) уходят за край экрана —
   их нельзя прокрутить и «выбрать невозможно»; нужны умное позиционирование
   вверх/вниз и закрытие при прокрутке;
3) live-перерисовка списков каналов/участников между mousedown и click
   «пересаживает» нажатие на соседнюю строку (открывается другой канал/
   другой человек) — нужна фиксация нажатой строки и пауза live во время клика.

Запуск: /tmp/venv/bin/python tests/test_panel_ui_consistency.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

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


print('== 1. Крошка страницы = только раздел; название в <h1>, не дублируется ==')
from services.panel_menu import MENU  # noqa: E402

page_of = {}
for grp in MENU:
    g = grp.get('group')

    def walk(pages):
        for p in pages:
            if p.get('sections'):
                for s in p['sections']:
                    walk(s.get('pages', []))
            elif p.get('pages'):
                walk(p['pages'])
            else:
                page_of[p['path']] = (g, p.get('label'))

    walk(grp.get('pages', []))

tpl_dir = 'web/templates'
checked = 0
bad = []
for path, (group, label) in sorted(page_of.items()):
    name = path.strip('/').replace('-', '_')
    fn = os.path.join(tpl_dir, name + '.html')
    if not os.path.exists(fn):
        cands = [f for f in os.listdir(tpl_dir) if f.startswith(name) and f.endswith('.html')]
        if not cands:
            continue
        fn = os.path.join(tpl_dir, cands[0])
    src = open(fn, encoding='utf-8').read()
    me = re.search(r'<div class="eyebrow">\s*([^<]*?)\s*</div>', src)
    mh = re.search(r'<h1[^>]*>(.*?)</h1>', src, re.S)
    if not me or not mh:
        continue
    checked += 1
    eyebrow = me.group(1).strip()
    h1 = re.sub(r'<[^>]+>', '', mh.group(1))
    h1 = re.sub(r'\s+', ' ', h1).strip()
    # eyebrow показывает ТОЛЬКО раздел и совпадает с группой в меню.
    if eyebrow != group:
        bad.append((path, 'раздел «%s»' % group, 'eyebrow «%s»' % eyebrow))
        continue
    # в eyebrow больше НЕТ разделителя и названия страницы (это был дубль с <h1>).
    if '·' in me.group(0) or label.lower() in eyebrow.lower():
        bad.append((path, 'без повтора названия', 'eyebrow «%s»' % eyebrow))
        continue
    # у страницы есть осмысленный <h1>.
    if not h1:
        bad.append((path, 'непустой <h1>', 'пусто'))
if bad:
    for path, want, got in bad:
        check(False, f'{path}: ждём {want}, страница: {got}')
else:
    check(checked > 30, f'все страницы меню ({checked}) — eyebrow = раздел, название только в <h1>')

print('== 2. Всплывающие списки: в рамках экрана, следуют за полем ==')
pick = open(os.path.join(ROOT, 'web', 'static', 'pickers.js'), encoding='utf-8').read()
css = open(os.path.join(ROOT, 'web', 'static', 'style.css'), encoding='utf-8').read()

check('function placePop' in pick and "classList.toggle('up'" in pick,
      'pickers: позиционирование .sshd вверх/вниз (placePop/up)')
check("document.body.appendChild(pop)" in pick and 'sshd-pop-float' in pick,
      'pickers: список монтируется в body (fixed) и не обрезается overflow панели')
check('addEventListener(\'scroll\'' in pick and 'placePop' in pick,
      'pickers: при прокрутке список переставляется к полю (клики не промахиваются)')
check("list.style.maxHeight" in pick and 'maxHeight' in pick,
      'pickers: высота списка ограничена свободным местом')
check('stopPropagation' in pick,
      'pickers: клик по строке не всплывает на страницу (мимо не попадёт)')
check('.sshd-pop.sshd-pop-float' in css and '.mpd.mpd-floating' in css,
      'css: fixed-режим есть у .sshd-pop и .mpd')
check("listBox.style.maxHeight" in pick,
      'pickers: высота списка людей ограничена свободным местом')

print('== 3. Клики по каналам/участникам не «уезжают» при live ==')
ch = open(os.path.join(ROOT, 'web', 'templates', 'channels.html'), encoding='utf-8').read()
us = open(os.path.join(ROOT, 'web', 'templates', 'users.html'), encoding='utf-8').read()
cs = open(os.path.join(ROOT, 'web', 'templates', 'channel_settings.html'), encoding='utf-8').read()

check('chPressedRowId' in ch and 'chLastPointerDown' in ch,
      'channels: нажатая строка запоминается (pointerdown)')
check("performance.now() - chLastPointerDown < 350" in ch,
      'channels: live-перерисовка не идёт во время клика')
check('pressedMemberId' in us and 'lastListPointerDown' in us,
      'users: нажатый участник запоминается (mousedown)')
check("performance.now() - lastListPointerDown < 350" in us,
      'users: live-перерисовка не идёт во время клика')
check('-webkit-text-fill-color' in cs and 'select option' in cs,
      'channel-settings: имя канала в селекте всегда видно (fill-color + option)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
