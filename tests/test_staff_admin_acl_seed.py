# -*- coding: utf-8 -*-
"""Сид × Staff Administrator: тир admin, полный ACL, лимиты +2."""
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_sa_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.abspath('data/bot.db')
os.environ['MAIN_GUILD_ID'] = '793336829280780331'

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== constants ==')
from services.staff_roles import (
    KNOWN_STAFF_ADMIN_ROLE_ID, KNOWN_ADMIN_ROLE_ID,
)
from services.staff_admin_acl_seed import (
    apply_staff_admin_acl_seed, STAFF_ADMIN_LIMITS,
)
SA = str(int(KNOWN_STAFF_ADMIN_ROLE_ID))
check(SA == '1549118975110152263', f'Staff Admin id ({SA})')
check(STAFF_ADMIN_LIMITS['mute'] == 12 and STAFF_ADMIN_LIMITS['ban'] == 7,
      f'лимиты +2 к admin: {STAFF_ADMIN_LIMITS}')

print('== apply seed ==')
GID = 793336829280780331
# baseline role_map without staff admin
with open('data/role_map.json', 'w', encoding='utf-8') as fh:
    json.dump({str(KNOWN_ADMIN_ROLE_ID): 'admin'}, fh)

rep = apply_staff_admin_acl_seed(force=True, guild_id=GID)
check(rep.get('applied') is True, f'applied ({rep})')
check(rep.get('role_map') is True, 'role_map обновлён')
check('ban' in (rep.get('acl_added') or []) and 'mute' in (rep.get('acl_added') or []),
      f'ACL выдан: {rep.get("acl_added")}')

rm = json.load(open('data/role_map.json', encoding='utf-8'))
check(rm.get(SA) == 'admin', f'role_map staff-admin=admin ({rm.get(SA)})')

from services.permission_acl import ACTIONS, load_action_acl
acl = load_action_acl(GID)
missing = [a for a in ACTIONS if SA not in [str(r) for r in (acl.get(a) or [])]]
check(not missing, f'все ACTIONS на Staff Admin (miss={missing})')

from services import staff_limits as SL
check(SL.tier_for_roles([SA]) == 'admin', 'tier=admin')
ov = SL.get_role_overrides(GID).get(SA) or {}
lims = ov.get('limits') or {}
check(lims.get('mute') == 12 and lims.get('ban') == 7,
      f'role limits +2: {lims}')

rep2 = apply_staff_admin_acl_seed(force=False, guild_id=GID)
check(rep2.get('applied') is False and 'already' in (rep2.get('reason') or ''),
      f'идемпотентно ({rep2.get("reason")})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
