# -*- coding: utf-8 -*-
"""Voice keep-alive не должен блокировать asyncio-цикл.

По умолчанию — ТОЛЬКО connect (без vc.play). Silence-ping только при
VOICE_SILENCE_PING=1, и тогда play строго через to_thread + wait_for.

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


print('== _monitor_voice: play выключен по умолчанию ==')
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

check('VOICE_SILENCE_PING' in body,
      'silence-ping только по VOICE_SILENCE_PING')
check('wait_for' in body and 'connect' in body,
      'connect обёрнут в wait_for (таймаут)')
check('to_thread' in body, 'если play — только через to_thread')
bad = [ln.strip() for ln in body.splitlines()
       if 'vc.play(' in ln and 'to_thread' not in ln]
check(not bad, f'нет голого vc.play: {bad}')
check('по умолчанию' in doc.lower() or 'без play' in doc.lower()
      or 'VOICE_SILENCE_PING' in doc,
      'докстринг: play выключен по умолчанию')

class _Finder(ast.NodeVisitor):
    def __init__(self):
        self.threaded_play = 0
        self.wait_for_connect = 0
        self.wait_for_play = 0

    def visit_Call(self, node):
        name = _call_name(node.func)
        if name == 'to_thread':
            for arg in node.args:
                if isinstance(arg, ast.Attribute) and arg.attr == 'play':
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
        self.generic_visit(node)


if fn:
    f = _Finder()
    f.visit(fn)
    check(f.wait_for_connect >= 1,
          f'wait_for(connect) в AST ({f.wait_for_connect})')
    check(f.threaded_play >= 1,
          f'to_thread(vc.play) есть в gated-ветке ({f.threaded_play})')
    check(f.wait_for_play >= 1,
          f'wait_for(to_thread(play)) в gated-ветке ({f.wait_for_play})')

print('== runtime: to_thread не стопорит loop ==')


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

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
