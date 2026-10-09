# -*- coding: utf-8 -*-
"""Селфи-канал: медиа → роль."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== selfie_role ==')
spec = importlib.util.spec_from_file_location(
    'selfie_role', ROOT / 'cogs' / 'selfie_role.py')
mod = importlib.util.module_from_spec(spec)
# config/discord may load — avoid full setup
import types
import sys

# stub discord/config if needed for import
class _Att:
    def __init__(self, content_type='', filename=''):
        self.content_type = content_type
        self.filename = filename


# Load source as text checks + exec media helpers only
src = (ROOT / 'cogs' / 'selfie_role.py').read_text(encoding='utf-8')
cfg = (ROOT / 'config.py').read_text(encoding='utf-8')
soft = (ROOT / 'web' / 'static' / 'panel-soft.js').read_text(encoding='utf-8')
app = (ROOT / 'web' / 'app.py').read_text(encoding='utf-8')

check('class SelfieRole' in src and 'on_message' in src, 'cog listener')
check('backfill' in src and 'channel.history' in src, 'history backfill')
check('1312434029278134294' in cfg and '920462510769975306' in cfg,
      'default channel/role IDs in Config')
check('SELFIE_CHANNEL_ID' in cfg and 'SELFIE_ROLE_ID' in cfg, 'Config fields')
check('HEAVY' in soft and 'lightPrefetch' in soft, 'soft-nav throttled')
check("PC.set(cache_key, out, ttl=30.0)" in app or "cases:" in app,
      'cases cache')
check("users_dir:" in app and "namebook:" in app, 'directory/namebook cache')

# media helper without importing discord bot stack
ns = {}
exec(
    'IMAGE_EXTS = ' + src.split('IMAGE_EXTS = ', 1)[1].split('\nVIDEO_EXTS', 1)[0]
    + '\nVIDEO_EXTS = ' + src.split('VIDEO_EXTS = ', 1)[1].split('\n\n', 1)[0]
    + '\n' + src[src.index('def is_media_attachment'):src.index('def message_has_media')],
    ns, ns,
)
check(ns['is_media_attachment'](_Att('image/png', 'a.png')), 'image ct')
check(ns['is_media_attachment'](_Att('video/mp4', 'a.mp4')), 'video ct')
check(ns['is_media_attachment'](_Att('', 'clip.mov')), 'video ext')
check(not ns['is_media_attachment'](_Att('application/pdf', 'a.pdf')), 'skip pdf')

print(f'\n{PASS} passed, {FAIL} failed')
raise SystemExit(1 if FAIL else 0)
