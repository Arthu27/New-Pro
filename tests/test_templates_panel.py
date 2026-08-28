# -*- coding: utf-8 -*-
"""Шаблоны сервера (идеи #151-155).

Снимок/мета/diff — напрямую через чистые функции кога на фейках;
сохранение-удаление-лимит 10 — текстами команд; применение повторяет
cmd_apply: создаёт только недостающее (роли с правами и reason, каналы с
темой/слоумодом), повторное — «создавать нечего»; офлайн-границы 409;
выгрузки JSON/CSV; права; шаблон; меню.

Запуск: python3 tests/test_templates_panel.py
"""
import asyncio
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
import threading
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='hakumo_templates_test_')
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


import discord  # noqa: E402
from cogs import server_template as ST  # noqa: E402
from db import GuildData  # noqa: E402
from web.routes import templates_panel as TP  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
db = GuildData('server_template')


def mk_role(name, position, managed=False, default=False, color=0, perms=0,
            hoist=True, mentionable=False):
    return SimpleNamespace(
        name=name, color=SimpleNamespace(value=color),
        permissions=SimpleNamespace(value=perms), hoist=hoist,
        mentionable=mentionable, position=position, managed=managed,
        is_default=lambda: default)


def mk_ch(name, type_='text', topic='', slow=0, nsfw=False, pos=0, category=None):
    return SimpleNamespace(name=name, type=type_, topic=topic,
                           slowmode_delay=slow, nsfw=nsfw, position=pos,
                           category=category)


class FakeGuild:
    def __init__(self, gid, name):
        self.id = gid
        self.name = name
        self.roles = [mk_role('everyone', 0, default=True)]
        self.categories = []
        self.text_channels = []
        self.voice_channels = []
        self.made_roles = []
        self.made_cats = []
        self.made_chs = []

    @property
    def channels(self):
        return self.text_channels + self.voice_channels + self.categories

    def _reg(self, ch, is_voice=False):
        (self.voice_channels if is_voice else self.text_channels).append(ch)
        return ch

    async def create_role(self, **kw):
        self.made_roles.append(kw)
        r = SimpleNamespace(name=kw['name'])
        self.roles.append(mk_role(kw['name'], 5))
        return r

    async def create_category(self, name, reason=None):
        self.made_cats.append({'name': name, 'reason': reason})
        c = SimpleNamespace(name=name, channels=[])
        self.categories.append(c)
        return c

    async def create_text_channel(self, name, category=None, topic=None,
                                  slowmode_delay=0, nsfw=False, reason=None):
        self.made_chs.append({'kind': 'text', 'name': name,
                              'category': category, 'topic': topic,
                              'slowmode': slowmode_delay, 'nsfw': nsfw,
                              'reason': reason})
        return self._reg(SimpleNamespace(name=name))

    async def create_voice_channel(self, name, category=None, reason=None):
        self.made_chs.append({'kind': 'voice', 'name': name,
                              'category': category, 'reason': reason})
        return self._reg(SimpleNamespace(name=name), is_voice=True)

    async def create_forum(self, name, category=None, topic=None, reason=None):
        self.made_chs.append({'kind': 'forum', 'name': name,
                              'category': category, 'reason': reason})
        return self._reg(SimpleNamespace(name=name))


loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()


class FakeBot:
    def __init__(self, guilds):
        self.loop = loop
        self.guilds = {g.id: g for g in guilds}

    def get_guild(self, gid):
        return self.guilds.get(int(gid))


# Живой полный сервер — с него снимаем слепки
FULL = FakeGuild(888, 'Hakumo')
FULL.roles += [mk_role('Бот-роль', 9, managed=True),
               mk_role('Модер', 2, color=0x3498DB, perms=8, mentionable=True),
               mk_role('Мирный', 1)]
CAT_MAIN = SimpleNamespace(name='Основное', channels=[])
CH_CHAT = mk_ch('чат', topic='болталка', slow=5, category=CAT_MAIN)
CH_VOICE = mk_ch('войс', 'voice', category=CAT_MAIN)
CAT_MAIN.channels = [CH_CHAT, CH_VOICE]
FULL.categories = [CAT_MAIN]
FULL.text_channels = [CH_CHAT, mk_ch('флуд', pos=2)]
FULL.voice_channels = [CH_VOICE]

# Разряженный сервер — на него применяем (модер и чат уже есть)
SPARSE = FakeGuild(777, 'Тестовый')
SPARSE.roles.append(mk_role('Модер', 2))
SPARSE.text_channels = [mk_ch('чат')]

LIMITED = FakeGuild(999, 'Лимитный')
BOT = FakeBot([FULL, SPARSE, LIMITED])

appmod = importlib.import_module('web.app')
appmod.bot_instance = BOT

