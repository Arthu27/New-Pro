# -*- coding: utf-8 -*-
"""Про-аналитика сообщений (идеи #11 теплокарта, #12 CSV-экспорт).

Проверяем: чистый разбор меток (aware/naive/'Z'/мусор), загрузку событий
из audit_log с фолбэком в message_logs, теплокарту 7x24 с пиком,
суточный ряд с нулевыми днями, топы, CSV (структура секций, BOM,
заголовок скачивания), права mod+, монтаж блоков в шаблоне.

Запуск: python3 tests/test_analytics_plus.py
"""
import importlib
import io
import json
import os
import csv
import re
import shutil
import sys
import tempfile
from datetime import date, timedelta

_TMP = tempfile.mkdtemp(prefix='aether_anplus_test_')
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


from web.routes import analytics_plus as AP  # noqa: E402

print('== 1. Чистые функции ==')
check(AP._parse_ts('2026-08-15T14:30:00').hour == 14, 'naive ISO читается')
check(AP._parse_ts('2026-08-15T14:30:00Z').tzinfo is None, "'Z' → aware→local naive")
check(AP._parse_ts('2026-08-15T10:30:00+00:00').tzinfo is None, 'aware → naive local')
check(AP._parse_ts('не дата') is None and AP._parse_ts('') is None and AP._parse_ts(None) is None,
      'мусор → None, не падаем')

audit = {'777': [
    {'category': 'message', 'action': 'message написано', 'user_name': 'Мира',
     'channel': 'общий', 'timestamp': '2026-08-10T21:15:00'},  # Пн 21
    {'category': 'message', 'action': 'message написано', 'user_name': 'Гром',
     'channel': 'общий', 'timestamp': '2026-08-10T21:45:00'},  # Пн 21
    {'category': 'message', 'action': 'message написано', 'user_name': 'Мира',
     'channel': 'флуд', 'timestamp': '2026-08-12T09:05:00'},   # Ср 09
    {'category': 'moderation', 'action': 'ban', 'user_name': 'Х',
     'timestamp': '2026-08-12T10:00:00'},
    {'category': 'message', 'action': 'message удалено', 'user_name': 'Х',
     'timestamp': '2026-08-12T11:00:00'},
    'битая запись',
    {'category': 'message', 'action': 'message написано', 'user_name': 'Мира',
     'channel': 'общий', 'timestamp': 'не дата'},
], '888': [
    {'category': 'message', 'action': 'message написано', 'user_name': 'Чужой',
     'channel': 'ихний', 'timestamp': '2026-08-10T10:00:00'},
]}
with open('data/audit_log.json', 'w', encoding='utf-8') as fh:
    json.dump(audit, fh)

ev = AP.load_message_events(777)
check(len(ev) == 4, 'только валидные message-написано события сервера')
check(all(e[0] in ('Мира', 'Гром') for e in ev), 'чужой сервер отфильтрован')

hm = AP.heatmap_matrix(ev)
check(hm['max'] == 2 and hm['total'] == 3, 'max/total матрицы (событие без метки вне сетки)')
check(hm['matrix'][0][21] == 2 and hm['matrix'][2][9] == 1, 'ячейки по дню/часу')
check(hm['peak'] == {'weekday': 'Пн', 'hour': 21, 'count': 2}, 'пик посчитан')
check(all(len(r) == 24 for r in hm['matrix']) and len(hm['matrix']) == 7, 'геометрия 7x24')

ev_empty = AP.load_message_events(424242)
check(ev_empty == [], 'нет файлов — пусто')
hm0 = AP.heatmap_matrix(ev_empty)
check(hm0['max'] == 0 and hm0['peak'] is None and hm0['total'] == 0, 'пустая теплокарта честная')

print('== 2. Фолбэк в message_logs ==')
# сервер без записей в audit_log, но с message_logs
with open('data/message_logs_555.json', 'w', encoding='utf-8') as fh:
    json.dump([
        {'author': 'Соло', 'channel': 'общий', 'timestamp': '2026-08-15T18:00:00'},
        {'author': 'Соло', 'channel': 'общий', 'timestamp': '2026-08-15T19:00:00'},
    ], fh)
