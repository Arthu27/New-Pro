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

_TMP = tempfile.mkdtemp(prefix='hakumo_slash_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
# Сервер из .env: часть когов регистрирует команды ЛОКАЛЬНО (guild-scoped)
# через add_cog(..., guilds=Config.guild_objects()) — бюджет обязан
# почистить и их (иначе /security, /backup, /ticket-* возвращаются в меню).
os.environ['MAIN_GUILD_ID'] = '777'
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
        | {c.name for c in bot.tree.get_commands(guild=discord.Object(id=777))
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

print('== 4. Меню — ровно белый список (глобально И на сервере) ==')
stray = [n for n in tree_names if n not in keep]
check(not stray, f'ничего лишнего вне KEEP_SLASH (лишнее: {stray[:5]})')
for gone in ('security', 'security-toggle', 'security-newaccount', 'scan-link',
             'backup', 'backup-list', 'staff-panel', 'my-application'):
    check(gone not in tree_names,
          f'guild-scoped {gone} не вернулся в меню (бюджет чистит и локальные команды)')
# тикетная панель вернулась по заказу владельца — обязана быть в меню
# (guild-scoped). ticket-add/ticket-remove убраны (заказ 2026-08-29
# «должны быть в меню тикета»): их работа — кнопки ➕/➖ в TicketManageView.
for need in ('ticket-panel',):
    check(need in tree_names,
          f'тикетная {need} в меню (заказ «вернуть тикеты» — бюджета ей нет)')
for moved in ('ticket-add', 'ticket-remove'):
    check(moved not in tree_names,
          f'{moved} убрана из слеш-меню — теперь это кнопки в меню тикета')
realized = [n for n in keep if n in tree_names]
missing = sorted(set(keep) - set(tree_names))
print(f'  KEEP-имена реально в меню: {len(realized)}/{len(keep)}; отсутствуют оффлайн: {missing}')
check(not missing, f'белый список не протух: все {len(keep)} имён на месте (нет: {missing})')

print('== 5. Прунинг реально работает ==')
check(stats['pruned'] >= 30, f'на префикс вынесено {stats["pruned"]} команд (>= 30)')
check(stats['loaded'] >= 60, f'загрузилось большинство модулей: {stats["loaded"]} >= 60')
check('CommandLimitReached' not in ''.join(stats['failed'].values()),
      'ни один модуль не упал о лимит команд')

print('== 6. BOT_FULL=1: меню держит ВСЕ команды (жалоба «команды не грузятся») ==')
os.environ['BOT_FULL'] = '1'   # как у владельца в .env
check(slash_budget.full_menu_mode({'BOT_FULL': '1'}) is True,
      'full_menu_mode распознаёт BOT_FULL=1')
check(slash_budget.full_menu_mode({}) is False,
      'без флага — лёгкий кураторский режим')


class _Cmd:
    def __init__(self, name):
        self.name = name


class _Tree:
    """Дерево-заглушка: команды живут в множестве, remove по имени."""

    def __init__(self, names):
        self._cmds = {n: _Cmd(n) for n in names}

    def get_commands(self, guild=None):
        return list(self._cmds.values())

    def remove_command(self, name, type=None, guild=None):
        return self._cmds.pop(name, None)


_names80 = [f'cmd{i:02d}' for i in range(80)]
_tree = _Tree(_names80)
_kept80, _pruned80 = slash_budget.apply_slash_budget(_tree, guilds=[])
check(len(_kept80) == 80 and not _pruned80,
      f'BOT_FULL держит всё меню целиком ({len(_kept80)} из 80)')
# а теперь перебор: 130 команд — хвост уходит на префикс, лимит не пробит
_names130 = [f'cmd{i:03d}' for i in range(130)]
_tree130 = _Tree(_names130)
_kept130, _pruned130 = slash_budget.apply_slash_budget(_tree130, guilds=[])
# 7 мест из SAFE_FULL зарезервированы под KEEP_SLASH — их имён в дереве нет,
# реально остаётся SAFE_FULL - |KEEP_SLASH| команд
_full_cap = slash_budget.SAFE_FULL - len(slash_budget.KEEP_SLASH)
check(len(_kept130) == _full_cap and len(_pruned130) == 130 - _full_cap,
      f'перебор урезается до безопасных {slash_budget.SAFE_FULL} '
      f'(мест под KEEP_SLASH включены): {len(_kept130)} в меню, {len(_pruned130)} на префикс')
# 88 команд (LIMIT - MAX_COG_BURST) — ещё влезают целиком, запас для следующего кога
_names88 = [f'cmd{i:02d}' for i in range(88)]
_tree88 = _Tree(_names88)
_kept88, _pruned88 = slash_budget.apply_slash_budget(_tree88, guilds=[])
check(len(_kept88) == 88 and not _pruned88,
      'до порога — меню не режется вовсе (88 команд целиком)')
# 89 — уже режем до SAFE_FULL
_names89 = [f'cmd{i:02d}' for i in range(89)]
_tree89 = _Tree(_names89)
_kept89, _pruned89 = slash_budget.apply_slash_budget(_tree89, guilds=[])
check(len(_kept89) == _full_cap,
      'за порогом — урезается до SAFE_FULL (гильдия не переполнится после копии)')
print('== 7. Кураторский режим: ПКМ-меню не утекают (жалоба «13 лишних команд») ==')
import discord as _disc2
from discord import app_commands as _ac2
from discord import AppCommandType as _ACT2


class _CtxTree2:
    """Мини-дерево, различающее chat-input и контекстные ПКМ-меню по scope."""

    def __init__(self):
        self.chat = {}
        self.ctx = {}

    def add_chat(self, name, scope=None):
        self.chat.setdefault(scope, set()).add(name)

    def add_ctx(self, name, scope=None):
        self.ctx.setdefault(scope, set()).add(name)

    def get_commands(self, guild=None):
        out = []
        for n in self.chat.get(guild, ()):
            out.append(type('C', (), {'name': n})())
        for n in self.ctx.get(guild, ()):
            m = type('M', (), {'name': n})()
            m.type = _ACT2.user
            out.append(m)
        return out

    def remove_command(self, name, type=None, guild=None):
        bucket = self.ctx if type in (_ACT2.user,
                                      _ACT2.message) else self.chat
        bucket.setdefault(guild, set()).discard(name)


# isinstance(c, ContextMenu) в бюджетe: подменяем _context_menus на наш разбор
def _ctx_names(tree, guild=None):
    return sorted(n for n in tree.ctx.get(guild, ()))


_orig_context_menus = slash_budget._context_menus


def _fake_context_menus(tree, guild=None):
    class _Proxy:
        def __init__(self, name):
            self.name = name
            self.type = _ACT2.user
    return [_Proxy(n) for n in tree.ctx.get(guild, ())]


slash_budget._context_menus = _fake_context_menus

# LEAN: 6 ПКМ-меню глобально + кураторские слэш-команды
os.environ.pop('BOT_FULL', None)
_t = _CtxTree2()
for _n in slash_budget.KEEP_SLASH:
    _t.add_chat(_n, None)
for _m in ('Предупредить', 'Изолировать', 'Варн за сообщение',
           'Войс-мут', 'Войс-размут', 'Кик из войса'):
    _t.add_ctx(_m, None)
slash_budget.apply_slash_budget(_t, guilds=[])
check(not _t.ctx.get(None),
      f'LEAN: все ПКМ-меню вырезаны из глобального дерева (осталось {len(_t.ctx.get(None, ()))})')
check(len(_t.chat.get(None, ())) == len(slash_budget.KEEP_SLASH),
      f'LEAN: кураторские слэш-команды на месте ({len(_t.chat.get(None, ()))})')

# BOT_FULL: ПКМ-меню сохраняются (отдельный лимит Discord, не в бюджете 100)
os.environ['BOT_FULL'] = '1'
_t2 = _CtxTree2()
for _i in range(10):
    _t2.add_chat(f'cmd{_i}', None)
for _m in ('Предупредить', 'Варн за сообщение'):
    _t2.add_ctx(_m, None)
slash_budget.apply_slash_budget(_t2, guilds=[])
check(len(_t2.ctx.get(None, ())) == 2,
      f'BOT_FULL: ПКМ-меню сохраняются в меню ({len(_t2.ctx.get(None, ()))})')
os.environ.pop('BOT_FULL', None)
slash_budget._context_menus = _orig_context_menus

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
