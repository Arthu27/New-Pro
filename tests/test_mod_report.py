# -*- coding: utf-8 -*-
"""Отчёт модерации (идеи #31-33).

Проверяем: окно по дням и отброс старых/нетипированных, топ модераторов
(безымянные не считаются), типы действий, рецидивистов по user_name,
CSV-секции, права mod+ (read-only страница), шаблон и меню.

Запуск: python3 tests/test_mod_report.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

_TMP = tempfile.mkdtemp(prefix='aether_modrep_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'

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


from web.routes import mod_report as MR  # noqa: E402

NOW = datetime.now().replace(minute=12, second=0, microsecond=0)
audit = {'777': [], '888': []}


def ev(days_ago, action, mod, user):
    return {'category': 'mod', 'action': action, 'mod_name': mod,
            'user_name': user,
            'timestamp': (NOW - timedelta(days=days_ago)).isoformat()}


audit['777'] = [
    ev(1, 'Бан', 'Старший', 'Нарушитель'),
    ev(2, 'Мут', 'Старший', 'Нарушитель'),
    ev(2, 'Варн', 'Младший', 'Нарушитель'),
    ev(3, 'Бан', 'Старший', 'Тихоня'),
    ev(0, 'Кик', None, 'Тихоня'),              # безымянный мод — в общий зачёт, не в топ
    ev(25, 'Бан', 'Старший', 'Древний'),       # вне 7/14, внутри 30 дней
    ev(2, 'Бан', 'Старший', None),             # без цели — не рецидивист
    {'category': 'message', 'action': 'msg', 'timestamp': NOW.isoformat()},
    'битая',
]
audit['888'].append(ev(1, 'Бан', 'Чужой', 'Кто-то'))
with open('data/audit_log.json', 'w', encoding='utf-8') as fh:
    json.dump(audit, fh)

print('== 1. Чистый отчёт ==')
r = MR.mod_report(777, days=7, now=NOW)
check(r['total'] == 6, 'всего 6 (цель-безымянная и мод-безымянный считаются)')
check(r['per_mod'][0] == ('Старший', 4) and ('Младший', 1) in r['per_mod'],
      'топ модераторов')
check(r['mods_total'] == 2, 'модераторов двое')
acts = dict(r['by_action'])
check(acts == {'Бан': 3, 'Мут': 1, 'Варн': 1, 'Кик': 1}, 'типы действий')
check(r['recidivists'] == [{'name': 'Нарушитель', 'count': 3}], 'рецидивист один (3+)')
check(r['recidivists_total'] == 1, 'счётчик рецидивистов')
check(len(r['per_day']['labels']) == 7 and r['per_day']['counts'][-2] == 1
      and r['per_day']['counts'][-3] == 3, 'ряд по дням (вчера 1, позавчера 3)')
r30 = MR.mod_report(777, days=30, now=NOW)
check(r30['total'] == 7, 'окно 30 дней захватывает древнее событие')
check(MR.mod_report(888, days=7, now=NOW)['total'] == 1, 'чужой сервер отдельно')
empty = MR.mod_report(424242, days=7, now=NOW)
check(empty['total'] == 0 and empty['per_mod'] == [] and empty['recidivists'] == [],
      'пустой сервер — нули')
check(MR.mod_report(777, days='мусор', now=NOW)['days'] == 7, 'мусорный период — дефолт 7')
check(MR.mod_report(777, days=365, now=NOW)['days'] == 90, 'период капнут сверху (90)')

txt = MR.mod_report_csv(777, days=7, now=NOW)
check('Модератор;Действий' in txt and 'Старший;4' in txt, 'CSV: секция модераторов')
check('Действие;Кол-во' in txt and 'Бан;3' in txt, 'CSV: типы')
check('Рецидивист (3+);Нарушений' in txt and 'Нарушитель;3' in txt, 'CSV: рецидивисты')

print('== 2. API: права ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


check(client.get('/mod-report').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get('/api/mod-report').status_code in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get('/mod-report').status_code == 403, 'uye нельзя')
check(client.get('/api/mod-report').status_code == 403, 'uye нельзя API')
login('mod')
check(client.get('/mod-report').status_code == 200, 'mod читает страницу')
rr = client.get('/api/mod-report?days=30')
check(rr.status_code == 200 and rr.get_json()['total'] == 7, 'mod читает API')
rc = client.get('/api/mod-report.csv?days=7')
check(rc.status_code == 200 and 'mod_report_777_' in rc.headers.get('Content-Disposition', ''),
      'mod скачивает выгрузку')

print('== 3. Шаблон и меню ==')
html = client.get('/mod-report').get_data(as_text=True)
check('mrKpis' in html and 'mrMods' in html, 'страница монтирует блоки')
tpl = open(os.path.join(ROOT, 'web/templates/mod_report.html'), encoding='utf-8').read()
emoji = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not emoji.search(tpl), 'в шаблоне нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
check("method: 'POST'" not in tpl, 'честно read-only: ни одного POST')
import services.panel_menu as PM
paths = [pg['path'] for g in PM.MENU for pg in g['pages']]
check('/mod-studio' in paths, 'отчёт живёт в Студии модерации (единая точка входа)')
check('/mod-report' not in PM.PAGE_COGS, 'отчёт — от аудит-файла, в PAGE_COGS не входит')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
