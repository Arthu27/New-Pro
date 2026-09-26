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
check('EVENT_VOICE_STANDALONE' in main,
      'main.py уважает EVENT_VOICE_STANDALONE')
svc = os.path.join(ROOT, 'deploy', 'hakumo-event-voice.service')
check(os.path.isfile(svc), 'deploy/hakumo-event-voice.service есть')
runner = os.path.join(ROOT, 'scripts', 'run_event_voice_stay.py')
check(os.path.isfile(runner), 'scripts/run_event_voice_stay.py есть')

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
check(EV._stay_on() is True, 'stay всегда on')
# выключатель игнорируется
EV.save_event_voice_cfg(stay_enabled=False)
check(EV.load_event_voice_cfg().get('stay_enabled') is True, 'stay нельзя выключить')
check('timeout=45' not in open(
    os.path.join(ROOT, 'services', 'event_voice_bot.py'), encoding='utf-8').read(),
    'нет таймаута connect 45с')
check('backoff_until' not in open(
    os.path.join(ROOT, 'services', 'event_voice_bot.py'), encoding='utf-8').read(),
    'нет backoff-потолка монитора')

print('== mafia on event-bot ==')
ev_src = open(os.path.join(ROOT, 'services', 'event_voice_bot.py'), encoding='utf-8').read()
check('cog mafia' in ev_src and 'EventPanel снят' in ev_src,
      'event-bot грузит mafia, EventPanel снят')
check(('from cogs.mafia import Mafia' in ev_src
      or ('from cogs import mafia' in ev_src and 'Mafia' in ev_src)),
      'import Mafia')
check('EventLifecycle' in ev_src and 'event_lifecycle' in ev_src,
      'event-bot грузит EventLifecycle (/eventstart)')
check("'event-panel'" not in ev_src or 'без event-panel' in ev_src.lower()
      or 'Без event-panel' in ev_src or 'Без старого event-panel' in ev_src,
      'докстринг без event-panel как основной фичи')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
