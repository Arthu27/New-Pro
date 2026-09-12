# -*- coding: utf-8 -*-
"""Живой смоук: age-guard + selfie + helper /modpanel (чат-мут)."""
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


class FakeChannel:
    def __init__(self, cid, guild=None):
        self.id = cid
        self.guild = guild
        self.send = AsyncMock()


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

        msg = FakeMessage(ch, author, 'мне 16 лет')
        await cog.on_message(msg)
        check(msg.delete.await_count == 1, 'age-guard: удалил «мне 16 лет»')
        check(ch.send.await_count == 1, 'age-guard: предупреждение отправлено')

        msg18 = FakeMessage(ch, author, 'мне 18')
        await cog.on_message(msg18)
        check(msg18.delete.await_count == 0, 'age-guard: «мне 18» оставлен')

        staff = FakeMember(1002, roles=[FakeRole(1)], manage_messages=True)
        msgs = FakeMessage(ch, staff, 'мне 15')
        await cog.on_message(msgs)
        check(msgs.delete.await_count == 0, 'age-guard: staff иммунен')

        ch2 = FakeChannel(age_ids[1], guild)
        msg2 = FakeMessage(ch2, author, 'возраст 14')
        await cog.on_message(msg2)
        check(msg2.delete.await_count == 1, 'age-guard: второй канал чистит')

        other = FakeChannel(999, guild)
        msg_o = FakeMessage(other, author, 'мне 12')
        await cog.on_message(msg_o)
        check(msg_o.delete.await_count == 0, 'age-guard: чужой канал не трогает')

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

    check(cg.claimed_underage('мне семнадцать') == 17, 'слова: семнадцать')
    check(cg.claimed_underage('2 года на сервере') is None, 'tenure false-positive нет')


def run_helper_modpanel():
    from services.helper_acl_seed import (
        HELPER_ROLE_ID, apply_helper_acl_seed, HELPER_ACTIONS,
    )
    from services import permission_acl as pacl
    from cogs.moderation import (
        actions_for_member, mute_kinds_for, unmute_kinds_for, MODPANEL_ACTIONS,
    )

    gid = 1312000000000000001
    os.environ['MAIN_GUILD_ID'] = str(gid)

    mod_role = '803553848396349510'
    pacl.save_action_acl(gid, {
        'ban': [mod_role],
        'mute': [mod_role],
        'vmute': [mod_role],
        'purge': [mod_role],
        'warn': [mod_role],
        'timeout': [mod_role],
    })
    pacl.set_rule(gid, 'modpanel', [mod_role])

    for p in Path('data').glob('.helper_acl*'):
        p.unlink(missing_ok=True)

    rep = apply_helper_acl_seed(force=True, guild_id=gid)
    check(rep.get('applied') is True, f'helper seed applied: {rep}')
    check(HELPER_ACTIONS == ('mute', 'purge'), f'HELPER_ACTIONS={HELPER_ACTIONS}')

    acl = pacl.load_action_acl(gid)
    h = str(HELPER_ROLE_ID)
    check(h in [str(x) for x in acl.get('mute', [])], 'ACL mute ← helper (чат-мут)')
    check(h in [str(x) for x in acl.get('purge', [])], 'ACL purge ← helper')
    check(h not in [str(x) for x in acl.get('ban', [])], 'ACL ban без helper')
    check(h not in [str(x) for x in acl.get('vmute', [])], 'ACL vmute без helper')
    check(h not in [str(x) for x in acl.get('warn', [])], 'ACL warn без helper')

    class Guild:
        id = gid

    helper = FakeMember(42, roles=[FakeRole(gid), FakeRole(HELPER_ROLE_ID)],
                        manage_messages=True)
    mod = FakeMember(43, roles=[FakeRole(gid), FakeRole(int(mod_role))],
                     manage_messages=True, moderate_members=True)

    h_acts = [a[0] for a in actions_for_member(Guild(), helper)]
    m_acts = [a[0] for a in actions_for_member(Guild(), mod)]

    check(h_acts == ['mute', 'unmute', 'clear'],
          f'helper меню ТОЛЬКО mute/unmute/clear: {h_acts}')
    check('ban' not in h_acts and 'warn' not in h_acts,
          f'helper без ban/warn: {h_acts}')
    check('mute' in m_acts and 'ban' in m_acts,
          f'мод видит mute+ban: {m_acts}')

    h_mute = [k[0] for k in mute_kinds_for(gid, helper)]
    h_unmute = [k[0] for k in unmute_kinds_for(gid, helper)]
    m_mute = [k[0] for k in mute_kinds_for(gid, mod)]

    check(h_mute == ['mute_chat'], f'helper mute kinds = chat only: {h_mute}')
    check(h_unmute == ['unmute_chat'], f'helper unmute kinds = chat only: {h_unmute}')
    check('mute_chat' in m_mute and 'vmute' in m_mute,
          f'мод видит chat+voice: {m_mute}')

    check(pacl.check_action(gid, helper, 'mute') is True, 'check_action mute OK (чат)')
    check(pacl.check_action(gid, helper, 'purge') is True, 'check_action purge OK')
    check(pacl.check_action(gid, helper, 'ban') is False, 'check_action ban DENY')
    check(pacl.check_action(gid, helper, 'vmute') is False, 'check_action vmute DENY')

    labels = {a[0]: a[1] for a in MODPANEL_ACTIONS}
    check(labels.get('mute') == 'Мут', 'пункт меню «Мут»')
    check(mute_kinds_for(gid, helper)[0][1] == 'Чат',
          'второй шаг у хелпера — «Чат»')


def main():
    print('== LIVE: age-guard + selfie ==')
    asyncio.run(run_age_and_selfie())
    print('\n== LIVE: helper /modpanel (чат-мут) ==')
    run_helper_modpanel()
    print(f'\n=== {PASS} passed, {FAIL} failed ===')
    out = Path('/opt/cursor/artifacts/live-smoke-channel-guards.txt')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(LOG) + f'\n\n=== {PASS} passed, {FAIL} failed ===\n',
                   encoding='utf-8')
    print(f'artifact: {out}')
    return 1 if FAIL else 0


if __name__ == '__main__':
    raise SystemExit(main())
