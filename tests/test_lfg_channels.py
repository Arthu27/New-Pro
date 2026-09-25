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
os.environ['LFG_MARKER'] = os.path.join(_TMP, 'data', '.lfg_teammates_rules.v2')

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
check(LFG.channel_kind(LFG.TEAMMATES_CHANNEL_ID) == 'teammates', 'kind teammates')
check(LFG.channel_kind(LFG.DATING_CHANNEL_ID) == 'dating', 'kind dating')

print('== v2 rules card ==')
view = LFG.build_lfg_rules_view(kind='teammates')
emb = LFG.build_lfg_rules_embed(kind='teammates')
check(emb is not None and 'тиммейты' in (emb.description or ''), 'embed fallback teammates')
check('Реклама' in LFG.RULES_BODY_TEAMMATES, 'body mentions ads ban')
# V2 may be unavailable in slim env — then view is None (ok)
from services.v2_layouts import V2_AVAILABLE
if V2_AVAILABLE:
    check(view is not None, 'V2 LayoutView собран')
else:
    check(view is None, 'без V2 — view None (фолбек embed)')

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
