# -*- coding: utf-8 -*-
"""Сквозные регрессии качества веб-панели (Light Edition).

Проверяет доступность исходных шаблонов, целостность дизайн-системы
и клиентского кита, Jinja-синтаксис и HTTP-рендер всех пунктов owner-меню.

Запуск: python3 tests/test_quality_suite.py
"""
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix='hakumo_quality_suite_test_')
os.chdir(_TMP)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ['PANEL_PASSWORD'] = 'QualitySuiteTest!2026'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DB_PATH'] = str(Path(_TMP) / 'quality.db')

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


TEMPLATES = ROOT / 'web' / 'templates'
STATIC = ROOT / 'web' / 'static'
files = sorted(TEMPLATES.glob('*.html'))

print('== 1. Source-level доступность всех шаблонов ==')
missing_alt = []
missing_type = []
unlabelled_icons = []
for path in files:
    source = path.read_text(encoding='utf-8')
    for match in re.finditer(r'<img\b[^>]*>', source, re.I | re.S):
        if not re.search(r'\balt\s*=', match.group(0), re.I):
            missing_alt.append((path.name, source.count('\n', 0, match.start()) + 1))
    for match in re.finditer(r'<button\b[^>]*>', source, re.I | re.S):
        if not re.search(r'\btype\s*=', match.group(0), re.I):
            missing_type.append((path.name, source.count('\n', 0, match.start()) + 1))
    for match in re.finditer(r'(<button\b[^>]*>)(.*?)</button\s*>',
                             source, re.I | re.S):
        opening, body = match.groups()
        visible = re.sub(r'<[^>]+>|\{[{%].*?[}%]\}', '', body,
                         flags=re.S)
        if (not html.unescape(visible).strip()
                and not re.search(r'aria-label\s*=|\btitle\s*=', opening,
                                  re.I)):
            unlabelled_icons.append(
                (path.name, source.count('\n', 0, match.start()) + 1))

check(len(files) >= 80, f'аудит охватывает все шаблоны ({len(files)})')
check(not missing_alt, f'каждое изображение имеет alt ({missing_alt[:5] or "OK"})')
check(not missing_type,
      f'каждая кнопка имеет явный безопасный type ({missing_type[:5] or "OK"})')
check(not unlabelled_icons,
      f'икон-кнопки имеют доступное имя ({unlabelled_icons[:5] or "OK"})')

print('== 2. Глобальный shell и ассеты ==')
base = (TEMPLATES / 'base.html').read_text(encoding='utf-8')
for marker, label in [
    ('/static/style.css', 'дизайн-система'),
    ('/static/app.js', 'единый клиентский кит'),
    ('class="skip-link"', 'skip-link к содержимому'),
    ('id="main-content"', 'цель keyboard-навигации'),
    ('id="sidebarSearch"', 'фильтр меню'),
    ('id="palette-data"', 'данные палитры команд'),
    ('id="notifDrawer"', 'дровер уведомлений'),
    ('data-theme="light"', 'светлая тема по умолчанию'),
]:
    check(marker in base, f'base.html содержит: {label}')
for dead in ('quality-suite.css', 'quality-suite.js', 'ux-kit.js', 'polish.css',
             'moderation-suite.css', 'moderation-rooms.css', 'welcomeScreen'):
    check(dead not in base, f'старый ассет удалён из base.html: {dead}')

css_path = STATIC / 'style.css'
js_path = STATIC / 'app.js'
check(css_path.is_file() and js_path.is_file(), 'дизайн-система и кит существуют')
css = css_path.read_text(encoding='utf-8')
js = js_path.read_text(encoding='utf-8')
check(css.count('{') == css.count('}') and css.count('{') >= 200,
      f'CSS структурно целый и содержательный ({css.count("{{")} блоков)')
for marker in ('.kbd-palette', '.drawer', '.toast', '.modal-overlay',
               '.data-table', '.switch', '@media (max-width: 1080px)',
               'prefers-reduced-motion', ':focus-visible'):
    check(marker in css, f'CSS реализует {marker}')
for marker in ('showToast', 'confirmAction', 'fetchCachedJSON', 'setLiveRefresh',
               'qualitySetLoading', 'revealInit', "addEventListener('click'"):
    check(marker in js, f'app.js реализует {marker}')
node = subprocess.run(['node', '--check', str(js_path)], capture_output=True,
                      text=True, timeout=30)
check(node.returncode == 0,
      f'app.js проходит node --check ({node.stderr.strip() or "OK"})')

print('== 3. Jinja-синтаксис и HTTP-рендер ==')
from jinja2 import Environment  # noqa: E402

env = Environment()
bad_jinja = []
for path in files:
    try:
        env.parse(path.read_text(encoding='utf-8'))
    except Exception as exc:
        bad_jinja.append((path.name, str(exc)[:80]))
check(not bad_jinja,
      f'все {len(files)} шаблонов парсятся Jinja ({bad_jinja[:3] or "OK"})')

import web.app as webapp  # noqa: E402
from services.panel_menu import panel_groups_for  # noqa: E402

client = webapp.app.test_client()
with client.session_transaction() as session:
    session.clear()
    session['logged_in'] = True
    session['username'] = 'QualityTester'
    session['role'] = 'owner'

asset_css = client.get('/static/style.css')
asset_js = client.get('/static/app.js')
check(asset_css.status_code == 200 and b'.kbd-palette' in asset_css.data,
      'CSS отдаётся Flask static')
check(asset_js.status_code == 200 and b'fetchCachedJSON' in asset_js.data,
      'app.js отдаётся Flask static')

pages = [page for group in panel_groups_for('owner') for page in group['pages']]
paths = [page['path'] for page in pages]
check(len(paths) == 77 and len(set(paths)) == 77,
      f'owner-меню содержит 77 уникальных страниц ({len(paths)})')

rendered = 0
for route in paths:
    try:
        response = client.get(route, follow_redirects=True)
        body = response.get_data(as_text=True)
        ok = (response.status_code == 200
              and 'style.css' in body
              and 'app.js' in body
              and 'class="skip-link"' in body
              and 'id="main-content"' in body)
    except Exception as exc:
        ok = False
        body = f'{type(exc).__name__}: {exc}'
    if ok:
        rendered += 1
    check(ok, f'{route}: HTTP 200 + общий shell')
check(rendered == len(paths),
      f'shell есть на всех маршрутах ({rendered}/{len(paths)})')

home = client.get('/').get_data(as_text=True)
check('welcomeScreen' not in home, 'старый splash-экран удалён с главной')
check('class="page-hero"' in home, 'главная использует светлую шапку')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
