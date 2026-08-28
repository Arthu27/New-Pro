# -*- coding: utf-8 -*-
"""Никаких выдуманных данных в панели (заказ владельца 2026-08-27:
«в панели загружаются данные, которых я не добавлял»).

Раньше при офлайн-боте/пустых данных панель подставляла зашитых в код
людей (sonya.staff, artem.mods, ecobar, dragon…) и фейковые цифры —
даже в боевом режиме. Теперь демо-состав живёт ТОЛЬКО в режиме
предпросмотра (DEMO_MODE=1 без бота); в бою — честные пустые данные.

1. /api/login/suggest: без бота и без members.json — пусто (нет ecobar).
2. Карточка участника: автодополнение без sonya/artem (только реальные).
3. Лвлинг: без данных — нули и пустой топ (никаких 184200 XP).
4. Таблицы лидеров: офлайн-рендер без выдуманных имён.
5. Контраст: в DEMO_MODE=1 демо-состав по-прежнему есть (превью живое).

Запуск: python3 tests/test_no_foreign_data.py
"""
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_no_foreign_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
os.environ['MAIN_GUILD_ID'] = '777'
os.environ.pop('DEMO_MODE', None)          # боевой режим: никаких демо

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


FAKE = ('sonya', 'artem', 'ecobar', 'dragon', 'hzdio', 'oberaru', 'meow_meow',
        'lina', 'kolyan', 'nastya', 'vanya', 'dasha', 'max')

import web.app as appmod  # noqa: E402

appmod.app.config['TESTING'] = True
appmod.bot_instance = None                 # бот офлайн — самый честный случай
client = appmod.app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'
    s['selected_guild'] = '777'

print('== 1. Подсказки логина: без бота — пусто, никаких «известных» людей ==')
d = client.get('/api/login/suggest').get_json()
check(d.get('success') and d.get('suggestions') == [],
      'пустой запрос без бота → пустой список')
d = client.post('/api/login/suggest', json={'q': 'ecobar'}).get_json()
check(d.get('suggestions') == [], 'поиск «ecobar» → ничего (в бою его нет)')
d = client.post('/api/login/suggest', json={'q': 'sonya'}).get_json()
check(d.get('suggestions') == [], 'поиск «sonya» → ничего')

print('== 2. Карточка участника: автодополнение без демо-людей ==')
from web.routes import member_card_panel as MC  # noqa: E402

pool = MC._name_pool('777')
leaked = [f for f in FAKE if any(f in str(n).lower() for n in pool.values())]
check(not leaked, f'в пуле имён нет зашитых людей ({leaked[:3]})')
check(MC.suggest('777', 'sonya') == [] and MC.suggest('777', 'ecobar') == [],
      'подсказки не находят демо-имена')

print('== 3. Лвлинг: без данных — честные нули, не выдуманный топ ==')
r = client.get('/api/leveling/stats')
d = r.get_json()
check(d.get('total_users') == 0 and d.get('total_xp') == 0,
      f"тоталы нулевые ({d.get('total_users')}/{d.get('total_xp')})")
check(d.get('top') == [], 'топ пуст — никаких sonya/ecobar/dragon с XP')

print('== 4. Таблицы лидеров: офлайн-рендер без выдуманных имён ==')
from web.routes import leaderboards_panel as LB  # noqa: E402

names = LB._demo_names()
leaked = [f for f in FAKE if any(f in str(v).lower() for v in names.values())]
check(not leaked, f'офлайн-карта имён без демо-людей ({leaked[:3]})')

print('== 5. Контраст: DEMO_MODE=1 (превью без бота) — демо-состав на месте ==')
os.environ['DEMO_MODE'] = '1'
try:
    check(appmod._demo_mode() is True, 'демо-режим включился')
    d = client.post('/api/login/suggest', json={'q': 'ecobar'}).get_json()
    check(any(x.get('name') == 'ecobar' for x in d.get('suggestions', [])),
          'в превью подсказки снова находят демо-состав')
    pool2 = MC._name_pool('777')
    check(any('sonya' in str(n).lower() for n in pool2.values()),
          'в превью пул имён содержит демо-участников')
finally:
    os.environ.pop('DEMO_MODE', None)

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
