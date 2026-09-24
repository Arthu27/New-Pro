# -*- coding: utf-8 -*-
"""Прогрессия мута: 2ч → +2ч, сброс на варн.
Запуск: python3 tests/test_mute_progression.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_mute_prog_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


from services import mute_progression as MP  # noqa: E402
from services import staff_limits as SL  # noqa: E402

G, U = 42, 1001

print('== 1. Первый мут = 2 часа ==')
check(MP.cap_seconds(G, U) == 2 * 3600, f'cap={MP.cap_seconds(G, U)}')
check(MP.step_for(G, U) == 0, 'step 0')
check(SL.resolve_mute_cap(G, U, []) == 2 * 3600, 'resolve = 2ч')

print('== 2. После мута +2ч ==')
MP.bump_after_mute(G, U)
check(MP.step_for(G, U) == 1, 'step 1')
check(MP.cap_seconds(G, U) == 4 * 3600, 'cap 4ч')
MP.bump_after_mute(G, U)
check(MP.cap_seconds(G, U) == 6 * 3600, 'cap 6ч')
MP.bump_after_mute(G, U)
check(MP.cap_seconds(G, U) == 8 * 3600, 'cap 8ч')

print('== 3. Варн → снова 2ч ==')
MP.reset_on_warn(G, U)
check(MP.step_for(G, U) == 0 and MP.cap_seconds(G, U) == 2 * 3600,
      'после варна снова 2ч')

print('== 4. Отказ по потолку ==')
err = SL.mute_duration_error(3 * 3600, cap_sec=2 * 3600)
check(err and '2 ч' in err, f'3ч при потолке 2ч → отказ: {err}')
ok = SL.mute_duration_error(2 * 3600, cap_sec=2 * 3600)
check(ok is None, 'ровно 2ч — можно')
short = SL.mute_duration_error(15 * 60, cap_sec=2 * 3600)
check(short and '30' in short, 'короче 30 мин — отказ')

print('== 5. Владелец без потолка ==')
# тир owner через role_map
with open('data/role_map.json', 'w') as fh:
    fh.write('{"999":"owner"}')
check(SL.resolve_mute_cap(G, U, [999]) == 0, 'owner → 0')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
