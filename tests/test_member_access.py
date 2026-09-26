# -*- coding: utf-8 -*-
"""Доступ к составу сервера по ролям панели.

Регрессия, которую нашли разбором раздела «Участники»:
страница /users закрыта ролью admin, а вот API состава
/api/guild/<gid>/members был закрыт ТОЛЬКО авторизацией. То есть любой
залогиненный в панели — включая низшую роль uye — забирал весь список
участников (ники, роли, даты входа, статусы) запросом к API в обход
страницы. Здесь фиксируем порог, чтобы дыра не вернулась.

Порог mod, а не admin: этот же список читают /member-notes (mod) и
/chat (owner), поэтому admin сломал бы заметки о участниках.

Запуск:  .venv/bin/python tests/test_member_access.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DEMO_MODE', '1')
# Без MAIN_GUILD_ID /api/members отдаёт 503 «Сервер не выбран» ещё до проверки
# роли, и тест проверял бы не то, что нужно.
os.environ.setdefault('MAIN_GUILD_ID', '793336829280780331')

from web.app import app, ROLES  # noqa: E402

GID = '793336829280780331'
PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


def client_as(role):
    c = app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['username'] = f'probe-{role}'
        s['role'] = role
        s['discord_id'] = '424242'
        s['selected_guild'] = GID
    return c


print('== 0. лестница ролей ==')
check(ROLES['uye'] < ROLES['mod'] < ROLES['curator'] < ROLES['admin'] < ROLES['owner'],
      'uye < mod < curator < admin < owner')

print('== 1. низшая роль не видит состав ==')
c = client_as('uye')
check(c.get('/users').status_code == 302, 'страница /users для uye — редирект')
r = c.get(f'/api/guild/{GID}/members?limit=5')
check(r.status_code == 403,
      f'API состава для uye -> {r.status_code} (было 200 со всем списком)')
body = r.get_json() or {}
check('роль' in str(body.get('error', '')).lower() or 'Нужна' in str(body.get('error', '')),
      f"403 объясняет причину: {str(body.get('error',''))[:50]}")

print('== 2. обходной /api/members закрыт тем же порогом ==')
_r = client_as('uye').get('/api/members?limit=3')
check(_r.status_code == 403,
      f'/api/members для uye -> {_r.status_code} (ждём 403; он делегирует в api_guild_members)')

print('== 3. модератор и выше — доступ есть ==')
for role in ('mod', 'curator', 'admin', 'owner'):
    r = client_as(role).get(f'/api/guild/{GID}/members?limit=5')
    check(r.status_code == 200,
          f'{role} получает состав -> {r.status_code} (порог mod не сломал заметки)')

print('== 4. страница заметок про участника остаётся модераторской ==')
check(client_as('mod').get('/member-notes').status_code == 200,
      '/member-notes открывается у mod — порог API его не сломал')
check(client_as('uye').get('/member-notes').status_code == 302,
      '/member-notes для uye — редирект')

print('== 5. добавление участника в панель — только admin ==')
for role, want in (('uye', 403), ('mod', 403), ('curator', 403), ('admin', 200)):
    got = client_as(role).post('/api/add-member',
                               json={'discord_id': '1', 'password': 'x'}).status_code
    check(got == want, f'/api/add-member для {role} -> {got} (ждём {want})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
