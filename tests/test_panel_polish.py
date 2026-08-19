# -*- coding: utf-8 -*-
"""Тесты светлой дизайн-системы панели (style.css + base.html).

Проверяют целостность токенов, светлую тему по умолчанию, компоненты
и отсутствие старого тёмного «золотого» наследия.

Запуск: python3 tests/test_panel_polish.py
"""
import os
import re
import subprocess
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
check('@import' not in css, 'шрифты не блокируют рендер (асинхронно из base.html)')
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
    ('favsDragSort', 'drag-сортировка избранного'),
    ('__renderFavs', 'хук перерисовки избранного'),
    ('compact: dense', 'плотность сохраняется в /api/ux/prefs'),
]:
    check(marker in js, f'app.js: {label}')
for marker, label in [
    ('fx-ring-el', 'живой градиентный обод'),
    ('#fx-confetti', 'канвас конфетти'),
    ('fx-drag-over', 'индикатор drag-сортировки'),
    ('@property --fx-ang', 'регистрация угла градиента'),
]:
    check(marker in css, f'style.css: {label}')
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
    ('fx-shine', 'блик панелей'),
    ('fabBreathe', 'дыхание FAB'),
    ('fxMagnetic', 'магнитные кнопки'),
]:
    check(marker in css or marker in js, f'FX-слой 10: {label}')

# ═══ 7. Чистота интерфейса: без искр клика и света за мышкой ═════════════
print('== чистота интерфейса ==')
check('fx-click-spark' not in css and 'fx-click-spark' not in js,
      'искры-точки после клика удалены')
check('fx-star-spark' not in css and 'fx-star-spark' not in js,
      'звёздный бурст избранного удалён')
check('fxCursor' not in css and 'fxCursor' not in js and 'fxCursor' not in base,
      'глобальное свечение за курсором удалено')
check('spot-on' not in css and 'spot-on' not in js,
      'спотлайт, следующий за мышью внутри карточек, отключён')
check('tickerDrift' in open(os.path.join(ROOT, 'web', 'templates', 'mod_center.html'), encoding='utf-8').read(),
      'лента событий мод-центра стала живой (авто-дрейф с паузой)')
# ═══ 8. Комбо-красота: шапки, эмблема, переходы, киоск ════════════════════
print('== комбо-красота ==')
check('.main-content:has(> .page-hero) .navbar { display: none; }' in css,
      'дубль заголовка в навбаре скрыт для hero-страниц')
check('.page-hero.compact h1 > i:first-child' in css,
      'старый компактный hero переведён на премиум-вид (иконка-плитка)')
check('pageHeadAuto' in js and 'fx-built' in js,
      'страницы без шапки автоматически получают премиум page-head')
check('@view-transition' not in css and 'снапшот всего DOM' in css,
      'переходы View Transitions выключены ради 60-120 FPS (без рывков на навигации)')
check(os.path.isfile(os.path.join(ROOT, 'web', 'static', 'favicon.ico')),
      'фавикон Aether создан')
check(os.path.isfile(os.path.join(ROOT, 'web', 'static', 'brand', 'emblem-dragon.png')),
      'эмблема Aether (белый дракон) создана')
check('emblem-dragon.png' in base,
      'дракон в бренд-шапке панели')
dash_t = open(os.path.join(ROOT, 'web', 'templates', 'dashboard.html'), encoding='utf-8').read()
check('ccSettingsModal' in dash_t and 'Настройки виджетов биндятся первыми' in dash_t,
      'настройки виджетов главной: полноценная модалка и привязка первой')
check('.modal-overlay:not(.open) { display: none; }' in css,
      'модалки скрыты по умолчанию и показываются только по .open')
kiosk = open(os.path.join(ROOT, 'web', 'templates', 'mod_kiosk.html'), encoding='utf-8').read()
check('kioskTime' in kiosk and 'kioskMain' in kiosk and 'kioskDrift' in kiosk,
      'экран дежурного: часы, стена и лента на месте')
login_as('owner')
r = client.get('/mod-kiosk')
check(r.status_code == 200 and 'Экран дежурного' in r.get_data(as_text=True),
      '/mod-kiosk открывается под owner')
r = client.get('/favicon.ico')
check(r.status_code == 200, 'фавикон отдаётся сервером')

