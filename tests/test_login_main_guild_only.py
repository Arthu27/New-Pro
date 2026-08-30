# -*- coding: utf-8 -*-
"""Вход/подсказки/регистрация в панели — только участники ОСНОВНОГО сервера.

Регресс (заказ владельца): бота добавляют на несколько серверов, и в форме
«Войти»/«Регистрация» в подсказках появлялись люди НЕ с основного сервера,
а вход по PIN и создание доступа проходили для посторонних.

Эндпоинты под проверкой:
  GET  /api/login/suggest   — подсказки в полях входа
  POST /api/discord-check   — вход по PIN (проверка Discord)
  POST /register            — создание доступа (шаг 1)
  GET  /api/search          — глобальный поиск (участники)

Запуск: python3 tests/test_login_main_guild_only.py
"""
import os
import sys
import asyncio
import tempfile
from types import SimpleNamespace as NS

os.environ['DEMO_MODE'] = '1'
os.environ.setdefault('PANEL_PORT', '5099')
os.environ.setdefault('PANEL_USER', 'owner')
os.environ.setdefault('PANEL_PASSWORD', 'demo-pass')
os.environ['MAIN_GUILD_ID'] = '777'

_TMP = tempfile.mkdtemp(prefix='hakumo_login_guild_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


# --- фейковый Discord: основной сервер 777 и ЧУЖОЙ 888 ---------------------
MAIN_ID = 777
FOREIGN_ID = 888

# Реалистичные Discord snowflake (18 цифр, «старые» — проходят проверку
# возраста аккаунта в /api/discord-check). Короткие id вроде 1001 endpoint
# отвергает как некорректный Discord ID.
UID_ALICE = 240000000000000001     # основной сервер
UID_BOB = 240000000000000002       # основной сервер
UID_MALLORY = 550000000000000001   # ЧУЖОЙ сервер
UID_EVE = 550000000000000002       # ЧУЖОЙ сервер


class _Avatar:
    url = 'https://cdn.discordapp.com/embed/avatars/0.png'


def _member(uid, name, gid, bot=False):
    m = NS()
    m.id = uid
    m.name = name
    m.display_name = name
    m.bot = bot
    m.display_avatar = _Avatar()
    m.guild_id = gid

    async def _send(*a, **k):
        return None
    m.send = _send
    return m


alice = _member(UID_ALICE, 'alice', MAIN_ID)      # свой сервер
bob = _member(UID_BOB, 'bob_local', MAIN_ID)    # свой сервер
mallory = _member(UID_MALLORY, 'mallory_foreign', FOREIGN_ID)  # чужой сервер
eve = _member(UID_EVE, 'eve_foreign', FOREIGN_ID)          # чужой сервер

main_guild = NS(id=MAIN_ID, name='Основной', members=[alice, bob],
                owner_id=UID_ALICE)
foreign_guild = NS(id=FOREIGN_ID, name='Чужой', members=[mallory, eve],
                   owner_id=2001)

# Рабочий event loop в фоновом потоке: /register и /api/discord-check шлют
# корутины через run_coroutine_threadsafe(coro, bot_instance.loop) — loop
# должен реально крутиться, иначе .result() висит до таймаута.
_loop = asyncio.new_event_loop()
import threading as _threading


def _run_loop():
    asyncio.set_event_loop(_loop)
    _loop.run_forever()


_loop_thread = _threading.Thread(target=_run_loop, daemon=True)
_loop_thread.start()


class _FakeBot:
    guilds = [main_guild, foreign_guild]
    loop = _loop

    def get_guild(self, gid):
        return main_guild if int(gid) == MAIN_ID else None

    async def fetch_user(self, uid):
        # «любой пользователь Discord» — имитируем, что посторонний существует
        # (это проверяет, что /register НЕ полагается на fetch_user для чужих)
        return _member(int(uid), f'user{uid}', FOREIGN_ID)


import web.app as A

A.bot_instance = _FakeBot()
A.MAIN_GUILD_ID = str(MAIN_ID)

# _resolve_guild_member(_sync) и _async смотрят только в наш фейк-кэш главного
def _fake_resolve(guild, uid):
    for m in guild.members:
        if m.id == int(uid):
            return m
    return None


async def _fake_resolve_async(guild, uid):
    return _fake_resolve(guild, uid)


A._resolve_guild_member = _fake_resolve
A._resolve_guild_member_async = _fake_resolve_async

client = A.app.test_client()

print('== /api/login/suggest: только основной сервер ==')
r = client.get('/api/login/suggest?q=')
d = r.get_json(silent=True) or {}
sug = d.get('suggestions') or []
ids = {str(x.get('id')) for x in sug}
names = [x.get('name') for x in sug]
check(r.status_code == 200 and d.get('success') is True, 'подсказки отдаются (200)', f'→ {r.status_code} {d}')
check(str(UID_ALICE) in ids and str(UID_BOB) in ids, 'свои участники (alice, bob) в подсказках', f'→ {names}')
check(str(UID_MALLORY) not in ids and str(UID_EVE) not in ids, 'ЧУЖИЕ (mallory/eve) НЕ показываются', f'→ {names}')

r = client.get(f'/api/login/suggest?q=mallory')
d = r.get_json(silent=True) or {}
sug = d.get('suggestions') or []
check([x for x in sug if str(x.get('id')) == str(UID_MALLORY)] == [],
      'поиск по нику постороннего — пусто (mallory не находит)', f'→ {sug}')

r = client.get('/api/login/suggest?q=alice')
d = r.get_json(silent=True) or {}
sug = d.get('suggestions') or []
check(any(str(x.get('id')) == str(UID_ALICE) for x in sug),
      'поиск по нику своего — находит alice', f'→ {sug}')

print('== /api/discord-check: посторонний не проходит, свой проходит ==')
r = client.post('/api/discord-check', json={'query': str(UID_MALLORY)})
d = r.get_json(silent=True) or {}
check(r.status_code == 200 and d.get('success') is False,
      'чужой участник (mallory) — вход запрещён', f'→ {d.get("success")} {d.get("error")}')
check('основн' in (d.get('error') or '') or 'сервер' in (d.get('error') or ''),
      'причина отказа упоминает основной сервер', f'→ {d.get("error")}')

r = client.post('/api/discord-check', json={'query': str(UID_EVE)})
d = r.get_json(silent=True) or {}
check(d.get('success') is False, 'второй чужой (eve) — тоже запрещён', f'→ {d.get("error")}')

r = client.post('/api/discord-check', json={'query': 'mallory_foreign'})
d = r.get_json(silent=True) or {}
check(d.get('success') is False, 'чужой по нику — запрещён', f'→ {d.get("error")}')

# свой по ID должен пройти проверки вплоть до отправки PIN (DM замокан в _FakeBot)
r = client.post('/api/discord-check', json={'query': str(UID_BOB)})
d = r.get_json(silent=True) or {}
check(d.get('success') is True and str(d.get('discord_id')) == str(UID_BOB),
      'свой участник (bob) — допущен к PIN', f'→ {d.get("success")} {d.get("error")}')

# Владелец бота, которого ещё НЕТ на сервере (этап настройки), — вход разрешён:
# профиль тянется через fetch_user, а проверка членства делает исключение.
UID_OWNER = 770000000000000003
os.environ['OWNER_ID'] = str(UID_OWNER)
# config читает owner'ов через Config.all_owner_ids(); в фейке fetch_user вернёт профиль
r = client.post('/api/discord-check', json={'query': str(UID_OWNER)})
d = r.get_json(silent=True) or {}
check(d.get('success') is True,
      'владелец бота без членства на сервере — допущен к входу (настройка)',
      f'→ {d.get("success")} {d.get("error")}')
os.environ.pop('OWNER_ID', None)

print('== /register (шаг 1): чужой ID не регистрируется ==')
r = client.post('/register', data={
    'step': '1', 'discord_id': str(UID_MALLORY), 'password': 'secret123',
    'password2': 'secret123'})
html = r.get_data(as_text=True)
check(r.status_code == 200 and 'не найден на основном сервере' in html,
      'регистрация чужого ID отклонена с понятным текстом', f'→ статус {r.status_code}')
check(str(UID_MALLORY) not in A.PENDING_VERIFICATIONS,
      'для чужого ID не создаётся pending-проверка (PIN не уходит)',
      f'→ {list(A.PENDING_VERIFICATIONS)}')

r = client.post('/register', data={
    'step': '1', 'discord_id': str(UID_BOB), 'password': 'secret123',
    'password2': 'secret123'})
html = r.get_data(as_text=True)
check(r.status_code == 200 and str(UID_BOB) in A.PENDING_VERIFICATIONS,
      'регистрация своего ID переходит к шагу 2 (PIN отправлен)',
      f'→ pending={list(A.PENDING_VERIFICATIONS)}')

print('== /api/search (модерский): участники только основного сервера ==')
with client.session_transaction() as sess:
    sess['logged_in'] = True
    sess['username'] = 'test-mod'
    sess['role'] = 'mod'
    sess['discord_id'] = str(UID_ALICE)
r = client.get('/api/search?q=foreign')
d = r.get_json(silent=True) or []
titles = [x.get('title') for x in d if x.get('type') == 'member']
check(not any('foreign' in str(t).lower() for t in titles),
      'глобальный поиск не находит участников чужого сервера', f'→ {titles}')
r = client.get('/api/search?q=alice')
d = r.get_json(silent=True) or []
titles = [x.get('title') for x in d if x.get('type') == 'member']
check(any('alice' in str(t).lower() for t in titles),
      'глобальный поиск находит своего участника', f'→ {titles}')

print()
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
