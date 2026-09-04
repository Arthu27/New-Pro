#!/usr/bin/env python3
"""Страница «Пользователи»: карточка участника с разделами.

Заказ владельца: «Пользователи — нормально красивую меню сделай, чтобы можно
было много чего сделать». Проверки ниже держат три вещи:

1. Карточка состоит из шести разделов, и у каждого есть своя панель.
2. Каждый эндпоинт, к которому обращается страница, реально существует.
   Прежняя карточка звала /member-card/lookup, которого не было никогда, —
   из-за этого окно вечно показывало «Сеть моргнула — попробуйте кликнуть
   ещё раз». Теперь такое не пройдёт незамеченным.
3. Фильтры, KPI и сброс на месте, инлайн-скрипт синтаксически жив.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TPL = os.path.join(ROOT, 'web', 'templates', 'users.html')

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


SRC = open(TPL, encoding='utf-8').read()

# ─── 1. Разделы карточки ───────────────────────────────────────────────────
print('== 1. Разделы карточки участника ==')
PANES = [
    ('overview', 'Обзор'),
    ('warns', 'Предупреждения'),
    ('history', 'История'),
    ('notes', 'Заметки'),
    ('appeals', 'Апелляции'),
    ('punish', 'Наказание'),
]
tabs = re.findall(r'class="mcf-tab[^"]*"[^>]*data-pane="([a-z]+)"', SRC)
panes = re.findall(r'class="mcf-pane[^"]*"[^>]*data-pane="([a-z]+)"', SRC)
for key, label in PANES:
    check(key in tabs, f'вкладка «{label}» есть')
    check(key in panes, f'панель «{label}» есть')
check(sorted(tabs) == sorted(panes),
      f'вкладки и панели совпадают ({len(tabs)} и {len(panes)})')
check('id="mcTabs"' in SRC and 'role="tablist"' in SRC,
      'список вкладок доступен для читалок экрана')

# ─── 2. Эндпоинты страницы существуют ─────────────────────────────────────
print('== 2. Каждый эндпоинт страницы существует ==')
from web.app import app as _app  # noqa: E402

_rules = {str(r) for r in _app.url_map.iter_rules()}
NEEDED = [
    '/api/guilds',
    '/api/guild/<guild_id>/members',
    '/api/member-profile/<guild_id>/<user_id>',
    '/api/member-notes/<member_id>',
    '/api/member-notes/<member_id>/add',
    '/api/member-notes/<member_id>/<note_id>/delete',
    '/api/watchlist/<guild_id>',
    '/api/guild/<gid>/appeals/user/<uid>',
    '/api/guild/<gid>/punish/options',
    '/api/guild/<gid>/punish',
]
for rule in NEEDED:
    check(rule in _rules, f'маршрут жив: {rule}')

# ровно та болезнь, из-за которой карточка раньше не открывалась
for ghost in ('member-card/lookup', 'member-card/export', 'MemberCard.renderCard'):
    check(ghost not in SRC, f'мёртвого {ghost} в странице нет')

# каждый путь, который страница просит fetch'ем, должен начинаться с живого
# префикса — иначе снова появится кнопка, которая «моргает сетью»
_js = '\n'.join(re.findall(r'<script>(.*?)</script>', SRC, re.S))
_calls = sorted(set(re.findall(r"fetch\('(/[a-zA-Z0-9_\-/]+)", _js)))
check(_js.count('fetch(') >= 8, f"fetch-вызовов на странице: {_js.count('fetch(')}")
for call in _calls:
    hit = any(r.startswith(call.rstrip('/')) or call.rstrip('/') in r for r in _rules)
    check(hit, f'цель fetch существует: {call}')

# ─── 3. Фильтры, KPI, сброс ───────────────────────────────────────────────
print('== 3. Фильтры, KPI и сброс ==')
for st, label in (('all', 'Все'), ('on', 'В сети'), ('off', 'Не в сети'),
                  ('new', 'Новички'), ('bot', 'Боты')):
    check(f'data-st="{st}"' in SRC, f'фильтр «{label}» есть')
check("statusFilter === 'new'" in _js and "statusFilter === 'bot'" in _js,
      'новые фильтры действительно применяются в applyView')
check('class="u-kpis"' in SRC and 'u-kpi-ico' in SRC, 'KPI-карточки на месте')
check('id="uReset"' in SRC, 'кнопка сброса фильтров есть')
check("data-copy=" in SRC, 'быстрое копирование ID/упоминания есть')

# ─── 4. Инлайн-скрипт живой ───────────────────────────────────────────────
print('== 4. Синтаксис инлайн-скрипта ==')
node = shutil.which('node')
if node:
    tmp = tempfile.mkdtemp(prefix='users_panel_')
    path = os.path.join(tmp, 'page.js')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(_js)
    proc = subprocess.run([node, '--check', path], capture_output=True, text=True, timeout=60)
    check(proc.returncode == 0,
          'node --check: скрипт без синтаксических ошибок'
          + (f' ({proc.stderr.strip()[:200]})' if proc.returncode else ''))
else:
    check(True, 'node не установлен — проверка пропущена')

# ─── 5. Страница отдаётся ─────────────────────────────────────────────────
print('== 5. Страница рендерится ==')
_app.config['TESTING'] = True
_client = _app.test_client()
with _client.session_transaction() as _s:
    _s.clear()
    _s['logged_in'] = True
    _s['username'] = 'UsersTest'
    _s['role'] = 'owner'
_r = _client.get('/users', follow_redirects=True)
_body = _r.get_data(as_text=True)
check(_r.status_code == 200, f'/users отдаёт {_r.status_code}')
_n_tabs = len(re.findall(r'class="mcf-tab( active)?"', _body))
check(_n_tabs == len(PANES), f'в ответе ровно {len(PANES)} вкладок (нашли {_n_tabs})')
check('id="mcWin"' in _body, 'окно карточки в ответе есть')
check('Сеть моргнула — попробуйте кликнуть ещё раз' not in _body,
      'прежней ошибки карточки в ответе нет')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