ev_fb = AP.load_message_events(555)
check(len(ev_fb) == 2 and ev_fb[0][0] == 'Соло', 'фолбэк сработал')
# битый message_logs — не роняем
with open('data/message_logs_556.json', 'w', encoding='utf-8') as fh:
    fh.write('{битый')
check(AP.load_message_events(556) == [], 'битый message_logs — пусто, не падаем')

ser = AP.daily_series(ev, days=30)
check(len(ser) == 30 and ser[-1][0] == date.today().isoformat(), '30 дней до сегодня')
check(ser[0][0] == (date.today() - timedelta(days=29)).isoformat(), 'ряд хронологичный')
check(all(isinstance(c, int) and c >= 0 for _d, c in ser), 'нулевые дни есть, отрицательных нет')
check(AP.top_counter(ev, 0)[0] == ('Мира', 3), 'топ участников (мусорная метка не попала)')
check(AP.top_counter(ev, 1)[0] == ('общий', 3), 'топ каналов')

print('== 3. CSV ==')
text = AP.analytics_csv(777, days=30)
rows = list(csv.reader(io.StringIO(text), delimiter=';'))
check(rows[0] == ['Дата', 'Сообщений'], 'секция дней')
blank1 = rows.index([])
sec_members = rows[blank1 + 1]
check(sec_members == ['Участник', 'Сообщений'], 'секция участников')
blank2 = rows.index([], blank1 + 1)
check(rows[blank2 + 1] == ['Канал', 'Сообщений'], 'секция каналов')
check(sum(1 for r in rows if r and r[0] == 'Мира' and r[1] == '3') == 1, 'Мира с тройкой в CSV')
check(sum(1 for r in rows if r and r[0] == '2026-08-10' and r[1] == '2') == 1, 'день с двойкой в CSV')

print('== 4. API: права и заголовки ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


check(client.get('/api/guild/777/analytics/heatmap').status_code in (302, 401, 403),
      'гостю теплокарта закрыта')
check(client.get('/api/guild/777/analytics.csv').status_code in (302, 401, 403),
      'гостю CSV закрыт')
login('uye')
check(client.get('/api/guild/777/analytics/heatmap').status_code == 403, 'uye нельзя')
login('mod')
r = client.get('/api/guild/777/analytics/heatmap')
check(r.status_code == 200 and r.get_json()['max'] == 2, 'mod читает теплокарту')
r = client.get('/api/guild/777/analytics.csv')
check(r.status_code == 200 and r.mimetype == 'text/csv', 'mod качает CSV')
check(r.headers.get('Content-Disposition', '').startswith('attachment; filename="analytics_777_'),
      'CSV скачивается файлом с датой')
body = r.get_data(as_text=True)
check(body.startswith('\ufeff'), 'BOM для Excel на месте')
check('Мира;3' in body and 'общий;3' in body, 'данные в ответе')

print('== 5. Монтаж шаблона ==')
tpl = open(os.path.join(ROOT, 'web/templates/analytics.html'), encoding='utf-8').read()
check('anHeatmap' in tpl and 'loadHeatmap' in tpl, 'теплокарта смонтирована на /analytics')
check('anCsvBtn' in tpl and 'analytics.csv' in tpl, 'CSV-кнопка смонтирована')
check('analytics-cockpit' in tpl and 'analytics-pulse-ring' in tpl,
      'оперативный analytics-cockpit смонтирован')
check('analytics-brief' in tpl and 'anKpiMessages' in tpl and 'anKpiGrowth' in tpl,
      'ключевые показатели вынесены над графиками')
check('analytics-jump' in tpl and 'anOperations' in tpl and 'anChannel' in tpl,
      'быстрая навигация охватывает аналитические контуры')
check('function updateCockpit' in tpl and '_lastSummary' in tpl and '_lastFlow' in tpl,
      'динамический индекс объединяет активность и поток аудитории')
check('analytics-signal-grid' in tpl and 'anSignalActivity' in tpl and 'anSignalPeak' in tpl,
      'сигнальная комната формирует отдельные выводы для команды')
check('data-an-lens="content"' in tpl and 'function setLens' in tpl and
      "localStorage.setItem('analytics_lens'" in tpl,
      'рабочие линзы переключают контент, аудиторию и команду')
check('contextGid' in tpl and 'ensureGuilds' in tpl and "'/api/guilds'" in tpl,
      'селектор сервера заполняется из /api/guilds (без MAIN_GUILD_ID не виснет)')
check('renderNoContext' in tpl and 'Бот пока не виден ни на одном сервере' in tpl,
      'нет серверов — честное пустое состояние вместо вечного «Загрузка…»')
check('analytics-chart-shell' in tpl and 'analytics-chart-panel' in tpl,
      'графики получили собственную полноэкранную визуальную систему')
check('id="anPrint"' in tpl and 'window.print()' in tpl,
      'снимок аналитики готовится штатной печатью/PDF')
r = client.get('/analytics')
check(r.status_code == 200 and 'contextGid' in r.get_data(as_text=True),
      'страница /analytics живая и несёт фолбэк выбора сервера')
demo_source = open(os.path.join(ROOT, 'scripts', 'demo_panel.py'), encoding='utf-8').read()
check("message_log_path = f'data/message_logs_{GID}.json'" in demo_source and
      'for day in range(30)' in demo_source,
      'demo-preview получает наглядную 30-дневную историю активности')
check("('member', 'Участник вошёл'" in demo_source and
      "('invite', 'Приглашение создано'" in demo_source,
      'demo-preview показывает поток аудитории и инвайт-сигналы')
emoji = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not emoji.search(tpl), 'в шаблоне нет эмодзи')
check(tpl.count('an-rowl') >= 2, 'стили теплокарты на месте')

