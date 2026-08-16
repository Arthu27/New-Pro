# -*- coding: utf-8 -*-
"""Пульт плеера в панели (идея #2).

Проверяем: чистые shuffle_queue/remove_track (поведение 1:1 с !shuffle),
payload с фейк-ботом и настоящим когом (сериализация очереди, статусы,
громкость), транспорт pause/resume/skip/shuffle/clear/volume/leave с
честными 409/400, remove с undo-инфо, бот офлайн/ког не загружен → 503,
права mod/admin, шаблон (гейтинг, без эмодзи), меню.

Запуск: python3 tests/test_music_panel.py
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

_TMP = tempfile.mkdtemp(prefix='aether_musicpanel_test_')
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


import random  # noqa: E402

from cogs import music_cog as MC  # noqa: E402
from web.routes import music_panel as MP  # noqa: E402

print('== 1. Чистые: shuffle_queue/remove_track ==')
random.seed(7)
q = [{'query': 'one'}, {'query': 'two'}, {'query': 'three'}, {'query': 'four'}]
sh = MC.shuffle_queue(q)
check(sh[0]['query'] == 'one' and sorted(x['query'] for x in sh) == ['four', 'one', 'three', 'two'],
      'шаффл держит играющий первым, состав неизменен')
check(len(sh) == len(q) and sh is not q, 'шаффл — новый список той же длины')
check(MC.shuffle_queue([{'query': 'solo'}])[0]['query'] == 'solo', 'один трек — без шаффла')
ok, err, _ = MC.remove_track(q, 'не число')
check(not ok and err == 'Номер трека должен быть целым числом.', 'remove: мусор → честная 400-ошибка')
ok, err, _ = MC.remove_track(q, 0)
check(not ok and err == 'Нет трека с таким номером.', 'remove: 0 → 404-ошибка')
ok, err, _ = MC.remove_track(q, 99)
check(not ok and err == 'Нет трека с таким номером.', 'remove: за пределами → 404-ошибка')
ok, err, rem = MC.remove_track(q, 2)
check(ok and rem['query'] == 'two' and q[1]['query'] == 'three', 'remove: убрал и сдвинул')


class FakeReq:
    def __init__(self, name):
        self.display_name = name
        self.mention = '@' + name


class FakeSource:
    volume = 0.6


class FakeVC:
    def __init__(self):
        self._playing = True
        self._paused = False
        self._connected = True
        self.source = FakeSource()
        self.channel = type('ch', (), {'name': 'Голосовой'})()
        self.calls = []

    def is_playing(self):
        return self._playing and not self._paused

    def is_paused(self):
        return self._paused

    def is_connected(self):
        return self._connected

    def pause(self):
        self.calls.append('pause')
        self._paused = True

    def resume(self):
        self.calls.append('resume')
        self._paused = False

    def stop(self):
        self.calls.append('stop')
        self._playing = False

    async def disconnect(self):
        self.calls.append('disconnect')
        self._connected = False


class FakeGuild:
    def __init__(self):
        self.id = 777
        self.voice_client = FakeVC()


class FakeBot:
    def __init__(self):
        self.guild = FakeGuild()
        self.cog = MC.MusicCog(self)
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

    def get_guild(self, gid):
        return self.guild if gid == 777 else None

    def get_cog(self, name):
        return self.cog if name == 'MusicCog' else None


print('== 2. Payload с настоящим когом ==')
fake = FakeBot()
fake.cog.queues[777] = [
    {'query': 'lofi radio', 'requester': FakeReq('Мира')},
    {'query': 'night drive mix', 'requester': FakeReq('Тёма')},
    {'query': 'synthwave', 'requester': None},
]
import web.app as appmod  # noqa: E402
appmod.bot_instance = fake
p = MP.music_payload(777, fake)
check(p['success'] and p['total'] == 3 and p['playing'] and not p['paused'], 'статусы: играет')
check(p['channel'] == 'Голосовой' and p['volume'] == 60, 'канал и громкость (60%)')
check(p['current']['query'] == 'lofi radio' and p['current']['requester'] == 'Мира', 'сейчас играет')
check(p['queue'][2]['requester'] == '', 'без requester — пусто, не падаем')

print('== 3. API: права и транспорт ==')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


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


check(client.get('/music').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get('/api/music/state').status_code in (302, 401, 403), 'гостю state закрыт')
login('uye')
check(client.get('/music').status_code == 403, 'uye нельзя')
login('mod')
check(client.get('/music').status_code == 200, 'mod читает страницу (200)')
check(client.get('/api/music/state').status_code == 200, 'mod читает state (200)')
check(post('/api/music/control', {'action': 'skip'})[0] == 403, 'mod не управляет (403)')
check(post('/api/music/remove', {'index': 1})[0] == 403, 'mod не удаляет (403)')

login('admin')
code, d = post('/api/music/control', {'action': 'pause'})
check(code == 200 and d['paused'] and 'pause' in fake.guild.voice_client.calls, 'пауза: vc.pause()')
code, d = post('/api/music/control', {'action': 'pause'})
check(code == 409 and d['error'] == 'Сейчас ничего не играет.', 'повторная пауза — честная 409')
code, d = post('/api/music/control', {'action': 'resume'})
check(code == 200 and not d['paused'] and 'resume' in fake.guild.voice_client.calls, 'resume: vc.resume()')
code, d = post('/api/music/control', {'action': 'volume', 'volume': 'громко'})
check(code == 400 and d['error'] == 'Громкость должна быть целым числом.', 'volume: мусор → 400')
code, d = post('/api/music/control', {'action': 'volume', 'volume': 500})
check(code == 400 and d['error'] == 'Уровень громкости должен быть от 0 до 200%.',
      'volume: рамки бота (0-200%)')
code, d = post('/api/music/control', {'action': 'volume', 'volume': 85})
check(code == 200 and abs(fake.guild.voice_client.source.volume - 0.85) < 1e-9 and d['volume'] == 85,
      'volume: выставлен в source (85%)')
before = [s['query'] for s in fake.cog.queues[777]]
code, d = post('/api/music/control', {'action': 'shuffle'})
check(code == 200 and sorted(x['query'] for x in d['queue']) == sorted(before)
      and d['queue'][0]['query'] == before[0], 'shuffle: первый на месте, состав тот же')
code, d = post('/api/music/remove', {'index': 'ха'})
check(code == 400 and d['error'] == 'Номер трека должен быть целым числом.', 'API отдаёт текст кога 1:1 (400)')
code, d = post('/api/music/remove', {'index': 99})
check(code == 404 and d['error'] == 'Нет трека с таким номером.', 'API отдаёт текст кога 1:1 (404)')
code, d = post('/api/music/remove', {'index': 2})
check(code == 200 and d['removed']['query'] and d['total'] == 2, 'remove: 200 + undo-инфо')
code, d = post('/api/music/control', {'action': 'wizard'})
check(code == 400 and d['error'] == 'Неизвестное действие.', 'неизвестное действие — 400')
code, d = post('/api/music/control', {'action': 'skip'})
check(code == 200 and 'stop' in fake.guild.voice_client.calls, 'skip: vc.stop()')
code, d = post('/api/music/control', {'action': 'skip'})
check(code == 409 and d['error'] == 'Сейчас ничего не играет.', 'skip после остановки — 409')
fake.guild.voice_client._playing = True
code, d = post('/api/music/control', {'action': 'clear'})
check(code == 200 and d['total'] == 0 and fake.cog.queues[777] == [], 'clear: очередь пуста')
code, d = post('/api/music/control', {'action': 'leave'})
check(code == 200 and 'disconnect' in fake.guild.voice_client.calls and d['connected'] is False,
      'leave: disconnect() исполнен циклом бота')

print('== 4. Офлайн и шаблон ==')
appmod.bot_instance = None
check(client.get('/api/music/state').status_code == 503, 'бот офлайн → 503')
code, d = post('/api/music/control', {'action': 'clear'})
check(code == 503 and d['offline'], 'мутация офлайн → 503 с флагом')
appmod.bot_instance = fake
fake2 = FakeBot()
fake2.cog = None
appmod.bot_instance = fake2
check(client.get('/api/music/state').status_code == 200
      and client.get('/api/music/state').get_json().get('success') is False,
      'ког не загружен → честный offline-payload')

html = client.get('/music').get_data(as_text=True)
check('muControls' in html and 'CAN_EDIT = true' in html, 'admin: пульт и CAN_EDIT=true')
login('mod')
html_mod = client.get('/music').get_data(as_text=True)
check('var CAN_EDIT = false' in html_mod, 'mod: CAN_EDIT=false')
tpl = open(os.path.join(ROOT, 'web/templates/music.html'), encoding='utf-8').read()
emoji = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not emoji.search(tpl), 'в шаблоне нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
check('askConfirm' in tpl and 'setLiveRefresh' in tpl, 'confirm и live-refresh на месте')
import services.panel_menu as PM
paths = [pg['path'] for g in PM.MENU for pg in g['pages']]
check('/music' in paths, 'пункт меню «Музыка» есть')
check(PM.PAGE_COGS.get('/music') == ('music_cog',), 'PAGE_COGS привязан к music_cog')

appmod.bot_instance = None
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
