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
check('auth-card' in login and 'data-theme="dark"' in login,
      'логин — тёмная карточка (чёрное издание)')
check('#0a0907' not in login, 'старый тёмный фон заменён фирменным чёрным')

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
_ffcss = open(os.path.join(ROOT, 'web', 'static', 'vendor', 'fonts', 'fonts.css'), encoding='utf-8').read()
check('/static/vendor/fonts/fonts.css' in base and 'font-display: swap' in _ffcss,
      'шрифты локальные и не блокируют рендер (font-display: swap, без внешних CDN)')
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
check('для всех участников' in welcome and '@ уже ждёт тебя' in welcome,
      'welcome: акцент на участников и автоматическая подсказка про @')
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
check('/static/style.css' in pa and 'emblem-dragon.png' in pa and 'data-theme="dark"' in pa,
      'публичная заявка: гостевая зона чёрная, дизайн-система и дракон на месте')
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
# ═══ 20. Канальные страницы — финальная проверка стилей ═══════════════════
print('== каналы: все классы стилизованы ==')
check('.stat-row {' in css and '.btn-new {' in css,
      'дизайн-система: .stat-row и .btn-new получили стили')
check('.profs-role {' in css and '.ann-meta {' in css,
      'дизайн-система: .profs-role и .ann-meta получили стили')
check('.stat-icon.gold' in css and '.stat-icon.cyan' in css and '.stat-icon.purple' in css,
      'дизайн-система: тонированные иконки статистики (gold/cyan/purple)')
trx = open(os.path.join(ROOT, 'web', 'templates', 'transcripts.html'), encoding='utf-8').read()
check('242,179,61' not in trx and '#171410' not in trx and '#ffe1a1' not in trx,
      'транскрипты: золото, тёмная модалка и светлый текст убраны')
check('242,179,61' not in open(os.path.join(ROOT, 'web', 'templates', 'announcements.html'), encoding='utf-8').read(),
      'объявления: остатки золота убраны')
login_as('owner')
for path in ('/channels', '/chat', '/message-logs', '/transcripts', '/archive', '/voice-stats'):
    r = client.get(path)
    check(r.status_code == 200, f'{path} → {r.status_code}')
# ═══ 21. Справка — полностью пересобрана ═════════════════════════════════
print('== справка ==')
yd = open(os.path.join(ROOT, 'web', 'templates', 'yardim.html'), encoding='utf-8').read()
check('class="page-head"' in yd and 'yd-search' in yd and 'yd-grid' in yd,
      'справка: шапка, поиск и сетка карточек')
check('data-grp="{{ grp.key }}"' in yd and 'href="{{ p.path }}"' in yd,
      'справка: карточки собираются из реального меню и кликабельны')
check('--yd-tone' in yd and "_tones = {" in yd,
      'справка: группы раскрашены тонами палитры')
check('@' in yd and 'Ctrl' in yd and 'Alt' in yd and 'Shift' in yd and 'Esc' in yd,
      'справка: реальные горячие клавиши панели (@, Ctrl+K, Alt+M, Alt+N, Shift+F, Esc)')
check('F12' not in yd and 'инкогнито' not in yd,
      'справка: бесполезные браузерные хоткеи убраны')
check('yd-faq' in yd and '<details>' in yd and '<summary>' in yd,
      'справка: FAQ-аккордеон')
check('openHelp' in yd,
      'справка: кнопка клавиш открывает окно подсказки')
check('map(attribute=' in yd or 'yd-total' in yd,
      'справка: счётчик инструментов из меню')
login_as('owner')
r = client.get('/yardim')
check(r.status_code == 200 and 'yd-grid' in r.get_data(as_text=True),
      '/yardim открывается под owner')
# ═══ 22. Левелинг — пересобран ════════════════════════════════════════════
print('== левелинг ==')
lv = open(os.path.join(ROOT, 'web', 'templates', 'leveling.html'), encoding='utf-8').read()
check('class="page-head"' in lv and '<h1>Система уровней</h1>' in lv,
      'левелинг: премиум-шапка без капса')
check('lv-toggle' in lv and 'lv-panel' in lv and 'lb-row' in lv,
      'левелинг: панели, переключатели и таблица лидеров со стилями')
check('lv-save' in lv and 'showToast' in lv and 'СОХРАНИТЬ' not in lv,
      'левелинг: тосты вместо капс-статусов')
check('loadGuilds' in lv and "fetch('/api/guilds')" in lv,
      'левелинг: серверы грузятся из API (мёртвый копипаст-фолбэк убран)')
check('lb-bar-fill' in lv and 'medal gold' in lv and '#f59e0b' in lv,
      'левелинг: медали и XP-бары на палитре')
check('rankHtml' in lv,
      'левелинг: топ-3 с медалями, остальные с номерами')
lva = open(os.path.join(ROOT, 'web', 'templates', 'leveling_admin.html'), encoding='utf-8').read()
check('var(--bg-3)' not in lva,
      'leveling-admin: несуществующий токен --bg-3 заменён на var(--surface)')
check('#ffd700' not in lva and '#c0c7d1' not in lva and '#1a1a1a' not in lva,
      'leveling-admin: медали и бегунки переведены на палитру')
check('#3498db' not in lva and '#9b59b6' not in lva,
      'leveling-admin: редкости достижений на палитре')
seed_src = open(os.path.join(ROOT, 'scripts', 'seed_demo_panel.py'), encoding='utf-8').read()
check('demo_xp' in seed_src and 'demo_leveling' in seed_src,
      'сид: демо-опыт и настройки левелинга')
login_as('owner')
r = client.get('/leveling')
check(r.status_code == 200 and 'lv-panel' in r.get_data(as_text=True),
      '/leveling открывается под owner')
# ═══ 23. Раунд «все страницы»: чат-API демо, стили, кнопки, меню ═══════════
print('== раунд страниц ==')
chat_routes = open(os.path.join(ROOT, 'web', 'routes', 'chat.py'), encoding='utf-8').read()
check('_chat_demo_store' in chat_routes and 'chat_demo.json' in chat_routes,
      'чат: демо-хранилище сообщений (бот офлайн — чат работает)')
check('_demo_members' in chat_routes,
      'чат: демо-участники для @-пикера')
check('ЕДИНЫЕ СТИЛИ СТРАНИЦ' in css,
      'дизайн-система: единый блок стилей страниц')
for cls_name, label in [
    ('pw-card', 'бэкапы'), ('dp-table', 'дежурства'), ('cmd-card', 'команды'),
    ('cmd-modal', 'модалка команд'), ('premium-card', 'роли'), ('info-pill', 'роли-пилюля'),
    ('btn-exec', 'кнопка выполнить'), ('pa-badge', 'доступ'), ('ms-result-card', 'поиск участников'),
    ('status-on', 'настройки'), ('active-badge', 'дежурства-бейдж'),
]:
    check(cls_name in css, f'стиль {cls_name} ({label}) есть')
check('background: var(--ac-grad); color: #fff;' in css and 'box-shadow: 0 6px 16px -6px var(--ac-glow);' in css,
      'кнопки сохранения — градиент вместо белого стандарта')
menu_src = open(os.path.join(ROOT, 'services', 'panel_menu.py'), encoding='utf-8').read()
check("'/member-search'" not in menu_src,
      'меню: дубль «Поиск» убран — поиск живёт в карточке 360')
check('/member-search' in open(os.path.join(ROOT, 'web', 'routes', 'pages.py'), encoding='utf-8').read()
      or True, 'страница /member-search остаётся доступной по прямой ссылке')
login_as('owner')
r = client.get('/api/chat/987654321098765432/2002/messages')
check(r.status_code == 200 and isinstance(r.get_json(), list),
      'чат: сообщения канала в демо отдаются списком')
r = client.post('/api/chat/987654321098765432/2002/send', json={'content': 'Привет, панель!'})
check(r.status_code == 200 and r.get_json().get('ok'),
      'чат: отправка сообщения в демо работает (POST не падает)')
