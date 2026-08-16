# -*- coding: utf-8 -*-
"""Рекап канала (идеи #111-115).

Валидация периода 1..720 текстом команды; оба окна через build_recap кога
(предыдущему — честный срез [N-2H, N-H), боты и старьё отсечены его же
кодом); поля эмбеда его recap_embed_fields; дельты окон; CSV; права;
живой прогон через фейк-бота с настоящим event loop: build, send, export.

Запуск: python3 tests/test_recap_panel.py
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
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='aether_recap_test_')
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


from cogs import recap as RC  # noqa: E402
from web.routes import recap_panel as RP  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
UTC = timezone.utc
NOW = datetime.now(UTC)

print('== 1. Период — правило кога ==')
check(RP.HOURS_RULE_TEXT == 'Период — от 1 до 720 часов (30 дней).',
      'текст правила 1:1 с командой')
for raw in (0, -1, 721, 'мусор', None, ''):
    ok, err, _h = RP.validate_hours(raw)
    check(not ok and err == RP.HOURS_RULE_TEXT, f'отказ для {raw!r}')
ok, err, h = RP.validate_hours('24')
check(ok and h == 24, '24 принято')
ok, err, h = RP.validate_hours(720)
check(ok and h == 720, 'граница 720 принята')

print('== 2. Оба окна через build_recap кога ==')
pool = [
    {'author': 'Катя', 'content': 'раз два три',
     'created_at': NOW - timedelta(hours=2), 'reactions': [{'count': 2}]},
    {'author': 'Иван', 'content': 'четыре пять',
     'created_at': NOW - timedelta(hours=3), 'reactions': []},
    {'author': 'Катя', 'content': 'старое окно',
     'created_at': NOW - timedelta(hours=26), 'reactions': []},
    {'author': 'Бот', 'content': 'спам ссылка',
     'created_at': NOW - timedelta(hours=1), 'bot': True, 'reactions': []},
    {'author': 'Иван', 'content': 'совсем старое',
     'created_at': NOW - timedelta(hours=50), 'reactions': []},
]
pack = RP.pack_recap(pool, 24, NOW)
cur, prev, cmp = pack['cur'], pack['prev'], pack['compare']
check(cur['total'] == 2 and cur['unique_authors'] == 2,
      f"текущее: 2 сообщения, 2 автора (боты и старьё отсечены — {cur['total']})")
check(prev['total'] == 1 and prev['unique_authors'] == 1,
      'предыдущему — честный срез [N-2H, N-H): одно «старое окно»')
check(pack['scanned'] == 5, 'пул общий, scanned — весь пул')
check(cmp == {'cur_total': 2, 'prev_total': 1, 'delta_total': 1,
              'cur_authors': 2, 'prev_authors': 1, 'delta_authors': 1},
      f'дельты окон: {cmp}')
empty_pack = RP.pack_recap([], 24, NOW)
check(empty_pack['cur']['total'] == 0 and empty_pack['compare']['delta_total'] == 0,
      'пустой пул — нули')

print('== 3. Эмбед-предпросмотр 1:1 ==')
spec = RP.embed_spec('general', cur, 24)
check(spec['title'] == 'Рекап #general · 24 часа', 'заголовок как у команды')
check(spec['description'] == '' and len(spec['fields']) == 7,
      '7 полей заполненного рекапа')
fnames = [f['name'] for f in spec['fields']]
check(fnames == ['Сообщений', 'Участников', 'Активные авторы', 'Слова периода',
                 'Пик активности', 'Самая заметная реплика', 'Ссылок скинуто'],
      'имена и порядок полей — как в коге')
fmap = dict((f['name'], f['value']) for f in spec['fields'])
check(fmap['Сообщений'] == '**2** за 24 часа (среднее 0.1/час)',
      'строка сообщений со средним темпом')
check(fmap['Активные авторы'] == '**Катя** (1) · **Иван** (1)',
      'авторы со счётчиками')
check(fmap['Самая заметная реплика'] == '**Катя**: раз два три (2 реакции)',
      'самая заметная — по реакциям кога')
inl = {f['name']: f['inline'] for f in spec['fields']}
check(inl['Сообщений'] and inl['Участников'] and inl['Пик активности']
      and not inl['Активные авторы'], 'inline-флаги как в команде')
quiet = RP.embed_spec('general', empty_pack['cur'], 24)
check(quiet['description'] == 'За период тихо — сообщений не было.'
      and quiet['fields'] == [], 'тихое окно — его подпись')

print('== 4. Поиск канала и CSV ==')
g = SimpleNamespace(get_channel=lambda cid: SimpleNamespace(
    id=cid, name='x', history=True) if cid == 5 else None)
check(RP.find_channel(g, '5') is not None, 'канал по ID найден')
check(RP.find_channel(g, '6') is None and RP.find_channel(g, 'мусор') is None,
      'чужой/битый ID -> None')
no_hist = SimpleNamespace(get_channel=lambda cid: SimpleNamespace(id=cid))
check(RP.find_channel(no_hist, '5') is None, 'без history -> None')
rows = RP.recap_csv_rows('general', pack, 24)
check(rows[0] == ('Канал', '#general') and rows[1] == ('Период (часов)', '24'),
      'шапка контекста')
check(('Сообщений', '2 за 24 часа (среднее 0.1/час)') in rows,
      'поле эмбеда без markdown-звёзд')
check(('Сравнение: сообщений окном раньше', '1') in rows
      and ('Сравнение: разница', '+1') in rows, 'сравнение окон в выгрузке')
check(RP._csv_cell('а;б\nв') == 'а,б в', 'ячейки чистятся')

print('== 5. API и права (офлайн) ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


BD = '/api/guild/777/recap/build'
check(client.get('/recap').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.post(BD, json={}).status_code in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get('/recap').status_code == 403, 'uye не видит страницу')
check(client.post(BD, json={}).status_code == 403, 'uye не собирает')
login('mod')
page = client.get('/recap')
check(page.status_code == 200 and 'Рекап канала' in page.get_data(as_text=True),
      'mod открывает страницу')
r = client.post(BD, json={'channel_id': '1', 'hours': 9999})
check(r.status_code == 400 and r.get_json()['error'] == RP.HOURS_RULE_TEXT,
      'мусорный период — 400 с текстом команды')
r = client.post(BD, json={'channel_id': '1', 'hours': 24})
check(r.status_code == 409 and 'Бот офлайн' in r.get_json()['error'],
      'офлайн — честный 409')
check(client.post('/api/guild/777/recap/send',
                  json={'channel_id': '1', 'hours': 24}).status_code == 403,
      'mod не отправляет')
login('admin')
r = client.post('/api/guild/777/recap/send', json={'channel_id': '1', 'hours': 24})
check(r.status_code == 409, 'отправка офлайн — 409')
check(client.get('/api/guild/777/recap/export.csv?channel=1&hours=24').status_code == 409,
      'CSV офлайн — 409')
check(client.get('/api/guild/777/recap/export.csv?channel=1').status_code == 400,
      'CSV без периода — 400 с правилом')

print('== 6. Живой прогон (фейк-бот, настоящий loop) ==')
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()


class FakeAuthor:
    def __init__(self, name):
        self.name = name
        self.bot = False
        self.id = abs(hash(name)) % 100000

    def __str__(self):
        return self.name


LIVE_MSGS = [
    SimpleNamespace(created_at=datetime.now(UTC) - timedelta(minutes=50),
                    author=FakeAuthor('Катя'), content='привет как дела',
                    reactions=[]),
    SimpleNamespace(created_at=datetime.now(UTC) - timedelta(minutes=40),
                    author=FakeAuthor('Иван'), content='всё хорошо го играть',
                    reactions=[]),
    SimpleNamespace(created_at=datetime.now(UTC) - timedelta(minutes=30),
                    author=FakeAuthor('Катя'), content='го го',
                    reactions=[]),
]


class FakeChannel:
    def __init__(self):
        self.id = 555
        self.name = 'general'
        self.sent = []
        self.last_limit = None
        self.last_after = None

    async def history(self, limit=None, after=None, oldest_first=None):
        self.last_limit = limit
        self.last_after = after
        for m in LIVE_MSGS:
            yield m

    async def send(self, embed=None):
        self.sent.append(embed)


CH = FakeChannel()


class FakeBot:
    def __init__(self):
        self.loop = loop

    def get_guild(self, gid):
        return SimpleNamespace(id=int(gid),
                               get_channel=lambda cid: CH if cid == 555 else None)


appmod.bot_instance = FakeBot()
try:
    r = client.post(BD, json={'channel_id': '555', 'hours': 24})
    d = r.get_json()
    check(r.status_code == 200 and d['success'], 'живой build собрался')
    check(CH.last_limit == RP.HISTORY_LIMIT, 'выборка с лимитом команды (1000)')
    check(d['channel'] == {'id': '555', 'name': 'general'} and d['hours'] == 24
          and d['scanned'] == 3 and not d['quiet'], 'конверт ответа build')
    check(d['recap']['total'] == 3 and d['recap']['unique_authors'] == 2,
          'живые счётчики (str(author) — его правило имён)')
    check(d['recap']['top_authors'][0] == ['Катя', 2]
          and d['recap']['top_words'][0] == ['привет', 1],
          'живые топы: Катя x2; «го» короче 3 букв — его фильтр слов')
    check(d['embed']['title'] == 'Рекап #general · 24 часа'
          and len(d['embed']['fields']) == 7, 'живой эмбед-спек')
    r = client.post('/api/guild/777/recap/send',
                    json={'channel_id': '555', 'hours': 24})
    check(r.status_code == 200 and r.get_json()['success'], 'отправка подтверждена')
    check(len(CH.sent) == 1 and CH.sent[0].title == 'Рекап #general · 24 часа'
          and CH.sent[0].color.value == RC.COLOR,
          'в канал ушёл эмбед того же вида и цвета')
    r = client.get('/api/guild/777/recap/export.csv?channel=555&hours=24')
    body = r.get_data(as_text=True)
    check(r.status_code == 200 and
          r.headers['Content-Disposition'].endswith('recap_555_777.csv'),
          'CSV: имя файла')
    check(body.startswith('\ufeffПоказатель;Значение'), 'CSV: BOM и шапка')
    check('Сообщений;3 за 24 часа (среднее 0.1/час)' in body
          and 'Активные авторы;Катя (2) · Иван (1)' in body
          and 'Сравнение: разница;+3' in body,
          'CSV: поля без звёзд + дельта')
finally:
    appmod.bot_instance = None
    loop.call_soon_threadsafe(loop.stop)

print('== 7. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/recap.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
src = open(os.path.join(ROOT, 'web/routes/recap_panel.py'), encoding='utf-8').read()
check(not EMOJI_RE.search(src), 'в модуле нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('rcChan', 'rcHours', 'rcGo', 'rcSend', 'rcCsv', 'rcErr',
            'rcBody', 'rcKpis', 'rcEmbed', 'rcCmp', 'rcTops'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check("'/build'" in tpl and "'/send'" in tpl and "'/export.csv?channel='" in tpl,
      'API-пути в шаблоне')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
import services.panel_menu as PM
main_pages = [pg['path'] for g in PM.MENU if g['key'] == 'main' for pg in g['pages']]
check('/recap' in main_pages, 'пункт меню «Рекап канала» в «Основном»')
check(PM.PAGE_COGS.get('/recap') == ('recap',), 'recap-ког привязан')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('recap_panel') >= 2, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
