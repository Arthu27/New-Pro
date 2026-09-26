# -*- coding: utf-8 -*-
"""appeal_context: текущее наказание + кто выдал."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== current punishment from mod_data ==')
td = Path(tempfile.mkdtemp(prefix='hakumo_apctx_'))
os.chdir(ROOT)

import services.appeal_context as AC

AC.MOD_DATA_FILE = str(td / 'mod_data.json')
AC.CACHE_FILE = str(td / 'audit.json')
AC.PUNISH_ROLES_FILE = str(td / 'punish.json')

GID = '793336829280780331'
UID = '963507121851351090'
(td / 'mod_data.json').write_text(json.dumps({
    'cases': {
        GID: [
            {
                'id': 109,
                'action': 'ban',
                'user_id': UID,
                'mod_id': '1273714824303476859',
                'mod_name': "Gordost'",
                'reason': '1.1 — Запрещена реклама',
                'timestamp': '2026-09-26T09:44:03.272856+00:00',
            }
        ]
    }
}), encoding='utf-8')
(td / 'audit.json').write_text('{}', encoding='utf-8')
(td / 'punish.json').write_text(json.dumps({
    GID: {'roles': {'ban': 1, 'mute': 2, 'vmute': 3}}
}), encoding='utf-8')

cur = AC.current_punishment(GID, UID)
check(cur is not None, 'found current')
check(cur and cur.get('label') == 'Бан', f"label Бан (got {cur})")
check(cur and "Gordost" in (cur.get('mod_name') or ''), 'mod name')
check(cur and '1.1' in (cur.get('reason') or ''), 'reason')

block = AC.format_current(cur)
check('Сейчас:' in block and 'Выдал:' in block, 'format block')
check('Gordost' in block, 'issuer in block')

ctx = AC.build_context({'items': []}, GID, UID)
check('Сейчас:' in ctx['rich'], 'rich has current')
check('Баны: 1' in ctx['punish_line'] or 'Баны: 1' in ctx['rich'],
      'ban count from mod_data')
check('Gordost' in ctx['line'] or 'Gordost' in ctx['rich'], 'issuer in context')

# after unban — no current
data = json.loads((td / 'mod_data.json').read_text(encoding='utf-8'))
data['cases'][GID].append({
    'id': 110, 'action': 'unban', 'user_id': UID,
    'mod_id': '1', 'mod_name': 'Admin',
    'reason': 'ok', 'timestamp': '2026-09-26T10:00:00+00:00',
})
(td / 'mod_data.json').write_text(json.dumps(data), encoding='utf-8')
cur2 = AC.current_punishment(GID, UID)
check(cur2 is None, 'unban clears current')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
