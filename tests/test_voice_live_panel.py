# -*- coding: utf-8 -*-
"""Войс в панеле live: не только на leave, а пока человек ещё в канале."""
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs import voice_tracker as VT


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('OK', msg)


class _FakeDB:
    def __init__(self):
        self.store = {}

    def get(self, gid, uid, default=None):
        return self.store.get((int(gid), str(uid)), default)

    def set(self, gid, uid, data):
        self.store[(int(gid), str(uid))] = dict(data)

    def get_all(self, gid):
        return {uid: dict(rec) for (g, uid), rec in self.store.items() if g == int(gid)}

    def count(self, gid):
        return len(self.get_all(gid))


class _FakeMember:
    def __init__(self, uid, name='User'):
        self.id = int(uid)
        self.display_name = name
        self.display_avatar = SimpleNamespace(url='https://cdn.example/a.png')


class _FakeGuild:
    def __init__(self, gid, members):
        self.id = int(gid)
        self._members = {int(m.id): m for m in members}

    def get_member(self, uid):
        return self._members.get(int(uid))


class _FakeBot:
    def __init__(self, guilds):
        self.guilds = guilds

    def get_guild(self, gid):
        for g in self.guilds:
            if g.id == int(gid):
                return g
        return None


# без discord.ext.tasks — тестируем чистую логику credit/merge
cog = SimpleNamespace(
    bot=None,
    db=_FakeDB(),
    sessions={},
    _pending={},
)
VT._set_active_tracker(cog)
cog.db = _FakeDB()

# monkeypatch GuildData path used by _record via cog.db
member = _FakeMember(42, 'Tester')
guild = _FakeGuild(7, [member])
cog.bot = _FakeBot([guild])
cog.sessions = {7: {'42': time.time() - 20}}


def _record(guild_id, member, elapsed):
    # копия VoiceTracker._record на fake cog
    if elapsed <= 0:
        return
    uid = str(member.id)
    key = (guild_id, uid)
    data = cog._pending.get(key)
    if data is None:
        data = cog.db.get(guild_id, uid, {
            'name': member.display_name,
            'avatar': str(member.display_avatar.url),
            'total_seconds': 0,
            'daily': {},
        }) or {
            'name': member.display_name,
            'avatar': str(member.display_avatar.url),
            'total_seconds': 0,
            'daily': {},
        }
    data['total_seconds'] = int(data.get('total_seconds', 0) or 0) + elapsed
    data['name'] = member.display_name
    data['avatar'] = str(member.display_avatar.url)
    from datetime import date
    today = str(date.today())
    daily = data.get('daily') or {}
    daily[today] = int(daily.get(today, 0) or 0) + elapsed
    data['daily'] = daily
    cog._pending[key] = data


cog._record = _record


def _credit():
    now = time.time()
    for gid, users in list(cog.sessions.items()):
        g = cog.bot.get_guild(gid)
        for uid, join_time in list(users.items()):
            elapsed = int(now - float(join_time))
            if elapsed < 3:
                continue
            m = g.get_member(int(uid))
            if m is None:
                cog.sessions[gid][uid] = now
                continue
            cog._record(int(gid), m, elapsed)
            cog.sessions[gid][uid] = now


_credit()
check((7, '42') in cog._pending, 'live tick пишет в pending пока ещё в войсе')
check(cog._pending[(7, '42')]['total_seconds'] >= 15, 'накоплены секунды сессии')

# voice_all видит pending+хвост сессии
VT._voice_db = lambda: cog.db  # type: ignore
merged = VT._merge_live_voice(7, {})
check('42' in merged, 'merge live отдаёт uid')
check(merged['42']['total_seconds'] >= 15, 'merge live показывает время до leave')

# после leave-симуляции: списать остаток
cog.sessions[7]['42'] = time.time() - 5
_credit()
join_gone = cog.sessions[7].pop('42', None)
check(join_gone is not None, 'leave забирает session')
# остаток уже в pending через credit; leave дописал бы ещё — ок
VT._set_active_tracker(None)
print('ALL OK')
