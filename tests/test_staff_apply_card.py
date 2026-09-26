# -*- coding: utf-8 -*-
"""Staff apply card: V2 LayoutView without role ping (owner 2026-09-24).

  1) curator role: panel → .env → known server role;
  2) V2 card with Accept/Decline; NO separate curator ping message;
  3) web path uses same StaffAppCardView.

Run: python3 tests/test_staff_apply_card.py
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
CURATOR = 807030012301541377
ROOM = 1544483947705008188

import discord  # noqa: E402
from config import Config  # noqa: E402
from cogs import staff_apply as SA  # noqa: E402
from services import staff_roles as SR  # noqa: E402


print('== 1. Curator role resolution ==')
check(SR.KNOWN_CURATOR_ROLE_ID == CURATOR,
      'known curator role id')
check(SR.curator_role_id(GID) == CURATOR,
      'default curator', SR.curator_role_id(GID))
SR.save_setting(GID, 'curator_role', 601)
check(SR.curator_role_id(GID) == 601, 'panel overrides')
SR.save_setting(GID, 'curator_role', 0)
check(SR.curator_role_id(GID, env_value=602) == 602, '.env fallback')
check(SR.curator_role_id(GID, env_value=0) == CURATOR,
      'known role when empty')
SR.save_setting(GID, 'moderator_channel', 502)
SR.save_setting(GID, 'helper_channel', 501)


print('== 2. apply_target routing ==')


class _Role:
    def __init__(s, rid, name='role'):
        s.id, s.name = int(rid), name


class _Chan:
    def __init__(s, cid, name='channel'):
        s.id = int(cid)
        s.name = name
        s.sent = []
        s.webhooks_list = []

    async def webhooks(s):
        return s.webhooks_list

    async def send(s, content=None, embed=None, view=None, **kw):
        s.sent.append({'content': content, 'embed': embed, 'view': view, **kw})
        return types.SimpleNamespace(id=555001)


class _Guild:
    def __init__(s, channels=(), roles=()):
        s.id = GID
        s.name = 'Hakumo'
        s._ch = {int(c.id): c for c in channels}
        s._roles = {int(r.id): r for r in roles}
        s.me = types.SimpleNamespace(id=1)

    def get_channel(s, cid):
        return s._ch.get(int(cid)) if cid else None

    def get_role(s, rid):
        return s._roles.get(int(rid))


# Patch room route → ROOM
import services.channel_routes as CR  # noqa: E402
_prev_get = CR.get_route
_prev_known = dict(CR.KNOWN_CHANNELS)


def _fake_get_route(gid, key, *a, **k):
    if key == 'ban_appeal_channel':
        return ROOM
    return _prev_get(gid, key, *a, **k)


CR.get_route = _fake_get_route
CR.KNOWN_CHANNELS['ban_appeal_channel'] = ROOM

room_ch = _Chan(ROOM, 'room')
mod_ch = _Chan(502, 'mod')
help_ch = _Chan(501, 'help')
g_room = _Guild(
    channels=(room_ch, mod_ch, help_ch),
    roles=(_Role(CURATOR), _Role(SR.KNOWN_CURATOR_BY_KIND['moderator']),
           _Role(SR.KNOWN_CURATOR_BY_KIND['helper'])))

# own branch when apply channel not on this guild
ch, tag = SA.apply_target('Moderator', g_room)
check(ch is not None and ch.id == 502,
      'Moderator → own branch 502', getattr(ch, 'id', None))
check(tag == f"<@&{SR.KNOWN_CURATOR_BY_KIND['moderator']}>",
      'Moderator curator tag for branch', tag)

ch, tag = SA.apply_target('Helper', g_room)
check(ch is not None and ch.id == 501 and
      tag == f"<@&{SR.KNOWN_CURATOR_BY_KIND['helper']}>",
      'Helper → branch 501 + curator tag')

check(SA.apply_target('Moderator', None) == (None, ''), 'no guild')

# without own branch → apply channel (preferred) then room
SR.save_setting(GID, 'moderator_channel', 0)
SR.save_setting(GID, 'helper_channel', 0)
APPS_CH = 1312436222307860490
apps_ch = _Chan(APPS_CH, 'apps')
g_apps = _Guild(
    channels=(room_ch, mod_ch, help_ch, apps_ch),
    roles=(_Role(CURATOR), _Role(SR.KNOWN_CURATOR_BY_KIND['moderator']),
           _Role(SR.KNOWN_CURATOR_BY_KIND['helper'])))
_saved_apply = SA.APPLY_CHANNEL_ID
SA.APPLY_CHANNEL_ID = APPS_CH
try:
    ch, tag = SA.apply_target('Moderator', g_apps)
    check(ch is not None and ch.id == APPS_CH,
          'no branch → apply channel', getattr(ch, 'id', None))
    check(tag == f"<@&{SR.KNOWN_CURATOR_BY_KIND['moderator']}>",
          'curator tag still computed for apps channel', tag)
finally:
    SA.APPLY_CHANNEL_ID = _saved_apply

# apply channel missing on guild → НЕ в апелляции
ch, tag = SA.apply_target('Moderator', g_room)
check(ch is None,
      'нет канала анкет и ветки → не в апелляции', getattr(ch, 'id', None))
check(tag == f"<@&{SR.KNOWN_CURATOR_BY_KIND['moderator']}>",
      'curator tag still computed for room', tag)


print('== 3. Modal submits V2 card ==')


class _User:
    id = 777888999000111222
    display_name = 'Egorik'
    display_avatar = types.SimpleNamespace(url='https://cdn/x.png')

    def __str__(s):
        return 'Egorik#0001'

    @property
    def mention(s):
        return f'<@{s.id}>'


class _Resp:
    def __init__(s):
        s._done = False
        s.sent = []

    def is_done(s):
        return s._done

    async def defer(s, **kw):
        s._done = True

    async def send_message(s, *a, **kw):
        s.sent.append(kw)
        s._done = True


class _Inter:
    def __init__(s, guild):
        s.user = _User()
        s.guild = guild
        s.response = _Resp()
        s.followup = types.SimpleNamespace(
            send=lambda *a, **k: asyncio.sleep(0))


# канал анкет на сервере (не апелляции)
apps_ch2 = _Chan(APPS_CH, 'apps')
g_submit = _Guild(
    channels=(room_ch, mod_ch, help_ch, apps_ch2),
    roles=(_Role(CURATOR), _Role(SR.KNOWN_CURATOR_BY_KIND['moderator']),
           _Role(SR.KNOWN_CURATOR_BY_KIND['helper'])))
_saved_apply2 = SA.APPLY_CHANNEL_ID
SA.APPLY_CHANNEL_ID = APPS_CH
modal = SA.StaffApplyModal(role_name='Moderator')
modal.age._value = '19'
modal.activity._value = 'пк, 2 часа'
modal.experience._value = 'zxc гуль'
modal.reason._value = '10/10'
inter = _Inter(g_submit)
asyncio.get_event_loop().run_until_complete(modal.on_submit(inter))
SA.APPLY_CHANNEL_ID = _saved_apply2

check(len(apps_ch2.sent) >= 1, 'card sent to apps channel')
check(len(room_ch.sent) == 0, 'апелляции не трогаем')
check(len(mod_ch.sent) == 0 and len(help_ch.sent) == 0, 'own branches unused')
# Без пинга: только карточка (view), content-сообщений нет
ping_msgs = [s for s in apps_ch2.sent if s.get('content')]
card_msg = next((s for s in apps_ch2.sent if s.get('view') is not None), None)
sent = card_msg or apps_ch2.sent[-1]
check(not ping_msgs, 'no separate ping before card', ping_msgs)
view = sent.get('view')
check(isinstance(view, SA.StaffAppCardView),
      'V2 StaffAppCardView', type(view))
check(getattr(view, 'has_components_v2', lambda: False)(),
      'card has Components V2')
# body uses moderator question labels
from services.v2_layouts import layout_plain_text  # noqa: E402
card_text = layout_plain_text(view) if view else ''
check('С чего вы сидите' in card_text and 'знания правил' in card_text,
      'moderator question labels on card', card_text[:200])
check('куратор этой ветки' in card_text.lower(),
      'footer names branch curator', card_text[-160:])
apps = SA.load_apps()
app_key = '777888999000111222:moderator'
app = apps.get(app_key) or apps.get('777888999000111222')
check(app is not None and app['status'] == 'pending', 'saved pending', list(apps.keys()))
check(app.get('role') == 'Moderator', 'role stored as Moderator', app.get('role'))
check(app.get('message_id') == '555001', 'message_id saved')
check(app.get('curator_tag') == f"<@&{SR.KNOWN_CURATOR_BY_KIND['moderator']}>",
      'curator_tag saved (metadata, без пинга)')
check(isinstance(app.get('answers'), list) and len(app['answers']) == 4,
      'answers list saved with 4 Qs')
# повтор на ту же ветку запрещён
deny = SA.apply_blocked_reason('777888999000111222', 'Moderator')
check(deny and 'уже' in deny.lower(), 'pending blocks re-apply', deny)
# другая ветка свободна
ok_other = SA.apply_blocked_reason('777888999000111222', 'Helper')
check(not ok_other, 'other branch still open while Mod pending', ok_other)

print('== 3b. Per-branch questions ==')
for kind, needle in (
        ('Helper', 'предлагать идеи'),
        ('Eventsmod', 'ивентмоды'),
        ('Broadcaster', 'часовой пояс'),
):
    m = SA.StaffApplyModal(role_name=kind)
    labels = [ti.label for ti in m._inputs]
    check(any(needle.lower() in lab.lower() for lab in labels),
          f'{kind} has branch question «{needle}»', labels)
    check(all(len(lab) <= 45 for lab in labels),
          f'{kind} labels ≤45 chars')

# Events: 5 вопросов владельца
m_ev = SA.StaffApplyModal(role_name='Eventsmod')
ev_labels = [ti.label for ti in m_ev._inputs]
check(len(ev_labels) == 5, f'Events has 5 fields', ev_labels)
check('возраст' in ev_labels[0].lower(), 'Events Q1 age')
check('пик активности' in ev_labels[1].lower(), 'Events Q2 peak')
check('ивентмоды' in ev_labels[2].lower(), 'Events Q3 why')
check('стаффе' in ev_labels[3].lower() or 'стафф' in ev_labels[3].lower(),
      'Events Q4 staff exp')
check('ивенты' in ev_labels[4].lower() and 'пример' in ev_labels[4].lower(),
      'Events Q5 favorite events', ev_labels[4])

# Broadcaster: точные 5 вопросов со скрина
m_br = SA.StaffApplyModal(role_name='Broadcaster')
br_labels = [ti.label for ti in m_br._inputs]
check(len(br_labels) == 5, f'Broadcaster has 5 fields', br_labels)
check(br_labels[0].startswith('Ваше Имя и Возраст'), 'Broadcaster Q1 name/age')
check('часовой пояс' in br_labels[1].lower(), 'Broadcaster Q2 timezone')
check('опыт' in br_labels[2].lower(), 'Broadcaster Q3 experience')
check('ПК и микрофон' in br_labels[3] or 'пк и микрофон' in br_labels[3].lower(),
      'Broadcaster Q4 PC+mic')
check('веб камера' in br_labels[4].lower()
      or 'вебкамера' in br_labels[4].lower().replace(' ', ''),
      'Broadcaster Q5 webcam', br_labels[4])

# Event body labels
body_ev = SA.build_application_body(
    user=_User(), user_id='1', age='19', activity='пт–вс 18–23',
    experience='хочу вести', reason='да, helper', extra='мафия, квиз',
    kind='event')
check('возраст' in body_ev.lower() and 'ивентмоды' in body_ev.lower()
      and 'пример' in body_ev.lower(),
      'Events body uses event questions', body_ev[:400])
body_br = SA.build_application_body(
    user=_User(), user_id='1', age='Лёша 22', activity='МСК',
    experience='да', reason='Да', extra='Да', kind='broadcaster')
check('часовой пояс' in body_br.lower() and 'веб камера' in body_br.lower(),
      'Broadcaster body uses broadcaster questions')

print('== 4. Web send_to_discord uses V2 ==')
web_src = open(os.path.join(ROOT, 'web', 'app.py'), encoding='utf-8').read()
check('StaffAppCardView' in web_src and '_send_staff_card' in web_src,
      'web uses V2 staff card')
check('apply_target' in web_src, 'web routes via apply_target')
check('Новая заявка — ' not in web_src.split('send_to_discord')[1][:2000],
      'web no longer builds classic embed title')

CR.get_route = _prev_get
CR.KNOWN_CHANNELS.clear()
CR.KNOWN_CHANNELS.update(_prev_known)

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
