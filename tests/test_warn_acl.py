# -*- coding: utf-8 -*-
"""Warn ACL: только «× Отвечаю за …» своей ветки.

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
    KNOWN_CURATOR_BY_KIND,
    KNOWN_GRANT_BY_KIND,
)
ADMIN = 1189999426631122964
CREATIVE = int(KNOWN_GRANT_BY_KIND['creative'])
CREATIVE_CUR = int(KNOWN_CURATOR_BY_KIND['creative'])
MOD_CUR = int(KNOWN_CURATOR_BY_KIND['moderator'])
HELP_CUR = int(KNOWN_CURATOR_BY_KIND['helper'])


class Role:
    def __init__(self, rid):
        self.id = rid


class Mem:
    def __init__(self, uid, roles, bot=False, guild=None):
        self.id = uid
        self.roles = [Role(r) for r in roles]
        self.bot = bot
        self.guild = guild


class Guild:
    id = 1
    owner_id = 0

    def get_member(self, uid):
        return None


g = Guild()

print('== 1. ветки цели / issuer ==')
check(WA.branches_of(Mem(1, [HELPER])) == frozenset({'helper'}), 'helper branch')
check(WA.branches_of(Mem(2, [MOD])) == frozenset({'moderator'}), 'mod branch')
check(WA.issuer_branches_of(Mem(3, [HELP_CUR])) == frozenset({'helper'}),
      'отвечаю за Helper → helper')
check(WA.issuer_branches_of(Mem(4, [MOD_CUR])) == frozenset({'moderator'}),
      'отвечаю за Moderator → moderator')
check(WA.issuer_branches_of(Mem(5, [CUR, HELPER])) == frozenset(),
      'общий куратор без «отвечаю» → нет issuer-ветки')
check(WA.branches_of(Mem(6, [CREATIVE])) == frozenset({'creative'}),
      'creative staff branch')

print('== 2. кто может выдавать (только отвечаю за) ==')
check(WA.can_issue_manual_warn(Mem(1, [HELPER])) is False, 'helper NO')
check(WA.can_issue_manual_warn(Mem(2, [MOD])) is False, 'mod NO')
check(WA.can_issue_manual_warn(Mem(3, [MASTER, HELPER])) is False,
      'master без отвечаю NO')
check(WA.can_issue_manual_warn(Mem(4, [CUR, HELPER])) is False,
      'общий curator без отвечаю NO')
check(WA.can_issue_manual_warn(Mem(5, [ADMIN, MOD])) is False,
      'admin без отвечаю NO')
check(WA.can_issue_manual_warn(Mem(6, [HELP_CUR])) is True,
      '× Отвечаю за Helper YES')
check(WA.can_issue_manual_warn(Mem(7, [MOD_CUR])) is True,
      '× Отвечаю за Moderator YES')
check(WA.can_issue_manual_warn(Mem(8, [CREATIVE_CUR])) is True,
      '× Отвечаю за Creative YES')

print('== 3. роль warn только у отвечаю за ==')
check(WA.warn_role_eligible(Mem(1, [HELPER])) is False, 'helper role NO')
check(WA.warn_role_eligible(Mem(2, [CUR])) is False, 'общий curator NO')
check(WA.warn_role_eligible(Mem(3, [HELP_CUR])) is True, 'отвечаю YES')

print('== 4. ручной варн ==')
uye = Mem(10, [])
helper_staff = Mem(11, [HELPER])
mod_staff = Mem(12, [MOD])
creative_staff = Mem(13, [CREATIVE])
otv_h = Mem(20, [HELP_CUR])
otv_m = Mem(21, [MOD_CUR])
otv_c = Mem(22, [CREATIVE_CUR])
bot = Mem(99, [], bot=True)

ok, deny = WA.manual_warn_check(g, otv_h, uye)
check(ok is False and deny and 'бот' in deny.lower(),
      f'отвечаю → участник DENY: {deny}')

ok, deny = WA.manual_warn_check(g, bot, uye)
check(ok is True, 'бот → участник OK')

ok, deny = WA.manual_warn_check(g, otv_h, helper_staff)
check(ok is True, 'отвечаю Helper → хелпер OK')

ok, deny = WA.manual_warn_check(g, otv_h, mod_staff)
check(ok is False and 'ветк' in (deny or '').lower(),
      f'отвечаю Helper → модер DENY: {deny}')

ok, deny = WA.manual_warn_check(g, otv_m, mod_staff)
check(ok is True, 'отвечаю Mod → модер OK')

ok, deny = WA.manual_warn_check(g, otv_m, helper_staff)
check(ok is False and 'ветк' in (deny or '').lower(),
      f'отвечаю Mod → хелпер DENY: {deny}')

ok, deny = WA.manual_warn_check(g, Mem(30, [CUR, HELPER]), helper_staff)
check(ok is False, 'общий куратор → DENY')

ok, deny = WA.manual_warn_check(g, otv_c, creative_staff)
check(ok is True, 'отвечаю Creative → creative OK')

ok, deny = WA.manual_warn_check(g, otv_c, helper_staff)
check(ok is False and 'ветк' in (deny or '').lower(),
      f'creative → helper DENY: {deny}')

print('== 5. filter modpanel ==')
acts = [('warn', 'Варн', '', 'warn'), ('mute', 'Мут', '', 'mute')]
check(WA.filter_modpanel_actions(Mem(1, [CUR, HELPER]), acts)
      == [('mute', 'Мут', '', 'mute')],
      'общий куратор — warn скрыт')
check(WA.filter_modpanel_actions(otv_h, acts)
      == [('mute', 'Мут', '', 'mute')],
      'отвечаю без цели — warn скрыт')
check(WA.filter_modpanel_actions(otv_h, acts, target=helper_staff, guild=g) == acts,
      'отвечаю + свой хелпер — warn виден')
check(WA.filter_modpanel_actions(otv_h, acts, target=mod_staff, guild=g)
      == [('mute', 'Мут', '', 'mute')],
      'отвечаю + чужая ветка — warn скрыт')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
