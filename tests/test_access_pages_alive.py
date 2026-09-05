# -*- coding: utf-8 -*-
"""Доступ → Права команд: роли грузятся, пункт меню не теряется (владелец, 2026-09-05).

1) «роли не загрежаються»: страницы «Доступа» брали роли ТОЛЬКО из живого
   бота в своём процессе. Панель отдельным процессом (или бот на
   перезапуске) = пустой список навсегда. Теперь — фолбэк на дисковый
   снимок бота (services.bot_bridge, data/bot_roles_<gid>.json).
2) «Права команд не видно»: страницы «Доступа» (/panel-access,
   /role-permissions) нельзя скрыть глазиком в «Меню панели» — а если
   запись «скрыт» уже лежит в data/panel_menu.json, она игнорируется
   (пункт возвращается сам после обновления).

Запуск: python3 tests/test_access_pages_alive.py
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(tempfile.mkdtemp(prefix='acc_alive_'))
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.abspath(os.path.join('data', 'bot.db'))
os.environ['DEMO_MODE'] = '1'
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'x'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['PANEL_PORT'] = '5098'
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== 1. Снимок ролей: мост отдаёт список без живого бота ==')
from services import bot_bridge as BB  # noqa: E402
from services import panel_menu as PM  # noqa: E402

GID = 1484574976580391004
BB.write_roles(GID, [
    type('R', (), {'id': 8001, 'name': 'Админ', 'color': None,
                   'position': 5, 'managed': False})(),
    type('R', (), {'id': 8002, 'name': 'Модератор', 'color': None,
                   'position': 3, 'managed': False})(),
])
snap = BB.read_roles(GID)
check(isinstance(snap, list) and len(snap) == 2,
      'снимок data/bot_roles_<gid>.json пишется и читается', f'→ {snap}')

print('== 2. «Права команд»: роли из снимка, когда бота в процессе нет ==')
# Демо-режим перекрывает мост, поэтому снимок проверяем на функции
# _guild_roles напрямую с bot=None и реальным gid (не демо-сервер).
from web.routes.permissions import _guild_roles  # noqa: E402
import web.app as _app  # noqa: E402

_demo_was = os.environ.get('DEMO_MODE')
os.environ['DEMO_MODE'] = ''
roles = _guild_roles(GID, None, None)
os.environ['DEMO_MODE'] = _demo_was or '1'
check(len(roles) == 2 and roles[0]['name'] == 'Админ',
      'фолбэк: без бота роли берутся из снимка моста', f'→ {[r["name"] for r in roles]}')
check(roles[0]['position'] >= roles[1]['position'],
      'роли отсортированы по позиции (сверху — старшие)')
check(all('id' in r and 'name' in r for r in roles),
      'формат ролей совместим с payload страницы')

print('== 3. «Панели и роли»: тот же фолбэк ==')
# _role_map_guild_roles читает MAIN_GUILD_ID: подставим боевой gid
import web.app as W  # noqa: E402
W.MAIN_GUILD_ID = GID
os.environ['DEMO_MODE'] = ''
W._ROLE_MAP_ROLES.update({'ts': 0.0, 'roles': None})   # сбросить TTL-кэш
rmap = W._role_map_guild_roles()
os.environ['DEMO_MODE'] = '1'
check(len(rmap) == 2 and {r['name'] for r in rmap} == {'Админ', 'Модератор'},
      '«Панели и роли» тоже подхватывает снимок моста', f'→ {[r["name"] for r in rmap]}')

print('== 4. «Права команд» нельзя скрыть из меню (глазик) ==')
check('/role-permissions' in PM._PROTECTED and '/panel-access' in PM._PROTECTED,
      'страницы «Доступа» в списке _PROTECTED', f'→ {PM._PROTECTED}')
# запись «скрыт» уже лежит в файле → _apply_layout её игнорирует
PM.save_layout(['/role-permissions', '/appeals'], {}, None)
lay = PM.layout_view()
check('/appeals' in lay['hidden_pages'] and '/role-permissions' not in lay['hidden_pages'],
      'save_layout не записывает «Доступ» в скрытые', f'→ {lay["hidden_pages"]}')
# а если запись попала в файл раньше (старые данные) — при показе игнорируется
cfg = PM._load()
cfg.setdefault('_layout', {})['hidden_pages'] = ['/role-permissions', '/logs']
PM._save(cfg)
groups = PM.panel_groups_for('owner')
acc = next((g for g in groups if g['key'] == 'access'), None)
paths = [p['path'] for g in groups for p in g['pages']]
check('/role-permissions' in paths and '/panel-access' in paths,
      'даже с мусором в файле «Доступ» виден владельцу', f'→ {paths[:8]}')
check('/logs' not in paths,
      'обычные страницы скрываются как раньше (правило не ослаблено)')

print('== 5. JS «Меню панели» защищает те же страницы ==')
tpl = open(os.path.join(ROOT, 'web', 'templates', 'panel_menu.html'),
           encoding='utf-8').read()
check('PROTECTED_PATHS' in tpl and '/role-permissions' in tpl and '/panel-access' in tpl,
      'глазик в UI знает про защищённые страницы')
check(tpl.count('PROTECTED_PATHS.indexOf') >= 2,
      'и одиночное скрытие, и «скрыть категорию» обходят «Доступ»')

print('== 6. Сквозняк: payload страницы с фолбэком ==')
import web.app as webapp  # noqa: E402
_client = webapp.app.test_client()
r = _client.get(f'/api/role-permissions/{GID}')
d = r.get_json() or {}
check(r.status_code == 200 and d.get('success'),
      'payload «Права команд» отвечает', f'→ {r.status_code}')

print()
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
