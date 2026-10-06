# -*- coding: utf-8 -*-
"""Staff activity: орг-ветки + день/неделя/месяц.

Запуск: python3 tests/test_staff_board.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

_TMP = tempfile.mkdtemp(prefix='hakumo_sboard_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== org branches ==')
from services.staff_board import (
    build_staff_board, fmt_voice, ROLE_TITLE, ROLE_ORDER,
    BRANCH_GROUPS, BRANCH_KEYS, branch_of_tag, resolve_span,
    org_branches_of, person_org_branches,
)
from services import staff_roles as SR

check(fmt_voice(0) == '0 мин', 'fmt 0')
day = resolve_span('day')
week = resolve_span('week')
check(day['days'] == 1, 'day=1')
check(week['span'] == 'week', 'week span')

# Helper grant → helper branch
hb = org_branches_of([SR.KNOWN_HELPER_ROLE_ID])
check(hb == ['helper'], f'helper grant → {hb}')

# Mod curator → moderator branch (не «Мастера»!)
mb = org_branches_of([SR.KNOWN_CURATOR_BY_KIND['moderator']])
check(mb == ['moderator'], f'mod curator → {mb}')

# Creative curator + grant
cb = org_branches_of([
    SR.KNOWN_CURATOR_BY_KIND['creative'],
    SR.KNOWN_GRANT_BY_KIND['creative'],
])
check(cb == ['creative'], f'creative → {cb}')

# Master без grant/curator → только leadership (не Helper!)
mst = org_branches_of([SR.KNOWN_MASTER_ROLE_ID])
check(mst == ['leadership'], f'master alone → {mst}')

# Assistent без grant/curator → leadership
ast = org_branches_of([SR.KNOWN_ASSISTENT_ROLE_ID])
check(ast == ['leadership'], f'assistent alone → {ast}')

# Master + helper grant → только Helper
mh = org_branches_of([SR.KNOWN_MASTER_ROLE_ID, SR.KNOWN_HELPER_ROLE_ID])
check(mh == ['helper'], f'master+helper → {mh}')

# Assistent + mod curator → только Moderator
am = org_branches_of([
    SR.KNOWN_ASSISTENT_ROLE_ID,
    SR.KNOWN_CURATOR_BY_KIND['moderator'],
])
check(am == ['moderator'], f'asst+mod curator → {am}')

# Admin only → leadership
ab = org_branches_of([SR.KNOWN_ADMIN_ROLE_ID])
check(ab == ['leadership'], f'admin → {ab}')

# Admin who is also helper curator → helper (not only leadership)
ah = org_branches_of([
    SR.KNOWN_ADMIN_ROLE_ID,
    SR.KNOWN_CURATOR_BY_KIND['helper'],
])
check('helper' in ah and 'leadership' not in ah, f'admin+helper curator → {ah}')

# Common staff без ветки → не Helper
cm = org_branches_of([SR.KNOWN_COMMON_STAFF_ROLE_ID])
check(cm == ['leadership'], f'common staff → {cm}')

# fallback tag curator без role_ids → leadership (не Helper)
fb = person_org_branches({'role': 'curator', 'role_tag': 'curator'})
check(fb == ['leadership'], f'tag curator fallback → {fb}')

check('moderator' in BRANCH_KEYS and 'helper' in BRANCH_KEYS, 'org keys')
check('admin' not in BRANCH_KEYS or 'leadership' in BRANCH_KEYS, 'no rank-admin bag')
check(branch_of_tag('mod') == 'moderator', 'tag mod→moderator')
check(branch_of_tag('assistent') == 'leadership', 'tag asst→leadership')

print('== board build ==')
people = [
    {'id': '1', 'name': 'HelpOne', 'handle': 'h1', 'avatar': '',
     'role': 'helper', 'role_tag': 'helper', 'role_label': 'Helper',
     'role_ids': [SR.KNOWN_HELPER_ROLE_ID]},
    {'id': '2', 'name': 'ModCur', 'handle': 'mc', 'avatar': '',
     'role': 'curator', 'role_tag': 'curator', 'role_label': 'Curator',
     'role_ids': [SR.KNOWN_CURATOR_BY_KIND['moderator']]},
    {'id': '3', 'name': 'MasterX', 'handle': 'mx', 'avatar': '',
     'role': 'master', 'role_tag': 'master', 'role_label': 'Master',
     'role_ids': [SR.KNOWN_MASTER_ROLE_ID]},
    {'id': '4', 'name': 'AdminOnly', 'handle': 'ao', 'avatar': '',
     'role': 'admin', 'role_tag': 'admin', 'role_label': 'Admin',
     'role_ids': [SR.KNOWN_ADMIN_ROLE_ID]},
    {'id': '5', 'name': 'HelpMaster', 'handle': 'hm', 'avatar': '',
     'role': 'master', 'role_tag': 'master', 'role_label': 'Master',
     'role_ids': [SR.KNOWN_MASTER_ROLE_ID, SR.KNOWN_HELPER_ROLE_ID]},
]
mod_rows = [
    {'id': '1', 'name': 'HelpOne', 'total': 5, 'warns': 3, 'mutes': 2, 'kicks': 0, 'bans': 0},
    {'id': '2', 'name': 'ModCur', 'total': 2, 'warns': 1, 'mutes': 1, 'kicks': 0, 'bans': 0},
]

import services.staff_board as sb
voice_map = {'1': {'seconds': 600, 'name': 'HelpOne', 'avatar': ''}}
msg_map = {'1': 12, '2': 3}

with mock.patch.object(sb, 'voice_window_map', return_value=voice_map), \
     mock.patch.object(sb, 'messages_window_map', return_value=msg_map):
    board = build_staff_board(
        guild_id=1, span='week', people=people, mod_rows=mod_rows,
        include_zero=True)

keys = {b['key'] for b in board['branches']}
check('helper' in keys, f'helper branch present {keys}')
check('moderator' in keys, f'moderator branch present {keys}')
check('leadership' in keys, f'leadership present {keys}')
check('master' not in keys and 'admin' not in keys,
      'no rank-based Master/Admin sections')

mod_br = next(b for b in board['branches'] if b['key'] == 'moderator')
mod_ids = {r['id'] for r in mod_br['rows']}
check('2' in mod_ids, 'mod curator in Moderator branch')
check('3' not in mod_ids, 'lone master NOT in Moderator')

help_br = next(b for b in board['branches'] if b['key'] == 'helper')
help_ids = {r['id'] for r in help_br['rows']}
check('1' in help_ids, 'helper grant in Helper')
check('3' not in help_ids, 'lone master NOT in Helper')
check('5' in help_ids, 'master+helper grant in Helper')

lead = next(b for b in board['branches'] if b['key'] == 'leadership')
lead_ids = {r['id'] for r in lead['rows']}
check('4' in lead_ids and '3' in lead_ids, 'admin + lone master in Старшие')

print('== templates / login ==')
act = (ROOT / 'web' / 'templates' / '_activity.html').read_text(encoding='utf-8')
staff = (ROOT / 'web' / 'templates' / 'staff.html').read_text(encoding='utf-8')
app = (ROOT / 'web' / 'app.py').read_text(encoding='utf-8')
check('Все ветки' in act and 'act-branch' in act, 'branch UI')
check('Moderator' in staff or 'орг-ветк' in staff.lower() or 'Орг-ветки' in staff,
      'staff copy org branches')
check('_resolve_staff_person' in app, 'login resolve by id')
check('auth_ticket' in app and 'panel_login_tickets' in app, 'dm ticket login')
check('limit=300' in app, 'login people limit 300')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
