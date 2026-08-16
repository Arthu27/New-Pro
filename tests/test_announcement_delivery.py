# -*- coding: utf-8 -*-
"""Объявления: /api/send-announcement с опциональной доставкой в Discord.

Раньше «Опубликовать объявление» писало JSON-файл — и всё: в Discord ничего
не уходило, члены сервера объявлений не видели. Теперь компаундер умеет
доставлять эмбед в выбранный канал (честно — результат доставки ждётся),
но лента панели работает и без канала.

Плюс статика обновлённых страниц: «Отправить сообщение» v2 (счётчик
символов, выбор сервера) и дашборд (селектор канала анонса).

Запуск: python3 tests/test_announcement_delivery.py
"""
import asyncio
import importlib
import json
import os
import shutil
import sys
import tempfile
import threading

_TMP = tempfile.mkdtemp(prefix='aether_ann_test_')
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


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


def post(payload):
    r = client.post('/api/send-announcement', data=json.dumps(payload),
                    content_type='application/json')
    try:
        return r.status_code, r.get_json()
    except Exception:
        return r.status_code, {'raw': r.data[:200]}


ok_ch = FakeTextChannel(404)
guild = FakeGuild(777, {404: ok_ch})
bot = FakeBot([guild])
appmod.set_bot_instance(bot)


def ann_file_entries():
    path = os.path.join('data', 'announcements.json')
    if not os.path.exists(path):
        return []
    return json.load(open(path, encoding='utf-8'))


print('== 1. Доступ и валидация ==')
code, body = post({'title': 't', 'message': 'm'})
check(code in (302, 401, 403), f'без логина закрыто ({code})')
login('owner')
code, body = post({'title': '', 'message': 'm'})
check(not body.get('success') and body.get('error'), 'пустой заголовок отвергнут')

print('== 2. Только лента панели (как раньше) ==')
code, body = post({'title': 'Планёрка', 'message': 'Завтра в 20:00'})
check(body.get('success') is True and body.get('delivered') is False, f'панельный анонс: {body}')
check('ленте панели' in (body.get('message') or ''), 'текст ответа честный: только лента')
entries = ann_file_entries()
check(len(entries) == 1 and entries[0]['delivered'] is False and entries[0]['channel_id'] is None,
      'запись в файле: без канала, delivered=False')

print('== 3. Доставка в Discord ==')
code, body = post({'title': 'Обнова', 'message': 'Залетело', 'guild_id': '777', 'channel_id': '404'})
check(body.get('success') is True and body.get('delivered') is True, f'доставлено: {body}')
check(len(ok_ch.sent) == 1, 'эмбед реально ушёл в канал ДО ответа')
emb = ok_ch.sent[0][1]
check(emb is not None and emb.title == 'Обнова' and emb.description == 'Залетело',
      'эмбед с заголовком и текстом')
entries = ann_file_entries()
check(entries[-1]['delivered'] is True and entries[-1]['channel_id'] == '404',
      'в файле зафиксирована доставка')

print('== 4. Доставка не удалась — но честно ==')
bad_ch = FakeTextChannel(405, raise_on_send=RuntimeError('Missing Access'))
guild._channels[405] = bad_ch
code, body = post({'title': 'Проверка', 'message': 'x', 'guild_id': '777', 'channel_id': '405'})
check(body.get('success') is True and body.get('delivered') is False,
      'панельная часть не ломается от сбоя Discord')
check('Missing Access' in (body.get('deliver_error') or ''), f'причина видна: {body.get("deliver_error")}')
check('не ушло' in (body.get('message') or ''), 'сообщение в UI предупреждает о недоставке')
entries = ann_file_entries()
check(entries[-1]['delivered'] is False and 'Missing Access' in entries[-1]['deliver_error'],
      'ошибка доставки записана в историю')

print('== 5. Edge: бот офлайн / канал не найден ==')
appmod.set_bot_instance(None)
code, body = post({'title': 't', 'message': 'm', 'guild_id': '777', 'channel_id': '404'})
check(body.get('success') is True and body.get('delivered') is False
      and 'не в сети' in (body.get('deliver_error') or ''),
      f'бот офлайн: {body.get("deliver_error")}')
appmod.set_bot_instance(bot)
code, body = post({'title': 't', 'message': 'm', 'guild_id': '777', 'channel_id': '999'})
check(body.get('delivered') is False and 'не найден' in (body.get('deliver_error') or ''),
      f'нет канала: {body.get("deliver_error")}')

print('== 6. Статика страниц ==')
dash = open(os.path.join(ROOT, 'web', 'templates', 'dashboard.html'), encoding='utf-8').read()
check('id="ann-channel"' in dash, 'дашборд: селектор канала анонса есть')
check('loadAnnChannels' in dash and "opt.value = c.id" in dash or 'o.value = c.id' in dash,
      'дашборд: каналы подгружаются из API')
page = open(os.path.join(ROOT, 'web', 'templates', 'send_command.html'), encoding='utf-8').read()
check("fetch('/api/guilds')" in page, 'send-command v2: реальный выбор сервера из /api/guilds')
check('id="char-counter"' in page and '/ 2000' in page, 'счётчик символов до 2000')
check('updateCounter()' in page and 'refreshSendState()' in page, 'живые состояния кнопки и счётчика')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
