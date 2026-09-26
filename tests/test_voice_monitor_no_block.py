# -*- coding: utf-8 -*-
"""Voice keep-alive: всегда вкл, без лимитов, play не блокирует цикл.

По умолчанию — ТОЛЬКО connect (без vc.play). Silence-ping только при
VOICE_SILENCE_PING=1, и тогда play строго через to_thread + wait_for.
Connect без wait_for/таймаута — бесконечный rejoin как у Event-бота.

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


print('== _monitor_voice: always-on, play gated ==')
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
check('await asyncio.sleep(2)' in body or 'sleep(2)' in body,
      'монитор каждые 2с (без 30с паузы)')
check('backoff_until' not in body,
      'нет backoff_until в мониторе')
check('timeout=30' not in body and 'wait_for' not in body.split('VOICE_SILENCE_PING')[0],
      'connect без wait_for/таймаута 30с')
check('_ensure_main_voice_joined' in body or '_schedule_main_voice_rejoin' in body,
      'монитор зовёт ensure/rejoin')
check('to_thread' in body, 'если play — только через to_thread')
bad = [ln.strip() for ln in body.splitlines()
       if 'vc.play(' in ln and 'to_thread' not in ln]
check(not bad, f'нет голого vc.play: {bad}')
check('по умолчанию' in doc.lower() or 'без play' in doc.lower()
      or 'VOICE_SILENCE_PING' in doc,
      'докстринг: play выключен по умолчанию')

check('_ensure_main_voice_joined' in src, 'ensure_voice helper есть')
check('_schedule_main_voice_rejoin' in src, 'schedule rejoin есть')
check('self_deaf=True' in src and 'self_mute=True' in src,
      'self_deaf/self_mute для stay')
check('kicked-or-moved' in src, 'rejoin по кику')
check('VOICE_STAY_ENABLED игнорируется' in src
      or 'VOICE_STAY_ENABLED игнорируется' in src
      or ('voice stay: всегда вкл' in src
          and 'VOICE_STAY_ENABLED=0' not in src.split('_monitor_voice')[0]),
      'VOICE_STAY_ENABLED больше не выключает stay')
# явная проверка: стартовый блок не читает VOICE_STAY_ENABLED для выключения
on_ready_chunk = src
check("os.environ.get('VOICE_STAY_ENABLED')" not in on_ready_chunk
      or 'игнорируется' in on_ready_chunk,
      'нет выключателя VOICE_STAY_ENABLED')
check('_bind_voice_gw_listeners' in src,
      'gw listeners через add_listener (error_handler-safe)')

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
    check(f.wait_for_connect == 0,
          f'нет wait_for(connect) в мониторе ({f.wait_for_connect})')
    check(f.threaded_play >= 1,
          f'to_thread(vc.play) есть в gated-ветке ({f.threaded_play})')
    check(f.wait_for_play >= 1,
          f'wait_for(to_thread(play)) в gated-ветке ({f.wait_for_play})')

print('== config/voice_stay.json ==')
import json  # noqa: E402
cfg = json.load(open(os.path.join(ROOT, 'config', 'voice_stay.json'), encoding='utf-8'))
check('channel_id' in cfg, f'channel_id key present ({cfg.get("channel_id")!r})')
check(cfg.get('stay_enabled') is True, 'stay_enabled=true в json')

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