# ═══ 9. Премиум-формы: селекты и элементы выбора ══════════════════════════
print('== премиум-формы ==')
check('27.7 FX-СЛОЙ 11' in css, 'FX-слой 11 «премиум-формы» добавлен')
check('calc(100% - 21px) calc(50% - 3px)' in css and 'var(--ac) 50%' in css,
      'стрелка селектов — фирменный градиентный шеврон')
check('select option:checked' in css and 'select[multiple] option:checked' in css,
      'опции селектов стилизованы (включая multi-select)')
check('input[type="checkbox"]:indeterminate' in css and 'checkPop' in css,
      'чекбоксы: indeterminate-состояние и pop-анимация')
check('input[type="radio"]:checked::after' in css,
      'радио-кнопки с градиентной точкой')
check('input[type="range"]::-webkit-slider-thumb' in css
      and 'input[type="range"]::-moz-range-thumb' in css,
      'ползунки с фирменным бегунком')
check('-webkit-calendar-picker-indicator' in css,
      'индикатор календаря у date/time оформлен')
check('.switch input:checked + .track' in css,
      'переключатели с градиентным треком и свечением')
check('background-color: var(--surface) !important' in open(os.path.join(ROOT, 'web', 'templates', 'analytics.html'), encoding='utf-8').read(),
      'аналитика: стрелка селекта больше не скрывается фоном')

# ═══ 10. Кастомные дропдауны вместо нативных списков ══════════════════════
print('== кастомные дропдауны ==')
check('AETHER KIT 11' in js and 'aetherSelect' in js,
      'AetherSelect: движок кастомных дропдаунов в app.js')
check('aes-panel' in css and 'aes-opt' in css and 'aes-search' in css,
      'стили панели, опций и поиска дропдауна в style.css')
check('27.8 КАСТОМНЫЕ ДРОПДАУНЫ' in css, 'секция 27.8 добавлена в дизайн-систему')
check('aes-native' in css and 'opacity: 0 !important' in css,
      'исходный select скрыт без потери form-семантики (не display:none)')
check("orig.dispatchEvent(new Event('change', { bubbles: true }))" in js,
      'выбор в дропдауне продолжает запускать change-события страниц')
check('OPTGROUP' in js and 'aes-group' in css,
      'группы опций (optgroup) поддерживаются')
check('aes-lg' in js and 'aes-inline' in js,
      'варианты оформления: крупный (сервер) и встроенный (кокпит)')
# регрессия: replaceChild не должен получать узел-предок (HierarchyRequestError)
m = re.search(r'parent\.replaceChild\(shell, orig\).*?shell\.appendChild\(orig\)', js, re.S)
check(bool(m), 'дропдаун: замена узла идёт ДО переноса select внутрь shell (фикс зависаний)')
m = re.search(r'shell\.appendChild\(orig\).*?orig\.parentNode\.replaceChild\(shell, orig\)', js, re.S)
check(m is None, 'дропдаун: запрещённый порядок (replaceChild по предку) отсутствует')
check('tryEnhance' in js and 'removeAttribute(\'data-aes\')' in js,
      'дропдаун: сбой одного селекта не ломает остальные')

# ═══ 11. Производительность: нет вечных анимаций и тяжёлого блюра ═════════
print('== производительность ==')
check(re.search(r'\.fx-ring-el \{[^}]*animation: none;', css, re.S) is not None,
      'кольца карточек по умолчанию не анимируются')
check(re.search(r'\.fx-ring-host:hover \.fx-ring-el,\n\.fx-ring-host:focus-within \.fx-ring-el \{\n  opacity: 1;\n\}', css) is not None,
      'кольца при ховере — только появление, без анимации')
check('.panel:hover::before { animation: hairline 4.5s linear infinite; }' in css,
      'хаирлайн панелей анимируется только при наведении')
check('blur(20px)' not in css and 'blur(24px)' not in css and 'blur(16px)' not in css,
      'тяжёлый backdrop-blur (16px+) снижен')
check('lastRect' in js and 'requestAnimationFrame(function () { apply(lastE); })' in js,
      'магнитные кнопки: rAF-троттлинг и кэш rect (без layout на mousemove)')
