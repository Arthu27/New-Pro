# -*- coding: utf-8 -*-
"""Автобан по имени АртемаВавилова / ArtemaVavilova."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.name_autoban import is_banned_name, member_banned_identity, normalize_name

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== normalize / match ==')
check(normalize_name('АртемаВавилова') == 'артемававилова', 'ru exact')
check(normalize_name('Артема Вавилова') == 'артемававилова', 'ru spaced')
check(normalize_name('артема_вавилова') == 'артемававилова', 'ru underscore')
check(is_banned_name('АртемаВавилова'), 'ban RU exact')
check(is_banned_name('артемававилова'), 'ban RU casefold')
check(is_banned_name('ArtemaVavilova'), 'ban EN Artema')
check(is_banned_name('ArtyomaVavilova'), 'ban EN Artyoma')
check(is_banned_name('Artema Vavilova'), 'ban EN spaced')
check(is_banned_name('artema.vavilova'), 'ban EN dotted')
check(not is_banned_name('Discipline'), 'safe other name')
check(not is_banned_name('Вавилов'), 'partial not enough')
check(not is_banned_name('Artema'), 'partial EN not enough')

print('== member identity ==')


class _M:
    def __init__(self, **kw):
        self.nick = kw.get('nick')
        self.display_name = kw.get('display_name') or kw.get('nick') or kw.get('name')
        self.global_name = kw.get('global_name')
        self.name = kw.get('name')
        self.id = 1
        self.bot = False


check(member_banned_identity(_M(name='АртемаВавилова')) == 'АртемаВавилова',
      'member name hit')
check(member_banned_identity(_M(nick='ArtemaVavilova', name='x')) == 'ArtemaVavilova',
      'member nick hit')
check(member_banned_identity(_M(name='ok', nick='ok')) is None, 'clean member')

print('== modpanel banner_url kw ==')
import inspect
from services.v2_layouts import build_modpanel_items
sig = inspect.signature(build_modpanel_items)
check('banner_url' in sig.parameters, 'banner_url accepted')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
