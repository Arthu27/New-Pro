# -*- coding: utf-8 -*-
"""После варна/мута/бана — удалить последние 30 сообщений ИМЕННО нарушителя.

Запуск: python3 tests/test_modpanel_purge_after_punish.py
"""
import asyncio
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_purge_punish_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ.setdefault('DB_PATH', os.path.join(_TMP, 'data', 'bot.db'))
os.environ.setdefault('MAIN_GUILD_ID', '1')

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


src = open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read()

print('== source hooks ==')
check('PURGE_AFTER_PUNISH = 30' in src or 'PURGE_AFTER_PUNISH=30' in src.replace(' ', ''),
      'PURGE_AFTER_PUNISH = 30')
check('_purge_user_recent' in src, 'multi-channel recent purge')
check('_schedule_purge_after_punish' in src, 'schedule helper')
check("name='modpanel-purge-after-punish'" in src, 'background task name')
check('_schedule_purge_after_punish(interaction, user' in src, 'wired into punish paths')
# warn / mute / ban — not unmute
warn_block = src[src.index('if action =="warn"'):src.index("if action =='unwarn'")]
check('_schedule_purge_after_punish' in warn_block, 'warn schedules purge')
mc = src[src.index('elif action == "mute_chat"'):src.index('elif action =="vmute"')]
check('_schedule_purge_after_punish' in mc, 'mute_chat schedules purge')
to = src[src.index('elif action == "timeout"'):src.index('elif action == "mute_chat"')]
check('_schedule_purge_after_punish' in to, 'timeout schedules purge')
check("if action == 'ban'" in src and '_schedule_purge_after_punish' in src[
    src.index("if action == 'ban'"):src.index("if action == 'ban'") + 800],
      'ban schedules purge')

print('== runtime: only that user, up to 30 ==')


class FakeAuthor:
    def __init__(self, uid):
        self.id = uid


class FakeMsg:
    def __init__(self, mid, uid):
        self.id = mid
        self.author = FakeAuthor(uid)


class FakeChan:
    def __init__(self, cid, msgs):
        self.id = cid
        self.name = f'ch{cid}'
        self._msgs = list(msgs)
        self.bulk = None

    async def history(self, limit=100):
        for m in self._msgs[:limit]:
            yield m

    async def delete_messages(self, msgs):
        self.bulk = list(msgs)


class FakeGuild:
    def __init__(self, channels):
        self.text_channels = channels


from cogs.moderation import Moderation  # noqa: E402

uid, other = 42, 99
# канал A: 20 своих + чужие; канал B: ещё 20 своих
msgs_a = [FakeMsg(i, uid if i % 2 == 0 else other) for i in range(40)]
msgs_b = [FakeMsg(1000 + i, uid) for i in range(20)]
ch_a = FakeChan(1, list(reversed(msgs_a)))
ch_b = FakeChan(2, list(reversed(msgs_b)))
guild = FakeGuild([ch_a, ch_b])

cog = Moderation.__new__(Moderation)
deleted = asyncio.get_event_loop().run_until_complete(
    cog._purge_user_recent(guild, ch_a, uid, 30))
check(len(deleted) == 30, f'удалено ровно 30 (got {len(deleted)})')
check(all(m.author.id == uid for m in deleted), 'все — от нарушителя')
# часть из prefer-канала, остаток из второго
from_a = sum(1 for m in deleted if m.id < 1000)
from_b = sum(1 for m in deleted if m.id >= 1000)
check(from_a > 0 and from_b > 0, f'набрано из нескольких каналов a={from_a} b={from_b}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
