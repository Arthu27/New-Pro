# -*- coding: utf-8 -*-
"""Лимиты стаффа (защита от «плохих» модераторов): дефолты, счётчики,
сброс по дню, переопределение лимитов. Запуск: python3 tests/test_staff_limits.py"""
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_limits_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

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


from services import staff_limits as SL  # noqa: E402

G, MOD, OTHER = 777001, 111, 222

print('== 1. Дефолты и чтение ==')
lim = SL.get_limits(G)
check(lim['ban'] == 8 and lim['clear'] == 500, f'дефолты: 8 банов и 500 сообщений ({lim})')

print('== 2. Проверка без записи ==')
ok, used, limit = SL.check_limit(G, MOD, 'ban', 1)
check(ok and used == 0 and limit == 8, 'первый бан разрешён, потрачено 0/8')
ok2, used2, _l = SL.check_limit(G, MOD, 'clear', 500)
check(ok2 and used2 == 0, 'полупорог чистки 500/500 разрешён')

print('== 3. Счётчик растёт и упирается в лимит ==')
for _ in range(8):
    SL.record_hit(G, MOD, 'ban', 1)
ok3, used3, lim3 = SL.check_limit(G, MOD, 'ban', 1)
check(used3 == 8 and not ok3, f'9-й бан запрещён (потрачено {used3}/{lim3})')
ok4, used4, _l = SL.check_limit(G, OTHER, 'ban', 1)
check(ok4 and used4 == 0, 'другой модератор не affected — счётчики личные')

print('== 4. Чистка считает СООБЩЕНИЯ, не вызовы ==')
SL.record_hit(G, MOD, 'clear', 480)
ok5, used5, lim5 = SL.check_limit(G, MOD, 'clear', 25)
check(used5 == 480 and not ok5, 'чистка +25 сверх 480/500 запрещена')
ok6, _u, _l = SL.check_limit(G, MOD, 'clear', 20)
check(ok6, 'чистка +20 ровно до 500 разрешена')

print('== 5. Переопределение лимитов живёт на диске ==')
new_lim = SL.set_limits(G, ban=3, clear=100)
check(new_lim['ban'] == 3 and new_lim['clear'] == 100, 'set_limits обновил лимиты')
lim2 = SL.get_limits(G)
check(lim2['ban'] == 3 and lim2['clear'] == 100, 'лимиты пережили перечитывание с диска')
ok7, used7, lim7 = SL.check_limit(G, MOD, 'ban', 1)
check(not ok7 and lim7 == 3, 'под новый лимит 3: уже потраченные 8 банов > 3 — запрет')

print('== 6. status_text для модератора ==')
txt = SL.status_text(G, MOD)
check('баны 8/3' in txt and 'чистка 480/100' in txt, f'status_text: {txt}')

print('== 7. Битые файлы не роняют сервис ==')
import json
open(SL._cnt_path(G), 'w').write('{"бито')
ok8, _u, _l = SL.check_limit(G, MOD, 'ban', 1)
check(ok8, 'битый файл счётчика -> день с чистого листа, запрета нет')
open(SL._cfg_path(G), 'w').write('не json')
lim3 = SL.get_limits(G)
check(lim3['ban'] == SL.DEFAULT_LIMITS['ban'], 'битый файл лимитов -> дефолты')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
