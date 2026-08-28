# -*- coding: utf-8 -*-
"""Discord Embedded App (Activity): музыкальная панель в войсе.

Проверяем:
1. Статика активности (index.html/app.js/style.css/вендор SDK) отдаётся.
2. Заголовки: на странице активности X-Frame-Options снят, frame-ancestors
   разрешает Discord; на обычных страницах правила прежние (регрессия).
3. Демо-режим: config/token/state/control отвечают без реального Discord.
4. Без валидного токена (не демо) — 401.

Запуск: python3 tests/test_music_activity.py
"""
import json
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.makedirs('data', exist_ok=True)

import config
config.Config.DB_PATH = os.path.abspath('data/bot.db')

os.environ['DEMO_MODE'] = '1'
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
os.environ['MAIN_GUILD_ID'] = '777'

import web.app as appmod  # noqa: E402
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()

PASS = 0; FAIL = 0
def check(ok, msg):
    global PASS, FAIL
    if ok: PASS += 1; print(f'  PASS: {msg}')
    else: FAIL += 1; print(f'  FAIL: {msg}')

print('== 1. Статика активности ==')
for path in ('/static/activity/music/index.html', '/static/activity/music/app.js',
             '/static/activity/music/style.css', '/static/activity/vendor/sdk.global.js'):
    r = client.get(path)
    check(r.status_code == 200, f'{path} → {r.status_code}')

print('== 2. Заголовки встраивания ==')
r = client.get('/static/activity/music/index.html')
check('X-Frame-Options' not in r.headers, 'страница активности: X-Frame-Options снят')
csp = r.headers.get('Content-Security-Policy', '')
check('discord.com' in csp and 'frame-ancestors' in csp,
      'страница активности: frame-ancestors разрешает discord.com')
r2 = client.get('/welcome')
check(r2.headers.get('X-Frame-Options') == 'SAMEORIGIN',
      'обычная страница: X-Frame-Options SAMEORIGIN не тронут (регрессия)')
check("frame-ancestors 'self'" in r2.headers.get('Content-Security-Policy', ''),
      'обычная страница: CSP прежний')

print('== 3. Демо: config/token/state/control ==')
r = client.get('/api/activity/music/config')
cfg = r.get_json()
check(r.status_code == 200 and cfg.get('success') and cfg.get('demo') is True,
      'config отдаётся (demo=True)')

r = client.post('/api/activity/music/token', json={'code': 'x'})
check(r.status_code == 200 and r.get_json().get('access_token') == 'demo',
      'token в демо → access_token=demo')

r = client.get('/api/activity/music/state?guild_id=777',
               headers={'Authorization': 'Bearer demo'})
d = r.get_json()
check(r.status_code == 200 and d.get('success') and d.get('total') == 3,
      'state в демо → живой плейлист (3 трека)')

r = client.post('/api/activity/music/control',
                json={'action': 'pause', 'guild_id': '777'},
                headers={'Authorization': 'Bearer demo'})
d = r.get_json()
check(r.status_code == 200 and d.get('success'), 'control в демо → success')

print('== 4. Без токена (не демо) — 401 ==')
os.environ['DEMO_MODE'] = '0'
import web.app as appmod2  # noqa: E402
# демо-флаг читается из окружения на каждый запрос (_demo_mode())
r = client.get('/api/activity/music/state?guild_id=777')
check(r.status_code == 401, 'state без токена → 401')
r = client.get('/api/activity/music/state?guild_id=777',
               headers={'Authorization': 'Bearer bad-token'})
check(r.status_code == 401, 'state с невалидным токеном → 401')
os.environ['DEMO_MODE'] = '1'

os.system('rm -rf data')
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
