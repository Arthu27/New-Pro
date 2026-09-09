# -*- coding: utf-8 -*-
"""Апелляции — упрощённая схема 2026-09-08: заявка просто в канал апелляций."""

import asyncio
import os
import sys
import tempfile
import types

_TMP = tempfile.mkdtemp(prefix='hakumo_appeals_room_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '711000'

PASS = 0
FAIL = 0

def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')

GID = 711000
ROOM = 1544483947705008188
CARDS = 1312434963941167134
BANNED = 697389321447145482
MOD = 424200000000000424

import discord  # noqa: E402
from cogs import appeals as A  # noqa: E402
from services import channel_routes as CR  # noqa: E402

class _Chan:
    def __init__(s, cid, name='канал', fail_threads=False):
        s.id = cid
        s.name = name
        s.fail_threads = fail_threads
        s.sent = []
        s.threads = []
        s.overwrites = []
    async def create_thread(s, **kw):
        if s.fail_threads:
            raise discord.Forbidden(types.SimpleNamespace(status=403, reason='Missing Access'), '403 Forbidden')
        t = _Chan(900000 + len(s.threads), kw.get('name', ''))
        s.threads.append(t)
        return t
    async def send(s, *args, **kw):
        if args:
            kw['content'] = args[0]
        s.sent.append(kw)
        return types.SimpleNamespace(id=1000 + len(s.sent), jump_url=f'http://j/{len(s.sent)}')
    async def set_permissions(s, user, overwrite=None, **kw):
        s.overwrites.append((getattr(user, 'id', 0), overwrite))

class _Guild:
    def __init__(s, channels):
        s.id = GID
        s.name = 'Сервер владельца'
        s._ch = {c.id: c for c in channels}
        s.system_channel = None
        s.roles = []
    def get_channel(s, cid): return s._ch.get(int(cid))
    def get_member(s, uid): return None

class _User:
    def __init__(s, uid, name):
        s.id = uid
        s.name = name
        s.display_name = name
        s.mention = f'<@{uid}>'
        s.bot = False
        s.display_avatar = types.SimpleNamespace(url='http://a/1')
        s.roles = []
        s.dms = []
    async def send(s, embed=None, **kw): s.dms.append((embed, kw))

class _Bot:
    def __init__(s, guild):
        s.guilds = [guild]
        s._g = guild
    def get_guild(s, gid): return s._g if int(gid) == GID else None

print('== 1. _card_channel: главный канал апелляций ==')
CR.set_route(GID, 'ban_appeal_channel', ROOM)
CR.set_route(GID, 'appeals_channel', CARDS)
room = _Chan(ROOM, 'комната-апелляций')
cards = _Chan(CARDS, 'карточки')
guild = _Guild([room, cards])
cog = A.Appeals(_Bot(guild))

async def _t1():
    return await cog._card_channel(guild, {})

ch, use_thread = asyncio.new_event_loop().run_until_complete(_t1())
check(getattr(ch, 'id', None) == ROOM and use_thread is False, 'комната задана → карточка в неё, без ветки')

CR.set_route(GID, 'ban_appeal_channel', 0)
cards_only = _Chan(CARDS, 'карточки')
guild_no_room = _Guild([cards_only])

async def _t1b():
    return await cog._card_channel(guild_no_room, {})

ch2, use_thread2 = asyncio.new_event_loop().run_until_complete(_t1b())
# в простой схеме даже без комнаты — без ветки, просто в запасной канал
check(getattr(ch2, 'id', None) == CARDS and use_thread2 is False, 'комнаты нет → запасной канал, без ветки')
CR.set_route(GID, 'ban_appeal_channel', ROOM)

print('== 2. Подача из ЛС: карточка просто в канал ==')
state = cog._load(GID)

class _DMedUser(_User):
    pass

vasya = _DMedUser(BANNED, 'Егорик')

async def _t2():
    return await cog._submit_appeal(vasya, guild, 'Прошу разбан, я всё осознал')

item, err = asyncio.new_event_loop().run_until_complete(_t2())
check(err is None and item is not None, 'апелляция из ЛС создана', err or '')
check(len(room.sent) >= 1 and len(room.threads) == 0, 'карточка легла прямо в канал без тредов')
check(len(cards.sent) == 0, 'запасной канал не тронут')
view = (room.sent[0] or {}).get('view')
ids = [str(b.custom_id) for b in view.children] if view else []
check(any(i.startswith('appeal:accept:') for i in ids), 'на карточке кнопки Принять / Отклонить')
check(item.get('card_channel_id') == ROOM and item.get('message_id'), 'канал и сообщение запомнены')

st = cog._load(GID)
st['settings'] = dict(st.get('settings') or {})
st['settings']['ping_role_id'] = 7001
cog._save(GID, st)
room.sent.clear()

async def _t2b():
    return await cog._submit_appeal(_DMedUser(111222333444555667, 'Второй'), guild, 'Тоже прошу разбана')

item2, err2 = asyncio.new_event_loop().run_until_complete(_t2b())
check(err2 is None and len(room.sent) >= 1, 'карточка + пинг — в канале')
_ping = [m for m in room.sent if '<@&7001>' in str(m.get('content') or '')]
check(len(_ping) == 1, 'пинг роли уведомляет про новую заявку')

print('== 2b. Тег куратора по умолчанию ==')
st = cog._load(GID)
st['settings'] = dict(st.get('settings') or {})
st['settings']['ping_role_id'] = 0
cog._save(GID, st)
room.sent.clear()

async def _t2c():
    return await cog._submit_appeal(_DMedUser(222333444555666777, 'Третий'), guild, 'Прошу разбана')

item3, err3 = asyncio.new_event_loop().run_until_complete(_t2c())
check(err3 is None and item3 is not None, 'апелляция создана')
_cur = [m for m in room.sent if '<@&807030012301541377>' in str(m.get('content') or '')]
check(len(_cur) == 1, 'новая апелляция тегает куратора по умолчанию')

print('== 2c. ЛС-путь — тоже просто в канал, без тредов ==')
CR.set_route(GID, 'ban_appeal_channel', 0)
CR.set_route(GID, 'appeals_channel', CARDS)
cards2 = _Chan(CARDS, 'карточки')
guild2 = _Guild([cards2])
cog2 = A.Appeals(_Bot(guild2))

async def _t2d():
    return await cog2._submit_appeal(_DMedUser(333444555666777888, 'Четвёртый'), guild2, 'Прошу разбана')

item4, err4 = asyncio.new_event_loop().run_until_complete(_t2d())
check(err4 is None and item4 is not None, 'апелляция из ЛС создана')
check(len(cards2.sent) >= 1 and len(cards2.threads) == 0, 'карточка просто в канал, без тредов')
CR.set_route(GID, 'ban_appeal_channel', ROOM)

print('== 3. Кнопка «Подать апелляцию» в ЛС ==')
v = A.AppealDMView()
btn = v.children[0]
check(str(btn.custom_id) == A.DM_APPEAL_CUSTOM_ID == 'appeal:dm:open', 'custom_id стабильный')
check(v.timeout is None, 'view persistent')
check(btn.label == 'Подать апелляцию' and btn.style is discord.ButtonStyle.success, 'зелёная кнопка')

class _Resp:
    def __init__(s): s.modal = None; s.msg = None
    async def send_modal(s, m): s.modal = m
    async def send_message(s, content=None, **kw): s.msg = str(content or '')

class _Inter:
    def __init__(s, user, cog, banned=True):
        s.user = user
        s.response = _Resp()
        s.client = types.SimpleNamespace(get_cog=lambda name: (cog if name == 'Appeals' else None))
        class _G:
            id = GID
            name = 'Сервер владельца'
            async def fetch_ban(s, u):
                if not banned:
                    raise discord.NotFound(types.SimpleNamespace(status=404, reason=''), 'нет')
                return True
        s._g = _G()

class _StubCog:
    def _main_guild(s): return guild
    async def _is_banned(s, g, u): return s._banned

stub = _StubCog()
stub._banned = True
it = _Inter(_User(BANNED, 'Егорик'), stub, banned=True)
asyncio.new_event_loop().run_until_complete(v._open(it))
check(it.response.modal is not None and isinstance(it.response.modal, A.AppealModal), 'забаненному — форма')
stub._banned = False
it2 = _Inter(_User(BANNED, 'Егорик'), stub, banned=False)
asyncio.new_event_loop().run_until_complete(v._open(it2))
check(it2.response.modal is None and 'не забанены' in (it2.response.msg or ''), 'незабаненному — отказ')

print('== 4. «Взять в работу» — помечает, но НЕ открывает канал ==')
from services import permission_acl as PACL
PACL.set_action_rule(GID, 'ban', ['9001'])
mod_user = _User(MOD, 'Лина.Мод')
mod_user.roles = [types.SimpleNamespace(id=9001)]

async def _fu(uid): return vasya
cog.bot.fetch_user = _fu

class _Resp2:
    async def edit_message(s, **kw): pass
class _Fup:
    def __init__(s): s.sent = []
    async def send(s, *a, **kw): s.sent.append(kw)
class _Inter2:
    def __init__(s, user):
        s.user = user
        s.message = types.SimpleNamespace(embeds=[])
        s.response = _Resp2()
        s.followup = _Fup()

room.sent.clear()
room.overwrites.clear()
view = A.AppealView(cog, GID, item['id'])
inter = _Inter2(mod_user)
asyncio.new_event_loop().run_until_complete(view._claim(inter))
_st = cog._load(GID)
_it = A.get_appeal(_st, item['id'])
check(_it.get('claimed_by', {}).get('id') == str(MOD), 'апелляция в работе у модера')
check(len(room.overwrites) == 0, 'в простой схеме канал НЕ открываем (нет overwrite)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
