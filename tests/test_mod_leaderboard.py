# -*- coding: utf-8 -*-
"""Эффективность модераторов: композитный рейтинг (services/mod_leaderboard).

Активность из аудита + решения и скорость апелляций + звёзды staff_rating
+ справедливость оценок; нет данных — нейтральная половина, а не ноль.

Запуск: python3 tests/test_mod_leaderboard.py
"""
import importlib
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_leadboard_test_')
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


from db import GuildData  # noqa: E402
from cogs import appeals as AP  # noqa: E402
from services.mod_leaderboard import compute_leaderboard  # noqa: E402

NOW = datetime.now(timezone.utc)

print('== 1. пусто — честная пустота ==')
res = compute_leaderboard('777')
check(res['rows'] == [] and res['mod_of_month'] is None,
      'нет данных — нет рейтинга, короны нет')

print('== 2. три фигуры команды ==')
# Активист: 30 действий, быстрые решения, все довольны
evs = [{'category': 'mod', 'action': 'mute', 'mod_name': 'Swift',
        'user_id': '1', 'timestamp': datetime.now().isoformat()}
       for _ in range(30)]
evs += [{'category': 'mod', 'action': 'warn', 'mod_name': 'slowcoach',
         'user_id': '2', 'timestamp': datetime.now().isoformat()}
        for _ in range(3)]
json.dump({'777': evs}, open('data/audit_log.json', 'w'))

st = AP.empty_state()
st['items'] = [
    {'id': 1, 'user_id': 10, 'user_name': 'A', 'text': 'x' * 12, 'link': None,
     'status': 'accepted', 'created_at': (NOW - timedelta(hours=2)).isoformat(),
     'reviewed_by': 'Swift', 'reviewed_at': NOW.isoformat(), 'reply': 'ок',
     'rating': 'up', 'rating_comment': None, 'claimed_by': None,
     'escalated_at': None},
    {'id': 2, 'user_id': 11, 'user_name': 'B', 'text': 'x' * 12, 'link': None,
     'status': 'rejected',
     'created_at': (NOW - timedelta(hours=50)).isoformat(),
     'reviewed_by': 'Slowcoach', 'reviewed_at': NOW.isoformat(), 'reply': 'нет',
     'rating': 'down', 'rating_comment': None, 'claimed_by': None,
     'escalated_at': None},
     # авто-закрытая самим Discord — в рейтинг не должна попасть
    {'id': 3, 'user_id': 12, 'user_name': 'C', 'text': 'x' * 12, 'link': None,
     'status': 'auto_closed',
     'created_at': (NOW - timedelta(hours=50)).isoformat(),
     'reviewed_by': 'Discord (разбан вручную)',
     'reviewed_at': NOW.isoformat(), 'reply': None,
     'rating': None, 'rating_comment': None},
]
GuildData('appeals').set('777', 'state', st)
sr = {'staff': {'42': {'votes': {'1': 5, '2': 5}, 'comments': []}}}
GuildData('staff_rating').set('777', 'state', sr)
# имя id=42 неизвестно аудиту — покажем строкой с id
res = compute_leaderboard('777')
rows = {r['mod'].lower(): r for r in res['rows']}
check('swift' in rows and 'slowcoach' in rows,
      f'оба модератора в таблице (слияние по регистру): {list(rows)}')
sw = rows['swift']
check(sw['actions'] == 30 and sw['decisions'] == 1,
      'действия и решения поименно')
check(sw['avg_hours'] == 2.0, f'скорость Swifта 2 ч (есть {sw["avg_hours"]})')
check(sw['fair_pct'] == 100, 'у Swifта 100% справедливости')
sl = rows['slowcoach']
check(sl['avg_hours'] == 50.0 and sl['fair_pct'] == 0,
      'у Slowcoach 50 ч и 0% справедливости')
check(sw['score'] > sl['score'], f'порядок: Swift выше ({sw["score"]} > {sl["score"]})')
check(all(r['mod'] != 'Discord (разбан вручную)' for r in res['rows']),
      'Discord-автозакрытия в рейтинг не попадают')
check(res['rows'][0]['rank'] == 1 and res['mod_of_month'] == 'Swift',
      'корона за первым местом')
unk = [r for r in res['rows'] if r['mod'] == '42']
check(not unk or unk[0]['stars'] == 5.0, 'звёзды id=42 подтянуты в его строку')
check(res['days'] == 30, 'окно 30 дней в ответе')

print('== 3. API ==')
appmod = importlib.import_module('web.app')
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


check(client.get('/api/guild/777/staff-leaderboard').status_code in (302, 401, 403),
      'гостю API закрыто')
login('mod')
r = client.get('/api/guild/777/staff-leaderboard').get_json()
check(r.get('success') and r.get('mod_of_month') == 'Swift'
      and r['rows'][0]['score'] >= r['rows'][-1]['score'],
      'API отдаёт отсортированный рейтинг с короной')
r = client.get('/staff-rating')
html = r.get_data(as_text=True)
check(r.status_code == 200 and 'id="srLbTable"' in html
      and "'/staff-leaderboard'" in html and 'Модератор месяца' in html,
      'блок эффективности в шаблоне оценок персонала')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
