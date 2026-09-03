# -*- coding: utf-8 -*-
"""Вход по паролю — для ВСЕХ (владелец и участники), логин по ID или нику.

Заказ владельца (2026-09): «почему только owner может заходить через пароль?
сделай нормально, чтобы все могли зайти через пароль». При этом без роли на
сервере вход невозможен даже с верным паролем — роль проверяется живьём
из Discord при каждом входе (POST /login и /api/login-probe). Регистрация
снова требует пароль (он нужен для входа), а «забыли пароль» работает по
коду в ЛС Discord.

Под проверкой:
  POST /login              — участник по Discord ID и по нику, uye отклонён
  POST /api/login-probe    — зеркалит логин без сессии
  POST /register           — шаг 1 требует пароль (длина/совпадение)
  POST /api/forgot-password — поиск по нику/ID, код уходит в Discord

Запуск: python3 tests/test_login_all_members_password.py
"""
import asyncio
import json
import os
import sys
import tempfile
import threading
from types import SimpleNamespace as NS

os.environ['DEMO_MODE'] = '1'
os.environ.setdefault('PANEL_PORT', '5098')
os.environ.setdefault('PANEL_USER', 'owner')
os.environ.setdefault('PANEL_PASSWORD', 'demo-pass')
os.environ['MAIN_GUILD_ID'] = '777'

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)
sys.path.insert(0, _ROOT)
_TMP = tempfile.mkdtemp(prefix='hakumo_allpw_')

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


UID_MOD = 240000000000000001   # на основном сервере, есть права -> роль не uye
UID_UEYE = 240000000000000002  # на основном сервере, без прав -> uye


class _Perms:
    administrator = True
    ban_members = False
    kick_members = False
    manage_guild = False
    manage_messages = False
    manage_channels = False


def _member(uid, name, perms=None):
    m = NS(id=uid, name=name, display_name=name, bot=False,
           roles=[], guild_permissions=perms or _Perms())
    return m


mod = _member(UID_MOD, 'alice', _Perms())
uye = _member(UID_UEYE, 'bob', NS(administrator=False, ban_members=False,
              kick_members=False, manage_guild=False, manage_messages=False,
              manage_channels=False))
guild = NS(id=777, name='Основной', owner_id=100, members=[mod, uye])


class _FakeBot:
    guilds = [guild]
    loop = None

    def get_guild(self, gid):
        return guild if int(gid) == 777 else None

    async def fetch_user(self, uid):
        # для /api/forgot-password (DM шлёт код) и прочих прямых fetch
        u = NS(id=int(uid), display_name=f'user{uid}', name=f'user{uid}')
        async def send(*a, **k):
            return None
        u.send = send
        return u


_loop = asyncio.new_event_loop()


def _run_loop():
    asyncio.set_event_loop(_loop)
    _loop.run_forever()


threading.Thread(target=_run_loop, daemon=True).start()


def _fake_resolve(guild_, uid):
    for m in guild_.members:
        if m.id == int(uid):
            return m
    return None


async def _fake_resolve_async(guild_, uid):
    return _fake_resolve(guild_, uid)


import web.app as A  # noqa: E402

A.bot_instance = _FakeBot()
_FakeBot.loop = _loop
A.MAIN_GUILD_ID = '777'
A._resolve_guild_member = _fake_resolve
A._resolve_guild_member_async = _fake_resolve_async

os.makedirs('data', exist_ok=True)
json.dump({
    str(UID_MOD): {'password': A._hash_pw('alicepass1'), 'role': 'uye',
                   'display_name': 'alice', 'name': 'alice'},
    str(UID_UEYE): {'password': A._hash_pw('bobpass111'), 'role': 'uye',
                    'display_name': 'bob', 'name': 'bob'},
}, open('data/members.json', 'w', encoding='utf-8'), ensure_ascii=False)

client = A.app.test_client()

print('== вход участника по Discord ID ==')
r = client.post('/login', data={'username': str(UID_MOD), 'password': 'alicepass1'})
check(r.status_code == 302 and 'login' not in r.headers.get('Location', ''),
      'верный пароль по ID -> редирект в панель', f'→ {r.status_code} {r.headers.get("Location")}')
with client.session_transaction() as s:
    check(s.get('logged_in') is True and s.get('discord_id') == str(UID_MOD)
          and s.get('username') == 'alice' and s.get('role') != 'uye',
          'сессия: discord_id/display_name/роль установлены из Discord')

print('== вход по нику (без ID) ==')
c2 = A.app.test_client()
r = c2.post('/login', data={'username': 'alice', 'password': 'alicepass1'})
check(r.status_code == 302, 'вход по нику (@alice без @ тоже) -> редирект',
      f'→ {r.status_code} {r.headers.get("Location")}')
with c2.session_transaction() as s:
    check(s.get('discord_id') == str(UID_MOD), 'по нику найден правильный Discord ID')

print('== роль есть только у настоящих прав: uye не пускаем ==')
r = client.post('/login', data={'username': str(UID_UEYE), 'password': 'bobpass111'})
html = r.get_data(as_text=True)
check(r.status_code == 200 and 'auth-error' in html and 'Доступа к панели нет' in html,
      'uye с ВЕРНЫМ паролем -> «Доступа к панели нет»', f'→ {r.status_code}')

print('== неверный пароль ==')
r = client.post('/login', data={'username': str(UID_MOD), 'password': 'nope-nope'})
check(r.status_code == 200 and 'Неверное имя пользователя' in r.get_data(as_text=True),
      'неверный пароль -> «Неверное имя пользователя»')

print('== /api/login-probe зеркалит вход ==')
r = client.post('/api/login-probe', json={'username': str(UID_MOD), 'password': 'alicepass1'})
d = r.get_json(silent=True) or {}
check(d.get('success') is True and d.get('role') not in (None, 'uye'),
      'probe: верный пароль участника -> success+роль', f'→ {d}')
r = client.post('/api/login-probe', json={'username': 'bob', 'password': 'bobpass111'})
d = r.get_json(silent=True) or {}
check(d.get('success') is False and 'нет' in (d.get('error') or ''),
      'probe: uye -> false с объяснением', f'→ {d}')

print('== /register: пароль снова обязателен ==')
r = client.post('/register', data={'step': '1', 'discord_id': str(UID_MOD),
                                   'password': '', 'password2': ''})
check('Заполните все поля' in r.get_data(as_text=True),
      'пустой пароль при регистрации -> «Заполните все поля»')
r = client.post('/register', data={'step': '1', 'discord_id': str(UID_MOD),
                                   'password': '12345', 'password2': '12345'})
check('не короче 6' in r.get_data(as_text=True),
      'короткий пароль -> ошибка длины')

print('== /api/forgot-password по нику ==')
r = client.post('/api/forgot-password', json={'discord_id': 'bob'})
d = r.get_json(silent=True) or {}
check(d.get('success') is True and d.get('discord_id') == str(UID_UEYE),
      'запрос кода по нику находит участника', f'→ {d}')

try:
    os.remove('data/members.json')
except OSError:
    pass

print()
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
