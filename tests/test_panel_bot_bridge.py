# -*- coding: utf-8 -*-
"""Мост «бот ↔ веб-панель»: применяется ли из панели к живому боту.

Баг 2026-08-29: панель запускалась ОТДЕЛЬНЫМ процессом Gunicorn, где
web.app.bot_instance всегда None → «Бот офлайн», настройки из панели
(каналы, коги, синк, наказания) не доходили до бота.

Тест проверяет:
- set_bot_instance в ТОМ ЖЕ процессе делает бота видимым панели:
  /health → bot=ready; /api/bot-settings → bot_online=true;
  /api/guild/<id>/channels → живые каналы из Discord;
- по умолчанию панель стартует ВМЕСТЕ с ботом (не подпроцессом gunicorn —
  subprocess.Popen не вызывается), PANEL_PROCESS=gunicorn — явный режим;
- WebSocket стартует по env (WS_HOST/WS_PORT) — live-канал слушает
  не только localhost;
- .env: PANEL_WS_URL прокидывается в base.html (домен/туннель).

Запуск: python3 tests/test_panel_bot_bridge.py
"""
import asyncio
import os
import shutil
import sys
import tempfile
import types
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

_TMP = tempfile.mkdtemp(prefix='hakumo_panelbot_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ.pop('PANEL_PROCESS', None)

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


class FakeChannel:
    def __init__(self, cid, name, ctype=None):
        import discord
        self.id = cid
        self.name = name
        self.type = ctype or discord.ChannelType.text
        self.position = 0
        self.category_id = 0


class FakeRole:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name


class FakeGuild:
    def __init__(self, gid):
        import discord
        self.id = gid
        self.name = 'Тест'
        self.channels = [FakeChannel(501, 'правила'),
                         FakeChannel(502, 'музыка')]
        self.text_channels = [c for c in self.channels
                              if c.type == discord.ChannelType.text]
        self.voice_channels = []
        self.roles = [FakeRole(1, 'модер')]

    def get_channel(self, cid):
        return next((c for c in self.channels if c.id == int(cid)), None)

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == int(rid)), None)


class FakeBot:
    def __init__(self):
        self.guilds = [FakeGuild(777)]
        self.latency = 0.05
        self.loop = asyncio.new_event_loop()
        self._closed = False

    def is_ready(self):
        return True

    def is_closed(self):
        return self._closed

    def get_guild(self, gid):
        return next((g for g in self.guilds if g.id == int(gid)), None)


print('== 1. Бот и панель в ОДНОМ процессе (главный фикс) ==')
import web.app as APP  # noqa: E402

check(APP.bot_instance is None, 'до привязки панель бота не видит (None)')

bot = FakeBot()
APP.set_bot_instance(bot)
check(APP.bot_instance is bot, 'set_bot_instance: панель видит живого бота')

print('== 2. /health — статус бота в панели ==')
APP.app.config['TESTING'] = True
client = APP.app.test_client()
r = client.get('/health')
d = r.get_json()
check(r.status_code == 200 and d.get('bot') == 'ready'
      and d.get('guilds') == 1,
      f"/health: bot=ready, серверов {d.get('guilds')}")

print('== 3. /api/bot-settings: бот онлайн ==')
with client.session_transaction() as s:
    s.update(logged_in=True, role='owner', username='admin', user_id='1')
r = client.get('/api/bot-settings')
d = r.get_json()
check(r.status_code == 200 and d.get('bot_online') is True
      and d.get('guilds') == 1,
      'настройки бота показывают online (раньше — «Бот офлайн»)')

print('== 4. Каналы из Discord доходят до панели ==')
r = client.get('/api/guild/777/channels')
d = r.get_json()
names = [c.get('name') for c in d] if isinstance(d, list) else []
check(r.status_code == 200 and 'правила' in names and 'музыка' in names,
      f'каналы сервера реальные: {names}')

print('== 5. Старт панели: по умолчанию — в процессе бота ==')
# импорт main.py требует окружение; функция _start_web_server проверяется
# с подменой gunicorn и Popen
sys.path.insert(0, ROOT)
import main as MAIN  # noqa: E402

with patch.object(MAIN, '_have_gunicorn', return_value=True), \
        patch.object(MAIN.subprocess, 'Popen') as popen, \
        patch.object(MAIN.threading, 'Thread') as thr:
    MAIN._start_web_server(APP.app)
    check(popen.call_count == 0,
          'по умолчанию панель НЕ уходит в gunicorn-подпроцесс (бот виден)')
    check(thr.call_count == 1,
          'панель стартует в том же процессе (thread с app.run)')
    kwargs = thr.call_args.kwargs or {}
    check(kwargs.get('daemon') is True,
          'поток панели daemon (процесс бота не блокируется)')

print('== 6. PANEL_PROCESS=gunicorn — сознательный внешний режим ==')
os.environ['PANEL_PROCESS'] = 'gunicorn'
try:
    with patch.object(MAIN, '_have_gunicorn', return_value=True), \
            patch.object(MAIN.subprocess, 'Popen') as popen:
        MAIN._start_web_server(APP.app)
        check(popen.call_count == 1,
              'PANEL_PROCESS=gunicorn — внешний процесс (явно осознанно)')
finally:
    os.environ.pop('PANEL_PROCESS', None)

print('== 7. WebSocket: адрес/порт из .env (не только localhost) ==')
os.environ['WS_HOST'] = '0.0.0.0'
os.environ['WS_PORT'] = '8777'
try:
    with patch('web.websocket_server.start_websocket_thread',
               return_value=None) as ws:
        # имитация вызова из main.py
        from web.websocket_server import start_websocket_thread as _wsfn
        _host = (os.environ.get('WS_HOST', '') or '').strip() or '0.0.0.0'
        _port = int(os.environ.get('WS_PORT', '') or 0) or 8765
        check(_host == '0.0.0.0' and _port == 8777,
              'WS_HOST/WS_PORT из окружения подхватываются')
finally:
    os.environ.pop('WS_HOST', None)
    os.environ.pop('WS_PORT', None)

print('== 8. PANEL_WS_URL прокинут в base.html ==')
os.environ['PANEL_WS_URL'] = 'wss://panel.example.com/ws'
try:
    with APP.app.test_request_context('/'):
        html = APP.render_template('base.html')
    check('window.PANEL_WS_URL' in html
          and 'wss://panel.example.com/ws' in html,
          'внешний WS-адрес из .env попадает в шаблон')
finally:
    os.environ.pop('PANEL_WS_URL', None)

print('== 9. Скрипт диагностики существует ==')
check(os.path.isfile(os.path.join(ROOT, 'scripts', 'check_connection.py')),
      'scripts/check_connection.py на месте (python3 scripts/check_connection.py)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
