# -*- coding: utf-8 -*-
"""Хелпер — только чат (mute+purge), не полные права модера.

Запуск: python3 tests/test_helper_acl_seed.py
"""
import json
import os
import sys
import tempfile

GID = 1312000000000000088
os.environ['MAIN_GUILD_ID'] = str(GID)

_TMP = tempfile.mkdtemp(prefix='hakumo_helper_acl_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
os.makedirs('config', exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402
config.Config.DB_PATH = os.path.abspath('data/bot.db')
config.Config.MAIN_GUILD_ID = GID

from services.staff_roles import (  # noqa: E402
    KNOWN_HELPER_ROLE_ID, KNOWN_MODERATOR_ROLE_ID,
)
from services import permission_acl as pacl  # noqa: E402
from services import staff_limits as SL  # noqa: E402
from services.helper_acl_seed import (  # noqa: E402
    apply_helper_acl_seed, HELPER_ACTIONS, HELPER_LIMITS,
)
from services import role_seed as RS  # noqa: E402
from cogs.moderation import actions_for_member  # noqa: E402

HELPER = str(int(KNOWN_HELPER_ROLE_ID))
MOD = str(int(KNOWN_MODERATOR_ROLE_ID))

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


class _Perms:
    administrator = False
    manage_messages = True
    ban_members = False
    manage_guild = False
    moderate_members = False


class _Member:
    def __init__(self, uid, role_ids):
        self.id = uid
        self.bot = False
        self.roles = [_Role(r) for r in role_ids]
        self.guild_permissions = _Perms()


class _Guild:
    def __init__(self, gid):
        self.id = gid
        self.owner_id = 1


# Симулируем «грязный» ACL после старого role_seed: хелпер во ВСЕХ действиях
pacl.save_action_acl(GID, {a: [HELPER, MOD] for a in pacl.ACTIONS})
with open('data/role_map.json', 'w', encoding='utf-8') as fh:
    json.dump({HELPER: 'helper', MOD: 'mod'}, fh)

print('== 1. helper_acl_seed чистит тяжёлые права ==')
rep = apply_helper_acl_seed(force=True, guild_id=GID)
check(rep.get('applied') is True, f'seed applied ({rep.get("reason")})')
check(set(rep.get('actions_removed') or ()) >= {
    'ban', 'vmute', 'timeout', 'kick'},
      f'сняты тяжёлые: {rep.get("actions_removed")}')
acl = pacl.load_action_acl(GID)
check(HELPER in [str(r) for r in acl.get('mute', [])], 'хелпер в mute')
check(HELPER in [str(r) for r in acl.get('purge', [])], 'хелпер в purge')
check(HELPER in [str(r) for r in acl.get('warn', [])], 'хелпер в warn')
check(HELPER not in [str(r) for r in acl.get('ban', [])], 'хелпер НЕ в ban')
check(HELPER not in [str(r) for r in acl.get('vmute', [])], 'хелпер НЕ в vmute')
check(HELPER not in [str(r) for r in acl.get('timeout', [])],
      'хелпер НЕ в timeout')
check(MOD in [str(r) for r in acl.get('ban', [])], 'модер остался в ban')

print('== 2. Лимиты хелпера → меню mute/clear/warn ==')
check(rep.get('limits') is True, 'limits seeded')
scoped = SL.role_scoped_actions(GID, [int(HELPER)])
check(scoped == {'mute', 'unmute', 'clear', 'warn'}, f'scoped={scoped}')
lm, _ = SL.effective_limits(GID, [int(HELPER)])
check(lm.get('mute') == 3 and lm.get('unmute') == 3 and lm.get('clear') == 10
      and lm.get('warn') == 1,
      f'хелпер limits warn/mute/unmute/clear')

print('== 3. /modpanel меню ==')
g = _Guild(GID)
h = _Member(10, [GID, HELPER])
m = _Member(11, [GID, MOD])
h_acts = [a[0] for a in actions_for_member(g, h)]
check(set(h_acts) <= {'mute', 'unmute', 'clear', 'warn'},
      f'хелпер меню: {h_acts}')
check('ban' not in h_acts, f'хелпер без ban: {h_acts}')
check('warn' in h_acts and 'mute' in h_acts,
      f'хелпер видит warn/mute: {h_acts}')
check(pacl.check_action(GID, h, 'mute') is True, 'хелпер check mute OK')
check(pacl.check_action(GID, h, 'warn') is True, 'хелпер check warn OK')
check(pacl.check_action(GID, h, 'ban') is False, 'хелпер check ban DENY')
check(pacl.check_action(GID, m, 'ban') is True, 'модер check ban OK')
check(pacl.check_action(GID, m, 'vmute') is True, 'модер check vmute OK')
check(pacl.check_action(GID, m, 'warn') is True, 'модер check warn OK')

print('== 4. role_seed исключает хелпера из полного ACL ==')
# чистый прогон с хелпером в role_map
os.remove('data/.helper_acl.v4') if os.path.exists('data/.helper_acl.v4') else None
for p in ('data/.role_seed.v6', 'data/.role_seed.v5'):
    if os.path.exists(p):
        os.remove(p)
pacl.save_action_acl(GID, {})
SEED = {
    'version': 6,
    'role_map': {HELPER: 'helper', MOD: 'mod'},
    'action_default': {'tiers': ['mod', 'master', 'curator', 'admin']},
}
with open('config/role_seed.json', 'w', encoding='utf-8') as fh:
    json.dump(SEED, fh)
rep2 = RS.apply_role_seed(force=True, guild_id=GID)
acl2 = pacl.load_action_acl(GID)
check(HELPER not in [str(r) for r in (acl2.get('ban') or [])],
      'role_seed: хелпер НЕ в ban')
check(MOD in [str(r) for r in (acl2.get('ban') or [])],
      'role_seed: модер в ban')
check(HELPER not in [str(r) for r in (acl2.get('mute') or [])],
      'role_seed: хелпер ещё не в mute (его добавит helper_acl_seed)')
rep3 = apply_helper_acl_seed(force=True, guild_id=GID)
acl3 = pacl.load_action_acl(GID)
check(HELPER in [str(r) for r in (acl3.get('mute') or [])],
      'после helper_seed: хелпер в mute')
check(HELPER in [str(r) for r in (acl3.get('warn') or [])],
      'после helper_seed: хелпер в warn')
check(HELPER not in [str(r) for r in (acl3.get('ban') or [])],
      'после helper_seed: хелпер всё ещё не в ban')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
print('\n--- Хелпер ---')
print(f'  права:  {", ".join(HELPER_ACTIONS)}')
print(f'  лимиты: warn {HELPER_LIMITS["warn"]}, mute/unmute {HELPER_LIMITS["mute"]}, clear {HELPER_LIMITS["clear"]}')
print('--- Модератор ---')
print('  права:  полный ACL')
mod_l = SL.TIER_DEFAULT_LIMITS['mod']
print(f'  лимиты: mute/unmute {mod_l["mute"]}, ban {mod_l["ban"]}, '
      f'warn {mod_l["warn"]}, clear {mod_l["clear"]}')
sys.exit(1 if FAIL else 0)
