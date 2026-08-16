# -*- coding: utf-8 -*-
"""Карма-панель (идеи #51-55).

Чистые агрегаты (зал, лента окна, тёплые пары + фермерские флаги,
корректировка 1:1 с apply_rep кога), HTTP-права mod+/admin+, CSV с BOM,
шаблон без эмодзи, меню и PAGE_COGS.

Запуск: python3 tests/test_karma_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

_TMP = tempfile.mkdtemp(prefix='aether_karma_test_')
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


from web.routes import karma_panel as KP  # noqa: E402
from db import GuildData  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
NOW = datetime(2026, 8, 16, 12, 0)
NAMES = {'1': 'Аня', '2': 'Боря', '3': 'Вик;а', '5': 'Дима', '6': 'Ева'}


def ago(**kw):
    return (NOW - timedelta(**kw)).isoformat()


def seed_state():
    return {
        'scores': {'1': 7, '2': 5, '3': 5, '4': 0},
        'thanks': [
            {'giver': '1', 'target': '2', 'at': ago(days=3), 'reason': 'помог с боссом'},
            {'giver': '1', 'target': '2', 'at': ago(days=2), 'reason': 'снова выручил'},
            {'giver': '2', 'target': '1', 'at': ago(days=1), 'reason': ''},
            {'giver': '5', 'target': '6', 'at': ago(days=5), 'reason': 'спасибо'},
            {'giver': '5', 'target': '6', 'at': ago(hours=36), 'reason': 'угостил'},
            {'giver': '6', 'target': '5', 'at': ago(days=4), 'reason': ''},
            {'giver': '6', 'target': '5', 'at': ago(days=2), 'reason': ''},
            {'giver': '6', 'target': '5', 'at': ago(days=1), 'reason': ''},
            {'giver': '5', 'target': '6', 'at': ago(hours=12), 'reason': 'держал слово'},
            {'giver': '9', 'target': '8', 'at': ago(days=10), 'reason': 'старое'},
        ],
    }


print('== 1. Сводка зала благодарностей ==')
snap = KP.karma_snapshot(seed_state(), names=NAMES, now=NOW)
check([r['user_id'] for r in snap['top']] == ['1', '2', '3'],
      'топ 1:1 с top_rows кога (7, 5, 5 — ничья решается ID)')
check(snap['top'][0]['name'] == 'Аня' and snap['top'][0]['score'] == 7,
      'лидер с именем и очками')
check(snap['people'] == 4 and snap['points_total'] == 17, 'люди и сумма очков')
check(snap['thanks_total'] == 10 and snap['thanks_window'] == 9,
      'журнал 9 записей, из них 8 за неделю')
check(snap['leader']['user_id'] == '1', 'лидер выделен')
empty = KP.karma_snapshot(None, now=NOW)
check(empty['top'] == [] and empty['leader'] is None and empty['points_total'] == 0,
      'пустое состояние — честные нули')

print('== 2. Лента благодарностей ==')
feed = KP.thanks_feed(seed_state(), names=NAMES, now=NOW)
check(len(feed) == 9, '9 записей за окно')
check(feed[0]['giver'] == '5' and feed[0]['reason'] == 'держал слово',
      'свежая первая, причина цела')
check(feed[0]['giver_name'] == 'Дима' and feed[0]['target_name'] == 'Ева',
      'имена обеих сторон')
check(all(r['giver'] != '9' for r in feed), 'запись старше окна отрезана')
fil = KP.thanks_feed(seed_state(), now=NOW, user_id='2')
check(len(fil) == 3 and fil[0]['giver'] == '2' and fil[0]['target'] == '1',
      'фильтр по участнику ловит обе стороны, свежая первая')
fil_none = KP.thanks_feed(seed_state(), now=NOW, user_id='424242')
check(fil_none == [], 'чужой фильтр — пусто без падения')
lim = KP.thanks_feed(seed_state(), now=NOW, limit=3)
check(len(lim) == 3, 'лимит ленты')

print('== 3. Тёплые пары и фермерство ==')
pairs = KP.warm_pairs(seed_state(), now=NOW)
check(len(pairs) == 2, 'две связки от двух благодарностей')
check(pairs[0]['giver'] == '5' and pairs[0]['count'] == 3 and pairs[0]['back'] == 3
      and pairs[0]['farming'] is True,
      'взаимный фарм 3×3 помечен и идёт первым (строка — направление 5→6)')
check(pairs[1]['giver'] == '1' and pairs[1]['count'] == 2 and pairs[1]['back'] == 1
      and pairs[1]['farming'] is False, 'тёплая, но не фермерская пара')
check(all(not (p['giver'] == '6' and p['target'] == '5') for p in pairs),
      'обратная сторона взаимной пары не дублируется строкой')
weak = KP.warm_pairs({'scores': {}, 'thanks': [
    {'giver': '1', 'target': '2', 'at': ago(days=1), 'reason': ''}]}, now=NOW)
check(weak == [], 'одиночное спасибо парой не считается')

print('== 4. Корректировка очков ==')
st = seed_state()
ok, err, total = KP.adjust_score(st, '<@1>', 5)
check(ok and total == 12 and st['scores']['1'] == 12,
      'плюсовка через apply_rep кога: 7+5=12')
ok, err, total = KP.adjust_score(st, '2', -3)
check(ok and total == 2 and st['scores']['2'] == 2, 'минусовка: 5-3=2')
check(KP.adjust_score(st, '3', 'много')[1] == 'Корректировка — целое число',
      'не число — ошибка')
check(KP.adjust_score(st, '3', 0) == (False, 'Корректировка не бывает нулевой', None),
      'ноль запрещён')
check(KP.adjust_score(st, '3', 501)[1] == 'Разом — не больше ±500', 'потолок ±500')
check(KP.adjust_score(st, 'куку', 5)[1] == 'Некорректный ID пользователя',
      'битый ID — ошибка 1:1 с мод-контролем')

print('== 5. API: права и потоки ==')
GuildData('karma').set(777, 'state', seed_state())
with open('data/audit_log.json', 'w', encoding='utf-8') as fh:
    json.dump({'777': [
        {'category': 'mod', 'action': 'Мут', 'user_id': '1', 'user_name': 'Аня',
         'timestamp': NOW.isoformat()},
        {'category': 'mod', 'action': 'Мут', 'user_id': '2', 'user_name': 'Боря',
         'timestamp': NOW.isoformat()},
        {'category': 'mod', 'action': 'Мут', 'user_id': '3', 'user_name': 'Вик;а',
         'timestamp': NOW.isoformat()},
        {'category': 'mod', 'action': 'Мут', 'user_id': '5', 'user_name': 'Дима',
         'timestamp': NOW.isoformat()},
        {'category': 'mod', 'action': 'Мут', 'user_id': '6', 'user_name': 'Ева',
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


OV = '/api/guild/777/karma/overview'
check(client.get('/karma').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get(OV).status_code in (302, 401, 403), 'гостю снимок закрыт')
login('uye')
check(client.get(OV).status_code == 403, 'uye нельзя')
login('mod')
page = client.get('/karma')
check(page.status_code == 200 and 'Зал благодарностей' in page.get_data(as_text=True),
      'mod открывает страницу')
check("var GID = '777'" in page.get_data(as_text=True), 'активный сервер в странице')
ov = client.get(OV).get_json()
check(ov['success'] and ov['can_edit'] is False, 'mod читает без права правки')
check(ov['snapshot']['top'][0]['name'] == 'Аня', 'имя лидера из аудит-журнала')
check(len(ov['feed']) == 9 and len(ov['pairs']) == 2, 'лента и пары в снимке')
check(ov['pairs'][0]['farming'] is True and ov['pairs'][0]['target_name'] == 'Ева',
      'фермерская пара с именами')
fil = client.get(OV + '?user=<@2>').get_json()
check(fil['feed_filter'] == '2' and len(fil['feed']) == 3, 'фильтр ленты по упоминанию')
bad = client.get(OV + '?user=прокол').get_json()
check(bad['feed_filter'] is None and len(bad['feed']) == 9,
      'битый фильтр мягко снят, не 400')

check(client.post('/api/guild/777/karma/adjust',
                  json={'user_id': '3', 'delta': -2}).status_code == 403,
      'mod не корректирует очки')
login('admin')
r = client.post('/api/guild/777/karma/adjust', json={'user_id': '<@3>', 'delta': '-2'})
d = r.get_json()
check(r.status_code == 200 and d['total'] == 3 and d['user_id'] == '3',
      'admin корректирует (строковая дельта тоже парсится)')
check(GuildData('karma').get(777, 'state')['scores']['3'] == 3, 'хранилище кога обновлено')
check(d['snapshot']['top'][1]['score'] == 5, 'снимок после правки пересчитан')
r = client.post('/api/guild/777/karma/adjust', json={'user_id': '3', 'delta': 0})
check(r.status_code == 400 and r.get_json()['error'] == 'Корректировка не бывает нулевой',
      'ноль — 400 словами валидатора')
r = client.post('/api/guild/777/karma/adjust', json={'user_id': '3', 'delta': 999})
check(r.status_code == 400 and r.get_json()['error'] == 'Разом — не больше ±500',
      'размах — 400')

csv_r = client.get('/api/guild/777/karma/export.csv')
body = csv_r.get_data(as_text=True)
check(csv_r.status_code == 200 and 'karma_777.csv' in csv_r.headers.get('Content-Disposition', ''),
      'CSV скачивается с именем сервера')
check(body.startswith('﻿rank;user_id;name;score'), 'BOM + шапка для Excel')
check('1;1;Аня;7' in body and '3;3;Вик,а;3' in body,
      'строки с рангами; точка с запятой в имени обезврежена')

print('== 6. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/karma.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('kmKpis', 'kmTop', 'kmFeed', 'kmPairs', 'kmAdjId', 'kmAdjDelta',
            'kmCsv', 'kmFilter', 'kmAdjustPanel'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check('/export.csv' in tpl and "'/overview'" in tpl, 'API-пути в шаблоне')
import services.panel_menu as PM
com_pages = [pg['path'] for g in PM.MENU if g['key'] == 'community' for pg in g['pages']]
check('/karma' in com_pages, 'пункт «Карма» в группе «Сообщество»')
check(PM.PAGE_COGS.get('/karma') == ('karma',), 'карма-ког привязан к странице')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('karma_panel') >= 2, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
