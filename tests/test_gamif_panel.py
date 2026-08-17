# -*- coding: utf-8 -*-
"""Панель «Геймификация» (идеи #86-90).

Арифметика 1:1 с services/gamification.py: уровни LEVELS (перебор сверху,
прогресс), дейли (24ч кулдаун, битая дата = можно), серии (перерыв >1 дня
обнуляет текущую), корректировка формой add_points (reason 'panel').
Кросс-проверка уровня живым LevelSystem. Права mod+/admin+, CSV с BOM,
шаблон без эмодзи.

Запуск: python3 tests/test_gamif_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

_TMP = tempfile.mkdtemp(prefix='aether_gamif_test_')
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


from web.routes import gamif_panel as GF  # noqa: E402
import services.gamification as GM  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
NOW = datetime(2026, 8, 16, 12, 0)


def iso(dt):
    return dt.isoformat()


def seed_points(now):
    return {
        '7': {'total_points': 2600,
              'history': [{'points': 100, 'reason': 'daily',
                           'timestamp': iso(now - timedelta(days=1, hours=2))}],
              'last_daily': iso(now - timedelta(days=1, hours=2))},
        '12': {'total_points': 120,
               'history': [{'points': 120, 'reason': 'x',
                            'timestamp': iso(now - timedelta(hours=5))}],
               'last_daily': iso(now - timedelta(hours=5))},
        '9': {'total_points': 5000, 'history': []},
        'junk': ['no'],
    }


def seed_streaks(now):
    return {
        '7': {'current_streak': 5, 'longest_streak': 12,
              'last_activity': iso(now - timedelta(hours=3))},
        '12': {'current_streak': 9, 'longest_streak': 9,
               'last_activity': iso(now - timedelta(days=1))},
        '9': {'current_streak': 30, 'longest_streak': 30,
              'last_activity': iso(now - timedelta(days=4))},
        '55': {'current_streak': 2, 'longest_streak': 3,
               'last_activity': 'вчера-непонятно'},
        'junk': 'no',
    }


print('== 0. Константы из сервиса, не копии ==')
check(GF.DAILY_REWARD == GM.PointsSystem.DAILY_REWARD == 100
      and GF.DAILY_COOLDOWN == timedelta(hours=GM.PointsSystem.DAILY_COOLDOWN_HOURS),
      'награда и кулдаун дейли — атрибуты класса сервиса')

print('== 1. Уровни 1:1 ==')
lv = GF.level_view(5000)
check((lv['level'], lv['name'], lv['points_to_next'], lv['progress']) ==
      (6, 'Гуру', 5000, 0.0), '5000 — Гуру, до Легенды 5000')
lv = GF.level_view(2600)
check((lv['level'], lv['name'], lv['points_to_next'], lv['progress']) ==
      (5, 'Мастер', 2400, 4.0), '2600 — Мастер, прогресс 4%')
lv = GF.level_view(0)
check((lv['level'], lv['name'], lv['points_to_next'], lv['progress']) ==
      (1, 'Новичок', 100, 0.0), 'ноль — Новичок')
lv = GF.level_view(10000)
check(lv['level'] == 7 and lv['next_level'] is None
      and lv['progress'] == 100 and lv['points_to_next'] == 0,
      '10000 — Легенда, следующего нет')

print('== 2. Дейли 1:1 с can_claim_daily ==')
check(GF.daily_state({}, now=NOW) == (True, None), 'никогда не брал — можно')
check(GF.daily_state({'last_daily': iso(NOW - timedelta(hours=24))}, now=NOW)[0] is True,
      'ровно 24 часа — можно (>= кулдаун)')
can, left = GF.daily_state({'last_daily': iso(NOW - timedelta(hours=5))}, now=NOW)
check(can is False and left == 19 * 3600, '5 часов назад — ждать 19 ч')
check(GF.daily_state({'last_daily': 'абракадабра'}, now=NOW) == (True, None),
      'битая дата — можно, как у сервиса')
check(GF.daily_state(None, now=NOW) == (True, None), 'None-запись — можно')

print('== 3. Зал очков и сводка ==')
rows = GF.points_rows(seed_points(NOW), now=NOW)
check([r['user_id'] for r in rows] == ['9', '7', '12'],
      'топ по очкам, мусор пропущен')
check([r['rank'] for r in rows] == [1, 2, 3], 'ранги')
check([r['daily_can'] for r in rows] == [True, True, False],
      'флаги дейли по строкам')
check(rows[2]['daily_left_s'] == 68400, 'остаток кулдауна в секундах')
check(rows[0]['name'] == 'ID 9' and rows[1]['history'] == 1,
      'имя-фолбэк и длина истории')
summ = GF.points_summary(seed_points(NOW), now=NOW)
check(summ == {'people': 3, 'points_total': 7720, 'daily_claimable': 2,
               'daily_cooldown': 1, 'daily_reward': 100}, 'сводка зала')
check(GF.points_summary(None)['people'] == 0, 'пусто без падения')

print('== 4. Серии с обнулением перерыва ==')
rows = GF.streak_rows(seed_streaks(NOW), now=NOW)
check([r['user_id'] for r in rows] == ['12', '7', '55', '9'],
      'по живой серии: 12 (9), 7 (5), 55 (2), 9 (прервана)')
check(rows[0]['current'] == 9 and rows[0]['active_today'] is False, 'вчера — жива')
check(rows[1]['active_today'] is True, 'три часа назад — сегодня')
check(rows[3]['current'] == 0 and rows[3]['longest'] == 30,
      'перерыв 4 дня — текущая ноль, рекорд цел')
check(rows[2]['current'] == 2 and rows[2]['last_date'] == '',
      'битая дата — серию не трогаем')
ss = GF.streak_summary(seed_streaks(NOW), now=NOW)
check(ss == {'tracked': 4, 'active_today': 1, 'running': 3, 'best': 30},
      'сводка серий')

print('== 5. Досье и корректировка ==')
badges = {'7': [{'badge_id': 'first_ticket', 'name': 'Первый тикет'},
                {'badge_id': 'x7', 'name': '7 дней подряд'}]}
d = GF.player_dossier(seed_points(NOW), seed_streaks(NOW), badges, '7', now=NOW)
check(d['points'] == 2600 and d['level']['name'] == 'Мастер'
      and d['daily_can'] is True, 'досье: очки, уровень, дейли')
check(d['streak']['current'] == 5 and d['badges'] == ['Первый тикет', '7 дней подряд'],
      'досье: серия и бейджи')
check(len(d['history']) == 1 and d['history'][0]['reason'] == 'daily',
      'досье: история начислений')
check(GF.player_dossier(seed_points(NOW), seed_streaks(NOW), badges, '999') is None,
      'нет нигде — None')
store = {}
total, err, uid = GF.adjust_points(store, '<@123>', '50', 'admin', now=NOW)
check(total == 50 and err == '' and uid == '123', 'корректировка по упоминанию')
rec = store['123']
check(rec == {'total_points': 50, 'history': [
    {'points': 50, 'reason': 'panel', 'timestamp': iso(NOW)}]},
      'форма записи 1:1 с add_points (reason panel, naive iso)')
total, _e, _u = GF.adjust_points(store, '123', '-70', 'admin')
check(total == -20, 'минус честный, сервис тоже не режет в ноль')
check(GF.adjust_points(store, '123', 0, 'x')[1] == 'Корректировка не бывает нулевой',
      'ноль отброшен')
check(GF.adjust_points(store, '123', 5001, 'x')[1] == 'Разом — не больше ±5000',
      'потолок разовой корректировки')
check(GF.adjust_points(store, '123', 'много', 'x')[1] == 'Корректировка — целое число',
      'не число')
check(GF.adjust_points(store, 'ку-ку', 5, 'x')[1] == 'Некорректный ID пользователя',
      'ID через валидатор мод-контроля')

print('== 6. API: права и потоки ==')
real_now = datetime.now()
with open('data/user_points.json', 'w', encoding='utf-8') as fh:
    json.dump(seed_points(real_now), fh)
with open('data/user_streaks.json', 'w', encoding='utf-8') as fh:
    json.dump(seed_streaks(real_now), fh)
with open('data/user_badges.json', 'w', encoding='utf-8') as fh:
    json.dump(badges, fh)
with open('data/audit_log.json', 'w', encoding='utf-8') as fh:
    json.dump({'777': [
        {'category': 'mod', 'action': 'Мут', 'user_id': '12', 'user_name': 'Олег',
         'timestamp': iso(real_now)},
    ]}, fh)

appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


OV = '/api/guild/777/gamification/overview'
check(client.get('/gamification').status_code in (302, 401, 403),
      'гостю страница закрыта')
check(client.get(OV).status_code in (302, 401, 403), 'гостю снимок закрыт')
login('uye')
check(client.get(OV).status_code == 403, 'uye нельзя')
login('mod')
page = client.get('/gamification')
check(page.status_code == 200 and 'Геймификация' in page.get_data(as_text=True),
      'mod открывает страницу')
ov = client.get(OV).get_json()
check(ov['success'] and ov['can_edit'] is False, 'mod читает без права правки')
check(ov['points'][0]['user_id'] == '9' and ov['points'][1]['name'] == 'ID 7'
      and ov['points'][2]['name'] == 'Олег', 'имена: аудит сработал на Олеге')
check(ov['points_summary']['points_total'] == 7720
      and ov['streaks_summary']['best'] == 30, 'сводки в снимке')

r = client.get('/api/guild/777/gamification/player/7')
d = r.get_json()
check(r.status_code == 200 and d['player']['level']['level'] == 5
      and d['player']['badges'][0] == 'Первый тикет', 'досье игрока')
check(client.get('/api/guild/777/gamification/player/<@7>').get_json()['success'],
      'досье по упоминанию')
r = client.get('/api/guild/777/gamification/player/999')
check(r.status_code == 404 and r.get_json()['error'] == 'Игрок не найден.',
      'нет игрока — 404')
r = client.get('/api/guild/777/gamification/player/xyz')
check(r.status_code == 400
      and r.get_json()['error'] == 'Некорректный ID пользователя', 'битый ID — 400')
check(client.post('/api/guild/777/gamification/adjust',
                  json={'user_id': '9', 'delta': 1}).status_code == 403,
      'mod не крутит очки')

login('admin')
r = client.post('/api/guild/777/gamification/adjust',
                json={'user_id': '<@300>', 'delta': '25'})
d = r.get_json()
check(r.status_code == 200 and d['total'] == 25 and d['level']['name'] == 'Новичок',
      'admin начислил новичку 25')
disk = json.load(open('data/user_points.json', encoding='utf-8'))
check(disk['300']['history'][0]['reason'] == 'panel'
      and disk['300']['total_points'] == 25, 'запись в файле формы сервиса')
r = client.post('/api/guild/777/gamification/adjust',
                json={'user_id': '9', 'delta': 6000})
check(r.status_code == 400
      and r.get_json()['error'] == 'Разом — не больше ±5000', 'потолок — 400')

login('mod')
pts = GM.PointsSystem()           # свежий экземпляр читает файл tmp-каталога
svc = GM.LevelSystem(pts).get_level('9')
mine = GF.level_view(5000)
check((svc['level'], svc['name'], svc['points_to_next'], svc['progress']) ==
      (mine['level'], mine['name'], mine['points_to_next'], mine['progress']),
      'кросс-проверка уровня с живым сервисом')

csv_r = client.get('/api/guild/777/gamification/export.csv?kind=points')
body = csv_r.get_data(as_text=True)
check(csv_r.status_code == 200 and body.startswith('﻿rank;user_id;name;points'),
      'CSV очков: BOM + шапка')
check('1;9;ID 9;5000' in body and 'gamif_points.csv'
      in csv_r.headers.get('Content-Disposition', ''), 'лидер + имя файла')
csv_r = client.get('/api/guild/777/gamification/export.csv?kind=streaks')
body = csv_r.get_data(as_text=True)
check(body.startswith('﻿rank;user_id;name;current;longest;last_date'),
      'CSV серий: BOM + шапка')
check('1;12;Олег;9;9;' in body, 'серия Олега первой (имя из аудита)')
csv_r = client.get('/api/guild/777/gamification/export.csv')
check(csv_r.get_data(as_text=True).startswith('﻿rank;user_id;name;points'),
      'без kind — очки по умолчанию')

print('== 7. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/gamification.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('gfKpis', 'gfPoints', 'gfStreaks', 'gfAdjPanel', 'gfAdjId',
            'gfAdjDelta', 'gfAdjMsg', 'gfPid', 'gfPlayer',
            'gfCsvPoints', 'gfCsvStreaks'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check("'/overview'" in tpl and "'/player/'" in tpl and '/export.csv' in tpl,
      'API-пути в шаблоне')
import services.panel_menu as PM
com_pages = [pg['path'] for g in PM.MENU if g['key'] == 'community' for pg in g['pages']]
check('/gamification' in com_pages, 'пункт «Геймификация» в группе «Сообщество»')
check(PM.PAGE_COGS.get('/gamification') == ('gamification_cog',),
      'gamification_cog привязан к странице')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('gamif_panel') >= 1, 'модуль зарегистрирован в routes_extra')
import services.notification_dispatcher as ND
check(ND.EVENTS['gamification'][0] == 'event_gamification'
      and ND.DEFAULT_SETTINGS['event_gamification'] is True
      and ND.EVENT_LINKS['gamification'] == '/gamification',
      'событие gamification зарегистрировано в диспетчере')
tpl_n = open(os.path.join(ROOT, 'web/templates/notifications.html'),
             encoding='utf-8').read()
check('id="event-gamification"' in tpl_n, 'тумблер геймификации в центре уведомлений')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
