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

# Работаем из корня репозитория (как и прод-панель): относительные пути
# data/... резолвятся одинаково в коде и в тесте. Тестовые data-файлы
# удаляем в конце, чтобы не сорить в реальной data/.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)
sys.path.insert(0, _ROOT)
_TMP = tempfile.mkdtemp(prefix='hakumo_login_guild_')

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
    m.roles = []   # живая проверка роли читает member.roles

    async def _send(*a, **k):
        return None
    m.send = _send
    return m


def _mod_perms():
    # PIN-вход теперь только у.staff: без роли модератора код не отправляется
    return NS(administrator=False, ban_members=True, kick_members=True,
              manage_guild=False, manage_messages=False, manage_channels=False)


alice = _member(UID_ALICE, 'alice', MAIN_ID)      # свой сервер
alice.guild_permissions = _mod_perms()
bob = _member(UID_BOB, 'bob_local', MAIN_ID)    # свой сервер
bob.guild_permissions = _mod_perms()
# свой, но БЕЗ роли модератора — PIN не получит (заказ владельца: реальный лимит по ролям)
bob_norole = _member(240000000000000003, 'bob_norole', MAIN_ID)
bob_norole.guild_permissions = NS(administrator=False, ban_members=False,
                                  kick_members=False, manage_guild=False,
                                  manage_messages=False, manage_channels=False)
mallory = _member(UID_MALLORY, 'mallory_foreign', FOREIGN_ID)  # чужой сервер
eve = _member(UID_EVE, 'eve_foreign', FOREIGN_ID)          # чужой сервер

main_guild = NS(id=MAIN_ID, name='Основной', members=[alice, bob, bob_norole],
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

# Заявки в команду с двух серверов: своя (777), чужая (888) и legacy без guild_id
import json as _json
os.makedirs('data', exist_ok=True)
with open('data/staff_apps.json', 'w', encoding='utf-8') as _f:
    _json.dump({
        'app-main': {'app_id': 'app-main', 'user_id': str(UID_BOB),
                     'display_name': 'bob_local', 'status': 'pending',
                     'guild_id': str(MAIN_ID), 'timestamp': '2026-08-30T10:00:00+00:00'},
        'app-foreign': {'app_id': 'app-foreign', 'user_id': str(UID_MALLORY),
                        'display_name': 'mallory_foreign', 'status': 'pending',
                        'guild_id': str(FOREIGN_ID), 'timestamp': '2026-08-30T11:00:00+00:00'},
        'app-old-noguild': {'app_id': 'app-old-noguild', 'user_id': '999',
                            'display_name': 'legacy', 'status': 'pending',
                            'guild_id': None, 'timestamp': '2026-08-30T09:00:00+00:00'},
    }, _f, ensure_ascii=False)

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

# свой МОДЕРАТОР по ID проходит проверки вплоть до отправки PIN (DM замокан в _FakeBot)
r = client.post('/api/discord-check', json={'query': str(UID_BOB)})
d = r.get_json(silent=True) or {}
check(d.get('success') is True and str(d.get('discord_id')) == str(UID_BOB),
      'свой модератор (bob) — допущен к PIN', f'→ {d.get("success")} {d.get("error")}')

# свой, но БЕЗ роли модератора: PIN не отправляется (реальный лимит по ролям)
r = client.post('/api/discord-check', json={'query': 'bob_norole'})
d = r.get_json(silent=True) or {}
check(d.get('success') is False and 'роль модератора' in (d.get('error') or ''),
      'свой без роли — PIN не отправляется, отказ про роль',
      f'→ {d.get("success")} {d.get("error")}')

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
check(r.status_code == 200 and 'на основном сервере' in html,
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

print('== /api/staff-apps: заявки только основного сервера ==')
# owner-сессия, чтобы role_required не понижал роль (фильтр данных не зависит
# от роли — проверяем именно изоляцию серверов).
with client.session_transaction() as sess:
    sess['logged_in'] = True
    sess['username'] = 'test-owner'
    sess['role'] = 'owner'
    sess['discord_id'] = str(UID_ALICE)
r = client.get('/api/staff-apps')
d = r.get_json(silent=True) or []
app_ids = {a.get('app_id') for a in d}
app_guilds = {str(a.get('guild_id')) for a in d}
check('app-main' in app_ids, 'своя заявка (777) видна', f'→ статус {r.status_code} {app_ids}')
check('app-foreign' not in app_ids, 'ЧУЖАЯ заявка (888) скрыта', f'→ {app_ids}')
check(str(FOREIGN_ID) not in app_guilds, 'в ответе нет записей чужого сервера', f'→ {app_guilds}')
check('app-old-noguild' in app_ids, 'старая заявка без guild_id не прячется', f'→ {app_ids}')

r = client.post('/api/staff-apps/app-foreign/review', json={'action': 'approve'})
d = r.get_json(silent=True) or {}
check(r.status_code == 404 and 'другого сервера' in (d.get('error') or ''),
      'рассмотрение заявки чужого сервера запрещено (404)', f'→ {r.status_code} {d.get("error")}')

# 2026-09-04: /api/login-probe удалён (дублировал POST /login — «проверки
# кружатся»). Эквивалентные проверки — через сам POST /login:
r = client.post('/login', data={'username': 'owner', 'password': 'demo-pass'})
check(r.status_code == 302,
      'верный пароль владельца — вход проходит', f'→ {r.status_code}')
r = client.post('/login', data={'username': 'owner', 'password': 'wrong-pass'})
check(r.status_code == 200 and 'Неверное' in r.get_data(as_text=True),
      'неверный пароль — ошибка как у формы входа')
r = client.post('/login', data={'username': '', 'password': ''})
check(r.status_code == 200 and 'Неверное' in r.get_data(as_text=True),
      'пустые поля — вход не проходит')
r = client.get('/api/login-probe')
check(r.status_code == 404, 'probe-эндпоинта больше нет', f'→ {r.status_code}')

try:
    os.remove('data/staff_apps.json')
except OSError:
    pass

print()
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
