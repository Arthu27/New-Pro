# -*- coding: utf-8 -*-
"""Тесты cogs/server_stats.py — рендер шаблонов, сбор статистики, план и лимиты.

Запуск: python3 tests/test_server_stats.py
"""
import ast
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='aether_stats_test_')
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
from cogs import server_stats as ss  # noqa: E402
from db import GuildData  # noqa: E402

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)


class FakeMember:
    def __init__(self, bot=False, status='online'):
        self.bot = bot
        self.status = status


class FakeChannel:
    def __init__(self, cid, name):
        self.id = cid
        self.name = name


class FakeGuild:
    pass


def make_guild():
    g = FakeGuild()
    g.member_count = 10
    g.members = [FakeMember() for _ in range(8)] + [FakeMember(bot=True) for _ in range(2)]
    g.members[0].status = 'offline'
    g.text_channels = [FakeChannel(1, 'общий')]
    g.voice_channels = [FakeChannel(2, 'голосовой')]
    g.channels = g.text_channels + g.voice_channels
    g.roles = ['@everyone', 'Модератор', 'Участник']
    g.premium_subscription_count = 3
    return g


print('== 1. gather_stats ==')
stats = ss.gather_stats(make_guild())
check(stats['members'] == 10 and stats['bots'] == 2, 'участники и боты посчитаны')
check(stats['online'] == 9, 'онлайн = без offline-статуса')
check(stats['channels'] == 2 and stats['text'] == 1 and stats['voice'] == 1,
      'каналы по типам')
check(stats['roles'] == 3 and stats['boosts'] == 3, 'роли и бусты')
empty = ss.gather_stats(FakeGuild())
check(empty['members'] == 0 and empty['channels'] == 0, 'пустой фейк не роняет сбор')

print('== 2. render_counter ==')
check(ss.render_counter('Участники: {members}', {'members': 128}) == 'Участники: 128',
      'подстановка')
check(ss.render_counter('Онлайн {online}/{members}', {'online': 5, 'members': 10})
      == 'Онлайн 5/10', 'несколько переменных')
check(ss.render_counter('Что-то {unknown_var} тут', {}) == 'Что-то {unknown_var} тут',
      'неизвестная переменная остаётся текстом — рендер не падает')
check(len(ss.render_counter('x' * 300, {})) == 80, 'длинное имя обрезано под лимит')

print('== 3. plan_updates: только изменившиеся ==')
settings = ss.merge_settings({'channels': {'2': 'Голосовых: {voice}',
                                           '3': 'Участники: {members}'}})
current = {'2': 'Голосовых: 1', '3': 'Участники: 999'}
plan = ss.plan_updates(settings, current, {'voice': 1, 'members': 128})
check(plan == [('3', 'Участники: 128')],
      f'переименовываем только то, что поменялось: {plan}')
check(ss.plan_updates(settings, {'2': 'Голосовых: 1', '3': 'Участники: 128'},
                      {'voice': 1, 'members': 128}) == [],
      'ничего не поменялось — пустой план (реитлимиты целы)')

print('== 4. should_auto_update / manual_allowed ==')
s = ss.merge_settings({'enabled': True, 'channels': {'2': 'x {members}'}})
check(ss.should_auto_update(s, NOW) is True, 'первый запуск — обновляем')
s['last_update'] = NOW.isoformat()
check(ss.should_auto_update(s, NOW + timedelta(seconds=120)) is False,
      'недавно обновляли — стоим')
check(ss.should_auto_update(s, NOW + timedelta(seconds=601)) is True,
      'интервал вышел — пора')
s['enabled'] = False
check(ss.should_auto_update(s, NOW + timedelta(days=9)) is False, 'выключено — нет')
s['last_update'] = 'билайн'
s['enabled'] = True
check(ss.should_auto_update(s, NOW) is True, 'битая метка — перестраховка, обновляем')

ok, left = ss.manual_allowed(ss.merge_settings({}), NOW)
check(ok and left == 0, 'первое ручное — можно')
s2 = ss.merge_settings({'last_manual': NOW.isoformat()})
ok, left = ss.manual_allowed(s2, NOW + timedelta(seconds=100))
check(not ok and left == 230, f'ручное ограничено: осталось {left}')
ok, left = ss.manual_allowed(s2, NOW + timedelta(seconds=400))
check(ok, 'после паузы — можно')

print('== 5. merge_settings и хранилище ==')
m = ss.merge_settings({'channels': {5: 'x'}, 'enabled': 'нет нет', 'hack': 1})
check(m['channels'] == {'5': 'x'} and 'hack' not in m, 'каналы приведены к str, мусор вон')
db = GuildData('server_stats')
db.set(4242, 'settings', s)
back = ss.merge_settings(db.get(4242, 'settings', {}))
check(back['channels'] == s['channels'], 'настройки переживают roundtrip')

print('== 6. линт ==')
src = open(os.path.join(ROOT, 'cogs', 'server_stats.py'), encoding='utf-8').read()
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
