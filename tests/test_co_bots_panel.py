# -*- coding: utf-8 -*-
"""Совместные боты: env upsert + API + event voice stay."""
from __future__ import annotations

import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_cobots_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.makedirs('config', exist_ok=True)

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== env_file upsert ==')
from services import env_file as EF  # noqa: E402

envp = os.path.join(_TMP, '.env')
open(envp, 'w', encoding='utf-8').write('TOKEN=abc\nFOO=1\n')
# monkey: upsert uses repo_root → point to _TMP
rep = EF.upsert_env_keys({'EVENT_BOT_TOKEN': 'test.tok.ENVALUE'}, repo_root=_TMP)
check(rep.get('ok') and 'EVENT_BOT_TOKEN' in rep.get('written', []),
      f'wrote token: {rep}')
txt = open(envp, encoding='utf-8').read()
check('EVENT_BOT_TOKEN=test.tok.ENVALUE' in txt and 'TOKEN=abc' in txt,
      'старые ключи на месте')
check(os.environ.get('EVENT_BOT_TOKEN') == 'test.tok.ENVALUE', 'os.environ обновлён')
rep2 = EF.upsert_env_keys({'EVENT_BOT_TOKEN': ''}, repo_root=_TMP)
check('EVENT_BOT_TOKEN' not in open(envp, encoding='utf-8').read(),
      'пустой value удаляет ключ')
check(EF.mask_secret('abcdef1234') == '••••1234', 'mask_secret')

print('== event voice cfg ==')
from services import event_voice_bot as EV  # noqa: E402

# cfg path relative to package → write into repo config is ok; use save API
saved = EV.save_event_voice_cfg(
    channel_id='1547390550108540948', stay_enabled=True)
check(saved.get('channel_id') == '1547390550108540948'
      and saved.get('stay_enabled') is True, f'save cfg: {saved}')
check(EV._resolve_event_voice_channel_id() == 1547390550108540948,
      'resolve channel')
st = EV.event_bot_status()
check('token_set' in st and 'channel_id' in st and 'online' in st,
      f'status keys: {list(st)}')

print('== panel wiring ==')
menu = open(os.path.join(ROOT, 'services/panel_menu.py'), encoding='utf-8').read()
check("'/co-bots'" in menu and 'Совместные боты' in menu, 'меню: /co-bots')
check("'/co-bots': 'owner'" in menu, 'PAGE_MIN_ROLE owner')
rex = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check('co_bots' in rex, 'routes_extra импортирует co_bots')
check(os.path.isfile(os.path.join(ROOT, 'web/templates/co_bots.html')),
      'шаблон co_bots.html')
check(os.path.isfile(os.path.join(ROOT, 'web/routes/co_bots.py')),
      'роут co_bots.py')

print('== start.bat ==')
bat = open(os.path.join(ROOT, 'start.bat'), encoding='utf-8', errors='ignore').read()
check('EVENT_BOT_TOKEN' in bat and 'main.py' in bat, 'start.bat знает Event + main')
check('start_console.log' in bat and 'runloop' in bat.lower() or ':runloop' in bat,
      'start.bat с авто-перезапуском')
sb = open(os.path.join(ROOT, 'start_bot.bat'), encoding='utf-8', errors='ignore').read()
check('start.bat' in sb, 'start_bot.bat делегирует в start.bat')

print('== API smoke (flask) ==')
os.environ['PANEL_PASSWORD'] = 'CoBotsTest1!'
from web.app import app as flask_app  # noqa: E402
client = flask_app.test_client()
# login owner
r = client.post('/login', data={'username': 'owner', 'password': 'CoBotsTest1!'},
                follow_redirects=True)
# may need credentials file password — try session inject
with client.session_transaction() as sess:
    sess.clear()
    sess['logged_in'] = True
    sess['username'] = 'Boss'
    sess['role'] = 'owner'
r = client.get('/co-bots')
check(r.status_code == 200 and b'Event' in r.data, f'GET /co-bots ({r.status_code})')
r = client.get('/api/co-bots')
d = r.get_json() or {}
check(r.status_code == 200 and d.get('ok') and 'event' in d and 'main' in d,
      f'GET /api/co-bots: {str(d)[:120]}')
r = client.post('/api/co-bots/event', json={
    'channel_id': '1547390550108540948', 'stay_enabled': True})
d = r.get_json() or {}
check(r.status_code == 200 and d.get('ok'), f'POST event cfg: {d}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