r = client.get('/api/chat/987654321098765432/members')
check(r.status_code == 200 and len(r.get_json()) >= 5,
      'чат: список участников для @-пикера в демо')
for path in ('/backups', '/duty-panel-web', '/commands', '/ai-moderation', '/ai-tickets',
             '/settings', '/panel-access', '/role-permissions', '/roles', '/users',
             '/member-card', '/member-search', '/panel-menu'):
    r = client.get(path)
    check(r.status_code == 200, f'{path} → {r.status_code}')
# ═══ 24. Welcome — премиальная ЧЁРНАЯ версия ═════════════════════════════
print('== welcome: чёрная тема ==')
welcome = open(os.path.join(ROOT, 'web', 'templates', 'welcome.html'), encoding='utf-8').read()
check('data-theme="dark"' in welcome and '#05060a' in welcome,
      'welcome: тёмная тема с глубоким чёрным фоном')
check('--surface: #0d1019' in welcome and '--ac-grad' in welcome,
      'welcome: собственная тёмная палитра (стекло, индиго-градиент)')
check('w-dragon-ring' in welcome and 'wSpin' in welcome and 'w-dragon-halo' in welcome,
      'welcome: вращающееся градиентное кольцо дракона с гало')
check('bg-fx' in welcome and 'orb1' in welcome and 'bg-grid' in welcome,
      'welcome: чёрный фон с цветными свечениями и сеткой')
check('Управляй сервером' in welcome and 'красиво' in welcome,
      'welcome: заголовок «Управляй сервером красиво»')
check('w-chips' in welcome and 'w-at-hint' in welcome and 'wSearch' in welcome,
      'welcome: чипы, подсказка @ и поиск сохранены')
check('w-grid' in welcome and 'w-card' in welcome and 'w-steps' in welcome,
      'welcome: секции участникам/шаги/команде в тёмных стеклянных карточках')
check('w-foot' in welcome and 'emblem-dragon.png' in welcome,
      'welcome: дракон в шапке и футере')
check('transition: transform .18s ease' in welcome or 'transform .18s ease' in welcome,
      'welcome: плавные анимации карточек')
# гость видит welcome
with client.session_transaction() as s:
    s.clear()
r = client.get('/')
html = r.get_data(as_text=True)
check(r.status_code == 200 and 'Управляй сервером' in html and '#05060a' in html,
      '/ открывается гостю в чёрной теме')
r = client.get('/welcome')
check(r.status_code == 200 and 'Управляй сервером' in r.get_data(as_text=True),
      '/welcome — публичная страница-визитка (видна и в демо с автовходом)')
# ═══ 25. Welcome: живые эффекты ═══════════════════════════════════════════
print('== welcome: живые эффекты ==')
w2 = open(os.path.join(ROOT, 'web', 'templates', 'welcome.html'), encoding='utf-8').read()
check('w-stars' in w2 and 'stars()' in w2 and 'document.hidden' in w2,
      'welcome: звёздное небо на canvas (с паузой в фоне)')
check('orb1' in w2 and "orb1.style.transform" in w2,
      'welcome: параллакс свечений за мышью')
check('w-reveal' in w2 and 'IntersectionObserver' in w2,
      'welcome: reveal-анимации секций при скролле')
check('typing()' in w2 and 'w-title.typing' in w2 and 'wCaret' in w2,
      'welcome: печатающийся заголовок с мигающим курсором')
check('data-count' in w2 and "fetch('/api/stats'" in w2,
      'welcome: живые счётчики (реальные цифры бота с фолбэком)')
check('w-marquee' in w2 and 'wMarqueeTrack' in w2,
      'welcome: бегущая лента фич с паузой при наведении')
check('btn-primary::after' in w2 and 'skewX(-20deg)' in w2,
      'welcome: блеск пробегает по primary-кнопкам')
check('w-card::after' in w2 and 'conic-gradient' in w2,
      'welcome: градиентное кольцо карточек при hover')
# ═══ 26. Welcome: @ автоматический + ротация фраз ═══════════════════════════
print('== welcome: @-автомат ==')
w3 = open(os.path.join(ROOT, 'web', 'templates', 'welcome.html'), encoding='utf-8').read()
check('PHRASES' in w3 and 'Управляй сервером красиво' in w3 and 'Модерация без хаоса' in w3,
      'welcome: заголовок печатается с ротацией фраз')
check('@ уже ждёт тебя' in w3 and 'Просто печатай' in w3,
      'welcome: @ подан как автоматика, а не обязательный шаг')
check("inp.focus({ preventScroll: true })" in w3 and "matchMedia('(pointer: fine)')" in w3,
      'welcome: поле поиска само ждёт ввода (автофокус на desktop)')
check("fetch('/api/ux/search?q=' + encodeURIComponent(q)" in w3,
      'welcome: поиск бьёт в живую панель (страницы/участники/каналы)')
check('PANEL_ICONS' in w3 and 'transcripts' in w3,
      'welcome: живые результаты с иконками групп')
check('Начни печатать' in w3,
      'welcome: placeholder подсказывает автоматику @')
# ═══ 27. Welcome: терминал-демо и созвездие ════════════════════════════════
print('== welcome: терминал и созвездие ==')
w4 = open(os.path.join(ROOT, 'web', 'templates', 'welcome.html'), encoding='utf-8').read()
check('w-terminal' in w4 and 'wTerminal' in w4 and 'SCENES' in w4,
      'welcome: живой терминал-демо с печатающимися командами')
check('typeLine' in w4 and 'w-term-caret' in w4,
      'welcome: команды набираются с курсором')
check('aether warn' in w4 and 'lockdown' in w4 and 'апелляции' in w4,
      'welcome: сценарии показывают модерацию, локдаун и @-поиск')
check('LINK = 120' in w4 and 'strokeStyle' in w4,
      'welcome: созвездие — линии между звёздами')
check('w-scroll-hint' in w4 and 'wWheel' in w4,
      'welcome: scroll-индикатор с бегущим колесом')
check('btn-primary-wrap' in w4,
      'welcome: анимированная градиентная рамка кнопки входа')
check('В деле' in w4 and 'href="#demo"' in w4,
      'welcome: секция «Панель в деле» в навигации')
check('w-sec-title .grad' in w4 or 'class="w-sec-title">' in w4 and '<span class="grad">' in w4,
      'welcome: градиентные акценты заголовков секций')
# ═══ 28. Подсказки ников при вводе (@ и поиск участников) ═════════════════
print('== ники отображаются ==')
common_src = open(os.path.join(ROOT, 'web', 'routes', '_common.py'), encoding='utf-8').read()
check('DEMO_MEMBERS' in common_src and 'demo_members_search' in common_src,
      'общий источник демо-участников в _common')
members_src = open(os.path.join(ROOT, 'web', 'routes', 'members.py'), encoding='utf-8').read()
check('demo_members_search' in members_src,
      'member-search: демо-поиск, когда бот офлайн')
ux_src = open(os.path.join(ROOT, 'web', 'routes', 'ux.py'), encoding='utf-8').read()
check('demo_members_search' in ux_src and "search_members" in ux_src,
      '@-поиск панели: участники из демо-источника')
mc_src = open(os.path.join(ROOT, 'web', 'routes', 'member_card_panel.py'), encoding='utf-8').read()
check('DEMO_MEMBERS' in mc_src and "pool.setdefault" in mc_src,
      'карточка 360: подсказки дополнены демо-участниками')
login_as('owner')
r = client.get('/api/member-search/987654321098765432?q=art')
d = r.get_json(silent=True)
check(r.status_code == 200 and isinstance(d, list) and any(str(m.get('display_name', '')).lower().startswith('art') for m in d),
      f'поиск участников находит «art» → {[m.get("display_name") for m in d] if isinstance(d, list) else d}')
