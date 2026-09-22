# -*- coding: utf-8 -*-
"""Канал доказательств 1552088029047423027 + карточка кто/кому/за что/медиа."""
from __future__ import annotations

import asyncio
import io
import os
import sys
import tempfile

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

PASS = 0
FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== 1. Известный канал доказательств ==')
from services import channel_routes as CHR  # noqa: E402

check(CHR.PROOF_CHANNEL_ID == 1552088029047423027,
      f'PROOF_CHANNEL_ID = {CHR.PROOF_CHANNEL_ID}')
check(CHR.KNOWN_CHANNELS.get('proof_channel') == 1552088029047423027,
      'KNOWN_CHANNELS.proof_channel привязан')


class _Ch:
    def __init__(self, cid):
        self.id = cid
        self.sent = []

    async def send(self, embed=None, file=None):
        self.sent.append({'embed': embed, 'file': file})
        class _Msg:
            id = 9001
            attachments = [type('A', (), {'url': 'https://cdn.example/p.png'})()] if file else []
        return _Msg()


class _Guild:
    id = 555001

    def __init__(self, ch):
        self._ch = ch

    def get_channel(self, cid):
        return self._ch if int(cid) == int(self._ch.id) else None

    get_channel_or_thread = get_channel


print('== 2. resolve_route подставляет канал, если он есть на гильдии ==')
ch = _Ch(CHR.PROOF_CHANNEL_ID)
g = _Guild(ch)
# чистый store — без сохранённого маршрута
td = tempfile.mkdtemp(prefix='proof_ch_')
old = CHR.ROUTES_FILE
CHR.ROUTES_FILE = os.path.join(td, 'routes.json')
try:
    check(CHR.get_route(g.id, 'proof_channel') == 0, 'get_route пуст без записи')
    check(CHR.resolve_route(g.id, 'proof_channel', g) == CHR.PROOF_CHANNEL_ID,
          'resolve_route → боевой канал доказательств')
    check(CHR.resolve_route(g.id, 'proof_channel', None) == 0,
          'без guild известный ID не подставляем вслепую')
finally:
    CHR.ROUTES_FILE = old


print('== 3. ProofCog._proof_channel читает resolve_route ==')
from cogs.proof_cog import ProofCog, proof_add, try_deliver_proof_bytes  # noqa: E402
import cogs.proof_cog as PC  # noqa: E402

CHR.ROUTES_FILE = os.path.join(td, 'routes2.json')
try:
    got = asyncio.run(ProofCog._proof_channel(object.__new__(ProofCog), g))
    check(getattr(got, 'id', None) == CHR.PROOF_CHANNEL_ID,
          f'_proof_channel → {getattr(got, "id", None)}')
finally:
    CHR.ROUTES_FILE = old


print('== 4. Карточка: кто выдал / кому / за что / медиа ==')
cog = object.__new__(ProofCog)
entry = {
    'id': 7,
    'user_id': 111,
    'mod_id': 222,
    'mod_name': 'ModAlice',
    'action': 'мут',
    'reason': 'спам в общем',
    'link': None,
    'media': {'kind': 'image', 'name': 'shot.png'},
}
emb = ProofCog._proof_embed(cog, '<@111>', entry)
names = [f.name for f in emb.fields]
check('Кто выдал' in names and 'Кому' in names and 'За что' in names,
      f'поля карточки: {names}')
who = next(f.value for f in emb.fields if f.name == 'Кто выдал')
what = next(f.value for f in emb.fields if f.name == 'За что')
check('ModAlice' in who and '222' in who, f'кто выдал: {who}')
check('спам в общем' in what, f'за что: {what}')
media_f = next((f for f in emb.fields if f.name == 'Медиа'), None)
check(media_f is not None and 'Фото' in media_f.value, f'медиа: {media_f}')


print('== 5. try_deliver_proof_bytes постит файл в канал ==')
# подмена DATA_DIR через временный cwd для modproof json
old_cwd = os.getcwd()
os.chdir(td)
try:
    class _Bot:
        def get_cog(self, name):
            return self._cog if name == 'ProofCog' else None

    class _User:
        def __init__(self, uid, name):
            self.id = uid
            self.display_name = name

        def __str__(self):
            return self.display_name

    bot = _Bot()
    real = ProofCog(bot)
    bot._cog = real
    # _proof_channel → наш канал
    async def _ch(guild):
        return ch
    real._proof_channel = _ch  # type: ignore

    png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64
    mod = _User(222, 'ModAlice')
    bad = _User(111, 'BadGuy')
    status = asyncio.run(try_deliver_proof_bytes(
        bot, g, mod, bad, 'мут', 'спам в общем',
        'shot.png', png, 'image/png'))
    check(status and 'Демка #' in status, f'status: {status}')
    check(len(ch.sent) == 1, 'сообщение ушло в канал')
    sent = ch.sent[0]
    check(sent['file'] is not None, 'файл во вложении')
    emb2 = sent['embed']
    fnames = [f.name for f in emb2.fields]
    check('Кто выдал' in fnames and 'Кому' in fnames and 'За что' in fnames,
          f'пост в канал с полями: {fnames}')
finally:
    os.chdir(old_cwd)
    CHR.ROUTES_FILE = old


print('== 6. proof_is_required по умолчанию ВКЛ ==')
from cogs.proof_cog import proof_is_required, _PROOF_REQ_CACHE  # noqa: E402
_PROOF_REQ_CACHE.clear()
check(proof_is_required(987654321098) is True,
      'без конфига — доказательства обязательны')


print(f'\nИтого: {PASS} PASS / {FAIL} FAIL')
sys.exit(1 if FAIL else 0)
