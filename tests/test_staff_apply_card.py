# -*- coding: utf-8 -*-
"""Staff apply card: curator ping + V2 LayoutView (owner 2026-09-06 / 09-24).

  1) curator role: panel → .env → known server role;
  2) V2 card with Accept/Decline; content pings curator;
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

# own branch takes priority when set
ch, tag = SA.apply_target('Moderator', g_room)
check(ch is not None and ch.id == 502,
      'Moderator → own branch 502', getattr(ch, 'id', None))
check(tag == f"<@&{SR.KNOWN_CURATOR_BY_KIND['moderator']}>",
      'Moderator pings own curator', tag)

ch, tag = SA.apply_target('Helper', g_room)
check(ch is not None and ch.id == 501 and
      tag == f"<@&{SR.KNOWN_CURATOR_BY_KIND['helper']}>",
      'Helper → branch 501 + curator')

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
          'still pings mod curator in apps channel', tag)
finally:
    SA.APPLY_CHANNEL_ID = _saved_apply

# apply channel missing on guild → legacy room
ch, tag = SA.apply_target('Moderator', g_room)
check(ch is not None and ch.id == ROOM,
      'no apply channel on guild → shared room', getattr(ch, 'id', None))
check(tag == f"<@&{SR.KNOWN_CURATOR_BY_KIND['moderator']}>",
      'still pings mod curator in room', tag)


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


# restore own branches empty → room
modal = SA.StaffApplyModal(role_name='Moderator')
modal.age._value = '19'
modal.experience._value = 'Mod on server X for 2y'
modal.reason._value = 'Like the community'
modal.activity._value = '5h/day'
inter = _Inter(g_room)
asyncio.get_event_loop().run_until_complete(modal.on_submit(inter))

check(len(room_ch.sent) >= 1, 'card sent to shared room')
check(len(mod_ch.sent) == 0 and len(help_ch.sent) == 0, 'own branches unused')
# V2: пинг отдельным сообщением, карточка — view без content
ping_msg = next((s for s in room_ch.sent if s.get('content')), None)
card_msg = next((s for s in room_ch.sent if s.get('view') is not None), None)
sent = card_msg or room_ch.sent[-1]
cur_ping = f"<@&{SR.KNOWN_CURATOR_BY_KIND['moderator']}>"
ping_content = str((ping_msg or {}).get('content') or '')
check(cur_ping in ping_content,
      'ping message mentions curator', ping_content)
check('<@777888999000111222>' in ping_content,
      'ping message tags applicant', ping_content)
view = sent.get('view')
check(isinstance(view, SA.StaffAppCardView),
      'V2 StaffAppCardView', type(view))
check(getattr(view, 'has_components_v2', lambda: False)(),
      'card has Components V2')
# allowed_mentions на пинг-сообщении (V2-карточка без content)
am = (ping_msg or {}).get('allowed_mentions')
check(am is not None,
      'ping has allowed_mentions', am)
apps = SA.load_apps()
app = apps.get('777888999000111222')
check(app is not None and app['status'] == 'pending', 'saved pending')
check(app.get('role') == 'Moderator', 'role stored as Moderator', app.get('role'))
check(app.get('message_id') == '555001', 'message_id saved')
check(app.get('curator_tag') == f"<@&{SR.KNOWN_CURATOR_BY_KIND['moderator']}>",
      'curator_tag saved')


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