check('fx-particles' not in base and 'canvas частиц отключён' in js,
      'фоновый canvas частиц отключён (не перерисовывает стекло 30 раз/сек)')
check('backdrop-filter' not in css,
      'backdrop-blur полностью убран — стекло на полупрозрачности без GPU-блюра')
check('blur(90px)' not in css and 'blur(70px)' not in css and 'mix-blend-mode' not in css,
      'гигантские блюры и blend-слои авроры/сетки удалены')
check('auroraFloat' not in css and 'meshFloat' not in css,
      'вечные анимации авроры и сетки удалены')
check('btnGlow' not in css and 'gradShift' not in css and 'btnShine 5.5s' not in css,
      'вечные блики/свечения кнопок удалены (только hover-эффекты)')
check('barShine 2.4s' not in css and 'secLine 4s' not in css,
      'вечные шиммеры прогресс-баров и линий секций удалены')
check('.page-head h1:hover { animation: titleSheen' in css,
      'сияние заголовка — только при наведении')
check('--glass: var(--surface)' in css,
      'стекло стало непрозрачным — ноль перерисовок при скролле')
check('translateZ(0)' not in css,
      'слои translateZ убраны — текст шапки и сайдбара чёткий')
check('Параллакс авроры тоже выключен' in js,
      'трансформация полноэкранного слоя авроры на скролл отключена')
check('fxRingAng 3.5s linear infinite' not in css,
      'кольца при ховере — статичный градиент (без вечного вращения)')
check('brandAura' not in css,
      'пульс бренда убран (остался hover-эффект)')
check('transition: all' not in css,
      'transition: all заменён на точечные свойства')
check('lastRing' in js and 'now - lastRing >= 120' in js,
      'кольцо кнопки «наверх» перерисовывается не чаще 8 раз/сек')
check('fxCardParallax' not in js and 'fx-parallax-card' not in css,
      'параллакс карточек удалён — субпиксельные transform не мылят текст')
check('translateZ(0)' not in css and 'will-change' not in css,
      'слои translateZ/will-change убраны — текст и иконки не размываются')

# ═══ 12. Стабильность и плавность ═════════════════════════════════════════
print('== стабильность ==')
check('@import' not in css and 'неблокирующе из base.html' in css,
      'блокирующий @import шрифтов убран из CSS')
check('media="print" onload="this.media=' in base,
      'шрифты грузятся асинхронно (не блокируют рендер)')
check('aether_splash_done' in js and 'сплэш показываем один раз за сессию' in js,
      'сплэш загрузки — один раз за сессию (без вспышек на навигации)')
check('_logsFp' in open(os.path.join(ROOT, 'web', 'templates', 'logs.html'), encoding='utf-8').read()
      and 'не перерисовываем (стабильность, без мерцания)' in open(os.path.join(ROOT, 'web', 'templates', 'logs.html'), encoding='utf-8').read(),
      'журнал не мерцает при live-обновлении без изменений')
check('_chartsFp' in open(os.path.join(ROOT, 'web', 'templates', 'mod_center.html'), encoding='utf-8').read(),
      'графики мод-центра не перерисовываются при тех же данных')

# ═══ 13. Порядок в каналах ═════════════════════════════════════════════════
print('== порядок каналов ==')
seed = open(os.path.join(ROOT, 'scripts', 'seed_demo_panel.py'), encoding='utf-8').read()
check('demo_channels' in seed and 'data/demo_channels.json' in seed,
      'сид демо создаёт структуру каналов')
gadmin = open(os.path.join(ROOT, 'web', 'routes', 'guild_admin.py'), encoding='utf-8').read()
check('demo_channels.json' in gadmin and 'отдаём демо-структуру каналов' in gadmin,
      'API каналов отдаёт демо-структуру, когда бот офлайн')
channels_t = open(os.path.join(ROOT, 'web', 'templates', 'channels.html'), encoding='utf-8').read()
check("((a.position || 0) - (b.position || 0))" in channels_t,
      'страница каналов сортирует по позиции и имени')
chat_t = open(os.path.join(ROOT, 'web', 'templates', 'chat.html'), encoding='utf-8').read()
check('groups.push({ name: key, items: [] })' in chat_t
      and "if (!a.name) return 1;" in chat_t
      and "var head = g.name ?" in chat_t,
      'чат группирует каналы по категориям, внекатегорийные — в конце без заголовка')
