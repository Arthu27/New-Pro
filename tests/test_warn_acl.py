# -*- coding: utf-8 -*-
"""Warn ACL: куратор/админ ветки, без кросс-ветки, роль только curator+.

Запуск: python3 tests/test_warn_acl.py
"""
import os
import sys
import tempfile
import json

_TMP = tempfile.mkdtemp(prefix='hakumo_warn_acl_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

json.dump({
    '948969471916249119': 'helper',
    '803553848396349510': 'mod',
    '1552637932907667466': 'master',
    '807030012301541377': 'curator',
    '1189999426631122964': 'admin',
}, open('data/role_map.json', 'w'))

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


from services import warn_acl as WA  # noqa: E402
from services.staff_roles import (  # noqa: E402
    KNOWN_HELPER_ROLE_ID as HELPER,
    KNOWN_MODERATOR_ROLE_ID as MOD,
    KNOWN_CURATOR_ROLE_ID as CUR,
    KNOWN_MASTER_ROLE_ID as MASTER,
)
ADMIN = 1189999426631122964


class Role:
    def __init__(self, rid):
        self.id = rid


class Mem:
    def __init__(self, uid, roles, bot=False):
        self.id = uid
        self.roles = [Role(r) for r in roles]
        self.bot = bot
        self.guild = None


class Guild:
    id = 1
    owner_id = 0


g = Guild()

print('== 1. ветки ==')
check(WA.branches_of(Mem(1, [HELPER])) == frozenset({'helper'}), 'helper branch')
check(WA.branches_of(Mem(2, [MOD])) == frozenset({'mod'}), 'mod branch')
check(WA.branches_of(Mem(3, [CUR, HELPER])) == frozenset({'helper'}),
      'curator+helper → helper')
check(WA.branches_of(Mem(4, [ADMIN, MOD])) == frozenset({'mod'}),
      'admin+mod → mod')
check(WA.branches_of(Mem(5, [CUR])) == frozenset(), 'curator alone → no branch')

print('== 2. кто может выдавать ==')
check(WA.can_issue_manual_warn(Mem(1, [HELPER])) is False, 'helper NO')
check(WA.can_issue_manual_warn(Mem(2, [MOD])) is False, 'mod NO')
check(WA.can_issue_manual_warn(Mem(3, [MASTER, HELPER])) is False, 'master NO')
check(WA.can_issue_manual_warn(Mem(4, [CUR, HELPER])) is True, 'curator+helper YES')
check(WA.can_issue_manual_warn(Mem(5, [ADMIN, MOD])) is True, 'admin+mod YES')

print('== 3. роль warn только curator/admin ==')
check(WA.warn_role_eligible(Mem(1, [HELPER])) is False, 'helper role NO')
check(WA.warn_role_eligible(Mem(2, [MOD])) is False, 'mod role NO')
check(WA.warn_role_eligible(Mem(3, [CUR])) is True, 'curator role YES')
check(WA.warn_role_eligible(Mem(4, [ADMIN])) is True, 'admin role YES')

print('== 4. ручной варн: участник / ветки ==')
uye = Mem(10, [])
helper_staff = Mem(11, [HELPER])
mod_staff = Mem(12, [MOD])
cur_h = Mem(20, [CUR, HELPER])
adm_m = Mem(21, [ADMIN, MOD])
bot = Mem(99, [], bot=True)

ok, deny = WA.manual_warn_check(g, cur_h, uye)
check(ok is False and deny and 'бот' in deny.lower(),
      f'куратор → участник DENY: {deny}')

ok, deny = WA.manual_warn_check(g, bot, uye)
check(ok is True, 'бот → участник OK (авто)')

ok, deny = WA.manual_warn_check(g, cur_h, helper_staff)
check(ok is True, 'куратор хелперов → хелпер OK')

ok, deny = WA.manual_warn_check(g, cur_h, mod_staff)
check(ok is False and deny and 'ветк' in deny.lower(),
      f'куратор хелперов → модер DENY: {deny}')

ok, deny = WA.manual_warn_check(g, adm_m, mod_staff)
check(ok is True, 'админ модов → модер OK')

ok, deny = WA.manual_warn_check(g, adm_m, helper_staff)
check(ok is False and 'ветк' in (deny or '').lower(),
      f'админ модов → хелпер DENY: {deny}')

ok, deny = WA.manual_warn_check(g, Mem(30, [HELPER]), helper_staff)
check(ok is False, 'хелпер → хелпер DENY (не issuer)')

print('== 5. filter modpanel ==')
acts = [('warn', 'Варн', '', 'warn'), ('mute', 'Мут', '', 'mute')]
check(WA.filter_modpanel_actions(Mem(1, [HELPER]), acts) == [('mute', 'Мут', '', 'mute')],
      'helper меню без warn')
check(WA.filter_modpanel_actions(cur_h, acts) == acts,
      'куратор видит warn')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
