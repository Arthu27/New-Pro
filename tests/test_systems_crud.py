# -*- coding: utf-8 -*-
"""CRUD жизненных циклов: temp-mod, punish, appeals, ladder, verify, security, team-board.

Запуск: python3 tests/test_systems_crud.py
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
_TMP = tempfile.mkdtemp(prefix='hakumo_systems_')
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
        self.timed_out = False
        self.banned = False
        self.kicked = False

    async def timeout(self, until, reason=''):
        self.timed_out = until is not None

    def is_timed_out(self):
        return self.timed_out

    async def ban(self, **kw):
        self.banned = True

    async def kick(self, reason=''):
        self.kicked = True


class FakeTempCog:
    def __init__(self):
        self._mutes, self._bans, self._kicks, self._scheduled = {}, {}, {}, []
        self.saved = []

    def _mutes_file(self):
        return 'data/tmp_mutes.json'

    def _bans_file(self):
        return 'data/tmp_bans.json'

    def _kicks_file(self):
        return 'data/tmp_kicks.json'

    def _scheduled_file(self):
        return 'data/tmp_sched.json'

    def _save(self, what, path):
        self.saved.append(what)


MEMBERS = {300: FakeMember(300), 301: FakeMember(301)}


class FakeGuild:
    id = 777
    owner_id = 42
    name = 'Systems'
    roles = []
    channels = []

    def get_member(self, uid):
        return MEMBERS.get(int(uid))


    async def fetch_member(self, uid):
        return MEMBERS.get(int(uid))

    async def unban(self, user):
        return True

    async def ban(self, member, reason=''):
        member.banned = True

    members = property(lambda self: list(MEMBERS.values()))

    def get_channel(self, cid):
        return None

    def get_role(self, rid):
        return None


guild = FakeGuild()
async def _fetch_user(uid):
    return NS(id=uid, name=f'u{uid}', send=None)

loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()
_temp_cog = FakeTempCog()
A.bot_instance = NS(guilds=[guild], get_guild=lambda gid: guild if gid == 777 else None,
                    loop=loop, latency=0.05,
                    get_cog=lambda n: _temp_cog if n == 'TempModeration' else None,
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


# ── TEMP-MOD: mute ──────────────────────────────────────────────────────────
r = c.post('/api/temp-mod/mute', json={'user_id': '300', 'duration': '30мин', 'reason': 'тест'})
check(r.status_code == 200 and r.get_json().get('ok'), 'mute 300 на 30m → ok', f'{r.status_code} {r.get_data(as_text=True)[:120]}')
mute_rec = _temp_cog._mutes.get('777', {}).get('300')
check(mute_rec and abs(mute_rec['duration'] - 1800) < 5, 'запись мута в коре (duration=1800)', repr(_temp_cog._mutes))
r = c.post('/api/temp-mod/mute', json={'user_id': '300', 'duration': 'мусор'})
check(r.status_code == 400, 'mute с битым duration → 400', f'{r.status_code} {r.get_data(as_text=True)[:100]}')
r = c.post('/api/temp-mod/mute', json={'user_id': '99999', 'duration': '30мин'})
check(r.status_code == 404, 'mute неизвестного юзера → 404 «Пользователь не найден»', f'{r.status_code}')
r = c.post('/api/temp-mod/mute', json={})
check(r.status_code == 404, 'mute с пустым json → 404 (юзер не найден), не 500', f'{r.status_code}')

# ── TEMP-MOD: active ────────────────────────────────────────────────────────
r = c.get('/api/temp-mod/active')
j = r.get_json()
check(r.status_code == 200 and 'mutes' in j and 'bans' in j, 'GET /api/temp-mod/active → списки', r.get_data(as_text=True)[:120])

# ── TEMP-MOD: unmute ────────────────────────────────────────────────────────
MEMBERS[300].timed_out = True
r = c.post('/api/temp-mod/unmute', json={'user_id': '300'})
check(r.status_code == 200 and r.get_json().get('ok') and not MEMBERS[300].timed_out,
      'unmute 300 → ok, timeout снят', f'{r.status_code} {r.get_data(as_text=True)[:120]}')

# ── TEMP-MOD: ban/unban ─────────────────────────────────────────────────────
r = c.post('/api/temp-mod/ban', json={'user_id': '301', 'duration': '1d', 'reason': 'тест'})
check(r.status_code == 200 and r.get_json().get('ok') and MEMBERS[301].banned,
      'ban 301 на 1d → ok', f'{r.status_code} {r.get_data(as_text=True)[:120]}')
r = c.post('/api/temp-mod/ban', json={'user_id': '301', 'duration': 'мусор'})
check(r.status_code == 400, 'ban с битым duration → 400', f'{r.status_code}')
r = c.post('/api/temp-mod/unban', json={'user_id': '301'})
check(r.status_code == 200 and r.get_json().get('ok'),
      'unban 301 → ok', f'{r.status_code} {r.get_data(as_text=True)[:120]}')

# ── TEMP-MOD: kick + unschedule ─────────────────────────────────────────────
r = c.post('/api/temp-mod/kick', json={'user_id': '301', 'reason': 'тест'})
check(r.status_code == 200 and r.get_json().get('ok') and MEMBERS[301].kicked,
      'kick 301 без duration (дефолт 5m) → ok', f'{r.status_code} {r.get_data(as_text=True)[:120]}')
_temp_cog._scheduled.append({'id': 'e1', 'user_id': 300, 'action': 'unmute'})
r = c.post('/api/temp-mod/unschedule', json={'id': 'e1'})
check(r.status_code == 200 and r.get_json().get('ok') and not _temp_cog._scheduled,
      'unschedule e1 → ok, запись удалена', f'{r.status_code} {r.get_data(as_text=True)[:120]}')

# ── PUNISH ──────────────────────────────────────────────────────────────────
r = c.post('/api/guild/777/punish', json={'action': 'нет-такого'})
check(r.status_code == 404, 'punish без кора Moderation → 404 «Модуль не загружен»', f'{r.status_code} {r.get_data(as_text=True)[:100]}')
r = c.get('/api/guild/777/punish/options')
check(r.status_code == 200 and r.get_json().get('success') is not None,
      'punish/options → 200', f'{r.status_code} {r.get_data(as_text=True)[:100]}')

# ── APPEALS ─────────────────────────────────────────────────────────────────
r = c.get('/appeals')
check(r.status_code == 200, 'страница /appeals → 200', str(r.status_code))
r = c.get('/api/guild/777/appeals/overview')
j = r.get_json()
check(r.status_code == 200 and j.get('success') and 'stats' in j, 'appeals/overview → success+stats', r.get_data(as_text=True)[:120])
r = c.get('/api/guild/777/appeals/history')
check(r.status_code == 200 and r.get_json().get('success'), 'appeals/history → success', r.get_data(as_text=True)[:120])
r = c.get('/api/guild/777/appeals/export.csv')
check(r.status_code == 200 and 'csv' in (r.content_type or ''), 'appeals/export.csv → 200 csv', f'{r.status_code} {r.content_type}')
r = c.post('/api/guild/777/appeals/claim', json={'id': 'нет-такого'})
check(r.status_code in (200, 400, 404) and r.status_code != 500, 'appeals/claim несуществующего → аккуратный отказ', f'{r.status_code} {r.get_data(as_text=True)[:120]}')
r = c.post('/api/guild/777/appeals/resolve', json={'id': 'нет-такого', 'decision': 'approve'})
check(r.status_code in (200, 400, 404) and r.status_code != 500, 'appeals/resolve несуществующего → аккуратный отказ', f'{r.status_code} {r.get_data(as_text=True)[:120]}')

# ── LADDER ──────────────────────────────────────────────────────────────────
r = c.get('/ladder')
check(r.status_code == 200, 'страница /ladder → 200', str(r.status_code))
r = c.get('/api/guild/777/ladder/view')
j = r.get_json()
check(r.status_code == 200 and j.get('success') and 'steps' in json.dumps(j), 'ladder/view → success', r.get_data(as_text=True)[:120])
r = c.post('/api/guild/777/ladder/add', json={'count': 2, 'action': 'mute', 'duration': 30, 'unit': 'minute'})
check(r.status_code == 200 and r.get_json().get('success'), 'ladder/add (timeout 30m) → success', f'{r.status_code} {r.get_data(as_text=True)[:120]}')
r = c.post('/api/guild/777/ladder/add', json={'count': 2, 'action': 'нет-такого'})
check(r.status_code in (200, 400) and not r.get_json().get('success'), 'ladder/add с мусорным action → отказ без 500', f'{r.status_code} {r.get_data(as_text=True)[:120]}')
r = c.get('/api/guild/777/ladder/simulate?user=300')
check(r.status_code == 200, 'ladder/simulate → 200', f'{r.status_code} {r.get_data(as_text=True)[:100]}')
r = c.get('/api/guild/777/ladder/export.csv')
check(r.status_code == 200 and 'csv' in (r.content_type or ''), 'ladder/export.csv → 200 csv', f'{r.status_code} {r.content_type}')
r = c.post('/api/guild/777/ladder/remove', json={'count': 2})
check(r.status_code == 200 and r.get_json().get('success'), 'ladder/remove существующей ступени → success', f'{r.status_code} {r.get_data(as_text=True)[:120]}')

# ── VERIFY ──────────────────────────────────────────────────────────────────
r = c.get('/verify')
check(r.status_code == 200, 'страница /verify → 200', str(r.status_code))
r = c.get('/api/guild/777/verify/config')
j = r.get_json()
check(r.status_code == 200 and j.get('success') and 'config' in j and 'pending' in j, 'verify/config GET → success+config+pending', r.get_data(as_text=True)[:120])
r = c.post('/api/guild/777/verify/publish', json={})
check(r.status_code == 400 and not r.get_json().get('success'),
      'verify/publish без канала → 400 «Канал верификации не задан»', f'{r.status_code} {r.get_data(as_text=True)[:120]}')

# ── SECURITY-CENTER ─────────────────────────────────────────────────────────
r = c.get('/security')
check(r.status_code == 200, 'страница /security → 200', str(r.status_code))
r = c.post('/api/guild/777/security-center/scan', json={})
check(r.status_code == 400, 'scan без текста → 400 «Пустой текст»', f'{r.status_code}')
r = c.post('/api/guild/777/security-center/scan', json={'text': 'Куплю аккаунты дешево, пишите в лс http://spam.example'})
j = r.get_json()
check(r.status_code == 200 and j.get('success'), 'scan со спам-текстом → success', f'{r.status_code} {r.get_data(as_text=True)[:120]}')
r = c.get('/api/guild/777/security-center/overview')
check(r.status_code == 200 and r.get_json().get('success'), 'security/overview → success', r.get_data(as_text=True)[:120])
r = c.get('/api/guild/777/security-center/export.csv')
check(r.status_code == 200 and 'csv' in (r.content_type or ''), 'security/export.csv → 200 csv', f'{r.status_code} {r.content_type}')

# ── TEAM-BOARD ──────────────────────────────────────────────────────────────
r = c.get('/api/team-board')
check(r.status_code == 200, 'GET /api/team-board → 200', f'{r.status_code} {r.get_data(as_text=True)[:100]}')
r = c.post('/api/team-board/reorder', json={'order': []})
check(r.status_code != 500, 'team-board/reorder с пустым order → не 500', f'{r.status_code} {r.get_data(as_text=True)[:100]}')
r = c.patch('/api/team-board/999999', json={'status': 'done'})
check(r.status_code in (200, 400, 404), 'team-board PATCH несуществующей → аккуратный отказ', f'{r.status_code} {r.get_data(as_text=True)[:100]}')

print(f'\n════ SYSTEMS CRUD: PASS {PASS} / FAIL {FAIL} ════')
sys.exit(1 if FAIL else 0)
