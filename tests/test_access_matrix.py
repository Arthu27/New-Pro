# -*- coding: utf-8 -*-
"""Живая матрица доступа: какая роль куда реально попадает.

Сценарий аудита «все связки»: owner/admin/curator/mod/uye против страниц
и API. uye не проходит ВХОД вообще (живая проверка роли на логине) —
для матрицы ему симулируется унаследованная сессия, и защита обязана
гасить её на каждом защищённом маршруте. Куратор входит живьём через
role_map (данные роль-карты читаются ОДИН раз на import web.app).

Запуск: python3 tests/test_access_matrix.py
"""

import os, sys, tempfile, asyncio, threading, json
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'owner-pass-123'
os.environ['OWNER_ID'] = '42'
os.environ.pop('DEMO_MODE', None)
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['PANEL_LOGIN_CONFIRM'] = '0'   # без DM-подтверждения — чистая матрица ролей
_TMP = tempfile.mkdtemp(prefix='hakumo_matrix_')
os.chdir(_TMP)
sys.path.insert(0, '/home/user/New-Pro')
# role_map ДО импорта web.app: карта Discord-ролей читается один раз на import
os.makedirs('data', exist_ok=True)
json.dump({'400': 'curator'}, open('data/role_map.json', 'w'))
from types import SimpleNamespace as NS
import web.app as A

def make_member(uid, mod=False, admin=False, role_ids=()):
    perms = NS(administrator=admin, ban_members=mod, kick_members=mod,
               manage_guild=False, manage_messages=False, manage_channels=False)
    return NS(id=uid, bot=False,
              roles=[NS(id=r, name=f'role{r}', members=[], colour=None) for r in role_ids],
              guild_permissions=perms, display_name=f'user{uid}', name=f'user{uid}')

GUILD_MEMBERS = {
    '100': make_member(100, admin=True),                  # админ сервера
    '200': make_member(200, mod=True),                    # модератор
    '300': make_member(300, mod=False),                   # участник (uye)
    '400': make_member(400, role_ids=[400]),              # куратор (роль 400 → role_map)
}
import discord as _discord
_ch = NS(id=1001, name='pravila', position=0, type=_discord.ChannelType.text, category=None,
         topic='', nsfw=False, slowmode_delay=0, bitrate=0, user_limit=0,
         created_at=None, mention='<#1001>', members=[])
guild = NS(id=777, owner_id=42, name='Matrix', get_member=lambda uid: GUILD_MEMBERS.get(str(uid)),
           members=list(GUILD_MEMBERS.values()), channels=[_ch])
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()
A.bot_instance = NS(guilds=[guild], get_guild=lambda gid: guild if gid == 777 else None,
                    loop=loop, latency=0.05, get_cog=lambda name: None,
                    get_role=lambda rid: NS(id=rid, name=f'role{rid}', members=[], colour=None,
                                            permissions=NS(administrator=False, ban_members=False,
                                                           kick_members=False, manage_guild=False,
                                                           manage_messages=False, manage_channels=False)),
                    fetch_user=lambda uid: NS(id=uid, send=None) if False else None)
A._resolve_guild_member = lambda g, uid: GUILD_MEMBERS.get(str(uid))
json.dump({
    '100': {'display_name': 'admin100', 'name': 'admin100', 'role': 'admin', 'password': A._hash_pw('pass-admin'), 'registered_at': '2026-01-01'},
    '200': {'display_name': 'mod200', 'name': 'mod200', 'role': 'mod', 'password': A._hash_pw('pass-mod'), 'registered_at': '2026-01-01'},
    '300': {'display_name': 'member300', 'name': 'member300', 'role': 'uye', 'password': A._hash_pw('pass-uye'), 'registered_at': '2026-01-01'},
    '400': {'display_name': 'curator400', 'name': 'curator400', 'role': 'curator', 'password': A._hash_pw('pass-cur'), 'registered_at': '2026-01-01'},
}, open('data/members.json', 'w'))

c = A.app.test_client()
PASS = FAIL = 0
def check(name, cond, extra=''):
    global PASS, FAIL
    if cond: PASS += 1; print(f'  PASS {name}')
    else: FAIL += 1; print(f'  FAIL {name} {extra}')

def login_as(did, pw):
    cc = A.app.test_client()
    r = cc.post('/login', data={'username': did, 'password': pw})
    assert r.status_code == 302, (did, r.status_code)
    return cc

