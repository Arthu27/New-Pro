# -*- coding: utf-8 -*-
"""Staff activity board: ветки + день/неделя/месяц.

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
from services.staff_board import (
    build_staff_board, fmt_voice, ROLE_TITLE, ROLE_ORDER,
    BRANCH_GROUPS, BRANCH_KEYS, branch_of_tag, resolve_span,
)

check(fmt_voice(0) == '0 мин', 'fmt 0')
check(fmt_voice(125) == '2 мин', 'fmt minutes')
check('ч' in fmt_voice(3700), 'fmt hours')

day = resolve_span('day')
week = resolve_span('week')
month = resolve_span('month')
check(day['span'] == 'day' and day['days'] == 1, f"day span ({day})")
check(week['span'] == 'week' and week['days'] >= 1 and week['days'] <= 7,
      f"week span days={week['days']}")
check(month['span'] == 'month' and month['days'] == 30, 'month span')
check(branch_of_tag('staff-admin') == 'admin', 'staff-admin → admin branch')
check(branch_of_tag('master') == 'master', 'master branch')
check(branch_of_tag('assistent') == 'assistent', 'assistent branch')
check(branch_of_tag('helper') == 'helper', 'helper branch')
check(branch_of_tag('creative') == 'branches', 'creative → branches')
check(set(BRANCH_KEYS) >= {'admin', 'master', 'assistent', 'mod', 'helper', 'branches'},
      'branch keys')

people = [
    {'id': '1', 'name': 'HelpOne', 'handle': 'h1', 'avatar': '',
     'role': 'helper', 'role_tag': 'helper', 'role_label': 'Helper'},
    {'id': '2', 'name': 'ModOne', 'handle': 'm1', 'avatar': '',
     'role': 'mod', 'role_tag': 'mod', 'role_label': 'Moderator'},
    {'id': '3', 'name': 'StaffAd', 'handle': 'sa', 'avatar': '',
     'role': 'admin', 'role_tag': 'staff-admin', 'role_label': 'Staff Admin'},
    {'id': '4', 'name': 'IdleHelp', 'handle': 'ih', 'avatar': '',
     'role': 'helper', 'role_tag': 'helper', 'role_label': 'Helper'},
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
        guild_id=1, span='week', people=people, mod_rows=mod_rows,
        include_zero=True)

check(board['summary']['actions'] == 8, f"actions sum ({board['summary']})")
check(board['summary']['messages'] == 16, f"messages ({board['summary']})")
check(board['summary']['span'] == 'week', 'summary span week')
check(any(r['key'] == 'helper' for r in board['branches']), 'branch helper')
help_br = next(r for r in board['branches'] if r['key'] == 'helper')
check(help_br['count'] >= 2, f"helpers include idle ({help_br['count']})")
check(any(r['key'] == 'admin' for r in board['branches']), 'branch admin')
admin_br = next(r for r in board['branches'] if r['key'] == 'admin')
check(admin_br['rows'][0]['id'] == '3', 'admin #1 is StaffAd')
check('by_branch' in board and 'helper' in board['by_branch'], 'by_branch map')

with mock.patch.object(sb, 'voice_window_map', return_value=voice_map), \
     mock.patch.object(sb, 'messages_window_map', return_value=msg_map):
    day_board = build_staff_board(
        guild_id=1, span='day', people=people, mod_rows=mod_rows)
check(day_board['summary']['days'] == 1, 'day board days=1')

check('Staff Admin' in ROLE_TITLE.values(), 'staff admin title')
check('Master' in ROLE_TITLE.values() and 'master' in ROLE_ORDER, 'master role on board')
for k in ('creative', 'broadcaster', 'event', 'support', 'closemod'):
    check(k in ROLE_ORDER and k in ROLE_TITLE, f'branch {k} on board')

print('== templates / css ==')
act = (ROOT / 'web' / 'templates' / '_activity.html').read_text(encoding='utf-8')
css = (ROOT / 'web' / 'static' / 'panel.css').read_text(encoding='utf-8')
staff = (ROOT / 'web' / 'templates' / 'staff.html').read_text(encoding='utf-8')
app = (ROOT / 'web' / 'app.py').read_text(encoding='utf-8')
check('act-podium' in act and 'act-kpi' in act, 'activity template board')
check('act-branch' in act and 'Все ветки' in act, 'branch panels in template')
check("span='day'" in act and 'День' in act, 'day span toggle')
check('act-branch-grids' in css and 'people-branches' in css, 'branch CSS')
check("{% include '_activity.html' %}" in staff, 'staff includes board')
check('people_by_branch' in staff, 'staff people by branch')
check('branch_filter' in app and "span == 'day'" in app.replace(' ', '')
      or "raw_span in ('day'" in app, 'app wires day+branch')
check('resolve_span' in app and 'BRANCH_KEYS' in app, 'app uses resolve_span')

print('== modpanel markers (soft) ==')
mod = (ROOT / 'cogs' / 'moderation.py').read_text(encoding='utf-8')
check('for_action=' in mod and "for_action='mute_chat'" in mod,
      'selective mute clear')
check('mute_kinds=' in mod and 'unmute_kinds=' in mod, 'kinds precomputed off UI thread')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
