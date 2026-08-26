# -*- coding: utf-8 -*-
"""Тесты cogs/karma.py — начисление, кулдаун пар, топ, журнал.

Запуск: python3 tests/test_karma.py
"""
import ast
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_karma_test_')
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
from cogs import karma as km  # noqa: E402
from db import GuildData  # noqa: E402

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)

print('== 1. apply_rep / top / score ==')
st = km.empty_state()
check(km.apply_rep(st, 5) == 1 and km.apply_rep(st, 5) == 2,
      'очки накапливаются')
km.apply_rep(st, 7); km.apply_rep(st, 9); km.apply_rep(st, 9); km.apply_rep(st, 9)
rows = km.top_rows(st)
check(rows[0] == (9, 3) and rows[1] == (5, 2) and rows[2] == (7, 1),
      f'топ по убыванию: {rows}')
check(km.get_score(st, 5) == 2 and km.get_score(st, 999) == 0, 'get_score')
check(km.top_rows(None) == [], 'пустое состояние -> пустой топ')

print('== 2. thank: кулдаун на пару и анти-накрутка ==')
st = km.empty_state()
st, ok, total = km.thank(st, 1, 2, NOW, 'помог с ролью')
check(ok and total == 1, 'первое спасибо прошло')
st, ok, left = km.thank(st, 1, 2, NOW + timedelta(seconds=30))
check(not ok and left == 30, f'кулдаун 60с: через 30с отказ (осталось {left})')
st, ok, total = km.thank(st, 1, 3, NOW + timedelta(seconds=30))
check(ok, 'кулдаун — на пару, другому сказать можно')
st, ok, _ = km.thank(st, 2, 2, NOW)
check(not ok, 'себе спасибо нельзя')
st, ok, total = km.thank(st, 1, 2, NOW + timedelta(seconds=61))
check(ok and total == 2, 'после кулдауна снова можно')
check(len(st['thanks']) == 3, 'журнал благодарностей ведётся (отказы не пишутся)')

# битая запись в журнале не роняет кулдаун
st['thanks'].append({'giver': 1, 'target': 2, 'at': 'билайн', 'reason': ''})
st, ok, _ = km.thank(st, 1, 2, NOW + timedelta(days=1))
check(ok, 'мусорная метка в журнале переживается')

# хвост журнала ограничен 200 записями
st2 = km.empty_state()
for i in range(300):
    st2['thanks'].append({'giver': 1, 'target': i + 100, 'at': NOW.isoformat(),
                          'reason': ''})
st2, ok, _ = km.thank(st2, 1, 5, NOW)
check(len(st2['thanks']) <= 200, f'журнал не раздувается ({len(st2["thanks"])})')

print('== 3. naive-метка в журнале ==')
st3 = km.empty_state()
st3['thanks'] = [{'giver': 1, 'target': 2,
                  'at': NOW.replace(tzinfo=None).isoformat(), 'reason': ''}]
st3, ok, left = km.thank(st3, 1, 2, NOW + timedelta(seconds=10))
check(not ok and left == 50, 'naive метка трактуется как UTC, кулдаун честный')

print('== 4. хранилище ==')
db = GuildData('karma')
db.set(4242, 'state', st)
back = db.get(4242, 'state', km.empty_state())
check(km.get_score(back, 2) == 3, 'карма переживает roundtrip')

print('== 5. линт ==')
src = open(os.path.join(ROOT, 'cogs', 'karma.py'), encoding='utf-8').read()
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
