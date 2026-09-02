# -*- coding: utf-8 -*-
"""Раздел «Доступ»: панели и роли, меню панели, права команд.

Что нашёл подробный разбор раздела:

1. Блок `if __name__ == '__main__': app.run(...)` стоял В СЕРЕДИНЕ
   web/app.py (строка 4057 из 4580). app.run() блокирует импорт, поэтому
   четыре маршрута ниже не регистрировались, и «python web/app.py»
   отвечал на них 404:
     /api/forgot-password, /api/reset-password,
     /api/notifications/poll, /api/activity-feed
   Колокольчик уведомлений опрашивает /api/notifications/poll на КАЖДОЙ
   странице (app.js:1023) — то есть 404 летел постоянно. Через main.py
   (бот поднимает панель сам) __name__ != '__main__', поэтому тесты,
   которые импортируют web.app, этого не видели.

2. Страницы «Панели и роли» и «Права команд» подписаны на SSE-топик
   role_map, но его никто не публиковал: правка карты ролей доезжала до
   соседней вкладки только по страховочному таймеру (30 с).

3. Во всех 8 обработчиках /api/role-permissions/<guild_id>/... стоял
   int(guild_id) без проверки — 500 с трейсбеком на нечисловом id.
   Глобальный guard ловит такое только когда MAIN_GUILD_ID задан.

4. 15 страниц имели <title> с дефисом («Права команд - Hakumo») при 68
   с тирем («— Hakumo»).

Запуск:  .venv/bin/python tests/test_access_category.py
"""
import glob
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DEMO_MODE', '1')
os.environ.setdefault('MAIN_GUILD_ID', '987654321098765432')

PASS = FAIL = 0
GID = '987654321098765432'
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


def _backup(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return f.read()


def _restore(path, text):
    if text is None:
        if os.path.exists(path):
            os.remove(path)
    else:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)


import web.app as appmod  # noqa: E402
from web.app import app  # noqa: E402
from services import live_bus  # noqa: E402

print('== 1. Маршруты после app.run() не регистрируются — их быть не должно ==')
src = io.open(os.path.join(ROOT, 'web', 'app.py'), encoding='utf-8').read()
run_pos = src.find('app .run (host')
if run_pos < 0:
    run_pos = src.find('app.run(host')
check(run_pos > 0, 'app.run() в web/app.py найден')
tail = src[run_pos:]
lost = re.findall(r'@app\s*\.route\s*\(\s*[\'"]([^\'"]+)', tail)
check(not lost, f'после app.run() маршрутов нет (иначе 404): {lost}')

main_block = src.rfind("if __name__ =='__main__':")
if main_block < 0:
    main_block = src.rfind('if __name__ == "__main__":')
check(main_block > run_pos - 2000 and main_block > len(src) * 0.9,
      'блок __main__ стоит в самом конце файла')

for path in ('/api/forgot-password', '/api/reset-password',
             '/api/notifications/poll', '/api/activity-feed'):
    rules = [r for r in app.url_map.iter_rules() if str(r) == path]
    check(bool(rules), f'маршрут {path} зарегистрирован')

print('== 2. Живая проверка: четыре маршрута отвечают ==')
client = app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'
    s['selected_guild'] = GID

check(client.get('/api/notifications/poll').status_code == 200,
      '/api/notifications/poll -> 200 (колокольчик на каждой странице)')
check(client.get('/api/activity-feed').status_code == 200,
      '/api/activity-feed -> 200 (лента активности)')
r = client.post('/api/forgot-password', json={'discord_id': '1'})
check(r.status_code in (200, 400, 404),
      f'/api/forgot-password отвечает, а не 404: {r.status_code}')
r = client.post('/api/reset-password', json={})
check(r.status_code in (200, 400, 404),
      f'/api/reset-password отвечает, а не 404: {r.status_code}')

print('== 3. Карта ролей шлёт SSE-сигнал role_map ==')
rm_bk = _backup('data/role_map.json')
q, unsub = live_bus.subscribe(['role_map'])
r = client.post('/api/role-map', json={'role_id': '4242', 'panel_role': 'mod'})
got = []
try:
    got.append(q.get(timeout=2))
except Exception:
    pass
check(r.status_code == 200 and (r.get_json() or {}).get('success'),
      f'сопоставление сохранено: {r.status_code}')
check(bool(got), f'опубликован топик role_map: {got}')

q2, unsub2 = live_bus.subscribe(['role_map'])
client.delete('/api/role-map/4242')
got2 = []
try:
    got2.append(q2.get(timeout=2))
except Exception:
    pass
