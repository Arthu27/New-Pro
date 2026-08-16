# -*- coding: utf-8 -*-
"""OPS-центр тикетов (идеи #21-25).

Проверяем: чистые sla_snapshot (возраст/просрочка/среднее закрытие),
bulk_close с пропусками, reopen (стирание полей закрытия), add_note с
рамками, assign/unassign, атомарную запись в файл кога, API
права mod/ponder admin на массовом, шаблон и меню.

Запуск: python3 tests/test_tickets_ops.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_tickops_test_')
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


from web.routes import tickets_ops as TO  # noqa: E402

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
GID = 777

fixture = {
    't1': {'user_id': 111, 'category': 'Жалоба', 'status': 'ai_handling',
           'created_at': (NOW - timedelta(hours=30)).isoformat()},
    't2': {'user_id': 222, 'category': 'Вопрос', 'status': 'open',
           'created_at': (NOW - timedelta(hours=10)).isoformat()},
    't3': {'user_id': 333, 'category': 'Баг', 'status': 'closed',
           'created_at': (NOW - timedelta(hours=50)).isoformat(),
           'closed_at': (NOW - timedelta(hours=2)).isoformat(), 'closed_by': 'panel:X'},
    't4': {'user_id': 444, 'category': 'Жалоба', 'status': 'ai_handling'},  # без даты
}

print('== 1. Чистые: SLA ==')
s = TO.sla_snapshot(fixture, now=NOW, sla_hours=24)
check(s['open_count'] == 3, 'открыто 3 (closed не считаем)')
check(s['overdue_count'] == 1, 'просрочен только t1 (30 ч при SLA 24)')
ages = {i['id']: i['age_h'] for i in s['items']}
check(ages['t1'] == 30.0 and ages['t2'] == 10.0 and ages['t4'] is None, 'возрасты честные')
check(s['items'][0]['id'] == 't1', 'сортировка: самый старый первым')
check(s['avg_close_hours'] == 48.0 and s['closed_total'] == 1, 'среднее закрытие 48 ч')
s2 = TO.sla_snapshot(fixture, now=NOW, sla_hours=12)
check(s2['overdue_count'] == 1, 'SLA 12 ч — просрочен всё равно только t1 (30 ч)')
s0 = TO.sla_snapshot({}, now=NOW)
check(s0['open_count'] == 0 and s0['avg_close_hours'] is None, 'пусто — нули и прочерк')
s_bad = TO.sla_snapshot(fixture, now=NOW, sla_hours='мусор')
check(s_bad['sla_hours'] == 24.0, 'мусорный SLA — дефолт 24')

print('== 2. Мутации: bulk-close/reopen/note/assign ==')
tk = json.loads(json.dumps(fixture))
closed, skipped = TO.bulk_close(tk, ['t1', 't2', 't3', 'ghost'], by='panel:mod', now=NOW)
check(sorted(closed) == ['t1', 't2'] and sorted(skipped) == ['ghost', 't3'],
      'bulk: закрыты открытые, пропущены closed/призрак')
check(tk['t1']['status'] == 'closed' and tk['t1']['closed_by'] == 'panel:mod'
      and tk['t1']['closed_at'], 'поля закрытия проставлены')
check(TO.reopen_ticket(tk, 't1') is True, 'реопен закрытого — ок')
check('closed_at' not in tk['t1'] and tk['t1']['status'] == 'open' and tk['t1']['reopened_at'],
      'реопен стирает поля закрытия')
check(TO.reopen_ticket(tk, 't2') is True, 'реопен второго закрытого — ок')
check(TO.reopen_ticket(tk, 't4') is False and TO.reopen_ticket(tk, 'ghost') is False,
      'реопен открытого/призрака — False')

ok, err = TO.add_note(tk, 'ghost', 'привет', by='panel:m')
check(not ok and err == 'Тикет не найден.', 'заметка призраку — 404-текст')
ok, err = TO.add_note(tk, 't1', '   ', by='panel:m')
check(not ok and err == 'Введите текст заметки.', 'пустая заметка — 400-текст')
ok, err = TO.add_note(tk, 't1', 'x' * 301, by='panel:m')
check(not ok and 'максимум 300' in err, 'длинная заметка — 400-текст')
ok, note = TO.add_note(tk, 't1', 'Пользователь просил перезвон', by='panel:m', now=NOW)
check(ok and tk['t1']['notes'][0]['text'].startswith('Пользователь'), 'заметка сохранена с автором и меткой')

ok, err = TO.assign_ticket(tk, 't1', 'panel:mod', by='panel:m')
check(ok and tk['t1']['assigned_to'] == 'panel:mod' and tk['t1']['assigned_by'] == 'panel:m',
      'назначение с автором')
ok, err = TO.assign_ticket(tk, 't1', '', by='panel:m')
check(ok and 'assigned_to' not in tk['t1'], 'снятие назначения')
ok, err = TO.assign_ticket(tk, 'ghost', 'x', by='y')
check(not ok and err == 'Тикет не найден.', 'назначение призраку — 404')

TO.save_tickets(GID, tk)
back = TO.load_tickets(GID)
check(back['t1']['notes'][0]['text'] == tk['t1']['notes'][0]['text'], 'круг файла жива')
check(TO.load_tickets(424242) == {}, 'нет файла — пусто')
with open(f'data/ai_tickets_{GID}.json', 'w', encoding='utf-8') as fh:
    fh.write('{битый')
check(TO.load_tickets(GID) == {}, 'битый файл — пусто, не падаем')

print('== 3. API: права и интероп ==')
TO.save_tickets(GID, fixture)
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


def post(path, payload):
    r = client.post(path, data=json.dumps(payload), content_type='application/json')
    try:
        return r.status_code, r.get_json()
    except Exception:
        return r.status_code, {'raw': r.data[:200]}


check(client.get('/tickets-ops').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get('/api/tickets-ops/sla').status_code in (302, 401, 403), 'гостю sla закрыт')
login('uye')
check(client.get('/tickets-ops').status_code == 403, 'uye нельзя')
login('mod')
check(client.get('/tickets-ops').status_code == 200, 'mod читает страницу')
r = client.get('/api/tickets-ops/sla?h=24')
check(r.status_code == 200 and r.get_json()['open_count'] == 3, 'mod читает sla')
check(r.get_json()['can_edit'] is False, 'mod: can_edit=false')
check(post('/api/tickets-ops/t1/note', {'text': 'принято в работу'})[0] == 200, 'mod пишет заметку')
check(post('/api/tickets-ops/t1/assign', {'name': 'panel:admin'})[0] == 200, 'mod назначает')
check(post('/api/tickets-ops/bulk-close', {'ids': ['t1']})[0] == 403, 'mod нельзя массовое закрытие')

login('admin')
r = client.get('/api/tickets-ops/sla')
check(r.get_json()['can_edit'] is True, 'admin: can_edit=true')
code, d = post('/api/tickets-ops/bulk-close', {'ids': []})
check(code == 400 and d['error'] == 'Не выбраны тикеты.', 'пустой bulk — 400')
code, d = post('/api/tickets-ops/bulk-close', {'ids': ['t3', 'ghost']})
check(code == 400 and d['error'].startswith('Нечего закрывать'), 'bulk closed-only — 400')
code, d = post('/api/tickets-ops/bulk-close', {'ids': ['t1', 't2']})
check(code == 200 and sorted(d['closed']) == ['t1', 't2'], 'admin массово закрывает')
r2 = client.get('/api/tickets-ops/sla')
check(r2.get_json()['open_count'] == 1, 'после bulk остался один открытый (без даты)')
code, d = post('/api/tickets-ops/t1/reopen', {})
check(code == 200, 'реопен через API')
check(client.get('/api/tickets-ops/t1').get_json()['status'] == 'open', 'карточка видит реопен')
check(post('/api/tickets-ops/ghost/reopen', {})[0] == 404, 'реопен призрака — 404')
check(client.get('/api/tickets-ops/ghost').status_code == 404, 'карточка призрака — 404')

print('== 4. Шаблон и меню ==')
html = client.get('/tickets-ops').get_data(as_text=True)
check('tpKpis' in html and 'tpBulkClose' in html, 'страница монтирует блоки')
tpl = open(os.path.join(ROOT, 'web/templates/tickets_ops.html'), encoding='utf-8').read()
emoji = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not emoji.search(tpl), 'в шаблоне нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
check('askConfirm' in tpl and 'uxUndo' in tpl, 'confirm и undo на месте')
import services.panel_menu as PM
paths = [pg['path'] for g in PM.MENU for pg in g['pages']]
check('/tickets-ops' in paths, 'пункт меню «OPS-центр» есть')
check(PM.PAGE_COGS.get('/tickets-ops') == ('ticket',), 'PAGE_COGS привязан к ticket')

print('== 5. История автора, переоткрытые, экспорт (#26-30) ==')
TO.save_tickets(GID, fixture)
hist = TO.author_history(fixture, 222, exclude='t2')
check(hist['total'] == 1 and hist['last'] == [], 'единственный тикет автора исключён корректно')
# делаем у 222 ещё один, более свежий
fx = json.loads(json.dumps(fixture))
fx['t9'] = {'user_id': 222, 'category': 'Вопрос', 'status': 'closed',
            'created_at': (NOW - timedelta(hours=5)).isoformat(),
            'closed_at': (NOW - timedelta(hours=1)).isoformat()}
hist2 = TO.author_history(fx, 222, exclude='t2')
check(hist2['total'] == 2 and hist2['last'][0]['id'] == 't9', 'история: свежий первым, счёт с текущим')
card = TO.ticket_card(fx, 't2')
check(card['history']['total'] == 2 and isinstance(card['history']['last'], list),
      'карточка везёт историю автора')

snap = TO.sla_snapshot(fx, now=NOW, sla_hours=24)
check('t1' in snap['overdue_ids'] and snap['reopened_total'] == 0, 'overdue_ids и reopened_total в снимке')
fx['t1']['reopened_at'] = NOW.isoformat()
snap2 = TO.sla_snapshot(fx, now=NOW, sla_hours=24)
check(snap2['reopened_total'] == 1, 'переоткрытый учтён в KPI')

csv_text = TO.tickets_csv(fx)
check(csv_text.splitlines()[0].startswith('ID;Категория'), 'шапка CSV')
check('t1;Жалоба;111;ai_handling' in csv_text, 'строка открытого тикета в CSV')
check('t3;Баг;333;closed' in csv_text and 'panel:X' in csv_text, 'закрытый с закрывающим в CSV')

r = client.get('/api/tickets-ops/export.csv')
check(r.status_code == 200 and 'tickets_777_' in r.headers.get('Content-Disposition', ''),
      'мод скачивает выгрузку')
login('uye')
check(client.get('/api/tickets-ops/export.csv').status_code == 403, 'uye нельзя выгрузку')
login('mod')

tpl = open(os.path.join(ROOT, 'web/templates/tickets_ops.html'), encoding='utf-8').read()
check('tpCloseOverdue' in tpl and 'overdue_ids' in tpl, 'кнопка «закрыть просроченные» смонтирована')
check('tpFilter' in tpl, 'фильтр таблицы смонтирован')
check('tpHistory' in tpl and 'author_history' in open(os.path.join(ROOT, 'web/routes/tickets_ops.py'), encoding="utf-8").read(),
      'история автора смонтирована')
check('export.csv' in tpl, 'ссылка выгрузки на месте')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
