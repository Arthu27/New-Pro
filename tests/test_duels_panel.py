# -*- coding: utf-8 -*-
"""Дуэльная арена в панели (идея #4).

Проверяем: payload по тому же хранилищу кога (KPI, топ в порядке top_duels,
винрейт из player_stats, горячие серии, свежесть по last_at), фолбэки имён,
пустой сервер, read-only права, шаблон, меню.

Запуск: python3 tests/test_duels_panel.py
"""
import importlib
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_duelspanel_test_')
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
from cogs import duels as DU  # noqa: E402
from web.routes import duels_panel as DP  # noqa: E402

GID = 777

# фикстура — через ту же чистую запись результатов, что жмёт сам ког
state = DU.empty_state()
DU.record_result(state, 111, 222, __import__('datetime').datetime(2026, 8, 14, 12, 0,
                                                                  tzinfo=__import__('datetime').timezone.utc))
DU.record_result(state, 111, 222, __import__('datetime').datetime(2026, 8, 14, 12, 5,
                                                                  tzinfo=__import__('datetime').timezone.utc))
DU.record_result(state, 222, 333, __import__('datetime').datetime(2026, 8, 15, 18, 40,
                                                                  tzinfo=__import__('datetime').timezone.utc))
GuildData('duels').set(GID, 'state', state)

print('== 1. Payload агрегация ==')
p = DP.duels_payload(GID)
check(p['success'] and p['total_duels'] == 3, 'всего дуэлей = 3')
check(p['players'] == 3, 'трое дуэлянтов')
check(p['best_streak_ever'] == 2, 'лучшая серия = 2')
check([r['user_id'] for r in p['top']] == [u for u, _w, _l in DU.top_duels(state, limit=10)],
      'порядок топа = top_duels кога')
top111 = p['top'][0]
check(top111['user_id'] == 111 and top111['wins'] == 2 and top111['losses'] == 0,
      'лидер 2:0')
check(top111['winrate'] == DU.player_stats(state, 111)['winrate'] == 100, 'винрейт из кога')
check(top111['streak'] == 2 and top111['best_streak'] == 2, 'серии на месте')
check(len(p['hot']) == 1 and p['hot'][0]['user_id'] == 111 and p['hot'][0]['streak'] == 2,
      'горячая серия только у лидера (2+)')
check(p['recent'][0]['user_id'] == 222 and p['recent'][0]['summary'] == '1:2',
      'свежесть по last_at: последний бой 222')
check(p['recent'][1]['user_id'] == 333, 'второй по свежести — 333')
check(p['top'][0]['name'] == 'ID 111', 'без бота — фолбэк ID')


class FakeMember:
    def __init__(self, name):
        self.display_name = name


class FakeGuild:
    id = 777

    def get_member(self, uid):
        return {'111': FakeMember('Вихрь'), '222': FakeMember('Гром')}.get(str(uid))


class FakeBot:
    def get_guild(self, gid):
        return FakeGuild() if gid == 777 else None


p2 = DP.duels_payload(GID, bot=FakeBot())
check(p2['top'][0]['name'] == 'Вихрь', 'имя из кэша бота')
check(p2['top'][1]['name'] == 'Гром', 'второе имя из кэша')
check(p2['top'][2]['name'] == 'ID 333', 'не в кэше — ID')

empty = DP.duels_payload(555000)
check(empty['total_duels'] == 0 and empty['players'] == 0 and empty['top'] == []
      and empty['hot'] == [] and empty['recent'] == [] and empty['best_streak_ever'] == 0,
      'пустой сервер: честные нули, без падений')

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


check(client.get('/duels').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get('/api/duels/state').status_code in (302, 401, 403), 'гостю state закрыт')
login('uye')
check(client.get('/duels').status_code == 403, 'uye нельзя')
login('mod')
check(client.get('/duels').status_code == 200, 'mod читает страницу (200)')
r = client.get('/api/duels/state')
check(r.status_code == 200 and r.get_json()['total_duels'] == 3, 'mod читает state (200)')

print('== 3. Шаблон и меню ==')
html = client.get('/duels').get_data(as_text=True)
check('dlKpis' in html and 'dlTop' in html, 'страница монтирует блоки')
tpl = open(os.path.join(ROOT, 'web/templates/duels.html'), encoding='utf-8').read()
emoji = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not emoji.search(tpl), 'в шаблоне нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
check("method: 'POST'" not in tpl, 'честно read-only: ни одного POST')
import services.panel_menu as PM
paths = [pg['path'] for g in PM.MENU for pg in g['pages']]
check('/duels' in paths, 'пункт меню «Дуэли» есть')
check(PM.PAGE_COGS.get('/duels') == ('duels',), 'PAGE_COGS привязан к duels')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
