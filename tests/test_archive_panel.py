# -*- coding: utf-8 -*-
"""Архиватор каналов (идеи #171-175).

HTML 1:1 — тот самый generate_html кога (escape контента, картинки <img>,
файлы ссылками), имя файла шаблоном /archive (archive_<канал>_<UTC>). TXT
1:1 построчно /backup-channel + его имя файла; попутные фиксы кога
(«Всего сообщений», alt вместо «низ», «сообщений скопировано.») закреплены.
Лимиты: мусор → дефолт команды, кламп 1..2000. Превью и счётчики — на тех
же сообщениях; offline — честный 409 «Бот не работает». Live-фетч гоняется
через настоящий asyncio loop в потоке, как в боте.

Запуск: python3 tests/test_archive_panel.py
"""
import asyncio
import importlib
import os
import re
import shutil
import sys
import tempfile
import threading
from datetime import datetime, timedelta

_TMP = tempfile.mkdtemp(prefix='aether_archive_test_')
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


from web.routes import archive_panel as AP  # noqa: E402
from cogs.archive import Archive  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')

T0 = datetime(2026, 8, 10, 12, 0, 0)


class FakeAuthor:
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name


class FakeAtt:
    def __init__(self, content_type, filename):
        self.content_type = content_type
        self.filename = filename
        self.url = f'https://cdn.example/{filename}'


class FakeMsg:
    def __init__(self, author, content, atts, ts):
        self.author = FakeAuthor(author)
        self.content = content
        self.attachments = atts
        self.created_at = ts


class FakeChannel:
    def __init__(self, cid, name, msgs):
        self.id, self.name, self._msgs = cid, name, msgs

    def history(self, limit=None, oldest_first=False):
        msgs = list(self._msgs if oldest_first else reversed(self._msgs))
        if limit is not None:
            msgs = msgs[:limit]

        async def gen():
            for m in msgs:
                yield m
        return gen()


MSGS = [
    FakeMsg('Вася', 'Первое <i>сообщение</i>', [], T0),
    FakeMsg('Петя', 'Смотри сюда', [FakeAtt('image/png', 'cat.png')],
            T0 + timedelta(minutes=1)),
    FakeMsg('Вася', 'и файл с; точкой', [FakeAtt('text/plain', 'n.txt')],
            T0 + timedelta(minutes=2)),
]
CH_GENERAL = FakeChannel(501, 'general', MSGS)
CH_RANDOM = FakeChannel(502, 'random',
                        [FakeMsg('Петя', 'rr', [], T0 + timedelta(minutes=3))])


class FakeGuild:
    def __init__(self, gid, channels):
        self.id = gid
        self.text_channels = channels


class FakeBot:
    def __init__(self, guilds):
        self.guilds = guilds
        self.loop = LOOP

    def get_guild(self, gid):
        return next((g for g in self.guilds if g.id == gid), None)


LOOP = asyncio.new_event_loop()
threading.Thread(target=lambda: (asyncio.set_event_loop(LOOP),
                                 LOOP.run_forever()),
                 daemon=True).start()
FB = FakeBot([FakeGuild(777, [CH_GENERAL, CH_RANDOM])])

print('== 1. Проводка и фиксы кога ==')
check(callable(AP._archiver.generate_html), 'рендер — тот самый метод кога')
cog_src = open(os.path.join(ROOT, 'cogs/archive.py'), encoding='utf-8').read()
check('yedaddndi' not in cog_src and 'сообщений скопировано.' in cog_src,
      'мусорный ответ backup-channel заменён')
check('Всего Сообщение' not in cog_src and 'низ=' not in cog_src,
      '«Всего сообщений» и alt вместо «низ»')

print('== 2. Помощники — лимиты, имена, строки ==')
check(AP._limit('мусор', 100) == 100 and AP._limit(None, 500) == 500,
      'мусор и пусто — в дефолты команд')
check(AP._limit('7', 100) == 7 and AP._limit('99999', 100) == 2000
      and AP._limit('0', 100) == 1, 'кламп 1..2000')
check(re.match(r'^archive_general_\d{8}_\d{6}\.html$',
               AP.html_name('general')), 'имя HTML шаблоном команды')
