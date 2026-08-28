# -*- coding: utf-8 -*-
"""Тесты cogs/night_mode.py — ночное окно, настройки, план каналов.

Запуск: python3 tests/test_night_mode.py
"""
import ast
import os
import sys
import tempfile
from datetime import datetime, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_night_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')

PASS = 0
FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


UTC = timezone.utc
from cogs import night_mode as nm  # noqa: E402
from db import GuildData  # noqa: E402


def at(hour):
    return datetime(2026, 8, 13, hour, 30, tzinfo=UTC)


print('== 1. is_night: окна через полночь и внутри суток ==')
check(nm.is_night(at(23), 23, 7) and nm.is_night(at(3), 23, 7)
      and not nm.is_night(at(12), 23, 7), '23–7: ночь в 23:30 и 3:30, день в 12:30')
check(not nm.is_night(at(22), 23, 7) and not nm.is_night(at(7), 23, 7),
      'границы: 22 — ещё день, 7 — уже утро (полуинтервал)')
check(nm.is_night(at(10), 8, 20) and not nm.is_night(at(21), 8, 20),
      'дневное окно 8–20 тоже работает')
check(not nm.is_night(at(12), 0, 0), 'start == end -> окно пустое')
check(nm.is_night(at(0), 23, 7), 'полночь внутри 23–7')
check(nm.is_night('2026-08-13T02:15:00+00:00', 23, 7), 'ISO-строка на входе')

print('== 2. merge_settings ==')
s = nm.merge_settings({'enabled': True, 'start_hour': 24, 'end_hour': 'утро',
                       'slowmode_seconds': 999999})
check(s['enabled'] is True, 'enabled сохраняется')
check(s['start_hour'] == 0 and s['end_hour'] == 7, 'битые часы -> дефолт/модуль 24')
check(s['slowmode_seconds'] == 21600, 'слоумод зажат в дискордовый максимум 21600')
s = nm.merge_settings({'exempt_channels': 'да канал'})
check(s['exempt_channels'] == [], 'битый список исключений -> пустой')
check(nm.merge_settings(None) == nm.DEFAULT_SETTINGS, 'None -> дефолт')

print('== 3. окно/строки статуса ==')
check(nm.window_text({'start_hour': 23, 'end_hour': 7}) == '23:00–07:00 UTC',
      'окно человеческим текстом')
lines = nm.plan_settings_lines({'enabled': True, 'start_hour': 22, 'end_hour': 6,
                                'slowmode_seconds': 5, 'lock_channels': True,
                                'exempt_channels': [1, 2]})
check('включён' in lines[0] and '22:00–06:00' in lines[1] and '5 секунд' in lines[2],
      f'строки статуса: {lines[:3]}')
check('да' in lines[3] and '2 канала' in lines[4], 'лок и исключения по-русски')

print('== 4. channels_for_action: исключения ==')


class FakeChannel:
    def __init__(self, cid):
        self.id = cid


class FakeGuild:
    text_channels = [FakeChannel(10), FakeChannel(11), FakeChannel(12)]


got = nm.channels_for_action(FakeGuild(), {'exempt_channels': [11]})
check([c.id for c in got] == [10, 12], 'исключённый канал не попадает в план')
got = nm.channels_for_action(FakeGuild(), None)
check(len(got) == 3, 'без исключений — все текстовые')

print('== 5. состояние и хранилище ==')
check(nm.empty_state() == {'active': False, 'slow_before': {}, 'lock_before': {},
                           'since': None}, 'empty_state стабильно')
db = GuildData('night_mode')
db.set(4242, 'settings', {'enabled': True, 'start_hour': 22})
db.set(4242, 'state', {'active': True, 'slow_before': {'10': 0}, 'lock_before': {},
                       'since': '2026-08-13T00:00:00+00:00'})
back_s = nm.merge_settings(db.get(4242, 'settings', {}))
back_st = db.get(4242, 'state', nm.empty_state())
check(back_s['enabled'] is True and back_s['start_hour'] == 22,
      'настройки переживают roundtrip')
check(back_st['active'] is True and back_st['slow_before']['10'] == 0,
      'состояние (до-значения слоумода) переживает roundtrip')

print('== 6. линт модуля ==')
src = open(os.path.join(ROOT, 'cogs', 'night_mode.py'), encoding='utf-8').read()
tree = ast.parse(src)
silent = [n.lineno for n in ast.walk(tree)
          if isinstance(n, ast.ExceptHandler)
          and len([b for b in n.body if not (isinstance(b, ast.Expr)
                   and isinstance(b.value, ast.Constant))]) == 1
          and isinstance([b for b in n.body if not (isinstance(b, ast.Expr)
                          and isinstance(b.value, ast.Constant))][0],
                         (ast.Pass, ast.Continue))]
check(not silent, f'ни одного молчаливого except {silent or "ок"}')
check('utcnow' not in src, 'utcnow() не используется')

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
