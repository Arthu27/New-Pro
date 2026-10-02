# -*- coding: utf-8 -*-
"""Modpanel: защита от лага / «приложение не отвечает».

Запуск: python3 tests/test_modpanel_lag_guard.py
"""
import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='hakumo_mplag_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# import helpers from moderation without loading full cog discord gateway
import importlib.util

spec = importlib.util.spec_from_file_location(
    'moderation_lag', os.path.join(ROOT, 'cogs', 'moderation.py'))
# Too heavy — test via source + light helpers extracted by exec of top funcs

src = open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read()

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== source guards ==')
check('_ack_or_busy' in src, '_ack_or_busy helper')
check('Бот был занят' in src, 'busy message for user')
check('wait_for' in src and '_PUSH_TO' in src, 'panel push timeout')
check("name='modpanel-bg-reset'" in src and '_cancel_panel_reset(panel)' in src[
    src.index('def _bg_reset_after_step'):src.index('async def _enter_kind_mode')],
      'bg reset cancels previous task')
check('_allowed_cache_key' in src and 'panel._rebuild(guild)' in src,
      'rebuild on loop + allowed cache')
# UnmuteKindSelect thinking True via _ack_or_busy
uks = src[src.index('class UnmuteKindSelect'):src.index('class UnmuteKindView')]
check('_ack_or_busy' in uks and 'thinking=True' in uks,
      'UnmuteKindSelect: thinking=True (не «не ответило»)')
# no double schedule 0.45 after every step
ras = src[src.index('async def _reset_after_step'):src.index('def _bg_reset_after_step')]
check('delay=0.45' not in ras, 'нет обязательного второго reset через 0.45с')
check('multi-fix-v17' in src or 'multi-fix-v18' in src, 'build tag v17+')
check('_allowed_cache_key' in src, 'кэш allowed на rebuild')
check('successor' in src or 'нет живого successor' in src
      or '_reset_task' in src[src.index('except _aio.CancelledError'):
                               src.index('except _aio.CancelledError') + 500],
      'CancelledError push respects successor reset-task')

# Action select lag > 2.2 soft nack
asel = src[src.index('class ModActionSelect'):src.index('_PUNISH_MODPANEL')]
check('lag > 2.2' in asel and 'Бот был занят' in asel,
      'ModActionSelect: soft-nack при lag>2.2')
mks = src[src.index('class MuteKindSelect'):src.index('class MuteKindView')]
check('lag > 2.2' in mks and 'Бот был занят' in mks,
      'MuteKindSelect: soft-nack при lag>2.2')

# Wrong-message / known_target guards
push_fn = src[src.index('async def _push_panel_view'):src.index('async def _silent_reset_panel')]
check('known_target' in push_fn and 'не мигрируем' in push_fn,
      'push: known_target + чужой id → fail')
mts = src[src.index('class ModTargetSelect'):src.index('class ModPanelView')]
check('_bg_reset_after_step' in mts, 'ModTargetSelect tracked bg-reset')
check('_reset_push_retrying' in src, 'schedule in-task push retry flag')

print('== runtime lag helper ==')
# exec just the small helpers with fake datetime already imported in module path
ns = {}
# pull helper functions by compiling a slice
helper_src = '''
from datetime import datetime, timezone, timedelta
''' + src[src.index('def _interaction_lag_sec'):src.index('def _is_untouchable')]
# _ack_or_busy depends on _ack and log — stub
exec('''
from datetime import datetime, timezone, timedelta
import logging
log = logging.getLogger("t")

async def _ack(interaction, ephemeral=True, thinking=True):
    interaction.response._done = True

''' + src[src.index('def _interaction_lag_sec'):src.index('def _is_untouchable')], ns)


class Resp:
    def __init__(self):
        self._done = False
        self.sent = None

    def is_done(self):
        return self._done

    async def send_message(self, **kw):
        self._done = True
        self.sent = kw

    async def defer(self, **kw):
        self._done = True


class Ix:
    def __init__(self, lag):
        self.created_at = datetime.now(timezone.utc) - timedelta(seconds=lag)
        self.response = Resp()


async def main():
    lag = ns['_interaction_lag_sec'](Ix(2.5))
    check(lag >= 2.4, f'lag measure ~2.5 got {lag:.2f}')
    ok = await ns['_ack_or_busy'](Ix(2.5), thinking=True, limit=2.2)
    check(ok is False, 'busy → False')
    ok2 = await ns['_ack_or_busy'](Ix(0.1), thinking=True, limit=2.2)
    check(ok2 is True, 'fresh → True')

asyncio.run(main())
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
