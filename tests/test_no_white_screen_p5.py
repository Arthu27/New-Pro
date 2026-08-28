# -*- coding: utf-8 -*-
"""П.5: фон никогда не становится белым при переходах по панели.

Гарантии:
1. base.html: boot-скрипт с data-theme стоит ПЕРЕД любым stylesheet;
   затем критический inline-стиль (тёмный/светлый фон + color-scheme),
   затем внешние CSS — первый кадр всегда тематический.
2. app.js: pageTransitions — fade не висит (bfcache pageshow), переход
   быстрый, preload следующих страниц (prefetch), API/auth не пострадают.
3. Все внутренние страницы наследуют base.html ⇒ единая сцена.
4. HTTP: полученные страницы содержат критический boot до stylesheet.
"""
import os
import sys
import glob
import re
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0


def check(ok, msg, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {detail}')


print('== 1. base.html: порядок бут-кода ==')
base = open(os.path.join(ROOT, 'web/templates/base.html'), encoding='utf-8').read()
head = base[base.index('<head>'):base.index('</head>')]
i_boot = head.index("localStorage.getItem('hakumo_theme')")
i_css1 = head.index('stylesheet')
i_crit = head.index('П.5 — критическая сцена')
check(i_boot < i_css1, 'boot-скрипт темы раньше всех stylesheet')
check(i_css1 > i_crit, 'критический inline-стиль раньше всех stylesheet')
crit = head[head.index('<style>'):head.index('</style>')]
check('#0f1013' in crit and 'data-theme="light"]' in crit and '#f5f6f8' in crit,
      'критический стиль: тёмный + светлый фон под любую тему')
check('color-scheme' in crit, 'color-scheme в критическом стиле (скроллбары/поля не будут белыми)')
check('prefers-color-scheme' in head, 'первый визит: тема берётся из системы, а не жёстко light')

print('== 2. app.js: переходы без белой полосы ==')
app = open(os.path.join(ROOT, 'web/static/app.js'), encoding='utf-8').read()
pt = app[app.index('Плавные переходы между страницами'):]
pt = pt[:pt.index('/* ── 14b.')]
check("'pageshow'" in pt and "classList.remove('page-leaving')" in pt,
      'bfcache: page-leaving снимается на pageshow')
check("rel = 'prefetch'" in pt and "'mouseover'" in pt and "'touchstart'" in pt,
      'prefetch следующей страницы по наведению/тапу')
check("'/api/'" in pt and "'/auth/'" in pt, 'prefetch не трогает API/auth')
m = re.search(r'setTimeout\(function \(\) \{ window\.location\.href = href; \}, (\d+)\)', pt)
check(bool(m) and int(m.group(1)) <= 90, f"межстраничный fade короткий ({m.group(1) if m else '—'} мс)")

print('== 3. Все внутренние страницы наследуют base ==')
STANDALONE = {'base.html', 'login.html', 'register.html', 'welcome.html',
              'status_public.html', 'public_apply.html', 'mod_kiosk.html',
              '_sidebar_nav.html'}



print('== 3.1. Самостоятельные страницы: тоже критически тёмные/светлые ==')
import os as _os
for f, crit_bg in [('login.html', '#0f1013'), ('register.html', '#0f1013'),
                   ('welcome.html', '#0f1013'), ('status_public.html', '#0f1013'),
                   ('public_apply.html', '#0f1013'), ('mod_kiosk.html', '#f5f6f8')]:
    src = open(_os.path.join(ROOT, 'web/templates', f), encoding='utf-8').read()
    check('П.5 — критическая сцена' in src and crit_bg in src and src.index('<style>') < src.index('stylesheet'),
          f'{f}: критический фон {crit_bg} до stylesheet')
orphans = []
for f in glob.glob(os.path.join(ROOT, 'web/templates/*.html')):
    name = os.path.basename(f)
    if name in STANDALONE:
        continue
    src = open(f, encoding='utf-8').read()
    if '{% extends' not in src:
        orphans.append(name)
check(not orphans, f'нет страниц без базового шаблона (сироты: {orphans})')

print('== 4. HTTP: страницы отдаются с бутом до стилей ==')
_TMP = tempfile.mkdtemp(prefix='p5_http_')
os.chdir(_TMP)
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
os.environ.setdefault('MAIN_GUILD_ID', '777')
sys.path.insert(0, ROOT)
import web.app as appmod  # noqa: E402
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'admin'
    s['role'] = 'mod'
    s['selected_guild'] = '777'

print('== 4.1. Многократные переключения разделов подряд (x3 круга) ==')
pages = ['/dashboard', '/analytics', '/leaderboards', '/karma', '/mod-control']
for _round in range(3):
    for path in pages:
        r = client.get(path)
        assert r.status_code == 200, (path, r.status_code)
for path in pages:
    r = client.get(path)
    html = r.get_data(as_text=True)
    if r.status_code != 200:
        check(False, f'GET {path} — 200 ОК', f'код {r.status_code}')
        continue
    if "localStorage.getItem('hakumo_theme')" not in html or 'stylesheet' not in html:
        check(False, f'{path}: бут-код до stylesheet', 'фрагменты не найдены')
        continue
    order_ok = (html.index("localStorage.getItem('hakumo_theme')") < html.index('stylesheet'))
    crit_ok = 'П.5 — критическая сцена' in html
    check(order_ok and crit_ok, f'{path}: boot→критика→stylesheet в выдаче')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
