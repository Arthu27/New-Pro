# -*- coding: utf-8 -*-
"""Очередь репортов в панели + события «новая апелляция/репорт» в колокольчик.

Тикеты — общая SQLite (services/reports_core); события — единый диспетчер
уведомлений, чей веб-канал пишет broadcast в data/panel_logs.json, а его
подхватывает опрос колокольчика /api/notifications/poll.

Запуск: python3 tests/test_reports_queue.py
"""
import importlib
import json
import os
import shutil
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix='hakumo_rqueue_test_')
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


from services import reports_core as RC  # noqa: E402
from services import notification_dispatcher as ND  # noqa: E402
from web.routes import reports_queue as RQ  # noqa: E402

print('== 1. ядро тикетов ==')
NOW = time.time()
RC.ticket_create('777', 't1', '42', '43', kind='report')
RC.ticket_create('777', 't2', '44', '44', kind='appeal')
RC.ticket_create('555', 't3', '50', '51', kind='report')
RC.ticket_set('t1', created=NOW - 100)
RC.ticket_set('t2', created=NOW - 50, closed=NOW - 3600, verdict='Нарушение снято')
lst = RC.ticket_list('777')
check([t['thread_id'] for t in lst] == ['t2', 't1'], 'список: свежие сверху, только свой сервер')
st = RC.ticket_stats('777')
check(st['total'] == 2 and st['open'] == 1 and st['closed_week'] == 1,
      f'сводка открыто/решено за неделю: {st}')
py = RQ.queue_payload('777', {'42': 'Жалобщик', '43': 'Нарушитель'})
check(len(py['items']) == 2 and 'stats' in py, 'payload собран')
open1 = [i for i in py['items'] if not i['closed']][0]
check(open1['reporter'] == 'Жалобщик' and open1['accused'] == 'Нарушитель',
      'имена из общей карты вместо голых ID')
closed1 = [i for i in py['items'] if i['closed']][0]
check(closed1['verdict'].startswith('Нарушение') and closed1['kind'] == 'appeal',
      'решённый тикет несёт вердикт и вид')
check(open1['age_min'] >= 0 and open1['created_readable'], 'возраст и дата человеческие')

print('== 2. события диспетчера ==')
check('appeal_new' in ND.EVENTS and 'report_new' in ND.EVENTS,
      'новые события зарегистрированы')
check(ND.DEFAULT_SETTINGS['event_appeal_new'] is True and
      ND.DEFAULT_SETTINGS['event_report_new'] is True,
      'события включены по умолчанию')
check(ND.EVENT_LINKS['appeal_new'] == '/appeals' and
      ND.EVENT_LINKS['report_new'] == '/reports-queue',
      'клик по уведомлению ведёт на нужную страницу')
res = ND.notify_event('appeal_new', None, '#12 от **Юзер**: прошу разбана')
check(res.get('web') is True, f'веб-канал записал событие: {res}')
res2 = ND.notify_event('report_new', None, 'На **Хулиган** пожаловался Мод')
check(res2.get('web') is True, 'событие репорта записано')
raw = json.load(open('data/panel_logs.json', encoding='utf-8'))
ev = [e.get('event') for e in raw if e.get('broadcast')]
check('appeal_new' in ev and 'report_new' in ev, 'broadcast-события в журнале панели')
hit = [e for e in raw if e.get('event') == 'appeal_new'][0]
check(hit.get('link') == '/appeals' and 'разбана' in (hit.get('detail') or ''),
      'у записи ссылка и тело')
# отключённое событие не пишется
st_path = 'data/notification_settings.json'
json.dump({'event_report_new': False}, open(st_path, 'w', encoding='utf-8'))
before = len(json.load(open('data/panel_logs.json', encoding='utf-8')))
res3 = ND.notify_event('report_new', None, 'тихий репорт')
check('skipped' in res3 and len(json.load(open('data/panel_logs.json', encoding='utf-8'))) == before,
      'выключенный переключатель глушит событие')
os.remove(st_path)

print('== 3. веб ==')
appmod = importlib.import_module('web.app')
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


check(client.get('/reports-queue').status_code in (302, 401, 403),
      'гостю страница закрыта')
login('mod')
r = client.get('/reports-queue')
check(r.status_code == 200, 'страница открывается модератору')
html = r.get_data(as_text=True)
check('id="rqKpis"' in html and 'id="rqChips"' in html and 'id="rqList"' in html,
      'KPI, фильтры и список в шаблоне')
r = client.get('/api/guild/777/reports-queue').get_json()
check(r.get('success') and r['stats']['open'] == 1
      and any(i['thread_id'] == 't2' and i['verdict'] for i in r['items']),
      'API: сводка и элементы')
r = client.get('/api/guild/555/reports-queue').get_json()
check(r.get('success') and all(i['thread_id'] != 't3' for i in r['items']),
      'изоляция: /555 отвечает данными главного сервера')

# колокольчик подхватывает broadcast-события
r = client.get('/api/notifications/poll').get_json()
notifs = r.get('notifications') or []
check(any('апелляция' in (n.get('title') or '').lower() for n in notifs),
      'колокольчик видит событие новой апелляции')

print('== 4. меню ==')
from services import panel_menu as PM  # noqa: E402
paths = [i['path'] for g in PM.MENU for i in g.get('pages', [])]
check('/reports-queue' in paths, 'пункт меню «Репорты» зарегистрирован')
check(PM.PAGE_COGS.get('/reports-queue') == ('reports',),
      'страница привязана к когу репортов')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
