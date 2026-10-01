# -*- coding: utf-8 -*-
"""Assistent — выше куратора (обе ветки). Master — mid.

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
    KNOWN_HELPER_ROLE_ID, KNOWN_MASTER_ROLE_ID, KNOWN_ASSISTENT_ROLE_IDS,
)
from services import permission_acl as pacl  # noqa: E402
from services import staff_limits as SL  # noqa: E402
from services import staff_hierarchy as SH  # noqa: E402
from services.assistent_acl_seed import (  # noqa: E402
    apply_assistent_acl_seed, ensure_assistent_acl,
    ASSISTENT_LIMITS, STAFF_ASSISTENT_LIMITS,
)
from services.master_acl_seed import (  # noqa: E402
    apply_master_acl_seed, MASTER_LIMITS,
)
from services.helper_acl_seed import HELPER_LIMITS  # noqa: E402

ASS = str(int(KNOWN_ASSISTENT_ROLE_ID))
STAFF_ASS = str(int(KNOWN_STAFF_ASSISTENT_ROLE_ID))
HELPER = str(int(KNOWN_HELPER_ROLE_ID))
MASTER = str(int(KNOWN_MASTER_ROLE_ID))
CUR = '807030012301541377'

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== 1. Иерархия: master < curator < assistent < admin ==')
check(SH.RANK['master'] < SH.RANK['curator'], 'master < curator')
check(SH.RANK['curator'] < SH.RANK['assistent'], 'curator < assistent')
check(SH.RANK['assistent'] < SH.RANK['admin'], 'assistent < admin')
check(SL.TIER_ORDER.index('master') < SL.TIER_ORDER.index('curator'),
      'TIER master < curator')
check(SL.TIER_ORDER.index('curator') < SL.TIER_ORDER.index('assistent'),
      'TIER curator < assistent')
check(ASS in [str(x) for x in KNOWN_ASSISTENT_ROLE_IDS], 'in ASSISTENT ids')

print('== 2. Лимиты mid / above ==')
check(MASTER_LIMITS['mute'] == 5, 'master mute 5')
check(ASSISTENT_LIMITS['mute'] == 9, 'assistent mute 9')
check(ASSISTENT_LIMITS['mute'] > SL.TIER_DEFAULT_LIMITS['curator']['mute'],
      'assistent mute > curator')
check(ASSISTENT_LIMITS['ban'] == 3, 'assistent ban 3')
check(STAFF_ASSISTENT_LIMITS['mute'] == 10, 'staff assistent mute 10')
check(HELPER_LIMITS['mute'] == 3, 'helper mute 3')

print('== 3. сид Assistent: тир + полный ACL ==')
pacl.save_action_acl(GID, {a: [HELPER] for a in pacl.ACTIONS})
with open('data/role_map.json', 'w', encoding='utf-8') as fh:
    json.dump({HELPER: 'helper', MASTER: 'master', CUR: 'curator'}, fh)

rep = apply_assistent_acl_seed(force=True, guild_id=GID)
check(rep.get('applied') is True, f'seed applied ({rep.get("reason")})')
rm = json.load(open('data/role_map.json', encoding='utf-8'))
check(rm.get(ASS) == 'assistent', 'Assistent → assistent')
check(rm.get(STAFF_ASS) == 'assistent', 'Staff Assistent → assistent')
check(SL.tier_for_roles([int(ASS)]) == 'assistent', 'tier=assistent')

acl = pacl.load_action_acl(GID)
for act in ('mute', 'ban', 'vmute', 'warn', 'purge', 'timeout'):
    check(ASS in [str(r) for r in acl.get(act, [])], f'Assistent в {act}')

lim, _ = SL.effective_limits(GID, [int(ASS)])
check(lim.get('mute') == 9 and lim.get('ban') == 3,
      f'effective assistent: {lim}')

print('== 4. Master сид mid ==')
rep_m = apply_master_acl_seed(force=True, guild_id=GID)
check(rep_m.get('applied') is True, f'master seed ({rep_m.get("reason")})')
lim_m, _ = SL.effective_limits(GID, [int(MASTER)])
check(lim_m.get('mute') == 5 and lim_m.get('ban') == 1,
      f'effective master: {lim_m}')
check(SL.tier_for_roles([int(MASTER)]) == 'master', 'Master tier')

print('== 5. Иерархия наказаний ==')


class _Role:
    def __init__(self, rid):
        self.id = int(rid)


class _Mem:
    def __init__(self, uid, roles):
        self.id = uid
        self.bot = False
        self.roles = [_Role(r) for r in roles]


class _G:
    id = GID
    owner_id = 1


g = _G()
# uid далеко от OWNER_ID=1 и тестовых 10.. — иначе actor → owner
# ассистент может наказать куратора
ok, deny, ar, tr = SH.check(
    g, _Mem(900001, [int(ASS)]), _Mem(900002, [int(CUR)]), 'mute')
check(ok is True and ar == 'assistent' and tr == 'curator',
      f'assistent→curator OK ({ar}/{tr} {deny})')
# куратор НЕ может наказать ассистента
ok, deny, ar, tr = SH.check(
    g, _Mem(900003, [int(CUR)]), _Mem(900004, [int(ASS)]), 'mute')
check(ok is False and 'ассистент' in (deny or '').lower(),
      f'curator→assistent DENY ({deny})')
# мастер не трогает куратора
ok, deny, ar, tr = SH.check(
    g, _Mem(900005, [int(MASTER), int(HELPER)]),
    _Mem(900006, [int(CUR)]), 'mute')
check(ok is False, f'master→curator DENY ({deny})')

print('== 6. ensure идемпотентен ==')
rep2 = ensure_assistent_acl(guild_id=GID)
check(rep2.get('reason') in ('acl ok', 'acl repaired'),
      f'ensure: {rep2.get("reason")}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
print('\n--- Полная лестница (мут/сутки) ---')
print(f"  helper/mod:  {HELPER_LIMITS['mute']}")
print(f"  master:      {MASTER_LIMITS['mute']}")
print(f"  curator:     {SL.TIER_DEFAULT_LIMITS['curator']['mute']}")
print(f"  assistent:   {ASSISTENT_LIMITS['mute']}")
print(f"  staff_ass:   {STAFF_ASSISTENT_LIMITS['mute']}")
print(f"  admin:       {SL.TIER_DEFAULT_LIMITS['admin']['mute']}")
sys.exit(1 if FAIL else 0)
