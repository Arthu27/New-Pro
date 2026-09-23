# -*- coding: utf-8 -*-
"""Event panel + Event Mod ACL seed.

Запуск: python3 tests/test_event_panel.py
"""
import ast
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_event_panel_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['MAIN_GUILD_ID'] = '111222333444555666'

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== constants ==')
from services.event_mod_acl_seed import (  # noqa: E402
    EVENT_ADMIN_ROLE_ID, EVENT_MOD_ROLE_ID, EVENT_STAFF_ROLE_IDS,
    apply_event_mod_acl_seed, SEED_VERSION)
from cogs import event_panel as EP  # noqa: E402

check(EVENT_MOD_ROLE_ID == 852634463535759461, 'EVENT_MOD_ROLE_ID')
check(EVENT_ADMIN_ROLE_ID == 1551527644326002748, 'EVENT_ADMIN_ROLE_ID')
check(EP.EVENT_MOD_ROLE_ID == EVENT_MOD_ROLE_ID, 'cog использует тот же mod id')
check(EP.EVENT_ADMIN_ROLE_ID == EVENT_ADMIN_ROLE_ID, 'cog использует тот же admin id')
check(SEED_VERSION >= 2, f'seed v2+: {SEED_VERSION}')
check(callable(EP.configured_panel_channel_id), 'configured_panel_channel_id')
check(callable(EP.resolve_panel_channel), 'resolve_panel_channel')
check(callable(EP.apply_start) and callable(EP.apply_end), 'start/end helpers')
check('EVENT_PANEL_CHANNEL_ID' in open(
    os.path.join(ROOT, 'config.py'), encoding='utf-8').read(),
    'Config.EVENT_PANEL_CHANNEL_ID')
src = open(os.path.join(ROOT, 'cogs/event_panel.py'), encoding='utf-8').read()
check("name='event-panel'" in src
      and 'channel: discord.TextChannel' in src,
    '/event-panel принимает channel')
check("event_panel:start" in src and '▶' in src, 'кнопка Старт')
check("event_panel:end" in src, 'кнопка Финиш')

print('== seed ==')
for p in __import__('pathlib').Path('data').glob('.event_mod_acl*'):
    p.unlink(missing_ok=True)
rep = apply_event_mod_acl_seed(force=True, guild_id=111222333444555666)
check(rep.get('applied') is True, f'seed applied: {rep}')
from services import permission_acl as pacl  # noqa: E402
cmd = pacl.load_acl(111222333444555666)
for rid in EVENT_STAFF_ROLE_IDS:
    check(str(rid) in [str(x) for x in cmd.get('event-panel', [])],
          f'staff {rid} в cmd_acl event-panel')

print('== panel cfg ==')
EP.save_panel_cfg(42, {'title': 'Тест', 'signups': ['1'], 'registration_open': True})
cfg = EP.load_panel_cfg(42)
check(cfg.get('title') == 'Тест' and cfg.get('signups') == ['1'],
      'save/load panel cfg')


class _Role:
    def __init__(self, rid):
        self.id = rid


class _Perms:
    manage_guild = False
    administrator = False


class _Member:
    def __init__(self, uid, roles=(), manage=False):
        self.id = uid
        self.roles = [_Role(r) for r in roles]
        self.guild_permissions = _Perms()
        if manage:
            self.guild_permissions.manage_guild = True


check(EP.is_event_mod(_Member(1, [EVENT_MOD_ROLE_ID])), 'роль event mod → True')
check(EP.is_event_mod(_Member(11, [EVENT_ADMIN_ROLE_ID])), 'роль event admin → True')
check(EP.is_event_mod(_Member(2, [], manage=True)), 'manage_guild → True')
check(not EP.is_event_mod(_Member(3, [999])), 'чужая роль → False')

print('== start / end phase ==')
cfg0 = {'title': 'Mafia', 'signups': ['1', '2'], 'registration_open': True, 'phase': 'open'}
live = EP.apply_start(cfg0, by_user_id=99)
check(live.get('phase') == 'live' and live.get('registration_open') is False
      and live.get('started_by') == '99', f'apply_start: {live}')
