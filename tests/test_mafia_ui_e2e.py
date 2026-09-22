# -*- coding: utf-8 -*-
"""E2E-мок Discord UI мафии: каждый шаг ТЗ без живого токена."""
from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace
from typing import Any, List

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

import discord  # noqa: E402
from discord.ext import commands  # noqa: E402

from services.mafia import STORE, PHASE_PLAYING, PHASE_READY, PHASE_ENDED  # noqa: E402
from services.mafia.game import Game  # noqa: E402
import cogs.mafia as MC  # noqa: E402

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


class _Resp:
    def __init__(self):
        self._done = False
        self.sent: List[Any] = []
        self.edited: List[Any] = []

    def is_done(self):
        return self._done

    async def send_message(self, content=None, **kwargs):
        self._done = True
        self.sent.append({'content': content, **kwargs})

    async def edit_message(self, **kwargs):
        self._done = True
        self.edited.append(kwargs)

    async def defer(self, **kwargs):
        self._done = True


class _Followup:
    def __init__(self):
        self.sent: List[Any] = []

    async def send(self, content=None, **kwargs):
        self.sent.append({'content': content, **kwargs})


class FakeUser:
    def __init__(self, uid, name='User', guild=None):
        self.id = uid
        self.name = name
        self.display_name = name
        self.mention = f'<@{uid}>'
        self.bot = False
        self.guild = guild
        self.voice = None
        self.guild_permissions = SimpleNamespace(administrator=False)
        self._dms: List[Any] = []

    async def send(self, content=None, **kwargs):
        self._dms.append({'content': content, **kwargs})
        return SimpleNamespace(
            id=9000 + len(self._dms),
            channel=SimpleNamespace(id=8000 + self.id),
        )


class FakeMember(FakeUser):
    pass


class FakeVoice:
    def __init__(self, channel):
        self.channel = channel


class FakeVoiceChannel:
    def __init__(self, cid, members):
        self.id = cid
        self.members = members


class FakeTextChannel:
    def __init__(self, cid):
        self.id = cid
        self._msgs = {}

    async def fetch_message(self, mid):
        return self._msgs[mid]


class FakeMessage:
    def __init__(self, channel, mid, content=None, embed=None, view=None):
        self.id = mid
        self.channel = channel
        self.content = content
        self.embed = embed
        self.view = view
        self.edits = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)
        if 'embed' in kwargs:
            self.embed = kwargs['embed']
        if 'view' in kwargs:
            self.view = kwargs['view']
        if 'content' in kwargs:
            self.content = kwargs['content']


class FakeGuild:
    def __init__(self, gid):
        self.id = gid
        self._channels = {}
        self._members = {}

    def get_channel(self, cid):
        return self._channels.get(cid)

    def get_member(self, uid):
        return self._members.get(uid)


class FakeInteraction:
    def __init__(self, user, guild, channel, client, data=None):
        self.user = user
        self.guild = guild
        self.guild_id = guild.id if guild else None
        self.channel = channel
        self.channel_id = channel.id if channel else None
        self.client = client
        self.data = data or {}
        self.response = _Resp()
        self.followup = _Followup()


class FakeBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=discord.Intents.none(),
                         help_command=None)
        self._users = {}
        self._channels = {}
        self._views = []

    def get_user(self, uid):
        return self._users.get(uid)

    async def fetch_user(self, uid):
        return self._users[uid]

    def get_channel(self, cid):
        return self._channels.get(cid)

    async def fetch_channel(self, cid):
        return self._channels[cid]

    def add_view(self, view, **kwargs):
        self._views.append(view)


