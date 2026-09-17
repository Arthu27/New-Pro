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
    EVENT_MOD_ROLE_ID, apply_event_mod_acl_seed, SEED_VERSION)
from cogs import event_panel as EP  # noqa: E402

check(EVENT_MOD_ROLE_ID == 852634463535759461, 'EVENT_MOD_ROLE_ID')
check(EP.EVENT_MOD_ROLE_ID == EVENT_MOD_ROLE_ID, 'cog использует тот же id')
check(callable(EP.configured_panel_channel_id), 'configured_panel_channel_id')
check(callable(EP.resolve_panel_channel), 'resolve_panel_channel')
check('EVENT_PANEL_CHANNEL_ID' in open(
    os.path.join(ROOT, 'config.py'), encoding='utf-8').read(),
    'Config.EVENT_PANEL_CHANNEL_ID')
check("name='event-panel'" in open(
    os.path.join(ROOT, 'cogs/event_panel.py'), encoding='utf-8').read()
    and 'channel: discord.TextChannel' in open(
        os.path.join(ROOT, 'cogs/event_panel.py'), encoding='utf-8').read(),
    '/event-panel принимает channel')

print('== seed ==')
for p in __import__('pathlib').Path('data').glob('.event_mod_acl*'):
    p.unlink(missing_ok=True)
rep = apply_event_mod_acl_seed(force=True, guild_id=111222333444555666)
check(rep.get('applied') is True, f'seed applied: {rep}')
from services import permission_acl as pacl  # noqa: E402
cmd = pacl.load_acl(111222333444555666)
h = str(EVENT_MOD_ROLE_ID)
check(h in [str(x) for x in cmd.get('event-panel', [])],
      'event-mod в cmd_acl event-panel')

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
check(EP.is_event_mod(_Member(2, [], manage=True)), 'manage_guild → True')
check(not EP.is_event_mod(_Member(3, [999])), 'чужая роль → False')

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
check('page-head-copy' in ev_html and 'eyebrow' in ev_html, 'events.html: page-head polish')

# AST: persistent custom_id
src = open(os.path.join(ROOT, 'cogs/event_panel.py'), encoding='utf-8').read()
for cid in ('event_panel:signup', 'event_panel:announce',
            'event_panel:close', 'event_panel:list'):
    check(cid in src, f'persistent button {cid}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
