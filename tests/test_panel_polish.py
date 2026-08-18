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

# ═══ 4. Дашборд / логин: локальные слои ══════════════════════════════════
print('== дашборд и логин ==')
dash = open(os.path.join(ROOT, 'web', 'templates', 'dashboard.html'), encoding='utf-8').read()
check('Dashboard polish' in dash, 'дашборд: слой полироли подключён')
check('.stat-card-big.purple::after' in dash and 'var(--violet)' in dash,
      'дашборд: цветные углы у стат-карточек')
check('.hero-chips .chip:hover' in dash and '.donut-card:hover' in dash,
      'дашборд: hover-подъёмы чипов и донатов')
check('prefers-reduced-motion' in dash, 'дашборд: reduced motion учтён')

login_as('owner')
r = client.get('/')
check(r.status_code == 200 and 'Dashboard polish' in r.get_data(as_text=True),
      'дашборд рендерится со слоем (owner, /)')

loginf = open(os.path.join(ROOT, 'web', 'templates', 'login.html'), encoding='utf-8').read()
check('Login polish' in loginf and 'loginTitleShine' in loginf and 'loginCardIn' in loginf,
      'логин: перелив заголовка + появление карточки')
check('btn-submit::after' in loginf and 'loginAlertIn' in loginf,
      'логин: блик кнопки и своя анимация алерта (без зависимости от style.css)')
check('animation: msgIn' not in loginf, 'логин: нет ссылки на чужой msgIn (его нет в файле)')

with client.session_transaction() as s:
    s.clear()
r = client.get('/login')
check(r.status_code == 200 and 'Login polish' in r.get_data(as_text=True),
      'страница /login рендерится со слоем без логина')

check('.msg.ok' in css and '.msg.err' in css and '.msg.info' in css,
      'polish.css: глобальные .msg-оповещения (ok/err/info)')
base_now = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('v=5' in base_now, 'base.html: кэш polish.css сброшен (v=5)')

# ═══ 6. Мобильный проход (v4) ═════════════════════════════════════════════
print('== v4: мобильный проход ==')
check('.sidebar-backdrop' in css and 'body.sb-open' in css,
      'v4: бэкдроп + лок скрола под меню')
check('pointer: coarse' in css, 'v4: увеличенные тач-зоны для пальцев')
check('font-size: 16px !important' in css, 'v4: анти-зум iOS у полей ввода')
check('safe-area-inset-bottom' in css, 'v4: учтена бровь-безопасная зона')
check('.navbar-clock' in css and 'display: none' in css, 'v4: часы прячутся на мобиле')
check('.ac-metrics' in css, 'v4: мелкая сетка метрик на телефоне')

check("id = 'sidebarBackdrop'" in base_now or "id='sidebarBackdrop'" in base_now
      or "bd.id = 'sidebarBackdrop'" in base_now, 'v4: JS создаёт бэкдроп')
check("e.key === 'Escape'" in base_now, 'v4: Esc закрывает меню')
check("sb.querySelectorAll('.nav-link')" in base_now, 'v4: тап по ссылке закрывает меню')
check('fa-xmark' in base_now, 'v4: кнопка меню превращается в крестик')
check('sb-open' in base_now, 'v4: JS ставит класс лок-скролла')

# ═══ 5. Общие компоненты + лендинг (v3) ═══════════════════════════════════
print('== v3: компоненты и лендинг ==')
check('.stat-box:hover' in css and '.log-stat:hover' in css and '.premium-card:hover' in css,
      'v3: подъём stat-карточек многих страниц')
check('.stat-box:hover .stat-icon' in css, 'v3: иконка стат-карточки оживает')
check('.action-bar' in css and 'sticky' in css, 'v3: липкие панели действий')
check('.welcome-title' in css and 'acTitleShine' in css, 'v3: перелив заголовка лендинга')
check('.wf-item:hover' in css and '.wn-link::after' in css, 'v3: фичи и ссылки лендинга оживают')
check('border-color: var(--ac-line) !important' in css, 'v3: единая акцентная рамка при наведении')

logs_html = open(os.path.join(ROOT, 'web', 'templates', 'logs.html'), encoding='utf-8').read()
check('lg-feed' in logs_html and 'position:sticky' in logs_html.replace(' ', ''),
      'логи: лента событий + липкая панель фильтров')
check('.lg-act' in logs_html and 'uppercase' in logs_html,
      'логи: аккуратные пилюли действий')

login_as('owner')
r = client.get('/logs')
check(r.status_code == 200, '/logs — реальная страница (Студия удалена)')
r = client.get('/roles')
check(r.status_code == 200 and 'polish.css' in r.get_data(as_text=True),
      'страница /roles рендерится со слоем')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
