# -*- coding: utf-8 -*-
"""Роли уровней варнов — сквозная проверка через ког Warnings.

/banции: варн → вырос уровень → роль предыдущего уровня слетела, новая
выдана; /unwarn → уровень упал → пересчёт; сняли всё → ролей уровня нет.
Задействуем реальные add_warn / unwarn кога (та же точка, что у панели
и AI-модератора: add_warning) — без моков самого перехода.

Запуск: python3 tests/test_warn_level_roles.py
"""
import asyncio
import os
import shutil
import sys
import tempfile
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
from db import GuildData  # noqa: E402
import cogs.warnings as W  # noqa: E402

R_LVL1, R_LVL3, R_LVL10 = 555001, 555003, 555010


class FakeRole:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name
        self.managed = False


class FakeMember:
    def __init__(self, uid, name, guild):
        self.id = uid
        self.name = name
        self.display_name = name
        self.guild = guild
        self.roles = []
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
        self._roles = [FakeRole(R_LVL1, 'Уровень 1'),
                       FakeRole(R_LVL3, 'Уровень 3'),
                       FakeRole(R_LVL10, 'Уровень 10')]

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
mod = FakeMember(1, 'Мод', guild)
user = FakeMember(42, 'Нарушитель', guild)
cog = W.warnings.__new__(W.warnings)
cog.bot = SimpleNamespace(get_cog=lambda name: None, guilds=[guild])
cog.db = GuildData('warnings')


def wcount():
    return len(cog._get_warns(777, 42))


def role_ids():
    return sorted(r.id for r in user.roles)


print('== 1. выдача при варнах ==')
PR.set_roles('777', warn_1=str(R_LVL1), warn_3=str(R_LVL3), warn_10=str(R_LVL10),
             who='test')
res = asyncio.run(cog.add_warn(FakeInteraction(guild, mod), user, 'флуд'))
check(wcount() == 1 and role_ids() == [R_LVL1],
      f'1 варн → роль уровня 1 (варн #{res[0]})')
res = asyncio.run(cog.add_warn(FakeInteraction(guild, mod), user, 'снова'))
check(wcount() == 2 and role_ids() == [R_LVL1],
      '2 варна — всё ещё ближайший уровень 1, роли без дублей')
res = asyncio.run(cog.add_warn(FakeInteraction(guild, mod), user, 'третий'))
check(wcount() == 3 and role_ids() == [R_LVL3],
      f'3 варна → роль уровня 3, уровня 1 снята: {role_ids()}')
removed_lv1 = [rid for rid, _ in user.removed].count(R_LVL1) >= 1
check(removed_lv1, 'предыдущая роль уровня снята именно через remove_roles')
dupe_adds = [rid for rid, _ in user.added].count(R_LVL3) == 1
check(dupe_adds, 'роль уровня 3 выдана ровно один раз')

print('== 2. снятие варнов — уровень падает, роль пересчитывается ==')
asyncio.run(cog.unwarn.callback(cog, FakeInteraction(guild, mod), user))
check(wcount() == 2 and role_ids() == [R_LVL1],
      f'unwarn → 2 варна: назад на роль уровня 1 {role_ids()}')
asyncio.run(cog.unwarn.callback(cog, FakeInteraction(guild, mod), user))
asyncio.run(cog.unwarn.callback(cog, FakeInteraction(guild, mod), user))
check(wcount() == 0 and role_ids() == [],
      'все варны сняты → warn-ролей на участнике нет')

print('== 3. панель/AI-путь (add_warning) — тот же переезд ==')
res = asyncio.run(cog.add_warning(user, mod, 'через панель'))
check(wcount() == 1 and role_ids() == [R_LVL1],
      'add_warning выдаёт роль уровня 1')

print('== 4. без выбранных ролей — ничего не трогаем ==')
user2 = FakeMember(43, 'Тихий', guild)
PR.set_roles('777', warn_1='0', warn_3='0', warn_10='0', who='test')
cog._save_warns(777, 43, [])
res = asyncio.run(cog.add_warn(FakeInteraction(guild, mod), user2, 'проверка'))
check(wcount() == 1 and (user2.added, user2.removed) == ([], []),
      'нет настроенных ролей → ноль обращений к ролям Дискорда')

print('== 5. роль удалена с сервера — не падаем ==')
PR.set_roles('777', warn_1='999999999999999999', who='test')
user3 = FakeMember(44, 'Край', guild)
res = asyncio.run(cog.add_warn(FakeInteraction(guild, mod), user3, 'край'))
check(wcount() == 1 and user3.added == [],
      'несуществующая роль уровня просто не выдаётся')

print('== 6. хук подключён во всех трёх потоках ==')
src = open(os.path.join(ROOT, 'cogs', 'warnings.py'), encoding='utf-8').read()
check(src.count('_sync_warn_level_roles') == 1 + 4,
      'метод + 4 вызова (add_warn, add_warning, unwarn, remove_last_warning)')
check('level_transition' in src, 'переход через сервис переиспользуется')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