print('== 6. Приходы/уходы и неделя к неделе (#13, #14) ==')
# докидываем member-события относительно сегодня — тест не зависит от часов
from datetime import datetime as _dt  # noqa: E402
today = date.today()
d_y = (today - timedelta(days=1)).isoformat()
d_t = today.isoformat()
with open('data/audit_log.json', encoding='utf-8') as fh:
    audit2 = json.load(fh)
audit2['777'].extend([
    {'category': 'member', 'action': 'Участник вошёл', 'timestamp': d_y + 'T10:00:00'},
    {'category': 'member', 'action': 'Участник вошёл', 'timestamp': d_y + 'T12:00:00'},
    {'category': 'member', 'action': 'Участник вошёл', 'timestamp': d_t + 'T09:00:00'},
    {'category': 'member', 'action': 'Участник вышел', 'timestamp': d_y + 'T20:00:00'},
    {'category': 'member', 'action': 'Псевдоним изменён', 'timestamp': d_t + 'T09:30:00'},
    {'category': 'member', 'action': 'Участник вошёл', 'timestamp': 'не дата'},
])
with open('data/audit_log.json', 'w', encoding='utf-8') as fh:
    json.dump(audit2, fh)

flow = AP.member_flow(777, days=14)
check(flow['joined_total'] == 3 and flow['left_total'] == 1 and flow['net'] == 2,
      'итоги потока: 3+/1-/Δ2')
check(flow['joins'][-2] == 2 and flow['joins'][-1] == 1, 'по дням: вчера 2, сегодня 1')
check(flow['leaves'][-2] == 1, 'уходы по дням')
check(len(flow['labels']) == 14 and len(flow['joins']) == 14, 'окно 14 дней')
check(AP.member_flow(424242)['net'] == 0 and AP.member_flow(424242)['joined_total'] == 0,
      'пустой сервер — нули')

now = _dt(2026, 8, 16, 12, 0, 0)
events = [
    ('Аня', 'общий', now - timedelta(days=1)),
    ('Боря', 'общий', now - timedelta(days=2)),
    ('Аня', 'общий', now - timedelta(days=8)),   # прошлая неделя
    ('Аня', 'общий', now - timedelta(days=20)),  # вне окон
    ('Ветераный', 'общий', None),                 # без метки
]
ws = AP.week_summary(events, now=now)
check(ws['week_msgs'] == 2 and ws['prev_week_msgs'] == 1, 'окна 7+7 суток')
check(ws['msgs_delta'] == 100, 'дельта сообщений +100%')
check(ws['week_users'] == 2 and ws['prev_week_users'] == 1 and ws['users_delta'] == 100,
      'дельта авторов +100%')
