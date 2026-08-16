# -*- coding: utf-8 -*-
"""Транскрипты тикетов: хранилище, запись при закрытии, панель (поиск/просмотр/экспорт).

Регрессия по «вечно пустой» странице: панель читала data/transcripts.json,
в который никто не писал — ког и автозакрытие слали txt только в ticket-log
и в DM. Плюс HTML-экспорт подставлял контент без экранирования (XSS через
сообщение тикета прямо в админский браузер), а кнопка «Экспорт PDF» вела на 501.

Проверяем: record() (shape, кап, терпимость к битому входу), фильтры (поиск/
период/категория, aware/naive-ts), рендеры (экранирование, автономность HTML,
безопасное имя файла), роуты панели (доступ mod+, 404/400, заголовки файлов),
что оба пути закрытия в коде пишут в хранилище, шаблон v2 без дыр и эмодзи.

Запуск: python3 tests/test_transcripts.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_trx_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'

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


from services import transcript_store as ts  # noqa: E402

NOW = datetime.now(timezone.utc)
OPENED = NOW - timedelta(hours=2, minutes=15)

MSGS = [
    {'timestamp': OPENED, 'author': 'Иван', 'content': 'здравствуйте, помогите', 'is_bot': False},
    {'timestamp': OPENED + timedelta(minutes=1), 'author': 'Aether', 'content': 'Чем помочь?', 'is_bot': True},
    {'timestamp': OPENED + timedelta(minutes=2), 'author': 'Иван', 'content': '  ', 'is_bot': False},
    {'timestamp': OPENED + timedelta(minutes=3), 'author': 'Иван', 'content': '<script>alert(1)</script>&"\'', 'is_bot': False},
]

print('== 1. record(): форма записи, категории, длительность ==')
rec = ts.record(guild_id=777, channel_id=555, channel_name='ticket-ivan-1',
                user_id=42, user_name='Иван', category='soru', status='done',
                closed_by='moder', opened_at=OPENED, closed_at=NOW, messages=MSGS)
check(rec['id'] == 'ticket-ivan-1 · 555', 'id = канал · channel_id')
check(rec['category'] == 'Вопрос', 'категория-ключ переведён в русский ярлык')
check(rec['duration'] == '2 ч 15 мин', f"длительность посчитана: {rec['duration']}")
check(len(rec['messages']) == 3, 'пустое сообщение (пробелы) отфильтровано')
check(rec['messages'][2]['is_bot'] is False and rec['messages'][1]['is_bot'] is True,
      'флаг is_bot сохраняется')
saved = ts.load()
check(len(saved) == 1 and saved[0]['id'] == rec['id'], 'запись персистентна в data/transcripts.json')
check(saved[0]['opened_at'].endswith('+00:00'), 'timestamps aware-ISO')

print('== 2. Терпимость к входу ==')
rec2 = ts.record(guild_id=777, channel_id=556, channel_name='ticket-anna-2',
                 messages=[{'timestamp': 'битая строка', 'author': 'Анна', 'content': 'ок'},
                           {'timestamp': None, 'author': 'Анна', 'content': 'ещё'}])
check(rec2['duration'] == '—' and rec2['opened_at'] is None, 'без opened_at — честная прочерк-длительность')
check(len(rec2['messages']) == 2 and all(m['timestamp'] == '' or m['timestamp'].endswith('+00:00')
      for m in rec2['messages']), 'битые timestamp не роняют запись')
ts.record(guild_id=777, channel_id=557, channel_name='ticket-x-3', category='Нестандарт')
check(ts.load()[-1]['category'] == 'Нестандарт', 'незнакомая категория сохраняется как есть')

print('== 3. Кап и устойчивость хранилища ==')
many = [{'id': f'old-{i}', 'closed_at': f'2026-01-{i % 28 + 1:02d}T00:00:00+00:00', 'messages': []}
        for i in range(ts.MAX_RECORDS + 5)]
ts._save_all(many)
check(len(ts.load()) == ts.MAX_RECORDS, f'файл ограничен {ts.MAX_RECORDS} записями')
with open('data/transcripts.json', 'w', encoding='utf-8') as f:
    f.write('{битый json')
check(ts.load() == [], 'битый JSON — пустое хранилище, не исключение')
with open('data/transcripts.json', 'w', encoding='utf-8') as f:
    json.dump({'not': 'a list'}, f)
check(ts.load() == [], 'не-список JSON — тоже пусто')

print('== 4. Фильтры ==')
records = [
    {'id': 'a · 1', 'user_name': 'Иван', 'channel_name': 'ticket-ivan-1', 'category': 'Вопрос',
     'closed_at': NOW.isoformat(), 'messages': [{'content': 'x'}]},
    {'id': 'b · 2', 'user_name': 'Анна', 'channel_name': 'ticket-anna-2', 'category': 'Жалоба',
     'closed_at': (NOW - timedelta(days=10)).isoformat(), 'messages': []},
    {'id': 'c · 3', 'user_name': 'Пётр', 'channel_name': 'ticket-petr-3', 'category': 'Вопрос',
     'closed_at': (NOW - timedelta(days=40)).strftime('%Y-%m-%d %H:%M:%S'), 'messages': []},
]
all_r = ts.filter_records(records)
check(len(all_r) == 3 and all_r[0]['id'] == 'a · 1', 'без фильтров: все, свежие первые')
check([t['id'] for t in ts.filter_records(records, days='7')] == ['a · 1'], 'days=7 режет старые')
check([t['id'] for t in ts.filter_records(records, days='45')] == ['a · 1', 'b · 2', 'c · 3'],
      'наивная дата (strftime) в closed_at не ломает фильтр')
check([t['id'] for t in ts.filter_records(records, days='abc')] == [t['id'] for t in all_r],
      'days="abc" мягко игнорируется')
check([t['id'] for t in ts.filter_records(records, category='вопрос')] == ['a · 1', 'c · 3'],
      'категория регистронезависима')
check([t['id'] for t in ts.filter_records(records, search='анна')] == ['b · 2'], 'поиск по имени')
check([t['id'] for t in ts.filter_records(records, search='TICKET-PETR')] == ['c · 3'], 'поиск по каналу')

print('== 5. Рендеры: экранирование и автономность ==')
evil = ts.record(guild_id=777, channel_id=900, channel_name='ticket-e<script>-9',
                 user_name='<b>зло</b>', category='Жалоба', messages=MSGS)
html_doc = ts.render_html(evil)
check('<script>alert(1)</script>' not in html_doc and '&lt;script&gt;' in html_doc,
      'HTML: контент сообщений экранирован (XSS закрыт)')
check('&lt;b&gt;зло&lt;/b&gt;' in html_doc and '<b>зло</b>' not in html_doc.replace('<b>', '').replace('</b>', ''),
      'HTML: имя пользователя тоже экранировано')
check('http://' not in html_doc and 'https://' not in html_doc, 'HTML автономен: ноль внешних URL')
check('@media print' in html_doc, 'print-стили для распечатки')
txt_doc = ts.render_txt(evil)
check('<script>' in txt_doc and 'Иван:' in txt_doc and '=' * 80 in txt_doc,
      'TXT: плоский текст без экранирования, с разделителем')
fname = ts.export_filename(evil, 'html')
check(re.fullmatch(r'[0-9A-Za-zА-Яа-я_.-]+', fname) and fname.endswith('.html'),
      f'имя файла безопасно: {fname!r}')

# ═══ Панель ══════════════════════════════════════════════════════════════
print('== 6. Роуты панели ==')
appmod = importlib.import_module('web.app')
app = appmod.app
app.config['TESTING'] = True
client = app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


# файл на данный момент: записи из шагов 1-3 + evil (битые шаг 3 перезаписали, но дальше добили)
if not ts.load():
    ts.record(guild_id=777, channel_id=1, channel_name='seed-1', user_name='Сид', messages=MSGS)
target = ts.load()[0]

with client.session_transaction() as s:
    s.clear()
r = client.post('/api/transcripts/search', json={})
check(r.status_code in (302, 401, 403), f'гость: поиск закрыт ({r.status_code})')
login('uye')
r = client.post('/api/transcripts/search', json={})
check(r.status_code == 403, 'uye: поиск закрыт (403 — переписка не для участников)')
login('mod')
r = client.post('/api/transcripts/search', json={})
data = r.get_json()
check(r.status_code == 200 and data.get('success') and data.get('total', 0) >= 1, 'mod: поиск работает')
check('messages' not in data['transcripts'][0] and 'message_count' in data['transcripts'][0],
      'список отдаёт лёгкие проекции без массива сообщений')

r = client.post('/api/transcripts/search', json={'days': '1'})
check(r.get_json()['success'] is True, 'фильтр days принимается')
r = client.post('/api/transcripts/search', json={'days': 'zzz'})
check(r.get_json()['success'] is True, 'битый days не роняет API (200, фильтр проигнорирован)')

r = client.get('/api/transcripts/' + target['id'])
check(r.status_code == 200 and r.get_json()['transcript']['id'] == target['id'], 'полный транскрипт по id')
r = client.get('/api/transcripts/no-such-id')
check(r.status_code == 404, 'неизвестный id — 404')

r = client.get('/api/transcripts/no-such-id/export')
check(r.status_code == 404, 'экспорт неизвестного — 404')
r = client.get('/api/transcripts/' + evil['id'] + '/export?format=html')
body = r.get_data(as_text=True)
cd = r.headers.get('Content-Disposition', '')
check(r.status_code == 200 and 'attachment' in cd and '.html' in cd, 'HTML-экспорт: файл-вложение')
check('&lt;script&gt;' in body and '<script>alert' not in body, 'HTML-экспорт экранирован')
check(r.headers.get('Cache-Control') == 'no-store', 'экспорт без кэша (no-store)')
r = client.get('/api/transcripts/' + target['id'] + '/export?format=txt')
check(r.status_code == 200 and 'attachment' in r.headers.get('Content-Disposition', '')
      and 'text/plain' in r.headers.get('Content-Type', ''), 'TXT-экспорт: headers корректны')
r = client.get('/api/transcripts/' + target['id'] + '/export?format=pdf')
check(r.status_code == 400 and 'txt' in (r.get_json().get('error') or ''),
      'неподдержанный формат — честный 400, а не 501-заглушка')

print('== 7. Страница /transcripts ==')
login('mod')
r = client.get('/transcripts')
check(r.status_code == 200, 'страница открывается персоналу (200)')
login('uye')
r = client.get('/transcripts')
check(r.status_code == 403, 'участнику страница запрещена (403)')

src = open(os.path.join(ROOT, 'web', 'templates', 'transcripts.html'), encoding='utf-8').read()
for token in ('trx-item', 'trx-backdrop', "encodeURIComponent(t.id)", "exportTranscript('html')",
              'debounceTimer', 'Escape', 'empty-state'):
    assert token in src, token
check(True, 'шаблон v2: модалка, дебаунс, ESC/бэкдроп, encodeURIComponent')
check('fa-file-pdf' not in src and 'pdf' not in src.lower().replace('pdf-транскриптов', ''),
      'кнопка-заглушка «Экспорт PDF» убрана')
check('alert(' not in src, 'alert() заменён на нормальные состояния')
EMOJI = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not EMOJI.search(src), 'эмодзи в шаблоне нет (FA-иконки только)')

from services import panel_menu as pm
menu_paths = {it['path'] for g in pm.MENU for it in g['pages']}
check('/transcripts' in menu_paths, 'пункт «Транскрипты» есть в меню (группа Тикеты)')

print('== 8. Запись при закрытии — оба пути заведены ==')
ticket_src = open(os.path.join(ROOT, 'cogs', 'ticket.py'), encoding='utf-8').read()
check('transcript_store' in ticket_src and '_tstore .record (' in ticket_src.replace('.record(', '.record ('),
      'ручное закрытие пишет транскрипт в хранилище')
check('full_msgs' in ticket_src, 'close: полная лента с is_bot собирается')
autoclose_src = open(os.path.join(ROOT, 'services', 'auto_close_service.py'), encoding='utf-8').read()
check('transcript_store' in autoclose_src and 'full_msgs' in autoclose_src,
      'автозакрытие тоже пишет транскрипт в хранилище')
check('category_label' in open(os.path.join(ROOT, 'services', 'transcript_store.py'), encoding='utf-8').read(),
      'сервис переводит category-ключи в русские ярлыки')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
