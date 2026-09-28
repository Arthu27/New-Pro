# -*- coding: utf-8 -*-
"""profile_templates: persist вне git, без перезаписи + HTTP /profiles."""
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
for name in ('index.html', 'profile-card.png', 'most-active.png', 'couple-card.png'):
    (seed / name).write_bytes(b'SEED-' + name.encode())

os.environ['PROFILES_DIR'] = str(persist)
os.environ['PROFILES_PIN_DIR'] = str(pin)
import services.profile_templates as PT
PT.static_seed_dir = lambda: seed  # type: ignore
PT.persist_dir = lambda: persist  # type: ignore
PT.pin_dir = lambda: pin  # type: ignore

d1 = PT.ensure_profile_templates(overwrite=False)
check(d1 == persist, 'returns persist dir')
check((persist / 'couple-card.png').read_bytes().startswith(b'SEED-'), 'seeded couple')
check((persist / 'profile-card.png').is_file(), 'seeded profile-card')
check((persist / 'most-active.png').is_file(), 'seeded most-active')
check((pin / 'couple-card.png').is_file(), 'mirrored to pin')
check((pin / 'profile-card.png').is_file(), 'pin has profile-card')

(seed / 'couple-card.png').write_bytes(b'NEW-VERSION')
PT.ensure_profile_templates(overwrite=False)
check((persist / 'couple-card.png').read_bytes().startswith(b'SEED-'),
      'second ensure does not overwrite')

(persist / 'most-active.png').unlink()
(seed / 'most-active.png').write_bytes(b'SEED-most-active.png')
# pin still has old most-active — refill from pin first (не из seed)
PT.ensure_profile_templates(overwrite=False)
check((persist / 'most-active.png').is_file(), 'refilled missing only')
check((persist / 'most-active.png').read_bytes().startswith(b'SEED-'),
      'refilled from pin (original seed)')
check((persist / 'couple-card.png').read_bytes().startswith(b'SEED-'),
      'existing still intact after refill')

# Если и persist, и seed пусты — восстанавливаем только из pin
(persist / 'profile-card.png').unlink()
(seed / 'profile-card.png').unlink()
PT.ensure_profile_templates(overwrite=False)
check((persist / 'profile-card.png').is_file(), 'restored from pin when seed gone')

print('== routes in app.py ==')
app_src = (ROOT / 'web' / 'app.py').read_text(encoding='utf-8')
check("@app .route ('/profiles')" in app_src or "@app.route('/profiles')" in app_src,
      'route /profiles')
check('profiles_file' in app_src and 'profiles_gallery' in app_src,
      'gallery + file handlers')
check('ensure_profile_templates' in app_src, 'ensure on app load')
check((ROOT / 'web' / 'static' / 'profiles' / 'profile-card.png').is_file(),
      'seed profile-card.png in static')
check((ROOT / 'web' / 'static' / 'profiles' / 'most-active.png').is_file(),
      'seed most-active.png in static')
check((ROOT / 'web' / 'static' / 'profiles' / 'couple-card.png').is_file(),
      'seed couple-card.png in static')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