check(EP.normalize_phase(live) == 'live', 'normalize live')
ended = EP.apply_end(live, by_user_id=99)
check(ended.get('phase') == 'ended' and ended.get('live') is False, f'apply_end: {ended}')
check(EP.event_voice_channel_id() == 1550986919981351043
      or isinstance(EP.event_voice_channel_id(), int),
      f'voice id={EP.event_voice_channel_id()}')

print('== wiring ==')
policy = open(os.path.join(ROOT, 'cogs_policy.py'), encoding='utf-8').read()
check('event_panel.py' in policy and 'EVENT_LEAN_COGS' in policy,
      'LEAN грузит event_panel')
sb = open(os.path.join(ROOT, 'slash_budget.py'), encoding='utf-8').read()
check("'event-panel'" in sb, 'KEEP_SLASH содержит event-panel')
main = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
check('apply_event_mod_acl_seed' in main, 'on_ready зовёт event_mod seed')
menu = open(os.path.join(ROOT, 'services/panel_menu.py'), encoding='utf-8').read()
check("'/events'" in menu, 'меню панели: /events')
check(os.path.exists(os.path.join(ROOT, 'web/templates/events.html')),
      'шаблон events.html')
pages = open(os.path.join(ROOT, 'web/routes/pages.py'), encoding='utf-8').read()
check("'/events'" in pages, 'роут /events')
check("event-panel'" in open(
    os.path.join(ROOT, 'web/routes/guild_extra.py'), encoding='utf-8').read()
    or '/event-panel' in open(
        os.path.join(ROOT, 'web/routes/guild_extra.py'), encoding='utf-8').read(),
    'API /event-panel')
ev_html = open(os.path.join(ROOT, 'web/templates/events.html'), encoding='utf-8').read()
check('evKpis' in ev_html and 'ev-discord' in ev_html, 'events.html: KPI + Discord preview')
check('Старт' in ev_html, 'events.html: сценарий Старт')
check('ev-btn-go' in ev_html or 'pub-opt-accent' in ev_html, 'events.html: акцент Старт')
check('V2' in ev_html and 'pub-opt' in ev_html, 'events.html: V2 howto cards')
check('лобби `/mafia` из списка' not in ev_html and '_maybe_launch_mafia' not in open(
    os.path.join(ROOT, 'cogs/event_panel.py'), encoding='utf-8').read(),
    'event-panel больше не автозапускает мафию')
check('page-head-copy' in ev_html and 'eyebrow' in ev_html, 'events.html: page-head polish')
check('evPublish' in ev_html and 'evChannel' in ev_html, 'events.html: publish + channel select')
check('event_panel_channel' in open(
    os.path.join(ROOT, 'services/channel_routes.py'), encoding='utf-8').read(),
    'маршрут event_panel_channel')
check('set_target_channel_id' in open(
    os.path.join(ROOT, 'cogs/event_panel.py'), encoding='utf-8').read()
    and 'publish_event_panel' in open(
        os.path.join(ROOT, 'cogs/event_panel.py'), encoding='utf-8').read(),
    'target_channel + publish helpers')
check("/event-panel/publish" in open(
    os.path.join(ROOT, 'web/routes/guild_extra.py'), encoding='utf-8').read(),
    'API publish')

# target channel roundtrip
EP.set_target_channel_id(99, 555666777)
check(EP.target_channel_id(guild_id=99) == 555666777, 'set/get target_channel_id')
EP.set_target_channel_id(99, 0)
check(EP.target_channel_id(guild_id=99) == 0, 'clear target_channel_id')

# AST: persistent custom_id
src = open(os.path.join(ROOT, 'cogs/event_panel.py'), encoding='utf-8').read()
for cid in ('event_panel:signup', 'event_panel:announce',
            'event_panel:start', 'event_panel:close',
            'event_panel:list', 'event_panel:end'):
    check(cid in src, f'persistent button {cid}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
