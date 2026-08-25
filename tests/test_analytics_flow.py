# -*- coding: utf-8 -*-
"""Аналитика сервера: поток данных «сообщение → статистика → панель».

Жалоба владельца (2026-08-25): «данные не загружаются, я пишу, но не
работает». Причина: панель читает data/message_logs_<gid>.json, который
бот никогда не писал. Проверяем сборщик, файл, скользящее окно и то,
 что API аналитики реально наполняется живыми событиями.

Запуск: python3 tests/test_analytics_flow.py
"""
import importlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_anflow_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'owner'
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


print('== 1. Сборщик message_stats ==')
from services import message_stats as MS  # noqa: E402

check(MS.record('777', 'Мира', 'флудилка') is True, 'record принимает событие')
check(MS.pending_count() >= 1, 'событие копится в буфере (без мгновенной записи)')
MS.record('777', '', 'флудилка')
check(MS.pending_count() >= 1, 'пустой автор не ломит буфер и не пишется')
MS.flush_all()
_p = 'data/message_logs_777.json'
check(os.path.exists(_p), 'flush_all создаёт message_logs_777.json')
_rows = json.load(open(_p, encoding='utf-8'))
check(any(r.get('author') == 'Мира' for r in _rows), 'автор записан')
check(all(set(r) == {'author', 'channel', 'timestamp'} for r in _rows),
      'только метаданные — ТЕКСТ сообщения не сохраняется (приватность)')
check(MS.pending_count() == 0, 'после flush буфер пуст')

print('== 2. Скользящее окно (файл не растёт вечно) ==')
_now = datetime.now(timezone.utc)
for i in range(MS.MAX_PER_GUILD + 500):        # старые → новые, как в жизни
    MS.record('555', f'u{i}', 'общий', _now - timedelta(seconds=MS.MAX_PER_GUILD + 500 - i))
MS.flush_all()
_rows5 = json.load(open('data/message_logs_555.json', encoding='utf-8'))
check(len(_rows5) == MS.MAX_PER_GUILD,
      f'окно {MS.MAX_PER_GUILD} держится (было записано {MS.MAX_PER_GUILD + 500})')
check(_rows5[0]['author'] == 'u500', 'старейшие события вытеснены, свежие на месте')

print('== 3. Панель: аналитика наполняется из живых событий ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'

os.remove('data/message_logs_777.json')
_today = datetime.now(timezone.utc)
for i, day in enumerate(range(6, -1, -1)):
    for k in range((i + 1) * 3):     # разгон: 3..21 сообщение в день
        MS.record('777', ['Мира', 'Гром', 'Лина'][k % 3],
                  ['флудилка', 'мемы'][k % 2], _today - timedelta(days=day))
MS.flush_all()
r = client.get('/api/guild/777/analytics')
d = r.get_json() or {}
check(r.status_code == 200 and sum(d.get('daily_messages', [])) > 0,
      'график «сообщения/день» больше не нулевой — «я пишу» видно')
check(sum(d.get('daily_messages', [])) == 84, 'все 84 сообщения посчитаны')
check(any(m['name'] == 'Мира' for m in d.get('top_members', [])),
      'топ участников наполняется')
check(any(c['name'] == 'флудилка' for c in d.get('top_channels', [])),
      'топ каналов наполняется')

r = client.get('/api/guild/777/analytics/heatmap')
h = r.get_json() or {}
check(h.get('total', 0) == 84, 'теплокарта видит те же события')
r = client.get('/api/guild/777/analytics/week-summary')
w = r.get_json() or {}
check(w.get('week_msgs', 0) == 84, 'сводка недели считает сообщения')

print('== 4. Ког-слушатель и шаблон ==')
src = open(os.path.join(ROOT, 'cogs/activity_stats.py'), encoding='utf-8').read()
check('on_message' in src and 'message_stats.record' in src,
      'ког слушает on_message и пишет в сборщик')
check('author.bot' in src and 'webhook_id' in src and 'message.guild' in src,
      'боты, вебхуки и ЛС не считаются')
tpl = open(os.path.join(ROOT, 'web/templates/analytics.html'), encoding='utf-8').read()
check('anEmptyHint' in tpl and 'Пока тишина' in tpl,
      'при пустых данных — человеческая подсказка вместо пустых нулей')
check("_eh.style.display = _hasData ? 'none' : ''" in tpl,
      'подсказка исчезает, как только появляются реальные данные')
main_src = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
check('cogs_policy' in main_src and 'os.listdir("./cogs")' in main_src,
      'ког подхватится автозагрузкой cogs/ (отдельной регистрации не нужно)')

MS.stop()
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