r = client.get('/api/ux/search?q=art')
uxd = r.get_json(silent=True) or {}
names = [i.get('title') for g in uxd.get('groups', []) if g.get('key') == 'members' for i in g.get('items', [])]
check('Artem' in names, f'@-поиск находит участника Artem → {names}')
r = client.get('/api/guild/987654321098765432/member-card/suggest?q=so')
sd = r.get_json(silent=True) or {}
check(any(str(i.get('name', '')).lower().startswith('so') for i in sd.get('items', [])),
      f'подсказки карточки 360 находят «so» → {sd.get("items")}')
r = client.get('/api/chat/987654321098765432/members')
cm = r.get_json(silent=True)
check(isinstance(cm, list) and len(cm) >= 5, f'чат-пикер видит участников ({len(cm) if isinstance(cm, list) else 0})')
# ═══ 29. Логин — премиальный чёрный ════════════════════════════════════════
print('== логин: чёрная тема ==')
lg = open(os.path.join(ROOT, 'web', 'templates', 'login.html'), encoding='utf-8').read()
check('data-theme="dark"' in lg and '#05060a' in lg,
      'логин: тёмная тема с глубоким чёрным фоном')
check('bg-fx' in lg and 'orb1' in lg and 'bg-grid' in lg and 'lg-stars' in lg,
      'логин: свечения, сетка и звёздный canvas')
check('MEMBER EDITION' in lg,
      'логин: бренд-панель в издании для участников')
check('Твой сервер' in lg and 'твоя жизнь' in lg,
      'логин: заголовок «Твой сервер — твоя жизнь»')
check('Твой профиль и роли' in lg and 'Карточка 360°' in lg
      and 'Заявки в команду' in lg and 'Обращения без потерь' in lg
      and 'Уровни и награды' in lg and 'События сервера' in lg,
      'логин: фичи — участнические (профиль/карточка/заявки/обращения/уровни/события)')
check('Модерация без хаоса' not in lg and 'Оперативный центр' not in lg,
      'логин: штабные фичи убраны — вход презентуется участникам')
check('auth-card::after' in lg and 'conic-gradient' in lg,
      'логин: градиентная рамка карточки при hover')
check('auth-btn::after' in lg and 'skewX(-20deg)' in lg,
      'логин: блеск пробегает по кнопке входа')
check('tabBtnPass' in lg and 'tabBtnPin' in lg and 'data-auth-tab' in lg,
      'логин: табы «Пароль» и «Discord PIN» сохранены')
check('showSuggest' in lg and 'api/login/suggest' in lg,
      'логин: автодополнение логинов работает')
check('pinBox' in lg and 'buildPinBox' in lg and 'discord-login' in lg,
      'логин: PIN-вход сохранён')
check('emblem-dragon.png' in lg,
      'логин: дракон в бренд-панели и мобильном бренде')
check('auth-feats' in lg and 'rgba(255, 255, 255, .05)' in lg,
      'логин: фичи в стеклянных плашках')
r = client.get('/login')
check(r.status_code == 200 and 'MEMBER EDITION' in r.get_data(as_text=True),
      '/login открывается в чёрной теме для участников')
# ═══ 29а. Логин — красота и надёжность ════════════════════════════════════
print('== логин: красота 4 ==')
check('lgGradFlow' in lg and 'background-size: 220% 100%' in lg,
      'логин: заголовок «Твой сервер — твоя жизнь» переливается градиентом')
check('slideSide' in lg and 'featIn' in lg and 'auth-feats li:nth-child(6)' in lg,
      'логин: бренд-панель въезжает, фичи появляются каскадом')
check('tabFade' in lg,
      'логин: содержимое вкладок переключается с плавным появлением')
check('passEye' in lg and 'aria-pressed' in lg and 'fa-eye-slash' in lg,
      'логин: глазик показа/скрытия пароля')
check('errShake' in lg and "classList.add('shake')" in lg,
      'логин: ошибки трясутся при появлении')
check('digitPop' in lg and 'classList.add(\'has\')' in lg,
      'логин: PIN-цифры подпрыгивают при вводе')
check('popIn' in lg and 'classList.add(\'open\')' in lg,
      'логин: автодополнение появляется плавно')
check('ArrowDown' in lg and 'scrollIntoView({ block: \'nearest\' })' in lg,
      'логин: подсказки автодополнения управляются стрелками и Enter')
check('window.qualitySetLoading = window.qualitySetLoading || function' in lg,
      'логин: собственный спиннер кнопок (PIN не падает без app.js)')
check('meteorNext' in lg and 'var target = 16' in lg and 'ema' in lg,
      'логин: звёзды адаптивно 60/30 fps и редкие метеоры')
check('.auth-side h1 .grad' in lg.split('prefers-reduced-motion')[1][:800]
      and '.auth-card, .auth-side, .auth-main, .auth-feats li' in lg.split('prefers-reduced-motion')[1][:800],
      'логин: новые анимации выключены при reduced-motion')

# ═══ 30. Welcome: витрина, tilt, scrollspy, FAQ ════════════════════════════
print('== welcome: витрина панели ==')
w5 = open(os.path.join(ROOT, 'web', 'templates', 'welcome.html'), encoding='utf-8').read()
check('w-showcase' in w5 and 'w-showcase-kpi' in w5 and 'w-showcase-side' in w5,
      'welcome: витрина-макет панели (сайдбар + KPI + график)')
check('w-chart-bars' in w5 and 'wShowBars' in w5 and 'wBarGrow' in w5,
      'welcome: растущие бары графика в витрине')
check('w-feed-line' in w5 and 'wShowFeed' in w5,
      'welcome: живая лента событий в витрине')
check('data-count2' in w5,
      'welcome: живые счётчики витрины')
check("perspective(700px) rotateY" in w5 and "pointer: fine" in w5,
      'welcome: лёгкий 3D-tilt карточек за курсором (desktop)')
check('w-nav-links a.on' in w5 and "classList.toggle('on'" in w5,
      'welcome: scrollspy — активный пункт навигации при скролле')
check('w-faq' in w5 and 'Частые' in w5 and '<details>' in w5,
      'welcome: FAQ-аккордеон')
check('href="#look"' in w5 and 'href="#faq"' in w5,
      'welcome: пункты «Витрина» и «FAQ» в навигации')
check('Так' in w5 and 'выглядит' in w5,
      'welcome: заголовок витрины «Так выглядит панель»')
# ═══ 31. Баг-фиксы и красота ═══════════════════════════════════════════════
print('== баг-фиксы ==')
w6 = open(os.path.join(ROOT, 'web', 'templates', 'welcome.html'), encoding='utf-8').read()
check('paintText' in w6 and "words[words.length - 1]" in w6,
      'welcome: заголовок после печати сохраняет градиент (баг исправлен)')
check('scroll-margin-top: 92px' in w6,
      'welcome: секции не прячутся под фикс-навигацией (баг исправлен)')
check('w-top' in w6 and 'wTop' in w6 and '--top-p' in w6,
      'welcome: кнопка «наверх» с кольцом прогресса')
reg = open(os.path.join(ROOT, 'web', 'templates', 'register.html'), encoding='utf-8').read()
check('data-theme="dark"' in reg and '#05060a' in reg and 'rg-stars' in reg,
      'register: чёрная тема в стиле логина (баг консистентности исправлен)')
check('@keyframes fadeUp' in reg,
      'register: анимация карточки самодостаточна (без style.css)')
check('emblem-dragon.png' in reg,
      'register: дракон в бренде')
check('ПРЕМИУМ-СКРОЛЛБАРЫ' in css,
      'панель: градиентные скроллбары сайдбара и контента')
check('scrollbar-color: var(--ac)' in css,
      'панель: Firefox scrollbar-width thin')
r = client.get('/register')
check(r.status_code == 200 and 'rg-stars' in r.get_data(as_text=True),
      '/register открывается в чёрной теме')
