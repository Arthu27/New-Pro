# -*- coding: utf-8 -*-
"""Индекс здоровья сервера (services/health_index + панель дашборда).

Шесть взвешенных факторов (сумма 100), пустые данные = здорово/нейтрально,
больные факторы честно давят цифру, худший фактор даёт подсказку.

Запуск: python3 tests/test_health_index.py
"""
import importlib
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_health_test_')
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
from services import reports_core as RC  # noqa: E402
from services import health_index as HI  # noqa: E402

NOW = datetime.now(timezone.utc)
NOW_TS = time.time()

print('== 1. пустой сервер: здоров, факторы прозрачны ==')
h = HI.compute_health('777')
check(0 <= h['score'] <= 100 and h['score'] >= 70,
      f'пустой сервер не выглядит больным ({h["score"]})')
check(len(h['factors']) == 6 and abs(sum(f['max'] for f in h['factors']) - 100) < 1,
      'шесть факторов, веса дают ровно 100')
check(all(f['detail'] for f in h['factors']), 'каждый фактор объяснён строкой')
check(h['label'] and h['hint'] and h['tone'] in ('ok', 'info', 'warn', 'err'),
      'ярлык, подсказка и тон приезжают')

print('== 2. больные факторы давят индекс ==')
# апелляция висит давно (просрочка съедает вес очереди)
st = AP.empty_state()
st['settings'] = {'stale_hours': 1}
AP.create_appeal(st, 1, 'Ждун', 'жду решения уже неделю точно',
                 NOW - timedelta(days=7))
db = GuildData('appeals')
db.set('777', 'state', st)
# три активных наказания
json.dump({'777': {str(i): {'until': NOW_TS + 3600, 'reason': '', 'mod_id': '1'}
                   for i in (1, 2, 3)}}, open('data/temp_mutes.json', 'w'))
# два открытых репорта
RC.ticket_create('777', 'h1', '1', '2')
RC.ticket_create('777', 'h2', '1', '3')
# аудит есть, но в нём тишина
json.dump({'777': []}, open('data/audit_log.json', 'w'))

h2 = HI.compute_health('777')
by = {f['key']: f for f in h2['factors']}
check(by['appeals']['points'] < 1 and 'просрочено' in by['appeals']['detail'],
      f"просрочка почти обнуляет очередь ({by['appeals']['points']})")
check(by['punishments']['points'] == 14, 'три наказания = 20 - 6 баллов')
check(by['reports']['points'] == 5, 'два репорта = 15 - 10 баллов')
check(by['activity']['points'] == 0 and 'тишина' in by['activity']['detail'],
      'аудит есть, но пуст — активность честный ноль')
check(h2['score'] < h['score'], f'индекс упал ({h2["score"]} < {h["score"]})')
check(h2['hint'], 'подсказка куда смотреть есть')

# десяток свежих мод-действий возвращают активность на максимум
evs = [{'category': 'mod', 'action': 'mute', 'user_id': '1',
        'timestamp': NOW.isoformat()} for _ in range(10)]
json.dump({'777': evs}, open('data/audit_log.json', 'w'))
h3 = HI.compute_health('777')
by3 = {f['key']: f for f in h3['factors']}
check(by3['activity']['points'] == by3['activity']['max'],
      'десять действий за неделю — полный вес активности')
old = [{'category': 'mod', 'action': 'mute', 'user_id': '1',
        'timestamp': (NOW - timedelta(days=30)).isoformat()} for _ in range(10)]
json.dump({'777': old}, open('data/audit_log.json', 'w'))
h4 = HI.compute_health('777')
by4 = {f['key']: f for f in h4['factors']}
check(by4['activity']['points'] == 0, 'старые действия за окно недели не считаются')

# оценки команды поднимают фактор
sr = {'staff': {'55': {'votes': {'1': 5, '2': 4}, 'comments': []}}}
GuildData('staff_rating').set('777', 'state', sr)
h5 = HI.compute_health('777')
by5 = {f['key']: f for f in h5['factors']}
check(by5['staff']['points'] == 13.5 and 'из 5' in by5['staff']['detail'],
      f"средний 4.5 → 13.5 баллов ({by5['staff']['points']})")

print('== 3. веб ==')
appmod = importlib.import_module('web.app')
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


check(client.get('/api/dashboard/health').status_code in (302, 401, 403),
      'гостю API закрыто')
login('mod')
r = client.get('/api/dashboard/health').get_json()
check(r.get('success') and isinstance(r.get('health'), dict)
      and 'score' in r['health'] and len(r['health']['factors']) == 6,
      'API отдаёт индекс с факторами')
r = client.get('/dashboard')
html = r.get_data(as_text=True)
# п.2: SVG-дуги и полосы-факторы заменены числами (заказчика «без линий»)
check(r.status_code == 200 and 'srvHealthArc' not in html
      and 'hl-bar' not in html
      and 'id="srvHealthScore"' in html
      and 'id="srvHealthFactors"' in html and "'/api/dashboard/health'" in html,
      'индекс здоровья только числами — ни дуги, ни полос факторов')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
