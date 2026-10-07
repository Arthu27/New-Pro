# -*- coding: utf-8 -*-
"""Warn 1/2/3 роли + порог 3: бан участнику / снятие стаффа + бан набора 30д.

Запуск: python3 tests/test_warn3_ladder.py
"""
import asyncio
import json
import os
import sys
import tempfile
import types
from datetime import datetime, timezone, timedelta

TMP = tempfile.mkdtemp(prefix='hakumo_warn3_')
os.chdir(TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

PASS = 0
FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


from services import punish_roles as PR  # noqa: E402
from services import staff_roles as SR  # noqa: E402
import cogs.staff_apply as SA  # noqa: E402
from cogs.warnings import warnings as WarnCog  # noqa: E402

GID = 793336829280780331

print('== 1. Known warn role IDs ==')
check(PR.KNOWN_WARN_ROLE_BY_LEVEL[1] == 1545468739221327942, 'warn_1 id')
check(PR.KNOWN_WARN_ROLE_BY_LEVEL[2] == 1557474469394518187, 'warn_2 id')
check(PR.KNOWN_WARN_ROLE_BY_LEVEL[3] == 1557474898069430394, 'warn_3 id')
check(PR.MAX_WARN_BEFORE_PUNISH == 3, 'порог 3')
check(PR.STAFF_APPLY_BAN_DAYS == 30, 'бан набора 30д')

print('== 2. ensure_known_warn_roles ==')
got = PR.ensure_known_warn_roles(GID, who='test')
check(got.get('warn_1') == 1545468739221327942, 'ensure warn_1', got)
check(got.get('warn_2') == 1557474469394518187, 'ensure warn_2', got)
check(got.get('warn_3') == 1557474898069430394, 'ensure warn_3', got)
add1, rem1 = PR.level_transition(GID, 1)
check(add1 == 1545468739221327942, 'level 1 → warn_1')
add2, rem2 = PR.level_transition(GID, 2)
check(add2 == 1557474469394518187, 'level 2 → warn_2')
check(1545468739221327942 in rem2, 'level 2 снимает warn_1')
add3, rem3 = PR.level_transition(GID, 3)
check(add3 == 1557474898069430394, 'level 3 → warn_3')
check(1557474469394518187 in rem3, 'level 3 снимает warn_2')

print('== 3. Staff apply ban 30d ==')
SA.BLACKLIST_FILE = 'data/staff_blacklist.json'
uid = '1502218831999926362'
res = SA.ban_staff_apply(uid, days=30, by='test', reason='3 warns', guild_id=GID)
check(res.get('days') == 30, 'ban_staff_apply days')
check(SA.is_blacklisted(uid, 'support'), 'ЧС support')
check(SA.is_blacklisted(uid, 'helper'), 'ЧС helper')
check(SA.apply_ban_until(uid), 'полный until')
deny = SA.apply_blocked_reason(uid, 'Support')
check('Набор закрыт' in deny or 'закрыт' in deny.lower(),
      'apply_blocked показывает бан набора', deny)

# просроченный until → можно снова
bl = SA.load_blacklist()
past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
for k in list(bl[uid]):
    bl[uid][k]['until'] = past
SA.save_blacklist(bl)
check(not SA.is_blacklisted(uid, 'support'), 'после until — ЧС снят')

print('== 4. strip_staff_roles + punish paths ==')


class R:
    def __init__(self, rid, name):
        self.id, self.name = int(rid), name
        self.position = 1
        self.managed = False


class Mem:
    def __init__(self, mid, roles=None):
        self.id = mid
        self.roles = list(roles or [])
        self.added = []
        self.removed = []
        self.guild = None
        self.display_name = 'u'
        self.bot = False

    async def add_roles(self, *roles, **kw):
        for r in roles:
            self.added.append(int(r.id))
            if all(int(getattr(x, 'id', 0)) != int(r.id) for x in self.roles):
                self.roles.append(r)

    async def remove_roles(self, *roles, **kw):
        ids = {int(r.id) for r in roles}
        self.removed.extend(sorted(ids))
        self.roles = [r for r in self.roles if int(r.id) not in ids]

    async def ban(self, **kw):
        self.banned = True


class G:
    def __init__(self):
        self.id = GID
        self.roles = [
            R(PR.KNOWN_WARN_ROLE_BY_LEVEL[1], 'warn 1'),
            R(PR.KNOWN_WARN_ROLE_BY_LEVEL[2], 'warn 2'),
            R(PR.KNOWN_WARN_ROLE_BY_LEVEL[3], 'warn 3'),
            R(SR.KNOWN_HELPER_ROLE_ID, '× Helper'),
            R(SR.KNOWN_COMMON_STAFF_ROLE_ID, '× Staff'),
            R(SR.KNOWN_GRANT_BY_KIND['support'], '× Support'),
            R(999888777, 'ban-role'),
        ]
        self.me = types.SimpleNamespace(
            top_role=R(1, 'bot'),
            guild_permissions=types.SimpleNamespace(manage_roles=True),
        )

    def get_role(self, rid):
        rid = int(rid or 0)
        return next((r for r in self.roles if r.id == rid), None)

    def get_channel(self, cid):
        return None


loop = asyncio.new_event_loop()
g = G()
PR.set_roles(GID, who='test', ban=999888777)

# strip staff
helper = R(SR.KNOWN_HELPER_ROLE_ID, '× Helper')
common = R(SR.KNOWN_COMMON_STAFF_ROLE_ID, '× Staff')
m_staff = Mem(42, roles=[helper, common, R(1, '@everyone')])
m_staff.guild = g
strip = loop.run_until_complete(SR.strip_staff_roles(g, m_staff, reason='test'))
check(SR.KNOWN_HELPER_ROLE_ID in strip.get('removed', []),
      'strip Helper', strip)
check(SR.KNOWN_COMMON_STAFF_ROLE_ID in strip.get('removed', []),
      'strip common', strip)

# cog punish: member → ban role
cog = WarnCog(types.SimpleNamespace())
m_user = Mem(1001, roles=[R(1, '@everyone')])
m_user.guild = g
# monkeypatch staff check
import services.warn_acl as WA  # noqa: E402
_orig = WA._is_staff_target
WA._is_staff_target = lambda guild, target: False
pun = loop.run_until_complete(cog.apply_warn_punishment(g, m_user, 3))
check(pun and 'Бан' in pun, 'участник @3 → бан', pun)
check(999888777 in m_user.added, 'участнику выдана ban-роль', m_user.added)

# staff @3 → strip + apply ban
WA._is_staff_target = lambda guild, target: True
m_st = Mem(1002, roles=[
    R(SR.KNOWN_HELPER_ROLE_ID, '× Helper'),
    R(SR.KNOWN_COMMON_STAFF_ROLE_ID, '× Staff'),
])
m_st.guild = g
SA.BLACKLIST_FILE = 'data/staff_blacklist.json'
pun2 = loop.run_until_complete(cog.apply_warn_punishment(g, m_st, 3))
check(pun2 and 'Снят со стаффа' in pun2, 'стафф @3 → снят', pun2)
check(SA.is_blacklisted(1002, 'moderator'), 'стафф в ЧС набора')
check('30' in pun2 or 'набор' in pun2.lower(), 'текст про набор', pun2)

# ниже порога — без авто-бана (пустой config)
WA._is_staff_target = _orig
m_low = Mem(1003)
pun0 = loop.run_until_complete(cog.apply_warn_punishment(g, m_low, 2))
check(pun0 is None, 'варн 2 без steps → без авто-наказания', pun0)

loop.close()
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
