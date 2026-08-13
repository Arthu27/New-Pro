# -*- coding: utf-8 -*-
"""Тесты cogs/welcome_pro.py — рендер шаблонов, ротация, добавление/удаление.

Запуск: python3 tests/test_welcome_pro.py
"""
import ast
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_welcome_test_')
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


from cogs import welcome_pro as wp  # noqa: E402
from db import GuildData  # noqa: E402

print('== 1. render_welcome: переменные ==')
out = wp.render_welcome('Привет, {mention}! Ты {count}-й на {server}.',
                        'Zhulik', '<@5>', 'Hakumo', 42)
check(out == 'Привет, <@5>! Ты 42-й на Hakumo.', 'все переменные подставлены')
out = wp.render_welcome('Привет, {user}!', 'Meloman', '<@6>', 'Hakumo', 7)
check(out == 'Привет, Meloman!', 'user работает')
out = wp.render_welcome('Новичок {username} зашёл!', 'A', '<@1>', 'S', 1)
check('{username}' in out, 'неизвестная переменная остаётся текстом, рендер не падает')
out = wp.render_welcome('{user} {user} {user}', 'A', 'm', 'S', 1)
check(out == 'A A A', 'повторные переменные ок')

print('== 2. ротация шаблонов ==')
s = wp.merge_settings(None)
check(len(s['templates']) == 3, 'дефолтных шаблона три')
seen = []
for _ in range(5):
    text, nxt = wp.pick_template(s)
    seen.append(s['templates'].index(text))
    s['rotate_index'] = nxt
check(seen == [0, 1, 2, 0, 1], f'круговая ротация 0-1-2-0-1, got {seen}')
s_bad = dict(s)
s_bad['rotate_index'] = 99
text, nxt = wp.pick_template(s_bad)
check(nxt in (0, 1, 2), 'битый индекс ротации лечится модулем')

print('== 3. add/remove шаблонов ==')
s2, err = wp.add_template(wp.merge_settings(None), 'Привет, {mention}, добро пожаловать домой!')
check(err is None and len(s2['templates']) == 4, 'добавление ок')
s2, err = wp.add_template(s2, 'без переменных вообще совсем')
check(err is not None and 'mention' in err, 'шаблон без {mention}/{user} отклонён')
s2, err = wp.add_template(s2, '{user} а')
check(err is not None and '10 символов' in err, 'слишком короткий отклонён')

big = wp.merge_settings(None)
big['templates'] = ['{mention} шаблон номер ' + str(i) for i in range(15)]
big, err = wp.add_template(big, '{mention} шестнадцатый лишний')
check(err is not None and '15' in err, 'потолок 15 шаблонов')

s3 = wp.merge_settings(None)
s3, err = wp.remove_template(s3, 2)
check(err is None and len(s3['templates']) == 2, 'удаление №2 ок')
s3, err = wp.remove_template(s3, 99)
check(err is not None and 'нет шаблона' in err, 'несуществующий номер — ошибка')
s3, err = wp.remove_template(s3, 1)
s3, err = wp.remove_template(s3, 1)
check(err is not None and 'последний' in err, 'последний шаблон не даём удалить')

print('== 4. merge_settings: битые данные ==')
s = wp.merge_settings({'templates': 'сломано', 'rotate_index': 'x'})
check(s['templates'] == wp.DEFAULT_SETTINGS['templates'] and s['rotate_index'] == 0,
      'битые типы -> дефолт')
s = wp.merge_settings({'templates': []})
check(len(s['templates']) == 3, 'пустой список -> дефолтные три')
s = wp.merge_settings({'templates': ['{mention} ок', 12345, None]})
check(all(isinstance(t, str) for t in s['templates']), 'не-строки приводятся к строкам')

print('== 5. хранилище ==')
db = GuildData('welcome_pro')
db.set(4242, 'settings', {'enabled': True, 'channel_id': 100,
                          'templates': ['{mention} привет из БД'], 'rotate_index': 0})
back = wp.merge_settings(db.get(4242, 'settings', {}))
check(back['enabled'] is True and back['templates'] == ['{mention} привет из БД'],
      'настройки переживают roundtrip')

print('== 6. линт ==')
src = open(os.path.join(ROOT, 'cogs', 'welcome_pro.py'), encoding='utf-8').read()
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
