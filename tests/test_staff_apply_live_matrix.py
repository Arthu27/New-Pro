# -*- coding: utf-8 -*-
"""Набор: авто-выдача ролей + изоляция кураторов 4×4.

Проверяет:
  1) grant IDs (Helper/Moderator/Eventsmod/Broadcaster);
  2) resolve → add_roles после approve;
  3) куратор чужой ветки не может принять (роль не выдаётся);
  4) куратор своей ветки принимает и выдаёт роль;
  5) пинги кураторов по веткам.

Запуск: python3 tests/test_staff_apply_live_matrix.py
"""
import asyncio
import json
import os
import sys
import tempfile
import types

TMP = tempfile.mkdtemp(prefix='hakumo_staff_matrix_')
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


from services import staff_roles as SR  # noqa: E402
from cogs.staff_apply import (  # noqa: E402
    StaffReviewView, RoleSelect, StaffAppCardView, _curator_ping)
from config import Config  # noqa: E402
import cogs.staff_apply as SA  # noqa: E402

SA.APPS_FILE = 'data/staff_apps.json'

EXPECT_GRANT = {
    'helper': 948969471916249119,
    'moderator': 803553848396349510,
    'event': 852634463535759461,
    'broadcaster': 1551180629687664670,
}


class R:
    def __init__(self, rid, name):
        self.id, self.name = rid, name


class Mem:
    def __init__(self, mid):
        self.id = mid
        self.added = []

    async def add_roles(self, role, **kw):
        self.added.append(role.id)


class G:
    def __init__(self, roles):
        self.id = 793336829280780331
        self.roles = roles
        self._m = {}

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == int(rid)), None)

    def get_member(self, uid):
        return self._m.get(int(uid))


live_roles = [
    R(948969471916249119, '× Helper'),
    R(803553848396349510, '× Moderator'),
    R(852634463535759461, '× Eventsmod'),
    R(1551180629687664670, '× Broadcaster'),
    R(1551525681207189504, '× Отвечаю за Helper'),
    R(1551524708552278036, '× Отвечаю за Moderator'),
    R(1551527644326002748, '× Отвечаю за Eventsmod'),
    R(1552640159051157576, '× Отвечаю за Broadcaster'),
]
g = G(live_roles)
loop = asyncio.new_event_loop()

print('== 1. Grant IDs ==')
for kind, rid in EXPECT_GRANT.items():
    check(SR.KNOWN_GRANT_BY_KIND.get(kind) == rid, f'KNOWN_GRANT {kind}')
    cfg = getattr(Config, {
        'helper': 'STAFF_HELPER_ROLE_ID',
        'moderator': 'STAFF_MODERATOR_ROLE_ID',
        'event': 'STAFF_EVENT_ROLE_ID',
        'broadcaster': 'STAFF_BROADCASTER_ROLE_ID',
    }[kind])
    check(int(cfg) == rid, f'Config {kind}')
    role, _ = SR.resolve_staff_role(g, kind)
    check(role is not None and role.id == rid, f'resolve {kind}')

print('== 2. Auto-grant all 4 ==')
for kind, rid in EXPECT_GRANT.items():
    m = Mem(1000 + list(EXPECT_GRANT).index(kind))
    g._m[m.id] = m
    res = loop.run_until_complete(
        SR.grant_staff_role(g, m.id, SR.position_label(kind)))
    check(res.get('role_name') and rid in m.added,
          f'grant {SR.position_label(kind)}', res)

print('== 3. Isolation matrix 4×4 ==')


class CurRole:
    def __init__(self, rid):
        self.id = rid


class CurPerm:
    administrator = False


class CurMember:
    guild_permissions = CurPerm()

    def __init__(self, rid):
        self.roles = [CurRole(rid)]
        self.guild = types.SimpleNamespace(id=g.id)
        self.display_name = 'cur'


for cur_kind in SR.POSITIONS:
    cur_rid = SR.KNOWN_CURATOR_BY_KIND[cur_kind]
    for app_kind in SR.POSITIONS:
        ok, deny = SR.can_review_position(
            CurMember(cur_rid), SR.position_label(app_kind))
        should = cur_kind == app_kind
        check(ok is should,
              f'{cur_kind} × {app_kind} → {"OK" if should else "DENY"}',
              f'ok={ok} deny={deny!r}')

print('== 4. Discord review: deny wrong branch (no grant) ==')
apps = {'u1': {
    'user_id': '42', 'role': 'Eventsmod', 'status': 'pending',
    'message_id': '999', 'guild_id': str(g.id),
    'submitted_at': '2026-09-24T00:00:00', 'timestamp': '2026-09-24T00:00:00',
}}
json.dump(apps, open('data/staff_apps.json', 'w'))


class FakeMsg:
    id = 999
    embeds = []
    content = None

    async def edit(self, **kw):
        pass


class FakeResp:
    def __init__(self):
        self._done = False
        self.kw = {}

    def is_done(self):
        return self._done

    async def defer(self, **kw):
        self._done = True

    async def send_message(self, *a, **k):
        self._done = True
        self.kw = k


class FakeFollow:
    def __init__(self):
        self.msgs = []

    async def send(self, *a, **k):
        self.msgs.append(k or a)


class FakeClient:
    def get_guild(self, gid):
        return g

    async def fetch_user(self, uid):
        u = types.SimpleNamespace(id=uid)

        async def send(*a, **k):
            pass

        u.send = send
        return u


m42 = Mem(42)
g._m[42] = m42
helper_cur = CurMember(SR.KNOWN_CURATOR_BY_KIND['helper'])
helper_cur.display_name = 'HelperCur'
inter = types.SimpleNamespace(
    user=helper_cur, message=FakeMsg(), client=FakeClient(), guild=g,
    response=FakeResp(), followup=FakeFollow())
loop.run_until_complete(StaffReviewView()._review(inter, 'approve'))
data = json.load(open('data/staff_apps.json'))
check(data['u1']['status'] == 'pending', 'чужая ветка: статус не тронут')
check(m42.added == [], 'чужая ветка: роль не выдана')

print('== 5. Discord review: own branch grants ==')
apps['u1']['status'] = 'pending'
json.dump(apps, open('data/staff_apps.json', 'w'))
event_cur = CurMember(SR.KNOWN_CURATOR_BY_KIND['event'])
event_cur.display_name = 'EventCur'
inter2 = types.SimpleNamespace(
    user=event_cur, message=FakeMsg(), client=FakeClient(), guild=g,
    response=FakeResp(), followup=FakeFollow())
m42.added.clear()
loop.run_until_complete(StaffReviewView()._review(inter2, 'approve'))
data = json.load(open('data/staff_apps.json'))
check(data['u1']['status'] == 'approved', 'своя ветка: approved')
check(EXPECT_GRANT['event'] in m42.added, 'своя ветка: Eventsmod выдана')
check(data['u1'].get('granted_role') == '× Eventsmod', 'granted_role в базе')

print('== 6. UI + curator pings ==')
sel = RoleSelect()
check([o.value for o in sel.options] ==
      ['Helper', 'Moderator', 'Eventsmod', 'Broadcaster'], 'select EN')
check(StaffAppCardView(title='Moderator', body='x').has_components_v2(), 'V2 card')
for kind in SR.POSITIONS:
    tag = _curator_ping(
        types.SimpleNamespace(
            id=g.id,
            get_channel=lambda cid: None,
            get_role=g.get_role),
        SR.position_label(kind))
    check(tag == f"<@&{SR.KNOWN_CURATOR_BY_KIND[kind]}>", f'ping {kind}')

loop.close()
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
