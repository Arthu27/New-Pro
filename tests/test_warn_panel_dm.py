# -*- coding: utf-8 -*-
"""Warn reasons / DM / store reason_type / staff never gets role.

Запуск: python3 tests/test_warn_panel_dm.py
"""
import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='hakumo_warn_panel_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['WARN_ROLE_ID'] = '1545468739221327942'
os.environ['MAIN_GUILD_ID'] = '777'

PASS = FAIL = 0
WARN_RID = 1545468739221327942
HELPER = 948969471916249119


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== 1. reasons config ==')
from services import warn_reasons as WR  # noqa: E402
check(len(WR.MEMBER_WARN_REASONS) >= 5, 'member reasons')
check(len(WR.STAFF_WARN_REASONS) >= 5, 'staff reasons')
check(WR.find_reason('staff', 'abuse') is not None, 'staff abuse code')
check('abuse' not in [c for c, *_ in WR.MEMBER_WARN_REASONS],
      'staff codes not in member list')
fmt = WR.format_reason('staff', 'abuse', 'тест')
check('abuse' in fmt and 'тест' in fmt, f'format staff: {fmt}')

print('== 2. store reason_type migration ==')
from services import warn_store as WS  # noqa: E402
WS.ensure_table()
row = WS.add_warn(
    777, 101, 202, '1.8 · Спам — флуд',
    reason_type='member', reason_code='1.8', source='discord')
check(row.get('reason_type') == 'member', 'reason_type member')
check(row.get('reason_code') == '1.8', 'reason_code')
row2 = WS.add_warn(
    777, 102, 202, 'abuse · Злоупотребление — x',
    is_staff_target=True, branch='helper',
    reason_type='staff', reason_code='abuse', source='web')
check(row2.get('reason_type') == 'staff', 'reason_type staff')
check(row2.get('source') == 'web', 'source web')
st = WS.stats_active(777)
check(st['active_warns'] == 2, f"stats {st}")
lst, total = WS.list_guild_warns(777, reason_type='staff')
check(total == 1 and lst[0]['reason_code'] == 'abuse', 'filter staff')
rm = WS.deactivate_warn(row['id'], 202, removed_reason='ошибка')
check(rm and rm.get('active') == 0 and rm.get('removed_reason') == 'ошибка',
      'soft remove + reason')

print('== 3. DM builders ==')
from services import warn_dm as WDM  # noqa: E402
guild = SimpleNamespace(name='Test', icon=None)
mod = SimpleNamespace(display_name='Curator', id=1)
em = WDM.build_member_warn_dm(
    guild, mod, reason='спам', warn_id=1, active_count=2)
check('Предупреждение' in (em.title or ''), 'member dm title')
check(em.color and int(em.color.value) == 0xF39C12, 'member yellow/orange')
es = WDM.build_staff_warn_dm(
    guild, mod, reason='abuse', warn_id=2, active_count=1, branch='Helper')
check('сотрудник' in (es.title or '').lower(), 'staff dm title')
check(es.color and int(es.color.value) == 0x8B0000, 'staff dark red')
check('не выдаётся' in (es.description or '').lower()
      or 'не выдается' in (es.description or '').lower(),
      'staff dm: роль не выдаётся')
eu = WDM.build_member_unwarn_dm(
    guild, mod, reason='x', warn_id=1, active_count=0)
check('снят' in (eu.title or '').lower(), 'member unwarn dm')
eu2 = WDM.build_staff_unwarn_dm(
    guild, mod, reason='x', warn_id=2, active_count=0, branch='Helper')
check('личном деле' in (eu2.title or '').lower()
      or 'снят' in (eu2.description or '').lower(), 'staff unwarn dm')

print('== 4. sync_warn_role never on staff ==')
from services import warn_role as WRole  # noqa: E402


class FakeRole:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name
        self.members = []


class FakeMember:
    def __init__(self, uid, guild, roles=None):
        self.id = uid
        self.guild = guild
        self.roles = list(roles or [])
        self.added = []
        self.removed = []
        self.display_name = str(uid)
        self.bot = False

    async def add_roles(self, role, reason=None):
        self.added.append(role.id)
        if role not in self.roles:
            self.roles.append(role)

    async def remove_roles(self, role, reason=None):
        self.removed.append(role.id)
        if role in self.roles:
            self.roles.remove(role)


class FakeGuild:
    def __init__(self):
        self.id = 777
        self._roles = {WARN_RID: FakeRole(WARN_RID, 'warn'),
                       HELPER: FakeRole(HELPER, 'Helper')}

    def get_role(self, rid):
        return self._roles.get(rid)


g = FakeGuild()
warn_role = g.get_role(WARN_RID)
helper_role = g.get_role(HELPER)
# staff with active warn + mistakenly has role → remove
WS.add_warn(777, 303, 1, 'staff test', is_staff_target=True,
            reason_type='staff', reason_code='abuse')
staff = FakeMember(303, g, roles=[helper_role, warn_role])
# monkeypatch is_staff
_orig = WRole.is_staff_member
WRole.is_staff_member = lambda guild, m: True
st = asyncio.get_event_loop().run_until_complete(WRole.sync_warn_role(staff))
WRole.is_staff_member = _orig
check(WARN_RID in staff.removed, f'staff role removed ({st})')
check(WARN_RID not in staff.added, 'staff never added warn role')

# member with active → add
WS.add_warn(777, 404, 1, 'member', reason_type='member', reason_code='1.8')
mem = FakeMember(404, g, roles=[])
WRole.is_staff_member = lambda guild, m: False
st2 = asyncio.get_event_loop().run_until_complete(WRole.sync_warn_role(mem))
WRole.is_staff_member = _orig
check(WARN_RID in mem.added, f'member got warn role ({st2})')

print('== 5. shared module wiring ==')
check(os.path.isfile(os.path.join(ROOT, 'services/warn_actions.py')),
      'warn_actions exists')
check(os.path.isfile(os.path.join(ROOT, 'services/warn_dm.py')),
      'warn_dm exists')
src = open(os.path.join(ROOT, 'cogs/warnings.py'), encoding='utf-8').read()
check('warn_actions' in src, 'warnings cog uses warn_actions')
msrc = open(os.path.join(ROOT, 'cogs/moderation.py'), encoding='utf-8').read()
check('warn_reasons' in msrc and 'warn_reason_type' in msrc,
      'modpanel uses staff/member reasons')
wsrc = open(os.path.join(ROOT, 'web/app.py'), encoding='utf-8').read()
check('/api/warns/issue' in wsrc and '/api/bans/unban' in wsrc,
      'web API warn/unban')
check('list_users_aggregated' in wsrc or 'list_guild_warns' in wsrc,
      'web uses warn_store list')
check("'/warns'" in wsrc or 'def warns(' in wsrc, 'warns page route')
check("'/bans'" in wsrc, 'bans page route')
check("'bans'" in wsrc and 'mod_nav_keys' in wsrc, 'nav wiring present')
check(os.path.isfile(os.path.join(ROOT, 'services/warn_board.py')),
      'warn_board exists')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
