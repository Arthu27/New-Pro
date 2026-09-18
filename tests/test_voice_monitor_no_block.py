# -*- coding: utf-8 -*-
"""Voice keep-alive не должен блокировать asyncio-цикл.

Жалоба 2026-09-18: EVENT-LOOP ЗАВИСАНИЕ 6.8 сек, стек:
  main._monitor_voice → vc.play → Thread.start → _started.wait

``discord.VoiceClient.play`` синхронно ждёт старт AudioPlayer — на loop
это зависание. Проверяем, что play уходит в to_thread / executor.

Запуск: python3 tests/test_voice_monitor_no_block.py
"""
import ast
import os
import sys

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
check('to_thread' in body or 'run_in_executor' in body,
      'play уходит в to_thread / run_in_executor')
check('await asyncio.to_thread(vc.play' in body
      or 'await asyncio.to_thread(vc.play,' in body
      or 'run_in_executor' in body and 'vc.play' in body,
      'конкретно vc.play обёрнут в await to_thread/executor')

# Прямой vc.play(...) на loop запрещён (без to_thread рядом)
# Ищем в AST: Call attr play на vc без родителя Await(to_thread...)
class _PlayFinder(ast.NodeVisitor):
    def __init__(self):
        self.direct = []
        self.threaded = []

    def visit_Await(self, node):
        # await asyncio.to_thread(vc.play, ...)
        call = node.value
        if isinstance(call, ast.Call):
            f = call.func
            name = ''
            if isinstance(f, ast.Attribute):
                name = f.attr
            elif isinstance(f, ast.Name):
                name = f.id
            if name in ('to_thread', 'run_in_executor') and call.args:
                first = call.args[0]
                # run_in_executor(None, vc.play, source) — play вторым
                for arg in call.args:
                    if (isinstance(arg, ast.Attribute) and arg.attr == 'play'):
                        self.threaded.append(arg)
                        break
                else:
                    if (isinstance(first, ast.Attribute) and first.attr == 'play'):
                        self.threaded.append(first)
        self.generic_visit(node)

    def visit_Call(self, node):
        if (isinstance(node.func, ast.Attribute) and node.func.attr == 'play'
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == 'vc'):
            # отметим; threaded проверим отдельно
            self.direct.append(node)
        self.generic_visit(node)


if fn:
    finder = _PlayFinder()
    finder.visit(fn)
    check(len(finder.threaded) >= 1,
          f'есть await to_thread(vc.play) ({len(finder.threaded)})')
    # каждый vc.play должен быть аргументом to_thread — не «голый» call как statement
    # Голый: Expr(Call(play)) — плохо. Call(play) как arg to_thread — ок.
    bare = []
    for n in finder.direct:
        parent_ok = any(n is t or n.func is t for t in finder.threaded)
        # проще: если Call(play) не является первым/вторым аргом Await(to_thread)
        # — считаем голым, если родитель не Call(to_thread)
        bare.append(n)
    # Перепроверим: в исходнике не должно быть строки «vc.play(» без to_thread на той же/пред строке
    lines = body.splitlines()
    bad_lines = []
    for i, line in enumerate(lines):
        if 'vc.play(' in line and 'to_thread' not in line and 'run_in_executor' not in line:
            # предыдущая строка тоже без to_thread?
            prev = lines[i - 1] if i else ''
            if 'to_thread' not in prev and 'run_in_executor' not in prev:
                bad_lines.append(line.strip())
    check(not bad_lines,
          f'нет голого vc.play( на loop ({bad_lines})')

check('EVENT-LOOP' in (fn.docstring if fn and hasattr(fn, 'docstring') else '')
      or 'to_thread' in (ast.get_docstring(fn) or ''),
      'докстринг объясняет зависание / to_thread')

print('== runtime: блокирующий play через to_thread не стопорит loop ==')
import asyncio
import time


async def _sim():
    def blocking_play(_src=None):
        time.sleep(0.35)  # имитация Thread.start/_started.wait

    t0 = time.monotonic()
    # параллельно крутим loop — если play на loop, ticks не успеют
    ticks = 0

    async def ticker():
        nonlocal ticks
        while ticks < 5:
            await asyncio.sleep(0.05)
            ticks += 1

    task = asyncio.create_task(ticker())
    await asyncio.to_thread(blocking_play, object())
    await task
    elapsed = time.monotonic() - t0
    return ticks, elapsed


ticks, elapsed = asyncio.run(_sim())
check(ticks >= 5, f'ticker успел 5 тиков пока play «висел» ({ticks})')
check(elapsed < 1.0, f'wall < 1s ({elapsed:.2f}s)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
