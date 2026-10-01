# -*- coding: utf-8 -*-
"""Матрица лимитов: admin ≠ helper, мод/мастер/куратор по лестнице.

Запуск: python3 tests/test_staff_limits_matrix.py
"""
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_lim_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

HELPER = 948969471916249119
MOD = 803553848396349510
MASTER = 1552637932907667466
CUR = 807030012301541377
OTV_H = 1551525681207189504
ASS = 1552815174115664013
ADMIN = 1189999426631122964
STAFF_ADMIN = 1549118975110152263
GID = 793336829280780331

json.dump({
    str(HELPER): 'helper',
    str(MOD): 'mod',
    str(MASTER): 'master',
    str(CUR): 'curator',
    str(OTV_H): 'curator',
    str(ASS): 'assistent',
    str(ADMIN): 'admin',
    str(STAFF_ADMIN): 'admin',
}, open('data/role_map.json', 'w'))

from services.staff_limits import (  # noqa: E402
    TIER_DEFAULT_LIMITS, limits_for_roles, set_role_limits, unset_role_keys,
)
from services.helper_acl_seed import HELPER_LIMITS  # noqa: E402
from services.staff_admin_acl_seed import ADMIN_LIMITS, STAFF_ADMIN_LIMITS  # noqa: E402

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


# как на проде после сидов
set_role_limits(GID, HELPER, **HELPER_LIMITS)
unset_role_keys(GID, HELPER, limit_keys=('warn', 'ban', 'kick'))
set_role_limits(GID, ADMIN, **ADMIN_LIMITS)
set_role_limits(GID, STAFF_ADMIN, **STAFF_ADMIN_LIMITS)
set_role_limits(GID, OTV_H, **TIER_DEFAULT_LIMITS['curator'])
set_role_limits(GID, MASTER, **TIER_DEFAULT_LIMITS['master'])
set_role_limits(GID, ASS, **TIER_DEFAULT_LIMITS['assistent'])

print('== ladder counts ==')
h = limits_for_roles(GID, [HELPER])
m = limits_for_roles(GID, [MOD])
mst = limits_for_roles(GID, [MASTER, HELPER])
c = limits_for_roles(GID, [OTV_H, HELPER])
a = limits_for_roles(GID, [ASS, HELPER])
ad = limits_for_roles(GID, [ADMIN])
ad_h = limits_for_roles(GID, [ADMIN, HELPER])
sa = limits_for_roles(GID, [STAFF_ADMIN, HELPER])

check(h.get('mute') == 3 and h.get('unmute') == 3, f'helper mute/unmute=3 ({h.get("mute")})')
check(m.get('mute') == 3 and m.get('warn') == 3, f'mod mute=3 warn=3 ({m.get("mute")}/{m.get("warn")})')
check(mst.get('mute') == 5, f'master+helper mute=5 ({mst.get("mute")})')
check(c.get('mute') == 7 and c.get('ban') == 2, f'otv+helper curator 7/2 ({c.get("mute")}/{c.get("ban")})')
check(a.get('mute') == 9, f'assistent+helper mute=9 ({a.get("mute")})')
check(ad.get('mute') == 10 and ad.get('ban') == 5,
      f'admin mute=10 ban=5 ({ad.get("mute")}/{ad.get("ban")})')
check(ad_h.get('mute') == 10 and ad_h.get('ban') == 5,
      f'admin+helper НЕ хелперские ({ad_h.get("mute")}/{ad_h.get("ban")})')
check(sa.get('mute') == 12 and sa.get('ban') == 7,
      f'staff_admin+helper 12/7 ({sa.get("mute")}/{sa.get("ban")})')
check(ad.get('mute') > h.get('mute') and ad.get('ban') > h.get('ban'),
      'admin строже/мягче хелпера по квоте (выше числа)')
check(h.get('mute') < mst.get('mute') < c.get('mute') < a.get('mute') <= ad.get('mute'),
      'лестница mute: H < Master < Cur < Ass ≤ Admin')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
