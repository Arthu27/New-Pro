# -*- coding: utf-8 -*-
"""Тесты cogs/staff_rating.py — голосование, замена голоса, средний балл, топ.

Запуск: python3 tests/test_staff_rating.py
"""
import ast
import os
import sys
import tempfile
from datetime import datetime, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_staff_test_')
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
from cogs import staff_rating as sr  # noqa: E402
from db import GuildData  # noqa: E402

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)

print('== 1. add_vote: валидация ==')
st = sr.empty_state()
res, v = sr.add_vote(st, 1, 77, 5, 'отличная работа', NOW)
check(res == 'ok' and v == 5.0, 'первый голос: ok, средний = 5.0')
res, v = sr.add_vote(st, 1, 77, 3, '', NOW)
check(res == 'updated' and v == 3.0, 'переголосование заменяет, не суммирует')
res, v = sr.add_vote(st, 2, 77, 4, 'норм', NOW)
check(res == 'ok' and v == 3.5, f'среднее 3 и 4 -> 3.5, got {v}')
res, v = sr.add_vote(st, 77, 77, 5, '', NOW)
check(res == 'self', 'себя оценить нельзя')
res, v = sr.add_vote(st, 3, 77, 6, '', NOW)
check(res == 'bad_score', '6 из 5 — в отказ')
res, v = sr.add_vote(st, 3, 77, 'много', '', NOW)
check(res == 'bad_score', 'не число — в отказ')
res, v = sr.add_vote(st, 3, 77, 0, '', NOW)
check(res == 'bad_score', '0 — в отказ')

print('== 2. summary / rating_rows / звёзды ==')
s = sr.staff_summary(st, 77)
check(s['avg'] == 3.5 and s['votes'] == 2, 'сводка зачётки')
check(len(s['comments']) == 2, 'комментарии хранятся (голос без коммента не пишется)')
check(sr.staff_summary(st, 999) is None, 'без голосов -> None')
check(sr.staff_summary(None, 77) is None, 'пустое состояние -> None')

sr.add_vote(st, 1, 88, 5, '', NOW)
sr.add_vote(st, 2, 88, 5, 'пушка', NOW)
sr.add_vote(st, 3, 88, 4, '', NOW)
rows = sr.rating_rows(st)
check(rows[0] == (88, 4.67, 3) and rows[1] == (77, 3.5, 2),
      f'топ по баллу и числу голосов: {rows}')

check(sr.score_stars(5) == '★★★★★' and sr.score_stars(3) == '★★★☆☆'
      and sr.score_stars(0) == '☆☆☆☆☆', 'шкала звёзд')
check(sr.score_stars(4.5) == '★★★★★', '4.5 округляется к 5')
check(sr.score_stars('билайн') == '☆☆☆☆☆', 'мусор -> пустая шкала')

print('== 3. лимит комментариев ==')
st2 = sr.empty_state()
for i in range(50):
    sr.add_vote(st2, i + 100, 77, 5, f'комментарий {i}', NOW)
check(len(st2['staff']['77']['comments']) == sr.COMMENTS_KEEP,
      f'храним последние {sr.COMMENTS_KEEP} комментариев')
check(st2['staff']['77']['comments'][-1]['text'] == 'комментарий 49',
      'самый свежий — последний')

print('== 4. хранилище ==')
db = GuildData('staff_rating')
db.set(4242, 'state', st)
back = db.get(4242, 'state', sr.empty_state())
check(sr.staff_summary(back, 88)['avg'] == 4.67, 'рейтинг переживает roundtrip')

print('== 5. линт ==')
src = open(os.path.join(ROOT, 'cogs', 'staff_rating.py'), encoding='utf-8').read()
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
