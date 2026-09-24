# -*- coding: utf-8 -*-
"""Повторный/параллельный мут одному человеку запрещён."""
import os
import sys
import tempfile
import types

_TMP = tempfile.mkdtemp(prefix='hakumo_mute_lock_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


from services import mute_state as MS  # noqa: E402
from services import punish_roles as PR  # noqa: E402

GID = 424280
UID = 3000000000000000300
MUTE_R, VMUTE_R = 111001, 111002

PR.set_roles(GID, mute=MUTE_R, vmute=VMUTE_R, who='test')


class _Role:
    def __init__(self, rid):
        self.id = rid


class _Member:
    def __init__(self, roles=None, timed_out=False):
        self.id = UID
        self.roles = list(roles or [])
        self.timed_out_until = object() if timed_out else None


class _Guild:
    id = GID


print('== active_mute_kinds ==')
g = _Guild()
m0 = _Member()
check(MS.active_mute_kinds(g, m0) == set(), 'чисто — пусто')

m1 = _Member(roles=[_Role(MUTE_R)])
check(MS.active_mute_kinds(g, m1) == {'mute'}, 'чат-мут по роли')

m2 = _Member(roles=[_Role(VMUTE_R)])
check(MS.active_mute_kinds(g, m2) == {'vmute'}, 'войс-мут по роли')

m3 = _Member(timed_out=True)
check('timeout' in MS.active_mute_kinds(g, m3), 'нативный таймаут')

PR.add_temp(GID, UID, MUTE_R, __import__('time').time() + 3600)
m4 = _Member()
check('mute' in MS.active_mute_kinds(g, m4), 'мут по temps без роли в кэше')

print('== already_muted_deny ==')
check(MS.already_muted_deny('timeout', set()) is None, 'пусто → ok')
d = MS.already_muted_deny('timeout', {'mute'})
check(d and 'уже в муте' in d, f'timeout при mute → deny ({d})')
d2 = MS.already_muted_deny('mute_chat', {'mute'})
check(d2 and 'уже в муте' in d2, 'mute_chat повтор → deny')
d3 = MS.already_muted_deny('vmute', {'vmute'})
check(d3 and 'уже в муте' in d3, 'vmute повтор → deny')
check(MS.already_muted_deny('ban', {'mute'}) is None, 'бан не блокируем этим')

print('== mute_apply_lock ==')
import asyncio


async def _lock_race():
    lock = MS.mute_apply_lock(GID, UID)
    await lock.acquire()
    got = False
    try:
        await asyncio.wait_for(
            MS.mute_apply_lock(GID, UID).acquire(), timeout=0.05)
        got = True
    except asyncio.TimeoutError:
        got = False
    finally:
        lock.release()
    return not got


check(asyncio.run(_lock_race()), 'второй acquire под локом — timeout')

print('== wiring ==')
src = open(os.path.join(ROOT, 'cogs/moderation.py'), encoding='utf-8').read()
check('already_muted_deny' in src and 'mute_apply_lock' in src,
      'modpanel использует mute guard')
# ищем именно warn-ветку: actor = interaction.user (не display_name)
warn_chunk = ''
i = src.find('if action =="warn"')
j = src.find("if action =='unwarn'", i if i >= 0 else 0)
if i >= 0 and j > i:
    warn_chunk = src[i:j]
check('actor =interaction .user' in warn_chunk
      or 'actor = interaction.user' in warn_chunk,
      f'warn из modpanel передаёт реального Member (chunk={len(warn_chunk)})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
