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

print('== break: cancel mid-push must not stale-overwrite newer reset ==')


async def cancel_stale_push():
    edits = []

    class SlowMsg:
        id = 200

        async def edit(self, **kw):
            edits.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.35)  # как медленный Discord
            return self

    panel = SimpleNamespace(
        selected_uid='9',
        pending_action=None,
        _panel_message=SlowMsg(),
        _panel_message_id=200,
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
    M._bg_reset_after_step(ix, panel)
    await asyncio.sleep(0.08)  # первый уже в push
    M._bg_reset_after_step(ix, panel)  # cancel + новый gen
    await asyncio.sleep(0.9)
    # без фикса CancelledError давал 3 edit'а (stale + new); с фиксом ≤2
    check(len(edits) <= 2, f'no stale cancel-push ({len(edits)} edits)')
    check(panel._reset_gen >= 2, f'gen advanced ({panel._reset_gen})')

asyncio.run(cancel_stale_push())

print('== break: MuteKindSelect lag > 2.2 → soft nack, no modal ==')


async def mute_kind_lag():
    kinds = [('mute_chat', 'Чат', 'только чат')]
    sel = M.MuteKindSelect(cog=None, target_id='1', kinds=kinds, panel=None)
    sel._values = ['mute_chat']  # discord.py Select.values
    # monkeypatch property via values attr used in callback: self.values[0]
    type(sel).values = property(lambda self: getattr(self, '_values', []))
    ix = Ix(lag=2.5)
    await sel.callback(ix)
    check(ix.response.sent and 'занят' in (ix.response.sent[0].get('content') or ''),
          'MuteKindSelect busy-nack')
    check(not ix.response.modal, 'MuteKindSelect no modal on lag')

asyncio.run(mute_kind_lag())

print('== break: edit_original wrong msg must NOT claim success ==')


async def wrong_orig_push():
    class FailMsg:
        id = 42

        async def edit(self, **kw):
            raise RuntimeError('msg gone')

    edited = []

    async def edit_orig(**kw):
        edited.append(kw)
        # как kind-меню / чужой original — другой id
        return SimpleNamespace(id=777)

    panel = SimpleNamespace(
        _panel_message=FailMsg(),
        _panel_message_id=42,
        _root_edit=None,
        _mod_followup=None,
    )
    ix = SimpleNamespace(followup=None, edit_original_response=edit_orig)
    ok = await M._push_panel_view(panel, ix)
    check(ok is False, 'wrong-orig push → False (не silent-success)')
    check(panel._panel_message_id == 42, 'panel id не мигрировал на 777')
    check(bool(edited), 'edit_original всё же вызывали (fallback path)')

asyncio.run(wrong_orig_push())

print('== break: followup.edit wrong id → fail ==')


async def wrong_fu_push():
    class FailMsg:
        id = 10

        async def edit(self, **kw):
            raise RuntimeError('x')

    class FU:
        async def edit_message(self, mid, **kw):
            return SimpleNamespace(id=999)

    panel = SimpleNamespace(
        _panel_message=FailMsg(),
        _panel_message_id=10,
        _root_edit=None,
        _mod_followup=FU(),
    )
    ok = await M._push_panel_view(panel, None)
    check(ok is False, 'wrong followup msg → False')

asyncio.run(wrong_fu_push())

print('== break: schedule push 503 → in-task retry ==')


async def schedule_retry():
    attempts = {'n': 0}

    class Flaky:
        id = 55

        async def edit(self, **kw):
            attempts['n'] += 1
            if attempts['n'] == 1:
                raise RuntimeError('503')
            return self

    panel = SimpleNamespace(
        selected_uid='1',
        pending_action=None,
        _panel_message=Flaky(),
        _panel_message_id=55,
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
        _reset_push_retrying=False,
    )
    ix = SimpleNamespace(
        guild=panel._guild, message=panel._panel_message,
        followup=None, edit_original_response=None)
    M._schedule_panel_reset(ix, panel, delay=0.01)
    await asyncio.sleep(1.0)
    check(attempts['n'] >= 2, f'schedule retries after 503 ({attempts["n"]})')
    check(panel._reset_task is None or panel._reset_task.done(),
          'retry task finishes')

asyncio.run(schedule_retry())

print('== break: lag edges 2.2 / 3.0 (mocked measure) ==')


async def lag_edges():
    real = M._interaction_lag_sec

    class R:
        def __init__(self):
            self._done = False
            self.sent = []

        def is_done(self):
            return self._done

        async def defer(self, **kw):
            self._done = True

        async def send_message(self, **kw):
            self._done = True
            self.sent.append(kw)

    for lag, expect_ok in ((2.2, True), (2.2000001, False), (3.0, False)):
        M._interaction_lag_sec = lambda ix, L=lag: L
        ix = SimpleNamespace(response=R())
        ok = await M._ack_or_busy(ix, thinking=True, limit=2.2)
        check(ok is expect_ok, f'lag={lag} → ok={expect_ok} (got {ok})')
    M._interaction_lag_sec = real

asyncio.run(lag_edges())

print('== break: cancel without successor still pushes ==')


async def cancel_no_successor():
    pushes = []
    gate = asyncio.Event()

    class Msg:
        id = 71

        async def edit(self, **kw):
            pushes.append('edit')
            return self

    panel = SimpleNamespace(
        selected_uid='1',
        pending_action=None,
        _panel_message=Msg(),
        _panel_message_id=71,
        _root_edit=None,
        _mod_followup=None,
        _reset_task=None,
        _reset_gen=1,
        _guild=SimpleNamespace(id=1),
        _clear_kind_mode=lambda: None,
        _rebuild=lambda g: None,
        _allowed_cache_key=None,
        allowed=[],
        base_allowed=[],
    )
    ix = SimpleNamespace(
        guild=panel._guild, message=panel._panel_message,
        followup=None, edit_original_response=None)

    import asyncio as aio
    real_sleep = aio.sleep

    async def slow0(delay=0, result=None):
        if delay == 0:
            gate.set()
            await real_sleep(0.25)
            return result
        return await real_sleep(delay)

    aio.sleep = slow0
    try:
        task = aio.create_task(M._silent_reset_panel(ix, panel, gen=1))
        panel._reset_task = task
        await gate.wait()
        # как ModActionSelect lag-nack: cancel + нет нового reset
        panel._reset_gen = 2
        panel._reset_task = None
        task.cancel()
        try:
            await task
        except aio.CancelledError:
            pass
        check(pushes == ['edit'], f'cancel-no-successor pushes once ({pushes})')
    finally:
        aio.sleep = real_sleep

asyncio.run(cancel_no_successor())

print('== break: ModTargetSelect uses tracked bg-reset ==')

src = open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read()
mts = src[src.index('class ModTargetSelect'):src.index('class ModPanelView')]
check('_bg_reset_after_step' in mts, 'ModTargetSelect → tracked _bg_reset_after_step')
check('create_task(' not in mts or '_silent_reset_panel(interaction, view)' not in mts,
      'нет untracked create_task(_silent_reset)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
