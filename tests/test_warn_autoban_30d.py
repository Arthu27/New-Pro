# -*- coding: utf-8 -*-
"""Автобан за 3 варна на 30 дней + авто-снятие; сид лестницы."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix='hakumo_warn_autoban_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['MAIN_GUILD_ID'] = '111222333444555666'

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== 1. Сид лестницы: 3 → бан 30д ==')
from services.warn_ladder_seed import (  # noqa: E402
    DEFAULT_STEPS, apply_warn_ladder_seed, SEED_VERSION)
from cogs.warnings import load_warn_config, duration_to_minutes  # noqa: E402

check(DEFAULT_STEPS[0]['count'] == 3 and DEFAULT_STEPS[0]['action'] == 'ban'
      and DEFAULT_STEPS[0]['duration'] == 30 and DEFAULT_STEPS[0]['unit'] == 'day',
      f'дефолт ступени: {DEFAULT_STEPS}')
check(duration_to_minutes(30, 'day') == 30 * 1440, '30 дней = 43200 минут')

for p in __import__('pathlib').Path('data').glob('.warn_ladder_seed*'):
    p.unlink(missing_ok=True)
rep = apply_warn_ladder_seed(force=True, guild_id=111222333444555666)
check(rep.get('applied') and rep.get('seeded'), f'seed applied: {rep}')
cfg = load_warn_config('111222333444555666')
steps = cfg.get('steps') or []
check(len(steps) == 1 and steps[0]['count'] == 3 and steps[0]['action'] == 'ban'
      and steps[0]['duration'] == 30,
      f'warn_config записан: {steps}')
# повторно не перетирает
steps[0]['duration'] = 7
from cogs.ladder import _save_warn_config  # noqa: E402
_save_warn_config(111222333444555666, cfg)
rep2 = apply_warn_ladder_seed(force=True, guild_id=111222333444555666)
check(rep2.get('seeded') is False, 'повторный сид не затирает лестницу')
cfg2 = load_warn_config('111222333444555666')
check((cfg2.get('steps') or [{}])[0].get('duration') == 7,
      'ручная правка сохранилась')


print('== 2. apply_warn_punishment: бан ролью на 30д → add_temp ==')
from services import punish_roles as PR  # noqa: E402
import cogs.warnings as WC  # noqa: E402

GID = 555001
UID = 111000000000000333
BAN_ROLE = 777001
PR.set_roles(GID, ban=BAN_ROLE)
_save_warn_config(GID, {'steps': [
    {'count': 3, 'action': 'ban', 'duration': 30, 'unit': 'day'}]})


class _Role:
    def __init__(self, i, name='ban'):
        self.id = i
        self.name = name


class _Member:
    def __init__(self, i):
        self.id = i
        self.display_name = 'Bad'
        self.given = []
        self.banned = False

    def __str__(self):
        return self.display_name

    async def add_roles(self, *roles, reason=None):
        self.given.extend(roles)
        self.given_reason = reason

    async def ban(self, reason=None):
        self.banned = True
        self.ban_reason = reason


class _Guild:
    def __init__(self):
        self.id = GID
        self._role = _Role(BAN_ROLE, 'Апелляция')

    def get_role(self, rid):
        return self._role if int(rid) == BAN_ROLE else None

    def get_channel(self, cid):
        return None


class _Bot:
    def get_cog(self, name):
        return None


cog = WC.warnings.__new__(WC.warnings)
cog.bot = _Bot()
guild = _Guild()
member = _Member(UID)
before = time.time()
text = asyncio.run(cog.apply_warn_punishment(guild, member, 3))
after = time.time()
check(member.given and member.given[0].id == BAN_ROLE, f'роль бана выдана ({text})')
check(text and '30' in text and 'авто-снятие' in text.lower(),
      f'ответ про 30д + авто-снятие ({text})')
temps = PR.temps_for(GID, UID)
check(str(BAN_ROLE) in {str(k) for k in temps} or BAN_ROLE in temps,
      f'temp роль зарегистрирована: {temps}')
until = temps.get(BAN_ROLE) or temps.get(str(BAN_ROLE))
# ~30 дней
expect = 30 * 86400
check(until and (expect - 120) <= (until - before) <= (expect + 120),
      f'срок ≈ 30 дней ({until - before:.0f}с)')


print('== 3. hard-ban регистрируется в TempModeration._bans ==')
PR.set_roles(GID + 1, ban=0)  # без роли бана → discord.ban
_save_warn_config(GID + 1, {'steps': [
    {'count': 3, 'action': 'ban', 'duration': 30, 'unit': 'day'}]})


class _TM:
    def __init__(self):
        self._bans = {}

    def _bans_file(self):
        return 'data/temp_bans.json'

    def _save(self, attr, path):
        import json
        os.makedirs('data', exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(getattr(self, attr), fh)


class _Bot2:
    def __init__(self, tm):
        self._tm = tm

    def get_cog(self, name):
        return self._tm if name == 'TempModeration' else None


tm = _TM()
cog2 = WC.warnings.__new__(WC.warnings)
cog2.bot = _Bot2(tm)


class _G2:
    def __init__(self):
        self.id = GID + 1

    def get_role(self, rid):
        return None

    def get_channel(self, cid):
        return None


m2 = _Member(UID + 1)
text2 = asyncio.run(cog2.apply_warn_punishment(_G2(), m2, 3))
check(m2.banned is True, f'hard-ban вызван ({text2})')
entry = (tm._bans.get(str(GID + 1)) or {}).get(str(UID + 1))
check(entry and entry.get('until', 0) > time.time() + 29 * 86400,
      f'temp_bans зарегистрирован: {entry}')
check(text2 and 'авто-снятие' in text2.lower(), f'текст авто-снятия ({text2})')


print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