unsub(); unsub2()
check(bool(got2), f'удаление сопоставления тоже шлёт role_map: {got2}')
_restore('data/role_map.json', rm_bk)

print('== 4. Нечисловой id сервера: внятная 400, а не 500 с трейсбеком ==')
# Глобальный guard перехватывает чужой id только когда MAIN_GUILD_ID задан;
# без него запрос доходит до обработчика — там и ловим.
_saved_main = appmod.MAIN_GUILD_ID
appmod.MAIN_GUILD_ID = ''
try:
    bad_gid = 'не-число'
    cases = [
        ('GET', f'/api/role-permissions/{bad_gid}'),
        ('POST', f'/api/role-permissions/{bad_gid}/action/set'),
        ('POST', f'/api/role-permissions/{bad_gid}/actions/clear'),
        ('POST', f'/api/role-permissions/{bad_gid}/set'),
        ('POST', f'/api/role-permissions/{bad_gid}/clear'),
        ('POST', f'/api/role-permissions/{bad_gid}/preset'),
        ('POST', f'/api/role-permissions/{bad_gid}/category/everyone'),
        ('POST', f'/api/role-permissions/{bad_gid}/category/assign'),
    ]
    for method, url in cases:
        if method == 'GET':
            r = client.get(url)
        else:
            r = client.post(url, json={})
        body = r.get_json() or {}
        check(r.status_code == 400 and 'сервера' in str(body.get('error', '')).lower(),
              f'{url.split("/api")[1][:46]} -> 400 «{body.get("error")}»')
finally:
    appmod.MAIN_GUILD_ID = _saved_main

print('== 5. Права команд: нормальный id работает ==')
r = client.get(f'/api/role-permissions/{GID}')
d = r.get_json() or {}
check(r.status_code == 200 and d.get('success'), f'список ролей и команд: {r.status_code}')
check(len(d.get('roles', [])) > 0, f'ролей в ответе {len(d.get("roles", []))}')
check(len(d.get('categories', {})) > 0,
      f'категорий команд {len(d.get("categories", {}))}')
check(r.headers.get('ETag'), 'ETag отдаётся (повторный опрос — 304 без тела)')
etag = r.headers.get('ETag')
r2 = client.get(f'/api/role-permissions/{GID}', headers={'If-None-Match': etag or ''})
check(r2.status_code in (200, 304), f'повторный запрос: {r2.status_code}')

print('== 6. Названия: один суффикс и одно тире во всех <title> ==')
bad_dash, bad_hyphen = [], []
for f in sorted(glob.glob(os.path.join(ROOT, 'web', 'templates', '*.html'))):
    t = io.open(f, encoding='utf-8').read()
    m = re.search(r'\{%\s*block title\s*%\}(.*?){%\s*endblock', t, re.S)
    if not m:
        continue
    title = m.group(1)
    if 'Hakumo' not in title:
        continue
    # base.html — запасной заголовок без разделителя («Панель Hakumo»),
    # он подставляется, когда страница не определила свой block title
    if os.path.basename(f) == 'base.html':
        continue
    if ' - Hakumo' in title:
        bad_hyphen.append(os.path.basename(f))
    if '— Hakumo' not in title:
        bad_dash.append(os.path.basename(f))
check(not bad_hyphen, f'ни одна страница не использует дефис: {bad_hyphen}')
check(not bad_dash, f'все заголовки с тирем «— Hakumo»: {bad_dash}')

print('== 7. Раздел «Доступ» в меню: три страницы на месте ==')
from services.panel_menu import MENU  # noqa: E402
acc = [g for g in MENU if g['key'] == 'access']
check(len(acc) == 1, 'группа «Доступ» есть')
paths = [p['path'] for p in acc[0]['pages']] if acc else []
check(paths == ['/panel-access', '/panel-menu', '/role-permissions'],
      f'состав раздела: {paths}')
labels = [p['label'] for p in acc[0]['pages']] if acc else []
check(labels == ['Панели и роли', 'Меню панели', 'Права команд'],
      f'подписи: {labels}')
for path, label in zip(paths, labels):
    for f in sorted(glob.glob(os.path.join(ROOT, 'web', 'templates', '*.html'))):
        t = io.open(f, encoding='utf-8').read()
        m = re.search(r'\{%\s*block page_title\s*%\}(.*?){%\s*endblock', t, re.S)
        if m and label in re.sub(r'<[^>]+>', '', m.group(1)):
            break
    else:
        check(False, f'заголовок страницы «{label}» не найден ни в одном шаблоне')
        continue
    check(True, f'заголовок страницы «{label}» совпадает с меню')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
