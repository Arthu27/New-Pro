# -*- coding: utf-8 -*-
"""Роли уровней варнов — только для стаффа, с 3 варнов на неделю.

Заказ 2026-09-24: обычным участникам warn-роль не выдаём (и снимаем);
стаффу при ≥3 варнах — роль warn_3 на 7 дней (temps).

Запуск: python3 tests/test_warn_level_roles.py
"""
import asyncio
import os
import shutil
import sys
import tempfile
import time
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='hakumo_wlevel_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'

PASS = 0
FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


from services import punish_roles as PR  # noqa: E402
from services.staff_roles import KNOWN_HELPER_ROLE_ID  # noqa: E402
from db import GuildData  # noqa: E402
import cogs.warnings as W  # noqa: E402

R_LVL3 = 555003
HELPER_RID = int(KNOWN_HELPER_ROLE_ID)


class FakeRole:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name
        self.managed = False


class FakeMember:
    def __init__(self, uid, name, guild, staff=False):
        self.id = uid
        self.name = name
        self.display_name = name
        self.guild = guild
        self.roles = []
        if staff:
            self.roles.append(FakeRole(HELPER_RID, 'Helper'))
        self.added = []
        self.removed = []
        self.bot = False

    @property
    def mention(self):
        return f'<@{self.id}>'

    display_avatar = SimpleNamespace(url='https://x.test/a.png')

    async def remove_roles(self, role, reason=None):
        self.removed.append((role.id, reason))
        self.roles = [r for r in self.roles if r.id != role.id]

    async def add_roles(self, role, reason=None):
        self.added.append((role.id, reason))
        if not any(r.id == role.id for r in self.roles):
            self.roles.append(role)

    async def send(self, **kw):
        return None


class FakeGuild:
    def __init__(self, gid):
        self.id = gid
        self.name = 'Сервер теста'
        self.icon = None
        self.owner_id = 1
        self._roles = [FakeRole(R_LVL3, 'Уровень 3'),
                       FakeRole(HELPER_RID, 'Helper')]

    def get_role(self, rid):
        return next((r for r in self._roles if r.id == rid), None)

    def get_channel(self, cid):
        return None


class FakeResp:
    async def send_message(self, **kw):
        return None

    def is_done(self):
        return False


class FakeInteraction:
    def __init__(self, guild, user):
        self.guild = guild
        self.user = user
        self.response = FakeResp()
        self.followup = FakeResp()


guild = FakeGuild(777)
guild.owner_id = 1
mod = FakeMember(1, 'Мод', guild, staff=True)
user = FakeMember(42, 'Нарушитель', guild, staff=False)
staff = FakeMember(43, 'Хелпер-нарушитель', guild, staff=True)
cog = W.warnings.__new__(W.warnings)
cog.bot = SimpleNamespace(get_cog=lambda name: None, guilds=[guild])
cog.db = GuildData('warnings')


def wcount(uid=42):
    return len(cog._get_warns(777, uid))


def role_ids(member):
    return sorted(r.id for r in member.roles if r.id != HELPER_RID)


print('== 1. обычный участник — warn-роль НЕ выдаём ==')
PR.set_roles('777', warn_3=str(R_LVL3), who='test')
res = asyncio.run(cog.add_warn(FakeInteraction(guild, mod), user, 'флуд'))
check(wcount() == 1 and role_ids(user) == [],
      f'1 варн обычному — без роли (варн #{res[0]})')
asyncio.run(cog.add_warn(FakeInteraction(guild, mod), user, 'снова'))
asyncio.run(cog.add_warn(FakeInteraction(guild, mod), user, 'третий'))
check(wcount() == 3 and role_ids(user) == [],
      f'3 варна обычному — всё равно без роли: {role_ids(user)}')

print('== 2. стафф — роль с 3 варнов на неделю ==')
res = asyncio.run(cog.add_warn(FakeInteraction(guild, mod), staff, 'раз'))
check(wcount(43) == 1 and role_ids(staff) == [],
      '1 варн стаффу — роли ещё нет')
asyncio.run(cog.add_warn(FakeInteraction(guild, mod), staff, 'два'))
check(wcount(43) == 2 and role_ids(staff) == [],
      '2 варна стаффу — роли ещё нет')
asyncio.run(cog.add_warn(FakeInteraction(guild, mod), staff, 'три'))
check(wcount(43) == 3 and role_ids(staff) == [R_LVL3],
      f'3 варна стаффу → роль warn_3: {role_ids(staff)}')
temps = PR.temps_for(777, 43)
check(R_LVL3 in temps and temps[R_LVL3] > time.time() + 6 * 86400,
      f'temp на ~7 дней: {temps}')
reason_ok = any('неделю' in (r or '') for _, r in staff.added)
check(reason_ok, 'reason упоминает неделю')

print('== 3. unwarn стаффа — роль снимается ==')
asyncio.run(cog.unwarn.callback(cog, FakeInteraction(guild, mod), staff))
check(wcount(43) == 2 and role_ids(staff) == [],
      f'unwarn → 2 варна: роль снята {role_ids(staff)}')

print('== 4. не-стаффу снимаем уже висевшую warn-роль ==')
user2 = FakeMember(44, 'С ролью', guild, staff=False)
user2.roles.append(FakeRole(R_LVL3, 'Уровень 3'))
asyncio.run(cog._sync_warn_level_roles(guild, user2, 5))
check(role_ids(user2) == [] and any(rid == R_LVL3 for rid, _ in user2.removed),
      'не-стаффу warn-роль снята при синхе')

print('== 5. хук подключён во всех трёх потоках ==')
src = open(os.path.join(ROOT, 'cogs', 'warnings.py'), encoding='utf-8').read()
check(src.count('_sync_warn_level_roles') == 1 + 4,
      'метод + 4 вызова (add_warn, add_warning, unwarn, remove_last_warning)')
check('is_staff' in src and '7 * 86400' in src,
      'staff-only + недельный temp')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
