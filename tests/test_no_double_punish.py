# -*- coding: utf-8 -*-
"""Нельзя наказывать два раза подряд одной и той же мерой.

Бан / чат-мут / войс-мут / полный мут: если роль уже на участнике —
_execute_mod_action отказывается, без нового дела и без списания лимита.
Пустой unmute/unban — тоже без дела.

Запуск: python3 tests/test_no_double_punish.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

os.environ['DB_PATH'] = os.path.join(tempfile.mkdtemp(prefix='ndp_db_'), 'bot.db')
os.chdir(tempfile.mkdtemp(prefix='ndp_ws_'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.makedirs('data', exist_ok=True)

from cogs import moderation as M  # noqa: E402

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


class Role:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name

    def __eq__(self, other):
        return getattr(other, 'id', None) == self.id

    def __hash__(self):
        return hash(self.id)


class Member:
    def __init__(self, uid, roles=None):
        self.id = uid
        self.roles = list(roles or [])
        self.display_name = f'u{uid}'
        self.mention = f'<@{uid}>'
        self.bot = False
        self.voice = None
        self.timed_out_until = None
        self.add_roles = AsyncMock()
        self.remove_roles = AsyncMock()
        self.edit = AsyncMock()
        self.timeout = AsyncMock()
        self.send = AsyncMock()
        self.top_role = Role(1, 'member')
        self.guild_permissions = NS(
            administrator=False, manage_messages=False,
            moderate_members=False, ban_members=False)

    def __str__(self):
        return self.display_name


class Interaction:
    def __init__(self, guild, actor):
        self.guild = guild
        self.user = actor
        self.guild_id = guild.id
        self.response = NS(
            is_done=lambda: True,
            send_message=AsyncMock(),
            defer=AsyncMock(),
        )
        self.followup = NS(send=AsyncMock())
        self.channel = NS(id=1, mention='#mod')
        self.client = NS(user=NS(id=999))


async def _run(action, target_roles, punish_map):
    guild = NS(id=42, owner_id=700000000000000007, me=NS(
        top_role=Role(9999, 'bot'),
        guild_permissions=NS(
            manage_roles=True, ban_members=True,
            moderate_members=True, manage_messages=True)))
    actor = Member(700000000000000007, roles=[Role(50, 'mod')])
    actor.guild_permissions = NS(
        administrator=True, manage_messages=True,
        moderate_members=True, ban_members=True)
    target = Member(100000000000000100, roles=list(target_roles))
    target.top_role = Role(2, 'member')
    it = Interaction(guild, actor)

    bot = MagicMock()
    bot.get_cog = MagicMock(return_value=None)
    bot.user = NS(id=999)
    cog = M.Moderation(bot)
    cog._punish_role = lambda g, kind: punish_map.get(kind)
    cog.preflight_reason = AsyncMock(return_value=None)
    cog.save_case = MagicMock(return_value='case1')
    cog._maybe_watchlist_after_mute = AsyncMock()
    cog._remember_temp = MagicMock()
    cog._clear_chat_mute = AsyncMock()
    cog._fix_vmute_role_connect = AsyncMock()
    cog._drop_roles = AsyncMock()
    guild.owner_id = actor.id
    guild.members = [target, actor]
    guild.get_member = lambda uid: target if int(uid) == target.id else (
        actor if int(uid) == actor.id else None)

    from unittest.mock import patch
    with patch('cogs.proof_cog.require_proof', AsyncMock(return_value=True)):
        with patch('services.mute_state.clear_all_mutes', AsyncMock()):
            with patch('services.mute_state.clear_chat_mute', AsyncMock()):
                await cog._execute_mod_action(
                    it, action, str(target.id), amount='30m',
                    reason='test', proof_link='https://cdn.example/x.png')
    return target, it, cog


def main():
    ban = Role(10, 'Бан')
    mute = Role(11, 'Мут')
    vmute = Role(12, 'ВойсМут')
    roles = {'ban': ban, 'mute': mute, 'vmute': vmute}

    print('== ban ==')
    t, _, cog = asyncio.run(_run('ban', [ban], roles))
    check(t.add_roles.await_count == 0, 'повторный ban: add_roles не вызван')
    check(cog.save_case.call_count == 0, 'повторный ban: дело не пишется')
    t2, _, cog2 = asyncio.run(_run('ban', [], roles))
    check(t2.add_roles.await_count == 1, 'первый ban: add_roles вызван')
    check(cog2.save_case.call_count == 1, 'первый ban: дело пишется')

    print('== mute_chat ==')
    t3, _, cog3 = asyncio.run(_run('mute_chat', [mute], roles))
    check(t3.add_roles.await_count == 0, 'повторный mute_chat: нет add_roles')
    check(cog3.save_case.call_count == 0, 'повторный mute_chat: дело не пишется')
    t4, _, _ = asyncio.run(_run('mute_chat', [], roles))
    check(t4.add_roles.await_count == 1, 'первый mute_chat: add_roles')

    print('== vmute ==')
    t5, _, cog5 = asyncio.run(_run('vmute', [vmute], roles))
    check(t5.add_roles.await_count == 0, 'повторный vmute: нет add_roles')
    check(cog5.save_case.call_count == 0, 'повторный vmute: дело не пишется')
    t6, _, _ = asyncio.run(_run('vmute', [], roles))
    check(t6.add_roles.await_count == 1, 'первый vmute: add_roles')

    print('== timeout (чат+войс) ==')
    t7, _, cog7 = asyncio.run(_run('timeout', [mute, vmute], roles))
    check(t7.add_roles.await_count == 0, 'повторный timeout: нет add_roles')
    check(cog7.save_case.call_count == 0, 'повторный timeout: дело не пишется')
    t8, _, _ = asyncio.run(_run('timeout', [], roles))
    check(t8.add_roles.await_count >= 1, 'первый timeout: add_roles')

    print('== empty unmute ==')
    _, _, cog9 = asyncio.run(_run('untimeout', [], roles))
    check(cog9.save_case.call_count == 0, 'пустой untimeout: дело не пишется')
    _, _, cog10 = asyncio.run(_run('vunmute', [], roles))
    check(cog10.save_case.call_count == 0, 'пустой vunmute: дело не пишется')
    _, _, cog11 = asyncio.run(_run('unmute_chat', [], roles))
    check(cog11.save_case.call_count == 0, 'пустой unmute_chat: дело не пишется')

    print('== source guards ==')
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, 'cogs', 'moderation.py'), encoding='utf-8').read()
    check('уже под баном' in src, 'текст отказа бана')
    check('уже под чат-мутом' in src, 'текст отказа чат-мута')
    check('уже под войс-мутом' in src, 'текст отказа войс-мута')
    check('уже под мутом (чат + войс)' in src, 'текст отказа полного мута')
    check('actor=interaction.user' in src,
          'ПКМ: иерархия от реального Member')
    check('actor =interaction .user' in src,
          '/modpanel warn/unwarn: реальный Member')
    check('Ничего не изменилось — нет роли бана' in src,
          'пустой разбан без дела/лимита')
    check('снимать нечего' in src,
          'пустой unmute без дела/лимита')
    check('PR .clear (guild .id ,user .id ,role .id )' in src,
          'снятие роли чистит только её таймер')

    warn_src = open(os.path.join(root, 'cogs', 'warnings.py'), encoding='utf-8').read()
    check('уже под ролью' in warn_src,
          'авто-наказание по варнам не дублирует роль')
    check('уже в Discord-бане' in warn_src,
          'авто-бан не дублирует Discord-бан')

    print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
    return 1 if FAIL else 0


if __name__ == '__main__':
    raise SystemExit(main())
