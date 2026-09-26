# -*- coding: utf-8 -*-
"""«Доступ → Права команд» открывается мгновенно (жалоба владельца 2026-09-05:
«5 секунд примерно жду, чтобы канал и данные загрузились»).

Проверяем реальным API (/api/role-permissions):
  • повторные открытия отдаются из кэша — второй вызов почти бесплатный;
  • устаревший payload НЕ заставляет ждать: отдаётся сразу, пересборка
    уходит в фон (serve-stale-then-refresh);
  • правка прав сбрасывает кэш — данные не «застаиваются»;
  • каталог команд кэшируется отдельно (скан AST по когам — один раз).
Запуск: python3 tests/test_permissions_speed.py
"""
import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix='perm_speed_test_')
os.chdir(_TMP)
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

_src = os.path.join(ROOT, 'data')
if os.path.isdir(_src):
    for fn in os.listdir(_src):
        _s, _d = os.path.join(_src, fn), os.path.join('data', fn)
        if os.path.isdir(_s):
            shutil.copytree(_s, _d, dirs_exist_ok=True)
        else:
            shutil.copy(_s, _d)

os.environ['DEMO_MODE'] = '1'
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


import web.app as appmod  # noqa: E402
from web.routes import permissions as PM  # noqa: E402

appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def owner_session():
    with client.session_transaction() as s:
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = 'owner'
        s['selected_guild'] = '777'


print('== Скорость «Права команд» ==')

# холодный вызов (строит payload), затем горячий
owner_session()
PM._payload_cache.pop(777, None)
t0 = time.time()
r1 = client.get('/api/role-permissions/777')
cold = time.time() - t0
check(r1.status_code == 200, 'первый запрос отдаёт данные',
      f'HTTP {r1.status_code}')

owner_session()
t0 = time.time()
r2 = client.get('/api/role-permissions/777')
warm = time.time() - t0
check(r2.status_code == 200 and warm < 0.05,
      f'повторное открытие мгновенное ({warm * 1000:.1f} мс < 50 мс)',
      f'{warm * 1000:.1f} мс')

d = json.loads(r2.get_data(as_text=True))
check(d.get('success') and isinstance(d.get('roles'), list)
      and isinstance(d.get('categories'), dict) and 'acl' in d,
      'payload полный: роли, категории, ACL')

# TTL поднят: 5-секундного ожидания больше нет
check(PM._PAYLOAD_TTL >= 60 and PM._ROLE_TTL >= 120,
      f'кэш держится долго (payload {PM._PAYLOAD_TTL:.0f} с, роли {PM._ROLE_TTL:.0f} с)')

# serve-stale: устаревший payload отдаётся сразу, обновление в фоне
PM._payload_cache[777] = (time.time() - PM._PAYLOAD_TTL - 1, r2.get_data(as_text=True),
                          json.loads(json.dumps('"stale"')))
t0 = time.time()
r3 = client.get('/api/role-permissions/777')
stale_ms = (time.time() - t0) * 1000
check(r3.status_code == 200 and stale_ms < 50,
      f'устаревшие данные отдаются сразу ({stale_ms:.1f} мс), без ожидания')
deadline = time.time() + 5
while time.time() < deadline:
    with PM._perm_cache_lock:
        hit = PM._payload_cache.get(777)
    if hit and hit[0] > time.time() - 3 and hit[2] != '"stale"':
        break
    time.sleep(0.05)
check(hit is not None and hit[2] != '"stale"',
      'фоновая пересборка обновила кэш без участия страницы')

# правка прав сбрасывает кэш
with PM._perm_cache_lock:
    PM._payload_cache.pop(777, None)
r4 = client.post('/api/role-permissions/777/set', json={'command': 'report', 'role_ids': []})
check(r4.status_code == 200, 'правка прав принимается', f'HTTP {r4.status_code}')
with PM._perm_cache_lock:
    check(777 not in PM._payload_cache,
          'после правки кэш сброшен — страница получит свежее')

# каталог команд: из кэша — мгновенно
from services.permission_acl import all_categories, _CATS_CACHE  # noqa: E402
_CATS_CACHE['data'], _CATS_CACHE['ts'] = None, 0.0
t0 = time.time()
all_categories()
cold_cat = time.time() - t0
t0 = time.time()
all_categories()
warm_cat = time.time() - t0
check(warm_cat < 0.005,
      f'каталог команд из кэша ({warm_cat * 1000:.1f} мс; холодный скан {cold_cat:.2f} с)',
      f'{warm_cat * 1000:.1f} мс')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
