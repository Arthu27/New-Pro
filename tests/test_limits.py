# -*- coding: utf-8 -*-
"""Все лимиты панели — «туда» (блокирует) и «сюда» (отпускает).

Сценарий владельца: «сделай проверки лимитов туда-сюда, всё проверь».

Матрица лимитов:
  * пароль: троттлинг неверных попыток 0.5с*n, окно 15 мин, потолок 3с;
  * код подтверждения входа (пароль + ЛС): повторная отправка ≤3/10 мин,
    TTL 10 мин, перебор — код сгорает после 5 промахов, код одноразовый;
  * PIN-вход: отправка ≤3/10 мин, TTL 5 мин, перебор — PIN сгорает после
    5 промахов, PIN одноразовый;
  * код сброса пароля: TTL 10 мин, перебор — сгорает после 5 промахов;
  * доверенное устройство: доверие живёт 30 дней, чужой аккаунт не подходит;
  * возраст аккаунта: младше 7 дней вход запрещён;
  * живая перепроверка роли: GET раз в 5 мин / POST раз в минуту —
    покрыто в tests/test_auth_live_checks.py (сценарии 8-10), здесь не дублируем.

Запуск: python3 tests/test_limits.py
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

_TMP = tempfile.mkdtemp(prefix='hakumo_limits_')
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


def make_member(uid, mod=True):
    perms = NS(administrator=False, ban_members=mod, kick_members=mod,
               manage_guild=False, manage_messages=False, manage_channels=False)
    return NS(id=uid, bot=False, roles=[], guild_permissions=perms,
              display_name=f'user{uid}', name=f'user{uid}')


GUILD_MEMBERS = {555: make_member(555), 999: make_member(999)}
guild = NS(id=777, owner_id=42, name='Hakumo Test',
           get_member=lambda uid: GUILD_MEMBERS.get(uid),
           members=list(GUILD_MEMBERS.values()))

# Живой цикл + фейковый fetch_user: PIN «уходит» в ЛС без ошибки
_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()


class FakeUser:
    def __init__(self, uid):
        self.uid = uid

    async def send(self, content=None, embed=None):
        return None


async def fake_fetch(uid):
    return FakeUser(uid)


A.bot_instance = NS(guilds=[guild],
                    get_guild=lambda gid: guild if gid == 777 else None,
                    loop=_loop, latency=0.05, fetch_user=fake_fetch)
A._resolve_guild_member = lambda g, uid: GUILD_MEMBERS.get(
    int(uid) if str(uid).isdigit() else uid)
os.makedirs('data', exist_ok=True)


c = A.app.test_client()

# ════════════════════════════════════════════════════════════════════
print('== 1. Пароль: троттлинг неверных попыток — растёт, отпускает, потолок ==')
_sleeps = []
_real_sleep = A._time.sleep
A._time.sleep = lambda s: _sleeps.append(round(s, 2))
try:
    _thr = A.app.test_request_context('/', environ_base={'REMOTE_ADDR': '9.9.9.9'})
    _thr.push()
    A._throttle_failed_login('thr-user')
    A._throttle_failed_login('thr-user')
    A._throttle_failed_login('thr-user')
    check(_sleeps == [0.5, 1.0, 1.5],
          'задержка растёт с каждой неудачей: 0.5с → 1с → 1.5с', f'→ {_sleeps}')
    for _ in range(5):
        A._throttle_failed_login('thr-user')
    check(_sleeps[-1] == 3.0, 'потолок задержки 3с не превышается',
          f'→ {_sleeps[-3:]}')
    _key = [k for k in A._login_fails if k[1] == 'thr-user'][0]
    A._login_fails[_key] = [_time.time() - 901] * 8  # окно 15 мин истекло
    A._throttle_failed_login('thr-user')
    check(_sleeps[-1] == 0.5, 'через 15 минут лимит ОТПУСТИЛО (снова 0.5с)',
          f'→ {_sleeps[-1]}')
    _thr.pop()
finally:
    A._time.sleep = _real_sleep

# ════════════════════════════════════════════════════════════════════
print('== 2. Код входа (пароль+ЛС): повторная отправка ≤3/10 мин ==')
A._send_discord_dm = lambda did, mk: (True, '')
for i in range(3):
    ok, err = A._issue_login_code('700', {'display_name': 'user700'})
    check(ok, f'отправка #{i + 1} кода подтверждения прошла') if i == 0 else None
ok, err = A._issue_login_code('700', {'display_name': 'user700'})
check(not ok and 'Слишком много кодов' in err,
      '4-я отправка ЗАБЛОКИРОВАНА (лимит 3 за 10 минут)', f'→ {err!r}')
A._login_dm_codes['700']['resends'] = [t - 601 for t in
                                       A._login_dm_codes['700']['resends']]
ok, err = A._issue_login_code('700', {'display_name': 'user700'})
check(ok, 'через 10 минут лимит ОТПУСТИЛО — код снова уходит', f'→ {err!r}')

print('== 3. Код входа: перебор — 5 промахов и код сгорел ==')
A._login_dm_codes['701'] = {'code': '111222', 'expires': _time.time() + 600,
                            'attempts': 0, 'member_info': {'display_name': 'u'},
                            'resends': [_time.time()]}
res = [A._check_login_code('701', '000000') for _ in range(5)]
check(all(r == 'bad' for r in res), '5 неверных вводов → «bad»', f'→ {res}')
check(A._check_login_code('701', '111222') == 'locked',
      '6-я попытка (даже ВЕРНЫМ кодом) → «locked» — перебор невозможен')
check(A._check_login_code('701', '111222') == 'expired',
      'сгоревшая запись исчезла (новый код только по запросу)')

print('== 4. Код входа: TTL 10 минут и одноразовость ==')
A._login_dm_codes['702'] = {'code': '333444', 'expires': _time.time() - 1,
                            'attempts': 0, 'member_info': {'display_name': 'u'},
                            'resends': [_time.time()]}
check(A._check_login_code('702', '333444') == 'expired',
      'просроченный код → «expired», даже если набран верно')
check('702' not in A._login_dm_codes, 'просроченная запись удалена')
A._login_dm_codes['703'] = {'code': '555666', 'expires': _time.time() + 600,
                            'attempts': 0, 'member_info': {'dn': 'ok'},
                            'resends': [_time.time()]}
check(A._check_login_code('703', '555666') == {'dn': 'ok'},
      'верный код → вход разрешён')
check(A._check_login_code('703', '555666') == 'expired',
      'код ОДНОРАЗОВЫЙ: повторно не принимается')

# ════════════════════════════════════════════════════════════════════
print('== 5. PIN-вход: отправка ≤3/10 мин — блокирует и отпускает ==')
getattr(A.api_discord_check, '_pin_sends', {}).pop('555', None)
for i in range(3):
    r = c.post('/api/discord-check', json={'query': 'user555'})
    d = r.get_json(silent=True) or {}
    check(d.get('success') is True, f'PIN-отправка #{i + 1} прошла',
          f'→ {d.get("error")}')
r = c.post('/api/discord-check', json={'query': 'user555'})
d = r.get_json(silent=True) or {}
check(d.get('success') is False and 'Слишком много кодов' in d.get('error', ''),
      '4-я отправка PIN ЗАБЛОКИРОВАНА (3 за 10 минут)', f'→ {d}')
A.api_discord_check._pin_sends['555'] = [t - 601 for t in
                                         A.api_discord_check._pin_sends['555']]
r = c.post('/api/discord-check', json={'query': 'user555'})
d = r.get_json(silent=True) or {}
check(d.get('success') is True,
      'через 10 минут лимит ОТПУСТИЛО — PIN снова уходит', f'→ {d.get("error")}')

print('== 6. PIN-вход: перебор — 5 промахов и PIN сгорел (НОВОЕ) ==')
pin_code = A._login_pins['555']['code']
ans = []
for _ in range(5):
    r = c.post('/api/discord-login', json={'discord_id': '555', 'pin': '000000'})
    ans.append((r.get_json(silent=True) or {}).get('error', ''))
check(all('неверный PIN-код' in a for a in ans),
      '5 неверных PIN → «Введен неверный PIN-код»', f'→ {ans}')
r = c.post('/api/discord-login', json={'discord_id': '555', 'pin': pin_code})
d = r.get_json(silent=True) or {}
check(d.get('success') is False and 'Слишком много неверных PIN' in d.get('error', ''),
      '6-я попытка ВЕРНЫМ PIN → сгорел, перебор невозможен', f'→ {d}')
r = c.post('/api/discord-login', json={'discord_id': '555', 'pin': pin_code})
d = r.get_json(silent=True) or {}
check('не найден активный PIN' in d.get('error', ''),
      'сгоревший PIN исчез — только отправка нового', f'→ {d}')

print('== 7. PIN-вход: TTL 5 минут и одноразовость ==')
A._login_pins['555'] = {'code': '987654', 'expires': _time.time() - 1,
                        'member_info': {'display_name': 'user555',
                                        'name': 'user555', 'avatar': ''}}
r = c.post('/api/discord-login', json={'discord_id': '555', 'pin': '987654'})
d = r.get_json(silent=True) or {}
check('Срок действия PIN-кода истек' in d.get('error', ''),
      'просроченный PIN → отказ, даже если набран верно', f'→ {d}')
A._login_pins['555'] = {'code': '123321', 'expires': _time.time() + 300,
                        'attempts': 0, 'member_info': {'display_name': 'user555',
                                                       'name': 'user555', 'avatar': ''}}
r = c.post('/api/discord-login', json={'discord_id': '555', 'pin': '123321'})
d = r.get_json(silent=True) or {}
check(d.get('success') is True, 'верный PIN → успех', f'→ {d.get("error")}')
r = c.post('/api/discord-login', json={'discord_id': '555', 'pin': '123321'})
d = r.get_json(silent=True) or {}
check('не найден активный PIN' in d.get('error', ''),
      'PIN ОДНОРАЗОВЫЙ: повторно не принимается', f'→ {d}')

# ════════════════════════════════════════════════════════════════════
print('== 8. Сброс пароля: перебор и TTL кода ==')
A._reset_codes['555'] = {'code': '777888', 'expires': _time.time() + 600}
errs = []
for _ in range(5):
    r = c.post('/api/reset-password', json={'discord_id': '555',
                                            'code': '000000',
                                            'new_password': 'newpass123'})
    errs.append((r.get_json(silent=True) or {}).get('error', ''))
check(all('Неверный код' in e for e in errs),
      '5 неверных кодов сброса → «Неверный код»', f'→ {errs}')
r = c.post('/api/reset-password', json={'discord_id': '555', 'code': '777888',
                                        'new_password': 'newpass123'})
d = r.get_json(silent=True) or {}
check('Слишком много неверных кодов' in d.get('error', ''),
      '6-я попытка верным кодом → код сгорел', f'→ {d}')
r = c.post('/api/reset-password', json={'discord_id': '555', 'code': '777888',
                                        'new_password': 'newpass123'})
d = r.get_json(silent=True) or {}
check('Сначала запросите код' in d.get('error', ''),
      'сгоревшая запись удалена — код запрашивается заново', f'→ {d}')
A._reset_codes['555'] = {'code': '777888', 'expires': _time.time() - 1}
r = c.post('/api/reset-password', json={'discord_id': '555', 'code': '777888',
                                        'new_password': 'newpass123'})
d = r.get_json(silent=True) or {}
check('Срок действия кода истёк' in d.get('error', ''),
      'TTL 10 минут: просроченный код сброса не работает', f'→ {d}')

# ════════════════════════════════════════════════════════════════════
print('== 9. Доверенное устройство: живёт 30 дней, чужой аккаунт не подходит ==')
A._trusted_store_write({'TOK1': {'discord_id': '555', 'created_at': _time.time()},
                        'TOK2': {'discord_id': '555',
                                 'created_at': _time.time() - 31 * 24 * 3600},
                        'TOK3': {'discord_id': '42', 'created_at': _time.time()}})
with A.app.test_request_context('/', headers={'Cookie': 'panel_device=TOK1'}):
    check(A._device_trusted('555') is True,
          'свежая доверенность (25 день из 30) → код повторно не спрашивают')
with A.app.test_request_context('/', headers={'Cookie': 'panel_device=TOK2'}):
    check(A._device_trusted('555') is False,
          'через 31 день доверенность ПРОТУХЛА — снова нужен код из ЛС')
with A.app.test_request_context('/', headers={'Cookie': 'panel_device=TOK3'}):
    check(A._device_trusted('555') is False,
          'доверенность ДРУГОГО аккаунта не работает (чей аккаунт — сверен)')
with A.app.test_request_context('/'):
    check(A._device_trusted('555') is False,
          'без cookie устройство недоверенное')

# ════════════════════════════════════════════════════════════════════
print('== 10. Возраст аккаунта: младше 7 дней вход запрещён ==')
_DAYS = 24 * 3600
young_id = (int((_time.time() - 3 * _DAYS - 1420070400) * 1000) << 22)
GUILD_MEMBERS[young_id] = make_member(young_id)
guild.members.append(GUILD_MEMBERS[young_id])
r = c.post('/api/discord-check', json={'query': str(young_id)})
d = r.get_json(silent=True) or {}
age = next((t for t in d.get('tests', []) if t.get('name') == 'Возраст аккаунта'), {})
check(d.get('success') is False and 'менее 7 дней' in d.get('error', ''),
      'аккаунт 3 дней → ВХОД ЗАПРЕЩЁН', f'→ {d.get("error")}')
check(age.get('status') == 'fail' and 'дн.' in age.get('detail', ''),
      'в чек-листе честно показан возраст в днях', f'→ {age}')
check(getattr(A.api_discord_check, '_pin_sends', {}).get(str(young_id)) is None,
      'запрещённому по возрасту PIN НЕ отправлялся (и лимит не тратился)')

print(f'\\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
