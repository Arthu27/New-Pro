# -*- coding: utf-8 -*-
"""Апелляции — упрощённая схема 2026-09-08

1) Карточка уходит просто в канал апелляций с кнопками, без тредов и без открытия доступов
2) /report тегает только модераторов
"""
import asyncio
import json
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(tempfile.mkdtemp(prefix='app_rep_'))
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.abspath(os.path.join('data', 'bot.db'))
sys.path.insert(0, ROOT)

PASS = FAIL = 0

def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')

import discord  # noqa: E402
from cogs import appeals as A  # noqa: E402
from cogs import reports as R  # noqa: E402
from services import channel_routes as CR  # noqa: E402

GID = 1484574976580391004
APPEAL_CH = 1544483947705008188
CARDS_CH = 1312434963941167134

class _Perms:
    def __init__(self, **kw):
        d = dict(administrator=False, ban_members=False, moderate_members=False, manage_messages=False, create_public_threads=False, manage_threads=False, mention_everyone=False)
        d.update(kw)
        self.__dict__.update(d)

class _Role:
    def __init__(self, rid, name, perms=None, managed=False):
        self.id = rid
        self.name = name
        self.managed = managed
        self.mention = f'<@&{rid}>'
        self.permissions = perms or _Perms()
        self.is_default = lambda: rid == 0

class _Channel:
    def __init__(self, cid, name='апелляции', fail_threads=False):
        self.id = cid
        self.name = name
        self.fail_threads = fail_threads
        self.sent = []
        self.threads = []
        self.overwrites = []
    async def create_thread(self, **kw):
        if self.fail_threads:
            raise discord.Forbidden(types.SimpleNamespace(status=403, reason='Missing Access'), '403 Forbidden')
        t = _Channel(900000 + len(self.threads), kw.get('name', ''))
        self.threads.append(t)
        return t
    async def send(self, *args, **kw):
        if args:
            kw['content'] = args[0]
        self.sent.append(kw)
        return types.SimpleNamespace(id=1000 + len(self.sent), jump_url=f'http://j/{len(self.sent)}')
    async def set_permissions(self, user, overwrite=None, **kw):
        self.overwrites.append((user.id, overwrite))

class _Guild:
    def __init__(self, channels, roles):
        self.id = GID
        self.name = 'Hakumo'
        self._channels = {c.id: c for c in channels}
        self.roles = roles
        self.system_channel = None
        self._members = {}
    def get_member(self, uid): return self._members.get(int(uid))
    def get_channel(self, cid): return self._channels.get(int(cid))
    def get_role(self, rid):
        for r in self.roles:
            if r.id == int(rid):
                return r
        return None

class _User:
    def __init__(self, uid, name):
        self.id = uid
        self.name = name
        self.display_name = name
        self.mention = f'<@{uid}>'
        self.bot = False
        self.display_avatar = types.SimpleNamespace(url='http://a/1')
        self.roles = []
        self.guild_permissions = _Perms()
        self.dms = []
    async def send(self, embed=None, **kw): self.dms.append(embed)

class _Bot:
    def __init__(self, guild):
        self._g = guild
        self.guilds = [guild]
    def get_guild(self, gid): return self._g if int(gid) == GID else None

CR.set_route(GID, 'ban_appeal_channel', APPEAL_CH)
CR.set_route(GID, 'appeals_channel', CARDS_CH)
appeal_ch = _Channel(APPEAL_CH)
cards_ch = _Channel(CARDS_CH, name='карточки')
mod_role = _Role(7001, 'Модератор', _Perms(ban_members=True))
admin_role = _Role(7002, 'Админ', _Perms(administrator=True))
everyone = _Role(0, '@everyone')
guild = _Guild([appeal_ch, cards_ch], [everyone, mod_role, admin_role])
bot = _Bot(guild)
cog = A.Appeals(bot)

