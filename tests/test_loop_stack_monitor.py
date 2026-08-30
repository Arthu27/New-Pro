# -*- coding: utf-8 -*-
"""Тесты потокового монитора стека event-loop (СТЕК ВИНОВНИКА).

Проблема с VDS: «EVENT-LOOP ЗАВИСАНИЕ: цикл не отвечал 5.9–12.7 сек» ×5.
Async-watchdog замечает зависание ТОЛЬКО ПОСЛЕ отвисания — стек виновника
уже вернулся, в логе только цифра. Потоковый монитор (daemon-поток
loop-stack-monitor + пульс _loop_beat) снимает стек main-потока ПРЯМО
В МОМЕНТ зависания — следующий инцидент станет диагностируемым.

Запуск: python3 tests/test_loop_stack_monitor.py
"""
import logging
import os
import re
import sys
import tempfile
import threading
import time

_TMP = tempfile.mkdtemp(prefix='hakumo_stack_mon_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from error_handler import ErrorHandler  # noqa: E402

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


class FakeBot:
    guilds = []
    latency = 0.05

    def is_closed(self):
        return False


# Ловим CRITICAL-записи логгера «errors» (туда пишет и watchdog, и монитор)
class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.CRITICAL)
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())


_cap = _Capture()
_errors_logger = logging.getLogger('errors')
if not _errors_logger.handlers and not logging.getLogger().handlers:
    # В тестовом окружении логгер может быть без хендлеров — добавляем
    # свой, чтобы записи не терялись в /dev/null.
    _errors_logger.addHandler(logging.NullHandler())
_errors_logger.addHandler(_cap)


print('== Монитор стека: инстанцирование ==')
eh = ErrorHandler(FakeBot())

check(hasattr(eh, '_loop_beat') and hasattr(eh, '_stack_frozen'),
      'ErrorHandler: появились _loop_beat/_stack_frozen (пульс монитора)')
check(any(t.name == 'loop-stack-monitor' for t in threading.enumerate()),
      'daemon-поток loop-stack-monitor запущен вместе с ErrorHandler')
check(eh._stack_frozen is False,
      'исходно _stack_frozen=False (цикл не считаем зависшим)')
_thresh = float(eh.config.get('loop_lag_threshold', 5.0)) + 1.0
print(f'  (порог срабатывания монитора: {_thresh:.1f} сек '
      f'= loop_lag_threshold({eh.config.get("loop_lag_threshold", 5.0)}) + 1)')

print('\n== Монитор стека: зависание 10 сек (пульс замер) ==')
_cap.records.clear()
# Имитируем блокировку event-loop: пульс не обновляется 10 секунд,
# а main-поток (он же «виновник») стоит в time.sleep этого теста.
eh._loop_beat = time.monotonic() - 10.0
time.sleep(3.0)  # поток опрашивает пульс раз в 1 сек

check(eh._stack_frozen is True,
      'пульс замер дольше порога -> _stack_frozen=True (монитор увидел)')
_crits = [r for r in _cap.records if 'СТЕК ВИНОВНИКА' in r]
check(len(_crits) == 1,
      'ровно ОДНА CRITICAL-запись за одно зависание (без спама)')
if _crits:
    _msg = _crits[0]
    check('EVENT-LOOP ЗАВИСАНИЕ' in _msg
          and re.search(r'\d+\.\d+ сек', _msg),
          'в записи есть длительность зависания (сек)')
    check('СТЕК ВИНОВНИКА' in _msg and 'main-поток' in _msg,
          'запись помечена «СТЕК ВИНОВНИКА (main-поток)»')
    check('test_loop_stack_monitor.py' in _msg,
          'в стеке — РЕАЛЬНЫЙ кадр виновника (файл этого теста, time.sleep)')
    check('File "' in _msg and ', line ' in _msg,
          'стек отформатирован с файлом и номером строки')

print('\n== Монитор стека: восстановление и повторное зависание ==')
eh._loop_beat = time.monotonic()  # «отвисло» — пульс снова тикает
time.sleep(2.0)
check(eh._stack_frozen is False,
      'пульс ожил -> _stack_frozen сброшен (готов к новому инциденту)')

_cap.records.clear()
eh._loop_beat = time.monotonic() - 10.0
time.sleep(3.0)
_crits2 = [r for r in _cap.records if 'СТЕК ВИНОВНИКА' in r]
check(len(_crits2) == 1,
      'второе зависание снова даёт ровно одну запись со стеком')

print('\n== Монитор стека: живой пульс не даёт ложных срабатываний ==')
_cap.records.clear()
eh._loop_beat = time.monotonic()
time.sleep(2.5)  # пульс свежий, зависания нет
check(eh._stack_frozen is False
      and not [r for r in _cap.records if 'СТЕК ВИНОВНИКА' in r],
      'живой пульс -> ни флага, ни CRITICAL (false positive нет)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
