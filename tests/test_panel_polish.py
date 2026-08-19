# -*- coding: utf-8 -*-
"""Тесты светлой дизайн-системы панели (style.css + base.html).

Проверяют целостность токенов, светлую тему по умолчанию, компоненты
и отсутствие старого тёмного «золотого» наследия.

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


# ═══ 1. Файл дизайн-системы: целостность ═════════════════════════════════
print('== style.css ==')
css_path = os.path.join(ROOT, 'web', 'static', 'style.css')
check(os.path.isfile(css_path), 'style.css существует')
css = open(css_path, encoding='utf-8').read()
check(css.count('{') == css.count('}'), f'сбалансированные скобки ({css.count("{{")} пар)')
check('/*' in css and '*/' in css and css.count('/*') == css.count('*/'),
      'комментарии закрыты корректно')
check('@import' in css, 'шрифты подключаются из style.css')
check(len(css) > 20000, f'дизайн-система содержательная ({len(css)} символов)')

# Светлая тема по умолчанию и тёмная как опция
check(':root {' in css and '--bg: #f5f6f8' in css, 'светлая тема — корневые токены')
check('[data-theme="dark"]' in css, 'тёмная тема остаётся опцией')
for token in ('--surface', '--line', '--text', '--ac', '--ok', '--warn', '--err',
              '--shadow-1', '--r-lg', '--sidebar-w', '--fs-md'):
    check(token in css, f'токен {token} определён')
check('--ac: #4f46e5' in css or '--ac:#4f46e5' in css, 'акцент — индиго')

# Ключевые компоненты
for marker, label in [
    ('.app-shell', 'каркас приложения'),
    ('.sidebar', 'сайдбар'),
    ('.nav-subgroup', 'подгруппы модерации'),
    ('.page-head', 'заголовок страницы'),
    ('.kpi', 'KPI-карточки'),
    ('.panel', 'панели-карточки'),
    ('.data-table', 'таблицы данных'),
    ('.toolbar', 'тулбары фильтров'),
    ('.kbd-palette', 'палитра Ctrl+K'),
    ('.drawer', 'дроверы'),
    ('.toast', 'тосты'),
    ('.switch', 'переключатели'),
    ('.chip', 'чипы'),
    ('.modal-overlay', 'модальные окна'),
    ('.empty', 'пустые состояния'),
    ('::selection', 'акцентное выделение текста'),
    (':focus-visible', 'видимый фокус с клавиатуры'),
    ('prefers-reduced-motion', 'уважение к reduced motion'),
]:
    check(marker in css, f'CSS содержит: {label}')

# Работа через токены: никаких жёстких «золотых» констант старой темы
check('#e0b04a' not in css and 'gold' not in css.split('/*')[0],
      'старый золотой акцент удалён из дизайн-системы')
check('color-mix' in css, 'color-mix используется для производных оттенков')
check('var(--ac' in css and 'var(--text' in css, 'работа через токены темы')

# Старое наследие удалено
for dead in ('.ops-canvas', '.mod-suite', '.ops-room-label', '.tm-tab',
             '.bg-ambient', 'welcome-screen', '.mod-command-room'):
    check(dead not in css, f'старый терминальный стиль удалён: {dead}')

# ═══ 2. base.html подключает дизайн-систему ══════════════════════════════
print('== base.html ==')
base = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('/static/style.css' in base, 'base.html ссылается на style.css')
for dead in ('polish.css', 'moderation-suite.css', 'moderation-rooms.css',
             'quality-suite.css'):
    check(dead not in base, f'старый слой {dead} отключён')
check('data-theme="light"' in base, 'светлая тема применяется до отрисовки')

# ═══ 3. Страницы рендерятся с новой системой ═════════════════════════════
print('== страницы ==')
from web.app import app as _flask_app  # noqa: E402

client = _flask_app.test_client()


def login_as(role):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'PanelPolish'
        s['role'] = role


r = client.get('/static/style.css')
check(r.status_code == 200 and ('text/css' in (r.headers.get('Content-Type') or '') or 'stylesheet' in (r.headers.get('Content-Type') or '')),
      f'style.css отдаётся статикой ({r.status_code})')
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
    ok = 'style.css' in page and 'app.js' in page
    if ok:
        rendered += 1
    check(ok, f'{path}: 200, дизайн-система и кит подключены')
check(rendered == 5, 'все контрольные страницы отрендерились с новой системой')

# ═══ 4. Дашборд и логин: новая светлая подача ════════════════════════════
print('== дашборд и логин ==')
dash = open(os.path.join(ROOT, 'web', 'templates', 'dashboard.html'), encoding='utf-8').read()
check('class="page-hero"' in dash and 'class="kpi-row"' in dash,
      'дашборд использует компоненты дизайн-системы')
check('.stat-card-big' not in dash and '--ac-glow' not in dash,
      'старый тёмный дашборд с золотыми бликами удалён')
login = open(os.path.join(ROOT, 'web', 'templates', 'login.html'), encoding='utf-8').read()
check('auth-card' in login and 'data-theme="light"' in login,
      'логин — светлая карточка')
check('#0a0907' not in login, 'тёмный фон старого логина удалён')

login_as('owner')
r = client.get('/')
check(r.status_code == 200 and 'Обзор сервера' in r.get_data(as_text=True),
      'главная страница открывается в новом виде')

# ═══ 5. Чат и FX-слой 9 ══════════════════════════════════════════════════
print('== чат и FX-слой 9 ==')
chat = open(os.path.join(ROOT, 'web', 'templates', 'chat.html'), encoding='utf-8').read()
check('--ac-soft' in chat and 'var(--surface)' in chat,
      'чат переведён на токены светлой дизайн-системы')
check('#d8d0bb' not in chat and '#0a0907' not in chat and '#e0b04a' not in chat,
      'старое тёмно-золотое наследие из чата удалено')
check('class="page-head"' in chat, 'у чата появился заголовок страницы')
for hook in ('guild-bar', 'chat-input', 'members-scroll', 'etiket-popup', 'profs-popup'):
    check('id="%s"' % hook in chat, f'хук JS сохранён: {hook}')
check(bool(re.search(r'[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]', chat)) is False,
      'в шаблоне чата нет эмодзи')
login_as('owner')
r = client.get('/chat')
check(r.status_code == 200 and 'chat-wrap' in r.get_data(as_text=True),
      '/chat открывается под owner с новой вёрсткой')
js = open(os.path.join(ROOT, 'web', 'static', 'app.js'), encoding='utf-8').read()
for marker, label in [
    ('fxEntranceConfetti', 'конфетти при входе'),
    ('fxCardParallax', 'параллакс карточек'),
    ('favsDragSort', 'drag-сортировка избранного'),
    ('__renderFavs', 'хук перерисовки избранного'),
    ('compact: dense', 'плотность сохраняется в /api/ux/prefs'),
]:
    check(marker in js, f'app.js: {label}')
for marker, label in [
    ('fx-ring-el', 'живой градиентный обод'),
    ('fx-parallax-card', 'класс параллакса'),
    ('#fx-confetti', 'канвас конфетти'),
    ('fx-drag-over', 'индикатор drag-сортировки'),
    ('@property --fx-ang', 'регистрация угла градиента'),
]:
    check(marker in css, f'style.css: {label}')
check('app.js?v=30' in base and 'style.css?v=84' in base,
      'версии ассетов забумплены (84/30)')

# ═══ 6. Аналитика и FX-слой 10 ═══════════════════════════════════════════
print('== аналитика и FX-слой 10 ==')
an = open(os.path.join(ROOT, 'web', 'templates', 'analytics.html'), encoding='utf-8').read()
check('#11131c' not in an and '#0b0d13' not in an and '#10121a' not in an,
      'тёмный кокпит аналитики переведён на светлую систему')
check('var(--ac-line)' in an and 'color-mix(in srgb, var(--ac)' in an,
      'аналитика использует токены панели')
login_as('owner')
r = client.get('/analytics')
check(r.status_code == 200 and 'analytics-cockpit' in r.get_data(as_text=True),
      '/analytics открывается под owner')
check('analytics-cockpit' in an and 'window.__analytics' in an,
      'хуки JS аналитики сохранены')
for marker, label in [
    ('fx-scroll-progress', 'полоса прогресса прокрутки'),
    ('fx-topbtn', 'кнопка «наверх» с кольцом'),
    ('fx-click-spark', 'искры клика'),
    ('fx-shine', 'блик панелей'),
    ('fx-star-spark', 'звёздный бурст избранного'),
    ('fabBreathe', 'дыхание FAB'),
    ('fxMagnetic', 'магнитные кнопки'),
]:
    check(marker in css or marker in js, f'FX-слой 10: {label}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
import shutil
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
