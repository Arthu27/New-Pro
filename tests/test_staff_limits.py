# -*- coding: utf-8 -*-
"""Лимиты стаффа (защита от «плохих» модераторов): дефолты, счётчики,
сброс по дню, переопределение лимитов. Запуск: python3 tests/test_staff_limits.py"""
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_limits_test_')
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

print('== 8. Свои лимиты ролей ГЛАВНЕЕ общих ==')
# свежая гильдия, чтобы не зависеть от предыдущих разделов
G2 = G + 9
SL.set_limits(G2, ban=3)                          # общий: 3 бана
SL.set_role_limits(G2, 500, who='t', role_name='Старший мод', ban=10)
lim_r, win_r = SL.effective_limits(G2, [500])
check(lim_r['ban'] == 10, f'роль 10 при общем 3 → действует 10 ({lim_r["ban"]})')
ok_r, used_r, lim_eff = SL.check_limit(G2, 333, 'ban', 9, role_ids=[500])
check(ok_r and lim_eff == 10, 'по лимиту РОЛИ: 9-й бан разрешён (общий 3 не мешает)')

SL.set_role_limits(G2, 501, who='t', role_name='Стажёр', ban=2)
lim_j, _w = SL.effective_limits(G2, [501])
check(lim_j['ban'] == 2, 'роль 2 при общем 3 → действует 2 (жёстче — тоже её цифра)')

SL.set_role_limits(G2, 502, who='t', role_name='Спец', unban=4)
lim_u, _wu = SL.effective_limits(G2, [502])
check(lim_u.get('unban') == 4, 'общий дефолт 10, у роли 4 → действует 4')

SL.set_role_limits(G2, 503, who='t', role_name='Мягкая', ban=9)
lim_m, _wm = SL.effective_limits(G2, [501, 503])
check(lim_m['ban'] == 9, 'две роли (2 и 9) → действует мягчайшая (9)')

SL.set_role_windows(G2, 500, who='t', role_name='Старший мод', ban=3600)
check(SL.effective_limits(G2, [500])[1].get('ban') == 3600,
      'свой период роли применяется вместе с её лимитом')

check(SL.effective_limits(G2, [999])[0]['ban'] == 3,
      'роль без своих лимитов → общий (3)')


class _R:
    def __init__(self, i):
        self.id = i


class _M:
    def __init__(self, i, roles):
        self.id = i
        self.roles = roles
        self.bot = False


class _GG:
    def __init__(self, i):
        self.id = i
        self.owner_id = 1


gA = _GG(G2)
mA = _M(777, [_R(500), _R(G2)])                   # @everyone отбрасывается
last_text = ''
for _ in range(11):
    ok_a, last_text = SL.check_action(gA, mA, 'ban', 1)
    if not ok_a:
        break
    SL.record_hit(gA.id, mA.id, 'ban', 1)
check(ok_a is False and '10' in (last_text or ''),
      f'check_action: 11-й бан сверх лимита роли 10 запрещён ({last_text})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
