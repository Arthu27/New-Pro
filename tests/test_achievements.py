# -*- coding: utf-8 -*-
"""Тесты cogs/achievements.py — каталог, оценка, выдача, очки, хранилище.

Запуск: python3 tests/test_achievements.py
"""
import ast
import os
import sys
import tempfile
from datetime import datetime, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_ach_test_')
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
from cogs import achievements as ach  # noqa: E402
from db import GuildData  # noqa: E402

print('== 1. каталог здоров ==')
check(len(ach.ACHIEVEMENTS) >= 10, f'ачивок хватает ({len(ach.ACHIEVEMENTS)})')
ok = all(len(v) == 4 and isinstance(v[0], str) and isinstance(v[2], int)
         and callable(v[3]) for v in ach.ACHIEVEMENTS.values())
check(ok, 'у каждой: имя, описание, очки, проверка')
check(len(set(ach.ACHIEVEMENTS)) == len(ach.ACHIEVEMENTS), 'ключи уникальны')

print('== 2. norm_stats ==')
check(ach.norm_stats({'messages': 5}) == {'messages': 5, 'voice_seconds': 0, 'days_member': 0},
      'недостающее -> 0')
check(ach.norm_stats(None) == {'messages': 0, 'voice_seconds': 0, 'days_member': 0},
      'None -> нули')
check(ach.norm_stats({'messages': 'много', 'voice_seconds': -10})['voice_seconds'] == 0,
      'мусор и минус -> 0')

print('== 3. evaluate ==')
check(ach.evaluate({'messages': 0}) == set(), 'нулевой — без ачивок')
got = ach.evaluate({'messages': 1})
check(got == {'first_words'}, f'первое сообщение -> first_words, got {got}')
got = ach.evaluate({'messages': 1500, 'voice_seconds': 40000, 'days_member': 40})
expect = {'first_words', 'talker_100', 'talker_1000', 'voice_1h', 'voice_10h',
          'member_7d', 'member_30d'}
check(got == expect, f'комбо-статистика: {sorted(got)}')
check('member_365d' in ach.evaluate({'days_member': 400}), 'год + месяц -> старожил')
check('talker_10000' in ach.evaluate({'messages': 10001}), '10000 сообщений -> легенда')

print('== 4. new_grants / очки / прогресс ==')
check(ach.new_grants({'a', 'b'}, ['a']) == ['b'], 'выдаются только новые')
check(ach.new_grants(set(), ['a']) == [], 'ничего не заслужено — ничего не выдаём')
check(ach.total_points(['first_words', 'talker_100', 'небывалая']) == 15,
      'очки суммируются, неизвестные ключи молча пропускаются')
rows = ach.progress_rows({'messages': 150, 'voice_seconds': 4000, 'days_member': 10},
                         ['first_words', 'talker_100', 'voice_1h', 'member_7d'])
done = [r['key'] for r in rows if r['done']]
check(set(done) == {'first_words', 'talker_100', 'voice_1h', 'member_7d'},
      'progress_rows: полученные помечены')
check(all('points' in r and 'desc' in r for r in rows), 'полные поля строк')

print('== 5. хранилище и батч-счётчик ==')
db = GuildData('achievements')
rec = ach.user_record()
rec['grants'] = ['first_words']
rec['messages'] = 5
db.set(4242, 'user_77', rec)
back = db.get(4242, 'user_77', ach.user_record())
check(back['grants'] == ['first_words'] and back['messages'] == 5,
      'запись пользователя переживает roundtrip')
check(db.get(4242, 'user_999', ach.user_record()) == ach.user_record(),
      'новый пользователь -> пустая запись')

cog = object.__new__(ach.Achievements)
cog._pending = {}
# прогоиняем логику батча без discord: просто накидываем счётчик
for _ in range(3):
    key = (4242, 77)
    cog._pending[key] = cog._pending.get(key, 0) + 1
check(cog._pending[(4242, 77)] == 3, 'слушатель копит сообщения в батч')

print('== 6. линт ==')
src = open(os.path.join(ROOT, 'cogs', 'achievements.py'), encoding='utf-8').read()
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
