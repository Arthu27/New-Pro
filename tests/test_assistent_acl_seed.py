# -*- coding: utf-8 -*-
"""Assistent — мастер ветки Helper (mid между хелпером и куратором).

Запуск: python3 tests/test_assistent_acl_seed.py
"""
import json
import os
import sys
import tempfile

GID = 1312000000000000099
os.environ['MAIN_GUILD_ID'] = str(GID)

_TMP = tempfile.mkdtemp(prefix='hakumo_assistent_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
os.makedirs('config', exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402
config.Config.DB_PATH = os.path.abspath('data/bot.db')
config.Config.MAIN_GUILD_ID = GID

from services.staff_roles import (  # noqa: E402
    KNOWN_ASSISTENT_ROLE_ID, KNOWN_STAFF_ASSISTENT_ROLE_ID,
    KNOWN_HELPER_ROLE_ID, KNOWN_HELPER_MASTER_ROLE_IDS,
)
from services import permission_acl as pacl  # noqa: E402
from services import staff_limits as SL  # noqa: E402
from services.assistent_acl_seed import (  # noqa: E402
    apply_assistent_acl_seed, ensure_assistent_acl,
    ASSISTENT_ACTIONS, ASSISTENT_LIMITS,
)
from services.helper_acl_seed import HELPER_LIMITS  # noqa: E402

ASS = str(int(KNOWN_ASSISTENT_ROLE_ID))
STAFF_ASS = str(int(KNOWN_STAFF_ASSISTENT_ROLE_ID))
HELPER = str(int(KNOWN_HELPER_ROLE_ID))

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


class _Role:
    def __init__(self, rid):
        self.id = int(rid)


class _Member:
    def __init__(self, uid, role_ids):
        self.id = uid
        self.bot = False
        self.roles = [_Role(r) for r in role_ids]


print('== 1. IDs и mid-лимиты ==')
check(KNOWN_ASSISTENT_ROLE_ID == 1552815174115664013, 'Assistent id')
check(KNOWN_STAFF_ASSISTENT_ROLE_ID == 1554932049528225842, 'Staff Assistent id')
check(ASS in [str(x) for x in KNOWN_HELPER_MASTER_ROLE_IDS], 'in HELPER_MASTER')
check(ASSISTENT_LIMITS['mute'] == 5 and ASSISTENT_LIMITS['unmute'] == 5,
      'assistent mute/unmute 5')
check(HELPER_LIMITS['mute'] == 3, 'helper mute 3')
check(ASSISTENT_LIMITS['mute'] > HELPER_LIMITS['mute'],
      'assistent > helper mute')
check(ASSISTENT_LIMITS['mute'] < SL.TIER_DEFAULT_LIMITS['curator']['mute'],
      'assistent < curator mute')
check(set(ASSISTENT_ACTIONS) == {'mute', 'purge'}, 'actions mute+purge')

print('== 2. сид: role_map master + ACL + limits ==')
pacl.save_action_acl(GID, {a: [HELPER] for a in pacl.ACTIONS})
with open('data/role_map.json', 'w', encoding='utf-8') as fh:
    json.dump({HELPER: 'helper'}, fh)

rep = apply_assistent_acl_seed(force=True, guild_id=GID)
check(rep.get('applied') is True, f'seed applied ({rep.get("reason")})')
rm = json.load(open('data/role_map.json', encoding='utf-8'))
check(rm.get(ASS) == 'master', 'Assistent → master')
check(rm.get(STAFF_ASS) == 'master', 'Staff Assistent → master')
check(SL.tier_for_roles([int(ASS)]) == 'master', 'tier_for Assistent=master')

acl = pacl.load_action_acl(GID)
check(ASS in [str(r) for r in acl.get('mute', [])], 'Assistent в mute')
check(ASS in [str(r) for r in acl.get('purge', [])], 'Assistent в purge')
check(ASS not in [str(r) for r in acl.get('ban', [])], 'Assistent НЕ в ban')
check(ASS not in [str(r) for r in acl.get('warn', [])], 'Assistent НЕ в warn')
check(ASS not in [str(r) for r in acl.get('vmute', [])], 'Assistent НЕ в vmute')

lim, _ = SL.effective_limits(GID, [int(ASS)])
check(lim.get('mute') == 5 and lim.get('unmute') == 5,
      f'effective mute/unmute 5: {lim}')

print('== 3. гейт: Assistent один — можно наказывать ==')
ok, deny = SL.master_punish_allowed(_Member(1, [int(ASS)]))
check(ok is True and deny is None, 'Assistent alone OK')

ok, deny = SL.master_punish_allowed(
    _Member(2, [1552637932907667466]))  # × Master alone
check(ok is False, '× Master alone DENY')

print('== 4. ensure идемпотентен ==')
rep2 = ensure_assistent_acl(guild_id=GID)
check(rep2.get('reason') in ('acl ok', 'acl repaired'),
      f'ensure: {rep2.get("reason")}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
print('\n--- Ветка Helper (за сутки) ---')
print(f"  хелпер:     мут/размут {HELPER_LIMITS['mute']}  (бан —)")
print(f"  assistent:  мут/размут {ASSISTENT_LIMITS['mute']}  (бан —)")
print(f"  куратор:    варн 2  мут/размут 7  бан 2")
sys.exit(1 if FAIL else 0)
