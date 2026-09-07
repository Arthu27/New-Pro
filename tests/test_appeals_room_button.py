# -*- coding: utf-8 -*-
"""Апелляции — «всё в комнату, кроме логов» + кнопка в ЛС о бане (2026-09-06).

1) Карточка апелляции падает в саму комнату апелляции (маршрут
   «Комната апелляции», 1544483947705008188): заявка, кнопки, пинг и
   напоминания — всё в одном канале. Запасной канал карточек используется
   только если комнаты нет (там заявка уходит в свою ветку).
2) ЛС о бане получает внизу зелёную кнопку «Подать апелляцию»: та же
   форма, что /апелляция; кнопка persistent — переживает рестарт.

Запуск: python3 tests/test_appeals_room_button.py
"""
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
ROOM = 1544483947705008188      # комната апелляции — ID от владельца
CARDS = 1312434963941167134     # запасной канал карточек
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
            raise discord.Forbidden(
                types.SimpleNamespace(status=403, reason='Missing Access'),
                '403 Forbidden')
        t = _Chan(900000 + len(s.threads), kw.get('name', ''))
        s.threads.append(t)
        return t

    async def send(s, *args, **kw):
        if args:
            kw['content'] = args[0]
        s.sent.append(kw)
        return types.SimpleNamespace(id=1000 + len(s.sent),
                                     jump_url=f'http://j/{len(s.sent)}')

    async def set_permissions(s, user, overwrite=None, **kw):
        s.overwrites.append((getattr(user, 'id', 0), overwrite))


class _Guild:
    def __init__(s, channels):
        s.id = GID
        s.name = 'Сервер владельца'
        s._ch = {c.id: c for c in channels}
        s.system_channel = None
        s.roles = []

    def get_channel(s, cid):
        return s._ch.get(int(cid))

    def get_member(s, uid):
        return None


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

    async def send(s, embed=None, **kw):
        s.dms.append((embed, kw))


class _Bot:
    def __init__(s, guild):
        s.guilds = [guild]
        s._g = guild

    def get_guild(s, gid):
        return s._g if int(gid) == GID else None


print('== 1. _card_channel: комната — главный, карточки — запасной ==')
CR.set_route(GID, 'ban_appeal_channel', ROOM)
CR.set_route(GID, 'appeals_channel', CARDS)
room = _Chan(ROOM, 'комната-апелляций')
cards = _Chan(CARDS, 'карточки')
guild = _Guild([room, cards])
cog = A.Appeals(_Bot(guild))

async def _t1():
    return await cog._card_channel(guild, {})
ch, use_thread = asyncio.new_event_loop().run_until_complete(_t1())
check(getattr(ch, 'id', None) == ROOM and use_thread is False,
      'комната задана → карточка в неё, без ветки', f'{ch} {use_thread}')

# «комнаты нет»: у владельца комната — известный ID (KNOWN fallback),
# поэтому честно проверяем запасной путь на сервере БЕЗ этого канала
CR.set_route(GID, 'ban_appeal_channel', 0)
cards_only = _Chan(CARDS, 'карточки')
guild_no_room = _Guild([cards_only])


async def _t1b():
    return await cog._card_channel(guild_no_room, {})


ch2, use_thread2 = asyncio.new_event_loop().run_until_complete(_t1b())
check(getattr(ch2, 'id', None) == CARDS and use_thread2 is True,
      'комнаты нет → запасной канал карточек + своя ветка',
      f'{getattr(ch2, "id", ch2)} {use_thread2}')
CR.set_route(GID, 'ban_appeal_channel', ROOM)


print('== 2. Подача из ЛС: карточка и пинг — в комнате апелляции ==')
state = cog._load(GID)


class _DMedUser(_User):
    pass


vasya = _DMedUser(BANNED, 'Егорик')


async def _t2():
    return await cog._submit_appeal(vasya, guild, 'Прошу разбан, я всё осознал')


item, err = asyncio.new_event_loop().run_until_complete(_t2())
check(err is None and item is not None, 'апелляция из ЛС создана', err or '')
check(len(room.sent) >= 1 and not room.threads,
      'карточка легла прямо в комнату апелляции')
