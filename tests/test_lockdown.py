# -*- coding: utf-8 -*-
"""Тесты cogs/lockdown.py — снимок прав, лок/откат, сводка состояния.

Запуск: python3 tests/test_lockdown.py
"""
import ast
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_lock_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')

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


UTC = timezone.utc
from cogs import lockdown as ld  # noqa: E402
from db import GuildData  # noqa: E402

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)


class FakeOverwrite:
    """Мини-копия discord.PermissionOverwrite по нашим полям."""
    def __init__(self, send_messages=None, add_reactions=None,
                 create_public_threads=None, connect=None):
        self.send_messages = send_messages
        self.add_reactions = add_reactions
        self.create_public_threads = create_public_threads
        self.connect = connect


print('== 1. снимок и лок перезаписи ==')
ow = FakeOverwrite(send_messages=True, add_reactions=None)
snap = ld.snapshot_overwrite(ow)
check(snap == {'send_messages': True, 'add_reactions': None,
               'create_public_threads': None, 'connect': None},
      'снимок сохраняет True/None как есть')

locked = ld.apply_lock(FakeOverwrite(send_messages=True))
check(locked.send_messages is False and locked.add_reactions is False
      and locked.connect is False and locked.create_public_threads is False,
      'лок закрывает всё наблюдаемое')

ow2 = FakeOverwrite(send_messages=True, add_reactions=None)
ld.apply_lock(ow2)
ld.apply_restore(ow2, snap)
check(ow2.send_messages is True and ow2.add_reactions is None,
      'откат возвращает исходные значения точно (True -> True, None -> None)')

snap2 = ld.snapshot_overwrite(FakeOverwrite(send_messages=False))
ow3 = FakeOverwrite(send_messages=True)
ld.apply_restore(ow3, snap2)
check(ow3.send_messages is False, 'канал, закрытый ДО локдауна, остаётся закрытым после')

print('== 2. состояние и сводка ==')
st = ld.empty_state()
check(ld.state_locked_count(st) == 0 and ld.state_summary(st) == 'локдауна нет',
      'пустое состояние — понятная строка')
st['channels'] = {'100': snap, '101': snap, '102': snap}
st['since'] = (NOW - timedelta(hours=2)).isoformat()
st['reason'] = 'рейд с фишинговых ссылок'
summary = ld.state_summary(st, NOW)
check('3 канала закрыто' in summary and '2 часа назад' in summary and 'рейд' in summary,
      f'сводка читаемая: {summary!r}')
check(ld.is_locked(st, 101) and not ld.is_locked(st, 999), 'is_locked по id')

print('== 3. резолв целей (чистая логика через фейки) ==')


class FakeCh:
    def __init__(self, cid, name):
        self.id = cid
        self.name = name
        self.mention = f'#{name}'


class FakeGuild:
    def __init__(self):
        self.text_channels = [FakeCh(100, 'общий'), FakeCh(101, 'флуд'),
                              FakeCh(102, 'арт')]
        self._by_id = {c.id: c for c in self.text_channels}

    def get_channel(self, cid):
        return self._by_id.get(cid)


g = FakeGuild()
from cogs.lockdown import Lockdown  # noqa: E402
resolver = Lockdown._resolve_targets
inst = object.__new__(Lockdown)
check([c.id for c in resolver(inst, g, 'all', None)] == [100, 101, 102],
      "'all' — все текстовые")
check([c.id for c in resolver(inst, g, 'флуд', None)] == [101], 'по имени')
check([c.id for c in resolver(inst, g, '<#102>', None)] == [102], 'по упоминанию')
check([c.id for c in resolver(inst, g, '102', None)] == [102], 'по id')
here = g.text_channels[0]
check(resolver(inst, g, '', here) == [here], 'без аргумента — текущий канал')
check(resolver(inst, g, 'небывалый', here) == [], 'мусор — пусто')

print('== 4. хранилище ==')
db = GuildData('lockdown')
db.set(4242, 'state', st)
back = db.get(4242, 'state', ld.empty_state())
check(back['channels'] == st['channels'] and back['reason'].startswith('рейд'),
      'состояние переживает рестарт (SQLite roundtrip)')
check(db.get(777, 'state', ld.empty_state()) == ld.empty_state(),
      'чужой сервер -> пустое состояние')

print('== 5. линт ==')
src = open(os.path.join(ROOT, 'cogs', 'lockdown.py'), encoding='utf-8').read()
tree = ast.parse(src)
silent = [n.lineno for n in ast.walk(tree)
          if isinstance(n, ast.ExceptHandler)
          and len([b for b in n.body if not (isinstance(b, ast.Expr)
                   and isinstance(b.value, ast.Constant))]) == 1
          and isinstance([b for b in n.body if not (isinstance(b, ast.Expr)
                          and isinstance(b.value, ast.Constant))][0],
                         (ast.Pass, ast.Continue))]
check(not silent, f'ни одного молчаливого except {silent or "ок"}')
check('utcnow' not in src, 'utcnow() не используется')
check('WATCHED_PERMS' in src, 'наблюдаемые права — одним списком, не россыпью')

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
