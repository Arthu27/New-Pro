# -*- coding: utf-8 -*-
"""Love Room bot: store / naming / ACL / wiring."""
from __future__ import annotations

import ast
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix='hakumo_love_room_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== module + config ==')
from services import love_room_store as S  # noqa: E402
from services import love_room_bot as LR  # noqa: E402

check(callable(LR.start_love_room_bot) and callable(LR.build_love_client),
      'start/build API')
check(LR.love_bot_token() == '', 'без env токен пуст')
check(LR.token_hint('abcdefghij') == '••••ghij', 'token hint last4')

cfg = S.load_love_room_cfg()
check(S.cfg_int(cfg, 'category_id') == 0, 'default category_id=0')
check(S.cfg_int(cfg, 'panel_channel_id') == 0, 'default panel_channel_id=0')
check(cfg.get('name_prefix') == 'love room', f'prefix={cfg.get("name_prefix")}')
check(isinstance(cfg.get('heart_emojis'), list) and len(cfg['heart_emojis']) >= 3,
      'heart pool')

os.environ['LOVE_ROOM_CATEGORY_ID'] = '123'
cfg2 = S.load_love_room_cfg()
check(S.cfg_int(cfg2, 'category_id') == 123, 'env overrides category')
os.environ.pop('LOVE_ROOM_CATEGORY_ID', None)

print('== naming + store ==')
name = S.room_name('love room', '💕')
check(name == 'love room 💕', f'name={name}')
check(S.is_love_room_name(name), 'is_love_room_name')
check(not S.is_love_room_name('General'), 'reject other names')

heart = S.pick_heart(set(), ['💕', '💖'])
check(heart == '💕', f'first free heart={heart}')
heart2 = S.pick_heart({'💕'}, ['💕', '💖'])
check(heart2 == '💖', f'skip used={heart2}')

gid = 793336829280780331
meta = S.register_room(gid, channel_id=111, name=name, users=[1, 2], created_by=9)
check(meta['channel_id'] == '111', 'register')
check(S.find_room_for_user(gid, 1) is not None, 'find by user')
check(S.find_room_by_channel(gid, 111) is not None, 'find by channel')
check(S.pair_key(2, 1) == '1:2', 'pair key sorted')
check(S.try_acquire_pair_lock(1, 2), 'pair lock acquire')
check(not S.try_acquire_pair_lock(2, 1), 'pair lock blocks')
S.release_pair_lock(1, 2)
check(S.try_acquire_pair_lock(1, 2), 'pair lock release')
S.release_pair_lock(1, 2)

check(S.should_delete_empty(0), 'empty → delete')
check(not S.should_delete_empty(1), 'one human → keep')
check(S.unregister_room(gid, 111), 'unregister')

S.set_cooldown(gid, 42, sec=5)
left = S.cooldown_remaining(gid, 42)
check(left > 0, f'cooldown left={left:.2f}')

print('== ACL ==')


class _Perms:
    administrator = False
    manage_guild = False


class _Role:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name


class _Member:
    def __init__(self, roles=None, admin=False):
        self.roles = roles or []
        self.guild_permissions = _Perms()
        self.guild_permissions.administrator = admin
        self.guild = None


os.environ['VEDUSHIY_ROLE_ID'] = '999001'
m_host = _Member(roles=[_Role(999001, 'Ведущий')])
check(S.member_has_host_acl(m_host), 'host by role id')
m_name = _Member(roles=[_Role(1, 'ведущий')])
check(S.member_has_host_acl(m_name), 'host by name alias')
m_admin = _Member(admin=True)
check(S.member_has_host_acl(m_admin), 'admin allowed')
m_user = _Member(roles=[_Role(2, 'Member')])
check(not S.member_has_host_acl(m_user), 'plain member denied')
os.environ.pop('VEDUSHIY_ROLE_ID', None)

