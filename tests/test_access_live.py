# -*- coding: utf-8 -*-
"""Живая проверка «Доступа» в панели: все эндпоинты категории в трёх ролях
(owner / admin / mod) + создатель сервера автоматически = владелец панели.

Запуск: python3 tests/test_access_live.py
"""
import os
import sys
import tempfile

os.environ['DEMO_MODE'] = '1'
os.environ.setdefault('PANEL_PORT', '5099')
os.environ.setdefault('PANEL_USER', 'owner')
os.environ.setdefault('PANEL_PASSWORD', 'demo-pass')

_TMP = tempfile.mkdtemp(prefix='hakumo_access_live_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = 0
FAIL = 0


def check(cond, label, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


def client_with(role):
    """Тест-клиент с готовой сессией нужной роли."""
    import web.app as A
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess['logged_in'] = True
        sess['username'] = f'test-{role}'
        sess['role'] = role
        sess['discord_id'] = '424242'
    return c


GID = '777'

print('== Владелец: разделы «Доступ» целиком ==')
own = client_with('owner')

r = own.get('/role-permissions')
check(r.status_code == 200 and 'Права команд'.lower() in r.get_data(as_text=True).lower() or r.status_code == 200,
      'страница «Права команд» открывается (200)')

r = own.get(f'/api/role-permissions/{GID}')
d = r.get_json(silent=True) or {}
check(r.status_code == 200 and d.get('success', True) is not False,
      'GET список прав отдаётся')

cases = [
    ('category/assign', {'category': 'Модерация', 'role_ids': ['111']}, 'категория выдачи ролям разом'),
    ('category/everyone', {'category': 'Модерация'}, 'категория «для всех» снимается'),
    ('preset', {'preset': 'all', 'role_ids': ['111']}, 'пресет «Все команды»'),
    ('set', {'command': 'warn', 'role_ids': ['111']}, 'одна команда — дать ролям'),
    ('clear', {}, 'сброс ограничений команд'),
    ('action/set', {'action': 'ban', 'role_ids': ['111']}, 'действие — дать ролям'),
    ('actions/clear', {}, 'сброс ограничений действий'),
]
for ep, body, label in cases:
    r = own.post(f'/api/role-permissions/{GID}/{ep}', json=body)
    d = r.get_json(silent=True) or {}
    check(r.status_code == 200 and d.get('success') is True,
          f'POST /{ep} — {label}', f'→ {r.status_code} {d}')

r = own.get('/panel-access')
check(r.status_code == 200, 'страница «Панели и роли» открывается')
r = own.post('/api/panel/visibility', json={'pages': []})
check(r.status_code == 200, 'POST видимость панели')

print('== Владелец: «Команды» и массовые тумблеры ==')
r = own.get('/commands')
html = r.get_data(as_text=True)
check(r.status_code == 200 and 'Вкл показанные' in html and 'Выкл показанные' in html,
      'страница «Команды» с кнопками «Вкл/Выкл показанные»')
r = own.post('/api/commands/switch-bulk', json={'names': ['warn'], 'disabled': False})
d = r.get_json(silent=True) or {}
check(r.status_code == 200 and d.get('success') is True, 'bulk-тумблер команд')

print('== Админ: понятные отказы вместо молчанки ==')
adm = client_with('admin')
r = adm.get('/role-permissions')
check(r.status_code == 302 and (r.headers.get('Location') or '').startswith('/?denied='),
      '«Права команд» для админа → главная с ?denied=', f'→ {r.status_code} {r.headers.get("Location")}')
r = adm.post(f'/api/role-permissions/{GID}/set', json={'command': 'warn', 'role_ids': ['1']})
d = r.get_json(silent=True) or {}
check(r.status_code == 403 and 'Владелец' in (d.get('error') or ''),
      'API для админа — 403 с подсказкой про роль «Владелец»', f'→ {r.status_code} {d}')
r = adm.get('/commands')
check(r.status_code == 200 and 'Вкл показанные' in r.get_data(as_text=True),
      '«Команды» админу можно, тумблеры видны')
r = adm.post('/api/commands/switch', json={'name': 'warn', 'disabled': False})
check(r.status_code == 200, 'админ может переключать команды')

print('== Модератор: только просмотр ==')
mod = client_with('mod')
r = mod.get('/commands')
check(r.status_code == 200 and 'Вкл показанные' not in r.get_data(as_text=True),
      '«Команды» модеру — просмотр без кнопок массового выключения')
# бот офлайн: роль в сессии НЕ понижается до «Участника»
with mod.session_transaction() as sess:
    check(sess.get('role') in ('mod', 'admin', 'owner'),
          'бот офлайн — роль админа/модера не срезана до участника',
          f"→ {sess.get('role')}")
r = mod.post('/api/commands/switch-bulk', json={'names': ['warn'], 'disabled': True})
d = r.get_json(silent=True) or {}
check(r.status_code == 403 and 'role' in str(d.get('error', '')).lower() or 'роль' in str(d.get('error', '')),
      'bulk модеру запрещён с объяснением', f'→ {r.status_code} {d}')

print('== Создатель сервера = владелец панели (функционально) ==')
import web.app as A
from types import SimpleNamespace as NS

class _FakeMember(NS):
    pass

me_owner = _FakeMember(id=42, roles=[], guild_permissions=NS(administrator=True),
                       top_role=NS(position=1, name='Owner'))
me_admin = _FakeMember(id=43, roles=[], guild_permissions=NS(administrator=True),
                       top_role=NS(position=1, name='Admins'))
guild = NS(id=777, owner_id=42, me=me_admin, get_member=lambda uid: me_owner if uid == 42 else me_admin)
bot = NS(guilds=[guild], get_guild=lambda gid: guild if gid == 777 else None)
A.bot_instance = bot
A.MAIN_GUILD_ID = '777'
_orig_resolve = A._resolve_guild_member
A._resolve_guild_member = lambda g, uid: g.get_member(uid)

check(A._get_role_from_discord('42') == 'owner',
      'создатель сервера → роль owner',
      f"→ {A._get_role_from_discord('42')}")
check(A._get_role_from_discord('43') == 'admin',
      'просто админ → роль admin (не owner)',
      f"→ {A._get_role_from_discord('43')}")

A._resolve_guild_member = _orig_resolve

print('== Бот: предпроверка прав (preflight) ==')
src = open(os.path.join(os.path.dirname(_TMP), *[]) or '', encoding='utf-8') if False else None
mod_src = open(os.path.join(sys.path[0], 'cogs', 'moderation.py'), encoding='utf-8').read()
check('async def preflight_reason' in mod_src and 'У бота не хватит прав' in mod_src,
      'preflight до исполнения: бот заранее знает, хватит ли прав')
check('"Не хватило прав у бота"' in mod_src and 'error_embed (await _forbidden_reason' in mod_src,
      'Forbidden: причина в тексте, короткий титул (порядок аргументов верный)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
