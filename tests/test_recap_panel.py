# -*- coding: utf-8 -*-
"""Рекап канала (идеи #111-115).

Период 1..720 словами кога, оба окна через build_recap (текущее + сдвинутое
на период — дельты), эмбед 1:1 с _do_recap (заголовок, «тихо», inline-флаги),
CSV без markdown-звёзд, офлайн — честный 409, права, шаблон, меню.

Запуск: python3 tests/test_recap_panel.py
"""
import importlib
import os
import re
import shutil
import sys
import tempfile
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


from web.routes import recap_panel as RP  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def mk(author, content, hours_ago, count=0, bot=False):
    return {'author': author, 'author_id': 1, 'content': content, 'bot': bot,
            'created_at': NOW - timedelta(hours=hours_ago),
            'reactions': [{'count': count}] if count else []}


POOL = [
    mk('Анна', 'привет https://x.dev смотрите', 1, count=3),
    mk('Борис', 'смотрите новости', 2, count=1),
    mk('Анна', 'новости классные', 23),
    mk('Вера', 'старое сообщение', 25),
    mk('Гоша', '', 3),
    mk('Анна', 'кот http://a.ru и пёс', 30),
    mk('Бот', 'служебное', 1, bot=True),
    mk('Динозавр', 'очень старое', 100),
]

print('== 1. Период и канал ==')
check(RP.validate_hours('24') == (True, '', 24), '24 часа ок')
check(RP.validate_hours(720) == (True, '', 720), 'граница 720 ок')
for raw in ('0', '721', '-5', 'abc', '', None):
    ok, err, _ = RP.validate_hours(raw)
    check(not ok and err == 'Период — от 1 до 720 часов (30 дней).',
          f'{raw!r} — текст кога')

chan = SimpleNamespace(id=5, name='general', history=object())
guild = SimpleNamespace(get_channel=lambda cid: chan if cid == 5 else None)
check(RP.find_channel(guild, '5') is chan, 'канал найден')
check(RP.find_channel(guild, '6') is None, 'чужой ID — None')
check(RP.find_channel(guild, 'qq') is None, 'буквы — None')
check(RP.find_channel(SimpleNamespace(get_channel=lambda cid: SimpleNamespace(id=1)),
                      '1') is None, 'голосовой без history не подходит')
check(RP.find_channel(None, '5') is None, 'нет гильдии — None')

print('== 2. Сборка 1:1 с build_recap ==')
pack = RP.pack_recap(POOL, 24, NOW)
cur, prev = pack['cur'], pack['prev']
check(cur['total'] == 4 and cur['unique_authors'] == 3, 'окно: 4 сообщения, 3 автора')
check(cur['top_authors'][0] == ('Анна', 2), 'Анна первой')
words = dict(cur['top_words'])
check(words.get('смотрите') == 2 and words.get('новости') == 2
      and 'https' not in words and 'и' not in words, 'слова без ссылок и стоп-слов')
check(cur['links'] == 1 and cur['avg_per_hour'] == 0.2, 'ссылка и темп')
check(cur['hottest']['author'] == 'Анна' and cur['hottest']['reactions'] == 3,
      'самая реактивная реплика')
check(cur['busy_hour'] == (NOW - timedelta(hours=1)).hour, 'пик — час первой вставки')
check(prev['total'] == 2 and prev['unique_authors'] == 2, 'предыдущее окно: Вера + Анна')
cmp = pack['compare']
check(cmp['delta_total'] == 2 and cmp['delta_authors'] == 1, 'дельты +2/+1')
check(pack['scanned'] == 8, 'пул — все 8 записей')

quiet = RP.pack_recap([mk('Кто', 'раньше', 100)], 24, NOW)
check(quiet['cur']['total'] == 0 and quiet['compare']['delta_total'] == 0,
      'пустое окно — нули')

