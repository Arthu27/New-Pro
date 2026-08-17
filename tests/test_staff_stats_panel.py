# -*- coding: utf-8 -*-
"""Активность персонала (идеи #196-200).

Сборка 1:1 cogs/staff_stats.py: те же collect_actions (mod_data.json +
temp_history.json + варны sqlite namespace 'warnings'), summarize за
период 1..365 (кламп как в команде, дефолт 30) и _breakdown с подписями
ACTION_LABEL кога. Сортировка топа — по total desc как в эмбеде, имена из
кэша гильдии, запасной вариант «ID x» — тот же. Карточка: последние 5
действий тем же отбором. Всё чтение — mod+.

Запуск: python3 tests/test_staff_stats_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_staff_stats_test_')
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


from cogs import staff_stats as SS  # noqa: E402
from db import GuildData  # noqa: E402
from web.routes import staff_stats_panel as SP  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
UTC = timezone.utc
NOW = time.time()


def iso_ago(days=None, seconds=None):
    dt = datetime.now(UTC)
    if days is not None:
        dt -= timedelta(days=days)
    if seconds is not None:
        dt -= timedelta(seconds=seconds)
    return dt.isoformat()


class FakeMember:
    def __init__(self, name, mid):
        self.display_name = name
        self.id = mid
        self.bot = False


class FakeGuild:
    def __init__(self, gid, members=()):
        self.id = gid
        self.members = list(members)

    def get_member(self, uid):
        return next((m for m in self.members if m.id == uid), None)


class FakeBot:
    def __init__(self, guilds):
        self.guilds = list(guilds)

    def get_guild(self, gid):
        return next((g for g in self.guilds if g.id == gid), None)


G777 = FakeGuild(777, [FakeMember('Модера Аня', 11), FakeMember('Модер Боря', 22)])
FB = FakeBot([G777])


def seed_all():
    """Три источника ровно в том виде, что читает collect_actions."""
    with open('data/mod_data.json', 'w', encoding='utf-8') as f:
        json.dump({'cases': {'777': [
            {'mod_id': 11, 'action': 'ban', 'timestamp': iso_ago(days=1)},
            {'mod_id': 11, 'action': 'warn', 'timestamp': iso_ago(days=2)},
            {'mod_id': 22, 'action': 'kick', 'timestamp': iso_ago(days=3)},
            {'mod_id': 22, 'action': 'ban', 'timestamp': iso_ago(days=40)},
            {'mod_id': 33, 'action': 'ban', 'timestamp': None},
        ]}}, f, ensure_ascii=False)
    with open('data/temp_history.json', 'w', encoding='utf-8') as f:
        json.dump([
            {'guild_id': 777, 'mod_id': 11, 'action': 'timeout',
             'ts': NOW - 3600},
            {'guild_id': 777, 'mod_id': 22, 'action': 'vmute',
             'ts': NOW - 2 * 86400},
            {'guild_id': 999, 'mod_id': 11, 'action': 'timeout',
             'ts': NOW - 100},
            {'guild_id': 777, 'action': 'timeout', 'ts': NOW - 60},
        ], f, ensure_ascii=False)
    GuildData('warnings').set(777, '555', [
        {'mod_id': 22, 'timestamp': iso_ago(days=5)}])


print('== 1. Сборка действий кога 1:1 ==')
seed_all()
acts = SS.collect_actions(777)
check(len(acts) == 7, 'все три источника: дела + таймы + варны (7 записей)')
check(('11', 'ban', acts[0][2]) in acts and ('22', 'warn', acts[-1][2]) in acts,
      'mod_id строками, warn из sqlite на месте')
check(all(a[0] != '33' for a in acts), 'запись без метки времени отброшена')
check(sum(1 for a in acts if a == ('11', 'timeout', NOW - 3600)) == 1
      and all(a[2] != NOW - 100 for a in acts)
      and all(a[2] != NOW - 60 for a in acts),
      'чужой сервер (999) и запись без mod_id не попали')
check(sum(1 for a in acts if a[0] == '11') == 3
      and sum(1 for a in acts if a[0] == '22') == 4, 'разброс по модам верный')
check(SS._parse_ts('2026-08-17T10:00:00Z') > 0
      and SS._parse_ts('мусор') == 0.0 and SS._parse_ts(42) == 42.0,
      '_parse_ts: Z-iso, мусор, unix')

print('== 2. Витрина топа 1:1 эмбеду ==')
ok, err, code, p = SP.table_flow(lambda: FB, '777', 30)
check(ok and code == 200 and p['days'] == 30
      and p['grand_total'] == 6 and p['mods_total'] == 2,
      'за 30 дней: 6 действий, 2 мода — сорокалетний бан вне окна')
check([r['mod_id'] for r in p['rows']] == ['11', '22'],
      'сортировка по total desc, порядок как в dict — стабильный')
check(p['rows'][0]['name'] == 'Модера Аня'
      and p['rows'][1]['name'] == 'Модер Боря', 'имена из кэша гильдии')
check(p['rows'][0]['breakdown'] == SS._breakdown(
    {'ban': 1, 'warn': 1, 'timeout': 1}),
      'разбивка первой строки — строкой кога')
check(p['rows'][1]['by'] == {'kick': 1, 'vmute': 1, 'warn': 1},
      'второй мод: кик дела, войс-мьют таймов, варн sqlite')
check(p['sources'] == 'Читаются: mod_data.json, temp_history.json, варны из базы',
      'подпись источников — из пустого эмбеда команды')
check(p['live_names'] is True, 'живой бот помечен')
ok, err, code, p = SP.table_flow(lambda: FB, '777', 365)
check(p['rows'][0]['mod_id'] == '22' and p['rows'][0]['total'] == 4
      and p['grand_total'] == 7, 'за 365 дней сорокодневный бан доехал, лидер сменился')
ok, err, code, p = SP.table_flow(lambda: None, '777', 30)
check(ok and p['live_names'] is False
      and p['rows'][0]['name'] == 'ID 11' and p['grand_total'] == 6,
      'без бота — запасной «ID x» самой команды, данные на месте')
ok, err, code, p = SP.table_flow(lambda: FB, '777', 'много')
check(not ok and code == 400 and err == SP.ERR_DAYS, 'битые дни — 400')
ok, err, code, p = SP.table_flow(lambda: FB, '777', 0)
check(ok and p['days'] == 1, 'ноль дней зажат в один — как в команде')
ok, err, code, p = SP.table_flow(lambda: FB, '777', 9999)
check(ok and p['days'] == 365, 'потолок 365 — как Range команды')
ok, err, code, p = SP.table_flow(lambda: FB, '888', 30)
check(ok and p['rows'] == [] and p['grand_total'] == 0,
      'пустой сервер — пустая витрина, не 404')

print('== 3. Карточка модератора 1:1 ==')
ok, err, code, p = SP.card_flow(lambda: FB, '777', 22, 30)
check(ok and p['name'] == 'Модер Боря' and p['total'] == 3
      and p['breakdown'] == SS._breakdown({'kick': 1, 'vmute': 1, 'warn': 1}),
      'карточка: имя, всего, разбивка коговой строкой')
check([a['action'] for a in p['recent']] == ['vmute', 'kick', 'warn', 'ban'],
      'последние действия — desc по времени, без учёта периода, как в эмбеде')
check(len(p['recent']) == 4
      and p['recent'][0]['label'] == SS.ACTION_LABEL['vmute'],
      'подписи действий — из ACTION_LABEL кога')
check(re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', p['recent'][0]['at'])
      and re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', p['last_at']),
      'даты читаемые')
ok, err, code, p = SP.card_flow(lambda: FB, '777', 99, 30)
check(ok and p['total'] == 0 and p['breakdown'] == '—'
      and p['recent'] == [] and p['last_at'] == '',
      'незнакомый мод — нули и тире, как поля эмбеда')
ok, err, code, p = SP.card_flow(lambda: FB, '777', 'х', 30)
check(not ok and code == 400 and err == SP.ERR_NUMBER, 'битый ID — 400')
ok, err, code, p = SP.card_flow(lambda: None, '777', 11, 30)
check(ok and p['name'] == 'ID 11' and p['total'] == 3,
      'карточка без бота — запасное имя')

print('== 4. API и права ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


seed_all()
check(client.get('/staff-stats').status_code in (302, 401, 403),
      'гостю страница закрыта')
check(client.get('/api/guild/777/staff-stats/table').status_code
      in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get('/staff-stats').status_code == 403, 'uye не смотрит')
login('mod')
page = client.get('/staff-stats')
check(page.status_code == 200
      and 'Активность персонала' in page.get_data(as_text=True),
      'mod открывает страницу — как moderate_members у команды')
appmod.bot_instance = FB
try:
    d = client.get('/api/guild/777/staff-stats/table').get_json()
    check(d['success'] and d['days'] == 30 and d['grand_total'] == 6,
          'дефолтный период 30 — как параметр команды')
    d = client.get('/api/guild/777/staff-stats/table?days=90').get_json()
    check(d['days'] == 90 and d['grand_total'] == 7
          and d['rows'][0]['mod_id'] == '22',
          'период из адресной строки — сорокодневный бан влез, лидер сменился')
    r = client.get('/api/guild/777/staff-stats/table?days=abc')
    check(r.status_code == 400 and r.get_json()['error'] == SP.ERR_DAYS,
          'битые дни — 400 через API')
    r = client.post('/api/guild/777/staff-stats/card',
                    json={'user_id': '11'})
    check(r.status_code == 200 and r.get_json()['total'] == 3,
          'карточка через API')
    r = client.get('/api/guild/777/staff-stats/export.csv')
    body = r.get_data(as_text=True)
    check(r.headers['Content-Disposition']
          .endswith('staff_stats_777.csv'), 'CSV: имя файла')
    check(body.startswith('\ufeffmod_id;name;total;last_at;breakdown'),
          'CSV: BOM + шапка')
    lines = body.strip().split('\n')
    check(len(lines) == 3 and lines[1].startswith('11;Модера Аня;3;')
          and lines[2].startswith('22;Модер Боря;3;'),
          'CSV: две строки модов в топ-порядке')
    appmod.bot_instance = None
    d = client.get('/api/guild/777/staff-stats/table').get_json()
    check(d['success'] and d['live_names'] is False
          and d['rows'][0]['name'] == 'ID 11',
          'без бота таблица работает — 200 с «ID x»')
finally:
    appmod.bot_instance = None

print('== 5. Шаблон, ког, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/staff_stats.html'),
           encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
src = open(os.path.join(ROOT, 'web/routes/staff_stats_panel.py'),
           encoding='utf-8').read()
check(not EMOJI_RE.search(src), 'в модуле панели нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
for fid in ('ssDays', 'ssReload', 'ssCsv', 'ssMsg', 'ssSources', 'ssGrand',
            'ssMods', 'ssBox', 'ssCardUid', 'ssCardGo', 'ssCardMsg',
            'ssCardRes'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
for days_mark in ('data-days="7"', 'data-days="30"', 'data-days="90"',
                  'data-days="365"'):
    check(days_mark in tpl, f'кнопка {days_mark} на месте')
for path in ("'/table?days='", "'/card'", "'/export.csv?days='"):
    check(path in tpl, f'путь {path} в шаблоне')
check(hasattr(SS, 'StaffStats') and callable(SS.setup), 'ког staff_stats цел')
check(SP.SS is SS, 'панель зовёт сам модуль кога, не копию')
import services.panel_menu as PM
comm_pages = [pg['path'] for g in PM.MENU if g['key'] == 'community'
              for pg in g['pages']]
check('/staff-stats' in comm_pages,
      'пункт меню «Активность персонала» в «Сообществе»')
check(PM.PAGE_COGS.get('/staff-stats') == ('staff_stats',), 'ког привязан')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('staff_stats_panel') >= 1,
      'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
