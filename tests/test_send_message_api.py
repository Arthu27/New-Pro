# -*- coding: utf-8 -*-
"""E2E панели «Отправить сообщение»: /api/send-message.

Регрессия по прод-жалобе: эндпоинт стрелял корутину «в никуда»
(run_coroutine_threadsafe без .result), сразу отвечал success — а любое
исключение из channel.send (нет прав, пустой текст, лимит 2000…) тонуло
в логе. Панель рисовала «Сообщение отправлено», в канале — тишина.

Проверяем: успех ЖДЁТ реальной отправки; ошибки Discord возвращаются
в JSON; валидация входа (канал/сообщение/длина) — честная.

Запуск: python3 tests/test_send_message_api.py
"""
import asyncio
import importlib
import json
import os
import sys
import tempfile
import threading

_TMP = tempfile.mkdtemp(prefix='aether_sendmsg_test_')
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
import shutil  # noqa: E402


class FakeTextChannel(discord.TextChannel):
    """Настоящий discord.TextChannel (isinstance!), но без протокола."""

    def __init__(self, cid, raise_on_send=None):
        self.id = cid
        self.name = 'general'
        self.sent = []
        self._raise = raise_on_send

    async def send(self, content):
        if self._raise is not None:
            raise self._raise
        self.sent.append(content)
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
    r = client.post('/api/send-message', data=json.dumps(payload),
                    content_type='application/json')
    try:
        return r.status_code, r.get_json()
    except Exception:
        return r.status_code, {'raw': r.data[:200]}


ok_ch = FakeTextChannel(101)
guild = FakeGuild(777, {101: ok_ch})
bot = FakeBot([guild])
appmod.set_bot_instance(bot)
login()

print('== 1. Без логина / без бота ==')
with client.session_transaction() as s:
    s.clear()
code, body = post({'guild_id': '777', 'channel_id': '101', 'message': 'hi'})
check(code in (302, 401, 403), f'без логина закрыто ({code})')
login()

appmod.set_bot_instance(None)
code, body = post({'guild_id': '777', 'channel_id': '101', 'message': 'hi'})
check(not body.get('success') and 'не в сети' in (body.get('error') or ''),
      f'бот офлайн -> честная ошибка: {body.get("error")}')
appmod.set_bot_instance(bot)

print('== 2. Валидация входа ==')
code, body = post({'guild_id': '777', 'channel_id': '101', 'message': ''})
check(not body.get('success') and body.get('error'), f'пустое сообщение отвергнуто: {body.get("error")}')
code, body = post({'guild_id': '777', 'channel_id': '101', 'message': '   '})
check(not body.get('success'), 'сообщение из пробелов отвергнуто')
code, body = post({'guild_id': '777', 'channel_id': '101', 'message': 'х' * 2001})
check(not body.get('success') and '2000' in (body.get('error') or ''),
      f'длиннее 2000 символов -> понятная ошибка: {body.get("error")}')
code, body = post({'guild_id': '999', 'channel_id': '101', 'message': 'hi'})
check(not body.get('success') and 'Сервер' in (body.get('error') or ''),
      f'чужой сервер -> ошибка: {body.get("error")}')
code, body = post({'guild_id': '777', 'channel_id': '555', 'message': 'hi'})
check(not body.get('success') and 'Канал' in (body.get('error') or ''),
      f'нет такого канала -> ошибка: {body.get("error")}')
check(ok_ch.sent == [], 'при всех ошибках ничего не ушло в канал')

print('== 3. Успех — отправка реально произошла до ответа ==')
code, body = post({'guild_id': '777', 'channel_id': '101', 'message': 'Привет из панели'})
check(body.get('success') is True, f'success: {body}')
check(ok_ch.sent == ['Привет из панели'],
      f'сообщение ДОСТАВЛЕНО в канал (а не обещано): {ok_ch.sent}')

print('== 4. Ошибка Discord видна, а не проглочена ==')
bad_ch = FakeTextChannel(102, raise_on_send=RuntimeError('Missing Permissions'))
guild._channels[102] = bad_ch
code, body = post({'guild_id': '777', 'channel_id': '102', 'message': 'test'})
check(not body.get('success'), f'при падении send success не возвращается: {body}')
check('Missing Permissions' in (body.get('error') or '') or 'Ошибка' in (body.get('error') or ''),
      f'текст ошибки дошёл до панели: {body.get("error")}')

print('== 5. Страница /send-command — фолбэк сервера без MAIN_GUILD_ID ==')
_check_env_backup = os.environ.pop('MAIN_GUILD_ID', None)
page = client.get('/send-command')
html = page.get_data(as_text=True)
check(page.status_code == 200, f'страница открывается ({page.status_code})')
check("const PREFERRED_GUILD = '777'" in html,
      'без MAIN_GUILD_ID в .env страница берёт первый сервер бота, а не пустой id')
if _check_env_backup:
    os.environ['MAIN_GUILD_ID'] = _check_env_backup

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
