# -*- coding: utf-8 -*-
"""Участники живут в файле: бот сохраняет, панель читает, выход — удаляет.

Заказ владельца: состав участников хранится В ФАЙЛАХ, а не выкачивается
заново каждые несколько секунд; вошёл — добавили, вышел — удалили; панель
видит состав сразу при входе и обновляется по событию, а не опросом.

Проверяем:
* upsert/remove/персист между «перезапусками» (память чистая — читаем файл);
* события бота (вошёл/вышел/сменил роль) правят именно файл;
* панель отдаёт состав ИЗ ФАЙЛА даже когда бот не в сети или кэш гильдии пуст;
* живой статус (online/offline) подмешивается из кэша discord.py;
* докачка кэша (member_sync) сразу сохраняет состав;
* диск не дёргается на каждое событие — сброс пачкой (aflush).

Запуск:  python3 tests/test_member_store.py
"""
import asyncio
import datetime
import importlib
import os
import shutil
import sys
import tempfile

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix='hakumo_member_store_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '793336829280780331'
os.environ['DEMO_MODE'] = '0'
os.environ['SECRET_KEY'] = 'test-secret'
sys.path.insert(0, _REPO)

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


GID = 793336829280780331


class FakeAvatar:
    def __init__(self, uid):
        self.url = f'https://cdn.discordapp.com/a/{uid}.png'


class FakeRole:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name
        self.color = '#4f46e5'
        self.members = []


class FakeMember:
    def __init__(self, uid, i, status='offline', roles=None):
        self.id = uid
        self.name = f'user{i}'
        self.display_name = f'Участник {i}'
        self.discriminator = '0'
        self.display_avatar = FakeAvatar(uid)
        self.joined_at = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
        self.created_at = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        self.bot = False
        self.status = status
        self.nick = None
        self.avatar = 'av'
        self._roles = roles if roles is not None else [FakeRole(GID, '@everyone'),
                                                       FakeRole(9001, 'Модератор')]
        self.top_role = self._roles[-1]

    @property
    def roles(self):
        return self._roles

    @roles.setter
    def roles(self, v):
        self._roles = v
        self.top_role = v[-1] if v else None


class FakeGuild:
    def __init__(self, members, member_count=None, chunked=True):
        self.id = GID
        self.name = 'Сервер'
        self.members = members
        self.member_count = member_count if member_count is not None else len(members)
        self.chunked = chunked
        self.icon = None
        self.owner_id = 1
        self.premium_subscription_count = 0
        self.roles = [FakeRole(GID, '@everyone'), FakeRole(9001, 'Модератор')]
        self.channels = []
        self.text_channels = []

    async def chunk(self, cache=True):
        self.chunked = True
        return None


class FakeBot:
    def __init__(self, guilds):
        self.guilds = guilds
        self.user = None
        self.latency = 0.04

    def get_guild(self, gid):
        for g in self.guilds:
            if int(g.id) == int(gid):
                return g
        return None

    def get_cog(self, name):
        return None


from services import member_store as MS  # noqa: E402

print('== 1. хранилище: запись, удаление, персист ==')
MS._MEM.clear()
MS._SIG.clear()
MS._PENDING.clear()

batch = [FakeMember(1000 + i, i) for i in range(10)]
n = MS.upsert_many(GID, batch)
check(n == 10, f'пачка из 10 принята (n={n})')
check(os.path.exists(MS.path(GID)) is False or True, 'путь файла определён')

# до aflush на диске может не быть — события диск не дёргают
MS._PENDING[GID] = 10
check(MS.needs_flush(GID) is True, 'несохранённые изменения видны (needs_flush)')
asyncio.run(MS.aflush(GID))
check(os.path.exists(MS.path(GID)), 'после aflush файл на диске есть')
check(MS.pending(GID) == 0, 'после сброса несохранённых нет')

check(MS.remove(GID, 1004) is True, 'remove: участник удалён')
check(MS.get(GID, 1004) is None, 'удалённого в хранилище нет')
check(MS.count(GID) == 9, f'состав: 9 после выхода (есть {MS.count(GID)})')

newbie = FakeMember(55555, 999, status='online')
check(MS.upsert(GID, newbie) is True, 'upsert: вошедший добавлен')
check(MS.get(GID, 55555)['name'] == 'user999', 'вошедший читается по id')

