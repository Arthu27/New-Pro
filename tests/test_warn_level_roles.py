# -*- coding: utf-8 -*-
"""Роль warn — только куратор/админ при ≥3 варнах (неделя).

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

import json
json.dump({
    '948969471916249119': 'helper',
    '803553848396349510': 'mod',
    '807030012301541377': 'curator',
    '1189999426631122964': 'admin',
}, open('data/role_map.json', 'w'))

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
from services.staff_roles import (  # noqa: E402
    KNOWN_HELPER_ROLE_ID, KNOWN_CURATOR_ROLE_ID)
from db import GuildData  # noqa: E402
import cogs.warnings as W  # noqa: E402

R_LVL3 = 555003
HELPER_RID = int(KNOWN_HELPER_ROLE_ID)
CURATOR_RID = int(KNOWN_CURATOR_ROLE_ID)


class FakeRole:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name
        self.managed = False


class FakeMember:
    def __init__(self, uid, name, guild, roles=None):
        self.id = uid
        self.name = name
        self.display_name = name
        self.guild = guild
        self.roles = []
        for rid in (roles or []):
            self.roles.append(FakeRole(rid, str(rid)))
        self.added = []
        self.removed = []
        self.bot = False

    @property
    def mention(self):
        return f'<@{self.id}>'

    display_avatar = SimpleNamespace(url='https://x.test/a.png')

    async def add_roles(self, role, reason=None):
        self.added.append((role.id, reason))
        if not any(r.id == role.id for r in self.roles):
            self.roles.append(role)

    async def remove_roles(self, role, reason=None):
        self.removed.append((role.id, reason))
        self.roles = [r for r in self.roles if r.id != role.id]

    async def send(self, **kw):
        return None


class FakeGuild:
    def __init__(self, gid):
        self.id = gid
        self.name = 'Сервер теста'
        self.icon = None
        self.owner_id = 1
        self._roles = [FakeRole(R_LVL3, 'Уровень 3'),
                       FakeRole(HELPER_RID, 'Helper'),
                       FakeRole(CURATOR_RID, 'Curator')]

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
mod = FakeMember(1, 'Владелец', guild, roles=[CURATOR_RID, HELPER_RID])
user = FakeMember(42, 'Участник', guild)
helper = FakeMember(43, 'Хелпер', guild, roles=[HELPER_RID])
curator = FakeMember(44, 'Куратор', guild, roles=[CURATOR_RID, HELPER_RID])
cog = W.warnings.__new__(W.warnings)
cog.bot = SimpleNamespace(get_cog=lambda name: None, guilds=[guild])
cog.db = GuildData('warnings')


def wcount(uid=42):
    return len(cog._get_warns(777, uid))


def role_ids(member):
    skip = {HELPER_RID, CURATOR_RID}
    return sorted(r.id for r in member.roles if r.id not in skip)


print('== 1. обычный / хелпер — роль НЕ выдаём ==')
PR.set_roles('777', warn_3=str(R_LVL3), who='test')
for _ in range(3):
    asyncio.run(cog.add_warn(FakeInteraction(guild, mod), user, 'x'))
check(wcount() == 3 and role_ids(user) == [],
      f'участник 3 варна — без роли: {role_ids(user)}')

for _ in range(3):
    asyncio.run(cog.add_warning(helper, mod, 'x'))
# add_warning через owner Panel? mod is curator - but helper target is OK for branch
# wait - add_warning with human mod checks ACL. mod is curator+helper, helper is helper branch - OK
# But we used add_warning which for human goes through manual_warn - good
# Actually after 3 add_warning on helper - need to check if warns were added
# Hierarchy: curator can warn helper. Branch match. Good.
check(wcount(43) == 3 and role_ids(helper) == [],
      f'хелпер 3 варна — без роли: {role_ids(helper)}')

print('== 2. куратор — роль с 3 варнов на неделю ==')
# пишем варны напрямую + sync (обход дневного лимита issuer'а)
cog._save_warns(777, 44, [
    {'id': i, 'reason': 'x', 'mod': 'a', 'mod_id': '2',
     'timestamp': '2026-01-01T00:00:00+00:00'}
    for i in (1, 2, 3)])
asyncio.run(cog._sync_warn_level_roles(guild, curator, 3))
check(wcount(44) == 3 and role_ids(curator) == [R_LVL3],
      f'куратор 3 варна → роль: {role_ids(curator)}')
temps = PR.temps_for(777, 44)
check(R_LVL3 in temps and temps[R_LVL3] > time.time() + 6 * 86400,
      f'temp ~7д: {temps}')

print('== 3. не-куратору снимаем висевшую ==')
helper2 = FakeMember(45, 'С ролью', guild, roles=[HELPER_RID, R_LVL3])
asyncio.run(cog._sync_warn_level_roles(guild, helper2, 5))
check(role_ids(helper2) == [] and any(rid == R_LVL3 for rid, _ in helper2.removed),
      'хелперу warn-роль снята')

print('== 4. хуки ==')
src = open(os.path.join(ROOT, 'cogs', 'warnings.py'), encoding='utf-8').read()
check(src.count('_sync_warn_level_roles') == 1 + 4,
      'метод + 4 вызова')
check('warn_role_eligible' in src and '7 * 86400' in src,
      'curator/admin + недельный temp')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
