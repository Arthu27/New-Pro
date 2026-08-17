# -*- coding: utf-8 -*-
"""Панель «Топ сервера» (идеи #81-85).

Агрегации и строки 1:1 с _get_lb_data кога: сообщения (int, «1 500
СООБЩЕНИЙ»), войс (voice_view, «Hч Mм В ВОЙСЕ», имя из записи), монеты
(balance+bank, «1 500 МОНЕТ»); битая категория валится целиком — как у
кога; имена member→аудит→«ID xxx»; сводка, свежесть файлов, CSV с BOM;
права mod+, мутаций нет.

Запуск: python3 tests/test_tops_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime

_TMP = tempfile.mkdtemp(prefix='aether_tops_test_')
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


from web.routes import tops_panel as TP  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')


def seed_lb():
    return {'messages': {'7': 1500, '12': 900, '9': 1_000_000}}


def seed_econ():
    return {'7': {'balance': 1000, 'bank': 500},
            '12': {'balance': 100},
            'junk': [1, 2],
            '55': {'balance': 200}}


def seed_voice():
    return {'5': {'name': 'Витёк', 'total_seconds': 5400},
            '6': {'name': '', 'total_seconds': 1800},
            '8': 3660}


print('== 1. Агрегации 1:1 с карточкой кога ==')
rows, st = TP.messages_rows(seed_lb()['messages'])
check([r['user_id'] for r in rows] == ['9', '7', '12'] and st == 'ok',
      'порядок по числу сообщений')
check(rows[0]['display'] == '1 000 000 СООБЩЕНИЙ'
      and rows[1]['display'] == '1 500 СООБЩЕНИЙ',
      'запятые → пробелы, подпись кога')
check(rows[0]['name'] == 'ID 9', 'без резолвера — fallback кога (uid[:6])')
check([r['rank'] for r in rows] == [1, 2, 3], 'ранги проставлены')
rows, st = TP.messages_rows({'7': 1500}, resolve=lambda uid: 'Глеб')
check(rows[0]['name'] == 'Глеб', 'имя через резолвер')
rows, st = TP.messages_rows({'7': 'много'})
check(rows == [] and st == 'error', 'битое значение валит категорию — как у кога')
check(TP.messages_rows({}) == ([], 'empty'), 'пусто — empty')

rows, st = TP.voice_rows(seed_voice())
check([r['user_id'] for r in rows] == ['5', '8', '6'],
      'войс по секундам (легаси-int тоже)')
check(rows[0]['display'] == '1ч 30м В ВОЙСЕ'
      and rows[0]['name'] == 'Витёк', 'часы+минуты, имя из записи')
check(rows[2]['display'] == '30м В ВОЙСЕ' and rows[2]['name'] == 'ID 6',
      'до часа без «0ч», пустое имя — fallback')
check(rows[1]['display'] == '1ч 1м В ВОЙСЕ', 'легаси 3660 сек — 1ч 1м')
check(TP.voice_rows({'5': 'мусор'})[1] == 'error', 'битый войс — error')

rows, st = TP.balance_rows(seed_econ())
check([r['user_id'] for r in rows] == ['7', '55', '12'],
      'монеты: balance+bank, не-словарь пропущен')
check(rows[0]['display'] == '1 500 МОНЕТ' and rows[0]['value'] == 1500,
      'суммарный баланс, подпись кога')
check(TP.balance_rows({'7': {'balance': 'много'}})[1] == 'error',
      'битый баланс — error')
many = {str(i): i for i in range(1, 40)}
check(len(TP.messages_rows(many)[0]) == 25, 'глубина панели — 25 (карточка — 7)')

print('== 2. Сводка и свежесть ==')
summ = TP.board_summary(seed_lb()['messages'], seed_voice(), seed_econ())
check(summ['messages_total'] == 1_002_400, 'всего сообщений: 1500+900+1 000 000')
check(summ['voice_seconds_total'] == 5400 + 1800 + 3660, 'секунды войса с легаси')
check(summ['coins_total'] == 1000 + 500 + 100 + 200, 'монеты баланс+банк')
check(summ['people_balance'] == 3, 'не-словарь не человек')
check(TP.board_summary(None, None, None)['messages_total'] == 0, 'нули без падения')
junk = {'1': {'balance': 'много', 'bank': 10}, '2': {'balance': 5}}
check(TP.board_summary(junk, {}, junk)['coins_total'] == 15,
      'мусорные поля аккуратно пропущены')

now = datetime.now()
fresh = os.path.join('data', 'leaderboard_66.json')
with open(fresh, 'w') as fh:
    json.dump({}, fh)
stale = os.path.join('data', 'economy_66.json')
with open(stale, 'w') as fh:
    json.dump({}, fh)
os.utime(stale, (time.time() - 5 * 86400,) * 2)
fr = TP.source_freshness(66, now=now)
check(fr['messages'] == {'state': 'fresh', 'age_days': 0}, 'свежий файл')
check(fr['balance']['state'] == 'stale'
      and fr['balance']['age_days'] in (4, 5),
      'пятидневный — устарел (дни дробятся на границе секунд)')
check(fr['voice'] == {'state': 'live', 'age_days': 0}, 'войс — живой SQLite')
fr = TP.source_freshness(999, now=now)
check(fr['messages']['state'] == 'missing', 'нет файла — честно')

print('== 3. API: права и потоки ==')
with open('data/leaderboard_777.json', 'w', encoding='utf-8') as fh:
    json.dump(seed_lb(), fh)
with open('data/economy_777.json', 'w', encoding='utf-8') as fh:
    json.dump(seed_econ(), fh)
from db import GuildData  # noqa: E402
GuildData('voice_stats').set(777, '5',
                             {'name': 'Витёк', 'total_seconds': 5400, 'daily': {}})
GuildData('voice_stats').set(777, '6',
                             {'name': '', 'total_seconds': 1800, 'daily': {}})
with open('data/audit_log.json', 'w', encoding='utf-8') as fh:
    json.dump({'777': [
        {'category': 'mod', 'action': 'Мут', 'user_id': '12', 'user_name': 'Олег',
         'timestamp': now.isoformat()},
    ]}, fh)

appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


class _FakeMember:
    def __init__(self, name):
        self.display_name = name


class _FakeGuild:
    id = 777
    name = 'Тестхейм'

    def get_member(self, uid):
        return _FakeMember('Глеб') if uid == 7 else None


class _FakeBot:
    guilds = [_FakeGuild()]

    def get_guild(self, gid):
        return self.guilds[0] if gid == 777 else None


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


OV = '/api/guild/777/tops/overview'
check(client.get('/tops').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get(OV).status_code in (302, 401, 403), 'гостю снимок закрыт')
login('uye')
check(client.get(OV).status_code == 403, 'uye нельзя')
login('mod')
page = client.get('/tops')
check(page.status_code == 200 and 'Топ сервера' in page.get_data(as_text=True),
      'mod открывает страницу')
check("var GID = '777'" in page.get_data(as_text=True), 'активный сервер в странице')

appmod.set_bot_instance(_FakeBot())
ov = client.get(OV).get_json()
check(ov['success'] and ov['category'] == 'messages', 'категория по умолчанию')
by_uid = {r['user_id']: r for r in ov['rows']}
check(by_uid['7']['name'] == 'Глеб' and by_uid['12']['name'] == 'Олег'
      and by_uid['9']['name'] == 'ID 9',
      'member → аудит → fallback, как у кога')
check(ov['summary']['messages_total'] == 1_002_400, 'сводка в снимке')
check(ov['freshness']['voice']['state'] == 'live', 'свежесть источников')
r = client.get(OV + '?category=zzz')
check(r.status_code == 400 and r.get_json()['error'] == 'Нет такой категории',
      'левая категория — 400')
ov = client.get(OV + '?category=voice').get_json()
check(ov['rows'][0]['name'] == 'Витёк' and ov['rows'][1]['name'] == '6',
      'войс с именами записей (пустое имя voice_view сам подменяет на uid)')
ov = client.get(OV + '?category=balance').get_json()
check(ov['rows'][0]['display'] == '1 500 МОНЕТ' and ov['rows'][0]['name'] == 'Глеб',
      'баланс: лидер с живым именем')

csv_r = client.get('/api/guild/777/tops/messages.csv')
body = csv_r.get_data(as_text=True)
check(csv_r.status_code == 200
      and 'tops_messages_777.csv' in csv_r.headers.get('Content-Disposition', ''),
      'CSV с именем категории и сервера')
check(body.startswith('\ufeffrank;user_id;name;display;value'), 'BOM + шапка')
check('1;9;ID 9;1 000 000 СООБЩЕНИЙ;1000000' in body, 'лидер первой строкой')
r = client.get('/api/guild/777/tops/zzz.csv')
check(r.status_code == 404 and r.get_json()['error'] == 'Нет такой категории',
      'CSV левой категории — 404')

print('== 4. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/tops.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('tpKpis', 'tpTabs', 'tpRows', 'tpCsv', 'tpState', 'tpFresh'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check('/overview?category=' in tpl and '.csv' in tpl,
      'API-пути в шаблоне')
import services.panel_menu as PM
com_pages = [pg['path'] for g in PM.MENU if g['key'] == 'community' for pg in g['pages']]
check('/tops' in com_pages, 'пункт «Топ сервера» в группе «Сообщество»')
check(PM.PAGE_COGS.get('/tops') == ('leaderboard',),
      'leaderboard-ког привязан к странице')
check(PM.PAGE_COGS.get('/join-to-create') == ('join_to_create',),
      'J2C-привязка прошлой пачки цела')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('tops_panel') >= 1, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
