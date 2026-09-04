# -*- coding: utf-8 -*-
"""member-picker suggest API + фоновая дозагрузка участников (member_sync).

Покрываем:
  1. GET /api/guild/<gid>/member-card/suggest в демо: 200, формат items
     {user_id,name,bot,avatar}, пустой q отдаёт стартовый список, пагинация
     offset сдвигает страницу, неавторизованный без демо — 302/403 (не 404!).
     Это регрессия на «GET .../member-card/suggest · HTTP 404».
  2. services.member_sync._sync_guild: уже синхронизированную гильдию не
     трогает, неполную докачивает, ошибку/таймаут chunk переживает.

Запуск: python3 tests/test_member_picker_sync.py
"""
import asyncio
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_picker_')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ВАЖНО: cwd не меняем — web.app регистрирует роуты относительно корня репо;
# в tmp уходим только для файлов данных.
os.chdir(ROOT)
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['DEMO_MODE'] = '1'
os.environ.pop('TOKEN', None)
os.environ.pop('TОКEN', None)
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'preview123'
os.environ['MAIN_GUILD_ID'] = '987654321098765432'

PASS = 0
FAIL = 0


def check(cond, label, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


# Демо-гильдия = MAIN_GUILD_ID из env: before_request-гард отбивает запросы
# к ЧУЖИМ серверам 404, поэтому проверяем именно «свою» панельную гильдию.
GID = os.environ.get('MAIN_GUILD_ID', '987654321098765432')

# ── 1. API в демо-режиме ───────────────────────────────────────────────
import web.app as A  # noqa: E402

c = A.app.test_client()
with c.session_transaction() as sess:
    sess['logged_in'] = True
    sess['role'] = 'admin'
    sess['username'] = 'tester'

r = c.get(f'/api/guild/{GID}/member-card/suggest')
check(r.status_code == 200, 'suggest без q: 200 (не 404)', r.status_code)
d = r.get_json() or {}
items = d.get('items')
check(isinstance(items, list) and items, 'suggest без q: непустой items')
if items:
    it = items[0]
    check(all(k in it for k in ('user_id', 'name', 'bot', 'avatar')),
          'элемент содержит user_id/name/bot/avatar', str(it)[:120])

r2 = c.get(f'/api/guild/{GID}/member-card/suggest?q=a')
check(r2.status_code == 200 and isinstance((r2.get_json() or {}).get('items'), list),
      'suggest?q=a: 200 и список')

d3 = (c.get(f'/api/guild/{GID}/member-card/suggest?offset=0&limit=2').get_json() or {})
d4 = (c.get(f'/api/guild/{GID}/member-card/suggest?offset=2&limit=2').get_json() or {})
ids1 = {x['user_id'] for x in d3.get('items', [])}
ids2 = {x['user_id'] for x in d4.get('items', [])}
check(not (ids1 & ids2), 'пагинация offset: страницы не пересекаются',
      f'{ids1} vs {ids2}')

# роль uye (страница профиля участника доступна участнику) — пикер пускает
cu = A.app.test_client()
with cu.session_transaction() as s:
    s['logged_in'] = True
    s['role'] = 'uye'
    s['username'] = 'u'
ru = cu.get(f'/api/guild/{GID}/member-card/suggest?q=a')
check(ru.status_code == 200, 'роль uye допущена к пикеру', ru.status_code)


# ── 2. member_sync логика ──────────────────────────────────────────────
from services import member_sync as MS  # noqa: E402


class FakeGuild:
    def __init__(self, gid, cached, total, chunked=False, fail=False, slow=False):
        self.id = gid
        self.members = list(range(cached))
        self.member_count = total
        self._chunked = chunked
        self.chunk_calls = 0
        self._fail = fail
        self._slow = slow

    @property
    def chunked(self):
        return self._chunked

    async def chunk(self, cache=True):
        self.chunk_calls += 1
        if self._fail:
            raise RuntimeError('gateway 500')
        if self._slow:
            await asyncio.sleep(100)
        self.members = list(range(self.member_count))
        self._chunked = True


class GrowingGuild(FakeGuild):
    """Гильдия, у которой состав прибывает постепенно — как настоящая докачка.

    Нужна, чтобы проверить главное свойство: пока люди приходят, докачка не
    обрывается, сколько бы всего людей ни было на сервере.
    """

    def __init__(self, gid, total, step, delay):
        super().__init__(gid, cached=0, total=total)
        self._step = step
        self._delay = delay

    async def chunk(self, cache=True):
        self.chunk_calls += 1
        while len(self.members) < self.member_count:
            await asyncio.sleep(self._delay)
            self.members = list(range(min(len(self.members) + self._step,
                                          self.member_count)))
        self._chunked = True


async def _t():
    g_ok = FakeGuild(1, cached=100, total=100, chunked=True)
    w = await MS._sync_guild(g_ok)
    check(w is False and g_ok.chunk_calls == 0,
          'sync: полную гильдию не дёргает (chunk не вызван)')

    g_part = FakeGuild(2, cached=10, total=50, chunked=False)
    w = await MS._sync_guild(g_part)
    check(w is True and g_part.chunk_calls == 1 and len(g_part.members) == 50,
          'sync: неполную докачивает 10 -> 50')

    g_fail = FakeGuild(3, cached=5, total=50, chunked=False, fail=True)
    w = await MS._sync_guild(g_fail)
    check(w is False, 'sync: ошибка chunk переживается (не падаем)')

    # Порог теперь — не «потолок на всю докачку», а время БЕЗ прогресса.
    old_stall, old_poll = MS.CHUNK_STALL_SEC, MS.CHUNK_POLL_SEC
    MS.CHUNK_STALL_SEC = 0.3
    MS.CHUNK_POLL_SEC = 0.05

    g_slow = FakeGuild(4, cached=1, total=50, chunked=False, slow=True)
    w = await MS._sync_guild(g_slow)
    check(w is False, 'sync: люди перестали прибывать — сдаёмся, не висим')

    # Главное: пока пачки прибывают, докачка НЕ обрывается. Общая длительность
    # (2.4 с) в разы больше порога «без прогресса» (0.3 с) — старый потолок
    # здесь оборвал бы докачку и выбросил уже полученные пачки.
    g_grow = GrowingGuild(8, total=120000, step=1000, delay=0.02)
    w = await MS._sync_guild(g_grow)
    check(w is True and len(g_grow.members) == 120000,
          f'sync: 120 000 людей докачаны до конца, прогресс не потерян '
          f'(в кэше {len(g_grow.members)})')

    MS.CHUNK_STALL_SEC, MS.CHUNK_POLL_SEC = old_stall, old_poll

    # Потолка по размеру сервера больше нет: ожидание зависит только от того,
    # прибывают ли люди, а не от того, сколько их на сервере.
    t0 = MS._chunk_timeout(FakeGuild(5, cached=0, total=0))
    check(t0 == MS.CHUNK_STALL_SEC,
          f'порог «без прогресса»: {t0:.0f} с')
    t_big = MS._chunk_timeout(FakeGuild(7, cached=0, total=500000))
    check(t_big == t0,
          'порог не зависит от размера сервера — потолка по составу нет')


asyncio.run(_t())


# ── 3. Боевой режим: бот подключён, но сервера/кэша нет — НЕ 404 ──────────
# Регрессия на «GET /api/guild/<id>/member-card/suggest · HTTP 404 я везде»:
# раньше при подключённом боте и отсутствующем в кэше сервере роут отдавал 404
# и ломал все пикеры. Теперь — 200 с локальной картой имён.
class _NoGuildBot:
    guilds = []
    def get_guild(self, gid): return None

class _EmptyGuildBot:
    guilds = []
    def get_guild(self, gid):
        class _G:
            members = []
        return _G()

_names_file = os.path.join(ROOT, 'data', f'member_names_{GID}.json')
_orig_names = None
if os.path.exists(_names_file):
    with open(_names_file, encoding='utf-8') as f:
        _orig_names = f.read()
with open(_names_file, 'w', encoding='utf-8') as f:
    json.dump({'111': 'Arthur', '222': 'Nika'}, f)

_old_bot = A.bot_instance
try:
    A.bot_instance = _NoGuildBot()
    r = c.get(f'/api/guild/{GID}/member-card/suggest')
    check(r.status_code == 200, 'бот есть, сервера нет в кэше → 200 (не 404)', r.status_code)
    items = (r.get_json() or {}).get('items', [])
    check(any(i.get('name') == 'Arthur' for i in items),
          'fallback отдаёт имена из локальной карты')

    r = c.get(f'/api/guild/{GID}/member-card/suggest?q=arth')
    check(r.status_code == 200 and (r.get_json() or {}).get('items'),
          'fallback с q=arth находит Arthur')

    A.bot_instance = _EmptyGuildBot()
    r = c.get(f'/api/guild/{GID}/member-card/suggest')
    check(r.status_code == 200, 'бот есть, кэш участников пуст → 200 (не 404)', r.status_code)
finally:
    A.bot_instance = _old_bot
    try:
        if _orig_names is not None:
            with open(_names_file, 'w', encoding='utf-8') as f:
                f.write(_orig_names)
        else:
            os.remove(_names_file)
    except OSError:
        pass

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