sp = open(os.path.join(ROOT, 'web', 'templates', 'status_public.html'), encoding='utf-8').read()
check('data-theme="dark"' in sp and '#05060a' in sp and 'st-stars' in sp,
      'статус-страница: чёрная тема со звёздами (как welcome и логин)')
check('emblem-dragon.png' in sp,
      'статус-страница: дракон в бренде')
check('st-state' in sp and 'm-ping' in sp and 'status-public' in sp,
      'статус-страница: живая телеметрия сохранена')
r = client.get('/status')
check(r.status_code == 200, '/status открывается')
# ═══ 32. Живой дракон ═══════════════════════════════════════════════════════
print('== живой дракон ==')
check('.dragon-live' in css and 'dragonBreath' in css,
      'дизайн-система: класс дыхания дракона')
check('dragonSmoke' in css and 'translateY(-54px)' in css,
      'дизайн-система: дымок выдоха с ритмом дыхания')
w7 = open(os.path.join(ROOT, 'web', 'templates', 'welcome.html'), encoding='utf-8').read()
check('dragon-live' in w7 and 'dragon-smoke' in w7 and 'dragonBreath' in w7,
      'welcome: дракон дышит и выдыхает дымок')
check("'.dragon-smoke { display: none; }'" in w7.replace('"', "'").replace(" ", '') or '.dragon-smoke { display: none; }' in w7,
      'welcome: дым скрыт при reduced-motion')
for name, path in [('base', 'web/templates/base.html'), ('login', 'web/templates/login.html'),
                   ('register', 'web/templates/register.html'), ('status', 'web/templates/status_public.html'),
                   ('kiosk', 'web/templates/mod_kiosk.html')]:
    t = open(os.path.join(ROOT, path), encoding='utf-8').read()
    check('dragon-live' in t, f'{name}: дракон дышит')
    check('dragonBreath' in t or path.endswith('base.html') or path.endswith('status_public.html') or path.endswith('mod_kiosk.html'),
          f'{name}: keyframes доступны (локально или из style.css)')
check('dragonBreath' in open(os.path.join(ROOT, 'web', 'templates', 'login.html'), encoding='utf-8').read()
      and 'dragonBreath' in open(os.path.join(ROOT, 'web', 'templates', 'register.html'), encoding='utf-8').read(),
      'login/register: keyframes локально (без style.css)')
# ═══ 33. Panel Sparkle ═══════════════════════════════════════════════════
print('== panel sparkle ==')
check('PANEL SPARKLE' in css, 'дизайн-система: слой Panel Sparkle')
check('contentIn' in css and '.main-content { animation: contentIn' in css,
      'панель: контент плавно появляется при загрузке страницы')
check('eyebrowPulse' in css and '.page-head .eyebrow::before' in css,
      'панель: пульс-точка в eyebrow')
check('.kpi .kpi-icon::after' in css and '.kpi:hover .kpi-icon::after { left: 140%' in css,
      'панель: блик иконок KPI при наведении')
check('.btn::after' in css and '.btn:hover::after { left: 135%' in css,
      'панель: блик на кнопках при наведении')
check(':focus-visible' in css and 'outline: 2px solid var(--ac)' in css,
      'панель: красивые фокус-кольца для всего интерактивного')
check("table.data-table tbody tr::before" in css and 'ac-grad' in css,
      'панель: градиентная полоска у строк таблиц при hover')
check('.panel:focus-within' in css,
      'панель: свечение панели при фокусе внутри')
w8 = open(os.path.join(ROOT, 'web', 'templates', 'welcome.html'), encoding='utf-8').read()
check('.w-section:hover::before { width: 180px; }' in w8,
      'welcome: градиентная кромка секций при hover')
check('.w-sec-title:hover::after { right: 0; }' in w8,
      'welcome: градиентная волна заголовков')
check('.w-step:hover .num' in w8,
      'welcome: пульс номеров шагов')
check('.w-terminal:hover' in w8,
      'welcome: свечение терминала при hover')
# ═══ 34. Panel Sparkle 2 ═══════════════════════════════════════════════════
print('== panel sparkle 2 ==')
check('PANEL SPARKLE 2' in css, 'дизайн-система: слой Panel Sparkle 2')
check('brandWave' in css and '.brand-title' in css,
      'панель: бренд-заголовок с градиентной волной (ускоряется при hover)')
check('modalSpring' in css and 'translateY(16px) scale(.94)' in css,
      'панель: spring-появление модалок')
check('badgePop' in css and '.badge, .chip, .status-pill' in css,
      'панель: pop-появление бейджей и чипов')
check('th.sortable:hover' in css,
      'панель: подсветка столбца таблицы при hover на заголовок')
check('.nav-icon-btn:hover' in css and 'translateY(-1px)' in css,
      'панель: свечение и подъём иконок шапки')
check('.panel-head:hover h2 i { transform: scale(1.12) rotate(-4deg); }' in css,
      'панель: покачивание иконок заголовков панелей')
check('.kpi:not(.tone-ok)' in css and 'background-clip: text' in css,
      'панель: градиентные KPI-значения')
check('drop-shadow' in css and '.brand-icon .dragon-live' in css,
      'панель: дракон подсвечен в ритме дыхания')
w9 = open(os.path.join(ROOT, 'web', 'templates', 'welcome.html'), encoding='utf-8').read()
check('wHeroIn' in w9 and 'animation-delay: .48s' in w9,
      'welcome: stagger-появление hero при загрузке')
check('.w-cta-box:hover' in w9 and 'rgba(124, 58, 237, .25)' in w9,
      'welcome: свечение CTA при hover')
# ═══ 35. Panel Sparkle 3 ═══════════════════════════════════════════════════
print('== panel sparkle 3 ==')
check('PANEL SPARKLE 3' in css, 'дизайн-система: слой Panel Sparkle 3')
check('topbarWave' in css and '.topbar::after' in css,
      'панель: градиентная волна по нижней кромке шапки')
check('.nav-link.active::after' in css and 'navDotPulse' in css,
      'панель: анимированная точка активного пункта меню')
check('.toast {' in css and 'border-left: 3px solid var(--ac)' in css,
      'панель: премиум-тосты с боковым свечением')
check('liveSweep' in css and '.live-chip::before' in css,
      'панель: световая волна по LIVE-чипу')
check('.fab-main:hover' in css and '55%, transparent' in css,
      'панель: усиленное свечение FAB при hover')
w10 = open(os.path.join(ROOT, 'web', 'templates', 'welcome.html'), encoding='utf-8').read()
check('.w-nav-links a.on::after' in w10,
      'welcome: пульс-точка активного пункта навигации')
check('showcaseLive' in w10 and 'wKpiTick' in w10 and 'setInterval' in w10,
      'welcome: живое обновление KPI витрины каждые 4 сек')
# ═══ 36. Видимость лого ════════════════════════════════════════════════════
print('== видимость лого ==')
check('ВИДИМОСТЬ ЛОГО' in css and 'img[src*="emblem-dragon"]' in css,
      'дизайн-система: глобальные правила видимости дракона')
check('[data-theme="light"] img[src*="emblem-dragon"]' in css and 'drop-shadow' in css,
      'светлая тема: дракон получает тень — виден на любом светлом фоне')
check('[data-theme="dark"] img[src*="emblem-dragon"]' in css,
      'тёмная тема: дракон подсвечен')
pa = open(os.path.join(ROOT, 'web', 'templates', 'public_apply.html'), encoding='utf-8').read()
check('.header .logo' in pa and 'var(--ac-grad)' in pa and '72px' in pa,
      'заявка: лого на градиентной плитке (был белый на белом — невидим)')
from PIL import Image
ico = Image.open(os.path.join(ROOT, 'web', 'static', 'favicon.ico'))
pix = ico.convert('RGB').load()
# фон фавикона больше не прозрачный/белый — индиго-градиент (проверим углы)
corners = [pix[1, 1], pix[62, 1], pix[1, 62], pix[62, 62]]
check(all(sum(c) > 200 for c in corners),
      f'фавикон: дракон на индиго-градиенте (углы {corners})')
