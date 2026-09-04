# -*- coding: utf-8 -*-
"""Живая матрица доступа: какая роль куда реально попадает.

Сценарий аудита «все связки»: owner/admin/mod/uye против страниц и
API. uye не проходит ВХОД вообще (живая проверка роли на логине) —
для матрицы ему симулируется унаследованная сессия, и защита обязана
гасить её на каждом защищённом маршруте.

Запуск: python3 tests/test_access_matrix.py
"""

import os, sys, tempfile, asyncio, threading
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'owner-pass-123'
os.environ['OWNER_ID'] = '42'
os.environ.pop('DEMO_MODE', None)
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['PANEL_LOGIN_CONFIRM'] = '0'   # без DM-подтверждения — чистая матрица ролей
_TMP = tempfile.mkdtemp(prefix='hakumo_matrix_')
os.chdir(_TMP)
sys.path.insert(0, '/home/user/New-Pro')
from types import SimpleNamespace as NS
import web.app as A

def make_member(uid, mod=False, admin=False):
    perms = NS(administrator=admin, ban_members=mod, kick_members=mod,
               manage_guild=False, manage_messages=False, manage_channels=False)
    return NS(id=uid, bot=False, roles=[], guild_permissions=perms,
              display_name=f'user{uid}', name=f'user{uid}')

GUILD_MEMBERS = {
    '100': make_member(100, admin=True),          # админ сервера
    '200': make_member(200, mod=True),            # модератор
    '300': make_member(300, mod=False),           # участник (uye)
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
                    fetch_user=lambda uid: NS(id=uid, send=None) if False else None)
A._resolve_guild_member = lambda g, uid: GUILD_MEMBERS.get(str(uid))
os.makedirs('data', exist_ok=True)
import json
json.dump({
    '100': {'display_name': 'admin100', 'name': 'admin100', 'role': 'admin', 'password': A._hash_pw('pass-admin'), 'registered_at': '2026-01-01'},
    '200': {'display_name': 'mod200', 'name': 'mod200', 'role': 'mod', 'password': A._hash_pw('pass-mod'), 'registered_at': '2026-01-01'},
    '300': {'display_name': 'member300', 'name': 'member300', 'role': 'uye', 'password': A._hash_pw('pass-uye'), 'registered_at': '2026-01-01'},
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

# ожидание: True = должен пустить, False = должен НЕ пустить (302 на / или 403)
CASES = [
    # (описание, метод+путь, {role: allowed})
    ('страница Цветные роли',        ('GET', '/color-roles'),           {'owner': True, 'admin': False, 'mod': False, 'uye': False}),
    ('страница Настройки каналов',   ('GET', '/channel-settings'),      {'owner': True, 'admin': True, 'mod': True, 'uye': False}),
    ('страница Приветствия',         ('GET', '/welcome-editor'),        {'owner': True, 'admin': True, 'mod': False, 'uye': False}),
    ('страница Уведомления',         ('GET', '/notifications'),         {'owner': True, 'admin': True, 'mod': True, 'uye': False}),
    ('страница Апелляции',           ('GET', '/appeals'),               {'owner': True, 'admin': True, 'mod': True, 'uye': False}),
    ('страница Участники (/users)',  ('GET', '/users'),                 {'owner': True, 'admin': True, 'mod': False, 'uye': False}),
    ('страница Обзор',               ('GET', '/'),                      {'owner': True, 'admin': True, 'mod': True, 'uye': 'member'}),
    ('API: todo/add (owner)',        ('POST', '/api/todo/add', {'text': 'x'}),   {'owner': True, 'admin': False, 'mod': False, 'uye': False}),
    ('API: ai-mod/test (admin)',     ('POST', '/api/ai-mod/test', {'text': 'привет'}), {'owner': True, 'admin': True, 'mod': False, 'uye': False}),
    ('API: autofilter/save (admin)', ('POST', '/api/autofilter/save', {'words': {'enabled': False}}), {'owner': True, 'admin': True, 'mod': False, 'uye': False}),
    ('API: список участников',       ('GET', '/api/guild/777/members'), {'owner': True, 'admin': True, 'mod': True, 'uye': False}),
    ('API: каналы',                  ('GET', '/api/channels'),          {'owner': True, 'admin': True, 'mod': True, 'uye': True}),
]
USERS = [('owner', {'pw': 'owner-pass-123'}), ('admin', ('100', 'pass-admin')),
         ('mod', ('200', 'pass-mod')), ('uye', ('300', 'pass-uye'))]

sessions = {}
for role in ('owner', 'admin', 'mod', 'uye'):
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

for name, (method, path, *payload), expectations in CASES:
    for role in ('owner', 'admin', 'mod', 'uye'):
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

print(f'\n════ МАТРИЦА ДОСТУПА: PASS {PASS} / FAIL {FAIL} ════')
sys.exit(1 if FAIL else 0)
