# -*- coding: utf-8 -*-
"""Канал hakumo-panel и Auto-Repair Discord — по умолчанию выкл.

Запуск: python3 tests/test_panel_discord_channel_off.py
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== panel discord channel off by default ==')
src = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
check('def _panel_discord_channel_enabled' in src, 'есть флаг PANEL_DISCORD_CHANNEL')
check('create_text_channel("hakumo-panel"' not in src,
      'автосоздание hakumo-panel убрано')
check("os.getenv('PANEL_DISCORD_CHANNEL') or '0'" in src,
      'по умолчанию PANEL_DISCORD_CHANNEL=0')
check('Ссылка панели в Discord отключена' in src,
      'send_panel_link молчит когда выкл')

# Проверяем тело функции: при выкл — ранний return, без create
tree = ast.parse(src)
fn = None
for node in tree.body:
    if isinstance(node, ast.AsyncFunctionDef) and node.name == 'send_panel_link':
        fn = node
        break
check(fn is not None, 'send_panel_link найдена')
fn_src = ast.get_source_segment(src, fn) or ''
check('create_text_channel' not in fn_src,
      'внутри send_panel_link нет create_text_channel')
check('return' in fn_src, 'ранний выход когда канал выкл')

print('== diagnostics quiet ==')
os.environ['AUTO_REPAIR_DISCORD_NOTIFY'] = '0'
from cogs import diagnostics as DIAG  # noqa: E402
check(DIAG._discord_notify_enabled() is False, 'Auto-Repair Discord OFF')
check(DIAG.REPAIR_ACTIONS['high_memory'] == 'Garbage collect',
      'без reload heaviest cog')
check(DIAG.THRESHOLDS['memory_mb']['warn'] >= 750, 'порог памяти не спамит')

ex = open(os.path.join(ROOT, '.env.example'), encoding='utf-8').read()
check('PANEL_DISCORD_CHANNEL=0' in ex, '.env.example: PANEL_DISCORD_CHANNEL=0')
check('AUTO_REPAIR_DISCORD_NOTIFY=0' in ex, '.env.example: AUTO_REPAIR OFF')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