# ожидание: True = должен пустить, False = должен НЕ пустить (302 на /?denied= или 403)
# куратор — mod-тир (уровень 2): всё, что доступно mod, плюс ничего из admin+
CASES = [
    # (описание, метод+путь, {role: allowed})
    ('страница Цветные роли',        ('GET', '/color-roles'),           {'owner': True, 'admin': False, 'curator': False, 'mod': False, 'uye': False}),
    ('страница Настройки каналов',   ('GET', '/channel-settings'),      {'owner': True, 'admin': True, 'curator': True, 'mod': True, 'uye': False}),
    ('страница Приветствия',         ('GET', '/welcome-editor'),        {'owner': True, 'admin': True, 'curator': False, 'mod': False, 'uye': False}),
    ('страница Уведомления',         ('GET', '/notifications'),         {'owner': True, 'admin': True, 'curator': True, 'mod': True, 'uye': False}),
    ('страница Апелляции',           ('GET', '/appeals'),               {'owner': True, 'admin': True, 'curator': True, 'mod': True, 'uye': False}),
    ('страница Участники (/users)',  ('GET', '/users'),                 {'owner': True, 'admin': True, 'curator': False, 'mod': False, 'uye': False}),
    ('страница Обзор',               ('GET', '/'),                      {'owner': True, 'admin': True, 'curator': True, 'mod': True, 'uye': 'member'}),
    ('API: todo/add (owner)',        ('POST', '/api/todo/add', {'text': 'x'}),   {'owner': True, 'admin': False, 'curator': False, 'mod': False, 'uye': False}),
    ('API: ai-mod/test (admin)',     ('POST', '/api/ai-mod/test', {'text': 'привет'}), {'owner': True, 'admin': True, 'curator': False, 'mod': False, 'uye': False}),
    ('API: autofilter/save (admin)', ('POST', '/api/autofilter/save', {'words': {'enabled': False}}), {'owner': True, 'admin': True, 'curator': False, 'mod': False, 'uye': False}),
    ('API: список участников',       ('GET', '/api/guild/777/members'), {'owner': True, 'admin': True, 'curator': True, 'mod': True, 'uye': False}),
    ('API: каналы',                  ('GET', '/api/channels'),          {'owner': True, 'admin': True, 'curator': True, 'mod': True, 'uye': True}),
]
USERS = [('owner', {'pw': 'owner-pass-123'}), ('admin', ('100', 'pass-admin')),
         ('curator', ('400', 'pass-cur')), ('mod', ('200', 'pass-mod')), ('uye', ('300', 'pass-uye'))]

sessions = {}
for role in ('owner', 'admin', 'curator', 'mod', 'uye'):
    if role == 'owner':
        sessions[role] = A.app.test_client()
        sessions[role].post('/login', data={'username': 'owner', 'password': 'owner-pass-123'})
    elif role == 'uye':
        # uye не проходит ВХОД (живая роль-проверка) — симулируем
        # унаследованную сессию: защита должна гасить её на страницах
        cc = A.app.test_client()
        with cc.session_transaction() as ss:
            ss['logged_in'] = True
            ss['role'] = 'uye'
            ss['discord_id'] = '300'
            ss['username'] = 'member300'
            ss['_role_checked'] = A._time.time()
        sessions[role] = cc
    else:
        did, pw = USERS[[u[0] for u in USERS].index(role)][1]
        sessions[role] = login_as(did, pw)

# куратор должен получить роль 'curator' именно ЖИВОЙ проверкой role_map
assert sessions['curator'].get('/').status_code == 200, 'куратор не прошёл живую роль-проверку'

for name, (method, path, *payload), expectations in CASES:
    for role in ('owner', 'admin', 'curator', 'mod', 'uye'):
        kwargs = {}
        if payload: kwargs['json'] = payload[0]
        r = sessions[role].open(path, method=method, follow_redirects=False, **kwargs)
        allowed = r.status_code in (200, 304, 404)
        want = expectations[role]
        okflag = (allowed == want) or (want == 'member' and allowed)
        if not okflag:
            check(f'{name} [{role}]', False, f'ожидалось {"пуск" if want else "запрет"}, got {r.status_code}')
        else:
            check(f'{name} [{role}] → {"пуск" if want else "запрет"} ({r.status_code})', True)

# семантика запрета: страницы → redirect /?denied=, API → 403 JSON (проверяем на кураторе)
_r1 = sessions['curator'].get('/users')
check('запрет-страница: /users куратору → 302 /?denied=', _r1.status_code == 302 and _r1.headers.get('Location', '').startswith('/?denied='),
      f'got {_r1.status_code} {_r1.headers.get("Location", "")!r}')
_r2 = sessions['curator'].post('/api/ai-mod/test', json={'text': 'привет'})
check('запрет-API: /api/ai-mod/test куратору → 403 JSON', _r2.status_code == 403 and _r2.is_json, f'got {_r2.status_code}')
_r3 = sessions['curator'].get('/notifications')
check('допуск-страница: /notifications куратору → 200', _r3.status_code == 200, f'got {_r3.status_code}')

print(f'\n════ МАТРИЦА ДОСТУПА: PASS {PASS} / FAIL {FAIL} ════')
sys.exit(1 if FAIL else 0)
