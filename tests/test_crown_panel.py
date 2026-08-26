# -*- coding: utf-8 -*-
"""Зал корон в панели (идея #7): история коронаций + серии побед.

Проверяем: чистые crown_history (ISO-неделя в поясе, cap, мусор-фильтр) и
crown_streaks (текущая/лучшая серия), что ког пишет историю при коронации
(crown_now через FakeGuild), payload (свежие сверху, имена, серии), API-права,
монтаж шаблона и меню.

Запуск: python3 tests/test_crown_panel.py
"""
import asyncio
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='hakumo_crownpanel_test_')
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


from cogs import weekly_crown as W  # noqa: E402
from web.routes import crown_panel as CP  # noqa: E402

print('== 1. crown_history (чистая) ==')
cfg = {'history': [{'week': '2026-W30', 'uid': 5, 'dm': 10, 'dv': 5, 'score': 15, 'ts': 'x'}, 'мусор']}
hist = W.crown_history(cfg, uid=7, dm=20, dv=30, score=50, tz_offset=3)
check(len(hist) == 2 and hist[0]['week'] == '2026-W30', 'прошлая запись жива, мусор выкинут')
check(re.match(r'^\d{4}-W\d{2}$', hist[1]['week']), 'ISO-неделя: ' + hist[1]['week'])
check(hist[1]['uid'] == 7 and hist[1]['score'] == 50 and hist[1]['dm'] == 20 and hist[1]['dv'] == 30,
      'статы записаны')
check(hist[1]['ts'], 'отметка времени есть')
check(cfg['history'][0]['week'] == '2026-W30' and len(cfg['history']) == 2,
      'cfg не мутирован (чистая возвращает копию)')
cfg2 = {'history': [{'week': f'W{i}', 'uid': i} for i in range(W.HISTORY_CAP)]}
hist2 = W.crown_history(cfg2, uid=99, dm=1, dv=1, score=2, tz_offset='плохо')
check(len(hist2) == W.HISTORY_CAP and hist2[-1]['uid'] == 99 and hist2[0]['uid'] == 1,
      f'cap {W.HISTORY_CAP} держится, самая старая отрезана, кривой пояс мягко = 3')

print('== 2. crown_streaks ==')
mk = lambda uid: {'uid': uid}
s = W.crown_streaks([])
check(s == {'current_uid': None, 'current': 0, 'best_uid': None, 'best': 0}, 'пусто — нули')
s = W.crown_streaks([mk(1), mk(1), mk(2), mk(1), mk(1), mk(1)])
check(s['current_uid'] == 1 and s['current'] == 3, 'текущая серия последнего — 3')
check(s['best_uid'] == 1 and s['best'] == 3, 'лучшая — 3 (хвост)')
s = W.crown_streaks([mk(2), mk(2), mk(2), mk(2), mk(1)])
check(s['current'] == 1 and s['best'] == 4 and s['best_uid'] == 2, 'лучшая в прошлом не теряется')

print('== 3. Ког пишет историю при коронации ==')
run = asyncio.get_event_loop().run_until_complete


class FakeRole:
    id = 42
    name = 'Чемпион недели'
    mention = '@role'


class FakeMember:
    def __init__(self, uid):
        self.id = uid
        self.bot = False
        self.roles = []
        self.mention = f'<@{uid}>'
        self.display_name = f'Юзер{uid}'
        self.display_avatar = SimpleNamespace(url='')

    def __str__(self):
        return self.display_name


class FakeChan:
    def __init__(self):
        self.sent = []

    async def send(self, **kw):
        self.sent.append(kw)


class FakeGuild2:
    def __init__(self):
        self.id = 777
        self.name = 'Тест'
        self.system_channel = None
        self._m = FakeMember(7)
        self._role = FakeRole()

    def get_member(self, uid):
        return self._m if uid == 7 else None

    def get_role(self, rid):
        return self._role if rid == 42 else None

    async def create_role(self, **kw):
        return self._role

    def get_channel(self, cid):
        return None

    @property
    def text_channels(self):
        return []


os.makedirs('data', exist_ok=True)
with open(f'data/leaderboard_777.json', 'w', encoding='utf-8') as f:
    json.dump({'messages': {'7': 25}}, f)

cog = W.WeeklyCrown.__new__(W.WeeklyCrown)
cog.bot = SimpleNamespace(guilds=[])
cog._state = {'777': {'enabled': True, 'role_id': 42, 'channel_id': 0,
                      'tz_offset': 3, 'last_week': '', 'holder_id': 0, 'snapshot': {}}}
g = FakeGuild2()
res = run(cog.crown_now(g))
check(res is not None and res[0].id == 7, 'коронация прошла (чемпион 7)')
hist = cog._state['777'].get('history', [])
check(len(hist) == 1 and hist[0]['uid'] == 7 and hist[0]['dm'] == 25,
      'история записана когом с дельтой сообщений')
check(cog._state['777'].get('holder_id') == 7, 'держатель обновлён как раньше')

print('== 4. Payload панели ==')
cog._state['777']['history'] = [
    {'week': '2026-W31', 'uid': 5, 'dm': 1, 'dv': 1, 'score': 2, 'ts': 'a'},
    {'week': '2026-W32', 'uid': 7, 'dm': 3, 'dv': 2, 'score': 5, 'ts': 'b'},
    {'week': '2026-W33', 'uid': 7, 'dm': 4, 'dv': 4, 'score': 8, 'ts': 'c'},
]
W._save(cog._state)
p = CP.crown_payload(777, bot=None)
check(p['total'] == 3 and p['history'][0]['week'] == '2026-W33', 'свежие сверху')
check(p['history'][0]['name'] == 'ID 7', 'бот офлайн — честный ID')
check(p['current_streak']['n'] == 2 and p['current_streak']['uid'] == '7', 'текущая серия 2')
check(p['best_streak']['n'] == 2, 'лучшая серия 2')
check(p['holder_name'] == 'ID 7' and p['enabled'], 'держатель и статус на месте')

print('== 5. API ==')
appmod = importlib.import_module('web.app')
app = appmod.app
app.config['TESTING'] = True
client = app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


check(client.get('/api/crown/state').status_code in (302, 401, 403), 'гостю закрыто')
login('uye')
check(client.get('/api/crown/state').status_code == 403, 'uye нельзя')
login('mod')
r = client.get('/api/crown/state')
check(r.status_code == 200 and r.get_json()['total'] == 3, 'mod читает зал (200)')
body = r.get_json()
check({'history', 'current_streak', 'best_streak', 'holder_name', 'tz_offset'} <= set(body),
      'форма payload полная')

print('== 6. Страница и шаблон ==')
check(client.get('/crown').status_code == 200, 'страница открывается (200)')
src = open(os.path.join(ROOT, 'web', 'templates', 'crown.html'), encoding='utf-8').read()
for token in ('/api/crown/state', 'cr-table', '/crown now', 'sk-row', 'fa-crown',
              'renderSafe'):
    assert token in src, token
check(True, 'монтаж на месте, подсказки про Discord-команды честные')
check('esc(h.name)' in src and 'esc(d.holder_name)' in src, 'поля через esc()')
EMOJI = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not EMOJI.search(src), 'эмодзи нет (даже цитатная корона — иконка FA)')
menu = open(os.path.join(ROOT, 'services', 'panel_menu.py'), encoding='utf-8').read()
check("'/crown'" in menu and "'label': 'Зал корон'" in menu, 'пункт меню добавлен')
check("'/crown': ('weekly_crown',)" in menu, 'карта когов знает страницу')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
