# -*- coding: utf-8 -*-
"""Страж дублей команд: бот обязан стартовать чисто в ЛЮБОМ профиле .env.

Инцидент 30.08 «бот не запускается / команды дублируются». Причина: две
разные команды назывались одинаково — `/backup` из cogs/backup_cog.py
(группа: архив папки data/) и `/backup` из cogs/security.py (снимок настроек
сервера). Симптом ЗАВИСЕЛ от .env, поэтому баг и жил так долго:

  * MAIN_GUILD_ID пуст  → оба кога регистрируются ГЛОБАЛЬНО, discord.py
    роняет второй ког на старте:
    `CommandAlreadyRegistered: Command 'backup' already registered`
    (в BOT_FULL=1 отваливался весь security.py — антиспам, детект фейков,
    сканер ссылок);
  * MAIN_GUILD_ID задан → security.py уходит в guild-scope, падения нет,
    но одно и то же имя лежит и в глобальном, и в серверном меню Discord —
    в списке «/» команда двоится.

Здесь мы поднимаем НАСТОЯЩИЙ CommandTree и грузим настоящие коги (Discord
не нужен) в каждом профиле и в обоих режимах MAIN_GUILD_ID, проверяя:

  * ни один ког не упал при загрузке (особенно с CommandAlreadyRegistered);
  * в дереве нет повторов имён — ни в глобальном скоупе, ни в гильдовом;
  * ни одно имя не лежит одновременно в глобальном И гильдовом скоупе
    (это и есть «каждая команда по две» в меню Discord);
  * префиксные команды и их алиасы не перекрывают друг друга;
  * имена команд/групп уникальны на уровне исходников (AST) — ловит
    столкновение ещё до запуска бота.

Запуск: python3 tests/test_no_duplicate_commands.py
"""
import ast
import asyncio
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict

_TMP = tempfile.mkdtemp(prefix='hakumo_dupcmd_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['SECRET_KEY'] = 'test-secret'

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


# ─────────────────────────────────────────────────────────────────────────
# 1. Статика: имена команд в исходниках уникальны (ловит баг без запуска)
# ─────────────────────────────────────────────────────────────────────────
print('== 1. Имена команд в исходниках (AST, без запуска бота) ==')

COGS_DIR = os.path.join(ROOT, 'cogs')
_DECOS = {'command', 'hybrid_command', 'group', 'hybrid_group', 'Group'}


def _dotted(node):
    f = node.func if isinstance(node, ast.Call) else node
    parts = []
    while isinstance(f, ast.Attribute):
        parts.append(f.attr)
        f = f.value
    if isinstance(f, ast.Name):
        parts.append(f.id)
    return '.'.join(reversed(parts))


def _kw(node, key):
    for k in getattr(node, 'keywords', ()) or ():
        if k.arg == key and isinstance(k.value, ast.Constant):
            return k.value.value
    return None


# Считаем ОТДЕЛЬНО два пространства имён — они не пересекаются в Discord:
#   slash  — дерево app-команд («/имя»): app_commands.command / .Group
#            + гибриды (они попадают и в меню, и на префикс);
#   prefix — текстовые команды («!имя»): commands.command / .group.
# Пример легального совпадения: !report-setup (расписание отчётов,
# cogs/mod_report.py) и /report-setup (система репортов, cogs/reports.py) —
# разные namespace'ы, конфликта в Discord нет.
# Подкоманды групп (@grp.command) тоже не в счёт: у /backup list и
# /schedule list общее только последнее слово.
# Хелперы из cogs_policy.HELPER_COGS пропускаем — они никогда не грузятся
# как коги (leveling_engagement.py импортируется веб-панелью ради формул).
from cogs_policy import HELPER_COGS  # noqa: E402

slash_ns = defaultdict(set)
prefix_ns = defaultdict(set)

for fname in sorted(os.listdir(COGS_DIR)):
    if not fname.endswith('.py') or fname in HELPER_COGS:
        continue
    tree = ast.parse(open(os.path.join(COGS_DIR, fname), encoding='utf-8').read(), fname)
    for node in ast.walk(tree):
        # name = app_commands.Group(name='backup') — корень слеш-группы
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if _dotted(node.value).endswith('Group'):
                n = _kw(node.value, 'name')
                if n:
                    slash_ns[n].add(fname)
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for d in node.decorator_list:
            if not isinstance(d, ast.Call):
                continue
            dotted = _dotted(d)
            last = dotted.rsplit('.', 1)[-1]
            owner = dotted.rsplit('.', 1)[0] if '.' in dotted else ''
            if last not in _DECOS:
                continue
            # подкоманда группы (@backup_group.command / @grp.command)
            if owner and not owner.startswith(('app_commands', 'commands')):
                continue
            name = _kw(d, 'name') or node.name
            if owner.startswith('app_commands'):
                slash_ns[name].add(fname)
            elif 'hybrid' in last:      # гибрид живёт в ОБОИХ пространствах
                slash_ns[name].add(fname)
                prefix_ns[name].add(fname)
            else:
                prefix_ns[name].add(fname)

slash_clash = {n: sorted(f) for n, f in slash_ns.items() if len(f) > 1}
prefix_clash = {n: sorted(f) for n, f in prefix_ns.items() if len(f) > 1}
check(not slash_clash,
      f'слеш-команды: нет одинаковых имён в разных когах ({slash_clash})')
check(not prefix_clash,
      f'префиксные команды: нет одинаковых имён в разных когах ({prefix_clash})')
check('backup' not in slash_clash,
      "/backup больше не объявлен дважды (security.py vs backup_cog.py)")
check(len(slash_ns.get('backup', ())) <= 1,
      f"имя 'backup' принадлежит ровно одному когу ({sorted(slash_ns.get('backup', ()))})")

# ─────────────────────────────────────────────────────────────────────────
# 2. Живая загрузка когов во всех профилях .env
# ─────────────────────────────────────────────────────────────────────────
print('== 2. Живая загрузка когов: все профили × MAIN_GUILD_ID ==')
logging.disable(logging.CRITICAL)

import discord  # noqa: E402
from discord import app_commands  # noqa: E402
from discord.ext import commands  # noqa: E402

import cogs_policy  # noqa: E402
import slash_budget  # noqa: E402

PROFILES = {
    'LEAN (по умолчанию)': {},
    'BOT_FULL=1': {'BOT_FULL': '1'},
    'MOD_ONLY=1': {'MOD_ONLY': '1'},
    'BOT_SLIM=1': {'BOT_SLIM': '1'},
    'BOT_CORE=1': {'BOT_CORE': '1'},
}

GUILD_ID = 777


def _walk(cmds, prefix=''):
    for c in cmds:
        full = f'{prefix}{c.name}'
        yield full, c
        if isinstance(c, app_commands.Group):
            yield from _walk(c.commands, full + ' ')


async def _load(profile_env, with_guild):
    """Грузим коги ровно как main.load_cogs() и возвращаем состояние дерева."""
    for v in ('BOT_FULL', 'MOD_ONLY', 'BOT_SLIM', 'BOT_CORE',
              'DISABLED_COGS', 'EXTRA_COGS'):
        os.environ.pop(v, None)
    os.environ.update(profile_env)
    if with_guild:
        os.environ['MAIN_GUILD_ID'] = str(GUILD_ID)
    else:
        os.environ.pop('MAIN_GUILD_ID', None)

    import config
    import importlib
    importlib.reload(config)
    importlib.reload(cogs_policy)

    bot = commands.Bot(command_prefix='!', intents=discord.Intents.all(),
                       help_command=None)
    asyncio.get_running_loop().set_exception_handler(lambda _l, _c: None)
    failed = {}
    async with bot:
        all_files = sorted(f for f in os.listdir(COGS_DIR) if f.endswith('.py'))
        files, _gone = cogs_policy.select_from_environment(all_files)
        for f in files:
            try:
                await asyncio.wait_for(bot.load_extension(f'cogs.{f[:-3]}'),
                                       timeout=30)
                slash_budget.apply_slash_budget(bot.tree)
            except Exception as e:
                failed[f] = f'{type(e).__name__}: {e}'
        slash_budget.apply_slash_budget(bot.tree)

        scopes = {'GLOBAL': None}
        if with_guild:
            scopes[f'GUILD'] = discord.Object(id=GUILD_ID)
        snap = {}
        for label, sc in scopes.items():
            try:
                top = bot.tree.get_commands(guild=sc)
            except TypeError:
                top = bot.tree.get_commands()
            nodes = list(_walk(top))
            snap[label] = {
                'top': [c.name for c in top
                        if not isinstance(c, app_commands.ContextMenu)],
                'all': [n for n, c in nodes
                        if not isinstance(c, app_commands.ContextMenu)],
                'ctx': [(c.name, c.type.name) for _n, c in nodes
                        if isinstance(c, app_commands.ContextMenu)],
            }
        prefix_names = []

        def _wp(cmds, pre=''):
            for c in cmds:
                prefix_names.append(f'{pre}{c.name}')
                if isinstance(c, commands.Group):
                    _wp(c.commands, f'{pre}{c.name} ')

        _wp(bot.commands)

        # алиасы против имён в ОДНОМ пространстве имён
        alias_clash = []

        def _lvl(cmdlist, path=''):
            seen = defaultdict(list)
            for c in cmdlist:
                seen[c.name].append(f'имя {c.qualified_name}')
                for a in c.aliases:
                    seen[a].append(f'алиас {c.qualified_name}')
            for n, who in seen.items():
                if len(who) > 1:
                    alias_clash.append(f'{path}{n}: {who}')
            for c in cmdlist:
                if isinstance(c, commands.Group):
                    _lvl(list(c.commands), f'{c.qualified_name} > ')

        _lvl(list(bot.commands))
    return failed, snap, prefix_names, alias_clash


for label, env in PROFILES.items():
    for with_guild in (False, True):
        tag = f'{label} · MAIN_GUILD_ID={"777" if with_guild else "(пусто)"}'
        failed, snap, prefix_names, alias_clash = asyncio.run(_load(env, with_guild))

        dup_err = {f: e for f, e in failed.items()
                   if 'AlreadyRegistered' in e or 'already loaded' in e}
        check(not dup_err, f'{tag}: нет падений из-за дублей ({dup_err})')
        check(not failed, f'{tag}: все коги загрузились ({sorted(failed)})')

        for scope, data in snap.items():
            d = [n for n, k in Counter(data['all']).items() if k > 1]
            check(not d, f'{tag}: {scope} — нет повторов имён в дереве ({d})')
            check(len(data['top']) <= slash_budget.LIMIT,
                  f'{tag}: {scope} — {len(data["top"])} команд ≤ лимита Discord 100')
            dctx = [n for n, k in Counter(data['ctx']).items() if k > 1]
            check(not dctx, f'{tag}: {scope} — контекстные меню без дублей ({dctx})')

        if 'GUILD' in snap:
            both = sorted(set(snap['GLOBAL']['top']) & set(snap['GUILD']['top']))
            check(not both,
                  f'{tag}: ни одна команда не лежит и в глобальном, и в серверном '
                  f'меню — иначе в Discord она двоится ({both})')

        pd = [n for n, k in Counter(prefix_names).items() if k > 1]
        check(not pd, f'{tag}: префиксные команды без дублей ({pd})')
        check(not alias_clash, f'{tag}: алиасы не перекрывают имена ({alias_clash})')

# ─────────────────────────────────────────────────────────────────────────
# 3. main.py стартует до входа в Discord (без токена — падение на login)
# ─────────────────────────────────────────────────────────────────────────
print('== 3. main.py доходит до подключения без ошибок загрузки ==')
env = dict(os.environ)
env.update({'BOT_FULL': '1', 'TOKEN': '', 'SECRET_KEY': 'test-secret',
            'WS_PORT': '8791', 'WEB_PORT': '5091', 'QUICK_TUNNEL': '0'})
for v in ('MOD_ONLY', 'BOT_SLIM', 'BOT_CORE', 'MAIN_GUILD_ID'):
    env.pop(v, None)
try:
    proc = subprocess.run([sys.executable, os.path.join(ROOT, 'main.py')],
                          cwd=ROOT, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=300)
    out = proc.stdout.decode('utf-8', errors='replace')
    check('CommandAlreadyRegistered' not in out,
          'в логе старта нет CommandAlreadyRegistered')
    check('CommandLimitReached' not in out,
          'в логе старта нет CommandLimitReached (переполнение меню)')
    check('Ошибка загрузки кога' not in out,
          'в логе старта нет «Ошибка загрузки кога»')
    # без токена бот обязан честно сказать об этом и выйти кодом 7
    check(proc.returncode == 7 and 'Токен не найден' in out,
          f'без TOKEN бот внятно ругается и выходит (код {proc.returncode})')
except subprocess.TimeoutExpired:
    check(False, 'main.py не завершился за 300с')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
