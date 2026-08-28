# -*- coding: utf-8 -*-
"""Тесты cogs/server_template.py — снимок, мета-строка, diff-план, хранилище.

Запуск: python3 tests/test_server_template.py
"""
import ast
import os
import sys
import tempfile
from datetime import datetime, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_tpl_test_')
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


from cogs import server_template as st  # noqa: E402
from db import GuildData  # noqa: E402


class FakeColor:
    def __init__(self, value):
        self.value = value


class FakePerms:
    def __init__(self, value):
        self.value = value


class FakeRole:
    def __init__(self, name, pos=1, managed=False, default=False):
        self.name = name
        self.color = FakeColor(0xFF0000)
        self.permissions = FakePerms(104320)
        self.hoist = True
        self.mentionable = True
        self.position = pos
        self.managed = managed
        self._default = default

    def is_default(self):
        return self._default


class FakeTextChannel:
    def __init__(self, name, category=None, pos=0):
        self.name = name
        self.type = 'ChannelType.text'
        self.topic = 'тема канала'
        self.slowmode_delay = 5
        self.nsfw = False
        self.position = pos
        self.category = category


class FakeCategory:
    def __init__(self, name, channels):
        self.name = name
        self.channels = channels


class FakeGuild:
    def __init__(self):
        cat_a = FakeCategory.__new__(FakeCategory)
        cat_a.name = 'Общение'
        ch1 = FakeTextChannel('общий', category=cat_a, pos=1)
        ch2 = FakeTextChannel('флуд', category=cat_a, pos=2)
        cat_a.channels = [ch1, ch2]
        cat_b = FakeCategory.__new__(FakeCategory)
        cat_b.name = 'Голос'
        cat_b.channels = []
        self.categories = [cat_a, cat_b]
        self.text_channels = [ch1, ch2, FakeTextChannel('правила')]
        self.text_channels[-1].category = None
        self.voice_channels = []
        self.roles = [FakeRole('Модератор', 5), FakeRole('Участник', 1),
                      FakeRole('@everyone', default=True),
                      FakeRole('BotRole', managed=True)]
        self.name = 'Hakumo'


print('== 1. snapshot_guild ==')
g = FakeGuild()
tpl = st.snapshot_guild(g)
check([r['name'] for r in tpl['roles']] == ['Участник', 'Модератор'],
      'роли: по позиции, @everyone и managed пропущены')
check(tpl['roles'][0]['color'] == 0xFF0000 and tpl['roles'][0]['permissions'] == 104320,
      'снимок роли: цвет/права сохранены')
check(len(tpl['categories']) == 2 and len(tpl['categories'][0]['channels']) == 2,
      'категории с каналами')
check([c['name'] for c in tpl['channels']] == ['правила'], 'каналы без категории — отдельно')
ch0 = tpl['categories'][0]['channels'][0]
check(ch0['type'] == 'text' and ch0['slowmode'] == 5 and ch0['topic'] == 'тема канала',
      'снимок канала: тип очищен от ChannelType., топик/слоумод сохранены')
check(tpl['version'] == 1, 'версия шаблона зашита')

print('== 2. template_meta ==')
meta = st.template_meta(tpl)
check(meta == '2 роли · 2 категории · 3 канала', f'мета: {meta!r}')
check(st.template_meta({'roles': [], 'categories': [], 'channels': []})
      == '0 ролей · 0 категорий · 0 каналов', 'пустой шаблон')

print('== 3. diff_plan ==')
plan = st.diff_plan(tpl, g)
check(plan == {'roles': [], 'categories': [], 'channels': []},
      'на исходном сервере создавать нечего')


class EmptyGuild(FakeGuild):
    def __init__(self):
        super().__init__()
        self.roles = [FakeRole('Участник', 1)]      # «Модератор» потерян
        self.categories = []                        # категории потеряны
        self.text_channels = [FakeTextChannel('общий')]
        self.voice_channels = []


plan2 = st.diff_plan(tpl, EmptyGuild())
check(plan2['roles'] == ['Модератор'], f'роль-должник найдена: {plan2["roles"]}')
check(set(plan2['categories']) == {'Общение', 'Голос'}, 'категории-должники')
check(set(plan2['channels']) == {'флуд', 'правила'} and 'общий' not in plan2['channels'],
      f'каналы-должники без уже живущего «общий»: {plan2["channels"]}')

# регистр имён не важен
tpl_upper = st.snapshot_guild(g)
tpl_upper['roles'][0]['name'] = tpl_upper['roles'][0]['name'].upper()
plan3 = st.diff_plan(tpl_upper, g)
check(plan3['roles'] == [], 'сравнение регистронезависимое')

print('== 4. хранилище ==')
db = GuildData('server_template')
store = {  # как ког складывает в 'templates'
    'база': {'template': tpl, 'description': 'основа', 'created_by': 'Arthur',
             'created_at': datetime.now(timezone.utc).isoformat(),
             'source_guild': 'Hakumo'},
}
db.set(4242, 'templates', store)
back = db.get(4242, 'templates', {})
check(back['база']['template'] == tpl and back['база']['source_guild'] == 'Hakumo',
      'шаблон переживает roundtrip через SQLite (кириллица цела)')

print('== 5. линт ==')
src = open(os.path.join(ROOT, 'cogs', 'server_template.py'), encoding='utf-8').read()
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
