# -*- coding: utf-8 -*-
"""Живой смоук: age-guard (<18 guild-wide) + selfie auto-role."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

# Path already imported above via pathlib

_TMP = tempfile.mkdtemp(prefix='hakumo_live_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASS = FAIL = 0
LOG = []


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        line = f'PASS  {msg}'
    else:
        FAIL += 1
        line = f'FAIL  {msg}'
    print(line)
    LOG.append(line)


class FakePerms:
    def __init__(self, **kw):
        self.administrator = kw.get('administrator', False)
        self.manage_messages = kw.get('manage_messages', False)
        self.moderate_members = kw.get('moderate_members', False)
        self.manage_roles = kw.get('manage_roles', False)


class FakeRole:
    def __init__(self, rid, name='role'):
        self.id = rid
        self.name = name

    def __eq__(self, other):
        return getattr(other, 'id', None) == self.id

    def __hash__(self):
        return hash(self.id)


class FakeMember:
    def __init__(self, uid, roles=None, **perms):
        self.id = uid
        self.bot = False
        self.roles = list(roles or [])
        self.guild_permissions = FakePerms(**perms)
        self.mention = f'<@{uid}>'
        self.add_roles = AsyncMock()
        self.send = AsyncMock()  # ЛС для age-guard


class FakeChannel:
    def __init__(self, cid, guild=None):
        self.id = cid
        self.guild = guild
        self.send = AsyncMock()
        self.mention = f'<#{cid}>'


class FakeGuild:
    def __init__(self, gid):
        self.id = gid
        self._roles = {}

    def get_role(self, rid):
        return self._roles.get(rid)

    def add_role(self, role):
        self._roles[role.id] = role


class FakeMessage:
    def __init__(self, channel, author, content='', attachments=None, embeds=None):
        self.id = 555
        self.guild = channel.guild
        self.channel = channel
        self.author = author
        self.content = content
        self.attachments = attachments or []
        self.embeds = embeds or []
        self.delete = AsyncMock()


async def run_age_and_selfie():
    import cogs.channel_guards as cg

    age_ids = list(cg.AGE_GUARD_CHANNELS)
    guild = FakeGuild(42)
    selfie_role = FakeRole(cg.SELFIE_ROLE_ID, 'selfie')
    guild.add_role(selfie_role)
    cog = cg.ChannelGuards(MagicMock())

    with patch('cogs.channel_guards.discord.Member', FakeMember):
        ch = FakeChannel(age_ids[0], guild)
        author = FakeMember(1001, roles=[FakeRole(1, '@everyone')])

        author.send = AsyncMock()
        msg = FakeMessage(ch, author, 'мне 16_')
        await cog.on_message(msg)
        check(msg.delete.await_count == 1, 'age-guard: удалил «мне 16_»')
        check(ch.send.await_count == 0, 'age-guard: в канал НЕ пишет')
        check(author.send.await_count == 1, 'age-guard: предупреждение в ЛС')

        msg14 = FakeMessage(ch, author, 'мне 18')
        await cog.on_message(msg14)
        check(msg14.delete.await_count == 0, 'age-guard: «мне 18» оставлен')

        msg13 = FakeMessage(ch, author, '17+')
        await cog.on_message(msg13)
        check(msg13.delete.await_count == 1, 'age-guard: удалил голое «17+»')
        msg16 = FakeMessage(ch, author, 'мне 16')
        await cog.on_message(msg16)
        check(msg16.delete.await_count == 1, 'age-guard: удалил «мне 16»')

        msg18 = FakeMessage(ch, author, 'мне 18')
        await cog.on_message(msg18)
        check(msg18.delete.await_count == 0, 'age-guard: «мне 18» оставлен')

        staff = FakeMember(1002, roles=[FakeRole(1)], manage_messages=True)
        msgs = FakeMessage(ch, staff, 'мне 11')
        await cog.on_message(msgs)
        check(msgs.delete.await_count == 0, 'age-guard: staff иммунен')

        ch2 = FakeChannel(age_ids[1], guild)
        msg2 = FakeMessage(ch2, author, 'возраст 10')
        await cog.on_message(msg2)
        check(msg2.delete.await_count == 1, 'age-guard: второй канал чистит')

        other = FakeChannel(999, guild)
        msg_o = FakeMessage(other, author, 'мне 12')
        await cog.on_message(msg_o)
        check(msg_o.delete.await_count == 1,
              'age-guard: общий канал тоже чистит «мне 12» (guild-wide)')
        check(author.send.await_count >= 1, 'age-guard: ЛС после guild-wide')

        # в общем чате голые цифры НЕ трогаем (только знакомства)
        msg_bare = FakeMessage(other, author, 'просто 17+ в чате')
        await cog.on_message(msg_bare)
        check(msg_bare.delete.await_count == 0,
              'age-guard: голое 17+ вне знакомств не трогает')

        # правка сообщения с возрастом
        edited = FakeMessage(other, author, 'мне 14')
        await cog.on_message_edit(
            FakeMessage(other, author, 'привет'), edited)
        check(edited.delete.await_count == 1,
              'age-guard: правка «мне 14» удалена')

        # solicitation везде
        msg_sol = FakeMessage(other, author, 'ищу девушку меньше 18')
        await cog.on_message(msg_sol)
        check(msg_sol.delete.await_count == 1,
              'age-guard: «меньше 18» в общем канале удалено')

        # живой кейс: «Ищу девушку мне 16» (Morg) — должно удалиться везде
        msg_morg = FakeMessage(other, author, 'Ищу девушку мне 16')
        await cog.on_message(msg_morg)
        check(msg_morg.delete.await_count == 1,
              'age-guard: «Ищу девушку мне 16» удалено (guild-wide)')
        check(other.send.await_count == 0,
              'age-guard: Morg-кейс — в канал не пишет')

        sch = FakeChannel(cg.SELFIE_CHANNEL_ID, guild)
        poster = FakeMember(2001, roles=[FakeRole(1)])
        att = SimpleNamespace(content_type='image/png', filename='me.png')
        await cog.on_message(FakeMessage(sch, poster, 'селка', attachments=[att]))
        check(poster.add_roles.await_count == 1, 'selfie: add_roles вызван')
        check(poster.add_roles.await_args.args[0].id == cg.SELFIE_ROLE_ID,
              f'selfie: роль {cg.SELFIE_ROLE_ID}')

        poster2 = FakeMember(2002, roles=[FakeRole(1)])
        await cog.on_message(FakeMessage(sch, poster2, 'просто текст'))
        check(poster2.add_roles.await_count == 0, 'selfie: без медиа — skip')

        poster3 = FakeMember(2003, roles=[FakeRole(1), selfie_role])
        await cog.on_message(FakeMessage(sch, poster3, 'ещё', attachments=[att]))
        check(poster3.add_roles.await_count == 0, 'selfie: роль уже есть — skip')

    check(cg.claimed_underage('мне двенадцать') == 12, 'слова: двенадцать')
    check(cg.claimed_underage('мне семнадцать') == 17, 'слова: семнадцать → 17')
    check(cg.claimed_underage('2 года на сервере') is None, 'tenure false-positive нет')
    check(cg.claimed_underage('Ищу девушку мне 16') == 16, 'Morg phrase → 16')


def main():
    print('== LIVE: age-guard + selfie ==')
    asyncio.run(run_age_and_selfie())
    print(f'\n=== {PASS} passed, {FAIL} failed ===')
    out = Path('/opt/cursor/artifacts/live-smoke-channel-guards.txt')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(LOG) + f'\n\n=== {PASS} passed, {FAIL} failed ===\n',
                   encoding='utf-8')
    print(f'artifact: {out}')
    return 1 if FAIL else 0


if __name__ == '__main__':
    raise SystemExit(main())
