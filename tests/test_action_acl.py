# -*- coding: utf-8 -*-
"""Второй слой авторизации: ACL «Права команд» (action_acl, default-deny).

role_required пускает админа панели, но bulk-действия дополнительно
требуют явного разрешения роли владельцем (Доступ → Права команд).
Без правила — 403 даже админу; с правилом — действие проходит дальше;
чужая роль без правила — по-прежнему 403; снятие правила снова закрывает.

Запуск: python3 tests/test_action_acl.py
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
_TMP = tempfile.mkdtemp(prefix='hakumo_acl_')
os.chdir(_TMP)
# ВАЖНО: изолированная sqlite (иначе тест пишет в общую data/bot.db репо,
# и правила от прошлых прогонов «сами» появляются в следующем)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from types import SimpleNamespace as NS

os.makedirs('data', exist_ok=True)
json.dump({'400': 'curator'}, open('data/role_map.json', 'w'))

import web.app as A


def make_member(uid, role_ids=(), admin=False, mod=False):
    # Discord-пермишены нужны ВХОДУ (роль решается живьём); ACL «Права команд»
    # их умышленно игнорирует — разрешает только явное правило роли.
    perms = NS(administrator=admin, ban_members=mod, kick_members=mod,
               manage_guild=False, manage_messages=False, manage_channels=False)
    m = NS(id=uid, bot=False,
           roles=[NS(id=r, name=f'role{r}', members=[], colour=None) for r in role_ids],
           guild_permissions=perms, display_name=f'user{uid}', name=f'user{uid}',
           display_avatar=NS(url='http://avatar/'), status=None, joined_at=None, nick=None)

    async def _timeout(until, reason=''):
        m.timed_out = until is not None

    m.timeout = _timeout
    return m


GUILD_MEMBERS = {
    '100': make_member(100, role_ids=[500], admin=True),  # админ-фейк с ролью 500
    '200': make_member(200, mod=True, role_ids=[500]),    # мод-фейк, роль 500 (ACL-роль не зависит от панели-роли)
}
guild = NS(id=777, owner_id=42, name='ACLTest',
           get_member=lambda uid: GUILD_MEMBERS.get(str(uid)),
           get_channel=lambda cid: None, get_role=lambda rid: None,
           members=list(GUILD_MEMBERS.values()), roles=[], channels=[])
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()
A.bot_instance = NS(guilds=[guild], get_guild=lambda gid: guild if gid == 777 else None,
                    loop=loop, latency=0.05, get_cog=lambda n: None,
                    get_channel=lambda cid: None, get_role=lambda rid: None,
                    change_presence=lambda **k: None, description='stub', application_id=1,
                    user=NS(id=1, name='bot'))
A._resolve_guild_member = lambda g, uid: GUILD_MEMBERS.get(str(uid))
json.dump({
    '100': {'display_name': 'admin100', 'name': 'admin100', 'role': 'admin', 'password': A._hash_pw('pass-admin'), 'registered_at': 'x'},
    '200': {'display_name': 'mod200', 'name': 'mod200', 'role': 'mod', 'password': A._hash_pw('pass-mod'), 'registered_at': 'x'},
}, open('data/members.json', 'w'))

owner = A.app.test_client()
owner.post('/login', data={'username': 'owner', 'password': 'owner-pass-123'})
admin = A.app.test_client()
r = admin.post('/login', data={'username': '100', 'password': 'pass-admin'})
assert r.status_code == 302, ('login админа', r.status_code, r.get_data(as_text=True)[:200])
mod = A.app.test_client()
mod.post('/login', data={'username': '200', 'password': 'pass-mod'})

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


def bulk_ban(sess):
    return sess.post('/api/guild/777/bulk-ban', json={})


# 1. default-deny: даже админ панели без выданного правила получает 403
r = bulk_ban(admin)
j = r.get_json()
check(r.status_code == 403 and 'Нет права' in (j.get('error') or ''),
      'default-deny: bulk-ban админом без ACL-правила → 403', f'{r.status_code} {str(j)[:100]}')

# 2. владелец панели — доверенный вход, ACL его не ограничивает
r = bulk_ban(owner)
check(r.status_code != 403, 'owner → не 403 (доверенный вход)', f'{r.status_code} {r.get_data(as_text=True)[:80]}')

# 3. выдано правило ban → роль 500: админ проходит ACL-слой
r = owner.post('/api/role-permissions/777/action/set', json={'action': 'ban', 'role_ids': ['500']})
check(r.status_code == 200 and r.get_json().get('success'),
      'выдача правила ban → роль 500', r.get_data(as_text=True)[:100])
r = bulk_ban(admin)
check(r.status_code != 403, 'bulk-ban админом с ролью 500 → дальше 403 (до бизнеса)', f'{r.status_code} {r.get_data(as_text=True)[:100]}')

# 4. ACL на mod-тире: /api/temp-mod/mute с фейк-кором — мод без роли в правиле → 403 ACL
class FakeTempCog:
    _mutes = {}

    def _mutes_file(self):
        return 'data/tmp_mutes.json'

    def _save(self, what, path):
        pass

A.bot_instance = NS(**{**A.bot_instance.__dict__,
                       'get_cog': lambda n: FakeTempCog() if n == 'TempModeration' else None})
r = mod.post('/api/temp-mod/mute', json={'user_id': '100', 'duration': '30m'})
check(r.status_code == 403 and 'Нет права' in (r.get_json().get('error') or ''),
      'mute модом без ACL-правила → 403 ACL', f'{r.status_code} {r.get_data(as_text=True)[:120]}')
r = owner.post('/api/role-permissions/777/action/set', json={'action': 'mute', 'role_ids': ['500']})
check(r.status_code == 200, 'выдача правила mute → роль 500', r.get_data(as_text=True)[:80])
r = mod.post('/api/temp-mod/mute', json={'user_id': '100', 'duration': '30m'})
check(r.status_code != 403, 'mute модом с ролью 500 → дальше ACL (бизнес-слой)', f'{r.status_code} {r.get_data(as_text=True)[:120]}')

# 5. сервис-уровень: check_action согласован
from services.permission_acl import check_action
check(check_action(777, GUILD_MEMBERS['100'], 'ban') is True, 'check_action: admin с ролью 500 → True')
check(check_action(777, GUILD_MEMBERS['200'], 'ban') is True, 'check_action: mod с ролью 500 → True (ACL-роль независимо от панели-роли)')
check(check_action(777, make_member(201, mod=True), 'ban') is False, 'check_action: участник без ACL-роли → False')
check(check_action(777, None, 'ban') is True, 'check_action: member None (доверенный) → True')

# 6. снятие правила снова закрывает действие всем, кроме доверенных
r = owner.post('/api/role-permissions/777/action/set', json={'action': 'ban', 'role_ids': []})
check(r.status_code == 200, 'снятие правила', r.get_data(as_text=True)[:80])
r = bulk_ban(admin)
check(r.status_code == 403, 'после снятия правила админ снова 403', f'{r.status_code}')

print(f'\n════ ACTION ACL: PASS {PASS} / FAIL {FAIL} ════')
sys.exit(1 if FAIL else 0)
