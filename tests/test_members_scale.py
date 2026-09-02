# -*- coding: utf-8 -*-
"""Большой сервер: список участников доходит до конца, а не обрывается на 500.

Заказ владельца: на сервере 20 000+ людей, а панель показывала максимум 500 —
дальше список просто не существовал (поиск, фильтр по ролям и статистика
работали по первым 500). Проверяем серверную часть договора:

* пагинация добирает ВСЕХ участников (20 000 уникальных id);
* заголовки честно отдают «сколько на сервере» и «сколько бот уже держит
  в кэше» — иначе панель выдаёт частичный список за полный;
* неполный кэш виден снаружи (X-Chunked=0, X-Cached-Count < X-Guild-Count);
* потолок пачки и дефолт такие, что 20 000 человек — это десятки запросов,
  а не тысячи.

Запуск:  python3 tests/test_members_scale.py
"""
import datetime
import importlib
import os
import shutil
import sys
import tempfile
import time

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix='hakumo_members_scale_')
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


# ---------- фейковый Discord на 20 000 человек ----------
class FakeAvatar:
    url = 'https://cdn.discordapp.com/embed/avatars/0.png'


class FakeRole:
    def __init__(self, name):
        self.name = name
        self.color = 0x3498db


class FakeMember:
    def __init__(self, mid, i):
        # валидный snowflake: discord.utils.snowflake_time(id) не должен падать
        self.id = (17592186044416 << 22) + mid
        self.name = f'user{i}'
        self.display_name = f'Участник {i}'
        self.discriminator = '0'
        self.display_avatar = FakeAvatar()
        self.joined_at = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
        self.roles = [FakeRole('@everyone'), FakeRole('Новичок')]
        self.bot = (i % 500 == 0)
        self.status = 'online' if i % 3 == 0 else 'offline'
        self.nick = None
        self.top_role = FakeRole('Новичок')


class FakeGuild:
    def __init__(self, gid, members, member_count, chunked):
        self.id = gid
        self.members = members
        self.member_count = member_count
        self.chunked = chunked


class FakeBot:
    def __init__(self, guilds):
        self.guilds = guilds

    def get_guild(self, gid):
        for g in self.guilds:
            if g.id == gid:
                return g
        return None


TOTAL = 20000
GID = 793336829280780331
_members = [FakeMember(1000 + i, i) for i in range(TOTAL)]

appmod = importlib.import_module('web.app')
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


def set_guild(members, member_count, chunked):
    appmod.bot_instance = FakeBot([FakeGuild(GID, members, member_count, chunked)])
    # кэш ответов 10 с — чистим, чтобы не подмешивать прошлый состав
    try:
        appmod._store._cache.clear()
    except Exception:
        pass


def page(offset, limit=1000):
    return client.get(f'/api/guild/{GID}/members?limit={limit}&offset={offset}')


print('== 1. 20 000 участников добираются до конца ==')
login('owner')
set_guild(_members, TOTAL, True)

t0 = time.time()
seen = set()
offset = 0
rounds = 0
while True:
    r = page(offset)
    batch = r.get_json()
    total = int(r.headers.get('X-Total-Count', '0'))
    if not batch:
        break
    seen.update(m['id'] for m in batch)
    offset += len(batch)
    rounds += 1
    if offset >= total:
        break
elapsed = time.time() - t0

check(len(seen) == TOTAL, f'собрано {len(seen)} из {TOTAL} уникальных участников')
check(offset == TOTAL, f'пагинация дошла до конца (offset={offset})')
check(rounds == 20, f'пачек по 1000 — {rounds} (ожидали 20)')
check(elapsed < 30.0, f'20 000 человек за {elapsed:.2f} с')

print('== 2. заголовки отдают честные числа ==')
r = page(0)
check(r.headers.get('X-Total-Count') == str(TOTAL),
      f"X-Total-Count={r.headers.get('X-Total-Count')}")
check(r.headers.get('X-Guild-Count') == str(TOTAL),
      f"X-Guild-Count={r.headers.get('X-Guild-Count')} — сколько людей на сервере")
check(r.headers.get('X-Cached-Count') == str(TOTAL),
      f"X-Cached-Count={r.headers.get('X-Cached-Count')} — сколько в кэше бота")
check(r.headers.get('X-Chunked') == '1', 'X-Chunked=1 — гильдия дочанкена')

print('== 3. дефолт и потолок пачки ==')
r = client.get(f'/api/guild/{GID}/members')
check(r.headers.get('X-Limit') == '1000',
      f"дефолт limit={r.headers.get('X-Limit')} (было 50 — страница рвалась на 500)")
check(len(r.get_json()) == 1000, 'без параметров приходит 1000 человек')
# Потолка нет ВООБЩЕ: владелец растит сервер, 20 000 — это не предел.
# Весь состав отдаётся одним запросом, а «безумный» limit просто вернёт
# остаток списка — срез в Python за пределы не падает.
r = page(0, limit=TOTAL)
check(r.headers.get('X-Limit') == str(TOTAL),
      f"запросили весь сервер: X-Limit={r.headers.get('X-Limit')} (было 5000)")
check(len(r.get_json()) == TOTAL, f'одним запросом пришли все {TOTAL} человек')
r = page(0, limit=99999999)
check(r.headers.get('X-Limit') == '99999999',
      f"лимит НЕ обрезается: X-Limit={r.headers.get('X-Limit')} (просили 99999999)")
check(len(r.get_json()) == TOTAL,
      f'лишний limit не ломает ответ — отдан весь состав ({len(r.get_json())})')

print('== 4. неполный кэш виден снаружи ==')
set_guild(_members[:3000], TOTAL, False)
r = page(0)
check(r.headers.get('X-Guild-Count') == str(TOTAL),
      'на сервере по-прежнему 20 000')
check(r.headers.get('X-Cached-Count') == '3000',
      f"в кэше пока 3000 (X-Cached-Count={r.headers.get('X-Cached-Count')})")
check(r.headers.get('X-Chunked') == '0', 'X-Chunked=0 — докачка ещё идёт')

print('== 5. край страницы не теряет людей ==')
set_guild(_members, TOTAL, True)
r = page(19500, limit=1000)
check(len(r.get_json()) == 500, f'последняя пачка — остаток 500 (пришло {len(r.get_json())})')
r = page(20000, limit=1000)
check(r.status_code == 200 and r.get_json() == [],
      'за концом списка — пустой ответ, не ошибка')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
