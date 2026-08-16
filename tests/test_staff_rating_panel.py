# -*- coding: utf-8 -*-
"""Панель «Оценки персонала» (идеи #101-105).

Таблица 1:1 с rating_rows кога (сорт, пропуски, лимит), команда средняя
1:1 _avg, звёзды данными (в шаблоне — через chr), зачётка: гистограмма,
комментарии хвостом, голосующие по оценке; снятие голоса admin+ (комменты
голосующего улетают), CSV с BOM, права, шаблон без эмодзи, меню/регистрация.

Запуск: python3 tests/test_staff_rating_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_srating_test_')
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


from web.routes import staff_rating_panel as SP  # noqa: E402
from cogs import staff_rating as SR  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')


def raw_state():
    return {'staff': {
        '10': {'votes': {'1': 5, '2': 4, '3': 5},
               'comments': [
                   {'voter': '1', 'score': 5, 'text': 'топ', 'at': '2026-08-10T10:00'},
                   {'voter': '3', 'score': 5, 'text': 'класс', 'at': '2026-08-12T09:00'}]},
        '20': {'votes': {'1': 3, '4': 2},
               'comments': [{'voter': '4', 'score': 2, 'text': 'груб;но', 'at': '2026-08-11T08:00'}]},
        '30': {'votes': {'2': 5}, 'comments': []},
        '40': {'votes': {}, 'comments': []},
        'xx': {'votes': {'9': 1}, 'comments': []},
    }}


def filled_state():
    """Живой state через add_vote кога: '40' — 2 голоса и 2 комментария."""
    state = SR.empty_state()
    t = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
    SR.add_vote(state, '7', '40', 5, 'молодец', now=t)
    SR.add_vote(state, '8', '40', 3, 'норм', now=t + timedelta(hours=1))
    return state


print('== 1. Таблица и сводка 1:1 с когом ==')
table = SP.rating_table(raw_state(), names={'10': 'Мира', '30': 'Лев'})
check([r['staff_id'] for r in table] == ['30', '10', '20'],
      'порядок кога: балл, голоса, ID')
check(table[0]['name'] == 'Лев' and table[1]['name'] == 'Мира'
      and table[2]['name'] == '', 'имена из аудита, без имени — пусто')
check(table[1]['avg'] == 4.67 and table[0]['avg'] == 5.0, 'баллы кога')
check(table[1]['stars'] == '★★★★★' and table[2]['stars'] == '★★★☆☆',
      'звёзды score_stars кога (4.67 → 5, 2.5 → 3)')
check(table[1]['rank'] == 2 and table[0]['rank'] == 1, 'места 1-го ранга')
check(all(r['staff_id'] not in ('40', 'xx') for r in table),
      'без голосов и «xx» пропущены — как у кога')
stats = SP.overview_stats(raw_state(), names={'10': 'Мира', '30': 'Лев'})
check(stats['team_avg'] == 4.0 and stats['votes_total'] == 6,
      '24 балла за 6 голосов = 4.0')
check(stats['staff_rated'] == 3, 'трое с голосами')
check(stats['leader']['staff_id'] == '30' and stats['leader']['name'] == 'Лев',
      'лидер — Лев')
empty = SP.overview_stats(SR.empty_state())
check(empty['team_avg'] == 0 and empty['leader'] is None and empty['staff_rated'] == 0,
      'пусто — нули и без лидера')
check(SP.rating_table(raw_state(), limit=2) == SP.rating_table(raw_state())[:2],
      'лимит кога уважается')

print('== 2. Гистограмма и зачётка ==')
check(SP.score_distribution({'a': 5, 'b': 4, 'c': 5}) == {'1': 0, '2': 0, '3': 0,
                                                          '4': 1, '5': 2}, '5/4/5')
check(SP.score_distribution({'a': 0, 'b': 7, 'c': 'x', 'd': True, 'e': 3})
      == {'1': 0, '2': 0, '3': 1, '4': 0, '5': 0}, 'кривые оценки — как у кога')
check(SP.score_distribution(None) == {'1': 0, '2': 0, '3': 0, '4': 0, '5': 0},
      'пустая гистограмма')
card = SP.staff_card(raw_state(), 10, names={'1': 'Ксения', '3': 'Женя', '10': 'Мира'})
check(card['name'] == 'Мира' and card['avg'] == 4.67 and card['votes'] == 3,
      'голова зачётки')
check([c['voter'] for c in card['comments']] == ['3', '1']
      and card['comments'][0]['voter_name'] == 'Женя',
      'комментарии свежие первыми с именами')
check(card['comments'][0]['at'] == '2026-08-12 09:00', 'метка читаемая')
check([(v['voter'], v['score']) for v in card['voters']] ==
      [('1', 5), ('3', 5), ('2', 4)], 'голосующие: оценка убывает, потом ID')
check(set(card['distribution'].values()) == {0, 1, 2}
      and card['distribution']['5'] == 2 and card['distribution']['4'] == 1,
      'гистограмма в зачётке')
check(SP.staff_card(raw_state(), 40) is None, 'без голосов — None (как staff_summary)')
check(SP.staff_card(None, 10) is None, 'пустое хранилище — None')

print('== 3. Снятие голоса ==')
st = raw_state()
ok, err, n = SP.remove_vote(st, 10, 2)
check(ok and n == 1 and st['staff']['10']['votes'] == {'1': 5, '3': 5},
      'голос снят, соседи целы')
ok, err, n = SP.remove_vote(st, 10, 9)
check(not ok and err == 'Голос не найден' and n == 0, 'чужой голос — 404 текст')
st = raw_state()
ok, err, n = SP.remove_vote(st, 20)
check(ok and n == 2 and '20' not in st['staff'], 'зачётка очищена целиком')
ok, err, n = SP.remove_vote(st, 99)
check(not ok and err == 'Модератор без оценок не найден', 'нет такого — 404 текст')
st = raw_state()
ok, err, n = SP.remove_vote(st, 30, 2)
check(ok and n == 1 and '30' not in st['staff'],
      'последний голос снимаем — запись уходит')
st = filled_state()
ok, err, n = SP.remove_vote(st, 40, 7)
check(ok and n == 1 and st['staff']['40']['votes'] == {'8': 3},
      'голос 7 снят, остался 8')
check([c['voter'] for c in st['staff']['40']['comments']] == ['8'],
      'и его комментарий улетел')
ok, avg = SR.add_vote(SR.empty_state(), '1', '2', 5, now=datetime.now(timezone.utc))
check(avg == 5.0 and ok in ('ok', 'updated'), 'add_vote кога жив (паритет)')

print('== 4. API: права, потоки, CSV ==')
from db import GuildData
state = raw_state()
state['staff'].update(filled_state()['staff'])
GuildData('staff_rating').set('777', 'state', state)

appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


OV = '/api/guild/777/staff-rating/overview'
check(client.get('/staff-rating').status_code in (302, 401, 403), 'гостю закрыто')
check(client.get(OV).status_code in (302, 401, 403), 'гостю снимок закрыт')
login('uye')
check(client.get(OV).status_code == 403, 'uye нельзя')
login('mod')
page = client.get('/staff-rating')
check(page.status_code == 200 and 'Оценки персонала' in page.get_data(as_text=True),
      'mod открывает страницу')
check(page.get_data(as_text=True).count('pickers.js') == 0,
      'чужие хелперы не тащим (странице нечего подсказывать)')
ov = client.get(OV).get_json()
check(ov['success'] and ov['can_edit'] is False, 'mod без права правки')
check(ov['stats']['votes_total'] == 8 and ov['stats']['staff_rated'] == 4,
      'сводка по четырём модераторам')
r = client.get('/api/guild/777/staff-rating/card?staff=10')
check(r.status_code == 200 and r.get_json()['card']['can_edit'] is False,
      'mod открывает зачётку без крестиков')
r = client.get('/api/guild/777/staff-rating/card?staff=куку')
check(r.status_code == 400 and r.get_json()['error'] == 'Некорректный ID пользователя',
      'битый staff — валидация мод-контроля')
r = client.get('/api/guild/777/staff-rating/card?staff=999')
check(r.status_code == 404 and r.get_json()['error'] == 'Оценок у модератора нет.',
      'нет голосов — 404')
check(client.post('/api/guild/777/staff-rating/remove',
                  json={'staff_id': '10', 'voter_id': '1'}).status_code == 403,
      'mod не снимает голоса')

login('admin')
r = client.post('/api/guild/777/staff-rating/remove',
                json={'staff_id': '10', 'voter_id': '2'})
d = r.get_json()
check(r.status_code == 200 and d['removed'] == 1
      and d['card']['votes'] == 2 and d['card']['avg'] == 5.0,
      'admin снял голос — зачётка пересчитана')
r = client.post('/api/guild/777/staff-rating/remove', json={'staff_id': '10', 'voter_id': '<@3>'})
check(r.get_json()['removed'] == 1, 'снятие по упоминанию')
r = client.post('/api/guild/777/staff-rating/remove', json={'staff_id': '10'})
d = r.get_json()
check(r.status_code == 200 and d['removed'] == 1 and d['card'] is None,
      'без voter_id вся зачётка уходит, остался один голос — removed 1')
r = client.post('/api/guild/777/staff-rating/remove', json={'staff_id': '10'})
check(r.status_code == 404
      and r.get_json()['error'] == 'Модератор без оценок не найден',
      'повтор — уже пусто, 404 словами панели')
r = client.post('/api/guild/777/staff-rating/remove',
                json={'staff_id': '30', 'voter_id': '*'})
d = r.get_json()
check(r.status_code == 200 and d['removed'] == 1 and d['card'] is None,
      'звёздочка очистила Льва, карточки больше нет')
r = client.post('/api/guild/777/staff-rating/remove', json={'staff_id': 'криво'})
check(r.status_code == 400 and r.get_json()['error'] == 'Некорректный ID пользователя',
      'битый staff_id — 400')
r = client.post('/api/guild/777/staff-rating/remove',
                json={'staff_id': '40', 'voter_id': 'криво'})
check(r.status_code == 400, 'битый voter_id — 400')

csv_r = client.get('/api/guild/777/staff-rating/export.csv')
body = csv_r.get_data(as_text=True)
check(csv_r.status_code == 200
      and 'staff_rating_777.csv' in csv_r.headers.get('Content-Disposition', ''),
      'CSV с именем сервера')
check(body.startswith('﻿rank;staff_id;name;avg;stars;votes'), 'BOM + шапка')
check('★★★★☆' in body, 'звёзды 4.0 в CSV — данные, а не шаблон')

login('mod')
csv_r = client.get('/api/guild/777/staff-rating/export.csv')
check(csv_r.status_code == 200, 'mod тоже выгружает')

print('== 5. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/staff_rating.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи (звёзды — из данных)')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('srKpis', 'srTable', 'srCard', 'srCsv'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check("'/overview'" in tpl and "'/card?staff='" in tpl and '/export.csv' in tpl,
      'API-пути в шаблоне')
check('\\u2605' in tpl and '\\u2606' in tpl, 'звёзды через unicode-последовательности')
import services.panel_menu as PM
mod_pages = [pg['path'] for g in PM.MENU if g['key'] == 'mod' for pg in g['pages']]
com_pages = [pg['path'] for g in PM.MENU if g['key'] == 'community' for pg in g['pages']]
check('/staff-rating' in mod_pages or '/staff-rating' in com_pages,
      'пункт меню «Оценки персонала»')
check(PM.PAGE_COGS.get('/staff-rating') == ('staff_rating',),
      'staff_rating-ког привязан к странице')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('staff_rating_panel') >= 2, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
