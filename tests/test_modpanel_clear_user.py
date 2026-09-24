# -*- coding: utf-8 -*-
"""/modpanel clear: при выбранном участнике — его сообщения, не канал.

Жалоба 2026-09-24: выбрали юзера + «удаление сообщений» — должно снести
~10 его сообщений, а не просто последние N любых в канале.

Запуск: python3 tests/test_modpanel_clear_user.py
"""
import asyncio
import os
import sys
import tempfile
import types

_TMP = tempfile.mkdtemp(prefix='hakumo_clear_user_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ.setdefault('DB_PATH', os.path.join(_TMP, 'data', 'bot.db'))
os.environ.setdefault('PANEL_USER', 'a')
os.environ.setdefault('PANEL_PASSWORD', 'b')
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


print('== 1. Source: clear uses target user ==')
src = open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read()
check('_purge_user_messages' in src, 'есть _purge_user_messages')
check('target_uid' in src and '_purge_user_messages' in src,
      'clear ветка смотрит на target')
check('от {who}' in src or 'сообщ. от' in src,
      'подтверждение упоминает автора')

print('== 2. _purge_user_messages picks only that user ==')


class FakeAuthor:
    def __init__(self, uid):
        self.id = uid


class FakeMsg:
    def __init__(self, mid, uid):
        self.id = mid
        self.author = FakeAuthor(uid)
        self.deleted = False

    async def delete(self):
        self.deleted = True


class FakeChan:
    def __init__(self, msgs):
        self._msgs = list(msgs)
        self.bulk = None

    async def history(self, limit=100):
        for m in self._msgs[:limit]:
            yield m

    async def delete_messages(self, msgs):
        self.bulk = list(msgs)
        for m in msgs:
            m.deleted = True


# 3 чужих + 12 целевых вперемешку
msgs = []
uid = 42
other = 99
for i in range(20):
    msgs.append(FakeMsg(i, uid if i % 2 == 0 else other))
# история идёт от новых к старым — как Discord
chan = FakeChan(list(reversed(msgs)))

from cogs.moderation import Moderation  # noqa: E402

cog = Moderation.__new__(Moderation)
deleted = asyncio.get_event_loop().run_until_complete(
    cog._purge_user_messages(chan, uid, 10))
check(len(deleted) == 10, f'удалено ровно 10 своих (got {len(deleted)})')
check(all(m.author.id == uid for m in deleted), 'все удалённые — от цели')
check(chan.bulk is not None and len(chan.bulk) == 10, 'bulk delete вызван')

print('== 3. Grant verifies role after add ==')
gr = open(os.path.join(ROOT, 'services', 'staff_roles.py'), encoding='utf-8').read()
check('not_applied' in gr and 'fetch_member' in gr,
      'grant проверяет роль после add_roles')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
