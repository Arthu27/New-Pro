# -*- coding: utf-8 -*-
"""Отчёты поддержки (идеи #166-170).

/report-daily, /report-weekly (с разбивкой по дням), /report-custom по трём
типам с текстом ошибки команды, /report-analytics (топ категорий и лучшие
сотрудники) — всё на тех же синглтонах services.advanced_reporting, что у
кога; aware-даты честно ловятся вместо тихого 500. Библиотека отчётов:
CRUD через публичный ReportBuilder, id за максимальным номером, генерация
обновляет last_generated в общем файле. CSV. API, права, шаблон, меню.

Запуск: python3 tests/test_reports_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

_TMP = tempfile.mkdtemp(prefix='aether_reports_test_')
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


NOW = datetime.now().replace(microsecond=0)
FULL = [
    {'id': 'A', 'status': 'open', 'category': 'support', 'priority': 'high',
     'created_at': NOW.isoformat()},
    {'id': 'B', 'status': 'closed', 'category': 'billing',
     'created_at': (NOW - timedelta(hours=2)).isoformat(),
     'closed_at': (NOW - timedelta(hours=1)).isoformat(),
     'rating': 5, 'claimed_by_name': 'Мод'},
    {'id': 'C', 'status': 'closed', 'category': 'support',
     'created_at': (NOW - timedelta(days=1)).isoformat(),
     'closed_at': (NOW - timedelta(days=1) + timedelta(hours=2)).isoformat(),
     'rating': 3, 'claimed_by_name': 'Мод'},
    {'id': 'D', 'status': 'open', 'category': 'other', 'priority': 'low',
     'created_at': (NOW - timedelta(days=3)).isoformat()},
    {'id': 'E', 'status': 'closed', 'category': 'billing',
     'created_at': (NOW - timedelta(days=3)).isoformat(),
     'closed_at': (NOW - timedelta(days=3) + timedelta(hours=4)).isoformat(),
     'staff_name': 'Старший'},
    {'id': 'F', 'status': 'closed', 'category': 'support',
     'created_at': (NOW - timedelta(days=10)).isoformat(),
     'closed_at': (NOW - timedelta(days=10) + timedelta(hours=100)).isoformat(),
     'rating': 1, 'claimed_by_name': 'Мод'},
    {'id': 'G', 'status': 'open', 'category': 'support',
     'created_at': (NOW - timedelta(days=40)).isoformat()},
    {'id': 'H', 'status': 'open'},  # без created_at — сервис пропускает
]


def write_tickets(rows):
    json.dump(rows, open('data/customer_tickets.json', 'w', encoding='utf-8'),
              ensure_ascii=False)


from web.routes import reports_panel as SP  # noqa: E402
import services.advanced_reporting as AR  # noqa: E402
import cogs.report_cog as RCG  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')

print('== 0. Проводка ==')
check(SP.report_builder is AR.report_builder is RCG.report_builder,
      'панель и ког делят один report_builder')
check(SP.analytics_engine is AR.analytics_engine is RCG.analytics_engine,
      'и один analytics_engine')
cog_src = open(os.path.join(ROOT, 'cogs/report_cog.py'), encoding='utf-8').read()
check(SP.ERR_TYPE in cog_src, 'текст «неверный тип» — словами команды')

print('== 1. Ежедневный отчёт — /report-daily ==')
write_tickets([
    {'id': 'A', 'status': 'open', 'category': 'support',
     'created_at': NOW.isoformat()},
    {'id': 'B', 'status': 'closed', 'category': 'billing',
     'created_at': NOW.isoformat(),
     'closed_at': (NOW + timedelta(hours=3)).isoformat(), 'rating': 5},
])
ok, d = SP.daily_view()
check(ok and d['date'] == NOW.date().isoformat(), 'дата — сегодня')
check(d['total_tickets'] == 2 and d['open_tickets'] == 1
      and d['closed_tickets'] == 1, 'счётчики дня')
check(d['avg_resolution_time'] == 3.0 and d['sla_compliance'] == 100.0
      and d['customer_satisfaction'] == 5.0, 'время, SLA, оценка')

print('== 2. Еженедельный — /report-weekly ==')
write_tickets(FULL)
ok, w = SP.weekly_view()
check(ok and w['week_start'] == (NOW - timedelta(days=7)).date().isoformat()
      and w['week_end'] == NOW.date().isoformat(), 'рамки недели')
check(w['total_tickets'] == 5 and w['open_tickets'] == 2
      and w['closed_tickets'] == 3, 'неделя: 5/2/3 (F и G вне окна)')
check(w['avg_resolution_time'] == round(7 / 3, 2)
      and w['sla_compliance'] == 100.0 and w['customer_satisfaction'] == 4.0,
      'неделя: avg 2.33 ч, SLA 100, оценка 4.0')
bd = w['daily_breakdown']
d3 = (NOW - timedelta(days=3)).date().isoformat()
check(sum(bd.values()) == 5 and bd.get(d3) == 2
      and bd.get(NOW.date().isoformat()) in (1, 2),
      'разбивка по дням (край полуночи честно разведён)')

print('== 3. Специальный отчёт — /report-custom ==')
ok, err, rep = SP.custom_flow('30', 'tickets')
check(ok and rep['stats'] == {'total_tickets': 6, 'open_tickets': 2,
                              'closed_tickets': 4},
      'tickets за 30 дней (G старше окна)')
check(rep['period_start'] == (NOW - timedelta(days=30)).date().isoformat()
      and rep['period_end'] == NOW.date().isoformat()
      and rep['period_days'] == 30 and rep['report_type'] == 'tickets',
      'период и тип эхом')
ok, err, rep = SP.custom_flow('30', 'sla')
check(ok and rep['stats'] == {'total_tickets': 6, 'closed_tickets': 4,
                              'sla_compliance': 75.0,
                              'avg_resolution_time': 26.75},
      'sla: 100-часовой F ломает процент')
ok, err, rep = SP.custom_flow('30', 'performance')
check(ok and rep['stats'] == {'closed_tickets': 4,
                              'avg_resolution_time': 26.75,
                              'customer_satisfaction': 3.0}, 'performance')
ok, err, rep = SP.custom_flow('45', 'tickets')
check(ok and rep['stats']['total_tickets'] == 7
      and rep['stats']['open_tickets'] == 3, '45 дней зовут и G')
ok, err, rep = SP.custom_flow('мусор', 'tickets')
check(ok and rep['period_days'] == 30, 'мусорные дни — дефолт 30')
ok, err, _ = SP.custom_flow('30', 'crypto')
check(not ok and err == SP.ERR_TYPE, 'левый тип — текстом команды')
ok, err, rep = SP.custom_flow(None, None)
check(ok and rep['report_type'] == 'tickets' and rep['period_days'] == 30,
      'оба дефолта — как у параметров команды')

print('== 4. Аналитика — /report-analytics ==')
ok, a = SP.analytics_view()
check(ok and a['total_tickets'] == 6 and a['open_tickets'] == 2
      and a['closed_tickets'] == 4, 'обзор 6/2/4')
check(a['avg_resolution_time'] == 26.75 and a['sla_compliance'] == 75.0
      and a['customer_satisfaction'] == 3.0, 'метрики дашборда')
check(a['categories'] == {'support': 3, 'billing': 2, 'other': 1}
      and a['priorities'] == {'high': 1, 'low': 1, 'medium': 4},
      'разрезы категорий и приоритетов')
check(a['top_categories'] == [{'category': 'support', 'count': 3},
                              {'category': 'billing', 'count': 2},
                              {'category': 'other', 'count': 1}],
      'топ категорий — как в эмбеде')
check(a['top_performers'] == [{'user_name': 'Мод', 'closed_tickets': 3},
                              {'user_name': 'Старший', 'closed_tickets': 1}],
      'сотрудники: claimed/staff_name, «—» отфильтрован')

print('== 5. Aware-дата — честный отказ вместо тихого 500 ==')
write_tickets(FULL + [{'id': 'I', 'status': 'open',
                       'created_at': (NOW - timedelta(hours=1)).isoformat()
                       + '+00:00'}])
ok, err, _ = SP.custom_flow('30', 'tickets')
check(not ok and err == SP.ERR_CALC, 'custom честно отказал')
ok_d, d_err = SP.daily_view()
check(not ok_d and d_err == SP.ERR_CALC, 'daily тоже (и команда упала бы)')
write_tickets(FULL)
ok, err, rep = SP.custom_flow('30', 'tickets')
check(ok and rep['stats']['total_tickets'] == 6, 'после чистки всё живо')

print('== 6. Библиотека пользовательских отчётов ==')
check(SP.library_view() == [], 'стартует пустой')
ok, err, _ = SP.create_flow('', ['total_tickets'], {})
check(not ok and err == SP.ERR_NAME, 'без названия — отказ')
ok, err, _ = SP.create_flow('Пульс', [], {})
check(not ok and err == SP.ERR_METRICS, 'без метрик — отказ')
ok, err, p = SP.create_flow('Пульс поддержки',
                            ['total_tickets', 'avg_resolution_time', 'junk'],
                            {'status': 'closed', 'evil': 'x'})
check(ok and p['message'] == 'Отчёт «Пульс поддержки» сохранён. ID: rep_1.',
      'создан — id rep_1')
check(p['reports'][0]['metrics'] == ['total_tickets', 'avg_resolution_time']
      and p['reports'][0]['filters'] == {'status': 'closed'},
      'мусорная метрика и фильтр отсечены')
saved = json.load(open('data/custom_reports.json', encoding='utf-8'))
check('rep_1' in saved and saved['rep_1']['last_generated'] is None,
      'файл общий, ещё не генерировался')
ok, err, _ = SP.generate_flow('rep_9', 30)
check(not ok and err == SP.ERR_REPORT, 'чужой id — «Отчёт не найден»')
ok, err, p = SP.generate_flow('rep_1', '30')
check(ok and p['report']['data']['total_tickets'] == 4
      and p['report']['data']['avg_resolution_time'] == 26.75,
      'генерация: 4 закрытых, avg 26.75')
check(SP.report_builder.get_report('rep_1')['last_generated'] is not None,
      'last_generated обновлён, как в сервисе')
ok, err, p = SP.create_flow('Статусы', ['tickets_by_status'], {})
check(ok and p['message'].endswith('ID: rep_2.'), 'второй — rep_2')
ok, err, p = SP.generate_flow('rep_2', 30)
check(ok and dict(p['report']['data']['tickets_by_status'])
      == {'open': 2, 'closed': 4}, 'Counter сервиса доезжает')
ok, err, p = SP.delete_flow('rep_1')
check(ok and p['message'] == 'Отчёт «Пульс поддержки» удалён. '
                             'Всего отчётов: 1.', 'удаление со счётчиком')
ok, err, p = SP.create_flow('Третий', ['total_tickets'], {})
check(ok and p['message'].endswith('ID: rep_3.'),
      'id за максимумом — удаление не задвоило')
ok, err, p = SP.delete_flow('rep_2')
check(ok and [r['report_id'] for r in SP.library_view()] == ['rep_3'],
      'остался только rep_3')
ok, err, _ = SP.delete_flow('rep_2')
check(not ok and err == SP.ERR_REPORT, 'повторное удаление — отказ')

print('== 7. Строки CSV ==')
rows = SP.weekly_csv_rows()
check((d3, 2) in rows and sum(n for _, n in rows) == 5,
      'неделя: дни и суммы')
rows = SP.custom_csv_rows('30', 'sla')
check(rows == [('period_start', (NOW - timedelta(days=30)).date().isoformat()),
               ('period_end', NOW.date().isoformat()),
               ('report_type', 'sla'),
               ('total_tickets', 6), ('closed_tickets', 4),
               ('sla_compliance', 75.0), ('avg_resolution_time', 26.75)],
      'спец: период и статы по порядку')
check(SP.custom_csv_rows('30', 'crypto') == [], 'битый тип — пустая выгрузка')
check(SP._csv_cell('а;б\nв') == 'а,б в', 'ячейки чистятся')

print('== 8. API и права ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


VW = '/api/guild/777/reports/view'
check(client.get('/reports').status_code in (302, 401, 403),
      'гостю страница закрыта')
check(client.get(VW).status_code in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get(VW).status_code == 403, 'uye не смотрит')
check(client.get('/api/guild/777/reports/weekly.csv').status_code == 403,
      'uye не выгружает')
login('mod')
page = client.get('/reports')
check(page.status_code == 200
      and 'Отчёты поддержки' in page.get_data(as_text=True),
      'mod открывает страницу')
d = client.get(VW).get_json()
check(d['success'] and d['daily']['total_tickets'] >= 1
      and d['weekly']['total_tickets'] == 5
      and d['analytics']['total_tickets'] == 6
      and len(d['reports']) == 1 and d['can_edit'] is False,
      'вид для mod — секции живые')
d = client.get('/api/guild/777/reports/custom?days=30&type=sla').get_json()
check(d['success'] and d['stats']['sla_compliance'] == 75.0,
      'спец через API')
r = client.get('/api/guild/777/reports/custom?days=30&type=crypto')
check(r.status_code == 400 and r.get_json()['error'] == SP.ERR_TYPE,
      'левый тип — 400 текстом команды')
check(client.post('/api/guild/777/reports/create',
                  json={'name': 'x', 'metrics': ['total_tickets']})
      .status_code == 403, 'mod не создаёт отчёты')
check(client.post('/api/guild/777/reports/generate',
                  json={'report_id': 'rep_3'}).status_code == 403,
      'mod не генерирует')
login('admin')
r = client.post('/api/guild/777/reports/create',
                json={'name': 'АИ-дайджест', 'metrics': ['total_tickets'],
                      'filters': {'category': 'support'}})
check(r.status_code == 200 and 'сохранён. ID: rep_4.' in r.get_json()['message'],
      'admin создал — id за максимумом')
r = client.post('/api/guild/777/reports/generate',
                json={'report_id': 'rep_4', 'days': '7'})
check(r.status_code == 200
      and r.get_json()['report']['data']['total_tickets'] == 2,
      'admin собрал: support за неделю — A и C')
r = client.post('/api/guild/777/reports/delete', json={'report_id': 'rep_4'})
check(r.status_code == 200
      and 'Всего отчётов: 1.' in r.get_json()['message'], 'admin убрал')
r = client.post('/api/guild/777/reports/delete', json={'report_id': 'rep_4'})
check(r.status_code == 400 and r.get_json()['error'] == SP.ERR_REPORT,
      'повторное — 400')
ex = client.get('/api/guild/777/reports/weekly.csv')
body = ex.get_data(as_text=True)
check(ex.status_code == 200 and ex.headers['Content-Disposition']
      .endswith('reports_weekly_777.csv'), 'CSV недели: имя файла')
check(body.startswith('\ufeffdate;tickets') and (d3 + ';2') in body,
      'CSV недели: BOM, шапка, строка руками')
ex = client.get('/api/guild/777/reports/custom.csv?days=30&type=sla')
body = ex.get_data(as_text=True)
check(ex.status_code == 200 and ex.headers['Content-Disposition']
      .endswith('reports_custom_777.csv')
      and body.startswith('\ufeffmetric;value')
      and 'sla_compliance;75.0' in body, 'CSV спец: имя, шапка, метрика')
login('mod')

print('== 9. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/reports.html'),
           encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
src = open(os.path.join(ROOT, 'web/routes/reports_panel.py'),
           encoding='utf-8').read()
check(not EMOJI_RE.search(src), 'в модуле нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('repKpis', 'repDaily', 'repWeek', 'repCsvW', 'repDays', 'repType',
            'repCustomGo', 'repCsvC', 'repCustom', 'repCustomMsg', 'repAna',
            'repAnaCats', 'repAnaTop', 'repLib', 'repLibNew', 'repName',
            'repMetrics', 'repFStatus', 'repFCat', 'repFPrio', 'repCreate',
            'repLibMsg', 'repData'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
for path in ("'/view'", "'/custom?days='", "'/create'", "'/generate'",
             "'/delete'", "'/weekly.csv'", "'/custom.csv?days='"):
    check(path in tpl, f'путь {path} в шаблоне')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
import services.panel_menu as PM
log_pages = [pg['path'] for g in PM.MENU if g['key'] == 'logs'
             for pg in g['pages']]
check('/reports' in log_pages, 'пункт меню «Отчёты поддержки» в «Логах»')
check(PM.PAGE_COGS.get('/reports') == ('report_cog',), 'ког привязан')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('reports_panel') >= 1, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