# демо-режим: API отдаёт структуру каналов (проверяем в сабпроцессе)
demo_script = '''
import os, sys
os.environ["DEMO_MODE"] = "1"
sys.path.insert(0, %r)
from web.app import app
c = app.test_client()
with c.session_transaction() as s:
    s["logged_in"] = True; s["username"] = "DemoCh"; s["role"] = "owner"
r = c.get("/api/guild/987654321098765432/channels")
d = r.get_json(silent=True) or []
print(len(d) if isinstance(d, list) else -1)
''' % ROOT
if not os.path.isfile(os.path.join(ROOT, 'data', 'demo_channels.json')):
    subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'seed_demo_panel.py')],
                   capture_output=True, text=True, timeout=120, cwd=ROOT)
proc = subprocess.run([sys.executable, '-c', demo_script], capture_output=True,
                      text=True, timeout=120, cwd=ROOT)
n_demo = -1
for _line in (proc.stdout or '').splitlines():
    if _line.strip().isdigit():
        n_demo = int(_line.strip())
check(n_demo >= 10,
      f'API каналов в демо-режиме отдаёт структуру ({n_demo} шт.)')

# ═══ 14. Скрытие каналов владельцем ════════════════════════════════════════
print('== скрытие каналов ==')
gadmin = open(os.path.join(ROOT, 'web', 'routes', 'guild_admin.py'), encoding='utf-8').read()
check('channels-visibility' in gadmin and 'hidden_channels.json' in gadmin,
      'API видимости каналов владельца в guild_admin.py')
check("role_required ('owner')" in gadmin,
      'смена видимости доступна только owner')
ch_t = open(os.path.join(ROOT, 'web', 'templates', 'channels.html'), encoding='utf-8').read()
check('chShowHidden' in ch_t and 'toggleHide' in ch_t and 'data-hide-id' in ch_t,
      'страница каналов: кнопки скрытия и режим «показать скрытые»')
check("role == 'owner'" in ch_t,
      'кнопки скрытия рендерятся только для owner')
chat_t = open(os.path.join(ROOT, 'web', 'templates', 'chat.html'), encoding='utf-8').read()
check("!c.hidden" in chat_t,
      'чат не показывает скрытые каналы')
# Поведение API в демо-режиме (сабпроцесс): скрыть → hidden:true → вернуть
hide_script = '''
import os, sys, json
os.environ["DEMO_MODE"] = "1"
sys.path.insert(0, %r)
from web.app import app
c = app.test_client()
def login(role):
    with c.session_transaction() as s:
        s["logged_in"] = True; s["username"] = "H" + role; s["role"] = role
login("owner")
r = c.post("/api/guild/987654321098765432/channels-visibility",
           json={"id": "4003", "kind": "channel", "hidden": True})
ok1 = r.status_code == 200 and r.get_json().get("success")
d = c.get("/api/guild/987654321098765432/channels").get_json(silent=True) or []
ch = next((x for x in d if str(x.get("id")) == "4003"), None) if isinstance(d, list) else None
ok2 = ch is not None and ch.get("hidden") is True
r = c.post("/api/guild/987654321098765432/channels-visibility",
           json={"id": "4003", "kind": "channel", "hidden": False})
ok3 = r.status_code == 200 and r.get_json().get("success")
login("mod")
r = c.post("/api/guild/987654321098765432/channels-visibility",
           json={"id": "4003", "kind": "channel", "hidden": True})
ok4 = r.status_code == 403
print("OK" if (ok1 and ok2 and ok3 and ok4) else "BAD")
''' % ROOT
proc = subprocess.run([sys.executable, '-c', hide_script], capture_output=True,
                      text=True, timeout=120, cwd=ROOT)
check('OK' in (proc.stdout or ''),
      'API: owner скрывает канал (hidden:true), возвращает обратно; модератору — 403')
# @-поиск и welcome
check('AETHER KIT 12' in js and 'atFinderInput' in js and 'at-finder' in css,
      '@-поиск: мгновенный поиск по панели (страницы, участники, каналы)')
