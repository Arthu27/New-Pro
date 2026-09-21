# -*- coding: utf-8 -*-
"""Voice keep-alive не должен блокировать asyncio-цикл.

Жалоба 2026-09-18: EVENT-LOOP ЗАВИСАНИЕ 6.8 сек, стек:
  main._monitor_voice → vc.play → Thread.start → _started.wait

``discord.VoiceClient.play`` синхронно ждёт старт AudioPlayer — на loop
это зависание. Проверяем: play → to_thread (+ wait_for), connect → wait_for.

Запуск: python3 tests/test_voice_monitor_no_block.py
"""
import ast
import asyncio
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


def _call_name(node):
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ''


print('== _monitor_voice: play не на event loop ==')
src_path = os.path.join(ROOT, 'main.py')
src = open(src_path, encoding='utf-8').read()
tree = ast.parse(src)

fn = None
for node in tree.body:
    if isinstance(node, ast.AsyncFunctionDef) and node.name == '_monitor_voice':
        fn = node
        break

check(fn is not None, '_monitor_voice найдена')
body = ast.get_source_segment(src, fn) if fn else ''
doc = ast.get_docstring(fn) or ''

check('to_thread' in body, 'play уходит в to_thread')
check('wait_for' in body and 'connect' in body,
      'connect обёрнут в wait_for (таймаут)')
check('wait_for' in body and 'to_thread' in body,
      'play: wait_for(to_thread(...))')
check('vc.play(' not in body.replace('to_thread(vc.play', ''),
      'нет голого vc.play( вне to_thread')
# проще по строкам
bad = [ln.strip() for ln in body.splitlines()
       if 'vc.play(' in ln and 'to_thread' not in ln]
check(not bad, f'строки без to_thread рядом с vc.play: {bad}')
check('to_thread' in doc or 'EVENT-LOOP' in doc,
      'докстринг объясняет зависание')

# AST: to_thread(vc.play) существует внутри функции
class _Finder(ast.NodeVisitor):
    def __init__(self):
        self.threaded_play = 0
        self.wait_for_connect = 0
        self.wait_for_play = 0
        self.bare_play = 0

    def visit_Call(self, node):
        name = _call_name(node.func)
        if name == 'to_thread':
            for arg in node.args:
                if (isinstance(arg, ast.Attribute) and arg.attr == 'play'):
                    self.threaded_play += 1
        if name == 'wait_for' and node.args:
            inner = node.args[0]
            if isinstance(inner, ast.Call):
                iname = _call_name(inner.func)
                if iname == 'connect' or (
                        isinstance(inner.func, ast.Attribute)
                        and inner.func.attr == 'connect'):
                    self.wait_for_connect += 1
                if iname == 'to_thread':
                    self.wait_for_play += 1
        if (isinstance(node.func, ast.Attribute) and node.func.attr == 'play'
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == 'vc'):
            # Call(vc.play) — ок только как arg to_thread; иначе bare
            # Проверим родителя нельзя здесь — считаем через threaded_play
            self.bare_play += 1
        self.generic_visit(node)


if fn:
    f = _Finder()
    f.visit(fn)
    check(f.threaded_play >= 1, f'to_thread(vc.play) в AST ({f.threaded_play})')
    check(f.wait_for_connect >= 1,
          f'wait_for(connect) в AST ({f.wait_for_connect})')
    check(f.wait_for_play >= 1,
          f'wait_for(to_thread(play)) в AST ({f.wait_for_play})')
    check(f.bare_play == 0,
          f'нет вызова vc.play(...) — только ссылка в to_thread '
          f'(bare={f.bare_play})')

print('== нет других vc.play в репозитории ==')
other = []
for dirpath, _dns, files in os.walk(ROOT):
    if any(x in dirpath for x in ('/.git', '/__pycache__', '/.venv', '/venv',
                                    '/node_modules', '/tests')):
        continue
    for fnm in files:
        if not fnm.endswith('.py'):
            continue
        path = os.path.join(dirpath, fnm)
        try:
            text = open(path, encoding='utf-8').read()
        except OSError:
            continue
        if 'vc.play(' in text or '.play(source)' in text:
            if path.endswith('main.py') and '_monitor_voice' in text:
                continue
            other.append(os.path.relpath(path, ROOT))
check(not other, f'других play(source) нет ({other})')

print('== runtime: блокирующий play через to_thread не стопорит loop ==')


async def _sim():
    def blocking_play(_src=None):
        time.sleep(0.35)

    ticks = 0

    async def ticker():
        nonlocal ticks
        while ticks < 5:
            await asyncio.sleep(0.05)
            ticks += 1

    task = asyncio.create_task(ticker())
    await asyncio.wait_for(asyncio.to_thread(blocking_play, object()),
                           timeout=15.0)
    await task
    return ticks


ticks = asyncio.run(_sim())
check(ticks >= 5, f'ticker успел 5 тиков пока play «висел» ({ticks})')

print('== runtime: wait_for рвёт вечный play ==')


async def _sim_timeout():
    def forever(_src=None):
        time.sleep(60)

    t0 = time.monotonic()
    try:
        await asyncio.wait_for(asyncio.to_thread(forever, object()),
                               timeout=0.2)
        return False, time.monotonic() - t0
    except asyncio.TimeoutError:
        return True, time.monotonic() - t0


ok_to, elapsed = asyncio.run(_sim_timeout())
check(ok_to, 'wait_for даёт TimeoutError')
check(elapsed < 2.0, f'timeout сработал быстро ({elapsed:.2f}s)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
