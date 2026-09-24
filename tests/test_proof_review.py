# -*- coding: utf-8 -*-
"""Тесты потока демки после мута: collect → review → approve/reject."""
import os
import sys
import tempfile
import shutil

_TMP = tempfile.mkdtemp(prefix='hakumo_proof_rev_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402
config.Config.DB_PATH = os.path.abspath('data/bot.db')

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== 1. channel_routes KNOWN proof ==')
from services import channel_routes as CR
check(CR.PROOF_CHANNEL_ID == 1552088029047423027, 'PROOF_CHANNEL_ID')
check(CR.KNOWN_CHANNELS.get('proof_channel') == 1552088029047423027,
      'KNOWN proof_channel')

print('== 2. proof_review helpers ==')
from services import proof_review as PR
check('mute_chat' in PR.MUTE_PROOF_ACTIONS and 'vmute' in PR.MUTE_PROOF_ACTIONS,
      'mute actions covered')
check(PR.action_label('mute_chat') == 'Мут чата', 'label mute_chat')
check('готово' in PR.DONE_WORDS and '+' in PR.DONE_WORDS, 'done words')

print('== 3. V2 proof review layout ==')
from services.v2_layouts import V2_AVAILABLE, build_proof_review_items
if V2_AVAILABLE:
    items = build_proof_review_items(
        title='Демка #1', body='тест', footer='Hakumo',
        media_filenames=['a.png', 'b.mp4'], select=None, accent=0xE67E22)
    check(bool(items), f'build_proof_review_items → {type(items)}')
    import discord
    sel = discord.ui.Select(
        placeholder='x', options=[
            discord.SelectOption(label='Одобрить', value='approve'),
            discord.SelectOption(label='Отклонить', value='reject'),
        ], custom_id='proofrev:sel:1')
    items2 = build_proof_review_items(
        title='Демка #1', body='тест', select=sel, media_urls=['https://cdn.example/a.png'])
    check(bool(items2), 'layout with real Select + media_urls')
else:
    check(True, 'V2 недоступен в окружении — skip layout')

print('== 4. proof entry + review fields ==')
from cogs.proof_cog import proof_add, proof_update, proof_get
e = proof_add(1, 100, 'User', 200, 'Mod', 'Мут чата', 'спам')
proof_update(1, e['id'], mute_action='mute_chat', case_id=7,
             review_status='pending_review', media_list=[{'filename': 'p1.png'}])
got = proof_get(1, e['id'])
check(got.get('review_status') == 'pending_review', 'pending_review stored')
check(got.get('mute_action') == 'mute_chat', 'mute_action stored')
check(got.get('case_id') == 7, 'case_id stored')

print('== 5. moderation hooks source ==')
src = open(os.path.join(ROOT, 'cogs/moderation.py'), encoding='utf-8').read()
check('start_proof_collection' in src, 'moderation calls start_proof_collection')
check("action not in _mute_proof" in src or "action not in _mute_proof" in src.replace(' ', ''),
      'mute skips pre-require_proof')
flow = open(os.path.join(ROOT, 'cogs/proof_flow.py'), encoding='utf-8').read()
check('ProofReviewSelect' in flow and 'proofrev:sel:' in flow, 'select custom_id')
check('consume_unmute_limit' in flow and 'undo_mute' in flow, 'reject → unmute')
check('HOOK_USERNAME' in flow and 'webhook' in flow.lower(), 'webhook path')

print('== 6. ProofCog listener ==')
pc = open(os.path.join(ROOT, 'cogs/proof_cog.py'), encoding='utf-8').read()
check('on_moderator_message' in pc and 'async def on_message' in pc,
      'ProofCog.on_message → collector')
check('register_pending_views' in pc, 'cog_load registers views')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
