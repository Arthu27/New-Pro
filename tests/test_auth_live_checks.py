# -*- coding: utf-8 -*-
"""Живая проверка доступа в панель: роли, сервер, «чей аккаунт».

Сценарии владельца:
  * модер вышел с сервера / роль сняли → сессия гасится до первого действия;
  * вход по паролю на новом устройстве требует код из ЛС Discord — знание
    пароля без доступа к Discord-аккаунту в панель не попадает;
  * доверенное устройство (30 дней) код повторно не спрашивает;
  * владелец панели входит по паролю сразу, сессия привязана к OWNER_ID
    и тоже живьём перепроверяется;
  * вход через Discord (PIN) без роли модератора даже не отправляет код;
  * коды одноразовые, перебор блокируется, у регистрации есть TTL.

Запуск: python3 tests/test_auth_live_checks.py
"""
import asyncio
import json
import os
import sys
import tempfile
import threading
import time as _time

os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'test-pass-123'
os.environ['OWNER_ID'] = '42'
os.environ.pop('DEMO_MODE', None)
os.environ['MAIN_GUILD_ID'] = '777'
os.environ.pop('PANEL_LOGIN_CONFIRM', None)

_TMP = tempfile.mkdtemp(prefix='hakumo_auth_live_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = 0
FAIL = 0


def check(ok, label, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


from types import SimpleNamespace as NS  # noqa: E402
import web.app as A  # noqa: E402


def make_member(uid, mod=False, admin=False):
    perms = NS(administrator=admin, ban_members=mod, kick_members=mod,
               manage_guild=False, manage_messages=False, manage_channels=False)
    return NS(id=uid, bot=False, roles=[], guild_permissions=perms,
              display_name=f'user{uid}', name=f'user{uid}')


GUILD_MEMBERS = {555: make_member(555, mod=True),
                 556: make_member(556, mod=False),
                 42: make_member(42, admin=True)}
guild = NS(id=777, owner_id=42, name='Hakumo Test',
           get_member=lambda uid: GUILD_MEMBERS.get(uid),
           members=list(GUILD_MEMBERS.values()))
A.bot_instance = NS(guilds=[guild],
                    get_guild=lambda gid: guild if gid == 777 else None,
                    loop=None, latency=0.05)
A._resolve_guild_member = lambda g, uid: g.get_member(uid)

os.makedirs('data', exist_ok=True)


def save_members():
    json.dump({
        '555': {'display_name': 'user555', 'name': 'user555', 'avatar': '',
                'role': 'mod', 'password': A._hash_pw('secret123'),
                'registered_at': '2026-01-01'},
        '556': {'display_name': 'user556', 'name': 'user556', 'avatar': '',
                'role': 'uye', 'password': A._hash_pw('secret123'),
                'registered_at': '2026-01-01'},
    }, open('data/members.json', 'w'))


save_members()

# ── Фейковые ЛС: коды «приходят» в sent[] ────────────────────────────────
sent = {}
A._send_discord_dm = lambda did, mk: (sent.__setitem__(did, mk()), (True, ''))[1]


def code_from_embed(embed):
    return embed.description.split('```fix')[1].split('```')[0].strip()


print('== 1. Владелец: пароль → сразу в панель, сессия привязана к OWNER_ID ==')
c = A.app.test_client()
r = c.post('/login', data={'username': 'owner', 'password': 'test-pass-123'})
check(r.status_code == 302, 'верный пароль владельца → редирект в панель',
      f'→ {r.status_code}')
with c.session_transaction() as s:
    check(s.get('role') == 'owner', 'роль owner')
    check(str(s.get('discord_id')) == '42',
          'сессия привязана к Discord ID владельца (живая перепроверка)',
          f'→ {s.get("discord_id")}')
    check(bool(s.get('_role_checked')), 'отметка живой проверки выставлена')

r = c.post('/login', data={'username': 'owner', 'password': 'плохой-пароль'})
check(r.status_code == 200 and 'Неверное' in r.get_data(as_text=True),
      'неверный пароль владельца → отказ')

print('== 2. Участник без роли: пароль верный, вход ЗАПРЕЩЁН ==')
c2 = A.app.test_client()
r = c2.post('/login', data={'username': '556', 'password': 'secret123'})
check('нужна роль' in r.get_data(as_text=True),
      'роль «участник» → в панель не пускает даже с паролем')

print('== 3. Модер + новое устройство: код из ЛС Discord обязателен ==')
r = c2.post('/login', data={'username': '555', 'password': 'secret123'})
page = r.get_data(as_text=True)
check('name="step" value="code"' in page,
      'после пароля показан шаг «код из ЛС Discord»')
check('555' in sent, 'код реально отправлен в ЛС модератора')
code = code_from_embed(sent['555'])
r = c2.post('/login', data={'step': 'code', 'discord_id': '555',
                            'code': code, 'username': '555'})
check(r.status_code == 302, 'верный код → вход', f'→ {r.status_code}')
check('panel_device' in (r.headers.get('Set-Cookie') or ''),
      'устройство помечено доверенным (cookie)')
with c2.session_transaction() as s:
    check(s.get('role') == 'mod' and s.get('discord_id') == '555',
          'сессия модератора с живой ролью')

print('== 4. Доверенное устройство: повторный вход без кода ==')
tok = list(A._trusted_store_read().keys())[0]
c3 = A.app.test_client()
c3.set_cookie('panel_device', tok)
r = c3.post('/login', data={'username': '555', 'password': 'secret123'})
check(r.status_code == 302, 'пароль → сразу вход, код не требуется',
      f'→ {r.status_code}')

print('== 5. Чужое устройство + чужой пароль: перебор кода блокируется ==')
c4 = A.app.test_client()
c4.post('/login', data={'username': '555', 'password': 'secret123'})
last = None
for _ in range(6):
    last = c4.post('/login', data={'step': 'code', 'discord_id': '555',
                                   'code': '000000', 'username': '555'})
with c4.session_transaction() as s:
    check('logged_in' not in s, 'сессия НЕ создана перебором')
check('много неверных кодов' in last.get_data(as_text=True),
      'после 5 промахов код сгорает')

print('== 6. Модер вышел с сервера → доступ умирает ДО действия ==')
c5 = A.app.test_client()
with c5.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'user555'
    s['role'] = 'mod'
    s['discord_id'] = '555'
    s['_role_checked'] = _time.time() - 120   # проверка протухла
GUILD_MEMBERS.pop(555)                        # вышел с сервера
r = c5.post('/api/commands/switch', json={'name': 'warn', 'disabled': False})
with c5.session_transaction() as s:
    check('logged_in' not in s, 'сессия погашена на первом же действии')
check(r.status_code in (302, 403), 'запрос не выполнен с чужой ролью',
      f'→ {r.status_code}')

# и та же история при снятии роли (человек на сервере, роли нет)
GUILD_MEMBERS[555] = make_member(555, mod=False)   # роль сняли
c5b = A.app.test_client()
with c5b.session_transaction() as s:
    s['logged_in'] = True
    s['role'] = 'mod'
    s['discord_id'] = '555'
    s['_role_checked'] = _time.time() - 400   # старше 5-минутного TTL для GET
r = c5b.get('/commands')
with c5b.session_transaction() as s:
    check('logged_in' not in s, 'снятие роли тоже гасит сессию')

print('== 7. Вход через Discord (PIN): без роли код не отправляется ==')
r = A.app.test_client().post('/api/discord-check',
                             json={'query': 'user556'})
d = r.get_json(silent=True) or {}
check(d.get('success') is False and 'роль модератора' in (d.get('error') or ''),
      'участнику без роли PIN не отправляется', f'→ {d.get("error")}')
check('556' not in A._login_pins, 'PIN-код для него не создавался')

print('== 8. Вход через Discord (PIN): полный цикл с реальной проверкой ==')
# возвращаем модератора после сценариев 6 (там роль снималась)
GUILD_MEMBERS[555] = make_member(555, mod=True)
# настоящий asyncio-луп, чтобы send_pin дошёл до «ЛС»
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()
fake_users = {555: NS(display_name='user555', name='user555',
                      bot=False, id=555, send=None)}
_sent_pins = []


class FakeUser:
    def __init__(self, uid):
        self.uid = uid

    async def send(self, content=None, embed=None):
        _sent_pins.append(embed)


async def fake_fetch(uid):
    return FakeUser(uid)


A.bot_instance = NS(guilds=[guild],
                    get_guild=lambda gid: guild if gid == 777 else None,
                    loop=loop, latency=0.05, fetch_user=fake_fetch)

cc = A.app.test_client()
r = cc.post('/api/discord-check', json={'query': 'user555'})
d = r.get_json(silent=True) or {}
check(d.get('success') is True, 'модератору код отправлен', f'→ {d}')
check(any(t.get('name') == 'Роль модератора' and t.get('status') == 'ok'
          for t in d.get('tests', [])),
      'в чек-листе видна живая проверка роли')
check(len(_sent_pins) == 1, 'PIN ушёл в ЛС ровно один раз')
pin = _sent_pins[0].description.split('```fix')[1].split('```')[0].strip()
r = cc.post('/api/discord-login', json={'discord_id': '555', 'pin': pin})
d = r.get_json(silent=True) or {}
check(d.get('success') is True and d.get('redirect') == '/',
      'верный PIN → вход', f'→ {d}')
check('panel_device' in (r.headers.get('Set-Cookie') or ''),
      'после Discord-входа устройство доверенное')

print('== 9. Регистрация: участник вышел между шагами → отмена ==')
A.PENDING_VERIFICATIONS['999'] = {
    'code': '123456', 'password': A._hash_pw('qwerty123'),
    'member_info': {'display_name': 'x', 'name': 'x', 'avatar': ''},
    'created_at': _time.time()}
r = A.app.test_client().post('/register', data={
    'step': '2', 'discord_id': '999', 'code': '123456',
    'password': 'qwerty123', 'password2': 'qwerty123'})
check('нет на основном сервере' in r.get_data(as_text=True),
      'вышедший с сервера не может завершить регистрацию')
check('999' not in A.PENDING_VERIFICATIONS, 'заявка registration удалена')

A.PENDING_VERIFICATIONS['888'] = {
    'code': '654321', 'password': 'x',
    'member_info': {'display_name': 'y', 'name': 'y', 'avatar': ''},
    'created_at': _time.time() - 700}
r = A.app.test_client().post('/register', data={
    'step': '2', 'discord_id': '888', 'code': '654321',
    'password': 'x', 'password2': 'x'})
check('истёк' in r.get_data(as_text=True), 'код регистрации протухает (10 минут)')

print('== 10. Вход без двойной проверки: /api/login-probe удалён ==')
A.bot_instance = NS(guilds=[guild],
                    get_guild=lambda gid: guild if gid == 777 else None,
                    loop=None, latency=0.05)   # без лупа: DM не шлёт
r = A.app.test_client().post('/api/login-probe',
                             json={'username': '555', 'password': 'secret123'})
check(r.status_code == 404,
      '/api/login-probe больше нет (проверка ОДНА — в POST /login)',
      f'→ {r.status_code}')
# Новое устройство → POST /login сам показывает шаг кода из ЛС Discord
_r2 = A.app.test_client().post('/login',
                               data={'username': '555', 'password': 'secret123'})
check('Код подтверждения отправлен' in _r2.get_data(as_text=True),
      'новое устройство → POST /login сам просит код из ЛС',
      f'→ {_r2.status_code}')

print('== 11а. Возраст аккаунта реально вычисляется (регресс «Неизвестно») ==')
# в сценарии 8 чек-лист уже получен: проверяем строку возраста
r = A.app.test_client().post('/api/discord-check', json={'query': 'user555'})
d = r.get_json(silent=True) or {}
_age = next((t for t in d.get('tests', []) if t.get('name') == 'Возраст аккаунта'), {})
check(_age.get('status') == 'ok' and 'Неизвестно' not in (_age.get('detail') or ''),
      'возраст аккаунта вычислен, а не «Неизвестно»', f'→ {_age}')
check(('дн.' in (_age.get('detail') or '')) or ('мес.' in (_age.get('detail') or '')),
      'возраст показан по-человечески', f'→ {_age.get("detail")}')

print('== 11б. Ник не в кэше бота — ищем в members.json, проверяем fetch ==')
_empty = NS(id=777, owner_id=42, name='Hakumo Test', get_member=lambda uid: None, members=[])
_saved_bot = A.bot_instance
_saved_res = A._resolve_guild_member
A.bot_instance = NS(guilds=[_empty], get_guild=lambda gid: _empty if gid == 777 else None,
                    loop=loop, latency=0.05, fetch_user=fake_fetch)
A._resolve_guild_member = lambda g, uid: GUILD_MEMBERS.get(uid)  # «fetch_member»
getattr(A.api_discord_check, '_pin_sends', {}).pop('555', None)  # сброс лимита
try:
    r = A.app.test_client().post('/api/discord-check', json={'query': 'user555'})
    d = r.get_json(silent=True) or {}
    check(d.get('success') is True and d.get('discord_id') == '555',
          'ник найден через members.json + fetch, бот-кэш пустой не мешает',
          f'→ {d.get("success")} {d.get("error")}')
finally:
    A.bot_instance = _saved_bot
    A._resolve_guild_member = _saved_res

print('== 11. Страницы входа/регистрации ==')
r = A.app.test_client().get('/login')
page = r.get_data(as_text=True)
check(r.status_code == 200, 'страница входа открывается')
check('Через Discord' in page and 'По паролю' in page,
      'на входе два способа: Discord-PIN и пароль')
r = A.app.test_client().get('/register')
check(r.status_code == 200, 'страница регистрации открывается')

loop.call_soon_threadsafe(loop.stop)

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
