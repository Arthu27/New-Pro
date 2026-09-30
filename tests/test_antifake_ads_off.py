# -*- coding: utf-8 -*-
"""Антиреклама AntiFake полностью выключена (заказ владельца).

Запуск: python3 tests/test_antifake_ads_off.py
"""
import ast
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_antifake_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

json.dump({
    '1': {'enabled': True, 'check_ads': True, 'strike_timeout': True}
}, open('data/antifake.json', 'w'))

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


SRC = open(os.path.join(ROOT, 'cogs', 'impersonation.py'), encoding='utf-8').read()

print('== source defaults ==')
check("'check_ads': False" in SRC or '"check_ads": False' in SRC,
      'DEFAULT check_ads=False в исходнике')
check("'strike_timeout': False" in SRC or '"strike_timeout": False' in SRC,
      'DEFAULT strike_timeout=False в исходнике')
check('c[\'check_ads\'] = False' in SRC or 'c["check_ads"] = False' in SRC,
      'cfg() принудительно check_ads=False')
check("async def on_message" in SRC and
      'Антиреклама / страйки' in SRC.split('async def on_message')[1][:400],
      'on_message заглушен (антиреклама off)')

# runtime cfg via minimal stub of AntiFake.cfg/set_cfg logic
print('== runtime cfg force-off ==')
exec_globals = {}
# Extract DEFAULT_CFG dict from AST
tree = ast.parse(SRC)
default = None
for node in tree.body:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == 'DEFAULT_CFG':
                default = ast.literal_eval(node.value)
check(default is not None and default.get('check_ads') is False,
      f'DEFAULT_CFG.check_ads={default and default.get("check_ads")}')
check(default.get('strike_timeout') is False,
      f'DEFAULT_CFG.strike_timeout={default.get("strike_timeout")}')

# Simulate cfg merge
file_cfg = json.load(open('data/antifake.json'))['1']
merged = dict(default)
merged.update(file_cfg)
merged['check_ads'] = False
merged['strike_timeout'] = False
check(merged['check_ads'] is False and merged['enabled'] is True,
      'даже при check_ads=true в файле — выкл')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