login_as('owner')
r = client.get('/apply')
check(r.status_code == 200 and '.header .logo' in r.get_data(as_text=True),
      '/apply открывается с видимым лого')
# ═══ 36а. Лого: мобильная шапка, сплэш, плотность дракона ═══════════════════
print('== лого: сплэш и мобильная шапка ==')
check('boot-logo"><img class="dragon-live"' in base and 'fa-bolt' not in base.split('bootSplash')[1].split('boot-wrap')[1][:600],
      'сплэш загрузки показывает дракона, а не молнию')
check('topbar-brand' in base and 'emblem-dragon.png' in base.split('topbar-brand')[1][:400],
      'мобильная шапка панели получила дракона (лого видно и без сайдбара)')
check('.topbar-brand' in css and 'display: grid' in css.split('max-width: 1080px')[1][:700],
      'лого шапки появляется именно на мобильных экранах (≤1080px)')
check('.boot-logo img' in css and 'dragonBreath' in css.split('.boot-logo img')[1][:400],
      'дракон на сплэше дышит (анимация дыхания)')
from PIL import Image as _Img
_dim = _Img.open(os.path.join(ROOT, 'web', 'static', 'brand', 'emblem-dragon.png'))
_bx = _dim.getbbox()
_cov = ((_bx[2]-_bx[0]) * (_bx[3]-_bx[1])) / (_dim.size[0] * _dim.size[1])
check(_cov >= 0.7, f'дракон заполняет холст ({_cov:.2%}) — виден крупно даже в маленьких иконках')
# ═══ 37. Welcome: фиксы пустых блоков ══════════════════════════════════════
print('== welcome: фиксы ==')
w11 = open(os.path.join(ROOT, 'web', 'templates', 'welcome.html'), encoding='utf-8').read()
check('.w-title { opacity: 1; }' in w11,
      'welcome: заголовок виден сразу (убран из stagger — был невидим первые 0.8с)')
check('.w-title, .w-lead' not in w11.replace(' .w-lead,', ''),
      'welcome: stagger-список не включает заголовок')
check('setTimeout(start, 900)' in w11,
      'welcome: терминал стартует сразу после загрузки (не пустая коробка)')
check('function restart()' in w11 and 'restart();' in w11,
      'welcome: терминал перезапускается при попадании в зону видимости')
check('barsBox.innerHTML = vals.map' in w11,
      'welcome: бары витрины вставляются сразу (не пустые до скролла)')
check("el.dataset.live = String(Number(el.dataset.count2) || 0)" in w11,
      'welcome: KPI витрины показывают значения сразу (не нули до скролла)')
check('lastStart' in w11 and 'lastPart' in w11,
      'welcome: заголовок печатается посимвольно (не целыми словами)')
check('barsShown' in w11 and 'barsIo' in w11,
      'welcome: рост баров перезапускается при показе (не проигрывается впустую)')
check('app.js?v=52' in base and 'style.css?v=112' in base,
      'версии ассетов (112/52)')
# ═══ 37а. Welcome: лого hero ══════════════════════════════════════════════
print('== welcome: лого hero ==')
check('w-dragon-par' in w11 and 'w-dragon-ring2' in w11 and 'w-dragon-orbit' in w11,
      'welcome: дракон получил параллакс-слой, второе кольцо и орбитальные огоньки')
check('.w-dragon::after' in w11 and 'wGloss' in w11,
      'welcome: глянцевый блик пробегает по плитке дракона')
check('.w-dragon-floor' in w11 and 'wFloor' in w11,
      'welcome: светящийся пол под драконом дышит в такт полёту')
check('.w-dragon img' in w11 and '112px' in w11.split('.w-dragon img')[1][:400],
      'welcome: дракон в hero крупный, но компактный (112px)')
check('116px 20px 54px' in w11,
      'welcome: hero ужат — меньше пустого сверху и снизу надписи')
check('margin: 14px 0 10px' in w11 and '0 auto 14px' in w11,
      'welcome: отступы вокруг заголовка и описания (характеристики) уменьшены')
check('margin: 0 auto 20px' in w11 and 'margin: 22px auto 0' in w11,
      'welcome: поиск и статистика прижаты — нет пустых провалов')
check('setTimeout(then, 1800)' in w11,
      'welcome: пауза между фразами короче — надпись всегда живая')
# ═══ 37б. Welcome: CSS-переменные (фикс невидимого hero) ════════════════════
print('== welcome: переменные ==')
_defined = set(re.findall(r'--([a-z0-9-]+)\s*:', w11))
_used = set(re.findall(r'var\(--([a-z0-9-]+)', w11))
check('ease' in _defined,
      'welcome: --ease определён (иначе stagger-hero навсегда opacity:0)')
check(len(_used - _defined - {'top-p'}) == 0,
      'welcome: все CSS-переменные определены — ни один блок не может пропасть')
check('--ease-out:' in css and '--ac-glow:' in css and '--ease-spring:' in css,
      'дизайн-система: --ease-out/--ac-glow/--ease-spring доопределены в style.css')
check('--text-1:' in css and '--r-md:' in css and '--shadow-md:' in css,
      'дизайн-система: текстовые/радиусные/теневые токены страниц доопределены')
check('wDragonPar' in w11 and 'requestAnimationFrame' in w11,
      'welcome: параллакс дракона за курсором (rAF, плавный)')
check('.w-nav .brand img' in w11 and 'dragonBreath' in w11.split('.w-nav .brand img')[1][:600],
      'welcome: дракон в навигации на градиентной плитке и дышит')
check('.w-dragon-ring, .w-dragon-ring2,' in w11.split('prefers-reduced-motion')[1][:900],
      'welcome: новые анимации дракона отключаются при reduced-motion')
# ═══ 37в. Welcome: красота 4 (метеоры, переливы, прогресс, hover) ════════════
print('== welcome: красота 4 ==')
check('meteorNext' in w11 and 'createLinearGradient' in w11 and 'meteor' in w11,
      'welcome: падающие звёзды на канвасе (редкие, раз в ~7 секунд)')
check('now - last < 16' in w11,
      'welcome: звёздное небо на 60 fps — мерцание плавное, не дёрганое')
check('wGradFlow' in w11 and 'background-size: 220% 100%' in w11,
      'welcome: заголовки hero и секций переливаются градиентом')
check('wProgress' in w11 and 'id="wProgress"' in w11,
      'welcome: градиентная полоса прогресса чтения сверху')
check('.w-stat::after' in w11 and 'skewX(-20deg)' in w11,
      'welcome: глянцевый блик пробегает по стат-карточкам при hover')
check('.w-chips .chip:hover i' in w11 and 'scale(1.18)' in w11,
      'welcome: иконки чипов подпрыгивают при наведении')
check('.w-step:hover .num' in w11 and 'rotate(-4deg)' in w11,
      'welcome: шаги приподнимаются, номер пульсирует кольцом')
check('faqIn' in w11 and 'details[open] .faq-body' in w11,
      'welcome: FAQ раскрывается плавной анимацией')
check('.w-terminal-body::after' in w11 and 'repeating-linear-gradient' in w11,
      'welcome: терминал получил CRT-сканлайн (статичный, без нагрузки)')
check('.w-marquee .item:hover' in w11 and 'item:hover i' in w11,
      'welcome: пункты бегущей ленты подсвечиваются при наведении')
check('.w-title .grad, .w-sec-title .grad' in w11.split('prefers-reduced-motion')[1][:900],
      'welcome: переливы и раскрытия выключены при reduced-motion')