ws0 = AP.week_summary([], now=now)
check(ws0['msgs_delta'] is None and ws0['users_delta'] is None and ws0['week_msgs'] == 0,
      'без прошлой недели — честный прочерк, а не деление на ноль')

r = client.get('/api/guild/777/analytics/member-flow')
check(r.status_code == 200 and r.get_json()['net'] == 2, 'mod читает member-flow')
r = client.get('/api/guild/777/analytics/week-summary')
check(r.status_code == 200 and 'week_msgs' in r.get_json(), 'mod читает week-summary')
login('uye')
check(client.get('/api/guild/777/analytics/member-flow').status_code == 403, 'uye нельзя flow')
check(client.get('/api/guild/777/analytics/week-summary').status_code == 403, 'uye нельзя сводку')
login('mod')

tpl = open(os.path.join(ROOT, 'web/templates/analytics.html'), encoding='utf-8').read()
check('flowChart' in tpl and 'member-flow' in tpl, 'график потока смонтирован')
check('anWeekSum' in tpl and 'week-summary' in tpl, 'чипы недели смонтированы')
check(not emoji.search(tpl), 'всё ещё без эмодзи')

print('== 7. Детализация по каналу и рекорды (#15, #16) ==')
drill = AP.channel_drill(AP.load_message_events(777), 'общий', days=30)
check(drill['total'] == 3 and drill['unique_authors'] == 2, 'дрилл: всего/авторы')
check(len(drill['days']) == 30 and sum(c for _d, c in drill['days']) == 2,
      'ряд 30 дней сходится (событие без метки вне сетки)')
check(drill['top_authors'][0][1] == 2, 'топ авторов канала')  # у Миры и Грома в «общем» поровну — берём счёт
drill_empty = AP.channel_drill(AP.load_message_events(777), 'неттакого')
check(drill_empty['total'] == 0 and drill_empty['top_authors'] == [], 'неизвестный канал — честные нули')

recs = AP.record_days(AP.load_message_events(777))
check(recs and recs[0][1] == 2 and recs[0][0] == '2026-08-10', 'рекордный день — 10.08 (2 сообщ.)')
check(len(recs) <= 3, 'не больше трёх рекордов')
check(AP.record_days([]) == [], 'без событий — без рекордов')

r = client.get('/api/guild/777/analytics/channel-drill?name=общий')
check(r.status_code == 200 and r.get_json()['total'] == 3, 'mod читает дрилл канала')
r = client.get('/api/guild/777/analytics/records')
d = r.get_json()
check(r.status_code == 200 and d['records'] and 'today_count' in d and 'today_rank' in d,
      'mod читает рекорды')
check(d['records'][0]['count'] == 2, 'эндпоинт рекордов согласован с чистой функцией')
login('uye')
check(client.get('/api/guild/777/analytics/channel-drill?name=x').status_code == 403, 'uye нельзя дрилл')
check(client.get('/api/guild/777/analytics/records').status_code == 403, 'uye нельзя рекорды')
login('mod')

tpl = open(os.path.join(ROOT, 'web/templates/analytics.html'), encoding='utf-8').read()
check('anDrillSel' in tpl and 'channel-drill' in tpl, 'дрилл смонтирован')
check('anRecords' in tpl and 'analytics/records' in tpl, 'рекорды смонтированы')

print('== 8. Мод-нагрузка, войс-пульс, инвайты, полный CSV (#17-#20) ==')
with open('data/audit_log.json', encoding='utf-8') as fh:
    audit3 = json.load(fh)
