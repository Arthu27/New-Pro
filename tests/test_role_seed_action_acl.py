# -*- coding: utf-8 -*-
"""Стартовый сид ролей: role_map + дефолтные разрешения действий (action ACL).

Проверяем:
  1) role_map дополняется ролями персонала, маркер версии ставится;
  2) дефолтные разрешения действий ложатся в action_acl — на ЧИСТОМ сервере
     строгий default-deny больше не блокирует варны («варны не работают»);
  3) роли без стафферского тира действий не получают (default-deny держится);
  4) идемпотентность: повторный прогон — no-op;
  5) ручное правило владельца (сужение действия до админа) сид НЕ перетирает.

Запуск: python3 tests/test_role_seed_action_acl.py
"""
import json
import os
import shutil
import sys
import tempfile

GID = 555000111222333444
# MAIN_GUILD_ID должен стоять в окружении ДО импорта config (config читает
# окружение один раз при загрузке) — иначе сид не найдёт боевой сервер.
os.environ['MAIN_GUILD_ID'] = str(GID)

_TMP = tempfile.mkdtemp(prefix='hakumo_seed_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.makedirs('config', exist_ok=True)

# Изолируем sqlite от боевой/демо-БД (как в остальных тестах).
import config  # noqa: E402
config.Config.DB_PATH = os.path.abspath('data/bot.db')
config.Config.MAIN_GUILD_ID = GID
MOD_R = '803553848396349510'
CUR_R = '807030012301541377'
ADM_R = '1189999426631122964'
STAFF = [MOD_R, CUR_R, ADM_R]

SEED = {
    "version": 2,
    "role_map": {MOD_R: "mod", CUR_R: "curator", ADM_R: "admin"},
    "punish_roles": {"ban": 1083106265422643251},
    "action_default": {"tiers": ["mod", "curator", "admin"]},
}
with open('config/role_seed.json', 'w', encoding='utf-8') as fh:
    json.dump(SEED, fh, ensure_ascii=False)

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


from services import role_seed as RS  # noqa: E402

print('== 1. первый прогон: role_map + action ACL ==')
rep = RS.apply_role_seed()
check(rep.get('applied') is True, 'сид применился')
rm = json.load(open('data/role_map.json', encoding='utf-8'))
check(rm.get(MOD_R) == 'mod', 'мод-роль в role_map')
check(rm.get(ADM_R) == 'admin', 'админ-роль в role_map')
check(os.path.exists(f'data/.role_seed.v{SEED["version"]}'), 'маркер версии поставлен')

from services.permission_acl import ACTIONS, load_action_acl, check_action  # noqa: E402
acl = load_action_acl(GID)
check(rep.get('action_acl_actions') == len(ACTIONS),
      f'заданы дефолты для всех {len(ACTIONS)} действий')
check(all(set(STAFF) <= set(acl.get(a, [])) for a in ACTIONS),
      'всем стафферским ролям разрешены все действия')

print('== 2. варны больше не блокированы default-deny ==')


class _Role:
    def __init__(self, rid):
        self.id = int(rid)


class _Member:
    bot = False
    is_panel = False
    id = 4242

    def __init__(self, role_ids):
        self.roles = [_Role(r) for r in role_ids]


check(check_action(GID, _Member([MOD_R]), 'warn') is True, 'мод может warn')
check(check_action(GID, _Member([CUR_R]), 'ban') is True, 'куратор может ban')
check(check_action(GID, _Member([ADM_R]), 'lockdown') is True, 'админ может lockdown')
check(check_action(GID, _Member(['999999999999999999']), 'warn') is False,
      'левая роль (не стаф) warn НЕ может — default-deny держится')

print('== 3. идемпотентность ==')
rep2 = RS.apply_role_seed()
check(rep2.get('reason', '').startswith('already applied'),
      f'повторный прогон — no-op (reason={rep2.get("reason")})')

print('== 4. ручное правило владельца не перетирается ==')
acl = load_action_acl(GID)
acl['warn'] = [int(ADM_R)]            # владелец сузил варн только до админа
from services.permission_acl import save_action_acl  # noqa: E402
save_action_acl(GID, acl)
RS.apply_role_seed(force=True)
acl2 = load_action_acl(GID)
check([str(r) for r in acl2['warn']] == [str(ADM_R)],
      'суженное до админа правило warn осталось нетронутым')
check(set(STAFF) <= set(acl2.get('ban', [])),
      'нетронутые дефолты других действий на месте')

print('== 5. демо-режим ничего не сеет ==')
os.environ['DEMO_MODE'] = '1'
shutil.rmtree('data', ignore_errors=True)
os.makedirs('data', exist_ok=True)
rep_demo = RS.apply_role_seed(force=True)
check(rep_demo.get('applied') is False, f'демо пропущено (reason={rep_demo.get("reason")})')
check(not os.path.exists('data/role_map.json'), 'в демо role_map не пишется')

shutil.rmtree(_TMP, ignore_errors=True)

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
