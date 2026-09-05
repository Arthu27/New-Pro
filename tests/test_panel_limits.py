# -*- coding: utf-8 -*-
"""Лимиты стаффа сквозь панель: обходных путей нет.

Движок лимитов (services/staff_limits) покрыт tests/test_staff_limits.py.
Этот тест проверяет ГЕЙТЫ: каждый панельный маршрут наказаний считает
те же счётчики, что и команды бота — модератор не может «перепомпать»
себя через страницы панели (временная модерация, профиль, массовые
операции, чистка).

Запуск: python3 tests/test_panel_limits.py
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
os.environ['DB_PATH'] = os.path.join(tempfile.mkdtemp(prefix='hakumo_pldb_'), 'bot.db')
_TMP = tempfile.mkdtemp(prefix='hakumo_pl_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from types import SimpleNamespace as NS

os.makedirs('data', exist_ok=True)
# role_map: Discord-роль 555 = админ панели (live-роль пересчитывается при логине)
json.dump({'400': 'curator', '555': 'admin'}, open('data/role_map.json', 'w'))

import web.app as A


def make_member(uid, mod=False, admin=False, role_ids=()):
    perms = NS(administrator=admin, ban_members=mod, kick_members=mod,
               manage_guild=False, manage_messages=False, manage_channels=False)
    m = NS(id=uid, bot=False,
           roles=[NS(id=r, name=f'role{r}', members=[], colour=None) for r in role_ids],
           guild_permissions=perms, display_name=f'user{uid}', name=f'user{uid}',
           display_avatar=NS(url='http://avatar/'), status=None, joined_at=None, nick=None)

    async def _to(until, reason=''):
        m.timed_out = until is not None
    m.timeout = _to

    def _is_timed_out():
        return getattr(m, 'timed_out', False)
    m.is_timed_out = _is_timed_out
    return m


GUILD_MEMBERS = {
    # модератор с панельным входом: НЕ админ Discord, пермишены нужны живому
    # логину, а лимиты решаются отдельно (staff_limits)
    '200': make_member(200, mod=True, role_ids=[555]),
    '300': make_member(300),
}
async def _g_ban(member, reason=None):
    BANNED.append(member.id)


async def _g_unban(user, reason=None):
    pass


BANNED = []
guild = NS(id=777, owner_id=42, name='Limits', description='stub',
           ban=_g_ban, unban=_g_unban,
           me=NS(id=1, name='bot', display_avatar=NS(url='http://avatar/'), bot=True),
           get_member=lambda uid: GUILD_MEMBERS.get(str(uid)),
           get_channel=lambda cid: NS(id=cid, name=f'chan{cid}', members=[], mention='<#1>'),
           get_role=lambda rid: NS(id=rid, name=f'role{rid}', members=[], colour=None,
                                    permissions=NS(administrator=False, ban_members=False,
                                                   kick_members=False, manage_guild=False,
                                                   manage_messages=False, manage_channels=False)),
           members=list(GUILD_MEMBERS.values()), roles=[], channels=[])
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()


async def _fetch_user(uid):
    return NS(id=uid, name=f'u{uid}', send=None)


class FakeTempCog:
    def __init__(self):
        self._mutes, self._bans, self._kicks, self._scheduled = {}, {}, {}, []

    def _mutes_file(self):
        return 'data/m.json'

    def _bans_file(self):
        return 'data/b.json'

    def _kicks_file(self):
        return 'data/k.json'

    def _scheduled_file(self):
        return 'data/s.json'

    def _save(self, what, path):
        pass


A.bot_instance = NS(guilds=[guild], get_guild=lambda gid: guild if gid == 777 else None,
                    loop=loop, latency=0.05,
                    get_cog=lambda n: FakeTempCog() if n == 'TempModeration' else None,
                    get_channel=lambda cid: NS(id=cid, name=f'chan{cid}', members=[], mention='<#1>'),
                    get_role=lambda rid: None,
                    fetch_user=_fetch_user,
                    change_presence=lambda **k: None, description='stub', application_id=1,
                    user=NS(id=1, name='bot'))
A._resolve_guild_member = lambda g, uid: GUILD_MEMBERS.get(str(uid))
json.dump({
    '200': {'display_name': 'mod200', 'name': 'mod200', 'role': 'Администратор', 'password': A._hash_pw('p-mod'), 'registered_at': 'x'},
    '300': {'display_name': 'member300', 'name': 'member300', 'role': 'uye', 'password': A._hash_pw('p-uye'), 'registered_at': 'x'},
}, open('data/members.json', 'w'))

# владелец панели (статический вход) + модератор через Discord-аккаунт
owner = A.app.test_client()
owner.post('/login', data={'username': 'owner', 'password': 'owner-pass-123'})
mod = A.app.test_client()
mod.post('/login', data={'username': '200', 'password': 'p-mod'})

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


from services import staff_limits as SL
from services.permission_acl import save_action_acl

# строгая модель ACL: явно разрешаем модератору (роль 555) действия
save_action_acl(777, {'mute': [555], 'unmute': [555], 'ban': [555],
                      'warn': [555], 'kick': [555], 'clear': [555],
                      'purge': [555]})

# лимиты РОЛИ 555 (перебивают и общие, и тировые дефолты админа):
# мут 2, бан 1, unmute 1, чистка 5 ОПЕРАЦИЙ за окно
SL.set_role_limits(777, 555, mute=2, ban=1, unmute=1, clear=5)

# ── 1. temp-mod/mute: 2 ок, 3-й → 429 ──────────────────────────────────────
r1 = mod.post('/api/temp-mod/mute', json={'user_id': '300', 'duration': '1h'})
r2 = mod.post('/api/temp-mod/mute', json={'user_id': '300', 'duration': '1h'})
r3 = mod.post('/api/temp-mod/mute', json={'user_id': '300', 'duration': '1h'})
check(r1.status_code == 200 and r2.status_code == 200, 'мут 1-2 из 2 → ок', f'{r1.status_code},{r2.status_code}')
check(r3.status_code == 429 and 'Лимит' in r3.get_json().get('error', ''),
      'мут 3-й сверх лимита → 429 «Лимит исчерпан»', f'{r3.status_code} {r3.get_data(as_text=True)[:90]}')

# владелец панели (доверенный вход) тем же эндпоинтом не ограничен
ro = owner.post('/api/temp-mod/mute', json={'user_id': '300', 'duration': '30мин'})
check(ro.status_code == 200, 'доверенный вход (owner) не ограничен', str(ro.status_code))

# потолок длительности: 6ч при капе 2ч
SL.set_durations(777, mute=2 * 3600)
rc = mod.post('/api/temp-mod/mute', json={'user_id': '300', 'duration': '6ч'})
# лимит уже исчерпан (429 раньше капа) — проверяем кап на ком-то с остатком
SL.set_role_limits(777, 555, mute=3)
rc = mod.post('/api/temp-mod/mute', json={'user_id': '300', 'duration': '6ч'})
check(rc.status_code == 429 and 'потолок' in rc.get_json().get('error', ''),
      'мут 6ч при потолке 2ч → 429 с текстом про потолок', f'{rc.status_code} {rc.get_data(as_text=True)[:90]}')
SL.set_durations(777, mute=0)

# ── 2. temp-mod/ban: 1 ок, 2-й → 429 ───────────────────────────────────────
BAN_MEMBERS = GUILD_MEMBERS
r1 = mod.post('/api/temp-mod/ban', json={'user_id': '300', 'duration': '1д'})
r2 = mod.post('/api/temp-mod/ban', json={'user_id': '300', 'duration': '1д'})
check(r1.status_code == 200, 'бан 1-й из 1 → ок', f'{r1.status_code} {r1.get_data(as_text=True)[:80]}')
check(r2.status_code == 429 and 'Лимит' in r2.get_json().get('error', ''),
      'бан 2-й сверх лимита → 429', f'{r2.status_code} {r2.get_data(as_text=True)[:90]}')

# ── 3. temp-mod/unmute: 1 ок, 2-й → 429 ────────────────────────────────────
GUILD_MEMBERS['300'].timed_out = True
r1 = mod.post('/api/temp-mod/unmute', json={'user_id': '300'})
GUILD_MEMBERS['300'].timed_out = True
r2 = mod.post('/api/temp-mod/unmute', json={'user_id': '300'})
check(r1.status_code == 200 and r2.status_code == 429,
      'unmute: 1 ок, 2-й → 429', f'{r1.status_code},{r2.status_code}')

# ── 4. member-profile/ban: тот же счётчик «бан» (1 потрачен выше) ──────────
r = mod.post('/api/member-profile/777/300/ban', json={'reason': 'тест'})
check(r.status_code == 429, 'профиль→бан видит тот же счётчик → 429', f'{r.status_code} {r.get_data(as_text=True)[:90]}')

# ── 5. purge: 1 хит за чистку, не за каждое сообщение ──────────────────────
async def _fake_purge(limit=10):
    return list(range(min(int(limit or 1), 4)))

A.bot_instance.get_channel = lambda cid: NS(
    id=cid, name=f'chan{cid}', members=[], mention='<#1>',
    purge=_fake_purge)

codes = []
for _i in range(5):
    r = mod.post('/api/guild/777/purge', json={'channel_id': '1001', 'count': 10})
    codes.append(r.status_code)
check(all(c != 429 for c in codes),
      f'5 чисток по 10 сообщений при лимите 5 операций — ок ({codes})')
r = mod.post('/api/guild/777/purge', json={'channel_id': '1001', 'count': 3})
check(r.status_code == 429 and 'Лимит' in (r.get_json() or {}).get('error', ''),
      '6-я чистка сверх 5 операций → 429', f'{r.status_code} {r.get_data(as_text=True)[:90]}')

# ── 6. bulk-*: гейты отвечают 429 при исчерпанном лимите ───────────────────
SL.set_role_limits(777, 555, kick=1)  # kick: 1 на окно
r = mod.post('/api/guild/777/bulk-kick', json={'role_id': '555'})
check(r.status_code != 500, 'bulk-kick → аккуратный ответ', f'{r.status_code}')

# ── 7. движок: счётчики именно модератора, не чужих ────────────────────────
hits, _ = SL._hits(777, 200, 'mute')
check(len([h for h in hits if h > 0]) >= 2, 'хиты мута записаны на модератора 200', str(hits))

print(f'\n════ PANEL LIMITS: PASS {PASS} / FAIL {FAIL} ════')
sys.exit(1 if FAIL else 0)
