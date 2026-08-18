# -*- coding: utf-8 -*-
"""Поиск по серверу (идеи #181-185).

Выражения 1:1 cogs/search_cog: подстрока без регистра по display_name /
имени роли / имени канала, первые десять в выдаче, полное число в счётчике,
боты не фильтруются (команда их оставляет). Тексты пустых секций словами
команд без эмодзи. Регистр запроса, потолок TOP=10, offline 409, CSV.
Заглушечная «!search» панелью честно заменена единым запросом по трём видам.

Запуск: python3 tests/test_search_panel.py
"""
import importlib
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_search_test_')
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


from web.routes import search_panel as SP  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')


class FakeMember:
    def __init__(self, name, mid, bot=False):
        self.display_name = name
        self.id = mid
        self.bot = bot


class FakeRole:
    def __init__(self, name, rid, members=None):
        self.name = name
        self.id = rid
        self.members = members or []


class FakeChannel:
    def __init__(self, name, cid):
        self.name = name
        self.id = cid


class FakeGuild:
    def __init__(self, gid, members=(), roles=(), channels=()):
        self.id = gid
        self.members = list(members)
        self.roles = list(roles)
        self.channels = list(channels)


class FakeBot:
    def __init__(self, guilds):
        self.guilds = list(guilds)

    def get_guild(self, gid):
        return next((g for g in self.guilds if g.id == gid), None)


G777 = FakeGuild(777,
                 members=[FakeMember('Анна', 101), FakeMember('антон', 102),
                          FakeMember('SearchBot', 103, bot=True),
                          FakeMember('борис', 104)],
                 roles=[FakeRole('Моды', 201, [FakeMember('x', 1),
                                               FakeMember('y', 2)]),
                        FakeRole('Админ', 202, [FakeMember('x', 1)]),
                        FakeRole('muted', 203)],
                 channels=[FakeChannel('general', 301),
                           FakeChannel('memes', 302),
                           FakeChannel('archive-news', 303)])
G555 = FakeGuild(555,
                 roles=[FakeRole(f'рейд-{i}', 400 + i) for i in range(12)])
FB = FakeBot([G777, G555])

print('== 1. Выражения команд 1:1 ==')
ok, err, code, p = SP.search_flow(lambda: FB, '777', 'ан')
check(ok and code == 200, 'запрос прошёл')
check(p['members']['total'] == 2
      and [m['name'] for m in p['members']['items']] == ['Анна', 'антон'],
      '«ан» нашёл Анну и антона (регистр имени не важен)')
check(p['roles']['total'] == 0 and p['roles']['note'] == 'Роль не найдена!',
      'ролей нет — словами !searchrole')
check(p['channels']['total'] == 0
      and p['channels']['note'] == 'Канал не найден!', 'каналов нет — словами команды')
ok, err, code, p = SP.search_flow(lambda: FB, '777', 'SEARCH')
check(ok and p['members']['total'] == 1
      and p['members']['items'][0]['name'] == 'SearchBot',
      'регистр запроса не важен; бот в выдаче — как в команде')
ok, err, code, p = SP.search_flow(lambda: FB, '777', 'м')
check(ok and [r['name'] for r in p['roles']['items']] == ['Моды', 'Админ'],
      'кириллическая «м» не матчит латинский muted')
check([r['members'] for r in p['roles']['items']] == [2, 1],
      'счётчики участников ролей — как в value эмбеда')
ok, err, code, p = SP.search_flow(lambda: FB, '777', 'mem')
check(ok and p['channels']['total'] == 1
      and p['channels']['items'][0] == {'name': 'memes', 'id': '302'},
      'канал memes нашёлся')

print('== 2. Потолок выдачи и полный счётчик ==')
ok, err, code, p = SP.search_flow(lambda: FB, '555', 'рейд')
check(ok and p['roles']['total'] == 12 and len(p['roles']['items']) == 10,
      '«Найдено: 12», показаны первые 10 — как эмбед команды')
check(p['members']['note'] == 'Участник не найден!',
      'пустая секция участников — словами !searchuser')

print('== 3. Ошибки и offline ==')
ok, err, code, p = SP.search_flow(lambda: FB, '777', '   ')
check(not ok and code == 400 and err == SP.ERR_QUERY, 'пробелы — 400')
ok, err, code, p = SP.search_flow(lambda: None, '777', 'ан')
check(not ok and code == 409 and err == 'Бот не работает', 'без бота — 409')
ok, err, code, p = SP.search_flow(lambda: FB, '999', 'ан')
check(not ok and code == 404 and err == SP.ERR_GUILD, 'чужой сервер — 404')

print('== 4. CSV ==')
ok, err, code, p = SP.search_flow(lambda: FB, '777', 'м')
rows = SP.csv_rows(p)
check(rows == [('role', '201', 'Моды', 2), ('role', '202', 'Админ', 1)],
      'строки ролей с числом участников')
ok, err, code, p = SP.search_flow(lambda: FB, '777', 'ан')
check(SP.csv_rows(p) == [('user', '101', 'Анна', ''),
                         ('user', '102', 'антон', '')],
      'строки участников в порядке выдачи')
check(SP._csv_cell('а;б\nв') == 'а,б в', 'ячейки чистятся')

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


Q = '/api/guild/777/search/query?q=ан'
check(client.get('/search').status_code in (302, 401, 403),
      'гостю страница закрыта')
check(client.get(Q).status_code in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get(Q).status_code == 403, 'uye не ищет')
login('mod')
page = client.get('/search')
check(page.status_code == 200
      and 'Поиск по серверу' in page.get_data(as_text=True),
      'mod открывает страницу')
appmod.bot_instance = FB
try:
    d = client.get(Q).get_json()
    check(d['success'] and d['members']['total'] == 2
          and d['channels']['note'] == 'Канал не найден!',
          'поиск через API')
    r = client.get('/api/guild/777/search/query')
    check(r.status_code == 400 and r.get_json()['error'] == SP.ERR_QUERY,
          'без q — 400')
    ex = client.get('/api/guild/777/search/export.csv?q=ан')
    body = ex.get_data(as_text=True)
    check(ex.status_code == 200 and ex.headers['Content-Disposition']
          .endswith('search_777.csv'), 'CSV: имя файла')
    check(body.startswith('\ufeffkind;id;name;extra')
          and len(body.strip().split('\n')) == 3, 'CSV: шапка + 2 участника')
    appmod.bot_instance = None
    r = client.get(Q)
    check(r.status_code == 409
          and r.get_json()['error'] == 'Бот не работает', 'offline — 409 через API')
finally:
    appmod.bot_instance = None

print('== 6. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/search.html'),
           encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
src = open(os.path.join(ROOT, 'web/routes/search_panel.py'),
           encoding='utf-8').read()
check(not EMOJI_RE.search(src), 'в модуле нет эмодзи')
base_tpl = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('data-theme="light"' in base_tpl, 'светлая тема учтена (общий shell)')
for fid in ('srQuery', 'srGo', 'srCsv', 'srMsg', 'srResults', 'srMembers',
            'srRoles', 'srChannels', 'srCntM', 'srCntR', 'srCntC'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
for path in ("'/query?q='", "'/export.csv?q='"):
    check(path in tpl, f'путь {path} в шаблоне')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
import services.panel_menu as PM
util_pages = [pg['path'] for g in PM.MENU if g['key'] == 'utility'
              for pg in g['pages']]
check('/search' in util_pages, 'пункт меню «Поиск по серверу» в «Утилитах»')
check(PM.PAGE_COGS.get('/search') == ('search_cog',), 'ког привязан')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('search_panel') >= 1, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
