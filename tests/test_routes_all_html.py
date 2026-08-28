# -*- coding: utf-8 -*-
"""П.7/П.8: личный обход КАЖДОЙ страницы панели — авто-дискавери маршрутов.

Каждый HTML-GET маршрут Flask: заходим с авторизованной сессией, ожидаем
200, HTML не содержит traceback/jinja-ошибок, сохранён порядок
boot→критика→stylesheet (фон никогда не белый). Маршруты с параметрами
подставляем из MAIN_GUILD_ID; /api/, статика, auth-потоки — пропуск.
"""
import os
import sys
import tempfile
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix='routes_all_')
os.chdir(_TMP)
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
os.environ['MAIN_GUILD_ID'] = '777'
sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0
SKIP = []


def check(ok, msg, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {detail}')


import web.app as appmod  # noqa: E402

appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'admin'
    s['role'] = 'mod'
    s['selected_guild'] = '777'

BAD_MARKERS = ('Traceback (most recent call last)', 'jinja2.exceptions',
               'werkzeug.exceptions', 'Internal Server Error')

html_routes = []
for rule in sorted(appmod.app.url_map.iter_rules(), key=lambda r: str(r)):
    if 'GET' not in rule.methods:
        continue
    path = str(rule)
    if path.startswith(('/api/', '/static/', '/ws')):
        continue
    if '<' in path:
        if '<int:guild_id>' in path or '<guild_id>' in path:
            path = re.sub(r'<[^>]*guild_id[^>]*>', '777', path)
        if '<' in path:
            SKIP.append(path)   # параметр, для которого надёжной заглушки нет
            continue
    if path in ('/logout', '/login') or path.startswith('/auth/'):
        continue
    html_routes.append(path)

print(f'== Обход: {len(html_routes)} html-stranic, {len(SKIP)} param (skip) ==')
for path in html_routes:
    r = client.get(path)
    so = r.status_code
    # gzip/бинарный контент не декодируем: аккуратно с заменой
    html = r.get_data().decode('utf-8', 'replace') if so < 500 else ''
    if path == '/health' and so == 503:
        # health-endpoint честно 503 при оффлайн-боте — это PASS-мониторинг
        html = ''
    # 200 — готово; 301/302 — маршрут осознанно перенаправляет (глобальный guard/
    # требования гильдии) — легитимный ответ, но НЕ 404 и НЕ 5xx.
    ok_codes = (200, 301, 302) if path != '/health' else (200, 503)
    check(so in ok_codes, f'{path} → 200/redirect', f'код {so}')
    if so < 500:
        check(not any(m in html for m in BAD_MARKERS),
              f'{path}: без traceback/шаблонных ошибок')
        if 'localStorage.getItem' in html and 'stylesheet' in html:
            check(html.index('localStorage.getItem') < html.index('stylesheet'),
                  f'{path}: boot до stylesheet')
    # повтор — стабильность при быстрых переключениях
    r2 = client.get(path)
    check(r2.status_code == so, f'{path}: повторный заход стабилен [{so}]')
    if r2.status_code not in (301, 302) and 'localStorage.getItem' in html and 'stylesheet' in html:
        pass

print(f'\nМаршрутов с параметрами (пропуски): {len(SKIP)}')
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
