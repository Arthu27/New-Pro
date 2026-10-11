# -*- coding: utf-8 -*-
"""Warn ACL: участникам — мод+; стаффу — только «× Отвечаю за …».

Staff-цель → отдельное меню (только warn-семейство).
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
uye = Mem(10, [])
helper_staff = Mem(11, [HELPER])
mod_staff = Mem(12, [MOD])
creative_staff = Mem(13, [CREATIVE])
mod_actor = Mem(40, [MOD])
otv_h = Mem(20, [HELP_CUR])
otv_m = Mem(21, [MOD_CUR])
otv_c = Mem(22, [CREATIVE_CUR])
bot = Mem(99, [], bot=True)

print('== 1. участникам — мод+ ==')
ok, deny = WA.manual_warn_check(g, mod_actor, uye)
check(ok is True, f'модер → участник OK ({deny})')
ok, deny = WA.manual_warn_check(g, Mem(41, [HELPER]), uye)
check(ok is False, f'хелпер → участник DENY ({deny})')
ok, deny = WA.manual_warn_check(g, bot, uye)
check(ok is True, 'бот → участник OK')
ok, deny = WA.manual_warn_check(g, otv_h, uye)
check(ok is True, 'отвечаю → участник OK')
ok, deny = WA.manual_warn_check(g, mod_actor, mod_actor)
check(ok is False, f'себе DENY ({deny})')

print('== 2. стаффу — только отвечаю за ==')
ok, deny = WA.manual_warn_check(g, mod_actor, helper_staff)
check(ok is False, f'модер → хелпер DENY ({deny})')
ok, deny = WA.manual_warn_check(g, Mem(42, [CUR, HELPER]), helper_staff)
check(ok is False, f'общий куратор → хелпер DENY ({deny})')
ok, deny = WA.manual_warn_check(g, otv_h, helper_staff)
check(ok is True, 'отвечаю Helper → хелпер OK')
ok, deny = WA.manual_warn_check(g, otv_h, mod_staff)
check(ok is False and 'ветк' in (deny or '').lower(),
      f'отвечаю Helper → модер DENY: {deny}')
ok, deny = WA.manual_warn_check(g, otv_m, mod_staff)
check(ok is True, 'отвечаю Mod → модер OK')
ok, deny = WA.manual_warn_check(g, otv_c, creative_staff)
check(ok is True, 'отвечаю Creative → creative OK')

print('== 3. filter modpanel ==')
acts = [('warn', 'Варн', '', 'warn'), ('mute', 'Мут', '', 'mute'),
        ('ban', 'Бан', '', 'ban')]
check(WA.filter_modpanel_actions(mod_actor, acts)
      == [('mute', 'Мут', '', 'mute'), ('ban', 'Бан', '', 'ban')],
      'без цели — warn скрыт')
check(WA.filter_modpanel_actions(mod_actor, acts, target=uye, guild=g) == acts,
      'модер + участник — warn виден')

# Стафф-цель: только warn-меню (модеру чужая ветка → пусто)
staff_menu_mod = WA.filter_modpanel_actions(
    mod_actor, acts, target=helper_staff, guild=g)
check(staff_menu_mod == [],
      f'модер + стафф — пустое staff-меню: {staff_menu_mod}')

staff_menu = WA.filter_modpanel_actions(
    otv_h, acts, target=helper_staff, guild=g)
keys = [a[0] for a in staff_menu]
check(keys[0] == 'warn' and 'mute' not in keys and 'ban' not in keys,
      f'отвечаю + свой стафф — только warn-меню: {keys}')
check('warn_history' in keys and 'unwarn' in keys,
      f'staff-меню содержит историю и снятие: {keys}')

print('== 4. правила: warn/ban по коду ==')
from services import mod_reasons as MR  # noqa: E402
check(MR.allows('1.1', 'ban') and MR.allows('1.1', 'warn'),
      '1.1 Бан/Варн')
check(MR.allows('1.1', 'ban') and not MR.allows('1.1', 'mute'),
      '1.1 без мута')
check(MR.allows('1.6', 'warn') and MR.allows('1.6', 'mute_chat')
      and not MR.allows('1.6', 'ban'), '1.6 Пред/Мут')
check(MR.STAFF_HINTS['1.1'].startswith('Бан/Варн'), 'hint 1.1')
check(MR.STAFF_HINTS['1.8'].startswith('Пред/Мут'), 'hint 1.8 Пред/Мут')
check('1.1' in MR.codes_for_action('ban')
      and '1.6' not in MR.codes_for_action('ban'),
      'ban rules filter')
check('1.8' in MR.codes_for_action('warn')
      and '1.1' in MR.codes_for_action('warn'),
      'warn rules filter')

print('== 5. is_staff: Discord Administrator / owner тоже стафф ==')
class _GP:
    def __init__(self, admin=False, manage_messages=False):
        self.administrator = admin
        self.manage_messages = manage_messages
        self.manage_guild = False
        self.ban_members = False
        self.kick_members = False
        self.moderate_members = False


class MemPerm(Mem):
    def __init__(self, uid, roles, *, admin=False, manage_messages=False):
        super().__init__(uid, roles, guild=g)
        self.guild_permissions = _GP(admin=admin, manage_messages=manage_messages)


admin_only = MemPerm(77, [], admin=True)
check(WA._is_staff_target(g, admin_only) is True,
      'Administrator без role_map → is_staff')
mm_only = MemPerm(78, [], manage_messages=True)
check(WA._is_staff_target(g, mm_only) is True,
      'manage_messages без role_map → is_staff')
nobody = MemPerm(79, [])
check(WA._is_staff_target(g, nobody) is False,
      'без прав и ролей → не стафф')
info = WA.get_staff_info(admin_only)
check(info[0] is True, 'get_staff_info(Administrator) → is_staff')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