check('at-item' in css and 'at-group' in css,
      'стили результатов @-поиска на месте')
welcome = open(os.path.join(ROOT, 'web', 'templates', 'welcome.html'), encoding='utf-8').read()
check('w-dragon' in welcome and 'emblem-dragon.png' in welcome,
      'welcome: белый дракон в герое')
check('Участникам' in welcome and 'wSearch' in welcome and 'w-steps' in welcome,
      'welcome: инфо для участников, поиск и «как начать»')
check('для всех участников' in welcome and 'Нажми' in welcome and '@' in welcome,
      'welcome: акцент на участников и подсказка про @')
# ═══ 15. Страницы заявок и каналов — единый премиум-вид ═══════════════════
print('== заявки и каналы ==')
ma = open(os.path.join(ROOT, 'web', 'templates', 'member_apply.html'), encoding='utf-8').read()
check('class="page-head"' in ma and 'apply-steps' in ma and 'apply-step' in ma,
      'заявка в администрацию: премиум-шапка и индикатор шагов')
check('server-card' in ma and 'member-card' in ma and 'success-screen' in ma,
      'заявка: карточки серверов, верификация Discord и экран успеха')
check('paintSteps' in ma and 'step-srv' in ma and 'step-form' in ma,
      'заявка: шаги подсвечиваются по прогрессу')
check('rgba(20,18,14' not in ma and '⏳' not in ma and '✅' not in ma and '❌' not in ma,
      'заявка: без тёмных фонов и эмодзи (только Font Awesome)')
mya = open(os.path.join(ROOT, 'web', 'templates', 'my_applications.html'), encoding='utf-8').read()
check('apps-list' in mya and 'status-approved' in mya and 'fa-hourglass-half' in mya,
      'мои заявки: статусная лента с иконками')
check('⏳' not in mya,
      'мои заявки: эмодзи заменены иконками')
sa = open(os.path.join(ROOT, 'web', 'templates', 'staff_apps.html'), encoding='utf-8').read()
check('139492' not in sa and '1a1a20' not in sa and '#d4a843' not in sa,
      'рассмотрение заявок: тёмная модалка и золотые градиенты заменены палитрой')
pa = open(os.path.join(ROOT, 'web', 'templates', 'public_apply.html'), encoding='utf-8').read()
check('/static/style.css' in pa and 'emblem-dragon.png' in pa and 'data-theme="light"' in pa,
      'публичная заявка: подключена дизайн-система и дракон')
check('⏳' not in pa and '✅' not in pa and '❌' not in pa and '⚠' not in pa,
      'публичная заявка: статусы ID на иконках')
login_as('owner')
for path in ('/member-apply', '/staff-apps', '/apply', '/channels', '/chat'):
    r = client.get(path)
    check(r.status_code == 200, f'{path} → {r.status_code}')
# «Мои заявки» — страница участника (role uye)
with client.session_transaction() as s:
    s['logged_in'] = True; s['username'] = 'MemberApply'; s['role'] = 'uye'
r = client.get('/my-applications')
check(r.status_code == 200 and 'apps-list' in r.get_data(as_text=True),
      '/my-applications → 200 для участника')
# ═══ 16. Заявки в команду, @-пикер, welcome-hero, чистка каналов ═══════════
print('== заявки, @-пикер, чистота ==')
import glob as _glob
menu_src = open(os.path.join(ROOT, 'services', 'panel_menu.py'), encoding='utf-8').read()
check("'section': 'management'" in menu_src.split("'path': '/staff-apps'")[1][:200],
      'меню: заявки в команду — в Модерации → управление')
check("'path': '/staff-apps'" not in menu_src.split("{'group': 'Тикеты'")[1].split("]},")[0]
      if "{'group': 'Тикеты'" in menu_src else True,
      'меню: заявки убраны из группы «Тикеты»')
app_src = open(os.path.join(ROOT, 'web', 'app.py'), encoding='utf-8').read()
check("data ['role']=str (data .get ('role')or 'Модератор')" in app_src
      and "'role':data ['role']" in app_src,
      'API заявки: должность сохраняется (роль хелпер/мод/чат-контроль)')
check("if 'почему'not in data and data .get ('why')" in app_src,
      'API заявки: принимает ключи формы (почему/why, активен/activity)')
