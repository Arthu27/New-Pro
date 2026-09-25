# -*- coding: utf-8 -*-
"""LFG channels: teammates like dating + ads seed."""
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_lfg_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['LFG_MARKER'] = os.path.join(_TMP, 'data', '.lfg_teammates_rules.v1')

from services import lfg_channels as LFG  # noqa: E402
from cogs import auto_filter as AF  # noqa: E402

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== lfg constants ==')
check(LFG.TEAMMATES_CHANNEL_ID == 1312552287360516207, 'тиммейты id')
check(LFG.DATING_CHANNEL_ID == 1312430207067623456, 'знакомства id')
check('реклама' in LFG.TEAMMATES_TOPIC.lower(), 'topic про рекламу')
check(LFG.ads_apply_channels() == [
    str(LFG.DATING_CHANNEL_ID), str(LFG.TEAMMATES_CHANNEL_ID)
], 'ads apply = dating+teammates')

print('== ads seed ==')
gid = 793336829280780331
cfg = LFG.ensure_autofilter_ads(gid)
check(cfg['enabled'] is True and cfg['ads']['enabled'] is True, 'seed включает ads')
check(cfg['ads']['apply_channels'] == LFG.ads_apply_channels(), 'seed каналы LFG')
check(os.path.exists('data/.lfg_ads_seed.v1'), 'seed marker')
# повтор не ломает выключение владельцем
AF.save_config(gid, {'enabled': False, 'ads': {'enabled': False, 'apply_channels': []}})
cfg2 = LFG.ensure_autofilter_ads(gid)
back = AF.load_config(gid)
check(back['enabled'] is False and back['ads']['enabled'] is False,
      'повторный seed не форсит enabled обратно')

print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
