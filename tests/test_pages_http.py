# -*- coding: utf-8 -*-
"""HTTP-прогон всех страниц панели через Flask test_client (без сети).

Проверки:
1. Каждый шаблон, указанный в меню панели (services/panel_menu.py), существует.
2. Каждая страница меню отвечает 200 владельцу.
3. Гостевые страницы (welcome/login/register/status/apply/mod-kiosk) — 200.
4. Все литеральные GET-API из шаблонов отвечают не 500 (200/302/403/404/405 ок —
   данные зависят от бота, но сервер не должен падать).
5. Ответы страниц — HTML с корректным doctype, без «Internal Server Error».

Запуск: python3 tests/test_pages_http.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
os.environ['MAIN_GUILD_ID'] = '777'

PASS = 0
FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


import web.app as appmod  # noqa: E402

appmod.app.config['TESTING'] = True
client = appmod.app.test_client()

with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'admin'
    s['role'] = 'owner'
    s['selected_guild'] = '777'

# ── Страницы из меню ─────────────────────────────────────────────────────
print('== 1. Страницы меню существуют и отвечают 200 ==')
from services.panel_menu import MENU  # noqa: E402

menu_paths = set()


def _walk(node):
    if isinstance(node, dict):
        if node.get('path'):
            menu_paths.add(node['path'])
        for v in node.values():
            _walk(v)
    elif isinstance(node, list):
        for v in node:
            _walk(v)


_walk(MENU)

check(len(menu_paths) >= 100, f'меню содержит {len(menu_paths)} страниц')

_bad = []
for path in sorted(menu_paths):
    r = client.get(path)
    if r.status_code != 200:
        _bad.append(f'{path} → {r.status_code}')
check(not _bad, f'все {len(menu_paths)} страниц меню отвечают 200 владельцу ({_bad[:3]})')

print('== 2. Страницы — настоящий HTML ==')
_bad = []
for path in sorted(menu_paths):
    r = client.get(path)
    if r.status_code != 200:
        continue
    body = r.get_data(as_text=True)
    if not body.lstrip().lower().startswith('<!doctype html') and '<html' not in body[:200].lower():
        _bad.append(f'{path}: не HTML')
    if 'Internal Server Error' in body:
        _bad.append(f'{path}: Internal Server Error в теле')
    if 'Traceback (most recent call last)' in body:
        _bad.append(f'{path}: Traceback в теле')
check(not _bad, f'все страницы — чистый HTML без ошибок сервера ({_bad[:3]})')

print('== 3. Гостевые страницы ==')
guests = ['/welcome', '/login', '/register', '/status', '/apply', '/mod-kiosk']
_bad = []
for path in guests:
    r = client.get(path)
    if r.status_code != 200:
        _bad.append(f'{path} → {r.status_code}')
check(not _bad, f'гостевые страницы открыты ({_bad[:3]})')

print('== 4. GET-API из шаблонов не падают 500 ==')
apis = set()
for f in sorted(os.listdir(os.path.join(ROOT, 'web', 'templates'))):
    if not f.endswith('.html'):
        continue
    src = open(os.path.join(ROOT, 'web', 'templates', f), encoding='utf-8').read()
    for m in re.finditer(r"fetch(?:CachedJSON)?\(\s*['\"](/api/[^'\"?]+)", src):
        apis.add(m.group(1))

GID = str(os.environ.get('MAIN_GUILD_ID') or '777')
_bad = []
_ok = 0
for u in sorted(apis):
    if '<' in u or '{' in u:
        continue
    probe = u.replace('/api/guild/', f'/api/guild/{GID}/')  # не используется — просто литералы
    r = client.get(probe)
    if r.status_code == 500:
        _bad.append(f'{probe} → 500')
    else:
        _ok += 1
check(not _bad, f'{_ok} GET-API проверено, 500-х нет ({_bad[:3]})')

print('== 5. Статические ассеты ==')
for asset in ('/static/app.js', '/static/style.css', '/static/vendor/fontawesome/css/all.min.css',
              '/static/vendor/fonts/fonts.css', '/static/vendor/chartjs/chart.umd.js',
              '/static/brand/emblem-dragon.png', '/static/favicon.ico'):
    r = client.get(asset)
    check(r.status_code == 200, f'{asset} → {r.status_code}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