# Жёсткая фикстура шаблона для 777
TPL = {'roles': [{'name': 'Модер', 'color': 3447003, 'permissions': 8,
                  'hoist': True, 'mentionable': False, 'position': 2}],
       'categories': [{'name': 'Основное', 'channels': [
           {'name': 'чат', 'type': 'text', 'topic': 'тема', 'slowmode': 5,
            'nsfw': False, 'position': 0},
           {'name': 'войс', 'type': 'voice', 'topic': '', 'slowmode': 0,
            'nsfw': False, 'position': 1}]}],
       'channels': [{'name': 'флуд', 'type': 'text', 'topic': '', 'slowmode': 0,
                     'nsfw': False, 'position': 2}],
       'version': 1}
ENTRY = {'template': TPL, 'description': 'основа',
         'created_at': '2026-08-17T10:00:00+00:00', 'created_by': 'админ',
         'source_guild': 'Hakumo'}
db.set('777', 'templates', {'основа': ENTRY})

print('== 1. Слепок и мета — чистые функции кога ==')
snap = ST.snapshot_guild(FULL)
check([r['name'] for r in snap['roles']] == ['Мирный', 'Модер'],
      'роли без @everyone и ботовских, по позиции')
check(ST.template_meta(snap) == '2 роли · 1 категория · 3 канала',
      'сводка словами кога')
check(snap['categories'][0]['channels'][0]['slowmode'] == 5
      and snap['categories'][0]['channels'][0]['topic'] == 'болталка',
      'каналы со слоумодом и темой')
check(snap['channels'][0]['name'] == 'флуд', 'без категории — отдельно')
other = SimpleNamespace(
    roles=[mk_role('everyone', 0, default=True), mk_role('Модер', 2)],
    categories=[],
    text_channels=[mk_ch('чат')], voice_channels=[mk_ch('войс', 'voice')])
plan = ST.diff_plan(snap, other)
check(plan == {'roles': ['Мирный'], 'categories': ['Основное'],
               'channels': ['флуд']}, 'diff план — только недостающее, имена')

print('== 2. Сохранение/удаление/лимит — потоки команд ==')
check(TP.norm_name('  MAIN  ') == 'main', 'имя: strip+lower+30')
ok, err, _ = TP.save_flow(None, '888', 'x', '', 'тестер')
check(not ok and err == TP.ERR_OFFLINE_SNAP, 'офлайн-снимок — честный отказ')
ok, err, payload = TP.save_flow(BOT, '888', '  Вик ', 'описание-проба', 'тестер')
check(ok and payload['message'] == 'Шаблон «вик» сохранён: 2 роли · 1 категория · 3 канала.',
      'снимок живого сервера — текст команды')
entry = db.get('888', 'templates', {})['вик']
check(entry['created_by'] == 'тестер' and entry['source_guild'] == 'Hakumo'
      and entry['description'] == 'описание-проба' and entry['created_at'],
      'карточка снимка как у команды')
ok, err, _ = TP.save_flow(BOT, '888', '   ', '', 'тестер')
check(not ok and err == 'Имя шаблона пустое.', 'пустое имя — слова команды')
db.set('999', 'templates',
       {f'ш{i}': {'template': {'roles': [], 'categories': [], 'channels': []},
                  'description': '', 'created_at': '', 'created_by': ''}
        for i in range(10)})
ok, err, _ = TP.save_flow(BOT, '999', 'одиннадцатый', '', 'тестер')
check(not ok and err == 'Максимум 10 шаблонов на сервер.', 'лимит 10 — текст команды')
ok, err, _ = TP.save_flow(BOT, '999', 'ш1', '', 'тестер')
check(ok, 'перезапись существующего лимитом не режется')
ok, err, _ = TP.delete_flow('888', 'мусор')
check(not ok and err == 'Шаблон «мусор» не найден.', 'не найден — слова команды')
ok, err, payload = TP.delete_flow('888', 'вик')
check(ok and payload['message'] == 'Шаблон «вик» удалён.'
      and 'вик' not in db.get('888', 'templates', {}), 'удаление — слова команды')

print('== 3. Библиотека и инфо ==')
lv = TP.list_view('777')
check(lv['count'] == 1 and lv['templates'][0]['meta'] == '1 роль · 1 категория · 3 канала',
      'карточка библиотеки с метой кога')
lv = TP.list_view('321')
check(lv['count'] == 0 and lv['empty_text'] == TP.TEXT_NONE_YET, 'пусто — подсказка команды')
ok, err, _ = TP.info_view('777', 'мусор')
check(not ok and err == 'Шаблон «мусор» не найден.', 'инфо: не найден')
ok, err, info = TP.info_view('777', ' ОСНОВА ')
check(ok and info['name'] == 'основа' and info['roles'] == ['Модер'],
      'инфо с нормализацией имени')
