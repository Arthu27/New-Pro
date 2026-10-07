# -*- coding: utf-8 -*-
"""Единая роль warn + SQLite + sync_warn_role.

- счётчик = active-записи в таблице warns
- стаффу роль warn никогда не выдаётся
- обычному участнику с active>0 — роль есть; active=0 — снимается

Запуск: python3 tests/test_warn_system.py
"""
import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='hakumo_warn_sys_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['WARN_ROLE_ID'] = '1545468739221327942'
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
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


from services import warn_store as WS  # noqa: E402
from services import warn_role as WR  # noqa: E402
from services.warn_config import warn_role_id  # noqa: E402
import cogs.warnings as Wcog  # noqa: E402


class FakeRole:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name
        self.managed = False
        self.members = []


class FakeMember:
    def __init__(self, uid, name, guild, roles=None):
        self.id = uid
        self.name = name
        self.display_name = name
        self.guild = guild
        self.roles = list(roles or [])
        self.added = []
        self.removed = []
        self.bot = False

    @property
    def mention(self):
        return f'<@{self.id}>'

    display_avatar = SimpleNamespace(url='https://x.test/a.png')

    async def add_roles(self, role, reason=None):
        self.added.append((role.id, reason))
        if role not in self.roles:
            self.roles.append(role)

    async def remove_roles(self, role, reason=None):
        self.removed.append((role.id, reason))
        if role in self.roles:
            self.roles.remove(role)

    async def send(self, **kw):
        return None


class FakeGuild:
    def __init__(self, gid):
        self.id = gid
        self.name = 'Сервер теста'
        self.icon = None
        self.owner_id = 1
        self._roles = {
            WARN_RID: FakeRole(WARN_RID, 'warn'),
            HELPER: FakeRole(HELPER, 'Helper'),
        }

    def get_role(self, rid):
        return self._roles.get(int(rid))

    def get_member(self, uid):
        return None

    def get_channel(self, cid):
        return None


print('== 1. конфиг роли ==')
check(warn_role_id() == WARN_RID, f'WARN_ROLE_ID={warn_role_id()}')

print('== 2. store: add / count / deactivate ==')
WS.ensure_table()
row = WS.add_warn(777, 42, 99, 'флуд', is_staff_target=False)
check(row['id'] > 0 and row['active'] == 1, f'add_warn id={row["id"]}')
check(WS.count_active(777, 42) == 1, 'count=1')
WS.add_warn(777, 42, 99, 'ещё', is_staff_target=False)
check(WS.count_active(777, 42) == 2, 'count=2')
removed = WS.deactivate_last_active(777, 42, 99)
check(removed and removed['active'] == 0, 'deactivate soft')
check(WS.count_active(777, 42) == 1, 'count после снятия=1')
hist = WS.list_warns(777, 42)
check(len(hist) == 2, f'история сохранена: {len(hist)}')

print('== 3. sync_warn_role: участник ==')
guild = FakeGuild(777)
uye = FakeMember(42, 'Uye', guild)
# уже 1 active
st = asyncio.run(WR.sync_warn_role(uye))
check(st == 'added', f'sync выдал роль: {st}')
check(any(r.id == WARN_RID for r in uye.roles), 'роль warn на участнике')

# снимаем последний → 0
WS.deactivate_last_active(777, 42, 99)
st = asyncio.run(WR.sync_warn_role(uye))
check(st == 'removed', f'sync снял роль: {st}')
check(not any(r.id == WARN_RID for r in uye.roles), 'роли warn нет')

print('== 4. sync_warn_role: стафф — никогда ==')
staff = FakeMember(50, 'Helper', guild,
                   roles=[guild.get_role(HELPER)])
WS.add_warn(777, 50, 99, 'опоздание', is_staff_target=True, branch='helper')
# вручную повесили роль — sync должен снять
staff.roles.append(guild.get_role(WARN_RID))
st = asyncio.run(WR.sync_warn_role(staff))
check(st == 'removed', f'стафф: роль снята ({st})')
check(not any(r.id == WARN_RID for r in staff.roles),
      'у стаффа нет warn-роли')
check(WS.count_active(777, 50) == 1, 'варн в БД у стаффа остался')

print('== 5. cog add_warning / remove ==')
bot = SimpleNamespace(guilds=[])
cog = Wcog.warnings(bot)
mod = FakeMember(99, 'Mod', guild)
target = FakeMember(60, 'User', guild)
# бот-актор: без ACL
mod.bot = True
res = asyncio.run(cog.add_warning(target, mod, 'тест'))
check(res[0] > 0 and res[1] == 1, f'add_warning → {res}')
check(any(r.id == WARN_RID for r in target.roles),
      'после add_warning роль выдана')
removed, total = asyncio.run(cog.remove_last_warning(target, mod))
check(removed is not None and total == 0, f'remove → total={total}')
check(not any(r.id == WARN_RID for r in target.roles),
      'после remove роль снята')

print('== 6. нет _sync_warn_level_roles ==')
src = open(os.path.join(ROOT, 'cogs', 'warnings.py'), encoding='utf-8').read()
check('_sync_warn_level_roles' not in src,
      'старый sync уровней удалён')
check('level_transition' not in src,
      'level_transition больше не вызывается')
check('sync_warn_role' in src, 'новый sync_warn_role используется')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
