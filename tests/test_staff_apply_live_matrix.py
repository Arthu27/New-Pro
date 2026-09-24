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
    R(1552639452713848912, '× Отвечаю за Broadcaster'),
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

print('== 3b. Admin reviews all branches ==')
for app_kind in SR.POSITIONS:
    ok, deny = SR.can_review_position(
        CurMember(SR.KNOWN_ADMIN_ROLE_ID), SR.position_label(app_kind))
    check(ok, f'admin × {app_kind} → OK', f'deny={deny!r}')

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
      ['Moderator', 'Helper', 'Eventsmod', 'Broadcaster'], 'select EN')
check(StaffAppCardView(title='Moderator', body='x').has_components_v2(), 'V2 card')
from cogs.staff_apply import StaffReviewSelect  # noqa: E402
rev = StaffReviewSelect()
check([o.value for o in rev.options] == ['approve', 'reject', 'blacklist'],
      'review: Принять/Отклонить/Чёрный список')
for kind in SR.POSITIONS:
    tag = _curator_ping(
        types.SimpleNamespace(
            id=g.id,
            get_channel=lambda cid: None,
            get_role=g.get_role),
        SR.position_label(kind))
    check(tag == f"<@&{SR.KNOWN_CURATOR_BY_KIND[kind]}>", f'ping {kind}')

print('== 7. Channels + blacklist ==')
check(int(Config.APPLY_CHANNEL_ID) == 1312436222307860490, 'apps channel default')
check(int(Config.STAFF_MENU_CHANNEL_ID) == 1312429743865335939, 'menu channel default')
check(SA.APPLY_CHANNEL_ID == 1312436222307860490, 'SA.APPLY_CHANNEL_ID')
from services.channel_routes import (  # noqa: E402
    STAFF_MENU_CHANNEL_ID as _MENU, STAFF_APPLY_CHANNEL_ID as _APPS,
    KNOWN_CHANNELS)
check(_MENU == 1312429743865335939 and _APPS == 1312436222307860490,
      'KNOWN staff channels')
check(KNOWN_CHANNELS.get('staff_menu_channel') == _MENU, 'KNOWN menu route')

# apply_target prefers apply channel over ban_appeal room
apps_cid = 1312436222307860490
room_cid = 1544483947705008188


class _Chan:
    def __init__(self, cid):
        self.id = cid


class _GRoute:
    id = g.id

    def __init__(self):
        self._ch = {
            apps_cid: _Chan(apps_cid),
            room_cid: _Chan(room_cid),
        }

    def get_channel(self, cid):
        return self._ch.get(int(cid)) if cid else None

    def get_role(self, rid):
        return g.get_role(rid)


gr = _GRoute()
ch, _ = SA.apply_target('Helper', gr)
check(ch is not None and ch.id == apps_cid, 'apps before room')

# blacklist action
SA.BLACKLIST_FILE = 'data/staff_blacklist.json'
apps = {'u2': {
    'user_id': '77', 'role': 'Helper', 'status': 'pending',
    'message_id': '888', 'guild_id': str(g.id),
    'submitted_at': '2026-09-24T00:00:00', 'timestamp': '2026-09-24T00:00:00',
}}
json.dump(apps, open('data/staff_apps.json', 'w'))


class FakeMsg2:
    id = 888
    embeds = []
    content = None

    async def edit(self, **kw):
        pass


helper_cur2 = CurMember(SR.KNOWN_CURATOR_BY_KIND['helper'])
helper_cur2.display_name = 'HelperCur'
inter3 = types.SimpleNamespace(
    user=helper_cur2, message=FakeMsg2(), client=FakeClient(), guild=g,
    response=FakeResp(), followup=FakeFollow())
loop.run_until_complete(StaffReviewView()._review(inter3, 'blacklist'))
data = json.load(open('data/staff_apps.json'))
check(data['u2']['status'] == 'blacklisted', 'blacklist: status')
check(SA.is_blacklisted(77, 'Helper'), 'blacklist: Helper ветка')
check(not SA.is_blacklisted(77, 'Moderator'), 'blacklist: Moderator свободна')
check(not SA.is_blacklisted(999, 'Helper'), 'blacklist: other free')
check(SA.blacklisted_kinds(77) == ['helper'], 'blacklist: kinds list')

# blocked re-apply только своей ветки
class BlResp:
    def __init__(self):
        self._done = False
        self.modal = None

    def is_done(self):
        return self._done

    async def send_message(self, *a, **k):
        self._done = True

    async def send_modal(self, modal):
        self.modal = modal
        self._done = True


class RSHelper(RoleSelect):
    @property
    def values(self):
        return ['Helper']


class RSMod(RoleSelect):
    @property
    def values(self):
        return ['Moderator']


bl_inter = types.SimpleNamespace(
    user=types.SimpleNamespace(id=77),
    response=BlResp(), guild=g)
loop.run_until_complete(RSHelper().callback(bl_inter))
check(bl_inter.response.modal is None, 'Helper BL blocks Helper modal')

bl_other = types.SimpleNamespace(
    user=types.SimpleNamespace(id=77),
    response=BlResp(), guild=g)
loop.run_until_complete(RSMod().callback(bl_other))
check(bl_other.response.modal is not None, 'Helper BL: Moderator still open')

ok_inter2 = types.SimpleNamespace(
    user=types.SimpleNamespace(id=999),
    response=BlResp(), guild=g)
loop.run_until_complete(RSHelper().callback(ok_inter2))
check(ok_inter2.response.modal is not None, 'non-bl can open modal')

# pending на ветке → нельзя подать снова на ту же
apps_pend = {
    '55:event': {
        'user_id': '55', 'role': 'Eventsmod', 'kind': 'event',
        'status': 'pending', 'submitted_at': '2026-09-24T00:00:00',
    }
}
json.dump(apps_pend, open('data/staff_apps.json', 'w'))
deny_pend = SA.apply_blocked_reason(55, 'Eventsmod')
check(deny_pend and 'рассмотрении' in deny_pend.lower(),
      'pending Events blocks re-apply', deny_pend)
check(not SA.apply_blocked_reason(55, 'Helper'),
      'pending Events: Helper still open')
# approved → тоже нельзя
apps_pend['55:event']['status'] = 'approved'
json.dump(apps_pend, open('data/staff_apps.json', 'w'))
deny_ok = SA.apply_blocked_reason(55, 'Eventsmod')
check(deny_ok and ('приняли' in deny_ok.lower() or 'принят' in deny_ok.lower()),
      'approved Events blocks re-apply', deny_ok)
# rejected → можно снова
apps_pend['55:event']['status'] = 'rejected'
json.dump(apps_pend, open('data/staff_apps.json', 'w'))
check(not SA.apply_blocked_reason(55, 'Eventsmod'),
      'rejected Events allows re-apply')

# нет staff-panel команды
src = open(os.path.join(ROOT, 'cogs', 'staff_apply.py'), encoding='utf-8').read()
check('name="staff-panel"' not in src and '_ensure_staff_menu' in src,
      'меню само, без /staff-panel')
check('apply_blocked_reason' in src and 'app_storage_key' in src,
      'повтор заявок на ветку блокируется')

loop.close()
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
