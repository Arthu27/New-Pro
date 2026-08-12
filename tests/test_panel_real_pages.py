# -*- coding: utf-8 -*-
"""Тесты оживлённых страниц панели: /todo, /economy, /bot-settings + их API.

Запуск: python3 tests/test_panel_real_pages.py
"""
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_realpages_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


# ═══ 1. Хранилище задач (services/panel_todo) ════════════════════════════
print('== panel_todo: хранилище ==')
from services import panel_todo as todo  # noqa: E402

check(todo.list_tasks() == [], 'todo: пустой список на старте')
t1 = todo.add_task('Позвонить хостеру', 'ДемоОвнер')
t2 = todo.add_task('  Разобрать   логи  ', 'ДемоОвнер')
check(t1['id'] > 0 and t1['text'] == 'Позвонить хостеру', 'todo: id и текст корректны')
check(t2['text'] == 'Разобрать логи', 'todo: лишние пробелы схлопываются')
tasks = todo.list_tasks()
check(len(tasks) == 2 and tasks[0]['id'] == t2['id'], 'todo: новые сверху')
check(tasks[0]['author'] == 'ДемоОвнер' and tasks[0]['created'], 'todo: автор и дата сохраняются')
check(todo.toggle_task(t1['id']) is True, 'todo: toggle существующей')
check(todo.list_tasks()[1]['id'] == t1['id'] and todo.list_tasks()[1]['done'] is True,
      'todo: флаг done реально переключился')
check(todo.toggle_task(999999) is False, 'todo: toggle несуществующей → False')
check(todo.delete_task(t1['id']) is True and len(todo.list_tasks()) == 1, 'todo: удаление')
try:
    todo.add_task('   ')
    check(False, 'todo: пустой текст должен кидать ValueError')
except ValueError:
    check(True, 'todo: пустой текст → ValueError')
long_task = todo.add_task('х' * 300)
check(len(long_task['text']) <= todo.MAX_TEXT, f'todo: текст обрезается до {todo.MAX_TEXT} символов')
check(json.load(open(todo.PATH, encoding='utf-8')), 'todo: файл на диске и это валидный JSON')

# ═══ 2. Панель: доступы ══════════════════════════════════════════════════
print('== панель: доступы страниц ==')
from web.app import app as _flask_app, set_bot_instance  # noqa: E402


class FakeGuild:
    def __init__(self, gid):
        self.id = gid


class FakeBot:
    guilds = [FakeGuild(777)]
    latency = 0.03
    users = []

    def is_closed(self):
        return False

    def get_user(self, uid):
        return None

    async def change_presence(self, **kw):
        FakeBot.presence_applied = kw


# живой event-loop в потоке — _run_async (run_coroutine_threadsafe) требует bot.loop
import asyncio as _asyncio  # noqa: E402
import threading as _threading  # noqa: E402

_loop = _asyncio.new_event_loop()
_threading.Thread(target=_loop.run_forever, daemon=True).start()
FakeBot.loop = _loop

set_bot_instance(FakeBot())
client = _flask_app.test_client()


def login_as(role):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'PanelRP'
        s['role'] = role


for path, keeper in (('/todo', 'owner'), ('/economy', 'admin'), ('/bot-settings', 'owner')):
    with client.session_transaction() as s:      # честный «анонимный» запрос
        s.clear()
    r = client.get(path)
    check(r.status_code in (302, 401, 403), f'{path}: без логина закрыта ({r.status_code})')
    login_as('uye')
    check(client.get(path).status_code in (302, 403), f'{path}: uye не пускают')
    login_as(keeper)
    check(client.get(path).status_code == 200, f'{path}: {keeper} рендерит 200')

# ═══ 3. Страницы: разметка и честность (никаких фейков) ══════════════════
print('== панель: разметка ==')
login_as('owner')
page_todo = client.get('/todo').get_data(as_text=True)
TODO_MARKERS = ('id="stat-total"', 'id="stat-done"', 'id="stat-active"', 'id="new-todo"',
                'id="btn-add"', 'id="todo-body"', 'id="todo-count"', 'id="todo-toast"')