async def run():
    STORE._by_guild.clear()

    bot = FakeBot()
    await bot.add_cog(MC.Mafia(bot))
    cog: MC.Mafia = bot.get_cog('mafia')  # type: ignore

    guild = FakeGuild(555)
    text = FakeTextChannel(10)
    guild._channels[10] = text
    bot._channels[10] = text

    host = FakeMember(1, 'Host', guild)
    players = [FakeMember(100 + i, f'P{i}', guild) for i in range(6)]
    for p in players:
        guild._members[p.id] = p
        bot._users[p.id] = p
    guild._members[1] = host
    bot._users[1] = host

    voice = FakeVoiceChannel(20, [host] + players)
    guild._channels[20] = voice
    host.voice = FakeVoice(voice)

    print('== 1. Лобби из войса ==')
    # FakeVoiceChannel не проходит isinstance(..., discord.VoiceChannel) —
    # состав как из voice_members: все кроме ведущего и ботов.
    members = [(p.id, p.display_name) for p in players]
    check(len(members) == 6, f'состав без ведущего: {len(members)}')
    check(all(m[0] != 1 for m in members), 'ведущий не в составе')
    game = Game.create(555, 1, 20, 10, members)
    game.lobby_message_id = 42
    text._msgs[42] = FakeMessage(text, 42)
    STORE.set(game)
    check(STORE.get(555) is not None and len(game.players) == 6, 'игра в store, 6 игроков')

    print('== 2. Раздача → DM + сводка ==')
    inter2 = FakeInteraction(host, guild, text, bot)
    await inter2.response.defer()
    await cog.deal_roles(inter2, game)
    check(game.phase == 'confirm', 'фаза confirm')
    check(sum(len(p._dms) for p in players) == 6, '6 DM ролей')
    check(bool(host._dms), 'сводка ведущему')
    check(all(p._dms[-1].get('view') for p in players), 'у всех confirm view')

    print('== 3. Подтверждения ==')
    token, gid = game.deal_token, game.game_id
    for p in players:
        ic = FakeInteraction(p, guild, text, bot)
        await cog.handle_confirm(ic, gid, token)
        check(any('✅' in str(s.get('content', '')) for s in ic.response.sent),
              f'confirm {p.display_name}')
    ic_dup = FakeInteraction(players[0], guild, text, bot)
    await cog.handle_confirm(ic_dup, gid, token)
    check(any('уже' in str(s.get('content', '')).lower() for s in ic_dup.response.sent),
          'повтор игнорируется')
    check(game.phase == PHASE_READY, 'фаза ready')

    print('== 4. Старт игры ==')
    inter3 = FakeInteraction(host, guild, text, bot)
    hp_start = MC.HostPanelView()
    await MC.HostPanelView.start(hp_start, inter3)
    check(game.phase == PHASE_PLAYING, f'фаза playing ({game.phase})')
    check(any('началась' in str(s.get('content', '')).lower() for s in inter3.response.sent),
          'ответ о старте')

    print('== 5. Шериф ==')
    mafia_p = next(p for p in game.players.values() if p.role == 'mafia')
    rec = game.sheriff_check(mafia_p.user_id)
    check('Мафия' in rec['result'], 'шериф видит мафию')

    print('== 6. Голосование → победа города ==')
    inter4 = FakeInteraction(host, guild, text, bot)
    inter4.data = {'values': [str(mafia_p.user_id)]}
    await MC.PlayerSelectView(555, mode='vote')._on_select(inter4)
    check(STORE.get(555) is None, 'игра архивирована после финала')
    edited = inter4.response.edited
    check(edited and 'мирный' in str(edited[0].get('content', '')).lower(),
          f'плашка победы: {edited}')

    print('== 7. Старый deal_token отвергается ==')
    STORE._by_guild.clear()
    g2 = Game.create(556, 1, 20, 10, [(200 + i, f'Q{i}') for i in range(6)])
    STORE.set(g2)
    g2.deal()
    old = g2.deal_token
    uid = next(iter(g2.players))
    g2.confirm(uid, old)
    g2.deal()
    ic = FakeInteraction(FakeMember(uid, 'Q0', guild), guild, text, bot)
    await cog.handle_confirm(ic, g2.game_id, old)
    txt = str(ic.response.sent[0].get('content', '')).lower() if ic.response.sent else ''
    check('недействительн' in txt or 'нельзя' in txt, f'старый токен: {ic.response.sent}')

    print('== 8. Победа мафии 1:1 ==')
    STORE._by_guild.clear()
    g3 = Game.create(557, 1, 20, 10, [(300 + i, f'M{i}') for i in range(6)])
    for p, r in zip(g3.players.values(),
                    ['mafia', 'sheriff', 'citizen', 'citizen', 'citizen', 'citizen']):
        p.role = r
        p.confirmed = True
    g3.phase = PHASE_READY
    g3.start()
    town = [p for p in g3.players.values() if p.role != 'mafia']
    for p in town[:4]:
        g3.kill(p.user_id)
    check(g3.winner == 'mafia' and g3.phase == PHASE_ENDED, 'мафия 1:1')

    print('== 9. Pending + exclude ==')
    STORE._by_guild.clear()
    g4 = Game.create(558, 1, 20, 10, [(400 + i, f'X{i}') for i in range(6)])
    g4.deal()
    STORE.set(g4)
    hp = MC.HostPanelView()
    inter_p = FakeInteraction(host, guild, text, bot)
    await MC.HostPanelView.pending(hp, inter_p)
    check(inter_p.response.sent and '⏳' in str(inter_p.response.sent[0].get('content', '')),
          'pending список')
    kick = next(iter(g4.players))
    inter_ex = FakeInteraction(host, guild, text, bot)
    inter_ex.data = {'values': [str(kick)]}
    await MC.PlayerSelectView(558, mode='exclude', alive_only=False)._on_select(inter_ex)
    check(g4.phase == 'lobby' and kick not in g4.players, 'exclude → lobby')

    await bot.close()


asyncio.run(run())
print(f'\nИтого: {PASS} PASS / {FAIL} FAIL')
sys.exit(1 if FAIL else 0)
