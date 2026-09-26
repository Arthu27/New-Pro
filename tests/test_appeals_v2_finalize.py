# -*- coding: utf-8 -*-
"""Апелляции: V2-карточка после решения + меню в канале.

Баг: finalize слал content/embeds=[] на Components V2 → Discord 400,
карточка оставалась «новой» с кнопками (#14). Меню не публиковалось —
подать апелляцию было нельзя.

Запуск: python3 tests/test_appeals_v2_finalize.py
"""
import asyncio
import os
import sys
import tempfile
from datetime import datetime, timezone
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='hakumo_appeals_v2_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')

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


def _run(coro):
    return asyncio.run(coro)


UTC = timezone.utc
NOW = datetime.now(UTC)
GID = 793336829280780331

from db import GuildData  # noqa: E402
from cogs import appeals as AP  # noqa: E402
from cogs.appeals import Appeals  # noqa: E402


class _Flags:
    is_components_v2 = True


class _Msg:
    def __init__(self):
        self.id = 111
        self.channel = SimpleNamespace(id=1544483947705008188)
        self.flags = _Flags()
        self.edits = []

    async def edit(self, **kw):
        if 'content' in kw or 'embed' in kw or 'embeds' in kw:
            raise RuntimeError('V2 reject content/embeds')
        self.edits.append(kw)
        return self


class _FakeBot:
    def __init__(self):
        self.guilds = []

    def get_channel(self, cid):
        return None


print('== 1. finalize V2: только view, без content/embeds ==')
bot = _FakeBot()
cog = Appeals.__new__(Appeals)
cog.bot = bot
cog.db = GuildData('appeals')

state = AP.empty_state()
item, err = AP.create_appeal(state, 1001, 'TestUser',
                             'Прошу разбана, это ошибка', NOW)
check(item is not None, 'апелляция создана', err or '')
item['status'] = 'rejected'
item['reviewed_by'] = 'Мод'
item['message_id'] = 111
item['card_channel_id'] = 1544483947705008188
item['card_v2'] = {
    'title': f'Апелляция #{item["id"]}',
    'body': item['text'],
    'footer': 'ожидает',
    'image': None,
    'accent': 0xF1C40F,
}
cog._save(GID, state)
msg = _Msg()
guild = SimpleNamespace(id=GID, get_channel=lambda cid: None)

ok = _run(cog._finalize_appeal_card(
    guild, state, item, accept=False, unbanned=False,
    reviewer='Мод', message=msg))
check(ok is True, 'finalize вернул True')
check(len(msg.edits) == 1, f'один edit: {len(msg.edits)}')
edit = msg.edits[0] if msg.edits else {}
check('view' in edit, 'edit содержит view')
check('content' not in edit and 'embeds' not in edit and 'embed' not in edit,
      'V2 edit без content/embeds')
check(bool((item.get('card_v2') or {}).get('resolved')),
      'snapshot помечен resolved')


print('== 2. finalize V2: fallback fetch если первый edit упал ==')
state2 = AP.empty_state()
item2, err2 = AP.create_appeal(state2, 1002, 'U2',
                               'ещё одна апелляция про бан', NOW)
check(item2 is not None, 'вторая апелляция создана', err2 or '')
item2['status'] = 'accepted'
item2['message_id'] = 222
item2['card_channel_id'] = 1544483947705008188
item2['card_v2'] = {'title': 't', 'body': 'b', 'footer': 'f'}
cog._save(GID, state2)


class _BoomMsg(_Msg):
    async def edit(self, **kw):
        raise RuntimeError('transient')


class _Ch:
    def __init__(self):
        self.id = 1544483947705008188
        self.fetched = None

    async def fetch_message(self, mid):
        m = _Msg()
        m.id = mid
        self.fetched = m
        return m


ch = _Ch()
guild2 = SimpleNamespace(id=GID, get_channel=lambda cid: ch)
bot.get_channel = lambda cid: ch
boom = _BoomMsg()
ok2 = _run(cog._finalize_appeal_card(
    guild2, state2, item2, accept=True, unbanned=True,
    reviewer='Мод', message=boom))
check(ok2 is True, 'finalize после сбоя первого edit')
check(ch.fetched is not None and len(ch.fetched.edits) == 1,
      'fallback fetch+edit view-only')
fb = ch.fetched.edits[0] if ch.fetched and ch.fetched.edits else {}
check(set(fb.keys()) == {'view'}, f'fallback только view: {list(fb.keys())}')


print('== 3. publish_appeal_menu больше не публикует (только ЛС) ==')
purged = []


async def _purge(guild):
    purged.append(getattr(guild, 'id', 0))
    return True


cog._purge_appeal_menu = _purge
ch = SimpleNamespace(id=1544483947705008188, guild=SimpleNamespace(id=GID))
ok3, info3 = _run(cog.publish_appeal_menu(ch))
check(ok3 is False and 'ЛС' in info3, 'publish отказал, ссылка на ЛС', info3)
check(purged == [GID], 'publish вызвал purge старого меню')


print('== 4. purge снимает menu из state ==')


class _MsgDel:
    def __init__(self):
        self.deleted = False

    async def delete(self):
        self.deleted = True


class _PurgeCh:
    id = 1544483947705008188

    async def fetch_message(self, mid):
        return _MsgDel()


guild_p = SimpleNamespace(id=GID, get_channel=lambda cid: _PurgeCh())
bot.get_channel = lambda cid: _PurgeCh()
state_p = {'menu': {'message_id': 999, 'channel_id': 1544483947705008188},
           'items': []}
saved = {}


def _save(gid, st):
    saved['menu'] = st.get('menu')


cog._load = lambda gid: state_p
cog._save = _save
# restore real purge (was stubbed)
from cogs.appeals import Appeals as _A
cog._purge_appeal_menu = _A._purge_appeal_menu.__get__(cog, Appeals)
ok4 = _run(cog._purge_appeal_menu(guild_p))
check(ok4 is True and saved.get('menu') is None,
      'purge очистил menu в state')


print('== 5. repair вызывает finalize для rejected ==')
repaired = []


async def _fin(guild, state, item, **kw):
    repaired.append(item['id'])
    return True


cog._finalize_appeal_card = _fin
state_r = AP.empty_state()
it_r, _ = AP.create_appeal(state_r, 1003, 'U3', 'текст апелляции длинный', NOW)
it_r['status'] = 'rejected'
it_r['message_id'] = 333
it_r['card_channel_id'] = 1544483947705008188
it_r['card_v2'] = {'title': 'old', 'body': 'x'}
it_p, _ = AP.create_appeal(state_r, 1004, 'U4', 'pending text ok', NOW)
it_p['status'] = 'pending'
it_p['message_id'] = 334
it_p['card_channel_id'] = 1544483947705008188
it_p['card_v2'] = {'title': 'pend', 'body': 'y'}


class _RCh:
    id = 1544483947705008188

    async def fetch_message(self, mid):
        m = _Msg()
        m.id = mid
        return m


guild_r = SimpleNamespace(id=GID, get_channel=lambda cid: _RCh())
bot.get_channel = lambda cid: _RCh()
cog._load = lambda gid: state_r


async def _no_ch(guild):
    return None


cog._appeal_channel = _no_ch
n = _run(cog._repair_appeal_cards(guild_r))
check(it_r['id'] in repaired, 'repair finalize для rejected')
check(n >= 1, f'repair вернул count={n}')


print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
