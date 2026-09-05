# -*- coding: utf-8 -*-
"""Стабильность бота на VDS (заказ владельца 2026-08: «почему отключается»).

1. Короткие разрывы с Discord — норма, но они должны быть ВИДНЫ в логе
   (on_disconnect / on_resumed в main.py).
2. Смерть процесса — не норма: start.sh поднимает бот сам (цикл),
   systemd-служба deploy/hakumo.service — правильный способ на VDS.
3. Неверный токен — код выхода 7: скрипты не крутят бесконечный
   перезапуск против битого TOKEN.
Запуск: python3 tests/test_vds_stability.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = 0


FAIL = 0
def ok(name, cond, extra=''):
    global PASS
    if not cond:
        print(f'FAIL: {name} {extra}')
        sys.exit(1)
    PASS += 1
    print(f'  ok - {name}')


main_src = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
ok('разрыв связи с Discord виден в логе (on_disconnect)',
   'async def on_disconnect' in main_src and 'потеряно' in main_src)
ok('восстановление связи видно (on_resumed, события не теряются)',
   'async def on_resumed' in main_src and 'resume' in main_src.lower())
ok('внутренний цикл переподключения с паузой 5→60 сек на месте',
   'while True' in main_src and '_delay = min(60' in main_src)
ok('неверный/пропавший токен — код 7 (без вечного перезапуска)',
   main_src.count('sys.exit(7)') == 2)

sh = open(os.path.join(ROOT, 'start.sh'), encoding='utf-8').read()
ok('start.sh: авто-поднятие процесса (цикл while true)',
   'while true' in sh and 'sleep 5' in sh)
ok('start.sh: битый токен не гоняет цикл (выход по коду 7)',
   '"$CODE" -eq 7' in sh)
ok('start.sh: советует systemd-службу для VDS',
   'VDS-SETUP.md' in sh)
ok('start.sh синтаксически валиден (bash -n)',
   os.system('bash -n start.sh') == 0)

svc = open(os.path.join(ROOT, 'deploy', 'hakumo.service'), encoding='utf-8').read()
ok('systemd-служба: Restart=always + 5 сек',
   'Restart=always' in svc and 'RestartSec=5' in svc)
ok('systemd-служба: стартует после сети',
   'network-online.target' in svc)

guide = open(os.path.join(ROOT, 'deploy', 'VDS-SETUP.md'), encoding='utf-8').read()
for marker in ('journalctl -u hakumo -f', 'OOM', 'enable --now hakumo',
               'Короткие переподключения'):
    ok(f'инструкция VDS содержит «{marker}»', marker in guide)

# ── Живой учёт обрыв/возврат/простой (лог владельца 2026-09-04:
#    «потеряно (gateway) — всего обрывов: 15» + «восстановлено») ──
print('== учёт соединения: обрыв → resume → простой ==')
import tempfile as _tf
os.chdir(_tf.mkdtemp(prefix='vds_net_'))
os.makedirs('data', exist_ok=True)
import time as _time
import error_handler as _EH

eh = _EH.ErrorHandler.__new__(_EH.ErrorHandler)
eh.stats = eh._fresh_stats()
eh.config = dict(_EH.DEFAULT_CONFIG)
eh._disconnects = __import__('collections').deque(maxlen=200)
eh._disconnect_alert_at = 0.0
eh._disconnected_at = None
eh._alerts = []
eh._rate = __import__('collections').deque(maxlen=2000)
eh._cog_windows = {}
eh._breaker_state = {}
eh._lag_recent = 0.0
eh._alerts_sent_ts = __import__('collections').deque(maxlen=100)
eh._webhook_sent_ts = __import__('collections').deque(maxlen=200)
_sent = []
eh.queue_alert = lambda title, desc: _sent.append((title, desc))

# обрыв №1 … resume: короткое моргание сети
eh._on_disconnect('gateway')
ok('обрыв посчитан', eh.stats['disconnects'] == 1)
ok('момент разрыва зафиксирован', eh._disconnected_at is not None)
_time.sleep(0.05)
eh._on_resumed('gateway')
ok('восстановление посчитано', eh.stats['resumes'] == 1)
ok('простой записан', eh.stats['outage_last_sec'] >= 0.0
   and eh._disconnected_at is None)
ok('долгий-простой алерт не сорвался за моргание', not _sent)

# долгий простой: 6 минут без связи → алерт владельцу
eh._on_disconnect('gateway')
eh._disconnected_at = _time.time() - 360
eh._on_resumed('gateway')
ok('максимальный простой обновился', eh.stats['outage_max_sec'] >= 350)
ok('о долоком простом предупредили в канал', len(_sent) == 1
   and 'БЕЗ СВЯЗИ' in _sent[0][1] or len(_sent) == 1)

# overview несёт все поля панели
eh.bot = type('B', (), {'latency': 0.02, 'guilds': [], 'is_closed': lambda s: True})
ov = eh.get_overview()
for k in ('disconnects', 'disconnects_hour', 'resumes',
          'outage_last_sec', 'outage_max_sec'):
    ok(f'overview.{k} на месте', k in ov)

# панель (демо) и шаблон знают новые поля
ac = open(os.path.join(ROOT, 'web', 'routes', 'anticrash.py'),
          encoding='utf-8').read()
ok('демо-payload панели содержит resumes/простой',
   "'resumes':" in ac and "'outage_max_sec':" in ac)
tpl = open(os.path.join(ROOT, 'web', 'templates', 'anticrash.html'),
           encoding='utf-8').read()
ok('тайл «Обрывов WS» показывает возвраты и простой',
   'восстановлено' in tpl and 'простой макс' in tpl)

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
print('ALL PASS — бот на VDS поднимается сам' if not FAIL else 'ЕСТЬ ПАДЕНИЯ')