check(len(cards.sent) == 0, 'запасной канал не тронут')
view = (room.sent[0] or {}).get('view')
ids = [str(b.custom_id) for b in view.children] if view else []
check(any(i.startswith('appeal:accept:') for i in ids)
      and any(i.startswith('appeal:claim:') for i in ids),
      'на карточке кнопки Принять / Взять в работу', f'→ {ids}')
check(item.get('card_channel_id') == ROOM and item.get('message_id'),
      'канал и сообщение карточки запомнены')
# пинг роли при новой апелляции — тоже в комнату
st = cog._load(GID)
st['settings'] = dict(st.get('settings') or {})
st['settings']['ping_role_id'] = 7001
cog._save(GID, st)
room.sent.clear()


async def _t2b():
    return await cog._submit_appeal(_DMedUser(111222333444555667, 'Второй'),
                                    guild, 'Тоже прошу разбана, вот пруф')


item2, err2 = asyncio.new_event_loop().run_until_complete(_t2b())
check(err2 is None and len(room.sent) == 2,
      'карточка + пинг роли — оба в комнате апелляции',
      f'{len(room.sent)} сообщений')
_ping = [m for m in room.sent if '<@&7001>' in str(m.get('content') or '')]
check(len(_ping) == 1, 'пинг роли уведомляет про новую заявку в комнате')


print('== 3. Кнопка «Подать апелляцию» в ЛС о бане ==')
v = A.AppealDMView()
btn = v.children[0]
check(str(btn.custom_id) == A.DM_APPEAL_CUSTOM_ID == 'appeal:dm:open',
      'custom_id кнопки ЛС стабильный (persistent)')
check(v.timeout is None, 'view persistent — переживает рестарт')
check(btn.label == 'Подать апелляцию' and
      btn.style is discord.ButtonStyle.success,
      'зелёная кнопка «Подать апелляция»')


class _Resp:
    def __init__(s):
        s.modal = None
        s.msg = None

    async def send_modal(s, m):
        s.modal = m

    async def send_message(s, content=None, **kw):
        s.msg = str(content or '')


class _Inter:
    def __init__(s, user, cog, banned=True):
        s.user = user
        s.response = _Resp()
        s.client = types.SimpleNamespace(
            get_cog=lambda name: (cog if name == 'Appeals' else None))

        class _G:
            id = GID
            name = 'Сервер владельца'

            async def fetch_ban(s, u):
                if not banned:
                    raise discord.NotFound(
                        types.SimpleNamespace(status=404, reason=''), 'нет')
                return True
        s._g = _G()


class _StubCog:
    def _main_guild(s):
        return guild

    async def _is_banned(s, g, u):
        return s._banned


stub = _StubCog()
stub._banned = True
it = _Inter(_User(BANNED, 'Егорик'), stub, banned=True)
asyncio.new_event_loop().run_until_complete(v._open(it))
check(it.response.modal is not None
      and isinstance(it.response.modal, A.AppealModal),
      'забаненному кнопка открывает форму апелляции')
stub._banned = False
it2 = _Inter(_User(BANNED, 'Егорик'), stub, banned=False)
asyncio.new_event_loop().run_until_complete(v._open(it2))
check(it2.response.modal is None and 'не забанены' in (it2.response.msg or ''),
      'незабаненному — честный отказ без формы', it2.response.msg or '')

# регистрация после рестарта + привязка к ЛС о бане
a_src = open(os.path.join(ROOT, 'cogs', 'appeals.py'),
             encoding='utf-8').read()
m_src = open(os.path.join(ROOT, 'cogs', 'moderation.py'),
             encoding='utf-8').read()
e_src = open(os.path.join(ROOT, 'cogs', 'embed_utils.py'),
             encoding='utf-8').read()
check('self.bot.add_view(AppealDMView())' in a_src,
      'on_ready регистрирует кнопку ЛС (переживает рестарт)')
check("action =='ban'" in m_src.replace(' ', '').replace("action=='ban'", "action =='ban'")
      or "action=='ban'" in m_src.replace(' ', ''),
      'ЛС о бане получает кнопку (только для бана)')
