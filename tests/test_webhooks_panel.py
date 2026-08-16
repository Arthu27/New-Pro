# -*- coding: utf-8 -*-
"""Менеджер вебхуков в панели (идея #9).

Проверяем: payload (маска URL с токеном, сортировка), интероп с файлом кога
(запись формата /webhook видна в панели и обратно), create через фейк-бота
с реальным циклом (create_webhook исполнен), delete (запись уходит всегда,
Discord-удаление по возможности), send через monkeypatch транспорта,
права mod/admin, ошибки 400/404/503, монтаж шаблона и меню.

Запуск: python3 tests/test_webhooks_panel.py
"""
import asyncio
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
import threading

_TMP = tempfile.mkdtemp(prefix='aether_whpanel_test_')
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


from web.routes import webhooks_panel as WP  # noqa: E402

print('== 1. Чистые: файл/маска/payload ==')
check(WP.mask_url('https://discord.com/api/webhooks/123/SECRET').endswith('/123/•••'),
      'токен в маске не светится')
check('SECRET' not in WP.mask_url('https://discord.com/api/webhooks/123/SECRET'), 'секрет вырезан')
check(WP.mask_url('') == '•••', 'пустой url — безопасно')
check(WP.hooks_payload(777)['total'] == 0, 'пусто без файла')
# запись ровно в формате кога
cog_style = {'55': {'id': '55', 'name': 'Релизы', 'url': 'https://discord.com/api/webhooks/55/TOK',
                    'channel_id': '500', 'channel_name': 'news'}}
with open('data/webhooks_777.json', 'w', encoding='utf-8') as f:
    json.dump(cog_style, f)
p = WP.hooks_payload(777)
check(p['total'] == 1 and p['hooks'][0]['name'] == 'Релизы', 'запись кога читается')
check('TOK' not in p['hooks'][0]['url_masked'], 'токен не утёк в payload')
check(p['hooks'][0]['channel_name'] == 'news', 'канал на месте')
with open('data/webhooks_888.json', 'w', encoding='utf-8') as f:
    f.write('{битый')
check(WP.hooks_payload(888)['total'] == 0, 'битый JSON — пусто, не падаем')

print('== 2. API: права ==')
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


check(client.get('/api/webhooks').status_code in (302, 401, 403), 'гостю закрыто')
login('uye')
check(client.get('/api/webhooks').status_code == 403, 'uye нельзя')
login('mod')
check(client.get('/api/webhooks').status_code == 200, 'mod читает реестр (200)')
check(post('/api/webhooks/create', {'channel_id': 500, 'name': 'x'})[0] == 403, 'mod не создаёт (403)')
check(post('/api/webhooks/delete', {'webhook_id': '55'})[0] == 403, 'mod не удаляет (403)')

print('== 3. Create через цикл бота (формат совместим с когом) ==')


class FakeWh:
    def __init__(self):
        self.id = 9001
        self.url = 'https://discord.com/api/webhooks/9001/TOK2'


class FakeChannel:
    def __init__(self, cid, name):
        self.id = cid
        self.name = name
        self.created = []
        self.deleted = []

    async def create_webhook(self, name=None):
        self.created.append(name)
        return FakeWh()

    async def webhooks(self):
        fake = FakeWh()
        fake.id = 55

        async def _del():
            self.deleted.append(55)
        fake.delete = _del
        fake.name = 'Релизы'
        return [fake]


class FakeGuild:
    def __init__(self):
        self.id = 777
        self._ch = FakeChannel(501, 'релизы')
        self._ch2 = FakeChannel(500, 'news')

    def get_channel(self, cid):
        return {501: self._ch, 500: self._ch2}.get(cid)


class FakeBot:
    def __init__(self):
        self.guild = FakeGuild()
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

    def get_guild(self, gid):
        return self.guild if gid == 777 else None


old_bot = appmod.bot_instance
appmod.bot_instance = None
login('owner')
code, body = post('/api/webhooks/create', {'channel_id': 501, 'name': 'GH'})
check(code == 503 and 'Бот офлайн' in (body.get('error') or ''), 'бот офлайн — 503')

