# -*- coding: utf-8 -*-
"""Тесты глобального визуального полироля панели (polish.css + base.html).

Запуск: python3 tests/test_panel_polish.py
"""
import os
import re
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_polish_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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


# ═══ 1. Файл слоя: целостность ═══════════════════════════════════════════
print('== polish.css ==')
css_path = os.path.join(ROOT, 'web', 'static', 'polish.css')
check(os.path.isfile(css_path), 'polish.css существует')
css = open(css_path, encoding='utf-8').read()
check(css.count('{') == css.count('}'), f'сбалансированные скобки ({css.count("{")} пар)')
check('/*' in css and '*/' in css and css.count('/*') == css.count('*/'),
      'комментарии закрыты корректно')
check('@import' not in css, 'нет @import (шрифты уже грузит style.css)')
check('!important' in css, 'слой умеет перебивать базовые !important-правила')

# ключевые улучшения на месте
for marker, label in [
    ('body::after', 'глубина фона (виньетка + акцент)'),
    ('.sidebar::after', 'золотая кромка сайдбара'),
    ('.nav-link.active i', 'иконка-чип у активного пункта меню'),
    ('.page-hero::after', 'блик в герое страницы'),
    ('acSheen', 'анимация блика'),
    ('acTitleShine', 'перелив заголовка героя'),
    ('.main-content > *:nth-child', 'каскад появления страницы'),
    ('translateY(-2px)', 'подъём карточек при наведении'),
    (':active', 'тактильное нажатие кнопок'),
    ('thead th', 'липкая шапка таблиц'),
    ('::selection', 'акцентное выделение текста'),
    (':focus-visible', 'видимый фокус с клавиатуры'),
    ('prefers-reduced-motion', 'уважение к reduced motion'),
    ('.user-menu a:hover', 'анимация пунктов меню пользователя'),
]:
    check(marker in css, f'слой содержит: {label}')

# токены вместо жёстких цветов (адаптация к светлой теме и смене акцента)
hard_dark = re.findall(r'rgba\(\s*(?:10|26|8),\s*\d+', css)
check(not hard_dark, f'нет жёстких тёмных rgba (сломали бы светлую тему): {hard_dark or "ок"}')
check(css.count('color-mix') >= 8, 'color-mix активно используется (≥8)')
check('var(--ac' in css and 'var(--text' in css, 'работа через токены темы')

# ═══ 2. base.html подключает слой ════════════════════════════════════════
print('== base.html ==')
base = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
i_style = base.find('style.css')
i_polish = base.find('polish.css')
check(i_polish != -1, 'base.html ссылается на polish.css')
check(i_style != -1 and i_style < i_polish, 'слой подключён ПОСЛЕ style.css (переопределяет)')

# ═══ 3. Страницы рендерятся со слоем ═════════════════════════════════════
print('== страницы ==')
from web.app import app as _flask_app  # noqa: E402

client = _flask_app.test_client()


def login_as(role):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'PanelPolish'
        s['role'] = role


r = client.get('/static/polish.css')
check(r.status_code == 200 and 'stylesheet' in (r.headers.get('Content-Type') or '')
      or r.status_code == 200, f'polish.css отдаётся статикой ({r.status_code})')
check(r.get_data(as_text=True).count('{') == css.count('{'),
      'отдаётся именно наш файл (содержимое совпадает)')

login_as('owner')
rendered = 0
for path in ('/anticrash', '/proofs', '/backups', '/mod-tools', '/commands'):
    r = client.get(path)
    if r.status_code != 200:
        check(False, f'{path}: страница открывается под owner (код {r.status_code})')
        continue
    page = r.get_data(as_text=True)
    ok = 'polish.css' in page and 'style.css' in page
    if ok:
        rendered += 1
    check(ok, f'{path}: 200, оба стиля подключены')
check(rendered == 5, 'все контрольные страницы отрендерились со слоем')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
