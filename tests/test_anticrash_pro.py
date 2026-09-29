# -*- coding: utf-8 -*-
"""Anti-crash PRO: arm preset, restore flags, role health helper."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(ok, msg, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {detail}')


print('== guardian_arm_pro ==')
from cogs import guardian as G  # noqa: E402

armed = G.guardian_arm_pro({}, owner_id=840162887288619039)
check(armed['enabled'] is True, 'щит включён')
check(armed['kick_unauthorized_bots'] is True, 'кик чужих ботов')
check(armed.get('restore_channels') is True, 'restore каналов')
check(armed.get('reverse_bans') is True, 'откат банов')
check(armed['bot_action'] == 'ban', 'ботам — ban')
check('840162887288619039' in armed['whitelist_users'], 'owner в whitelist')
for key in ('channel_delete', 'role_delete', 'dangerous_perms', 'bot_add',
            'member_ban', 'webhook_create'):
    ev = armed['events'][key]
    check(ev['enabled'] is True, f'event {key} on')
check(armed['events']['role_delete']['threshold'] == 1, 'role_delete порог 1')
check(armed['events']['channel_delete']['threshold'] == 2, 'channel_delete порог 2')

print('== protection.arm_all ==')
from web import protection as P  # noqa: E402
# use fake gid 0 — no disk write for guardian save with gid 0? save_guardian skips?
# arm_all with gid=0 still mutates in-memory paths carefully
snap = P.arm_all_protections(0, None, owner_id=1)
check(snap['flags']['guardian'] or snap['guardian']['enabled'],
      'snapshot guardian on', snap['flags'])
check(snap['antiraid'].get('join_raid') is True, 'antiraid join_raid')
check(snap['antiraid'].get('raid_action') == 'kick', 'antiraid kick')
check(snap['security'].get('link_scanner') is True, 'security link')

print('== panel wiring ==')
html = open(os.path.join(ROOT, 'web/templates/anticrash.html'), encoding='utf-8').read()
app = open(os.path.join(ROOT, 'web/app.py'), encoding='utf-8').read()
check('arm_max' in html and 'Включить максимум PRO' in html, 'кнопка PRO')
check("action == 'arm_max'" in app, 'POST arm_max')
check('bot_role_health' in open(os.path.join(ROOT, 'cogs/guardian.py'),
                                encoding='utf-8').read(), 'role health')
check('_restore_channel' in open(os.path.join(ROOT, 'cogs/guardian.py'),
                                 encoding='utf-8').read(), 'channel restore')
check('_apply_raid_action' in open(os.path.join(ROOT, 'cogs/antiraid.py'),
                                   encoding='utf-8').read(), 'antiraid real action')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