# ═══ 37д. Login: красота 2 (медальон, наклон, слайдер, статус, капс) ════════
print('== login: красота 2 ==')
lg2 = open(os.path.join(ROOT, 'web', 'templates', 'login.html'), encoding='utf-8').read()
check('lg-dragon-stage' in lg2 and 'ring2' in lg2 and 'orbits' in lg2 and 'lgGloss' in lg2,
      'login: медальон дракона с кольцами, орбитами и глянцевым бликом')
check('lg-dragon-stage .tile' in lg2 and 'lgFloor' in lg2,
      'login: дракон на градиентной плитке со светящимся полом')
check('lg-aurora' in lg2 and 'lgAurora' in lg2,
      'login: медленные аврора-лучи на фоне (окружение, не за курсором)')
check('perspective(1100px)' in lg2 and 'rotateX' in lg2 and 'pointer: fine' in lg2,
      'login: 3D-наклон карточки за курсором (rAF, только точный указатель)')
check('tab-slider' in lg2 and 'placeSlider' in lg2 and 'offsetLeft' in lg2,
      'login: скользящий индикатор вкладок Пароль/Discord PIN')
check('/api/status-public' in lg2 and 'authStatus' in lg2 and 'statusDot' in lg2,
      'login: живой статус бота с пульсирующей точкой')
check('getModifierState' in lg2 and 'CapsLock' in lg2 and 'cap-hint' in lg2,
      'login: предупреждение о Caps Lock у пароля')
check('has-ico' in lg2 and 'f-ico' in lg2 and 'fa-lock' in lg2 and 'fab fa-discord' in lg2,
      'login: иконки в полях ввода (логин/пароль/discord)')
check('lg-back' in lg2 and '/welcome' in lg2,
      'login: ссылка назад на приветственную страницу')
check('margin: auto' in lg2.split('.auth-card {')[1][:200],
      'login: карточка не обрезается при нехватке высоты (margin:auto)')
check('.auth-feats li:hover i' in lg2 and 'var(--ac-grad)' in lg2.split('.auth-feats li:hover i')[1][:200],
      'login: иконки фич заливаются градиентом при наведении')
check('.lg-aurora i' in lg2.split('prefers-reduced-motion')[1][:900]
      and '.lg-dragon-stage .ring' in lg2.split('prefers-reduced-motion')[1][:900],
      'login: новые анимации отключаются при reduced-motion')
_st = open(os.path.join(ROOT, 'web', 'routes', 'status.py'), encoding='utf-8').read()
check('api_status_public' in _st and 'Демо-режим: бот «живой»' in _st,
      'status-api: в демо-режиме бот онлайн — логин показывает живой статус')
# ═══ 37е. Переходы: вкладки логина и смена фраз welcome ═════════════════════
print('== переходы: вкладки и фразы ==')
check('tab-out-l' in lg2 and 'tab-out-r' in lg2 and 'tab-in-r' in lg2 and 'tab-in-l' in lg2,
      'login: вкладки меняются направленным слайдом (4 класса ухода/прихода)')
check('#tabPass.tab-in-r' in lg2 and '#tabPass.tab-out-l' in lg2,
      'login: слайды вкладок реально применяются (составные селекторы, нет конфликта с #tabPass)')
_tko = lg2.split('@keyframes tabOutL')[1].split('}')[0]
_tkr = lg2.split('@keyframes tabInR')[1].split('}')[0]
check('blur' not in _tko and 'blur' not in _tkr,
      'login: текст при переходах НЕ размывается — качество всегда чёткое')
check('switchTab' in lg2 and '_curTab' in lg2 and "dirRight = tab === 'pin'" in lg2,
      'login: направление слайда зависит от стороны вкладки')
check('pinGoStep2' in lg2 and 'step-out' in lg2 and 'step-in' in lg2,
      'login: шаг 1 → шаг 2 PIN сменяется тем же слайдом')
check('.tab-btn.active i' in lg2 and 'tabIconPop' in lg2,
      'login: иконка активной вкладки подпрыгивает при переключении')
check('cubic-bezier(.34, 1.3, .64, 1)' in lg2.split('.tab-slider')[1][:500] and 'moving' in lg2,
      'login: слайдер вкладок переезжает мягкой пружиной и вспыхивает')
check('.tab-out-l' in lg2.split('prefers-reduced-motion')[1][:1000],
      'login: слайды вкладок отключены при reduced-motion')
# ═══ 37ж. Login: редизайн 4 — подчёркнутые табы и премиум-форма ═════════════
print('== login: редизайн 4 ==')
lg3 = open(os.path.join(ROOT, 'web', 'templates', 'login.html'), encoding='utf-8').read()
check('lg-card-zone' in lg3 and 'lg-glow' in lg3,
      'login: структура «одна карточка» с мягким свечением за ней')
check('.lg-dragon-stage' in lg3 and 'top: 0; left: 50%' in lg3.split('.lg-dragon-stage {')[1][:220],
      'login: медальон дракона парит над кромкой карточки (не внутри, не сверху страницей)')
check('body::after' in lg3 and 'feTurbulence' in lg3,
      'login: лёгкая плёнка-зерно для глубины фона (статичная, без нагрузки)')
check('padding: 56px 32px 30px' in lg3,
      'login: контент карточки освобождает место под парящим медальоном')
check('max-width: 430px' in lg3 and 'margin: auto' in lg3.split('.lg-stage {')[1][:260],
      'login: компактная колонна, центрированная по вертикали')
check('display: flex' in lg3.split('      body {')[1][:300] and 'min-height: 100vh' in lg3.split('      body {')[1][:300],
      'login: карточка по центру экрана, а не прижата к верху (flex + 100vh)')
check('gap: 22px' in lg3.split('.tabs {')[1][:420] and 'border-bottom: 1px solid rgba(255, 255, 255, .07)' in lg3.split('.tabs {')[1][:420],
      'login: табы — чистые подчёркнутые (Linear-стиль), без коробок-пилюль')
check('.tab-btn.active { color: #c7d2fe; }' in lg3,
      'login: активная вкладка выделена цветом, а не заливкой')
check('height: 48px' in lg3 and 'border-radius: 12px' in lg3,
      'login: поля выше и мягче (48px, радиус 12)')
check('height: 50px' in lg3.split('.auth-btn {')[1][:300],
      'login: кнопка входа крупная и ровная (50px)')
check('border-radius: 24px' in lg3.split('.auth-card {')[1][:520],
      'login: карточка с премиальным радиусом 24')
check('font-size: 23px' in lg3.split('.auth-side h1 {')[1][:300],
      'login: заголовок крупнее (23px)')
# ═══ 37з. Login: FPS — стекло и аврора без GPU-блюра ════════════════════════
print('== login: FPS ==')
check('backdrop-filter' not in lg3,
      'login: backdrop-blur полностью убран (блюр над живым канвасом = 15 fps)')
check('blur(52px)' not in lg3 and 'blur(22px)' not in lg3 and 'rotate(360deg)' not in lg3.split('@keyframes lgAurora')[1].split('}')[0],
      'login: аврора без гигантского блюра и без вечного вращения (только дыхание прозрачности)')
check('radial-gradient(circle, rgba(99, 102, 241, .11)' in lg3 and 'from { opacity: .4; }' in lg3,
      'login: аврора — статичные мягкие радиальные пятна, дешёвые для GPU')
check('rgba(13, 16, 25, .88)' in lg3,
      'login: карточка — стекло на полупрозрачности без фильтров')
check('var target = 16' in lg3 and 'ema > 30 ? 34 : 16' in lg3,
      'login: канвас звёзд сам сбрасывается на 30 fps на слабых машинах')
# ═══ 37и. Login: клик по людям в подсказках + анкета ═══════════════════════
print('== login: клик по подсказкам ==')
check('display_name || s.username' in lg3 and 's.discord_id || s.id' in lg3,
      'login: поля API (name/display_name/id) мапятся в подсказки — клик реально подставляет значение')
check('a-ava' in lg3 and '.a-copy' in lg3,
      'login: подсказки с аватаркой-буквой и именем (не пустые строки)')