check(re.match(r'^backup_general_\d{8}\.txt$', AP.txt_name('general')),
      'имя TXT шаблоном команды')
check(AP.txt_line(MSGS[0]) == '[2026-08-10 12:00:00] Вася: Первое <i>сообщение</i>',
      'строка TXT посимвольно как в команде')
check(AP._csv_cell('а;б\nв') == 'а,б в', 'ячейки чистятся')
s = AP._stats(MSGS)
check(s == {'count': 3, 'authors': 2, 'attachments': 2, 'images': 1},
      'счётчики превью руками')
rows = AP._rows(MSGS)
check(len(rows) == 3 and rows[0]['ts'] == '08-10 12:00'
      and rows[2]['atts'] == 1 and rows[0]['author'] == 'Вася',
      'строки превью')

print('== 3. Live-фетч через настоящий loop ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
appmod.bot_instance = FB
try:
    ok, err, code, p = AP.preview_view(lambda: FB, '777', '501', '3')
    check(ok and code == 200 and p['channel'] == 'general'
          and p['stats']['count'] == 3, 'превью живьём')
    check(p['note'] == '3 сообщений заархивировано.', 'итог словами команды')
    ok, err, code, p = AP.preview_view(lambda: FB, '777', '501', '2')
    check(ok and p['stats']['count'] == 2
          and p['rows'][-1]['author'] == 'Петя', 'лимит режет старые, как history')
    ok, err, code, _ = AP.preview_view(lambda: FB, '777', '999', '3')
    check(not ok and code == 404 and err == AP.ERR_CHANNEL, 'нет канала — 404')
    ok, err, code, p = AP.channels_view(lambda: FB, '777')
    check(ok and p['channels'] == [{'id': '501', 'name': 'general'},
                                   {'id': '502', 'name': 'random'}],
          'селект каналов живой')

    print('== 4. Файлы: HTML, TXT, CSV ==')
    ok, err, code, resp = AP.html_flow(lambda: FB, '777', '501', '100')
    body = resp.get_data(as_text=True)
    check(ok and code == 200 and resp.mimetype == 'text/html', 'HTML: ответ')
    check(re.search(r'filename=archive_general_\d{8}_\d{6}\.html',
                    resp.headers['Content-Disposition']), 'HTML: имя файла')
    check(resp.headers['X-Archived-Count'] == '3', 'HTML: счётчик заголовком')
    check('Архив #general' in body and 'Всего сообщений: 3' in body
          and '&lt;i&gt;сообщение&lt;/i&gt;' in body,
          'HTML: шапка, счёт, escape — как у команды')
    check('src="https://cdn.example/cat.png"' in body and 'alt="image"' in body
          and 'n.txt</a>' in body, 'HTML: картинка картинкой, файл ссылкой')
    ok, err, code, resp = AP.txt_flow(lambda: FB, '777', '501', '500')
    body = resp.get_data(as_text=True)
    lines = body.split('\n')
    check(ok and resp.mimetype == 'text/plain'
          and re.search(r'filename=backup_general_\d{8}\.txt',
                        resp.headers['Content-Disposition']),
          'TXT: тип и имя')
    check(lines[0] == '[2026-08-10 12:00:00] Вася: Первое <i>сообщение</i>'
          and len(lines) == 3 and resp.headers['X-Archived-Count'] == '3',
          'TXT: построчно как в команде, без escape')
    ok, err, code, resp = AP.csv_flow(lambda: FB, '777', '501', '100')
    body = resp.get_data(as_text=True)
    check(ok and body.startswith('\ufefftimestamp;author;content;attachments'),
          'CSV: BOM и шапка')
    check(resp.headers['Content-Disposition'].endswith(
        'archive_general_777.csv'), 'CSV: имя с каналом и гильдией')
    check(len(body.strip().split('\n')) == 4
          and 'Смотри сюда;1' in body
          and 'и файл с, точкой;1' in body, 'CSV: строки, «;» в ячейках мытые')

    print('== 5. Offline — честный 409 ==')
    for fn in (AP.preview_view, AP.html_flow, AP.txt_flow, AP.csv_flow):
        ok, err, code, _ = fn(lambda: None, '777', '501', '3')
        check(not ok and code == 409 and err == 'Бот не работает',
              f'{fn.__name__} без бота — 409 словами _run_async')
    ok, err, code, _ = AP.channels_view(lambda: None, '777')
    check(not ok and code == 409, 'каналы без бота — 409')

    print('== 6. API и права ==')
    client = appmod.app.test_client()

    def login(role='owner'):
        with client.session_transaction() as sess:
            sess.clear()
            sess['logged_in'] = True
            sess['username'] = 'admin'
            sess['role'] = role

    PV = '/api/guild/777/archive/preview?channel=501&limit=3'
    check(client.get('/archive').status_code in (302, 401, 403),
          'гостю страница закрыта')
    check(client.get(PV).status_code in (302, 401, 403), 'гостю API закрыто')
    login('uye')
    check(client.get(PV).status_code == 403, 'uye не смотрит')
    check(client.get('/api/guild/777/archive/channels').status_code == 403,
          'uye не видит каналы')
    login('mod')
    page = client.get('/archive')
    check(page.status_code == 200
          and 'Архиватор каналов' in page.get_data(as_text=True),
          'mod открывает страницу')
    d = client.get('/api/guild/777/archive/channels').get_json()
    check(d['success'] and len(d['channels']) == 2, 'каналы через API')
    d = client.get(PV).get_json()
    check(d['success'] and d['stats'] == {'count': 3, 'authors': 2,
                                          'attachments': 2, 'images': 1},
          'превью через API')
    r = client.get('/api/guild/777/archive/preview?channel=999')
    check(r.status_code == 404 and r.get_json()['error'] == 'Канал не найден',
          'нет канала — 404 через API')
    r = client.get('/api/guild/777/archive/html?channel=501')
    check(r.status_code == 200 and r.headers['X-Archived-Count'] == '3'
          and 'Всего сообщений: 3' in r.get_data(as_text=True),
          'mod скачивает HTML')
    check(client.get('/api/guild/777/archive/txt?channel=501')
          .status_code == 403, 'mod не тянет TXT (как administrator)')
    login('admin')
    r = client.get('/api/guild/777/archive/txt?channel=501&limit=2')
    body = r.get_data(as_text=True)
    check(r.status_code == 200 and len(body.split('\n')) == 2
          and body.split('\n')[0].startswith('[2026-08-10 12:00:00] Вася:'),
          'admin тянет TXT с лимитом')
    r = client.get('/api/guild/777/archive/csv?channel=501')
    check(r.status_code == 200
          and r.headers['Content-Disposition'].endswith(
              'archive_general_777.csv'), 'CSV через API')
    login('mod')

    print('== 7. Offline через API ==')
    appmod.bot_instance = None
    login('mod')
    r = client.get(PV)
    check(r.status_code == 409
          and r.get_json()['error'] == 'Бот не работает', 'превью: 409 без бота')
    r = client.get('/api/guild/777/archive/html?channel=501')
    check(r.status_code == 409, 'HTML: 409 без бота')
    login('admin')
    r = client.get('/api/guild/777/archive/txt?channel=501')
    check(r.status_code == 409, 'TXT: 409 без бота (даже админу)')
finally:
    appmod.bot_instance = None

print('== 8. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/archive.html'),
           encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
src = open(os.path.join(ROOT, 'web/routes/archive_panel.py'),
           encoding='utf-8').read()
check(not EMOJI_RE.search(src), 'в модуле нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('arChannel', 'arLimit', 'arPreview', 'arHtml', 'arTxt', 'arCsv',
            'arMsg', 'arStats', 'arRows', 'arPanelRows', 'arRowsSub'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
for path in ("'/channels'", "'/preview?'", "'/html?'", "'/txt?'", "'/csv?'"):
    check(path in tpl, f'путь {path} в шаблоне')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
import services.panel_menu as PM
log_pages = [pg['path'] for g in PM.MENU if g['key'] == 'logs'
             for pg in g['pages']]
check('/archive' in log_pages, 'пункт меню «Архиватор» в «Логах»')
check(PM.PAGE_COGS.get('/archive') == ('archive',), 'ког привязан')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('archive_panel') >= 1, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
