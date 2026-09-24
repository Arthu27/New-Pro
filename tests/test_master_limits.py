# -*- coding: utf-8 -*-
"""Тир Master: средние лимиты + гейт Helper/Moderator.

Заказ создателя 2026-09-24:
  • лимиты = среднее между mod и curator;
  • применять наказания можно только с ролью Helper или Moderator;
  • Master + Eventsmod/Broadcaster без Helper/Mod — отказ.

Запуск: python3 tests/test_master_limits.py
"""
import os
import sys
import tempfile
import types

_TMP = tempfile.mkdtemp(prefix='hakumo_master_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

# роль-карта с Master
import json
json.dump({
    '803553848396349510': 'mod',
    '948969471916249119': 'mod',
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


from services import staff_limits as SL  # noqa: E402
from services import staff_hierarchy as SH  # noqa: E402
from services.staff_roles import (  # noqa: E402
    KNOWN_MASTER_ROLE_ID, KNOWN_HELPER_ROLE_ID, KNOWN_MODERATOR_ROLE_ID)

MASTER = 1552637932907667466
HELPER = 948969471916249119
MOD = 803553848396349510
EVENT = 852634463535759461
BROAD = 1551180629687664670
CUR = 807030012301541377


class Role:
    def __init__(self, rid, name='r'):
        self.id = rid
        self.name = name


class Mem:
    def __init__(self, uid, roles):
        self.id = uid
        self.roles = [Role(r) for r in roles]
        self.bot = False


print('== 1. IDs и тиры ==')
check(KNOWN_MASTER_ROLE_ID == MASTER, 'KNOWN_MASTER_ROLE_ID')
check('master' in SL.TIER_ORDER, 'TIER_ORDER has master')
check(SL.TIER_ORDER.index('master') == SL.TIER_ORDER.index('mod') + 1,
      'master сразу после mod')
check(SL.TIER_ORDER.index('master') < SL.TIER_ORDER.index('curator'),
      'master ниже curator')
check(SH.RANK['master'] == 2 and SH.RANK['mod'] == 1 and SH.RANK['curator'] == 3,
      'hierarchy RANK')

print('== 2. Лимиты = среднее mod↔curator ==')
mod_l = SL.TIER_DEFAULT_LIMITS['mod']
cur_l = SL.TIER_DEFAULT_LIMITS['curator']
mst_l = SL.TIER_DEFAULT_LIMITS['master']
expect = {
    'warn': 4,   # (3+5)/2
    'ban': 2,    # (1+3)/2
    'unmute': 4, # (3+5)/2
    'mute': 8,   # round((5+10)/2)
    'clear': 10,
}
for k, v in expect.items():
    check(mst_l[k] == v, f'master {k}={v}', mst_l.get(k))
    avg = round((mod_l[k] + cur_l[k]) / 2)
    check(mst_l[k] == avg, f'{k} == round(avg)', f'{mst_l[k]} vs {avg}')

# effective_limits для Master+Helper
lim, _ = SL.effective_limits(1, [MASTER, HELPER])
check(lim['warn'] == 4 and lim['ban'] == 2 and lim['mute'] == 8,
      f'effective Master+Helper: { {k: lim[k] for k in expect} }')

print('== 3. Гейт веток ==')
# Master alone
ok, deny = SL.master_punish_allowed(Mem(1, [MASTER]))
check(ok is False and deny and 'Helper' in deny, 'Master alone DENY')

# Master + Eventsmod
ok, deny = SL.master_punish_allowed(Mem(2, [MASTER, EVENT]))
check(ok is False, 'Master+Eventsmod DENY')

# Master + Broadcaster
ok, deny = SL.master_punish_allowed(Mem(3, [MASTER, BROAD]))
check(ok is False, 'Master+Broadcaster DENY')

# Master + Helper
ok, deny = SL.master_punish_allowed(Mem(4, [MASTER, HELPER]))
check(ok is True and deny is None, 'Master+Helper OK')

# Master + Moderator
ok, deny = SL.master_punish_allowed(Mem(5, [MASTER, MOD]))
check(ok is True, 'Master+Moderator OK')

# Curator alone (not master tier) — gate skips
ok, deny = SL.master_punish_allowed(Mem(6, [CUR]))
check(ok is True, 'Curator alone OK (gate N/A)')

# Helper alone — not master
ok, deny = SL.master_punish_allowed(Mem(7, [HELPER]))
check(ok is True, 'Helper alone OK (gate N/A)')

print('== 4. check_action уважает гейт ==')


class G:
    id = 99
    owner_id = 0


g = G()
ok, deny = SL.check_action(g, Mem(10, [MASTER, EVENT]), 'ban')
check(ok is False and deny and 'Helper' in deny,
      'check_action Master+Event ban DENY')

ok, deny = SL.check_action(g, Mem(11, [MASTER, HELPER]), 'ban')
# ban limit 2, used 0 → allowed
check(ok is True, 'check_action Master+Helper ban OK')

print('== 5. actions_for_member пустое для чужой ветки ==')
from cogs.moderation import actions_for_member  # noqa: E402

acts = actions_for_member(g, Mem(12, [MASTER, EVENT]))
check(acts == [], 'menu empty for Master+Eventsmod')

acts2 = actions_for_member(g, Mem(13, [MASTER, BROAD]))
check(acts2 == [], 'menu empty for Master+Broadcaster')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
# print limits card for owner
print('\n--- Лимиты Master (за сутки) ---')
print(f"  варн:   {mst_l['warn']}  (mod {mod_l['warn']} → curator {cur_l['warn']})")
print(f"  мут:    {mst_l['mute']}  (mod {mod_l['mute']} → curator {cur_l['mute']})")
print(f"  размут: {mst_l['unmute']}  (mod {mod_l['unmute']} → curator {cur_l['unmute']})")
print(f"  бан:    {mst_l['ban']}  (mod {mod_l['ban']} → curator {cur_l['ban']})")
print(f"  чистка: {mst_l['clear']}")
print(f"  роль:   × Master ({MASTER})")
print('  гейт:   нужна ещё роль Helper или Moderator')
sys.exit(1 if FAIL else 0)
