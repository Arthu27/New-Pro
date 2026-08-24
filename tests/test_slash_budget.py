# -*- coding: utf-8 -*-
"""Страж бюджета слеш-команд: глобальное меню Discord ≤ 100 команд.

Прогоняет реальную загрузку всех когов в режиме BOT_FULL (худший случай:
выбор через cogs_policy, прунинг через slash_budget после каждого модуля) и проверяет:
  * в итоговом дереве не больше 95 команд — запас до лимита;
  * всё, что осталось в меню, входит в KEEP_SLASH (и UNIQUE);
  * KEEP_SLASH не «протух»: большинство имён реально существуют в дереве
    (ловит переименования команд, из-за которых меню молча пустеет);
  * сам белый список валиден: строки, строчные, без пробелов, ≤ 95 штук;
  * прунинг реально работает: из дерева вынеслись десятки команд (они
    остаются доступны через префикс — это и есть смысл бюджета).

Запуск: python3 tests/test_slash_budget.py
"""
import asyncio
import logging
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_slash_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
for _v in ('MOD_ONLY', 'DISABLED_COGS', 'EXTRA_COGS'):
    os.environ.pop(_v, None)

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


import discord  # noqa: E402
from discord.ext import commands  # noqa: E402

import cogs_policy  # noqa: E402
import slash_budget  # noqa: E402

print('== 1. Валидность белого списка KEEP_SLASH ==')
keep = slash_budget.KEEP_SLASH
check(isinstance(keep, frozenset) and len(keep) > 0, f'KEEP_SLASH непустой ({len(keep)} имён)')
check(len(keep) <= 95, f'белый список сам влезает в бюджет: {len(keep)} <= 95')
check(all(isinstance(n, str) and n for n in keep), 'все имена — непустые строки')
check(all(n == n.lower() for n in keep), 'все имена строчные (требование Discord)')
check(all(' ' not in n and '/' not in n for n in keep), 'без пробелов и слешей в именах')
check(len(set(keep)) == len(keep), 'без дублей')

print('== 2. Реальная загрузка всех когов с прунингом ==')
logging.disable(logging.CRITICAL)

stats = {'loaded': 0, 'failed': {}, 'pruned': 0}


async def _load_all():
    bot = commands.Bot(command_prefix='!', intents=discord.Intents.all(), help_command=None)
    asyncio.get_running_loop().set_exception_handler(lambda _l, _c: None)
    all_files = sorted(f for f in os.listdir(os.path.join(ROOT, 'cogs')) if f.endswith('.py'))
    files, _gone = cogs_policy.select_from_environment(all_files, environ={'BOT_FULL': '1'})
    stats['total_files'] = len(files)
    for f in files:
        try:
            await asyncio.wait_for(bot.load_extension(f'cogs.{f[:-3]}'), timeout=30)
            stats['loaded'] += 1
            _kept, pruned = slash_budget.apply_slash_budget(bot.tree)
            stats['pruned'] += len(pruned)
        except Exception as e:  # отсутствующие необязательные зависимости и т.п.
            stats['failed'][f] = f'{type(e).__name__}'
    tree_names = sorted(
        {c.name for c in bot.tree.get_commands()
         if not isinstance(c, discord.app_commands.ContextMenu)}
    )
    await bot.close()
    return tree_names


tree_names = asyncio.run(_load_all())
print(f'  загружено модулей: {stats["loaded"]}/{stats.get("total_files", 0)}, '
      f'не встало оффлайн: {len(stats["failed"])} {sorted(stats["failed"])}')
print(f'  в слеш-меню после бюджета: {len(tree_names)} команд, '
      f'вынесено на префикс: {stats["pruned"]}')

print('== 3. Бюджет держится ==')
check(len(tree_names) <= 95, f'меню умещается с запасом: {len(tree_names)} <= 95 (лимит 100)')
check(len(tree_names) == len(set(tree_names)), 'имена в меню уникальны')

print('== 4. Меню — ровно белый список ==')
stray = [n for n in tree_names if n not in keep]
check(not stray, f'ничего лишнего вне KEEP_SLASH (лишнее: {stray[:5]})')
realized = [n for n in keep if n in tree_names]
missing = sorted(set(keep) - set(tree_names))
print(f'  KEEP-имена реально в меню: {len(realized)}/{len(keep)}; отсутствуют оффлайн: {missing}')
check(not missing, f'белый список не протух: все {len(keep)} имён на месте (нет: {missing})')

print('== 5. Прунинг реально работает ==')
check(stats['pruned'] >= 30, f'на префикс вынесено {stats["pruned"]} команд (>= 30)')
check(stats['loaded'] >= 60, f'загрузилось большинство модулей: {stats["loaded"]} >= 60')
check('CommandLimitReached' not in ''.join(stats['failed'].values()),
      'ни один модуль не упал о лимит команд')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
