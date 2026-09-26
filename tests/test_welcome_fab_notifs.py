# -*- coding: utf-8 -*-
"""Уведомления колокольчика: message из API + FAB «+» кликабелен.

Баги:
  • /api/my-notifications отдаёт message, drawer читал только body/detail —
    личные уведомления пустые.
  • FAB backdrop имел класс «fab backdrop» и наследовал layout кнопки;
    закрытые fab-item перехватывали клики (opacity:0 без pointer-events:none).

Запуск: python3 tests/test_welcome_fab_notifs.py
"""
import os
import re
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_fab_notif_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


js = open(os.path.join(ROOT, 'web/static/app.js'), encoding='utf-8').read()
css = open(os.path.join(ROOT, 'web/static/style.css'), encoding='utf-8').read()

print('== уведомления ==')
own = js[js.find('var ownItems'):js.find('var all = sysItems')]
check('n.message' in own and 'n.body' in own,
      'ownItems: body || message || detail')
check("комнат" in js and "syn = 'канал'" in js,
      'поиск меню: синоним комнат→канал')

print('== FAB + ==')
fab = js[js.find('function fabInit'):js.find('function tourStart')]
check("className = 'fab-backdrop'" in fab or 'fab-backdrop' in fab,
      'backdrop без класса .fab (не ломает layout)')
check("className = 'fab backdrop'" not in fab,
      'старый «fab backdrop» убран')
check('stopPropagation' in fab and 'preventDefault' in fab,
      'клик по «+» не всплывает впустую')
check("'/events'" in fab, 'FAB знает про /events')
check('items.length' in fab or '!items.length' in fab,
      'пустой FAB не оставляем без fallback')

check('pointer-events: none' in css and '.fab.open .fab-item' in css,
      'закрытые fab-item не перехватывают клик')
check('.fab-backdrop' in css, 'стили .fab-backdrop есть')
check('z-index: 2250' in css or 'z-index:2250' in css,
      'FAB выше mobile-nav (2200)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