bot = FakeBot()
appmod.bot_instance = bot
code, body = post('/api/webhooks/create', {'channel_id': 'zz', 'name': 'x'})
check(code == 400, 'кривой канал — 400')
code, body = post('/api/webhooks/create', {'channel_id': 501, 'name': ''})
check(code == 400 and 'имя' in (body.get('error') or ''), 'пустое имя — 400')
code, body = post('/api/webhooks/create', {'channel_id': 999, 'name': 'x'})
check(code == 404, 'канала нет в кэше — 404')
code, body = post('/api/webhooks/create', {'channel_id': 501, 'name': 'GitHub'})
check(code == 200 and body['total'] == 2, 'создан (к юзерской записи добавилась новая)')
check(bot.guild._ch.created == ['GitHub'], 'Discord-вызов create_webhook исполнен')
saved = WP.load_hooks(777)
check(saved['9001']['url'].endswith('/9001/TOK2') and saved['9001']['channel_name'] == 'релизы',
      'запись — тот же формат, что пишет ког (url/name/channel)')
check(saved['55']['name'] == 'Релизы', 'коговская запись не пострадала')

print('== 4. Delete: запись всегда, Discord по возможности ==')
code, body = post('/api/webhooks/delete', {'webhook_id': '0000'})
check(code == 404, 'нет такого — 404')
code, body = post('/api/webhooks/delete', {'webhook_id': '55'})
check(code == 200 and '55' not in WP.load_hooks(777), 'запись снята')
check(bot.guild._ch2.deleted == [55], 'Discord-хук тоже удалён (канал был в кэше)')
code, body = post('/api/webhooks/delete', {'webhook_id': '9001'})
check(code == 200 and WP.hooks_payload(777)['total'] == 0, 'вторая снята (канал 501 живой, id 9001 не найден — молча)')

print('== 5. Send: транспорт monkeypatch, тексты ошибок ==')
sent = []


async def fake_deliver(url, content, username):
    sent.append((url, content, username))


orig = WP.deliver_webhook
WP.deliver_webhook = fake_deliver
with open('data/webhooks_777.json', 'w', encoding='utf-8') as f:
    json.dump(cog_style, f)
code, body = post('/api/webhooks/send', {'webhook_id': '55', 'message': 'привет'})
check(code == 200 and body['sent_to'] == 'Релизы', 'тест отправлен')
check(sent and sent[0][0].endswith('/55/TOK') and sent[0][2] == 'Релизы',
      'транспорт получил url/текст/имя коговской записи')
code, body = post('/api/webhooks/send', {'webhook_id': '55', 'message': '  '})
check(code == 400, 'пустое — 400')
code, body = post('/api/webhooks/send', {'webhook_id': '42', 'message': 'x'})
check(code == 404, 'нет хука — 404')
WP.deliver_webhook = orig
bot.loop.call_soon_threadsafe(bot.loop.stop)
appmod.bot_instance = old_bot

print('== 6. Страница и шаблон ==')
check(client.get('/webhooks').status_code == 200, 'страница открывается (200)')
src = open(os.path.join(ROOT, 'web', 'templates', 'webhooks.html'), encoding='utf-8').read()
for token in ('/api/webhooks/create', '/api/webhooks/delete', '/api/webhooks/send',
              'askConfirm', 'sk-row', 'url_masked', '/webhook список',
              "role == 'admin' or role == 'owner'"):
    assert token in src, token
check(True, 'монтаж, confirm на удаление, маска, скелетоны')
check('esc(h.name)' in src and 'esc(h.url_masked)' in src, 'esc() на месте')
EMOJI = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not EMOJI.search(src), 'эмодзи нет')
menu = open(os.path.join(ROOT, 'services', 'panel_menu.py'), encoding='utf-8').read()
check("'/webhooks'" in menu and "'label': 'Вебхуки'" in menu, 'пункт меню добавлен')
check("'/webhooks': ('webhooks',)" in menu, 'карта когов знает страницу')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