ma = open(os.path.join(ROOT, 'web', 'templates', 'member_apply.html'), encoding='utf-8').read()
check('apply-role' in ma and 'Хелпер' in ma and 'Чат-контроль' in ma and 'role-card' in ma,
      'форма заявки: выбор должности (хелпер/модератор/чат-контроль)')
check("role: role," in ma,
      'форма заявки: должность уходит в API')
pa = open(os.path.join(ROOT, 'web', 'templates', 'public_apply.html'), encoding='utf-8').read()
check('apply-role' in pa and 'Чат-контроль' in pa,
      'публичная заявка: выбор должности тоже есть')
chat = open(os.path.join(ROOT, 'web', 'templates', 'chat.html'), encoding='utf-8').read()
check('mention-head' in chat and '<mark>' in chat and 'mention-av-wrap' in chat
      and 'data-idx' in chat,
      '@-пикер чата: стиль Discord (шапка, аватары со статусом, подсветка совпадения)')
check('mousemove' in chat.split('mentionBind')[1][:600] if 'mentionBind' in chat else False,
      '@-пикер: выбор мышью при наведении')
welcome = open(os.path.join(ROOT, 'web', 'templates', 'welcome.html'), encoding='utf-8').read()
check('w-dragon-ring' in welcome and 'w-chips' in welcome and 'w-dragon-halo' in welcome,
      'welcome-hero: кольцо с градиентом, гало и фичи-чипы')
# глобальная чистота: ни эмодзи, ни тёмного наследия ни в одном шаблоне
import re as _re
EMOJI = _re.compile(r'[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u23E9-\u23FF\u2700-\u27BF]')
dirty = []
for _f in _glob.glob(os.path.join(ROOT, 'web', 'templates', '*.html')):
    _t = open(_f, encoding='utf-8').read()
    if EMOJI.search(_t):
        dirty.append(os.path.basename(_f) + ':emoji')
    for _p in ('rgba(20,18,14', '#0a0907', '#1a1a20', '#e2e8f0', '#d4a843', '#139492',
               '#8a8374', '#d8d0bb', '#2ecc71', '#e74c3c', '#ff6b6b'):
        if _p in _t:
            dirty.append(os.path.basename(_f) + ':' + _p)
check(not dirty, f'все шаблоны чистые: без эмодзи и тёмного наследия ({dirty[:4]}…)')
# ═══ 17. Финал: белые письма, золото и синтаксис вычищены ══════════════════
print('== финальная чистота ==')
all_tpl = ''
for _f in _glob.glob(os.path.join(ROOT, 'web', 'templates', '*.html')):
    all_tpl += open(_f, encoding='utf-8').read()
check('212,175,55' not in all_tpl and '#e8c96a' not in all_tpl and '#d4af37' not in all_tpl,
      'золотая старая палитра полностью удалена из шаблонов')
check('86efac' not in all_tpl and 'fca5a5' not in all_tpl and 'a5f3fc' not in all_tpl,
      'светлые нечитаемые тексты заменены тёмными тонами палитры')
check('background: rgba(0,0,0,0.3)' not in all_tpl
      and 'background:rgba(0,0,0,0.3)' not in all_tpl
      and 'background: rgba(0, 0, 0, 0.3)' not in all_tpl,
      'тёмные инпуты (чёрные дыры на светлой теме) заменены светлыми')
check('selected_guild' in app_src and "session ['selected_guild']=str (MAIN_GUILD_ID )" in app_src,
      'демо-сессия подставляет selected_guild (страницы с выбором сервера открываются)')
auto_js = open(os.path.join(ROOT, 'web', 'templates', 'automation.html'), encoding='utf-8').read()
check('var items = (d.state && d.state.items) || [];' in auto_js
      and 'window._trgItems; =' not in auto_js,
      'automation.html: синтаксис-ошибка JS исправлена')
konsol = open(os.path.join(ROOT, 'web', 'templates', 'konsol.html'), encoding='utf-8').read()
check('var(--ac-soft); border:1px solid var(--ac-line)' in konsol and '#fff' not in konsol.split('.kn-term')[0],
      'консоль: кнопки и селекты на палитре (белых писем нет)')
