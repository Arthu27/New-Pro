# -*- coding: utf-8 -*-
"""Вся панель в одном Nova-языке (v15 unify).

Проверяем: panel-nova v15, тема без purple/cream, меню-страницы
открываются, мобильные правила на месте. Настройки/API не ломаем.

Запуск: python3 tests/test_panel_all_pages_unify.py
"""
import importlib
import os
import re
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_panel_unify_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== 1. Nova v15 unify layer ==')
nova = open(os.path.join(ROOT, 'web', 'static', 'panel-nova.css'), encoding='utf-8').read()
check('Panel Unify ALL PAGES — v15' in nova or 'v15 ALL PAGES' in nova,
      'panel-nova.css помечен v15 all-pages')
check('.nv-theme-grid' in nova and '.nv-swatch' in nova,
      'тема: Nova swatches (без purple/cream UI)')
check('@media (max-width: 760px)' in nova and 'grid-template-columns: 1fr' in nova,
      'мобилка: колонка для grid/flex на ≤760')
check('touch-action: manipulation' in open(
    os.path.join(ROOT, 'web', 'static', 'style.css'), encoding='utf-8').read()
      or 'min-height: 42px' in nova,
      'тач-цели увеличены')

print('== 2. theme_settings без cream/purple ==')
ts = open(os.path.join(ROOT, 'web', 'templates', 'theme_settings.html'),
          encoding='utf-8').read()
check('#f5f1e8' not in ts and '#9b59b6' not in ts and '#4f46e5' not in ts,
      'theme_settings: нет cream/purple/indigo')
check('nv-theme-grid' in ts and 'setTheme' in ts, 'theme_settings на Nova-карточках')

print('== 3. шапки страниц ==')
tpl = os.path.join(ROOT, 'web', 'templates')
for name in ('ai_moderation.html', 'bot_diagnostics.html', 'dashboard.html',
             'announcements.html', 'member_dashboard.html', 'analytics.html'):
    raw = open(os.path.join(tpl, name), encoding='utf-8').read()
    check('page-head' in raw, f'{name}: page-head')

print('== 4. меню: страницы отвечают ==')
from services import panel_menu as PM  # noqa: E402
paths = [i['path'] for g in PM.MENU for i in g.get('pages', [])]
appmod = importlib.import_module('web.app')
client = appmod.app.test_client()
with client.session_transaction() as sess:
    sess.clear()
    sess['logged_in'] = True
    sess['username'] = 'admin'
    sess['role'] = 'owner'

ok_n = 0
bad = []
for path in paths:
    r = client.get(path)
    if r.status_code == 200:
        ok_n += 1
    else:
        bad.append((path, r.status_code))
check(ok_n >= len(paths) - 3,
      f'меню открывается: {ok_n}/{len(paths)} (допуск 3 редиректа/особо)')
if bad[:5]:
    print('  sample bad:', bad[:5])

# базовая оболочка Nova на любой странице
home = client.get('/').get_data(as_text=True)
check('panel-nova.css' in home and 'panel-nova' in home,
      'chrome грузит panel-nova')
check('click-guard.js' in home, 'click-guard на месте (тапы)')

print('== 5. репорты: вердикт всё ещё человеческий ==')
from services import reports_core as RC  # noqa: E402
from web.routes import reports_queue as RQ  # noqa: E402
import json
lab, kind = RQ._verdict_display(json.dumps(
    {'kind': 'none', 'label': 'Отклонено'}, ensure_ascii=True))
check(lab == 'Отклонено' and kind == 'none', 'verdict decode жив')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