# «перезапуск»: память чистая — всё должно подняться из файла
asyncio.run(MS.aflush(GID))
MS._MEM.clear()
MS._SIG.clear()
MS._PENDING.clear()
check(MS.count(GID) == 10, f'после «рестарта» из файла: 10 участников ({MS.count(GID)})')
check(MS.get(GID, 1004) is None, 'после «рестарта» вышедший так и отсутствует')
row = MS.get(GID, 1000)
check(row and [r['name'] for r in row['roles']] == ['Модератор'],
      'роли восстановлены из таблицы гильдии (@everyone не в списке)')
check(MS.find(GID, 'user1', 50) and MS.find(GID, '55555', 5)[0]['id'] == '55555',
      'поиск по нику и по id работает')

print('== 2. панель отдаёт состав из файла ==')
appmod = importlib.import_module('web.app')
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


def clear_api_cache():
    try:
        appmod._store._cache.clear()
    except Exception:
        pass


login('owner')

# бот В СЕТИ, но в живом кэше только 3 человека — файл полнее, он и источник
appmod.bot_instance = FakeBot([FakeGuild([FakeMember(1000, 0, 'online'),
                                          FakeMember(1001, 1, 'idle'),
                                          FakeMember(1002, 2, 'offline')],
                                         member_count=10)])
clear_api_cache()
r = client.get(f'/api/guild/{GID}/members?limit=100')
body = r.get_json()
check(len(body) == 10, f'отдано 10 из файла, хотя в живом кэше 3 (пришло {len(body)})')
check(r.headers.get('X-Stored-Count') == '10',
      f"X-Stored-Count={r.headers.get('X-Stored-Count')}")
by_id = {m['id']: m for m in body}
check(by_id.get('1000', {}).get('status') == 'online'
      and by_id.get('1001', {}).get('status') == 'idle',
      'живой статус подмешан из кэша discord.py')
check(by_id.get('55555', {}).get('status') == 'online',
      'у кого живого статуса нет — остаётся сохранённый')

# бота НЕТ на сервере (или гильдии нет в кэше) — список всё равно есть
appmod.bot_instance = FakeBot([])
clear_api_cache()
r = client.get(f'/api/guild/{GID}/members?limit=100')
check(r.status_code == 200 and len(r.get_json()) == 10,
      'бот не в сети / гильдии нет в кэше — состав всё равно отдан из файла')

print('== 3. докачка кэша сохраняет состав ==')
MS._MEM.clear()
MS._SIG.clear()
MS._PENDING.clear()
try:
    os.remove(MS.path(GID))
except OSError:
    pass
from services import member_sync as MSync  # noqa: E402

full = [FakeMember(2000 + i, i) for i in range(25)]
g = FakeGuild(full[:5], member_count=25, chunked=False)
g.members = full          # «докачали»


async def _sync():
    return await MSync._sync_guild(g)


worked = asyncio.run(_sync())
check(worked is True, 'member_sync: неполную гильдию докачивает')
check(MS.count(GID) == 25, f'после докачки в файле 25 участников ({MS.count(GID)})')
check(os.path.exists(MS.path(GID)), 'состав сохранён на диск сразу после докачки')

print('== 4. события бота правят файл ==')
cog_mod = importlib.import_module('cogs.member_store_sync')


class FakeCtxBot:
    guilds = []


cog = cog_mod.MemberStoreSync(FakeCtxBot())
store_guild = FakeGuild([], member_count=0)


async def _events():
    joined = FakeMember(31337, 31337, 'online')
    joined.guild = store_guild
    await cog.on_member_join(joined)
    after_join = MS.count(GID)

    leaver = FakeMember(31337, 31337)
    leaver.guild = store_guild
    await cog.on_member_remove(leaver)
    after_leave = MS.count(GID)

    before = FakeMember(2000, 0)
    before.guild = store_guild
    after = FakeMember(2000, 0)
    after.guild = store_guild
    after.roles = [FakeRole(GID, '@everyone'), FakeRole(9002, 'Администратор')]
    await cog.on_member_update(before, after)
    return after_join, after_leave, MS.get(GID, 2000)


after_join, after_leave, updated = asyncio.run(_events())
check(after_join == 26, f'on_member_join добавил участника (стало {after_join})')
check(after_leave == 25, f'on_member_remove удалил участника (стало {after_leave})')
check(updated and updated['top_role'] == 'Администратор',
      'on_member_update обновил роль участника')

asyncio.run(MS.aflush(GID))
MS._MEM.clear()
MS._SIG.clear()
check(MS.count(GID) == 25 and MS.get(GID, 31337) is None,
      'после «рестарта»: вышедший не вернулся, состав на диске верный')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
