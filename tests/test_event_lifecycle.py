# -*- coding: utf-8 -*-
"""Event lifecycle TZ: store, parse, announce body."""
import os
import sys
import tempfile
from datetime import datetime

_TMP = tempfile.mkdtemp(prefix='hakumo_evlife_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['EVENT_LIFECYCLE_DATA'] = os.path.join(_TMP, 'data')

from services import event_lifecycle_store as STORE  # noqa
from services import event_lifecycle_config as CFG  # noqa
from cogs import event_lifecycle as EL  # noqa

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== config ==')
cfg = CFG.load_config()
check(CFG.iid(cfg, 'event_mod_role_id') == 852634463535759461, 'event mod role')
check(isinstance(cfg.get('templates'), dict) and 'Among Us' in cfg['templates'], 'templates')

print('== parse dt ==')
dt = EL._parse_dt('27.09.2026', '20:00')
check(dt is not None and dt.hour == 20 and dt.day == 27, f'parse dd.mm.yyyy → {dt}')
dt2 = EL._parse_dt('27 сентября', '20:00')
check(dt2 is not None and dt2.month == 9 and dt2.day == 27, f'parse russian month → {dt2}')
check(EL._parse_dt('bad', 'xx') is None, 'bad date rejected')

print('== store signup / attendance ==')
ev = STORE.create_event(
    guild_id=1, organizer_id=9, title='Among Us', description='test',
    starts_at=datetime.now().timestamp() + 3600, max_participants=2,
    voice_channel_id=111, voice_name='Room')
eid = ev['id']
_, r1 = STORE.add_signup(eid, 100)
_, r2 = STORE.add_signup(eid, 100)
_, r3 = STORE.add_signup(eid, 101)
_, r4 = STORE.add_signup(eid, 102)
check(r1 == 'ok' and r2 == 'dup' and r3 == 'ok' and r4 == 'full', f'signup rules {r1,r2,r3,r4}')
STORE.add_voice_seconds(eid, 100, 700)
STORE.add_voice_seconds(eid, 101, 60)
ev2 = STORE.get_event(eid)
summ = STORE.attendance_summary(ev2, min_seconds=600)
check(summ['came'] == 1 and summ['no_show'] == 1 and summ['registered'] == 2, f'attendance {summ}')

print('== announce body ==')
body = EL._announce_body(ev2, 'Room')
check('Among Us' in body and 'Участники' in body and 'Room' in body, 'announce fields')

print('== organizer stats ==')
STORE.record_organizer_finish(1, 9, eid)
rows = STORE.organizer_counts(1)
check(rows and rows[0]['organizer_id'] == 9 and rows[0]['week'] >= 1, f'stats {rows}')

print('== runner wiring ==')
src = open(os.path.join(ROOT, 'services/event_voice_bot.py'), encoding='utf-8').read()
check('EventLifecycle' in src and 'eventstart' in open(
    os.path.join(ROOT, 'cogs/event_lifecycle.py'), encoding='utf-8').read(),
      'event bot loads EventLifecycle /eventstart')

print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