audit3['777'].extend([
    {'category': 'mod', 'action': 'Бан', 'mod_name': 'Старший Мод',
     'timestamp': (today - timedelta(days=2)).isoformat() + 'T10:00:00'},
    {'category': 'mod', 'action': 'Бан', 'mod_name': 'Старший Мод',
     'timestamp': (today - timedelta(days=5)).isoformat() + 'T11:00:00'},
    {'category': 'mod', 'action': 'Кик', 'mod_name': 'Старший Мод',
     'timestamp': d_t + 'T12:00:00'},
    {'category': 'mod', 'action': 'Мут', 'mod_name': None, 'timestamp': d_t + 'T13:00:00'},
    {'category': 'voice', 'action': 'Зашёл в голосовой', 'user_name': 'Мира',
     'channel': 'Общий войс', 'timestamp': d_t + 'T20:00:00'},
    {'category': 'voice', 'action': 'Зашёл в голосовой', 'user_name': 'Гром',
     'channel': 'Игровой', 'timestamp': d_y + 'T21:00:00'},
    {'category': 'voice', 'action': 'Вышел из голосового', 'user_name': 'Мира',
     'channel': 'Общий войс', 'timestamp': d_t + 'T22:00:00'},
    {'category': 'invite', 'action': 'Приглашение создано', 'user_name': 'Мира', 'code': 'aa'},
    {'category': 'invite', 'action': 'Приглашение создано', 'user_name': 'Мира', 'code': 'bb'},
    {'category': 'invite', 'action': 'Приглашение создано', 'user_name': 'Гром', 'code': 'cc'},
])
with open('data/audit_log.json', 'w', encoding='utf-8') as fh:
    json.dump(audit3, fh)

ml = AP.mod_load(777, days=30)
check(ml['total'] == 4, 'мод-действий всего = 4')
check(ml['mods'][0] == ('Старший Мод', 3), 'топ модератора (безымянное не считается)')
acts = dict(ml['actions'])
check(acts.get('Бан') == 2 and acts.get('Кик') == 1 and acts.get('Мут') == 1, 'по типам действий')
check(len(ml['labels']) == 30 and ml['counts'][-1] == 2, 'ряд по дням (сегодня 2)')
check(AP.mod_load(424242)['total'] == 0 and AP.mod_load(424242)['mods'] == [], 'пустой сервер модов')

vp = AP.voice_pulse(777)
check(vp['total_joins'] == 2 and vp['unique_users'] == 2, 'войс: только входы, 2 участника')
check(sum(vp['weekdays']) == 2, 'все входы попали в дни недели')
check({c for c, _n in vp['top_channels']} == {'Общий войс', 'Игровой'}, 'топ каналов войса')
check(AP.voice_pulse(424242)['total_joins'] == 0, 'пустой сервер войса')

il = AP.invite_leaders(777)
check(il['total'] == 3 and il['leaders'][0] == ('Мира', 2), 'инвайт-лидеры')
check(AP.invite_leaders(424242)['leaders'] == [], 'пустой сервер инвайтов')

full = AP.analytics_full_csv(777, days=30)
check('Мод-действие;Кол-во' in full and 'Бан;2' in full, 'полный CSV: секция модерации')
check('Инвайтер;Создано ссылок' in full and 'Мира;2' in full, 'полный CSV: инвайты')
check('Дата;Пришло;Ушло' in full, 'полный CSV: поток участников')
check('Участник;Сообщений' in full and 'Канал;Сообщений' in full, 'полный CSV: базовые секции')

for path in ('/api/guild/777/analytics/mod-load', '/api/guild/777/analytics/voice-pulse',
             '/api/guild/777/analytics/invite-leaders', '/api/guild/777/analytics_full.csv'):
    login('uye')
    check(client.get(path).status_code == 403, 'uye нельзя ' + path.split('/')[-1])
login('mod')
check(client.get('/api/guild/777/analytics/mod-load').get_json()['total'] == 4, 'mod читает мод-нагрузку')
check(client.get('/api/guild/777/analytics/voice-pulse').get_json()['total_joins'] == 2,
      'mod читает войс-пульс')
check(client.get('/api/guild/777/analytics/invite-leaders').get_json()['total'] == 3,
      'mod читает инвайты')
r = client.get('/api/guild/777/analytics_full.csv')
check(r.status_code == 200 and 'analytics_full_777_' in r.headers.get('Content-Disposition', ''),
      'полный CSV скачивается')

tpl = open(os.path.join(ROOT, 'web/templates/analytics.html'), encoding='utf-8').read()
check('anModLoad' in tpl and '/analytics/mod-load' in tpl, 'мод-нагрузка смонтирована')
check('anVoicePulse' in tpl and 'voice-pulse' in tpl, 'войс-пульс смонтирован')
check('anInvites' in tpl and 'invite-leaders' in tpl, 'инвайт-лидеры смонтированы')
check('anCsvFullBtn' in tpl and 'analytics_full.csv' in tpl, 'кнопка полного отчёта смонтирована')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
