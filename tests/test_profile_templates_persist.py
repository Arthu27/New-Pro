# -*- coding: utf-8 -*-
"""profile_templates: persist вне git, без перезаписи + публичный /profiles."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== persist seed / no overwrite ==')
td = Path(tempfile.mkdtemp(prefix='hakumo_prof_'))
seed = td / 'seed'
persist = td / 'persist'
pin = td / 'pin'
seed.mkdir()
png = b'\x89PNG\r\n\x1a\n' + b'SEED'
(seed / 'index.html').write_text(
    '<html><body><a href="profile-card.png">profile-card.png</a>'
    '<a href="most-active.png">most-active.png</a>'
    '<a href="couple-card.png">couple-card.png</a></body></html>',
    encoding='utf-8',
)
for name in ('profile-card.png', 'most-active.png', 'couple-card.png'):
    (seed / name).write_bytes(png + name.encode())

os.environ['PROFILES_DIR'] = str(persist)
os.environ['PROFILES_PIN_DIR'] = str(pin)
import services.profile_templates as PT
PT.static_seed_dir = lambda: seed  # type: ignore
PT.persist_dir = lambda: persist  # type: ignore
PT.pin_dir = lambda: pin  # type: ignore

d1 = PT.ensure_profile_templates(overwrite=False)
check(d1 == persist, 'returns persist dir')
check((persist / 'couple-card.png').read_bytes().endswith(b'couple-card.png'), 'seeded couple')
check((persist / 'profile-card.png').is_file(), 'seeded profile-card')
check((persist / 'most-active.png').is_file(), 'seeded most-active')
check((pin / 'couple-card.png').is_file(), 'mirrored to pin')
check((pin / 'profile-card.png').is_file(), 'pin has profile-card')

(seed / 'couple-card.png').write_bytes(b'NEW-VERSION')
PT.ensure_profile_templates(overwrite=False)
check((persist / 'couple-card.png').read_bytes().endswith(b'couple-card.png'),
      'second ensure does not overwrite')

(persist / 'most-active.png').unlink()
(seed / 'most-active.png').write_bytes(b'SEED-most-active.png-CHANGED')
PT.ensure_profile_templates(overwrite=False)
check((persist / 'most-active.png').is_file(), 'refilled missing only')
check((persist / 'most-active.png').read_bytes().endswith(b'most-active.png'),
      'refilled from pin (original), not a newer seed')
check((persist / 'couple-card.png').read_bytes().endswith(b'couple-card.png'),
      'existing still intact after refill')

(persist / 'profile-card.png').unlink()
(seed / 'profile-card.png').unlink()
PT.ensure_profile_templates(overwrite=False)
check((persist / 'profile-card.png').is_file(), 'restored from pin when seed gone')

print('== public routes, no login ==')
app_src = (ROOT / 'web' / 'app.py').read_text(encoding='utf-8')
check("@app.route('/profiles')" in app_src, 'route /profiles')
check('def profiles_file' in app_src and 'def profiles_gallery' in app_src,
      'gallery + file handlers')
check('ensure_profile_templates' in app_src, 'ensure on app load')
check('login_required' not in app_src.split('def profiles_gallery')[1].split('def profiles_file')[0],
      'gallery is not behind login')

from web.app import app
app.config['TESTING'] = True
client = app.test_client()
for name in ('profile-card.png', 'most-active.png', 'couple-card.png'):
    resp = client.get('/profiles/' + name)
    check(resp.status_code == 200, f'GET /profiles/{name}', str(resp.status_code))
    check(resp.mimetype == 'image/png', f'{name} is png', resp.mimetype)
    check('login' not in (resp.headers.get('Location') or ''), f'{name} not redirected')
    check('Content-Disposition' not in resp.headers, f'{name} is not a download')
    check(resp.headers.get('Access-Control-Allow-Origin') == '*', f'{name} is embeddable')
gallery = client.get('/profiles/')
check(gallery.status_code == 200, 'gallery 200', str(gallery.status_code))
body = gallery.get_data(as_text=True)
check('profile-card.png' in body and 'couple-card.png' in body and 'most-active.png' in body,
      'gallery lists all three')
missing = client.get('/profiles/nope.png')
check(missing.status_code == 404, 'unknown name stays 404', str(missing.status_code))

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
