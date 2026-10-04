# -*- coding: utf-8 -*-
"""Staff Admin / Assistent в панели, демки с перерешением, каналы подробно.

Запуск: python3 tests/test_webpanel_roles_proofs_channels.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

_TMP = tempfile.mkdtemp(prefix='hakumo_roles_proofs_')
os.chdir(_TMP)
os.makedirs('data/uploads/proofs', exist_ok=True)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault('MAIN_GUILD_ID', '793336829280780331')
os.environ.setdefault('OWNER_ID', '111111111111111111')
os.environ['PANEL_SECRET'] = 'test-secret-please-ignore'

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== source maps ==')
src = (ROOT / 'web' / 'app.py').read_text(encoding='utf-8')
check("'assistent': 4" in src or "'assistent':4" in src.replace(' ', ''),
      'LEVEL has assistent')
check('KNOWN_STAFF_ADMIN_ROLE_ID' in src, 'staff role bags include Staff Admin')
check('KNOWN_ASSISTENT_ROLE_ID' in src and 'KNOWN_STAFF_ASSISTENT_ROLE_ID' in src,
      'staff role bags include Assistent')
check('panel_role_display' in src, 'display labels helper')
check('review_proof_panel' in (ROOT / 'cogs' / 'proof_cog.py').read_text(encoding='utf-8'),
      'panel redecide in proof_cog')
check('_can_redecide_proof' in (ROOT / 'cogs' / 'proof_cog.py').read_text(encoding='utf-8'),
      'redecide ACL')
check("url_for('proof_detail'" in (ROOT / 'web' / 'templates' / 'proofs.html').read_text(encoding='utf-8')
      or 'proof_detail' in (ROOT / 'web' / 'templates' / 'proofs.html').read_text(encoding='utf-8'),
      'proofs link to detail')
check('Перерешение' in (ROOT / 'web' / 'templates' / 'proof_detail.html').read_text(encoding='utf-8'),
      'detail has redecide form')
check('route_label' in (ROOT / 'web' / 'templates' / 'channels.html').read_text(encoding='utf-8'),
      'channels show bot routes')
check('tag-assistent' in (ROOT / 'web' / 'static' / 'panel.css').read_text(encoding='utf-8'),
      'CSS tag for assistent')

print('== runtime resolve roles ==')
import web.app as W  # noqa: E402
W.DATA = Path('data').resolve()
W.ROOT = Path('.').resolve()
W.bot_instance = None

from services.staff_roles import (
    KNOWN_STAFF_ADMIN_ROLE_ID, KNOWN_ADMIN_ROLE_ID,
    KNOWN_ASSISTENT_ROLE_ID, KNOWN_STAFF_ASSISTENT_ROLE_ID,
    KNOWN_HELPER_ROLE_ID, KNOWN_MODERATOR_ROLE_ID,
)

bags = W._staff_role_id_set()
check(int(KNOWN_STAFF_ADMIN_ROLE_ID) in bags['admin'], 'Staff Admin in admin bag')
check(int(KNOWN_ASSISTENT_ROLE_ID) in bags['assistent'], 'Assistent in assistent bag')
check(int(KNOWN_STAFF_ASSISTENT_ROLE_ID) in bags['assistent'],
      'Staff Assistent in assistent bag')

r = W.resolve_discord_panel_role('999', [KNOWN_STAFF_ADMIN_ROLE_ID])
check(r == 'admin', f'Staff Admin → admin ({r})')
lab = W.panel_role_display(r, [KNOWN_STAFF_ADMIN_ROLE_ID])
check(lab == 'Staff Admin', f'label Staff Admin ({lab})')

r2 = W.resolve_discord_panel_role('998', [KNOWN_ASSISTENT_ROLE_ID])
check(r2 == 'assistent', f'Assistent → assistent ({r2})')
lab2 = W.panel_role_display(r2, [KNOWN_ASSISTENT_ROLE_ID])
check(lab2 == 'Assistent', f'label Assistent ({lab2})')

r3 = W.resolve_discord_panel_role('997', [KNOWN_STAFF_ASSISTENT_ROLE_ID])
check(r3 == 'assistent', f'Staff Assistent → assistent ({r3})')
lab3 = W.panel_role_display(r3, [KNOWN_STAFF_ASSISTENT_ROLE_ID])
check(lab3 == 'Staff Assistent', f'label Staff Assistent ({lab3})')

r4 = W.resolve_discord_panel_role('996', [KNOWN_ADMIN_ROLE_ID])
check(r4 == 'admin', f'Admin → admin ({r4})')
lab4 = W.panel_role_display(r4, [KNOWN_ADMIN_ROLE_ID])
check(lab4 == 'Admin', f'label Admin ({lab4})')

# hierarchy: staff admin beats assistent
r5 = W.resolve_discord_panel_role(
    '995', [KNOWN_ASSISTENT_ROLE_ID, KNOWN_STAFF_ADMIN_ROLE_ID])
check(r5 == 'admin', f'staff admin > assistent ({r5})')

# helper alone still works
r6 = W.resolve_discord_panel_role('994', [KNOWN_HELPER_ROLE_ID])
check(r6 == 'helper', f'helper ({r6})')
r7 = W.resolve_discord_panel_role('993', [KNOWN_MODERATOR_ROLE_ID])
check(r7 == 'mod', f'mod ({r7})')

print('== proof decide ACL ==')
with mock.patch.object(W, 'session', {'role': 'owner', 'discord_id': '111111111111111111'}):
    check(W._panel_can_decide_proof() is True, 'owner can decide')
with mock.patch.object(W, 'session', {'role': 'admin', 'discord_id': '1'}):
    check(W._panel_can_decide_proof() is True, 'admin can decide')
with mock.patch.object(W, 'session', {'role': 'assistent', 'discord_id': '1'}):
    check(W._panel_can_decide_proof() is False, 'assistent cannot redecide')
with mock.patch.object(W, 'session', {'role': 'mod', 'discord_id': '1'}):
    check(W._panel_can_decide_proof() is False, 'mod cannot redecide')

print('== LEVEL order ==')
check(W.LEVEL['assistent'] > W.LEVEL['curator'], 'assistent > curator')
check(W.LEVEL['admin'] > W.LEVEL['assistent'], 'admin > assistent')
check(W.LEVEL['owner'] > W.LEVEL['admin'], 'owner > admin')

print('== staff board rank / tags ==')
check(W.staff_board_rank('admin', 'Staff Admin') < W.staff_board_rank('admin', 'Admin'),
      'Staff Admin выше Admin на доске')
check(W.staff_board_rank('assistent', 'Staff Assistent') < W.staff_board_rank('admin', 'Admin'),
      'Staff Assistent выше Admin на доске')
check(W.staff_board_rank('admin', 'Staff Admin') < W.staff_board_rank('assistent', 'Staff Assistent'),
      'Staff Admin выше Staff Assistent')
check(W.panel_role_tag('admin', [KNOWN_STAFF_ADMIN_ROLE_ID]) == 'staff-admin',
      'tag staff-admin')
check(W.panel_role_tag('assistent', [KNOWN_STAFF_ASSISTENT_ROLE_ID]) == 'staff-assistent',
      'tag staff-assistent')
check(W.panel_role_tag('admin', [KNOWN_ADMIN_ROLE_ID]) == 'admin', 'tag admin')

css = (ROOT / 'web' / 'static' / 'panel.css').read_text(encoding='utf-8')
check('tag-staff-admin' in css and 'tag-staff-assistent' in css, 'CSS staff tags')
check('p-card__top' in css and 'text-overflow: ellipsis' in css, 'staff card no-overlap CSS')
check('proof-decide-form__input' in css and 'max-height: 160px' in css, 'proof detail compact/dark')
staff_html = (ROOT / 'web' / 'templates' / 'staff.html').read_text(encoding='utf-8')
check('role_tag' in staff_html and 'p-card__name' in staff_html, 'staff template uses role_tag')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
