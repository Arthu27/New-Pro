# -*- coding: utf-8 -*-
"""Живая история объявлений: статусы доставки и кнопка «Дослать».

Контекст: /api/send-announcement умеет доставлять эмбед в Discord, но если
доставка упала (бот офлайн, нет прав...), объявление навсегда оставалось
недошедшим — след был только в тексте ответа. Теперь у каждой записи есть
id, статус хранится в файле, страница /announcements показывает персоналу
чипы «В Discord / Не доставлено / Только в панели», а неудачу можно
дослать через POST /api/announcements/retry — снова честно, с ожиданием
реального результата отправки.

Проверяем: id у записей, миграция id на старых записях, авторизация и
валидация retry, успешная и неуспешная повторная доставка, персистентность
статуса, шаблон страницы (чипы/кнопка/живое обновление), пункт меню.

Запуск: python3 tests/test_announcements_history.py
"""
import asyncio
import importlib
import json
import os
import shutil
import sys
import tempfile
import threading

_TMP = tempfile.mkdtemp(prefix='aether_annhist_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'

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


import discord  # noqa: E402


class FakeTextChannel(discord.TextChannel):
    def __init__(self, cid, raise_on_send=None):
        self.id = cid
        self.name = 'ob-yavleniya'
        self.sent = []
        self._raise = raise_on_send

    async def send(self, content=None, embed=None):
        if self._raise is not None:
            raise self._raise
        self.sent.append((content, embed))
        return None


class FakeGuild:
    def __init__(self, gid, channels):
        self.id = gid
        self.name = 'TestGuild'
        self._channels = channels

    def get_channel(self, cid):
        return self._channels.get(cid)


class FakeBot:
    def __init__(self, guilds):
        self.guilds = guilds
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()


appmod = importlib.import_module('web.app')
app = appmod.app
app.config['TESTING'] = True
client = app.test_client()

ANN_PATH = os.path.join('data', 'announcements.json')


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


def reset_ann_file():
    if os.path.exists(ANN_PATH):
        os.remove(ANN_PATH)


def ann_file_entries():
    if not os.path.exists(ANN_PATH):
        return []
    with open(ANN_PATH, encoding='utf-8') as f:
        return json.load(f)


def post_ann(payload):
    r = client.post('/api/send-announcement', data=json.dumps(payload),
                    content_type='application/json')
    try:
        return r.status_code, r.get_json()
    except Exception:
        return r.status_code, {'raw': r.data[:200]}


def post_retry(payload):
    r = client.post('/api/announcements/retry', data=json.dumps(payload),
                    content_type='application/json')
    try:
        return r.status_code, r.get_json()
    except Exception:
        return r.status_code, {'raw': r.data[:200]}


ok_ch = FakeTextChannel(101)
guild = FakeGuild(777, {101: ok_ch})
bot = FakeBot([guild])

# ═══ 1. Миграция id на старой ленте (до «Дослать» записи были без id) ═════
print('== 1. Миграция id на старых записях ==')
reset_ann_file()
legacy = [{'title': 'Старое', 'message': 'x', 'from': 'admin', 'guild_id': '777',
           'channel_id': '101', 'delivered': False, 'deliver_error': 'кто-то упал',
           'created_at': '2026-08-15T10:00:00+00:00'},
          {'title': 'Панельное', 'message': 'y', 'from': 'admin', 'channel_id': None,
           'delivered': False, 'created_at': '2026-08-15T11:00:00+00:00'}]
with open(ANN_PATH, 'w', encoding='utf-8') as f:
    json.dump(legacy, f, ensure_ascii=False)
login()
r = client.get('/api/announcements')
data = r.get_json()
check(r.status_code == 200 and len(data) == 2, f'лента читается: {r.status_code}')
check(data[1].get('id', '').startswith('ann-'), 'старой записи с каналом выдан id')
check(not data[0].get('id'), 'панельной записи без канала id не нужен')
saved = ann_file_entries()
check(saved[0].get('id') == data[1]['id'], 'миграция id персистентна в файле')

# ═══ 2. Retry: авторизация и валидация ════════════════════════════════════
print('== 2. Авторизация и валидация retry ==')
with client.session_transaction() as s:
    s.clear()
code, body = post_retry({'id': data[1]['id']})
check(code in (302, 401, 403), f'гостю закрыто ({code})')
login('uye')
code, body = post_retry({'id': data[1]['id']})
check(code == 403 and body.get('error'), f'uye нельзя ({code})')
login('mod')
code, body = post_retry({})
check(code == 400 and 'id' in (body.get('error') or '').lower(), f'без id — 400: {body}')
code, body = post_retry({'id': 'ann-no-such'})
check(code == 404 and 'не найдено' in (body.get('error') or ''), f'неизвестный id — 404: {body}')

# ═══ 3. Панельное объявление дослать нельзя ═══════════════════════════════
print('== 3. Панельная запись — доставлять некуда ==')
appmod.set_bot_instance(bot)
code, body = post_ann({'title': 'Планёрка', 'message': 'Завтра в 20:00'})
check(body.get('success') is True, 'панельный анонс создан')
panel_rec = ann_file_entries()[-1]
check(panel_rec.get('id', '').startswith('ann-') and panel_rec['channel_id'] is None,
      'панельная запись: id есть, канала нет')
code, body = post_retry({'id': panel_rec['id']})
check(code == 400 and 'некуда' in (body.get('error') or ''), f'retry панельной — вежливый отказ: {body}')

# ═══ 4. Неудачная доставка → «Дослать» → успех ════════════════════════════
print('== 4. Упало → дослали → delivered=True персистентно ==')
appmod.set_bot_instance(None)
code, body = post_ann({'title': 'Обнова', 'message': 'Залетело', 'guild_id': '777', 'channel_id': '101'})
check(body.get('delivered') is False and 'не в сети' in (body.get('deliver_error') or ''),
      f'бот офлайн — не доставлено: {body.get("deliver_error")}')
rec = ann_file_entries()[-1]
check(rec.get('id') and rec['guild_id'] == '777' and rec['delivered'] is False,
      'запись упавшей доставки хранит id/guild_id/delivered=False')

appmod.set_bot_instance(bot)
sent_before = len(ok_ch.sent)
login('mod')
code, body = post_retry({'id': rec['id']})
check(code == 200 and body.get('success') is True, f'retry успешен: {body}')
check('Доставлено в #' in (body.get('message') or ''), 'ответ называет канал')
check(len(ok_ch.sent) == sent_before + 1, 'эмбед реально ушёл в канал ДО ответа')
saved = ann_file_entries()[-1]
check(saved['delivered'] is True and saved['deliver_error'] is None,
      'статус в файле переведён в delivered=True')
check(saved.get('redelivered_at') and saved.get('redelivered_by') == 'admin',
      'зафиксировано кто и когда дослал')
check(saved.get('channel_name') == 'ob-yavleniya', 'имя канала сохранено для истории')

code, body = post_retry({'id': rec['id']})
check(code == 400 and 'уже доставлено' in (body.get('error') or ''), f'повторный retry отвергнут: {body}')

# ═══ 5. Retry, который снова падает ═══════════════════════════════════════
print('== 5. Снова не ушло — честный 502 и статус без изменений ==')
bad_ch = FakeTextChannel(102, raise_on_send=RuntimeError('Missing Access'))
guild._channels[102] = bad_ch
code, body = post_ann({'title': 'Проверка', 'message': 'x', 'guild_id': '777', 'channel_id': '102'})
rec2 = ann_file_entries()[-1]
check(rec2['delivered'] is False and 'Missing Access' in (rec2.get('deliver_error') or ''),
      'упавшая доставка записана с причиной')
code, body = post_retry({'id': rec2['id']})
check(code == 502 and 'Снова не ушло' in (body.get('error') or ''), f'retry честно фейлится: {body}')
check('Missing Access' in (body.get('error') or ''), 'причина видна в ответе')
saved = ann_file_entries()[-1]
check(saved['delivered'] is False and saved.get('redelivered_at') is None,
      'статус остался недоставленным, даты досылы нет')

# ═══ 6. Старую запись (после миграции) тоже можно дослать ═════════════════
print('== 6. Мигрированная legacy-запись досылается ==')
legacy_id = ann_file_entries()[0]['id']
sent_before = len(ok_ch.sent)
code, body = post_retry({'id': legacy_id})
check(code == 200 and len(ok_ch.sent) == sent_before + 1, 'legacy-запись ушла в Discord')
check(ann_file_entries()[0]['delivered'] is True, 'статус legacy-записи обновлён в файле')

# ═══ 7. GET-лента: свежие сверху, поля на месте ═══════════════════════════
print('== 7. Лента целиком ==')
r = client.get('/api/announcements')
data = r.get_json()
check(len(data) == 5, f'все записи вернулись ({len(data)})')
check(data[0]['title'] == 'Проверка', 'свежая запись первая')
check(all('id' in a for a in data if a.get('channel_id')), 'у всех канальных записей есть id')

# ═══ 8. Страница и статика ════════════════════════════════════════════════
print('== 8. Страница /announcements и шаблон ==')
login('mod')
r = client.get('/announcements')
html = r.get_data(as_text=True)
check(r.status_code == 200, 'персоналу страница доступна (200)')
check('CAN_MANAGE = true' in html, 'мод видит управление доставкой')
login('uye')
r = client.get('/announcements')
html_u = r.get_data(as_text=True)
check(r.status_code == 200 and 'CAN_MANAGE = false' in html_u, 'участнику — чистая лента без чипов')

src = open(os.path.join(ROOT, 'web', 'templates', 'announcements.html'), encoding='utf-8').read()
for token in ('ann-chip', 'data-retry', '/api/announcements/retry', "box.className = 'ann-grid'",
              'redelivered_by', 'fa-rotate-right', 'setInterval'):
    assert token in src, token
check(True, 'шаблон: чипы, кнопка «Дослать», живое обновление — на месте')
import re
EMOJI = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not EMOJI.search(src), 'декоративных эмодзи в шаблоне нет (FA-иконки только)')

from services import panel_menu as pm
menu_paths = {it['path'] for g in pm.MENU for it in g['pages']}
check('/announcements' in menu_paths, 'пункт «Объявления» есть в меню персонала')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
