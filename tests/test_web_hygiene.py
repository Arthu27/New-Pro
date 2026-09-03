# -*- coding: utf-8 -*-
"""Гигиена web-слоя панели.

Проверки:
1. CSP без внешних CDN-доменов: все скрипты/стили/шрифты — 'self'
   (всё вендорено локально), внешние домены только для аватарок Discord
   (img-src https:) и API/WS (connect-src).
2. Базовые защитные заголовки на каждом ответе: X-Content-Type-Options,
   X-Frame-Options, Referrer-Policy; Cache-Control на статике.
3. В шаблонах нет внешних preconnect/<script src>/<link href> (кроме
   санкционированного CDN Discord для аватарок в <img src>).
4. Service worker (sw.js): кэширует только локальные /static/-ассеты,
   все они существуют, версия кэша инкрементируется (Hakumo-light-vN).
5. Бюджеты ассетов: app.js/style.css не распухают сверх лимитов,
   ни один файл статики не превышает кап размера.

Запуск: python3 tests/test_web_hygiene.py
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

# ─── 1. CSP без CDN ───────────────────────────────────────────────────────────
print('== 1. CSP: всё локальное, CDN-доменов нет ==')
r = client.get('/welcome')
csp = r.headers.get('Content-Security-Policy', '')
_bad = []
for host in ('cdn.jsdelivr.net', 'cdnjs.cloudflare.com', 'fonts.googleapis.com',
             'fonts.gstatic.com', 'unpkg.com', 'ajax.googleapis.com'):
    if host in csp:
        _bad.append(host)
check(not _bad, f'CSP чист от CDN-доменов ({_bad})')
check("default-src 'self'" in csp, "default-src 'self' на месте")
check("script-src 'self' 'unsafe-inline' 'unsafe-eval'" in csp,
      'script-src: только self + inline/eval (админ-панель)')
check("frame-ancestors 'self'" in csp, "frame-ancestors 'self' (антикликджекинг)")
check("img-src 'self' data: https:" in csp, 'img-src: self + data + https (аватарки Discord)')

# ─── 2. защитные заголовки ───────────────────────────────────────────────────
print('== 2. Защитные заголовки на каждом ответе ==')
for path, what in (('/welcome', 'страница'), ('/static/style.css', 'статика'),
                   ('/api/stats', 'API')):
    r = client.get(path)
    ok = (r.headers.get('X-Content-Type-Options') == 'nosniff'
          and r.headers.get('X-Frame-Options') == 'SAMEORIGIN'
          and r.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin')
    check(ok, f'{what} {path}: nosniff + SAMEORIGIN + referrer-policy')
r = client.get('/static/app.js')
check('no-cache' in r.headers.get('Cache-Control', ''), 'статика: Cache-Control no-cache')

# ─── 3. шаблоны без внешних ресурсов ─────────────────────────────────────────
print('== 3. Шаблоны: без внешних preconnect/script/link ==')
TPL_DIR = os.path.join(ROOT, 'web', 'templates')
_bad = []
for f in sorted(os.listdir(TPL_DIR)):
    if not f.endswith('.html'):
        continue
    src = open(os.path.join(TPL_DIR, f), encoding='utf-8').read()
    if re.search(r'<link[^>]*rel\s*=\s*["\']preconnect["\'][^>]*href\s*=\s*["\']https?://', src, re.I):
        _bad.append(f'{f}: внешний preconnect')
    for m in re.finditer(r'<(script|link)\b[^>]*\b(?:src|href)\s*=\s*["\'](https?://[^"\']+)', src, re.I):
        _bad.append(f'{f}: внешний {m.group(1)} → {m.group(2)}')
check(not _bad, f'{len(os.listdir(TPL_DIR))} шаблонов, внешних ресурсов: {len(_bad)} ({_bad[:3]})')

# ─── 4. service worker локальный ─────────────────────────────────────────────
print('== 4. sw.js кэширует только локальные ассеты ==')
sw = open(os.path.join(ROOT, 'web', 'static', 'sw.js'), encoding='utf-8').read()
m = re.search(r"CACHE_NAME\s*=\s*'([^']+)'", sw)
check(bool(m) and re.match(r'Hakumo-light-v\d+$', m.group(1) if m else ''),
      f'имя кэша инкрементируется: {m.group(1) if m else "?"}')
assets = re.findall(r"'([^']+)'", re.search(r'STATIC_ASSETS\s*=\s*\[([^\]]+)\]', sw, re.S).group(1))
external = [a for a in assets if a.startswith('http')]
check(not external, f'внешних URL в STATIC_ASSETS: {len(external)} ({external})')
missing = [a for a in assets if not os.path.exists(os.path.join(ROOT, 'web', a.lstrip('/')))]
check(not missing, f'{len(assets)} ассетов sw.js существуют ({missing[:3]})')

# ─── 5. бюджеты ассетов ──────────────────────────────────────────────────────
print('== 5. Бюджеты статики ==')
limits = {'app.js': 250_000, 'style.css': 320_000, 'pickers.js': 40_000,   # п.3 rich member dropdown + п.4 selectSuite
          'api-guard.js': 20_000, 'websocket-client.js': 30_000,
          'vendor/chartjs/chart.umd.js': 260_000}
_bad = []
for rel, cap in limits.items():
    p = os.path.join(ROOT, 'web', 'static', rel)
    if not os.path.exists(p):
        _bad.append(f'{rel}: нет файла')
        continue
    sz = os.path.getsize(p)
    if sz > cap:
        _bad.append(f'{rel}: {sz} > {cap}')
check(not _bad, f'бюджеты JS/CSS соблюдены ({_bad[:3]})')

STATIC_DIR = os.path.join(ROOT, 'web', 'static')
biggest = None
total = 0
count = 0
for dirpath, _, files in os.walk(STATIC_DIR):
    for fn in files:
        fp = os.path.join(dirpath, fn)
        sz = os.path.getsize(fp)
        total += sz
        count += 1
        if biggest is None or sz > biggest[1]:
            biggest = (os.path.relpath(fp, STATIC_DIR), sz)
check(biggest[1] <= 4_000_000, f'самый большой файл {biggest[0]}: {biggest[1]} байт (кап 4МБ)')
check(total <= 12_000_000, f'вся статика {count} файлов: {total} байт (кап 12МБ)')


# ─── CSP: домен веб-аналитики Cloudflare разрешён ────────────────────────────
# Регресс на жалобу владельца: консоль браузера писала
# «Loading the script 'https://static.cloudflareinsights.com/beacon.min.js'
# violates ... script-src 'self' 'unsafe-inline' 'unsafe-eval'» — Cloudflare
# сам вставляет beacon, а политика его не пускала.
print('== CSP: beacon Cloudflare Insights разрешён ==')
_r = client.get('/welcome')
_csp = _r.headers.get('Content-Security-Policy', '')
check('https://static.cloudflareinsights.com' in _csp,
      'script-src пускает static.cloudflareinsights.com (иначе консоль краснеет)')
check("script-src 'self' 'unsafe-inline' 'unsafe-eval' https://static.cloudflareinsights.com" in _csp,
      'script-src собран целиком: self + inline/eval + beacon')

# ─── Версия сборки видна в панели ────────────────────────────────────────────
# Заказ владельца: после обновления непонятно, применилось ли оно. Номер
# коммита отдаёт /api/build-info и показывает сайдбар.
print('== Версия сборки видна и совпадает с git ==')
import subprocess
_git = subprocess.run(['git', '-C', ROOT, 'rev-parse', 'HEAD'],
                      capture_output=True, text=True)
_head = (_git.stdout or '').strip()
_bi = appmod._BUILD_INFO
check(bool(_bi.get('sha')), f'версия сборки определена: {(_bi.get("sha") or "")[:7]}')
if _head:
    check(_bi.get('sha') == _head,
          f'сборка = HEAD репозитория ({_head[:7]})')
with client.session_transaction() as _s:
    _s['logged_in'] = True
    _s['username'] = 'probe'
    _s['role'] = 'owner'
_r2 = client.get('/api/build-info')
_d2 = _r2.get_json() or {}
check(_r2.status_code == 200 and _d2.get('success') is True,
      f'/api/build-info отвечает ({_r2.status_code})')
check(len(_d2.get('short') or '') == 7 and _d2.get('sha', '').startswith(_d2.get('short', '\0')),
      f'отдаёт короткий и полный sha: {_d2.get("short")}')
_html = client.get('/', follow_redirects=True).get_data(as_text=True)
check('id="sysBuild"' in _html, 'в сайдбаре есть строка «Сборка»')
check((_d2.get('short') or '\0') in _html,
      f'в сайдбаре показан тот же коммит {_d2.get("short")}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
