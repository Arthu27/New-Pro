# -*- coding: utf-8 -*-
"""AI chat must not spam PANEL-REMOVED stub when web.ai_helper is gone.

Запуск: python3 tests/test_ai_chat_no_panel_spam.py
"""
import importlib
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_ai_spam_')
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


print('== 1. defaults: AI chat OFF ==')
from services import ai_chat_settings as ACS  # noqa: E402
check(ACS.DEFAULT_SETTINGS.get('enabled') is False, 'enabled default False')
check(ACS.DEFAULT_SETTINGS.get('respond_all') is False, 'respond_all default False')

print('== 2. _call_ai silent without panel backend ==')
# Force reload so module-level cache is fresh
import cogs.ai_chat as AI  # noqa: E402
AI._AI_BACKEND_AVAILABLE = False
ans = AI._call_ai('привет', 1, guild=None)
check(ans == '', f'_call_ai returns empty (got {ans!r})')
check('PANEL-REMOVED' not in (ans or ''), 'no PANEL-REMOVED stub')
check(AI._ai_backend_available() is False, 'backend flagged unavailable')

print('== 3. source guards ==')
src = open(os.path.join(ROOT, 'cogs/ai_chat.py'), encoding='utf-8').read()
check('_ai_backend_available' in src, 'backend gate exists')
check("if not _ai_backend_available ():" in src.replace(' ', '')
      or 'if not _ai_backend_available():' in src
      or 'if not _ai_backend_available ():' in src,
      'on_message checks backend')
check('PANEL-REMOVED' in src and "return ''" in src, 'ImportError → empty')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
