# -*- coding: utf-8 -*-
"""Регрессы страницы «Аналитика сервера» (жалоба владельца: «работает неправильно»).

Два исправленных бага данных:

1. load_message_events() раньше читала ЛИБО audit_log, ЛИБО message_logs
   (фолбэк «если audit не пуст — logs не читаем»). Одного старого audit-сообщения
   хватало, чтобы весь message_logs (тысячи реальных сообщений) проигнорировался:
   теплокарта, недельная сводка, рекорды и детализация каналов выходили пустыми.
   Теперь источники ОБЪЕДИНЯЮТСЯ с дедупом.

2. Реконструкция ряда «число участников» в community.py считалась формулой со
   срезом joins[i:]/leaves[i:] и давала сдвиг на день. Теперь — пошаговая
   обратная реконструкция member_count_series(); при недоступном member_count
   (бот офлайн) рисуется честная относительная динамика, а не выдуманные числа.

Запуск: python3 tests/test_analytics_data_fixes.py
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_anfix_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

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


from web.routes import analytics_plus as AP  # noqa: E402

GID = '777'
now = datetime.now(timezone.utc)


def iso(days_ago, hour=12):
    d = now - timedelta(days=days_ago)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


print('== 1. Объединение источников сообщений (баг «нижние блоки пустые») ==')

# message_logs: 50 реальных сообщений
msgs = [
    {'author': ['Аня', 'Боря', 'Вера', 'Гена'][i % 4],
     'channel': ['общ', 'мемы', 'помощь'][i % 3],
     'timestamp': iso(i % 10, 8 + i % 14)}
    for i in range(50)
]
with open(f'data/message_logs_{GID}.json', 'w', encoding='utf-8') as fh:
    json.dump(msgs, fh, ensure_ascii=False)

# audit: ОДНО старое message-событие + не-message события
audit = {GID: [
    {'category': 'message', 'action': 'message написано', 'user_name': 'Старый',
     'channel': 'архив', 'timestamp': iso(40)},
    {'category': 'member', 'action': 'Участник вошёл', 'user_name': 'Н',
     'timestamp': iso(1)},
    {'category': 'voice', 'action': 'Зашёл в голосовой', 'user_name': 'Аня',
     'channel': 'Г1', 'timestamp': iso(1, 20)},
]}
with open('data/audit_log.json', 'w', encoding='utf-8') as fh:
    json.dump(audit, fh, ensure_ascii=False)

events = AP.load_message_events(GID)
check(len(events) == 51,
      f'видны И message_logs (50), И audit-сообщение (1) — всего {len(events)}, не 1')

hm = AP.heatmap_matrix(events)
check(hm['total'] == 51, f'теплокарта считает все события (total={hm["total"]})')

ws = AP.week_summary(events)
check(ws['week_msgs'] > 0, f'недельная сводка не нулевая (week_msgs={ws["week_msgs"]})')

cd = AP.channel_drill(events, 'общ')
check(cd['total'] > 0 and cd['unique_authors'] > 0,
      f'детализация канала «общ» не пустая (total={cd["total"]})')

recs = AP.record_days(events)
check(len(recs) > 0, 'рекордные дни определяются')

print('== 2. Дедуп совпадений audit↔logs (без двойного счёта) ==')
# Точная копия одного logs-сообщения в audit не должна задвоиться.
dup_ts = msgs[0]['timestamp']
with open('data/audit_log.json', 'w', encoding='utf-8') as fh:
    json.dump({GID: [
        {'category': 'message', 'action': 'message написано',
         'user_name': msgs[0]['author'], 'channel': msgs[0]['channel'],
         'timestamp': dup_ts},
    ]}, fh, ensure_ascii=False)
events2 = AP.load_message_events(GID)
check(len(events2) == 50,
      f'дубль того же автора/канала/секунды не задвоен (событий {len(events2)}, не 51)')

print('== 3. member_count_series — корректная пошаговая реконструкция ==')
# 7 дней, индекс 6 = сегодня. joins: день4=1, день5=1; leaves: день3=1.
flow = {'joins': [0, 0, 0, 0, 1, 1, 0],
        'leaves': [0, 0, 0, 1, 0, 0, 0]}
series = AP.member_count_series(100, flow, days=7)
# Эталон обратным ходом: [99,99,99,98,99,100,100]
check(series == [99, 99, 99, 98, 99, 100, 100],
      f'ряд участников без сдвига на день: {series}')
check(series[-1] == 100, 'последняя точка = текущее число участников (сегодня)')
check(all(v >= 0 for v in series), 'ряд не уходит в минус')

# Нет событий — линия ровная на текущем уровне.
flat = AP.member_count_series(250, {'joins': [0] * 7, 'leaves': [0] * 7}, days=7)
check(flat == [250] * 7, f'без приходов/уходов линия ровная: {flat}')

print('== 4. Относительная динамика при mc=0 (бот офлайн) ==')
# community.py при недоступном member_count берёт member_count_series(0,...) и
# нормирует к последней точке — получаем относительные дельты, а не [1,1,1,0,0,0].
rel = AP.member_count_series(0, flow, days=7)
base = rel[-1]
norm = [v - base for v in rel]
check(norm[-1] == 0, f'сегодня = 0 (точка отсчёта относительной динамики): {norm}')
check(max(norm) >= 1 and min(norm) <= 0,
      f'относительный ряд показывает и приходы, и уходы: {norm}')

print('== 5. member_flow по-прежнему считает приходы/уходы ==')
with open('data/audit_log.json', 'w', encoding='utf-8') as fh:
    json.dump({GID: [
        {'category': 'member', 'action': 'Участник вошёл', 'user_name': 'Н1',
         'timestamp': iso(2)},
        {'category': 'member', 'action': 'Участник вошёл', 'user_name': 'Н2',
         'timestamp': iso(1)},
        {'category': 'member', 'action': 'Участник вышел', 'user_name': 'У1',
         'timestamp': iso(3)},
    ]}, fh, ensure_ascii=False)
mf = AP.member_flow(GID, days=7)
check(mf['joined_total'] == 2 and mf['left_total'] == 1 and mf['net'] == 1,
      f"member_flow: пришло {mf['joined_total']}, ушло {mf['left_total']}, net {mf['net']}")

print()
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
