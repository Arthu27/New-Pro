# -*- coding: utf-8 -*-
"""Пульс бота не морозит event-loop: диск в потоке, без makedirs на каждый тик.

Дамп до обновления (Windows, Downloads, Python 3.14):
  _bridge_loop → bot_bridge.write_state → os.makedirs
Event-loop стоял, пока антивирус сканировал папку. Шлюз Discord молчал.

Запуск: python3 tests/test_bridge_loop_off_loop.py
"""
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_bridge_loop_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== 1. _bridge_loop пишет диск через to_thread ==')
src = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
a = src.find('async def _bridge_loop')
b = src.find('\nasync def main()')
body = src[a:b]
check('asyncio.to_thread' in body and '_flush' in body,
      'запись пульса/ролей/каналов уходит в to_thread, не в цикл')
loop_part = body[body.find('while True'):]
check('_bb.write_state' not in loop_part,
      'while True не зовёт write_state напрямую')
check('os.makedirs(' not in body, '_bridge_loop сам не создаёт папки')

print('== 2. write_state не зовёт makedirs, если data/ уже есть ==')
from services import bot_bridge as BB  # noqa: E402

n = {'n': 0}
_real = BB.os.makedirs


def _spy(*a, **k):
    n['n'] += 1
    return _real(*a, **k)


BB.os.makedirs = _spy
try:
    BB._BASE_OK = False
    os.makedirs('data', exist_ok=True)
    n['n'] = 0  # свой makedirs не считаем (os — тот же модуль)
    ok = BB.write_state('online', latency_ms=12.0,
                        guilds=[{'id': '777', 'name': 'G', 'member_count': 3}],
                        force=True)
    check(ok, 'пульс записался')
    check(n['n'] == 0, f'data/ есть — makedirs не звали (было {n["n"]})')
    st = BB.read_state()
    check(st and st.get('status') == 'online' and st.get('latency_ms') == 12.0,
          'read_state видит свежий пульс')
    BB.write_state('online', force=True)
    check(n['n'] == 0, 'второй тик тоже без makedirs')
finally:
    BB.os.makedirs = _real

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
