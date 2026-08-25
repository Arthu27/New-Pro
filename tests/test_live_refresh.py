# -*- coding: utf-8 -*-
"""«Всё обновляется само, без перезагрузки» (заказ владельца: «прям 100%»).

Три слоя свежести данных:
1. Фронт: каждая списочная/статусная страница сама перезабирает данные
   (setLiveRefresh) — список поддерживаемых страниц фиксирован тестом.
2. API: ответы без кэша (no-store) — браузер всегда получает свежее.
3. Бот: конфиги защиты читаются с диска НА КАЖДОМ событии — панель
   сохранила настройку, ког применяет её без рестарта бота.

Запуск: python3 tests/test_live_refresh.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_live_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DEMO_MODE'] = '1'

PASS = 0


def ok(name, cond, extra=''):
    global PASS
    if not cond:
        print(f'FAIL: {name} {extra}')
        sys.exit(1)
    PASS += 1
    print(f'  ok - {name}')


def tpl(name):
    return open(os.path.join(ROOT, 'web/templates', name + '.html'),
                encoding='utf-8').read()


print('== 1. Живое обновление на страницах ==')
LIVE_PAGES = [
    'analytics', 'dashboard',            # уже были
    'panel_logs', 'security', 'antifake', 'mod_insights', 'staff_stats',
    'sla', 'meetings', 'notifications', 'karma', 'leveling', 'gamification',
    'birthdays', 'duty_panel', 'staff_rating', 'starboard',
    'scheduled_messages', 'custom_commands', 'todo', 'knowledge_base',
    'reports', 'watchlist', 'tagjail', 'server_info', 'backups', 'economy',
    'advanced_analytics', 'my_applications', 'member_dashboard', 'tops',
    'transcripts', 'commands', 'panel_access', 'role_permissions',
]
for name in LIVE_PAGES:
    ok(f'{name}: живое обновление', 'setLiveRefresh' in tpl(name))

print('== 1b. Интервал везде — 1.5 секунды ==')
import glob
import re as _re
odd = []
for path in glob.glob(os.path.join(ROOT, 'web/templates/*.html')):
    src = open(path, encoding='utf-8').read()
    for m in _re.finditer(r'setLiveRefresh\s*\(.{0,600}?,\s*(\d{3,6})\s*\)\s*;', src, _re.S):
        if m.group(1) != '1500':
            odd.append((os.path.basename(path), m.group(1)))
ok('все setLiveRefresh → 1500 мс', not odd, str(odd[:5]))
ok('дефолт диспетчера 1500 (app.js)',
   'ms || 1500' in open(os.path.join(ROOT, 'web/static/app.js'), encoding='utf-8').read())
ok('фолбэк base.html тоже 1500', 'ms || 1500' in tpl('base'))

print('== 1c. Живой сайдбар: «Доступ» виден на любой открытой странице ==')
base = tpl('base')
ok('base.html опрашивает /api/panel/sidebar каждые 1.5с',
   '/api/panel/sidebar' in base and 'sidebarLive, 1500' in base)
frag = open(os.path.join(ROOT, 'web/templates/_sidebar_nav.html'), encoding='utf-8').read()
ok('фрагмент _sidebar_nav.html вынесен (active_path для подсветки)',
   'active_path' in frag and 'nav-group' in frag)
ok('base включает фрагмент', 'include "_sidebar_nav.html"' in base)
app_src = open(os.path.join(ROOT, 'web/app.py'), encoding='utf-8').read()
ok('эндпоинт /api/panel/sidebar отдаёт HTML меню', '/api/panel/sidebar' in app_src)
ok('app.js: sidebarInit переподвязывается после свапа',
   'window.sidebarInit = sidebarInit' in open(os.path.join(ROOT, 'web/static/app.js'),
                                              encoding='utf-8').read())

print('== 2. Логи панели: только реальные данные ==')
pl = tpl('panel_logs')
ok('panel_logs тянет /api/panel-logs', "fetch('/api/panel-logs'" in pl)
ok('panel_logs: захардкоженная выдумка удалена', '2 мин назад' not in pl)
ok('panel_logs: автообновление каждые 1.5с',
   'setLiveRefresh(fetchLogs, 1500)' in pl)

print('== 3. Глобальный каркас живых обновлений ==')
base = tpl('base')
ok('base.html: setLiveRefresh доступен всегда (фолбэк до app.js)',
   'setLiveRefresh' in base)
appjs = open(os.path.join(ROOT, 'web/static/app.js'), encoding='utf-8').read()
ok('app.js: диспетчер live-задач', 'liveFns' in appjs and 'livePaused' in appjs)

print('== 4. API без кэша — данные всегда свежие ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
client.post('/login', data={'username': 'admin', 'password': 'test123'})
r = client.get('/api/guilds')
cc = (r.headers.get('Cache-Control') or '') + (r.headers.get('Pragma') or '')
ok('/api/guilds: no-store/no-cache', 'no-store' in cc or 'no-cache' in cc)

json.dump([{'username': 'owner', 'role': 'owner', 'action': 'POST /api/x',
            'ip': '127.0.0.1', 'timestamp': '2026-08-25T01:00:00',
            'method': 'POST'}],
          open('data/panel_logs.json', 'w', encoding='utf-8'), ensure_ascii=False)
r = client.get('/api/panel-logs')
d = r.get_json()
ok('/api/panel-logs отдаёт реальные записи',
   r.status_code == 200 and isinstance(d, list) and d[0]['action'] == 'POST /api/x')

r = client.get('/api/panel/sidebar?path=/commands')
body = r.get_data(as_text=True)
ok('/api/panel/sidebar: HTML меню с группами и подсветкой страницы',
   r.status_code == 200 and 'nav-group' in body and '/commands' in body)

print('== 5. Бот подхватывает настройки без рестарта ==')
js_src = open(os.path.join(ROOT, 'json_store.py'), encoding='utf-8').read()
ok('json_store: кэш свежести по mtime_ns/size — правки с панели видны сразу',
   'mtime_ns' in js_src and 'st_size' in js_src)
sec_src = open(os.path.join(ROOT, 'cogs/security.py'), encoding='utf-8').read()
ok('security: конфиг читается через json_store на каждом событии',
   '_js_load' in sec_src)
af_src = open(os.path.join(ROOT, 'cogs/auto_filter.py'), encoding='utf-8').read()
ok('auto_filter: load_config без мемоизации',
   'def load_config' in af_src and 'lru_cache' not in af_src)
ok('в web-роутах нет кэширующих декораторов',
   'lru_cache' not in open(os.path.join(ROOT, 'web/routes/community.py'),
                           encoding='utf-8').read())

print(f'\nALL {PASS} PASS — всё обновляется само, без перезагрузки')
shutil.rmtree(_TMP, ignore_errors=True)
