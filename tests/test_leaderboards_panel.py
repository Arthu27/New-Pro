# -*- coding: utf-8 -*-
"""Рейтинги (идеи #146-150).

Топ-7 через _get_lb_data кога (тексты значений и демо-строки 1:1), сырые
списки из тех же трёх источников с той же сортировкой, позиция участника
за пределами семёрки, PNG карточкой кога офлайн, отправка (офлайн — 409),
CSV всех строк, права, шаблон, меню.

Запуск: python3 tests/test_leaderboards_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_leaderboards_test_')
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


from web.routes import leaderboards_panel as PL  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')

# Фикстуры до любых чтений (load_json кэширует). Лидерборд и экономику
# ког читает по абсолютному DATA_DIR (корень проекта) — пишем туда же
# и убираем за собой в конце прогона.
from cogs import leaderboard as LB  # noqa: E402
_LB_FILE = os.path.join(LB.DATA_DIR, 'leaderboard_777.json')
_ECO_FILE = os.path.join(LB.DATA_DIR, 'economy_777.json')
json.dump({'messages': {'111': 1850, '222': 1240, '333': 890, '444': 610,
                        '555': 420, '666': 300, '7777': 100, '8888': 50}},
          open(_LB_FILE, 'w', encoding='utf-8'))
json.dump({'111': {'balance': 100000, 'bank': 400000},
           '222': {'balance': 275000},
           '333': {'balance': 100000, 'bank': 50000}},
          open(_ECO_FILE, 'w', encoding='utf-8'))
json.dump({'users': {'111': {'total_seconds': 189600, 'name': 'Катя'},
                     '222': {'total_seconds': 77400, 'name': 'Иван'},
                     '333': {'total_seconds': 21400, 'name': 'Оля'}}},
          open('data/voice_stats_777.json', 'w', encoding='utf-8'))

print('== 1. Категории и сырые списки ==')
check(PL.clamp_cat('VOICE') == 'voice' and PL.clamp_cat('мусор') == 'messages'
      and PL.clamp_cat(None) == 'messages', 'кламп категории как в команде')
rows = PL.raw_rows('777', 'messages')
check(len(rows) == 8 and rows[0] == ('111', 1850) and rows[-1] == ('8888', 50),
      'сообщения: 8 строк по убыванию')
check([u for u, _v in PL.raw_rows('777', 'balance')] == ['111', '222', '333'],
      'баланс: кошелёк+банк')
check(PL.raw_rows('777', 'voice')[0] == ('111', 189600), 'войс: total_seconds')
check(PL.raw_rows('999', 'messages') == [], 'пустой сервер — пусто')

print('== 2. Топ-7 словами бота ==')
t = PL.table_view(None, '777', 'messages')
check(t['demo'] is False and len(t['rows']) == 7, 'семёрка из восьми без демо')
check(t['rows'][0] == {'rank': 1, 'name': 'ID 111', 'value': '1 850 СООБЩЕНИЙ'},
      'первая строка в наряде бота (офлайн-имя — его фолбэк)')
check(t['rows'][6]['name'] == 'ID 7777', 'седьмая строка отрезана правильно')
t = PL.table_view(None, '777', 'voice')
check(t['rows'][0] == {'rank': 1, 'name': 'Катя', 'value': '52ч 40м В ВОЙСЕ'},
      'войс: имя из статистики, значение его формата')
check(t['demo'] is False and len(t['rows']) == 3
      and t['rows'][2] == {'rank': 3, 'name': 'Оля', 'value': '5ч 56м В ВОЙСЕ'},
      '3 своих, демо нет — ког подмешивает только при полной пустоте')
t = PL.table_view(None, '777', 'balance')
check(t['rows'][0]['value'] == '500 000 МОНЕТ' and len(t['rows']) == 3
      and t['demo'] is False,
      'баланс: сумма и все свои строки')
t = PL.table_view(None, '999', 'messages')
check(t['demo'] is True and len(t['rows']) == 5
      and t['rows'][0]['name'] == 'AETHER_LEADER'
      and t['rows'][0]['value'] == '1 850 СООБЩЕНИЙ',
      'без данных — его демо-строки, помеченные')
check(t['title'] == 'ТОП ПО СООБЩЕНИЯМ', 'заголовок категории')

print('== 3. Позиция участника ==')
ok, err, ranks = PL.rank_view('777', 'мусор')
check(not ok and err == 'Некорректный ID пользователя', 'битый ID — текст валидатора')
ok, err, ranks = PL.rank_view('777', '<@111>')
check(ok and ranks[0]['rank'] == 1 and ranks[0]['raw'] == 1850
      and ranks[0]['total'] == 8, 'первый в сообщениях')
check(ranks[1] == {'cat': 'voice', 'title': 'ТОП ПО ГОЛОСУ', 'rank': 1,
                   'total': 3, 'raw': 189600}, 'первый в войсе')
check(ranks[2]['rank'] == 1 and ranks[2]['raw'] == 500000,
      'первый по балансу (кошелёк+банк)')
ok, err, ranks = PL.rank_view('777', '8888')
check(ranks[0]['rank'] == 8 and ranks[1]['rank'] is None
      and ranks[2]['rank'] is None, 'восьмой там, вне списка тут')
ok, err, ranks = PL.rank_view('777', '999')
check(all(r['rank'] is None and r['raw'] == 0 for r in ranks), 'незнакомец вне списков')
check(PL.rank_pretty('messages', 1850) == '1 850 сообщений', 'красиво: сообщения')
check(PL.rank_pretty('voice', 189600) == '2 д 4 ч', 'красиво: fmt_duration кога')
check(PL.rank_pretty('balance', 500000) == '500 000 монет', 'красиво: монеты')

print('== 4. CSV ==')
crow = PL.csv_rows(None, '777', 'messages')
check(len(crow) == 8 and crow[0] == (1, '111', 'ID 111', 1850),
      'CSV сообщений: весь список')
crow = PL.csv_rows(None, '777', 'voice')
check(crow[0] == (1, '111', 'Катя', 189600), 'CSV войса: имя из статистики')
check(PL._csv_cell('а;б\nв') == 'а,б в', 'ячейки чистятся')

print('== 5. API и права ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


TB = '/api/guild/777/leaderboards/table'
check(client.get('/leaderboards').status_code in (302, 401, 403),
      'гостю страница закрыта')
check(client.get(TB).status_code in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get(TB).status_code == 403, 'uye не смотрит таблицу')
check(client.get('/api/guild/777/leaderboards/card.png').status_code == 403,
      'uye не смотрит карточку')
login('mod')
page = client.get('/leaderboards')
check(page.status_code == 200 and 'Рейтинги сервера' in page.get_data(as_text=True),
      'mod открывает страницу')
d = client.get(TB + '?cat=voice').get_json()
check(d['success'] and d['table']['rows'][0]['name'] == 'Катя'
      and d['bot_online'] is False, 'таблица войса через API')
d = client.get(TB + '?cat=мусор').get_json()
check(d['cat'] == 'messages', 'API: кламп категории')
d = client.get('/api/guild/999/leaderboards/table').get_json()
check(d['table']['demo'] is True, 'API: демо-пометка пустого сервера')
d = client.get(TB).get_json()
check(len(d['table']['rows']) == 7 and d['table']['rows'][6]['name'] == 'ID 7777',
      'API: семёрка сообщений без демо')
r = client.get('/api/guild/777/leaderboards/card.png?cat=balance')
check(r.status_code == 200 and r.mimetype == 'image/png'
      and r.get_data().startswith(b'\x89PNG'), 'PNG-карточка рисуется офлайн')
r = client.get('/api/guild/777/leaderboards/rank?user=111')
d = r.get_json()
check(d['success'] and d['rows'][0]['pretty'] == '1 850 сообщений'
      and d['rows'][1]['pretty'] == '2 д 4 ч', 'ранг через API с красивыми значениями')
check(client.get('/api/guild/777/leaderboards/rank?user=x').status_code == 400,
      'ранг: битый ID — 400')
check(client.post('/api/guild/777/leaderboards/send',
                  json={'cat': 'messages', 'channel': '1'}).status_code == 403,
      'mod не отправляет карточку')
login('admin')
r = client.post('/api/guild/777/leaderboards/send',
                json={'cat': 'messages', 'channel': 'мусор'})
check(r.status_code == 400 and r.get_json()['error'] == PL.ERR_CHANNEL,
      'отправка: битый канал — 400')
r = client.post('/api/guild/777/leaderboards/send',
                json={'cat': 'voice', 'channel': '123'})
check(r.status_code == 409 and 'Бот офлайн' in r.get_json()['error'],
      'отправка: офлайн — честный 409')
ex = client.get('/api/guild/777/leaderboards/export.csv?cat=messages')
body = ex.get_data(as_text=True)
check(ex.status_code == 200 and ex.headers['Content-Disposition'].endswith(
      'leaderboards_messages_777.csv'), 'имя файла выгрузки')
check(body.startswith('\ufeffrank;uid;name;messages'), 'BOM и шапка сообщений')
lines = body.strip().split('\n')
check(len(lines) == 9 and lines[1] == '1;111;ID 111;1850',
      f'шапка + 8 строк (пришло {len(lines)})')
ex = client.get('/api/guild/777/leaderboards/export.csv?cat=voice')
check(ex.get_data(as_text=True).startswith('\ufeffrank;uid;name;voice_seconds'),
      'шапка войса')
login('uye')
check(client.get('/api/guild/777/leaderboards/export.csv').status_code == 403,
      'uye не выгружает')
login('mod')

print('== 6. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/leaderboards.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
src = open(os.path.join(ROOT, 'web/routes/leaderboards_panel.py'), encoding='utf-8').read()
check(not EMOJI_RE.search(src), 'в модуле нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('lbTabs', 'lbTable', 'lbCard', 'lbDl', 'lbCsv', 'lbRankInp',
            'lbRankGo', 'lbRankRes', 'lbSendCh', 'lbSend'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check("'/table?cat='" in tpl and "'/card.png?cat='" in tpl
      and "'/rank?user='" in tpl and "'/send'" in tpl
      and "'/export.csv?cat='" in tpl, 'API-пути в шаблоне')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
import services.panel_menu as PM
com_pages = [pg['path'] for g in PM.MENU if g['key'] == 'community' for pg in g['pages']]
check('/leaderboards' in com_pages, 'пункт меню «Рейтинги» в «Сообществе»')
check(PM.PAGE_COGS.get('/leaderboards') == ('leaderboard',), 'leaderboard-ког привязан')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('leaderboards_panel') >= 2, 'модуль зарегистрирован в routes_extra')

for _f in (_LB_FILE, _ECO_FILE):
    try:
        os.remove(_f)
    except OSError:
        pass

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
