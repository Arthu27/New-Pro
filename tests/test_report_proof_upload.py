# -*- coding: utf-8 -*-
"""/report FileUpload → демка в канал модерации (deliver_report_proofs)."""
import asyncio
import io
import os
import sys
import tempfile
from types import SimpleNamespace as NS

_TMP = tempfile.mkdtemp(prefix='hakumo_rp_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.abspath('data/bot.db')

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== wiring: модалка + helper ==')
rep = open(os.path.join(ROOT, 'cogs', 'reports.py'), encoding='utf-8').read()
prf = open(os.path.join(ROOT, 'cogs', 'proof_cog.py'), encoding='utf-8').read()
check('proof_upload' in rep and 'FileUpload' in rep,
      'ReportModal: FileUpload proof_upload')
check('Доказательства' in rep, 'Label «Доказательства» в форме')
check('deliver_report_proofs' in rep and 'deliver_report_proofs' in prf,
      'reports → deliver_report_proofs')
check("action, 'жалоба'" in prf or "'жалоба'" in prf,
      'демка из репорта с action=жалоба')
check('case_id' in prf and 'report:' in prf,
      'связь демки с карточкой report:<msg_id>')


print('== deliver_report_proofs runtime ==')
from cogs import proof_cog as P  # noqa: E402


class _Att:
    def __init__(self, name='shot.png', data=b'\x89PNG\r\n\x1a\n' + b'x' * 32):
        self.filename = name
        self.content_type = 'image/png'
        self.size = len(data)
        self.url = 'https://cdn.example/shot.png'
        self._data = data

    async def read(self):
        return self._data


class _FakeProofCog:
    def __init__(self):
        self.calls = []

    async def _create_and_post(self, guild, moderator, user, action, reason,
                               attachment=None, link=None):
        self.calls.append({
            'action': action, 'reason': reason,
            'att': getattr(attachment, 'filename', None),
            'user': getattr(user, 'id', None),
            'mod': getattr(moderator, 'id', None),
        })
        entry = P.proof_add(
            guild.id, user.id, str(user),
            moderator.id, str(moderator), action, reason)
        return True, entry, None


async def _run():
    cog = _FakeProofCog()
    bot = NS(get_cog=lambda n: cog if n == 'ProofCog' else None)
    guild = NS(id=42)
    reporter = NS(id=7, display_name='Rep')
    accused = NS(id=9, display_name='Acc')
    ids, notes = await P.deliver_report_proofs(
        bot, guild, reporter, accused, 'спам в чате',
        [_Att()], report_msg_id=555)
    check(ids == [1], f'одна демка создана (ids={ids})')
    check(not notes, f'без замечаний (notes={notes})')
    check(len(cog.calls) == 1 and cog.calls[0]['action'] == 'жалоба',
          'action=жалоба')
    check('report:555' in (cog.calls[0]['reason'] or ''),
          'reason содержит report:msg_id')
    entry = P.proof_get(42, 1) or {}
    check(entry.get('case_id') == 'report:555',
          f'case_id=report:555 (got {entry.get("case_id")!r})')

    # пустой список — no-op
    ids2, notes2 = await P.deliver_report_proofs(
        bot, guild, reporter, accused, 'x', [], report_msg_id=1)
    check(ids2 == [] and notes2 == [], 'без файлов — пустой результат')

    # не медиа — пропуск
    bad = _Att(name='notes.txt', data=b'hello')
    bad.content_type = 'text/plain'
    ids3, _ = await P.deliver_report_proofs(
        bot, guild, reporter, accused, 'x', [bad])
    check(ids3 == [], 'не-медиа пропускается')


asyncio.run(_run())
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
