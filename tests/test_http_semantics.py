# -*- coding: utf-8 -*-
"""HTTP-семантика и устойчивость сервера (другой срез, чем pages_http).

Проверки (через Flask test_client, без сети):
1. HEAD на страницы/статику/API отвечает тем же статусом, что и GET.
2. Неверные методы на GET-маршрутах → 405 (не 500, не тихий 200).
3. Неизвестные пути → 404 (страница и API).
4. MIME-типы: страницы text/html+charset, API application/json,
   статика (css/js/png/woff2/ttf/ico) — правильные типы.
5. Фазз: 360 случайных query-строк на страницах и API → никогда не 500.
6. Битый JSON на все POST-эндпоинты из шаблонов → не 500.
7. Бюджет времени рендера: все страницы меню + гостевые укладываются
   в лимит (среднее < 1с, сумма < 120с).

Запуск: python3 tests/test_http_semantics.py
"""
import glob
import os
import random
import re
import sys
import time

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

# ─── 1. HEAD == GET ──────────────────────────────────────────────────────────
print('== 1. HEAD отвечает тем же статусом, что и GET ==')
_sample = ['/welcome', '/login', '/register', '/status', '/dashboard', '/channels',
           '/api/stats', '/api/guilds', '/api/bot-stats', '/health',
           '/static/style.css', '/static/app.js', '/static/brand/emblem-dragon.png',
           '/static/favicon.ico']
_bad = []
for p in _sample:
    g = client.get(p).status_code
    h = client.head(p).status_code
    if g != h:
        _bad.append(f'{p}: GET {g} ≠ HEAD {h}')
check(not _bad, f'{len(_sample)} маршрутов HEAD==GET ({_bad[:3]})')

# ─── 2. неверные методы → 405 ────────────────────────────────────────────────
print('== 2. Неверный метод → 405 ==')
_bad = []
for method, path in (('post', '/welcome'), ('put', '/health'), ('delete', '/status'),
                     ('post', '/static/style.css'), ('put', '/api/stats'),
                     ('delete', '/register')):
    r = getattr(client, method)(path)
    if r.status_code != 405:
        _bad.append(f'{method.upper()} {path} → {r.status_code}')
check(not _bad, f'6 проверок метода → 405 ({_bad[:3]})')

# ─── 3. неизвестные пути → 404 ───────────────────────────────────────────────
print('== 3. Неизвестные пути → 404 ==')
_bad = []
for p in ('/definitely-not-a-page-42', '/api/definitely-not-an-api-42',
          '/static/missing-file-42.js'):
    r = client.get(p)
    if r.status_code != 404:
        _bad.append(f'{p} → {r.status_code}')
check(not _bad, f'3 неизвестных пути → 404 ({_bad[:3]})')

# ─── 4. MIME-типы ────────────────────────────────────────────────────────────
print('== 4. MIME-типы страниц/API/статики ==')
expect = {
    '/welcome': 'text/html', '/dashboard': 'text/html', '/api/stats': 'application/json',
    '/static/style.css': 'text/css', '/static/app.js': 'text/javascript',
    '/static/pickers.js': 'text/javascript', '/static/api-guard.js': 'text/javascript',
    '/static/sw.js': 'text/javascript', '/static/websocket-client.js': 'text/javascript',
    '/static/vendor/fontawesome/css/all.min.css': 'text/css',
    '/static/vendor/fonts/fonts.css': 'text/css',
    '/static/vendor/chartjs/chart.umd.js': 'text/javascript',
    '/static/brand/emblem-dragon.png': 'image/png',
    '/static/vendor/fontawesome/webfonts/fa-solid-900.woff2': 'font/woff2',
    '/static/vendor/fontawesome/webfonts/fa-solid-900.ttf': 'font/ttf',
    '/static/favicon.ico': 'image/vnd.microsoft.icon',
}
_bad = []
for p, want in expect.items():
    r = client.get(p)
    got = r.headers.get('Content-Type', '').split(';')[0].strip()
    if r.status_code != 200:
        _bad.append(f'{p} → {r.status_code}')
    elif got != want:
        _bad.append(f'{p}: {got} ≠ {want}')
r = client.get('/welcome')
if 'charset=utf-8' not in r.headers.get('Content-Type', ''):
    _bad.append('/welcome: нет charset=utf-8')
check(not _bad, f'{len(expect)} MIME-типов корректны ({_bad[:4]})')

# ─── 5. фазз query-строк ─────────────────────────────────────────────────────
print('== 5. Фазз: 360 случайных query-строк без 500 ==')
random.seed(42)
_bad = []
for path in ('/welcome', '/dashboard', '/channels', '/api/stats', '/api/guilds',
             '/api/leveling/stats'):
    for _ in range(60):
        parts = []
        for _2 in range(random.randint(1, 6)):
            k = ''.join(random.choices('abcXYZ019_', k=random.randint(1, 20)))
            v = '%' + ''.join(random.choices('abz09', k=random.randint(1, 10)))
            v += str(random.randint(0, 999999))
            parts.append(f'{k}={v}')
        r = client.get(path + '?' + '&'.join(parts))
        if r.status_code == 500:
            _bad.append(f'{path}?… → 500')
            break
check(not _bad, f'360 фазз-запросов без 500 ({_bad[:3]})')

# ─── 6. битый JSON на POST-эндпоинты ─────────────────────────────────────────
print('== 6. Битый JSON на POST-эндпоинты → не 500 ==')
posts = set()
for f in glob.glob(os.path.join(ROOT, 'web', 'templates', '*.html')):
    src = open(f, encoding='utf-8').read()
    for m in re.finditer(r"fetch(?:CachedJSON)?\(\s*['\"](/api/[^'\"]+)['\"]", src):
        window = src[m.end():m.end() + 500]
        if re.search(r"method\s*:\s*['\"]POST", window):
            posts.add(m.group(1))
_bad = []
_ok = 0
for p in sorted(posts):
    if '<' in p or '{' in p:
        continue
    r = client.post(p, data=b'{broken json!!', content_type='application/json')
    if r.status_code == 500:
        _bad.append(f'{p} → 500')
    else:
        _ok += 1
check(not _bad, f'{_ok} POST-эндпоинтов переживают битый JSON ({_bad[:4]})')

# ─── 7. бюджет времени рендера ───────────────────────────────────────────────
print('== 7. Бюджет времени рендера страниц ==')
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
paths = sorted(menu_paths) + ['/welcome', '/login', '/register', '/status', '/apply', '/mod-kiosk']
times = []
for p in paths:
    t0 = time.perf_counter()
    r = client.get(p)
    times.append(time.perf_counter() - t0)
    if r.status_code != 200:
        _bad.append(f'{p} → {r.status_code}')
total = sum(times)
mean = total / len(times)
check(total < 120 and mean < 1.0, f'{len(times)} страниц: сумма {total:.1f}с, среднее {mean * 1000:.0f}мс')
check(max(times) < 5.0, f'самая медленная страница: {max(times) * 1000:.0f}мс (порог 5000мс)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
