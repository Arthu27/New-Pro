# -*- coding: utf-8 -*-
"""Create / login member search helpers."""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_create_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['PANEL_INVITE_CODE'] = 'Hakumo-Invite'

PASS = 0
FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== invite casefold ==')
from web import app as W  # noqa: E402

check(W._invite_ok('hakumo-invite'), 'lower ok')
check(W._invite_ok('HAKUMO-INVITE'), 'upper ok')
check(W._invite_ok('Hakumo-Invite'), 'mixed ok')
check(not W._invite_ok('hakumo_invite'), 'wrong separator rejected')
check(not W._invite_ok(''), 'empty rejected')

print('== match rank ==')
check(W._match_rank('z1tkali', name='Z1tkali', handle='shivasguardddd', uid='1') == 0,
      'exact name rank 0')
check(W._match_rank('shi', name='Z1tkali', handle='shivasguardddd', uid='1') == 1,
      'handle prefix rank 1')
check(W._match_rank('zzz', name='Z1tkali', handle='shi', uid='1') >= 9,
      'no match high rank')

print('== api snapshot ==')
snap = W._snapshot_from_api_member({
    'nick': 'Дотер',
    'roles': ['1'],
    'user': {
        'id': '1146382053588336693',
        'username': 'aidoxe228',
        'global_name': 'Aidoxe',
        'avatar': 'abc',
        'bot': False,
    },
}, role='mod')
check(snap['id'] == '1146382053588336693', 'id')
check(snap['name'] == 'Дотер', 'nick preferred')
check(snap['handle'] == 'aidoxe228', 'handle')
check('avatars/1146382053588336693/abc.png' in snap['avatar'], 'avatar url')

print('== rest member wrapper ==')
rm = W._RestMember({
    'nick': 'Дотер',
    'roles': ['10', '20'],
    'user': {
        'id': '1146382053588336693',
        'username': 'aidoxe228',
        'global_name': 'Aidoxe',
        'avatar': None,
        'bot': False,
    },
})
check(rm.id == 1146382053588336693, 'rest id')
check(rm.display_name == 'Дотер', 'rest display')
check(len(rm.roles) == 2, 'rest roles')
check(bool(rm.display_avatar.url), 'rest avatar')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
raise SystemExit(1 if FAIL else 0)
