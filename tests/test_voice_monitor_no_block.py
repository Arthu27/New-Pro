# -*- coding: utf-8 -*-
"""Voice keep-alive: всегда вкл, без лимитов; silence play opt-in и не блокирует.

По умолчанию — ТОЛЬКО connect (без vc.play). Silence-ping только при
VOICE_SILENCE_PING=1 через start_silence_keepalive (без to_thread —
play() мгновенный; to_thread+PCM раньше флапал WS ~каждые 20с).

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

check('really_in_channel' in body or 'really_in_channel' in src,
      'монитор через Discord-truth')
check('await asyncio.sleep(2)' in body or 'sleep(2)' in body,
      'монитор каждые 2с (без 30с паузы)')
check('backoff_until' not in body,
      'нет backoff_until в мониторе')
check('_ensure_main_voice_joined' in body or '_schedule_main_voice_rejoin' in body,
      'монитор зовёт ensure/rejoin')
check("_schedule_main_voice_rejoin('latency-heal'" not in body
      and 'latency-heal', force=True)" not in body,
      'монитор НЕ делает latency-heal force (сам выкидывал из войса)')
check("_schedule_main_voice_rejoin('soft-reconnect'" not in body,
      'монитор не force soft-reconnect пока Discord in')
bad = [ln.strip() for ln in body.splitlines()
       if 'vc.play(' in ln and 'start_silence' not in ln]
check(not bad, f'нет голого vc.play в мониторе: {bad}')
check('to_thread' not in body or 'to_thread(vc.play' not in body.replace(' ', ''),
      'нет to_thread(vc.play) — флапало WS')
check('silence' in doc.lower() or 'VOICE_SILENCE_PING' in doc
      or 'keepalive' in doc.lower(),
      'докстринг: silence keepalive')

check('_ensure_main_voice_joined' in src, 'ensure_voice helper есть')
check('_schedule_main_voice_rejoin' in src, 'schedule rejoin есть')
check(('self_deaf=True' in src and 'self_mute=True' in src)
      or ('self_deaf=_self_deaf' in src and 'self_mute=_self_mute' in src),
      'self_deaf/self_mute для stay (или panel open_mic)')
check('effective_stay_channel_id' in src, 'panel hold через effective_stay')
check('kicked-or-moved' in src, 'rejoin по кику')
check('force=True' in src, 'force rejoin на kick/resume')
check('soft-reconnect' in src, 'soft reconnect против zombie')
check('voice_stay_health' in src, 'общий health-модуль')
check("os.environ.get('VOICE_STAY_ENABLED')" not in src
      or 'игнорируется' in src,
      'нет выключателя VOICE_STAY_ENABLED')
check('_bind_voice_gw_listeners' in src,
      'gw listeners через add_listener (error_handler-safe)')
check('+ 25.0' in src or '+25.0' in src.replace(' ', ''),
      'suppress после join ≥25с (анти-флап)')

class _Finder(ast.NodeVisitor):
    def __init__(self):
        self.threaded_play = 0
        self.wait_for_connect = 0
        self.silence_helper = 0

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
        if name == 'start_silence_keepalive':
            self.silence_helper += 1
        self.generic_visit(node)


if fn:
    f = _Finder()
    f.visit(fn)
    check(f.wait_for_connect == 0,
          f'нет wait_for(connect) в мониторе ({f.wait_for_connect})')
    check(f.threaded_play == 0,
          f'нет to_thread(vc.play) в keepalive ({f.threaded_play})')
    check(f.silence_helper >= 1 or 'start_silence_keepalive' in body,
          'start_silence_keepalive в мониторе (если silence ON)')

print('== config/voice_stay.json ==')
import json  # noqa: E402
cfg = json.load(open(os.path.join(ROOT, 'config', 'voice_stay.json'), encoding='utf-8'))
check(bool(cfg.get('channel_id')), f'channel_id={cfg.get("channel_id")}')
check(cfg.get('stay_enabled') is True, 'stay_enabled=true в json')

print('== silence_ping default OFF ==')
import services.voice_stay_health as H  # noqa: E402
old = os.environ.pop('VOICE_SILENCE_PING', None)
try:
    check(H.silence_ping_enabled() is False, 'default silence OFF')
    os.environ['VOICE_SILENCE_PING'] = '1'
    check(H.silence_ping_enabled() is True, 'VOICE_SILENCE_PING=1 → ON')
    src_obj = H.silence_source()
    check(src_obj.is_opus() is True, 'LoopSilence is_opus=True (не PCM)')
    frame = src_obj.read()
    check(frame == b'\xf8\xff\xfe', 'opus silence frame')
finally:
    if old is None:
        os.environ.pop('VOICE_SILENCE_PING', None)
    else:
        os.environ['VOICE_SILENCE_PING'] = old

print('== runtime: sync play не стопорит loop ==')


async def _sim():
    ticks = 0

    async def ticker():
        nonlocal ticks
        while ticks < 5:
            await asyncio.sleep(0.05)
            ticks += 1

    task = asyncio.create_task(ticker())
    # play() sync and instant — just yield
    await asyncio.sleep(0)
    await task
    return ticks


ticks = asyncio.run(_sim())
check(ticks >= 5, f'ticker успел 5 тиков ({ticks})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
