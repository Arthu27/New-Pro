# -*- coding: utf-8 -*-
"""Аудит меню панели и конкурентная устойчивость.

Проверки:
1. Каждый пункт меню имеет непустые path/label/icon; пути уникальны.
2. Каждый путь меню зарегистрирован в app.url_map (роут реально существует).
3. Доступы/тоны/секции пунктов — из разрешённого словаря.
4. Иконки групп и пунктов меню — валидные fa-* имена.
5. Каждый шаблон web/templates упоминается хотя бы в одном render_template
   (или include/extends) — нет мёртвых шаблонов.
6. Все render_template('x.html') в коде ссылаются на существующие файлы.
7. Конкурентность: 8 потоков × 15 смешанных GET (страницы+API) через
   отдельные test_client — все 200, ни одного 500.

Запуск: python3 tests/test_menu_audit.py
"""
import glob
import os
import re
import sys
import threading

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


from services.panel_menu import MENU  # noqa: E402

pages = [p for grp in MENU for p in grp.get('pages', [])]

# ─── 1. поля пунктов ─────────────────────────────────────────────────────────
print('== 1. Поля пунктов меню ==')
_bad = []
for p in pages:
    if not p.get('path') or not p.get('label') or not p.get('icon'):
        _bad.append(f'пустые поля у {p.get("path") or p.get("label")}')
paths = [p['path'] for p in pages if p.get('path')]
dups = {x for x in paths if paths.count(x) > 1}
if dups:
    _bad.append(f'дубли путей: {sorted(dups)[:5]}')
check(not _bad, f'{len(pages)} пунктов, пути уникальны ({_bad[:3]})')

# ─── 2. пути → роуты Flask ───────────────────────────────────────────────────
print('== 2. Каждый путь меню зарегистрирован во Flask ==')
import web.app as appmod  # noqa: E402

rules = {str(r) for r in appmod.app.url_map.iter_rules()}
_bad = [p for p in paths if p not in rules]
check(not _bad, f'{len(paths)} путей меню найдены в url_map ({_bad[:5]})')

# ─── 3. словари access/tone/section ──────────────────────────────────────────
print('== 3. access/tone/section из разрешённых словарей ==')
ALLOWED_ACCESS = {'Админ', 'Мод+'}
ALLOWED_TONE = {'analytics', 'critical', 'info', 'security', 'warning'}
_bad = []
for p in pages:
    if p.get('access') and p['access'] not in ALLOWED_ACCESS:
        _bad.append(f'{p["path"]}: access={p["access"]}')
    if p.get('tone') and p['tone'] not in ALLOWED_TONE:
        _bad.append(f'{p["path"]}: tone={p["tone"]}')
    if p.get('min_role') and not isinstance(p['min_role'], str):
        _bad.append(f'{p["path"]}: min_role не строка')
check(not _bad, f'словари валидны ({_bad[:4]})')

# ─── 4. иконки меню ──────────────────────────────────────────────────────────
print('== 4. Иконки меню — валидные fa-* имена ==')
_bad = []
for grp in MENU:
    for ic in (grp.get('icon'),) + tuple(p.get('icon') for p in grp.get('pages', [])):
        if ic is None:
            continue
        if isinstance(ic, str) and ic.startswith('fa-'):
            continue
        _bad.append(f'{ic!r}')
check(not _bad, f'иконки меню валидны ({_bad[:4]})')

# ─── 5. нет мёртвых шаблонов ─────────────────────────────────────────────────
print('== 5. Каждый шаблон кем-то рендерится ==')
py_src = ''
for f in glob.glob(os.path.join(ROOT, 'web', '**', '*.py'), recursive=True):
    py_src += open(f, encoding='utf-8').read()
all_src = py_src
for f in glob.glob(os.path.join(ROOT, 'web', 'templates', '*.html')):
    all_src += open(f, encoding='utf-8').read()
tpls = {os.path.basename(f) for f in glob.glob(os.path.join(ROOT, 'web', 'templates', '*.html'))}
referenced = set(re.findall(r'["\']([a-z0-9_]+\.html)["\']', all_src))
orphans = sorted(t for t in tpls if t not in referenced)
check(not orphans, f'{len(tpls)} шаблонов, мёртвых: {len(orphans)} ({orphans[:5]})')

# ─── 6. render_template → файл существует ────────────────────────────────────
print('== 6. render_template ссылается на существующие файлы ==')
_bad = []
for m in re.finditer(r'render_template\s*\(\s*[\'"]([^\'"]+\.html)', py_src):
    t = m.group(1)
    if not os.path.exists(os.path.join(ROOT, 'web', 'templates', t)):
        _bad.append(t)
check(not _bad, f'render_template → файлы на месте ({_bad[:5]})')

# ─── 7. конкурентность ───────────────────────────────────────────────────────
print('== 7. Конкурентность: 8 потоков × 15 запросов ==')
_targets = ['/dashboard', '/channels', '/api/stats', '/api/guilds', '/api/bot-stats',
            '/roles', '/antifake', '/autofilter', '/welcome', '/api/status-public']
errors = []
lock = threading.Lock()


def worker(tid):
    c = appmod.app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = 'owner'
        s['selected_guild'] = '777'
    for i in range(15):
        p = _targets[(tid * 3 + i) % len(_targets)]
        r = c.get(p)
        if r.status_code != 200:
            with lock:
                errors.append(f'[{tid}] {p} → {r.status_code}')


threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
for t in threads:
    t.start()
for t in threads:
    t.join()
check(not errors, f'120 конкурентных запросов без ошибок ({errors[:4]})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