check(info['categories'] == [{'name': 'Основное', 'channels': ['чат', 'войс']}]
      and info['channels'] == ['флуд'], 'структура как в /шаблон инфо')
check(info['footer'] == 'Создан: 2026-08-17 · админ', 'подпись инфо')

print('== 4. План и применение ==')
ok, err, _ = TP.plan_view(None, '777', 'основа')
check(not ok and err == TP.ERR_OFFLINE_PLAN, 'план офлайн — отказ')
ok, err, view = TP.plan_view(BOT, '777', 'основа')
check(ok and view['counts'] == {'roles': 0, 'categories': 1, 'channels': 2},
      'план против разряженного: категория + 2 канала')
check(view['plan']['channels'] == ['войс', 'флуд'] and not view['nothing'],
      'что именно создаст')
ok, err, code, payload = TP.apply_flow(None, '777', 'основа')
check(not ok and code == 409 and err == TP.ERR_OFFLINE_APPLY, 'применение офлайн — 409')
ok, err, code, payload = TP.apply_flow(BOT, '777', 'основа')
check(ok and payload['made'] == {'roles': 0, 'categories': 1, 'channels': 2},
      'применение: счётчики как у команды')
check(payload['message'] == ('Шаблон «основа» применён: 0 новых ролей, '
                             '1 категорий, 2 каналов. Существующие не трогал.'),
      'финальный текст команды')
check(SPARSE.made_cats == [{'name': 'Основное', 'reason': 'Шаблон «основа»'}],
      'категория с reason шаблона')
voice_ch = [c for c in SPARSE.made_chs if c['name'] == 'войс'][0]
flood_ch = [c for c in SPARSE.made_chs if c['name'] == 'флуд'][0]
check(voice_ch['kind'] == 'voice' and voice_ch['category'].name == 'Основное',
      'войс-создан под свежей категорией')
check(flood_ch['category'] is None and flood_ch['reason'] == 'Шаблон «основа»',
      'флуд — без категории')
ok, err, code, _ = TP.apply_flow(BOT, '777', 'основа')
check(not ok and code == 400 and err == TP.TEXT_NOTHING,
      'повторное применение — «уже совпадает»')

role_tpl = {'roles': [{'name': 'Хелпер', 'color': 3447003, 'permissions': 8,
                       'hoist': True, 'mentionable': True, 'position': 1}],
            'categories': [], 'channels': [], 'version': 1}
db.set('444', 'templates', {'сролей': {'template': role_tpl, 'description': '',
                                       'created_at': '', 'created_by': 'х'}})
ok, err, code, _p = TP.apply_flow(BOT, '444', 'сролей')
check(not ok and code == 409, 'сервер 444 боту недоступен — отказ 409')
G444 = FakeGuild(444, 'Ролевой')
appmod.bot_instance = FakeBot([G444])
ok, err, code, payload = TP.apply_flow(appmod.bot_instance, '444', 'сролей')
appmod.bot_instance = BOT
mr = G444.made_roles[0]
check(ok and payload['made']['roles'] == 1
      and mr['permissions'].value == 8 and mr['color'].value == 3447003
      and mr['hoist'] is True and mr['mentionable'] is True
      and mr['reason'] == 'Шаблон «сролей»', 'роль создана со всеми атрибутами слепка')

print('== 5. CSV-помощники ==')
check(TP.csv_rows('777') == [('основа', '1 роль · 1 категория · 3 канала',
                              'основа', '2026-08-17T10:00:00+00:00', 'админ')],
      'строка выгрузки')
check(TP._csv_cell('а;б\nв') == 'а,б в', 'ячейки чистятся')

print('== 6. API и права ==')
appmod.bot_instance = None
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


LS = '/api/guild/777/templates/list'
check(client.get('/templates').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get(LS).status_code in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get(LS).status_code == 403, 'uye не смотрит')
login('mod')
page = client.get('/templates')
check(page.status_code == 200 and 'Шаблоны сервера' in page.get_data(as_text=True),
      'mod открывает страницу')
d = client.get(LS).get_json()
check(d['success'] and d['count'] == 1 and d['max'] == 10, 'библиотека через API')
d = client.get('/api/guild/777/templates/info?name=ОСНОВА').get_json()
check(d['success'] and d['info']['footer'] == 'Создан: 2026-08-17 · админ',
      'инфо через API')
check(client.get('/api/guild/777/templates/info?name=мусор').status_code == 404,
      'инфо: 404 для чужого')
r = client.get('/api/guild/777/templates/plan?name=основа')
check(r.status_code == 409, 'план офлайн — 409')
check(client.post('/api/guild/777/templates/save', json={'name': 'x'}).status_code == 403,
      'mod не снимает')
