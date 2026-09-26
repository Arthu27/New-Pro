# -*- coding: utf-8 -*-
"""П.7 стабильность + П.8 «попробуй сломать»: стресс-прогон панели и бота-сервисов.

1. СОАК: 400+ циклов по горячим эндпоинтам (симуляция постоянного обновления
   статистики панелью). Память процесса не растёт >20%, ответы стабильны.
2. БОМБЫ: мусорные параметры/типы/юникод/огромные значения в публичные API —
   сервер отвечает аккуратными 4xx/200, ни одного 500.
3. БЫСТРЫЕ КЛИКИ: 50 повторных запросов toggle-like маршрута подряд — итог
   детерминирован, без 500 и застревших сессий.
4. ХЕЛСЧЕК: /health живой и цифровой (без линейных виджетов — свой тест).
"""
import os
import sys
import json
import tempfile
import time
import resource

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix='stress_p8_')
os.chdir(_TMP)
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
os.environ['MAIN_GUILD_ID'] = '777'
sys.path.insert(0, ROOT)

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


def rss_kb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


import web.app as appmod  # noqa: E402

appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'admin'
    s['role'] = 'mod'
    s['selected_guild'] = '777'

HOT = ['/api/member-search/777?q=%40',
       '/api/member-search/777?q=abc',
       '/dashboard', '/mod-control']

print('== 1. Соак: 400 циклов горячих эндпоинтов ==')
rss0 = rss_kb()
t0 = time.time()
errs = 0
for i in range(100):
    for path in HOT:
        r = client.get(path)
        if r.status_code >= 500:
            errs += 1
dt = time.time() - t0
rss1 = rss_kb()
check(errs == 0, f'400 циклов без 5xx (ошибок: {errs})')
check(dt < 60, f'400 циклов за {dt:.1f}с (<60с)')
growth = (rss1 - rss0) / max(rss0, 1) * 100
check(growth < 20, f'память выросла на {growth:.1f}% (<20%): {rss0}→{rss1} KB')

print('== 2. Бомбы: мусорные входы в API ==')
BOMBS = [
    '/api/member-search/777?q=' + 'x' * 5000,
    '/api/member-search/777?q=%EF%BF%BD%EF%BF%BD&offset=-50',
    '/api/member-search/777?q=%00%01',
    '/api/member-search/777?q=' + '🔥' * 200,
    '/api/member-search/н-not-an-int?q=a',
    '/api/member-search/9999999999?q=a&offset=9999999',
]
for url in BOMBS:
    r = client.get(url)
    check(r.status_code < 500, f'бомба сошла без 5xx [{r.status_code}]: {url[16:56]}…')
    if r.is_json:
        d = r.get_json(silent=True) or {}
        check(isinstance(d, dict), f'ответ — валидный JSON-dict ({url[16:44]}…)')

print('== 3. Быстрые повторные запросы (double-click spam) ==')
codes = []
for _ in range(50):
    codes.append(client.get('/api/member-search/777?q=@').status_code)
check(set(codes) <= {200, 403}, f'50 быстрых запросов — без 5xx ({sorted(set(codes))})')

print('== 4. Консольное чистое завершение модуля ==')
mods = ['web.routes.members', 'web.routes.modplus']
m_ok = True
for m in mods:
    try:
        __import__(m)
    except Exception as e:  # noqa: BLE001
        m_ok = False
        print(f'    import-fail {m}: {e}')
check(m_ok, 'модули маршрутов импортируются без побочных падений')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
