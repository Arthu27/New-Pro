# -*- coding: utf-8 -*-
"""Тесты cogs/triggers.py — добавление, матчинг (точный/подстрока), кулдаун.

Запуск: python3 tests/test_triggers.py
"""
import ast
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_trig_test_')
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
from cogs import triggers as tr  # noqa: E402
from db import GuildData  # noqa: E402

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)

print('== 1. split_spec и add_trigger ==')
check(tr.split_spec('ip | 1.2.3.4:27015') == ('ip', '1.2.3.4:27015'), 'разбор по |')
check(tr.split_spec('без разделителя') == (None, None), 'без | -> None')

st = tr.empty_state()
item, err = tr.add_trigger(st, 'правила', 'Правила тут: #правила')
check(item is not None and item['id'] == 1 and st['next_id'] == 2, 'добавление ок')
item, err = tr.add_trigger(st, 'ё', 'адрес')
check(err is not None, 'короткий триггер <2 симв — отклонён')
item, err = tr.add_trigger(st, 'правила', 'другая версия')
check(err is not None and 'уже есть' in err, 'дубликат не даём')
item, err = tr.add_trigger(st, 'правила', 'точная версия', exact=True)
check(item is not None, 'тот же текст в exact-режиме — другой триггер, ок')
item, err = tr.add_trigger(st, 'ok', '')
check(err is not None and 'пустой ответ' in err, 'пустой ответ отклонён')

st_full = tr.empty_state()
st_full['items'] = [{'id': i, 'trigger': f'w{i}', 'response': 'x', 'exact': False,
                     'uses': 0} for i in range(tr.MAX_TRIGGERS)]
item, err = tr.add_trigger(st_full, 'ещё', 'один')
check(err is not None and '50' in err, f'потолок {tr.MAX_TRIGGERS} триггеров')

print('== 2. matches: подстрока vs слово целиком ==')
sub = {'trigger': 'привет', 'exact': False}
exact = {'trigger': 'привет', 'exact': True}
check(tr.matches(sub, 'ну привет всем'), 'подстрока срабатывает в тексте')
check(tr.matches(sub, 'приветствую!'), 'подстрока ловит и внутри слова')
check(tr.matches(exact, 'ну привет всем'), 'точный — слово целиком')
check(not tr.matches(exact, 'приветствую'), 'точный не ловит внутри слова')
check(tr.matches(exact, 'скажи привет!'), 'точный: граница — знак прек')

print('== 3. find_match + кулдаун ==')
items = [
    {'id': 1, 'trigger': 'ip', 'exact': True, 'response': 'сервер: 1.2.3.4',
     'uses': 0},
    {'id': 2, 'trigger': 'ip сервера', 'exact': False, 'response': 'длинный',
     'uses': 0},
]
cds = {}
hit = tr.find_match(items, 'дайте ip плиз', cds, NOW)
check(hit['id'] == 1, 'короткий точный сработал')
tr.fire(hit, cds, NOW)
hit2 = tr.find_match(items, 'дайте ip плиз', cds, NOW + timedelta(seconds=5))
check(hit2 is None, 'кулдаун 30с держит')
hit3 = tr.find_match(items, 'дайте ip плиз', cds, NOW + timedelta(seconds=31))
check(hit3 is not None, 'после кулдауна снова стреляет')
tr.fire(hit3, cds, NOW + timedelta(seconds=31))
check(items[0]['uses'] == 2, 'счётчик срабатываний ведётся')

long_first = tr.find_match(items, 'какой ip сервера?', {}, NOW)
check(long_first['id'] == 2, 'длинный триггер приоритетнее короткого')
check(tr.find_match(items, 'случайный текст', {}, NOW) is None, 'нет совпадений — None')

print('== 4. remove_trigger и хранилище ==')
check(tr.remove_trigger(st, 1) and not tr.remove_trigger(st, 1), 'удаление идемпотентно')
db = GuildData('triggers')
db.set(4242, 'state', st)
back = db.get(4242, 'state', tr.empty_state())
check(len(back['items']) == 1 and back['items'][0]['exact'] is True,
      'состояние переживает roundtrip')

print('== 5. линт ==')
src = open(os.path.join(ROOT, 'cogs', 'triggers.py'), encoding='utf-8').read()
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
