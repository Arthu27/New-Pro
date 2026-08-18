# -*- coding: utf-8 -*-
"""Панель «События и поиск игроков» (идеи #61-65).

Афиша 1:1 с /activity-list (предстоящие по дате), активность поисков 1:1
с /game-list (моложе двух часов и не полный), составы с именами аудита,
CSV участников с BOM, удаление/закрытие admin+, шаблон без эмодзи,
меню и PAGE_COGS.

Запуск: python3 tests/test_social_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_social_test_')
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


from web.routes import social_panel as SP  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def seed_events(base=NOW):
    future1 = (base + timedelta(minutes=25)).isoformat()
    future2 = (base + timedelta(days=3)).isoformat()
    past1 = (base - timedelta(days=2)).isoformat()
    return {
        '100': {'id': '100', 'title': 'Киновечер', 'description': 'смотрим вместе',
                'date': future1, 'max_participants': 0, 'participants': ['1', '2'],
                'created_by': '1', 'channel_id': '9', 'message_id': '555',
                'reminded': False},
        '101': {'id': '101', 'title': 'Турнир', 'description': '',
                'date': future2, 'max_participants': 2, 'participants': ['1', '3'],
                'created_by': '3', 'channel_id': '9', 'message_id': None,
                'reminded': True},
        '102': {'id': '102', 'title': 'Старый стрим', 'date': past1,
                'max_participants': 5, 'participants': [], 'created_by': '1',
                'channel_id': '9', 'reminded': True},
        '103': {'id': '103', 'title': 'Битый', 'date': 'скоро'},
        '104': 'не словарь',
    }


def seed_matches(base=NOW):
    fresh = (base - timedelta(minutes=10)).isoformat()
    half = (base - timedelta(minutes=30)).isoformat()
    stale = (base - timedelta(hours=3)).isoformat()
    future = (base + timedelta(hours=1)).isoformat()
    return {
        '200': {'id': '200', 'game': 'CS2', 'max_players': 3,
                'players': ['1', '2', '3'], 'note': None, 'created_by': '1',
                'created_at': fresh},
        '201': {'id': '201', 'game': 'Valorant', 'max_players': 5,
                'players': ['5'], 'note': 'рейд', 'created_by': '5',
                'created_at': half},
        '202': {'id': '202', 'game': 'Dota', 'max_players': 4,
                'players': ['6'], 'note': '', 'created_by': '6',
                'created_at': stale},
        '205': {'id': '205', 'game': 'Из будущего', 'max_players': 4,
                'players': ['6'], 'note': '', 'created_by': '6',
                'created_at': future},
        '203': {'id': '203', 'game': 'Битая', 'created_at': 'вчера'},
        '204': 42,
    }


print('== 1. Афиша 1:1 с /activity-list ==')
events = SP.event_rows(seed_events(), now=NOW)
check([e['id'] for e in events] == ['100', '101', '102'],
      'предстоящие по дате, минувшее в хвосте, битые пропущены')
check(events[0]['past'] is False and events[0]['count'] == 2,
      'ближайшее событие, двое записались')
check(events[0]['max_participants'] == 0 and events[0]['spots_left'] is None
      and events[0]['full'] is False, 'ноль мест = без лимита')
check(events[1]['full'] is True and events[1]['spots_left'] == 0,
      'турнир 2/2 — мест нет')
check(events[2]['past'] is True and events[2]['reminded'] is True,
      'минувшее с ушедшим напоминанием')
check(events[1]['created_by'] == '3' and events[1]['channel_id'] == '9',
      'автор и канал сохранены')
check(SP.event_rows(None, now=NOW) == [] and SP.event_rows({}, now=NOW) == [],
      'пустые хранилища — пустая афиша')
naive = SP.event_rows({'1': {'date': '2026-08-20 18:00', 'title': 'Наивная'}},
                      now=NOW)
check(len(naive) == 1 and naive[0]['past'] is False,
      'наивная дата читается как UTC')
check(SP.event_rows({'1': {'date': '2026-08-16T16:00+03:00',
                           'title': 'Смоленск'}}, now=NOW)[0]['past'] is False,
      'дата со сдвигом +03:00 не врёт (16:00+03 = 13:00 UTC — ещё впереди)')

print('== 2. Доска поисков 1:1 с /game-list ==')
matches = SP.match_rows(seed_matches(), now=NOW)
check([m['id'] for m in matches] == ['205', '201', '200', '202'],
      'активные первыми (свежие сверху), потом полные и истёкшие')
check(matches[0]['active'] is True and matches[0]['age_min'] == -60,
      'created_at из будущего активен — как у кога')
check(matches[1]['active'] is True and matches[1]['age_min'] == 30,
      'получасовой поиск активен')
check(matches[2]['full'] is True and matches[2]['active'] is False,
      'полный состав не активен, хоть и свежий')
check(matches[3]['active'] is False and matches[3]['age_min'] == 180,
      'трёхчасовой истёк (окно 7200 с)')
check(matches[1]['note'] == 'рейд' and matches[2]['note'] == '',
      'заметка строкой, None — пустая')
edge = SP.match_rows({'1': {'created_at': (NOW - timedelta(seconds=7200)).isoformat(),
                            'max_players': 2, 'players': [], 'game': 'Г'}}, now=NOW)
check(edge[0]['active'] is False, 'ровно 7200 секунд — уже не активен (строгое <)')
check(SP.match_rows(None, now=NOW) == [], 'пустое хранилище — пустая доска')

print('== 3. Сводка доски ==')
stats = SP.board_stats(events, matches)
check(stats['events_total'] == 3 and stats['events_upcoming'] == 2,
      'всего и предстоящих событий')
check(stats['participants'] == 4, 'участники только в предстоящих (2+2)')
check(stats['matches_active'] == 2 and stats['seekers'] == 2,
      'два активных поиска, по игроку в каждом')
check(SP.board_stats([], []) == {'events_total': 0, 'events_upcoming': 0,
                                 'participants': 0, 'matches_active': 0,
                                 'seekers': 0}, 'нули без падения')

print('== 4. API: права и потоки ==')
real_now = datetime.now(timezone.utc)
with open('data/events_777.json', 'w', encoding='utf-8') as fh:
    json.dump(seed_events(real_now), fh)
with open('data/matchmaking_777.json', 'w', encoding='utf-8') as fh:
    json.dump(seed_matches(real_now), fh)
with open('data/audit_log.json', 'w', encoding='utf-8') as fh:
    json.dump({'777': [
        {'category': 'mod', 'action': 'Мут', 'user_id': '2', 'user_name': 'Борислав',
         'timestamp': NOW.isoformat()},
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


OV = '/api/guild/777/social/overview'
check(client.get('/social').status_code in (302, 401, 403),
      'гостю страница закрыта')
check(client.get(OV).status_code in (302, 401, 403), 'гостю снимок закрыт')
login('uye')
check(client.get(OV).status_code == 403, 'uye нельзя')
login('mod')
page = client.get('/social')
check(page.status_code == 200 and 'События' in page.get_data(as_text=True),
      'mod открывает страницу')
check("var GID = '777'" in page.get_data(as_text=True), 'активный сервер в странице')
ov = client.get(OV).get_json()
check(ov['success'] and ov['can_edit'] is False, 'mod читает без права правки')
check([e['id'] for e in ov['events']] == ['100', '101', '102'],
      'афиша в порядке кога')
check(ov['stats']['events_upcoming'] == 2 and ov['stats']['seekers'] == 2,
      'сводка в снимке')
m200 = [m for m in ov['matches'] if m['id'] == '200'][0]
check(m200['players_named'][1]['name'] == 'Борислав',
      'имена игроков из аудит-журнала')
check(m200['created_by_name'] == '' and ov['events'][0]['created_by_name'] == '',
      'неизвестный автор — пустая строка, не мусор')

check(client.post('/api/guild/777/social/events/delete',
                  json={'event_id': '102'}).status_code == 403,
      'mod не удаляет события')
check(client.post('/api/guild/777/social/matches/close',
                  json={'match_id': '202'}).status_code == 403,
      'mod не закрывает поиски')

login('admin')
r = client.post('/api/guild/777/social/events/delete', json={'event_id': '102'})
d = r.get_json()
check(r.status_code == 200 and d['removed']['title'] == 'Старый стрим',
      'admin удалил, удалённое возвращено')
disk = json.load(open('data/events_777.json', encoding='utf-8'))
check('102' not in disk and '100' in disk, 'файл события убран, соседи целы')
r = client.post('/api/guild/777/social/events/delete', json={'event_id': '102'})
check(r.status_code == 404 and r.get_json()['error'] == 'Событие не найдено.',
      'повторное удаление — 404')
r = client.post('/api/guild/777/social/events/delete', json={'event_id': ''})
check(r.status_code == 404, 'пустой ID — 404, не 500')

r = client.post('/api/guild/777/social/matches/close', json={'match_id': '202'})
check(r.status_code == 200 and r.get_json()['removed']['game'] == 'Dota',
      'admin закрыл истёкший поиск')
r = client.post('/api/guild/777/social/matches/close', json={'match_id': '202'})
check(r.status_code == 404 and r.get_json()['error'] == 'Поиск не найден.',
      'повторное закрытие — 404')

login('mod')
csv_r = client.get('/api/guild/777/social/events/100/participants.csv')
body = csv_r.get_data(as_text=True)
check(csv_r.status_code == 200
      and 'event_100_777.csv' in csv_r.headers.get('Content-Disposition', ''),
      'CSV состава с именем файла события и сервера')
check(body.startswith('\ufeffuser_id;name'), 'BOM + шапка')
check('2;Борислав' in body and '1;1' in body,
      'имя из аудита; без имени — голый ID')
r = client.get('/api/guild/777/social/events/999/participants.csv')
check(r.status_code == 404 and r.get_json()['error'] == 'Событие не найдено.',
      'CSV чужого события — 404')

print('== 5. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/social.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
base_tpl = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('data-theme="light"' in base_tpl, 'светлая тема учтена (общий shell)')
for fid in ('soKpis', 'soEvents', 'soMatches'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check("'/overview'" in tpl and 'participants.csv' in tpl, 'API-пути в шаблоне')
import services.panel_menu as PM
com_pages = [pg['path'] for g in PM.MENU if g['key'] == 'community' for pg in g['pages']]
check('/social' in com_pages, 'пункт «События» в группе «Сообщество»')
check(PM.PAGE_COGS.get('/social') == ('social',), 'social-ког привязан к странице')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('social_panel') >= 1, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
