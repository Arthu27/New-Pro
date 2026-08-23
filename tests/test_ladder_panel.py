# -*- coding: utf-8 -*-
"""Лестница наказаний (идеи #156-160).

Ступени через _steps/_fmt_step кога (сортировка, подписи «мут на 10 мин»,
кик, «бан навсегда»), правила ladder-add (кламп 1..100/0..10000, кик без
длительности, дефолт 10, дедуп по числу, юнит-фолбэк minute), ladder-remove
текстами, симуляция ladder-test по зеркалу варнов, «вес ступеней», карточка
Pillow офлайн, CSV, права, шаблон, меню.

Запуск: python3 tests/test_ladder_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_ladder_test_')
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


from cogs import ladder as LD  # noqa: E402
from web.routes import ladder_panel as LP  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')

# Фикстуры до чтений (файлы кога — простые json).
json.dump({'steps': [
    {'count': 5, 'action': 'ban', 'duration': 0, 'unit': 'minute'},
    {'count': 2, 'action': 'mute', 'duration': 10, 'unit': 'minute'},
    {'count': 3, 'action': 'kick', 'duration': 0, 'unit': 'minute'}]},
    open('data/warn_config_777.json', 'w', encoding='utf-8'))
json.dump({'steps': []}, open('data/warn_config_555.json', 'w', encoding='utf-8'))
json.dump({'777': {'111': [{'r': 1}, {'r': 2}, {'r': 3}],
                   '222': [{'r': 1}],
                   '333': [{'r': i} for i in range(7)]}},
          open('data/warnings.json', 'w', encoding='utf-8'))

print('== 1. Ступени и подписи кога ==')
steps = LP.steps_of(LP.load_cfg('777'))
check([s['count'] for s in steps] == [2, 3, 5], 'сортировка по числу варнов')
check([s['label'] for s in steps] == ['мут на 10 мин', 'кик', 'бан навсегда'],
      'подписи его _fmt_step')
check(LD._fmt_step({'action': 'timeout', 'duration': 2, 'unit': 'hour'})
      == 'мут на 2 ч', 'timeout читается как мут, часы')
check(LD._fmt_step({'action': 'mute', 'duration': 1, 'unit': 'day'})
      == 'мут на 1 дн', 'дни')
check(LP.steps_of({'thresholds': [{'count': 4, 'action': 'ban'}]})[0]['count'] == 4,
      'легаси-ключ thresholds тоже читается, как у _steps')
check(LP.steps_of(LP.load_cfg('321')) == [], 'без файла — пустые ступени')

print('== 2. Ступени из панели — правила ladder-add ==')
ok, err, _ = LP.add_flow('555', 'мусор', 'mute', 10, 'minute')
check(not ok and err == LP.ERR_COUNT, 'мусорное число — отказ')
ok, err, _ = LP.add_flow('555', 3, 'удалить нахрен', 10, 'minute')
check(not ok and err == LP.ERR_ACTION, 'левое действие — отказ')
ok, err, p = LP.add_flow('555', 3, 'kick', 60, 'minute')
check(ok and p['message'] == 'Ступень сохранена: 3 варнов → кик. '
                             'Всего ступеней: 1.', 'кик стёр длительность — как команда')
ok, err, p = LP.add_flow('555', 0, 'mute', None, 'недель')
check(ok and p['steps'][0]['count'] == 1 and p['steps'][0]['duration'] == 10
      and p['steps'][0]['unit'] == 'minute',
      'кламп 1, дефолт длительности 10, юнит-фолбэк minute')
ok, err, p = LP.add_flow('555', 200, 'mute', 999999, 'hour')
check(ok and p['steps'][-1]['count'] == 100 and p['steps'][-1]['duration'] == 10000
      and p['steps'][-1]['label'] == 'мут на 10000 ч', 'потолки 100/10000 — молча')
ok, err, p = LP.add_flow('555', 3, 'ban', 0, 'day')
check(ok and len(p['steps']) == 3 and p['steps'][1]['label'] == 'бан навсегда',
      'дедуп: ступень на 3 переписана, не задвоена')
check(p['message'] == 'Ступень сохранена: 3 варнов → бан навсегда. '
                      'Всего ступеней: 3.', 'текст сохранения словами команды')
stored = LP.load_cfg('555')['steps']
check(len(stored) == 3, 'файл кога пополнен теми же записями')

print('== 3. Удаление ==')
ok, err, _ = LP.remove_flow('555', 42)
check(not ok and err == 'Ступени на 42 варнов нет.', 'чужая ступень — слова команды')
ok, err, p = LP.remove_flow('555', 3)
check(ok and p['message'] == 'Ступень на 3 варнов убрана. Осталось: 2.'
      and [s['count'] for s in p['steps']] == [1, 100], 'убрана — текст и остаток')
ok, err, _ = LP.remove_flow('555', 'мусор')
check(not ok and err == LP.ERR_COUNT, 'удаление мусора — отказ')

print('== 4. Симулятор ladder-test ==')
ok, err, _ = LP.simulate_view('777', 'мусор')
check(not ok and err == 'Некорректный ID пользователя', 'битый ID — текст валидатора')
ok, err, v = LP.simulate_view('777', '111')
check(ok and v['total'] == 3 and v['matched']['label'] == 'кик',
      '3 варна -> активен кик')
check(v['next']['count'] == 5 and 'осталось 2' in v['lines'][2],
      'следующая ступень и «осталось N»')
check(v['lines'][0] == 'Сейчас предупреждений: 3', 'первая строка словами команды')
ok, err, v = LP.simulate_view('777', '222')
check(v['matched'] is None and
      v['lines'][1] == 'Активной меры нет — участник ниже первой ступени.',
      'ниже первой ступени — её строка')
check('2 варнов → мут на 10 мин (осталось 1)' in v['lines'][2], 'до первой — один варн')
ok, err, v = LP.simulate_view('777', '333')
check(v['matched']['label'] == 'бан навсегда' and v['next'] is None,
      '7 варнов — последняя ступень, следующей нет')

print('== 5. Вес ступеней и CSV ==')
imp = LP.impact_view('777')
check([s['users'] for s in imp['steps']] == [2, 2, 1],
      'на 2+: двое; на 3+: двое; на 5+: один')
check(imp['warned_users'] == 3, 'всего с варнами — трое')
check(LP.impact_view('321') == {'steps': [], 'warned_users': 0}, 'пусто — нули')
rows = LP.csv_rows('777')
check(rows[0] == (2, 'mute', 10, 'minute', 'мут на 10 мин', 2)
      and rows[2] == (5, 'ban', 0, 'minute', 'бан навсегда', 1), 'строки выгрузки')
check(LP._csv_cell('а;б\nв') == 'а,б в', 'ячейки чистятся')

print('== 6. API и права ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


VW = '/api/guild/777/ladder/view'
check(client.get('/ladder').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get(VW).status_code in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get(VW).status_code == 403, 'uye не смотрит')
check(client.get('/api/guild/777/ladder/card.png').status_code == 403,
      'uye не видит карточку')
login('mod')
page = client.get('/ladder')
check(page.status_code == 200 and 'Лестница наказаний' in page.get_data(as_text=True),
      'mod открывает страницу')
d = client.get(VW).get_json()
check(d['success'] and len(d['steps']) == 3 and d['impact']['warned_users'] == 3
      and d['can_edit'] is False, 'вид через API для mod')
d = client.get('/api/guild/777/ladder/simulate?user=111').get_json()
check(d['success'] and d['matched']['label'] == 'кик', 'симулятор через API')
check(client.get('/api/guild/777/ladder/simulate?user=x').status_code == 400,
      'симулятор: битый ID — 400')
r = client.get('/api/guild/777/ladder/card.png')
check(r.status_code == 200 and r.mimetype == 'image/png'
      and r.get_data().startswith(b'\x89PNG'), 'карточка рисуется офлайн')
check(client.post('/api/guild/777/ladder/add', json={'count': 7}).status_code == 403,
      'mod не меняет ступени')
login('admin')
r = client.post('/api/guild/555/ladder/add',
                json={'count': '9', 'action': 'mute', 'duration': '45', 'unit': 'hour'})
d = r.get_json()
check(r.status_code == 200
      and d['message'] == 'Ступень сохранена: 9 варнов → мут на 45 ч. '
                          'Всего ступеней: 3.', 'admin добавил — текст сложился')
r = client.post('/api/guild/555/ladder/remove', json={'count': 9})
check(r.status_code == 200 and 'Осталось: 2.' in r.get_json()['message'],
      'admin убрал')
r = client.post('/api/guild/555/ladder/remove', json={'count': 9})
check(r.status_code == 400 and r.get_json()['error'] == 'Ступени на 9 варнов нет.',
      'повторное — 404-текст команды, код 400')
ex = client.get('/api/guild/777/ladder/export.csv')
body = ex.get_data(as_text=True)
check(ex.status_code == 200 and
      ex.headers['Content-Disposition'].endswith('ladder_777.csv'), 'CSV: имя файла')
check(body.startswith('\ufeffcount;action;duration;unit;label;users_at_or_above'),
      'CSV: BOM и шапка')
check(len(body.strip().split('\n')) == 4, 'CSV: 3 ступени + шапка')
login('uye')
check(client.get('/api/guild/777/ladder/export.csv').status_code == 403,
      'uye не выгружает')
login('mod')

print('== 7. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/ladder.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
src = open(os.path.join(ROOT, 'web/routes/ladder_panel.py'), encoding='utf-8').read()
check(not EMOJI_RE.search(src), 'в модуле нет эмодзи')
base_tpl = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('data-theme="light"' in base_tpl, 'светлая тема учтена (общий shell)')
for fid in ('ldKpis', 'ldAddPanel', 'ldCount', 'ldAction', 'ldDuration', 'ldUnit',
            'ldAdd', 'ldSteps', 'ldUser', 'ldSimGo', 'ldSim', 'ldCard', 'ldCsv'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check("'/view'" in tpl and "'/card.png?t='" in tpl and "'/simulate?user='" in tpl
      and "'/add'" in tpl and "'/remove'" in tpl and "'/export.csv'" in tpl,
      'API-пути в шаблоне')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
import services.panel_menu as PM
mod_pages = [pg['path'] for g in PM.MENU if g['key'] == 'mod' for pg in g['pages']]
check('/ladder' in mod_pages, 'пункт меню «Лестница» в «Модерации»')
check(PM.PAGE_COGS.get('/ladder') == ('ladder', 'warnings'), 'коги привязаны')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('ladder_panel') >= 1, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
