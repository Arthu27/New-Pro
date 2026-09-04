# -*- coding: utf-8 -*-
"""Страницы и публичные зоны: rules-editor, analytics, users, публичные, 404.

Запуск: python3 tests/test_pages_public.py
"""
import io
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
_TMP = tempfile.mkdtemp(prefix='hakumo_pages_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from types import SimpleNamespace as NS

os.makedirs('data', exist_ok=True)
json.dump({'400': 'curator'}, open('data/role_map.json', 'w'))

import web.app as A


class FakeMember:
    def __init__(self, uid):
        self.id = uid
        self.name = f'user{uid}'
        self.display_name = self.name


MEMBERS = {300: FakeMember(300)}


class FakeGuild:
    id = 777
    owner_id = 42
    name = 'Pages'
    roles = []
    channels = []
    members = property(lambda self: list(MEMBERS.values()))

    def get_member(self, uid):
        return MEMBERS.get(int(uid))

    def get_channel(self, cid):
        return None

    def get_role(self, rid):
        return None


guild = FakeGuild()
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()


async def _fetch_user(uid):
    from datetime import datetime, timezone
    return NS(id=uid, name=f'u{uid}', display_name=f'u{uid}', bot=False, send=None,
              discriminator='0', created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
              avatar=None, display_avatar=NS(url='http://avatar/'))


A.bot_instance = NS(guilds=[guild], get_guild=lambda gid: guild if gid == 777 else None,
                    loop=loop, latency=0.05, get_cog=lambda n: None,
                    get_channel=lambda cid: None, get_role=lambda rid: None,
                    fetch_user=_fetch_user,
                    change_presence=lambda **k: None, description='stub', application_id=1,
                    user=NS(id=1, name='bot'))

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


# ── RULES: полный цикл редактора ────────────────────────────────────────────
r = c.get('/rules-editor')
check(r.status_code == 200, 'страница /rules-editor → 200', str(r.status_code))
r = c.get('/api/guild/777/rules')
check(r.status_code == 200 and r.get_json() == [], 'rules GET без файла → []', r.get_data(as_text=True)[:80])
RULES = [{'t': 'Правило 1', 'd': 'Не спамить'},
         {'t': 'Правило 2', 'd': 'Быть адекватным'},
         {'t': '', 'd': ''}]
r = c.post('/api/guild/777/rules', json=RULES)
j = r.get_json()
check(r.status_code == 200 and j.get('success') and len(j.get('rules', [])) == 2,
      'rules POST → success, пустые отброшены (2 из 3)', r.get_data(as_text=True)[:120])
r = c.get('/api/guild/777/rules')
saved = r.get_json()
check(len(saved) == 2 and saved[0]['t'] == 'Правило 1', 'rules GET после сохранения → roundtrip', str(saved)[:120])
r = c.post('/api/guild/777/rules', data='не json', content_type='application/json')
check(r.status_code == 200, 'rules POST мусором → трактован как пустой список (не 500)', f'{r.status_code}')
# мусорные URL в правилах: валидатор URL
r = c.post('/api/guild/777/rules', json=[{'t': 'x', 'd': 'якорь http://ok.example/a http://ok2.example/b'}])
check(r.status_code in (200, 400), 'rules POST с URL → 200/400 без 500', f'{r.status_code}')
# meta
r = c.get('/api/guild/777/rules/meta')
check(r.status_code == 200, 'rules/meta GET → 200', f'{r.status_code} {r.get_data(as_text=True)[:80]}')
r = c.post('/api/guild/777/rules/meta', json={'title': 'Правила'})
check(r.status_code == 200, 'rules/meta POST → 200', f'{r.status_code} {r.get_data(as_text=True)[:80]}')
# banner (чистый Pillow-рендер, без Discord)
r = c.get('/api/guild/777/rules/banner?text=Не спамить&n=1&total=2')
check(r.status_code == 200 and (r.content_type or '').startswith('image/png') and len(r.data) > 500,
      'rules/banner → PNG', f'{r.status_code} {r.content_type} {len(r.data)}b')
# publish без канала
r = c.post('/api/guild/777/rules/publish', json={'channel_id': ''})
check(r.status_code != 500, 'rules/publish без канала → аккуратный отказ', f'{r.status_code} {r.get_data(as_text=True)[:100]}')

# ── ANALYTICS: страницы и API ───────────────────────────────────────────────
r = c.get('/analytics')
check(r.status_code == 200, 'страница /analytics → 200', str(r.status_code))
for ep in ('heatmap', 'week-summary', 'member-flow', 'mod-load', 'records',
           'invite-leaders', 'voice-pulse', 'channel-drill'):
    r = c.get(f'/api/guild/777/analytics/{ep}')
    check(r.status_code == 200, f'analytics/{ep} → 200', f'{r.status_code} {r.get_data(as_text=True)[:80]}')
r = c.get('/api/guild/777/analytics.csv')
check(r.status_code == 200 and 'csv' in (r.content_type or ''), 'analytics.csv → 200 csv', f'{r.status_code} {r.content_type}')
r = c.get('/api/guild/777/analytics_full.csv')
check(r.status_code == 200 and 'csv' in (r.content_type or ''), 'analytics_full.csv → 200 csv', f'{r.status_code} {r.content_type}')

# ── USERS ───────────────────────────────────────────────────────────────────
r = c.get('/users')
check(r.status_code == 200, 'страница /users → 200', str(r.status_code))
r = c.get('/api/user/300')
j = r.get_json()
check(r.status_code == 200 and str(j.get('id')) == '300', '/api/user/300 → профиль', r.get_data(as_text=True)[:120])

# ── ПУБЛИЧНЫЕ ЗОНЫ ─────────────────────────────────────────────────────────
anon = A.app.test_client()
r = anon.get('/login')
check(r.status_code == 200, 'публичная /login → 200', str(r.status_code))
r = anon.get('/api/status-public')
j = r.get_json()
check(r.status_code == 200 and isinstance(j, dict), 'публичная /api/status-public → JSON', str(j)[:100])
r = anon.get('/этой-страницы-нет')
check(r.status_code == 404, 'неизвестный маршрут → 404', str(r.status_code))
r = anon.get('/users')
check(r.status_code in (301, 302), 'анониму /users → redirect (login)', f'{r.status_code}')
r = anon.get('/api/guild/777/analytics/heatmap')
check(r.status_code in (301, 302, 401, 403), 'анониму API → запрет', f'{r.status_code}')
r = c.get('/logout')
check(r.status_code in (200, 302), 'GET /logout → 200/302', str(r.status_code))

print(f'\n════ PAGES/PUBLIC: PASS {PASS} / FAIL {FAIL} ════')
sys.exit(1 if FAIL else 0)
