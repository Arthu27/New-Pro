# -*- coding: utf-8 -*-
"""Уровни варнов в ролях наказаний (services/punish_roles).

Роль ближайшего уровня ≤ warn_count, предыдущая роль уровня снимается:
level_transition возвращает (add, remove) так, что старые warn-роли
гарантированно слетают, дублей не бывает; 0 варнов — снять всё.
Валидация ключей: warn_1..warn_10 + классика mute/vmute/ban.

Запуск: python3 tests/test_punish_roles_levels.py
"""
import json
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_proles_test_')
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


from services import punish_roles as PR  # noqa: E402

print('== 1. валидность видов ==')
for k, ok in [('mute', True), ('vmute', True), ('ban', True),
              ('warn_1', True), ('warn_9', True), ('warn_10', True),
              ('warn_0', False), ('warn_11', False), ('warn_99', False),
              ('warn_a', False), ('', False), ('kick', False), ('warn1', False)]:
    check(PR.valid_kind(k) is ok, f'valid_kind({k!r}) == {ok}')

print('== 2. запись/чтение уровней ==')
PR.set_roles('777', mute='111', warn_1='555', warn_3='666', warn_10='777000')
got = PR.get('777')
check(got == {'mute': 111, 'warn_1': 555, 'warn_3': 666, 'warn_10': 777000},
      f'уровни сохраняются и читаются: {got}')
lv = PR.warn_levels(got)
check(lv == {1: 555, 3: 666, 10: 777000}, f'warn_levels: {lv}')
PR.set_roles('777', junk='999', warn_2='abc', warn_2x='123')
got = PR.get('777')
check('junk' not in got and 'warn_2' not in got and 'warn_2x' not in got,
      'мусорные ключи/значения не попадают в хранилище')
PR.set_roles('777', warn_1=0)
check('warn_1' not in PR.get('777'), '0 снимает выбор уровня')

print('== 3. переход уровней ==')
PR.set_roles('777', mute=0, vmute=0, ban=0)
PR.set_roles('777', warn_1='555', warn_3='666', warn_10='777000')
add, rem = PR.level_transition('777', 0)
check(add == 0 and set(rem) == {555, 666, 777000},
      f'0 варнов — снять все warn-роли: {add}/{rem}')
add, rem = PR.level_transition('777', 1)
check(add == 555 and set(rem) == {666, 777000},
      f'1 варн — роль 1-го уровня, остальные снять: {add}/{rem}')
add, rem = PR.level_transition('777', 2)
check(add == 555 and set(rem) == {666, 777000},
      '2 варна — всё ещё ближайший уровень 1')
add, rem = PR.level_transition('777', 3)
check(add == 666 and set(rem) == {555, 777000},
      f'3 варна — роль 3-го уровня, 1-й снимается: {add}/{rem}')
add, rem = PR.level_transition('777', 3)
check(set(rem) == {555, 777000} and add not in rem,
      'новая роль никогда не в списке снятия (дублей нет)')
add, rem = PR.level_transition('777', 5)
check(add == 666, '5 варнов — ближайший уровень 3 (незаполненные пропускаем)')
add, rem = PR.level_transition('777', 10)
check(add == 777000 and 666 in rem and 555 in rem,
      '10 варнов — максимальный уровень')
add, rem = PR.level_transition('777', 2)
check(add == 555 and 666 in rem and 777000 in rem,
      'падение с 10 до 2 — старшие роли снимаются')
# одна и та же роль на двух уровнях: снять нельзя то, что выдаём
PR.set_roles('777', warn_1=0, warn_3=0, warn_10=0)
PR.set_roles('777', warn_1='555', warn_3='555')
add, rem = PR.level_transition('777', 3)
check(add == 555 and rem == [], f'одна роль на несколько уровней — без снятия: {add}/{rem}')

print('== 4. старые виды ничем не сломаны ==')
PR.set_roles('888', mute='111', vmute='222', ban='333')
got = PR.get('888')
check(got == {'mute': 111, 'vmute': 222, 'ban': 333}, 'классика как была')
check(PR.role_for('888', 'mute') == 111 and PR.role_for('888', 'ban') == 333,
      'role_for для классики')
check(PR.role_for('888', 'warn_5') == 0, 'role_for уровня без выбора — 0')

print('== 5. временные выдачи не пострадали ==')
import time as _time
PR.add_temp('888', '42', 111, 100.0)
PR.add_temp('888', '42', 222, _time.time() + 1000)
due = {(g, u, r) for g, u, r in PR.due(200.0)}
check(('888', '42', 111) in due, 'просроченная видна лупу')
check(('888', '42', 222) not in due, 'непросроченная не видна')
PR.clear('888', '42', 111)
check(PR.due(200.0) == [], 'clear точечно снимает')

print('== 6. чтение битого файла не падает ==')
open('data/punish_roles.json', 'w', encoding='utf-8').write('{бито')
check(PR.get('777') == {}, 'битый JSON → пустой выбор')
json.dump({'777': {'roles': {'warn_1': 'не число', 'warn_2': 5, 'mute': -1}}},
          open('data/punish_roles.json', 'w', encoding='utf-8'))
got = PR.get('777')
check(got == {'warn_2': 5}, f'нечисловые/отрицательные отсекаются: {got}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