check(all(m in page_todo for m in TODO_MARKERS), 'todo: контейнеры на месте')
check("'/api/todo'" in page_todo and '/api/todo/add' in page_todo
      and '/api/todo/toggle' in page_todo and '/api/todo/delete' in page_todo,
      'todo: JS реально дёргает CRUD API')
check('Документацию обновить' not in page_todo and 'Задача yok' not in page_todo,
      'todo: хардкод-заглушка вычищена')
check('{%' not in page_todo and '{{' not in page_todo, 'todo: чистый рендер без Jinja-остатков')

login_as('admin')
page_eco = client.get('/economy').get_data(as_text=True)
ECO_MARKERS = ('id="stat-total"', 'id="stat-users"', 'id="stat-gems"', 'id="stat-richest"',
               'id="lb-body"', 'id="lb-count"', 'id="shop-grid"', 'id="shop-count"',
               'id="rich-body"', 'id="rich-count"', 'cat-card')
check(all(m in page_eco for m in ECO_MARKERS), 'economy: контейнеры на месте')
check('/api/economy/overview' in page_eco, 'economy: JS дёргает живой API')
check('{%' not in page_eco and '{{' not in page_eco, 'economy: чистый рендер')

login_as('owner')
page_bs = client.get('/bot-settings').get_data(as_text=True)
BS_MARKERS = ('id="bs-status"', 'id="bs-activity"', 'id="bs-text"', 'id="bs-save"',
              'id="bs-sync"', 'id="bs-sync-out"', 'id="bs-prefix"', 'id="bs-online"',
              'id="bs-guilds"', 'id="bs-version"', 'id="bs-toast"')
check(all(m in page_bs for m in BS_MARKERS), 'bot-settings: контейнеры на месте')
check('/api/bot-settings/presence' in page_bs and '/api/bot-settings/sync' in page_bs,
      'bot-settings: JS дёргает живые API')
check('tog-ai' not in page_bs and 'spam-action' not in page_bs,
      'bot-settings: фейковые тоглы ИИ/спама удалены')
check('{%' not in page_bs and '{{' not in page_bs, 'bot-settings: чистый рендер')

# ═══ 4. TODO API ═════════════════════════════════════════════════════════
print('== API: todo ==')
login_as('admin')
check(client.get('/api/todo').status_code in (302, 403), 'todo API: admin не owner → закрыто')
login_as('owner')
before = len(client.get('/api/todo').get_json()['tasks'])
r = client.post('/api/todo/add', json={'text': 'Проверка из API'})
d = r.get_json()
check(r.status_code == 200 and d['ok'] and d['task']['text'] == 'Проверка из API', 'todo API: добавление')
tid = d['task']['id']
after = client.get('/api/todo').get_json()['tasks']
check(len(after) == before + 1 and any(t['id'] == tid for t in after), 'todo API: задача видна в списке')
r = client.post('/api/todo/toggle', json={'id': tid})
cur = [t for t in client.get('/api/todo').get_json()['tasks'] if t['id'] == tid][0]
check(r.get_json()['ok'] and cur['done'] is True, 'todo API: toggle через API')
check(client.post('/api/todo/toggle', json={'id': 123456789}).status_code == 404,
      'todo API: toggle несуществующей → 404')
r = client.post('/api/todo/delete', json={'id': tid})
check(r.get_json()['ok'] and all(t['id'] != tid for t in client.get('/api/todo').get_json()['tasks']),
      'todo API: удаление через API')
check(client.post('/api/todo/add', json={'text': ''}).status_code == 400, 'todo API: пустой текст → 400')

# ═══ 5. ECONOMY API ══════════════════════════════════════════════════════
print('== API: economy ==')
from db import UserData  # noqa: E402

ec = UserData('economy')
# DB_PATH абсолютен (корень репо) — чистим неймспейс, чтобы тест был изолирован
for _uid in list(ec.get_all()):
    ec.delete(_uid)
ec.set(11111, {'balance': 500, 'bank': 1500, 'vault': 3})
ec.set(22222, {'balance': 9000, 'bank': 100, 'vault': 1})
ec.set(33333, {'balance': 50, 'bank': 50, 'vault': 0})

