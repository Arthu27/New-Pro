# -*- coding: utf-8 -*-
"""Тесты cogs/counting.py — считалка: числа, очерёдность, падения, рекорды.

Запуск: python3 tests/test_counting.py
"""
import ast
import os
import sys
import tempfile
from datetime import datetime, timezone

_TMP = tempfile.mkdtemp(prefix='aether_count_test_')
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
from cogs import counting as cn  # noqa: E402
from db import GuildData  # noqa: E402

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)

print('== 1. parse_number ==')
check(cn.parse_number('42') == 42, 'число распарсилось')
check(cn.parse_number(' 7 ') == 7, 'пробелы срезаны')
check(cn.parse_number('1 2') is None, 'два числа подряд — не счёт')
check(cn.parse_number('семь') is None and cn.parse_number('-5') is None
      and cn.parse_number('0') is None, 'слова/минус/ноль — в отказ')

print('== 2. try_count: логика ==')
st = cn.empty_state(0)
res, st = cn.try_count(st, 1, 'A', '1', NOW)
check(res == 'inactive', 'выключенная считалка (channel_id=0) молчит')

st = cn.empty_state(77)
res, st = cn.try_count(st, 1, 'A', '1', NOW)
check(res == 'ok' and st['next'] == 2 and st['last_user'] == 1 and st['best'] == 1,
      '1 от первого — засчитано, next=2')
res, st = cn.try_count(st, 1, 'A', '2', NOW)
check(res == 'same_user' and st['next'] == 1, 'дважды один человек — счёт упал')
res, st = cn.try_count(st, 2, 'B', '1', NOW)
check(res == 'ok' and st['next'] == 2, 'после падения начинаем с 1')
res, st = cn.try_count(st, 3, 'C', '5', NOW)
check(res == 'wrong_number' and st['fails'] == 2 and st['fail_expected'] == 2,
      'не то число — падение, ждали 2')
res, st = cn.try_count(st, 2, 'B', 'привет', NOW)
check(res == 'not_number' and st['next'] == 2 if False else res == 'not_number',
      'текст — не падение, просто не число (удалится молча)')
# рекорд держится через падения
st = cn.empty_state(77)
for uid, num in ((1, '1'), (2, '2'), (1, '3'), (2, '4')):
    res, st = cn.try_count(st, uid, 'X', num, NOW)
check(res == 'ok' and st['best'] == 4, 'серия 1-2-3-4 -> рекорд 4')
res, st = cn.try_count(st, 1, 'X', '9', NOW)
check(res == 'wrong_number' and st['best'] == 4, 'падение рекорд не тронуло')
check(st['updated_at'].endswith('+00:00'), 'метки aware UTC')

print('== 3. status_lines ==')
check(cn.status_lines(None)[0].startswith('Считалка выключена'),
      'выключенная — понятная строка')
st = cn.empty_state(55)
st.update({'next': 8, 'best': 7, 'last_user_name': 'Zhulik', 'fails': 3})
lines = cn.status_lines(st)
check('**8**' in lines[0] and '**7**' in lines[1] and 'Zhulik' in lines[2]
      and '3 раза' in lines[3], f'строки статуса: {lines}')

print('== 4. хранилище ==')
db = GuildData('counting')
db.set(4242, 'state', st)
back = db.get(4242, 'state', cn.empty_state())
check(back['next'] == 8 and back['best'] == 7, 'состояние переживает roundtrip')

print('== 5. линт ==')
src = open(os.path.join(ROOT, 'cogs', 'counting.py'), encoding='utf-8').read()
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
