# -*- coding: utf-8 -*-
"""Анкета в команду: тег куратора — в самой карточке (владелец 2026-09-06).

«807030012301541377 — это роль куратора»: бот раньше не тегал её вовсе
(роль нигде не была задана), а тег уходил голой строкой над карточкой.
Заявки идут в единую комнату 1544483947705008188 («всё сюда, кроме
логов» — апелляции и заявки в команду в одном месте, владелец
2026-09-06). Теперь:
  1) роль куратора: панель → .env → известная роль сервера
     (807030012301541377); тег ставится только реально существующей роли;
  2) карточка заявки переделана: тег куратора В САМОЙ АНКЕТЕ, заявитель
     в шапке, поля Возраст/Активность/Опыт/Почему, меню решения снизу;
  3) content с тем же тегом — чтобы Discord реально прислал уведомление
     роли (упоминание внутри embed не пингует);
  4) заявка с сайта (панель) приходит той же карточкой — тоже в комнату.

Запуск: python3 tests/test_staff_apply_card.py
"""
import asyncio
import os
import sys
import tempfile
import types

_TMP = tempfile.mkdtemp(prefix='hakumo_staff_card_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '811000'

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


GID = 811000
CURATOR = 807030012301541377     # роль куратора от владельца
ROOM = 1544483947705008188       # комната «всё сюда»: апелляции + заявки

import discord  # noqa: E402
from config import Config  # noqa: E402
from cogs import staff_apply as SA  # noqa: E402
from services import staff_roles as SR  # noqa: E402


print('== 1. Роль куратора: панель → .env → известная роль сервера ==')
check(SR.KNOWN_CURATOR_ROLE_ID == CURATOR,
      'известная роль куратора — ровно та, что дал владелец')
check(SR.curator_role_id(GID) == CURATOR,
      'без настроек — роль куратора по умолчанию',
      SR.curator_role_id(GID))
SR.save_setting(GID, 'curator_role', 601)
check(SR.curator_role_id(GID) == 601, 'настройка панели главнее')
SR.save_setting(GID, 'curator_role', 0)
check(SR.curator_role_id(GID, env_value=602) == 602, '.env — запасной вариант')
check(SR.curator_role_id(GID, env_value=0) == CURATOR,
      'панель и .env пусты — известная роль сервера')
# ветки заявок — как в панели владельца
SR.save_setting(GID, 'moderator_channel', 502)
SR.save_setting(GID, 'helper_channel', 501)


print('== 2. apply_target: «всё сюда» — комната заявок, ветки запасные ==')


class _Role:
    def __init__(s, rid, name='роль'):
        s.id, s.name = int(rid), name


class _Chan:
    def __init__(s, cid, name='канал'):
        s.id = int(cid)
        s.name = name
        s.sent = []

    async def send(s, content=None, embed=None, view=None, **kw):
        s.sent.append({'content': content, 'embed': embed, 'view': view, **kw})
        return types.SimpleNamespace(id=555001)


class _Guild:
    def __init__(s, channels=(), roles=()):
        s.id = GID
        s.name = 'Сервер владельца'
        s._ch = {int(c.id): c for c in channels}
        s._roles = {int(r.id): r for r in roles}

    def get_channel(s, cid):
        try:
            return s._ch.get(int(cid))
        except (TypeError, ValueError):
            return None

    def get_role(s, rid):
        try:
            return s._roles.get(int(rid))
        except (TypeError, ValueError):
            return None


mod_ch = _Chan(502, 'ветка-модераторов')
help_ch = _Chan(501, 'ветка-хелперов')
room_ch = _Chan(ROOM, 'комната-заявок')
# «всё сюда»: комната есть — обе должности идут в неё
g_room = _Guild([room_ch, mod_ch, help_ch], [_Role(CURATOR, 'Куратор')])
ch, tag = SA.apply_target('Модератор', g_room)
check(ch is not None and ch.id == ROOM,
      'заявка модератора — в комнату 1544483947705008188',
      getattr(ch, 'id', None))
check(tag == f'<@&{CURATOR}>', 'тег куратора приложен к заявке', tag)
ch, tag = SA.apply_target('Хелпер', g_room)
check(ch is not None and ch.id == ROOM, 'заявка хелпера — тоже в комнату: «всё сюда»')
check(SA.apply_target('Модератор', None) == (None, ''), 'без гильдии — ничего')
# комнаты нет на сервере — запасной путь прежний: ветки по должности
g_cur = _Guild([mod_ch, help_ch], [_Role(CURATOR, 'Куратор')])
ch, tag = SA.apply_target('Модератор', g_cur)
check(ch is not None and ch.id == 502, 'комнаты нет — заявка модератора в запасную ветку')
check(tag == f'<@&{CURATOR}>', 'тег куратора — роль владельца без всяких настроек',
      tag)
ch, tag = SA.apply_target('Хелпер', g_cur)
check(ch is not None and ch.id == 501, 'комнаты нет — заявка хелпера в свою ветку')
check(tag == f'<@&{CURATOR}>', 'куратор ОДИН: тот же тег и у хелперов')
# роли куратора нет на сервере — тег не ставим (@несуществующей роли не надо)
g_norole = _Guild([mod_ch, help_ch], [])
ch, tag = SA.apply_target('Модератор', g_norole)
check(ch is not None and tag == '', 'роли нет на сервере — без тега', tag)
# своя настройка панели главнее известной роли
SR.save_setting(GID, 'curator_role', 601)
g_own = _Guild([room_ch, mod_ch], [_Role(601, 'Куратор ветки')])
ch, tag = SA.apply_target('Модератор', g_own)
check(ch is not None and ch.id == ROOM and tag == '<@&601>',
      'своя роль куратора из панели важнее дефолта — и комната на месте', tag)
SR.save_setting(GID, 'curator_role', 0)


print('== 3. Карточка заявки из Discord: в комнату, тег в самом анкете ==')


class _Av:
    url = 'https://cdn.discordapp.com/a.png'


class _User:
    id = 777888999000111222
    display_name = 'Егорик'
    mention = '<@777888999000111222>'
    display_avatar = _Av()
    bot = False

    def __str__(s):
        return 'Егорик'


class _Resp:
    def __init__(s):
        s.sent = []

    async def send_message(s, embed=None, ephemeral=False, **kw):
        s.sent.append({'embed': embed, 'ephemeral': ephemeral})


class _Inter:
    def __init__(s, guild):
        s.user = _User()
        s.guild = guild
        s.response = _Resp()


modal = SA.StaffApplyModal(role_name='Модератор')
modal.age._value = '19'
modal.experience._value = 'Был модератором на сервере X два года'
modal.reason._value = 'Нравится комьюнити, хочу помогать'
modal.activity._value = '5 часов в день'
inter = _Inter(g_room)
asyncio.new_event_loop().run_until_complete(modal.on_submit(inter))

check(len(room_ch.sent) == 1, 'карточка ушла в комнату заявок (1544483947705008188)')
check(len(mod_ch.sent) == 0 and len(help_ch.sent) == 0,
      'запасные ветки не тронуты')
sent = room_ch.sent[0]
check(sent.get('content') == f'<@&{CURATOR}>',
      'content несёт тег — Discord реально пингует роль куратора',
      sent.get('content'))
emb = sent.get('embed')
check(emb is not None and 'Новая заявка — Модератор' in str(emb.title),
      'заголовок карточки — заявка с должностью', getattr(emb, 'title', None))
desc = str(getattr(emb, 'description', '') or '')
check(desc.startswith(f'<@&{CURATOR}>'),
      'тег куратора — В САМОЙ АНКЕТЕ, первой строкой', desc[:80])
check('Егорик' in str(getattr(emb, 'author', None) or '') ,
      'заявитель — в шапке карточки', str(getattr(emb, 'author', None)))
check('<@777888999000111222>' in desc and '777888999000111222' in desc,
      'в карточке упоминание и id заявителя', desc)
names = [f.name for f in emb.fields]
check(names == ['Возраст', 'Активность', 'Опыт модерации', 'Почему выбирает нас'],
      f'поля карточки: возраст/активность/опыт/почему {names}')
vals = {f.name: f.value for f in emb.fields}
check(vals['Возраст'] == '19' and vals['Активность'] == '5 часов в день',
      'короткие ответы — в строках')
check('сервере X' in vals['Опыт модерации'] and 'комьюнити' in vals['Почему выбирает нас'],
      'опыт и причина — целиком в карточке')
check('777888999000111222' in str(emb.footer.text),
      'футер держит ID заявителя', emb.footer.text)
check(isinstance(sent.get('view'), SA.StaffReviewView),
      'меню «Принять/Отклонить» — под карточкой')
am = sent.get('allowed_mentions')
check(am is not None and getattr(am, 'roles', None) is True,
      'пинг роли разрешён явно (allowed_mentions)')
check(len(inter.response.sent) == 1 and inter.response.sent[0]['ephemeral'] is True,
      'заявителю — ephemeral-подтверждение')
apps = SA.load_apps()
app = apps.get('777888999000111222')
check(app is not None and app['status'] == 'pending',
      'заявка сохранена со статусом pending')
check(app.get('message_id') == '555001', 'id карточки запомнен в заявке')
check(app.get('curator_tag') == f'<@&{CURATOR}>', 'тег куратора запомнен')


print('== 4. Заявка с сайта — та же карточка с тегом ==')
web_src = open(os.path.join(ROOT, 'web', 'app.py'), encoding='utf-8').read()
i = web_src.index('send_to_discord')
seg = web_src[i:i + 2600]
check('Новая заявка — ' in seg and 'заявка ждёт вашего взгляда' in seg,
      'карточка с сайта: тот же заголовок и тег внутри анкеты')
check('allowed_mentions =discord .AllowedMentions (roles =True )' in seg,
      'сайт тоже реально пингует роль куратора')
check('Заявитель:' in seg and 'подана с сайта' in seg,
      'сайт помечает, что заявка пришла с сайта')
check('apply_target' in seg,
      'сайт выбирает канал той же функцией — заявка идёт в комнату 1544483947705008188')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
