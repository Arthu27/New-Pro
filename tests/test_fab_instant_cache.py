# -*- coding: utf-8 -*-
"""FAB «+» кликабелен + мгновенный кэш данных панели.

Баги:
  • FAB backdrop имел класс «fab backdrop» и наследовал layout кнопки;
    закрытые fab-item перехватывали клики (opacity:0 без pointer-events:none).
  • /api/my-notifications отдаёт message, drawer читал только body/detail.
  • GET JSON почти без ETag/fetchCachedJSON — страницы ждали сеть каждый раз.

Запуск: python3 tests/test_fab_instant_cache.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_fab_cache_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


js = open(os.path.join(ROOT, 'web/static/app.js'), encoding='utf-8').read()
css = open(os.path.join(ROOT, 'web/static/style.css'), encoding='utf-8').read()
guard = open(os.path.join(ROOT, 'web/static/click-guard.js'), encoding='utf-8').read()
pickers = open(os.path.join(ROOT, 'web/static/pickers.js'), encoding='utf-8').read()
app = open(os.path.join(ROOT, 'web/app.py'), encoding='utf-8').read()

print('== FAB + ==')
fab = js[js.find('function fabInit'):js.find('function tourStart')]
check("className = 'fab-backdrop'" in fab, 'backdrop без класса .fab')
check("className = 'fab backdrop'" not in fab, 'старый «fab backdrop» убран')
check('stopPropagation' in fab and 'preventDefault' in fab,
      'клик по «+» не всплывает')
check('!items.length' in fab or 'items.length' in fab, 'пустой FAB — fallback')
check("'/channels'" in fab, 'FAB знает про /channels')
check('pointer-events: none' in css and '.fab.open .fab-item' in css,
      'закрытые fab-item не перехватывают клик')
check('.fab-backdrop' in css, 'стили .fab-backdrop')
check('z-index: 2250' in css or 'z-index:2250' in css, 'FAB выше mobile-nav')
check('.fab-backdrop.show' in guard, 'click-guard знает fab-backdrop')

print('== уведомления ==')
own = js[js.find('var ownItems'):js.find('var all = sysItems')]
check('n.message' in own and 'n.body' in own, 'ownItems: body || message || detail')

print('== мгновенный кэш ==')
check('sessionStorage' in js and 'hakumo_etag_json' in js,
      'JSON кэш переживает F5 (sessionStorage)')
check('cacheFirst' in js, 'cache-first opt-in для списков')
check('window.apiGet' in js, 'алиас apiGet = fetchCachedJSON')
check('fetchCachedJSON' in pickers, 'пикеры каналов/ролей через кэш')
check('_ETAG_PREFIXES' in app and '/api/guild/' in app,
      'сервер: ETag на /api/guild/*')
check("'/api/bot-settings'" in app and "'/api/channels'" in app,
      'сервер: ETag whitelist расширен')

# шаблоны: ключевые страницы на fetchCachedJSON
for name in ('channels.html', 'bot_settings.html', 'roles.html', 'dashboard.html'):
    src = open(os.path.join(ROOT, 'web/templates', name), encoding='utf-8').read()
    check('fetchCachedJSON' in src, f'{name}: fetchCachedJSON')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
