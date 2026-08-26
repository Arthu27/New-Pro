# -*- coding: utf-8 -*-
"""Журнал напоминаний в панели (модераторский обзор /напомни).

Проверяем: новые чистые функции кога (cancel_any/restore_item — отмена
чужих из панели и честный undo откатом done), payload журнала (сортировка,
просроченные, повторы, имена), API (права mod/admin, 400/404, текст ошибок),
полный цикл отменить → вернуть тем же API, монтаж шаблона и меню.

Запуск: python3 tests/test_reminders_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_rempanel_test_')
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


from cogs import reminders as R  # noqa: E402
from db import GuildData  # noqa: E402
from web.routes import reminders_panel as RP  # noqa: E402

UTC = timezone.utc
NOW = datetime.now(UTC)

print('== 1. Чистые cancel_any / restore_item ==')
state = R.empty_state()
item, err = R.create_reminder(state, 5, 10, 'продлить сервер', 'через 2ч', NOW, user_name='Ксюша')
check(item and err is None and item['id'] == 1, 'запись создана (1)')
item2, _ = R.create_reminder(state, 6, 10, 'вторая', 'через 3ч', NOW)
check(not R.cancel_any(state, 99), 'cancel_any мимо — False')
check(R.cancel_any(state, 1) and state['items'][0]['done'] is True, 'cancel_any снимает чужую (мод)')
check(not R.cancel_any(state, 1), 'повторная отмена — False (уже done)')
check(R.restore_item(state, 1) and state['items'][0]['done'] is False, 'restore_item — честный undo')
check(not R.restore_item(state, 2), 'restore активной — False (нечего возвращать)')

print('== 2. Payload журнала ==')
state['items'][0]['done'] = True  # вернём в done, чтобы просроченная отлежалась
old = {'id': 90, 'user_id': 7, 'user_name': '', 'channel_id': 10, 'text': 'старая',
       'due_at': (NOW - timedelta(hours=1)).isoformat(), 'created_at': NOW.isoformat(),
       'repeat_seconds': None, 'done': False}
rep = {'id': 91, 'user_id': 8, 'user_name': 'Миха', 'channel_id': 10, 'text': 'вода',
       'due_at': (NOW + timedelta(days=3)).isoformat(), 'created_at': NOW.isoformat(),
       'repeat_seconds': 86400, 'done': False}
soon = {'id': 92, 'user_id': 5, 'user_name': 'Ксюша', 'channel_id': 10, 'text': 'скоро',
        'due_at': (NOW + timedelta(minutes=30)).isoformat(), 'created_at': NOW.isoformat(),
        'repeat_seconds': None, 'done': False}
state['items'].extend([old, rep, soon])
GuildData('reminders').set(777, 'state', state)

p = RP.reminders_payload(777, bot=None, now=NOW)
check(p['success'] and p['total'] == 4, 'четыре активные (done не попадает)')
check(p['overdue'] == 1 and p['items'][-1]['text'] == 'вода' and p['items'][0]['id'] == 90,
      'сортировка: просроченные первые, дальние последние')
check(p['repeating'] == 1 and p['items'][-1]['repeat_seconds'] == 86400, 'повтор виден')
check(p['items'][0]['user_name'] == 'ID 7', 'без имени и бота — честный ID')
check([i for i in p['items'] if i['id'] == 91][0]['user_name'] == 'Миха', 'записанное имя показывается')

print('== 3. API: права и цикл ==')
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


def post(path, payload):
    r = client.post(path, data=json.dumps(payload), content_type='application/json')
    try:
        return r.status_code, r.get_json()
    except Exception:
        return r.status_code, {'raw': r.data[:200]}


check(client.get('/api/reminders/state').status_code in (302, 401, 403), 'гостю закрыто')
login('uye')
check(client.get('/api/reminders/state').status_code == 403, 'uye нельзя (403)')
login('mod')
check(client.get('/api/reminders/state').status_code == 200, 'mod читает журнал (200)')
check(post('/api/reminders/cancel', {'id': 90})[0] == 403, 'mod отменять чужие не может (403)')

login('owner')
code, body = post('/api/reminders/cancel', {'id': 'x'})
check(code == 400 and 'число' in (body.get('error') or ''), 'id не число — 400')
code, body = post('/api/reminders/cancel', {'id': 999})
check(code == 404 and 'не найдено' in (body.get('error') or ''), 'нет такой — 404')
code, body = post('/api/reminders/cancel', {'id': 90})
check(code == 200 and body['cancelled_id'] == 90 and body['total'] == 3, 'отменена, журнал пересчитан')
st = GuildData('reminders').get(777, 'state', {})
check([i for i in st['items'] if i['id'] == 90][0]['done'] is True, 'в хранилище done=True')
code, body = post('/api/reminders/cancel', {'id': 90})
check(code == 404, 'повторная отмена — честный 404')

print('== 4. Undo: restore через API ==')
code, body = post('/api/reminders/restore', {'id': 90})
check(code == 200 and body['total'] == 4, 'возвращена (undo честный)')
st = GuildData('reminders').get(777, 'state', {})
check([i for i in st['items'] if i['id'] == 90][0]['done'] is False, 'done откачен в False')
code, body = post('/api/reminders/restore', {'id': 91})
check(code == 404 and 'не отменено' in (body.get('error') or ''), 'любую активную вернуть нельзя (404)')

print('== 5. Страница и шаблон ==')
r = client.get('/reminders')
check(r.status_code == 200, 'страница открывается (200)')
src = open(os.path.join(ROOT, 'web', 'templates', 'reminders.html'), encoding='utf-8').read()
for token in ('/api/reminders/state', '/api/reminders/cancel', '/api/reminders/restore',
              'uxUndo', 'overdue', 'sk-row', "role == 'admin' or role == 'owner'",
              'fmtRepeat', '/напомни'):
    assert token in src, token
check(True, 'монтаж, undo, гейтинг, скелетоны на месте')
check('esc(it.text)' in src and 'esc(it.user_name)' in src, 'поля через esc()')
EMOJI = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not EMOJI.search(src), 'эмодзи нет')
menu = open(os.path.join(ROOT, 'services', 'panel_menu.py'), encoding='utf-8').read()
check("'/reminders'" in menu and "'label': 'Напоминания'" in menu, 'пункт меню добавлен')
check("'/reminders': ('reminders',)" in menu, 'карта когов знает страницу')

print('== 6. Ког не пострадал: свои команды как были ==')
check(R.cancel_item(state, 92, 5) is True, 'cancel_item (своя) жив')
check(R.cancel_item(state, 91, 999) is False, 'cancel_item чужую не трогает, как и раньше')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