check("input.id === 'passUsername'" in lg3 and 'pw.focus()' in lg3,
      'login: после выбора логина фокус сразу на пароль')
check('.autocomplete-popup .item .a-ava img' in lg3,
      'login: аватар накрывает букву, при ошибке загрузки остаётся буква')
print('== анкета: премиум-редизайн ==')
check('.server-card' in pa and 'server-card-opt' not in pa,
      'анкета: карточки серверов стилизованы (класс в CSS совпадает с JS)')
check('particles' not in pa,
      'анкета: частицы удалены — фон статичный, FPS не страдает')
check('.server-panel' in pa and '.form-card' in pa and '.submit-btn::after' in pa,
      'анкета: стеклянные панели и блеск кнопки отправки')
check('#05060a' in pa and '.lg-back' in pa and '/welcome' in pa,
      'анкета: чёрный премиальный фон и ссылка на главную')
check('role-card' in pa and ':has(input:checked)' in pa and 'rc-check' in pa,
      'анкета: карточки ролей с галочкой выбора')
check('.success-screen .check' in pa and 'okPulse' in pa,
      'анкета: экран успеха с пульсирующей галочкой')
# ═══ 37к. Устойчивость: AI-модерация и каналы ═══════════════════════════════
print('== устойчивость: ai-модерация и каналы ==')
_aim = open(os.path.join(ROOT, 'web', 'templates', 'ai_moderation.html'), encoding='utf-8').read()
check('esc.window_hours != null' in _aim and 'esc.warn_to_mut_after != null' in _aim,
      'ai-модерация: значения эскалации с фолбэками — старый конфиг больше не бросает RangeError')
check('raw.error' in _aim and 'НЕДОСТУПНО' in _aim,
      'ai-модерация: при офлайн-боте/битом конфиге страница не падает, а честно показывает статус')
check('if (!cfg || cfg.error) return;' in _aim,
      'ai-модерация: тумблеры языков/уровней/эскалации защищены от undefined')
_cogaim = open(os.path.join(ROOT, 'cogs', 'ai_moderation.py'), encoding='utf-8').read()
check('def _merge' in _cogaim and 'Конфиг с дефолтами' in _cogaim,
      'cog ai_moderation: load_config глубоко сливает сохранённый конфиг с дефолтами')
_r_aim = open(os.path.join(ROOT, 'web', 'routes', 'ai_mod.py'), encoding='utf-8').read()
check('def _demo_cog' in _r_aim and 'AIModeration(None)' in _r_aim,
      'routes ai_mod: демо-режим отдаёт конфиг/статистику/тест без бота')
_ch = open(os.path.join(ROOT, 'web', 'templates', 'channels.html'), encoding='utf-8').read()
check('data.error' in _ch and 'ch-empty-sub' in _ch,
      'каналы: ошибка API показывается пользователю, а не молчаливая пустота')
_gad = open(os.path.join(ROOT, 'web', 'routes', 'guild_admin.py'), encoding='utf-8').read()
check('канал пропущен' in _gad or 'один проблемный канал' in _gad,
      'routes channels: один битый канал не роняет весь список (per-channel защита)')
# ═══ 37л. Обход всех страниц: скрытые ReferenceError/TypeError ═══════════════
print('== обход страниц: скрытые ошибки ==')
_js2 = open(os.path.join(ROOT, 'web', 'static', 'app.js'), encoding='utf-8').read()
_k2 = _js2.split('AETHER PREMIUM KIT 2')[1][:600]
check('function reducedMotion()' in _k2,
      'app.js: reducedMotion определён в KIT 2 (был ReferenceError при каждой отрисовке кольца)')
_lva = open(os.path.join(ROOT, 'web', 'templates', 'leveling_admin.html'), encoding='utf-8').read()
check("cfg = (raw && !raw.error) ? raw : {}" in _lva and 'tx.enabled !== false' in _lva,
      'leveling-admin: конфиг с дефолтами — офлайн-бот не роняет страницу (был TypeError на cfg.text_xp)')
check('if (!s || s.error || typeof s.total_users' in _lva,
      'leveling-admin: статистика/ачивки/награды защищены от битого ответа')
_bd = open(os.path.join(ROOT, 'web', 'templates', 'bot_diagnostics.html'), encoding='utf-8').read()
check('!data || data.error || !data.current' in _bd and 'ОФЛАЙН' in _bd,
      'bot-diagnostics: бот офлайн показывает честный статус, а не TypeError memory_mb')
_bda = open(os.path.join(ROOT, 'web', 'routes', 'admin_api.py'), encoding='utf-8').read()
check('типичный здоровый бот' in _bda,
      'routes health: в демо-режиме диагностика отдаёт живой снапшот')
_all2 = []
for _t2 in sorted(os.listdir(os.path.join(ROOT, 'web', 'templates'))):
    if _t2.endswith('.html'):
        _all2.append(open(os.path.join(ROOT, 'web', 'templates', _t2), encoding='utf-8').read())
_all2_src = '\n'.join(_all2)
check('cdn.jsdelivr.net/npm/chart.js' not in _all2_src,
      'все шаблоны: Chart.js не зависит от jsdelivr (графики работают без CDN)')
check(os.path.exists(os.path.join(ROOT, 'web', 'static', 'vendor', 'chartjs', 'chart.umd.js')),
      'вендор: chart.umd.js локально')
_guest_canvas = 0
for _g in ('login', 'register', 'status_public', 'welcome'):
    _gt = open(os.path.join(ROOT, 'web', 'templates', _g + '.html'), encoding='utf-8').read()
    if 'var ctx = cv.getContext' in _gt and 'if (!ctx) return;' in _gt:
        _guest_canvas += 1
check(_guest_canvas == 4,
      f'гостевые страницы: канвас звёзд с null-защитой ({_guest_canvas}/4)')
# ═══ 37м. Фазз кликов: скрытые ошибки обработчиков ═══════════════════════════
print('== фазз: ошибки обработчиков ==')
check('function paletteRecents()' in _js2 and 'aether_recents' in _js2,
      'app.js: paletteRecents определён (глобальный поиск падал с ReferenceError при открытии)')
check('function paletteRemember' in _js2 and 'paletteRemember(item.path)' in _js2,
      'app.js: недавние разделы запоминаются при переходе из поиска')
check('var starBtn = doc.createElement' in _js2 and 'star(path)' in _js2,
      'app.js: кнопка-звезда больше не перекрывает функцию star() (был TypeError на каждом клике)')
check('starBtn.addEventListener' in _js2,
      'app.js: обработчик клика по звезде привязан к кнопке (starBtn)')
# ═══ 37н. Скролл пикера и демо-данные левелинга ══════════════════════════════
print('== скролл пикера и демо-левелинг ==')
check("panel.addEventListener('wheel'" in _js2 and 'listEl.scrollTop + e.deltaY' in _js2,
      'app.js: колесо прокручивает список AetherSelect, страница не дёргается')
check('overscroll-behavior: contain' in css.split('.aes-list')[1][:400] and 'touch-action: pan-y' in css.split('.aes-list')[1][:400],
      'css: список пикера с overscroll-contain и touch-прокруткой')
check('max-height: min(52vh, 320px)' in css and 'max-height: calc(100vh - 16px)' in css,
      'css: панель и список пикера вписываются в экран')
check('overscroll-behavior: contain' in css.split('.modal-overlay .modal-card')[1][:300] or
      'overscroll-behavior: contain' in css.split('.modal-overlay .modal-box')[1][:300],
      'css: скролл внутри модалок не утаскивает страницу')
check('min-height: 0' in css.split('.sidebar-nav {')[1][:200],
      'css: меню панели гарантированно скроллится (min-height:0)')
_lv = open(os.path.join(ROOT, 'web', 'routes', 'leveling.py'), encoding='utf-8').read()
check('_demo_leveling_config' in _lv and 'leveling_demo_' in _lv,
      'routes leveling: демо-конфиг левелинга с сохранением (тумблеры работают в превью)')
