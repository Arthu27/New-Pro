# -*- coding: utf-8 -*-
"""Статистика транскриптов: сводка на странице (KPI, категории, дни, закрывающие).

Третья часть транскрипт-саги: записи пишутся, ищутся, скачиваются — теперь
ещё и анализируются. stats() в хранилище собирает сводку (объёмы за 7/30
дней, топ категорий с долями, средняя/медианная длительности с отсечением
выбросов, закрытия по дням за 2 недели, топ закрывающих), страница рисует
это CSS-барами без единой внешней библиотеки.

Проверяем: чистый stats() с инжектированным временем (детерминизм!),
доли/топы/медианы/бакеты, отсев битых записей, API (права, форма),
статику секции в шаблоне.

Запуск: python3 tests/test_transcript_stats.py
"""
import importlib
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_trxstats_test_')
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

NOW = datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc)


def rec(closed_at=None, opened_at=None, category='Вопрос', closed_by='мод', msgs=1):
    return {
        'id': 'x', 'closed_at': closed_at.isoformat() if closed_at else None,
        'opened_at': opened_at.isoformat() if opened_at else None,
        'category': category, 'closed_by': closed_by,
        'messages': [{'content': 'm'}] * msgs,
    }


RECORDS = [
    rec(NOW, NOW - timedelta(hours=2), 'Жалоба', 'мод1', 3),
    rec(NOW - timedelta(days=3), NOW - timedelta(days=3, hours=1), 'Вопрос', 'мод1', 5),
    rec(NOW - timedelta(days=10), NOW - timedelta(days=10, minutes=30), 'Жалоба', 'мод2', 1),
    rec(NOW - timedelta(days=40), None, None, 'мод1', 1),
    rec(None, NOW - timedelta(hours=1), 'Хлам', 'хакер', 99),        # без closed_at — пропуск
]

print('== 1. stats(): объёмы и топы ==')
st = ts.stats(RECORDS, now=NOW)
check(st['total'] == 4, 'всего 4 (запись без closed_at пропущена)')
check(st['last7'] == 2 and st['last30'] == 3, f"7д={st['last7']}, 30д={st['last30']}")
cats = {c['name']: c for c in st['categories']}
check(st['categories'][0]['name'] == 'Жалоба' and st['categories'][0]['count'] == 2,
      'топ категории — Жалоба (2)')
check(abs(sum(c['count'] for c in st['categories']) - 4) == 0, 'категории покрывают все записи')
check(cats['Жалоба']['share'] == 50.0 and cats['Вопрос']['share'] == 25.0, 'доли в процентах честные')
cl = {c['name']: c['count'] for c in st['closers']}
check(cl == {'мод1': 3, 'мод2': 1}, f'топ закрывающих: {cl}')

print('== 2. Длительности и сообщения ==')
check(st['avg_duration_sec'] == 4200, 'avg = (7200+3600+1800)/3 = 4200 c')
check(st['median_duration_sec'] == 3600, 'медиана = 3600 c')
check(st['avg_duration'] == '1 ч 10 мин', f"avg человечески: {st['avg_duration']}")
check(st['median_duration'] == '1 ч', f"медиана человечески: {st['median_duration']}")
check(st['with_duration'] == 3, 'длительность посчитана для 3 (без opened_at — вне)')
check(st['avg_messages'] == 2.5, f"сообщений в среднем: {st['avg_messages']}")

print('== 3. Бакеты по дням ==')
days = st['days']
check(len(days) == ts.STATS_DAYS == 14, 'ровно 14 дневных бакетов')
check(days[-1]['count'] == 1, 'сегодняшний бакет = 1')
check(sum(d['count'] for d in days) == 3, 'в окне 14 дней — 3 закрытия (40-дневное вне)')
check(re.fullmatch(r'\d{2}\.\d{2}', days[0]['label']), 'подписи бакетов ДД.ММ')

print('== 4. Выбросы и пустота ==')
spike = RECORDS + [rec(NOW, NOW - timedelta(days=60), 'Жалоба', 'мод3')]
check(ts.stats(spike, now=NOW)['with_duration'] == 3, 'тикет на 60 суток — выброс, в средние не идёт')
empty = ts.stats([], now=NOW)
check(empty['total'] == 0 and empty['avg_duration'] == '0 мин' and empty['categories'] == []
      and empty['closers'] == [] and len(empty['days']) == 14
      and not any(d['count'] for d in empty['days']),
      'пустое хранилище — честные нули, не исключение')

print('== 5. API /api/transcripts/stats ==')
ts.record(guild_id=777, channel_id=1, channel_name='seed-1', user_name='Сид',
          category='soru', opened_at='2026-08-16T10:00:00+00:00',
          messages=[{'timestamp': '2026-08-16T10:05:00+00:00', 'author': 'Сид', 'content': 'привет'}])
appmod = importlib.import_module('web.app')
app = appmod.app
app.config['TESTING'] = True
client = app.test_client()
with client.session_transaction() as s:
    s.clear()
r = client.get('/api/transcripts/stats')
check(r.status_code in (302, 401, 403), f'гостю закрыто ({r.status_code})')
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'admin'
    s['role'] = 'uye'
r = client.get('/api/transcripts/stats')
check(r.status_code == 403, 'uye нельзя (403)')
with client.session_transaction() as s:
    s['role'] = 'mod'
r = client.get('/api/transcripts/stats')
data = r.get_json()
check(r.status_code == 200 and data.get('success'), 'mod: 200 + success')
stat = data.get('stats') or {}
check(stat.get('total') == 1 and stat.get('categories')[0]['name'] == 'Вопрос',
      'сид учтён: 1 запись, категория переведена')
check(len(stat.get('days') or []) == 14 and 'avg_duration' in stat and 'median_duration' in stat,
      'форма ответа полная')

print('== 6. Секция сводки в шаблоне ==')
src = open(os.path.join(ROOT, 'web', 'templates', 'transcripts.html'), encoding='utf-8').read()
for token in ('trxStatsSection', 'loadTrxStats', '/api/transcripts/stats', 'trx-kpi',
              'trx-chart', 'trx-bar-fill', 'esc(c.name)'):
    assert token in src, token
check(True, 'секция, загрузчик, KPI/бары/чарт — на месте')
check('!d.stats.total) return' in src, 'пустое хранилище прячет сводку (не показываем нули)')
EMOJI = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not EMOJI.search(src), 'эмодзи нет (FA-иконки только)')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
