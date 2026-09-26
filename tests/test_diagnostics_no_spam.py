# -*- coding: utf-8 -*-
"""Auto-Repair: без спама warn в ЛС, порог памяти выше «нормальной» нагрузки."""
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


print('== diagnostics: no Auto-Repair warn spam ==')
src = open(os.path.join(ROOT, 'cogs/diagnostics.py'), encoding='utf-8').read()
check('NOTIFY_DM_SEVERITIES' in src, 'есть NOTIFY_DM_SEVERITIES')
check('severity not in NOTIFY_DM_SEVERITIES' in src
      or 'severity not in NOTIFY_DM_SEVERITIES' in src.replace(' ', ''),
      'warn не уходит в ЛС')

# Парсим пороги из AST-подобной строки через exec модуля без discord-зависимости:
# читаем константы из исходника простым eval блока.
ns = {}
tree = ast.parse(src)
for node in tree.body:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id in (
                    'THRESHOLDS', 'NOTIFY_DM_SEVERITIES'):
                code = compile(ast.Module(body=[node], type_ignores=[]),
                               '<diag>', 'exec')
                exec(code, ns, ns)

th = ns.get('THRESHOLDS') or {}
mem = th.get('memory_mb') or {}
check(int(mem.get('warn', 0)) >= 800,
      f"memory warn ≥800 (сейчас {mem.get('warn')})")
check(int(mem.get('critical', 0)) >= 1200,
      f"memory critical ≥1200 (сейчас {mem.get('critical')})")
sev = ns.get('NOTIFY_DM_SEVERITIES') or set()
check('warn' not in sev and 'critical' in sev,
      f'в ЛС только critical: {sev}')

# send_panel_link остаётся no-op на этой ветке
main = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
check('create_text_channel("hakumo-panel"' not in main
      and "create_text_channel('hakumo-panel'" not in main,
      'hakumo-panel не создаётся')

print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
