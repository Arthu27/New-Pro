# -*- coding: utf-8 -*-
"""Support /verify: config, store, resolve, stickers."""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_support_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['SUPPORT_DATA_DIR'] = os.path.join(_TMP, 'data')

from services import support_bot_config as CFG  # noqa
from services import support_store as STORE  # noqa
from services import support_emojis as EMO  # noqa
from cogs import support_verify as SV  # noqa

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== config ==')
cfg = CFG.load_config()
check(CFG.gid(cfg) == 793336829280780331, 'guild id')
check(CFG.role_id(cfg, 'support_role_id') == 1553138713532563516, 'support role')
check(CFG.role_id(cfg, 'support_lead_role_id') == 1553139245735219390, 'lead role')
check(CFG.role_id(cfg, 'male_role_id') == 804361264641474602, 'male=cat')
check(CFG.role_id(cfg, 'female_role_id') == 804361268017627156, 'female=kitty')

print('== store ==')
r = STORE.add_review(guild_id=1, user_id=2, support_id=3, text='топ саппорт')
check(r.get('id') and r['text'] == 'топ саппорт', 'review saved')
a = STORE.add_appeal(guild_id=1, user_id=2, support_id=3, reason='несправедливо')
check(a.get('status') == 'pending', 'appeal pending')
STORE.set_appeal_status(a['id'], 'approved', reviewer_id=9)
check(STORE.get_appeal(a['id'])['status'] == 'approved', 'appeal approved')

print('== emojis / stickers ==')
for key in ('s_verify', 's_deny', 's_male', 's_female', 's_gender'):
    check(EMO.sticker_path(key) is not None, f'sticker file {key}')
check(isinstance(EMO.emoji_for('s_verify'), str), 'unicode fallback')

print('== resolve helpers ==')
class R:
    def __init__(self, i): self.id = i
class M:
    def __init__(self, i, roles=()):
        self.id = i
        self.roles = [R(x) for x in roles]
        self.bot = False
        self.guild_permissions = type('P', (), {'administrator': False})()
cfg2 = dict(cfg)
check(SV._is_verified(M(1, [804361264641474602]), cfg2) is True, 'verified male')
check(SV._is_verified(M(1, []), cfg2) is False, 'not verified')
check(SV._current_gender(M(1, [804361268017627156]), cfg2) == 'female', 'gender female')
check(SV._has_support(M(1, [1553138713532563516]), cfg2) is True, 'has support')
check(SV._has_support(M(1, []), cfg2) is False, 'no support')

print('== runner / service ==')
runner = open(os.path.join(ROOT, 'scripts/run_support_bot.py'), encoding='utf-8').read()
check('SUPPORT_BOT_TOKEN' in runner and 'bot.start(token)' in runner, 'runner uses env token')
check('MTU1MzE3' not in runner, 'no hard-coded token in runner')
svc = open(os.path.join(ROOT, 'deploy/hakumo-support.service'), encoding='utf-8').read()
check('run_support_bot.py' in svc, 'systemd unit')

print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
