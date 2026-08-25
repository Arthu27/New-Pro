# -*- coding: utf-8 -*-
"""Витрина ачивок в панели (идея #5).

Проверяем: агрегация payload по тому же хранилищу кога (охват/редкость/топ/
лента), имена из кэша бота с фолбэком ID, read-only права (mod читает,
uye/гость нет), шаблон без эмодзи и со светлой темой, меню.

Запуск: python3 tests/test_achievements_panel.py
"""
import importlib
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_achpanel_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'

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


from db import GuildData  # noqa: E402
from cogs import achievements as ACH  # noqa: E402
from web.routes import achievements_panel as AP  # noqa: E402

GID = 777

db = GuildData('achievements')
db.set(GID, 'user_111', {
    'messages': 120,
    'grants': ['first_words', 'talker_100'],
    'granted_at': {'first_words': '2026-08-10T10:00:00+00:00',
                   'talker_100': '2026-08-12T15:30:00+00:00'},
})
db.set(GID, 'user_222', {
    'messages': 3,
    'grants': ['first_words'],
    'granted_at': {'first_words': '2026-08-15T09:00:00+00:00'},
})
db.set(GID, 'user_333', {'messages': 40, 'grants': [], 'granted_at': {}})
db.set(GID, 'config', {'some': 'thing'})

print('== 1. Агрегация payload ==')
p = AP.achievements_payload(GID)
check(p['success'] and p['players'] == 2, 'игроки — только с грантами (user_333 вне зачёта)')
check(p['sum_points'] == 20 and p['sum_grants'] == 3, 'очки/гранты посчитаны')
expected_pts = ACH.total_points(['first_words', 'talker_100']) + ACH.total_points(['first_words'])
check(p['sum_points'] == expected_pts, 'очки = сумма total_points кога')
per_key = {c['key']: c['owners'] for c in p['catalog']}
check(per_key['first_words'] == 2 and per_key['talker_100'] == 1 and per_key['voice_1h'] == 0,
      'охват по ключам')
cov = {c['key']: c['coverage'] for c in p['catalog']}
check(cov['first_words'] == 100.0 and cov['talker_100'] == 50.0, 'coverage в процентах')
check(p['rarest'] == {'name': 'Говорун', 'owners': 1}, 'редчайшая — Говорун')
check(p['commonest'] == {'name': 'Первые слова', 'owners': 2}, 'массовейшая — Первые слова')
check(p['catalog_size'] == len(ACH.ACHIEVEMENTS) == 10, 'весь каталог на месте')
check(p['top'][0]['user_id'] == '111' and p['top'][0]['points'] == 15 and p['top'][0]['count'] == 2,
      'топ отсортирован по очкам')
check(p['top'][1]['user_id'] == '222', 'второй в топе')
check([r['ts'] for r in p['recent']] == sorted([r['ts'] for r in p['recent']], reverse=True),
      'лента по убыванию времени')
check(p['recent'][0]['ach_name'] == 'Первые слова' and p['recent'][0]['points'] == 5,
      'свежая запись с именем и очками ачивки')
check(p['top'][0]['name'] == 'ID 111', 'без бота — честный фолбэк ID')


class FakeMember:
    def __init__(self, name):
        self.display_name = name


class FakeGuild:
    id = 777

    def get_member(self, uid):
        return FakeMember('Мира') if uid == 111 else None


class FakeBot:
    def get_guild(self, gid):
        return FakeGuild() if gid == 777 else None


p2 = AP.achievements_payload(GID, bot=FakeBot())
check(p2['top'][0]['name'] == 'Мира', 'имя из кэша бота')
check(p2['top'][1]['name'] == 'ID 222', 'не в кэше — ID')

empty = AP.achievements_payload(424242)
check(empty['players'] == 0 and empty['rarest'] is None and empty['commonest'] is None
      and empty['catalog'] and empty['top'] == [], 'пустой сервер: честные пустышки, без падений')
cov0 = {c['coverage'] for c in empty['catalog']}
check(cov0 == {0}, 'без игроков coverage = 0 (деление защищено)')

print('== 2. API: права ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


check(client.get('/achievements').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get('/api/achievements/state').status_code in (302, 401, 403), 'гостю state закрыт')
login('uye')
check(client.get('/achievements').status_code == 403, 'uye нельзя')
check(client.get('/api/achievements/state').status_code == 403, 'uye нельзя state')
login('mod')
check(client.get('/achievements').status_code == 200, 'mod читает страницу (200)')
r = client.get('/api/achievements/state')
check(r.status_code == 200 and r.get_json()['players'] == 2, 'mod читает state (200)')

print('== 3. Шаблон и меню ==')
html = client.get('/achievements').get_data(as_text=True)
check('achKpis' in html and 'achCatalog' in html, 'страница монтирует блоки')
tpl = open(os.path.join(ROOT, 'web/templates/achievements.html'), encoding='utf-8').read()
emoji = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not emoji.search(tpl), 'в шаблоне нет эмодзи')
base_tpl = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('data-theme="light"' in base_tpl, 'светлая тема учтена (общий shell)')
check('methods' not in tpl.lower() or 'POST' not in tpl, 'шаблон честно read-only: нет POST-форм')
import services.panel_menu as PM
paths = [pg['path'] for g in PM.MENU for pg in g['pages']]
# Достижения «пока что» выключены: пункт скрыт из меню, но страница
# жива (PAGE_COGS и роут на месте) и честно показывает баннер.
check('/achievements' not in paths, 'пункт меню «Ачивки» скрыт (выключено владельцем)')
check('/achievements' in getattr(PM, 'HIDDEN_PATHS', []), 'путь назван в HIDDEN_PATHS')
check(PM.PAGE_COGS.get('/achievements') == ('achievements',), 'PAGE_COGS привязан к achievements')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