print('== stickers + files ==')
for key in ('love_enter', 'love_pair', 'love_room', 'love_raise',
            'love_lower', 'love_close', 'love_heart'):
    path = os.path.join(ROOT, 'assets', 'stickers', f'{key}.png')
    check(os.path.isfile(path) and os.path.getsize(path) > 100,
          f'sticker {key}.png')

cfg_path = os.path.join(ROOT, 'config', 'love_room.json')
check(os.path.isfile(cfg_path), 'config/love_room.json')
svc = os.path.join(ROOT, 'deploy', 'hakumo-love-room.service')
check(os.path.isfile(svc), 'systemd unit')
runner = os.path.join(ROOT, 'scripts', 'run_love_room.py')
check(os.path.isfile(runner), 'run_love_room.py')

print('== .env.example + main wiring ==')
ex = open(os.path.join(ROOT, '.env.example'), encoding='utf-8').read()
for key in ('LOVE_ROOM_BOT_TOKEN', 'LOVE_ROOM_STANDALONE', 'VEDUSHIY_ROLE_ID',
            'LOVE_ROOM_CATEGORY_ID', 'LOVE_ROOM_HOST_ROLE_IDS'):
    check(key in ex, f'.env.example has {key}')
main = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
check('start_love_room_bot' in main and 'LOVE_ROOM_STANDALONE' in main,
      'main.py wires love room')

print('== no hardcoded LOVE_ROOM_BOT_TOKEN ==')
import re  # noqa: E402
bad = []
pat = re.compile(r'LOVE_ROOM_BOT_TOKEN\s*=\s*[\'\"][^\'\"]{20,}')
for root, dirs, files in os.walk(os.path.join(ROOT, 'services')):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for fn in files:
        if not fn.endswith('.py'):
            continue
        path = os.path.join(root, fn)
        if pat.search(open(path, encoding='utf-8').read()):
            bad.append(path)
for path in (os.path.join(ROOT, 'main.py'),
             os.path.join(ROOT, 'cogs', 'love_room.py'),
             os.path.join(ROOT, 'scripts', 'run_love_room.py')):
    if os.path.isfile(path) and pat.search(open(path, encoding='utf-8').read()):
        bad.append(path)
check(not bad, 'токен только из env' if not bad else f'leak in {bad}')

print('== build client ==')
os.environ.pop('LOVE_ROOM_BOT_TOKEN', None)
client = LR.build_love_client()
check(client is not None and hasattr(client, 'start'), 'Bot собран')
check(hasattr(client, 'tree') and hasattr(client, 'add_cog'),
      'CommandTree + add_cog')
ints = client.intents
check(bool(ints.guilds) and bool(ints.voice_states),
      'intents guilds+voice')
check(not bool(getattr(ints, 'members', False)), 'без privileged members')
check(not bool(getattr(ints, 'message_content', False)),
      'без message_content')
st = LR.love_bot_status()
check(st.get('sits_in_voice') is False, 'не сидит в love rooms')
check(st.get('token_set') is False, 'token_set false без env')

print('== ui module ==')
from services import love_room_ui as UI  # noqa: E402
body = UI.panel_body_md(room_count=0, category_ok=False)
check('love room' in body.lower() and 'Ведущий' in body, 'panel body')
emb = UI.panel_embed(body=body, room_count=0)
check(emb.title == 'Love Room', 'embed title')

print('== menu_emojis love keys ==')
from services import menu_emojis as ME  # noqa: E402
check(hasattr(ME, 'LOVE_STICKER_KEYS') and 'love_enter' in ME.LOVE_STICKER_KEYS,
      'LOVE_STICKER_KEYS')
check(callable(ME.ensure_love_room_emojis) and callable(ME.emoji_for_love),
      'love emoji API')
# love keys must NOT be in main STICKER_KEYS (upload only on love bot)
check('love_enter' not in ME.STICKER_KEYS, 'love_* not on main STICKER_KEYS')

print(f'\n== RESULT: {PASS} passed, {FAIL} failed ==')
sys.exit(1 if FAIL else 0)
