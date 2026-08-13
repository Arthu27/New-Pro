# -*- coding: utf-8 -*-
"""Тесты cogs/duels.py — учёт исходов, серии, топ, строки статистики.

Запуск: python3 tests/test_duels.py
"""
import ast
import os
import sys
import tempfile
from datetime import datetime, timezone

_TMP = tempfile.mkdtemp(prefix='aether_duel_test_')
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
from cogs import duels as dl  # noqa: E402
from db import GuildData  # noqa: E402

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)

print('== 1. record_result: серии и счётчики ==')
st = dl.empty_state()
w, l = dl.record_result(st, 1, 2, NOW)
check(w['wins'] == 1 and w['streak'] == 1 and w['best_streak'] == 1,
      'первая победа: wins/streak/best = 1')
check(l['losses'] == 1 and l['streak'] == 0, 'проигрыш сбрасывает серию')
dl.record_result(st, 1, 2, NOW)
dl.record_result(st, 1, 3, NOW)
w1 = st['players']['1']
check(w1['wins'] == 3 and w1['streak'] == 3 and w1['best_streak'] == 3,
      'серия из трёх побед')
dl.record_result(st, 2, 1, NOW)
w1 = st['players']['1']
check(w1['streak'] == 0 and w1['best_streak'] == 3 and w1['losses'] == 1,
      'поражение обнуляет текущую, хранит лучшую')
check(st['total'] == 4, 'общий счётчик дуэлей')
check(w1['last_at'].endswith('+00:00'), 'метки aware UTC')

print('== 2. player_stats / summary / top ==')
s1 = dl.player_stats(st, 1)
check(s1['wins'] == 3 and s1['losses'] == 1 and s1['total'] == 4
      and s1['winrate'] == 75, f'винрейт 3/4 = 75%: {s1}')
check(dl.player_stats(st, 999) is None, 'нет дуэлей -> None (команда вежливо ответит)')
check(dl.player_stats(None, 1) is None, 'пустое состояние -> None')

summ = dl.duel_summary(st, 1)
check('3 победы' in summ and '75%' in summ, f'сводка: {summ!r}')
check(dl.duel_summary(st, 999) == 'дуэлей пока не было', 'новичок — понятная строка')

rows = dl.top_duels(st)
check(rows[0] == (1, 3, 1), f'первый в топе — по победам: {rows[0]}')
check(dl.top_duels(None) == [], 'пусто -> пусто')

print('== 3. хранилище и view ==')
db = GuildData('duels')
db.set(4242, 'state', st)
back = db.get(4242, 'state', dl.empty_state())
check(dl.player_stats(back, 1)['wins'] == 3, 'статистика переживает roundtrip')

view = dl.DuelView(object(), 4242, object(), object())
check(view.timeout == dl.DUEL_TIMEOUT, f'вызов живёт {dl.DUEL_TIMEOUT} секунд')
labels = sorted(c.label for c in view.children)
check(labels == ['Отказаться', 'Принять дуэль'], f'кнопки на месте: {labels}')

print('== 4. линт ==')
src = open(os.path.join(ROOT, 'cogs', 'duels.py'), encoding='utf-8').read()
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
import re as _re
EMOJI = _re.compile('[\U0001F000-\U0001FAFF☀-➿]')
check(not EMOJI.search(src), 'эмодзи в сообщениях бота нет (текстовый стиль)')

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
