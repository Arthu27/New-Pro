# -*- coding: utf-8 -*-
"""Vedushiy role seed: resolve / idempotent / no punish ACL."""
from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_vedushiy_')
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


print('== import ==')
from services import vedushiy_role_seed as V  # noqa: E402

check(V.ROLE_NAME == 'Ведущий', 'role name')
check('vedushiy' in V.NAME_ALIASES and 'broadcaster' in V.NAME_ALIASES,
      'aliases')
check(V.documented_discord_perms() == (
    'Move Members', 'Mute Members', 'Deafen Members'),
      'documented perms')
check(set(V.VOICE_HOST_PERMS) == {
    'move_members', 'mute_members', 'deafen_members'},
      'perm bits')
check(not V.should_force_perms(), 'force perms default off')

print('== resolve ==')
os.environ.pop('VEDUSHIY_ROLE_ID', None)
os.environ.pop('HOST_ROLE_ID', None)
check(V.env_vedushiy_role_id() == 0, 'env empty')
os.environ['VEDUSHIY_ROLE_ID'] = '1551180629687664670'
check(V.env_vedushiy_role_id() == 1551180629687664670, 'env id')
check(V.resolve_vedushiy_role_id() == 1551180629687664670, 'resolve env')


class _Role:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name


class _Guild:
    def __init__(self, roles):
        self.id = 793336829280780331
        self.roles = roles


os.environ.pop('VEDUSHIY_ROLE_ID', None)
g = _Guild([_Role(42, 'Ведущий'), _Role(1, 'Member')])
found = V.find_vedushiy_role(g)
check(found is not None and found.id == 42, 'find by exact name')
g2 = _Guild([_Role(7, 'Broadcaster')])
found2 = V.find_vedushiy_role(g2)
check(found2 is not None and found2.id == 7, 'find by alias')

print('== seed idempotent + no punish ==')
os.environ['MAIN_GUILD_ID'] = '793336829280780331'
os.environ['VEDUSHIY_ROLE_ID'] = '42'
# clean marker
if os.path.exists(V.MARKER):
    os.remove(V.MARKER)
r1 = V.apply_vedushiy_role_seed(guild=g)
check(r1.get('applied') is True, f'first apply: {r1.get("reason")}')
check(r1.get('punish_acl') is False, 'punish_acl false')
check(r1.get('role_id') == 42, 'role_id in report')
check(os.path.exists(V.MARKER), 'marker written')
r2 = V.apply_vedushiy_role_seed(guild=g)
check(r2.get('applied') is False, 'second apply skipped')
check('already' in (r2.get('reason') or ''), f'reason={r2.get("reason")}')

# force re-apply
r3 = V.apply_vedushiy_role_seed(force=True, guild=g)
check(r3.get('applied') is True, 'force apply')

# seed must not write action_acl files
check(not os.path.exists('data/action_acl.json')
      and not os.path.exists(os.path.join('data', 'action_acl.json')),
      'no action_acl side effect')

print('== permissions builder ==')
perms = V.build_voice_host_permissions()
check(bool(perms.move_members) and bool(perms.mute_members)
      and bool(perms.deafen_members), 'Permissions bits set')
check(not bool(perms.ban_members) and not bool(perms.kick_members),
      'no ban/kick bits')

print('== force perms flag ==')
os.environ['VEDUSHIY_FORCE_PERMS'] = '1'
check(V.should_force_perms(), 'force on')
os.environ.pop('VEDUSHIY_FORCE_PERMS', None)

print(f'\n== RESULT: {PASS} passed, {FAIL} failed ==')
sys.exit(1 if FAIL else 0)
