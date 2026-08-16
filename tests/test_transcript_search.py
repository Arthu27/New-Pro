# -*- coding: utf-8 -*-
"""Глубокий поиск по транскриптам: текст переписки + сниппеты с подсветкой.

Раньше поиск по транскриптам видел только мета-поля (id/имя/канал/категория):
вопрос «а в каком тикете обсуждали вайп?» оставался без ответа — переписку
пришлось бы открывать по одной. Теперь поиск проваливается в текст сообщений,
а карточки показывают сниппеты (контекст + совпадение + контекст, <mark>).

Проверяем: snippets() (регистр оригинала, обрезка контекста с …, лимит,
кириллица, схлопывание \n), глубокая фильтрация, что API прикрепляет
сниппеты только к контентным совпадениям, устойчивость к XSS-запросам,
и что шаблон экранирует куски сниппетов через esc().

Запуск: python3 tests/test_transcript_search.py
"""
import importlib
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_trxsearch_test_')
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

print('== 1. snippets(): вырезка совпадений ==')
rec = ts.record(guild_id=777, channel_id=11, channel_name='ticket-wipe-1',
                user_name='Степа', opened_at=NOW - timedelta(hours=1), closed_at=NOW,
                messages=[
                    {'timestamp': NOW - timedelta(minutes=50), 'author': 'Степа',
                     'content': 'привет, а скажите пожалуйста когда будет ВАЙП на сервере? очень жду', 'is_bot': False},
                    {'timestamp': NOW - timedelta(minutes=40), 'author': 'Aether',
                     'content': 'Ваш вопрос передан администрации', 'is_bot': True},
                    {'timestamp': NOW - timedelta(minutes=30), 'author': 'moder',
                     'content': 'вайп\nзапланирован\nна субботу', 'is_bot': False},
                ])
snips = ts.snippets(rec, 'вайп')
check(len(snips) == 2, 'сниппеты по двум сообщениям (лимит по умолчанию)')
check(snips[0]['match'] == 'ВАЙП', 'регистр оригинала сохранён в совпадении')
check(snips[0]['before'].endswith('когда будет ') and snips[0]['after'].startswith(' на сервере'),
      'контекст до/после на месте')
check(snips[0]['author'] == 'Степа' and snips[0]['timestamp'], 'автор и время у сниппета')
check('\n' not in snips[1]['before'] + snips[1]['match'] + snips[1]['after'],
      'переносы строк схлопнуты в пробелы')
long_msg = {'messages': [{'content': 'а' * 200 + 'игла' + 'б' * 200, 'author': 'x', 'timestamp': ''}]}
s2 = ts.snippets(long_msg, 'игла')[0]
check(s2['before'].startswith('…') and s2['after'].endswith('…'), 'длинный текст обрезан с многоточиями')
check(len(s2['before']) == ts.SNIPPET_CTX + 1 and len(s2['after']) == ts.SNIPPET_CTX + 1,
      'окно контекста ровно SNIPPET_CTX символов')
check(ts.snippets(rec, '') == [] and ts.snippets(rec, '   ') == [], 'пустой запрос — без сниппетов')
check(ts.snippets(rec, 'несуществуещее') == [], 'нет совпадений — пусто')
many = {'messages': [{'content': f'хит {i} цель', 'author': 'y', 'timestamp': ''} for i in range(5)]}
check(len(ts.snippets(many, 'цель')) == 2, 'лимит сниппетов уважается (2 из 5)')

print('== 2. Глубокая фильтрация ==')
records = ts.load()
deep = ts.filter_records(records, search='вайп')
check([t['channel_name'] for t in deep] == ['ticket-wipe-1'], 'контентный поиск находит тикет')
meta = ts.filter_records(records, search='степа')
check([t['channel_name'] for t in meta] == ['ticket-wipe-1'], 'мета-поиск по имени работает')
check(ts.filter_records(records, search='бургер') == [], 'нигде не встречается — пусто')
combo = ts.filter_records(records, search='вайп', days='1')
check(len(combo) == 1, 'глубокий поиск + фильтр периода сочетаются')
ts.record(guild_id=777, channel_id=12, channel_name='ticket-old-2', user_name='Гога',
          closed_at=(NOW - timedelta(days=30)).isoformat(),
          messages=[{'timestamp': NOW - timedelta(days=30), 'author': 'Гога',
                     'content': 'когда вайп?', 'is_bot': False}])
combo = ts.filter_records(records + [ts.load()[-1]], search='вайп', days='1')
check(len(combo) == 1 and combo[0]['channel_name'] == 'ticket-wipe-1',
      'старый тикет с тем же словом отрезан периодом')

print('== 3. API: сниппеты в ответе ==')
appmod = importlib.import_module('web.app')
app = appmod.app
app.config['TESTING'] = True
client = app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'admin'
    s['role'] = 'mod'

r = client.post('/api/transcripts/search', json={'search': 'вайп'})
data = r.get_json()
check(data['success'] and data['total'] >= 2, f"глубокий поиск по API: {data['total']} записи")
first = data['transcripts'][0]
check('snippets' in first and first['snippets'][0]['match'].lower() == 'вайп',
      'к контентному совпадению прикреплены сниппеты')
check({'before', 'match', 'after', 'author', 'timestamp'} <= set(first['snippets'][0]),
      'у сниппета полный набор полей')

r = client.post('/api/transcripts/search', json={'search': 'степа'})
st = r.get_json()['transcripts']
check(len(st) == 1, 'мета-совпадение по имени находится без глубокого поиска')
check(all('степа' not in (x.get('user_name') or '').lower() or 'snippets' not in x
          or all('степа' in (s['match'] + s['before'] + s['after']).lower() for s in x['snippets'])
          for x in st),
      'сниппеты, если есть, строго про текст запроса')

r = client.post('/api/transcripts/search', json={})
clean = r.get_json()['transcripts']
check(clean and not any('snippets' in x for x in clean), 'без запроса — без сниппетов (не раздуваем ответ)')

r = client.post('/api/transcripts/search', json={'search': '<img src=x onerror=alert(1)>'})
check(r.get_json()['success'] is True, 'XSS-запрос обрабатывается безопасно (просто нет совпадений)')

evil_msg = 'да го <script>alert(1)</script> в лс'
ts.record(guild_id=777, channel_id=13, channel_name='ticket-evil-3', user_name='Злой',
          messages=[{'timestamp': NOW, 'author': 'Злой', 'content': evil_msg, 'is_bot': False}])
r = client.post('/api/transcripts/search', json={'search': 'alert'})
evil_hit = [x for x in r.get_json()['transcripts'] if x['channel_name'] == 'ticket-evil-3']
check(evil_hit and '<script>' in evil_hit[0]['snippets'][0]['before'],
      'сырой текст в JSON (рендер-экранирование — задача шаблона)')

print('== 4. Шаблон: подсветка экранирована ==')
src = open(os.path.join(ROOT, 'web', 'templates', 'transcripts.html'), encoding='utf-8').read()
for token in ('trx-snip', 'snipsHtml(', 'esc(s.before)', 'esc(s.match)', 'esc(s.after)', '<mark>'):
    assert token in src, token
check(True, 'сниппеты рендерятся через esc() + <mark> подсветку')
check('текст сообщения' in src, 'плейсхолдер поиска говорит про текст переписки')
check('.trx-snip mark{' in src, 'CSS подсветки совпадения на месте')
EMOJI = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not EMOJI.search(src), 'эмодзи нет (FA-иконки только)')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
