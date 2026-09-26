# -*- coding: utf-8 -*-
"""warn_1 ensure: роль с 1 варна, миграция с warn_3."""
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


print('== ensure_warn_1_role ==')
td = Path(tempfile.mkdtemp(prefix='hakumo_warn_'))
punish = td / 'punish_roles.json'
os.environ['MAIN_GUILD_ID'] = '793336829280780331'
import services.role_seed as RS
RS.PUNISH_PATH = str(punish)

GID = '793336829280780331'
WARN = 1545468739221327942
punish.write_text(json.dumps({
    GID: {
        'roles': {
            'ban': 1, 'mute': 2, 'vmute': 3,
            'warn_3': WARN,
        },
        'warn_levels': [3],
    }
}), encoding='utf-8')

rep = RS.ensure_warn_1_role({})
data = json.loads(punish.read_text(encoding='utf-8'))
roles = data[GID]['roles']
check(roles.get('warn_1') == WARN, 'warn_1 set to known role')
check('warn_3' not in roles, 'warn_3 duplicate removed')
check(1 in data[GID].get('warn_levels', []), 'warn_levels includes 1')
check('warn_1' in (rep.get('punish_added') or []), 'report notes warn_1')

# idempotent
rep2 = RS.ensure_warn_1_role({})
check('warn_1' not in (rep2.get('punish_added') or []),
      'second ensure no churn')
data2 = json.loads(punish.read_text(encoding='utf-8'))
check(data2[GID]['roles'].get('warn_1') == WARN, 'still warn_1 after second ensure')

# level_transition at 1 warn → role
from services import punish_roles as PR
# point PR at our temp file
PR.PATH = str(punish)
PR._CACHE.update({'mtime': None, 'size': None, 'data': None})
add_id, remove = PR.level_transition(int(GID), 1)
check(add_id == WARN, f'level_transition(1) → warn role (got {add_id})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
