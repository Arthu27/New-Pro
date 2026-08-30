# -*- coding: utf-8 -*-
"""Дружба файлов: scripts/check_files.py проходит без единого FAIL.

Запускает проверщик отдельным процессом — ровно так же, как это сделает
владелец на VDS («python scripts/check_files.py»). HOME изолируем, чтобы
настоящий ~/.cloudflared машины не влиял на результат.

Что проверяется — см. docstring scripts/check_files.py:
порты (5001) во всех файлах, origin-политика 127.0.0.1, вызовы
main.py ↔ services/named_tunnel.py, батник ↔ Python, URL ↔ маршруты,
.env.example ↔ код, конфиги туннеля на диске, синтаксис.

Запуск: python3 tests/test_files_friendship.py
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OK = 0
FAIL = 0


def check(ok, msg):
    global OK, FAIL
    if ok:
        OK += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('[1/2] Прогон scripts/check_files.py (изолированный HOME):')
env = dict(os.environ)
_isolated_home = tempfile.mkdtemp(prefix='hakumo_files_friendship_')
env['HOME'] = _isolated_home
if os.name == 'nt':
    env['USERPROFILE'] = _isolated_home

proc = subprocess.run(
    [sys.executable, os.path.join(ROOT, 'scripts', 'check_files.py')],
    cwd=ROOT, env=env,
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300,
)
out = proc.stdout.decode('utf-8', errors='replace')
print(out.rstrip())

print('\n[2/2] Итог обёртки:')
matches = re.findall(r'=== PASS (\d+) / FAIL (\d+) ===', out)
inner_pass, inner_fail = (int(matches[-1][0]), int(matches[-1][1])) if matches else (0, -1)

check(proc.returncode == 0,
      'check_files.py завершился с кодом 0 (все файлы «дружат»)')
check(inner_fail == 0,
      f'внутри check_files.py: FAIL = {inner_fail} (должно быть 0)')
check(inner_pass >= 50,
      f'проверок достаточно: {inner_pass} PASS (ожидаем не меньше 50 — '
      'иначе проверщик «похудел» и кто-то вырезал секции)')
check('=== PASS' in out and '[A]' in out and '[H]' in out,
      'отчёт содержит все секции A–H и итоговую строку')

print()
print(f'=== PASS {OK} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
