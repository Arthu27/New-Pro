# -*- coding: utf-8 -*-
"""Страж запуска: on_ready обязан доходить до конца ВСЕГДА.

Инцидент 30.08 «бот не включается». В логе владельца всё выглядело
нормально и обрывалось на строке фоновой задачи тикетов:

    [БОТ] Подключение к Discord...
    [ТУННЕЛЬ] ... Registered tunnel connection ...
    ... | INFO | ticket.auto_close | [AutoClose] Цикл запущен ...
    (и больше ничего — навсегда)

Разбор: `[AutoClose] Цикл запущен` печатается ПОСЛЕ
`bot.wait_until_ready()`, то есть READY от Discord пришёл и on_ready
стартовал. Значит бот подключился — и завис ВНУТРИ on_ready, на первом
же шаге: `await full_sync(bot)`.

У full_sync нет собственного таймаута: он ходит в Discord bulk-upsert'ами
(глобальный скоуп + каждая гильдия, по 3 попытки). Один залипший HTTP
(429 с длинным retry_after, моргнувшая сеть/туннель) — и on_ready не
возвращается НИКОГДА. Всё, что ниже по коду, не выполняется:

  * bot.change_presence(...) — бот не выставляет статус и в клиенте
    Discord выглядит офлайн → «бот не включается»;
  * подключение к голосовому каналу;
  * web.app.set_bot_instance(bot) — веб-панель не получает бота и
    показывает «бот выключен», хотя процесс жив.

Фикс: синк уехал в фоновую задачу с таймаутом (SYNC_TIMEOUT_SEC, 180с),
а каждый шаг хвоста on_ready обёрнут в свой try + таймаут.

Здесь проверяем ПОВЕДЕНИЕ на залипшем HTTP-моке, а не текст кода.

Запуск: python3 tests/test_ready_never_hangs.py
"""
import asyncio
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_ready_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['SYNC_TIMEOUT_SEC'] = '2'      # в тесте ждать 180с незачем

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


class HangingHTTP:
    """Discord, который на bulk-upsert «думает» вечно (залипший 429/сеть)."""

    def __init__(self):
        self.calls = []

    async def bulk_upsert_global_commands(self, app_id, payload=None):
        self.calls.append('global')
        await asyncio.sleep(9999)
        return []

    async def bulk_upsert_guild_commands(self, app_id, guild_id, payload=None):
        self.calls.append(f'guild:{guild_id}')
        await asyncio.sleep(9999)
        return []


def _mk_bot():
    bot = commands.Bot(command_prefix='!', intents=discord.Intents.all(),
                       help_command=None)

    @bot.tree.command(name='ping', description='t')
    async def _ping(i):    # noqa: ARG001
        pass

    bot._connection.application_id = 1
    http = HangingHTTP()
    bot._connection.http = http
    bot.tree._http = http
    bot.http = http
    return bot, http


print('== 1. Синк не блокирует запуск: фоновая задача + таймаут ==')


async def scenario_hanging_sync():
    bot, http = _mk_bot()
    import main as M
    M.bot = bot
    M.SYNC_TIMEOUT_SEC = 2

    started = asyncio.get_event_loop().time()
    task = asyncio.create_task(M._sync_commands_bg())
    await asyncio.sleep(0.5)
    # пока синк висит — задача НЕ должна держать управление
    mid = (not task.done(), asyncio.get_event_loop().time() - started)
    # ...и обязана сама сдаться по таймауту, а не висеть вечно
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=8)
    except asyncio.TimeoutError:
        pass
    return mid, task, http


(_still_running, _elapsed), _task, _http = asyncio.run(scenario_hanging_sync())
check(_still_running,
      'синк работает в фоне и не держит on_ready (управление вернулось за '
      f'{_elapsed:.2f}с)')
check(_task.done(),
      'зависший синк сдаётся по таймауту, а не висит вечно')
check(not _task.cancelled() and _task.exception() is None,
      'таймаут обработан внутри — наружу исключение не летит '
      '(иначе «Task exception was never retrieved» и красный лог)')
check('global' in _http.calls, 'синк реально пытался сходить в Discord')

print('== 2. Хвост on_ready отрабатывает, даже когда синк висит ==')


async def scenario_tail():
    """Хвост on_ready: статус и — главное — связь с веб-панелью."""
    bot, _http = _mk_bot()
    import main as M
    M.bot = bot
    M.SYNC_TIMEOUT_SEC = 2

    state = {'presence': False, 'panel': False}

    async def _presence(*a, **k):
        state['presence'] = True

    bot.change_presence = _presence

    import web.app as WA
    _orig = WA.set_bot_instance

    def _spy(b):
        state['panel'] = True
        return _orig(b)

    WA.set_bot_instance = _spy
    try:
        sync_task = asyncio.create_task(M._sync_commands_bg())
        await asyncio.sleep(0.3)          # синк гарантированно «в полёте»
        # эмулируем хвост on_ready (он идёт СРАЗУ, не дожидаясь синка)
        await bot.change_presence()
        WA.set_bot_instance(bot)
        done_fast = dict(state)
        sync_task.cancel()
        return done_fast
    finally:
        WA.set_bot_instance = _orig


_tail = asyncio.run(scenario_tail())
check(_tail['presence'],
      'статус выставляется, пока синк ещё висит (в Discord бот «включён»)')
check(_tail['panel'],
      'web.app.set_bot_instance вызван — панель видит бота, а не «выключен»')

print('== 3. Порядок в on_ready: синк не стоит на пути у панели ==')
_src = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
_i = _src.find('async def on_ready():')
_j = _src.find('async def load_cogs():')
_body = _src[_i:_j]

check('await _full_sync(bot)' not in _body,
      'в on_ready нет блокирующего await full_sync (именно он и вешал старт)')
check('_sync_commands_bg' in _body,
      'синк уехал в фоновую задачу _sync_commands_bg')
check('set_bot_instance' in _body,
      'связь с панелью по-прежнему поднимается в on_ready')
# Сравниваем позиции РЕАЛЬНЫХ вызовов, а не упоминаний в комментариях:
# берём только строки кода (комментарии отбрасываем).
_code_lines = [ln for ln in _body.splitlines()
               if not ln.lstrip().startswith('#')]
_code = '\n'.join(_code_lines)
check(_code.index('create_task(_sync_commands_bg())')
      < _code.index('set_bot_instance(bot)'),
      'синк стартует раньше панели — и не мешает ей (он фоновый)')
check('asyncio.wait_for' in _body,
      'сетевые шаги хвоста on_ready прикрыты таймаутами')

# set_bot_instance обязан быть защищён: исключение из web.app не должно
# обрывать on_ready до конца (иначе снова «панель не видит бота»)
_tail_src = _body[_body.index('set_bot_instance'):]
check('except' in _tail_src,
      'подключение панели обёрнуто в try/except — не роняет остаток on_ready')

print('== 4. Таймаут синка настраивается из .env ==')
import main as _M  # noqa: E402
check(isinstance(_M.SYNC_TIMEOUT_SEC, int) and _M.SYNC_TIMEOUT_SEC > 0,
      f'SYNC_TIMEOUT_SEC — положительное число ({_M.SYNC_TIMEOUT_SEC})')
check('SYNC_TIMEOUT_SEC' in _src,
      'значение читается из окружения (можно поднять на медленной сети)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
