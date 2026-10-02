# -*- coding: utf-8 -*-
"""Ломаем /modpanel: гонки reset + lag > 3с → чиним через guards.

Запуск: python3 tests/test_modpanel_stress_break.py
"""
import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='hakumo_mpstress_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cogs.moderation as M  # noqa: E402

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


class Resp:
    def __init__(self):
        self._done = False
        self.modal = []
        self.sent = []
        self.defers = 0

    def is_done(self):
        return self._done

    async def defer(self, **kw):
        self.defers += 1
        self._done = True

    async def send_message(self, **kw):
        self._done = True
        self.sent.append(kw)

    async def send_modal(self, modal):
        self._done = True
        self.modal.append(modal)


class Follow:
    async def send(self, **kw):
        return SimpleNamespace(id=999, edit=lambda **k: asyncio.sleep(0))


class Ix:
    def __init__(self, lag=0.0, uid=1):
        self.created_at = datetime.now(timezone.utc) - timedelta(seconds=lag)
        self.response = Resp()
        self.followup = Follow()
        self.user = SimpleNamespace(id=uid, roles=[], guild_permissions=SimpleNamespace(
            administrator=False, ban_members=False, manage_guild=False,
            manage_messages=False))
        self.guild = SimpleNamespace(id=1, owner_id=0, get_member=lambda x: None)
        self.guild_id = 1
        self.message = SimpleNamespace(id=42, edit=None)
        self.client = None


class SlowMsg:
    def __init__(self, delay=3.5, mid=42):
        self.id = mid
        self.edits = 0
        self.delay = delay

    async def edit(self, **kw):
        self.edits += 1
        await asyncio.sleep(self.delay)
        return self


print('== break: lag > 2.2 → soft nack, no modal ==')


async def lag_break():
    ix = Ix(lag=2.5)
    ok = await M._ack_or_busy(ix, thinking=True, limit=2.2)
    check(ok is False, 'lag break → False')
    check(ix.response.sent and 'занят' in (ix.response.sent[0].get('content') or ''),
          'user sees busy text')

asyncio.run(lag_break())

print('== break: hung panel edit must not block forever ==')


async def push_timeout():
    panel = SimpleNamespace(
        _panel_message=SlowMsg(delay=5.0, mid=7),
        _panel_message_id=7,
        _root_edit=None,
        _mod_followup=None,
    )
    t0 = asyncio.get_event_loop().time()
    ok = await M._push_panel_view(panel, None)
    dt = asyncio.get_event_loop().time() - t0
    check(ok is False, 'push fails on hang')
    check(dt < 4.5, f'push timed out fast ({dt:.2f}s < 4.5)')

asyncio.run(push_timeout())

print('== break: parallel bg resets → only latest wins ==')


async def race_resets():
    edits = []

    class Msg:
        id = 100

        async def edit(self, **kw):
            edits.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.05)
            return self

    panel = SimpleNamespace(
        selected_uid='1',
        pending_action=None,
        _panel_message=Msg(),
        _panel_message_id=100,
        _root_edit=None,
        _mod_followup=None,
        _reset_task=None,
        _reset_gen=0,
        _guild=SimpleNamespace(id=1),
        _clear_kind_mode=lambda: None,
        _rebuild=lambda g: None,
        _allowed_cache_key=None,
        allowed=[],
        base_allowed=[],
    )
    ix = Ix(0.0)
    # fire 5 overlapping bg resets (как бешеные клики)
    for _ in range(5):
        M._bg_reset_after_step(ix, panel)
        await asyncio.sleep(0)
    await asyncio.sleep(0.5)
    # gen should have advanced; edits схлопнуты debounce'ом
    check(panel._reset_gen >= 5, f'reset_gen advanced ({panel._reset_gen})')
    check(len(edits) <= 2, f'edits collapsed ({len(edits)})')

asyncio.run(race_resets())

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
