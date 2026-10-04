# -*- coding: utf-8 -*-
"""Modpanel mute fast-path: ответ модеру до journal/watchlist/proof.

Запуск: python3 tests/test_modpanel_mute_fast.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_mfast_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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


print('== source: mute fast path ==')
check('_mute_aftermath' in src, 'aftermath helper')
check('_clear_mutes_if_needed' in src, 'skip clear when clean')
check('_member_has_any_mute' in src, 'detect existing mute state')
check("name='modpanel-mute-aftermath'" in src, 'aftermath scheduled as task')

# mute_chat: respond before aftermath
mc = src[src.index('elif action == "mute_chat"'):src.index('elif action =="vmute"')]
check('await _respond' in mc and '_mute_aftermath' in mc, 'mute_chat respond then aftermath')
check("name='modpanel-mute-aftermath')\n                    return" in mc
      or ("modpanel-mute-aftermath" in mc and 'return' in mc),
      'mute_chat returns after schedule')
check('_maybe_watchlist_after_mute' not in mc.split('await _respond')[0],
      'mute_chat: no watchlist before respond')

# timeout: parallel gather roles
to = src[src.index('elif action == "timeout"'):src.index('elif action == "mute_chat"')]
check('gather' in to and 'add_roles' in to, 'timeout parallel role adds')
check('_mute_aftermath' in to and 'do_native_timeout=True' in to,
      'timeout native deferred to aftermath')
check('await mute_state.clear_all_mutes' not in to.split('_clear_mutes_if_needed')[0],
      'timeout uses _clear_mutes_if_needed not blind clear')
check("for_action='timeout'" in to or 'for_action="timeout"' in to
      or "for_action='timeout'" in src,
      'timeout selective clear')

# vmute: no _give_punish_role on hot path; mic in aftermath
vm = src[src.index('elif action =="vmute"'):src.index('elif action =="vunmute"')]
check('_give_punish_role' not in vm, 'vmute skips heavy give_punish_role')
check('add_roles' in vm and '_mute_aftermath' in vm, 'vmute fast add_roles + aftermath')
check('do_server_mute=_in_voice' in vm, 'vmute mic deferred to aftermath')
check("label='vmute server-mute'" not in vm, 'vmute no hot-path server-mute')

# ban: respond before save_case / DM
bn = src[src.index('if action =="ban"'):src.index('elif action =="kick"')]
check('_ban_aftermath' in bn and 'await _respond' in bn, 'ban respond then aftermath')
check('save_case' not in bn.split('await _respond')[0], 'ban: no save_case before respond')
check("name='modpanel-ban-aftermath'" in src, 'ban aftermath task name')

# open: skip second ACL when no target
check("_allowed_cache_key = ('', '')" in src or '_allowed_cache_key = (\'\', \'\')' in src,
      'open skips second ACL without target')
check('if not _acked:' in src and '_ack_or_busy' in src, 'skip double ACK when modal done')

# watchlist gated at 2+
wl = src[src.index('async def _maybe_watchlist_after_mute'):src.index(
    '# ═══════════════════════════════════════════════════════════════════\n'
    '#  SELECT-МЕНЮ МОДЕРАЦИИ')]
check('mute_count < 2' in wl, 'watchlist only from 2nd mute')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