check('AppealDMView' in m_src and 'send_dm' in m_src,
      'модерация вешает view на ЛС о бане')
check('«Подать апелляцию»' in e_src and '/апелляция' in e_src,
      'текст ЛС о бане зовёт нажать кнопку (и команду оставили)')


print('== 3. «Взять в работу» → в комнату: «Вас будет обслуживать» ==')
# Владелец 2026-09-08: модератор взял апелляцию в работу — в комнату
# приходит сообщение, кто будет вести дело. Снятие с работы — тоже
# честно сообщается (человек не ждёт ушедшего модера).
from services import permission_acl as PACL  # noqa: E402

PACL.set_action_rule(GID, 'ban', ['9001'])

mod_user = _User(MOD, 'Лина.Мод')
mod_user.roles = [types.SimpleNamespace(id=9001)]


async def _fu(uid):
    return vasya


cog.bot.fetch_user = _fu


class _Resp:
    async def edit_message(s, **kw):
        pass


class _Fup:
    def __init__(s):
        s.sent = []

    async def send(s, *a, **kw):
        s.sent.append(kw)


class _Inter:
    def __init__(s, user):
        s.user = user
        s.message = types.SimpleNamespace(embeds=[])
        s.response = _Resp()
        s.followup = _Fup()


room.sent.clear()
view = A.AppealView(cog, GID, item['id'])
inter = _Inter(mod_user)
asyncio.new_event_loop().run_until_complete(view._claim(inter))
ann = [m for m in room.sent
       if 'Вас будет обслуживать' in str(m.get('content') or '')]
check(len(ann) == 1, 'в комнату пришло «Вас будет обслуживать: …»',
      f'{len(ann)} сообщений')
check(bool(ann) and mod_user.mention in str(ann[0].get('content') or ''),
      'в объявлении — упоминание модератора')
_st = cog._load(GID)
_it = A.get_appeal(_st, item['id'])
check(_it.get('claimed_by', {}).get('id') == str(MOD),
      'апелляция числится в работе у модера')
# доступ к комнате включился подавшему (overwrite по ID)
_room_ows = [u for u, _o in room.overwrites if int(u) == BANNED]
check(bool(_room_ows), 'overwrite доступа к комнате стоит для подавшего')

# снятие с работы — честное сообщение в комнату
room.sent.clear()
inter2 = _Inter(mod_user)
asyncio.new_event_loop().run_until_complete(view._claim(inter2))
gone = [m for m in room.sent if 'больше не ведёт' in str(m.get('content') or '')]
check(len(gone) == 1, 'снятие с работы — сообщение в комнату')
_st2 = cog._load(GID)
_it2 = A.get_appeal(_st2, item['id'])
check(not _it2.get('claimed_by'), 'очередь снова общая')


print('== 4. «Взять в работу» из веб-панели — объявление тоже уходит ==')
import threading
import asyncio as _aio
import web.app as _wapp
from web.routes import appeals_panel as WP

_loop = _aio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()


class _BotPanel(_Bot):
    loop = _loop

    def get_cog(s, name):
        return cog if name == 'Appeals' else None

    async def fetch_user(s, uid):
        return vasya


_fake = _BotPanel(guild)
_wapp.bot_instance = _fake
room.sent.clear()
_ok = WP._open_channel_for_claim(_fake, GID, item, reviewer='Лина.Мод')
check(_ok, 'комната открыта подавшему из панели')
_ann = [m for m in room.sent
        if 'Вас будет обслуживать' in str(m.get('content') or '')]
check(len(_ann) == 1 and 'Лина.Мод' in str(_ann[0].get('content') or ''),
      'объявление из панели: «Вас будет обслуживать: Лина.Мод»')

# снятие с работы из панели — честное сообщение в комнату
room.sent.clear()
_ok2 = WP._post_room_note(
    _fake, GID, '🌀 Лина.Мод больше не ведёт вашу апелляцию — она снова '
                'в общей очереди модерации.')
check(_ok2 and any('больше не ведёт' in str(m.get('content') or '')
                   for m in room.sent),
      'снятие с работы из панели — сообщение в комнату')
_wapp.bot_instance = None

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
