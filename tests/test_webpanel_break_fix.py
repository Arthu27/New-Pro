# -*- coding: utf-8 -*-
"""Ломаем веб-панель: лимиты owner, демки, журнал имён, кто отклонил апелляцию.

Запуск: python3 tests/test_webpanel_break_fix.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix='hakumo_webpanel_')
os.chdir(_TMP)
os.makedirs('data/uploads/proofs', exist_ok=True)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# stub minimal env so flask app imports
os.environ.setdefault('MAIN_GUILD_ID', '793336829280780331')
os.environ.setdefault('OWNER_ID', '111111111111111111')

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== source: owner limits exempt ==')
src = (ROOT / 'web' / 'app.py').read_text(encoding='utf-8')
check('_viewer_is_limit_exempt' in src, 'limit exempt helper')
check("'show': False" in src and 'exempt' in src, 'owner card show=False + exempt')
check('has_quota' in src, 'card only when real quotas')

print('== source: proofs from modproof ==')
check('proof_list' in src and 'modproof_' in src, 'reads modproof store')
check('/proof-media/' in src, 'serves local proof media')
check('proof-grid' in (ROOT / 'web' / 'templates' / 'proofs.html').read_text(encoding='utf-8'),
      'proofs template cards')

print('== source: appeals reviewer ==')
check('reviewer_id' in src and 'reviewed_by' in src, 'appeals show reviewed_by')
check('Решил' in (ROOT / 'web' / 'templates' / 'appeals.html').read_text(encoding='utf-8'),
      'appeals column Решил')
ap = (ROOT / 'cogs' / 'appeals.py').read_text(encoding='utf-8')
check('reviewer_id' in ap and 'display_name' in ap, 'resolve stores reviewer_id + display_name')

print('== source: cases store user_name ==')
mod = (ROOT / 'cogs' / 'moderation.py').read_text(encoding='utf-8')
check("user_name=None" in mod or "user_name =None" in mod or 'user_name=None' in mod.replace(' ', ''),
      'save_case accepts user_name')
check("'user_name':str" in mod.replace(' ', '') or "'user_name': str" in mod,
      'save_case writes user_name')

print('== runtime: proofs_list + best_name + limits ==')
# import app helpers with temp data
gid = '793336829280780331'
proof = {
    'next': 3,
    'items': {
        '1': {
            'id': 1, 'user_id': 222, 'user_name': 'Victim',
            'mod_id': 333, 'mod_name': 'Moddy',
            'action': 'бан', 'reason': '1.1', 'set_at': '2026-10-04T12:00:00+00:00',
            'review_status': 'rejected', 'reviewed_by': 'Boss',
            'channel_id': 10, 'msg_id': 20,
            'media': {
                'file': f'data/uploads/proofs/{gid}_1.jpg',
                'kind': 'image', 'name': 'x.jpg', 'size': 3, 'ctype': 'image/jpeg',
            },
        },
        '2': {
            'id': 2, 'user_id': 444, 'user_name': 'Other',
            'mod_id': 333, 'mod_name': 'Moddy',
            'action': 'мут', 'reason': 'spam', 'set_at': '2026-10-04T13:00:00+00:00',
            'review_status': 'pending',
            'channel_id': 10, 'msg_id': 21, 'media': {},
        },
    },
}
Path(f'data/modproof_{gid}.json').write_text(
    json.dumps(proof, ensure_ascii=False), encoding='utf-8')
Path(f'data/uploads/proofs/{gid}_1.jpg').write_bytes(b'\xff\xd8\xff')
Path('data/mod_data.json').write_text(json.dumps({
    'cases': {gid: [{
        'id': 1, 'action': 'ban', 'user_id': '222', 'user_name': None,
        'mod_id': '333', 'mod_name': 'Moddy',
        'reason': '1.1', 'timestamp': '2026-10-04T12:00:00+00:00',
    }]},
}), encoding='utf-8')

# load app module pieces by exec of helpers — Flask app import is heavy;
# import web.app after chdir so DATA points at tmp
os.environ['PANEL_SECRET'] = 'test-secret-please-ignore'
import web.app as W  # noqa: E402

# point DATA at tmp
W.DATA = Path('data').resolve()
W.ROOT = Path('.').resolve()
W.bot_instance = None

rows = W._proofs_list(gid)
check(len(rows) == 2, f'proofs_list returns 2 ({len(rows)})')
check(rows[0]['user_name'] == 'Other' or rows[1]['user_name'] == 'Victim',
      'proof names present', rows)
check(any(r.get('media_url') for r in rows), 'local media url', rows)
check(any(r.get('reviewer') == 'Boss' for r in rows), 'reviewer on rejected demo')

# best_name: None → id, not "—"
book = {'222': 'Victim'}
nm = W._best_name(None, '222', book)
check(nm == 'Victim', f'best_name from book ({nm})')
nm2 = W._best_name('None', '999999999999999999', {})
check(nm2 == '999999999999999999', f'best_name keeps snowflake ({nm2})')

cases = W._collect_cases(gid)
check(cases and cases[0]['user_name'] == 'Victim',
      f'collect_cases name from proof hints ({cases[0].get("user_name") if cases else None})')

# limits exempt for owner session
class FakeSess(dict):
    def get(self, k, d=None):
        return super().get(k, d)

# monkeypatch flask session via W.session is request-bound — call helper with role
from unittest import mock
with mock.patch.object(W, 'session', {'role': 'owner', 'discord_id': '111111111111111111', 'logged_in': True}):
    card = W._viewer_limits_card()
    check(card.get('show') is False, f'owner limits hidden ({card})')
    check(card.get('exempt') is True, 'owner marked exempt')
    check(W._viewer_is_limit_exempt() is True, 'limit exempt True')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
