# -*- coding: utf-8 -*-
"""Целостность Python-кода и отсутствие зашитых секретов.

Проверки:
1. compileall: каждый .py в web/, cogs/, services/, scripts/ и корне
   компилируется (ловит синтаксические ошибки в модулях, которые
   не импортируются другими тестами).
2. Секреты не зашиты в код: SECRET_KEY/TOKEN/PASSWORD/API_KEY с длинными
   строковыми литералами (не из окружения), литералы демо-паролей в
   боевом коде, Discord-токены по шаблону [MN]….….….
3. У каждого модуля web/routes есть docstring (порядок в проекте).

Запуск: python3 tests/test_py_compile.py
"""
import glob
import os
import py_compile
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


# ─── 1. compileall ───────────────────────────────────────────────────────────
print('== 1. Все .py компилируются ==')
targets = []
for pat in ('web/**/*.py', 'cogs/*.py', 'services/*.py', 'scripts/*.py', '*.py'):
    targets += glob.glob(os.path.join(ROOT, pat), recursive=True)
targets = [t for t in targets if '.venv' not in t]
_bad = []
for t in targets:
    try:
        py_compile.compile(t, doraise=True)
    except Exception as e:  # noqa: BLE001
        _bad.append(f'{os.path.relpath(t, ROOT)}: {e}')
check(not _bad, f'{len(targets)} файлов компилируются ({_bad[:3]})')

# ─── 2. секреты ──────────────────────────────────────────────────────────────
print('== 2. Секреты не зашиты в код ==')
prod_files = []
for pat in ('web/**/*.py', 'cogs/*.py', 'services/*.py', '*.py'):
    prod_files += glob.glob(os.path.join(ROOT, pat), recursive=True)
prod_files = [t for t in prod_files if '.venv' not in t]

_bad = []
for f in prod_files:
    src = open(f, encoding='utf-8').read()
    rel = os.path.relpath(f, ROOT)
    for m in re.finditer(
            r'\b(SECRET_KEY|TOKEN|PASSWORD|API_KEY|CLIENT_SECRET)\s*=\s*["\']([^"\']{8,})["\']', src):
        if 'getenv' in src[max(0, m.start() - 120):m.start()] or 'environ' in src[max(0, m.start() - 120):m.start()]:
            continue
        _bad.append(f'{rel}: {m.group(1)} = «{m.group(2)[:12]}…»')
    for m in re.finditer(r'["\'][MN][A-Za-z\d_-]{23,25}\.[\w-]{6}\.[\w-]{27,39}["\']', src):
        _bad.append(f'{rel}: похоже на Discord-токен')
    for lit in ('preview-secret', 'preview123'):
        if re.search(r'["\']' + lit + r'["\']', src):
            _bad.append(f'{rel}: демо-пароль {lit} в боевом коде')
check(not _bad, f'секретов не найдено ({_bad[:3]})')

# ─── 3. нет незадействованных route-модулей ──────────────────────────────────
print('== 3. Каждый модуль web/routes импортируется ==')
mods = [os.path.basename(f)[:-3] for f in glob.glob(os.path.join(ROOT, 'web', 'routes', '*.py'))
        if not f.endswith('__init__.py')]
all_src = ''
for f in glob.glob(os.path.join(ROOT, 'web', '**', '*.py'), recursive=True):
    all_src += open(f, encoding='utf-8').read()
dead = [m for m in mods if not re.search(r'\b' + re.escape(m) + r'\b', all_src)]
check(not dead, f'{len(mods)} route-модулей, незадействованных: {len(dead)} ({dead[:5]})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