login('admin')
r = client.post('/api/guild/777/templates/save', json={'name': 'x'})
check(r.status_code == 409, 'снимок офлайн — 409')
r = client.post('/api/guild/777/templates/save', json={'name': '   '})
check(r.status_code == 400 and r.get_json()['error'] == 'Имя шаблона пустое.',
      'пустое имя — 400')
r = client.post('/api/guild/777/templates/apply', json={'name': 'основа'})
check(r.status_code == 409, 'применение офлайн — 409')
r = client.get('/api/guild/777/templates/export.json?name=основа')
data = json.loads(r.get_data(as_text=True))
check(r.status_code == 200 and 'template_основа_777.json' in r.headers['Content-Disposition']
      and data['template']['roles'][0]['name'] == 'Модер', 'JSON-выгрузка шаблона')
check(client.get('/api/guild/777/templates/export.json?name=мусор').status_code == 404,
      'JSON чужого — 404')

print('== 7. Живой прогон через API ==')
G555 = FakeGuild(555, 'Живой')
G555.roles.append(mk_role('Модер', 2))
G555.text_channels = [mk_ch('чат')]
db.set('555', 'templates', {'основа': ENTRY})
appmod.bot_instance = FakeBot([FULL, G555])
try:
    d = client.get('/api/guild/555/templates/plan?name=основа').get_json()
    check(d['success'] and d['counts'] == {'roles': 0, 'categories': 1,
                                           'channels': 2}, 'живой план через API')
    r = client.post('/api/guild/555/templates/apply', json={'name': 'основа'})
    d = r.get_json()
    check(r.status_code == 200 and d['made'] == {'roles': 0, 'categories': 1,
                                                 'channels': 2},
          'живое применение через API')
    r = client.post('/api/guild/555/templates/apply', json={'name': 'основа'})
    check(r.status_code == 400 and r.get_json()['error'] == TP.TEXT_NOTHING,
          'повторное — «создавать нечего»')
    r = client.post('/api/guild/555/templates/save',
                    json={'name': 'Живой снимок', 'description': 'с панели'})
    check(r.status_code == 200 and
          r.get_json()['message'].startswith('Шаблон «живой снимок» сохранён:'),
          'живой снимок через API (имя приведено)')
    entry555 = db.get('555', 'templates', {})
    check('живой снимок' in entry555
          and entry555['живой снимок']['created_by'] == 'панель:admin',
          'created_by помечает панель')
    r = client.post('/api/guild/555/templates/delete', json={'name': 'живой снимок'})
    check(r.status_code == 200 and 'живой снимок' not in db.get('555', 'templates', {}),
          'удаление через API')
finally:
    appmod.bot_instance = None
loop.call_soon_threadsafe(loop.stop)

print('== 8. Выгрузки и шаблон/меню ==')
ex = client.get('/api/guild/777/templates/export.csv')
body = ex.get_data(as_text=True)
check(ex.status_code == 200 and
      ex.headers['Content-Disposition'].endswith('templates_777.csv'),
      'CSV: имя файла')
check(body.startswith('\ufeffname;meta;description;created_at;created_by'),
      'CSV: BOM и шапка')
check(body.strip().count('\n') == 1 and 'основа;' in body,
      'CSV: одна строка данных')
login('uye')
check(client.get('/api/guild/777/templates/export.csv').status_code == 403,
      'uye не выгружает')
check(client.get('/api/guild/777/templates/export.json?name=основа').status_code == 403,
      'uye не выгружает JSON')
login('mod')
tpl = open(os.path.join(ROOT, 'web/templates/templates.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
src = open(os.path.join(ROOT, 'web/routes/templates_panel.py'), encoding='utf-8').read()
check(not EMOJI_RE.search(src), 'в модуле нет эмодзи')
base_tpl = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('data-theme="light"' in base_tpl, 'светлая тема учтена (общий shell)')
for fid in ('tpKpis', 'tpSavePanel', 'tpSaveName', 'tpSaveDesc', 'tpSave',
            'tpSaveMsg', 'tpList', 'tpCsv'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check("'/list'" in tpl and "'/info?name='" in tpl and "'/plan?name='" in tpl
      and "'/apply'" in tpl and "'/delete'" in tpl and "'/export.csv'" in tpl
      and "'/export.json?name='" in tpl, 'API-пути в шаблоне')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
import services.panel_menu as PM
bot_pages = [pg['path'] for g in PM.MENU if g['key'] == 'bot' for pg in g['pages']]
check('/templates' in bot_pages, 'пункт меню «Шаблоны» в «Боте»')
check(PM.PAGE_COGS.get('/templates') == ('server_template',),
      'server_template-ког привязан')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('templates_panel') >= 1, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
