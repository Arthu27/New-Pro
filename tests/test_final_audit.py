# -*- coding: utf-8 -*-
"""Финальный аудит: дубли роутов, детерминизм, кодировки.

Проверки:
1. В url_map нет двух регистраций одного URL с пересекающимися методами
   (GET+POST на одном пути — норма, GET+GET — мёртвый обработчик).
2. Детерминизм: повторный рендер ключевых страниц и API даёт
   идентичный вывод (после нормализации меток времени) — нет случайного
   порядка/плавающих полей.
3. Кодировки: ни в одном файле нет U+FFFD, мохибаке (латиница-1 вместо
   кириллицы) и BOM в шаблонах.
4. Трейлинг-слэш: страницы отвечают и без слэша, и с ним (редирект или
   200, но не 404/500).

Запуск: python3 tests/test_final_audit.py
"""
import collections
import glob
import os
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

# ─── 1. дубли роутов ─────────────────────────────────────────────────────────
print('== 1. Дубли роутов: один URL — один метод ==')
by_rule = collections.defaultdict(list)
for r in appmod.app.url_map.iter_rules():
    by_rule[str(r)].append(r)
_bad = []
for rs, rs_list in by_rule.items():
    methods = collections.Counter()
    for r in rs_list:
        for m in r.methods - {'HEAD', 'OPTIONS'}:
            methods[m] += 1
    for m, cnt in methods.items():
        if cnt > 1:
            eps = sorted({r.endpoint for r in rs_list if m in r.methods})
            _bad.append(f'{rs} [{m}] × {cnt}: {eps}')
_total_rules = sum(1 for _ in appmod.app.url_map.iter_rules())
check(not _bad, f'{_total_rules} правил, дублей: {len(_bad)} ({_bad[:3]})')

# ─── 2. детерминизм рендера ──────────────────────────────────────────────────
print('== 2. Детерминизм: повторный рендер идентичен ==')
TIME_RE = re.compile(
    r'\d{4}-\d{2}-\d{2}[T ][\d:\.]+(?:Z|\+\d{2}:\d{2})?|\d{2}:\d{2}:\d{2}|\d{13}')


def norm(txt):
    return TIME_RE.sub('<TIME>', txt)


_bad = []
for p in ('/dashboard', '/welcome', '/status', '/api/stats', '/api/guilds', '/schedule'):
    bodies = []
    for _ in range(3):
        time.sleep(0.05)
        bodies.append(norm(client.get(p).get_data(as_text=True)))
    if not (bodies[0] == bodies[1] == bodies[2]):
        _bad.append(p)
check(not _bad, f'6 страниц/API детерминированы ({_bad[:3]})')

# ─── 3. кодировки ────────────────────────────────────────────────────────────
print('== 3. Кодировки: без U+FFFD, мохибаке, BOM ==')
files = (glob.glob(os.path.join(ROOT, 'web', 'templates', '*.html'))
         + glob.glob(os.path.join(ROOT, 'web', 'static', '*.js'))
         + glob.glob(os.path.join(ROOT, 'web', '**', '*.py'), recursive=True)
         + glob.glob(os.path.join(ROOT, 'cogs', '*.py'))
         + glob.glob(os.path.join(ROOT, 'services', '*.py'))
         + glob.glob(os.path.join(ROOT, '*.py')))
_bad = []
for f in files:
    raw = open(f, 'rb').read()
    rel = os.path.relpath(f, ROOT)
    if raw.startswith(b'\xef\xbb\xbf'):
        _bad.append(f'{rel}: BOM')
    try:
        txt = raw.decode('utf-8')
    except UnicodeDecodeError as e:
        _bad.append(f'{rel}: {e}')
        continue
    if '\ufffd' in txt:
        _bad.append(f'{rel}: U+FFFD')
    if 'Ð' in txt and 'Ð°' in txt:
        _bad.append(f'{rel}: мохибаке (латиница-1 вместо кириллицы)')
check(not _bad, f'{len(files)} файлов чистые ({_bad[:4]})')

# ─── 4. трейлинг-слэш ────────────────────────────────────────────────────────
print('== 4. Трейлинг-слэш: страницы живы и со слэшем ==')
_bad = []
for p in ('/dashboard', '/channels', '/welcome', '/status', '/roles'):
    r = client.get(p + '/')
    if r.status_code not in (200, 301, 302, 308):
        _bad.append(f'{p}/ → {r.status_code}')
check(not _bad, f'5 страниц отвечают со слэшем ({_bad[:3]})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
