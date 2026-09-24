# -*- coding: utf-8 -*-
"""Event voice bot: токен/канал/voice stay."""
from __future__ import annotations

import ast
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_event_bot_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== module + defaults ==')
from services import event_voice_bot as EV  # noqa: E402

check(EV.DEFAULT_EVENT_VOICE_CHANNEL_ID == 1550986919981351043,
      f'default voice = {EV.DEFAULT_EVENT_VOICE_CHANNEL_ID}')
check(callable(EV.start_event_bot) and callable(EV.build_event_client),
      'start/build API')
check(EV.event_bot_token() == '', 'без env токен пуст')

os.environ['EVENT_VOICE_CHANNEL_ID'] = '1550986919981351043'
check(EV._resolve_event_voice_channel_id() == 1550986919981351043,
      'EVENT_VOICE_CHANNEL_ID читается')
os.environ.pop('EVENT_VOICE_CHANNEL_ID', None)

cfg = os.path.join(ROOT, 'config', 'event_voice_stay.json')
check(os.path.isfile(cfg), 'config/event_voice_stay.json есть')
import json  # noqa: E402
data = json.load(open(cfg, encoding='utf-8'))
check(str(data.get('channel_id')) == '1550986919981351043',
      f'json channel_id={data.get("channel_id")}')

print('== .env.example + main wiring ==')
ex = open(os.path.join(ROOT, '.env.example'), encoding='utf-8').read()
check('EVENT_BOT_TOKEN' in ex and 'EVENT_VOICE_CHANNEL_ID' in ex,
      '.env.example документирует event-бота')
main = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
check('start_event_bot' in main and 'EVENT_BOT_TOKEN' in main,
      'main.py стартует event-бота')

print('== нет захардкоженного EVENT_BOT_TOKEN ==')
import re  # noqa: E402
bad = []
pat = re.compile(r'EVENT_BOT_TOKEN\s*=\s*[\'\"][^\'\"]{20,}')
for root, dirs, files in os.walk(os.path.join(ROOT, 'services')):
    for fn in files:
        if not fn.endswith('.py'):
            continue
        path = os.path.join(root, fn)
        txt = open(path, encoding='utf-8').read()
        if pat.search(txt):
            bad.append(path)
for path in (os.path.join(ROOT, 'main.py'),
             os.path.join(ROOT, 'config.py')):
    txt = open(path, encoding='utf-8').read()
    if pat.search(txt):
        bad.append(path)
check(not bad, 'токен только из env'
      if not bad else f'захардкожен в {bad}')
# .env — gitignored
check(os.path.exists(os.path.join(ROOT, '.gitignore')) and
      any('.env' in ln and not ln.strip().startswith('#')
          for ln in open(os.path.join(ROOT, '.gitignore'), encoding='utf-8')),
      '.env в .gitignore')

print('== build client ==')
# без реального старта — только конструктор
os.environ.pop('EVENT_BOT_TOKEN', None)
client = EV.build_event_client()
check(client is not None and hasattr(client, 'start'), 'Bot собран')
check(hasattr(client, 'tree') and hasattr(client, 'add_cog'),
      'есть CommandTree + add_cog (slash)')
# intents: guilds + voice
ints = client.intents
check(bool(ints.guilds) and bool(ints.voice_states),
      'intents: guilds + voice_states')
check(not bool(getattr(ints, 'message_content', False)),
      'без message_content (лёгкий клиент)')
check(callable(getattr(EV, '_load_and_sync_event_commands', None)),
      'sync /event-panel helper')

print('== event-panel roles ==')
from cogs import event_panel as EP  # noqa: E402
check(getattr(EP, 'EVENT_ADMIN_ROLE_ID', 0) == 1551527644326002748,
      'Event Admin role')
check(getattr(EP, 'EVENT_MOD_ROLE_ID', 0) == 852634463535759461,
      'Event Mod role')
check('event-panel' in open(
    os.path.join(ROOT, 'cogs', 'event_panel.py'), encoding='utf-8').read(),
      'команда event-panel в cog')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
