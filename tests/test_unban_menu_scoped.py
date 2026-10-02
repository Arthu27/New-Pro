# -*- coding: utf-8 -*-
"""Разбан в меню, если есть бан (scoped overrides).

Запуск: python3 tests/test_unban_menu_scoped.py
"""
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_unban_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

HELPER = 948969471916249119
MOD = 803553848396349510
OTV_H = 1551525681207189504
ADMIN = 1189999426631122964
GID = 793336829280780331

json.dump({
    str(HELPER): 'helper',
    str(MOD): 'mod',
    str(OTV_H): 'curator',
    str(ADMIN): 'admin',
}, open('data/role_map.json', 'w'))

from services.staff_limits import (  # noqa: E402
    set_role_limits, role_scoped_actions,
)
from cogs.moderation import actions_for_member  # noqa: E402
from services.permission_acl import save_action_acl  # noqa: E402

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


# ACL: ban для куратора/мода/админа, не для хелпера
save_action_acl(GID, {
    'ban': [str(MOD), str(OTV_H), str(ADMIN)],
    'mute': [str(HELPER), str(MOD), str(OTV_H), str(ADMIN)],
    'purge': [str(HELPER), str(MOD), str(OTV_H), str(ADMIN)],
    'warn': [str(MOD), str(OTV_H), str(ADMIN)],
    'timeout': [str(MOD), str(OTV_H), str(ADMIN)],
    'vmute': [str(MOD), str(OTV_H), str(ADMIN)],
    'unwarn': [str(MOD), str(OTV_H), str(ADMIN)],
})

# как на проде: лимиты без unban (0 не сохраняется)
set_role_limits(GID, HELPER, clear=10, mute=3, unmute=3)
set_role_limits(GID, OTV_H, warn=2, ban=2, mute=7, unmute=7, clear=10)
set_role_limits(GID, ADMIN, warn=2, ban=5, mute=10, unmute=10, clear=10)


class Role:
    def __init__(self, rid):
        self.id = rid


class Perms:
    administrator = False
    ban_members = False
    manage_guild = False
    manage_messages = False


class Mem:
    def __init__(self, roles):
        self.id = 1
        self.bot = False
        self.roles = [Role(r) for r in roles]
        self.guild_permissions = Perms()


class G:
    id = GID
    owner_id = 0


g = G()

print('== scoped pairs ==')
sc = role_scoped_actions(GID, [OTV_H, HELPER])
check('ban' in sc and 'unban' in sc, f'otv scoped has unban ({sc})')
sc_h = role_scoped_actions(GID, [HELPER])
check('unban' not in sc_h and 'ban' not in sc_h,
      f'helper scoped no ban/unban ({sc_h})')

print('== menu ==')
otv = actions_for_member(g, Mem([OTV_H, HELPER]))
keys = [a[3] for a in otv]
check('ban' in keys and 'unban' in keys, f'otv menu has ban+unban ({keys})')

admin = actions_for_member(g, Mem([ADMIN]))
akeys = [a[3] for a in admin]
check('unban' in akeys, f'admin menu has unban ({akeys})')

helper = actions_for_member(g, Mem([HELPER]))
hkeys = [a[3] for a in helper]
check('unban' not in hkeys and 'ban' not in hkeys,
      f'helper menu no ban/unban ({hkeys})')

# mod без role overrides → scoped None → полное меню с ACL
mod = actions_for_member(g, Mem([MOD]))
mkeys = [a[3] for a in mod]
check('unban' in mkeys, f'mod menu has unban ({mkeys})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
