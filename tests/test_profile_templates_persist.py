# -*- coding: utf-8 -*-
"""profile_templates: persist вне git, без перезаписи."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== persist seed / no overwrite ==')
td = Path(tempfile.mkdtemp(prefix='hakumo_prof_'))
seed = td / 'seed'
persist = td / 'persist'
seed.mkdir()
# minimal fake assets
for name in ('index.html', 'profile-card.png', 'most-active.png', 'couple-card.png'):
    (seed / name).write_bytes(b'SEED-' + name.encode())

os.environ['PROFILES_DIR'] = str(persist)
# point seed via monkeypatch
import services.profile_templates as PT
PT.static_seed_dir = lambda: seed  # type: ignore
PT.persist_dir = lambda: persist  # type: ignore

d1 = PT.ensure_profile_templates(overwrite=False)
check(d1 == persist, 'returns persist dir')
check((persist / 'couple-card.png').read_bytes().startswith(b'SEED-'), 'seeded couple')

# change seed — must NOT overwrite persist
(seed / 'couple-card.png').write_bytes(b'NEW-VERSION')
PT.ensure_profile_templates(overwrite=False)
check((persist / 'couple-card.png').read_bytes().startswith(b'SEED-'),
      'second ensure does not overwrite')

# missing file in persist gets filled, existing kept
(persist / 'most-active.png').unlink()
(seed / 'most-active.png').write_bytes(b'SEED-most-active.png')
PT.ensure_profile_templates(overwrite=False)
check((persist / 'most-active.png').is_file(), 'refilled missing only')
check((persist / 'couple-card.png').read_bytes().startswith(b'SEED-'),
      'existing still intact after refill')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