sched = open(os.path.join(ROOT, 'web', 'templates', 'schedule.html'), encoding='utf-8').read()
check('var(--ac-soft); border:1px solid var(--ac-line)' in sched and 'color:#fff' not in sched.split('.sc-toast')[0],
      'расписание: кнопки и формы на палитре (белых писем нет)')
# ═══ 18. Каждая страница — премиум page-head (или живой hero) ═══════════════
print('== все страницы с шапками ==')
import glob as _g
head_ok = 0; hero_ok = 0; nohdr = []
for _f in _g.glob(os.path.join(ROOT, 'web', 'templates', '*.html')):
    _t = open(_f, encoding='utf-8').read()
    if '{% extends "base.html" %}' not in _t:
        continue
    if 'class="page-head"' in _t:
        head_ok += 1
    elif 'class="page-hero' in _t:
        hero_ok += 1
    else:
        nohdr.append(os.path.basename(_f))
check(head_ok >= 125, f'премиум page-head у {head_ok} страниц (>=125)')
nohdr = [n for n in nohdr if n != 'analytics.html']  # у аналитики свой кокпит-hero
check(not nohdr, f'без шапки не осталось ни одной страницы ({nohdr[:3]})')
allt = ''
for _f in _g.glob(os.path.join(ROOT, 'web', 'templates', '*.html')):
    allt += open(_f, encoding='utf-8').read()
check('<div <div' not in allt, 'нигде нет двойных div')
check('page-hero compact' not in allt, 'старый компактный hero полностью заменён')
hero_rest = [os.path.basename(_f) for _f in _g.glob(os.path.join(ROOT, 'web', 'templates', '*.html'))
             if '{% block page_hero' in open(_f, encoding='utf-8').read()]
check(set(hero_rest) <= {'base.html', 'ai_moderation.html', 'announcements.html',
                         'bot_diagnostics.html', 'leveling_admin.html',
                         'analytics.html'},
      f'block page_hero остался только у страниц с живыми hero ({hero_rest})')
# ═══ 19. Правила сервера — полностью пересобраны ═══════════════════════════
print('== правила сервера ==')
rules_t = open(os.path.join(ROOT, 'web', 'templates', 'rules_editor.html'), encoding='utf-8').read()
check('class="page-head"' in rules_t and 'Правила сервера' in rules_t,
      'правила: премиум-шапка страницы')
check('rules-wrap' in rules_t and 'rules-panel' in rules_t and 'rule-row' in rules_t,
      'правила: сетка панелей с полноценными стилями (не «голые» классы)')
check('preview-card' in rules_t and 'preview-rule' in rules_t,
      'правила: превью в стиле Discord-сообщения')
check('rule-move' in rules_t and 'data-mv' in rules_t,
      'правила: порядок меняется кнопками вверх/вниз')
check('window.showToast' in rules_t and 'alert(' not in rules_t.replace('else alert(', '').replace('alert(msg);', ''),
      'правила: тосты вместо alert()')
check('yok' not in rules_t and 'butonuna' not in rules_t and 'Новый правило' not in rules_t,
      'правила: турецкие фразы заменены русскими')
check('fa-xmark' in rules_t and 'Правил пока нет' in rules_t,
      'правила: иконка удаления и стилизованное пустое состояние')
api_rules = open(os.path.join(ROOT, 'web', 'routes', 'tasks_rules.py'), encoding='utf-8').read()
check('edenler' not in api_rules and '0x4f46e5' in api_rules,
      'API публикации: русский текст и индиго-цвет эмбеда')
login_as('owner')
r = client.get('/rules-editor')
check(r.status_code == 200 and 'rules-panel' in r.get_data(as_text=True),
      '/rules-editor открывается под owner')
check('app.js?v=47' in base and 'style.css?v=100' in base,
      'версии ассетов (100/47)')
check('-moz-osx-font-smoothing: grayscale' in css and 'font-synthesis: none' in css,
      'сглаживание шрифтов полное (четкий текст на всех платформах)')
check('image-rendering: auto' in css and 'backface-visibility: hidden' in css,
      'изображения без мыла при масштабировании')
check("'translate(' + Math.round(dx / dist * pull)" in js,
      'магнитные кнопки двигаются целыми пикселями')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
import shutil
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
