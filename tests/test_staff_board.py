# -*- coding: utf-8 -*-
"""Staff activity board: меры + чат + войс, топы по ролям.

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


print('== staff_board unit ==')
from services.staff_board import build_staff_board, fmt_voice, ROLE_TITLE, ROLE_ORDER

check(fmt_voice(0) == '0 мин', 'fmt 0')
check(fmt_voice(125) == '2 мин', 'fmt minutes')
check('ч' in fmt_voice(3700), 'fmt hours')

people = [
    {'id': '1', 'name': 'HelpOne', 'handle': 'h1', 'avatar': '',
     'role': 'helper', 'role_tag': 'helper', 'role_label': 'Helper'},
    {'id': '2', 'name': 'ModOne', 'handle': 'm1', 'avatar': '',
     'role': 'mod', 'role_tag': 'mod', 'role_label': 'Moderator'},
    {'id': '3', 'name': 'StaffAd', 'handle': 'sa', 'avatar': '',
     'role': 'admin', 'role_tag': 'staff-admin', 'role_label': 'Staff Admin'},
]
mod_rows = [
    {'id': '1', 'name': 'HelpOne', 'total': 5, 'warns': 3, 'mutes': 2, 'kicks': 0, 'bans': 0},
    {'id': '2', 'name': 'ModOne', 'total': 2, 'warns': 1, 'mutes': 1, 'kicks': 0, 'bans': 0},
    {'id': '3', 'name': 'StaffAd', 'total': 1, 'warns': 0, 'mutes': 1, 'kicks': 0, 'bans': 0},
]

import services.staff_board as sb

voice_map = {
    '1': {'seconds': 600, 'name': 'HelpOne', 'avatar': ''},
    '2': {'seconds': 3600, 'name': 'ModOne', 'avatar': ''},
}
msg_map = {'1': 12, '2': 3, '3': 1}

with mock.patch.object(sb, 'voice_window_map', return_value=voice_map), \
     mock.patch.object(sb, 'messages_window_map', return_value=msg_map):
    board = build_staff_board(
        guild_id=1, days=7, people=people, mod_rows=mod_rows)

check(board['summary']['actions'] == 8, f"actions sum ({board['summary']})")
check(board['summary']['messages'] == 16, f"messages ({board['summary']})")
# ModOne: 2*12 + 3 + 60мин = 87; HelpOne: 5*12 + 12 + 10 = 82 → топ общий = Mod
check(board['podium'][0]['id'] == '2', f"overall #1 by score ({board['podium'][0]})")
places = [r['rank'] for r in board['rows']]
check(places == list(range(1, len(places) + 1)),
      f'sequential places after branches ({places})')
# снятый/ушедший с мерами в mod_activity не должен попасть в рейтинг
ghost_mods = mod_rows + [
    {'id': '99', 'name': 'Ghost', 'total': 99, 'warns': 9,
     'mutes': 0, 'kicks': 0, 'bans': 0},
]
with mock.patch.object(sb, 'voice_window_map', return_value=voice_map), \
     mock.patch.object(sb, 'messages_window_map', return_value=msg_map):
    board_g = build_staff_board(
        guild_id=1, days=7, people=people, mod_rows=ghost_mods)
check('99' not in {r['id'] for r in board_g['rows']}, 'no ghost from mod_activity')
check(any(r['key'] == 'helper' for r in board['role_tops']), 'role top helper')
helper_top = next(r for r in board['role_tops'] if r['key'] == 'helper')
check(helper_top['top'][0]['name'] == 'HelpOne', 'helper #1 among helpers')
check(helper_top['top'][0]['actions'] == 5, 'helper actions')
check('Staff Admin' in ROLE_TITLE.values(), 'staff admin title')
check('Master' in ROLE_TITLE.values() and 'master' in ROLE_ORDER, 'master role on board')
for k in ('creative', 'broadcaster', 'event', 'support', 'closemod'):
    check(k in ROLE_ORDER and k in ROLE_TITLE, f'branch {k} on board')

print('== templates / css ==')
act = (ROOT / 'web' / 'templates' / '_activity.html').read_text(encoding='utf-8')
css = (ROOT / 'web' / 'static' / 'panel.css').read_text(encoding='utf-8')
staff = (ROOT / 'web' / 'templates' / 'staff.html').read_text(encoding='utf-8')
check('act-podium' in act and 'act-kpi' in act, 'activity template board')
check('act-roles__chip' in act, 'role filter chips')
check('act-board' in css and 'act-row' in css, 'activity CSS')
check("{% include '_activity.html' %}" in staff, 'staff includes board')
check('staff_board' in (ROOT / 'web' / 'app.py').read_text(encoding='utf-8'),
      'app wires staff_board')

print('== modpanel speed markers ==')
mod = (ROOT / 'cogs' / 'moderation.py').read_text(encoding='utf-8')
check('cache_only=True' in mod, 'banner cache_only on open')
check('for_action=' in mod and "for_action='mute_chat'" in mod,
      'selective mute clear')
check('multi-fix-v20' in mod, 'build bump v20')
check('mute_kinds=' in mod and 'unmute_kinds=' in mod, 'kinds precomputed off UI thread')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
