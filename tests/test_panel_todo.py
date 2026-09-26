# -*- coding: utf-8 -*-
"""Связка панели с общим списком задач (/todo → services.panel_todo).

Сценарий аудита «все связки»: add → список → toggle → delete целиком,
плюс крайние случаи (None/мусор вместо id раньше роняли эндпоинт в 500
вместо вежливого «Задача не найдена»).
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_todo_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = 0
FAIL = 0


def check(ok, label, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


from services.panel_todo import (add_task, list_tasks, toggle_task,  # noqa: E402
                                 delete_task)

t = add_task('проверка связки', 'owner')
check(t['text'] == 'проверка связки' and t['done'] is False, 'задача создана')
lst = list_tasks()
check(any(x['id'] == t['id'] for x in lst), 'задача в списке')

check(toggle_task(t['id']) is True, 'toggle → True')
check(next(x for x in list_tasks() if x['id'] == t['id'])['done'] is True,
      'done=true сохранился на диске')

check(delete_task(t['id']) is True, 'delete → True')
check(all(x['id'] != t['id'] for x in list_tasks()), 'список чист')

check(toggle_task(None) is False, 'toggle(None) → False (не исключение)')
check(toggle_task('мусор') is False, 'toggle(«мусор») → False')
check(delete_task(None) is False, 'delete(None) → False')
check(delete_task(12345) is False, 'delete(несуществующий id) → False')

try:
    add_task('   ')
    check(False, 'пустая задача отвергнута')
except ValueError:
    check(True, 'пустая задача отвергнута (ValueError)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
