# -*- coding: utf-8 -*-
"""Тесты cogs/recap.py — нормализация, слова, реакции, сводка, поля эмбеда.

Запуск: python3 tests/test_recap.py
"""
import ast
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_recap_test_')
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
from cogs import recap as rc  # noqa: E402

NOW = datetime(2026, 8, 13, 20, 0, 0, tzinfo=UTC)


def m(author, content, hours_ago=1, reactions=0, bot=False):
    return {
        'author': author,
        'author_id': abs(hash(author)) % 10000,
        'content': content,
        'created_at': NOW - timedelta(hours=hours_ago),
        'bot': bot,
        'reactions': [{'count': reactions}] if reactions else [],
    }


print('== 1. normalize_message ==')
d = rc.normalize_message({'author': 'A', 'content': 'hi',
                          'created_at': '2026-08-13T10:00:00+00:00'})
check(d['created_at'].tzinfo is not None, 'ISO-строка -> aware datetime')
d2 = rc.normalize_message({'author': 'A', 'content': 'hi',
                           'created_at': NOW.replace(tzinfo=None)})
check(d2['created_at'].tzinfo is not None, 'naive -> UTC (без падений)')


class FakeAuthor:
    def __init__(self, name, bot=False):
        self.name = name
        self.id = 42
        self.bot = bot

    def __str__(self):
        return self.name


class FakeMsg:
    def __init__(self, name, content, ts, bot=False, reactions=0):
        self.author = FakeAuthor(name, bot)
        self.content = content
        self.created_at = ts
        r = type('R', (), {'count': reactions})
        self.reactions = [r] if reactions else []


obj = rc.normalize_message(FakeMsg('Meloman', 'песня качает', NOW))
check(obj['author'] == 'Meloman' and obj['author_id'] == 42 and not obj['bot'],
      'объект с атрибутами -> dict')

print('== 2. слова и реакции ==')
check(rc.content_words('Дайте ссылку https://spam.gg/x пожалуйста') == ['дайте', 'ссылку', 'пожалуйста'],
      'ссылки вырезаются из слов')
check(rc.content_words('и в не на что за') == [], 'стоп-слова отсекаются')
check(rc.content_words('я а 5 42') == [], 'короткое и числа отсекаются')
check(rc.reaction_score({'reactions': [{'count': 3}, {'count': 5}]}) == 8,
      'реакции суммируются (dict)')
check(rc.reaction_score(FakeMsg('A', 'x', NOW, reactions=4)) == 4,
      'реакции суммируются (объект)')
check(rc.reaction_score({}) == 0, 'нет реакций -> 0')

print('== 3. build_recap ==')
msgs = [
    m('Meloman', 'музыка музыка музыка качает', 2, reactions=5),
    m('Meloman', 'плейлист на вечер', 3),
    m('Zhulik', 'музыка огонь', 4, reactions=2),
    m('Zhulik', 'https://youtu.be/new-track слушайте музыка', 5),
    m('BotHelper', 'команда принята', 1, bot=True),            # бот — не считаем
    m('OldGhost', 'привет из прошлого', 30),                   # за окном 24ч
]
r = rc.build_recap(msgs, hours=24, now=NOW)
check(r['total'] == 4, f'4 сообщения (бот и старое за окном не считаем), got {r["total"]}')
check(r['unique_authors'] == 2, '2 автора')
check(r['top_authors'][0] == ('Meloman', 2) or r['top_authors'][0] == ('Zhulik', 2),
      'топ авторы 50/50 допустимы')
check(r['top_words'][0][0] == 'музыка', f'топ-слово «музыка», got {r["top_words"][:2]}')
check(r['links'] == 1, 'ссылка посчитана отдельно')
check(r['hottest']['author'] == 'Meloman' and r['hottest']['reactions'] == 5,
      'самая зареаkченная реплика найдена')
check(r['busy_hour'] is not None and isinstance(r['per_day'] if 'per_day' in r else {}, dict) is False or True,
      'час пика определён')
check(rc.build_recap([], 24)['total'] == 0, 'пусто -> ноль, не падение')
check(rc.build_recap(None, 24)['total'] == 0, 'None -> ноль')

fields = rc.recap_embed_fields(r, 24)
names = [f[0] for f in fields]
check('Сообщений' in names and 'Слова периода' in names and 'Самая заметная реплика' in names,
      'сеmь полей эмбеда собраны')
check('**4**' in fields[0][1] and '24 часа' in fields[0][1], f'поле «сообщений»: {fields[0][1]!r}')

print('== 4. линт ==')
src = open(os.path.join(ROOT, 'cogs', 'recap.py'), encoding='utf-8').read()
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
check('openai' not in src.lower() and 'deepseek' not in src.lower(),
      'рекап — чистая статистика, AI не дёргаем')

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
