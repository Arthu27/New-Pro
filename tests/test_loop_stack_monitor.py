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
check(any('GC в момент зависания' in r and 'полных сборок' in r
          for r in _cap.records),
      'дамп зависания содержит дешёвые GC-счётчики (корреляция с сборками)')

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

print('\n== GC-проба: каждая сборка мусора измеряется ==')
import error_handler as eh2

# новые пробы пишут в логгер error_handler — своя капча для него
_eh_cap = _Capture()
_eh_log = logging.getLogger('error_handler')
_eh_log.addHandler(_eh_cap)
_eh_cap.records.clear()
eh2._gc_probe('start', {'generation': 2})
check(eh2._gc_probe_t0.get('t0') is not None,
      'фаза start фиксирует момент начала сборки')
# сборка шла 3.4 сек -> CRITICAL с поколением
eh2._gc_probe_t0['t0'] -= 3.4
eh2._gc_probe('stop', {'generation': 2})
_gc_crit = [r for r in _eh_cap.records if 'GC' in r and 'СБОРКА' in r]
check(len(_gc_crit) == 1 and 'поколение 2' in _gc_crit[0],
      'сборка ≥2с -> CRITICAL «GC СБОРКА … поколение 2» (виновник назван)')
# короткая сборка - молчим
_eh_cap.records.clear()
eh2._gc_probe('start', {'generation': 0})
eh2._gc_probe('stop', {'generation': 0})
check(not [r for r in _eh_cap.records if 'СБОРКА' in r],
      'быстрая сборка мусора -> тишина (нет спама)')
# stop без start (коллбек прицепился посреди) - не падает
eh2._gc_probe('stop', {'generation': 1})
check(True, 'stop без start не бросает исключений')

print('\n== asyncio-детектор: медленный callback называется по имени ==')
import logging as _lg

_promote = eh2._AsyncioSlowPromote()
_eh_cap.records.clear()
_rec = _lg.LogRecord('asyncio', _lg.DEBUG, 'x', 1,
                     'Executing <Handle Task-9 step> took 6.5 seconds',
                     None, None)
_promote.emit(_rec)
check(len(_eh_cap.records) == 1 and 'МЕДЛЕННЫЙ CALLBACK' in _eh_cap.records[0]
      and 'Task-9' in _eh_cap.records[0],
      '«took 6.5 seconds» -> CRITICAL с именем callback (Task-9)')
_eh_cap.records.clear()
_promote.emit(_lg.LogRecord('asyncio', _lg.DEBUG, 'x', 1,
                            'Using selector: EpollSelector', None, None))
check(not _eh_cap.records,
      'обычный DEBUG-шум asyncio глотается (консоль чистая)')

_root_cap = []
class _RootCap(_lg.Handler):
    def emit(self, record):
        _root_cap.append(record.getMessage())
_h = _RootCap()
_lg.getLogger().addHandler(_h)
_promote.emit(_lg.LogRecord('asyncio', _lg.WARNING, 'x', 1,
                            'socket.send() raised exception.', None, None))
_lg.getLogger().removeHandler(_h)
check(len(_root_cap) == 1 and 'socket.send()' in _root_cap[0],
      'WARNING asyncio честно уходит в корневой логгер')

print('\n== install_loop_probes: цикл получает обе пробы ==')
import asyncio as _aio
import gc as _gc
import os as _os

# Боевой режим: ПОЛНЫЙ debug asyncio ВЫКЛЮЧЕН по умолчанию (его захват
# source-traceback на каждый таймер давал паузы 6–10с на медленном
# диске/антивирусе — инцидент 30.08). Пробы (gc.callbacks + хендлер +
# stack-monitor) при этом ставятся всегда.
_os.environ.pop('ASYNCIO_DEBUG', None)
_loop = _aio.new_event_loop()
_loop.set_debug(True)   # симулируем «debug уже был включён»
_before_cb = len(_gc.callbacks)
eh2.install_loop_probes(_loop)
check(_loop.get_debug() is False,
      'по умолчанию полный debug-режим asyncio ВЫКЛЮЧЕН (нет дорогих '
      'source-traceback/linecache на каждый таймер)')
check(eh2._gc_probe in _gc.callbacks,
      'gc-проба зарегистрирована в gc.callbacks (работает без debug)')
_aio_log = _lg.getLogger('asyncio')
check(any(isinstance(h, eh2._AsyncioSlowPromote) for h in _aio_log.handlers)
      and _aio_log.propagate is False,
      'хендлер промоции стоит, DEBUG-шум не утекает в консоль')

# Флаг ASYNCIO_DEBUG=1 возвращает полный debug для глубокой отладки.
_loop2 = _aio.new_event_loop()
_os.environ['ASYNCIO_DEBUG'] = '1'
eh2.install_loop_probes(_loop2)
check(_loop2.get_debug() is True and _loop2.slow_callback_duration == 2.0,
      'ASYNCIO_DEBUG=1 — полный debug включён, порог callback = 2.0 сек')
_os.environ.pop('ASYNCIO_DEBUG', None)

# повторный вызов не дублирует хендлеры и коллбеки
_n_h = sum(isinstance(h, eh2._AsyncioSlowPromote) for h in _aio_log.handlers)
eh2.install_loop_probes(_loop)
_n_h2 = sum(isinstance(h, eh2._AsyncioSlowPromote) for h in _aio_log.handlers)
check(_n_h2 == _n_h == 1 and _gc.callbacks.count(eh2._gc_probe) == 1,
      'повторная установка идемпотентна (без дублей)')
# уборка за тестом
_aio_log.handlers = [h for h in _aio_log.handlers
                     if not isinstance(h, eh2._AsyncioSlowPromote)]
_aio_log.propagate = True
_gc.callbacks.remove(eh2._gc_probe)
_loop.close()
_loop2.close()

print('\n== gc_stabilize: паузы GC лечатся ==')
_ok = eh2.gc_stabilize()
check(_ok is True and _gc.get_threshold() == eh2.GC_THRESHOLDS
      and eh2.GC_THRESHOLDS == (50_000, 5_000, 5_000),
      'стартовый граф заморожен, пороги 50000/5000/5000 (автоген2 убран)')

print('\n== environment_warnings: три ловушки среды запуска ==')
_w = eh2.environment_warnings(
    r'C:\Users\Administrator\Downloads\New-Pro-x\New-Pro-x', (3, 14, 0))
check(any('Downloads' in w for w in _w)
      and any('ВЛОЖЕННОЙ' in w for w in _w)
      and any('3.14' in w for w in _w),
      'Downloads + вложенная папка + Python 3.14 -> все три предупреждения')
_w2 = eh2.environment_warnings('C:\\Hakumo', (3, 12, 8))
check(_w2 == [],
      'C:\\Hakumo на Python 3.12 -> чисто (ложных тревог нет)')
_w3 = eh2.environment_warnings(r'D:\Bot\app', (3, 13, 1))
check(_w3 == [], 'обычная папка + 3.13 -> без предупреждений')
_w4 = eh2.environment_warnings(
    '/home/user/Downloads/bot', (3, 12, 0))
check(any('Downloads' in w for w in _w4),
      'Linux-путь с Downloads тоже подсвечивается')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
