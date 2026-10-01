# -*- coding: utf-8 -*-
"""Иерархия: role_map > Discord Administrator для наказаний.

Запуск: python3 tests/test_staff_ladder_hierarchy.py
"""
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_ladder_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

HELPER = 948969471916249119
OTV_H = 1551525681207189504
CUR = 807030012301541377

json.dump({
    str(HELPER): 'helper',
    str(OTV_H): 'curator',
    str(CUR): 'curator',
}, open('data/role_map.json', 'w'))

from services import staff_hierarchy as SH  # noqa: E402

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


class Role:
    def __init__(self, rid, name='r'):
        self.id = rid
        self.name = name


class Perms:
    def __init__(self, admin=False):
        self.administrator = admin
        self.ban_members = False
        self.manage_guild = False
        self.manage_messages = False


class Mem:
    def __init__(self, uid, roles, admin=False):
        self.id = uid
        self.bot = False
        self.roles = [Role(r) for r in roles]
        self.guild_permissions = Perms(admin)


class G:
    id = 1
    owner_id = 0


g = G()
# куратор хелперов + Discord Admin
actor = Mem(10, [OTV_H, HELPER], admin=True)
# хелпер с Discord Admin (как ^^groM)
target = Mem(20, [HELPER], admin=True)

print('== staff_ladder vs Discord Admin ==')
check(SH.best_mapped_tier(actor) == 'curator', 'mapped actor curator')
check(SH.target_panel_role(g, actor) == 'admin',
      'panel actor admin (меню)')
check(SH.staff_ladder_role(g, actor) == 'curator',
      'ladder actor curator')
check(SH.staff_ladder_role(g, target) == 'helper',
      'ladder target helper (не admin)')

ok, deny, ar, tr = SH.check(g, actor, target, 'unmute_chat')
check(ok is True and ar == 'curator' and tr == 'helper',
      f'куратор хелперов снимает мут с хелпера+DiscordAdmin ({ar}->{tr} {deny})')

# два куратора — нельзя
a2 = Mem(11, [CUR], admin=True)
t2 = Mem(21, [OTV_H], admin=False)
ok, deny, ar, tr = SH.check(g, a2, t2, 'unmute_chat')
check(ok is False and ar == 'curator' and tr == 'curator',
      f'куратор≠куратор ({ar}->{tr})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