print('== 3. Эмбед и CSV ==')
spec = RP.embed_spec('general', cur, 24)
check(spec['title'] == 'Рекап #general · 24 часа', 'заголовок кога')
check(len(spec['fields']) == 7, 'семь полей')
inl = {f['name']: f['inline'] for f in spec['fields']}
check(inl['Сообщений'] is True and inl['Участников'] is True
      and inl['Пик активности'] is True and inl['Активные авторы'] is False,
      'inline-флаги как в _do_recap')
check('**Анна** (2)' in spec['fields'][2]['value'], 'markdown бота сохранён')
qspec = RP.embed_spec('general', quiet['cur'], 24)
check(qspec['description'] == 'За период тихо — сообщений не было.'
      and qspec['fields'] == [], 'тихо — словами бота')

rows = RP.recap_csv_rows('general', pack, 24)
d = dict(rows)
check(rows[0] == ('Канал', '#general') and d['Период (часов)'] == '24', 'шапка данных')
check(d['Просмотрено сообщений в истории'] == '8', 'скан в выгрузке')
check(d['Сообщений'].startswith('4 за 24 часа'), 'поле без звёзд')
check(all('**' not in v for _k, v in rows), 'markdown вычищен везде')
check(d['Сравнение: разница'] == '+2' and d['Сравнение: сообщений окном раньше'] == '2',
      'сравнение в выгрузке')

print('== 4. API: права и офлайн ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


BLD = '/api/guild/777/recap/build'
check(client.get('/recap').status_code in (302, 401, 403), 'гостю страница закрыта')
login('uye')
check(client.post(BLD, json={'channel_id': '5', 'hours': '24'}).status_code == 403,
      'uye не собирает')
login('mod')
page = client.get('/recap')
check(page.status_code == 200 and 'Рекап канала' in page.get_data(as_text=True),
      'mod открывает страницу')
check('rcSend' in page.get_data(as_text=True), 'кнопка отправки в разметке')
r = client.post(BLD, json={'channel_id': '5', 'hours': 'abc'})
check(r.status_code == 400
      and r.get_json()['error'] == 'Период — от 1 до 720 часов (30 дней).',
      'битый период — текст кога')
r = client.post(BLD, json={'channel_id': '5', 'hours': '24'})
check(r.status_code == 409
      and r.get_json()['error'] == 'Бот офлайн — рекап собирается через живого бота',
      'офлайн — честный 409, не фальшивые нули')
r = client.get('/api/guild/777/recap/export.csv?channel=5&hours=721')
check(r.status_code == 400, 'выгрузка с кривым периодом — 400')
r = client.get('/api/guild/777/recap/export.csv?channel=5&hours=24')
check(r.status_code == 409, 'выгрузка офлайн — 409')
check(client.post('/api/guild/777/recap/send',
                  json={'channel_id': '5', 'hours': '24'}).status_code == 403,
      'mod не отправляет в канал')
login('admin')
r = client.post('/api/guild/777/recap/send', json={'channel_id': '5', 'hours': '24'})
check(r.status_code == 409, 'admin офлайн — тот же 409')
r = client.post('/api/guild/777/recap/send', json={'channel_id': '5', 'hours': '0'})
check(r.status_code == 400, 'валидация идёт до проверки живости')

print('== 5. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/recap.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
check('[data-theme="light"]' in tpl, 'светлая тема учтена')
for fid in ('rcChan', 'rcHours', 'rcGo', 'rcSend', 'rcCsv', 'rcEmbed', 'rcCmp'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check("'/build'" in tpl and "'/send'" in tpl and '/export.csv?channel=' in tpl,
      'API-пути в шаблоне')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
import services.panel_menu as PM
main_pages = [pg['path'] for g in PM.MENU if g['key'] == 'main' for pg in g['pages']]
check('/recap' in main_pages, 'пункт меню «Рекап канала» в «Основном»')
check(PM.PAGE_COGS.get('/recap') == ('recap',), 'recap-ког привязан к странице')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('recap_panel') >= 2, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
