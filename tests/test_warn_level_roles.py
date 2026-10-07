# -*- coding: utf-8 -*-
"""Обратная совместимость: уровни warn_1/2/3 больше НЕ используются.

Новая система: одна роль warn + счётчик в SQLite.
Этот файл проверяет, что ког warnings не зовёт level_transition
и что новый test_warn_system покрывает sync.

Запуск: python3 tests/test_warn_level_roles.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_wlevel_legacy_')
os.chdir(_TMP)
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


src = open(os.path.join(ROOT, 'cogs', 'warnings.py'), encoding='utf-8').read()
check('_sync_warn_level_roles' not in src, 'нет старого sync уровней')
check('level_transition' not in src, 'нет вызовов level_transition')
check('sync_warn_role' in src, 'есть sync_warn_role')

role_src = open(os.path.join(ROOT, 'services', 'warn_role.py'),
                encoding='utf-8').read()
check('is_staff_member' in role_src, 'staff check в warn_role')
check('active' in role_src, 'ориентир на active-счётчик')

store_src = open(os.path.join(ROOT, 'services', 'warn_store.py'),
                 encoding='utf-8').read()
check('CREATE TABLE IF NOT EXISTS warns' in store_src, 'таблица warns')
check('active' in store_src and 'removed_by' in store_src,
      'soft-remove поля')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
print('Полный сценарий: python3 tests/test_warn_system.py')
sys.exit(1 if FAIL else 0)