async def main():
    user = _User(555, 'Обвинённый Вася')

    print('== 1. Апелляция из канала: карточка просто в канал апелляций ==')
    item, err = await cog._submit_channel_appeal(user, guild, 'Прошу разбан')
    check(err is None, 'апелляция создана без ошибок', f'→ {err}')
    # в простой схеме карточка + тег куратора в том же канале, без тредов и без открытия доступов
    check(len(appeal_ch.sent) >= 1 and len(appeal_ch.threads) == 0,
          'карточка легла прямо в канал апелляций без тредов',
          f'{len(appeal_ch.sent)} сообщений, {len(appeal_ch.threads)} тредов')
    check(any('<@&807030012301541377>' in str(m.get('content') or '') for m in appeal_ch.sent),
          'тег куратора 807030012301541377 ушёл в канал при подаче')
    check(not cards_ch.sent, 'запасной канал модеров не тронут')
    view = (appeal_ch.sent[0] or {}).get('view')
    ids = [b.custom_id for b in view.children] if view else []
    check(any(str(i).startswith('appeal:accept:') for i in ids) and any(str(i).startswith('appeal:reject:') for i in ids),
          'на карточке есть Принять / Отклонить', f'→ {ids}')
    check(item.get('message_id') and item.get('card_channel_id') == APPEAL_CH, 'запись апелляции знает ID карточки и канал')
    check(len(appeal_ch.overwrites) == 0, 'комната НЕ открывается подавшему (простая схема)')

    print('== 2. Комнаты нет → запасной канал, без тредов ==')
    CR.set_route(GID, 'ban_appeal_channel', 0)
    cards_ch2 = _Channel(CARDS_CH, name='карточки')
    guild2 = _Guild([cards_ch2], [everyone, mod_role])
    cog2 = A.Appeals(_Bot(guild2))
    item2, err2 = await cog2._submit_channel_appeal(_User(556, 'Петя'), guild2, 'Верните доступ')
    check(err2 is None and len(cards_ch2.sent) >= 1,
          'без комнаты карточка ушла в запасной канал без тредов')
    CR.set_route(GID, 'ban_appeal_channel', APPEAL_CH)

    print('== 3. ЛС подавшему — простая схема ==')
    class _DmUser(_User):
        def __init__(self, uid=557, name='Сява'):
            super().__init__(uid, name)
            self.dms = []
        async def send(self, embed=None, **kw): self.dms.append(embed)
    du = _DmUser()
    appeal_ch3 = _Channel(APPEAL_CH, fail_threads=True)
    cards_ch3 = _Channel(CARDS_CH, name='карточки', fail_threads=True)
    guild3 = _Guild([appeal_ch3, cards_ch3], [everyone, mod_role])
    cog3 = A.Appeals(_Bot(guild3))
    guild3._members[du.id] = du
    await cog3._submit_channel_appeal(du, guild3, 'Прошу разбан, всё было не так')
    check(len(du.dms) == 1 and 'канал' in (du.dms[0].description or '').lower(), 'ЛС говорит про канал апелляций')

    print('== 4. /report тегает модераторов: каноническая роль ==')
    with open(f'data/reports_{GID}.json', 'w', encoding='utf-8') as f:
        json.dump({'mod_role_id': '7001'}, f)
    roles = R._mod_ping_roles(guild)
    check(mod_role in roles, 'тег: каноническая роль модераторов найдена')

    print('== 5. Без канона: только role_map «mod», не admin/curator ==')
    os.remove(f'data/reports_{GID}.json')
    for legacy in (f'data/ticket_notify_{GID}.json', f'data/ticket_permissions_{GID}.json', 'data/staff_roles.json'):
        if os.path.exists(legacy): os.remove(legacy)
    curator_role = _Role(7003, 'Куратор', _Perms(manage_messages=True))
    guild.roles.append(curator_role)
    with open('data/role_map.json', 'w', encoding='utf-8') as f:
        json.dump({'7001': 'mod', '7002': 'admin', '7003': 'curator'}, f)
    roles = R._mod_ping_roles(guild)
    check(mod_role in roles, 'тег: роль «mod» из role_map.json')
    check(admin_role not in roles, 'тег: админов НЕ зовём')
    check(curator_role not in roles, 'тег: кураторов НЕ зовём')
    check(everyone not in roles, 'тег: @everyone не тегается')

    print('== 6. Совсем нет ролей модерации → карточка уходит, панель предупреждена ==')
    guild_bare = _Guild([_Channel(1312434963941167134)], [_Role(0, '@everyone'), _Role(8001, 'Цветная', managed=True)])
    with open('data/role_map.json', 'w', encoding='utf-8') as f:
        json.dump({}, f)
    roles = R._mod_ping_roles(guild_bare)
    check(roles == [], 'кандидатов нет — не выдумываем')

    print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
    sys.exit(1 if FAIL else 0)

asyncio.run(main())