login_as('mod')
check(client.get('/api/economy/overview').status_code in (302, 403), 'economy API: mod мимо (admin+)')
login_as('admin')
d = client.get('/api/economy/overview').get_json()
check(d.get('ok') is True, 'economy API: ok')
check(d['users'] == 3, f"economy: 3 участника ({d['users']})")
check(d['in_circulation'] == 500 + 1500 + 9000 + 100 + 50 + 50, 'economy: оборот = сумма балансов+банков')
lb = d['leaderboard']
check(lb[0]['id'] == '22222' and lb[0]['total'] == 9100, 'economy: лидерборд по total desc')
check(lb[0]['name'] == 'ID 22222', 'economy: фолбэк имени, если бот юзера не знает')
rich = d['richest']
check(rich[0]['id'] == '11111' and rich[0]['bank'] == 1500, 'economy: топ банков отдельно')
cat = d['catalog']
check(len(cat) == 18 and all('price' in c and 'rarity' in c for c in cat), 'economy: каталог из ITEM_DETAILS (18 позиций)')
check(cat == sorted(cat, key=lambda c: c['price']), 'economy: каталог отсортирован по цене')

# ═══ 6. BOT SETTINGS API ═════════════════════════════════════════════════
print('== API: bot-settings ==')
login_as('admin')
check(client.get('/api/bot-settings').status_code in (302, 403), 'bot-settings API: admin мимо (owner)')
login_as('owner')
d = client.get('/api/bot-settings').get_json()
check(d['ok'] and d['prefix'] == '!' and 'discord_version' in d, 'bot-settings API: префикс/версия в ответе')
check(d['presence'] == {'status': 'idle', 'activity_type': 'listening',
                        'activity_text': '.gg/Aether'}, 'bot-settings API: дефолтный презенс')

r = client.post('/api/bot-settings/presence',
                json={'status': 'online', 'activity_type': 'playing', 'activity_text': 'на сервере Aether'})
d = r.get_json()
check(r.status_code == 200 and d['ok'], 'presence: валидное сохранение')
check(os.path.exists('data/bot_config.json'), 'presence: пишется тот же data/bot_config.json, что читает main.py')
on_disk = json.load(open('data/bot_config.json', encoding='utf-8'))
check(on_disk['status'] == 'online' and on_disk['activity_text'] == 'на сервере Aether',
      'presence: конфиг реально на диске')
check(getattr(FakeBot, 'presence_applied', {}).get('status').name == 'online', 'presence: применено живое к боту')
d2 = client.get('/api/bot-settings').get_json()
check(d2['presence']['status'] == 'online', 'presence: GET видит свежий конфиг')

check(client.post('/api/bot-settings/presence',
                  json={'status': 'bogus', 'activity_type': 'playing', 'activity_text': 'x'}).status_code == 400,
      'presence: неизвестный статус → 400')
check(client.post('/api/bot-settings/presence',
                  json={'status': 'online', 'activity_type': 'playing', 'activity_text': '   '}).status_code == 400,
      'presence: пустой текст → 400')
r = client.post('/api/bot-settings/presence',
                json={'status': 'idle', 'activity_type': 'watching', 'activity_text': 'я' * 200})
check(r.status_code == 200 and len(json.load(open('data/bot_config.json', encoding='utf-8'))['activity_text']) <= 80,
      'presence: длинный текст обрезается до 80')

# синк: у FakeBot нет tree → 503
r = client.post('/api/bot-settings/sync', json={})
check(r.status_code == 503, 'sync: бот без дерева команд → 503 с объяснением')


class FakeTree:
    async def sync(self):
        return [1, 2, 3]


class FakeBot2(FakeBot):
    tree = FakeTree()


set_bot_instance(FakeBot2())
r = client.post('/api/bot-settings/sync', json={})
d = r.get_json()
check(r.status_code == 200 and d['ok'] and d['synced'] == 3, 'sync: живой бот → synced=3')
set_bot_instance(FakeBot())

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
