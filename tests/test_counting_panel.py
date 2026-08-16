# -*- coding: utf-8 -*-
"""Комната счёта в панели: статус 1:1 с /счёт статус, вкл/выкл канала.

Проверяем: payload (числа, последний сбой, строки кога 1:1), API права
(mod читает, admin пишет), включение канала (реальный канал из кэша бота,
свежий стейт — зеркало «/счёт канал»), выключение (рекорд сохраняется,
зеркало «/счёт выкл»), ошибки 400/404/503, монтаж шаблона и меню.

Запуск: python3 tests/test_counting_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone

_TMP = tempfile.mkdtemp(prefix='aether_cntpanel_test_')
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


from cogs import counting as C  # noqa: E402
from db import GuildData  # noqa: E402
from web.routes import counting_panel as CP  # noqa: E402

UTC = timezone.utc

print('== 1. Payload: зеркала состояния кога ==')
state = C.empty_state(channel_id=500)
now = datetime.now(UTC)
state, ok = None, None
st = C.empty_state(500)
res, st = C.try_count(st, 11, 'Петя', '1', now)
res, st = C.try_count(st, 12, 'Света', '2', now)
res, st = C.try_count(st, 12, 'Света', '3', now)  # тот же юзер — падение
check(res == 'same_user' and st['next'] == 1 and st['fails'] == 1, 'состояние после сбоя (ког)')
GuildData('counting').set(777, 'state', st)

p = CP.counting_payload(777, bot=None)
check(p['success'] and p['active'] and p['channel_id'] == '500', 'активна, канал виден')
check(p['current'] == 0 and p['next'] == 1, 'после падения ждём 1, досчитали до 0')
check(p['best'] == 2 and p['fails'] == 1, 'рекорд 2, одно падение')
check(p['fail_reason'] == 'same_user', 'причина последнего сбоя на месте')
check(p['status_lines'] == C.status_lines(st), 'строки статуса — прямо из кога (1:1)')

print('== 2. Выключенное состояние ==')
GuildData('counting').set(888, 'state', C.empty_state())
p = CP.counting_payload(888, bot=None)
check(not p['active'] and 'Считалка выключена' in p['status_lines'][0],
      'выключено — строка кога про включение')

print('== 3. API: права и включение канала ==')
appmod = importlib.import_module('web.app')
app = appmod.app
app.config['TESTING'] = True
client = app.test_client()


class FakeChannel:
    def __init__(self, cid, name):
        self.id = cid
        self.name = name


class FakeGuild:
    def __init__(self):
        self.id = 777
        self.channels = [FakeChannel(500, 'счёт'), FakeChannel(501, 'флуд')]

    def get_channel(self, cid):
        for c in self.channels:
            if c.id == cid:
                return c
        return None


class FakeBot:
    def __init__(self):
        self.guilds = [FakeGuild()]

    def get_guild(self, gid):
        return self.guilds[0] if gid == 777 else None


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


def post(path, payload):
    r = client.post(path, data=json.dumps(payload), content_type='application/json')
    try:
        return r.status_code, r.get_json()
    except Exception:
        return r.status_code, {'raw': r.data[:200]}


check(client.get('/api/counting/state').status_code in (302, 401, 403), 'гостю закрыто')
login('uye')
check(client.get('/api/counting/state').status_code == 403, 'uye нельзя')
login('mod')
check(client.get('/api/counting/state').status_code == 200, 'mod читает (200)')
check(post('/api/counting/channel', {'channel_id': 500})[0] == 403, 'mod не переключает (403)')

login('owner')
old_bot = appmod.bot_instance
appmod.bot_instance = None
code, body = post('/api/counting/channel', {'channel_id': 500})
check(code == 503 and 'Бот офлайн' in (body.get('error') or ''), 'бот офлайн — честная 503')
appmod.bot_instance = FakeBot()
code, body = post('/api/counting/channel', {'channel_id': 'ab'})
check(code == 400 and 'число' in (body.get('error') or ''), 'кривой id — 400')
code, body = post('/api/counting/channel', {'channel_id': 999})
check(code == 404 and 'нет текстового канала' in (body.get('error') or ''), 'нет такого — 404')

code, body = post('/api/counting/channel', {'channel_id': 501})
check(code == 200 and body['active'] and body['channel_name'] == 'флуд',
      'включено в #флуд, имя канала подтянуто')
st = GuildData('counting').get(777, 'state', {})
check(st['channel_id'] == 501 and st['next'] == 1 and st['best'] == 0,
      'стейт свежий — зеркало /счёт канал (рекорд обнуляется со стейтом)')

print('== 4. Выключение сохраняет рекорд ==')
st['best'] = 42
st['fails'] = 3
GuildData('counting').set(777, 'state', st)
code, body = post('/api/counting/off', {})
check(code == 200 and not body['active'], 'выключено')
st = GuildData('counting').get(777, 'state', {})
check(st['best'] == 42 and st['fails'] == 3 and st['channel_id'] == 0,
      'рекорд жив — зеркало /счёт выкл')
check('выключена' in body['status_lines'][0], 'строки кога снова про выключение')
appmod.bot_instance = old_bot

print('== 5. Страница и шаблон ==')
r = client.get('/counting')
check(r.status_code == 200, 'страница открывается (200)')
src = open(os.path.join(ROOT, 'web', 'templates', 'counting.html'), encoding='utf-8').read()
for token in ('/api/counting/state', '/api/counting/channel', '/api/counting/off',
              '/api/guild/', 'askConfirm', 'sk-card', '/счёт статус',
              "role == 'admin' or role == 'owner'", 'data-countup'):
    assert token in src, token
check(True, 'монтаж, каналы, confirm, скелетоны, счётчик-анимация')
check('esc(d.channel_name' in src and 'esc(d.last_user_name)' in src, 'поля через esc()')
EMOJI = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not EMOJI.search(src), 'эмодзи нет')
menu = open(os.path.join(ROOT, 'services', 'panel_menu.py'), encoding='utf-8').read()
check("'/counting'" in menu and "'label': 'Счёт'" in menu, 'пункт меню добавлен')
check("'/counting': ('counting',)" in menu, 'карта когов знает страницу')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
