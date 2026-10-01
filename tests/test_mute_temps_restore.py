# -*- coding: utf-8 -*-
"""Восстановление сроков мутов после рестарта бота.

Запуск: python3 tests/test_mute_temps_restore.py
"""
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta

_TMP = tempfile.mkdtemp(prefix='hakumo_mute_restore_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services import punish_roles as PR  # noqa: E402

GID = 793336829280780331
MUTE = 943510457833095208
VMUTE = 943510458621632522
UID = 111222333444555666

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


# стартовая карта ролей без temps
PR.set_roles(GID, who='test', mute=MUTE, vmute=VMUTE)
check(PR.temps_for(GID, UID) == {}, 'temps пусты после set_roles')

print('== 1. add_temp переживает set_roles ==')
until = time.time() + 3600
PR.add_temp(GID, UID, MUTE, until)
check(abs(PR.temps_for(GID, UID)[MUTE] - until) < 1, 'add_temp записал')
PR.set_roles(GID, who='test2', ban=1083106265422643251)
check(MUTE in PR.temps_for(GID, UID), 'temps живы после set_roles')

print('== 2. restore из mod_data — активный срок ==')
# сброс temps
data = json.load(open('data/punish_roles.json', encoding='utf-8'))
data[str(GID)]['temps'] = {}
json.dump(data, open('data/punish_roles.json', 'w', encoding='utf-8'))
PR._CACHE['mtime'] = None

ts = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
json.dump({
    'cases': {
        str(GID): [{
            'id': 1,
            'action': 'mute_chat',
            'user_id': str(UID),
            'mod_id': '1',
            'reason': 'тест',
            'timestamp': ts,
            'duration_minutes': 120,
        }]
    }
}, open('data/mod_data.json', 'w', encoding='utf-8'))

rep = PR.restore_temps_from_mod_data(GID, [(UID, MUTE)])
check(rep['restored'] == 1, f'restored=1 ({rep})')
got = PR.temps_for(GID, UID).get(MUTE, 0)
check(got > time.time(), f'until в будущем: {got - time.time():.0f}s')

print('== 3. restore — уже истёкший → expired ==')
data = json.load(open('data/punish_roles.json', encoding='utf-8'))
data[str(GID)]['temps'] = {}
json.dump(data, open('data/punish_roles.json', 'w', encoding='utf-8'))
PR._CACHE['mtime'] = None

ts_old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
json.dump({
    'cases': {
        str(GID): [{
            'id': 1,
            'action': 'mute_chat',
            'user_id': str(UID),
            'mod_id': '1',
            'reason': 'вчера',
            'timestamp': ts_old,
            'duration_minutes': 60,
        }]
    }
}, open('data/mod_data.json', 'w', encoding='utf-8'))

rep2 = PR.restore_temps_from_mod_data(GID, [(UID, MUTE)])
check(len(rep2['expired']) == 1, f'expired=1 ({rep2})')
due = PR.due(time.time())
check(any(int(u) == UID and int(r) == MUTE for _g, u, r in due),
      'due содержит просроченный мут')

print('== 4. unmute после дела — не восстанавливаем ==')
data = json.load(open('data/punish_roles.json', encoding='utf-8'))
data[str(GID)]['temps'] = {}
json.dump(data, open('data/punish_roles.json', 'w', encoding='utf-8'))
PR._CACHE['mtime'] = None
json.dump({
    'cases': {
        str(GID): [
            {
                'id': 1, 'action': 'mute_chat', 'user_id': str(UID),
                'mod_id': '1', 'reason': 'x',
                'timestamp': ts, 'duration_minutes': 120,
            },
            {
                'id': 2, 'action': 'unmute_chat', 'user_id': str(UID),
                'mod_id': '1', 'reason': 'сняли',
                'timestamp': datetime.now(timezone.utc).isoformat(),
            },
        ]
    }
}, open('data/mod_data.json', 'w', encoding='utf-8'))
rep3 = PR.restore_temps_from_mod_data(GID, [(UID, MUTE)])
check(rep3['restored'] == 0 and not rep3['expired'],
      f'после unmute не restore ({rep3})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