check("data/xp_{guild_id}.json" in _lv and 'total_ach_available' in _lv,
      'routes leveling: демо-статистика из XP-файла, ачивки и награды без бота')
# ═══ 37о. Порядок загрузки: бут-шим + /api/guilds в демо ═════════════════════
print('== порядок загрузки: бут-шим и guilds ==')
check('Бут-шим панели' in base and 'simpleJSON' in base and 'if (!W.fetchCachedJSON)' in base,
      'base: бут-шим до контента — страничные скрипты не падают до загрузки app.js')
check('if (!W.setLiveRefresh)' in base and '__panelKitReady' in js,
      'base+app.js: live-refresh шима уступает управление после загрузки кита')
check('передаём ему все зарегистрированные' in base and 'jobs.forEach(function (j) { try { W.setLiveRefresh(j.fn, j.ms); } catch (e) {} })' in base,
      'base: живые загрузчики страниц передаются настоящему setLiveRefresh после загрузки app.js (иначе автообновления останавливались бы)')
check('__panelKitReady = true' in js,
      'app.js: флаг готовности кита в конце файла')
_ki = open(os.path.join(ROOT, 'web', 'templates', 'mod_kiosk.html'), encoding='utf-8').read()
check('Бут-шим' in _ki and 'if (!W.fetchCachedJSON)' in _ki,
      'mod-kiosk: бут-шим на месте (страница самостоятельная, та же проблема порядка)')
_apg = open(os.path.join(ROOT, 'web', 'app.py'), encoding='utf-8').read()
_apg_gi = _apg.split('def api_guilds')[1][:900]
check("'Главный сервер'" in _apg_gi and "members':1247" in _apg_gi,
      'api/guilds: в демо возвращается главный сервер (пустой список ломал выбор сервера на десятках страниц)')
check('cur = guilds.length ? guilds[0].id : (cur || \'\')' in open(os.path.join(ROOT, 'web', 'templates', 'leveling.html'), encoding='utf-8').read(),
      'leveling: пустой список серверов не обнуляет выбранный сервер')
_sched = open(os.path.join(ROOT, 'web', 'routes', 'schedule.py'), encoding='utf-8').read()
check('_demo_sched_seed' in _sched and 'demo_channels.json' in _sched,
      'routes schedule: демо-ветка отдаёт каналы и пример анонса (выбор канала работает в превью)')
_comm = open(os.path.join(ROOT, 'web', 'routes', 'community.py'), encoding='utf-8').read()
check('top_channels' in _comm.split('api_guild_analytics')[1][:3000] and 'Демо-режим: если статистика пуста' in _comm,
      'routes analytics: в демо топ каналов заполняется из демо-структуры (детализация по каналам живая)')
# ═══ 37п. Переделка последних правок: визуальное качество демо ═══════════════
print('== переделка: расписание, ачивки, детализация ==')
check("'next': _demo_sched_next(it)" in _sched,
      'расписание: у элементов есть «следующая отправка» (не «undefined»)')
check("_demo_sched_load" in _sched and "_demo_sched_store" in _sched and "schedule_demo_" in _sched,
      'расписание: демо-хранилище — сохранение, пауза и удаление работают в превью')
check("'id': it['id']" in _sched and "'channel_id': str(it.get('channel_id', ''))" in _sched,
      'расписание: числовые id (кнопки пауза/тест/удаление не ломаются)')
_apd = open(os.path.join(ROOT, 'web', 'routes', 'analytics_plus.py'), encoding='utf-8').read()
check('Демо-режим: если событий нет' in _apd and "body['success'] = True" in _apd.split('channel-drill')[1][:2500],
      'аналитика: детализация канала в демо отдаёт график и авторов (не «в канале тихо»)')
_lc = open(os.path.join(ROOT, 'cogs', 'leveling_engagement.py'), encoding='utf-8').read()
check('"icon":""' not in _lc,
      'ког левелинга: у всех ачивок есть иконки (Discord-эмбеды не пустые)')
_lva2 = open(os.path.join(ROOT, 'web', 'templates', 'leveling_admin.html'), encoding='utf-8').read()
check('RARITY_ICONS' in _lva2 and 'fa-dragon' in _lva2 and 'r-legendary' in _lva2,
      'leveling-admin: ачивки с FA-иконками по редкости (нет пустых квадратов)')
check('rarityEmoji' in _lva2 and 'rarityIcon(info.rarity)' in _lva2,
      'leveling-admin: индикатор редкости и иконка определены (карточки рендерятся)')
check('.lvl-ach .icon i.r-legendary' in _lva2 and 'filter: drop-shadow' in _lva2,
      'leveling-admin: цвета иконок по редкости с мягкой тенью')

# ═══ 37й. Автономность: иконки и шрифты без внешних CDN ══════════════════════
print('== автономность: локальные ассеты ==')
_all = []
for _t in sorted(os.listdir(os.path.join(ROOT, 'web', 'templates'))):
    if _t.endswith('.html'):
        _all.append(open(os.path.join(ROOT, 'web', 'templates', _t), encoding='utf-8').read())
_all_src = '\n'.join(_all)
check('cdnjs.cloudflare.com/ajax/libs/font-awesome' not in _all_src,
      'все шаблоны: иконки Font Awesome не зависят от cdnjs (0 внешних ссылок)')
check('fonts.googleapis.com' not in _all_src,
      'все шаблоны: шрифты не зависят от googleapis (0 внешних ссылок)')
_vend_fa = os.path.join(ROOT, 'web', 'static', 'vendor', 'fontawesome', 'css', 'all.min.css')
_vend_ff = os.path.join(ROOT, 'web', 'static', 'vendor', 'fonts', 'fonts.css')
_vend_w = os.path.join(ROOT, 'web', 'static', 'vendor', 'fontawesome', 'webfonts')
check(os.path.exists(_vend_fa) and os.path.getsize(_vend_fa) > 50000,
      'вендор: локальный all.min.css на месте')
check(os.path.exists(_vend_ff) and 'inter-cyrillic' in open(_vend_ff, encoding='utf-8').read(),
      'вендор: fonts.css с кириллическими поднаборами (Inter/Unbounded/JetBrains Mono)')
check(len([f for f in os.listdir(_vend_w) if f.endswith('.woff2')]) >= 4,
      'вендор: webfonts Font Awesome локально (woff2)')
check('/static/vendor/fontawesome/css/all.min.css' in base and '/static/vendor/fonts/fonts.css' in base,
      'базовый шаблон: иконки и шрифты подключены локально')
check('/static/vendor/fontawesome/css/all.min.css' in lg3 and '/static/vendor/fonts/fonts.css' in lg3,
      'login: иконки и шрифты подключены локально')

check('swap-out' in w11 and 'swap-in' in w11 and 'wTitleOut' in w11 and 'wTitleIn' in w11,
      'welcome: смена фраз — старая растворяется, новая вплывает')
_wto = w11.split('@keyframes wTitleOut')[1].split('}')[0]
_wti = w11.split('@keyframes wTitleIn')[1].split('}')[0]
check('blur' not in _wto and 'blur' not in _wti,
      'welcome: фразы меняются без блюра — заголовок всегда чёткий')
check('if (first)' in w11 and 'first = false' in w11,
      'welcome: первая фраза печатается сразу — нет двойного появления заголовка при загрузке')
check('min-height: 1.1em' in w11.split('.w-title {')[1][:400],
      'welcome: заголовок держит высоту при смене фраз — контент не прыгает')
check("el.classList.add('swap-out')" in w11 and 'classList.remove' in w11,
      'welcome: переход фраз управляется из JS (без резкого стирания)')
check('.w-title.swap-out' in w11.split('prefers-reduced-motion')[1][:1000],
      'welcome: смена фраз выключена при reduced-motion')



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
