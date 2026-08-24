# -*- coding: utf-8 -*-
"""Пачкователь логов (роли/ники): сливает события окна в один вызов,
не теряет раздельные окна, переживает пустые буферы.
Запуск: python3 tests/test_log_throttle.py"""
import asyncio
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_throttle_test_')
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


from services.log_throttle import Throttler  # noqa: E402

print('== 1. Пачка за одно окно -> один вызов фабрики ==')
flushes = []


async def factory(items):
    flushes.append(list(items))


async def scenario1():
    th = Throttler(window=0.20)
    key = (777, 'roles')
    th.feed(key, {'user_name': 'A'}, factory)
    th.feed(key, {'user_name': 'B'}, factory)
    th.feed(key, {'user_name': 'C'}, factory)
    await asyncio.sleep(0.45)
    return th


th1 = asyncio.run(scenario1())
check(len(flushes) == 1, f'одна отправка вместо трёх ({len(flushes)})')
check(len(flushes[0]) == 3, 'все 3 события доехали одной пачкой')
check([i['user_name'] for i in flushes[0]] == ['A', 'B', 'C'], 'порядок событий сохранён')
check(th1.pending((777, 'roles')) == 0, 'буфер очищен после отправки')

print('== 2. События после окна -> отдельная пачка ==')
flushes.clear()


async def scenario2():
    th = Throttler(window=0.15)
    key = (777, 'roles')
    th.feed(key, {'n': 1}, factory)
    await asyncio.sleep(0.35)
    th.feed(key, {'n': 2}, factory)
    await asyncio.sleep(0.35)


asyncio.run(scenario2())
check(len(flushes) == 2, f'два окна -> две отправки ({len(flushes)})')
check(flushes[0][0]['n'] == 1 and flushes[1][0]['n'] == 2, 'обе пачки одиночные и по порядку')

print('== 3. Разные ключи не путаются ==')
flushes.clear()


async def scenario3():
    th = Throttler(window=0.15)
    th.feed((777, 'roles'), {'k': 'r1'}, factory)
    th.feed((777, 'nick'), {'k': 'n1'}, factory)
    th.feed((888, 'roles'), {'k': 'r2'}, factory)
    await asyncio.sleep(0.4)


asyncio.run(scenario3())
check(len(flushes) == 3, f'три изолированные пачки ({len(flushes)})')
all_items = [i['k'] for batch in flushes for i in batch]
check(sorted(all_items) == ['n1', 'r1', 'r2'], f'каждый в своей пачке: {all_items}')

print('== 4. Фабрика упала — страдает только она ==')
booms = []


async def bad_factory(items):
    booms.append(len(items))
    raise RuntimeError('discord offline')


async def scenario4():
    th = Throttler(window=0.10)
    th.feed('x', {'z': 1}, bad_factory)
    await asyncio.sleep(0.3)
    return th


th4 = asyncio.run(scenario4())  # не должно кинуть
check(booms == [1], 'фабрика вызвана один раз')
check(th4.pending('x') == 0, 'буфер сброшен даже после падения фабрики')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
