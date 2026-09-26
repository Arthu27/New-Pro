# -*- coding: utf-8 -*-
"""Робастность write-API: пустые/мусорные тела не дают 500.

История: паттерн `request.get_json(silent=True) or {}` пропускал
списки/строки (→ AttributeError → 500); bulk/purge-маршруты падали
KeyError'ом на отсутствующих полях; command/ban|kick — int(None).
Теперь везде _safe_json_obj() + валидация полей (400).

Запуск: python3 tests/test_write_api_robustness.py
"""
import json
import os
import sys
import tempfile
import asyncio
import threading

os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'owner-pass-123'
os.environ['OWNER_ID'] = '42'
os.environ.pop('DEMO_MODE', None)
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['PANEL_LOGIN_CONFIRM'] = '0'
os.environ['DB_PATH'] = os.path.join(tempfile.mkdtemp(prefix='hakumo_wadb_'), 'bot.db')
_TMP = tempfile.mkdtemp(prefix='hakumo_wa_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from types import SimpleNamespace as NS

os.makedirs('data', exist_ok=True)
json.dump({'400': 'curator'}, open('data/role_map.json', 'w'))

import web.app as A


def make_member(uid, admin=False, mod=False):
    perms = NS(administrator=admin, ban_members=mod, kick_members=mod,
               manage_guild=False, manage_messages=False, manage_channels=False)
    m = NS(id=uid, bot=False, roles=[], guild_permissions=perms,
           display_name=f'user{uid}', name=f'user{uid}',
           display_avatar=NS(url='http://avatar/'), status=None, joined_at=None, nick=None)

    async def _to(until, reason=''):
        pass

    m.timeout = _to
    return m


class FakeChannel:
    id = 1001
    name = 'chan1001'
    members = []
    mention = '<#1001>'

    def __init__(self):
        pass

    async def fetch_message(self, mid):
        m = NS(id=mid, author=NS(id=999, name='a', bot=False), content='x', created_at=None, pinned=False)

        async def _del():
            return None
        m.delete = _del
        return m

    async def purge(self, limit=10):
        return []

    async def delete(self):
        return None


GUILD_MEMBERS = {'100': make_member(100, admin=True), '200': make_member(200, mod=True)}
guild = NS(id=777, owner_id=42, name='Robust', description='stub',
           me=NS(id=1, name='bot', display_avatar=NS(url='http://avatar/'), bot=True),
           get_member=lambda uid: GUILD_MEMBERS.get(str(uid)),
           get_channel=lambda cid: FakeChannel(),
           get_role=lambda rid: None,
           members=list(GUILD_MEMBERS.values()), roles=[], channels=[FakeChannel()])
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()


async def _presence(**k):
    return None


A.bot_instance = NS(guilds=[guild], get_guild=lambda gid: guild if gid == 777 else None,
                    loop=loop, latency=0.05,
                    get_cog=lambda n: NS(_mutes={}, _bans={}, _kicks={}, _scheduled=[],
                                          _mutes_file=lambda: 'd1', _bans_file=lambda: 'd2',
                                          _kicks_file=lambda: 'd3', _scheduled_file=lambda: 'd4',
                                          _save=lambda w, p: None) if n == 'TempModeration' else None,
                    get_channel=lambda cid: FakeChannel(),
                    get_role=lambda rid: None,
                    change_presence=_presence,
                    description='stub', application_id=1, user=NS(id=1, name='bot'))
A._resolve_guild_member = lambda g, uid: GUILD_MEMBERS.get(str(uid))
json.dump({
    '100': {'display_name': 'admin100', 'name': 'admin100', 'role': 'admin', 'password': A._hash_pw('p-admin'), 'registered_at': 'x'},
    '200': {'display_name': 'mod200', 'name': 'mod200', 'role': 'mod', 'password': A._hash_pw('p-mod'), 'registered_at': 'x'},
}, open('data/members.json', 'w'))

c = A.app.test_client()
c.post('/login', data={'username': 'owner', 'password': 'owner-pass-123'})

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


BODIES = [None, {}, [1, 2, 3], 'мусор', 42]

CASES = [
    ('POST', '/api/todo/add'),
    ('POST', '/api/todo/toggle'),
    ('POST', '/api/todo/delete'),
    ('POST', '/api/command/ban'),
    ('POST', '/api/command/kick'),
    ('POST', '/api/command/warn'),
    ('POST', '/api/temp-mod/mute'),
    ('POST', '/api/temp-mod/ban'),
    ('POST', '/api/temp-mod/unmute'),
    ('POST', '/api/temp-mod/unschedule'),
    ('POST', '/api/guild/777/purge'),
    ('POST', '/api/guild/777/bulk-ban'),
    ('POST', '/api/guild/777/bulk-mute'),
    ('POST', '/api/guild/777/bulk-kick'),
    ('POST', '/api/guild/777/bulk-roles'),
    ('POST', '/api/guild/777/bulk-dm'),
    ('POST', '/api/bot/status'),
    ('POST', '/api/chat/777/1001/delete/55'),
    ('POST', '/api/guild/777/roles/500/delete'),
    ('POST', '/api/role-permissions/777/action/set'),
    ('POST', '/api/guild/777/rules'),
    ('POST', '/api/feature-flags/toggle'),
    ('POST', '/api/ai-mod/test', {'text': 'привет'}),
]

for case in CASES:
    method, path = case[0], case[1]
    good = case[2] if len(case) > 2 else None
    for body in BODIES:
        kwargs = {}
        if body is not None:
            kwargs['json'] = body
        r = c.open(path, method=method, follow_redirects=False, **kwargs)
        check(r.status_code < 500, f'{method} {path} тело={body!r} → не 5xx', str(r.status_code))
    if good is not None:
        r = c.open(path, method=method, json=good, follow_redirects=False)
        check(r.status_code < 500, f'{method} {path} валидное тело → не 5xx', str(r.status_code))

# валидация полей: внятный 400 с указанием, чего не хватает
r = c.post('/api/guild/777/purge', json={})
check(r.status_code == 400 and 'channel_id' in r.get_json().get('error', ''),
      'purge без полей → 400 с перечнем', f'{r.status_code} {r.get_data(as_text=True)[:100]}')
r = c.post('/api/command/ban', json={'guild_id': 'abc'})
check(r.status_code == 400, 'command/ban с нечисловым id → 400', f'{r.status_code}')
r = c.post('/api/temp-mod/unmute', json={'user_id': ''})
check(r.status_code == 400, 'unmute с пустым user_id → 400', f'{r.status_code} {r.get_data(as_text=True)[:100]}')

print(f'\n════ WRITE-API ROBUSTNESS: PASS {PASS} / FAIL {FAIL} ════')
sys.exit(1 if FAIL else 0)
