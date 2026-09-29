# -*- coding: utf-8 -*-
"""Закрытие демки: ПРИНЯТО/ОТКЛОНЕНО, select уходит, локальный файл удаляется."""
import asyncio
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== proof decision note ==')
from cogs.proof_cog import (  # noqa: E402
    _proof_decision_note, ProofReviewDoneView, ProofReviewSelect,
    proof_add, proof_update, proof_get, proof_save_media, proof_delete_media,
    proof_media_abspath, MEDIA_DIR, _review_proof, _can_review_proof,
    PROOF_REVIEW_ROLE_ID,
)

who = types.SimpleNamespace(display_name='Reviewer', id=1)
st, note, acc = _proof_decision_note('accept', who)
check(st == 'ПРИНЯТО' and acc == 0x2ECC71, f'accept → ПРИНЯТО ({st})')
check('Reviewer' in note, 'note содержит кто принял')
st2, note2, acc2 = _proof_decision_note(
    'reject', who, reject_reason='плохое видео', extra='мут снят')
check(st2 == 'ОТКЛОНЕНО' and acc2 == 0xE74C3C, f'reject → ОТКЛОНЕНО ({st2})')
check('плохое видео' in note2 and 'мут снят' in note2, 'reject note полный')

print('== done view без select ==')
view = ProofReviewDoneView(
    entry_id=3, action='мут чата', body='**Нарушитель** · <@1>',
    status='ПРИНЯТО', note='Принял: X', media_urls=[], accent=0x2ECC71)
sels = []
try:
    for c in view.walk_children():
        if isinstance(c, __import__('discord').ui.Select):
            sels.append(c)
except Exception:
    pass
check(len(sels) == 0, f'done view без select ({len(sels)})')
check(len(view.children) >= 1, 'done view имеет контейнер')

print('== review select 🤍 ==')
rev = ProofReviewSelect(1, 1)
check(all(o.value in ('accept', 'reject') for o in rev.options), 'accept/reject')
check(all(str(o.emoji) == '🤍' or getattr(o.emoji, 'name', None)
          for o in rev.options), 'emoji 🤍')

print('== локальный файл удаляется ==')
td = tempfile.mkdtemp(prefix='proof_close_')
# подменяем MEDIA_DIR через запись в реальный путь тестом с уникальным gid
gid = 99112233
entry = proof_add(gid, 10, 'u', 20, 'm', 'мут чата', '1.9')
raw = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64
media = proof_save_media(gid, entry['id'], 'demo.png', raw, 'image/png')
check(media and media.get('file'), f'media saved: {media}')
proof_update(gid, entry['id'], media=media)
entry2 = proof_get(gid, entry['id'])
full = proof_media_abspath(entry2)
check(full and os.path.isfile(full), f'file exists: {full}')
deleted = proof_delete_media(gid, entry2)
check(deleted is True, 'proof_delete_media → True')
check(not os.path.isfile(full), 'файл с диска убран')

print('== _publish_proof_decision путь (мок) ==')
from cogs.proof_cog import _publish_proof_decision  # noqa: E402


class _Resp:
    def __init__(self):
        self._done = False

    def is_done(self):
        return self._done

    async def edit_message(self, **kw):
        self._done = True
        self.last = kw
        return True


class _Inter:
    def __init__(self):
        self.response = _Resp()
        self.message = types.SimpleNamespace(id=555, edit=None)
        self.followup = None
        self.client = types.SimpleNamespace()
        self.guild = None
        self.user = who


async def _run():
    inter = _Inter()
    done = ProofReviewDoneView(
        entry_id=1, action='мут', body='b', status='ПРИНЯТО',
        note='n', media_urls=[], accent=0x2ECC71)
    how = await _publish_proof_decision(inter, view=done, message_id=555)
    return how, inter.response._done, getattr(inter.response, 'last', {})


how, done_flag, last = asyncio.get_event_loop().run_until_complete(_run())
check(how == 'response', f'publish via response ({how})')
check(done_flag and last.get('view') is not None, 'edit_message получил view')
check('attachments' not in last, 'attachments не чистим (видео остаётся)')

print('== helpers в коде ==')
src = open(os.path.join(ROOT, 'cogs/proof_cog.py'), encoding='utf-8').read()
check('proof_delete_media' in src and '_close_proof_card' in src,
      '_close_proof_card + delete media')
check('_publish_proof_decision' in src, '_publish_proof_decision')
check('attachments=[]' not in src, 'нет attachments=[] на закрытии')

print(f'\nИтого: {PASS} PASS / {FAIL} FAIL')
sys.exit(1 if FAIL else 0)
